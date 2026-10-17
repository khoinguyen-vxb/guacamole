"""Wall-mounted L-brackets: Milestone B's prompt-to-review-package benchmark.

Run with: uv sync
          .venv/bin/python -m examples.bracket.bracket [runs/<timestamp>]

Every brief in briefs/ runs as its own project under runs/<timestamp>/. A brief
passes when its run reaches a ready PDR review: native CAD, STEP, drawing and BOM
published, checked and delivered, with no open review issues. Every question gets
one scripted reply as it is asked; each brief holds at its review until a human
accepts it or requests changes (review.py). A brief paused by a provider failure
(usage limit, outage) stops the benchmark there: pass its runs/<timestamp> to
resume it, keeping the briefs that finished.

Edit the configuration below; the only argument is a runs directory to resume.
Install FreeCAD (freecadcmd, or the snap's freecad.cmd) and the Claude Code CLI, and
log in to it before running. Model calls count against that account's usage.
"""

import asyncio
import csv
import json
import math
import re
import sys
import time
from collections.abc import Iterable
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
    Watchdog,
)
from guacamole.console import host, preflight
from guacamole.contracts import ArtifactRecord
from guacamole.integrations import ap242, drafting
from guacamole.integrations.freecad import FREECAD, run_job
from guacamole.providers.claude import ClaudeReasoning
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
    # Claude budgets by UTF-8 bytes, about 2.9x the Codex estimate.
    max_run_input_tokens=17_000_000,
)
CONTEXT = ContextSpec(max_input_tokens=400_000, reserved_output_tokens=20_000)
MAX_CONCURRENT_CALLS = 2
CONTROL_PORT = 8767  # ehopper/RDE use 8766, kookaburra 8765.
FREECAD_TIMEOUT_S = 300
SCRIPTED_REPLY = (
    "Benchmark reply: no further input is available. Proceed on explicit "
    "assumptions and record each one as an open item, naming the requirements "
    "whose unknowns it covers and only the review stages that need it."
)


def reasoning() -> ClaudeReasoning:
    """The benchmarked model, used by the Chief and the Systems Engineer alike."""
    return ClaudeReasoning(web_search=False, effort="xhigh")


SCRIPT = ROOT / "freecad_bracket.py"


class Material(NamedTuple):
    density: float  # kg/m^3
    yield_mpa: float
    modulus_mpa: float
    name: str  # As the drawing's title block states it


MATERIALS = {
    "aluminium-6061-t6": Material(2700, 276, 68_900, "Aluminium 6061-T6"),
    "steel-s275": Material(7850, 275, 210_000, "Steel S275"),
    "stainless-304": Material(8000, 215, 193_000, "Stainless steel 304"),
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

# The family's drafting rules, ISO GPS (examples/drafting.py). Holes are ISO 273 medium
# clearance holes, class H13 as ISO 273 gives for that series, positioned at maximum
# material for a floating fastener: T = H - F, the hole's smallest size less the
# screw's. Everything else falls under the ISO 22081 general specification, set to
# bent-plate workshop practice; change these with the shop that makes the parts.
HOLE_CLASS = "H13"
GENERAL_SIZE_MM = 0.5
GENERAL_PROFILE_MM = 1.0
OWNER = "Guacamole bracket benchmark"  # The title block's legal owner
DATUMS = {"A": "wall_face", "B": "base_face", "C": "side_face"}
LAYOUT = {  # Where the drawing shows each dimension, hole callout and datum.
    "dimensions": (
        drafting.Between(planes=("side_face", "far_side"), view="FRONT", side="below"),
        drafting.Between(planes=("base_face", "wall_top"), view="RIGHT", side="right"),
        drafting.Between(
            planes=("wall_face", "shelf_front"), view="RIGHT", side="below"
        ),
        drafting.Between(
            planes=("wall_face", "wall_inner"), view="RIGHT", side="above"
        ),
        drafting.Between(planes=("base_face", "shelf_top"), view="RIGHT", side="left"),
    ),
    "callouts": (
        drafting.Callout(feature="wall_holes", view="FRONT", side="left"),
        drafting.Callout(feature="shelf_holes", view="TOP", side="right"),
    ),
    "datum_views": {"A": "TOP", "B": "FRONT", "C": "FRONT"},
}

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
    "N/mm^2": ("stress", 1.0),  # SysML's SI has no MPa.
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
- bracket_generate(design, name) builds the parametric FreeCAD assembly, its STEP
  AP242 export carrying the PMI on the bracket's faces, the bracket's PMI (ISO GPS
  datums and tolerances, JSON), its ISO part drawing (editable DXF, SVG for
  review and PDF for print) and the CAD-derived BOM. If it returns problems, the
  design breaks a layout or drafting rule: change the design and call it again.
  Its optional tolerancing argument replaces the family's GD&T rule (H13 holes
  positioned at maximum material by T = H - F, ISO 22081 general ±0.5 and
  profile 1): use it only when a requirement asks for tighter GD&T, such as a
  flatter mounting face.
