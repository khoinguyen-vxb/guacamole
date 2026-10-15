"""Runs inside headless FreeCAD: builds or inspects one L-bracket assembly.

bracket.py writes a job file and names it in BRACKET_JOB. Every number arrives in
the job; the engineering tables stay in bracket.py. "generate" writes the native
model, STEP and BOM, and returns the bracket's projected views and named features
for the drawing. "inspect" reopens a native model and reports what it measures,
including the named features, without judging it.
"""

import csv
import json
import os

import FreeCAD as App
import Import
import Part
import TechDraw

# Third-angle views of the part. Rows map model axes (x along the wall, y out of it,
# z up) to sheet right, sheet up and toward the viewer; FRONT looks at the wall.
VIEWS = {
    "FRONT": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "TOP": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
    "RIGHT": ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
}

PARAMETERS = (
    "width",
    "thickness",
    "wall_leg",
    "shelf_leg",
    "hole_d",
    "edge",
    "screw_d",
    "screw_len",
    "head_d",
    "head_h",
    "washer_od",
    "washer_id",
    "washer_h",
)
BOM_HEADER = [
    "item",
    "part_number",
    "description",
    "material",
    "quantity",
    "unit_mass_kg",
    "total_mass_kg",
]


def build(doc, job):
    """A parametric tree: every dimension is an expression on the Parameters sheet."""
    sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
    for row, name in enumerate(PARAMETERS, start=1):
        sheet.set(f"A{row}", name)
        sheet.set(f"B{row}", str(job["parameters"][name]))
        sheet.setAlias(f"B{row}", name)
    doc.recompute()

    def feature(kind, name, **expressions):
        obj = doc.addObject(kind, name)
        for prop, expression in expressions.items():
            obj.setExpression(prop.replace("_", "."), expression)
        obj.Visibility = False
        return obj

    def cylinder(name, radius, height, x, y, z, along_y):
        obj = feature(
            "Part::Cylinder",
            name,
            Radius=radius,
            Height=height,
            Placement_Base_x=x,
            Placement_Base_y=y,
            Placement_Base_z=z,
        )
        if along_y:  # Turn the default +z axis to +y, out of the wall.
            obj.Placement.Rotation = App.Rotation(App.Vector(1, 0, 0), -90)
        return obj

    def combine(kind, name, *shapes):
        obj = doc.addObject(kind, name)
        if kind == "Part::Cut":
            obj.Base, obj.Tool = shapes
        else:
            obj.Shapes = list(shapes)
        obj.Refine = True
        obj.Visibility = False
        return obj

    p = "Parameters."
    t = p + "thickness"
    wall = feature(
        "Part::Box",
        "WallLeg",
        Length=p + "width",
        Width=t,
        Height=p + "wall_leg",
    )
    shelf = feature(
        "Part::Box",
        "ShelfLeg",
        Length=p + "width",
        Width=p + "shelf_leg",
        Height=t,
    )
    holes, components = [], []
    count = job["holes"]
    wall_z = f"{p}wall_leg - {p}edge"
    under_head = f"{t} + {p}washer_h"
    fasteners = []
    for i in range(1, count + 1):
        x = f"{p}width * {i} / {count + 1}"
        holes.append(
            cylinder(
                f"WallHole{i}", p + "hole_d / 2", t + " + 2", x, "-1", wall_z, True
            )
        )
        holes.append(
            cylinder(
                f"ShelfHole{i}",
                p + "hole_d / 2",
                t + " + 2",
                x,
                f"{p}shelf_leg - {p}edge",
                "-1",
                False,
            )
        )
        shank = cylinder(
            f"Shank{i}",
            p + "screw_d / 2",
            p + "screw_len",
            x,
            f"{under_head} - {p}screw_len",
            wall_z,
            True,
        )
        head = cylinder(
            f"Head{i}", p + "head_d / 2", p + "head_h", x, under_head, wall_z, True
        )
        outer = cylinder(
            f"WasherOuter{i}", p + "washer_od / 2", p + "washer_h", x, t, wall_z, True
        )
        bore = cylinder(
            f"WasherBore{i}",
            p + "washer_id / 2",
            p + "washer_h + 2",
            x,
            t + " - 1",
            wall_z,
            True,
        )
        fasteners.append(
            (
                combine("Part::MultiFuse", f"Screw{i}", shank, head),
                combine("Part::Cut", f"Washer{i}", outer, bore),
            )
        )
    body = combine("Part::MultiFuse", "Body", wall, shelf)
    cutters = combine("Part::MultiFuse", "Holes", *holes)
    bracket = combine("Part::Cut", "Bracket", body, cutters)
    for obj, part in (
        (bracket, "bracket"),
        *((s, "screw") for s, _ in fasteners),
        *((w, "washer") for _, w in fasteners),
    ):
        for key in ("PartNumber", "Description", "Material"):
            obj.addProperty("App::PropertyString", key, "BOM")
            setattr(obj, key, job["parts"][part][key])
        obj.addProperty("App::PropertyFloat", "Density", "BOM", "kg/m^3")
        obj.Density = job["parts"][part]["Density"]
        obj.Visibility = True
        components.append(obj)
    assembly = doc.addObject("App::DocumentObjectGroup", "Assembly")
    assembly.Group = components
    doc.recompute()
    return components


