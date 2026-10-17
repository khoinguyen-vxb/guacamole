"""Generic tools for host scripts: read supplied inputs, write and run in the sandbox.

Register them with register_workspace_tools. Readers need no plan; writing and
running do. Document readers import pypdf, pypdfium2, python-pptx and openpyxl on first use.
Tool processes keep the user's OS permissions; the sandbox is not an OS sandbox.
"""

import asyncio
import json
import os
import shutil
import signal
import sys
from collections.abc import Iterable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4
from zipfile import ZipFile

from pydantic import Field, ValidationError

from ..contracts import (
    FileRecord,
    Model,
    ProducedFile,
    Ref,
    SourceExcerpt,
    VerificationResult,
)

if TYPE_CHECKING:
    from ..project import Project

type Offset = Annotated[int, Field(ge=0)]
type First = Annotated[int, Field(ge=1)]
type Count = Annotated[int, Field(ge=1, le=50)]
type Seconds = Annotated[float, Field(gt=0, le=7200)]
type Command = Annotated[tuple[str, ...], Field(min_length=1)]

# The directory holding the guacamole package, so tool scripts can import it.
SOURCE = Path(__file__).resolve().parents[2]
# Packaged agent skills (e.g. engineering-documentation); always readable so
# any agent can read_text/list_files a skill's SKILL.md and its assets.
SKILLS = SOURCE / "guacamole" / "agents" / "skills"
# Passed to tool processes; the reasoning API key never is.
ENVIRONMENT = (
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
)


class Execution(Model):
    returncode: int
    timed_out: bool
    stdout: str
    stderr: str
    files: tuple[ProducedFile, ...]
    missing_outputs: tuple[str, ...]
    stdout_log: ProducedFile
    stderr_log: ProducedFile


def tool_paths(tooling: Path, *extra: Path) -> dict[str, Path]:
    """Source checkouts and scripts under tooling, plus extra ones that exist."""
    paths = {
        p.stem if p.is_file() else p.name: p.resolve()
        for p in (sorted(tooling.iterdir()) if tooling.is_dir() else ())
        if not p.name.startswith(".") and (p.is_dir() or p.suffix == ".py")
    }
    for path in extra:
        if path.exists():
            paths.setdefault(path.name, path.resolve())
    return paths


