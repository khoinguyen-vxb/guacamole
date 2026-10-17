# /// script
# requires-python = ">=3.13.3"
# dependencies = [
#   "guacamole-engineering[sounding-rocket,langchain,graphiti,mem0]",
#   "freecad-mcp",
# ]
# [tool.uv.sources]
# guacamole-engineering = { path = "../..", editable = true }
# freecad-mcp = { path = "freecad-mcp", editable = true }
# ///
"""Run with: uv run examples/ehopper/ehopper.py

Or: uv sync --extra sounding-rocket --extra langchain --extra graphiti --extra mem0
    uv sync --project examples/ehopper/freecad-mcp --locked --no-dev
    .venv/bin/python -m examples.ehopper.ehopper

Edit the configuration below; this script has no command-line arguments.
Install the Codex CLI and run codex login with your ChatGPT account before running.
Reasoning uses a local codex exec process with GPT-6 Astra; no API key is needed.
Optional OPENAI_API_KEY adds context summarization and Graphiti/mem0 memory.
uv installs this script's document readers; backend installations are separate.
See https://docs.astral.sh/uv/guides/scripts/ for inline dependency metadata.

The authenticated loopback WebSocket stays available during work and human waits.
Use human_inbox/reply_human/interject/review_disposition commands from README.md.
Ctrl-C stops the host; rerunning resumes this workspace's saved run.
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
from guacamole.integrations.freecad import register_freecad_tools
from guacamole.middleware import standard_middleware
from guacamole.providers.codex import CodexReasoning
from guacamole.tools.workspace import inventory, register_workspace_tools, tool_paths

# Project configuration. Paths are relative to this file, never the shell's cwd.
ROOT = Path(__file__).resolve().parent
DOCUMENTS = ROOT / "context"
TOOLING = ROOT / "tooling"
WORKSPACE = ROOT / ".guacamole"
SANDBOX = ROOT / "results"
FREECAD_MCP = ROOT / "freecad-mcp"
RESUME_RUN_ID: str | None = None  # None automatically resumes a single saved run.
CONTROL_PORT = 8766
CONTEXT = ContextSpec(max_input_tokens=12800000, reserved_output_tokens=20000)
WORKER_MAX_INPUT_TOKENS = CONTEXT.max_input_tokens
# The watchdog prints a status report at this interval and helps looping or
# context-saturated agents using its own low-effort codex process (no web search).
WATCHDOG_REPORT_S = 600.0
# Agent model calls running at once; others queue. Lower it if codex rate-limits.
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

# Optional interpreter overrides, e.g. {"6dof_hopper": Path("/path/to/python")}.
# Otherwise use the repository's .venv/bin/python if present, then this interpreter.
PYTHON_EXECUTABLES: dict[str, Path] = {}


DESCRIPTION = """Project Electronic Hopper: build a self-landing hopper using
electric motors and counter-rotating coaxial propellers. Reach approximately 5 m
above takeoff level, sustain hover there for 5 minutes, then land under control.
There is no specified propeller diameter limit. Keep purchased vehicle hardware and
materials below 500 AUD, excluding tax and shipping. It is a zero-payload
demonstrator flown in calm air near sea level. The photos in
context/reference_images show flown designs of this kind.

Scope: select the motors, coaxial propellers, ESCs and battery; design the
editable vehicle CAD using the supplied FreeCAD MCP; diagnose, fix, improve
and integrate PID control into the supplied tooling/6dof_hopper simulator.
Deliver the propulsion trade study and priced BOM, native FCStd assembly and
STEP/drawings, mass/CG/inertia data, runnable corrected simulator and PID code,
gain configuration, repeatable verification scripts, logs and test procedures.
Prepare the PDR package for these deliverables; CDR is out of scope for this run.
context/brief.md is the current project brief: it records the agreed vehicle
configuration, budget rules and simulation acceptance targets. Controller hardware
remains open. Ask focused questions where missing requirements block selection;
keep provisional assumptions explicit.
"""

INSTRUCTIONS = """Start with the hopper brief and context/previous_run/README.md, which
indexes unverified prior work to build on rather than repeat.

Use built-in live web search for current manufacturer/supplier prices, motor
dimensions, mounting drawings, thrust data, ESC ratings and battery specifications.
Record exact part numbers, source URLs, access dates, currency, units, stock status
and shipping/tax exclusions in sourcing notes saved through write_text. Keep
unavailable or conflicting specifications explicit rather than inventing them.

