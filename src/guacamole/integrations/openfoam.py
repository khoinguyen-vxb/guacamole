"""OpenFOAM for workers: tutorial cases, dictionary edits, runs and their logs.

OpenFOAM is a set of command-line applications with no session to hold, so this
drives them directly, on the host or in a container (tools/containers.py). Every
command sources the installation's etc/bashrc first, so both run the same way and
no other host environment reaches OpenFOAM. Cases live in the sandbox and start
from the installation's own tutorials, which are correct for its fork and version
by construction. Dictionaries are read and edited through OpenFOAM's own
foamDictionary, so every edit is parsed the way the installed version parses it.

Solver logs are parsed for residuals and checkMesh logs for mesh quality. A
converged run is numerical convergence, never physical validation.
"""

import asyncio
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from ..contracts import Model, ProducedFile
from ..tools.containers import Container, runner
from ..tools.workspace import Count, Offset

if TYPE_CHECKING:
    from ..project import Project

APPLICATION = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]*")
TEXT = 16_000
TAIL = 60
# Run "$@" in the installation's environment; $1 is its bashrc.
SOURCED = 'source "$1" >/dev/null 2>&1; shift; exec "$@"'
DISCOVER = r"""source "$1" >/dev/null 2>&1
printf 'WM_PROJECT=%s\nWM_PROJECT_VERSION=%s\nFOAM_TUTORIALS=%s\nMPIRUN=%s\n' \
    "$WM_PROJECT" "$WM_PROJECT_VERSION" "$FOAM_TUTORIALS" "$(command -v mpirun)"
for d in "$FOAM_USER_APPBIN" "$FOAM_SITE_APPBIN" "$FOAM_APPBIN"; do
    [ -d "$d" ] && for f in "$d"/*; do [ -f "$f" ] && [ -x "$f" ] && echo "APP=${f##*/}"; done
done
[ -d "$FOAM_TUTORIALS" ] && find "$FOAM_TUTORIALS" -path '*/system/controlDict' | sed 's/^/TUTORIAL=/'
true
"""

type RunSeconds = Annotated[float, Field(gt=0, le=86_400)]
type Processors = Annotated[int, Field(ge=1, le=1024)]
type Rows = Annotated[int, Field(ge=1, le=200)]
type Tolerance = Annotated[float, Field(gt=0, lt=1)]

SOLVE = re.compile(
    r"Solving for (\w+), Initial residual = ([^,\s]+), Final residual = ([^,\s]+),"
)
TIME = re.compile(r"^Time = (\S+?)s?$")
CONTINUITY = re.compile(r"continuity errors : sum local = ([^,\s]+)")


class OpenFOAMInfo(Model):
    project: str
    version: str
    fork: Literal["foundation", "esi"]
    runtime: str  # "host", or the container image
    tutorials: str
    applications: tuple[str, ...]


class OpenFOAMCase(Model):
    case: str
    files: tuple[str, ...]  # Case-relative


class FieldResiduals(Model):
    """A field's initial residual at its first solve of each time step."""

    field: str
    first: float | None
    last: float | None  # None when the last residual was not finite
    minimum: float | None
    maximum: float | None
    steps: int
    nonfinite: int


class Residuals(Model):
    verdict: Literal["converged", "not_converged", "diverged"]
    tolerance: float
    fields: tuple[FieldResiduals, ...]
    steps: int
    last_time: str
    end_reached: bool
    continuity: float | None  # The last time step's sum local continuity error


class MeshCheck(Model):
    ok: bool
    failed_checks: int
    cells: int | None
    max_non_orthogonality: float | None
    max_skewness: float | None


class OpenFOAMRun(Model):
    application: str
    command: tuple[str, ...]  # As the runtime ran it, after sourcing the bashrc
    runtime: str  # "host", or the container image that produced the results
    returncode: int
    timed_out: bool
    fatal_error: str
    tail: str
    log: ProducedFile
    residuals: Residuals | None  # Solver logs
    mesh: MeshCheck | None  # checkMesh logs
    times: tuple[str, ...]