def components_of(doc):
    return list(doc.getObject("Assembly").Group)  # The order the BOM lists them.


def invalid(doc):
    return sorted(
        o.Name
        for o in doc.Objects
        if "Invalid" in o.State
        or (
            o.isDerivedFrom("Part::Feature")
            and (o.Shape.isNull() or not o.Shape.isValid())
        )
    )


def bom(components):
    """Rows derived from the assembly tree: one per part number."""
    rows = {}
    for obj in components:
        mass = obj.Shape.Volume * obj.Density * 1e-9  # mm^3 x kg/m^3
        row = rows.setdefault(obj.PartNumber, [obj.Description, obj.Material, 0, mass])
        row[2] += 1
    return [BOM_HEADER] + [
        [str(item), number, d, m, str(q), f"{unit:.6f}", f"{unit * q:.6f}"]
        for item, (number, (d, m, q, unit)) in enumerate(rows.items(), start=1)
    ]


def edges(*compounds):
    """Projected edges in sheet mm at 1:1: lines, full circles, other curves as polylines."""
    found = {"lines": [], "circles": [], "polylines": []}
    for compound in compounds:
        for edge in compound.Edges:
            curve = edge.Curve
            if isinstance(curve, Part.Line):
                a, b = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
                found["lines"].append([a.x, a.y, b.x, b.y])
            elif isinstance(curve, Part.Circle) and edge.isClosed():
                found["circles"].append([curve.Center.x, curve.Center.y, curve.Radius])
            else:
                points = edge.discretize(Deflection=0.01)
                found["polylines"].append([[p.x, p.y] for p in points])
    return found


def project(shape):
    """Each view's visible and hidden edges: hard edges and silhouettes."""
    views = {}
    for name, rows in VIEWS.items():
        matrix = App.Matrix(*rows[0], 0, *rows[1], 0, *rows[2], 0, 0, 0, 0, 1)
        view = shape.copy()
        view.transformShape(matrix)
        # projectEx: visible hard, smooth, seam, outline, iso; then the hidden five.
        groups = TechDraw.projectEx(view, App.Vector(0, 0, 1))
        views[name] = {
            "rows": rows,
            "visible": edges(groups[0], groups[3]),
            "hidden": edges(groups[5], groups[8]),
        }
    return views


