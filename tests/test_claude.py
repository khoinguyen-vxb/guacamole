"""Exercise the Claude CLI protocol with a real local fixture process, without model calls."""

import base64
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guacamole import Ref, Usage
from guacamole.context import CONTINUED, ProviderError
from guacamole.contracts import ContextPacket, ImageAttachment, Wait
from guacamole.providers.claude import ClaudeReasoning


class ClaudeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.capture = self.root / "capture.json"
        self.executable = self.root / "fake claude"
        self.executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            f"capture = Path({str(self.capture)!r})\n"
            "attempt = json.loads(capture.read_text())['attempt'] + 1 if capture.exists() else 1\n"
            "system = Path(sys.argv[sys.argv.index('--system-prompt-file') + 1]).read_text()\n"
            "content = json.loads(sys.stdin.read())['message']['content']\n"
            "stdin = ''.join(b['text'] for b in content if b['type'] == 'text')\n"
            "capture.write_text(json.dumps({\n"
            "    'argv': sys.argv[1:], 'system': system, 'stdin': stdin,\n"
            "    'attempt': attempt, 'environment': list(os.environ),\n"
            "    'blocks': [b['type'] for b in content],\n"
            "    'images': [b['source'] for b in content if b['type'] == 'image'],\n"
            "}))\n"
            "if '\"stderr_limit\"' in stdin:\n"
            '    sys.stderr.write("You\'ve hit your limit · resets 3pm fixture-secret\\n")\n'
            "    sys.exit(1)\n"
            "if '\"limit\"' in stdin:\n"
            "    print(json.dumps({'type': 'result', 'is_error': True,\n"
            "                      'result': 'Claude AI usage limit reached|1 fixture-secret'}))\n"
            "    sys.exit(1)\n"
            "turn = {\n"
            "    'rationale': {'objective': 'fixture', 'explanation': 'No engineering claim'},\n"
            "    'action': {'kind': 'wait', 'reason': 'fixture'},\n"
            "}\n"
            "invalid = '\"invalid_once\"' in stdin and attempt == 1\n"
            "usage = {'input_tokens': 100, 'cache_read_input_tokens': 900,\n"
            "         'cache_creation_input_tokens': 0, 'output_tokens': 40}\n"
            "wrapped = '\"prose_wrapped\"' in stdin\n"
            "result = json.dumps(turn)\n"
            "if wrapped:  # A sentence, a brace in prose, then the fenced object\n"
            "    result = 'Next {step}:\\n```json\\n' + result + '\\n```\\nDone.'\n"
            "print(json.dumps({'type': 'system', 'subtype': 'init'}))\n"
            "print(json.dumps({\n"
            "    'type': 'result', 'is_error': False, 'total_cost_usd': 0.25, 'usage': usage,\n"
            "    'result': 'fixture-invalid' if invalid else result,\n"
            "}))\n"
        )
        self.executable.chmod(0o755)
        self.provider = ClaudeReasoning(
            executable=str(self.executable), web_search=False
        )

    async def test_stable_prefix_rides_in_system_prompt_and_usage_is_reported(self):
        prompt = '{"instructions":"stable","state":{"mode":"ok"}}'
        stable = prompt.index('"state"')
        packet = ContextPacket(
            agent_id="fixture",
            invocation_id="fixture",
            request_id="fixture",
            provider=self.provider.name,
            model=self.provider.model,
            prompt=prompt,
            input_tokens=len(prompt),
            token_count_method="utf8_upper_bound",
            reserved_output_tokens=1000,
            cache_breakpoints=(stable,),
        )
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret"}):
            result = await self.provider.respond(packet)
        self.assertEqual(result.action, Wait(reason="fixture"))
        capture = json.loads(self.capture.read_text())
        self.assertIn("reasoning provider for Guacamole", capture["system"])
        self.assertTrue(capture["system"].endswith(CONTINUED + prompt[:stable]))
        self.assertEqual(capture["stdin"], prompt[stable:])
        self.assertEqual(capture["blocks"], ["text"])
        argv = " ".join(capture["argv"])
        self.assertIn("--input-format stream-json", argv)
        self.assertIn("--output-format stream-json --verbose", argv)
        self.assertNotIn("--system-prompt", capture["argv"])
        self.assertNotIn("ANTHROPIC_API_KEY", capture["environment"])
        self.assertEqual(
            result.usage,
            Usage(
                input_tokens=100,
                cache_read_input_tokens=900,
                cache_creation_input_tokens=0,
                output_tokens=40,
                cost_usd=0.25,
            ),
        )
        # An object wrapped in prose and a fence is read without a retry.
        self.capture.unlink()
        wrapped = packet.model_copy(
            update={"prompt": prompt.replace('"ok"', '"prose_wrapped"')}
        )
        result = await self.provider.respond(wrapped)
        self.assertEqual(json.loads(self.capture.read_text())["attempt"], 1)
        self.assertIsInstance(result.action, Wait)
        # A corrected retry resends only the rest, and both attempts count.
        self.capture.unlink()
        retry = packet.model_copy(
            update={"prompt": prompt.replace('"ok"', '"invalid_once"')}
        )
        with self.assertLogs("guacamole.providers.claude", level="WARNING"):
            result = await self.provider.respond(retry)
        capture = json.loads(self.capture.read_text())
        self.assertEqual(capture["attempt"], 2)
        self.assertTrue(
            capture["stdin"].startswith(
                retry.prompt[stable:] + "\n\nvalidation_feedback:\n"
            )
        )
        self.assertNotIn("fixture-invalid", capture["system"])
        self.assertEqual(result.usage.input_tokens, 200)
        self.assertEqual(result.usage.cost_usd, 0.5)
        # Images lead the text as base64 blocks, and a retry sends them again.
        self.capture.unlink()
        view = self.root / "view.jpg"
        view.write_bytes(b"fixture pixels")
        image = ImageAttachment(
            source=Ref(kind="source", id="view", revision=1, sha256="0" * 64),
            path=str(view),
            sha256=hashlib.sha256(b"fixture pixels").hexdigest(),
            media_type="image/jpeg",
        )
        with self.assertLogs("guacamole.providers.claude", level="WARNING"):
            await self.provider.respond(retry.model_copy(update={"images": (image,)}))
        capture = json.loads(self.capture.read_text())
        self.assertEqual(capture["attempt"], 2)
        self.assertEqual(capture["blocks"], ["image", "text"])
        self.assertEqual(
            capture["images"],
            [
                {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(b"fixture pixels").decode(),
                }
            ],
        )

    async def test_cli_failure_names_its_cause_without_its_text(self):
        packet = ContextPacket(
            agent_id="fixture",
            invocation_id="fixture",
            request_id="fixture",
            provider=self.provider.name,
            model=self.provider.model,
            prompt='{"mode":"limit"}',
            input_tokens=100,
            reserved_output_tokens=1000,
        )
        with self.assertRaises(ProviderError) as raised:
            await self.provider.respond(packet)
        self.assertIn("status 1 (usage limit)", str(raised.exception))
        self.assertNotIn("fixture-secret", str(raised.exception))
        # The subscription limit message can arrive on stderr, without a result.
        packet = packet.model_copy(update={"prompt": '{"mode":"stderr_limit"}'})
        with self.assertRaises(ProviderError) as raised:
            await self.provider.respond(packet)
        self.assertIn("status 1 (usage limit)", str(raised.exception))
        self.assertNotIn("fixture-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
