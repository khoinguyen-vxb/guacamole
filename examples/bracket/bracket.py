"""Wall-mounted L-brackets: Milestone B's prompt-to-review-package benchmark.

Run with: uv sync
          .venv/bin/python -m examples.bracket.bracket

Every brief in briefs/ runs as its own project under runs/<timestamp>/. A brief
passes when its run reaches a ready PDR review: native CAD, STEP, drawing and BOM
published, checked and delivered, with no open review issues. Blocking questions
get one scripted reply each; final acceptance stays with a human.

Edit the configuration below; this script has no command-line arguments.
Install FreeCAD (freecadcmd, or the snap's freecad.cmd) and the Codex CLI, and run
codex login before running. Model calls count against that account's usage.
"""

import asyncio
import csv
import json
import math
import os
import shutil
import signal
import time
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

from pydantic import Field

from guacamole import (
    Budget,
    ContextSpec,
    Model,
    ProducedFile,
    Project,
    ProjectRequest,
    Quantity,
    Requirement,
    ToolRegistry,
    VerificationResult,
)
from guacamole.contracts import ArtifactRecord
from guacamole.providers.codex import CodexReasoning
from guacamole.tools.registry import encode

# Configuration. Paths are relative to this file. FreeCAD must see the runs
# directory: snap and Flatpak builds can read $HOME but not /tmp.
ROOT = Path(__file__).resolve().parent
BRIEFS = ROOT / "briefs"
RUNS = ROOT / "runs"
BUDGET = Budget(
    max_steps=300,
    max_tool_calls=120,
    max_seconds=5400,
    max_agents=4,
    max_run_input_tokens=6_000_000,
)
CONTEXT = ContextSpec(max_input_tokens=400_000, reserved_output_tokens=20_000)
MAX_CONCURRENT_CALLS = 2
FREECAD_TIMEOUT_S = 300
SCRIPTED_REPLY = (
    "Benchmark reply: no further input is available. Proceed on explicit "
    "assumptions and record each one as an open item."
)


def reasoning() -> CodexReasoning:
    """The benchmarked model; ClaudeReasoning(web_search=False) also fits."""
    return CodexReasoning(web_search=False)


FREECAD = next(
    (p for n in ("freecadcmd", "FreeCADCmd", "freecad.cmd") if (p := shutil.which(n))),
    None,
)
SCRIPT = ROOT / "freecad_bracket.py"


class Material(NamedTuple):
    density: float  # kg/m^3
    yield_mpa: float
    modulus_mpa: float


MATERIALS = {
    "aluminium-6061-t6": Material(2700, 276, 68_900),
    "steel-s275": Material(7850, 275, 210_000),
    "stainless-304": Material(8000, 215, 193_000),
}


class Fastener(NamedTuple):
    d: float  # Thread, mm
    hole: float  # ISO 273 medium clearance hole
    head: float  # ISO 4017 head across corners, modelled round
    head_h: float
    stress_area: float  # mm^2
    washer_id: float  # ISO 7089
    washer_od: float
    washer_h: float


FASTENERS = {
    "M4": Fastener(4, 4.5, 7.66, 2.8, 8.78, 4.3, 9, 0.8),
    "M5": Fastener(5, 5.5, 8.79, 3.5, 14.2, 5.3, 10, 1.0),
    "M6": Fastener(6, 6.6, 11.05, 4.0, 20.1, 6.4, 12, 1.6),
    "M8": Fastener(8, 9.0, 14.38, 5.3, 36.6, 8.4, 16, 1.6),
    "M10": Fastener(10, 11.0, 18.9, 6.4, 58.0, 10.5, 20, 2.0),
}
PROOF_MPA = 600  # Property class 8.8 screws.
EMBEDMENT_MM = 25  # Screw length past the washer face, into the wall plug.

