import json
import tempfile
import unittest
from pathlib import Path

from runtime_support import TestReasoning

from guacamole import (
    AgentTurn,
    ContextSpec,
    Note,
    Project,
    ProjectRequest,
    Usage,
    Watchdog,
)
from guacamole.contracts import Rationale, Read, Send, Wait


class WatchdogTests(unittest.IsolatedAsyncioTestCase):
    async def test_watchdog_helps_looping_agent_near_its_context_budget(self):
        rationale = Rationale(objective="Fixture", explanation="Fixture")

        class Supervisor(TestReasoning):
            effort = "max"

            def __init__(self):
                self.states = []

            async def respond(self, packet):
                state = json.loads(packet.prompt)["state"]
                self.states.append(state)
                if state["last_observation"]:
                    return AgentTurn(rationale=rationale, action=Wait(reason="Done"))
                note = Note(text="Decision is stale; decide a new plan, then compact.")
                return AgentTurn(
                    rationale=rationale,
                    action=Send(
                        recipient=state["issues"][0]["agent_id"],
                        payload=note.model_dump(mode="json"),
                    ),
                )

        class Looping(TestReasoning):
            def __init__(self, stale):
                self.stale, self.packets = stale, []

            async def respond(self, packet):
                self.packets.append(packet)
                if len(self.packets) == 4:  # Three rejected reads are now logged.
                    await project.watchdog.check()
                senders = {m["sender"] for m in json.loads(packet.prompt)["messages"]}
                return AgentTurn(
                    rationale=rationale,
                    action=Wait(reason="Following watchdog note")
                    if "watchdog" in senders
                    else Read(refs=(self.stale,)),
                    usage=Usage(
                        input_tokens=10, cache_read_input_tokens=90, output_tokens=5
                    ),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supervisor = Supervisor()
            watchdog = Watchdog(supervisor, poll_s=3600, compact_at=0.2)
            with Project(root / "state", watchdog=watchdog) as project:
                (root / "plan.txt").write_text("superseded plan")
                stale = project.ingest(root / "plan.txt")
                project.store.invalidate(stale, actor="script", reason="Fixture")
                (root / "large.txt").write_text("measured data " * 2_000)
                large = project.ingest(root / "large.txt")
                project.reasoning = provider = Looping(stale)
                await project.run(
                    ProjectRequest(
                        description="Watchdog fixture",
                        context=ContextSpec(
                            selected=(large,),
                            max_input_tokens=100_000,
                            reserved_output_tokens=1_000,
                        ),
                    )
                )

                issues = {i["kind"]: i for i in supervisor.states[0]["issues"]}
                self.assertEqual(issues["loop"]["pattern"], "rejected")
                problem = issues["loop"]["reference_problems"][0]
                self.assertTrue(problem["problem"].startswith("stale"))
                self.assertIsNone(problem["current"])
                self.assertEqual(
                    issues["context"]["largest_optional_sources"][0]["ref"],
                    large.model_dump(mode="json"),
                )
                self.assertEqual(len(supervisor.states), 2)
                self.assertEqual(watchdog.provider.effort, "low")
                self.assertEqual(supervisor.effort, "max")
                self.assertEqual(len(provider.packets), 5)
                note = project.inbox(issues["loop"]["agent_id"])[-1].message
                self.assertEqual(note.sender, "watchdog")
                self.assertIn(note.id, provider.packets[-1].message_ids)
                reports = [e for e in project.events() if e.type == "watchdog.report"]
                self.assertEqual(len(reports), 1)
                self.assertIn("chief [waiting]", reports[0].details["text"])
                self.assertIn("chief (loop)", reports[0].details["text"])
                # Token audit: provider usage of all five turns, the prompts of
                # the four rejected reads, and where prompt characters went.
                tokens = reports[0].details["tokens"]
                self.assertEqual(
                    tokens["usage"],
                    Usage(
                        input_tokens=50, cache_read_input_tokens=450, output_tokens=25
                    ).model_dump(mode="json"),
                )
                sent = [p.input_tokens for p in provider.packets]
                self.assertEqual(tokens["input_tokens_sent"], sum(sent))
                self.assertEqual(
                    tokens["input_tokens_on_rejected_turns"], sum(sent[:4])
                )
                self.assertAlmostEqual(sum(tokens["component_share"].values()), 1, 2)
                self.assertIn("sources.selected", tokens["component_share"])
                self.assertGreater(tokens["watchdog"]["input_tokens_sent"], 0)
                self.assertIn(
                    "(450 cache reads, 0 cache writes, 90% from cache)",
                    reports[0].details["text"],
                )
                self.assertIn("Prompt share: ", reports[0].details["text"])
                self.assertEqual(
                    project.requests(agent="watchdog")[0].status, "completed"
                )
