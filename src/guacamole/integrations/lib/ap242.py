"""STEP AP242 semantic PMI: write a part's PMI onto its faces, read it back, compare.

Over OCCT through CadQuery's OCP (the `bracket` extra, loaded on first use). write() reads
a model's STEP, finds the faces each PMI feature's fingerprint names, and writes AP242
with semantic GD&T: datums, sizes, locations and ISO 1101 frames with their zones,
modifiers and datum systems. Each also carries graphical PMI: drawn as on the
drawing, upright in a principal view plane by its feature, with leaders, and linked
to its semantic element (CAx-IF PMI practice 4.1, section 8). read() shares nothing
with write(): a fresh XCAF document from the file, each construct mapped to typed
values with the faces it attaches to, and everything it cannot map listed. compare()
reports every difference from the PMI, so nothing is dropped silently.

Carried: everything the typed PMI holds. That is datums on planes and features of
size, and on point, line, circle and rectangle targets (CAx-IF PMI practice 4.1,
section 6.6); diameters, widths and radii by ISO 286 class (IT2 and coarser) or
deviations; linear locations; every ISO 1101 characteristic with its zone, material
requirement, modifiers and datum material requirements; and the ISO 22081 general
surface profile, as that practice's section 6.3 gives it: a surface profile on every
face no other surface profile covers. Not carried, and listed by
write(): the ISO 22081 general size tolerance, for which AP242 has no semantic
entity, and projected zones, all around and all over, which OCCT's writer drops (its
reader maps them). The drawing's plain dimensions are presentation.
"""

import io
import math
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from pydantic import Field

from ...contracts import Model
from . import drafting
from .drafting import (
    PMI,
    Face,
    Feature,
    Holes,
    Location,
    Plane,
    Shafts,
    Size,
    Surfaces,
    Target,
    Tolerance,
    Width,
    distance,
    problems,
    specs,
)

TOL = 1e-4  # mm: STEP round trips move geometry by far less
# ISO 1101 characteristic: OCCT XCAF tolerance type.
TYPES = {
    "straightness": "Straightness",
    "flatness": "Flatness",
    "circularity": "CircularityOrRoundness",
    "cylindricity": "Cylindricity",
    "profile_line": "ProfileOfLine",
    "profile_surface": "ProfileOfSurface",
    "parallelism": "Parallelism",
    "perpendicularity": "Perpendicularity",
    "angularity": "Angularity",
    "position": "Position",
    "concentricity": "Concentricity",
    "coaxiality": "Coaxiality",
    "symmetry": "Symmetry",
    "circular_runout": "CircularRunout",
    "total_runout": "TotalRunout",
}
CHARACTERISTICS = {v: k for k, v in TYPES.items()}
MODIFIERS = {  # PMI modifier: OCCT XCAF tolerance modifier
    "all_around": "All_Around",
    "all_over": "All_Over",
    "any_cross_section": "Any_Cross_Section",
    "common_zone": "Common_Zone",
    "free_state": "Free_State",
    "line_element": "Line_Element",
    "reciprocity": "Reciprocity_Requirement",
    "separate_requirement": "Separate_Requirement",
    "statistical": "Statistical_Tolerance",
    "tangent_plane": "Tangent_Plane",
}
MODIFIER_NAMES = {v: k for k, v in MODIFIERS.items()}
DROPPED = ("all_around", "all_over")  # OCCT's AP242 writer skips these modifiers
DATUM_MATERIAL = {"M": "MaximumMaterialRequirement", "L": "LeastMaterialRequirement"}
# mm per unit. OCCT's reader returns GD&T values in mm, or unscaled when it misses the
# file's unit (it does for NIST's 'inch'); the geometry or the file text tells which.
SCALES = (1.0, 25.4, 1000.0)
GENERAL = "*general*"  # write()'s name for the faces the general profile covers
SIZES = {  # Feature kind: the XCAF type of its size
    "holes": "Size_Diameter",
    "shafts": "Size_Diameter",
    "width": "Size_Thickness",
    "surfaces": "Size_Radius",
}


class Found(Model):
    """What an AP242 file's semantic PMI says, in the PMI's own terms.

    features are keyed by the order they were met ("plane 1", "holes 1"); sizes and
    locations keep the nominal the file states beside the tolerance. general is the
    ISO 22081 general surface profile, value and datums: the surface profile on every
    face of its part that no other surface profile covers. Every dimension and
    tolerance in the file is counted in constructs and ends in exactly one place:
    sizes, locations, tolerances, general, unmapped (semantic PMI the typed PMI cannot
    represent, with why) or presentation (graphical annotations without semantics).
    """

    features: dict[str, Feature]
    datums: dict[str, str]
    targets: dict[str, tuple[Target, ...]] = Field(default_factory=dict)
    sizes: tuple[tuple[Size, float], ...] = ()
    locations: tuple[tuple[Location, float], ...] = ()
    tolerances: tuple[Tolerance, ...] = ()
    general: tuple[float, tuple[str, ...]] | None = None
    unmapped: tuple[str, ...] = ()
    presentation: int = 0
    presented: int = 0  # Semantic constructs that also carry graphical PMI
    constructs: int = 0
    conflicts: tuple[str, ...] = ()  # A datum letter on different features


def _ocp() -> Any:
    """OCP modules, imported on first use: the bracket extra installs them."""
    import OCP.BRep
    import OCP.BRepAdaptor
    import OCP.BRepGProp
    import OCP.GeomAbs
    import OCP.GProp
    import OCP.IFSelect
    import OCP.Interface
    import OCP.STEPCAFControl
    import OCP.STEPControl
    import OCP.TCollection
    import OCP.TDF
    import OCP.TDocStd
    import OCP.TopAbs
    import OCP.TopExp
    import OCP.TopoDS
    import OCP.TopTools
    import OCP.XCAFApp
    import OCP.XCAFDimTolObjects
    import OCP.XCAFDoc

    return OCP


def _document() -> Any:
    ocp = _ocp()
    doc = ocp.TDocStd.TDocStd_Document(
        ocp.TCollection.TCollection_ExtendedString("MDTV-XCAF")
    )
    ocp.XCAFApp.XCAFApp_Application.GetApplication_s().InitDocument(doc)
    return doc


def _sequence(labels: list) -> Any:
    sequence = _ocp().TDF.TDF_LabelSequence()
    for label in labels:
        sequence.Append(label)
    return sequence


def _items(sequence: Any) -> list:
    """An OCCT sequence's items; OCCT counts from 1."""
    return [sequence.Value(i) for i in range(1, sequence.Length() + 1)]


def _filled(method: Any, *args: Any) -> list:
    """The labels an OCCT call puts into the sequence passed last."""
    sequence = _ocp().TDF.TDF_LabelSequence()
    method(*args, sequence)
    return _items(sequence)


def _faces(shape: Any) -> Iterator[Any]:
    ocp = _ocp()
    explorer = ocp.TopExp.TopExp_Explorer(shape, ocp.TopAbs.TopAbs_FACE)
    while explorer.More():
        yield ocp.TopoDS.TopoDS.Face_s(explorer.Current())
        explorer.Next()


def _dot(a: Any, b: Any) -> float:
    return sum(x * y for x, y in zip(a, b))