# What bracket_check measures, by requirement constraint metric, and in what unit.
METRICS = {
    "mass": ("mass", "mass"),
    "width": ("width", "length"),
    "depth": ("depth", "length"),
    "height": ("height", "length"),
    "deflection": ("deflection", "length"),
    "max_stress": ("max_stress", "stress"),
    "safety_factor": ("safety_factor", "ratio"),
    "screw_tension": ("screw_tension", "force"),
}
UNITS = {  # Scale to the measurement's unit: kg, mm, MPa, 1, N.
    "kg": ("mass", 1.0),
    "g": ("mass", 1e-3),
    "mm": ("length", 1.0),
    "cm": ("length", 10.0),
    "m": ("length", 1000.0),
    "MPa": ("stress", 1.0),
    "N/mm2": ("stress", 1.0),
    "kPa": ("stress", 1e-3),
    "Pa": ("stress", 1e-6),
    "1": ("ratio", 1.0),
    "": ("ratio", 1.0),
    "-": ("ratio", 1.0),
    "N": ("force", 1.0),
    "kN": ("force", 1000.0),
}

INSTRUCTIONS = """Product family: wall-mounted L-brackets, one plate bent to an L
with a row of screw holes in each leg, fixed to the wall through the upright leg
with hex screws and washers. Design only within this family, using its tools:
- bracket_generate(design, name) builds the parametric FreeCAD assembly, STEP
  export, orthographic drawing and CAD-derived BOM. If it returns problems, the
  design breaks a layout rule: change the design and call it again.
- bracket_check(native_artifact, step_artifact, bom_artifact, load_n) reopens the
  published files, checks geometry, export, BOM and every requirement constraint,
  and returns a VerificationResult. Pass the three artifact refs as its inputs.
Record each measurable requirement with a constraint whose metric is one of:
mass (kg, whole assembly), width (mm, along the wall), depth (mm, out from the
wall), height (mm, up the wall), deflection (mm, shelf tip), max_stress (MPa),
safety_factor (unit "1"), screw_tension (N, per screw). bracket_check cannot
measure other metrics; it reports them as not performed.
Plan one PDR deliverable with artifact kinds native-cad, step, drawing and bom and
evidence kind cad-verification. Publish all four files of one bracket_generate run,
run bracket_check on them with the brief's design load, record its result as
cad-verification evidence citing those artifacts and the requirements, deliver,
then request the PDR review."""


class BracketDesign(Model):
    """One member of the family. Dimensions in mm; holes are per leg."""

    material: Literal["aluminium-6061-t6", "steel-s275", "stainless-304"]
    width_mm: Annotated[float, Field(ge=20, le=200)]
    thickness_mm: Annotated[float, Field(ge=2, le=20)]
    wall_leg_mm: Annotated[float, Field(ge=30, le=400)]
    shelf_leg_mm: Annotated[float, Field(ge=30, le=400)]
    fastener: Literal["M4", "M5", "M6", "M8", "M10"]
    holes_per_leg: Annotated[int, Field(ge=1, le=3)]


class BracketFiles(Model):
    native: ProducedFile
    step: ProducedFile
    drawing: ProducedFile
    bom: ProducedFile


class BracketBuild(Model):
    """Files for a valid design; otherwise the layout rules it breaks."""

    problems: tuple[str, ...]
    files: BracketFiles | None


def problems(design: BracketDesign) -> list[str]:
    """Layout rules the parametric model needs; the tool reports, not raises."""
    f = FASTENERS[design.fastener]
    edge = 2 * f.hole
    pitch = design.width_mm / (design.holes_per_leg + 1)
    found = []
    if pitch < f.washer_od + 2:
        found.append(
            f"{design.holes_per_leg} {design.fastener} holes need width >= "
            f"{(f.washer_od + 2) * (design.holes_per_leg + 1):g} mm"
        )
    for leg, length in (("wall", design.wall_leg_mm), ("shelf", design.shelf_leg_mm)):
        if length - edge - f.washer_od / 2 < design.thickness_mm + 1:
            found.append(
                f"{leg} leg needs >= {design.thickness_mm + 1 + edge + f.washer_od / 2:g} mm "
                f"for {design.fastener} holes {edge:g} mm from its end"
            )
    return found


