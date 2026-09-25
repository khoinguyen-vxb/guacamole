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

from guacamole import Project, ToolRegistry
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
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            async with Client(
                StdioServerParameters(
                    command=sys.executable,
                    args=[
                        str(root / "examples/cross_domain.py"),
                        "--mcp",
                        "--workspace",
                        directory,
                    ],
                    cwd=root,
                )
            ) as client:
                listing = await client.list_tools()
                self.assertEqual(len(listing.tools), 2)
                result = await client.call_tool(
                    "cantilever@1",
                    {
                        "force_n": 10.0,
                        "length_m": 2.0,
                        "youngs_pa": 200e9,
                        "inertia_m4": 1e-6,
                    },
                )
                self.assertAlmostEqual(
                    result.structured_content["result"]["tip_m"], 10 * 8 / 600000
                )

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
