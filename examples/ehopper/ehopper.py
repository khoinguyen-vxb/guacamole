# /// script
# requires-python = ">=3.13.3"
# dependencies = [
#   "guacamole-engineering[sounding-rocket]",
#   "freecad-mcp",
# ]
# [tool.uv.sources]
# guacamole-engineering = { path = "../..", editable = true }
# freecad-mcp = { path = "freecad-mcp", editable = true }
# ///
"""Run with: uv run examples/ehopper/ehopper.py

Or: uv sync --extra sounding-rocket
    uv sync --project examples/ehopper/freecad-mcp --locked --no-dev
    .venv/bin/python -m examples.ehopper.ehopper

Edit the configuration below; this script has no command-line arguments.
Install claude CLI and run claude login with your ChatGPT account before running.
Reasoning uses a local claude exec process with GPT-6 Astra; no API key is needed.
uv installs this script's document readers; backend installations are separate.
See https://docs.astral.sh/uv/guides/scripts/ for inline dependency metadata.

The authenticated loopback WebSocket stays available during work and human waits.
Use human_inbox/reply_human/interject/review_disposition commands from README.md.
Ctrl-C stops the host; rerunning resumes this workspace's saved run.
Tool processes have the user's OS permissions; the output directory is not an
OS sandbox. Source checkouts are available for inspection, not assumed installed.
"""

import asyncio
import importlib.util
import json
import os
import shutil
import signal
import sys
from contextlib import suppress
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from zipfile import ZipFile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from guacamole import (
    AgentSpec,
    Budget,
    ContextSpec,
    Model,
    ProducedFile,
    Project,
    ProjectRequest,
    Ref,
    SourceExcerpt,
    ToolRegistry,
    VerificationResult,
)
from guacamole.contracts import FileRecord
from guacamole.providers.claude import ClaudeReasoning
from guacamole.tools.mcp import ToolSession
from guacamole.websocket import WebSocketBridge

# Project configuration. Paths are relative to this file, never the shell's cwd.
ROOT = Path(__file__).resolve().parent
DOCUMENTS = ROOT / "context"
TOOLING = ROOT / "tooling"
WORKSPACE = ROOT / ".guacamole"
SANDBOX = ROOT / "results"
FREECAD_MCP = ROOT / "freecad-mcp"
EXTRA_TOOLS = (FREECAD_MCP,)
RESUME_RUN_ID: str | None = None  # None automatically resumes a single saved run.
CONTROL_PORT = 8766
CONTEXT = ContextSpec(max_input_tokens=12800000, reserved_output_tokens=20000)
BUDGET = Budget(
    max_steps=200000, max_tool_calls=15000, max_seconds=720000, max_agents=24
)

# Optional interpreter overrides, e.g. {"6dof_hopper": Path("/path/to/python")}.
# Otherwise use the repository's .venv/bin/python if present, then this interpreter.
PYTHON_EXECUTABLES: dict[str, Path] = {}

DESCRIPTION = """Project Electronic Hopper: build a self-landing rocket-shaped
hopper using electric motors and counter-rotating coaxial propellers.
Reach approximately 5 m above takeoff level, sustain hover there for 5 minutes,
then land under control. There is no specified propeller diameter limit.
Keep the complete vehicle hardware budget below 500; provisionally use AUD,
with currency and inclusion of shipping/tax still to be confirmed.

Scope: select the motors, coaxial propellers, ESCs and battery; design the
editable vehicle CAD using the supplied FreeCAD MCP; diagnose, fix, improve
and integrate PID control into the supplied tooling/6dof_hopper simulator.
Deliver the propulsion trade study and priced BOM, native FCStd assembly and
STEP/drawings, mass/CG/inertia data, runnable corrected simulator and PID code,
gain configuration, repeatable verification scripts, logs and test procedures.
Prepare scoped PDR/CDR packages for these deliverables. Mass, payload, operating
conditions, landing tolerances and controller hardware remain open requirements.
Use context/brief.md as the current project brief. Ask focused questions where
missing requirements block selection; keep provisional assumptions explicit.
"""

