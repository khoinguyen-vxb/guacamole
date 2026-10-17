"""Fan-cooled electronics enclosure: one small project that exercises every integration.

Run with: .venv/bin/python -m examples.enclosure.enclosure

Needs `uv sync --all-extras`, the Claude Code CLI logged in (`claude login`), the
freecad-mcp checkout (`uv sync --project vendor/freecad-mcp --locked
--no-dev`) with FreeCAD installed, typst on PATH, and the two podman images built
from containers/ (their IDs are pinned below; rebuild and update them together).

Edit the configuration below; this script has no command-line arguments.
Ctrl-C stops the host; rerunning resumes this workspace's saved run.
"""

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path

from guacamole import (
    Budget,
    ContextSpec,
    Project,
    ProjectRequest,
    ToolRegistry,
    Watchdog,
)
from guacamole.console import host, preflight
from guacamole.integrations.freecad import SERVER as FREECAD_MCP
from guacamole.integrations.konnect import register_konnect_tools
from guacamole.integrations.openfoam import register_openfoam_tools
from guacamole.integrations.usd.twin import register_twin_tools
from guacamole.middleware import standard_middleware
from guacamole.providers.claude import ClaudeReasoning
from guacamole.tools.containers import Container
from guacamole.tools.workspace import register_workspace_tools, tool_paths

# Paths are relative to this file, never the shell's cwd.
ROOT = Path(__file__).resolve().parent
TOOLING = ROOT / "tooling"
WORKSPACE = ROOT / ".guacamole"
SANDBOX = ROOT / "results"
CONTROL_PORT = 8768

# Local podman images from containers/*.Containerfile, pinned by image ID.
OPENFOAM = Container(
    image="sha256:976cc96c082e1829a619bebe632ffebc1de8ee7c17f85c589a64722541ef2f9e",
    engine="podman",
    shm_size="1g",
)
OPENFOAM_BASHRC = Path("/opt/openfoam12/etc/bashrc")
KONNECT = Container(
    image="sha256:6f3c9de2fc39c5e97087ffe9aaa047c4c734ae6820d979203f81029d4738459c",
    engine="podman",
)
KONNECT_BINARY = Path("/usr/local/bin/konnect")
# The image's symbol and footprint libraries, copied out for agents to read:
# containers/kicad-libs.sh <KONNECT image ID>.
KICAD_LIBS = ROOT / "kicad-libs"

# A trial project: modest limits so a run shows the whole flow without a large bill.
CONTEXT = ContextSpec(max_input_tokens=400_000, reserved_output_tokens=20_000)
BUDGET = Budget(
    max_steps=4_000,
    max_tool_calls=1_500,
    max_seconds=6 * 3600,
    max_agents=8,
    max_run_input_tokens=8_000_000,
)
MAX_CONCURRENT_CALLS = 3
# Chief, Systems Engineer and workers; ClaudeReasoning defaults to "max".
EFFORT = "high"
# The watchdog reports at this interval and sends a note to an agent whose recent
# actions were all rejected or repeated, using its own low-effort Claude process.
WATCHDOG_REPORT_S = 600.0

DESCRIPTION = """
Fan-cooled electronics enclosure, to preliminary design review (PDR).

Design a small wall- or desk-mounted enclosure for a single-board computer that
dissipates 8 W in steady state (treat it as one 85 x 56 mm board with a 15 x 15 mm
SoC carrying 6 W; the remaining 2 W spread over the board). It sits indoors in
still air at up to 35 degC ambient.

Requirements:
- External envelope no larger than 120 x 90 x 50 mm.
- One 40 x 40 x 10 mm 12 V axial fan; the airflow path, inlet and outlet vents
  are the designer's choice. Vents must stop a 2.5 mm probe (IP2X-style finger
  and wire protection).
- SoC case temperature at most 70 degC at 35 degC ambient, shown by CFD with
  heat transfer; report the margin. If the fan curve is not known, state the
  assumed operating point.
- Enclosure printable in PETG with 2 mm minimum wall thickness; total mass of the
  enclosure parts at most 150 g.
- A small fan and power-entry PCB: 12 V DC barrel jack, reverse-polarity
  protection, a 2-pin fan header, a 10 k NTC thermistor near the SoC, and a
  header passing 12 V and the thermistor to the computer. It must pass ERC and
  DRC with zero errors and have fabrication outputs.

Deliverables for PDR: parametric CAD and STEP of the enclosure; the CFD case and
its results; the PCB project with ERC/DRC reports, schematic PDF and fabrication
outputs; a USD digital twin carrying the CAD, thermal and electrical layers; and
a design report as a PDF.
"""

