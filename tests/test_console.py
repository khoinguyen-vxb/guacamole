"""Host loop checks; model calls are scripted fixtures."""

import asyncio
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from runtime_support import TestReasoning

from guacamole import AgentTurn, AskHuman, Budget, ContextSpec, Project, ProjectRequest
from guacamole.console import host
from guacamole.contracts import Rationale, Wait


class HostTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_blocking_question_holds_the_run_until_a_human_answers(self):
        class Asking(TestReasoning):
            calls = 0

            async def respond(self, packet):
                self.calls += 1
                return AgentTurn(
                    rationale=Rationale(objective="fixture", explanation="Fixture"),
                    action=AskHuman(question="Which wall material?")
                    if self.calls == 1
                    else Wait(reason="Answered"),
                )

        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=Asking()) as project,
            redirect_stdout(io.StringIO()) as output,
        ):

            async def answer() -> None:
                while not (inbox := project.human.inbox()):
                    await asyncio.sleep(0.05)
                # The host must still be waiting, not finished with awaiting_human.
                await asyncio.sleep(1)
                self.assertFalse(running.done())
                project.human.reply(
                    inbox[0].message.request_id or "", "Brick", author="test"
                )

            running = asyncio.create_task(
                host(
                    project,
                    lambda context: ProjectRequest(
                        description="fixture", context=context
                    ),
                    port=0,
                    context=ContextSpec(max_input_tokens=200_000),
                    budget=Budget(),
                )
            )
            await asyncio.wait_for(answer(), 30)
            result = await asyncio.wait_for(running, 30)
            self.assertEqual(result.status, "incomplete")
            self.assertFalse(project.human.inbox())
            self.assertIn("Authorization: Bearer", output.getvalue())
            self.assertTrue((project.sandbox / "result.json").is_file())


if __name__ == "__main__":
    unittest.main()