- bracket_check(native_artifact, step_artifact, bom_artifact, pmi_artifact,
  drawing_artifact, load_n) reopens the published files, checks geometry, export,
  BOM, PMI, the DXF drawing and every requirement constraint, and returns a
  VerificationResult. Pass the five artifact refs as its inputs.
The systems engineer records each measurable requirement with a constraint whose
metric is one of:
mass (kg, whole assembly), width (mm, along the wall), depth (mm, out from the
wall), height (mm, up the wall), deflection (mm, shelf tip), max_stress (N/mm^2,
as SysML spells MPa),
safety_factor (dimensionless), screw_tension (N, per screw). bracket_check cannot
measure other metrics; it reports them as not performed.
Plan one PDR deliverable with artifact kinds native-cad, step, pmi, drawing and bom
and evidence kind cad-verification. Publish all seven files of one bracket_generate
run (the DXF, SVG and PDF all as kind drawing), run bracket_check on them with the
brief's design load, record its result as
cad-verification evidence citing the five artifacts it checked and the requirements,
and send it to the systems engineer, which records the compliance assessment.
Deliver, then request the PDR review."""


class BracketDesign(Model):
    """One member of the family. Dimensions in mm; holes are per leg."""

    material: Literal["aluminium-6061-t6", "steel-s275", "stainless-304"]
    width_mm: Annotated[float, Field(ge=20, le=200)]
    thickness_mm: Annotated[float, Field(ge=2, le=20)]
    wall_leg_mm: Annotated[float, Field(ge=30, le=400)]
    shelf_leg_mm: Annotated[float, Field(ge=30, le=400)]
    fastener: Literal["M4", "M5", "M6", "M8", "M10"]
    holes_per_leg: Annotated[int, Field(ge=1, le=3)]


class Tolerancing(Model):
    """GD&T the designer proposes in place of the family rule: checked, not trusted.

    Holes take an ISO 286 H class (the smallest hole is then its nominal) and a
    position at maximum material; the mounting face, datum A, may take a flatness
    tighter than the ISO 22081 general profile. Unset fields keep the family rule.
    """

    hole_class: Annotated[str, Field(pattern=r"^H(7|8|9|10|11|12|13|14)$")] = HOLE_CLASS
    position_mm: Annotated[float, Field(gt=0)] | None = None  # Default: H - F
    wall_flatness_mm: Annotated[float, Field(gt=0)] | None = None
    general_size_mm: Annotated[float, Field(gt=0, le=2)] = GENERAL_SIZE_MM
    general_profile_mm: Annotated[float, Field(gt=0, le=5)] = GENERAL_PROFILE_MM


def tolerancing_problems(t: Tolerancing, fastener: Fastener) -> list[str]:
    """Where proposed GD&T breaks the family's engineering rules."""
    found = []
    limit = fastener.hole - fastener.d
    if t.position_mm is not None and t.position_mm > limit + 1e-9:
        found.append(
            f"hole position {t.position_mm:g} exceeds the floating-fastener limit "
            f"T = H - F = {limit:g} mm: screws may not assemble"
        )
    if t.wall_flatness_mm is not None and t.wall_flatness_mm >= t.general_profile_mm:
        found.append(
            f"wall flatness {t.wall_flatness_mm:g} adds nothing to the general profile "
            f"{t.general_profile_mm:g}: make it tighter or leave it out"
        )
    return found


