import re
import tempfile
import unittest
from pathlib import Path

from guacamole import Project
from guacamole.integrations import ap242, mbd
from guacamole.integrations.freecad import FREECAD, run_job

NATIVE = """import json, os
import FreeCAD as App, Part
job = json.load(open(os.environ["GUACAMOLE_JOB"]))
doc = App.newDocument("Plate")
doc.addObject("Part::Feature", "Plate").Shape = Part.read(job["step"])
doc.recompute()
doc.saveAs(job["fcstd"])
json.dump({}, open(job["result"], "w"))
"""


def plate(path: Path) -> None:
    """TEST FIXTURE: an 80 x 60 x 10 mm plate with two 9 mm through holes, as STEP."""
    ocp = ap242._ocp()
    import OCP.BRepAlgoAPI
    import OCP.BRepPrimAPI
    import OCP.gp

    shape = OCP.BRepPrimAPI.BRepPrimAPI_MakeBox(80.0, 60.0, 10.0).Shape()
    for x in (20.0, 60.0):
        axis = OCP.gp.gp_Ax2(OCP.gp.gp_Pnt(x, 30.0, -1.0), OCP.gp.gp_Dir(0, 0, 1))
        hole = OCP.BRepPrimAPI.BRepPrimAPI_MakeCylinder(axis, 4.5, 12.0).Shape()
        shape = OCP.BRepAlgoAPI.BRepAlgoAPI_Cut(shape, hole).Shape()
    writer = ocp.STEPControl.STEPControl_Writer()
    writer.Transfer(shape, ocp.STEPControl.STEPControl_AsIs)
    writer.Write(str(path))


def plane(normal, offset):
    return {"kind": "plane", "normal": normal, "offset": offset}


@unittest.skipUnless(FREECAD, "needs FreeCAD (freecadcmd or freecad.cmd)")
class DrawPartTests(unittest.IsolatedAsyncioTestCase):
    async def test_any_projects_agents_draw_a_one_part_step_to_iso_gps(self):
        # Snap and Flatpak FreeCAD builds see $HOME but not /tmp.
        cache = Path.home() / ".cache"
        cache.mkdir(exist_ok=True)
        with (
            tempfile.TemporaryDirectory(dir=cache) as directory,
            Project(Path(directory)) as project,
        ):
            plate(project.sandbox / "plate.step")
            tool = project.tools.get("draw_part@1")
            datums = ["A", "B", "C"]
            payload = {
                "step": "plate.step",
                "pmi": {
                    "features": {
                        "base": plane([0, 0, -1], 0),
                        "top": plane([0, 0, 1], 10),
                        "front": plane([0, -1, 0], 0),
                        "back": plane([0, 1, 0], 60),
                        "left": plane([-1, 0, 0], 0),
                        "right": plane([1, 0, 0], 80),
                        "holes": {"kind": "holes", "axis": [0, 0, 1], "diameter": 9},
                    },
                    "datums": {"A": "base", "B": "front", "C": "left"},
                    "sizes": [{"feature": "holes", "fit": "H13"}],
                    "tolerances": [
                        {
                            "feature": "holes",
                            "characteristic": "position",
                            "value": 0.5,
                            "diameter": True,
                            "material": "M",
                            "datums": datums,
                        }
                    ],
                    "general": {"size": 0.5, "profile": 1, "datums": datums},
                },
                "sheet": {
                    "title": "TEST FIXTURE PLATE",
                    "number": "PLT-1",
                    "revision": "A",
                    "date": "2026-10-17",
                    "status": "In review",
                    "owner": "TEST FIXTURE",
                    "creator": "test",
                    "material": "EN AW-6061-T6",
                    "mass_kg": 0.12,
                    "revisions": [["A", "First issue", "2026-10-17"]],
                    "dimensions": [
                        {"planes": ["left", "right"], "view": "FRONT", "side": "below"},
                        {"planes": ["base", "top"], "view": "FRONT", "side": "right"},
                        {"planes": ["front", "back"], "view": "TOP", "side": "right"},
                    ],
                    "callouts": [{"feature": "holes", "view": "TOP", "side": "left"}],
                },
            }
            drawn = tool.result(await tool.function(**tool.arguments(payload)))
            self.assertEqual(drawn.problems, ())
            self.assertTrue(drawn.checks and all(drawn.checks.values()), drawn.checks)
            self.assertEqual(drawn.differences, ())
            self.assertTrue(
                all(
                    (project.sandbox / f.path).is_file()
                    for f in dict(drawn.files).values()
                )
            )
            if not mbd.available():
                return
            # The same PMI into a native model of the plate, through the Workbench.
            script = Path(directory) / "native.py"
            script.write_text(NATIVE)
            await run_job(
                {
                    "step": str(project.sandbox / "plate.step"),
                    "fcstd": str(project.sandbox / "plate.FCStd"),
                },
                Path(directory),
                script,
            )
            annotated = await project.call(
                project.tools.get("mbd_annotate@1"),
                {
                    "native": "plate.FCStd",
                    "part": "Plate",
                    "pmi": "drawings/PLT-1/PLT-1-pmi.json",
                },
            )
            self.assertTrue(annotated.exported, annotated)
            self.assertEqual(annotated.issues, ())
            # FreeCAD 1.1's OCCT 7.8.0 attaches no face to a datum on a plane bounded
            # by one loop (test_mbd.py): here B and C, the plain side faces.
            self.assertTrue(
                all(re.search(r"\b[BC]\b", d) for d in annotated.differences),
                annotated.differences,
            )
