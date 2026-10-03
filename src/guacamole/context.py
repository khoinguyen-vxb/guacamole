"""Source-preserving context selection and provider-specific token accounting."""

import asyncio
from collections.abc import Callable
from typing import Protocol

from .activity import Activity
from .contracts import (
    JSON,
    AgentSpec,
    AgentTurn,
    ContextPacket,
    Omission,
    Ref,
    uid,
)
from .storage import Store
from .tools.registry import ToolRegistry, encode


class ReasoningProvider(Protocol):
    name: str
    model: str
    context_capacity_tokens: int

    async def count_tokens(self, prompt: str) -> int: ...
    async def respond(self, packet: ContextPacket) -> AgentTurn: ...


class ContextOverflow(ValueError):
    pass


class ProviderError(RuntimeError):
    """A locally constructed provider diagnostic safe to persist without secrets."""


class ContextBuilder:
    def __init__(
        self, store: Store, activity: Activity, registry: ToolRegistry
    ) -> None:
        self.store, self.activity, self.registry = store, activity, registry

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
                    reader, Activity(reader, self.registry), self.registry
                )
                return builder._assemble(
                    agent,
                    request_id,
                    provider,
                    count,
                    instructions=instructions,
                    state=state,
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
    ) -> ContextPacket:
        spec = agent.context
        if (
            spec.max_input_tokens + spec.reserved_output_tokens
            > provider.context_capacity_tokens
        ):
            raise ContextOverflow(
                "Input budget plus reserved output exceeds the configured provider capacity"
            )
        payload = {
            "instructions": instructions,
            "user_instructions": spec.instructions,
            "agent": agent.model_dump(mode="json"),
            "state": state,
            "tool_schemas": [
                t.model_dump(mode="json")
                for t in self.registry.definitions(agent.tools)
            ],
            "result_schema": self.registry.schemas[agent.result_schema].json_schema(),
            "response_schema": AgentTurn.model_json_schema(),
            "sources": [],
            "messages": [],
        }
        refs: list[Ref] = []
        for ref in spec.pinned:
            snapshot = self.store.resolve(ref, current=True)
            payload["sources"].append(
                snapshot.model_dump(mode="json") | {"locator": ref.locator}
            )
            refs.append(ref)
        count = count_tokens(encode(payload))
        if count > spec.max_input_tokens:
            raise ContextOverflow(
                f"Pinned context and contracts require {count} input tokens; budget is {spec.max_input_tokens}"
            )
        omissions: list[Omission] = []
        messages: list[str] = []
        # New messages first. Inclusion is never acknowledgement.
        entries = sorted(
            self.activity.inbox(agent.id),
            key=lambda e: (
                not e.message.sender.startswith("human:"),
                bool(e.included_packets),
                e.message.created_at,
            ),
        )
        for entry in entries:
            if entry.delivered_at is None or entry.acknowledged_at is not None:
                continue
            payload["messages"].append(entry.message.model_dump(mode="json"))
            measured = count_tokens(encode(payload))
            if measured <= spec.max_input_tokens:
                count = measured
                messages.append(entry.message.id)
            else:
                payload["messages"].pop()
                if entry.message.sender.startswith("human:"):
                    raise ContextOverflow(
                        "Human input exceeds the context budget; increase the budget before continuing"
                    )
                omissions.append(
                    Omission(
                        item=entry.message.id,
                        reason="Inbox message exceeds remaining input budget; remains pending",
                    )
                )
        selected = (
            *spec.selected,
            *spec.summaries,
            *self.search(spec.search, spec.max_search_results),
        )
        for ref in selected:
            # A current pinned revision supersedes an older selected version.
            if any((r.kind, r.id) == (ref.kind, ref.id) for r in refs):
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
            payload["sources"].append(
                snapshot.model_dump(mode="json") | {"locator": ref.locator}
            )
            measured = count_tokens(encode(payload))
            if measured <= spec.max_input_tokens:
                count = measured
                refs.append(ref)
            else:
                payload["sources"].pop()
                omissions.append(
                    Omission(
                        item=f"{ref.kind}:{ref.id}@{ref.revision}",
                        reason="Selected source exceeds remaining input budget",
                    )
                )
        packet = ContextPacket(
            agent_id=agent.id,
            invocation_id=uid(),
            request_id=request_id,
            provider=provider.name,
            model=provider.model,
            prompt=encode(payload),
            input_tokens=count,
            token_count_method=getattr(provider, "token_count_method", "exact"),
            reserved_output_tokens=spec.reserved_output_tokens,
            sources=tuple(refs),
            message_ids=tuple(messages),
            deferred=tuple(omissions),
        )
        return packet

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
