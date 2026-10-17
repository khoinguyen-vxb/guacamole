"""Runs inside headless FreeCAD: the projected views of one part, for its drawing.

drawing.py writes a job naming a STEP file and names it in GUACAMOLE_JOB. The result
holds how many solids the file has and, when it has exactly one, that solid's volume
and its views in drafting.compile_drawing's terms. freecad_bracket.py imports
project() for its own views.
"""

import json
import os

import FreeCAD as App
import Part
import TechDraw

# Third-angle views. Rows map model axes to sheet right, sheet up and toward the
# viewer: FRONT looks along +y with x right and z up, TOP along -z, RIGHT along -x.
VIEWS = {
    "FRONT": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    "TOP": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "RIGHT": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
}


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


def project(shape, views=VIEWS):
    """Each view's visible and hidden edges: hard edges and silhouettes."""
    found = {}
    for name, rows in views.items():
        matrix = App.Matrix(*rows[0], 0, *rows[1], 0, *rows[2], 0, 0, 0, 0, 1)
        view = shape.copy()
        view.transformShape(matrix)
        # projectEx: visible hard, smooth, seam, outline, iso; then the hidden five.
        groups = TechDraw.projectEx(view, App.Vector(0, 0, 1))
        found[name] = {
            "rows": rows,
            "visible": edges(groups[0], groups[3]),
            "hidden": edges(groups[5], groups[8]),
        }
    return found


if __name__ == "__main__":
    with open(os.environ["GUACAMOLE_JOB"], encoding="utf-8") as f:
        job = json.load(f)
    solids = Part.read(job["step"]).Solids
    result = {"solids": len(solids)}
    if len(solids) == 1:
        result |= {"volume": solids[0].Volume, "views": project(solids[0])}
    with open(job["result"], "w", encoding="utf-8") as f:
        json.dump(result, f)