def _describe(face: Any) -> dict:
    """A face's surface type, centroid and area, and what places it in a feature.

    A plane adds its outward normal. A cylinder adds its axis, radius, a point on the
    axis, its extent along it and its angular span, and is a "hole" when the material
    lies outside it, a "shaft" when inside.
    """
    ocp = _ocp()
    surface = ocp.BRepAdaptor.BRepAdaptor_Surface(face)
    reversed_ = face.Orientation() == ocp.TopAbs.TopAbs_REVERSED
    props = ocp.GProp.GProp_GProps()
    ocp.BRepGProp.BRepGProp.SurfaceProperties_s(face, props)
    c = props.CentreOfMass()
    kind = surface.GetType()
    d: dict = {
        "kind": "other",
        "surface": kind.name.removeprefix("GeomAbs_"),
        "point": (c.X(), c.Y(), c.Z()),
        "area": props.Mass(),
    }
    # A right-handed surface's parametric normal is its axis direction (a plane) or
    # points away from its axis (a cylinder); a reversed face turns it round.
    if kind == ocp.GeomAbs.GeomAbs_Plane:
        plane = surface.Plane()
        n = plane.Axis().Direction()
        if reversed_ == plane.Position().Direct():
            n = n.Reversed()
        d.update(kind="plane", normal=(n.X(), n.Y(), n.Z()))
    elif kind == ocp.GeomAbs.GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        a, p = cylinder.Axis().Direction(), cylinder.Axis().Location()
        axis, center = (a.X(), a.Y(), a.Z()), (p.X(), p.Y(), p.Z())
        at = _dot(center, axis)  # V runs along the axis from its location
        d.update(
            kind="hole" if reversed_ == cylinder.Position().Direct() else "shaft",
            axis=axis,
            radius=cylinder.Radius(),
            center=center,
            ends=(at + surface.FirstVParameter(), at + surface.LastVParameter()),
            span=surface.LastUParameter() - surface.FirstUParameter(),
        )
    return d


def _moved(face: Any, location: Any) -> Any:
    """The face where its component's location places it."""
    return _ocp().TopoDS.TopoDS.Face_s(face.Moved(location))


def _parallel(a: Any, b: Any) -> bool:
    return abs(abs(_dot(a, b)) - 1) < 1e-6


def _sense(v: Any) -> tuple[float, float, float]:
    """One sense for a direction: its first non-zero component positive."""
    x, y, z = v if next(c for c in v if abs(c) > 1e-9) > 0 else (-c for c in v)
    return x + 0.0, y + 0.0, z + 0.0


def _key(axis: Any, point: Any) -> tuple[float, ...]:
    """An axis line's point nearest the origin, rounded: the same for every point on it."""
    along = _dot(point, axis)
    return tuple(round(p - a * along, 4) for p, a in zip(point, axis))


def _feature(ds: list[dict]) -> Feature:
    """The feature a set of faces makes.

    One plane (coplanar faces); two opposed parallel planes, a width; complete holes or
    shafts of one size, direction and length; otherwise a set of surfaces, with a
    radius when they are all cylinders of one radius.
    """
    kinds = {d["kind"] for d in ds}
    if kinds == {"plane"}:
        planes: dict[tuple, list[dict]] = {}
        for d in ds:
            offset = round(_dot(d["point"], d["normal"]), 4) + 0.0
            key = (*(round(x, 6) + 0.0 for x in d["normal"]), offset)
            planes.setdefault(key, []).append(d)
        merged = []  # Per plane: normal, area-weighted centroid, area
        for group in planes.values():
            area = sum(d["area"] for d in group)
            point = tuple(
                sum(d["point"][i] * d["area"] for d in group) / area for i in range(3)
            )
            merged.append((group[0]["normal"], point, area))
        if len(merged) == 1:
            normal, point, area = merged[0]
            return Plane(point=point, normal=normal, area=area)
        if len(merged) == 2 and _dot(merged[0][0], merged[1][0]) < -1 + 1e-6:
            (n, p, a), (_, q, b) = merged
            across = _dot([y - x for x, y in zip(p, q)], n)
            return Width(
                normal=_sense(n),
                center=tuple((x + y) / 2 for x, y in zip(p, q)),
                width=abs(across),
                internal=across > 0,  # Each face looks across empty space at the other
                area=min(a, b),
            )
    elif kinds in ({"hole"}, {"shaft"}) and (cylinders := _cylinders(ds)) is not None:
        return cylinders
    radius = ds[0].get("radius")
    if radius is None or any(abs(d.get("radius", -1.0) - radius) > TOL for d in ds):
        radius = None
    faces = (Face(surface=d["surface"], point=d["point"], area=d["area"]) for d in ds)
    return Surfaces(
        faces=tuple(sorted(faces, key=lambda f: (f.surface, f.point))), radius=radius
    )


def _cylinders(ds: list[dict]) -> Holes | None:
    """Complete holes or shafts of one size, direction and length; None otherwise."""
    axis, radius = _sense(ds[0]["axis"]), ds[0]["radius"]
    if not all(
        _parallel(d["axis"], axis) and abs(d["radius"] - radius) < TOL for d in ds
    ):
        return None
    extents: dict[tuple, list[float]] = {}
    spans: dict[tuple, float] = {}
    for d in ds:
        sign = 1 if _dot(d["axis"], axis) > 0 else -1
        key = _key(axis, d["center"])
        extents.setdefault(key, []).extend(sorted(e * sign for e in d["ends"]))
        spans[key] = spans.get(key, 0.0) + d["span"]
    lengths = {round(max(v) - min(v), 4) for v in extents.values()}
    if len(lengths) != 1 or any(s < 2 * math.pi - 1e-6 for s in spans.values()):
        return None
    centers = tuple(
        tuple(k + a * (min(v) + max(v)) / 2 for k, a in zip(key, axis))
        for key, v in sorted(extents.items())
    )
    kind = Holes if ds[0]["kind"] == "hole" else Shafts
    return kind(axis=axis, diameter=2 * radius, centers=centers, length=lengths.pop())


def _same_area(a: float, b: float) -> bool:
    return abs(a - b) < 1e-3 * max(a, 1)


def _same_face(f: Any, g: Any) -> bool:
    """Two Face records (or face dicts) for the same face."""
    f, g = (x if isinstance(x, dict) else x.model_dump() for x in (f, g))
    return (
        f["surface"] == g["surface"]
        and math.dist(f["point"], g["point"]) < 1e-3
        and _same_area(f["area"], g["area"])
    )


def _same(a: Feature, b: Feature) -> bool:
    """The same geometry, to the round-trip tolerance."""
    if a.kind != b.kind:
        return False
    if isinstance(a, Plane) and isinstance(b, Plane):
        return (
            all(abs(x - y) < 1e-6 for x, y in zip(a.normal, b.normal))
            and math.dist(a.point, b.point) < 1e-3
            and _same_area(a.area, b.area)
        )
    if isinstance(a, Holes) and isinstance(b, Holes):
        return (
            _parallel(a.axis, b.axis)
            and abs(a.diameter - b.diameter) < TOL
            and abs(a.length - b.length) < 1e-3
            and len(a.centers) == len(b.centers)
            and all(
                any(
                    math.dist(_key(a.axis, c), _key(a.axis, d)) < 1e-3
                    for d in b.centers
                )
                for c in a.centers
            )
        )
    if isinstance(a, Width) and isinstance(b, Width):
        return (
            _parallel(a.normal, b.normal)
            and abs(a.width - b.width) < TOL
            and a.internal == b.internal
            and math.dist(a.center, b.center) < 1e-3
            and _same_area(a.area, b.area)
        )
    if isinstance(a, Surfaces) and isinstance(b, Surfaces):
        return (
            (a.radius is None) == (b.radius is None)
            and abs((a.radius or 0) - (b.radius or 0)) < TOL
            and len(a.faces) == len(b.faces)
            and all(any(_same_face(f, g) for g in b.faces) for f in a.faces)
        )
    return False