async def freecad(job: dict[str, object], directory: Path) -> dict:
    """Run freecad_bracket.py on one job in its own headless FreeCAD process group.

    A timeout or a cancelled call kills that group, not just the wait for it.
    """
    if FREECAD is None:
        raise RuntimeError("FreeCAD is not installed: no freecadcmd on PATH")
    path, result = directory / "job.json", directory / "result.json"
    result.unlink(missing_ok=True)
    path.write_text(json.dumps({**job, "result": str(result)}), encoding="utf-8")
    process = await asyncio.create_subprocess_exec(
        FREECAD,
        "-c",
        f"exec(open({str(SCRIPT)!r}, encoding='utf-8').read())",
        env={**os.environ, "BRACKET_JOB": str(path)},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), FREECAD_TIMEOUT_S)
    except (TimeoutError, asyncio.CancelledError) as exc:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        # Not TimeoutError: the runtime would read that as its own turn timing out.
        raise RuntimeError(f"FreeCAD took over {FREECAD_TIMEOUT_S} s") from None
    if process.returncode or not result.exists():
        tail = "\n".join(output.decode(errors="replace").splitlines()[-15:])
        raise RuntimeError(f"FreeCAD exited {process.returncode}:\n{tail}")
    return json.loads(result.read_text(encoding="utf-8"))


def assess(
    measured: dict,
    published_bom: list[list[str]],
    load_n: float,
    requirements: Iterable[Requirement],
) -> VerificationResult:
    """Judge one inspected assembly: geometry, export, BOM, then requirements.

    The structural numbers are a PDR hand calculation from the model's own
    parameters: the shelf leg as a cantilever plate on a rigid upright, the load
    at its tip, and the wall screws in tension about the heel.
    """
    p, parts = measured["parameters"], measured["components"]
    bracket = next(c for c in parts if c["name"] == "Bracket")
    material = MATERIALS[bracket["material"]]
    fastener = next(f for f in FASTENERS.values() if f.d == p["screw_d"])
    holes = measured["holes"]
    width, t, shelf = p["width"], p["thickness"], p["shelf_leg"]
    stress = 6 * load_n * shelf / (width * t**2)
    deflection = 4 * load_n * shelf**3 / (material.modulus_mpa * width * t**3)
    tension = load_n * shelf / ((p["wall_leg"] - p["edge"]) * holes)
    safety = min(
        material.yield_mpa / stress, fastener.stress_area * PROOF_MPA / tension
    )
    mass = sum(c["volume"] * c["density"] * 1e-9 for c in parts)
    measurements = {
        "mass": Quantity(value=mass, unit="kg"),
        "width": Quantity(value=bracket["size"][0], unit="mm"),
        "depth": Quantity(value=bracket["size"][1], unit="mm"),
        "height": Quantity(value=bracket["size"][2], unit="mm"),
        "deflection": Quantity(value=deflection, unit="mm"),
        "max_stress": Quantity(value=stress, unit="MPa"),
        "safety_factor": Quantity(value=safety, unit="1"),
        "screw_tension": Quantity(value=tension, unit="N"),
        "design_load": Quantity(value=load_n, unit="N"),
    }
    step, native = measured["step_volumes"], sorted(c["volume"] for c in parts)
    thickened = measured["thickened"]
    checks: dict[str, bool | None] = {
        "native model recomputes without errors": not measured["errors"],
        "every component is one valid solid": all(
            c["valid"] and c["solids"] == 1 for c in parts
        ),
        "model recomputes valid after a +1 mm thickness change": not thickened["errors"]
        and thickened["volume_after"] > thickened["volume_before"],
        "STEP holds one solid per component": len(step) == len(parts),
        "STEP solid volumes match the native components": len(step) == len(native)
        and all(math.isclose(a, b, rel_tol=1e-3) for a, b in zip(step, native)),
        "no interference between components": not measured["interferences"],
        "BOM matches the assembly": published_bom == measured["bom"],
    }
    for requirement in requirements:
        c = requirement.constraint
        if c is None:
            continue
        bounds = " and ".join(
            f"{op} {value:g}"
            for op, value in ((">=", c.minimum), ("<=", c.maximum))
            if value is not None
        )
        unit_name = "" if c.unit.strip() in {"", "1", "-"} else f" {c.unit}"
        name = f"{requirement.id}: {c.metric} {bounds}{unit_name}"
        metric = METRICS.get(c.metric.strip().lower().replace(" ", "_"))
        unit = UNITS.get(c.unit.strip())
        if metric is None or unit is None or metric[1] != unit[0]:
            checks[name] = None  # Not something this tool measures.
            continue
        value = measurements[metric[0]].value / unit[1]
        measurements[requirement.id] = Quantity(value=value, unit=c.unit)
        checks[name] = (c.minimum is None or value >= c.minimum) and (
            c.maximum is None or value <= c.maximum
        )
    results = list(checks.values())
    outcome = (
        "failed"
        if False in results
        else "inconclusive"
        if None in results
        else "passed"
    )
    explanation = (
        f"{len(parts)}-component assembly, {mass:.3f} kg. Under {load_n:g} N at the "
        f"shelf tip: plate root stress {stress:.1f} MPa, tip deflection "
        f"{deflection:.2f} mm, {tension:.0f} N per wall screw, safety factor "
        f"{safety:.2f}. Hand calculation: cantilevered shelf plate on a rigid upright, "
        "screws in tension about the heel; screw shear, prying and wall anchorage are "
        f"not assessed. {results.count(True)} of {len(results)} checks passed, "
        f"{results.count(None)} not performed."
    )
    return VerificationResult(
        outcome=outcome,
        explanation=explanation,
        checks=checks,
        measurements=measurements,
    )


