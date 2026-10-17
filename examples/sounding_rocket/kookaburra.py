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
from guacamole.middleware import standard_middleware
from guacamole.providers.codex import CodexReasoning
from guacamole.tools.workspace import inventory, register_workspace_tools, tool_paths

# Project configuration. Paths are relative to this file, never the shell's cwd.
ROOT = Path(__file__).resolve().parent
DOCUMENTS = ROOT / "technical_documents"
TOOLING = ROOT / "tooling"
WORKSPACE = ROOT / ".guacamole"
SANDBOX = ROOT / "results"
RESUME_RUN_ID: str | None = None  # None automatically resumes a single saved run.
CONTROL_PORT = 8765
CONTEXT = ContextSpec(max_input_tokens=12800000, reserved_output_tokens=20000)
# The watchdog prints a status report at this interval and helps looping or
# context-saturated agents using its own low-effort Codex process (no web search).
WATCHDOG_REPORT_S = 600
BUDGET = Budget(
    max_steps=20000, max_tool_calls=15000, max_seconds=720000, max_agents=24
)
SUMMARY_MODEL = "openai/gpt-6-luna" 
SUMMARIZE_AT_TOKENS = 150_000 
CLEAR_AT_TOKENS = 80_000 
PYTHON_EXECUTABLES: dict[str, Path] = {}

DESCRIPTION = """Project Kookaburra: 
Hello friend, I want to build a sounding rocket with a custom made hybrid rocket engine. 

The rocket's mission profile is to carry a 3U 2kg payload to a 30,000ft AGL altitude, launching from Spaceport Midland Texas during July 2027. You need
to design an apogee tolerance for +/- 2000ft FT from the apogee target, in order to accomplish this - please implement an airbrakes system with a controller 
and associated custom avionics. You also need a backup avionics system that is commercial off the shelf. 

I've supplied to you existing propietary technical documentation for previous successful rockets from USYD Rocketry Team as a basis to formulate your design decisions upon.
"""








INSTRUCTIONS = """Start with the relevant historical design documents.
list_files with an empty path lists the supplied input/output directories. Reader
paths may be absolute, relative to this example, or relative to the output directory
(including FileRecord.path values such as artifacts/<hash>/<filename>).
"""


def register_tools(project: Project) -> None:
    register_workspace_tools(
        project, ROOT, (DOCUMENTS, TOOLING), tool_paths(TOOLING), PYTHON_EXECUTABLES
    )


def project_request(project: Project, context: ContextSpec) -> ProjectRequest:
    """Inventory the supplied packages without importing or running their code."""
    documents, inventory_ref = inventory(
        project,
        "Kookaburra supplied inputs",
        DOCUMENTS,
        tool_paths(TOOLING),
        ("uv", "docker", "java", "pythonscad", "openscad", "kicad-cli", "foamRun"),
    )
    return ProjectRequest(
        description=DESCRIPTION,
        documents=documents,
        context=context.model_copy(
            update={"instructions": INSTRUCTIONS, "pinned": (inventory_ref,)}
        ),
        budget=BUDGET,
    )


async def main() -> None:
    preflight(
        "codex",
        "Install Codex CLI on PATH and run 'codex login' with your ChatGPT account.",
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
        "--extra mem0', then '.venv/bin/python -m examples.sounding_rocket.kookaburra'; "
        "or use 'uv run examples/sounding_rocket/kookaburra.py'.",
    )
    with Project(
        WORKSPACE,
        sandbox=SANDBOX,
        tools=ToolRegistry(),
        reasoning=CodexReasoning(),
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
            )


if __name__ == "__main__":
    asyncio.run(main())
