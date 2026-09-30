import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from runtime_support import TestReasoning, plan_request

from guacamole import (
    AgentTurn,
    AskHuman,
    ContextSpec,
    Project,
    ProjectRequest,
    Requirement,
    ToolRegistry,
)
from guacamole.contracts import Decide, Rationale, Record, ToolCall, Wait
from guacamole.tools.mcp import ToolSession
from guacamole.websocket import Command, HumanReply, Interject, WebSocketBridge


def turn(action):
    return AgentTurn(
        rationale=Rationale(
            objective="Human interaction fixture", explanation="No engineering claim"
        ),
        action=action,
    )


def brief():
    return ProjectRequest(
        description="payload mass 2 kg", context=ContextSpec(max_input_tokens=200_000)
    )


class HumanTests(unittest.IsolatedAsyncioTestCase):
    async def test_question_reply_restart_and_amended_requirement(self):
        class Questioner(TestReasoning):
            calls = 0

            async def respond(self, packet):
                self.calls += 1
                if project.human.references(
                    json.loads(packet.prompt)["state"]["run_id"]
                ):
                    return turn(Wait(reason="Fixture received the correction"))
                requirement = project.store.maybe("requirement", "payload")
                if requirement is None:
                    return turn(
                        Record(
                            record=Requirement(
                                id="payload",
                                wording="payload mass 2 kg",
                                source=project.store.get("source", "brief").ref,
                                source_quote="payload mass 2 kg",
                            )
                        )
                    )
                if not project.store.list("decision"):
                    return turn(
                        Decide(
                            request=plan_request(requirement.ref), selected="fixture"
                        )
                    )
                return turn(
                    AskHuman(
                        question="Confirm the payload mass?",
                        choices=("2 kg", "2.5 kg"),
                        references=(requirement.ref,),
                    )
                )

        with tempfile.TemporaryDirectory() as directory:
            provider = Questioner()
            with Project(Path(directory), reasoning=provider) as project:
                result = await project.run(brief())
                self.assertEqual(result.status, "awaiting_human")
                (entry,) = project.human.inbox()
                question_id = entry.message.request_id
                self.assertEqual(result.human_requests, (question_id,))
                self.assertIsNotNone(entry.delivered_at)
                old_plan = project.store.list("decision")[0].ref
                calls = provider.calls
                self.assertTrue(
                    any(e.type == "human.requested" for e in project.events())
                )
            with Project(Path(directory), reasoning=provider) as project:
                result = await project.run(resume=result.run_id)
                self.assertEqual(result.status, "awaiting_human")
                self.assertEqual(provider.calls, calls)
                source = project.human.reply(
                    question_id, "payload mass 2.5 kg", author="test human"
                )
                self.assertFalse(project.human.inbox())
                self.assertEqual(project.activity.get(question_id).status, "completed")
                self.assertTrue(project.store.resolve(old_plan).stale)
                corrected = project.record_requirement(
                    Requirement(
                        id="payload",
                        wording="payload mass 2.5 kg",
                        source=source,
                        source_quote="payload mass 2.5 kg",
                    ),
                    actor="human:test human",
                )
                result = await project.run(resume=result.run_id)
                self.assertEqual(result.status, "incomplete")
                latest_packets = [
                    s
                    for s in project.store.list("context")
                    if source.model_dump(mode="json") in s.data["sources"]
                ]
                self.assertTrue(latest_packets)
                plan = await project.decisions.choose(
                    plan_request(corrected),
                    run_id=result.run_id,
                    selected="fixture",
                    explanation="Use corrected input",
                )
                decision = project.decisions.record(plan)
                self.assertIn(source, [item.ref for item in decision.request.context])
                with self.assertRaises(ValueError):
                    project.human.reply(question_id, "duplicate", author="test human")
                before = len(project.events())
                with Project(Path(directory), read_only=True) as history:
                    self.assertFalse(history.human.inbox())
                    self.assertEqual(len(history.human.inbox(pending_only=False)), 1)
                    self.assertEqual(len(history.events()), before)

    async def test_live_correction_discards_proposal_and_marks_late_result_stale(self):
        proposed, release_proposal = asyncio.Event(), asyncio.Event()
        running, release_tool = asyncio.Event(), asyncio.Event()
        executions = []

        async def compute() -> int:
            executions.append("started")
            running.set()
            await release_tool.wait()
            return 7

        class SlowProposal(TestReasoning):
            async def respond(self, packet):
                if project.human.references(project.runtime.run_id):
                    return turn(Wait(reason="Replan after correction"))
                requirement = project.store.maybe("requirement", "payload")
                if requirement is None:
                    return turn(
                        Record(
                            record=Requirement(
                                id="payload",
                                wording="payload mass 2 kg",
                                source=project.store.get("source", "brief").ref,
                                source_quote="payload mass 2 kg",
                            )
                        )
                    )
                if not project.store.list("decision"):
                    return turn(
                        Decide(
                            selected="fixture",
                            request=plan_request(
                                requirement.ref, tools=(tool.definition.grant,)
                            ),
                        )
                    )
                proposed.set()
                await release_proposal.wait()
                return turn(ToolCall(tool=tool.definition.grant, arguments={}))

        with tempfile.TemporaryDirectory() as directory:
            tools = ToolRegistry()
            tool = tools.register(compute)
            with Project(
                Path(directory), tools=tools, reasoning=SlowProposal()
            ) as project:
                task = asyncio.create_task(project.run(brief()))
                await asyncio.wait_for(proposed.wait(), 5)
                source = project.human.interject(
                    "Change the payload mass to 2.5 kg", author="test human"
                )
                release_proposal.set()
                result = await asyncio.wait_for(task, 10)
                self.assertFalse(executions)
                self.assertTrue(
                    any(e.type == "agent.turn_superseded" for e in project.events())
                )
                self.assertTrue(project.human.references(result.run_id))
                requirement = project.store.get("requirement", "payload").ref
                decision = await project.decisions.choose(
                    plan_request(requirement, tools=(tool.definition.grant,)),
                    selected="fixture",
                    explanation="Test fixture selection",
                    run_id=result.run_id,
                )
                job = project.executor.submit(
                    tool, {}, run_id=result.run_id, decision_id=decision
                )
                await asyncio.wait_for(running.wait(), 5)
                project.human.interject(
                    "Reassess that calculation",
                    author="test human",
                    run_id=result.run_id,
                    references=(project.store.get("decision", decision).ref, source),
                )
                self.assertEqual(job.record.status, "running")
                release_tool.set()
                self.assertEqual(await job.collect(), 7)
                self.assertEqual(job.record.status, "completed")
                self.assertTrue(project.store.get("tool_result", job.id).stale)

    async def test_websocket_human_commands_are_deduplicated_and_host_only(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory)) as project,
        ):
            request_id = project.human.ask(
                AskHuman(question="Which input?"), run_id="script", sender="script"
            )
            bridge = WebSocketBridge(ToolSession(project))
            command = Command(
                id="answer",
                command=HumanReply(
                    kind="reply_human",
                    request_id=request_id,
                    text="Use the supplied measurement",
                    author="test human",
                ),
            )
            response = bridge.execute(command)
            before = len(project.events())
            self.assertEqual(bridge.execute(command), response)
            self.assertEqual(len(project.events()), before)
            self.assertEqual(project.human.version("script"), 1)
            with self.assertRaises(ValueError):
                bridge.execute(
                    command.model_copy(
                        update={
                            "command": command.command.model_copy(
                                update={"text": "different"}
                            )
                        }
                    )
                )
            bridge.session.agent_id = "worker"
            with self.assertRaises(PermissionError):
                bridge.execute(
                    Command(
                        command=Interject(
                            kind="interject",
                            run_id="script",
                            text="Spoofed correction",
                            author="human",
                        )
                    )
                )


if __name__ == "__main__":
    unittest.main()
