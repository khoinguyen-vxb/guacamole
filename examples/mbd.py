"""The FreeCAD MBD Workbench as a second AP242 writer for the PMI.

Example tooling around https://github.com/ChipsWoodShop/FreeCAD-MBDWorkbench (LGPL-2.1,
early preview, ASME Y14.5). export() runs mbd_freecad.py in headless FreeCAD to put
the PMI on the native model's faces as the Workbench's objects, save that model and
write AP242 with the Workbench's exporter. check() reads the file back with
ap242.read(), which shares no code with the Workbench, and compares it with the PMI
as the Workbench was given it to write.

The Workbench's exporter needs pythonocc-core inside FreeCAD. For the snap FreeCAD
(OCCT 7.8) a conda environment with pythonocc-core 7.8.1 works: its modules bind to
FreeCAD's own OCCT libraries. Set PYTHONOCC and WORKBENCH below.
"""

import json
from pathlib import Path

from examples import ap242
from examples.bracket.bracket import freecad
from examples.drafting import PMI

SCRIPT = Path(__file__).with_name("mbd_freecad.py")
PYTHONOCC = Path.home() / "miniconda3/envs/mbd-occ/lib/python3.12/site-packages"
WORKBENCH = Path.home() / "snap/freecad/common/Mod/MBDWorkbench"


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
    return await freecad(
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
