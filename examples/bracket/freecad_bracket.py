"""Runs inside headless FreeCAD: builds or inspects one L-bracket assembly.

bracket.py writes a job file and names it in BRACKET_JOB. Every number arrives in
the job; the engineering tables stay in bracket.py. "generate" writes the native
model, STEP, drawing and BOM. "inspect" reopens a native model and reports what it
measures without judging it.
"""

import csv
import json
import os

import FreeCAD as App
import Import
import Part
import TechDraw

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


def drawing(components, title):
    """Third-angle front, top and right views with overall dimensions, mm."""
    shape = Part.makeCompound([o.Shape for o in components])
    # Rows map model axes (x along the wall, y out of it, z up) to sheet right,
    # sheet up and toward the viewer. FRONT looks at the wall from the room.
    views = {
        "FRONT": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        "TOP": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
        "RIGHT": ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
    }
    projected = {}
    for name, rows in views.items():
        matrix = App.Matrix(*rows[0], 0, *rows[1], 0, *rows[2], 0, 0, 0, 0, 1)
        view = shape.copy()
        view.transformShape(matrix)
        box = view.BoundBox
        svg = TechDraw.projectToSVG(view, App.Vector(0, 0, 1))
        projected[name] = (svg, box.XMin, box.XMax, box.YMin, box.YMax)
    front, top, right = (projected[k] for k in ("FRONT", "TOP", "RIGHT"))
    width = front[2] - front[1] + right[2] - right[1]
    height = front[4] - front[3] + top[4] - top[3]
    scale = next(
        s for s in (1, 0.5, 0.2, 0.1, 0.05) if width * s <= 300 and height * s <= 180
    )
    left, base = 50.0, 40.0
    origin = {  # Upper-left sheet corner of each view.
        "TOP": (left, base),
        "FRONT": (left, base + (top[4] - top[3]) * scale + 30),
        "RIGHT": (
            left + (front[2] - front[1]) * scale + 40,
            base + (top[4] - top[3]) * scale + 30,
        ),
    }
    parts = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" '
            'viewBox="0 0 420 297" font-family="sans-serif">'
        ),
        '<rect x="10" y="10" width="400" height="277" fill="none" stroke="black" stroke-width="0.7"/>',
    ]
    for name, (svg, umin, umax, vmin, vmax) in projected.items():
        x, y = origin[name]
        w, h = (umax - umin) * scale, (vmax - vmin) * scale
        svg = svg.replace('stroke-width="1.0"', f'stroke-width="{0.35 / scale:.3f}"')
        parts.append(
            f'<g transform="translate({x - umin * scale:.3f},{y + vmax * scale:.3f}) '
            f'scale({scale})">{svg}</g>'
        )
        parts += [  # Overall dimensions, below and left of the view.
            f'<line x1="{x}" y1="{y + h + 8}" x2="{x + w}" y2="{y + h + 8}" stroke="black" stroke-width="0.25"/>',
            f'<text x="{x + w / 2}" y="{y + h + 13}" font-size="3.5" text-anchor="middle">{umax - umin:.1f}</text>',
            f'<line x1="{x - 8}" y1="{y}" x2="{x - 8}" y2="{y + h}" stroke="black" stroke-width="0.25"/>',
            f'<text x="{x - 10}" y="{y + h / 2}" font-size="3.5" text-anchor="end">{vmax - vmin:.1f}</text>',
            f'<text x="{x}" y="{y - 4}" font-size="4">{name}</text>',
        ]
    block = [
        title,
        f"Scale 1:{1 / scale:g}   Units mm   Third-angle projection",
        "Generated by bracket_generate from the native model",
    ]
    parts.append(
        '<rect x="250" y="252" width="160" height="35" fill="none" stroke="black" stroke-width="0.5"/>'
    )
    parts += [
        f'<text x="254" y="{262 + 9 * i}" font-size="{5 if i == 0 else 3.5}">{line}</text>'
        for i, line in enumerate(block)
    ]
    parts.append("</svg>")
    return "\n".join(parts)


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
    with open(paths["drawing"], "w", encoding="utf-8") as f:
        f.write(drawing(components, job["title"]))
    return {"components": len(components)}


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
    # Parameter-change check: thicken the plate, recompute, then discard the change.
    bracket = doc.getObject("Bracket")
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
