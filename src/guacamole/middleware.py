"""Context middleware around each agent invocation: memory, summarization, editing.

Pass instances to Project(middleware=...). before_model runs before the agent's
context is assembled; after_model runs after its action executes. Failures are
recorded as middleware.failed events and never stop the run. Pinned material is
never shown to a middleware; anything removed is cited or recorded as deferred.
"""

import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .contracts import JSON, AgentSpec, AgentTurn, Omission, Ref, Summary
from .tools.registry import encode

if TYPE_CHECKING:
    from graphiti_core import Graphiti
    from langchain.agents.middleware.types import AgentMiddleware
    from mem0 import AsyncMemory

    from .project import Project

# ponytail: turns are truncated for memory extraction; full records stay in the store.
_MEMORY_CHARS = 16_000


@dataclass
class Invocation:
    """One agent invocation as seen by middleware."""

    project: "Project"
    agent: AgentSpec  # Effective spec for this call; before_model may replace it.
    query: str  # Agent objective and last observation, for recall.
    memory: list[JSON] = field(default_factory=list)  # Optional recalled items.
    omissions: list[Omission] = field(default_factory=list)


class ContextMiddleware:
    async def before_model(self, call: Invocation) -> None:
        pass

    async def after_model(
        self, call: Invocation, turn: AgentTurn, observation: JSON
    ) -> None:
        pass


def _turn(call: Invocation, turn: AgentTurn, observation: JSON) -> str:
    return encode(
        {
            "agent": call.agent.task_id,
            "rationale": turn.rationale.model_dump(mode="json"),
            "action": turn.action.model_dump(mode="json"),
            "observation": observation,
        }
    )[:_MEMORY_CHARS]


class Mem0Memory(ContextMiddleware):
    """Per-task long-term memory: recall before each call, remember each turn."""

    def __init__(self, memory: "AsyncMemory", *, limit: int = 5) -> None:
        self.memory, self.limit = memory, limit

    # Scoped by task, so replacement workers for a task share its memories.
    async def before_model(self, call: Invocation) -> None:
        found = await self.memory.search(
            call.query,
            top_k=self.limit,
            filters={
                "user_id": call.project.store.project_id,
                "agent_id": call.agent.task_id,
            },
        )
        call.memory.extend(
            {"source": "mem0", "id": item["id"], "text": item["memory"]}
            for item in found["results"]
        )

    async def after_model(
        self, call: Invocation, turn: AgentTurn, observation: JSON
    ) -> None:
        await self.memory.add(
            [{"role": "assistant", "content": _turn(call, turn, observation)}],
            user_id=call.project.store.project_id,
            agent_id=call.agent.task_id,
        )


class GraphitiMemory(ContextMiddleware):
    """Project knowledge graph shared by all agents; facts carry validity times."""

    def __init__(self, graphiti: "Graphiti", *, limit: int = 10) -> None:
        self.graphiti, self.limit = graphiti, limit

    async def before_model(self, call: Invocation) -> None:
        edges = await self.graphiti.search(
            call.query,
            group_ids=[call.project.store.project_id],
            num_results=self.limit,
        )
        call.memory.extend(
            {
                "source": "graphiti",
                "id": edge.uuid,
                "text": edge.fact,
                "valid_at": edge.valid_at.isoformat() if edge.valid_at else None,
                "invalid_at": edge.invalid_at.isoformat() if edge.invalid_at else None,
            }
            for edge in edges
        )

    async def after_model(
        self, call: Invocation, turn: AgentTurn, observation: JSON
    ) -> None:
        from graphiti_core.nodes import EpisodeType

        await self.graphiti.add_episode(
            name=f"{call.agent.task_id}: {turn.action.kind}",
            episode_body=_turn(call, turn, observation),
            source=EpisodeType.text,
            source_description="Guacamole agent turn",
            reference_time=datetime.now(UTC),
            group_id=call.project.store.project_id,
        )