def register_tools(project: Project) -> None:
    async def bracket_generate(
        design: BracketDesign,
        name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")],
    ) -> BracketBuild:
        """Build one bracket: parametric FreeCAD model, STEP, drawing and BOM.

        Wall holes sit 2 clearance diameters below the upright's top, shelf holes 2
        diameters from the shelf's front edge, both spread evenly across the width.
        """
        found = problems(design)
        if found:
            return BracketBuild(problems=tuple(found), files=None)
        f, d = FASTENERS[design.fastener], design
        screw_len = 5 * math.ceil((d.thickness_mm + f.washer_h + EMBEDMENT_MM) / 5)
        number = f"BRK-{name}"
        directory = project.output_path(Path("cad") / name)
        directory.mkdir(parents=True, exist_ok=True)
        paths = {
            "native": directory / f"{number}.FCStd",
            "step": directory / f"{number}.step",
            "drawing": directory / f"{number}.svg",
            "bom": directory / f"{number}-bom.csv",
        }
        size = f"{d.width_mm:g} x {d.wall_leg_mm:g} x {d.shelf_leg_mm:g} x {d.thickness_mm:g} mm"
        await freecad(
            {
                "mode": "generate",
                "holes": d.holes_per_leg,
                "title": f"{number}  L-bracket {size}, {d.material}",
                "parameters": {
                    "width": d.width_mm,
                    "thickness": d.thickness_mm,
                    "wall_leg": d.wall_leg_mm,
                    "shelf_leg": d.shelf_leg_mm,
                    "hole_d": f.hole,
                    "edge": 2 * f.hole,
                    "screw_d": f.d,
                    "screw_len": screw_len,
                    "head_d": f.head,
                    "head_h": f.head_h,
                    "washer_od": f.washer_od,
                    "washer_id": f.washer_id,
                    "washer_h": f.washer_h,
                },
                "parts": {
                    "bracket": {
                        "PartNumber": number,
                        "Description": f"L-bracket {size}, "
                        f"{d.holes_per_leg} x {f.hole:g} mm holes per leg",
                        "Material": d.material,
                        "Density": MATERIALS[d.material].density,
                    },
                    "screw": {
                        "PartNumber": f"ISO4017-{d.fastener}x{screw_len:g}-8.8",
                        "Description": f"Hex head screw ISO 4017 {d.fastener} x {screw_len:g}, class 8.8",
                        "Material": "steel, zinc plated",
                        "Density": 7850,
                    },
                    "washer": {
                        "PartNumber": f"ISO7089-{f.d:g}-200HV",
                        "Description": f"Plain washer ISO 7089 size {f.d:g}, 200 HV",
                        "Material": "steel, zinc plated",
                        "Density": 7850,
                    },
                },
                "outputs": {k: str(v) for k, v in paths.items()},
            },
            directory,
        )
        return BracketBuild(
            problems=(),
            files=BracketFiles(
                **{k: ProducedFile.from_path(v) for k, v in paths.items()}
            ),
        )

    async def bracket_check(
        native_artifact: str,
        step_artifact: str,
        bom_artifact: str,
        load_n: Annotated[float, Field(gt=0)],
    ) -> VerificationResult:
        """Verify published bracket artifacts against geometry rules and requirements.

        Give the artifact ids of one bracket_generate run and the brief's design
        load at the shelf tip. Every current requirement with a constraint gets a
        check named after its id; metrics this tool cannot measure stay unperformed.
        """
        files = {
            key: project.verify_file(
                project.store.model("artifact", artifact, ArtifactRecord).file
            )
            for key, artifact in (
                ("native", native_artifact),
                ("step", step_artifact),
                ("bom", bom_artifact),
            )
        }
        directory = project.output_path(Path("cad") / "checks" / native_artifact)
        directory.mkdir(parents=True, exist_ok=True)
        measured = await freecad(
            {
                "mode": "inspect",
                "native": str(files["native"]),
                "step": str(files["step"]),
            },
            directory,
        )
        with files["bom"].open(newline="", encoding="utf-8") as stream:
            published = list(csv.reader(stream))
        requirements = [
            Requirement.model_validate_json(encode(s.data))
            for s in project.store.list("requirement")
            if not s.stale
        ]
        return assess(measured, published, load_n, requirements)

    # Generation rewrites its own files and checks only read: both safe to retry.
    project.tools.register(bracket_generate, retry_safe=True)
    project.tools.register(bracket_check, retry_safe=True)