Size propulsion from a complete mass and energy budget, including the battery
and climb/landing energy beyond the 300-second hover. Use traceable vendor data
and dated prices; if current product data cannot be obtained, request it from
the human and leave the selection provisional. Include coaxial interference,
counter-rotation torque, thrust reserve, current/voltage/thermal limits and usable
battery energy. Do not double isolated-rotor thrust without evidence. Retain
calibration parameters for coaxial loss and motor/ESC response.

Use freecad_status to inspect the GUI addon, and freecad_run to execute a saved
sandbox Python script through the supplied FreeCAD MCP. Headless execution is
the default and does not require the GUI addon. Declare all CAD exports in outputs.
With the GUI addon, freecad_view saves a screenshot to read; a picture can flag
a missing feature or interference but never replaces measured geometry checks.
Save parametric FCStd and STEP files; verify actual solids, rotor/structure
clearances, mounting interfaces and mass/CG/inertia with material densities.
FreeCAD lengths are mm; simulator quantities are SI. Record the CAD-to-body frame
transform. A CAD process succeeding does not establish geometry acceptance.

Audit the actual 6DOF plant and report each root cause before changing it.
Read every caller of affected functions. Repair state-vector handling, imports,
quaternion/frame conventions, integrator return values and propulsion interfaces
before tuning control. The supplied propeller class is incomplete, and the
pendulum project is reference material, not an already-integrated hopper PID.
Select a physically realizable pitch/roll actuator arrangement: a coaxial pair
alone does not provide arbitrary three-axis moments. Model motor lag, actuator
saturation, differential reaction torque and the selected tilt/control mechanism.
Update PID at a fixed control cadence, holding commands between samples; do not
mutate PID integrals inside adaptive solve_ivp RHS evaluations. Include anti-windup,
filtered derivative feedback, explicit units and configurable gains/limits.
Verify hover trim, quaternion norm, attitude recovery, altitude tracking,
disturbances, saturation recovery and takeoff/300-second hover/landing. Score them
against the simulation acceptance targets in the brief, propose the still-open
disturbance, reserve and solver tolerances for human agreement, and record measured
errors, touchdown rates, thrust/current/energy and budget margins. Preserve original
source checkouts; publish a runnable modified copy/patch under results/software.
Stay within propulsion, CAD and simulated PID integration; the pendulum reference
does not add Gazebo, ROS, MPC or machine-learning work to this project.
"""


def register_tools(project: Project) -> None:
    tools = tool_paths(TOOLING, FREECAD_MCP)
    register_workspace_tools(
        project, ROOT, (DOCUMENTS, TOOLING), tools, PYTHON_EXECUTABLES
    )
    register_freecad_tools(project, FREECAD_MCP)


def project_request(project: Project, context: ContextSpec) -> ProjectRequest:
    """Inventory the supplied packages without importing or running their code."""
    tools = tool_paths(TOOLING, FREECAD_MCP)
    pythrust = tools["6dof_hopper"] / "PyThrust"
    documents, inventory_ref = inventory(
        project,
        "Electronic Hopper supplied inputs",
        DOCUMENTS,
        tools,
        ("uv", "codex", "freecad", "freecadcmd", "FreeCADCmd", "freecad.cmd"),
        extra=(*pythrust.glob("README*"), *pythrust.glob("pyproject.toml")),
        tool_docs=("README*", "pyproject.toml", "docs/*.md"),
    )
    return ProjectRequest(
        description=DESCRIPTION,
        documents=documents,
        # PDR first; a CDR target waits until a PDR has been accepted.
        target_reviews=("PDR",),
        context=context.model_copy(
            update={"instructions": INSTRUCTIONS, "pinned": (inventory_ref,)}
        ),
        budget=BUDGET,
    )


async def main() -> None:
    preflight(
        "codex",
        "Install the Codex CLI on PATH and run 'codex login' with your ChatGPT account.",
        (
            "websockets",
            "pypdf",
            "openpyxl",
            "pptx",
            "langchain",
            "langchain_litellm",
            "graphiti_core",
            "mem0",
        ),
        "Run 'uv sync --extra sounding-rocket --extra langchain --extra graphiti "
        "--extra mem0', then '.venv/bin/python -m examples.ehopper.ehopper'; "
        "or use 'uv run examples/ehopper/ehopper.py'.",
    )
    with Project(
        WORKSPACE,
        sandbox=SANDBOX,
        tools=ToolRegistry(),
        max_concurrent_calls=MAX_CONCURRENT_CALLS,
        reasoning=CodexReasoning(web_search=True),
        watchdog=Watchdog(
            CodexReasoning(web_search=False), report_interval_s=WATCHDOG_REPORT_S
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