def inventory(
    project: "Project",
    title: str,
    documents: Path,
    tools: Mapping[str, Path],
    executables: Iterable[str],
    extra: Iterable[Path] = (),
    tool_docs: Iterable[str] = ("README*",),
) -> tuple[tuple[Path, ...], Ref]:
    """The supplied documents and an ingested inventory of inputs, for pinning.

    Documents are every file under documents, then extra, then each tool
    checkout's files matching tool_docs. The inventory lists the tools and their
    top-level files without importing or running their code, every document, and
    which executables are on PATH.
    """
    files = sorted(
        p
        for p in (documents.rglob("*") if documents.is_dir() else ())
        if p.is_file() and not p.name.startswith(".")
    )
    files.extend(extra)
    lines = [f"# {title}", "", "## Tool source paths"]
    for name, path in tools.items():
        lines.append(f"- {name}: {path}")
        if path.is_file():
            files.append(path)
            continue
        for pattern in tool_docs:
            files.extend(sorted(path.glob(pattern)))
        entry_points = sorted(p.name for p in path.glob("*.py"))
        lines.append(
            "  Top-level Python files: "
            + (", ".join(entry_points) or "(inspect subdirectories)")
        )
    lines.extend(("", "## Reference documents"))
    lines.extend(f"- {p.name}: {p.stat().st_size} bytes; {p}" for p in files)
    lines.extend(("", "## Executables visible to this host (presence only)"))
    lines.extend(f"- {n}: {shutil.which(n) or 'not on PATH'}" for n in executables)
    path = project.output_path(Path("context/inventory.md"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tuple(files), project.ingest(path, source_id="inventory")


def extract_document(
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
                    f"[page {i + 1}]\n"
                    + (reader.pages[i].extract_text() or "[No extractable text]")
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


def render_pdf(path: Path, first: int, count: int, out: Path) -> tuple[Path, ...]:
    """PDF pages as JPEGs at most 2000 px a side, the multi-image limit models take."""
    import pypdfium2

    document = pypdfium2.PdfDocument(path)
    try:
        if first > len(document):
            raise ValueError("Page is beyond the document")
        out.mkdir(parents=True, exist_ok=True)
        pages = []
        for i in range(first - 1, min(first + count - 1, len(document))):
            page = document[i]
            # Up to 200 dpi, so small pages are not blown up past legibility.
            scale = min(2000 / max(page.get_size()), 200 / 72)
            target = out / f"{path.stem}-page-{i + 1}.jpg"
            # JPEG keeps a dense 2000 px page well under the attachment size limit.
            page.render(scale=scale).to_pil().save(target, quality=90)
            pages.append(target)
        return tuple(pages)
    finally:
        document.close()


def register_workspace_tools(
    project: "Project",
    root: Path,
    inputs: Iterable[Path],
    tools: Mapping[str, Path] = {},
    python: Mapping[str, Path] = {},
) -> None:
    """Register the readers, write_text, execute and verify_command.

    root is the example directory: relative read paths resolve against it, then
    the sandbox. inputs are the supplied directories agents may read, as well as
    the tools, which execute may run by name. python overrides a tool's
    interpreter; otherwise its .venv/bin/python is used, then this interpreter.
    """
    root = root.resolve()
    readable = (
        *(p.resolve() for p in inputs),
        *tools.values(),
        project.sandbox,
        SKILLS,
    )

    def allowed(path: Path) -> bool:
        return any(path == r or path.is_relative_to(r) for r in readable)

    def input_path(path: str) -> Path:
        for base in (root, project.sandbox):
            resolved = (base / path).resolve()
            if allowed(resolved):
                return resolved
        raise ValueError("Read path is outside supplied inputs and project outputs")

    async def list_files(
        path: str = "", offset: Offset = 0, limit: Count = 50
    ) -> tuple[str, ...]:
        """List a supplied/output directory; empty path lists allowed roots. Paginate with offset."""
        entries = (
            (p for p in root.iterdir() if p.resolve() in readable)
            if (root / path).resolve() == root
            else input_path(path).iterdir()
        )
        visible = sorted(p for p in entries if not p.name.startswith("."))
        return tuple(
            str(p) + ("/" if p.is_dir() else "")
            for p in visible[offset : offset + limit]
        )

    async def read_text(path: str, offset: Offset = 0) -> str:
        """Read up to 16000 UTF-8 characters; paths can be absolute, example-relative or output-relative."""
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
        This tool extracts text; render_pages shows PDF figures as images.
        """
        saved = project.store.resolve(source, current=True)
        file = FileRecord.model_validate_json(json.dumps(saved.data))
        path = await asyncio.to_thread(project.verify_file, file)
        text, locator, truncated = await asyncio.to_thread(
            extract_document, path, first, count, sheet, offset
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

    async def render_pages(
        source: Ref, first: First = 1, count: Annotated[int, Field(ge=1, le=20)] = 1
    ) -> tuple[ProducedFile, ...]:
        """Render PDF pages to images; read the returned job files to see them.

        Supply source also in the tool action's inputs. first is 1-based. Use it for
        figures, drawings and photos text extraction cannot show; cite page numbers.
        """
        saved = project.store.resolve(source, current=True)
        file = FileRecord.model_validate_json(json.dumps(saved.data))
        path = await asyncio.to_thread(project.verify_file, file)
        if path.suffix.lower() != ".pdf":
            raise ValueError("render_pages reads PDF sources only")
        pages = await asyncio.to_thread(
            render_pdf, path, first, count, project.output_path(Path("renders"))
        )
        return tuple(ProducedFile.from_path(p) for p in pages)

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
        repo = tools[repository] if repository else None
        repo_root = repo.parent if repo and repo.is_file() else repo
        cwd = project.output_path(Path(workdir))
        output_paths = tuple(project.output_path(Path(p)) for p in outputs)
        cwd.mkdir(parents=True, exist_ok=True)
        interpreter = python.get(repository)
        if interpreter is None and repo_root:
            candidate = repo_root / ".venv/bin/python"
            interpreter = candidate if candidate.exists() else None
        argv = (
            (str(interpreter or sys.executable), *command[1:])
            if command[0] == "python"
            else command
        )
        environment = {k: v for k, v in os.environ.items() if k in ENVIRONMENT}
        environment.update(
            PYTHONPATH=os.pathsep.join(str(p) for p in (repo_root, SOURCE) if p),
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

        def preview(path: Path) -> str:
            with path.open(encoding="utf-8", errors="replace") as stream:
                return stream.read(8000)

        return Execution(
            returncode=process.returncode if process.returncode is not None else -1,
            timed_out=timed_out,
            stdout=preview(stdout),
            stderr=preview(stderr),
            files=tuple(ProducedFile.from_path(p) for p in output_paths if p.is_file()),
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
        outcome "passed" requires every performed check to be true; set a check the
        program cannot perform to null, and it is listed as not performed.
        """
        result = await execute(command, repository, workdir, timeout_s=timeout_s)
        if result.returncode or result.timed_out:
            return VerificationResult(
                outcome="inconclusive",
                explanation="Verification did not complete successfully; inspect "
                + result.stderr_log.path,
                checks={"process_completed": False},
            )
        try:
            return VerificationResult.model_validate_json(
                Path(result.stdout_log.path).read_text()
            )
        except ValidationError as exc:
            # Raised, this was hidden as "exception text omitted", so agents could
            # not fix their checker; the schema message is ours and safe to show.
            return VerificationResult(
                outcome="inconclusive",
                explanation=f"Checker stdout is not a valid VerificationResult: {exc}"[
                    :2000
                ],
                checks={"result_schema_valid": False},
            )

    # Local file and document errors hold no secrets; agents fix calls with them.
    for function in (list_files, read_text, read_document, render_pages):
        project.tools.register(
            function, retry_safe=True, requires_plan=False, show_errors=True
        )
    for function in (write_text, execute, verify_command):
        project.tools.register(function, show_errors=True)
