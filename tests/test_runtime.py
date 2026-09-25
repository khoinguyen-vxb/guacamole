import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from runtime_support import TestJev, TestReasoning, plan_request

from guacamole import (
    AgentSpec,
    AgentTurn,
    Candidate,
    ContextSpec,
    DecisionRequest,
    Note,
    Project,
    ProjectRequest,
    Requirement,
    TaskAuthorization,
    TaskReport,
)
from guacamole.context import ContextOverflow
from guacamole.contracts import (
    ContextPacket,
    Decide,
    Finish,
    MessageEnvelope,
    Rationale,
    Record,
    RequestRecord,
    Send,
    Spawn,
    Wait,
)
from guacamole.decision import DecisionBlocked
from guacamole.providers.astra import AstraReasoning


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_mandatory_jev_and_invalid_decisions(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=TestReasoning()) as project,
        ):
            with self.assertRaisesRegex(RuntimeError, "Jev"):
                await project.run(ProjectRequest(description="a fixture"))
            self.assertFalse(project.store.list("agent"))
            request = DecisionRequest(
                question="choose",
                kind="engineering",
                criteria=("valid",),
                candidates=(Candidate(id="a", description="A"),),
            )
            with self.assertRaises(DecisionBlocked):
                await project.decisions.choose(request)
            provider = TestJev()
            provider.abstain = True
            project.decisions.provider = provider
            with self.assertRaises(DecisionBlocked):
                await project.decisions.choose(request)
            self.assertFalse(project.store.list("decision")[0].data["accepted"])

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

    async def test_dynamic_workers_exchange_peer_subrequest(self):
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
                            )
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
                        action = Finish(
                            result=TaskReport(
                                summary="Peer evidence received"
                            ).model_dump(mode="json")
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
                Path(directory), reasoning=Conversation(), jev=TestJev()
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
            self.assertEqual(result.status, "incomplete")
            workers = [s for s in project.store.list("agent") if s.data["parent_id"]]
            self.assertEqual(len(workers), 2)
            peers = [r for r in project.requests() if r.kind == "peer"]
            self.assertEqual(len(peers), 1)
            self.assertEqual(peers[0].status, "completed")
            self.assertIsNotNone(peers[0].parent_id)
            self.assertTrue(project.trace(peers[0].parent_id)["events"])
            self.assertTrue(project.store.list("rationale"))


if __name__ == "__main__":
    unittest.main()