def _matches(spec: Mapping[str, Any], d: dict) -> bool:
    """Whether a face belongs to the feature a spec (drafting.specs) finds."""
    kind = spec["kind"]
    if kind == "plane":
        return (
            d["kind"] == "plane"
            and all(abs(x - y) < 1e-6 for x, y in zip(d["normal"], spec["normal"]))
            and abs(_dot(d["point"], spec["normal"]) - spec["offset"]) < TOL
        )
    if kind == "width":
        return (
            d["kind"] == "plane"
            and _parallel(d["normal"], spec["normal"])
            and abs(
                abs(_dot(d["point"], spec["normal"]) - spec["offset"])
                - spec["width"] / 2
            )
            < TOL
        )
    if kind in ("holes", "shafts"):
        return (
            d["kind"] == kind[:-1]
            and _parallel(d["axis"], spec["axis"])
            and abs(2 * d["radius"] - spec["diameter"]) < TOL
        )
    return any(_same_face(f, d) for f in spec["faces"])


def _fit(fit: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Za-z]{1,2})(\d{1,2})", fit)
    if match is None:
        raise ValueError(f"{fit} is no ISO 286 class")
    return match.group(1), int(match.group(2))


def _nominal(feature: Feature) -> float | None:
    """A feature of size's diameter or width, or a set of surfaces' radius."""
    if isinstance(feature, Holes):
        return feature.diameter
    if isinstance(feature, Width):
        return feature.width
    return feature.radius if isinstance(feature, Surfaces) else None


def fingerprints(path: Path, specs: Mapping[str, dict]) -> dict[str, dict]:
    """Named features of a STEP model, in freecad_bracket.features' terms.

    The same specs as drafting.specs gives for models that do not come from FreeCAD:
    a plane's outward normal and offset, holes' or shafts' axis and diameter, a
    width's normal, median offset and width, a set of surfaces' faces.
    drafting.features() validates the result. A spec whose faces make no feature of
    its kind gives {"matches": n}.
    """
    ocp = _ocp()
    reader = ocp.STEPControl.STEPControl_Reader()
    if reader.ReadFile(str(path)) != ocp.IFSelect.IFSelect_RetDone:
        raise ValueError(f"Cannot read {path.name}")
    reader.TransferRoots()
    faces = [_describe(face) for face in _faces(reader.OneShape())]
    found: dict[str, dict] = {}
    for name, spec in specs.items():
        hits = [d for d in faces if _matches(spec, d)]
        feature = _feature(hits) if hits else None
        found[name] = (
            feature.model_dump()
            if feature is not None and feature.kind == spec["kind"]
            else {"matches": len(hits)}
        )
    return found


