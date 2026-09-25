import asyncio
import json
import math
import sys
import tempfile
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from mcp import Client, StdioServerParameters
from pydantic import BaseModel, ValidationError

from guacamole import ProducedFile, Project, ToolRegistry
from guacamole.contracts import FileRecord
from guacamole.tools.mcp import ToolSession, create_mcp
from guacamole.websocket import WebSocketBridge


@dataclass(frozen=True)
class Point:
    x: float


class Nested(BaseModel):
    point: Point


def distance(point: Point) -> float:
    return abs(point.x)


def nested(value: Nested) -> Nested:
    return value


def broken(value: float) -> float:
    return "wrong output"


def nonfinite() -> float:
    return math.inf


def untyped(value: dict[str, Any]) -> int:
    return 1


class ToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_sandbox_outputs_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, sandbox = root / "state", root / "deliverables"
            source = root / "previous.txt"
            source.write_text("Original supplied design")

            def write(filename: str) -> ProducedFile:
                path = project.output_path(Path(filename))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("TEST FIXTURE: generated software")
                return ProducedFile.from_path(path)

            def return_file(path: str) -> ProducedFile:
                return ProducedFile.from_path(Path(path))

            tools = ToolRegistry()
            generate = tools.register(write)
            supplied = tools.register(return_file)
            with Project(workspace, sandbox=sandbox, tools=tools) as project:
                self.assertEqual(project.sandbox, sandbox)
                job = project.submit(generate, {"filename": "software/main.py"})
                output = await job.collect()
                self.assertEqual(Path(output.path), sandbox / "software/main.py")
                saved = project.store.model(
                    "job_file", f"{job.id}:{output.sha256}", FileRecord
                )
                snapshot = project.verify_file(saved)
                self.assertTrue(snapshot.is_relative_to(sandbox / "artifacts"))
                self.assertFalse((workspace / "artifacts").exists())
                source_ref = project.ingest(source)
                imported = project.store.model("source", source_ref.id, FileRecord)
                self.assertEqual(
                    project.verify_file(imported).read_text(), source.read_text()
                )
                # Intake may read outside the sandbox; generated outputs may not escape it.
                (sandbox / "link").symlink_to(root, target_is_directory=True)
                for filename in (str(source), "../escape.txt", "link/escape.txt"):
                    with (
                        self.subTest(filename=filename),
                        self.assertRaisesRegex(ValueError, "sandbox"),
                    ):
                        await project.call(generate, {"filename": filename})
                self.assertFalse((root / "escape.txt").exists())
                for path in (source, sandbox / "link/previous.txt"):
                    with self.assertRaisesRegex(ValueError, "sandbox"):
                        await project.call(supplied, {"path": str(path)})
                event_count = len(project.events())

            with Project(workspace, read_only=True) as history:
                self.assertEqual(history.sandbox, sandbox)
                self.assertEqual(history.verify_file(saved), snapshot)
                self.assertEqual(len(history.events()), event_count)
            other = root / "different"
            with self.assertRaisesRegex(ValueError, "already uses sandbox"):
                Project(workspace, sandbox=other)
            self.assertFalse(other.exists())
            with Project(workspace) as reopened:
                self.assertEqual(reopened.sandbox, sandbox)
                self.assertEqual(
                    reopened.verify_file(saved).read_text(),
                    "TEST FIXTURE: generated software",
                )

            # Historical projects without the setting retain workspace-relative snapshots.
            legacy = root / "legacy"
            with Project(legacy) as project:
                legacy_ref = project.ingest(source)
                legacy_file = project.store.model("source", legacy_ref.id, FileRecord)
                project.store.db.execute("DELETE FROM metadata WHERE key='sandbox'")
            with self.assertRaisesRegex(ValueError, "Existing project"):
                Project(legacy, sandbox=other)
            with Project(legacy, read_only=True) as history:
                self.assertEqual(history.sandbox, legacy)
                self.assertEqual(
                    history.verify_file(legacy_file).read_text(), source.read_text()
                )
                self.assertIsNone(
                    history.store.db.execute(
                        "SELECT value FROM metadata WHERE key='sandbox'"
                    ).fetchone()
                )

    async def test_failed_retry_read_only_inspection_and_alias_validation(self):
        type Unsafe = dict[str, Any]

        def bad_alias(value: Unsafe) -> int:
            return 1

        attempts = 0

        async def flaky() -> int:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("fixture failure")
            return 8

        tools = ToolRegistry()
        with self.assertRaises(TypeError):
            tools.register(bad_alias)
        tool = tools.register(flaky, retry_safe=True)
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=tools) as project,
        ):
            job = project.submit(tool, {})
            with self.assertRaises(RuntimeError):
                await job.collect()
            retry = project.retry_job(
                job.id, reason="Retry the deliberately failed fixture"
            )
            self.assertEqual(await retry.collect(), 8)
            self.assertEqual(job.id, retry.id)
            self.assertEqual(len(retry.record.attempts), 2)
            count = len(project.events())
            with Project(Path(directory), read_only=True) as view:
                self.assertEqual(view.requests()[0].status, "completed")
                trace = view.trace(job.id)
                self.assertGreater(len(trace["records"]), 3)
            self.assertEqual(len(project.events()), count)
            self.assertEqual(attempts, 2)

    async def test_contracts_and_atomic_dispatch(self):
        registry = ToolRegistry()
        with self.assertRaises(TypeError):
            registry.register(untyped)
        tool = registry.register(distance)
        wrapped = registry.register(nested)
        bad = registry.register(broken)
        infinity = registry.register(nonfinite)
        with self.assertRaises(ValueError):
            registry.register(distance)
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=registry) as project,
        ):
            self.assertEqual(await project.call(tool, {"point": {"x": -2.0}}), 2.0)
            for payload in (
                {"point": {"x": "2"}},
                {"point": {"x": 2.0, "extra": 1}},
                {"point": {"x": float("nan")}},
            ):
                with self.assertRaises((ValidationError, ValueError)):
                    await project.call(tool, payload)
            with self.assertRaises(ValidationError):
                await project.call(
                    wrapped, {"value": {"point": {"x": 1.0}, "extra": 1}}
                )
            for candidate, arguments in ((bad, {"value": 1.0}), (infinity, {})):
                with self.assertRaises((ValidationError, ValueError)):
                    await project.call(candidate, arguments)
            self.assertEqual(
                [r.status for r in project.requests()],
                ["completed", "failed", "failed"],
            )
            with (
                patch.object(project.store, "event", side_effect=OSError("disk full")),
                self.assertRaises(OSError),
            ):
                project.submit(tool, {"point": {"x": 4.0}})
            self.assertEqual(len(project.requests()), 3)

    async def test_mcp_matches_python_and_grants(self):
        tools = ToolRegistry()
        tool = tools.register(distance)
        tools.register(nested)
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=tools) as project,
        ):
            session = ToolSession(project, grants=(tool.definition.grant,))
            async with Client(create_mcp(session)) as client:
                listing = await client.list_tools()
                self.assertEqual([t.name for t in listing.tools], [tool.key])
                result = await client.call_tool(tool.key, {"point": {"x": -2.0}})
                self.assertEqual(result.structured_content, {"result": 2.0})
                wrong = await client.call_tool(tool.key, {"point": {"x": "2"}})
                self.assertTrue(wrong.is_error)
                denied = await client.call_tool(
                    "nested@1", {"value": {"point": {"x": 2.0}}}
                )
                self.assertTrue(denied.is_error)
            self.assertEqual(len(project.requests()), 1)

    async def test_real_stdio_client(self):
        server = """
import asyncio
import sys
from pathlib import Path
from guacamole import Project, ToolRegistry
from guacamole.tools.mcp import ToolSession, serve_stdio
from test_tools import distance, nested

tools = ToolRegistry()
tools.register(distance)
tools.register(nested)
with Project(Path(sys.argv[1]), sandbox=Path(sys.argv[2]), tools=tools) as project:
    asyncio.run(serve_stdio(ToolSession(project)))
"""
        with tempfile.TemporaryDirectory() as directory:
            async with Client(
                StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-B",
                        "-c",
                        server,
                        str(Path(directory) / "state"),
                        str(Path(directory) / "outputs"),
                    ],
                    cwd=Path(__file__).resolve().parent,
                )
            ) as client:
                listing = await client.list_tools()
                self.assertEqual(len(listing.tools), 2)
                result = await client.call_tool(
                    "distance@1",
                    {"point": {"x": -2.0}},
                )
                self.assertEqual(result.structured_content, {"result": 2.0})

    async def test_cancellation_does_not_claim_thread_termination(self):
        gate = threading.Event()

        def slow() -> int:
            gate.wait(3)
            return 7

        registry = ToolRegistry()
        tool = registry.register(slow)
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=registry) as project,
        ):
            job = project.submit(tool, {})
            with self.assertRaises(TimeoutError):
                await job.collect(0.01)
            job.cancel()
            self.assertEqual(job.record.status, "cancel_requested")
            gate.set()
            self.assertEqual(await job.collect(), 7)
            self.assertEqual(job.record.status, "completed")

    async def test_websocket_auth_dedupe_and_event_cursor(self):
        from websockets.asyncio.client import connect

        registry = ToolRegistry()
        tool = registry.register(distance)
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), tools=registry) as project,
        ):
            bridge = WebSocketBridge(ToolSession(project))
            async with bridge.serve() as server:
                port = server.sockets[0].getsockname()[1]
                uri = f"ws://127.0.0.1:{port}"
                command = json.dumps(
                    {
                        "id": "one",
                        "command": {
                            "kind": "call",
                            "tool": tool.key,
                            "arguments": {"point": {"x": 4.0}},
                        },
                    }
                )
                async with connect(
                    uri,
                    additional_headers={"Authorization": f"Bearer {bridge.token}"},
                ) as client:
                    await client.send(command)
                    first = json.loads(await client.recv())
                    await client.send(command)
                    self.assertEqual(json.loads(await client.recv()), first)
                await project.drain()
                self.assertEqual(len(project.requests()), 1)
                cursor = project.events()[-2].sequence
                async with connect(
                    uri,
                    additional_headers={"Authorization": f"Bearer {bridge.token}"},
                ) as client:
                    await client.send(
                        json.dumps(
                            {
                                "id": "feed",
                                "command": {"kind": "subscribe", "after": cursor},
                            }
                        )
                    )
                    event = json.loads(await asyncio.wait_for(client.recv(), 2))[
                        "event"
                    ]
                    self.assertGreater(event["sequence"], cursor)
                async with connect(uri) as client:
                    await client.wait_closed()
                    self.assertEqual(client.close_code, 1008)


if __name__ == "__main__":
    unittest.main()
