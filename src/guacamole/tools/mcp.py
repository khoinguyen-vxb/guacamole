"""Generated standard MCP over local stdio, using the shared executor."""

import base64
import sys
from contextlib import redirect_stdout
from typing import TYPE_CHECKING

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ..context import IMAGE_TYPES, MAX_IMAGE_BYTES
from ..contracts import JSON, AgentSpec, FileRecord, ToolGrant
from .execution import Job
from .registry import ToolDefinition, encode

if TYPE_CHECKING:
    from ..project import Project


class ToolSession:
    """Created by the host script; remote arguments can never choose an identity."""

    def __init__(
        self,
        project: "Project",
        *,
        grants: tuple[ToolGrant, ...] | None = None,
        agent_id: str | None = None,
        parent_id: str | None = None,
        packet_id: str | None = None,
        rationale_id: str | None = None,
    ) -> None:
        self.project, self.agent_id = project, agent_id
        self.parent_id, self.packet_id, self.rationale_id = (
            parent_id,
            packet_id,
            rationale_id,
        )
        if agent_id:
            agent = project.store.model("agent", agent_id, AgentSpec)
            if parent_id is None or packet_id is None or rationale_id is None:
                raise ValueError(
                    "Agent sessions require request, context, and rationale references"
                )
            if (
                project.activity.get(parent_id).target != agent_id
                or project.context(packet_id).agent_id != agent_id
            ):
                raise PermissionError(
                    "Session provenance does not belong to this agent"
                )
            self.grants = grants if grants is not None else agent.tools
            if not set(self.grants) <= set(agent.tools):
                raise PermissionError("Session grants exceed agent grants")
        else:
            self.grants = (
                grants
                if grants is not None
                else tuple(t.grant for t in project.tools.definitions())
            )
        project.tools.definitions(self.grants)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return self.project.tools.definitions(self.grants)

    def submit(self, key: str, arguments: JSON) -> Job:
        tool = self.project.tools.get(key)
        actor, decision_id, run_id = "script", None, "script"
        if self.agent_id:
            agent = self.project.store.model("agent", self.agent_id, AgentSpec)
            if tool.definition.grant not in agent.tools:
                raise PermissionError("Agent grant is no longer active")
            actor, decision_id = agent.id, agent.decision_id
            assert self.parent_id is not None
            run_id = self.project.activity.get(self.parent_id).run_id
        return self.project.executor.submit(
            tool,
            arguments,
            actor=actor,
            grants=self.grants,
            decision_id=decision_id,
            run_id=run_id,
            parent_id=self.parent_id,
            packet_id=self.packet_id,
            rationale_id=self.rationale_id,
        )


def create_mcp(session: ToolSession) -> Server:
    async def list_tools(context, params) -> types.ListToolsResult:
        tools = []
        for definition in session.definitions():
            schema = dict(definition.output_schema)
            definitions = schema.pop("$defs", {})
            output = {
                "type": "object",
                "properties": {"result": schema},
                "required": ["result"],
                "additionalProperties": False,
                "$defs": definitions,
            }
            tools.append(
                types.Tool(
                    name=definition.grant.key,
                    description=definition.description,
                    input_schema=definition.input_schema,
                    output_schema=output,
                )
            )
        return types.ListToolsResult(tools=tools)

    async def call_tool(
        context, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        try:
            job = session.submit(params.name, params.arguments or {})
            await job.collect()
            payload = {"result": job.record.result}
            return types.CallToolResult(
                content=[
                    types.TextContent(type="text", text=encode(payload)),
                    *_images(session.project, job.record.id),
                ],
                structured_content=payload,
            )
        except Exception as exc:  # noqa: BLE001 -- provider failures become protocol errors
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"{type(exc).__name__}: tool call rejected or failed; inspect the local request trace",
                    )
                ],
                is_error=True,
            )

    return Server(
        "guacamole", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool
    )


def _images(project: "Project", request_id: str) -> list[types.ImageContent]:
    """The images a tool run produced, verified, for clients that can see them."""
    images = []
    for snapshot in project.store.list("job_file"):
        file = FileRecord.model_validate_json(encode(snapshot.data))
        if file.producer_request != request_id or file.media_type not in IMAGE_TYPES:
            continue
        data = project.verify_file(file).read_bytes()
        if len(data) <= MAX_IMAGE_BYTES:
            images.append(
                types.ImageContent(
                    type="image",
                    data=base64.b64encode(data).decode("ascii"),
                    mime_type=file.media_type,
                )
            )
    return images


async def serve_stdio(session: ToolSession) -> None:
    server = create_mcp(session)
    async with stdio_server() as (reader, writer):
        with redirect_stdout(sys.stderr):
            await server.run(reader, writer, server.create_initialization_options())