def write(pmi: PMI, source: Path, target: Path) -> list[str]:
    """Write source's model to target as AP242 carrying the PMI on its faces.

    Returns what it did not carry. Raises ValueError for a malformed PMI, or when no
    single part of the model has the faces of every PMI feature.
    """
    if found := problems(pmi):
        raise ValueError("; ".join(found))
    ocp = _ocp()
    X, D = ocp.XCAFDimTolObjects, ocp.XCAFDoc
    doc = _document()
    reader = ocp.STEPCAFControl.STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    if reader.ReadFile(
        str(source)
    ) != ocp.IFSelect.IFSelect_RetDone or not reader.Transfer(doc):
        raise ValueError(f"Cannot read {source.name}")
    tool = D.XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    dgt = D.XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())

    # The part whose faces match every feature. Faces are compared where the model
    # places them; labels attach to the part's own faces.
    placed: dict[int, Any] = {}
    for component in _components(tool):
        referred = ocp.TDF.TDF_Label()
        if tool.GetReferredShape_s(component, referred):
            placed.setdefault(referred.Tag(), tool.GetLocation_s(component))
    wanted = specs(pmi)
    matches = []
    for part in _filled(tool.GetShapes):
        if tool.IsAssembly_s(part):
            continue
        location = placed.get(part.Tag())
        faces = [
            (face, _describe(face if location is None else _moved(face, location)))
            for face in _faces(tool.GetShape_s(part))
        ]
        found_faces = {
            name: _locate(f, wanted[name], faces) for name, f in pmi.features.items()
        }
        if all(not isinstance(v, str) for v in found_faces.values()):
            matches.append((part, found_faces, faces, location))
    if len(matches) != 1:
        raise ValueError(
            f"{len(matches)} parts of {source.name} have the faces of every PMI "
            "feature, not one"
        )
    part, located, faces, placement = matches[0]
    cache: dict[int, Any] = {}

    def labels(name: str) -> Any:
        out = []
        for face in located[name]:
            key = id(face)
            if key not in cache:
                cache[key] = tool.AddSubShape(part, face)
            out.append(cache[key])
        return _sequence(out)

    # Graphical PMI (CAx-IF PMI 4.1, section 8): each annotation drawn as on the
    # drawing, in a plane standing off its feature, with leaders to it, linked to its
    # semantic element. Annotations grow with the part so they stay readable.
    corners = [d["point"] for _, d in faces]
    centre = [sum(p[i] for p in corners) / len(corners) for i in range(3)]
    top = [max(p[i] for p in corners) for i in range(3)]
    scale = max(
        1.0,
        max(max(p[i] for p in corners) - min(p[i] for p in corners) for i in range(3))
        / 150,
    )
    stacked: dict[str, int] = {}

    def present(obj: Any, item: Any, names: tuple[str, ...], title: str) -> None:
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        lines = drafting.outlines(item)
        width = max(u for line in lines for u, _ in line)
        if names:  # Stacked outward from the feature, upright in its view
            anchor, (x, y, z), out = _anchor(pmi.features[names[0]], centre)
            k = stacked.get(names[0], 0)
            stacked[names[0]] = k + 1
            step = (12 + 2.4 * drafting.H * k) * scale
            origin = [a + o * step + v * scale for a, o, v in zip(anchor, out, z)]
            if _dot(out, x) < -0.5:  # Text runs away from the part, not into it
                origin = [o - u * width * scale for o, u in zip(origin, x)]
        else:  # The general specification: above the part's top corner, no leader
            (x, y, z), out = VIEWS[0], VIEWS[0][1]
            origin = [c + 12 * scale for c in top]
        near = 0 if _dot(out, x) >= -0.5 else width  # The end facing the feature
        start = [
            o + (u * near + v * drafting.H) * scale for o, u, v in zip(origin, x, y)
        ]
        leaders = [[start, list(_anchor(pmi.features[n], centre)[0])] for n in names]
        shape = _drawn(lines, origin, x, y, scale, leaders)
        plane, text = gp_Ax2(gp_Pnt(*origin), gp_Dir(*z), gp_Dir(*x)), gp_Pnt(*origin)
        if placement is not None:  # Drawn where the model places the part
            back = placement.Inverted().Transformation()
            shape = shape.Moved(placement.Inverted())
            plane, text = plane.Transformed(back), text.Transformed(back)
        obj.SetPresentation(shape, ocp.TCollection.TCollection_HAsciiString(title))
        obj.SetPlane(plane)
        obj.SetPointTextAttach(text)

    omitted = [
        (
            f"ISO 22081 general size tolerance ±{pmi.general.size:g}: AP242 has no "
            "semantic entity for it, and OCCT cannot write it as the CAx-IF practice's "
            "semantic text"
        ),
        (
            f"dimensioning standard {pmi.profile}: OCCT's writer declares none "
            "(CAx-IF PMI practice 4.1, section 4)"
        ),
    ]
    omitted += [
        f"size requirement {s.requirement} on {s.feature}: OCCT's writer has no size "
        "modifier for it"
        for s in pmi.sizes
        if s.requirement
    ]

    def dimension(
        kind: str, value: float, fit: str, upper: Any, lower: Any, what: str
    ) -> Any:
        """A new XCAF dimension; None when OCCT cannot write its tolerance."""
        if fit and _fit(fit)[1] < 2:
            omitted.append(f"{what}: OCCT cannot write grade IT{_fit(fit)[1]}")
            return None
        label = dgt.AddDimension()
        attribute = D.XCAFDoc_Dimension.Set_s(label)
        obj = attribute.GetObject()
        obj.SetType(
            getattr(
                X.XCAFDimTolObjects_DimensionType,
                f"XCAFDimTolObjects_DimensionType_{kind}",
            )
        )
        obj.SetValue(value)
        if fit:
            letters, grade = _fit(fit)
            # ITn is enum n + 1, and OCCT (7.9 to master) writes enum + 1 where its
            # reader expects n: H13 would become H15. It is given enum n - 1, which
            # it writes as n; read() and compare() catch it if that ever changes.
            obj.SetClassOfTolerance(
                letters.isupper(),  # Holes and slots take capitals, ISO 286
                getattr(
                    X.XCAFDimTolObjects_DimensionFormVariance,
                    f"XCAFDimTolObjects_DimensionFormVariance_{letters.upper()}",
                ),
                X.XCAFDimTolObjects_DimensionGrade(grade - 1),
            )
        else:
            # XCAF holds the lower deviation unsigned, as an amount below nominal; the
            # writer negates it into the file. OCCT's reader takes its absolute value,
            # so a lower deviation above nominal is written right but reads back wrong.
            obj.SetUpperTolValue(upper)
            obj.SetLowerTolValue(-lower)
            if lower > 0:
                omitted.append(
                    f"{what}: OCCT's reader cannot read back a lower deviation above "
                    "nominal"
                )
        attribute.SetObject(obj)
        return label

    for size in pmi.sizes:
        feature = pmi.features[size.feature]
        value = _nominal(feature)
        assert value is not None  # problems() admits sizes of these only
        label = dimension(
            SIZES[feature.kind],
            value,
            size.fit,
            size.upper,
            size.lower,
            f"size of {size.feature}",
        )
        if label is not None:
            dgt.SetDimension(labels(size.feature), ocp.TDF.TDF_LabelSequence(), label)
            shown = D.XCAFDoc_Dimension.Set_s(label)
            obj = shown.GetObject()
            text = drafting._size_text(size, feature)
            present(obj, text, (size.feature,), f"size of {size.feature}")
            shown.SetObject(obj)
    for location in pmi.locations:
        a, b = location.between
        value = distance(pmi.features[a], pmi.features[b])
        assert value is not None  # problems() admits measurable locations only
        label = dimension(
            "Location_LinearDistance",
            value,
            "",
            location.upper,
            location.lower,
            f"location of {b} from {a}",
        )
        dgt.SetDimension(labels(a), labels(b), label)
        shown = D.XCAFDoc_Dimension.Set_s(label)
        obj = shown.GetObject()
        text = f"{drafting._num(value)} {drafting._deviations(location.upper, location.lower)}"
        present(obj, text, (a, b), f"location of {b} from {a}")
        shown.SetObject(obj)

    # ISO 22081's general geometrical specification, as the CAx-IF PMI practice 4.1
    # (section 6.3) gives it: a surface profile on every face no other one covers.
    profiled = {
        id(face)
        for t in pmi.tolerances
        if t.characteristic == "profile_surface"
        for face in located[t.feature]
    }
    located[GENERAL] = [face for face, _ in faces if id(face) not in profiled]
    general = Tolerance(
        feature=GENERAL,
        characteristic="profile_surface",
        value=pmi.general.profile,
        datums=pmi.general.datums,
    )
    if not located[GENERAL]:
        omitted.append("ISO 22081 general profile: every face has its own")
    T = X.XCAFDimTolObjects_GeomToleranceType
    referenced = set()
    for t in (*pmi.tolerances, general) if located[GENERAL] else pmi.tolerances:
        tolerance = dgt.AddGeomTolerance()
        attribute = D.XCAFDoc_GeomTolerance.Set_s(tolerance)
        obj = attribute.GetObject()
        obj.SetType(
            getattr(T, f"XCAFDimTolObjects_GeomToleranceType_{TYPES[t.characteristic]}")
        )
        obj.SetValue(t.value)
        if t.diameter:
            obj.SetTypeOfValue(
                X.XCAFDimTolObjects_GeomToleranceTypeValue.XCAFDimTolObjects_GeomToleranceTypeValue_Diameter
            )
        if t.material:
            obj.SetMaterialRequirementModifier(
                getattr(
                    X.XCAFDimTolObjects_GeomToleranceMatReqModif,
                    f"XCAFDimTolObjects_GeomToleranceMatReqModif_{t.material}",
                )
            )
        what = f"{t.characteristic} of {t.feature}"
        for modifier in t.modifiers:
            if modifier in DROPPED:
                omitted.append(f"{what}: {modifier}, which OCCT's AP242 writer drops")
                continue
            obj.AddModifier(
                getattr(
                    X.XCAFDimTolObjects_GeomToleranceModif,
                    f"XCAFDimTolObjects_GeomToleranceModif_{MODIFIERS[modifier]}",
                )
            )
        if t.projected is not None:  # OCCT writes zone definitions for runout only
            omitted.append(
                f"{what}: projected zone {t.projected:g}, which OCCT's AP242 writer "
                "cannot write"
            )
        present(
            obj,
            t,
            () if t.feature == GENERAL else (t.feature,),
            f"{t.characteristic} of {t.feature}",
        )
        attribute.SetObject(obj)
        dgt.SetGeomTolerance(labels(t.feature), tolerance)
        # Each frame has its own datum labels: a datum's place is per datum system.
        # A datum on targets has a label per target, each on the datum's feature.
        for position, letter in enumerate(t.datums, start=1):
            for number, aim in enumerate(pmi.targets.get(letter, (None,)), start=1):
                datum = dgt.AddDatum()
                datum_attribute = D.XCAFDoc_Datum.Set_s(datum)
                datum_obj = datum_attribute.GetObject()
                datum_obj.SetName(ocp.TCollection.TCollection_HAsciiString(letter))
                datum_obj.SetPosition(position)
                if letter in t.datum_material:
                    datum_obj.AddModifier(
                        getattr(
                            X.XCAFDimTolObjects_DatumSingleModif,
                            "XCAFDimTolObjects_DatumSingleModif_"
                            + DATUM_MATERIAL[t.datum_material[letter]],
                        )
                    )
                if aim is not None:
                    _place(datum_obj, aim, number, placement)
                if letter not in referenced and number == 1:
                    feature = pmi.datums[letter]
                    present(datum_obj, ("datum", letter), (feature,), f"datum {letter}")
                datum_attribute.SetObject(datum_obj)
                dgt.SetDatum(labels(pmi.datums[letter]), datum)
                dgt.SetDatumToGeomTol(datum, tolerance)
            referenced.add(letter)
    omitted += [
        f"datum {letter}: no frame references it, and AP242 readers meet datums through frames"
        for letter in sorted(set(pmi.datums) - referenced)
    ]

    ocp.STEPCAFControl.STEPCAFControl_Controller.Init_s()  # Registers the schema setting
    if not ocp.Interface.Interface_Static.SetCVal_s("write.step.schema", "AP242DIS"):
        raise RuntimeError("OCCT did not accept the AP242 schema setting")
    writer = ocp.STEPCAFControl.STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetColorMode(True)
    writer.SetDimTolMode(True)
    if not writer.Transfer(
        doc, ocp.STEPControl.STEPControl_StepModelType.STEPControl_AsIs
    ) or (writer.Write(str(target)) != ocp.IFSelect.IFSelect_RetDone):
        raise RuntimeError(f"OCCT could not write {target.name}")
    return omitted


