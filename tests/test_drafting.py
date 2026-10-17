import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

from guacamole.integrations.lib import drafting
from guacamole.integrations.lib.drafting import Holes, Plane, Tolerance


def plate():
    """TEST FIXTURE: a 40 x 5 x 60 mm plate with two 6.6 mm holes through it.

    Model axes as the bracket's: x along the wall, y out of it, z up."""
    features = {
        "wall_face": Plane(point=(20, 0, 30), normal=(0, -1, 0), area=2400),
        "inner": Plane(point=(20, 5, 30), normal=(0, 1, 0), area=2400),
        "base": Plane(point=(20, 2.5, 0), normal=(0, 0, -1), area=200),
        "top": Plane(point=(20, 2.5, 60), normal=(0, 0, 1), area=200),
        "side": Plane(point=(0, 2.5, 30), normal=(-1, 0, 0), area=300),
        "far": Plane(point=(40, 2.5, 30), normal=(1, 0, 0), area=300),
        "holes": Holes(
            axis=(0, 1, 0),
            diameter=6.6,
            centers=((10, 2.5, 50), (30, 2.5, 50)),
            length=5,
        ),
    }

    def box(u0, v0, u1, v1):
        return [[u0, v0, u1, v0], [u1, v0, u1, v1], [u1, v1, u0, v1], [u0, v1, u0, v0]]

    def edges(lines=(), circles=()):
        return {"lines": [*lines], "circles": [*circles], "polylines": []}

    views = {  # u = rows[0] . p, v = rows[1] . p, as freecad_bracket.project gives them
        "FRONT": {
            "rows": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
            "visible": edges(box(-40, 0, 0, 60), [[-10, 50, 3.3], [-30, 50, 3.3]]),
            "hidden": edges(),
        },
        "TOP": {
            "rows": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
            "visible": edges(box(-40, -5, 0, 0)),
            "hidden": edges([[u, -5, u, 0] for u in (-13.3, -6.7, -33.3, -26.7)]),
        },
        "RIGHT": {
            "rows": ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
            "visible": edges(box(-5, 0, 0, 60)),
            "hidden": edges([[-5, v, 0, v] for v in (46.7, 53.3)]),
        },
    }
    return features, views


