"""KiCad 10 PCB design tools backed by a supplied Konnect MCP server binary.

Konnect (github.com/mixelpixx/Konnect, AGPL-3.0) serves 228 KiCad tools in 21
toolsets over stdio, loading only `project` and `config` at startup. Each call
here runs a fresh server process, loads the owning toolset, then calls the tool,
so nothing depends on the user's auto_load_toolsets setting. Exports and checks
need kicad-cli; live-board tools also need KiCad running with its IPC API on.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import Field

from ...contracts import JSON, Model, ProducedFile

if TYPE_CHECKING:
    from ...project import Project

type Severity = Literal["error", "warning", "info"]
type Limit = Annotated[int, Field(ge=1, le=500)]

# kicad-cli lookup, the macOS/Linux config path, the Windows config path, the
# KiCad IPC socket and log level; the reasoning API key is never passed.
ENVIRONMENT = {
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "TMPDIR",
    "KICAD_API_SOCKET",
    "RUST_LOG",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    "SYSTEMROOT",
}


class KiCadExport(Model):
    reply: str  # Konnect's JSON response text
    files: tuple[ProducedFile, ...]


@asynccontextmanager
async def _session(binary: Path, config: Path | None):
    parameters = StdioServerParameters(
        command=str(binary),
        args=["--config", str(config)] if config else [],
        env={k: v for k, v in os.environ.items() if k in ENVIRONMENT},
    )
    with Path(os.devnull).open("w") as errlog:  # noqa: ASYNC230 - /dev/null is local.
        async with (
            stdio_client(parameters, errlog=errlog) as (reader, writer),
            ClientSession(reader, writer, read_timeout_seconds=30.0) as session,
        ):
            await session.initialize()
            yield session


async def _call(
    session: ClientSession, name: str, arguments: JSON, timeout_s: float
) -> tuple[str, tuple[ImageContent, ...]]:
    result = await session.call_tool(name, arguments, read_timeout_seconds=timeout_s)
    if not isinstance(result, CallToolResult):
        raise TypeError("Konnect returned an unsupported response")
    reply = "\n".join(
        item.text for item in result.content if isinstance(item, TextContent)
    )
    if result.is_error:
        raise RuntimeError(reply)
    return reply, tuple(i for i in result.content if isinstance(i, ImageContent))


async def call(
    binary: Path,
    config: Path | None,
    toolset: str | None,
    name: str,
    arguments: JSON,
    timeout_s: float,
) -> tuple[str, tuple[ImageContent, ...]]:
    """Load toolset (None for always-visible meta-tools), then call the tool."""
    async with _session(binary, config) as session:
        if toolset is not None:
            await _call(session, "load_toolset", {"name": toolset}, 30.0)
        return await _call(session, name, arguments, timeout_s)


def register_konnect_tools(
    project: "Project", binary: Path, config: Path | None = None
) -> None:
    """Register the KiCad checks and exports on the binary.

    Each tool is typed, with every file argument resolved inside the sandbox; wrap
    further Konnect tools the same way rather than passing arguments through.
    config is an optional Konnect config file (kicad_cli path, IPC socket, JLCPCB
    database); without it Konnect uses its own search path and defaults.
    """
    binary = binary.resolve()

    def sandbox(path: str) -> str:
        return str(project.output_path(Path(path)))

    async def run(
        toolset: str | None, name: str, arguments: JSON, timeout_s: float
    ) -> str:
        return (await call(binary, config, toolset, name, arguments, timeout_s))[0]

    async def konnect_status() -> str:
        """Report the Konnect build, binary path, kicad-cli version and redacted KiCad IPC endpoint.

        Call first when KiCad tools fail: it says whether kicad-cli was found and
        whether a running KiCad's IPC API is reachable for live-board tools.
        """
        return await run(None, "get_installation_info", {}, 30.0)

    async def kicad_project_info(project_file: str) -> str:
        """Read a sandbox .kicad_pro: name, schematic/PCB paths, format and KiCad versions."""
        return await run(
            "project", "get_project_info", {"path": sandbox(project_file)}, 60.0
        )

    async def kicad_erc(schematic: str, severity: Severity = "warning") -> str:
        """Run KiCad's Electrical Rules Check on a sandbox .kicad_sch via kicad-cli.

        Returns violations at or above severity with positions in sheet mm. A report
        kicad-cli could not produce is an error, never an empty violation list.
        """
        return await run(
            "sch_export",
            "run_erc",
            {"schematic": sandbox(schematic), "severity": severity},
            300.0,
        )

    async def kicad_drc(
        board: str, severity: Severity = "warning", limit: Limit = 50
    ) -> str:
        """Run KiCad's full configured Design Rule Check on a saved sandbox .kicad_pcb.

        Checks the saved file, not unsaved edits in a live KiCad; schematic parity
        is included when the project has a root schematic. Returns error/warning
        counts and up to limit violations, each naming the owning board item or
        footprint. This is copper/electrical clearance evidence, unlike placement scores.
        """
        return await run(
            "verification",
            "run_drc",
            {"board": sandbox(board), "severity": severity, "limit": limit},
            300.0,
        )

    async def kicad_design_review(
        schematic: str, board: str = "", severity: Severity = "warning"
    ) -> str:
        """Run Konnect's consolidated design review on a sandbox schematic, and DRC on board if given.

        Audits decoupling, connections, power rails and BOM health across every
        reachable sheet. The verdict is INCOMPLETE, never approval, when coverage is
        partial, an audit failed or DRC could not run. Heuristic audits are review
        evidence, not verification of requirements.
        """
        arguments: JSON = {"schematic": sandbox(schematic), "severity_filter": severity}
        if board:
            arguments["board"] = sandbox(board)
        return await run("design_review", "run_design_review", arguments, 600.0)

    async def kicad_netlist_summary(schematic: str) -> str:
        """Summarise a sandbox schematic's components, nets and pin counts as JSON; no kicad-cli needed.

        Nets come from labels and power symbols.
        """
        return await run(
            "sch_export",
            "export_netlist_summary",
            {"schematic": sandbox(schematic)},
            120.0,
        )

    async def jlcpcb_search(
        query: str,
        category: str = "",
        basic_only: bool = False,
        in_stock: bool = True,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> str:
        """Search Konnect's local JLCPCB parts database; every query word must match.

        Words match LCSC number, MPN, package, manufacturer or description. Needs
        the database downloaded first (integration toolset, download_jlcpcb_database).
        Stock and price are as of that download, not live.
        """
        arguments: JSON = {
            "query": query,
            "basic_only": basic_only,
            "in_stock": in_stock,
            "limit": limit,
        }
        if category:
            arguments["category"] = category
        return await run("integration", "search_jlcpcb_parts", arguments, 120.0)

    async def kicad_export_schematic_pdf(
        schematic: str,
        output: str,
        black_and_white: bool = False,
        all_sheets: bool = True,
    ) -> KiCadExport:
        """Export a sandbox schematic to a PDF at a sandbox-relative output path via kicad-cli."""
        destination = project.output_path(Path(output))
        destination.parent.mkdir(parents=True, exist_ok=True)
        reply = await run(
            "sch_export",
            "export_schematic_pdf",
            {
                "schematic": sandbox(schematic),
                "output": str(destination),
                "black_and_white": black_and_white,
                "all_sheets": all_sheets,
            },
            300.0,
        )
        files = (ProducedFile.from_path(destination),) if destination.is_file() else ()
        return KiCadExport(reply=reply, files=files)

    async def kicad_export_manufacturing(
        board: str,
        output_dir: str,
        schematic: str = "",
        fab_house: Literal["jlcpcb", "pcbway", "oshpark", "generic"] = "jlcpcb",
        include_assembly: bool = True,
        bom_fields: str = "",
    ) -> KiCadExport:
        """Export Gerbers, drill, fab-house BOM and pick-and-place for a sandbox board.

        output_dir is sandbox-relative; files returns every file the export wrote
        or changed there. schematic supplies the BOM; bom_fields orders its columns,
        e.g. 'Reference,Value,Footprint,MPN,${QUANTITY}'. JLCPCB assembly needs the
        board open in KiCad with IPC enabled. Run kicad_drc first: exporting is not
        a manufacturability check.
        """
        directory = project.output_path(Path(output_dir))
        directory.mkdir(parents=True, exist_ok=True)

        def stamps() -> dict[Path, int]:
            return {
                p: p.stat().st_mtime_ns for p in directory.rglob("*") if p.is_file()
            }

        before = stamps()
        arguments: JSON = {
            "board": sandbox(board),
            "output_dir": str(directory),
            "fab_house": fab_house,
            "include_assembly": include_assembly,
        }
        if schematic:
            arguments["schematic"] = sandbox(schematic)
        if bom_fields:
            arguments["bom_fields"] = bom_fields
        reply = await run(
            "manufacturing", "export_manufacturing_package", arguments, 900.0
        )
        files = tuple(
            ProducedFile.from_path(p)
            for p, stamp in sorted(stamps().items())
            if before.get(p) != stamp
        )
        return KiCadExport(reply=reply, files=files)

    # Konnect's errors name files, fields and redacted endpoints, never credentials.
    for function in (
        konnect_status,
        kicad_project_info,
        kicad_erc,
        kicad_drc,
        kicad_design_review,
        kicad_netlist_summary,
        jlcpcb_search,
    ):
        project.tools.register(
            function, retry_safe=True, requires_plan=False, show_errors=True
        )
    for function in (kicad_export_schematic_pdf, kicad_export_manufacturing):
        project.tools.register(function, show_errors=True)
