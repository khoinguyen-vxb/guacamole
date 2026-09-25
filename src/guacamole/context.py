"""Source-preserving context selection and exact provider token accounting."""

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


class ContextBuilder:
    def __init__(
        self, store: Store, activity: Activity, registry: ToolRegistry
    ) -> None:
        self.store, self.activity, self.registry = store, activity, registry

    def search(self, query: str, limit: int = 8) -> tuple[Ref, ...]:
        words = query.casefold().split()
        matches = [
            s
            for s in self.store.list()
            if not s.stale
            and s.ref.kind
            in {"source", "artifact", "requirement", "evidence", "summary"}
        ]
        ranked = sorted(
            matches,
            key=lambda s: sum(encode(s.data).casefold().count(word) for word in words),
            reverse=True,
        )
        return tuple(
            s.ref
            for s in ranked
            if any(word in encode(s.data).casefold() for word in words)
        )[:limit]

    async def build(
        self,
        agent: AgentSpec,
        request_id: str,
        provider: ReasoningProvider,
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
        count = await provider.count_tokens(encode(payload))
        if count > spec.max_input_tokens:
            raise ContextOverflow(
                f"Pinned context and contracts require {count} input tokens; budget is {spec.max_input_tokens}"
            )
        omissions: list[Omission] = []
        messages: list[str] = []
        # New messages first. Inclusion is never acknowledgement.
        entries = sorted(
            self.activity.inbox(agent.id),
            key=lambda e: (bool(e.included_packets), e.message.created_at),
        )
        for entry in entries:
            if entry.delivered_at is None or entry.acknowledged_at is not None:
                continue
            payload["messages"].append(entry.message.model_dump(mode="json"))
            measured = await provider.count_tokens(encode(payload))
            if measured <= spec.max_input_tokens:
                count = measured
                messages.append(entry.message.id)
            else:
                payload["messages"].pop()
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
            if ref in refs:
                continue
            snapshot = self.store.resolve(ref, current=True)
            payload["sources"].append(
                snapshot.model_dump(mode="json") | {"locator": ref.locator}
            )
            measured = await provider.count_tokens(encode(payload))
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
            reserved_output_tokens=spec.reserved_output_tokens,
            sources=tuple(refs),
            message_ids=tuple(messages),
            deferred=tuple(omissions),
        )
        with self.store.atomic():
            self.store.put(
                "context",
                packet.id,
                packet,
                actor="runtime",
                dependencies=tuple(refs),
                request_id=request_id,
                event="context.saved",
            )
            for message_id in messages:
                self.activity.included(agent.id, message_id, packet.id)
        return packet
