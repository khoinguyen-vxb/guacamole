# /// script
# requires-python = ">=3.13.3"
# dependencies = [
#   "guacamole-engineering[sounding-rocket,langchain,graphiti,mem0,rde]",
#   "freecad-mcp",
#   # Linux aarch64 has no usd-core wheel; see the docstring.
#   "usd-core>=25.5,<27; platform_machine != 'aarch64'",
# ]
# [tool.uv.sources]
# guacamole-engineering = { path = "../..", editable = true }
# freecad-mcp = { path = "../../vendor/freecad-mcp", editable = true }
# ///
"""Rotating detonation engine with an aerospike nozzle, to PDR.

Run with: .venv/bin/python -m examples.RDE.RDE
Or:       uv run examples/RDE/RDE.py

Setup for the first form:
    uv sync --inexact --extra sounding-rocket --extra langchain --extra graphiti \\
        --extra mem0 --extra rde --extra usd
    uv sync --project vendor/freecad-mcp --locked --no-dev
Linux aarch64 has no usd-core wheel: leave out --extra usd, install conda-forge
openusd for Python 3.13, and add a .pth to .venv naming a directory that holds
only a link to its pxr package, plus a line setting PXR_PLUGINPATH_NAME to the
conda env's lib/usd (through the link, USD cannot find its own plugins).

Also needs the Claude Code CLI logged in (claude login), FreeCAD, typst on PATH,
docker, the detonationFoam and Konnect images built from containers/ (their IDs
are pinned below; rebuild and update them together) and the KiCad libraries
copied out of the Konnect image (see KICAD_LIBS), the PicoGK runtime copied out
of its image (see PICOGK_NATIVE), and the .NET 9 SDK on PATH as dotnet.

Edit the configuration below; this script has no command-line arguments.
Ctrl-C stops the host; rerunning resumes this workspace's saved run.
Follow it with examples/RDE/watch.py; correct it with examples/RDE/interject.py.
Tool processes have the user's OS permissions; the output directory is not an
OS sandbox. Source checkouts are available for inspection, not assumed installed.
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
from guacamole.tools.workspace import inventory, register_workspace_tools, tool_paths

# Project configuration. Paths are relative to this file, never the shell's cwd.
ROOT = Path(__file__).resolve().parent
DOCUMENTS = ROOT / "context"
TOOLING = ROOT / "tooling"
WORKSPACE = ROOT / ".guacamole"
SANDBOX = ROOT / "results"
RESUME_RUN_ID: str | None = None  # None automatically resumes a single saved run.
CONTROL_PORT = 8769  # ehopper 8766, kookaburra 8765, bracket 8767, enclosure 8768.

# Local docker image from containers/detonationfoam.Containerfile, pinned by ID:
# OpenFOAM 8 (rhoCentralFoam and the standard utilities) with detonationFoam V2.0.
DETONATIONFOAM = Container(
    image="sha256:58d7781c77e6371f4ee3dff1b94911010c66effefd6c753282c3f0cf9751053f",
    shm_size="2g",
)
OPENFOAM_BASHRC = Path("/opt/OpenFOAM-8/etc/bashrc")
# Local docker image from containers/konnect.Containerfile, pinned by ID: KiCad 10
# from its PPA and the Konnect MCP server built from source, both for this arch.
KONNECT = Container(
    image="sha256:e9a628074648585571daa8e0fa92511b03b187a902b7f9185fc3e9b9576b0de4"
)
KONNECT_BINARY = Path("/usr/local/bin/konnect")
# The image's symbol and footprint libraries, copied out for agents to read:
# ENGINE=docker examples/enclosure/containers/kicad-libs.sh <KONNECT image ID> \
#     examples/RDE/kicad-libs
KICAD_LIBS = ROOT / "kicad-libs"
# PicoGK's Linux runtime (picogk.26.2.so and its libraries; PicoGK ships only macOS
# and Windows ones), built with containers/picogk.Containerfile and copied here.
PICOGK_NATIVE = ROOT / "picogk-native"
# The NSGA-II genetic algorithm supplied with the sounding-rocket example.
NSGA = ROOT.parent / "sounding_rocket/tooling/nsga.py"

CONTEXT = ContextSpec(max_input_tokens=12800000, reserved_output_tokens=20000)
WORKER_MAX_INPUT_TOKENS = CONTEXT.max_input_tokens
# The watchdog prints a status report at this interval and helps looping or
# context-saturated agents using its own low-effort Claude process (no web search).
WATCHDOG_REPORT_S = 600.0
# Agent model calls running at once; others queue. Lower it if Claude rate-limits.
MAX_CONCURRENT_CALLS = 4
BUDGET = Budget(
    max_steps=200000, max_tool_calls=15000, max_seconds=720000, max_agents=24
)

# Context middleware, README "Context middleware". Context editing always runs and
# needs no API key. With OPENAI_API_KEY set, older sources are also summarized and
# every agent turn feeds a Graphiti knowledge graph and mem0 memory (billed usage).
SUMMARY_MODEL = "openai/gpt-6-luna"  # 922k-token input holds untrimmed sources.
SUMMARIZE_AT_TOKENS = 150_000  # Optional sources above this are compacted.
CLEAR_AT_TOKENS = 400_000  # Above this, reads beyond the latest 8 are hidden per call.

# Optional interpreter overrides, e.g. {"detonationFoam": Path("/path/to/python")}.
# Otherwise use the tool checkout's .venv/bin/python if present, then this interpreter.
PYTHON_EXECUTABLES: dict[str, Path] = {}

DESCRIPTION = """
Rotating detonation engine (RDE) with an aerospike nozzle, and everything needed
to hot-fire it on the ground, to preliminary design review (PDR). No mistakes.