class BracketFiles(Model):
    native: ProducedFile
    step: ProducedFile
    pmi: ProducedFile  # Canonical PMI: the drawing is compiled from it
    drawing: ProducedFile  # DXF
    drawing_svg: ProducedFile
    drawing_pdf: ProducedFile
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


def feature_specs(design: BracketDesign) -> dict[str, dict]:
    """The bracket's named features, located from its design: planes and hole sets.

    A plane is its outward normal and offset (normal . point) in model axes: x along
    the wall, y out of it, z up, origin at the wall-side bottom corner.
    """
    d, f = design, FASTENERS[design.fastener]

    def plane(normal: list[int], offset: float) -> dict:
        return {"kind": "plane", "normal": normal, "offset": offset}

    return {
        "wall_face": plane([0, -1, 0], 0),  # Against the wall
        "wall_inner": plane([0, 1, 0], d.thickness_mm),
        "wall_top": plane([0, 0, 1], d.wall_leg_mm),
        "base_face": plane([0, 0, -1], 0),  # Underside of the shelf leg
        "shelf_top": plane([0, 0, 1], d.thickness_mm),
        "shelf_front": plane([0, 1, 0], d.shelf_leg_mm),
        "side_face": plane([-1, 0, 0], 0),
        "far_side": plane([1, 0, 0], d.width_mm),
        "wall_holes": {"kind": "holes", "axis": [0, 1, 0], "diameter": f.hole},
        "shelf_holes": {"kind": "holes", "axis": [0, 0, 1], "diameter": f.hole},
    }


def bracket_pmi(
    features: dict, fastener: Fastener, tolerancing: Tolerancing | None = None
) -> drafting.PMI:
    """One bracket's PMI: datums A B C, H-class holes positioned at MMC, the general
    specification, and any mounting-face flatness the designer proposed."""
    t = tolerancing or Tolerancing()
    position = t.position_mm or fastener.hole - fastener.d  # Floating: T = H - F
    holes = (("wall_holes", ("A", "B", "C")), ("shelf_holes", ("B", "A", "C")))
    flatness = (
        (
            drafting.Tolerance(
                feature="wall_face", characteristic="flatness", value=t.wall_flatness_mm
            ),
        )
        if t.wall_flatness_mm is not None
        else ()
    )
    return drafting.PMI(
        features=features,
        datums=DATUMS,
        sizes=tuple(drafting.Size(feature=name, fit=t.hole_class) for name, _ in holes),
        tolerances=tuple(
            drafting.Tolerance(
                feature=name,
                characteristic="position",
                value=position,
                diameter=True,
                material="M",
                datums=datums,
            )
            for name, datums in holes
        )
        + flatness,
        general=drafting.General(
            size=t.general_size_mm,
            profile=t.general_profile_mm,
            datums=("A", "B", "C"),
        ),
    )


def floating(pmi: drafting.PMI, bom: list[list[str]]) -> bool:
    """Whether every hole position at MMC lets the BOM's screws float: T <= H - F."""
    screws = [
        float(m.group(1))
        for row in bom
        for cell in row
        if (m := re.search(r"ISO4017-M(\d+(?:\.\d+)?)", cell))
    ]
    if not screws:
        return False
    return all(
        t.value <= pmi.features[t.feature].diameter - max(screws) + 1e-9
        for t in pmi.tolerances
        if t.characteristic == "position"
        and t.material == "M"
        and isinstance(pmi.features[t.feature], drafting.Holes)
    )


