"""Optional authenticated loopback control and persisted event cursors."""

import asyncio
import hmac
import ipaddress
import secrets
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from pydantic import Field

from .contracts import JSON, Model, uid
from .tools.mcp import ToolSession
from .tools.registry import encode


class Call(Model):
    kind: Literal["call"]
    tool: str
    arguments: JSON


class JobCommand(Model):
    kind: Literal["status", "cancel"]
    job_id: str


class Events(Model):
    kind: Literal["events", "subscribe"]
    after: int = Field(default=0, ge=0)


class Inspect(Model):
    kind: Literal["tools", "inbox", "trace"]
    entity_id: str = ""


class Command(Model):
    id: str = Field(default_factory=uid)
    command: Annotated[
        Call | JobCommand | Events | Inspect, Field(discriminator="kind")
    ]


class WebSocketBridge:
    def __init__(self, session: ToolSession, *, token: str | None = None) -> None:
        self.session = session
        self.token = token or secrets.token_urlsafe(32)

    def execute(self, command: Command) -> JSON:
        project = self.session.project
        operation = command.command
        key = f"{self.session.agent_id or 'script'}:{command.id}"
        existing = project.store.maybe("control", key)
        if existing:
            if existing.data["command"] != command.model_dump(mode="json"):
                raise ValueError("Control command ID was reused with different content")
            result = existing.data["response"]
            if not isinstance(result, dict):
                raise ValueError("Invalid persisted control response")
            return result
        with project.store.atomic():
            result: JSON
            match operation:
                case Call():
                    job = self.session.submit(operation.tool, operation.arguments)
                    result = {"job_id": job.id}
                case JobCommand():
                    record = project.activity.get(operation.job_id)
                    if record.requester != (self.session.agent_id or "script"):
                        raise PermissionError("Job belongs to another principal")
                    if operation.kind == "cancel":
                        project.executor.jobs[operation.job_id].cancel()
                    result = {
                        "job": project.activity.get(operation.job_id).model_dump(
                            mode="json"
                        )
                    }
                case Events():
                    result = {
                        "events": [
                            e.model_dump(mode="json")
                            for e in project.events(operation.after)
                        ]
                    }
                case Inspect(kind="tools"):
                    result = {
                        "tools": [
                            d.model_dump(mode="json")
                            for d in self.session.definitions()
                        ]
                    }
                case Inspect(kind="inbox"):
                    if (
                        self.session.agent_id
                        and operation.entity_id != self.session.agent_id
                    ):
                        raise PermissionError("Agent may only inspect its own inbox")
                    result = {
                        "inbox": [
                            e.model_dump(mode="json")
                            for e in project.inbox(operation.entity_id)
                        ]
                    }
                case Inspect(kind="trace"):
                    if self.session.agent_id:
                        record = project.activity.get(operation.entity_id)
                        if self.session.agent_id not in (
                            record.requester,
                            record.target,
                        ):
                            raise PermissionError(
                                "Trace is outside this agent's requests"
                            )
                    result = project.trace(operation.entity_id)
                case _:
                    raise ValueError("Unknown command")
            # Only mutations need deduplication. Inspection never writes or acknowledges.
            if (
                isinstance(operation, Call)
                or isinstance(operation, JobCommand)
                and operation.kind == "cancel"
            ):
                project.store.put(
                    "control",
                    key,
                    {"command": command.model_dump(mode="json"), "response": result},
                    actor=self.session.agent_id or "script",
                    event="control.executed",
                )
        return result

    async def handle(self, socket) -> None:
        supplied = (
            socket.request.headers.get("Authorization", "") if socket.request else ""
        )
        if not hmac.compare_digest(supplied, f"Bearer {self.token}"):
            await socket.close(code=1008, reason="Authentication required")
            return
        async for raw in socket:
            try:
                command = Command.model_validate_json(raw)
                if (
                    isinstance(command.command, Events)
                    and command.command.kind == "subscribe"
                ):
                    cursor = command.command.after
                    while True:
                        for event in self.session.project.events(cursor):
                            await socket.send(
                                encode(
                                    {
                                        "id": command.id,
                                        "event": event.model_dump(mode="json"),
                                    }
                                )
                            )
                            cursor = event.sequence
                        try:
                            await asyncio.wait_for(socket.wait_closed(), timeout=0.1)
                            return
                        except TimeoutError:
                            pass
                else:
                    await socket.send(
                        encode({"id": command.id, "result": self.execute(command)})
                    )
            except (ValueError, KeyError, PermissionError) as exc:
                await socket.send(
                    encode(
                        {
                            "error": type(exc).__name__,
                            "detail": "Command rejected; no unvalidated action executed",
                        }
                    )
                )

    @asynccontextmanager
    async def serve(self, *, host: str = "127.0.0.1", port: int = 0):
        from websockets.asyncio.server import serve

        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("Guacamole WebSocket control must bind to loopback")
        # No browser origins; this is a script interface, and authentication is required.
        async with serve(
            self.handle, host, port, origins=[None], max_size=1_048_576
        ) as server:
            yield server
