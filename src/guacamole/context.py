"""Source-preserving context selection and provider-specific token accounting."""

import asyncio
import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import JsonValue

from .activity import Activity
from .contracts import (
    JSON,
    AgentSpec,
    AgentTurn,
    ContextPacket,
    FileRecord,
    ImageAttachment,
    InboxEntry,
    Omission,
    Ref,
    uid,
)
from .storage import Snapshot, Store
from .tools.registry import ToolRegistry, encode

# Prompt fields from least to most volatile. Each group but the last ends a prefix
# providers may cache: the first changes with an agent's role and grants, the second
# when it reads or records something, the last every turn.
LAYOUT = (
    (
        "instructions",
        "response_schema",
        "result_schema",
        "tool_schemas",
        "catalogue",
        "user_instructions",
    ),
    ("agent", "sources"),
    ("memory", "messages", "state"),
)
# Frames a stable prefix that a CLI provider sends with its system instructions.
CONTINUED = (
    "The context packet is one JSON object. It begins below, and the user message "
    "continues it.\n"
)
# Image files a provider may receive as pixels. Anthropic limits an image to 5 MiB
# of base64 text (about 3.9 MB of file) and, past 20 images, to 2,000 px a side.
IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
MAX_IMAGE_BYTES = 3_750_000
MAX_IMAGES = 20
# ponytail: one generous estimate per image for every provider, since each scales
# large images down; count by pixel size if images crowd budgets.
IMAGE_TOKENS = 5_000


class ReasoningProvider(Protocol):
    name: str
    model: str
    context_capacity_tokens: int
    # Optional image_tokens: estimated input per attached image. Absent or None,
    # the provider takes no images and image sources arrive as records only.

    async def count_tokens(self, prompt: str) -> int: ...
    async def respond(self, packet: ContextPacket) -> AgentTurn: ...


class ContextOverflow(ValueError):
    pass


class ProviderError(RuntimeError):
    """A locally constructed provider diagnostic safe to persist without secrets."""


def image_data(image: ImageAttachment) -> bytes:
    """An attached image's bytes, refused if they changed since context assembly."""
    try:
        data = Path(image.path).read_bytes()
    except OSError:
        data = b""
    if hashlib.sha256(data).hexdigest() != image.sha256:
        raise ProviderError(
            f"Image {image.source.kind}:{image.source.id} is missing or changed since "
            "its context was assembled; no action executed"
        )
    return data


