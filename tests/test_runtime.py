import asyncio
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import litellm
from runtime_support import (
    TestReasoning,
    commit_fixture_model,
    engineer_id,
    fixture_requirement,
    plan_request,
    to_engineer,
)

from guacamole import (
    AgentSpec,
    AgentTurn,
    AskHuman,
    Budget,
    Candidate,
    Constraint,
    ContextSpec,
    DecisionRequest,
    Note,
    ProducedFile,
    Project,
    ProjectRequest,
    Qualification,
    Quantity,
    Ref,
    Requirement,
    TaskAuthorization,
    TaskReport,
    ToolRegistry,
    Usage,
)
from guacamole.agents.runtime import Runtime
from guacamole.context import (
    ContextBuilder,
    ContextOverflow,
    ProviderError,
    encode_context,
    preview,
)
from guacamole.contracts import (
    Acknowledge,
    AgentState,
    ContextPacket,
    Decide,
    Finish,
    MessageEnvelope,
    OpenItem,
    Publish,
    PublishedFile,
    Rationale,
    Read,
    RequestRecord,
    Send,
    Spawn,
    ToolCall,
    Wait,
)
from guacamole.decision import DecisionBlocked
from guacamole.providers.litellm import LiteLLMReasoning
from guacamole.providers.litellm import _usage as litellm_usage


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolved_plan_input_allows_replanning_and_worker_recovery(self):
        calls = []

        def probe() -> str:
            calls.append("probe")
            return "ok"

        class Replanner(TestReasoning):
            def __init__(self):
                self.spawned = False
                self.packets = []

            def requirements(self):
                return fixture_requirement(project)

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                if data["agent"]["task_id"] == "chief":
                    self.packets.append(packet)
                    decision_id = data["agent"]["decision_id"]
                    plan = (
                        project.store.maybe("decision", decision_id)
                        if decision_id
                        else None
                    )
                    if plan is None or plan.stale:
                        request = plan_request(
                            project.store.list("requirement")[0].ref,
                            tasks=(
                                TaskAuthorization(
                                    id="A",
                                    objective="probe",
                                    tools=(tool.definition.grant,),
                                ),
                            ),
                        )
                        candidate = request.candidates[0]
                        candidate = candidate.model_copy(
                            update={
                                "plan": candidate.plan.model_copy(
                                    update={
                                        "inputs": (
                                            *candidate.plan.inputs,
                                            project.store.get("open_item", "gui").ref,
                                        )
                                    }
                                )
                            }
                        )
                        action = Decide(
                            selected="fixture",
                            request=request.model_copy(
                                update={"candidates": (candidate,)}
                            ),
                        )
                    elif not self.spawned:
                        self.spawned = True
                        action = Spawn(decision_id=plan.ref.id, task_id="A")
                    else:
                        action = Wait(reason="Fixture waits")
                elif len(project.store.list("decision")) > 1 and not calls:
                    action = ToolCall(tool=tool.definition.grant, arguments={})
                else:
                    action = Wait(reason="Fixture waits")
                return AgentTurn(
                    rationale=Rationale(objective="fixture", explanation="Fixture"),
                    action=action,
                )

        with tempfile.TemporaryDirectory() as directory:
            tools = ToolRegistry()
            tool = tools.register(probe)
            provider = Replanner()
            with Project(Path(directory), tools=tools, reasoning=provider) as project:
                original = OpenItem(
                    id="gui", kind="missing_tool", description="Offline"
                )
                old_input = project.record_open_item(original)
                result = await project.run(
                    ProjectRequest(
                        description="fixture",
                        context=ContextSpec(max_input_tokens=300_000),
                    )
                )
                old_plan = project.store.list("decision")[0].ref
                worker = next(
                    s for s in project.store.list("agent") if s.data["parent_id"]
                )
                # Model the same saved failure, including a stale pending explicit read.
                artifact = project.store.put(
                    "source",
                    "pending",
                    {"text": "old plan output"},
                    actor="script",
                    dependencies=(old_plan,),
                )
                valid = project.store.get("source", "brief").ref
                state = project.store.model("agent_state", worker.ref.id, AgentState)
                project.store.put(
                    "agent_state",
                    worker.ref.id,
                    state.model_copy(
                        update={
                            "status": "blocked",
                            "observation": {
                                "selected": [
                                    artifact.model_dump(mode="json"),
                                    valid.model_dump(mode="json"),
                                ]
                            },
                        }
                    ),
                    actor="script",
                )
                current_input = project.record_open_item(
                    original.model_copy(
                        update={
                            "description": "Resolved",
                            "resolved_by": (valid,),
                        }
                    )
                )
                with self.assertRaises(ValueError):
                    project.decisions.plan(old_plan.id)
                build = project.contexts.build

                async def delayed_build(agent, *args, **kwargs):
                    if agent.task_id == "A" and agent.decision_id == old_plan.id:
                        # Its old context must fail after the new plan repaired its reads.
                        async with asyncio.timeout(10):
                            while (
                                project.store.get("agent", agent.id).data["decision_id"]
                                == old_plan.id
                            ):
                                await asyncio.sleep(0.01)
                    return await build(agent, *args, **kwargs)

                with patch.object(project.contexts, "build", delayed_build):
                    await project.run(resume=result.run_id)
                self.assertEqual(calls, ["probe"])
                assigned = project.store.model("agent", worker.ref.id, AgentSpec)
                self.assertIn(current_input, assigned.context.pinned)
                self.assertNotIn(old_input, assigned.context.pinned)
                self.assertNotEqual(assigned.decision_id, old_plan.id)
                self.assertTrue(project.store.resolve(old_plan).stale)
                recovered = next(
                    p
                    for p in provider.packets
                    if any(o.item == f"decision:{old_plan.id}@1" for o in p.deferred)
                )
                self.assertNotIn(old_plan, recovered.sources)
                self.assertIn(
                    "unusable",
                    json.loads(recovered.prompt)["state"]["review_blockers"][0],
                )

    def test_context_shows_decision_evidence_snapshots_as_refs(self):
        ref = {"kind": "source", "id": "evidence", "revision": 1, "sha256": "hash"}
        content = {"text": "Historical engineering evidence " * 100}
        nested = {"kind": "decision", "id": "earlier", "revision": 1, "sha256": "hash"}
        current = {"kind": "artifact", "id": "current", "revision": 1, "sha256": "hash"}
        entries = [
            {"ref": ref, "content": content},
            {
                "ref": nested,
                "content": {"request": {"context": [{"ref": ref, "content": content}]}},
            },
            current,  # Newer decisions store refs only.
        ]
        payload = {
            "sources": [
                {"ref": ref, "data": content},
                {
                    "ref": {"kind": "decision"},
                    "data": {
                        "request": {"context": entries, "question": "Choose design"},
                        "result": {"selected": "approved"},
                    },
                },
            ]
        }
        original = json.dumps(payload)
        encoded = encode_context(payload)
        sources = json.loads(encoded)["sources"]
        context = sources[1]["data"]["request"]["context"]
        self.assertEqual(context, [ref, nested, current])
        self.assertEqual(sources[0]["data"], content)
        self.assertEqual(sources[1]["data"]["result"], {"selected": "approved"})
        self.assertEqual(json.dumps(payload), original)
        self.assertLess(len(encoded), len(original))

    def test_decisions_that_stored_evidence_copies_still_load_as_refs(self):
        ref = Ref(kind="requirement", id="r", revision=1, sha256="0" * 64)
        stored = plan_request(ref).model_dump(mode="json") | {
            "context": [{"ref": ref.model_dump(mode="json"), "content": {"x": 1}}]
        }
        request = DecisionRequest.model_validate_json(json.dumps(stored))
        self.assertEqual(request.context, (ref,))

    async def test_context_obeys_provider_character_limit_independently_of_tokens(self):
        class Limited(TestReasoning):
            max_input_chars = 30_000

            async def count_tokens(self, prompt):
                return len(prompt) // 10

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory)) as project,
        ):
            source = Path(directory) / "large.txt"
            source.write_text("π" * 30_000)
            ref = project.ingest(source)
            agent = AgentSpec(
                id="worker",
                task_id="task",
                parent_id="chief",
                objective="Inspect",
                context=ContextSpec(selected=(ref,), max_input_tokens=100_000),
                decision_id=None,
            )
            packet = await project.contexts.build(
                agent,
                "request",
                Limited(),
                instructions="test",
                state={},
            )
            self.assertLessEqual(len(packet.prompt), Limited.max_input_chars)
            self.assertNotIn(ref, packet.sources)
            self.assertTrue(packet.deferred)
            self.assertEqual(
                packet.input_tokens, await Limited().count_tokens(packet.prompt)
            )
            pinned = agent.model_copy(
                update={
                    "context": agent.context.model_copy(
                        update={"pinned": (ref,), "selected": ()},
                    )
                }
            )
            with self.assertRaisesRegex(ContextOverflow, "characters"):
                await project.contexts.build(
                    pinned,
                    "request",
                    Limited(),
                    instructions="test",
                    state={},
                )

    async def test_prompt_leads_with_stable_fields_and_marks_cacheable_prefixes(self):
        def probe(text: str) -> str:
            return text

        def other(text: str) -> str:
            return text

        tools = ToolRegistry()
        granted, _ = (tools.register(f, requires_plan=False) for f in (probe, other))
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=tools) as project,
        ):
            source = Path(directory) / "source.txt"
            source.write_text("pinned evidence")
            agent = AgentSpec(
                id="chief",
                task_id="chief",
                parent_id=None,
                objective="Plan",
                context=ContextSpec(
                    pinned=(project.ingest(source),), max_input_tokens=100_000
                ),
                decision_id=None,
                tools=(granted.definition.grant,),
            )
            packets = [
                await project.contexts.build(
                    agent,
                    "request",
                    TestReasoning(),
                    instructions="test",
                    state={"turn": turn},
                    catalogue=True,
                )
                for turn in (1, 2)
            ]
        first, second = packets
        data = json.loads(first.prompt)
        self.assertEqual(
            list(data)[:3], ["instructions", "response_schema", "result_schema"]
        )
        self.assertEqual(list(data)[-2:], ["messages", "state"])
        # The Chief's own tools are in tool_schemas; the catalogue lists the rest.
        self.assertEqual([t["grant"]["name"] for t in data["tool_schemas"]], ["probe"])
        self.assertEqual([t["grant"]["name"] for t in data["catalogue"]], ["other"])
        stable, semi = first.cache_breakpoints
        self.assertTrue(first.prompt[stable:].startswith('"agent":'))
        self.assertTrue(first.prompt[semi:].startswith('"messages":'))
        # Only the per-turn tail differs between turns.
        self.assertEqual(first.prompt[:semi], second.prompt[:semi])
        self.assertNotEqual(first.prompt[semi:], second.prompt[semi:])
        self.assertEqual(first.components["state.turn"], 1)
        self.assertGreater(first.components["sources.pinned"], 0)
        self.assertEqual(first.components["sources.selected"], 0)
        self.assertGreater(first.components["response_schema"], 1_000)

    async def test_context_counts_tokens_once_when_optional_material_fits(self):
        class Counting(TestReasoning):
            calls = 0

            async def count_tokens(self, prompt):
                Counting.calls += 1
                return len(prompt.encode())

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory)) as project,
        ):
            refs = []
            for index, size in enumerate((1_000, 1_000, 1_000, 5_000, 500)):
                path = Path(directory) / f"source{index}.txt"
                path.write_text("x" * size)
                refs.append(project.ingest(path))

            async def build(budget):
                agent = AgentSpec(
                    id="worker",
                    task_id="task",
                    parent_id="chief",
                    objective="Read",
                    context=ContextSpec(selected=tuple(refs), max_input_tokens=budget),
                    decision_id=None,
                )
                Counting.calls = 0
                return await project.contexts.build(
                    agent, "request", Counting(), instructions="test", state={}
                )

            packet = await build(100_000)
            self.assertEqual(packet.sources, tuple(refs))
            self.assertEqual(
                Counting.calls, 2
            )  # The pinned base, then all sources at once
            self.assertEqual(packet.input_tokens, len(packet.prompt.encode()))
            # 2,000 short: the large fourth source no longer fits, the small fifth does.
            packet = await build(len(packet.prompt.encode()) - 2_000)
            self.assertEqual(packet.sources, (*refs[:3], refs[4]))
            self.assertEqual(
                [o.item for o in packet.deferred],
                [f"source:{refs[3].id}@1"],
            )
            self.assertEqual(packet.input_tokens, len(packet.prompt.encode()))
            self.assertLess(Counting.calls, 8)

    def test_preview_bounds_large_values_and_keeps_short_fields(self):
        result = {
            "status": "converged",
            "residual": 0.0021,
            "log": "iteration " * 5_000,
            "cells": list(range(5_000)),
        }

        def size(value):
            return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

        shown = preview(result, 2_000)
        self.assertLessEqual(size(shown), 2_000)
        self.assertEqual(shown["status"], "converged")
        self.assertEqual(shown["residual"], 0.0021)
        self.assertRegex(shown["log"], r"…\[\d+ more chars\]$")
        self.assertRegex(shown["cells"][-1], r"…\[\d+ more items\]")
        self.assertEqual(shown["cells"][:3], [0, 1, 2])
        self.assertEqual(preview(result["status"], 2_000), "converged")
        many = {f"field{i}": "value" * 20 for i in range(200)}
        cut = preview(many, 1_000)
        self.assertLessEqual(size(cut), 1_000)
        self.assertIn("field0", cut)
        self.assertRegex(cut["…"], r"\[\d+ more fields\]")

    async def test_invalid_reads_do_not_poison_context_and_can_be_corrected(self):
        class Reader(TestReasoning):
            def __init__(self, wanted, bad):
                self.wanted, self.bad, self.packets = wanted, bad, []

            async def respond(self, packet):
                self.packets.append(packet)
                return AgentTurn(
                    rationale=Rationale(
                        objective="Read current sources", explanation="Fixture"
                    ),
                    action=Read(refs=(self.wanted, self.bad))
                    if len(self.packets) == 1
                    else Read(refs=(self.wanted,))
                    if len(self.packets) == 2
                    else Wait(reason="Read finished"),
                )

        for failure in ("missing", "mismatched", "stale", "older"):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                with Project(root / "state") as project:
                    source = root / "source.txt"
                    source.write_text("original")
                    original = project.ingest(source)
                    if failure == "stale":
                        project.store.invalidate(
                            original, actor="script", reason="Fixture invalidation"
                        )
                    elif failure == "older":
                        source.write_text("updated")
                        project.ingest(source, source_id=original.id)
                    bad = (
                        original.model_copy(update={"id": "missing-source"})
                        if failure == "missing"
                        else original.model_copy(update={"sha256": "0" * 64})
                        if failure == "mismatched"
                        else original
                    )
                    wanted_path = root / "wanted.txt"
                    wanted_path.write_text("wanted")
                    wanted = project.ingest(wanted_path)

                    provider = Reader(wanted, bad)
                    project.reasoning = provider
                    await project.run(
                        ProjectRequest(
                            description="Invalid read recovery fixture",
                            # Headroom over the contracts and system_model state.
                            context=ContextSpec(
                                max_input_tokens=64_000, selected=(bad,)
                            ),
                        )
                    )
                    packets = provider.packets
                    self.assertEqual(len(packets), 3)
                    observation = json.loads(packets[1].prompt)["state"][
                        "last_observation"
                    ]
                    self.assertEqual(observation["phase"], "action")
                    self.assertIn("current Ref", observation["detail"])
                    self.assertNotIn("selected", observation)
                    self.assertNotIn(bad, packets[0].sources)
                    self.assertNotIn(wanted, packets[1].sources)
                    self.assertIn(wanted, packets[2].sources)
                    self.assertIn(
                        f"{bad.kind}:{bad.id}@{bad.revision}",
                        {item.item for item in packets[0].deferred},
                    )
                    (chief,) = [
                        s
                        for s in project.store.list("agent")
                        if s.data["task_id"] == "chief"
                    ]
                    agent = project.store.model("agent", chief.ref.id, AgentSpec)
                    self.assertEqual(len(project.store.history("agent", agent.id)), 2)
                    pinned = agent.model_copy(
                        update={
                            "context": agent.context.model_copy(
                                update={"pinned": (bad,)}
                            )
                        }
                    )
                    with self.assertRaises(ValueError):
                        await project.contexts.build(
                            pinned,
                            "fixture",
                            TestReasoning(),
                            instructions="test",
                            state={},
                        )

    async def test_requested_records_take_priority_or_block_without_retrying(self):
        for size in (60_000, 180_000):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                seen = []

                class Reader(TestReasoning):
                    def __init__(self, packets):
                        self.target, self.packets = None, packets

                    async def respond(self, packet):
                        self.packets.append(packet)
                        return AgentTurn(
                            rationale=Rationale(
                                objective="Read", explanation="Fixture"
                            ),
                            action=Read(refs=(self.target,))
                            if len(self.packets) == 1
                            else Wait(reason="Read finished"),
                        )

                root = Path(directory)
                background = root / "background.txt"
                background.write_text("b" * 100_000)
                source = root / "wanted.txt"
                source.write_text("w" * size)
                reader = Reader(seen)
                with Project(root / "state", reasoning=reader) as project:
                    old = project.ingest(background)
                    wanted = project.ingest(source)
                    reader.target = wanted
                    result = await project.run(
                        ProjectRequest(
                            description="Read prioritisation fixture",
                            context=ContextSpec(
                                max_input_tokens=150_000, selected=(old, wanted)
                            ),
                        )
                    )
                    self.assertIn(old, seen[0].sources)
                    self.assertNotIn(wanted, seen[0].sources)
                    if size == 60_000:
                        self.assertEqual(len(seen), 2)
                        self.assertIn(wanted, seen[1].sources)
                        self.assertNotIn(old, seen[1].sources)
                    else:
                        self.assertEqual(len(seen), 1)
                        self.assertTrue(
                            any("Pinned context" in item for item in result.open_items)
                        )

    async def test_pending_reads_survive_provider_failure(self):
        class Reader(TestReasoning):
            def __init__(self):
                self.calls = 0
                self.target = None

            async def respond(self, packet):
                self.calls += 1
                if self.calls == 1:
                    return AgentTurn(
                        rationale=Rationale(objective="Read", explanation="Fixture"),
                        action=Read(refs=(self.target,)),
                    )
                raise RuntimeError("fixture provider failure")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reader = Reader()
            with Project(root / "state", reasoning=reader) as project:
                (root / "wanted.txt").write_text("wanted")
                reader.target = project.ingest(root / "wanted.txt")
                result = await project.run(
                    ProjectRequest(
                        description="Pending read fixture",
                        context=ContextSpec(max_input_tokens=200_000),
                    )
                )
                chief = project.store.get("run", result.run_id).data["chief_id"]
                state = project.store.get("agent_state", chief).data
                self.assertEqual(result.status, "incomplete")
                self.assertEqual(state["status"], "blocked")
                self.assertEqual(
                    state["observation"]["selected"][0]["id"], reader.target.id
                )

    async def test_earlier_tool_results_stay_in_later_turns(self):
        def shout(text: str) -> str:
            return text.upper()

        class Caller(TestReasoning):
            def __init__(self):
                self.states = []

            async def respond(self, packet):
                self.states.append(json.loads(packet.prompt)["state"])
                calls = len(self.states)
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=ToolCall(
                        tool=tool.definition.grant, arguments={"text": f"call {calls}"}
                    )
                    if calls <= 3
                    else Wait(reason="Fixture finished"),
                )

        tools = ToolRegistry()
        tool = tools.register(shout, requires_plan=False)
        with tempfile.TemporaryDirectory() as directory:
            provider = Caller()
            with Project(Path(directory), tools=tools, reasoning=provider) as project:
                await project.run(
                    ProjectRequest(
                        description="Tool history fixture",
                        context=ContextSpec(max_input_tokens=200_000),
                    )
                )
        state = provider.states[3]
        self.assertEqual(state["last_observation"]["result"], "CALL 3")
        self.assertEqual(
            [(c["arguments"]["text"], c["result"]) for c in state["recent_tool_calls"]],
            [("call 1", "CALL 1"), ("call 2", "CALL 2")],
        )

    async def test_large_tool_results_repeat_as_previews_until_read(self):
        def solve(case: str) -> dict[str, str]:
            return {"status": "converged", "log": f"{case} residual\n" * 2_000}

        class Solver(TestReasoning):
            def __init__(self):
                self.packets = []

            async def respond(self, packet):
                self.packets.append(packet)
                state = json.loads(packet.prompt)["state"]
                action = (
                    ToolCall(
                        tool=tool.definition.grant,
                        arguments={"case": f"case {len(self.packets)}"},
                    )
                    if len(self.packets) <= 2
                    else Read(refs=(Ref(**state["recent_tool_calls"][0]["ref"]),))
                    if len(self.packets) == 3
                    else Wait(reason="Fixture finished")
                )
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=action,
                )

        tools = ToolRegistry()
        tool = tools.register(solve, requires_plan=False)
        with tempfile.TemporaryDirectory() as directory:
            provider = Solver()
            with Project(Path(directory), tools=tools, reasoning=provider) as project:
                await project.run(
                    ProjectRequest(
                        description="Large result fixture",
                        context=ContextSpec(max_input_tokens=200_000),
                    )
                )
                calls = [r for r in project.requests() if r.kind == "tool"]
                first = project.store.get("tool_result", calls[0].id)
        state = json.loads(provider.packets[2].prompt)["state"]
        self.assertEqual(state["last_observation"]["result"]["log"].count("\n"), 2_000)
        (call,) = state["recent_tool_calls"]
        self.assertEqual(call["result"]["status"], "converged")
        self.assertRegex(call["result"]["log"], r"…\[\d+ more chars\]$")
        self.assertEqual(call["ref"], first.ref.model_dump(mode="json"))
        self.assertLess(len(json.dumps(call)), 3_000)
        # Reading the ref brings the whole result back as a source.
        self.assertIn(first.ref, provider.packets[3].sources)

    async def test_invalid_rationale_references_can_be_corrected(self):
        class Correcting(TestReasoning):
            def __init__(self, bad, current):
                self.bad, self.current, self.observations = bad, current, []

            async def respond(self, packet):
                self.observations.append(
                    json.loads(packet.prompt)["state"]["last_observation"]
                )
                return AgentTurn(
                    rationale=Rationale(
                        objective="Use current evidence",
                        explanation="Fixture",
                        evidence=(
                            self.bad if len(self.observations) == 1 else self.current,
                        ),
                    ),
                    action=Wait(reason="Evidence accepted"),
                )

        for failure in ("missing", "mismatched", "stale"):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                source = root / "source.txt"
                source.write_text("original")
                with Project(root / "state") as project:
                    original = project.ingest(source, source_id="fixture")
                    source.write_text("corrected")
                    current = project.ingest(source, source_id=original.id)
                    bad = (
                        current.model_copy(update={"id": "missing-source"})
                        if failure == "missing"
                        else current.model_copy(update={"sha256": "0" * 64})
                        if failure == "mismatched"
                        else original
                    )
                    provider = Correcting(bad, current)
                    project.reasoning = provider
                    await project.run(
                        ProjectRequest(
                            description="Invalid rationale recovery fixture",
                            context=ContextSpec(
                                selected=(current,), max_input_tokens=200_000
                            ),
                        )
                    )
                    observations = provider.observations
                    # The invalid turn's Wait must not run; the next turn can correct it.
                    self.assertEqual(len(observations), 2)
                    self.assertEqual(observations[1]["phase"], "rationale")
                    self.assertIn("current Ref", observations[1]["detail"])
                    self.assertNotIn(bad.id, observations[1]["detail"])
                    rationales = [
                        r
                        for r in project.store.list("rationale")
                        if r.data["author"] != engineer_id(project)
                    ]
                    self.assertEqual(len(rationales), 1)
                    self.assertEqual(rationales[0].dependencies, (current,))
                    self.assertEqual(
                        project.store.list("agent_state")[0].data["status"], "waiting"
                    )

    async def test_litellm_sends_the_exact_counted_packet(self):
        expected = AgentTurn(
            rationale=Rationale(
                objective="fixture", explanation="No engineering claim"
            ),
            action=Wait(reason="await inputs"),
        )
        # LiteLLM's mock_response runs its real request path without a network call.
        provider = LiteLLMReasoning(
            "anthropic/claude-opus-5-5",
            effort="low",
            mock_response=f"```json\n{expected.model_dump_json()}\n```",
        )
        prompt = '{"instructions":"Return JSON", "sources":[]}'
        packet = ContextPacket(
            agent_id="fixture",
            invocation_id="one",
            request_id="request",
            provider=provider.name,
            model=provider.model,
            prompt=prompt,
            input_tokens=await provider.count_tokens(prompt),
            token_count_method=provider.token_count_method,
            reserved_output_tokens=1000,
        )
        with patch.object(
            litellm, "acompletion", wraps=litellm.acompletion
        ) as completion:
            result = await provider.respond(packet)
        self.assertEqual(result.action, expected.action)
        self.assertTrue(result.provider_request_id)
        sent = completion.call_args.kwargs
        self.assertEqual(sent["messages"][-1], {"role": "user", "content": prompt})
        self.assertEqual(sent["model"], "anthropic/claude-opus-5-5")
        self.assertEqual(sent["reasoning_effort"], "low")
        self.assertEqual(sent["max_tokens"], 1000)
        self.assertNotIn("tools", sent)
        with self.assertRaisesRegex(ValueError, "context_capacity_tokens"):
            LiteLLMReasoning("fixture/unmapped-model")

    async def test_litellm_marks_stable_prefixes_for_claude_and_reports_usage(self):
        expected = AgentTurn(
            rationale=Rationale(
                objective="fixture", explanation="No engineering claim"
            ),
            action=Wait(reason="await inputs"),
        )
        prompt = '{"instructions":"stable","agent":{},"state":{"turn":1}}'
        breakpoints = (prompt.index('"agent"'), prompt.index('"state"'))
        for model, marked in (
            ("anthropic/claude-opus-5-5", True),
            ("openai/gpt-6-astra", False),  # OpenAI caches prefixes without markers
        ):
            provider = LiteLLMReasoning(model, mock_response=expected.model_dump_json())
            packet = ContextPacket(
                agent_id="fixture",
                invocation_id="one",
                request_id="request",
                provider=provider.name,
                model=provider.model,
                prompt=prompt,
                input_tokens=await provider.count_tokens(prompt),
                token_count_method=provider.token_count_method,
                reserved_output_tokens=1000,
                cache_breakpoints=breakpoints,
            )
            with (
                self.subTest(model=model),
                patch.object(
                    litellm, "acompletion", wraps=litellm.acompletion
                ) as completion,
            ):
                result = await provider.respond(packet)
                content = completion.call_args.kwargs["messages"][-1]["content"]
                if marked:
                    self.assertEqual("".join(b["text"] for b in content), prompt)
                    self.assertEqual(
                        [b.get("cache_control") for b in content],
                        [{"type": "ephemeral"}, {"type": "ephemeral"}, None],
                    )
                else:
                    self.assertEqual(content, prompt)
                # LiteLLM's mock reports 10 prompt and 20 completion tokens.
                self.assertEqual(result.usage.input_tokens, 10)
                self.assertEqual(result.usage.output_tokens, 20)
                self.assertGreater(result.usage.cost_usd, 0)
        # Anthropic counts cache reads and writes inside LiteLLM's prompt_tokens.
        response = litellm.ModelResponse(
            usage=litellm.Usage(
                prompt_tokens=1_000,
                completion_tokens=50,
                cache_read_input_tokens=600,
                cache_creation_input_tokens=300,
            )
        )
        self.assertEqual(
            litellm_usage(response),
            Usage(
                input_tokens=100,
                cache_read_input_tokens=600,
                cache_creation_input_tokens=300,
                output_tokens=50,
            ),
        )

    async def test_provider_diagnostics_survive_without_server_text(self):
        secret = "fixture-secret-must-not-persist"
        for error, expected in (
            (
                litellm.RateLimitError(f"insufficient_quota {secret}", "openai", "m"),
                "API credits or quota exhausted",
            ),
            (litellm.RateLimitError(secret, "openai", "m"), "API rate limit exceeded"),
            (litellm.AuthenticationError(secret, "openai", "m"), "API key"),
            (litellm.APIConnectionError(secret, "openai", "m"), "Connection failed"),
        ):
            with (
                self.subTest(expected=expected),
                tempfile.TemporaryDirectory() as directory,
                patch.object(litellm, "acompletion", side_effect=error),
                Project(
                    Path(directory), reasoning=LiteLLMReasoning("openai/gpt-6-astra")
                ) as project,
            ):
                result = await project.run(ProjectRequest(description="fixture"))
                self.assertEqual(result.status, "incomplete")
                self.assertIn(expected, result.open_items[-1])
                event = next(e for e in project.events() if e.type == "action.rejected")
                self.assertEqual(event.details["phase"], "provider")
                self.assertIn(expected, event.details["detail"])
                trace = json.dumps(project.trace(project.requests()[0].id))
                self.assertNotIn(secret, trace)

    async def test_arbitrary_provider_exception_text_stays_private(self):
        secret = "fixture-secret-must-not-persist"

        class Broken(TestReasoning):
            async def respond(self, packet):
                raise RuntimeError(secret)

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=Broken()) as project,
        ):
            result = await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(max_input_tokens=200_000),
                )
            )
            self.assertIn("Exception text omitted", result.open_items[-1])
            self.assertNotIn(
                secret, json.dumps(project.trace(project.requests()[0].id))
            )

    async def test_replacement_plan_keeps_running_workers_on_their_task(self):
        def probe() -> str:
            return "ok"

        class Replanner(TestReasoning):
            def __init__(self):
                self.steps = {}
                self.worker_results = []
                self.proposed = False

            def requirements(self):
                source = project.store.list("source")[0].ref
                return tuple(
                    Requirement(
                        id=id, wording="fixture", source=source, source_quote="fixture"
                    )
                    for id in ("r1", "r2")[: 1 + self.proposed]
                )

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps.get(task, 0)
                self.steps[task] = count + 1
                tasks = (
                    TaskAuthorization(
                        id="A", objective="probe", tools=(tool.definition.grant,)
                    ),
                )
                if task == "chief":
                    if count == 2:
                        # The second requirement leaves the first plan uncovered.
                        self.proposed = True
                        action = to_engineer(data, "Record r2")
                    elif count == 3:
                        action = Wait(reason="Await the engineer's reply")
                    elif count in (0, 4):
                        action = Decide(
                            selected="fixture",
                            request=plan_request(
                                *(s.ref for s in project.store.list("requirement")),
                                tasks=tasks,
                            ),
                        )
                    elif count == 1:
                        self.first_plan = data["agent"]["decision_id"]
                        action = Spawn(decision_id=self.first_plan, task_id="A")
                    else:
                        action = Wait(reason="Fixture finished")
                else:
                    self.worker_results.append(data["state"]["last_observation"])
                    # Concurrent turns may overlap the replan; probe until it lands.
                    done = data["state"]["last_observation"].get("result") == "ok"
                    # The replan first waits for the engineer to model r2.
                    async with asyncio.timeout(30):
                        while (
                            count
                            and not done
                            and len(project.store.list("decision")) < 2
                        ):
                            await asyncio.sleep(0.05)
                    action = (
                        Wait(reason="Fixture probed")
                        if done or count >= 10
                        else ToolCall(tool=tool.definition.grant, arguments={})
                    )
                return AgentTurn(
                    rationale=Rationale(objective=task, explanation="Fixture"),
                    action=action,
                )

        tools = ToolRegistry()
        tool = tools.register(probe)
        with tempfile.TemporaryDirectory() as directory:
            provider = Replanner()
            with Project(Path(directory), tools=tools, reasoning=provider) as project:
                result = await project.run(
                    ProjectRequest(
                        description="fixture",
                        context=ContextSpec(max_input_tokens=200_000),
                    )
                )
                agents = [s.data for s in project.store.list("agent")]
                (chief,) = [a for a in agents if a["task_id"] == "chief"]
                (worker,) = [a for a in agents if a["parent_id"]]
                self.assertEqual(worker["decision_id"], chief["decision_id"])
                # A worker left on an old plan by an earlier runtime moves on resume.
                spec = project.store.model("agent", worker["id"], AgentSpec)
                project.store.put(
                    "agent",
                    spec.id,
                    spec.model_copy(update={"decision_id": provider.first_plan}),
                    actor="script",
                )
                await project.run(resume=result.run_id)
                resumed = project.store.get("agent", worker["id"]).data
                self.assertEqual(resumed["decision_id"], chief["decision_id"])
        # Turn 1 may run before or after the second requirement, or span the replan
        # (about 6% of runs under load), so only the outcome is fixed: a probe
        # completes under the replacement.
        self.assertIn("ok", [r.get("result") for r in provider.worker_results])

    async def test_workers_reason_on_their_task_tier(self):
        seen = []

        class Tiered(TestReasoning):
            def __init__(self, model):
                self.model, self.effort = model, "low"

            def requirements(self):
                source = project.store.list("source")[0].ref
                return (
                    Requirement(
                        id="r", wording="fixture", source=source, source_quote="fixture"
                    ),
                )

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = sum(t == task for _, t, _ in seen)
                seen.append((self.model, task, data["state"]["last_observation"]))
                worker = TaskAuthorization(id="A", objective="w", tier="fast")
                if task == "chief" and count == 0:
                    self.prompt = packet.prompt
                if task != "chief":
                    action = Wait(reason="Fixture worker")
                elif count in (0, 1, 3):
                    # The first plan names a tier the project does not configure;
                    # the last escalates the running worker once it has had a turn.
                    while count == 3 and not any(t == "A" for _, t, _ in seen):
                        await asyncio.sleep(0.01)
                    tier = ("ghost", "fast", "", "slow")[count]
                    action = Decide(
                        selected="fixture",
                        request=plan_request(
                            project.store.list("requirement")[0].ref,
                            tasks=(worker.model_copy(update={"tier": tier}),),
                        ),
                    )
                elif count == 2:
                    action = Spawn(
                        decision_id=data["agent"]["decision_id"], task_id="A"
                    )
                else:
                    action = Wait(reason="Fixture finished")
                return AgentTurn(
                    rationale=Rationale(objective=task, explanation="Fixture"),
                    action=action,
                )

        chief, fast = Tiered("big"), Tiered("small")
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(
                Path(directory),
                reasoning=chief,
                tiers={"fast": fast, "slow": Tiered("medium")},
            ) as project,
        ):
            await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(max_input_tokens=200_000),
                )
            )
            (worker,) = [
                s.data for s in project.store.list("agent") if s.data["parent_id"]
            ]
            dispatched = [
                e.details
                for e in project.events()
                if e.type == "provider.dispatched" and e.actor == worker["id"]
            ]
        self.assertIn(
            "Worker reasoning tier fast: test-double-reasoning small", chief.prompt
        )
        self.assertIn("unconfigured reasoning tier: ghost", seen[1][2]["detail"])
        self.assertEqual(worker["tier"], "slow")
        self.assertEqual(
            [(d["model"], d["tier"], d["effort"]) for d in dispatched],
            [("small", "fast", "low")],
        )
        self.assertEqual({m for m, t, _ in seen if t == "chief"}, {"big"})

    def test_tasks_route_to_the_cheapest_qualified_tier(self):
        class Tier(TestReasoning):
            def __init__(self, model):
                self.model, self.effort = model, "low"

        def measured(model, family, trials, passed, cost):
            return Qualification(
                family=family,
                provider="test-double-reasoning",
                model=model,
                effort="low",
                trials=trials,
                passed=passed,
                cost_usd=cost,
            )

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(
                Path(directory),
                tiers={"cheap": Tier("small"), "dear": Tier("big")},
                qualifications=(
                    measured("small", "extraction", 2, 2, 0.10),
                    measured("big", "extraction", 2, 2, 1.00),
                    # Cheaper per trial, but a failure makes each verified result dearer.
                    measured("small", "analysis", 5, 4, 1.00),
                    measured("big", "analysis", 5, 5, 1.10),
                    measured("small", "diagnosis", 2, 1, 0.10),
                ),
            ) as project,
        ):
            runtime = Runtime(project, TestReasoning())

            def route(family, tier=None):
                task = TaskAuthorization(
                    id="t", objective="o", family=family, tier=tier
                )
                return runtime._route(task)[0]

            self.assertEqual(route("extraction"), "cheap")
            self.assertEqual(route("analysis"), "dear")
            # Unqualified or unmeasured work runs on the Chief's model unless overridden.
            self.assertIsNone(route("diagnosis"))
            self.assertIsNone(route(None))
            self.assertEqual(route("diagnosis", tier="cheap"), "cheap")
            self.assertIn("diagnosis: 1/2 trials verified, $0.100", runtime.tier_menu)
            self.assertIn("unqualified", runtime.tier_menu)
        with self.assertRaises(ValueError):
            measured("small", "extraction", 1, 2, 0.1)

    async def test_rejected_action_explains_runtime_errors_but_not_tool_errors(self):
        secret = "fixture-secret-must-not-persist"

        def leaky() -> str:
            raise ValueError(secret)

        def explained() -> str:
            raise ValueError("Path is outside the inputs; pick one from list_files")

        class Rejected(TestReasoning):
            def __init__(self):
                self.observations = []

            async def respond(self, packet):
                self.observations.append(
                    json.loads(packet.prompt)["state"]["last_observation"]
                )
                actions = (
                    Acknowledge(message_ids=("missing",)),
                    ToolCall(tool=tool.definition.grant, arguments={}),
                    ToolCall(tool=shown.definition.grant, arguments={}),
                    ToolCall(tool=tool.definition.grant, arguments={"path": "x"}),
                    Wait(reason="Fixture finished"),
                )
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=actions[len(self.observations) - 1],
                )

        tools = ToolRegistry()
        tool = tools.register(leaky, requires_plan=False)
        shown = tools.register(explained, requires_plan=False, show_errors=True)
        with tempfile.TemporaryDirectory() as directory:
            provider = Rejected()
            with Project(Path(directory), tools=tools, reasoning=provider) as project:
                await project.run(
                    ProjectRequest(
                        description="fixture",
                        context=ContextSpec(max_input_tokens=100_000),
                    )
                )
        observations = provider.observations
        self.assertIn("Unknown inbox: missing", observations[1]["detail"])
        self.assertNotIn(secret, json.dumps(observations[2]))
        self.assertIn(
            "Failed: ValueError; exception text omitted", observations[2]["detail"]
        )
        # A tool that declares its errors safe, and refusals before any tool runs,
        # tell the agent what to fix.
        self.assertIn("Failed: ValueError: Path is outside", observations[3]["detail"])
        self.assertIn("Not run: ValidationError", observations[4]["detail"])
        self.assertIn("path", observations[4]["detail"])

    async def test_chief_plans_with_readers_and_sees_what_blocks_its_review(self):
        def build() -> str:
            return "built"

        def look() -> str:
            return "seen"

        class Planner(TestReasoning):
            def __init__(self):
                self.prompts = []

            def requirements(self):
                source = project.store.list("source")[0].ref
                return (
                    Requirement(
                        id="r", wording="fixture", source=source, source_quote="fixture"
                    ),
                )

            async def respond(self, packet):
                self.prompts.append(json.loads(packet.prompt)["state"])
                requirement = next(iter(project.store.list("requirement")), None)
                count = len(self.prompts) - 1
                if count in (0, 1):
                    # The Chief first grants itself an execution tool.
                    tool = writer if count == 0 else reader
                    action = Decide(
                        selected="fixture",
                        request=plan_request(
                            requirement.ref, tools=(tool.definition.grant,)
                        ),
                    )
                elif count == 2:
                    action = Read(search="zzz-nothing-matches")
                else:
                    action = Wait(reason="Fixture finished")
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=action,
                )

        tools = ToolRegistry()
        writer = tools.register(build)
        reader = tools.register(look, requires_plan=False)
        provider = Planner()
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=tools, reasoning=provider) as project,
        ):
            await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(max_input_tokens=200_000),
                )
            )
        rejected, planned, searched = (
            p["last_observation"] for p in provider.prompts[1:4]
        )
        self.assertIn("Grant build@1 to worker tasks", rejected["detail"])
        self.assertNotIn("review_blockers", provider.prompts[1])
        self.assertIn("decision_id", planned)
        self.assertEqual(
            provider.prompts[2]["review_blockers"], ["PDR-design: missing deliverable"]
        )
        self.assertTrue(searched["search"].startswith("Nothing matched"))

    async def test_incomplete_provider_response_explains_output_limit(self):
        provider = LiteLLMReasoning("openai/gpt-6-astra")
        packet = ContextPacket(
            agent_id="fixture",
            invocation_id="one",
            request_id="request",
            provider=provider.name,
            model=provider.model,
            prompt="fixture",
            input_tokens=1,
            reserved_output_tokens=1000,
        )
        truncated = litellm.ModelResponse(
            choices=[
                {
                    "index": 0,
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": ""},
                }
            ]
        )
        with (
            patch.object(litellm, "acompletion", return_value=truncated),
            self.assertRaisesRegex(ProviderError, "reserved_output_tokens"),
        ):
            await provider.respond(packet)

    async def test_context_state_lists_current_records_and_open_requests(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory) / "state") as project,
        ):
            refs = []
            for name in ("current.txt", "stale.txt"):
                path = Path(directory) / name
                path.write_text(name)
                refs.append(project.ingest(path))
            project.store.invalidate(refs[1], actor="script", reason="Fixture")
            runtime = Runtime(project, TestReasoning())
            runtime.run_id = "fixture-run"
            chief, worker = (
                AgentSpec(
                    task_id=task,
                    parent_id=None,
                    objective="fixture",
                    context=ContextSpec(),
                    decision_id=None,
                )
                for task in ("chief", "worker")
            )
            runtime.chief_id = chief.id
            ids = {}
            for requester, status in (
                ("script", "completed"),
                ("script", "cancelled"),
                ("script", "failed"),
                (worker.id, "completed"),
                (worker.id, "failed"),
            ):
                record = project.activity.request(
                    RequestRecord(
                        run_id="fixture-run",
                        requester=requester,
                        target="fixture",
                        kind="tool",
                        arguments={},
                        purpose=status,
                    )
                )
                for step in ("dispatched", "running", status):
                    project.activity.transition(record.id, step, actor="script")
                ids[requester, status] = record.id
            results = {
                requester: project.store.put(
                    "tool_result",
                    ids[requester, "completed"],
                    {"value": requester},
                    actor="runtime",
                ).model_dump(mode="json")
                for requester in ("script", worker.id)
            }
            current = refs[0].model_dump(mode="json")
            # The Chief sees every open request and every agent's tool results.
            state = runtime._context_state(chief, AgentState(request_id="chief"))
            self.assertCountEqual(
                state["records"], [current, results["script"], results[worker.id]]
            )
            self.assertCountEqual(
                [r["id"] for r in state["requests"]],
                [ids["script", "failed"], ids[worker.id, "failed"]],
            )
            # A worker sees its own requests and tool records; pinned records
            # already arrive among its sources.
            state = runtime._context_state(
                worker, AgentState(request_id="worker"), (refs[0],)
            )
            self.assertEqual(state["records"], [results[worker.id]])
            self.assertEqual(
                [r["id"] for r in state["requests"]], [ids[worker.id, "failed"]]
            )

    async def test_required_context_raises_a_small_budget_to_the_run_limit(self):
        class Waiting(TestReasoning):
            async def respond(self, packet):
                return AgentTurn(
                    rationale=Rationale(objective="fixture", explanation="Fixture"),
                    action=Wait(reason="fixture"),
                )

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=Waiting()) as project,
        ):
            request = ProjectRequest(
                description="fixture", context=ContextSpec(max_input_tokens=200_000)
            )
            result = await project.run(request)
            chief_id = str(project.store.get("run", result.run_id).data["chief_id"])
            chief = project.store.model("agent", chief_id, AgentSpec)
            # A budget below the runtime's own share of the prompt, as a Chief may set.
            small = chief.context.model_copy(update={"max_input_tokens": 1_000})
            project.store.put(
                "agent",
                chief_id,
                chief.model_copy(update={"context": small}),
                actor="script",
            )
            await project.run(resume=result.run_id)
            raised = [e for e in project.events() if e.type == "agent.budget_raised"]
            self.assertEqual(
                [e.details for e in raised], [{"from": 1_000, "to": 200_000}]
            )
            chief = project.store.model("agent", chief_id, AgentSpec)
            self.assertEqual(chief.context.max_input_tokens, 200_000)
            self.assertFalse(
                [r for r in project.requests() if "Pinned context" in (r.reason or "")]
            )

    async def test_a_run_without_the_sysml_toolkit_stops_before_any_agent(self):
        from sysml.library import LibraryUnavailable

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=TestReasoning()) as project,
            patch("sysml.standard_library", side_effect=LibraryUnavailable("none")),
        ):
            with self.assertRaisesRegex(RuntimeError, "SysML Toolkit"):
                await project.run(ProjectRequest(description="a fixture"))
            self.assertFalse(project.store.list("agent"))

    async def test_waking_the_systems_engineer_gives_it_a_fresh_budget(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory)) as project,
        ):
            runtime = Runtime(project, TestReasoning())
            runtime.run_id = "fixture-run"
            chief = AgentSpec(
                task_id="chief",
                parent_id=None,
                objective="fixture",
                context=ContextSpec(),
                decision_id=None,
            )
            engineer = project.systems_engineer.spec(chief, Budget(max_steps=3))
            runtime.chief_id, runtime.engineer_id = chief.id, engineer.id
            spent = {"status": "waiting", "steps": 3, "tool_calls": 2, "elapsed_s": 9.0}
            for agent in (chief, engineer):
                runtime._add_agent(agent, parent_request=None)
                state = project.store.model("agent_state", agent.id, AgentState)
                runtime._wake(agent, state.model_copy(update=spent), "Fixture")
            woken = project.store.model("agent_state", engineer.id, AgentState)
            self.assertEqual(
                (woken.status, woken.steps, woken.tool_calls, woken.elapsed_s),
                ("active", 0, 0, 0.0),
            )
            # Workers and the chief spend one budget on their whole task.
            self.assertEqual(
                project.store.model("agent_state", chief.id, AgentState).steps, 3
            )

    async def test_reasoning_required_and_explicit_choices_validated(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory)) as project,
        ):
            with self.assertRaisesRegex(RuntimeError, "reasoning"):
                await project.run(ProjectRequest(description="a fixture"))
            self.assertFalse(project.store.list("agent"))
            brief = Path(directory) / "brief.txt"
            brief.write_text("fixture")
            project.ingest(brief)
            await commit_fixture_model(project)
            request = DecisionRequest(
                question="choose",
                kind="engineering",
                criteria=("valid",),
                constraints=(Constraint(metric="mass", unit="kg", maximum=2.0),),
                candidates=(
                    Candidate(
                        id="a",
                        description="Too heavy",
                        metrics={"mass": Quantity(value=3.0, unit="kg")},
                    ),
                    Candidate(
                        id="b",
                        description="Eligible",
                        metrics={"mass": Quantity(value=1.5, unit="kg")},
                    ),
                ),
            )
            for selected in ("unknown", "a"):
                with self.assertRaises(DecisionBlocked):
                    await project.decisions.choose(
                        request, selected=selected, explanation="Fixture"
                    )
            self.assertFalse(project.store.list("decision"))
            choice = await project.decisions.choose(
                request, selected="b", explanation="Within the mass limit"
            )
            record = project.decisions.record(choice)
            self.assertEqual(record.result.selected, "b")
            self.assertEqual(record.author, "script")
            self.assertEqual(project.activity.get(choice).status, "completed")
            self.assertFalse(project.activity.get(choice).attempts)

    async def test_context_assembly_leaves_event_loop_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(root) as project:
                source = root / "source.txt"
                source.write_text("source context")
                agent = AgentSpec(
                    id="worker",
                    task_id="task",
                    parent_id="chief",
                    objective="Inspect",
                    context=ContextSpec(
                        pinned=(project.ingest(source),),
                        max_input_tokens=100_000,
                        reserved_output_tokens=1000,
                    ),
                    decision_id=None,
                )
                assemble = ContextBuilder._assemble

                def slow(*args, **kwargs):
                    time.sleep(0.5)  # Stands in for a large project's assembly.
                    return assemble(*args, **kwargs)

                ticks = 0

                async def tick():
                    nonlocal ticks
                    while True:
                        await asyncio.sleep(0.01)
                        ticks += 1

                ticker = asyncio.create_task(tick())
                with patch.object(ContextBuilder, "_assemble", slow):
                    packet = await project.contexts.build(
                        agent,
                        "fixture",
                        TestReasoning(),
                        instructions="test",
                        state={},
                    )
                ticker.cancel()
                # A blocked loop (WebSocket handshakes time out) would not tick at all.
                self.assertGreater(ticks, 10)
                self.assertEqual(
                    project.store.get("context", packet.id).data["id"], packet.id
                )

    async def test_context_budget_inbox_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(root) as project:
                source = root / "source.txt"
                source.write_text("source context")
                ref = project.ingest(source)
                agent = AgentSpec(
                    id="worker",
                    task_id="task",
                    parent_id="chief",
                    objective="Inspect",
                    context=ContextSpec(
                        pinned=(ref,),
                        max_input_tokens=100_000,
                        reserved_output_tokens=1000,
                    ),
                    decision_id=None,
                )
                project.store.put("agent", agent.id, agent, actor="script")
                message = MessageEnvelope(
                    project_id=project.store.project_id,
                    run_id="run",
                    sender="chief",
                    recipient=agent.id,
                    kind="question",
                    schema_id="Note@1",
                    payload=Note(text="Please inspect").model_dump(mode="json"),
                )
                project.activity.deliver(message)
                project.activity.deliver(message)
                before = len(project.events())
                self.assertEqual(len(project.inbox(agent.id)), 1)
                self.assertEqual(len(project.events()), before)
                packet = await project.contexts.build(
                    agent,
                    "task-request",
                    TestReasoning(),
                    instructions="test",
                    state={},
                )
                entry = project.inbox(agent.id)[0]
                self.assertIn(packet.id, entry.included_packets)
                self.assertIsNone(entry.acknowledged_at)
                self.assertEqual(packet.input_tokens, len(packet.prompt.encode()))
                huge = MessageEnvelope(
                    project_id=project.store.project_id,
                    run_id="run",
                    sender="chief",
                    recipient=agent.id,
                    kind="finding",
                    schema_id="Note@1",
                    payload=Note(text="x" * 200_000).model_dump(mode="json"),
                )
                project.activity.deliver(huge)
                packet_with_omission = await project.contexts.build(
                    agent,
                    "task-request",
                    TestReasoning(),
                    instructions="test",
                    state={},
                )
                self.assertIn(
                    huge.id,
                    {omission.item for omission in packet_with_omission.deferred},
                )
                self.assertNotIn(huge.id, packet_with_omission.message_ids)
                # Acknowledged is not answered: finish still waits on the question.
                project.activity.acknowledge(agent.id, message.id)
                owed = await project.contexts.build(
                    agent,
                    "task-request",
                    TestReasoning(),
                    instructions="test",
                    state={},
                )
                self.assertIn(message.id, owed.message_ids)
                project.store.put(
                    "inbox",
                    message.id,
                    entry.model_copy(update={"response_message_id": "reply"}),
                    actor=agent.id,
                )
                answered = await project.contexts.build(
                    agent,
                    "task-request",
                    TestReasoning(),
                    instructions="test",
                    state={},
                )
                self.assertNotIn(message.id, answered.message_ids)
                tiny = agent.model_copy(
                    update={
                        "context": agent.context.model_copy(
                            update={"max_input_tokens": 1}
                        )
                    }
                )
                with self.assertRaises(ContextOverflow):
                    await project.contexts.build(
                        tiny,
                        "task-request",
                        TestReasoning(),
                        instructions="test",
                        state={},
                    )
                project.activity.acknowledge(agent.id, message.id)
                request = project.activity.request(
                    RequestRecord(
                        run_id="run",
                        requester=agent.id,
                        target="side_effect@1",
                        kind="tool",
                        arguments={},
                        purpose="test recovery",
                    )
                )
                project.activity.transition(request.id, "dispatched", actor="runtime")
                project.activity.transition(request.id, "running", actor="runtime")
                with self.assertRaises(sqlite3.IntegrityError):
                    project.store.db.execute("DELETE FROM events")
            with Project(root) as reopened:
                self.assertEqual(reopened.activity.get(request.id).status, "uncertain")
                self.assertIsNotNone(reopened.inbox(agent.id)[0].acknowledged_at)
                self.assertEqual(reopened.context(packet.id), packet)
                with self.assertRaises(ValueError):
                    reopened.activity.retry(request.id, actor="script", reason="retry")
                reopened.activity.retry(
                    request.id,
                    actor="script",
                    reason="Checked external system; no side effect occurred",
                    reconcile_uncertain=True,
                )
                reopened.activity.transition(request.id, "dispatched", actor="runtime")
                self.assertEqual(len(reopened.activity.get(request.id).attempts), 2)

    async def test_context_drops_carried_mail_and_renders_newest_reads_last(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory)) as project,
        ):
            refs = []
            for name in ("human", "older", "newer"):
                path = Path(directory) / f"{name}.txt"
                path.write_text(f"{name} fixture")
                refs.append(project.ingest(path))
            human, older, newer = refs
            agent = AgentSpec(
                id="worker",
                task_id="task",
                parent_id="chief",
                objective="Inspect",
                context=ContextSpec(
                    instructions="Fixture instructions",
                    pinned=(human,),
                    selected=(newer, older),
                    max_input_tokens=100_000,
                ),
                decision_id=None,
            )
            store = project.store
            store.put("agent", agent.id, agent, actor="script")
            gone = AgentState(request_id="fixture", status="superseded")
            store.put("agent_state", "gone", gone, actor="script")

            def send(sender: str, kind: str, *cited: Ref) -> str:
                message = MessageEnvelope(
                    project_id=store.project_id,
                    run_id="run",
                    sender=sender,
                    recipient=agent.id,
                    kind=kind,
                    schema_id="Note@1",
                    payload=Note(text=f"{sender} {kind}").model_dump(mode="json"),
                    context_refs=cited,
                )
                project.activity.deliver(message)
                return message.id

            echo = send("human:fixture", "finding", human)
            sent = {echo, send("gone", "finding"), send("gone", "request")}
            live = send("peer", "finding")
            # A superseded sender can no longer take the reply its request asked for.
            self.assertEqual(project.activity.obligations(agent.id), ())
            packets = [
                await project.contexts.build(
                    agent, "request", TestReasoning(), instructions="test", state={}
                )
                for _ in range(2)
            ]
            self.assertEqual(set(packets[0].message_ids), {*sent, live})
            # Shown once; then the pinned source carries it, or its sender is gone.
            self.assertEqual(packets[1].message_ids, (live,))
            data = json.loads(packets[1].prompt)
            self.assertEqual(data["user_instructions"], "Fixture instructions")
            self.assertFalse(
                {"instructions", "pinned", "selected", "summaries"}
                & data["agent"]["context"].keys()
            )
            # Pinned first, then reads oldest to newest, so a new read appends.
            self.assertEqual(
                [s["ref"]["id"] for s in data["sources"]],
                [human.id, older.id, newer.id],
            )
            components = packets[1].components
            self.assertGreater(
                components["sources.selected"], components["sources.pinned"]
            )

    async def test_one_publish_takes_a_runs_files_after_its_arguments_return(self):
        def pair() -> list[ProducedFile]:
            paths = [project.output_path(Path(n)) for n in ("first.txt", "second.txt")]
            for path in paths:
                path.write_text(f"TEST FIXTURE {path.name}")
            return [ProducedFile.from_path(path) for path in paths]

        class Publisher(TestReasoning):
            def __init__(self):
                self.prompts = []

            def requirements(self):
                return fixture_requirement(project)

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                self.prompts.append(data)
                store = project.store
                requirement = store.maybe("requirement", "r")
                runs = [r for r in project.requests() if r.kind == "tool"]
                if data["agent"]["task_id"] == "publish":
                    if not runs:
                        action = ToolCall(
                            tool=tool.definition.grant,
                            arguments={},
                            inputs=(requirement.ref,),
                        )
                    elif not store.list("artifact"):
                        action = Publish(
                            files=tuple(
                                PublishedFile(
                                    path=file["path"],
                                    artifact_id=Path(file["path"]).stem,
                                    artifact_kind="editable-design",
                                )
                                for file in runs[0].result
                            ),
                            tool_request=runs[0].id,
                            inputs=(requirement.ref,),
                            requirements=(requirement.ref,),
                        )
                    else:
                        action = Finish(
                            result=TaskReport(summary="Published").model_dump(
                                mode="json"
                            )
                        )
                elif not store.list("decision"):
                    task = TaskAuthorization(
                        id="publish",
                        objective="Publish",
                        tools=(tool.definition.grant,),
                    )
                    action = Decide(
                        selected="fixture",
                        request=plan_request(requirement.ref, tasks=(task,)),
                    )
                elif len(store.list("agent")) == 2:  # The chief and its engineer.
                    action = Spawn(
                        decision_id=data["agent"]["decision_id"], task_id="publish"
                    )
                elif data["messages"]:
                    action = Acknowledge(
                        message_ids=tuple(m["id"] for m in data["messages"])
                    )
                else:
                    action = Wait(reason="Fixture finished")
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=action,
                )

        tools = ToolRegistry()
        tool = tools.register(pair)
        provider = Publisher()
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=tools, reasoning=provider) as project,
        ):
            await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(
                        max_input_tokens=200_000, reserved_output_tokens=1000
                    ),
                )
            )
            (run,) = [r for r in project.requests() if r.kind == "tool"]
            artifacts = {s.ref.id for s in project.store.list("artifact")}
            (delegation,) = [
                e
                for e in project.inbox(provider.prompts[0]["agent"]["id"])
                if e.message.kind == "delegation"
            ]
        self.assertEqual(artifacts, {"first", "second"})
        worker = [p for p in provider.prompts if p["agent"]["task_id"] == "publish"]
        kinds = [p["state"]["last_observation"] for p in worker]
        publish = next(i for i, o in enumerate(kinds) if "refs" in o) - 1
        self.assertEqual(len(kinds[publish + 1]["refs"]), 2)
        # The call's full arguments arrived without a read turn.
        self.assertIn(
            ("job_inputs", run.id),
            {(s["ref"]["kind"], s["ref"]["id"]) for s in worker[publish]["sources"]},
        )
        self.assertIsNotNone(delegation.acknowledged_at)

    async def test_restart_keeps_peer_requests_answerable(self):
        with tempfile.TemporaryDirectory() as directory:
            with Project(Path(directory)) as project:
                records = [
                    project.activity.request(
                        RequestRecord(
                            run_id="script",
                            requester="a",
                            target=target,
                            kind=kind,
                            arguments={},
                            purpose="fixture",
                        )
                    )
                    for kind, target in (("peer", "b"), ("tool", "probe"))
                ]
                for record in records:
                    project.activity.transition(
                        record.id, "dispatched", actor="runtime"
                    )
            # Reopening the workspace runs crash recovery, as an EHopper restart does.
            with Project(Path(directory)) as project:
                peer, tool = (project.activity.get(r.id).status for r in records)
        self.assertEqual(peer, "dispatched")
        self.assertEqual(tool, "uncertain")

    async def test_agents_reason_concurrently_and_correct_rejected_plans(self):
        class Overlap(TestReasoning):
            def __init__(self):
                self.steps = {}
                self.chief_seen = []
                # Chief and both workers must be mid-call at once; a serial loop deadlocks.
                self.all_in_flight = asyncio.Barrier(3)

            def requirements(self):
                return fixture_requirement(project)

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps.get(task, 0)
                self.steps[task] = count + 1
                if task != "chief":
                    await asyncio.wait_for(self.all_in_flight.wait(), 5)
                    action = Finish(
                        result=TaskReport(
                            summary=task, handoffs=("Chief-owned input",)
                        ).model_dump(mode="json")
                    )
                else:
                    self.chief_seen.append(data)
                    requirement = next(iter(project.store.list("requirement")), None)
                    worker = TaskAuthorization(id="A", objective="w", peers=("chief",))
                    if count in (0, 1):
                        # The first plan names an unknown peer; the Chief sees why.
                        peers = ("chief", "ghost") if count == 0 else ("chief",)
                        action = Decide(
                            selected="fixture",
                            request=plan_request(
                                requirement.ref,
                                tasks=(
                                    worker.model_copy(update={"peers": peers}),
                                    worker.model_copy(update={"id": "B"}),
                                ),
                            ),
                        )
                    elif count in (2, 3):
                        action = Spawn(
                            decision_id=data["agent"]["decision_id"],
                            task_id="A" if count == 2 else "B",
                        )
                    elif count == 4:
                        await asyncio.wait_for(self.all_in_flight.wait(), 5)
                        # Workers finish during this turn, so their replies arrive
                        # while the Chief is not yet waiting.
                        while (
                            sum(
                                s.data["status"] == "completed"
                                for s in project.store.list("agent_state")
                            )
                            < 2
                        ):
                            await asyncio.sleep(0.01)
                        action = Wait(reason="Await workers")
                    else:
                        action = Wait(reason="Fixture finished")
                return AgentTurn(
                    rationale=Rationale(objective=task, explanation="Fixture"),
                    action=action,
                )

        provider = Overlap()
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=provider) as project,
        ):
            await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(max_input_tokens=200_000),
                )
            )
            states = [s.data["status"] for s in project.store.list("agent_state")]
        self.assertIn(
            "['ghost']", provider.chief_seen[1]["state"]["last_observation"]["detail"]
        )
        self.assertEqual(states.count("completed"), 2)
        # Woken after its mid-turn Wait, the Chief saw both worker replies, and the
        # handoffs that did not block their finish.
        replies = [
            m for m in provider.chief_seen[5]["messages"] if m["kind"] == "reply"
        ]
        self.assertEqual(len(replies), 2)
        for reply in replies:
            self.assertEqual(reply["payload"]["handoffs"], ["Chief-owned input"])

    async def test_dynamic_workers_exchange_peer_subrequest_and_ping_human(self):
        class Conversation(TestReasoning):
            def __init__(self):
                self.steps = {}
                self.unanswered = []
                self.follow_up = None
                self.task_reply = None
                self.asked = False
                self.replied_at = None

            def requirements(self):
                return fixture_requirement(project)

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps.get(task, 0)
                self.steps[task] = count + 1
                state = data["state"]
                if task == "chief":
                    if count == 0:
                        action = Decide(
                            selected="fixture",
                            request=plan_request(
                                project.store.get("requirement", "r").ref,
                                tasks=(
                                    TaskAuthorization(
                                        id="A", objective="ask peer", peers=("B",)
                                    ),
                                    TaskAuthorization(
                                        id="B", objective="reply to peer", peers=("A",)
                                    ),
                                ),
                            ),
                        )
                    elif count in (1, 2):
                        action = Spawn(
                            decision_id=project.store.list("decision")[0].ref.id,
                            task_id="A" if count == 1 else "B",
                        )
                    else:
                        action = Wait(reason="Fixture has no actual engineering tools")
                elif task == "A":
                    peer = next(
                        (a["id"] for a in state["agents"] if a["task_id"] == "B"), None
                    )
                    if not self.asked and peer is None:
                        # Agents run concurrently; B may not be spawned yet.
                        action = Read()
                    elif not self.asked:
                        self.asked = True
                        action = Send(
                            recipient=peer,
                            request=True,
                            payload=Note(text="Supply geometry evidence").model_dump(
                                mode="json"
                            ),
                        )
                    elif self.follow_up is None and (
                        replies := [m for m in data["messages"] if m["kind"] == "reply"]
                    ):
                        self.follow_up = replies[0]["id"]
                        action = Send(
                            recipient=replies[0]["sender"],
                            reply_to=self.follow_up,
                            payload=Note(text="Follow-up on the geometry").model_dump(
                                mode="json"
                            ),
                        )
                    elif self.follow_up:
                        action = AskHuman(
                            question="Can this peer evidence be used for the design?"
                        )
                    else:
                        action = Wait(reason="Await peer")
                else:
                    messages = [m for m in data["messages"] if m["kind"] == "request"]
                    stage = None if self.replied_at is None else count - self.replied_at
                    if stage is None and not messages:
                        action = Read()  # A's request has not arrived yet.
                    elif stage is None:
                        self.replied_at = count
                        action = Send(
                            recipient=messages[0]["sender"],
                            reply_to=messages[0]["id"],
                            payload=Note(text="Fixture geometry reference").model_dump(
                                mode="json"
                            ),
                        )
                    elif stage == 1:
                        # The reply acknowledged the request, so it left B's context.
                        self.unanswered.extend(messages)
                        self.sent_seen = state["sent_messages"]
                        action = Send(
                            recipient=next(
                                a["id"] for a in state["agents"] if a["task_id"] == "A"
                            ),
                            payload=Note(text="Additional peer information").model_dump(
                                mode="json"
                            ),
                        )
                    elif stage == 2:
                        # Replying to the task assignment is refused with guidance.
                        task_message = next(
                            m for m in data["messages"] if m["kind"] == "delegation"
                        )
                        action = Send(
                            recipient=task_message["sender"],
                            reply_to=task_message["id"],
                            payload=Note(text="Progress so far").model_dump(
                                mode="json"
                            ),
                        )
                    else:
                        if stage == 3:
                            self.task_reply = state["last_observation"]
                        action = Finish(
                            result=TaskReport(summary="Peer replied").model_dump(
                                mode="json"
                            )
                        )
                return AgentTurn(
                    rationale=Rationale(
                        objective=task, explanation="Explicit test rationale"
                    ),
                    action=action,
                )

        provider = Conversation()
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(
                Path(directory) / "state",
                sandbox=Path(directory) / "outputs",
                reasoning=provider,
            ) as project,
        ):
            result = await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(
                        max_input_tokens=200_000, reserved_output_tokens=1000
                    ),
                )
            )
            self.assertEqual(result.status, "awaiting_human")
            workers = [s for s in project.store.list("agent") if s.data["parent_id"]]
            self.assertEqual(len(workers), 2)
            questioner = next(w.ref.id for w in workers if w.data["task_id"] == "A")
            sibling = next(w.ref.id for w in workers if w.data["task_id"] == "B")
            self.assertEqual(
                project.store.get("agent_state", questioner).data["status"], "waiting"
            )
            self.assertEqual(
                project.store.get("agent_state", sibling).data["status"], "completed"
            )
            (question,) = project.human.inbox()
            self.assertEqual(question.message.sender, questioner)
            peers = [r for r in project.requests() if r.kind == "peer"]
            self.assertEqual(len(peers), 1)
            self.assertEqual(peers[0].status, "completed")
            self.assertFalse(provider.unanswered)
            # B's own reply stays visible after the request it answered left its inbox.
            self.assertEqual([m["kind"] for m in provider.sent_seen], ["reply"])
            (request,) = [
                e for e in project.inbox(sibling) if e.message.kind == "request"
            ]
            self.assertIsNotNone(request.response_message_id)
            self.assertIsNotNone(request.acknowledged_at)
            (follow_up,) = [
                s.data
                for s in project.store.list("message")
                if s.data["reply_to"] == provider.follow_up
            ]
            self.assertEqual(follow_up["sender"], questioner)
            (reply,) = [
                e
                for e in project.inbox(questioner)
                if e.message.id == provider.follow_up
            ]
            self.assertIsNotNone(reply.acknowledged_at)
            self.assertIn("without reply_to", provider.task_reply["detail"])
            self.assertIsNotNone(peers[0].parent_id)
            self.assertTrue(project.trace(peers[0].parent_id)["events"])
            self.assertTrue(project.store.list("rationale"))
            packets = project.store.list("context")
            self.assertEqual(
                {packet.data["agent_id"] for packet in packets},
                {agent.ref.id for agent in project.store.list("agent")},
            )
            for packet in packets:
                self.assertEqual(
                    json.loads(packet.data["prompt"])["state"]["sandbox"],
                    str(project.sandbox),
                )
            # A keep_workers note reaches every agent without replanning or stopping them.
            statuses = {
                s.ref.id: s.data["status"] for s in project.store.list("agent_state")
            }
            plan = project.store.list("decision")[0].ref.id
            note = project.human.interject(
                "Prioritise CAD",
                author="human",
                run_id=result.run_id,
                keep_workers=True,
            )
            self.assertEqual(
                {s.ref.id: s.data["status"] for s in project.store.list("agent_state")},
                statuses,
            )
            self.assertFalse(project.store.get("decision", plan).stale)
            self.assertIn(note, project.human.references(result.run_id))
            project.human.reply(
                question.message.request_id,
                "Use the new measurement instead",
                author="human",
            )
            self.assertEqual(
                project.store.get("agent_state", questioner).data["status"],
                "superseded",
            )
            self.assertEqual(
                project.store.get("agent_state", sibling).data["status"], "completed"
            )
            result = await project.run(resume=result.run_id)
            self.assertEqual(result.status, "incomplete")
            self.assertFalse(project.human.inbox())

    async def test_finished_and_superseded_workers_free_their_agent_slot(self):
        class Spawner(TestReasoning):
            count = 0

            def requirements(self):
                return fixture_requirement(project, "r1")

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                action = Wait(reason="Fixture waits")
                if data["agent"]["task_id"] == "chief":
                    self.count += 1
                    tasks = tuple(
                        TaskAuthorization(id=task, objective="fixture")
                        for task in ("A", "B")
                    )
                    if self.count == 1:
                        action = Decide(
                            selected="fixture",
                            request=plan_request(
                                project.store.get("requirement", "r1").ref, tasks=tasks
                            ),
                        )
                    elif self.count in (2, 4):
                        action = Spawn(
                            decision_id=data["agent"]["decision_id"],
                            task_id="A" if self.count == 2 else "B",
                        )
                return AgentTurn(
                    rationale=Rationale(objective="fixture", explanation="Fixture"),
                    action=action,
                )

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=Spawner()) as project,
        ):
            result = await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(max_input_tokens=200_000),
                    budget=Budget(max_agents=1),
                )
            )
            (worker,) = [
                s for s in project.store.list("agent") if s.data["task_id"] == "A"
            ]
            # As human input leaves an unfinished worker: no longer holding a slot.
            state = project.store.model("agent_state", worker.ref.id, AgentState)
            project.store.put(
                "agent_state",
                worker.ref.id,
                state.model_copy(update={"status": "superseded"}),
                actor="script",
            )
            await project.run(resume=result.run_id)
            self.assertEqual(
                sorted(s.data["task_id"] for s in project.store.list("agent")),
                ["A", "B", "chief", "systems_engineer"],
            )

    async def test_a_reply_that_spans_a_replan_is_not_acted_on(self):
        replanned = asyncio.Event()
        probes = []

        def probe() -> str:
            probes.append("probe")
            return "ok"

        class Overlap(TestReasoning):
            def __init__(self):
                self.steps = {}

            def requirements(self):
                return fixture_requirement(project, "r1")

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps[task] = self.steps.get(task, 0) + 1
                action = Wait(reason="Fixture waits")
                if task == "A" and count == 1:
                    # The Chief replans while this call is out.
                    await replanned.wait()
                    action = ToolCall(tool=tool.definition.grant, arguments={})
                elif task == "chief":
                    tasks = (
                        TaskAuthorization(
                            id="A", objective="probe", tools=(tool.definition.grant,)
                        ),
                    )
                    if count in (1, 3):
                        action = Decide(
                            selected="fixture",
                            request=plan_request(
                                project.store.get("requirement", "r1").ref, tasks=tasks
                            ),
                        )
                    elif count == 2:
                        action = Spawn(
                            decision_id=data["agent"]["decision_id"], task_id="A"
                        )
                    elif count == 4:
                        replanned.set()
                return AgentTurn(
                    rationale=Rationale(objective=task, explanation="Fixture"),
                    action=action,
                )

        tools = ToolRegistry()
        tool = tools.register(probe)
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=tools, reasoning=Overlap()) as project,
        ):
            await project.run(
                ProjectRequest(
                    description="fixture",
                    context=ContextSpec(max_input_tokens=200_000),
                )
            )
            dropped = [
                e.details for e in project.events() if e.type == "agent.turn_superseded"
            ]
        self.assertEqual(
            dropped, [{"reason": "The agent's plan changed during this invocation"}]
        )
        self.assertFalse(probes)

    async def test_a_plan_decision_keeps_the_budget_raised_in_its_turn(self):
        class Planner(TestReasoning):
            plan = False

            def requirements(self):
                return fixture_requirement(project, "r1")

            async def respond(self, packet):
                requirement = project.store.maybe("requirement", "r1")
                action = Wait(reason="Fixture waits")
                if self.plan and not project.store.list("decision"):
                    action = Decide(
                        selected="fixture", request=plan_request(requirement.ref)
                    )
                return AgentTurn(
                    rationale=Rationale(objective="fixture", explanation="Fixture"),
                    action=action,
                )

        provider = Planner()
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=provider) as project,
        ):
            request = ProjectRequest(
                description="fixture", context=ContextSpec(max_input_tokens=200_000)
            )
            result = await project.run(request)
            chief_id = str(project.store.get("run", result.run_id).data["chief_id"])
            chief = project.store.model("agent", chief_id, AgentSpec)
            small = chief.context.model_copy(update={"max_input_tokens": 1_000})
            project.store.put(
                "agent",
                chief_id,
                chief.model_copy(update={"context": small}),
                actor="script",
            )
            provider.plan = True
            await project.run(resume=result.run_id)
            chief = project.store.model("agent", chief_id, AgentSpec)
            self.assertIsNotNone(chief.decision_id)
            # Raised once: recording the plan no longer restores the stale budget.
            raised = [e for e in project.events() if e.type == "agent.budget_raised"]
            self.assertEqual(
                [e.details for e in raised], [{"from": 1_000, "to": 200_000}]
            )

    async def test_run_input_token_budget_blocks_dispatch_across_resume(self):
        class Waiting(TestReasoning):
            calls = 0

            async def respond(self, packet):
                self.calls += 1
                return AgentTurn(
                    rationale=Rationale(objective="fixture", explanation="Fixture"),
                    action=Wait(reason="fixture"),
                )

        provider = Waiting()
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=provider) as project,
        ):
            result = await project.run(
                ProjectRequest(
                    description="fixture", context=ContextSpec(max_input_tokens=200_000)
                )
            )
            sent = sum(
                e.details["input_tokens"]
                for e in project.events()
                if e.type == "provider.dispatched"
            )
            run = project.store.get("run", result.run_id).data
            run["request"]["budget"]["max_run_input_tokens"] = sent + 1
            project.store.put("run", result.run_id, run, actor="script")
            # The resumed run counts what it already sent, so nothing more goes out.
            result = await project.run(resume=result.run_id)
            self.assertEqual(provider.calls, 1)
            self.assertIn("input-token budget exhausted", "".join(result.open_items))


if __name__ == "__main__":
    unittest.main()