def slotted():
    """TEST FIXTURE: the 40 x 5 x 60 plate with a 6 mm slot down from the top, an R3
    round on the top far edge and one 4 mm bore, with a PMI using each of them."""
    features = {
        "wall_face": Plane(point=(20, 0, 30), normal=(0, -1, 0), area=2300),
        "inner": Plane(point=(20, 5, 30), normal=(0, 1, 0), area=2300),
        "base": Plane(point=(20, 2.5, 0), normal=(0, 0, -1), area=200),
        "top": Plane(point=(20, 2.5, 60), normal=(0, 0, 1), area=155),
        "side": Plane(point=(0, 2.5, 30), normal=(-1, 0, 0), area=300),
        "far": Plane(point=(40, 2.5, 28.5), normal=(1, 0, 0), area=285),
        "slot_bottom": Plane(point=(20, 2.5, 52), normal=(0, 0, 1), area=30),
        "slot": drafting.Width(
            normal=(1, 0, 0), center=(20, 2.5, 56), width=6, internal=True, area=40
        ),
        "round": drafting.Surfaces(
            faces=(
                drafting.Face(
                    surface="Cylinder",
                    point=(37 + 6 / math.pi, 2.5, 57 + 6 / math.pi),
                    area=7.5 * math.pi,
                ),
            ),
            radius=3,
        ),
        "bore": Holes(axis=(0, 1, 0), diameter=4, centers=((10, 2.5, 35),), length=5),
    }
    arc = [
        [-37 + 3 * math.cos(a), 57 + 3 * math.sin(a)]
        for a in (math.pi / 2 + k * math.pi / 16 for k in range(9))
    ]

    def edges(lines=(), circles=(), polylines=()):
        return {"lines": [*lines], "circles": [*circles], "polylines": [*polylines]}

    views = {
        "FRONT": {
            "rows": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
            "visible": edges(
                [
                    [-40, 0, 0, 0],
                    [0, 0, 0, 60],
                    [0, 60, -17, 60],
                    [-17, 60, -17, 52],
                    [-17, 52, -23, 52],
                    [-23, 52, -23, 60],
                    [-23, 60, -37, 60],
                    [-40, 57, -40, 0],
                ],
                [[-10, 35, 2]],
                [arc],
            ),
            "hidden": edges(),
        },
        "TOP": {
            "rows": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
            "visible": edges(
                [
                    [-40, -5, 0, -5],
                    [0, -5, 0, 0],
                    [0, 0, -40, 0],
                    [-40, 0, -40, -5],
                    *([u, -5, u, 0] for u in (-17, -23, -37)),
                ]
            ),
            "hidden": edges([[u, -5, u, 0] for u in (-8, -12)]),
        },
        "RIGHT": {
            "rows": ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
            "visible": edges(
                [[-5, 0, 0, 0], [0, 0, 0, 60], [0, 60, -5, 60], [-5, 60, -5, 0]]
            ),
            "hidden": edges([[-5, v, 0, v] for v in (33, 37, 52, 57)]),
        },
    }
    spec = drafting.PMI(
        features=features,
        datums={
            "A": "wall_face",
            "B": "base",
            "C": "side",
            "D": "bore",
            "E": "inner",
            "F": "slot",
        },
        targets={
            "E": (
                drafting.Target(kind="point", point=(5, 5, 5), normal=(0, 1, 0)),
                drafting.Target(
                    kind="line",
                    point=(20, 5, 5),
                    normal=(0, 1, 0),
                    direction=(1, 0, 0),
                    length=10,
                ),
                drafting.Target(
                    kind="rectangle",
                    point=(30, 5, 25),
                    normal=(0, 1, 0),
                    direction=(0, 0, 1),
                    length=4,
                    width=2,
                ),
                drafting.Target(
                    kind="circle", point=(5, 5, 40), normal=(0, 1, 0), length=3
                ),
            )
        },
        sizes=(
            drafting.Size(feature="bore", upper=0.05, lower=0.0),
            drafting.Size(feature="slot", fit="H11"),
            drafting.Size(feature="round", upper=0.2, lower=-0.2),
        ),
        locations=(
            drafting.Location(between=("side", "bore"), upper=0.1, lower=-0.1),
            drafting.Location(between=("top", "slot_bottom"), upper=0.2, lower=-0.2),
        ),
        tolerances=(
            Tolerance(
                feature="bore",
                characteristic="perpendicularity",
                value=0.05,
                diameter=True,
                datums=("A",),
            ),
            Tolerance(
                feature="slot", characteristic="symmetry", value=0.1, datums=("C",)
            ),
            Tolerance(
                feature="round", characteristic="profile_line", value=0.3, datums=("A",)
            ),
            Tolerance(
                feature="far",
                characteristic="perpendicularity",
                value=0.2,
                datums=("E",),
            ),
            Tolerance(
                feature="top",
                characteristic="perpendicularity",
                value=0.1,
                datums=("F",),
            ),
            Tolerance(
                feature="side", characteristic="parallelism", value=0.1, datums=("D",)
            ),
        ),
        general=drafting.General(size=0.5, profile=1.0, datums=("A", "B", "C")),
    )
    sheet = SHEET.model_copy(
        update={
            "dimensions": (),
            "callouts": (drafting.Callout(feature="bore", view="FRONT", side="left"),),
            "datum_views": {"A": "TOP", "B": "FRONT", "C": "FRONT", "E": "TOP"},
        }
    )
    return spec, sheet, views


def pmi(features, **changes):
    return drafting.PMI(
        features=features,
        datums={"A": "wall_face", "B": "base", "C": "side"},
        sizes=(drafting.Size(feature="holes", fit="H13"),),
        tolerances=(
            Tolerance(
                feature="holes",
                characteristic="position",
                value=0.6,
                diameter=True,
                material="M",
                datums=("A", "B", "C"),
            ),
            Tolerance(feature="wall_face", characteristic="flatness", value=0.1),
        ),
        general=drafting.General(size=0.5, profile=1.0, datums=("A", "B", "C")),
    ).model_copy(update=changes)