class LangChainMiddleware(ContextMiddleware):
    """Runs a LangChain message middleware over an agent's optional sources.

    Summaries come first, then selected sources oldest first, each as a read
    request, tool call and result. SummarizationMiddleware compacts older ones into
    a stored Summary citing them, like the compact action; its summary prompt holds
    every summarized source (trim_tokens_to_summarize=None). Cleared tool results
    from ContextEditingMiddleware are left out of this invocation with deferral
    records; reading a source again makes it the most recent.
    """

    def __init__(self, middleware: "AgentMiddleware") -> None:
        from langchain.agents.middleware import SummarizationMiddleware

        if isinstance(middleware, SummarizationMiddleware):
            # The default 4,000-token trim drops large sources from their own summary.
            middleware.trim_tokens_to_summarize = None
        self.middleware = middleware

    async def before_model(self, call: Invocation) -> None:
        from langchain.agents.middleware.types import AgentMiddleware, ModelRequest
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        project, spec = call.project, call.agent.context
        refs: dict[str, Ref] = {}
        messages: list[Any] = []
        # Selected sources are stored newest first.
        for ref in (*spec.summaries, *reversed(spec.selected)):
            if ref in spec.pinned:
                continue
            try:
                data = encode(project.store.resolve(ref, current=True).data)
            except ValueError:
                continue  # Assembly records unknown or stale references.
            key = f"{ref.kind}:{ref.id}@{ref.revision}"
            refs[key] = ref
            if ref.kind == "summary":
                messages.append(HumanMessage(data, id=key))
            else:
                # LangChain trims summarized history to start on a human message.
                read = {"name": "read", "args": ref.model_dump(mode="json"), "id": key}
                messages += [
                    HumanMessage(f"Read {key}", id=f"{key}#request"),
                    AIMessage("", tool_calls=[read], id=f"{key}#call"),
                    ToolMessage(data, tool_call_id=key, id=key),
                ]
        shown = {m.id for m in messages}

        update = await self.middleware.abefore_model(
            {"messages": messages},
            None,  # ty: ignore[invalid-argument-type] -- these hooks ignore runtime
        )
        if update:
            messages = [m for m in update["messages"] if m.type != "remove"]
            kept = {m.id for m in messages}
            summarized = tuple(ref for key, ref in refs.items() if key not in kept)
            text = "\n".join(m.text for m in messages if m.id not in shown)
            if summarized and text:
                project.compact(
                    call.agent.id,
                    Summary(text=text, sources=summarized),
                    actor="runtime",
                )
                stored = project.store.model("agent", call.agent.id, AgentSpec).context
                spec = spec.model_copy(
                    update={"selected": stored.selected, "summaries": stored.summaries}
                )
                call.agent = call.agent.model_copy(update={"context": spec})

        if type(self.middleware).awrap_model_call is AgentMiddleware.awrap_model_call:
            return
        edited = messages

        async def capture(request: ModelRequest) -> None:
            nonlocal edited
            edited = request.messages

        await self.middleware.awrap_model_call(
            ModelRequest(model=None, messages=messages),
            capture,
        )
        cleared = {
            m.id
            for m in edited
            if isinstance(m, ToolMessage)
            and m.response_metadata.get("context_editing", {}).get("cleared")
        }
        if cleared:
            selected = tuple(
                r
                for r in spec.selected
                if f"{r.kind}:{r.id}@{r.revision}" not in cleared
            )
            call.agent = call.agent.model_copy(
                update={"context": spec.model_copy(update={"selected": selected})}
            )
            call.omissions += [
                Omission(
                    item=key, reason="Cleared by context editing; read again if needed"
                )
                for key in sorted(cleared)
            ]


async def standard_middleware(
    workspace: Path,
    cleanup: AsyncExitStack,
    *,
    summary_model: str = "openai/gpt-6-luna",
    summarize_at_tokens: int = 150_000,
    clear_at_tokens: int = 400_000,
) -> tuple[ContextMiddleware, ...]:
    """Context editing, and with OPENAI_API_KEY also summaries and memory.

    Editing hides tool reads beyond the latest 8 once sources exceed
    clear_at_tokens, and needs no API key. With a key, sources above
    summarize_at_tokens are compacted by summary_model, and every turn feeds a
    Graphiti knowledge graph and mem0 memory kept in workspace (billed usage).
    Needs the langchain extra, plus graphiti and mem0 with a key. Close cleanup
    after the run to stop the embedded stores.
    """
    from langchain.agents.middleware import (
        ClearToolUsesEdit,
        ContextEditingMiddleware,
        SummarizationMiddleware,
    )

    editing = LangChainMiddleware(
        ContextEditingMiddleware(
            edits=[ClearToolUsesEdit(trigger=clear_at_tokens, keep=8)]
        )
    )
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is unset: context editing only, without summarization "
            "or Graphiti/mem0 memory.",
            flush=True,
        )
        return (editing,)
    # Keep project activity out of the libraries' usage telemetry.
    os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")
    os.environ.setdefault("MEM0_TELEMETRY", "False")
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from langchain_litellm import ChatLiteLLM
    from mem0 import AsyncMemory
    from redislite.async_falkordb_client import AsyncFalkorDB

    # Embedded FalkorDB; its append-only log keeps the graph through crashes.
    graph_db = AsyncFalkorDB(
        str(workspace / "graph.db"), serverconfig={"appendonly": "yes"}
    )
    cleanup.push_async_callback(graph_db.client.close)
    # redislite's async close leaves its embedded server running until exit.
    cleanup.push_async_callback(graph_db.client.shutdown)
    graphiti = Graphiti(graph_driver=FalkorDriver(falkor_db=graph_db))
    cleanup.push_async_callback(graphiti.close)
    await graphiti.build_indices_and_constraints()
    memory = AsyncMemory.from_config(
        {
            "vector_store": {
                "provider": "qdrant",
                "config": {"path": str(workspace / "mem0"), "on_disk": True},
            },
            "history_db_path": str(workspace / "mem0-history.db"),
        }
    )
    cleanup.callback(memory.close)
    summarizing = LangChainMiddleware(
        SummarizationMiddleware(
            ChatLiteLLM(model=summary_model),
            trigger=("tokens", summarize_at_tokens),
            # Keep less than clear_at_tokens so compacted context is not cleared too.
            keep=("tokens", 50_000),
        )
    )
    # Summarize first: context editing hides cleared sources from later middleware.
    return summarizing, editing, GraphitiMemory(graphiti), Mem0Memory(memory)