def _unit(v: Any) -> tuple[float, ...]:
    length = math.sqrt(_dot(v, v))
    return tuple(c / length for c in v)


def _cross(a: Any, b: Any) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _across(v: Any) -> tuple[float, ...]:
    """A unit direction square to v: the global axis least along it, straightened."""
    axis = min(((1, 0, 0), (0, 1, 0), (0, 0, 1)), key=lambda a: abs(_dot(a, v)))
    return _unit([a - _dot(axis, v) * c for a, c in zip(axis, v)])


# Principal views for graphical PMI, as rows: sheet right, sheet up, toward the
# viewer. Front looks along +y, top down -z, right along -x; then their opposites.
VIEWS = (
    ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
    ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
)


def _anchor(feature: Feature, centre: Any) -> tuple:
    """Where a feature's annotations attach, the view they read upright in, and the
    way out from the part they stand off along.

    A plane (or a width) in the first view showing it edge-on, standing out of it; a
    hole or shaft in the view along its axis, beside its near end; a set of surfaces
    in the front view, beside its first face.
    """
    if isinstance(feature, Plane):
        rows = next(r for r in VIEWS if abs(_dot(r[2], feature.normal)) < 1e-6)
        return feature.point, rows, feature.normal
    if isinstance(feature, Holes):
        rows = next(  # The first principal view along it, front, top or right first
            (r for r in VIEWS if abs(abs(_dot(r[2], feature.axis)) - 1) < 1e-6),
            VIEWS[0],
        )
        c, a, half = feature.centers[0], feature.axis, feature.length / 2
        sign = 1 if _dot(rows[2], a) > 0 else -1
        end = [p + d * half * sign for p, d in zip(c, a)]
        out = [p - q for p, q in zip(c, centre)]
        out = [x - _dot(out, rows[2]) * r for x, r in zip(out, rows[2])]
        return end, rows, _unit(out) if _dot(out, out) > 1e-9 else rows[1]
    if isinstance(feature, Width):
        rows = next(r for r in VIEWS if abs(_dot(r[2], feature.normal)) < 1e-6)
        out = [p - q for p, q in zip(feature.center, centre)]
        out = [x - _dot(out, rows[2]) * r for x, r in zip(out, rows[2])]
        return feature.center, rows, _unit(out) if _dot(out, out) > 1e-9 else rows[1]
    point = feature.faces[0].point
    out = [p - q for p, q in zip(point, centre)]
    out = [x - _dot(out, VIEWS[0][2]) * r for x, r in zip(out, VIEWS[0][2])]
    return point, VIEWS[0], _unit(out) if _dot(out, out) > 1e-9 else VIEWS[0][1]


def _drawn(lines: list, origin: Any, x: Any, y: Any, scale: float, extra: list) -> Any:
    """A compound of polyline edges: 2D lines in the plane at origin, and 3D ones."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import Geom_BSplineCurve
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    ocp = _ocp()
    builder, compound = ocp.BRep.BRep_Builder(), ocp.TopoDS.TopoDS_Compound()
    builder.MakeCompound(compound)
    polylines = [
        [
            [o + (u * a + v * b) * scale for o, a, b in zip(origin, x, y)]
            for u, v in line
        ]
        for line in lines
    ] + extra
    for line in polylines:
        points = [gp_Pnt(*line[0])]
        for p in line[1:]:
            if points[-1].Distance(gp_Pnt(*p)) > 1e-9:
                points.append(gp_Pnt(*p))
        n = len(points)
        if n < 2:
            continue
        if n == 2:
            builder.Add(compound, BRepBuilderAPI_MakeEdge(*points).Edge())
            continue
        poles, knots, mults = (
            TColgp_Array1OfPnt(1, n),
            TColStd_Array1OfReal(1, n),
            TColStd_Array1OfInteger(1, n),
        )
        for i, p in enumerate(points, start=1):  # A degree 1 B-spline: one line strip
            poles.SetValue(i, p)
            knots.SetValue(i, float(i))
            mults.SetValue(i, 2 if i in (1, n) else 1)
        curve = Geom_BSplineCurve(poles, knots, mults, 1)
        builder.Add(compound, BRepBuilderAPI_MakeEdge(curve).Edge())
    return compound


def _place(datum: Any, target: Target, number: int, placement: Any) -> None:
    """Make an XCAF datum the numbered target, in its part's own coordinates."""
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    ocp = _ocp()
    point, normal = gp_Pnt(*target.point), gp_Dir(*target.normal)
    axis = (
        gp_Ax2(point, normal)
        if target.direction is None
        else gp_Ax2(point, normal, gp_Dir(*target.direction))
    )
    if placement is not None:  # The PMI places it where the model places the part
        axis = axis.Transformed(placement.Inverted().Transformation())
    datum.IsDatumTarget(True)
    datum.SetDatumTargetType(
        getattr(
            ocp.XCAFDimTolObjects.XCAFDimTolObjects_DatumTargetType,
            f"XCAFDimTolObjects_DatumTargetType_{target.kind.capitalize()}",
        )
    )
    datum.SetDatumTargetAxis(axis)
    datum.SetDatumTargetNumber(number)
    if target.length is not None:
        datum.SetDatumTargetLength(target.length)
    if target.width is not None:
        datum.SetDatumTargetWidth(target.width)


def _components(tool: Any) -> list:
    ocp = _ocp()
    out = []
    pending = _filled(tool.GetFreeShapes)
    while pending:
        label = pending.pop()
        if tool.IsAssembly_s(label):
            for component in _filled(tool.GetComponents_s, label):
                out.append(component)
                referred = ocp.TDF.TDF_Label()
                if tool.GetReferredShape_s(component, referred):
                    pending.append(referred)
    return out


def _locate(
    feature: Feature, spec: Mapping[str, Any], faces: list[tuple[Any, dict]]
) -> list | str:
    """The faces of one model part a PMI feature names, or why there are none."""
    hits = [(face, d) for face, d in faces if _matches(spec, d)]
    if isinstance(feature, Holes):  # This feature's holes among others of that size
        feet = [_key(feature.axis, c) for c in feature.centers]
        hits = [
            (face, d)
            for face, d in hits
            if any(math.dist(_key(feature.axis, d["center"]), f) < TOL for f in feet)
        ]
    if not hits:
        return "no faces"
    found = _feature([d for _, d in hits])
    if not _same(found, feature):
        return f"{len(hits)} faces make a {found.kind} other than the one recorded"
    return [face for face, _ in hits]