SHEET = drafting.Sheet(
    title="TEST FIXTURE PLATE",
    number="FIX-1",
    revision="A",
    date="2026-10-15",
    status="In review",
    owner="TEST FIXTURE",
    creator="test",
    material="TEST FIXTURE",
    mass_kg=0.1,
    revisions=(("A", "TEST FIXTURE", "2026-10-15"),),
    dimensions=(
        drafting.Between(planes=("side", "far"), view="FRONT", side="below"),
        drafting.Between(planes=("base", "top"), view="RIGHT", side="right"),
        drafting.Between(planes=("wall_face", "inner"), view="RIGHT", side="above"),
    ),
    callouts=(drafting.Callout(feature="holes", view="FRONT", side="left"),),
    datum_views={"A": "TOP", "B": "FRONT", "C": "FRONT"},
)


class DraftingTests(unittest.TestCase):
    def test_malformed_datum_references_and_unsupported_tolerances_are_flagged(self):
        features, _ = plate()
        self.assertEqual(drafting.problems(pmi(features)), [])
        found = drafting.problems(
            pmi(
                features,
                datums={"A": "wall_face", "B": "holes", "c": "side", "T": "wall_face"},
                targets={
                    "T": (  # The wall faces -y at y = 0
                        drafting.Target(
                            kind="line", point=(5, 0, 5), normal=(0, -1, 0), length=10
                        ),
                        drafting.Target(
                            kind="point", point=(5, 2, 5), normal=(0, -1, 0), width=1
                        ),
                    ),
                    "Z": (),
                },
                sizes=(
                    drafting.Size(feature="holes", fit="H13", upper=0.1, lower=0.0),
                    drafting.Size(feature="wall_face", fit="h13"),
                ),
                locations=(
                    drafting.Location(
                        between=("wall_face", "base"), upper=0.1, lower=-0.1
                    ),
                ),
                tolerances=(
                    Tolerance(
                        feature="holes",
                        characteristic="position",
                        value=0.6,
                        datums=("A", "D"),
                        datum_material={"A": "M"},
                    ),
                    Tolerance(
                        feature="wall_face",
                        characteristic="flatness",
                        value=0.1,
                        datums=("A",),
                    ),
                    Tolerance(
                        feature="side",
                        characteristic="concentricity",
                        value=0.1,
                        datums=("A",),
                    ),
                    Tolerance(
                        feature="inner",
                        characteristic="perpendicularity",
                        value=0.1,
                        diameter=True,
                        datums=("A", "A"),
                        projected=10.0,
                    ),
                    Tolerance(
                        feature="top",
                        characteristic="flatness",
                        value=0.1,
                        modifiers=("all_around",),
                    ),
                    Tolerance(
                        feature="holes", characteristic="cylindricity", value=0.0
                    ),
                    Tolerance(feature="nothing", characteristic="position", value=0.1),
                    Tolerance(
                        feature="holes",
                        characteristic="position",
                        value=0.6,
                        datums=("T",),
                        datum_material={"T": "M"},
                    ),
                ),
                general=drafting.General(size=0.5, profile=1.0, datums=("A", "E")),
            )
        )
        for message in (
            "datum 'c': use one capital letter",
            "size of holes: give an ISO 286 class or deviations",
            "size of wall_face: not a feature of size or a radius",
            "location of base from wall_face: not two parallel planes, axes or median planes",
            "position of holes: datum D is not indicated",
            "position of holes: datum A is no feature of size to modify",
            "flatness of wall_face: a form tolerance takes no datums",
            "flatness of wall_face: references its own datum A",
            "concentricity of side: does not apply to a plane feature",
            "perpendicularity of inner: datums A A repeat or exceed three",
            "perpendicularity of inner: a cylindrical zone needs an axis",
            "perpendicularity of inner: a projected zone needs the location or orientation of an axis",
            "flatness of top: all around and all over apply to profiles",
            "cylindricity of holes: a zero tolerance needs a material modifier",
            "position of nothing: no such feature",
            "general specification: datum E is not indicated",
            "datum target T1: a direction across the normal for lines and rectangles only",
            "datum target T2: a point takes no size",
            "datum target T2: not on wall_face, facing out of it",
            "datum Z: targets need an indicated datum, and one target",
            "position of holes: datum T rests on targets, not a size",
        ):
            self.assertIn(message, found)

    def test_features_the_model_no_longer_holds_are_reported(self):
        features, _ = plate()
        measured = dict(features)
        measured["holes"] = features["holes"].model_copy(
            update={"centers": ((10.0, 2.5, 51.0), (30.0, 2.5, 50.0))}
        )
        del measured["far"]
        self.assertEqual(
            drafting.moved(pmi(features), measured),
            [
                "far: not in the model as the PMI recorded it",
                "holes: not in the model as the PMI recorded it",
            ],
        )
        found, failed = drafting.features(
            {"top": features["top"].model_dump(mode="json"), "side": {"matches": 2}}
        )
        self.assertEqual(found, {"top": features["top"]})
        self.assertEqual(failed, ["side: 2 matches in the model, not exactly one"])

    @unittest.skipUnless(
        importlib.util.find_spec("ezdxf"), "needs ezdxf (--extra bracket)"
    )
    def test_a_compiled_drawing_shows_its_pmi_and_conformance_catches_edits(self):
        import ezdxf

        features, views = plate()
        spec = pmi(features)
        with tempfile.TemporaryDirectory() as directory:
            dxf, svg = Path(directory) / "plate.dxf", Path(directory) / "plate.svg"
            drafting.write(drafting.compile_drawing(spec, SHEET, views), dxf, svg)
            checks = drafting.conformance(dxf, spec)
            self.assertTrue(all(checks.values()), checks)
            self.assertIn("<svg", svg.read_text())
            # The same drawing on an upright A4 sheet, ISO 5457.
            a4, pdf = Path(directory) / "a4.dxf", Path(directory) / "a4.pdf"
            upright = SHEET.model_copy(update={"size": "A4"})
            drafting.write(drafting.compile_drawing(spec, upright, views), a4, svg, pdf)
            self.assertTrue(all(drafting.conformance(a4, spec).values()))
            self.assertIn(b"/MediaBox [0 0 595.276 841.89]", pdf.read_bytes())
            # First angle, ISO 5456-2: the end view of the symbol's cone moves to the
            # right of it, and the views move round the front view.
            first = SHEET.model_copy(update={"projection": "first"})
            drafting.write(drafting.compile_drawing(spec, first, views), a4, svg)
            self.assertTrue(all(drafting.conformance(a4, spec).values()))
            msp = ezdxf.readfile(a4).modelspace()
            notes = drafting.paper(*drafting.PAPER["A3"]).notes
            circles = [c.dxf.center.x for c in msp.query("CIRCLE[layer=='VISIBLE']")]
            cone = next(
                e
                for e in msp.query("LWPOLYLINE[layer=='VISIBLE']")
                if notes[0] < e.get_points("xy")[0][0] < notes[2]
            )
            self.assertGreater(
                min(x for x in circles if notes[0] < x < notes[2]),
                max(x for x, _ in cone.get_points("xy")),
            )
            # An edited frame value and a deleted datum no longer match the PMI.
            edited = ezdxf.readfile(dxf)
            msp = edited.modelspace()
            for ref in msp.query("INSERT"):
                if ref.dxf.name.startswith("FCF_"):
                    ref.get_attrib("VALUE").dxf.text = "9"
                elif ref.dxf.name == "DATUM_A":
                    msp.delete_entity(ref)
            edited.saveas(dxf)
            checks = drafting.conformance(dxf, spec)
            self.assertFalse(
                checks["drawing: every geometrical specification of the PMI is shown"]
            )
            self.assertFalse(
                checks[
                    "drawing: every datum a specification references is indicated (ISO 5459)"
                ]
            )
        # A malformed PMI or a callout across the hole axes is refused, not drawn.
        with self.assertRaisesRegex(ValueError, "datum D is not indicated"):
            drafting.compile_drawing(
                pmi(
                    features, general=spec.general.model_copy(update={"datums": ("D",)})
                ),
                SHEET,
                views,
            )
        across = SHEET.model_copy(
            update={
                "callouts": (
                    drafting.Callout(feature="holes", view="TOP", side="left"),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "does not look along"):
            drafting.compile_drawing(spec, across, views)

    @unittest.skipUnless(
        importlib.util.find_spec("ezdxf"), "needs ezdxf (--extra bracket)"
    )
    def test_widths_radii_locations_and_datum_targets_are_drawn(self):
        import ezdxf

        spec, sheet, views = slotted()
        with tempfile.TemporaryDirectory() as directory:
            dxf, svg = Path(directory) / "slot.dxf", Path(directory) / "slot.svg"
            pdf = Path(directory) / "slot.pdf"
            drafting.write(drafting.compile_drawing(spec, sheet, views), dxf, svg, pdf)
            checks = drafting.conformance(dxf, spec)
            self.assertTrue(all(checks.values()), checks)
            data = pdf.read_bytes()  # One A3 page, its cross-reference table found
            self.assertTrue(data.startswith(b"%PDF-1.4") and data.endswith(b"%%EOF\n"))
            self.assertIn(b"/MediaBox [0 0 1190.551 841.89]", data)
            xref = int(data.rsplit(b"startxref\n", 1)[1].split()[0])
            self.assertTrue(data[xref:].startswith(b"xref"))
            shown = {e.dxf.text for e in ezdxf.readfile(dxf).modelspace().query("TEXT")}
            self.assertLessEqual({"6 H11", "R3 ±0.2", "10 ±0.1", "8 ±0.2"}, shown)
            # A deleted datum target is caught.
            edited = ezdxf.readfile(dxf)
            msp = edited.modelspace()
            for ref in msp.query("INSERT"):
                if ref.dxf.name == "TARGET_E2":
                    msp.delete_entity(ref)
            edited.saveas(dxf)
            self.assertFalse(
                drafting.conformance(dxf, spec)[
                    "drawing: every datum a specification references is indicated (ISO 5459)"
                ]
            )
        # A position frame and a toleranced distance on the same feature conflict.
        position = Tolerance(
            feature="bore",
            characteristic="position",
            value=0.2,
            diameter=True,
            datums=("A", "B", "C"),
        )
        doubled = spec.model_copy(update={"tolerances": (*spec.tolerances, position)})
        self.assertIn(
            "location of bore from side: the position of bore already locates it "
            "from side",
            drafting.problems(doubled),
        )

    @unittest.skipUnless(
        importlib.util.find_spec("ezdxf"), "needs ezdxf (--extra bracket)"
    )
    def test_iso_pmi_restated_for_asme_keeps_its_meaning_and_draws(self):
        import ezdxf

        spec, sheet, views = slotted()
        asme, notes = drafting.translate(spec, drafting.ASME)
        self.assertEqual(drafting.problems(asme), [])
        self.assertIn("symmetry of slot: becomes position", notes)
        # ISO 8015 independency survives Rule #1 as Ⓘ on each feature of size.
        self.assertEqual(
            {s.feature: s.requirement for s in asme.sizes},
            {"bore": "independency", "slot": "independency", "round": ""},
        )
        self.assertIn(
            "symmetry of slot: ASME Y14.5-2018 has no symmetry",
            drafting.problems(spec.model_copy(update={"profile": drafting.ASME})),
        )
        back, _ = drafting.translate(asme, drafting.PROFILE)
        self.assertEqual([s.requirement for s in back.sizes], ["", "", ""])
        with tempfile.TemporaryDirectory() as directory:
            dxf, svg = Path(directory) / "asme.dxf", Path(directory) / "asme.svg"
            drafting.write(drafting.compile_drawing(asme, sheet, views), dxf, svg)
            self.assertTrue(all(drafting.conformance(dxf, asme).values()))
            texts = {
                e.dxf.text: e.dxf.rotation
                for e in ezdxf.readfile(dxf).modelspace().query("TEXT")
            }
            self.assertIn("ASME Y14.5-2018", texts)
            self.assertEqual(texts["8 ±0.2"], 0.0)  # Unidirectional, read from below


if __name__ == "__main__":
    unittest.main()
