"""The FreeCAD MBD Workbench as a second AP242 writer for the PMI.

Wraps https://github.com/ChipsWoodShop/FreeCAD-MBDWorkbench (LGPL-2.1,
early preview, ASME Y14.5). export() runs mbd_freecad.py in headless FreeCAD to put
the PMI on the native model's faces as the Workbench's objects, save that model and
write AP242 with the Workbench's exporter. check() reads the file back with
ap242.read(), which shares no code with the Workbench, and compares it with the PMI
as the Workbench was given it to write.

The Workbench's exporter needs pythonocc-core inside FreeCAD. For the snap FreeCAD
(OCCT 7.8) a conda environment with pythonocc-core 7.8.1 works: its modules bind to
FreeCAD's own OCCT libraries. MBD_PYTHONOCC and MBD_WORKBENCH override where
they are looked for. Every Project registers mbd_annotate, which does both for agents.
"""

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ..contracts import Model, ProducedFile
from . import ap242
from .drafting import PMI
from .freecad import run_job

if TYPE_CHECKING:
    from ..project import Project

SCRIPT = Path(__file__).with_name("mbd_freecad.py")
PYTHONOCC = Path(
    os.environ.get("MBD_PYTHONOCC")
    or Path.home() / "miniconda3/envs/mbd-occ/lib/python3.12/site-packages"
)
WORKBENCH = Path(
    os.environ.get("MBD_WORKBENCH")
    or Path.home() / "snap/freecad/common/Mod/MBDWorkbench"
)


def available() -> bool:
    """The Workbench and pythonocc-core are where export() expects them."""
    return (PYTHONOCC / "OCC").is_dir() and (WORKBENCH / "freecad").is_dir()


async def export(pmi: PMI, native: Path, part: str, directory: Path) -> dict:
    """Write the PMI through the Workbench onto one part of the native model.

    Writes <part>-mbd.FCStd and <part>-mbd.step in directory. The result says
    whether the Workbench exported, holds the PMI as written ("pmi": patterns become
    one feature per element, since the Workbench puts each frame on one face) with a
    sentence for everything it could not hold, and its own validation issues.
    """
    return await run_job(
        {
            "native": str(native),
            "part": part,
            "pmi": pmi.model_dump(mode="json"),
            "step": str(directory / f"{part}-mbd.step"),
            "fcstd": str(directory / f"{part}-mbd.FCStd"),
            "pythonocc": str(PYTHONOCC),
            "workbench": str(WORKBENCH),
        },
        directory,
        SCRIPT,
    )


def check(result: dict, path: Path) -> list[str]:
    """How the Workbench's file differs from the PMI it was given to write.

    Leaves out the general specification: the Workbench has none, and the result
    lists it among what it could not hold.
    """
    written = PMI.model_validate_json(json.dumps(result["pmi"]))
    differences = ap242.compare(written, ap242.read(path))
    return [d for d in differences if not d.startswith("general surface profile")]


class MBDAnnotation(Model):
    exported: bool  # The Workbench's AP242 exporter succeeded
    fcstd: ProducedFile  # The native model, the Workbench's PMI objects on its faces
    step: ProducedFile | None  # Its AP242 export
    not_carried: tuple[str, ...]  # PMI the Workbench cannot hold
    issues: tuple[str, ...]  # The Workbench's own validation findings
    differences: tuple[str, ...]  # How the export reads back against what it was given


def register_mbd_tools(project: "Project") -> None:
    async def mbd_annotate(native: str, part: str, pmi: str) -> MBDAnnotation:
        """Put a part's PMI into its native FreeCAD model through the MBD Workbench.

        native: sandbox path of the FCStd; part: the name of its object holding the
        part's one solid; pmi: sandbox path of the -pmi.json draw_part wrote from
        that part's STEP. Writes <part>-mbd.FCStd, with the Workbench's datum,
        dimension and frame objects on the part's faces, and <part>-mbd.step, its
        AP242 export, under mbd/<part>/. The Workbench follows ASME Y14.5 and holds
        less than draw_part's AP242: not_carried lists what it left out, and
        differences how its export reads back against the PMI it was given.
        """
        if not available():
            raise RuntimeError(
                f"The MBD Workbench ({WORKBENCH}) or pythonocc-core ({PYTHONOCC}) is "
                "not installed; see guacamole/integrations/mbd.py"
            )
        out = project.output_path(Path("mbd") / part)
        out.mkdir(parents=True, exist_ok=True)
        given = PMI.model_validate_json(
            project.output_path(Path(pmi)).read_text(encoding="utf-8")
        )
        result = await export(given, project.output_path(Path(native)), part, out)
        step = out / f"{part}-mbd.step"
        exported = result["exported"] and step.is_file()
        return MBDAnnotation(
            exported=exported,
            fcstd=ProducedFile.from_path(out / f"{part}-mbd.FCStd"),
            step=ProducedFile.from_path(step) if exported else None,
            not_carried=tuple(result["not_carried"]),
            issues=tuple(result["issues"]),
            differences=tuple(check(result, step)) if exported else (),
        )

    # Workbench errors hold no secrets; agents fix calls with them.
    project.tools.register(mbd_annotate, show_errors=True)
