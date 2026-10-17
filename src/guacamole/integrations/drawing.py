"""draw_part: a standards-conformant part drawing and AP242 STEP for any one-part model.

Every Project registers it. Headless FreeCAD projects the part's views
(drawing_freecad.py), ap242.fingerprints finds each named feature among its faces,
drafting compiles the drawing from the PMI and those views, and ap242 writes the PMI
onto the part's faces. Both written files are read back and checked.
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from ..contracts import Model, ProducedFile
from . import ap242, drafting
from .freecad import run_job

if TYPE_CHECKING:
    from ..project import Project

SCRIPT = Path(__file__).with_name("drawing_freecad.py")


class FindPlane(Model):
    kind: Literal["plane"]
    normal: drafting.Vec  # Outward unit normal
    offset: float  # normal . any point on the face, mm


class FindAxes(Model):
    kind: Literal["holes", "shafts"]  # Every equal parallel one
    axis: drafting.Vec
    diameter: float


class FindWidth(Model):
    kind: Literal["width"]
    normal: drafting.Vec  # Across the slot or tab
    offset: float  # normal . a point on its median plane, mm
    width: float
    internal: bool  # A slot; False for a tab


type Find = Annotated[FindPlane | FindAxes | FindWidth, Field(discriminator="kind")]


# ponytail: no surface sets (fillets, freeform); naming them needs measured face
# centroids. Add a find-by-radius spec when a drawing needs one.
class PartPMI(drafting.PMI):
    """drafting.PMI with each feature given by where draw_part finds it."""

    features: dict[str, Find]


class DrawingFiles(Model):
    pmi: ProducedFile  # Canonical PMI, holding the features as measured
    step: ProducedFile  # AP242 carrying the PMI on the part's faces
    dxf: ProducedFile
    svg: ProducedFile
    pdf: ProducedFile


class PartDrawing(Model):
    problems: tuple[str, ...]  # What to fix; nothing was written when there are any
    files: DrawingFiles | None = None
    not_carried: tuple[str, ...] = ()  # PMI AP242 cannot hold; the drawing shows it
    checks: dict[str, bool] = Field(default_factory=dict)  # Read-backs of the files
    differences: tuple[str, ...] = ()  # How the AP242 read-back departs from the PMI


def draw(
    source: Path, request: PartPMI, sheet: drafting.Sheet, views: dict, out: Path
) -> PartDrawing:
    """Find the features, compile and write the drawing and AP242, read both back."""
    specs = {name: f.model_dump() for name, f in request.features.items()}
    features, failed = drafting.features(ap242.fingerprints(source, specs))
    if failed:
        return PartDrawing(problems=tuple(failed))
    pmi = drafting.PMI.model_validate(dict(request) | {"features": features})
    paths = {
        key: out / f"{sheet.number}{suffix}"
        for key, suffix in (
            ("pmi", "-pmi.json"),
            ("step", ".step"),
            ("dxf", ".dxf"),
            ("svg", ".svg"),
            ("pdf", ".pdf"),
        )
    }
    try:
        drawing = drafting.compile_drawing(pmi, sheet, views)
        not_carried = ap242.write(pmi, source, paths["step"])
    except ValueError as exc:
        return PartDrawing(problems=(str(exc),))
    paths["pmi"].write_text(pmi.model_dump_json(indent=2), encoding="utf-8")
    drafting.write(drawing, paths["dxf"], paths["svg"], paths["pdf"])
    differences = ap242.compare(pmi, ap242.read(paths["step"]))
    return PartDrawing(
        problems=(),
        files=DrawingFiles(**{k: ProducedFile.from_path(v) for k, v in paths.items()}),
        not_carried=tuple(not_carried),
        checks={
            **drafting.conformance(paths["dxf"], pmi),
            "STEP AP242 carries the PMI exactly": not differences,
        },
        differences=tuple(differences),
    )


def register_drawing_tools(project: "Project") -> None:
    async def draw_part(step: str, pmi: PartPMI, sheet: drafting.Sheet) -> PartDrawing:
        """Compile a part drawing and an AP242 STEP from one part's STEP and its PMI.

        step: sandbox path of a STEP holding the part alone, e.g. from freecad_run.
        pmi: ISO GPS (default) or ASME Y14.5 PMI. Its features say where each named
        feature is: a plane by its outward unit normal and offset (normal . any point
        on it, mm); holes or shafts, all equal parallel ones together, by axis and
        diameter; a slot or tab by the normal across it, its median plane's offset,
        width and internal. Datums, targets, sizes, locations, tolerances and the
        ISO 22081 general specification name those features; the values are your
        design's. sheet: the ISO 7200 title block and layout. The views are FRONT,
        TOP and RIGHT: FRONT looks along +y with x right and z up, TOP along -z,
        RIGHT along -x. Place plain dimensions between planes, a callout for each
        holes or shafts feature in a view along its axis, and optionally the view
        each datum is indicated in. Writes <number>.dxf, .svg and .pdf,
        <number>-pmi.json and <number>.step (AP242 with the PMI on the part's
        faces) under drawings/<number>/, then reads them back: checks and
        differences say what conforms. When a feature is not found exactly once,
        or the PMI or layout breaks a drafting rule, it writes nothing and returns
        problems: fix them and call again.
        """
        source = project.output_path(Path(step))
        out = project.output_path(Path("drawings") / sheet.number)
        out.mkdir(parents=True, exist_ok=True)
        part = await run_job({"step": str(source)}, out, SCRIPT)
        if part["solids"] != 1:
            return PartDrawing(
                problems=(
                    f"{step} holds {part['solids']} solids: export the part alone",
                )
            )
        # OCCT and ezdxf work for seconds; other agents keep running meanwhile.
        return await asyncio.to_thread(draw, source, pmi, sheet, part["views"], out)

    # Drafting errors hold no secrets; agents fix calls with them.
    project.tools.register(draw_part, show_errors=True)
