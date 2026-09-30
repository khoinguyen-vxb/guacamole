import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

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
)
from guacamole.context import ContextOverflow, ProviderError
from guacamole.contracts import (
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
    Wait,
)
from guacamole.decision import DecisionBlocked
from guacamole.providers.astra import AstraReasoning


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_astra_uses_the_exact_counted_packet(self):
        expected = AgentTurn(
            rationale=Rationale(
                objective="fixture", explanation="No engineering claim"
            ),
            action=Wait(reason="await inputs"),
        )

        class FakeHTTP(AstraReasoning):
            def __init__(self):
                super().__init__()
                self.calls = []

            def _post(self, path, data):
                self.calls.append((path, data))
                if path == "/input_tokens":
                    return {"input_tokens": len(data["input"])}
                return {
                    "id": "fixture-response",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": expected.model_dump_json(),
                                }
                            ],
                        }
                    ],
                }

        provider = FakeHTTP()
        prompt = '{"instructions":"Return JSON", "sources":[]}'
        count = await provider.count_tokens(prompt)
        packet = ContextPacket(
            agent_id="fixture",
            invocation_id="one",
            request_id="request",
            provider=provider.name,
            model=provider.model,
            prompt=prompt,
            input_tokens=count,
            reserved_output_tokens=1000,
        )
        result = await provider.respond(packet)
        self.assertEqual(result.provider_request_id, "fixture-response")
        self.assertEqual(provider.calls[0][1]["input"], provider.calls[1][1]["input"])
        self.assertEqual(provider.calls[1][1]["model"], "gpt-6-astra")
        self.assertFalse(provider.calls[1][1]["store"])
        self.assertNotIn("tools", provider.calls[1][1])

    async def test_provider_http_diagnostics_survive_without_server_text(self):
        secret = "fixture-secret-must-not-persist"

        class CountedAstra(AstraReasoning):
            async def count_tokens(self, prompt):
                return len(prompt)

        for phase, provider in (
            ("context", AstraReasoning()),
            ("provider", CountedAstra()),
        ):
            for code, expected in (
                ("credit_balance_exhausted", "API credits or quota exhausted"),
                ("insufficient_quota", "API credits or quota exhausted"),
                ("rate_limit_exceeded", "API rate limit exceeded"),
                (None, "Check API rate limits and billing quota"),
            ):
                body = json.dumps({"error": {"code": code, "message": secret}})
                error = HTTPError(
                    "https://api.openai.com/v1/responses",
                    429,
                    secret,
                    {},
                    io.BytesIO(body.encode() if code else secret.encode()),
                )
                with (
                    self.subTest(phase=phase, code=code),
                    tempfile.TemporaryDirectory() as directory,
                    patch.dict("os.environ", {"OPENAI_API_KEY": secret}),
                    patch("guacamole.providers.astra.urlopen", side_effect=error),
                    Project(Path(directory), reasoning=provider) as project,
                ):
                    result = await project.run(ProjectRequest(description="fixture"))
                    self.assertEqual(result.status, "incomplete")
                    self.assertIn(expected, result.open_items[-1])
                    request = project.requests()[0]
                    self.assertIn("HTTP 429", request.reason)
                    event = next(
                        e for e in project.events() if e.type == "action.rejected"
                    )
                    self.assertEqual(event.details["phase"], phase)
                    self.assertIn(expected, event.details["detail"])
                    self.assertNotIn(secret, json.dumps(project.trace(request.id)))

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

    async def test_incomplete_provider_response_explains_output_limit(self):
        provider = AstraReasoning()
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
        with (
            patch.object(
                provider,
                "_post",
                return_value={
                    "id": "fixture-response",
                    "status": "incomplete",
                    "output": [],
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            ),
            self.assertRaisesRegex(ProviderError, "reserved_output_tokens"),
        ):
            await provider.respond(packet)

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

    async def test_dynamic_workers_exchange_peer_subrequest_and_ping_human(self):
        class Conversation(TestReasoning):
            def __init__(self):
                self.steps = {}

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
                    if count == 0:
                        peer = next(
                            a["id"] for a in state["agents"] if a["task_id"] == "B"
                        )
                        action = Send(
                            recipient=peer,
                            request=True,
                            payload=Note(text="Supply geometry evidence").model_dump(
                                mode="json"
                            ),
                        )
                    elif any(m["kind"] == "reply" for m in data["messages"]):
                        action = AskHuman(
                            question="Can this peer evidence be used for the design?"
                        )
                    else:
                        action = Wait(reason="Await peer")
                else:
                    messages = [m for m in data["messages"] if m["kind"] == "request"]
                    if messages and count == 0:
                        action = Send(
                            recipient=messages[0]["sender"],
                            reply_to=messages[0]["id"],
                            payload=Note(text="Fixture geometry reference").model_dump(
                                mode="json"
                            ),
                        )
                    elif messages and count == 1:
                        action = Send(
                            recipient=messages[0]["sender"],
                            payload=Note(text="Additional peer information").model_dump(
                                mode="json"
                            ),
                        )
                    else:
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

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(
                Path(directory) / "state",
                sandbox=Path(directory) / "outputs",
                reasoning=Conversation(),
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
