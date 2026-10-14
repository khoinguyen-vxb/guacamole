"""Context middleware with labelled fixtures; no model, graph or vector-store calls."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    SummarizationMiddleware,
)
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from runtime_support import TestReasoning

from guacamole import AgentSpec, ContextSpec, Project, ProjectRequest
from guacamole.contracts import AgentTurn, Rationale, Read, Wait
from guacamole.middleware import (
    ContextMiddleware,
    GraphitiMemory,
    LangChainMiddleware,
    Mem0Memory,
)


class Reader(TestReasoning):
    """Reads one source per turn, then waits."""

    def __init__(self, refs):
        self.refs, self.packets = refs, []

    async def respond(self, packet):
        self.packets.append(packet)
        turn = len(self.packets)
        return AgentTurn(
            rationale=Rationale(objective="Read sources", explanation="Fixture"),
            action=Read(refs=(self.refs[turn - 1],))
            if turn <= len(self.refs)
            else Wait(reason="Read finished"),
        )


class FakeMem0:
    def __init__(self):
        self.filters, self.added = [], []

    async def search(self, query, *, top_k, filters):
        self.filters.append(filters)
        return {"results": [{"id": "m1", "memory": "Prefers 6061 aluminium"}]}

    async def add(self, messages, *, user_id, agent_id):
        self.added.append((messages, user_id, agent_id))


class FakeGraphiti:
    def __init__(self):
        self.episodes = []

    async def search(self, query, *, group_ids, num_results):
        return [
            SimpleNamespace(
                uuid="e1",
                fact="Motor M1 drives stage 2",
                valid_at=None,
                invalid_at=None,
            )
        ]

    async def add_episode(self, **episode):
        self.episodes.append(episode)


class Broken(ContextMiddleware):
    async def before_model(self, call):
        raise RuntimeError("fixture-secret-must-not-persist")


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def run_reader(self, *middleware):
        """Four reads; the last packet shows three older reads to the middleware."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        project = Project(root / "state", middleware=middleware)
        self.addCleanup(project.close)
        refs = []
        for index in range(4):
            path = root / f"source{index}.txt"
            path.write_text(f"Source {index} measured value {index}")
            refs.append(project.ingest(path))
        provider = Reader(refs)
        project.reasoning = provider
        # Headroom over the contracts' size, which every new action grows.
        await project.run(
            ProjectRequest(
                description="Middleware fixture",
                context=ContextSpec(max_input_tokens=64_000),
            )
        )
        self.assertEqual(len(provider.packets), 5)
        return project, refs, provider.packets[-1]

    async def test_summarization_compacts_older_sources_with_citations(self):
        model = FakeListChatModel(responses=["Sources 0 and 1 measured 0 and 1."])
        summarizer = SummarizationMiddleware(
            model, trigger=("messages", 7), keep=("messages", 3)
        )
        project, refs, packet = await self.run_reader(LangChainMiddleware(summarizer))
        self.assertIsNone(summarizer.trim_tokens_to_summarize)
        summary = next(r for r in packet.sources if r.kind == "summary")
        data = project.store.resolve(summary).data
        self.assertEqual(data["sources"], [r.model_dump(mode="json") for r in refs[:2]])
        self.assertIn("Sources 0 and 1 measured", data["text"])
        self.assertTrue({refs[2], refs[3]} <= set(packet.sources))
        self.assertFalse({refs[0], refs[1]} & set(packet.sources))
        agent = project.store.model("agent", packet.agent_id, AgentSpec).context
        self.assertEqual(agent.summaries, (summary,))
        self.assertNotIn(refs[0], agent.selected)

    async def test_context_editing_defers_older_reads_for_this_call_only(self):
        editor = ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=0, keep=1)])
        project, refs, packet = await self.run_reader(LangChainMiddleware(editor))
        self.assertFalse({refs[0], refs[1]} & set(packet.sources))
        self.assertTrue({refs[2], refs[3]} <= set(packet.sources))
        cleared = {o.item for o in packet.deferred if "context editing" in o.reason}
        self.assertEqual(cleared, {f"source:{r.id}@{r.revision}" for r in refs[:2]})
        agent = project.store.model("agent", packet.agent_id, AgentSpec).context
        self.assertIn(refs[0], agent.selected)

    async def test_memory_recalls_and_records_turns_and_failures_stay_private(self):
        mem0, graph = FakeMem0(), FakeGraphiti()
        project, _, packet = await self.run_reader(
            Broken(), Mem0Memory(mem0), GraphitiMemory(graph)
        )
        recalled = json.loads(packet.prompt)["memory"]
        self.assertEqual(
            [m["text"] for m in recalled],
            ["Prefers 6061 aluminium", "Motor M1 drives stage 2"],
        )
        agent = project.store.model("agent", packet.agent_id, AgentSpec)
        scope = {"user_id": project.store.project_id, "agent_id": agent.task_id}
        self.assertEqual(mem0.filters[0], scope)
        # The reader's five turns; the Systems Engineer's turn is its own memory.
        self.assertEqual(len([a for a in mem0.added if a[2] == "chief"]), 5)
        episodes = [e for e in graph.episodes if e["name"].startswith("chief:")]
        self.assertEqual(len(episodes), 5)
        self.assertIn("Read finished", episodes[-1]["episode_body"])
        failures = [e for e in project.events() if e.type == "middleware.failed"]
        self.assertEqual(len(failures), 6)
        self.assertEqual(failures[0].details["hook"], "Broken.before_model")
        self.assertNotIn("fixture-secret", json.dumps([e.details for e in failures]))


if __name__ == "__main__":
    unittest.main()