INSTRUCTIONS = """Start by inspecting the supplied inventory, tool documentation,
and the hopper brief. Use list_files, read_text and read_document
before planning; these readers do not require a work plan. Validate a work plan
before writing files or running capability checks and engineering tools. Treat
repository availability, installed dependencies, successful execution and physical
validation separately.
Read binary sources in bounded excerpts with read_document, supplying their Ref
also in the tool action's inputs. Use extract to register the SourceExcerpt.
Cite source pages/slides/cell addresses. Text extraction does not inspect figures;
request missing drawing/image interpretation or other capabilities from the human.
Resolve reader open items only after reviewing the relevant content.

Use write_text for new source/configuration files under the sandbox. execute runs
an argv list without a shell, with cwd inside the sandbox; use command[0]='python'
and repository=<inventory name> to select that backend's interpreter/import root.
Inspect backend setup and entry points first. Copy required data/templates into
the sandbox when a backend assumes cwd-relative inputs. Keep supplied source
repositories and original documents unchanged. Request missing installations
through ask_human; source checkout presence is not proof of a usable backend.
Declare generated files in outputs so they are snapshotted and publishable.
Full stdout/stderr logs are also returned as ProducedFile records.

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
disturbances, saturation recovery and takeoff/300-second hover/landing. Propose
numeric acceptance tolerances for human agreement and record measured errors,
touchdown rates, thrust/current/energy and budget margins. Preserve original
source checkouts; publish a runnable modified copy/patch under results/software.
Stay within propulsion, CAD and simulated PID integration; the pendulum reference
does not add Gazebo, ROS, MPC or machine-learning work to this project.

Verification programs must compute checks from the actual artifact inputs and
print only a VerificationResult JSON object to stdout; use verify_command and
include every tested artifact Ref in tool inputs. Never infer a passing physical
check from process exit status. Use stderr for diagnostic output. Develop and
retain the check program itself as an editable artifact. The Chief selects and
records engineering choices using the evidence, including numerical search results.

AskHuman and PDR/CDR readiness notifications reach the host console and WebSocket
inbox. Wait for explicit human review dispositions. Preserve all corrections,
assumptions, source provenance and evidence limitations in the review packages.
"""

type Offset = Annotated[int, Field(ge=0)]
type First = Annotated[int, Field(ge=1)]
type Count = Annotated[int, Field(ge=1, le=50)]
type Seconds = Annotated[float, Field(gt=0, le=7200)]
type Command = Annotated[tuple[str, ...], Field(min_length=1)]


class Execution(Model):
    returncode: int
    timed_out: bool
    stdout: str
    stderr: str
    files: tuple[ProducedFile, ...]
    missing_outputs: tuple[str, ...]
    stdout_log: ProducedFile
    stderr_log: ProducedFile


class FreeCADExecution(Model):
    reply: str
    files: tuple[ProducedFile, ...]
    missing_outputs: tuple[str, ...]
    log: ProducedFile


