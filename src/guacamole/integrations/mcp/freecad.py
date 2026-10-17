"""FreeCAD tools backed by a supplied freecad-mcp server, not bypassing it.

register_freecad_tools uses that server's own CAD execution tools; headless runs
need only FreeCADCmd, status and views need its GUI addon.
"""

import base64
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ImageContent, TextContent

from ...contracts import Model, ProducedFile
from ...tools.workspace import Seconds

if TYPE_CHECKING:
    from ...project import Project


class FreeCADExecution(Model):
    succeeded: bool
    reply: str
    files: tuple[ProducedFile, ...]
    missing_outputs: tuple[str, ...]
    log: ProducedFile
    views: tuple[ProducedFile, ...] = ()  # GUI screenshots


class FreeCADView(Model):
    view: ProducedFile | None
    reply: str  # FreeCAD's explanation when it returned no screenshot


async def call(
    server: Path, name: str, arguments: dict[str, object], timeout_s: float
) -> tuple[str, tuple[ImageContent, ...]]:
    """One tool call on the server checkout; returns its text and any screenshots."""
    candidate = server / ".venv/bin/python"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "USER", "LANG", "TMPDIR", "FREECAD_MCP_TOKEN"}
    }
    environment["PYTHONPATH"] = str(server / "src")
    parameters = StdioServerParameters(
        command=str(candidate if candidate.exists() else sys.executable),
        args=["-c", "from freecad_mcp.server import main; main()"],
        env=environment,
    )
    with Path(os.devnull).open("w") as errlog:  # noqa: ASYNC230 - /dev/null is local.
        async with (
            stdio_client(parameters, errlog=errlog) as (reader, writer),
            ClientSession(reader, writer, read_timeout_seconds=30.0) as session,
        ):
            await session.initialize()
            result = await session.call_tool(
                name, arguments, read_timeout_seconds=timeout_s
            )
    if not isinstance(result, CallToolResult):
        raise TypeError("FreeCAD MCP returned an unsupported response")
    reply = "\n".join(
        item.text for item in result.content if isinstance(item, TextContent)
    )
    if result.is_error:
        raise RuntimeError(reply)
    return reply, tuple(i for i in result.content if isinstance(i, ImageContent))


def register_freecad_tools(project: "Project", server: Path) -> None:
    """Register freecad_status, freecad_view and freecad_run on the server checkout."""

    def save_views(images: tuple[ImageContent, ...]) -> tuple[ProducedFile, ...]:
        """FreeCAD screenshots as sandbox files, which agents read to see them."""
        views = []
        for image in images:
            suffix = {"image/png": ".png", "image/jpeg": ".jpg"}.get(image.mime_type)
            if suffix is None:
                raise ValueError(f"Unexpected FreeCAD image type {image.mime_type}")
            path = project.output_path(Path("views") / f"freecad-{uuid4().hex}{suffix}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(image.data, validate=True))
            views.append(ProducedFile.from_path(path))
        return tuple(views)

    async def freecad_status() -> str:
        """Inspect the GUI addon through FreeCAD MCP. Headless CAD needs no GUI addon."""
        return (await call(server, "get_rpc_status", {}, 30.0))[0]

    async def freecad_view(
        view: Literal[
            "Isometric",
            "Dimetric",
            "Trimetric",
            "Front",
            "Back",
            "Top",
            "Bottom",
            "Left",
            "Right",
        ] = "Isometric",
        focus_object: str = "",
    ) -> FreeCADView:
        """Save a screenshot of the FreeCAD GUI's active view; needs the GUI addon.

        Read the screenshot's job_file record to see it. focus_object names the
        object to fit; blank fits everything. Pictures do not measure geometry.
        """
        arguments: dict[str, object] = {"view_name": view}
        if focus_object:
            arguments["focus_object"] = focus_object
        reply, images = await call(server, "get_view", arguments, 60.0)
        views = save_views(images[:1])
        return FreeCADView(view=views[0] if views else None, reply=reply)

    async def freecad_run(
        script: str,
        outputs: tuple[str, ...] = (),
        headless: bool = True,
        timeout_s: Seconds = 600.0,
    ) -> FreeCADExecution:
        """Run a saved sandbox Python script using the supplied FreeCAD MCP.

        Scripts run in the output directory; GUACAMOLE_SANDBOX gives its absolute
        path. Import FreeCAD/Part explicitly. Save FCStd/STEP and declare their
        sandbox-relative paths in outputs. Headless mode uses FreeCADCmd; GUI
        mode needs the running addon. Execution is not geometry verification.
        A failed run returns succeeded=false with the end of FreeCAD's output,
        including any traceback, in reply; partial outputs may remain on disk.
        GUI runs also return a screenshot in views; read its job_file to see it.
        """
        source = project.output_path(Path(script))
        output_paths = tuple(project.output_path(Path(p)) for p in outputs)
        code = (
            "import os\n"
            f"os.chdir({str(project.sandbox)!r})\n"
            f"os.environ['GUACAMOLE_SANDBOX'] = {str(project.sandbox)!r}\n"
            f"exec(compile({source.read_text(encoding='utf-8')!r}, {str(source)!r}, 'exec'))\n"
        )
        arguments: dict[str, object] = {"code": code, "timeout": timeout_s}
        reply, images = await call(
            server,
            "execute_code_headless" if headless else "execute_code",
            arguments,
            2 * timeout_s + 30,
        )
        log = project.output_path(Path("logs") / f"freecad-{uuid4().hex}.txt")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(reply, encoding="utf-8")
        # This server reports execution errors as text, sometimes without isError.
        success = (
            "Headless FreeCAD script finished (exit 0)."
            if headless
            else "Code executed successfully:"
        )
        # Raised, the failure was hidden as "exception text omitted", so agents could
        # not see their own script's traceback; it carries no host secrets.
        succeeded = any(line.startswith(success) for line in reply.splitlines())
        return FreeCADExecution(
            succeeded=succeeded,
            reply=reply[:16_000] if succeeded else reply[-16_000:],
            files=tuple(ProducedFile.from_path(p) for p in output_paths if p.is_file()),
            missing_outputs=tuple(str(p) for p in output_paths if not p.is_file()),
            log=ProducedFile.from_path(log),
            views=save_views(images),
        )

    # CAD errors hold no secrets; agents fix calls with them.
    for function in (freecad_status, freecad_view):
        project.tools.register(
            function, retry_safe=True, requires_plan=False, show_errors=True
        )
    project.tools.register(freecad_run, show_errors=True)