def read(path: Path) -> Found:
    """The semantic PMI of an AP242 file, independently of write()."""
    ocp = _ocp()
    X, D = ocp.XCAFDimTolObjects, ocp.XCAFDoc
    doc = _document()
    reader = ocp.STEPCAFControl.STEPCAFControl_Reader()
    reader.SetGDTMode(True)
    reader.SetNameMode(True)
    if reader.ReadFile(
        str(path)
    ) != ocp.IFSelect.IFSelect_RetDone or not reader.Transfer(doc):
        raise ValueError(f"Cannot read {path.name}")
    tool = D.XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    dgt = D.XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    tool_type = type(dgt)
    stated = _magnitudes(path)
    features: dict[str, Feature] = {}
    unmapped: list[str] = []

    def attached(label: Any, what: str, pair: bool = False) -> Any:
        """The key of the feature a construct attaches to, or the keys of a pair of
        features; None when unmappable."""
        first, second = ocp.TDF.TDF_LabelSequence(), ocp.TDF.TDF_LabelSequence()
        tool_type.GetRefShapeLabel_s(label, first, second)
        groups = [_items(first), _items(second)] if pair else [_items(first)]
        if not first.Length() or (pair and not second.Length()):
            unmapped.append(
                f"{what}: attached to no shape OCCT resolves"
                if not first.Length()
                else f"{what}: a distance from one feature to no other"
            )
            return None
        if not pair and second.Length():
            unmapped.append(
                f"{what}: attached to {first.Length()} shapes and {second.Length()} more"
            )
            return None
        keys = []
        for group in groups:
            shapes = [tool.GetShape_s(lab) for lab in group]
            if any(s.ShapeType() != ocp.TopAbs.TopAbs_FACE for s in shapes):
                unmapped.append(
                    f"{what}: attached to edges, vertices or solids, not faces"
                )
                return None
            feature = _feature([_describe(ocp.TopoDS.TopoDS.Face_s(s)) for s in shapes])
            key = next(
                (k for k, known in features.items() if _same(known, feature)), None
            )
            if key is None:
                n = sum(f.kind == feature.kind for f in features.values()) + 1
                key = f"{feature.kind} {n}"
                features[key] = feature
            keys.append(key)
        return tuple(keys) if pair else keys[0]

    def tolerance_of(obj: Any, what: str, scale: float) -> dict | None:
        """A dimension's ISO 286 class or deviations in mm; None when unmappable."""
        if obj.IsDimWithClassOfTolerance():
            dump = io.BytesIO()
            obj.DumpJson(dump)
            fields = dict(
                re.findall(
                    r'"(IsHole|FormVariance|Grade)": (\d+)', dump.getvalue().decode()
                )
            )
            letters = X.XCAFDimTolObjects_DimensionFormVariance(
                int(fields["FormVariance"])
            ).name.rsplit("_", 1)[1]
            grade = X.XCAFDimTolObjects_DimensionGrade(int(fields["Grade"])).name
            if fields["IsHole"] != "1":  # Shafts and tabs take small letters, ISO 286
                letters = letters.lower()
            return {"fit": letters + grade.rsplit("_IT", 1)[1]}
        if obj.IsDimWithPlusMinusTolerance():
            if stated["above"]:  # OCCT read them unsigned: their signs are lost
                unmapped.append(
                    f"{what}: the file has {stated['above']} lower deviations "
                    "above nominal, whose sign OCCT's reader drops"
                )
                return None
            upper = obj.GetUpperTolValue() * scale
            lower = -obj.GetLowerTolValue() * scale + 0.0
        else:
            upper = (obj.GetUpperBound() - obj.GetValue()) * scale
            lower = (obj.GetLowerBound() - obj.GetValue()) * scale
        if upper <= lower:
            unmapped.append(f"{what}: deviations {upper:+g}/{lower:+g} leave no zone")
            return None
        return {"upper": upper, "lower": lower}

    sizes, locations, presentation = [], [], 0
    dimensions = _filled(dgt.GetDimensionLabels)
    tolerance_labels = _filled(dgt.GetGeomToleranceLabels)
    for label in dimensions:
        obj = D.XCAFDoc_Dimension.Set_s(label).GetObject()
        kind = obj.GetType().name.removeprefix("XCAFDimTolObjects_DimensionType_")
        if kind in ("DimensionPresentation", "CommonLabel"):
            presentation += 1  # Graphical PMI only: no semantics to map
            continue
        what = f"dimension {kind} {obj.GetValue():g}"
        if (
            kind not in (*SIZES.values(), "Location_LinearDistance")
            or obj.GetModifiers().Length()
            or obj.HasQualifier()
        ):
            unmapped.append(
                f"{what}: only plain diameters, widths, radii and linear distances "
                "map to the PMI"
            )
            continue
        if not (
            obj.IsDimWithClassOfTolerance()
            or obj.IsDimWithPlusMinusTolerance()
            or obj.IsDimWithRange()
        ):
            unmapped.append(f"{what}: no tolerance")
            continue
        if kind == "Location_LinearDistance":
            pair = attached(label, what, pair=True)
            if pair is None:
                continue
            nominal = distance(features[pair[0]], features[pair[1]])
            if nominal is None:
                unmapped.append(
                    f"{what}: between {pair[0]} and {pair[1]}, which have no linear "
                    "distance"
                )
                continue
            measure = f"the geometry puts {pair[1]} {nominal:g} mm from {pair[0]}"
        else:
            key = attached(label, what)
            if key is None:
                continue
            nominal = _nominal(features[key])
            if SIZES.get(features[key].kind) != kind or nominal is None:
                unmapped.append(f"{what}: on {key}, which has no such size")
                continue
            measure = f"{key} measures {nominal:g} mm"
        scale = next(
            (s for s in SCALES if abs(obj.GetValue() * s - nominal) < 1e-3), None
        )
        if scale is None:
            unmapped.append(
                f"{what}: {measure}, not the stated nominal in mm, inches or metres"
            )
            continue
        tolerance = tolerance_of(obj, what, scale)
        if tolerance is None:
            continue
        if kind != "Location_LinearDistance":
            sizes.append((Size(feature=key, **tolerance), obj.GetValue() * scale))
        elif "fit" in tolerance:
            unmapped.append(f"{what}: a tolerance class on a distance")
        else:
            locations.append(
                (Location(between=pair, **tolerance), obj.GetValue() * scale)
            )

    datums: dict[str, str] = {}
    tolerances, conflicts, general = [], [], None
    general_label = _general(tool, tolerance_labels)
    # Every target of a datum, by letter: OCCT links only one of them to each frame.
    targets: dict[str, dict[int, Target | str]] = {}
    for datum_label in _filled(dgt.GetDatumLabels):
        datum = D.XCAFDoc_Datum.Set_s(datum_label).GetObject()
        if datum.IsDatumTarget() and datum.GetName():
            targets.setdefault(datum.GetName().ToCString(), {})[
                datum.GetDatumTargetNumber()
            ] = _target(datum, stated["targets"])
    found_targets: dict[str, tuple[Target, ...]] = {}
    for label in tolerance_labels:
        obj = D.XCAFDoc_GeomTolerance.Set_s(label).GetObject()
        kind = obj.GetType().name.removeprefix("XCAFDimTolObjects_GeomToleranceType_")
        if kind == "None":
            presentation += 1
            continue
        what = f"{kind} {obj.GetValue():g}"
        # A value the file states under the entity's own name is authoritative: it
        # recovers OCCT's misreads. Otherwise the value counts only when an equal
        # magnitude in the file, unclaimed by another tolerance, confirms it.
        semantic = obj.GetSemanticName()
        value = stated["names"].get(semantic.ToCString()) if semantic else None
        if value is None:
            value = _confirmed(obj.GetValue(), stated["values"])
            if value is None:
                unmapped.append(
                    f"{what}: OCCT reads magnitude {obj.GetValue():g}, which the file "
                    "does not confirm"
                )
                continue
            stated["values"].remove(value)
        characteristic = CHARACTERISTICS.get(kind)
        zone = obj.GetTypeOfValue().name.removeprefix(
            "XCAFDimTolObjects_GeomToleranceTypeValue_"
        )
        material = obj.GetMaterialRequirementModifier().name.rsplit("_", 1)[1]
        modifiers, extra = [], []
        for m in _items(obj.GetModifiers()):
            name = m.name.removeprefix("XCAFDimTolObjects_GeomToleranceModif_")
            if name in MODIFIER_NAMES:
                modifiers.append(MODIFIER_NAMES[name])
            else:
                extra.append(name)
        projected = None
        zone_modifier = obj.GetZoneModifier().name.rsplit("_", 1)[1]
        if zone_modifier == "Projected":
            projected = _confirmed(obj.GetValueOfZoneModifier(), stated["projected"])
            if projected is None:
                extra.append(
                    f"projected length {obj.GetValueOfZoneModifier():g} the file does "
                    "not confirm"
                )
        elif zone_modifier != "None":
            extra.append(f"{zone_modifier} zone")
        if obj.GetMaxValueModifier():
            extra.append("a maximum value")
        if characteristic is None or zone == "SphericalDiameter" or extra:
            unmapped.append(
                f"{what}: {', '.join(extra) or 'type or zone'} not in the typed PMI"
            )
            continue
        # The general profile has no feature of its own: it covers what others do not.
        is_general = (
            general_label is not None
            and label.IsEqual(general_label)
            and not (modifiers or material != "None")
        )
        key = None if is_general else attached(label, what)
        if key is None and not is_general:
            continue
        order, datum_material = [], {}
        for datum_label in _filled(tool_type.GetDatumWithObjectOfTolerLabels_s, label):
            datum = D.XCAFDoc_Datum.Set_s(datum_label).GetObject()
            name = datum.GetName().ToCString() if datum.GetName() else ""
            single = {m.name.rsplit("_", 1)[1] for m in _items(datum.GetModifiers())}
            material_of = [k for k, v in DATUM_MATERIAL.items() if v in single]
            placed = targets.get(name, {}) if datum.IsDatumTarget() else {}
            if (
                any(isinstance(x, str) for x in placed.values())
                or len(single) > len(material_of)
                or datum.GetModifierWithValue(  # OCP returns the value alone
                    X.XCAFDimTolObjects_DatumModifWithValue.XCAFDimTolObjects_DatumModifWithValue_None
                )[0]
            ):
                why = next((x for x in placed.values() if isinstance(x, str)), None)
                unmapped.append(f"{what}: datum {name} has {why or 'other modifiers'}")
                order = None
                break
            if placed:
                found_targets[name] = tuple(t for _, t in sorted(placed.items()))  # ty: ignore[invalid-assignment] -- string reasons broke out above
            target = attached(datum_label, f"datum {name}")
            if target is None:
                order = None
                break
            if datums.setdefault(name, target) != target:
                conflicts.append(f"datum {name}: on {datums[name]} and on {target}")
            order.append((datum.GetPosition(), name))
            if material_of:
                datum_material[name] = material_of[0]
        if order is None:
            continue
        if is_general and not datum_material:
            general = (value, tuple(name for _, name in sorted(order)))
            continue
        if key is None and (key := attached(label, what)) is None:
            continue
        tolerances.append(
            Tolerance(
                feature=key,
                characteristic=characteristic,  # ty: ignore[invalid-argument-type] -- a CHARACTERISTICS key
                value=value,
                diameter=zone == "Diameter",
                material="" if material == "None" else material,
                datums=tuple(name for _, name in sorted(order)),
                datum_material=datum_material,
                modifiers=tuple(modifiers),
                projected=projected,
            )
        )
    presented = sum(
        not D.XCAFDoc_Dimension.Set_s(label).GetObject().GetPresentation().IsNull()
        for label in dimensions
    ) + sum(
        not D.XCAFDoc_GeomTolerance.Set_s(label).GetObject().GetPresentation().IsNull()
        for label in tolerance_labels
    )
    return Found(
        features=features,
        datums=datums,
        targets=found_targets,
        sizes=tuple(sizes),
        locations=tuple(locations),
        tolerances=tuple(tolerances),
        general=general,
        unmapped=tuple(unmapped),
        presentation=presentation,
        constructs=len(dimensions) + len(tolerance_labels),
        conflicts=tuple(conflicts),
        presented=presented,
    )