def assess(
    measured: dict,
    published_bom: list[list[str]],
    load_n: float,
    requirements: Iterable[Requirement],
    drawing: dict[str, bool] | None = None,
) -> VerificationResult:
    """Judge one inspected assembly: geometry, export, BOM, drawing, then requirements.

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
        **(drawing or {}),
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
        tolerancing: Tolerancing | None = None,
    ) -> BracketBuild:
        """Build one bracket: parametric FreeCAD model, STEP AP242 with PMI, drawing and BOM.

        Wall holes sit 2 clearance diameters below the upright's top, shelf holes 2
        diameters from the shelf's front edge, both spread evenly across the width.
        Without tolerancing the family rule sets the GD&T; a proposal is checked
        against the floating-fastener rule and returned as problems if it breaks it.
        """
        found = problems(design)
        if not found and tolerancing is not None:
            found = tolerancing_problems(tolerancing, FASTENERS[design.fastener])
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
            "pmi": directory / f"{number}-pmi.json",
            "drawing": directory / f"{number}.dxf",
            "drawing_svg": directory / f"{number}.svg",
            "drawing_pdf": directory / f"{number}.pdf",
            "bom": directory / f"{number}-bom.csv",
        }
        size = f"{d.width_mm:g} x {d.wall_leg_mm:g} x {d.shelf_leg_mm:g} x {d.thickness_mm:g} mm"
        built = await run_job(
            {
                "mode": "generate",
                "holes": d.holes_per_leg,
                "features": feature_specs(d),
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
                "outputs": {k: str(paths[k]) for k in ("native", "step", "bom")},
            },
            directory,
            SCRIPT,
            FREECAD_TIMEOUT_S,
        )
        # The drawing is compiled from the PMI and the model's own geometry; a
        # feature the model no longer holds, or a malformed PMI, is a problem.
        features, failed = drafting.features(built["features"])
        if failed:
            return BracketBuild(problems=tuple(failed), files=None)
        pmi = bracket_pmi(features, f, tolerancing)
        today = time.strftime("%Y-%m-%d")
        sheet = drafting.Sheet(
            title=f"L-BRACKET {d.width_mm:g}×{d.wall_leg_mm:g}×{d.shelf_leg_mm:g}×"
            f"{d.thickness_mm:g}",
            number=number,
            revision="A",
            date=today,
            status="In review",
            owner=OWNER,
            creator="bracket_generate",
            reference=paths["native"].name,
            material=MATERIALS[d.material].name,
            mass_kg=built["volume"] * MATERIALS[d.material].density * 1e-9,
            revisions=(("A", "First issue for PDR review", today),),
            **LAYOUT,
        )
        try:
            drawing = drafting.compile_drawing(pmi, sheet, built["views"])
            # FreeCAD's STEP becomes AP242 with the PMI on the bracket's faces. What it
            # leaves out (the ISO 22081 general size tolerance) stays in the PMI and
            # on the drawing.
            ap242.write(pmi, paths["step"], paths["step"])
        except ValueError as exc:
            return BracketBuild(problems=(str(exc),), files=None)
        paths["pmi"].write_text(pmi.model_dump_json(indent=2), encoding="utf-8")
        drafting.write(
            drawing, paths["drawing"], paths["drawing_svg"], paths["drawing_pdf"]
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
        pmi_artifact: str,
        drawing_artifact: str,
        load_n: Annotated[float, Field(gt=0)],
    ) -> VerificationResult:
        """Verify published bracket artifacts against geometry rules and requirements.

        Give the artifact ids of one bracket_generate run (the DXF as the drawing)
        and the brief's design load at the shelf tip. The PMI is checked against the
        ISO GPS subset and the reopened model, and the drawing against the PMI. Every
        current requirement with a constraint gets a check named after its id;
        metrics this tool cannot measure stay unperformed.
        """
        files = {
            key: project.verify_file(
                project.store.model("artifact", artifact, ArtifactRecord).file
            )
            for key, artifact in (
                ("native", native_artifact),
                ("step", step_artifact),
                ("bom", bom_artifact),
                ("pmi", pmi_artifact),
                ("drawing", drawing_artifact),
            )
        }
        pmi = drafting.PMI.model_validate_json(files["pmi"].read_text(encoding="utf-8"))
        directory = project.output_path(Path("cad") / "checks" / native_artifact)
        directory.mkdir(parents=True, exist_ok=True)
        measured = await run_job(
            {
                "mode": "inspect",
                "native": str(files["native"]),
                "step": str(files["step"]),
                "features": drafting.specs(pmi),
            },
            directory,
            SCRIPT,
            FREECAD_TIMEOUT_S,
        )
        found, failed = drafting.features(measured["features"])
        malformed, moved = drafting.problems(pmi), drafting.moved(pmi, found)
        # An independent read of the published STEP: what an AP242 consumer gets.
        differences = ap242.compare(pmi, ap242.read(files["step"]))
        with files["bom"].open(newline="", encoding="utf-8") as stream:
            published = list(csv.reader(stream))
        drawing = {
            "PMI well formed in the ISO_GPS_MECHANICAL subset": not malformed,
            "hole positions let the BOM's screws float: T <= H - F": floating(
                pmi, published
            ),
            "PMI features map one-to-one onto the model, unchanged": not failed
            and not moved,
            "STEP AP242 carries the PMI exactly: datums, hole sizes, frames and the "
            "general profile on their faces": not differences,
            **drafting.conformance(files["drawing"], pmi),
        }
        requirements = [
            Requirement.model_validate_json(encode(s.data))
            for s in project.store.list("requirement")
            if not s.stale
        ]
        return assess(measured, published, load_n, requirements, drawing)

    # Generation rewrites its own files and checks only read: both safe to retry.
    project.tools.register(bracket_generate, retry_safe=True)
    project.tools.register(bracket_check, retry_safe=True)


def project_request(brief: str, context: ContextSpec) -> ProjectRequest:
    return ProjectRequest(
        description=brief,
        context=context.model_copy(update={"instructions": INSTRUCTIONS}),
        target_reviews=("PDR",),
        budget=BUDGET,
    )


async def run_brief(brief: Path, runs: Path) -> dict[str, object]:
    """One brief, one project; resumes the brief's saved run if it has one."""
    workspace = runs / brief.stem
    started = time.monotonic()
    with Project(
        workspace / "state",
        sandbox=workspace / "results",
        tools=ToolRegistry(),
        reasoning=reasoning(),
        watchdog=Watchdog(),  # Reuses reasoning() at low effort.
        max_concurrent_calls=MAX_CONCURRENT_CALLS,
    ) as project:
        register_tools(project)
        text = brief.read_text(encoding="utf-8")
        result = await host(
            project,
            lambda context: project_request(text, context),
            port=CONTROL_PORT,
            context=CONTEXT,
            budget=BUDGET,
            reply=SCRIPTED_REPLY,
        )
        events = project.events()
        return {
            "brief": brief.stem,
            "run_id": result.run_id,
            "passed": any(e.type == "review.ready" for e in events),
            "status": result.status,
            # A human reply also reaches the other agents as findings.
            "scripted_replies": sum(
                (s.data["sender"], s.data["kind"]) == ("human:unattended", "reply")
                for s in project.store.list("message")
            ),
            "estimated_input_tokens": sum(
                int(str(e.details.get("input_tokens", 0)))
                for e in events
                if e.type == "provider.dispatched"
            ),
            "seconds": round(time.monotonic() - started),
            "reviews": [r.id for r in result.reviews],
            "open_items": list(result.open_items),
        }


async def main() -> None:
    if FREECAD is None:
        raise SystemExit("Needs FreeCAD (freecadcmd or freecad.cmd) on PATH.")
    preflight(reasoning().executable, "Needs the reasoning CLI on PATH, logged in.")
    runs = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else RUNS / time.strftime("%Y%m%d-%H%M%S")
    )
    saved = runs / "benchmark.json"
    earlier = (
        {r["brief"]: r for r in json.loads(saved.read_text(encoding="utf-8"))}
        if saved.exists()
        else {}
    )
    results = []
    for brief in sorted(BRIEFS.glob("*.md")):
        previous = earlier.get(brief.stem)
        if previous and previous["status"] != "paused":
            results.append(previous)  # Finished on an earlier start.
            continue
        result = await run_brief(brief, runs)
        if previous:
            result["seconds"] += previous["seconds"]
        results.append(result)
        saved.write_text(json.dumps(results, indent=2), encoding="utf-8")
        if result["status"] == "paused":
            # A usage limit would fail every later brief in seconds.
            print(
                f"{brief.stem} paused on a provider failure; fix it, then resume with "
                f".venv/bin/python -m examples.bracket.bracket {runs}"
            )
            break
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