class OpenFOAMTable(Model):
    file: ProducedFile
    header: str
    columns: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]  # The last rows, oldest first
    total_rows: int
    nonfinite_rows: int


@dataclass(frozen=True)
class Installation:
    project: str
    version: str
    tutorials: str  # As the runtime sees it
    mpirun: bool
    applications: frozenset[str]
    cases: tuple[str, ...]  # Tutorial-relative


def discover(output: str) -> Installation:
    """Read DISCOVER's output."""
    values: dict[str, str] = {}
    applications, tutorials = set(), []
    for line in output.splitlines():
        key, _, value = line.partition("=")
        if key == "APP":
            applications.add(value)
        elif key == "TUTORIAL":
            tutorials.append(value)
        elif key:
            values[key] = value
    if not values.get("WM_PROJECT_VERSION"):
        raise RuntimeError(
            "No OpenFOAM installation: sourcing the bashrc set no WM_PROJECT_VERSION"
        )
    root, suffix = values.get("FOAM_TUTORIALS", "").rstrip("/"), "/system/controlDict"
    return Installation(
        project=values.get("WM_PROJECT", ""),
        version=values["WM_PROJECT_VERSION"],
        tutorials=root,
        mpirun=bool(values.get("MPIRUN")),
        applications=frozenset(applications),
        cases=tuple(
            sorted(
                t[len(root) + 1 : -len(suffix)]
                for t in tutorials
                if t.startswith(root + "/") and t.endswith(suffix)
            )
        ),
    )