def _target(datum: Any, stated: list[float]) -> Target | str:
    """An XCAF datum target as a typed one, or what it has that cannot be one.

    Its sizes are confirmed against the file text, in mm, inches or metres.
    """
    kind = datum.GetDatumTargetType().name.rsplit("_", 1)[1].lower()
    if kind not in ("point", "line", "circle", "rectangle"):
        return f"{kind} targets"
    axis = datum.GetDatumTargetAxis()
    p, z, x = axis.Location(), axis.Direction(), axis.XDirection()
    sizes = {}
    for field, read in (
        ("length", datum.GetDatumTargetLength()),
        ("width", datum.GetDatumTargetWidth()),
    ):
        if (field == "length" and kind != "point") or (
            field == "width" and kind == "rectangle"
        ):
            sizes[field] = _confirmed(read, stated)
            if sizes[field] is None:
                return f"a target {field} {read:g} the file does not confirm"
    return Target(
        kind=kind,
        point=(p.X(), p.Y(), p.Z()),
        normal=(z.X(), z.Y(), z.Z()),
        direction=(x.X(), x.Y(), x.Z()) if kind in ("line", "rectangle") else None,
        **sizes,
    )


def _general(tool: Any, labels: list) -> Any:
    """The label of the ISO 22081 general surface profile among tolerance labels.

    The surface profile on every face of its part that no other surface profile
    covers (CAx-IF PMI practice 4.1, section 6.3). When two profiles each cover what
    the other leaves, the one covering more faces; None if none or a tie.
    """
    ocp = _ocp()
    D = ocp.XCAFDoc
    profile = ocp.XCAFDimTolObjects.XCAFDimTolObjects_GeomToleranceType.XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface
    covers = []  # Per surface profile: its label, part label, face indices, part's faces
    for label in labels:
        if D.XCAFDoc_GeomTolerance.Set_s(label).GetObject().GetType() != profile:
            continue
        first, second = ocp.TDF.TDF_LabelSequence(), ocp.TDF.TDF_LabelSequence()
        D.XCAFDoc_DimTolTool.GetRefShapeLabel_s(label, first, second)
        shapes = _items(first)
        if not shapes or second.Length() or not all(map(tool.IsSubShape_s, shapes)):
            continue
        part = shapes[0].Father()
        whole = tool.GetShape_s(part)
        if not ocp.TopExp.TopExp_Explorer(whole, ocp.TopAbs.TopAbs_SOLID).More():
            continue  # Faces OCCT keeps apart from any solid: no part to cover
        faces = ocp.TopTools.TopTools_IndexedMapOfShape()
        ocp.TopExp.TopExp.MapShapes_s(whole, ocp.TopAbs.TopAbs_FACE, faces)
        indices = {faces.FindIndex(tool.GetShape_s(s)) for s in shapes}
        if all(s.Father().IsEqual(part) for s in shapes) and 0 not in indices:
            covers.append((label, part, indices, faces.Extent()))
    found = sorted(
        (len(indices), n)
        for n, (_, part, indices, count) in enumerate(covers)
        if indices
        == set(range(1, count + 1)).difference(
            *(i for m, (_, p, i, _) in enumerate(covers) if m != n and p.IsEqual(part))
        )
    )
    if not found or (len(found) > 1 and found[-1][0] == found[-2][0]):
        return None
    return covers[found[-1][1]][0]