Performance:
- 5 kN thrust at sea level; the nozzle exhausts to a constant 101325 Pa.
- At least 30 kN·s total impulse per firing.
- Propellants: chosen by a trade study of propellant combinations.
There is no operating pressure or specific impulse target: choose and justify the
pressures, and report the delivered specific impulse. There are no manufacturing
or budget constraints.

Scope: the complete test article and its ground support, as one system.
- Engine: injector and manifolds, annular combustor, centrebody and aerospike,
  cooling, igniter (predetonator) and instrumentation ports.
- Fluids: the propellant, pressurant and inert purge systems from storage to the
  injector: tanks or cylinders, regulators, main, purge, vent and relief valves,
  check valves, filters, lines, fittings and flow metering. Size them with
  pressure-drop, flow and relief calculations.
- Ground test equipment: a thrust stand with its load cell and calibration, engine
  mounts, propellant and plumbing panels, and safety provisions (shielding,
  keep-out distances, remote operation).
- Electronics: data acquisition (high-speed chamber pressure, feed pressures,
  temperatures and thrust), valve drivers and a firing sequencer with abort and
  emergency stop, the ignition supply, power distribution and wiring harnesses.

Every single component gets its own individual drawing and/or schematic:
- each manufactured part: a detail drawing with tolerances, material and finish;
- each purchased part: a drawing or specification sheet citing its part number
  and source;
- each assembly: an assembly drawing with its parts list;
- the fluid systems: a P&ID; each circuit board: a schematic, an ERC/DRC-clean PCB
  and fabrication outputs; each harness: a wiring diagram.

Deliverables for PDR: parametric CAD and STEP of every part and assembly, the
drawings and schematics above, the CFD cases and results, the analyses, a bill of
materials, a hazard analysis and ground test plan, a USD digital twin, and a
design report as a PDF.
"""

INSTRUCTIONS = """Work to a critical design review (CDR) package. Correctness
matters more than speed: every number is computed by a script you saved, in
explicit SI units, from a cited source or a recorded assumption.

Thermochemistry: use Cantera (installed in this interpreter: execute ['python',
...]). Trade propellant combinations (for example hydrogen, methane, ethylene,
kerosene or ethanol with oxygen or nitrous oxide) in a recorded study of
performance, detonability and cell size, density and storage, feed system,
cooling, and ground test safety. Use published mechanisms: Cantera ships
h2o2.yaml and gri30.yaml; save any other in the sandbox and cite its source
(kerosene needs a published surrogate). Choose the mixture ratio and the injection
and chamber pressures in the same study, then compute the
Chapman-Jouguet speed and pressure, the induction length and a detonation cell
size with its correlation and source, and frozen and shifting equilibrium
expansion to 101325 Pa. Size the annulus (fill height, channel gap, length,
diameter) and the injector against published RDE geometric criteria scaled by
cell size, citing them. Derive mass flow from thrust and the delivered specific
impulse, not the ideal one, and burn time and propellant loads from the total
impulse.

CFD: OpenFOAM 8 with detonationFoam V2.0 (solver detonationFoam_V2.0) and
rhoCentralFoam runs in a container through the openfoam_* tools; nothing
OpenFOAM is installed on the host. List cases with openfoam_tutorials (the
detonationFoam tutorials are under detonationFoam/), copy with
openfoam_copy_tutorial and adapt with openfoam_set or write_text. The solver
source and its README are in tooling/detonationFoam. This build solves gaseous
mixtures only (its two-phase spray model is on an unbuilt dev branch): model a
liquid propellant as pre-vaporised and record what that leaves out of liquid
injection. Convert mechanisms with chemkinToFoam. First verify
the solver on your mixture: a 1D detonation whose wave speed matches your
Cantera CJ speed, at a resolution of stated cells per induction length. Then run
an unrolled 2D annulus (periodic azimuthally, injection inlet, outlet) for wave
number, wave speed, pressure gain and thrust, and an axisymmetric rhoCentralFoam
case for the aerospike expansion at 101325 Pa. Show mesh convergence on the
quantities you report. Run in parallel with decomposePar; read residuals, probes
and logs. Convergence or a running wave alone is not acceptance.

