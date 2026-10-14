"""Image input from stored files to provider requests; model calls are opt-in."""

import base64
import hashlib
import os
import secrets
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import litellm
from mcp import Client
from runtime_support import TestReasoning

from guacamole import AgentSpec, ContextSpec, ProducedFile, Project, Ref, ToolRegistry
from guacamole import context as context_module
from guacamole.agents.runtime import Runtime
from guacamole.context import IMAGE_TOKENS, ContextOverflow, ProviderError, image_data
from guacamole.contracts import (
    AgentState,
    AgentTurn,
    ContextPacket,
    ImageAttachment,
    Rationale,
    Wait,
)
from guacamole.providers.claude import ClaudeReasoning
from guacamole.providers.codex import CodexReasoning
from guacamole.providers.litellm import LiteLLMReasoning
from guacamole.tools.mcp import ToolSession, create_mcp

# 3x5 digit glyphs for a label only the pixels hold.
DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


def png(rows: list[list[int]]) -> bytes:
    """A greyscale PNG from rows of 0-255 pixel values."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", len(rows[0]), len(rows), 8, 0, 0, 0, 0)
    pixels = b"".join(b"\0" + bytes(row) for row in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


def label(text: str, scale: int = 16) -> bytes:
    """Black digits on white, two glyph cells of margin."""
    cells = ["00" + "0".join(DIGITS[d][r] for d in text) + "00" for r in range(5)]
    blank = "0" * len(cells[0])
    cells = [blank, blank, *cells, blank, blank]
    return png(
        [
            [0 if cell == "1" else 255 for cell in row for _ in range(scale)]
            for row in cells
            for _ in range(scale)
        ]
    )


class Seeing(TestReasoning):
    image_tokens = 500


class Huge(TestReasoning):
    image_tokens = 10**6


def worker(*selected, pinned=(), max_input_tokens=100_000):
    return AgentSpec(
        id="worker",
        task_id="task",
        parent_id="chief",
        objective="Inspect the drawing",
        context=ContextSpec(
            selected=selected, pinned=pinned, max_input_tokens=max_input_tokens
        ),
        decision_id=None,
    )


class ImageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def image(self, name: str) -> Path:
        path = self.root / name
        path.write_bytes(label("42", scale=2))
        return path

    async def test_read_image_is_attached_counted_and_rechecked_when_sent(self):
        with Project(self.root / "state") as project:
            path = self.image("drawing.png")
            ref = project.ingest(path)

            async def build(agent, provider):
                return await project.contexts.build(
                    agent, "request", provider, instructions="test", state={}
                )

            packet = await build(worker(ref), Seeing())
            (image,) = packet.images
            self.assertEqual((image.source, image.media_type), (ref, "image/png"))
            self.assertEqual(image_data(image), path.read_bytes())
            self.assertIn('"image":"attached"', packet.prompt)
            self.assertEqual(packet.input_tokens, len(packet.prompt.encode()) + 500)
            self.assertEqual(project.context(packet.id).images, packet.images)
            # A text-only provider sees the record and why its pixels are missing.
            packet = await build(worker(ref), TestReasoning())
            self.assertEqual(packet.images, ())
            self.assertIn("accepts no images", packet.deferred[0].reason)
            self.assertIn('"image":"not attached: ', packet.prompt)
            # Too large for the budget: deferred when optional, an error when pinned.
            packet = await build(worker(ref), Huge())
            self.assertEqual((packet.images, packet.sources), ((), ()))
            self.assertIn("exceeds remaining input budget", packet.deferred[0].reason)
            with self.assertRaises(ContextOverflow):
                await build(worker(pinned=(ref,)), Huge())
            # Changed storage is refused when sent and left unattached afterwards.
            Path(image.path).write_bytes(b"tampered")
            with self.assertRaisesRegex(ProviderError, "missing or changed"):
                image_data(image)
            packet = await build(worker(ref), Seeing())
            self.assertEqual(packet.images, ())
            self.assertIn("missing or changed", packet.deferred[0].reason)

    async def test_image_count_and_size_limits(self):
        with Project(self.root / "state") as project:
            older, newer = (
                project.ingest(self.image(name)) for name in ("older.png", "newer.jpg")
            )
            with patch.object(context_module, "MAX_IMAGES", 1):
                packet = await project.contexts.build(
                    worker(newer, older), "r", Seeing(), instructions="t", state={}
                )
            self.assertEqual([i.source for i in packet.images], [newer])
            self.assertEqual(packet.images[0].media_type, "image/jpeg")
            self.assertIn("per turn", packet.deferred[0].reason)
            with patch.object(context_module, "MAX_IMAGE_BYTES", 10):
                packet = await project.contexts.build(
                    worker(newer), "r", Seeing(), instructions="t", state={}
                )
            self.assertEqual(packet.images, ())
            self.assertIn("exceeds 10 bytes", packet.deferred[0].reason)

    async def test_produced_images_are_listed_attached_and_returned_over_mcp(self):
        def render(name: str) -> tuple[ProducedFile, ProducedFile]:
            view = project.output_path(Path(f"{name}.png"))
            view.write_bytes(label("7", scale=2))
            log = project.output_path(Path(f"{name}.log"))
            log.write_text("rendered")
            return ProducedFile.from_path(view), ProducedFile.from_path(log)

        tools = ToolRegistry()
        tool = tools.register(render)
        with Project(self.root / "state", tools=tools) as project:
            async with Client(create_mcp(ToolSession(project))) as client:
                result = await client.call_tool(tool.key, {"name": "view"})
            (image,) = [c for c in result.content if c.type == "image"]
            view = (project.sandbox / "view.png").read_bytes()
            self.assertEqual(base64.b64decode(image.data), view)
            self.assertEqual(image.mime_type, "image/png")
            # The produced image, not the log, is listed so an agent can read it.
            runtime = Runtime(project, TestReasoning())
            runtime.run_id = "fixture-run"
            chief = worker().model_copy(update={"id": "chief", "parent_id": None})
            runtime.chief_id = chief.id
            state = runtime._context_state(chief, AgentState(request_id="chief"))
            (listed,) = [r for r in state["records"] if r["kind"] == "job_file"]
            sha256 = hashlib.sha256(view).hexdigest()
            self.assertTrue(listed["id"].endswith(sha256))
            packet = await project.contexts.build(
                worker(Ref.model_validate(listed)),
                "r",
                Seeing(),
                instructions="t",
                state={},
            )
            self.assertEqual(packet.images[0].sha256, sha256)

    async def test_litellm_appends_images_after_cached_text_for_vision_models(self):
        self.assertIsNone(LiteLLMReasoning("openai/gpt-3.5-turbo").image_tokens)
        turn = AgentTurn(
            rationale=Rationale(objective="fixture", explanation="No claim"),
            action=Wait(reason="fixture"),
        )
        path = self.image("view.png")
        image = ImageAttachment(
            source=Ref(kind="source", id="view", revision=1, sha256="0" * 64),
            path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            media_type="image/png",
        )
        block = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,"
                + base64.b64encode(path.read_bytes()).decode()
            },
        }
        prompt = '{"instructions":"stable","agent":{},"state":{"turn":1}}'
        breakpoints = (prompt.index('"agent"'), prompt.index('"state"'))
        for model, text_blocks in (
            ("anthropic/claude-opus-5-5", 3),  # One per cache-marked prefix
            ("openai/gpt-6-astra", 1),
        ):
            provider = LiteLLMReasoning(model, mock_response=turn.model_dump_json())
            self.assertEqual(provider.image_tokens, IMAGE_TOKENS)
            packet = ContextPacket(
                agent_id="fixture",
                invocation_id="one",
                request_id="request",
                provider=provider.name,
                model=provider.model,
                prompt=prompt,
                input_tokens=1_000,
                reserved_output_tokens=1_000,
                cache_breakpoints=breakpoints,
                images=(image,),
            )
            with (
                self.subTest(model=model),
                patch.object(
                    litellm, "acompletion", wraps=litellm.acompletion
                ) as completion,
            ):
                await provider.respond(packet)
                content = completion.call_args.kwargs["messages"][-1]["content"]
                self.assertEqual(len(content), text_blocks + 1)
                self.assertEqual("".join(b["text"] for b in content[:-1]), prompt)
                self.assertEqual(content[-1], block)

    @unittest.skipUnless(
        os.environ.get("GUACAMOLE_LIVE_VISION") in {"codex", "claude"},
        "set GUACAMOLE_LIVE_VISION=codex or claude; makes one model call",
    )
    async def test_live_provider_reads_a_label_only_the_pixels_hold(self):
        provider = (
            CodexReasoning(web_search=False, effort="low")
            if os.environ["GUACAMOLE_LIVE_VISION"] == "codex"
            else ClaudeReasoning(web_search=False, effort="low")
        )
        text = "".join(secrets.choice("123456789") for _ in range(6))
        with Project(self.root / "state") as project:
            path = self.root / "label.png"
            path.write_bytes(label(text))
            ref = project.ingest(path)
            packet = await project.contexts.build(
                worker(ref),
                "request",
                provider,
                instructions="Return a finish action whose result is the string of "
                "digits shown in the attached image.",
                state={},
            )
            self.assertEqual(len(packet.images), 1)
            self.assertNotIn(text, packet.prompt)
            turn = await provider.respond(packet)
        self.assertIn(text, turn.action.model_dump_json())


if __name__ == "__main__":
    unittest.main()