def _magnitudes(path: Path) -> dict[str, Any]:
    """What the file text itself says, as a cross-check on OCCT's reader.

    names and values: tolerance magnitudes in mm by tolerance name, and all of them.
    projected: projected zone lengths in mm. targets: datum target lengths, widths
    and diameters in mm. above: how many toleranced dimensions
    have a lower deviation above nominal. OCCT returns 0 for magnitudes written as
    complex length_measure_with_unit and measure_representation_item instances, and
    reads lower deviations unsigned. A name used twice maps to None; magnitudes in
    units other than mm, m and inch are left out.
    """
    text = path.read_text(encoding="latin-1")
    entities = dict(
        re.findall(r"^\s*#(\d+)\s*=\s*(.*?);\s*$", text, flags=re.MULTILINE | re.DOTALL)
    )

    measures = r"LENGTH_MEASURE\(\s*([-+0-9.Ee]+)\s*\)\s*,\s*#(\d+)"

    def unit_scale(ref: str) -> float | None:
        unit = "".join(entities.get(ref, "").split())
        return (
            1.0
            if ".MILLI.,.METRE." in unit
            else 1000.0
            if "$,.METRE." in unit
            else 25.4
            if "'INCH'" in unit.upper()
            else None
        )

    def length(ref: str) -> float | None:
        measure = re.search(measures, entities.get(ref, ""))
        scale = unit_scale(measure.group(2)) if measure else None
        return (
            None
            if measure is None or scale is None
            else float(measure.group(1)) * scale
        )

    found: dict[str, float | None] = {}
    values: list[float] = []
    projected: list[float] = []
    targets: list[float] = []
    above = 0
    for body in entities.values():
        if re.search(
            r"REPRESENTATION_ITEM\s*\(\s*'target (length|width|diameter)'", body
        ):
            measure = re.search(measures, body)
            scale = unit_scale(measure.group(2)) if measure else None
            if measure and scale is not None:
                targets.append(float(measure.group(1)) * scale)
        if match := re.search(
            r"\b\w+_TOLERANCE\(\s*'([^']*)'\s*,\s*'[^']*'\s*,\s*#(\d+)", body
        ):
            name, ref = match.groups()
            value = length(ref)
            if value is not None:
                values.append(value)
            found[name] = None if name in found else value
        elif body.startswith("PROJECTED_ZONE_DEFINITION"):
            value = length(re.findall(r"#(\d+)", body)[-1])
            if value is not None:
                projected.append(value)
        elif body.startswith("TOLERANCE_VALUE"):
            refs = re.findall(r"#(\d+)", body)
            measure = re.search(
                r"MEASURE\(\s*([-+0-9.Ee]+)\s*\)",
                entities.get(refs[0], "") if refs else "",
            )
            above += measure is not None and float(measure.group(1)) > 0
    return {
        "names": found,
        "values": values,
        "projected": projected,
        "targets": targets,
        "above": above,
    }


def _confirmed(read: float, stated: list[float]) -> float | None:
    """The magnitude in mm the file states for a value OCCT read, in whatever unit."""
    return next((v for v in stated for s in SCALES if abs(v - read * s) < 1e-6), None)


def compare(pmi: PMI, found: Found) -> list[str]:
    """Every difference between the PMI and what the file carries, as sentences."""
    names = {
        key: name
        for key, feature in found.features.items()
        for name, known in pmi.features.items()
        if _same(feature, known)
    }
    issues = [
        f"{key}: the file attaches PMI to geometry the PMI does not name"
        for key in found.features
        if key not in names
    ]

    def where(key: str) -> str:
        return names.get(key, key)

    for letter in sorted(set(pmi.datums) | set(found.datums)):
        expected, actual = pmi.datums.get(letter), found.datums.get(letter)
        if actual is None or where(actual) != expected:
            issues.append(
                f"datum {letter}: on {expected or 'nothing'} in the PMI, "
                f"on {where(actual) if actual else 'nothing'} in the file"
            )

    def placed(letter: str, targets: tuple[Target, ...]) -> list[str]:
        def at(v: Any) -> str:
            return "(" + ", ".join(f"{x + 0.0:.3f}" for x in v) + ")"

        return [
            f"datum target {letter}{n}: {t.kind} at {at(t.point)} facing {at(t.normal)}"
            + (f" along {at(t.direction)}" if t.direction else "")
            + "".join(
                f" {f} {v:.4g}"
                for f, v in (("length", t.length), ("width", t.width))
                if v
            )
            for n, t in enumerate(targets, start=1)
        ]

    issues += _differences(
        [line for letter, ts in pmi.targets.items() for line in placed(letter, ts)],
        [line for letter, ts in found.targets.items() for line in placed(letter, ts)],
    )
    measures = {"holes": "diameter", "shafts": "diameter", "width": "width"}

    def size(s: Size, feature: Feature, nominal: float | None) -> str:
        tolerance = s.fit or f"{s.upper:+.4g}/{s.lower:+.4g}"
        measure = measures.get(feature.kind, "radius")
        return f"size of {where(s.feature)}: {measure} {nominal or 0:.4g} {tolerance}"

    issues += _differences(
        [
            size(s, pmi.features[s.feature], _nominal(pmi.features[s.feature]))
            for s in pmi.sizes
        ],
        [size(s, found.features[s.feature], nominal) for s, nominal in found.sizes],
    )

    def location(x: Location, nominal: float | None) -> str:
        a, b = (where(name) for name in x.between)
        return f"location of {b} from {a}: {nominal or 0:.4g} {x.upper:+.4g}/{x.lower:+.4g}"

    issues += _differences(
        [
            location(x, distance(*(pmi.features[n] for n in x.between)))
            for x in pmi.locations
        ],
        [location(x, nominal) for x, nominal in found.locations],
    )

    def frame(t: Tolerance) -> str:
        zone = "diameter " if t.diameter else ""
        material = f" {t.material}" if t.material else ""
        projected = f" P {t.projected:.4g}" if t.projected is not None else ""
        modifiers = "".join(f" {m}" for m in sorted(t.modifiers))
        datums = " ".join(
            letter
            + (f"({t.datum_material[letter]})" if letter in t.datum_material else "")
            for letter in t.datums
        )
        datums = f" | {datums}" if datums else ""
        return (
            f"{t.characteristic} {zone}{t.value:.4g}{material}{projected}{modifiers}"
            f"{datums} on {where(t.feature)}"
        )

    issues += _differences(
        [frame(t) for t in pmi.tolerances], [frame(t) for t in found.tolerances]
    )

    def general(value: float, datums: tuple[str, ...]) -> str:
        return f"general surface profile {value:.4g}" + (
            f" | {' '.join(datums)}" if datums else ""
        )

    expected = general(pmi.general.profile, pmi.general.datums)
    actual = general(*found.general) if found.general else None
    if actual != expected:
        issues.append(f"{expected}: in the PMI; in the file, {actual or 'none'}")
    return (
        issues
        + list(found.conflicts)
        + [f"not mapped: {item}" for item in found.unmapped]
    )


def _differences(expected: list[str], actual: list[str]) -> list[str]:
    missing, extra = list(expected), []
    for item in actual:
        if item in missing:
            missing.remove(item)
        else:
            extra.append(item)
    return [f"{item}: in the PMI, not in the file" for item in missing] + [
        f"{item}: in the file, not in the PMI" for item in extra
    ]