Nozzle: design the aerospike contour by the method of characteristics (or a cited
approximate method) for the CFD-derived exit state, then choose and justify any
truncation and base bleed.

Thermal and structure: estimate wall heat flux from CFD and cited RDE
measurements (not the Bartz correlation alone), choose the cooling scheme
(respecting the coolant's coking, boiling or decomposition limits) and the
material with cited high-temperature properties, and check walls, centrebody,
injector and flanges for pressure, thermal stress and fatigue at the wave
frequency, using the CJ peak pressure as a load.

Cooling and channel exploration: with no manufacturing constraints, explore
unconventional cooling and flow-channel geometries before settling on one, such
as gyroid and other triply periodic minimal surface lattices, transpiration
through porous or lattice walls, branching manifolds, helical or variable-section
regenerative channels, and conformal channels in the centrebody and aerospike.
Generate them with PicoGK (tooling/PicoGK, C#; the .NET 9 SDK is on PATH as
dotnet). Write a net9.0 console project in the sandbox that compiles PicoGK's
sources in rather than referencing PicoGK.csproj, so nothing is built inside the
checkout: Compile PICOGK_PATH/**/*.cs excluding obj/ and bin/, embed
assets/ViewerEnvironment.zip and assets/Jost.ttf with LogicalName
PicoGK.Resources.Environment.zip and PicoGK.Resources.Font.ttf, reference the
SkiaSharp 3.119.0 package, and copy every file in PICOGK_NATIVE_PATH to the
output directory. Build geometry headless with `using Library lib = new(voxelMM)`
(never Library.Go, which opens a viewer) and export STL. Optimise each concept's
parameters with the NSGA-II genetic algorithm in nsga.py (execute with repository
nsga.py), scoring candidates with your saved thermal-hydraulic models (wall
temperature margin, coolant pressure drop and temperature rise, mass), and
confirm the chosen ones with CFD or conjugate heat transfer (chtMultiRegionFoam).
Record each Pareto front and why each concept was kept or dropped, then bring the
selected geometry into FreeCAD for the assemblies and drawings.

Fluids: draw the P&ID with ISO 10628-2 or ANSI/ISA-5.1 symbols as DXF and PDF from
a Python script using ezdxf (installed in this interpreter), tagging every line
and component to its BOM entry. Calculate propellant and pressurant masses with
residuals, line and orifice or venturi sizing, pressure drops along each path,
regulator droop, relief valve sizing to a cited method, and valve-closure surge.
Cover the selected propellants' handling: for a cryogen, chilldown, boil-off,
two-phase flow at the injector, insulation and trapped-volume relief; for an
oxidiser, material compatibility and cleaning to cited standards.

Ground test equipment: size the thrust stand for the peak and dynamic loads, keep
its natural frequency clear of the measured and wave frequencies, select and
calibrate the load cell, and set keep-out distances and shielding from a cited
method. The hazard analysis and test plan cover start, shutdown, abort, purge and
safing.

Electronics: KiCad 10 and its standard libraries run only inside the Konnect
container, which the kicad_* tools use; nothing KiCad is installed on the host.
Read symbol and footprint definitions from the read-only copy at KICAD_LIBS_PATH
(symbols/, footprints/, and the sym-lib-table and fp-lib-table naming each
library) with list_files and read_text. Write the .kicad_pro, .kicad_sch and
.kicad_pcb files with write_text or a Python script run through execute,
referencing parts by their standard library names and embedding the symbol and
footprint definitions you copied, so the container's KiCad resolves them. Check
with kicad_erc and kicad_drc, and export with kicad_export_schematic_pdf and
kicad_export_manufacturing. Never run docker or KiCad yourself, and do not search
outside the project and its inputs. jlcpcb_search has no network here; choose
parts by datasheet and record them. Size sample rates from the CFD wave frequency.
Draw each harness as a wiring diagram (a KiCad schematic or an ezdxf DXF/PDF).
Write the firing sequence and abort logic as software under results/software and
test every transition, including abort from each state.

CAD: write FreeCAD Python scripts to the sandbox and run them with freecad_run
(headless by default). Lengths are mm. Model every part of the engine, the fluid
systems and the test stand. Save FCStd and STEP, and STL for meshing and
conversion. Verify solids, gaps and wall thicknesses, mass and CG from the model
with recorded densities; a CAD process succeeding does not establish geometry
acceptance.

Drawings: export each part as its own one-part STEP and draw it with draw_part,
then put its PMI in the FCStd with mbd_annotate. Draw each assembly through a
FreeCAD TechDraw script run with freecad_run, with balloons and a parts list
matching the BOM. Purchased parts get a drawing from the vendor's STEP or a
specification sheet citing part number, source URL and access date. Keep a
drawing register mapping every BOM line to its drawing or schematic, and check it
is complete with verify_command before PDR.

Digital twin: once the SysML model has its parts, use twin_inspect, then
twin_attach a layer per domain (cad, cfd, thermal, fluids, electrical) citing the
records it rests on. Geometry layers take .usda files in metres, Z up: convert the
STL exports with a Python script using pxr (installed in this interpreter) run
through execute.

Documents: follow the engineering-documentation skill (read its SKILL.md with
read_text) and compile the design report and the PDR package summary with typst
through execute. Every claim cites a record.

Use built-in web search for papers, material data and supplier information, and
record source URLs and access dates; the supplied papers in context/ come first.
Stay within design and analysis to PDR: no hardware purchasing, no test claims
without data, and keep unknowns as open items.
"""


def supplied_tools() -> dict[str, Path]:
    tools = tool_paths(TOOLING, FREECAD_MCP, NSGA)
    tools.pop("VXB-Topology-Optimisation", None)  # In tooling/, not offered to agents.
    return tools


def register_tools(project: Project) -> None:
    register_workspace_tools(
        project,
        ROOT,
        (DOCUMENTS, KICAD_LIBS, PICOGK_NATIVE),
        supplied_tools(),
        PYTHON_EXECUTABLES,
    )
    register_openfoam_tools(project, OPENFOAM_BASHRC, DETONATIONFOAM)
    register_konnect_tools(project, KONNECT_BINARY, container=KONNECT)
    register_twin_tools(project)


def project_request(project: Project, context: ContextSpec) -> ProjectRequest:
    """Inventory the supplied packages without importing or running their code."""
    documents, inventory_ref = inventory(
        project,
        "RDE supplied inputs",
        DOCUMENTS,
        supplied_tools(),
        ("uv", "claude", "freecad", "freecadcmd", "freecad.cmd", "typst", "dotnet"),
        tool_docs=("README*", "pyproject.toml", "docs/*.md"),
    )
    return ProjectRequest(
        description=DESCRIPTION,
        documents=documents,
        context=context.model_copy(
            update={
                "instructions": INSTRUCTIONS.replace("KICAD_LIBS_PATH", str(KICAD_LIBS))
                .replace("PICOGK_NATIVE_PATH", str(PICOGK_NATIVE))
                .replace("PICOGK_PATH", str(TOOLING / "PicoGK")),
                "pinned": (inventory_ref,),
            }
        ),
        budget=BUDGET,
    )


async def main() -> None:
    preflight(
        "claude",
        "Install the Claude Code CLI on PATH and run 'claude login' with your Claude account.",
        (
            "websockets",
            "pypdf",
            "openpyxl",
            "pptx",
            "langchain",
            "langchain_litellm",
            "graphiti_core",
            "mem0",
            "cantera",
            "scipy",
            "pxr",
        ),
        "See the setup steps at the top of examples/RDE/RDE.py.",
    )
    stamp = KICAD_LIBS / "IMAGE"
    if not stamp.is_file() or stamp.read_text().strip() != KONNECT.image:
        raise SystemExit(
            "Copy the KiCad libraries out of the pinned image first: see KICAD_LIBS."
        )
    if not (PICOGK_NATIVE / "picogk.26.2.so").is_file():
        raise SystemExit(
            "Copy the PicoGK runtime out of its image first: see PICOGK_NATIVE."
        )
    with Project(
        WORKSPACE,
        sandbox=SANDBOX,
        tools=ToolRegistry(),
        max_concurrent_calls=MAX_CONCURRENT_CALLS,
        reasoning=ClaudeReasoning(web_search=True),
        watchdog=Watchdog(
            ClaudeReasoning(web_search=True), report_interval_s=WATCHDOG_REPORT_S
        ),  # Runs at the lowest reasoning effort to reserve usage budget.
    ) as project:
        register_tools(project)
        # Opened after the workspace lock: the graph and vector stores live in it.
        async with AsyncExitStack() as cleanup:
            project.middleware = await standard_middleware(
                WORKSPACE,
                cleanup,
                summary_model=SUMMARY_MODEL,
                summarize_at_tokens=SUMMARIZE_AT_TOKENS,
                clear_at_tokens=CLEAR_AT_TOKENS,
            )
            await host(
                project,
                lambda context: project_request(project, context),
                port=CONTROL_PORT,
                context=CONTEXT,
                budget=BUDGET,
                run_id=RESUME_RUN_ID,
                worker_max_input_tokens=WORKER_MAX_INPUT_TOKENS,
            )


if __name__ == "__main__":
    asyncio.run(main())
