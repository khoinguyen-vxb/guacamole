"""Runs inside headless FreeCAD: writes a part's PMI through the MBD Workbench.

mbd.py writes a job file and names it in GUACAMOLE_JOB: the native model and the part
to annotate, the PMI as JSON, the output paths, and where pythonocc-core and the
Workbench are. The part's solid is copied alone into a new document, because the
Workbench exports every solid it finds. Each PMI feature is found among its faces by
its fingerprint, the Workbench's datum, datum system, dimension and frame objects
are created on those faces, its validation runs, its exporter writes AP242 and the
annotated document is saved. The result holds the PMI as written, in the PMI schema,
and a sentence for everything the Workbench could not hold.
"""

import json
import os
import sys

import FreeCAD as App
import Part

with open(os.environ["GUACAMOLE_JOB"], encoding="utf-8") as f:
    job = json.load(f)
sys.path.append(job["pythonocc"])  # The Workbench's exporter needs pythonocc-core
sys.path.insert(0, job["workbench"])

from freecad.mbd_workbench import MBDExporter, MBDValidation
from freecad.mbd_workbench.MBDCommands import create_dimension_object
from freecad.mbd_workbench.MBDDatum import (
    MBDDatumFeature,
    update_geometry_signature,
)
from freecad.mbd_workbench.MBDDatumSystem import (
    MBDDatumSystem,
    synchronize_datum_system_label,
)
from freecad.mbd_workbench.MBDFeatureControlFrame import (
    MBDFeatureControlFrame,
)

# ISO 1101 characteristic: the Workbench's tolerance type. It follows ASME Y14.5-2018,
# which has no concentricity, coaxiality or symmetry.
TYPES = {
    "position": "Position",
    "flatness": "Flatness",
    "parallelism": "Parallelism",
    "perpendicularity": "Perpendicularity",
    "angularity": "Angularity",
    "straightness": "Straightness",
    "circularity": "Circularity",
    "cylindricity": "Cylindricity",
    "circular_runout": "CircularRunout",
    "total_runout": "TotalRunout",
    "profile_line": "LineProfile",
    "profile_surface": "Profile",
}
MODIFIERS = {  # PMI modifier: the frame property that carries it
    "tangent_plane": "TangentPlaneModifier",
    "statistical": "StatisticalToleranceModifier",
    "common_zone": "CommonZoneModifier",
    "all_over": "ProfileAllOver",
}
MATERIAL = {"": "None", "M": "MMC", "L": "LMC"}


def elements(shape, feature):
    """The faces of each element of a feature: the plane, or each hole or shaft."""
    if feature["kind"] == "plane":
        normal = App.Vector(*feature["normal"])
        offset = App.Vector(*feature["point"]).dot(normal)
        names = []
        for i, face in enumerate(shape.Faces, start=1):
            if not isinstance(face.Surface, Part.Plane):
                continue
            u0, u1, v0, v1 = face.ParameterRange
            n = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if (n - normal).Length < 1e-6 and abs(
                face.CenterOfMass.dot(normal) - offset
            ) < 1e-4:
                names.append(f"Face{i}")
        return [names]
    if feature["kind"] not in ("holes", "shafts"):
        return []  # Widths and surface sets are not located here
    axis = App.Vector(*feature["axis"])
    feet = [
        App.Vector(*c) - axis * App.Vector(*c).dot(axis) for c in feature["centers"]
    ]
    found = [[] for _ in feet]
    for i, face in enumerate(shape.Faces, start=1):
        surface = face.Surface
        if (
            isinstance(surface, Part.Cylinder)
            and abs(abs(surface.Axis.dot(axis)) - 1) < 1e-6
            and abs(2 * surface.Radius - feature["diameter"]) < 1e-4
        ):
            foot = surface.Center - axis * surface.Center.dot(axis)
            for k, f in enumerate(feet):
                if (foot - f).Length < 1e-4:
                    found[k].append(f"Face{i}")
    return found


