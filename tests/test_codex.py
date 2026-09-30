"""Exercise the CLI protocol with a real local fixture process, without model calls."""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guacamole import ContextSpec, Project, ProjectRequest
from guacamole.context import ProviderError
from guacamole.contracts import ContextPacket, Wait
from guacamole.providers.codex import CodexReasoning


class CodexTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.capture = self.root / "capture.json"
        self.executable = self.root / "fake codex"
        self.executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys, time\n"
            "from pathlib import Path\n"
            "prompt = sys.stdin.read()\n"
            f"capture = Path({str(self.capture)!r})\n"
            "attempt = json.loads(capture.read_text())['attempt'] + 1 if capture.exists() else 1\n"
            "config = next(x for x in sys.argv if x.startswith('model_instructions_file='))\n"
            "instructions = Path(json.loads(config.split('=', 1)[1])).read_text()\n"
            "temporary = capture.with_suffix('.tmp')\n"
            "temporary.write_text(json.dumps({\n"
            "    'prompt': prompt, 'argv': sys.argv[1:], 'cwd': os.getcwd(),\n"
            "    'pid': os.getpid(), 'environment': list(os.environ),\n"
            "    'attempt': attempt, 'instructions': instructions,\n"
            "}))\n"
            "temporary.replace(capture)\n"
            "packet, end = json.JSONDecoder().raw_decode(prompt)\n"
            "mode = packet.get('mode', 'ok')\n"
            "feedback = json.loads(prompt[end:].split('validation_feedback:\\n', 1)[1]) if prompt[end:].strip() else None\n"
            "if mode == 'sleep': time.sleep(30)\n"
            "if mode == 'invalid_then_sleep': time.sleep(0.75 if attempt == 1 else 30)\n"
            "if mode == 'fail':\n"
            "    print('fixture-secret', file=sys.stderr)\n"
            "    sys.exit(7)\n"
            "if mode == 'missing' or mode == 'invalid_then_missing' and attempt > 1: sys.exit(0)\n"
            "output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])\n"
            "payload = {\n"
            "    'rationale': {'objective': 'fixture', 'explanation': 'No engineering claim'},\n"
            "    'action': {'kind': 'wait', 'reason': 'fixture'},\n"
            "    'provider_request_id': 'invented', 'provider_summary': 'invented',\n"
            "}\n"
            "if mode == 'schema_invalid_once' and attempt == 1: payload['action']['kind'] = 'fixture-secret'\n"
            "if mode == 'fields_invalid_once':\n"
            "    corrected = feedback and json.loads(feedback['previous_response'])['action'].get('fixture-secret') == 'fixture'\n"
            "    expected = {('missing', ('action', 'wait', 'reason')), ('extra_forbidden', ('action', 'wait', 'fixture-secret'))}\n"
            "    corrected = corrected and {(e['type'], tuple(e['loc'])) for e in feedback['errors']} == expected\n"
            "    if not corrected: payload['action']['fixture-secret'] = payload['action'].pop('reason')\n"
            "invalid = mode == 'invalid' or mode in {'invalid_once', 'invalid_then_sleep', 'invalid_then_missing'} and attempt == 1\n"
            "output.write_text('fixture-secret' if invalid else json.dumps(payload))\n"
        )
        self.executable.chmod(0o755)
        self.provider = CodexReasoning(executable=str(self.executable))
        self.packet = ContextPacket(
            agent_id="fixture",
            invocation_id="fixture",
            request_id="fixture",
            provider=self.provider.name,
            model=self.provider.model,
            prompt='{"mode":"ok","text":"π"}',
            input_tokens=100,
            token_count_method="utf8_upper_bound",
            reserved_output_tokens=1000,
        )

    async def test_cli_receives_packet_without_api_credentials_and_records_bound(self):
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret"}
        ):
            result = await self.provider.respond(self.packet)
        self.assertEqual(result.action, Wait(reason="fixture"))
        self.assertIsNone(result.provider_request_id)
        self.assertIsNone(result.provider_summary)
        capture = json.loads(self.capture.read_text())
        self.assertEqual(capture["prompt"], self.packet.prompt)
        self.assertNotIn("OPENAI_API_KEY", capture["environment"])
        self.assertNotIn("CODEX_API_KEY", capture["environment"])
        argv = capture["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], self.provider.model)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertIn('forced_login_method="chatgpt"', argv)
        self.assertIn("--ignore-user-config", argv)
        self.assertIn("--ephemeral", argv)
        self.assertIn('web_search="disabled"', argv)
        self.assertIn("Do not execute tools yourself.", capture["instructions"])
        self.assertFalse(Path(capture["cwd"]).exists())
        self.assertEqual(await self.provider.count_tokens("π"), 2)
        with Project(self.root / "state", reasoning=self.provider) as project:
            await project.run(
                ProjectRequest(
                    description="fixture", context=ContextSpec(max_input_tokens=128_000)
                )
            )
            packet = project.store.list("context")[0].data
            self.assertEqual(packet["provider"], "codex-cli")
            self.assertEqual(packet["token_count_method"], "utf8_upper_bound")
            self.assertEqual(packet["input_tokens"], len(packet["prompt"].encode()))

    async def test_live_web_search_keeps_engineering_tools_in_runtime(self):
        provider = CodexReasoning(executable=str(self.executable), web_search=True)
        result = await provider.respond(self.packet)
        self.assertEqual(result.action, Wait(reason="fixture"))
        capture = json.loads(self.capture.read_text())
        self.assertIn('web_search="live"', capture["argv"])
        self.assertNotIn('web_search="disabled"', capture["argv"])
        disabled = [
            capture["argv"][i + 1]
            for i, value in enumerate(capture["argv"])
            if value == "--disable"
        ]
        self.assertEqual(disabled, ["shell_tool", "apps", "plugins", "multi_agent"])
        self.assertIn("You may use built-in web search", capture["instructions"])
        self.assertIn("source URLs, access dates", capture["instructions"])
        self.assertIn(
            "Do not execute Guacamole engineering tools yourself.",
            capture["instructions"],
        )

    async def test_cli_failure_and_invalid_output_never_return_an_action(self):
        for mode, message, attempts in (
            ("fail", "status 7", 1),
            ("missing", "output_unavailable", 1),
            ("invalid", "json_line=1, json_column=1", 2),
            ("invalid_then_missing", "output_unavailable", 2),
        ):
            self.capture.unlink(missing_ok=True)
            with self.subTest(mode=mode), self.assertRaises(ProviderError) as raised:
                await self.provider.respond(
                    self.packet.model_copy(
                        update={"prompt": json.dumps({"mode": mode})}
                    )
                )
            self.assertIn(message, str(raised.exception))
            self.assertNotIn("fixture-secret", str(raised.exception))
            self.assertEqual(json.loads(self.capture.read_text())["attempt"], attempts)
        missing = CodexReasoning(executable=str(self.root / "absent"))
        with self.assertRaisesRegex(ProviderError, "install codex"):
            await missing.respond(self.packet)

    async def test_invalid_output_retries_once_and_validates_replacement(self):
        for mode in ("invalid_once", "schema_invalid_once", "fields_invalid_once"):
            self.capture.unlink(missing_ok=True)
            packet = self.packet.model_copy(
                update={"prompt": json.dumps({"mode": mode})}
            )
            with (
                self.subTest(mode=mode),
                self.assertLogs("guacamole.providers.codex", level="WARNING") as logs,
            ):
                result = await self.provider.respond(packet)
            self.assertEqual(result.action, Wait(reason="fixture"))
            capture = json.loads(self.capture.read_text())
            self.assertEqual(capture["attempt"], 2)
            original, feedback = capture["prompt"].split("\n\nvalidation_feedback:\n")
            self.assertEqual(original, packet.prompt)
            feedback = json.loads(feedback)
            self.assertIn("fixture-secret", feedback["previous_response"])
            self.assertTrue(feedback["errors"])
            self.assertIn("correct the listed errors", capture["instructions"])
            self.assertNotIn("fixture-secret", capture["instructions"])
            self.assertNotIn("fixture-secret", "\n".join(logs.output))
        self.capture.unlink()
        with (
            patch.object(
                self.provider,
                "context_capacity_tokens",
                self.packet.input_tokens + self.packet.reserved_output_tokens,
            ),
            self.assertRaisesRegex(ProviderError, "correction feedback exceeds"),
        ):
            await self.provider.respond(packet)
        self.assertEqual(json.loads(self.capture.read_text())["attempt"], 1)

    async def test_timeout_and_cancellation_stop_the_process(self):
        for mode in ("sleep", "invalid_then_sleep"):
            packet = self.packet.model_copy(
                update={"prompt": json.dumps({"mode": mode})}
            )
            for cancel in (False, True):
                self.capture.unlink(missing_ok=True)
                provider = CodexReasoning(executable=str(self.executable), timeout_s=1)
                started = asyncio.get_running_loop().time()
                task = asyncio.create_task(provider.respond(packet))
                async with asyncio.timeout(5):
                    while not self.capture.exists() or json.loads(
                        self.capture.read_text()
                    )["attempt"] < (2 if mode == "invalid_then_sleep" else 1):
                        await asyncio.sleep(0.01)
                    pid = json.loads(self.capture.read_text())["pid"]
                    if cancel:
                        task.cancel()
                    with self.assertRaises(
                        asyncio.CancelledError if cancel else ProviderError
                    ):
                        await task
                self.assertLess(asyncio.get_running_loop().time() - started, 1.5)
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