INSTRUCTIONS = """This is a trial project to exercise the toolchain end to end. Keep
the design simple and conservative, and prefer recorded assumptions to questions.

CAD: write FreeCAD Python scripts to the sandbox and run them with freecad_run
(headless by default). Lengths are mm. Save FCStd and STEP, and export each part
as STL for meshing and conversion. Verify solids, wall thickness, envelope and mass
from the model with the PETG density you record.

CFD: start from the closest OpenFOAM 12 tutorial (openfoam_tutorials, for example
a conjugate heat transfer or buoyant case) with openfoam_copy_tutorial, then adapt
it with openfoam_set or write_text. Model the fan as a fixed flow inlet or
pressure jump at a recorded operating point. Run blockMesh/snappyHexMesh, checkMesh
and the solver with openfoam_run; read residuals and sample SoC temperature with
openfoam_table or postProcess. Convergence alone is not acceptance.

PCB: KiCad 10 and its standard libraries run only inside the Konnect container,
which the kicad_* tools use; nothing KiCad is installed on the host. Read symbol
and footprint definitions from the read-only copy at KICAD_LIBS_PATH (symbols/,
footprints/, and the sym-lib-table and fp-lib-table naming each library) with
list_files and read_text. Write the .kicad_pro, .kicad_sch and .kicad_pcb files
with write_text or a Python script run through execute, referencing parts by
their standard library names (Device:R, Connector_BarrelJack:BarrelJack_Horizontal)
and embedding the symbol and footprint definitions you copied, so the container's
KiCad resolves them. Check with kicad_erc and kicad_drc, and export with
kicad_export_schematic_pdf and kicad_export_manufacturing. Never run podman,
docker or KiCad yourself, and do not search outside the project and its inputs.
jlcpcb_search has no network here; choose generic parts and record them.

Digital twin: once the SysML model has its parts, use twin_inspect, then
twin_attach a layer per domain (cad, thermal, electrical) citing the records it
rests on. Geometry layers take .usda files in metres, Z up: convert the STL
exports with a Python script using pxr (usd-core is installed in this
interpreter) run through execute.

Documents: follow the engineering-documentation skill (read its SKILL.md with
read_text) and compile the design report and the PDR package summary with typst
through execute. Every claim cites a record.
"""


def project_request(context: ContextSpec) -> ProjectRequest:
    instructions = INSTRUCTIONS.replace("KICAD_LIBS_PATH", str(KICAD_LIBS))
    return ProjectRequest(
        description=DESCRIPTION,
        context=context.model_copy(update={"instructions": instructions}),
        budget=BUDGET,
    )


async def main() -> None:
    preflight(
        "claude",
        "Install the Claude Code CLI on PATH and run 'claude login'.",
        ("websockets", "pxr", "langchain"),
        "Run 'uv sync --all-extras', then '.venv/bin/python -m examples.enclosure.enclosure'.",
    )
    stamp = KICAD_LIBS / "IMAGE"
    if not stamp.is_file() or stamp.read_text().strip() != KONNECT.image:
        raise SystemExit(
            f"Run 'examples/enclosure/containers/kicad-libs.sh {KONNECT.image}' first."
        )
    with Project(
        WORKSPACE,
        sandbox=SANDBOX,
        tools=ToolRegistry(),
        max_concurrent_calls=MAX_CONCURRENT_CALLS,
        reasoning=ClaudeReasoning(web_search=False, effort=EFFORT),
        watchdog=Watchdog(
            ClaudeReasoning(web_search=False), report_interval_s=WATCHDOG_REPORT_S
        ),
    ) as project:
        tools = tool_paths(TOOLING, FREECAD_MCP)
        register_workspace_tools(project, ROOT, (KICAD_LIBS,), tools)
        register_openfoam_tools(project, OPENFOAM_BASHRC, OPENFOAM)
        register_konnect_tools(project, KONNECT_BINARY, container=KONNECT)
        register_twin_tools(project)
        async with AsyncExitStack() as cleanup:
            project.middleware = await standard_middleware(WORKSPACE, cleanup)
            await host(
                project,
                project_request,
                port=CONTROL_PORT,
                context=CONTEXT,
                budget=BUDGET,
            )


if __name__ == "__main__":
    asyncio.run(main())