def _float(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return math.nan


def _fatal(log: str) -> str:
    """The FOAM FATAL (IO) ERROR block, through OpenFOAM's exiting/aborting line."""
    start = log.find("FOAM FATAL")
    if start < 0:
        return ""
    block = log[log.rfind("\n", 0, start) + 1 :]
    end = re.search(r"\nFOAM (exiting|aborting).*", block)
    return (block[: end.end()] if end else block).strip()[:4000]


def parse_residuals(log: str, tolerance: float) -> Residuals | None:
    """Initial residuals per field and time step, and a steady-state verdict."""
    history: dict[str, list[float]] = {}
    solved: set[str] = set()
    steps, time, continuity = 0, "", None
    for line in log.splitlines():
        line = line.strip()
        if match := TIME.match(line):
            steps, time, solved = steps + 1, match[1], set()
        elif match := SOLVE.search(line):
            if match[1] not in solved:  # PIMPLE solves a field several times a step.
                solved.add(match[1])
                history.setdefault(match[1], []).append(_float(match[2]))
        elif match := CONTINUITY.search(line):
            value = _float(match[1])
            continuity = value if math.isfinite(value) else None
    if not history:
        return None
    fields = []
    for field, values in sorted(history.items()):
        finite = [v for v in values if math.isfinite(v)]
        fields.append(
            FieldResiduals(
                field=field,
                first=finite[0] if finite else None,
                last=values[-1] if math.isfinite(values[-1]) else None,
                minimum=min(finite) if finite else None,
                maximum=max(finite) if finite else None,
                steps=len(values),
                nonfinite=len(values) - len(finite),
            )
        )
    if any(f.nonfinite for f in fields):
        verdict = "diverged"
    elif all(f.last is not None and f.last <= tolerance for f in fields):
        verdict = "converged"
    else:
        verdict = "not_converged"
    return Residuals(
        verdict=verdict,
        tolerance=tolerance,
        fields=tuple(fields),
        steps=steps,
        last_time=time,
        end_reached=any(line.strip() == "End" for line in log.splitlines()[-50:]),
        continuity=continuity,
    )


def parse_mesh(log: str) -> MeshCheck | None:
    failed = re.search(r"Failed (\d+) mesh checks", log)
    if failed is None and "Mesh OK." not in log:
        return None

    def number(pattern: str) -> float | None:
        match = re.search(pattern, log)
        return _float(match[1]) if match and math.isfinite(_float(match[1])) else None

    cells = re.search(r"^\s*cells:\s+(\d+)", log, re.MULTILINE)
    return MeshCheck(
        ok=failed is None,
        failed_checks=int(failed[1]) if failed else 0,
        cells=int(cells[1]) if cells else None,
        max_non_orthogonality=number(r"non-orthogonality Max:\s*([0-9.eE+-]+)"),
        max_skewness=number(r"Max skewness = ([0-9.eE+-]+)"),
    )


def parse_table(text: str, last: int) -> tuple[str, tuple[str, ...], list, int, int]:
    """A postProcessing .dat table: header, columns, last rows, totals."""
    header, rows, nonfinite = "", [], 0
    for line in text.splitlines():
        if line.startswith("#"):
            if not rows:
                header = line.lstrip("#").strip()
            continue
        values = line.replace("(", " ").replace(")", " ").split()
        if not values:
            continue
        row = tuple(_float(v) for v in values)
        if all(math.isfinite(v) for v in row):
            rows.append(row)
        else:
            nonfinite += 1
    names = header.split()
    width = len(rows[-1]) if rows else 0
    columns = tuple(
        names if len(names) == width else (f"column_{i}" for i in range(width))
    )
    return header, columns, rows[-last:], len(rows), nonfinite


def _times(case: Path) -> tuple[str, ...]:
    times = []
    for path in case.iterdir():
        if path.is_dir() and math.isfinite(value := _float(path.name)):
            times.append((value, path.name))
    return tuple(name for _, name in sorted(times))


def register_openfoam_tools(
    project: "Project", bashrc: Path, container: Container | None = None
) -> None:
    """Register the OpenFOAM tools for the installation bashrc sets up.

    bashrc is the installation's etc/bashrc: a host path, or with container a path
    inside its image, such as /opt/openfoam12/etc/bashrc.
    """
    runs = runner(project, container)
    source = str(bashrc.resolve()) if container is None else bashrc.as_posix()
    install = discover(
        runs.check(["bash", "-c", DISCOVER, "bash", source], cwd=project.sandbox)
    )
    # ESI versions are named vYYMM; the Foundation's are plain numbers.
    fork: Literal["foundation", "esi"] = (
        "esi" if install.version.startswith("v") else "foundation"
    )

    def sourced(*command: str) -> list[str]:
        return ["bash", "-c", SOURCED, "bash", source, *command]

    def case_dir(case: str, *, existing: bool = True) -> Path:
        path = project.output_path(Path(case))
        if path == project.sandbox:
            raise ValueError("A case is a sandbox subdirectory, not the sandbox itself")
        if existing and not (path / "system/controlDict").is_file():
            raise ValueError(
                f"{case} is not an OpenFOAM case: it has no system/controlDict"
            )
        return path

    def inside(case: Path, file: str) -> Path:
        path = (case / file).resolve()
        if not path.is_relative_to(case):
            raise ValueError(f"{file} is outside the case")
        return path

    def installed(name: str) -> str:
        if not APPLICATION.fullmatch(name) or name not in install.applications:
            raise ValueError(
                f"{name} is not an OpenFOAM application; openfoam_info lists them, and "
                "case scripts run as ./Allrun"
            )
        return name

    async def dictionary(case: str, file: str, *options: str) -> tuple[Path, str]:
        path = case_dir(case)
        target = inside(path, file)
        if not target.is_file():
            raise ValueError(f"No dictionary {file} in {case}")
        code, output = await runs.capture(
            sourced(installed("foamDictionary"), runs.path(target), *options),
            cwd=path,
            timeout_s=120.0,
        )
        if code:
            raise RuntimeError(f"foamDictionary failed:\n{output[-4000:]}")
        return target, output

    async def openfoam_info() -> OpenFOAMInfo:
        """The OpenFOAM installation: fork, version, runtime, tutorials, applications.

        Foundation versions (e.g. 12) run solvers as foamRun -solver <module>; ESI
        versions (e.g. v2406) name solvers directly (simpleFoam, pimpleFoam).
        """
        return OpenFOAMInfo(
            project=install.project,
            version=install.version,
            fork=fork,
            runtime=runs.runtime,
            tutorials=install.tutorials,
            applications=tuple(sorted(install.applications)),
        )

    async def openfoam_tutorials(
        filter: str = "", offset: Offset = 0, limit: Count = 50
    ) -> tuple[str, ...]:
        """List the installation's tutorial cases, tutorial-relative; filter is a substring.

        Start a case from the closest tutorial with openfoam_copy_tutorial.
        """
        matching = [c for c in install.cases if filter.lower() in c.lower()]
        return tuple(matching[offset : offset + limit])

    async def openfoam_copy_tutorial(
        tutorial: str, case: str, replace: bool = False
    ) -> OpenFOAMCase:
        """Copy a tutorial case into a sandbox-relative case directory.

        replace deletes an existing case there first. Then change it with
        openfoam_set (or write_text for whole files, such as a new blockMeshDict).
        """
        if tutorial not in install.cases:
            raise ValueError(
                f"{tutorial} is not a tutorial case; openfoam_tutorials lists them"
            )
        destination = case_dir(case, existing=False)
        if destination.exists():
            if not replace:
                raise ValueError(f"{case} exists; pass replace to start it over")
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        code, output = await runs.capture(
            ["cp", "-R", f"{install.tutorials}/{tutorial}", runs.path(destination)],
            cwd=project.sandbox,
            timeout_s=600.0,
        )
        if code:
            raise RuntimeError(f"Copying {tutorial} failed:\n{output[-2000:]}")
        return OpenFOAMCase(
            case=str(destination),
            files=tuple(
                sorted(
                    str(p.relative_to(destination))
                    for p in destination.rglob("*")
                    if p.is_file()
                )
            ),
        )

    async def openfoam_read(
        case: str, file: str, entry: str = "", keywords: bool = False
    ) -> str:
        """Read a case dictionary as OpenFOAM parses it, through foamDictionary.

        file is case-relative (system/fvSolution, 0/U). entry selects one entry,
        scoped with '/' (boundaryField/inlet); keywords lists its sub-keywords
        instead of its value. Blank entry reads the whole dictionary.
        """
        options = [
            *(("-entry", entry) if entry else ()),
            *(("-keywords",) if keywords else ()),
        ]
        _, output = await dictionary(case, file, *options)
        return output[:TEXT]

    async def openfoam_set(
        case: str,
        file: str,
        changes: dict[str, str] | None = None,
        remove: tuple[str, ...] = (),
    ) -> ProducedFile:
        """Set or remove dictionary entries through foamDictionary, in order.

        changes maps an entry, scoped with '/', to its value in OpenFOAM syntax:
        {"boundaryField/inlet/value": "uniform (10 0 0)", "endTime": "2000"}.
        A set adds a missing entry. Returns the edited file.
        """
        if not changes and not remove:
            raise ValueError("Give changes or entries to remove")
        target = Path()
        for entry, value in (changes or {}).items():
            target, _ = await dictionary(case, file, "-entry", entry, "-set", value)
        for entry in remove:
            target, _ = await dictionary(case, file, "-entry", entry, "-remove")
        return ProducedFile.from_path(target)

    async def openfoam_residuals(
        case: str, log: str, tolerance: Tolerance = 1e-4
    ) -> Residuals | None:
        """Parse an existing solver log in the case, such as one an Allrun script wrote.

        None when the log holds no residuals. The verdict is for steady-state runs:
        converged when every field's last initial residual is at most tolerance.
        """
        path = inside(case_dir(case), log)
        text = await asyncio.to_thread(
            path.read_text, encoding="utf-8", errors="replace"
        )
        return parse_residuals(text, tolerance)

    async def openfoam_table(case: str, file: str, last: Rows = 20) -> OpenFOAMTable:
        """Read a function object's postProcessing table (forces, coefficients, probes).

        file is case-relative, e.g. postProcessing/forceCoeffs/0/forceCoeffs.dat.
        Vector components in parentheses become separate columns. Units are the
        function object's own: read its header and the case's dictionaries.
        """
        path = inside(case_dir(case), file)
        if not path.is_file():
            raise ValueError(f"No table {file} in {case}")
        text = await asyncio.to_thread(
            path.read_text, encoding="utf-8", errors="replace"
        )
        header, columns, rows, total, nonfinite = parse_table(text, last)
        return OpenFOAMTable(
            file=ProducedFile.from_path(path),
            header=header,
            columns=columns,
            rows=tuple(rows),
            total_rows=total,
            nonfinite_rows=nonfinite,
        )

    async def openfoam_run(
        case: str,
        application: str,
        args: tuple[str, ...] = (),
        processors: Processors = 1,
        tolerance: Tolerance = 1e-4,
        timeout_s: RunSeconds = 3600.0,
    ) -> OpenFOAMRun:
        """Run an OpenFOAM application or a case script in a sandbox case.

        application is an installed application (blockMesh, snappyHexMesh,
        checkMesh, foamRun, simpleFoam, decomposePar, postProcess...) or a script
        in the case such as ./Allrun. processors > 1 runs it with mpirun -parallel
        (run decomposePar first). Output goes to log.<application> in the case.
        A failed run returns its returncode and FOAM FATAL ERROR text, not an
        error. Solver logs return residuals; checkMesh logs return mesh quality.
        Convergence is numerical, not physical validation.
        """
        path = case_dir(case)
        if application.startswith("./"):
            script = inside(path, application)
            if not script.is_file() or processors > 1:
                raise ValueError(f"{application} is not a case script to run serially")
            command, name = ["bash", runs.path(script)], script.name
        else:
            command, name = [installed(application)], application
            if processors > 1:
                if not install.mpirun:
                    raise ValueError(
                        "Parallel runs need mpirun in the OpenFOAM environment"
                    )
                command = ["mpirun", "-np", str(processors), *command, "-parallel"]
        for arg in args:
            if arg == "-case":
                raise ValueError("Runs use their case directory; do not pass -case")
            if arg.startswith("/") or ".." in Path(arg).parts:
                resolved = (path / arg).resolve()
                if not resolved.is_relative_to(project.sandbox):
                    raise ValueError(f"{arg} is outside the sandbox")
                # Absolute paths are translated; relative ones mean the same in both.
                arg = runs.path(resolved) if arg.startswith("/") else arg
            command.append(arg)
        log = path / f"log.{name}"
        returncode, timed_out = await runs.run(
            sourced(*command), cwd=path, log=log, timeout_s=timeout_s
        )
        text = await asyncio.to_thread(
            log.read_text, encoding="utf-8", errors="replace"
        )
        return OpenFOAMRun(
            application=name,
            command=tuple(command),
            runtime=runs.runtime,
            returncode=returncode,
            timed_out=timed_out,
            fatal_error=_fatal(text),
            tail="\n".join(text.splitlines()[-TAIL:]),
            log=ProducedFile.from_path(log),
            residuals=parse_residuals(text, tolerance),
            mesh=parse_mesh(text),
            times=_times(path),
        )

    # OpenFOAM output and case paths hold no secrets; the host environment is not passed.
    for function in (
        openfoam_info,
        openfoam_tutorials,
        openfoam_read,
        openfoam_residuals,
        openfoam_table,
    ):
        project.tools.register(
            function, retry_safe=True, requires_plan=False, show_errors=True
        )
    for function in (openfoam_copy_tutorial, openfoam_set, openfoam_run):
        project.tools.register(function, show_errors=True)