def preview(value: JsonValue, limit: int) -> JsonValue:
    """value within about limit encoded characters, keeping its structure.

    Short fields stay verbatim, so a status beside a long log survives; long
    strings, lists and objects end in a marker counting what was cut.
    """
    if len(encode(value)) <= limit:
        return value
    room = limit - 24  # Left for content once the marker is in
    if isinstance(value, str):
        keep = max(room, 0)
        # Escapes make encoded text longer than the characters kept.
        while keep and (size := len(encode(value[:keep]))) > room:
            keep = keep * room // size
        return f"{value[:keep]}…[{len(value) - keep} more chars]"
    if isinstance(value, list):
        items: list[JsonValue] = []
        for item in value:
            part = preview(item, room)
            if len(encode(part)) + 1 > room:
                break
            items.append(part)
            room -= len(encode(part)) + 1
        cut = len(value) - len(items)
        return [*items, f"…[{cut} more items]"] if cut else items
    if isinstance(value, dict):
        # Smallest first: short fields stay whole, long ones share what is left.
        fields: dict[str, JsonValue] = {}
        order = sorted(value, key=lambda key: len(encode(value[key])))
        for index, key in enumerate(order):
            overhead = len(encode(key)) + 2
            share = max(room // (len(order) - index), 64)
            part = preview(value[key], share - overhead)
            if len(encode(part)) + overhead > room:
                break
            fields[key] = part
            room -= len(encode(part)) + overhead
        shown: dict[str, JsonValue] = {k: fields[k] for k in value if k in fields}
        if len(fields) < len(value):
            shown["…"] = f"[{len(value) - len(fields)} more fields]"
        return shown
    return value


def _referenced(payload: dict) -> dict:
    """Show older decisions' embedded evidence snapshots as refs, as newer ones store.

    A snapshot embeds earlier decisions with their own snapshots, so whole ones
    outgrow provider input limits (one ehopper decision reached 1.5M characters).
    """
    sources = []
    for source in payload["sources"]:
        data = source["data"]
        if source["ref"]["kind"] == "decision":
            request = data["request"]
            context = [entry.get("ref", entry) for entry in request["context"]]
            source = source | {
                "data": data | {"request": request | {"context": context}}
            }
        sources.append(source)
    return payload | {"sources": sources}


def _render(data: dict) -> tuple[str, tuple[int, ...]]:
    """Encode data in LAYOUT order; return the prompt and its cacheable prefix lengths."""
    known = {key for group in LAYOUT for key in group}
    groups = (*LAYOUT[:-1], (*LAYOUT[-1], *sorted(data.keys() - known)))
    fields: list[str] = []
    ends: list[int] = []
    length = 1  # The opening brace
    for group in groups:
        for key in group:
            if key in data:
                fields.append(f"{encode(key)}:{encode(data[key])}")
                length += len(fields[-1]) + 1  # The field and the comma after it
        ends.append(length)
    prompt = "{" + ",".join(fields) + "}"
    return prompt, tuple(sorted({end for end in ends[:-1] if 1 < end < len(prompt)}))


def _components(data: dict, pinned: set[tuple[str, str]]) -> dict[str, int]:
    """Characters per prompt component; state and sources are split further."""
    sizes: dict[str, int] = {}
    for key, value in data.items():
        if key == "state":
            sizes |= {f"state.{k}": len(encode(v)) for k, v in value.items()}
        elif key == "sources":
            held = [(s["ref"]["kind"], s["ref"]["id"]) in pinned for s in value]
            sizes["sources.pinned"] = sum(
                len(encode(s)) for s, p in zip(value, held) if p
            )
            sizes["sources.selected"] = sum(
                len(encode(s)) for s, p in zip(value, held) if not p
            )
        else:
            sizes[key] = len(encode(value))
    return sizes


def encode_context(payload: dict) -> str:
    """The prompt for payload: stable fields first, included evidence referenced once."""
    return _render(_referenced(payload))[0]


class ContextBuilder:
    def __init__(
        self,
        store: Store,
        activity: Activity,
        registry: ToolRegistry,
        files: Callable[[FileRecord], Path],
    ) -> None:
        """files returns a stored file's verified path, as Project.verify_file does."""
        self.store, self.activity, self.registry = store, activity, registry
        self.files = files

    def search(self, query: str, limit: int = 8) -> tuple[Ref, ...]:
        words = query.casefold().split()
        if not words:
            return ()
        scored = []
        for snapshot in self.store.list(
            "source", "artifact", "requirement", "evidence", "summary"
        ):
            if snapshot.stale:
                continue
            text = encode(snapshot.data).casefold()
            score = sum(text.count(word) for word in words)
            if score:
                scored.append((score, snapshot.ref))
        scored.sort(key=lambda item: item[0], reverse=True)
        return tuple(ref for _, ref in scored[:limit])

    async def build(
        self,
        agent: AgentSpec,
        request_id: str,
        provider: ReasoningProvider,
        *,
        instructions: str,
        state: JSON,
        memory: Sequence[JSON] = (),
        omissions: Sequence[Omission] = (),
        catalogue: bool = False,
    ) -> ContextPacket:
        loop = asyncio.get_running_loop()

        def count(prompt: str) -> int:
            return asyncio.run_coroutine_threadsafe(
                provider.count_tokens(prompt), loop
            ).result()

        def assemble() -> ContextPacket:
            # Assembly takes seconds on large projects; a private read connection keeps
            # it off the event loop so the WebSocket control endpoint stays responsive.
            reader = Store(self.store.directory, read_only=True)
            try:
                builder = ContextBuilder(
                    reader, Activity(reader, self.registry), self.registry, self.files
                )
                return builder._assemble(
                    agent,
                    request_id,
                    provider,
                    count,
                    instructions=instructions,
                    state=state,
                    memory=memory,
                    deferred=omissions,
                    catalogue=catalogue,
                )
            finally:
                reader.close()

        packet = await asyncio.to_thread(assemble)
        try:
            return self._save(packet)
        except ValueError:
            # A concurrent write staled a selected source during assembly; rebuild once.
            return self._save(await asyncio.to_thread(assemble))

    def _assemble(
        self,
        agent: AgentSpec,
        request_id: str,
        provider: ReasoningProvider,
        count_tokens: Callable[[str], int],
        *,
        instructions: str,
        state: JSON,
        memory: Sequence[JSON] = (),
        deferred: Sequence[Omission] = (),
        catalogue: bool = False,
    ) -> ContextPacket:
        spec = agent.context
        max_chars = getattr(provider, "max_input_chars", None)
        if (
            spec.max_input_tokens + spec.reserved_output_tokens
            > provider.context_capacity_tokens
        ):
            raise ContextOverflow(
                "Input budget plus reserved output exceeds the configured provider capacity"
            )
        sources: list[Any] = []  # Snapshot dumps, as rendered
        payload = {
            "instructions": instructions,
            "user_instructions": spec.instructions,
            # Its context lists repeat user_instructions and the sources' refs, and
            # changed on every read, voiding the cached prefix through the sources.
            "agent": agent.model_dump(
                mode="json",
                exclude={
                    "context": {"instructions", "pinned", "selected", "summaries"}
                },
            ),
            "state": state,
            "tool_schemas": [
                t.model_dump(mode="json")
                for t in self.registry.definitions(agent.tools)
            ],
            "result_schema": self.registry.schemas[agent.result_schema].json_schema(),
            "response_schema": AgentTurn.model_json_schema(),
            "sources": sources,
            "messages": [],
        }
        if catalogue:
            # The Chief plans with every registered tool; its own are in tool_schemas.
            payload["catalogue"] = [
                t.model_dump(mode="json")
                for t in self.registry.definitions()
                if t.grant not in agent.tools
            ]
        omissions = list(deferred)
        per_image = getattr(provider, "image_tokens", None)
        images: dict[str, ImageAttachment] = {}  # By "kind:id"

        def source(ref: Ref, snapshot: Snapshot) -> JSON:
            """A source as shown; an image file's pixels are attached, or it says why not."""
            shown = snapshot.model_dump(mode="json") | {"locator": ref.locator}
            data = (
                snapshot.data.get("file") if ref.kind == "artifact" else snapshot.data
            )
            if (
                ref.kind not in {"source", "job_file", "artifact"}
                or not isinstance(data, dict)
                or data.get("media_type") not in IMAGE_TYPES
            ):
                return shown
            file = FileRecord.model_validate_json(encode(data))
            if per_image is None:
                reason = f"{provider.model} via {provider.name} accepts no images"
            elif len(images) >= MAX_IMAGES:
                reason = f"{MAX_IMAGES} per turn, pinned then newest reads first"
            else:
                try:
                    path = self.files(file)
                    size = path.stat().st_size
                except (OSError, ValueError):
                    reason = "file is missing or changed since it was recorded"
                else:
                    if size <= MAX_IMAGE_BYTES:
                        images[f"{ref.kind}:{ref.id}"] = ImageAttachment(
                            source=ref,
                            path=str(path),
                            sha256=file.sha256,
                            media_type=file.media_type,
                        )
                        return shown | {"image": "attached"}
                    reason = f"file exceeds {MAX_IMAGE_BYTES:,} bytes"
            omissions.append(
                Omission(
                    item=f"{ref.kind}:{ref.id}@{ref.revision}",
                    reason=f"Image not attached: {reason}",
                )
            )
            return shown | {"image": f"not attached: {reason}"}

        def attached() -> list[ImageAttachment]:
            """Attached images among the prompt's sources, in prompt order."""
            return [
                image
                for s in sources
                if (image := images.get(f"{s['ref']['kind']}:{s['ref']['id']}"))
            ]

        def measure(prompt: str) -> int:
            return count_tokens(prompt) + len(attached()) * (per_image or 0)

        refs: list[Ref] = []
        for ref in spec.pinned:
            snapshot = self.store.resolve(ref, current=True)
            payload["sources"].append(source(ref, snapshot))
            refs.append(ref)
        prompt = encode_context(payload)
        if max_chars is not None and len(prompt) > max_chars:
            raise ContextOverflow(
                f"Pinned context and contracts require {len(prompt)} characters; "
                f"provider input limit is {max_chars}"
            )
        count = measure(prompt)
        if count > spec.max_input_tokens:
            raise ContextOverflow(
                f"Pinned context and contracts require {count} input tokens; budget is {spec.max_input_tokens}"
            )

        def admit(target: list, entries: Sequence) -> set[int]:
            """Append entries in priority order while the prompt fits; return the rest.

            A run of entries is measured whole and bisected only when it overflows,
            so a context that fits costs one count instead of one per entry.
            """
            nonlocal count
            rejected: set[int] = set()
            start, base = 0, len(target)
            while start < len(entries):
                # entries[start:fit] fits; nothing longer than entries[start:cap] can.
                fit, cap, probe = start, len(entries), len(entries)
                while fit < cap:
                    target[base:] = entries[start:probe]
                    prompt = encode_context(payload)
                    measured = (
                        None
                        if max_chars is not None and len(prompt) > max_chars
                        else measure(prompt)
                    )
                    if measured is not None and measured <= spec.max_input_tokens:
                        fit, count = probe, measured
                    else:
                        cap = probe - 1
                    probe = (fit + cap + 1) // 2
                target[base:] = entries[start:fit]
                base += fit - start
                if fit < len(entries):
                    rejected.add(fit)
                start = fit + 1
            return rejected

        # New messages first. Inclusion is never acknowledgement.
        entries = sorted(
            self.activity.inbox(agent.id),
            key=lambda e: (
                not e.message.sender.startswith("human:"),
                bool(e.included_packets),
                e.message.created_at,
            ),
        )
        # An answered message is settled even if never acknowledged; showing it
        # again made agents reply to it again. One still owed a reply stays after
        # acknowledgement; hiding it left finish rejected with nothing to answer.
        owed = {e.message.id for e in self.activity.obligations(agent.id)}
        pinned = {(r.kind, r.id) for r in refs}
        pending = [
            e
            for e in entries
            if e.delivered_at is not None
            and e.response_message_id is None
            and (e.acknowledged_at is None or e.message.id in owed)
            and (e.message.id in owed or not self._carried(e, pinned))
        ]
        rejected = admit(
            payload["messages"], [e.message.model_dump(mode="json") for e in pending]
        )
        for index in sorted(rejected):
            if pending[index].message.sender.startswith("human:"):
                raise ContextOverflow(
                    "Human input exceeds the context budget or provider input limit; "
                    "reduce context before continuing"
                )
            omissions.append(
                Omission(
                    item=pending[index].message.id,
                    reason="Inbox message exceeds remaining input budget or provider input limit; remains pending",
                )
            )
        messages = [e.message.id for i, e in enumerate(pending) if i not in rejected]
        selected = (
            *spec.selected,
            *spec.summaries,
            *self.search(spec.search, spec.max_search_results),
        )
        seen = {(r.kind, r.id) for r in refs}
        candidates: list[tuple[Ref, JSON]] = []
        for ref in selected:
            # A current pinned revision supersedes an older selected version.
            if (ref.kind, ref.id) in seen:
                continue
            try:
                snapshot = self.store.resolve(ref, current=True)
            except ValueError:
                omissions.append(
                    Omission(
                        item=f"{ref.kind}:{ref.id}@{ref.revision}",
                        reason="Selected reference is unknown, mismatched, or stale",
                    )
                )
                continue
            seen.add((ref.kind, ref.id))
            candidates.append((ref, source(ref, snapshot)))
        rejected = admit(payload["sources"], [data for _, data in candidates])
        for index, (ref, _) in enumerate(candidates):
            if index in rejected:
                omissions.append(
                    Omission(
                        item=f"{ref.kind}:{ref.id}@{ref.revision}",
                        reason="Selected source exceeds remaining input budget or provider input limit",
                    )
                )
            else:
                refs.append(ref)
        # Admission favours the newest reads, but they render last, oldest first: a
        # read then extends the prompt instead of shifting every source after it out
        # of the provider's cached prefix. Sources that are not reads lead.
        age = {(r.kind, r.id): i for i, r in enumerate(reversed(spec.selected))}
        payload["sources"].sort(
            key=lambda s: age.get((s["ref"]["kind"], s["ref"]["id"]), -1)
        )
        # Middleware recall is the lowest-priority optional material.
        if memory:
            recalled: list[JSON] = []
            payload["memory"] = recalled
            rejected = admit(recalled, memory)
            if not recalled:
                del payload["memory"]  # Keep the prompt the one last measured.
            omissions.extend(
                Omission(
                    item=f"memory:{memory[i].get('source')}:{memory[i].get('id')}",
                    reason="Recalled memory exceeds remaining input budget or provider input limit",
                )
                for i in sorted(rejected)
            )
        data = _referenced(payload)
        prompt, breakpoints = _render(data)
        packet = ContextPacket(
            agent_id=agent.id,
            invocation_id=uid(),
            request_id=request_id,
            provider=provider.name,
            model=provider.model,
            prompt=prompt,
            input_tokens=count,
            token_count_method=getattr(provider, "token_count_method", "exact"),
            reserved_output_tokens=spec.reserved_output_tokens,
            sources=tuple(refs),
            images=tuple(attached()),
            message_ids=tuple(messages),
            deferred=tuple(omissions),
            cache_breakpoints=breakpoints,
            components=_components(data, pinned),
        )
        return packet

    def _carried(self, entry: InboxEntry, pinned: set[tuple[str, str]]) -> bool:
        """Whether a message already shown is now carried elsewhere or moot.

        A human input is pinned as its source; a superseded sender awaits nothing.
        Left until acknowledged, the Chief re-read both every turn for weeks.
        """
        message = entry.message
        if not entry.included_packets:
            return False
        if message.sender.startswith("human:"):
            return bool(message.context_refs) and all(
                (r.kind, r.id) in pinned for r in message.context_refs
            )
        sender = self.store.maybe("agent_state", message.sender)
        return sender is not None and sender.data["status"] == "superseded"

    def _save(self, packet: ContextPacket) -> ContextPacket:
        with self.store.atomic():
            self.store.put(
                "context",
                packet.id,
                packet,
                actor="runtime",
                dependencies=packet.sources,
                request_id=packet.request_id,
                event="context.saved",
            )
            for message_id in packet.message_ids:
                self.activity.included(packet.agent_id, message_id, packet.id)
        return packet