async def _freecad_call(
    name: str, arguments: dict[str, object], timeout_s: float
) -> str:
    """Use the supplied MCP server, rather than bypassing its CAD execution tools."""
    candidate = FREECAD_MCP / ".venv/bin/python"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "USER", "LANG", "TMPDIR", "FREECAD_MCP_TOKEN"}
    }
    environment["PYTHONPATH"] = str(FREECAD_MCP / "src")
    server = StdioServerParameters(
        command=str(candidate if candidate.exists() else sys.executable),
        args=[
            "-c",
            "from freecad_mcp.server import main; main()",
            "--only-text-feedback",
        ],
        env=environment,
    )
    with Path(os.devnull).open("w") as errlog:  # noqa: ASYNC230 - /dev/null is local.
        async with (
            stdio_client(server, errlog=errlog) as (reader, writer),
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
    return reply


def tool_paths() -> dict[str, Path]:
    paths = {
        p.stem if p.is_file() else p.name: p.resolve()
        for p in sorted(TOOLING.iterdir())
        if not p.name.startswith(".") and (p.is_dir() or p.suffix == ".py")
    }
    for path in EXTRA_TOOLS:
        if path.exists():
            paths.setdefault(path.name, path.resolve())
    return paths


def _extract_document(
    path: Path, first: int, count: int, sheet: str, offset: int
) -> tuple[str, str, bool]:
    """Text only; page/slide/cell locators survive extraction."""
    stop = first + count - 1
    match path.suffix.lower():
        case ".pdf":
            from pypdf import PdfReader

            with path.open("rb") as stream:
                reader = PdfReader(stream)
                if first > len(reader.pages):
                    raise ValueError("Page is beyond the document")
                stop = min(stop, len(reader.pages))
                text = "\n".join(
                    f"[page {i + 1}]\n{reader.pages[i].extract_text() or '[No extractable text]'}"
                    for i in range(first - 1, stop)
                )
            locator = f"pages {first}-{stop}"
        case ".pptx":
            from pptx import Presentation

            presentation = Presentation(str(path))
            if first > len(presentation.slides):
                raise ValueError("Slide is beyond the presentation")
            stop = min(stop, len(presentation.slides))
            parts = []
            for i in range(first - 1, stop):
                slide = presentation.slides[i]
                parts.append(f"[slide {i + 1}]")
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        parts.append(shape.text)
                    if shape.has_table:
                        parts.extend(
                            " | ".join(cell.text for cell in row.cells)
                            for row in shape.table.rows
                        )
                if slide.has_notes_slide:
                    notes = slide.notes_slide.notes_text_frame
                    if notes is not None:
                        parts.append("[speaker notes]\n" + notes.text)
            text, locator = "\n".join(parts), f"slides {first}-{stop}"
        case ".xlsx":
            from openpyxl import load_workbook

            workbook = load_workbook(path, read_only=True, data_only=False)
            try:
                if not sheet:
                    text, locator = json.dumps(workbook.sheetnames), "worksheet names"
                else:
                    worksheet = workbook[sheet]
                    text = "\n".join(
                        " | ".join(
                            f"{cell.coordinate}={cell.value}"
                            for cell in row
                            if cell.value is not None
                        )
                        for row in worksheet.iter_rows(min_row=first, max_row=stop)
                    )
                    locator = (
                        f"sheet {sheet!r}, rows {first}-{stop} (formulas preserved)"
                    )
            finally:
                workbook.close()
        case ".ork":
            with ZipFile(path) as archive:
                text = archive.read("rocket.ork").decode("utf-8")
            locator = "rocket.ork XML"
        case _:
            raise ValueError(f"No document reader for {path.suffix}")
    return text[offset : offset + 16_000], locator, offset + 16_000 < len(text)


def register_tools(project: Project) -> None:
    paths = tool_paths()
    readable = (
        DOCUMENTS.resolve(),
        TOOLING.resolve(),
        *paths.values(),
        project.sandbox,
    )

    def input_path(path: str) -> Path:
        resolved = (ROOT / path).resolve()
        if not any(
            resolved == root or resolved.is_relative_to(root) for root in readable
        ):
            raise ValueError("Read path is outside supplied inputs and project outputs")
        return resolved

    async def list_files(
        path: str, offset: Offset = 0, limit: Count = 50
    ) -> tuple[str, ...]:
        """List one supplied/output directory; paginate with offset. No recursive scan."""
        return tuple(
            str(p) + ("/" if p.is_dir() else "")
            for p in sorted(input_path(path).iterdir())[offset : offset + limit]
            if not p.name.startswith(".")
        )

    async def read_text(path: str, offset: Offset = 0) -> str:
        """Read up to 16000 UTF-8 characters at a character offset from a supplied/output file."""
        with input_path(path).open(encoding="utf-8") as stream:
            stream.read(offset)
            return stream.read(16_000)

    async def write_text(path: str, text: str) -> ProducedFile:
        """Write an editable source/config file at a sandbox-relative path."""
        destination = project.output_path(Path(path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        return ProducedFile.from_path(destination)

    async def read_document(
        source: Ref,
        first: First = 1,
        count: Count = 1,
        sheet: str = "",
        offset: Offset = 0,
    ) -> SourceExcerpt:
        """Read PDF pages, PPTX slides/notes, XLSX rows (blank sheet lists names), or ORK XML.

        Supply source also in the tool action's inputs, then use extract on this job.
        first is 1-based; offset paginates text within the chosen page/slide/row range.
        Images and diagrams require a separate visual reader; this tool extracts text.
        """
        saved = project.store.resolve(source, current=True)
        file = FileRecord.model_validate_json(json.dumps(saved.data))
        path = await asyncio.to_thread(project.verify_file, file)
        text, locator, truncated = await asyncio.to_thread(
            _extract_document, path, first, count, sheet, offset
        )
        return SourceExcerpt(
            source=source,
            locator=f"{file.name}: {locator}; characters {offset}-{offset + len(text)}",
            text=text,
            metadata={"text_only": True, "more_text": truncated},
            missing_metadata=(
                "Figures and diagrams have not been visually interpreted",
            ),
        )

    async def execute(
        command: Command,
        repository: str = "",
        workdir: str = "work",
        outputs: tuple[str, ...] = (),
        timeout_s: Seconds = 600.0,
    ) -> Execution:
        """Run argv without a shell in a sandbox workdir; outputs are sandbox-relative.

        Use 'python' as argv[0] to select repository's interpreter. Repository adds
        only that source root to PYTHONPATH. Read logs and returncode before publishing.
        Process success is not physical verification. Local processes retain OS permissions.
        """
        repo = paths[repository] if repository else None
        repo_root = repo.parent if repo and repo.is_file() else repo
        cwd = project.output_path(Path(workdir))
        output_paths = tuple(project.output_path(Path(p)) for p in outputs)
        cwd.mkdir(parents=True, exist_ok=True)
        interpreter = PYTHON_EXECUTABLES.get(repository)
        if interpreter is None and repo_root:
            candidate = repo_root / ".venv/bin/python"
            interpreter = candidate if candidate.exists() else None
        argv = (
            (str(interpreter or sys.executable), *command[1:])
            if command[0] == "python"
            else command
        )
        # Pass backend environment settings, without forwarding the reasoning API key.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "PATH",
                "HOME",
                "USER",
                "LANG",
                "LC_ALL",
                "TMPDIR",
                "JAVA_HOME",
                "LD_LIBRARY_PATH",
                "OPENROCKET_HOME",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
            }
        }
        environment.update(
            PYTHONPATH=os.pathsep.join(
                str(p) for p in (repo_root, ROOT.parents[1] / "src") if p
            ),
            MPLBACKEND="Agg",
            MPLCONFIGDIR=str(project.sandbox / ".matplotlib"),
            GUACAMOLE_SANDBOX=str(project.sandbox),
        )
        logs = project.output_path(Path("logs") / uuid4().hex)
        logs.mkdir(parents=True)
        stdout, stderr = logs / "stdout.txt", logs / "stderr.txt"
        timed_out = False
        with stdout.open("wb") as out, stderr.open("wb") as err:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env=environment,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout_s)
            except (TimeoutError, asyncio.CancelledError) as exc:
                # This kills the local process group; external containers need their own cleanup.
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
                if isinstance(exc, asyncio.CancelledError):
                    raise
                timed_out = True
        files = tuple(ProducedFile.from_path(p) for p in output_paths if p.is_file())

        def preview(path: Path) -> str:
            with path.open(encoding="utf-8", errors="replace") as stream:
                return stream.read(8000)

        return Execution(
            returncode=process.returncode if process.returncode is not None else -1,
            timed_out=timed_out,
            stdout=preview(stdout),
            stderr=preview(stderr),
            files=files,
            missing_outputs=tuple(str(p) for p in output_paths if not p.is_file()),
            stdout_log=ProducedFile.from_path(stdout),
            stderr_log=ProducedFile.from_path(stderr),
        )

    async def verify_command(
        command: Command,
        repository: str = "",
        workdir: str = "work",
        timeout_s: Seconds = 600.0,
    ) -> VerificationResult:
        """Run an actual verification program which prints VerificationResult JSON to stdout.

        Include the tested artifact Refs in tool inputs. Stdout must contain only
        the result JSON; diagnostic logging belongs on stderr. Never invent checks.
        """
        result = await execute(command, repository, workdir, timeout_s=timeout_s)
        if result.returncode or result.timed_out:
            return VerificationResult(
                outcome="inconclusive",
                explanation=f"Verification did not complete successfully; inspect {result.stderr_log.path}",
                checks={"process_completed": False},
            )
        return VerificationResult.model_validate_json(
            Path(result.stdout_log.path).read_text()
        )

    async def freecad_status() -> str:
        """Inspect the GUI addon through FreeCAD MCP. Headless CAD needs no GUI addon."""
        return await _freecad_call("get_rpc_status", {}, 30.0)

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
        if not headless:
            arguments["include_screenshot"] = False
        reply = await _freecad_call(
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
        if not any(line.startswith(success) for line in reply.splitlines()):
            raise RuntimeError(f"FreeCAD execution failed; inspect {log}")
        return FreeCADExecution(
            reply=reply[:16_000],
            files=tuple(ProducedFile.from_path(p) for p in output_paths if p.is_file()),
            missing_outputs=tuple(str(p) for p in output_paths if not p.is_file()),
            log=ProducedFile.from_path(log),
        )

    for function in (list_files, read_text, read_document, freecad_status):
        project.tools.register(function, retry_safe=True, requires_plan=False)
    for function in (write_text, execute, verify_command, freecad_run):
        project.tools.register(function)


def configure_run(project: Project, run_id: str | None = None) -> ContextSpec:
    """Apply current host limits while preserving the saved engineering context."""
    if project.reasoning is None:
        raise ValueError("Configure a reasoning provider before setting run limits")
    capacity = project.reasoning.context_capacity_tokens
    if CONTEXT.reserved_output_tokens >= capacity:
        raise ValueError("Reserved output leaves no provider capacity for input")
    limits = {
        "max_input_tokens": min(
            CONTEXT.max_input_tokens, capacity - CONTEXT.reserved_output_tokens
        ),
        "reserved_output_tokens": CONTEXT.reserved_output_tokens,
    }
    context = CONTEXT.model_copy(update=limits)
    print(
        f"Context input budget: {context.max_input_tokens} "
        f"(configured {CONTEXT.max_input_tokens}; provider capacity {capacity}; "
        f"reserved output {context.reserved_output_tokens})",
        flush=True,
    )
    if run_id is not None:
        store = project.store
        run = store.get("run", run_id).data
        saved_request = ProjectRequest.model_validate_json(json.dumps(run["request"]))
        request = saved_request.model_copy(
            update={
                "context": saved_request.context.model_copy(update=limits),
                "budget": BUDGET,
            }
        )
        chief = store.model("agent", str(run["chief_id"]), AgentSpec)
        updated_chief = chief.model_copy(
            update={
                "context": chief.context.model_copy(update=limits),
                "budget": BUDGET,
            }
        )
        with store.atomic():
            if request != saved_request:
                store.put(
                    "run",
                    run_id,
                    run | {"request": request.model_dump(mode="json")},
                    actor="script",
                    event="run.budgets_updated",
                )
            if updated_chief != chief:
                store.put(
                    "agent",
                    chief.id,
                    updated_chief,
                    actor="script",
                    event="agent.budgets_updated",
                )
    return context


def project_request(project: Project, context: ContextSpec) -> ProjectRequest:
    """Inventory the supplied packages without importing or running their code."""
    documents = sorted(
        p for p in DOCUMENTS.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    lines = ["# Electronic Hopper supplied inputs", "", "## Tool source paths"]
    for name, path in tool_paths().items():
        lines.append(f"- {name}: {path}")
        if path.is_file():
            documents.append(path)
        else:
            documents.extend(sorted(path.glob("README*")))
            documents.extend(sorted(path.glob("pyproject.toml")))
            documents.extend(sorted((path / "docs").glob("*.md")))
            if name == "6dof_hopper":
                documents.extend(sorted((path / "PyThrust").glob("README*")))
                documents.extend(sorted((path / "PyThrust").glob("pyproject.toml")))
            entry_points = sorted(p.name for p in path.glob("*.py"))
            lines.append(
                f"  Top-level Python files: {', '.join(entry_points) or '(inspect subdirectories)'}"
            )
    lines.extend(("", "## Reference documents"))
    lines.extend(f"- {p.name}: {p.stat().st_size} bytes; {p}" for p in documents)
    lines.extend(("", "## Executables visible to this host (presence only)"))
    for name in (
        "uv",
        "claude",
        "freecad",
        "freecadcmd",
        "FreeCADCmd",
        "freecad.cmd",
    ):
        lines.append(f"- {name}: {shutil.which(name) or 'not on PATH'}")
    inventory = project.output_path(Path("context/inventory.md"))
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text("\n".join(lines) + "\n", encoding="utf-8")
    inventory_ref = project.ingest(inventory, source_id="inventory")
    return ProjectRequest(
        description=DESCRIPTION,
        documents=tuple(documents),
        context=context.model_copy(
            update={"instructions": INSTRUCTIONS, "pinned": (inventory_ref,)}
        ),
        budget=BUDGET,
    )


async def notifications(project: Project) -> None:
    cursor = 0
    while True:
        for event in project.events(after=cursor):
            cursor = event.sequence
            if event.type == "human.requested":
                print(
                    f"\nHUMAN INPUT [{event.entity_id}] {event.details['question']}",
                    flush=True,
                )
            elif event.type == "review.ready":
                print(
                    f"\nReview package ready: {project.sandbox / 'reviews' / event.entity_id}",
                    flush=True,
                )
        await asyncio.sleep(0.5)


async def main() -> None:
    if shutil.which("claude") is None:
        raise SystemExit(
            "Install claude CLI on PATH and run 'claude login' with your ChatGPT account."
        )
    missing = [
        name
        for name in ("websockets", "pypdf", "openpyxl", "pptx")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        raise SystemExit(
            f"Missing example dependencies: {', '.join(missing)}. "
            "Run 'uv sync --extra sounding-rocket', then "
            "'.venv/bin/python -m examples.ehopper.ehopper'; "
            "or use 'uv run examples/ehopper/ehopper.py'."
        )
    with Project(
        WORKSPACE,
        sandbox=SANDBOX,
        tools=ToolRegistry(),
        reasoning=ClaudeReasoning(web_search=True),
    ) as project:
        register_tools(project)
        runs = project.store.list("run")
        if RESUME_RUN_ID is None and len(runs) > 1:
            raise ValueError("Multiple saved runs: set RESUME_RUN_ID in this script")
        run_id = RESUME_RUN_ID or (runs[0].ref.id if runs else None)
        context = configure_run(project, run_id)
        request = None if run_id else project_request(project, context)
        bridge = WebSocketBridge(ToolSession(project))
        monitor = asyncio.create_task(notifications(project))
        try:
            async with bridge.serve(port=CONTROL_PORT):
                print(f"Human control: ws://127.0.0.1:{CONTROL_PORT}", flush=True)
                print(f"Authorization: Bearer {bridge.token}", flush=True)
                print(
                    f"Outputs: {project.sandbox}\nSend corrections with interject at any time.",
                    flush=True,
                )
                while True:
                    result = await project.run(request, resume=run_id)
                    request, run_id = None, result.run_id
                    print(result.model_dump_json(indent=2), flush=True)
                    project.output_path(Path("result.json")).write_text(
                        result.model_dump_json(indent=2), encoding="utf-8"
                    )
                    project.export(project.output_path(Path("timeline.jsonl")))
                    if result.status not in {"awaiting_human", "awaiting_review"}:
                        break
                    # Continue once the host records a reply, correction, or review disposition.
                    while any(
                        project.activity.get(entry.message.request_id or "").required
                        for entry in project.human.inbox(run_id=run_id)
                    ):
                        await asyncio.sleep(0.5)
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
            await project.drain()
            project.export(project.output_path(Path("timeline.jsonl")))


if __name__ == "__main__":
    asyncio.run(main())
