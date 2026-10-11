import asyncio
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import litellm
from runtime_support import TestReasoning, plan_request

from guacamole import (
    AgentSpec,
    AgentTurn,
    AskHuman,
    Candidate,
    Constraint,
    ContextSpec,
    DecisionRequest,
    Note,
    Project,
    ProjectRequest,
    Quantity,
    Requirement,
    TaskAuthorization,
    TaskReport,
    ToolRegistry,
)
from guacamole.agents.runtime import Runtime
from guacamole.context import (
    ContextBuilder,
    ContextOverflow,
    ProviderError,
    encode_context,
)
from guacamole.contracts import (
    Acknowledge,
    AgentState,
    ContextPacket,
    Decide,
    Finish,
    MessageEnvelope,
    Rationale,
    Read,
    Record,
    RequestRecord,
    Send,
    Spawn,
    ToolCall,
    Wait,
)
from guacamole.decision import DecisionBlocked
from guacamole.providers.litellm import LiteLLMReasoning


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_context_references_only_identical_included_decision_evidence(self):
        ref = {"kind": "source", "id": "evidence", "revision": 1, "sha256": "hash"}
        content = {"text": "Historical engineering evidence " * 100}
        entries = [
            {"ref": ref, "content": content},
            {"ref": ref | {"revision": 2}, "content": content},
            {"ref": ref, "content": {"text": "Different historical content"}},
        ]
        payload = {"sources": [
            {"ref": ref, "data": content},
            {"ref": {"kind": "decision"}, "data": {
                "request": {"context": entries, "question": "Choose design"},
                "result": {"selected": "approved"},
            }},
        ]}
        original = json.dumps(payload)
        encoded = encode_context(payload)
        sources = json.loads(encoded)["sources"]
        context = sources[1]["data"]["request"]["context"]
        self.assertEqual(context[0]["content"], {"included_source": ref})
        self.assertEqual(context[1:], entries[1:])
        self.assertEqual(sources[0]["data"], content)
        self.assertEqual(sources[1]["data"]["result"], {"selected": "approved"})
        self.assertEqual(json.dumps(payload), original)
        self.assertLess(len(encoded), len(original))

    async def test_context_obeys_provider_character_limit_independently_of_tokens(self):
        class Limited(TestReasoning):
            max_input_chars = 30_000

            async def count_tokens(self, prompt):
                return len(prompt) // 10

        with tempfile.TemporaryDirectory() as directory, Project(Path(directory)) as project:
            source = Path(directory) / "large.txt"
            source.write_text("π" * 30_000)
            ref = project.ingest(source)
            agent = AgentSpec(
                id="worker", task_id="task", parent_id="chief", objective="Inspect",
                context=ContextSpec(selected=(ref,), max_input_tokens=100_000),
                decision_id=None,
            )
            packet = await project.contexts.build(
                agent, "request", Limited(), instructions="test", state={},
            )
            self.assertLessEqual(len(packet.prompt), Limited.max_input_chars)
            self.assertNotIn(ref, packet.sources)
            self.assertTrue(packet.deferred)
            self.assertEqual(packet.input_tokens, await Limited().count_tokens(packet.prompt))
            pinned = agent.model_copy(update={"context": agent.context.model_copy(
                update={"pinned": (ref,), "selected": ()},
            )})
            with self.assertRaisesRegex(ContextOverflow, "characters"):
                await project.contexts.build(
                    pinned, "request", Limited(), instructions="test", state={},
                )

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
                            context=ContextSpec(selected=(bad,)),
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
                    agent = project.store.model(
                        "agent", project.store.list("agent")[0].ref.id, AgentSpec
                    )
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
                state = project.store.list("agent_state")[0].data
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
                            context=ContextSpec(selected=(current,)),
                        )
                    )
                    observations = provider.observations
                    # The invalid turn's Wait must not run; the next turn can correct it.
                    self.assertEqual(len(observations), 2)
                    self.assertEqual(observations[1]["phase"], "rationale")
                    self.assertIn("current Ref", observations[1]["detail"])
                    self.assertNotIn(bad.id, observations[1]["detail"])
                    rationales = project.store.list("rationale")
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
            result = await project.run(ProjectRequest(description="fixture"))
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

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps.get(task, 0)
                self.steps[task] = count + 1
                source = project.store.list("source")[0].ref
                tasks = (
                    TaskAuthorization(
                        id="A", objective="probe", tools=(tool.definition.grant,)
                    ),
                )
                if task == "chief":
                    if count in (0, 3):
                        # The second requirement leaves the first plan uncovered.
                        action = Record(
                            record=Requirement(
                                id=f"r{count // 3 + 1}",
                                wording="fixture",
                                source=source,
                                source_quote="fixture",
                            )
                        )
                    elif count in (1, 4):
                        action = Decide(
                            selected="fixture",
                            request=plan_request(
                                *(s.ref for s in project.store.list("requirement")),
                                tasks=tasks,
                            ),
                        )
                    elif count == 2:
                        self.first_plan = data["agent"]["decision_id"]
                        action = Spawn(decision_id=self.first_plan, task_id="A")
                    else:
                        action = Wait(reason="Fixture finished")
                else:
                    self.worker_results.append(data["state"]["last_observation"])
                    # Concurrent turns may overlap the replan; probe until it lands.
                    done = data["state"]["last_observation"].get("result") == "ok"
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
                (chief,) = [a for a in agents if not a["parent_id"]]
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
        # Turn 1 ran under the uncovered first plan; a later turn under the replacement.
        self.assertEqual(provider.worker_results[1]["phase"], "action")
        self.assertIn("ok", [r.get("result") for r in provider.worker_results])

    async def test_rejected_action_explains_runtime_errors_but_not_tool_errors(self):
        secret = "fixture-secret-must-not-persist"

        def leaky() -> str:
            raise ValueError(secret)

        class Rejected(TestReasoning):
            def __init__(self):
                self.observations = []

            async def respond(self, packet):
                self.observations.append(
                    json.loads(packet.prompt)["state"]["last_observation"]
                )
                actions = (
                    Acknowledge(message_id="missing"),
                    ToolCall(tool=tool.definition.grant, arguments={}),
                    Wait(reason="Fixture finished"),
                )
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=actions[len(self.observations) - 1],
                )

        tools = ToolRegistry()
        tool = tools.register(leaky, requires_plan=False)
        with tempfile.TemporaryDirectory() as directory:
            provider = Rejected()
            with Project(Path(directory), tools=tools, reasoning=provider) as project:
                await project.run(ProjectRequest(description="fixture"))
        self.assertIn("Unknown inbox: missing", provider.observations[1]["detail"])
        self.assertNotIn(secret, json.dumps(provider.observations[2]))

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
            ids = {}
            for status in ("completed", "cancelled", "failed"):
                record = project.activity.request(
                    RequestRecord(
                        run_id="fixture-run",
                        requester="script",
                        target="fixture",
                        kind="tool",
                        arguments={},
                        purpose=status,
                    )
                )
                for step in ("dispatched", "running", status):
                    project.activity.transition(record.id, step, actor="script")
                ids[status] = record.id
            agent = AgentSpec(
                task_id="fixture",
                parent_id=None,
                objective="fixture",
                context=ContextSpec(),
                decision_id=None,
            )
            state = runtime._context_state(agent, AgentState(request_id=ids["failed"]))
            self.assertEqual(state["records"], [refs[0].model_dump(mode="json")])
            self.assertEqual([r["id"] for r in state["requests"]], [ids["failed"]])

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

    async def test_reasoning_required_and_explicit_choices_validated(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory)) as project,
        ):
            with self.assertRaisesRegex(RuntimeError, "reasoning"):
                await project.run(ProjectRequest(description="a fixture"))
            self.assertFalse(project.store.list("agent"))
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

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps.get(task, 0)
                self.steps[task] = count + 1
                if task != "chief":
                    await asyncio.wait_for(self.all_in_flight.wait(), 5)
                    action = Finish(
                        result=TaskReport(summary=task).model_dump(mode="json")
                    )
                else:
                    self.chief_seen.append(data)
                    requirement = next(iter(project.store.list("requirement")), None)
                    worker = TaskAuthorization(id="A", objective="w", peers=("chief",))
                    if count == 0:
                        action = Record(
                            record=Requirement(
                                id="r",
                                wording="fixture",
                                source=project.store.list("source")[0].ref,
                                source_quote="fixture",
                            )
                        )
                    elif count in (1, 2):
                        # The first plan names an unknown peer; the Chief sees why.
                        peers = ("chief", "ghost") if count == 1 else ("chief",)
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
                    elif count in (3, 4):
                        action = Spawn(
                            decision_id=data["agent"]["decision_id"],
                            task_id="A" if count == 3 else "B",
                        )
                    elif count == 5:
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
            "['ghost']", provider.chief_seen[2]["state"]["last_observation"]["detail"]
        )
        self.assertEqual(states.count("completed"), 2)
        # Woken after its mid-turn Wait, the Chief saw both worker replies.
        self.assertEqual(
            len(
                [m for m in provider.chief_seen[6]["messages"] if m["kind"] == "reply"]
            ),
            2,
        )

    async def test_dynamic_workers_exchange_peer_subrequest_and_ping_human(self):
        class Conversation(TestReasoning):
            def __init__(self):
                self.steps = {}
                self.unanswered = []
                self.follow_up = None
                self.task_reply = None
                self.asked = False
                self.replied_at = None

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps.get(task, 0)
                self.steps[task] = count + 1
                state = data["state"]
                if task == "chief":
                    if count == 0:
                        source = project.store.list("source")[0].ref
                        action = Record(
                            record=Requirement(
                                id="r",
                                wording="fixture",
                                source=source,
                                source_quote="fixture",
                            )
                        )
                    elif count == 1:
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
                    elif count in (2, 3):
                        action = Spawn(
                            decision_id=project.store.list("decision")[0].ref.id,
                            task_id="A" if count == 2 else "B",
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
                e for e in project.inbox(questioner) if e.message.id == provider.follow_up
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


if __name__ == "__main__":
    unittest.main()