def project_request(brief: str) -> ProjectRequest:
    return ProjectRequest(
        description=brief,
        context=CONTEXT.model_copy(update={"instructions": INSTRUCTIONS}),
        target_reviews=("PDR",),
        budget=BUDGET,
    )


async def run_brief(brief: Path, runs: Path) -> dict[str, object]:
    """One brief, one fresh project; answer questions, stop at review or failure."""
    workspace = runs / brief.stem
    started = time.monotonic()
    with Project(
        workspace / "state",
        sandbox=workspace / "results",
        tools=ToolRegistry(),
        reasoning=reasoning(),
        max_concurrent_calls=MAX_CONCURRENT_CALLS,
    ) as project:
        register_tools(project)
        result = await project.run(project_request(brief.read_text(encoding="utf-8")))
        replies = 0
        for _ in range(5):  # Rounds of scripted replies to blocking questions.
            pending = [
                request
                for entry in project.human.inbox(run_id=result.run_id)
                if (
                    request := project.activity.get(entry.message.request_id or "")
                ).required
                and "review" not in request.arguments
            ]
            if result.status != "awaiting_human" or not pending:
                break
            for request in pending:
                project.human.reply(request.id, SCRIPTED_REPLY, author="benchmark")
            replies += len(pending)
            result = await project.run(resume=result.run_id)
        await project.drain()
        return {
            "brief": brief.stem,
            "passed": result.status == "awaiting_review",
            "status": result.status,
            "scripted_replies": replies,
            "estimated_input_tokens": sum(
                int(str(e.details.get("input_tokens", 0)))
                for e in project.events()
                if e.type == "provider.dispatched"
            ),
            "seconds": round(time.monotonic() - started),
            "reviews": [r.id for r in result.reviews],
            "open_items": list(result.open_items),
        }


async def main() -> None:
    if FREECAD is None or shutil.which(reasoning().executable) is None:
        raise SystemExit(
            "Needs FreeCAD (freecadcmd or freecad.cmd) and the reasoning CLI on PATH, "
            "logged in (for Codex: 'codex login')."
        )
    runs = RUNS / time.strftime("%Y%m%d-%H%M%S")
    results = [await run_brief(b, runs) for b in sorted(BRIEFS.glob("*.md"))]
    (runs / "benchmark.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    for r in results:
        print(
            f"{r['brief']:<12} {r['status']:<16} {r['estimated_input_tokens']:>11,} "
            f"tokens {r['seconds']:>6} s"
        )
    print(
        f"{sum(bool(r['passed']) for r in results)}/{len(results)} reached a ready review"
    )


if __name__ == "__main__":
    asyncio.run(main())
