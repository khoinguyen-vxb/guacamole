import importlib.util
import math
import os
import tempfile
import unittest
from pathlib import Path

from examples import drafting
from examples.drafting import Location, Size, Target, Tolerance

NIST = os.environ.get("GUACAMOLE_NIST_PMI")  # NIST-PMI-STEP-Files, unzipped


def plate(directory):
    """TEST FIXTURE: a 40 x 5 x 60 mm plate as STEP.

    Two 6.6 and two 4.5 mm holes, a 10 mm boss with a 4 mm bore through it, a 6 mm
    slot down from the top and an R3 round on the top far edge.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.STEPControl import STEPControl_StepModelType, STEPControl_Writer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    def cylinder(x, y, z, d, length):
        return BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 1, 0)), d / 2, length
        ).Shape()

    shape = BRepPrimAPI_MakeBox(40, 5, 60).Shape()
    rounded = BRepFilletAPI_MakeFillet(shape)
    edges = TopExp_Explorer(shape, TopAbs_EDGE)
    while edges.More():  # The edge along y at x = 40, z = 60
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(edges.Current()))
        middle = curve.Value((curve.FirstParameter() + curve.LastParameter()) / 2)
        if abs(middle.X() - 40) < 1e-9 and abs(middle.Z() - 60) < 1e-9:
            rounded.Add(3.0, TopoDS.Edge_s(edges.Current()))
        edges.Next()
    shape = BRepAlgoAPI_Fuse(rounded.Shape(), cylinder(20, 5, 35, 10, 7)).Shape()
    for x, z, d in ((10, 50, 6.6), (30, 50, 6.6), (10, 20, 4.5), (30, 20, 4.5)):
        shape = BRepAlgoAPI_Cut(shape, cylinder(x, -1, z, d, 7)).Shape()
    shape = BRepAlgoAPI_Cut(shape, cylinder(20, -1, 35, 4, 14)).Shape()
    slot = BRepPrimAPI_MakeBox(gp_Pnt(17, -1, 52), gp_Pnt(23, 6, 61)).Shape()
    shape = BRepAlgoAPI_Cut(shape, slot).Shape()
    path = Path(directory) / "plate.step"
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_StepModelType.STEPControl_AsIs)
    writer.Write(str(path))
    return path


def plane(normal, offset):
    return {"kind": "plane", "normal": normal, "offset": offset}


SPECS = {
    "wall": plane([0, -1, 0], 0),
    "inner": plane([0, 1, 0], 5),
    "base": plane([0, 0, -1], 0),
    "top": plane([0, 0, 1], 60),
    "side": plane([-1, 0, 0], 0),
    "far": plane([1, 0, 0], 40),
    "big": {"kind": "holes", "axis": [0, 1, 0], "diameter": 6.6},
    "small": {"kind": "holes", "axis": [0, 1, 0], "diameter": 4.5},
    "boss": {"kind": "shafts", "axis": [0, 1, 0], "diameter": 10},
    "bore": {"kind": "holes", "axis": [0, 1, 0], "diameter": 4},
    "slot": {
        "kind": "width",
        "normal": [1, 0, 0],
        "offset": 20,
        "width": 6,
        "internal": True,
    },
    "round": {  # A quarter of an R3 cylinder, 5 long, about the line x 37, z 57
        "kind": "surfaces",
        "faces": [
            {
                "surface": "Cylinder",
                "point": [37 + 6 / math.pi, 2.5, 57 + 6 / math.pi],
                "area": 7.5 * math.pi,
            }
        ],
    },
}


def matrix(features):
    """The declared supported matrix: every characteristic, zone and modifier carried."""
    return drafting.PMI(
        features=features,
        datums={"A": "wall", "B": "base", "C": "side", "D": "bore", "E": "inner"},
        targets={  # E1 to E4 on the inner face, one of each kind
            "E": (
                Target(kind="point", point=(5, 5, 5), normal=(0, 1, 0)),
                Target(
                    kind="line",
                    point=(20, 5, 5),
                    normal=(0, 1, 0),
                    direction=(1, 0, 0),
                    length=10,
                ),
                Target(
                    kind="rectangle",
                    point=(35, 5, 40),
                    normal=(0, 1, 0),
                    direction=(0, 0, 1),
                    length=4,
                    width=2,
                ),
                Target(kind="circle", point=(5, 5, 40), normal=(0, 1, 0), length=3),
            )
        },
        sizes=(
            Size(feature="big", fit="H13"),
            Size(feature="small", upper=0.1, lower=0.0),
            Size(feature="boss", fit="h9"),
            Size(feature="slot", fit="H11"),
            Size(feature="round", upper=0.2, lower=-0.2),
        ),
        locations=(
            Location(between=("base", "top"), upper=0.2, lower=-0.2),
            Location(between=("far", "bore"), upper=0.1, lower=-0.1),
        ),
        tolerances=(
            Tolerance(
                feature="big",
                characteristic="position",
                value=0.6,
                diameter=True,
                material="M",
                datums=("A", "B", "C"),
            ),
            Tolerance(
                feature="small",
                characteristic="position",
                value=0.3,
                diameter=True,
                material="L",
                datums=("B", "A", "C"),
            ),
            Tolerance(
                feature="big",
                characteristic="perpendicularity",
                value=0.0,
                diameter=True,
                material="M",
                datums=("A",),
            ),
            Tolerance(feature="wall", characteristic="flatness", value=0.1),
            Tolerance(
                feature="inner", characteristic="parallelism", value=0.2, datums=("A",)
            ),
            Tolerance(
                feature="base",
                characteristic="perpendicularity",
                value=0.3,
                datums=("A",),
            ),
            Tolerance(
                feature="top",
                characteristic="profile_surface",
                value=0.5,
                datums=("A", "B"),
            ),
            Tolerance(feature="far", characteristic="profile_surface", value=1.0),
            Tolerance(
                feature="boss",
                characteristic="coaxiality",
                value=0.05,
                diameter=True,
                datums=("D",),
            ),
            Tolerance(
                feature="boss",
                characteristic="position",
                value=0.1,
                diameter=True,
                material="M",
                datums=("A", "D"),
                datum_material={"D": "M"},
            ),
            Tolerance(
                feature="bore",
                characteristic="position",
                value=0.2,
                diameter=True,
                material="M",
                datums=("A", "B", "C"),
                projected=10.0,
            ),
            Tolerance(
                feature="slot", characteristic="symmetry", value=0.1, datums=("C",)
            ),
            Tolerance(
                feature="boss", characteristic="total_runout", value=0.05, datums=("D",)
            ),
            # Every modifier, each on a frame it suits.
            Tolerance(
                feature="round",
                characteristic="profile_line",
                value=0.3,
                modifiers=("all_around",),
            ),
            Tolerance(
                feature="top",
                characteristic="profile_surface",
                value=0.8,
                modifiers=("all_over", "statistical"),
            ),
            Tolerance(
                feature="boss",
                characteristic="cylindricity",
                value=0.02,
                modifiers=("any_cross_section", "free_state"),
            ),
            Tolerance(
                feature="big",
                characteristic="position",
                value=0.2,
                diameter=True,
                material="M",
                datums=("A",),
                modifiers=("common_zone", "reciprocity", "separate_requirement"),
            ),
            Tolerance(
                feature="base",
                characteristic="straightness",
                value=0.05,
                modifiers=("line_element",),
            ),
            Tolerance(
                feature="far",
                characteristic="parallelism",
                value=0.15,
                datums=("C",),
                modifiers=("tangent_plane",),
            ),
            Tolerance(
                feature="far",
                characteristic="perpendicularity",
                value=0.25,
                datums=("E",),
            ),
        ),
        general=drafting.General(size=0.5, profile=1.0, datums=("A", "B", "C")),
    )


@unittest.skipUnless(importlib.util.find_spec("OCP"), "needs OCP (--extra bracket)")
class AP242Tests(unittest.TestCase):
    def setUp(self):
        from examples import ap242

        self.ap242 = ap242
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        features, failed = drafting.features(
            ap242.fingerprints(plate(self.directory), SPECS)
        )
        self.assertEqual(failed, [])
        self.pmi = matrix(features)
        self.step = self.directory / "plate-ap242.step"
        self.omitted = ap242.write(self.pmi, self.directory / "plate.step", self.step)

    def test_the_supported_matrix_round_trips_exactly(self):
        found = self.ap242.read(self.step)
        # OCCT's writer drops projected zones, all around and all over; write() lists
        # them, and everything else comes back exactly.
        carried = self.pmi.model_copy(
            update={
                "tolerances": tuple(
                    t.model_copy(
                        update={
                            "projected": None,
                            "modifiers": tuple(
                                m
                                for m in t.modifiers
                                if m not in ("all_around", "all_over")
                            ),
                        }
                    )
                    for t in self.pmi.tolerances
                )
            }
        )
        self.assertEqual(self.ap242.compare(carried, found), [])
        frames = [o for o in self.omitted if " of " in o.split(":")[0]]
        self.assertEqual(
            sorted(o.split(":")[1].split(",")[0].strip() for o in frames),
            ["all_around", "all_over", "projected zone 10"],
        )
        self.assertEqual(
            found.constructs,
            len(found.sizes)
            + len(found.locations)
            + len(found.tolerances)
            + (found.general is not None)
            + found.presentation,
        )
        # The ISO 286 grade is right in the file, despite OCCT's writer (see write()).
        self.assertIn("LIMITS_AND_FITS('H','hole','13'", self.step.read_text())
        # Every construct carries graphical PMI linked to it (CAx-IF PMI 4.1, 8).
        self.assertEqual(found.presented, found.constructs)
        self.assertEqual(
            self.step.read_text().count("'PMI representation to presentation link'"),
            found.constructs + len(self.pmi.datums),
        )
        self.assertEqual(self.pmi.features["boss"].kind, "shafts")
        self.assertEqual(self.pmi.features["round"].radius, 3.0)
        self.assertIn("ISO 22081", self.omitted[0])

    def test_an_edited_file_reads_back_as_it_now_says(self):
        text = self.step.read_text()
        for old, new in (
            (".MAXIMUM_MATERIAL_REQUIREMENT.", ".LEAST_MATERIAL_REQUIREMENT."),
            ("'H','hole','13'", "'H','hole','11'"),
        ):
            self.assertIn(old, text)
            text = text.replace(old, new, 1)
        self.step.write_text(text)
        differences = self.ap242.compare(self.pmi, self.ap242.read(self.step))
        self.assertIn(
            "size of big: diameter 6.6 H11: in the file, not in the PMI", differences
        )
        self.assertTrue(any(" L | " in d and "in the file" in d for d in differences))

    def test_constructs_outside_the_typed_pmi_are_listed_never_dropped(self):
        text = self.step.read_text()
        old = "(.MAXIMUM_MATERIAL_REQUIREMENT.)"
        self.assertIn(old, text)
        radial = "(.MAXIMUM_MATERIAL_REQUIREMENT.,.EACH_RADIAL_ELEMENT.)"
        self.step.write_text(text.replace(old, radial, 1))
        found = self.ap242.read(self.step)
        self.assertEqual(
            found.constructs,
            len(found.sizes)
            + len(found.locations)
            + len(found.tolerances)
            + (found.general is not None)
            + len(found.unmapped)
            + found.presentation,
        )
        self.assertTrue(
            any("Each_Radial_Element" in u for u in found.unmapped), found.unmapped
        )
        differences = self.ap242.compare(self.pmi, found)
        self.assertTrue(any(d.startswith("not mapped: Position") for d in differences))
        # A PMI outside the supported subset is refused, not written in part.
        around = Tolerance(
            feature="wall",
            characteristic="flatness",
            value=0.1,
            modifiers=("all_around",),
        )
        unsupported = self.pmi.model_copy(update={"tolerances": (around,)})
        with self.assertRaisesRegex(ValueError, "apply to profiles"):
            self.ap242.write(unsupported, self.directory / "plate.step", self.step)

    @unittest.skipUnless(NIST, "set GUACAMOLE_NIST_PMI to NIST's PMI STEP files")
    def test_every_construct_of_the_nist_files_is_mapped_or_listed(self):
        files = sorted(Path(NIST).glob("*ap242-e*.stp"))
        self.assertTrue(files)
        for path in files:
            found = self.ap242.read(path)
            self.assertEqual(
                found.constructs,
                len(found.sizes)
                + len(found.locations)
                + len(found.tolerances)
                + (found.general is not None)
                + len(found.unmapped)
                + found.presentation,
                path.name,
            )
        # CTC 4 against NIST's drawing of it.
        found = self.ap242.read(Path(NIST) / "nist_ctc_04_asme1_ap242-e1.stp")
        sizes = {(round(n, 3), s.upper, s.lower) for s, n in found.sizes}
        self.assertLessEqual({(6.65, 0.12, -0.12), (14.0, 0.1, -0.1)}, sizes)
        frames = {(t.characteristic, t.value, t.datums) for t in found.tolerances}
        self.assertLessEqual(
            {
                ("position", 1.5, ("D", "E", "F")),
                ("position", 0.3, ("D", "E")),
                ("position", 0.35, ("A", "B", "C")),
                ("profile_surface", 0.5, ("A", "B", "C")),
            },
            frames,
        )
        self.assertEqual(sorted(found.datums), list("ABCDEFGH"))


if __name__ == "__main__":
    unittest.main()