def annotate(doc, part, pmi, lost):
    """Create the Workbench's objects for the PMI; return the PMI as written."""
    written = {
        **pmi,
        "features": {},
        "datums": {},
        "sizes": [],
        "locations": [],
        "tolerances": [],
    }
    # Feature name: (name as written, face) per element. The Workbench puts each
    # dimension and frame on one face, so a pattern becomes one feature per element.
    split = {}
    for name, feature in pmi["features"].items():
        groups = elements(part.Shape, feature)
        if not groups or any(len(g) != 1 for g in groups):
            lost.append(f"{name}: not one face per element of the part")
        elif len(groups) == 1:
            split[name] = [(name, groups[0][0])]
            written["features"][name] = feature
        else:
            split[name] = [(f"{name} {k}", g[0]) for k, g in enumerate(groups, start=1)]
            for k, center in enumerate(feature["centers"], start=1):
                written["features"][f"{name} {k}"] = {**feature, "centers": [center]}

    datums = {}
    for letter, name in sorted(pmi["datums"].items()):
        if len(split.get(name, ())) != 1:
            lost.append(f"datum {letter}: {name} is not one face")
            continue
        d = doc.addObject(
            "App::DocumentObjectGroupPython", f"MBD_DatumFeature_{letter}"
        )
        MBDDatumFeature(d)
        d.DatumLabel = letter
        d.DatumType = "Plane" if pmi["features"][name]["kind"] == "plane" else "Axis"
        d.ReferencedObject, d.ReferencedSubelement = part, split[name][0][1]
        update_geometry_signature(d)
        datums[letter] = d
        written["datums"][letter] = name

    systems = {}

    def system(order):
        if order not in systems:
            s = doc.addObject(
                "App::FeaturePython", "MBD_DatumSystem_" + "_".join(order)
            )
            MBDDatumSystem(s)
            compartments = [[datums[letter]] for letter in order]
            compartments += [[]] * (3 - len(compartments))
            s.PrimaryDatums, s.SecondaryDatums, s.TertiaryDatums = compartments
            synchronize_datum_system_label(s)
            systems[order] = s
        return systems[order]

    for size in pmi["sizes"]:
        name = size["feature"]
        if size["fit"]:
            lost.append(
                f"size of {name}: {size['fit']}, an ISO 286 class it cannot state"
            )
        elif size["upper"] < 0 or size["lower"] > 0:
            lost.append(f"size of {name}: deviations on one side of nominal")
        elif pmi["features"][name]["kind"] not in ("holes", "shafts"):
            lost.append(f"size of {name}: only diameters are written here")
        elif name in split:
            equal = abs(size["upper"] + size["lower"]) < 1e-9
            for element, face in split[name]:
                create_dimension_object(
                    doc,
                    part,
                    face,
                    nominal=pmi["features"][name]["diameter"],
                    dimension_purpose="EqualBilateral" if equal else "UnequalBilateral",
                    dimension_kind="Diameter",
                    upper_tolerance=size["upper"],
                    lower_tolerance=-size["lower"],
                )
                written["sizes"].append({**size, "feature": element})

    for n, t in enumerate(pmi["tolerances"]):
        what = f"{t['characteristic']} of {t['feature']}"
        if t["characteristic"] not in TYPES:
            lost.append(f"{what}: ASME Y14.5-2018 and the Workbench have no such type")
        elif any(m not in MODIFIERS for m in t["modifiers"]) or t["datum_material"]:
            lost.append(
                f"{what}: a modifier or datum material requirement it cannot state"
            )
        elif any(letter not in datums for letter in t["datums"]):
            lost.append(f"{what}: a datum it could not indicate")
        elif t["feature"] in split:
            if len(split[t["feature"]]) > 1:
                lost.append(f"{what}: one frame per element, not one for the pattern")
            for k, (element, face) in enumerate(split[t["feature"]]):
                fcf = doc.addObject("App::FeaturePython", f"MBD_FCF_{n}_{k}")
                MBDFeatureControlFrame(fcf)
                fcf.ToleranceType, fcf.ToleranceValue = (
                    TYPES[t["characteristic"]],
                    t["value"],
                )
                fcf.DiameterZone = t["diameter"]
                fcf.MaterialConditionModifier = MATERIAL[t["material"]]
                if t["datums"]:
                    fcf.DatumSystem = system(tuple(t["datums"]))
                for modifier in t["modifiers"]:
                    setattr(fcf, MODIFIERS[modifier], True)
                if t["projected"] is not None:
                    fcf.ProjectedToleranceZone = True
                    fcf.ProjectedToleranceHeight = t["projected"]
                fcf.ControlledObject, fcf.ControlledSubelement = part, face
                fcf.ReferencedObject, fcf.ReferencedSubelement = part, face
                update_geometry_signature(fcf)
                written["tolerances"].append({**t, "feature": element})
    lost += [f"location between {' and '.join(x['between'])}" for x in pmi["locations"]]
    lost.append(
        "the ISO 22081 general specification: no general tolerance in the Workbench"
    )
    return written


def run(job):
    source = App.openDocument(job["native"])
    doc = App.newDocument("MBD")
    part = doc.addObject("Part::Feature", "Part")
    (solid,) = source.getObject(job["part"]).Shape.Solids
    part.Shape = solid.copy()
    doc.recompute()
    lost = []
    written = annotate(doc, part, job["pmi"], lost)
    doc.recompute()
    issues = [
        f"{i.severity}: {getattr(i.obj, 'Label', '')}: {i.message}"
        for i in MBDValidation.validate_document_structured(doc)["issues"]
    ]
    # Stale geometry signatures would open a confirmation dialog; headless, decline.
    MBDExporter.confirm_export_despite_warnings = lambda issues: not issues
    App.setActiveDocument(doc.Name)
    exported = MBDExporter.export_ap242(job["step"]) is True
    doc.saveAs(job["fcstd"])
    return {"exported": exported, "pmi": written, "not_carried": lost, "issues": issues}


result = run(job)
with open(job["result"], "w", encoding="utf-8") as f:
    json.dump(result, f)