def features(shape, specs):
    """Fingerprint named features: the one face on each plane, or each set of holes.

    A plane spec gives its outward normal and offset (normal . point); a holes spec
    its axis and diameter. A spec matching no face, or a plane matching several,
    comes back as {"matches": n} so the drawing is never attached to a guess.
    """
    found = {}
    for name, spec in specs.items():
        if spec["kind"] == "plane":
            n = App.Vector(*spec["normal"])
            faces = []
            for face in shape.Faces:
                if not isinstance(face.Surface, Part.Plane):
                    continue
                u0, u1, v0, v1 = face.ParameterRange
                normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
                if (normal - n).Length < 1e-6 and abs(
                    face.CenterOfMass.dot(n) - spec["offset"]
                ) < 1e-6:
                    faces.append(face)
            found[name] = (
                {
                    "kind": "plane",
                    "point": list(faces[0].CenterOfMass),
                    "normal": spec["normal"],
                    "area": faces[0].Area,
                }
                if len(faces) == 1
                else {"matches": len(faces)}
            )
            continue
        axis = App.Vector(*spec["axis"])
        holes = {}  # Faces grouped by axis line: a hole may be split at its seam.
        for face in shape.Faces:
            surface = face.Surface
            if (
                isinstance(surface, Part.Cylinder)
                and abs(abs(surface.Axis.dot(axis)) - 1) < 1e-6
                and abs(2 * surface.Radius - spec["diameter"]) < 1e-6
            ):
                c = surface.Center
                key = tuple(round(x, 6) for x in c - axis * c.dot(axis))
                holes.setdefault(key, []).extend(
                    v.Point.dot(axis) for v in face.Vertexes
                )
        centers, lengths = [], set()
        for key, along in sorted(holes.items()):
            middle = (min(along) + max(along)) / 2
            centers.append(list(App.Vector(*key) + axis * middle))
            lengths.add(round(max(along) - min(along), 6))
        found[name] = (
            {
                "kind": "holes",
                "axis": spec["axis"],
                "diameter": spec["diameter"],
                "centers": centers,
                "length": lengths.pop(),
            }
            if len(lengths) == 1
            else {"matches": len(centers)}
        )
    return found


def generate(job):
    doc = App.newDocument("Bracket")
    components = build(doc, job)
    problems = invalid(doc)
    if problems:
        raise RuntimeError(f"Invalid features after recompute: {problems}")
    paths = job["outputs"]
    doc.saveAs(paths["native"])
    Import.export(components, paths["step"])
    with open(paths["bom"], "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(bom(components))
    part = doc.getObject("Bracket").Shape
    return {
        "components": len(components),
        "volume": part.Volume,
        "views": project(part),
        "features": features(part, job["features"]),
    }


def inspect(job):
    doc = App.openDocument(job["native"])
    doc.recompute()
    components = components_of(doc)
    sheet = doc.getObject("Parameters")
    report = {
        "errors": invalid(doc),
        "parameters": {
            n: float(getattr(sheet.get(n), "Value", sheet.get(n))) for n in PARAMETERS
        },
        "holes": len([o for o in doc.Objects if o.Name.startswith("WallHole")]),
        "components": [
            {
                "name": o.Name,
                "part_number": o.PartNumber,
                "material": o.Material,
                "density": o.Density,
                "valid": not o.Shape.isNull() and o.Shape.isValid(),
                "solids": len(o.Shape.Solids),
                "volume": o.Shape.Volume,
                "size": [
                    o.Shape.BoundBox.XLength,
                    o.Shape.BoundBox.YLength,
                    o.Shape.BoundBox.ZLength,
                ],
            }
            for o in components
        ],
        "bom": bom(components),
    }
    report["interferences"] = [
        [a.Name, b.Name, common]
        for i, a in enumerate(components)
        for b in components[i + 1 :]
        if a.Shape.BoundBox.intersect(b.Shape.BoundBox)
        and (common := a.Shape.common(b.Shape).Volume) > 1e-3
    ]
    step = Part.read(job["step"])
    report["step_volumes"] = sorted(s.Volume for s in step.Solids)
    bracket = doc.getObject("Bracket")
    report["features"] = features(bracket.Shape, job.get("features", {}))
    # Parameter-change check: thicken the plate, recompute, then discard the change.
    before = bracket.Shape.Volume
    cell = sheet.getCellFromAlias("thickness")
    sheet.set(cell, str(report["parameters"]["thickness"] + 1))
    doc.recompute()
    report["thickened"] = {
        "errors": invalid(doc),
        "volume_before": before,
        "volume_after": bracket.Shape.Volume,
    }
    App.closeDocument(doc.Name)
    return report


with open(os.environ["BRACKET_JOB"], encoding="utf-8") as f:
    job = json.load(f)
result = generate(job) if job["mode"] == "generate" else inspect(job)
with open(job["result"], "w", encoding="utf-8") as f:
    json.dump(result, f)
