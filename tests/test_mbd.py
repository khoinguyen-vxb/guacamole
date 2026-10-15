import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

from examples import mbd
from examples.bracket import bracket
from examples.drafting import PMI
from guacamole import Project, ToolRegistry


@unittest.skipUnless(
    bracket.FREECAD
    and mbd.available()
    and all(map(importlib.util.find_spec, ("ezdxf", "OCP"))),
    "needs FreeCAD, the MBD Workbench and pythonocc-core (see examples/mbd.py) "
    "and the bracket extra (ezdxf, OCP)",
)
class MBDWorkbenchTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_bracket_pmi_goes_through_the_workbench_and_reads_back(self):
        # Snap and Flatpak FreeCAD builds see $HOME but not /tmp.
        cache = Path.home() / ".cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            root = Path(directory)
            with Project(
                root / "state", sandbox=root / "results", tools=ToolRegistry()
            ) as project:
                bracket.register_tools(project)
                design = {
                    "material": "aluminium-6061-t6",
                    "width_mm": 60,
                    "thickness_mm": 8,
                    "wall_leg_mm": 100,
                    "shelf_leg_mm": 180,
                    "fastener": "M6",
                    "holes_per_leg": 2,
                }
                built = await project.call(
                    project.tools.get("bracket_generate@1"),
                    {"design": design, "name": "shelf"},
                )
            assert built.files is not None
            pmi = PMI.model_validate_json(Path(built.files.pmi.path).read_text())
            native = Path(built.files.native.path)
            result = await mbd.export(pmi, native, "Bracket", root)
            self.assertTrue(result["exported"], result)
            self.assertEqual(result["issues"], [])
            self.assertTrue((root / "Bracket-mbd.FCStd").exists())
            written = result["pmi"]
            self.assertEqual(written["datums"], pmi.datums)
            self.assertEqual(written["sizes"], [])  # H13 is an ISO 286 class
            self.assertEqual(  # One position frame per hole
                sorted(t["feature"] for t in written["tolerances"]),
                ["shelf_holes 1", "shelf_holes 2", "wall_holes 1", "wall_holes 2"],
            )
            self.assertEqual(
                len(result["not_carried"]), 5
            )  # 2 classes, 2 patterns, 22081
            # FreeCAD 1.1's OCCT 7.8.0 attaches no face to a datum on a plane bounded
            # by one loop (OCCT 7.9 does): datum C on the side face, and the frames
            # citing C then read back unattached. Every difference involves datum C.
            differences = mbd.check(result, root / "Bracket-mbd.step")
            self.assertTrue(
                all(re.search(r"\bC\b", d) for d in differences), differences
            )
