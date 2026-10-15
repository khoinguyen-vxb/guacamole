"""ISO GPS part drawings compiled from canonical PMI and projected model geometry.

Example tooling, not part of the Guacamole runtime: domain types belong to tools.
The PMI (named features, datums, size and geometrical specifications, and the general
specification) carries the engineering meaning and is tied to the geometry it was
made for. compile_drawing turns it, three projected views and a title block into an
editable DXF; svg renders that DXF for review; conformance reads a DXF back and checks
it against the PMI and the supported subset. Nothing here invents a value: sizes and
locations come from the geometry, tolerances from the PMI.

Supported subset, ISO_GPS_MECHANICAL: ISO 8015 invocation; all ISO 1101
characteristics and modifiers (SUPPORTED); ISO 5459 datums on planes, features of
size and datum targets; ISO 14405-1 sizes by ISO 286 class or deviations; toleranced
linear locations; ISO 22081 general specification; ISO 129-1 dimensions; ISO 128-2
line types; ISO 5457 sheets A4 to A0; ISO 7200 title block; ISO 5455 scales; third-angle
projection, ISO 5456-2. undrawn() lists what the PMI holds and the drawing cannot
show yet.
"""

import json
import math
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple

from pydantic import Field, TypeAdapter

from guacamole import Model

PROFILE = "ISO_GPS_MECHANICAL"
ASME = "ASME_Y14_5_2018"
# What ASME Y14.5-2018 lacks: it withdrew concentricity and symmetry, never had
# coaxiality, and has no combined zone, any cross section or reciprocity modifier.
NOT_ASME = frozenset(
    {
        "concentricity",
        "coaxiality",
        "symmetry",
        "common_zone",
        "any_cross_section",
        "reciprocity",
    }
)
FONT = "DejaVuSans.ttf"
H = 3.5  # Lettering height, ISO 3098
GAP = 1.0  # Extension lines start this far off the feature, ISO 129-1
ARROW = (3.0, 0.8)  # Closed filled arrowhead: length and half-width
SCALES = (2.0, 1.0, 0.5, 0.2, 0.1, 0.05)  # ISO 5455
PAPER = {  # ISO 5457 sheets, width x height in mm: A4 upright, the others landscape
    "A4": (210.0, 297.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
}


class Paper(NamedTuple):
    """A sheet's rectangles in mm: its edge, frame, title block and notes."""

    sheet: tuple[float, float]
    frame: tuple[float, float, float, float]
    title: tuple[float, float, float, float]
    notes: tuple[float, float, float, float]


def paper(width: float, height: float) -> Paper:
    """ISO 5457 frame (20 mm filing margin on the left), ISO 7200 title block 180 mm
    wide in the bottom right corner, and the notes above it."""
    return Paper(
        (width, height),
        (20.0, 10.0, width - 10, height - 10),
        (width - 190, 10.0, width - 10, 50.0),
        (width - 190, 50.0, width - 10, 74.0),
    )


LAYERS = {  # Linetype and lineweight (1/100 mm), ISO 128-2 widths for A3
    "VISIBLE": ("Continuous", 50),
    "HIDDEN": ("DASHED_ISO", 25),
    "CENTER": ("CENTER_ISO", 25),
    "PHANTOM": ("PHANTOM_ISO", 25),  # Datum target lines and areas, ISO 5459
    "DIMENSION": ("Continuous", 25),
    "TEXT": ("Continuous", 25),
    "TITLE": ("Continuous", 35),
    "FRAME": ("Continuous", 70),
    "SHEET": ("Continuous", 13),
}
STATUSES = ("In preparation", "In review", "Released", "Withdrawn")  # ISO 7200

type Vec = tuple[float, float, float]
type Side = Literal["left", "right", "below", "above"]
SIDES: dict[str, tuple[int, int]] = {
    "left": (-1, 0),
    "right": (1, 0),
    "below": (0, -1),
    "above": (0, 1),
}


class Plane(Model):
    """A planar face: centroid, outward unit normal and area (mm, mm2)."""

    kind: Literal["plane"] = "plane"
    point: Vec
    normal: Vec
    area: float


class Holes(Model):
    """Equal parallel holes: axis, diameter, the centre of each and their length."""

    kind: Literal["holes"] = "holes"
    axis: Vec
    diameter: float
    centers: tuple[Vec, ...] = Field(min_length=1)
    length: float


class Shafts(Holes):
    """Equal parallel external cylinders (bosses, pins), described as holes are."""

    kind: Literal["shafts"] = "shafts"


class Width(Model):
    """Two opposed parallel planes: a slot (internal) or a tab (external).

    normal points across the width; center lies on the median plane; area is one face's.
    """

    kind: Literal["width"] = "width"
    normal: Vec
    center: Vec
    width: float
    internal: bool
    area: float


class Face(Model):
    """One face of a surface set: its surface type, centroid and area."""

    surface: str  # OCCT surface type, e.g. "Plane", "Cylinder", "BSplineSurface"
    point: Vec
    area: float


class Surfaces(Model):
    """Any set of faces; radius when they are all arcs or rounds of one radius."""

    kind: Literal["surfaces"] = "surfaces"
    faces: tuple[Face, ...] = Field(min_length=1)
    radius: float | None = None


type Feature = Annotated[
    Plane | Holes | Shafts | Width | Surfaces, Field(discriminator="kind")
]
FEATURES = TypeAdapter(dict[str, Feature])
OF_SIZE = frozenset({"holes", "shafts", "width"})  # Features of size: MMR/LMR apply
AXES = frozenset({"holes", "shafts"})

type Characteristic = Literal[
    "straightness",
    "flatness",
    "circularity",
    "cylindricity",
    "profile_line",
    "profile_surface",
    "parallelism",
    "perpendicularity",
    "angularity",
    "position",
    "concentricity",
    "coaxiality",
    "symmetry",
    "circular_runout",
    "total_runout",
]
_ORIENTED = frozenset({"plane", "holes", "shafts", "width"})
# ISO 1101 characteristics: whether they take datums (none, required or optional) and
# the feature kinds they apply to. Characteristics missing here parse, and problems()
# reports them as outside the supported subset.
SUPPORTED: dict[str, tuple[str, frozenset[str]]] = {
    "straightness": ("none", frozenset({"plane", "holes", "shafts"})),
    "flatness": ("none", frozenset({"plane"})),
    "circularity": ("none", frozenset({"holes", "shafts", "surfaces"})),
    "cylindricity": ("none", AXES),
    "profile_line": ("optional", frozenset({"plane", "surfaces", "holes", "shafts"})),
    "profile_surface": ("optional", frozenset({"plane", "surfaces", "width"}) | AXES),
    "parallelism": ("required", _ORIENTED),
    "perpendicularity": ("required", _ORIENTED),
    "angularity": ("required", _ORIENTED),
    "position": ("optional", frozenset({"plane", "holes", "shafts", "width"})),
    "concentricity": ("required", AXES),
    "coaxiality": ("required", AXES),
    "symmetry": ("required", frozenset({"width"})),
    "circular_runout": ("required", frozenset({"plane", "surfaces"}) | AXES),
    "total_runout": ("required", frozenset({"plane"}) | AXES),
}
# ISO 1101 / ISO 2692 modifiers a frame may carry besides its material requirement.
type Modifier = Literal[
    "all_around",
    "all_over",
    "any_cross_section",
    "common_zone",
    "free_state",
    "line_element",
    "reciprocity",
    "separate_requirement",
    "statistical",
    "tangent_plane",
]


class Size(Model):
    """ISO 14405-1 size of a feature of size: an ISO 286 class or deviations (mm).

    A diameter for holes and shafts, a width for slots and tabs, a radius for arcs.
    """

    feature: str
    fit: str = ""  # e.g. "H13"
    upper: float | None = None
    lower: float | None = None
    # Stated on the drawing as ISO 14405-1 Ⓔ or ASME Y14.5 Ⓘ. Empty keeps the profile's
    # default: ISO 8015 independency, or ASME Y14.5's Rule #1 envelope.
    requirement: Literal["", "envelope", "independency"] = ""


class Tolerance(Model):
    """One ISO 1101 geometrical specification: a feature control frame."""

    feature: str
    characteristic: Characteristic
    value: float = Field(ge=0)  # Zero only with a material modifier: 0 at MMC
    diameter: bool = False  # Cylindrical zone, for hole axes
    material: Literal["", "M", "L"] = ""  # Maximum or least material requirement
    datums: tuple[str, ...] = ()  # Primary first
    # Material requirement on a datum feature of size, by letter: A(M) in the frame.
    datum_material: dict[str, Literal["M", "L"]] = Field(default_factory=dict)
    modifiers: tuple[Modifier, ...] = ()
    projected: float | None = Field(default=None, gt=0)  # Projected zone length, mm


class Target(Model):
    """An ISO 5459 datum target, placed as AP242 places it (CAx-IF PMI 4.1, 6.6.1).

    point is the point, a line's start, or a circle's or rectangle's centre; normal
    points out of the material. A line runs length along direction; a circle has
    diameter length; a rectangle is length along direction by width across it.
    """

    kind: Literal["point", "line", "circle", "rectangle"]
    point: Vec
    normal: Vec
    direction: Vec | None = None  # Lines and rectangles only
    length: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)  # Rectangles only


class Location(Model):
    """A toleranced distance between two features: planes, axes or median planes."""

    between: tuple[str, str]
    upper: float
    lower: float


class General(Model):
    """ISO 22081 general specification for every feature not individually specified."""

    size: float = Field(gt=0)  # +/- on linear sizes, mm
    profile: float = Field(gt=0)  # Surface profile zone, mm
    datums: tuple[str, ...]


class PMI(Model):
    """Canonical PMI for one part, tied to the geometry it was made for."""

    profile: Literal["ISO_GPS_MECHANICAL", "ASME_Y14_5_2018"] = PROFILE
    features: dict[str, Feature]
    datums: dict[
        str, str
    ]  # Letter: a plane, or a feature of size's axis or median plane
    # Letter: the targets on its feature that establish the datum, A1 first.
    targets: dict[str, tuple[Target, ...]] = Field(default_factory=dict)
    sizes: tuple[Size, ...] = ()
    locations: tuple[Location, ...] = ()
    tolerances: tuple[Tolerance, ...] = ()
    general: General


class Between(Model):
    """A plain dimension between two parallel planes, shown in one view on one side."""

    planes: tuple[str, str]
    view: str
    side: Side


class Callout(Model):
    """Where a hole feature's size and geometrical specifications are shown."""

    feature: str
    view: str  # One looking along the hole axes
    side: Literal["left", "right"]


class Sheet(Model):
    """ISO 7200 title block fields and the presentation choices for one sheet."""

    title: str
    number: str  # Identification number
    revision: str
    date: str  # Date of issue
    status: Literal["In preparation", "In review", "Released", "Withdrawn"]
    owner: str  # Legal owner
    creator: str
    approver: str = ""  # Empty until a human approves
    document_type: str = "Part drawing"
    reference: str = ""  # Technical reference: the model it was compiled from
    material: str
    mass_kg: float
    revisions: tuple[tuple[str, str, str], ...]  # Revision, description, date
    dimensions: tuple[Between, ...] = ()
    callouts: tuple[Callout, ...] = ()
    # Letter: the view to indicate it in; otherwise the first showing it edge-on.
    datum_views: dict[str, str] = Field(default_factory=dict)
    size: Literal["A4", "A3", "A2", "A1", "A0"] = "A3"  # ISO 5457
    projection: Literal["third", "first"] = "third"  # ISO 5456-2 angle


def distance(a: Feature, b: Feature) -> float | None:
    """The nominal distance between two planes, axes or median planes; None if undefined.

    Planes and median planes must be parallel, an axis parallel to a plane, two axes
    parallel, and a set of holes or shafts a single one.
    """

    def element(f: Feature) -> tuple[str, Vec, Vec] | None:
        if isinstance(f, Plane):
            return "plane", f.normal, f.point
        if isinstance(f, Width):
            return "plane", f.normal, f.center
        if isinstance(f, Holes) and len(f.centers) == 1:
            return "axis", f.axis, f.centers[0]
        return None

    first, second = element(a), element(b)
    if first is None or second is None:
        return None
    (ka, da, pa), (kb, db, pb) = sorted((first, second))  # Axes before planes
    gap = tuple(y - x for x, y in zip(pa, pb))
    if ka == "plane":  # Two planes: parallel, measured along the normal
        if abs(abs(_dot(da, db)) - 1) > 1e-6:
            return None
        return abs(_dot(gap, da))
    if kb == "plane":  # An axis and a plane: the axis lies parallel to the plane
        if abs(_dot(da, db)) > 1e-6:
            return None
        return abs(_dot(gap, db))
    if abs(abs(_dot(da, db)) - 1) > 1e-6:  # Two axes: parallel
        return None
    along = _dot(gap, da)
    return math.sqrt(max(_dot(gap, gap) - along * along, 0.0))


def problems(pmi: PMI) -> list[str]:
    """Malformed references and specifications outside the supported subset."""
    found = []

    def kind(name: str) -> str | None:
        feature = pmi.features.get(name)
        return feature.kind if feature else None

    for letter, feature in pmi.datums.items():
        if not re.fullmatch(r"[A-Z]", letter):
            found.append(f"datum {letter!r}: use one capital letter")
        if kind(feature) not in {"plane"} | OF_SIZE:
            found.append(
                f"datum {letter}: {feature} is not a plane or a feature of size"
            )
    for letter, targets in pmi.targets.items():
        on = pmi.features.get(pmi.datums.get(letter, ""))
        if on is None or not targets:
            found.append(
                f"datum {letter}: targets need an indicated datum, and one target"
            )
            continue
        for n, t in enumerate(targets, start=1):
            name = f"datum target {letter}{n}"
            sized = {"point": (), "line": ("length",), "circle": ("length",)}
            needs = sized.get(t.kind, ("length", "width"))
            if any(getattr(t, f) is None for f in needs) or any(
                getattr(t, f) is not None for f in {"length", "width"} - set(needs)
            ):
                found.append(
                    f"{name}: a {t.kind} takes {' and '.join(needs) or 'no size'}"
                )
            if (t.direction is None) != (t.kind in ("point", "circle")) or (
                t.direction is not None and abs(_dot(t.direction, t.normal)) > 1e-6
            ):
                found.append(
                    f"{name}: a direction across the normal for lines and rectangles only"
                )
            if isinstance(on, Plane) and (
                _dot(t.normal, on.normal) < 1 - 1e-6
                or abs(_dot([p - q for p, q in zip(t.point, on.point)], on.normal))
                > 1e-4
            ):
                found.append(f"{name}: not on {pmi.datums[letter]}, facing out of it")
    for size in pmi.sizes:
        name = f"size of {size.feature}"
        feature = pmi.features.get(size.feature)
        deviations = size.upper is not None and size.lower is not None
        radius = isinstance(feature, Surfaces) and feature.radius is not None
        if not (radius or kind(size.feature) in OF_SIZE):
            found.append(f"{name}: not a feature of size or a radius")
            continue
        internal = isinstance(feature, Holes) and not isinstance(feature, Shafts)
        internal |= isinstance(feature, Width) and feature.internal
        pattern = r"[A-Z]{1,2}\d{1,2}" if internal else r"[a-z]{1,2}\d{1,2}"
        if bool(size.fit) == deviations:
            found.append(f"{name}: give an ISO 286 class or deviations")
        elif size.fit and (radius or not re.fullmatch(pattern, size.fit)):
            found.append(
                f"{name}: {size.fit} is no ISO 286 "
                + ("class for a radius" if radius else "hole" if internal else "shaft")
                + (" class" if not radius else "")
            )
        elif deviations and size.lower >= size.upper:
            found.append(f"{name}: deviations leave no zone")
        if size.requirement and radius:
            found.append(f"{name}: envelope and independency need a feature of size")
    for location in pmi.locations:
        a, b = location.between
        name = f"location of {b} from {a}"
        if a == b or a not in pmi.features or b not in pmi.features:
            found.append(f"{name}: needs two different known features")
        elif distance(pmi.features[a], pmi.features[b]) is None:
            found.append(f"{name}: not two parallel planes, axes or median planes")
        if location.lower >= location.upper:
            found.append(f"{name}: deviations leave no zone")
        # ISO 5458: a position frame locates its feature from its datums by
        # theoretically exact dimensions; a toleranced distance as well conflicts.
        for x, y in ((a, b), (b, a)):
            letters = {k for k, v in pmi.datums.items() if v == y}
            if any(
                t.feature == x
                and t.characteristic == "position"
                and letters & set(t.datums)
                for t in pmi.tolerances
            ):
                found.append(f"{name}: the position of {x} already locates it from {y}")
    for t in pmi.tolerances:
        name = f"{t.characteristic} of {t.feature}"
        rule = SUPPORTED.get(t.characteristic)
        if rule is None:
            found.append(f"{name}: not in the supported {pmi.profile} subset")
            continue
        datums, kinds = rule
        if pmi.profile == ASME and NOT_ASME & {t.characteristic, *t.modifiers}:
            lacking = sorted(NOT_ASME & {t.characteristic, *t.modifiers})
            found.append(f"{name}: ASME Y14.5-2018 has no {', '.join(lacking)}")
        if kind(t.feature) is None:
            found.append(f"{name}: no such feature")
            continue
        if kind(t.feature) not in kinds:
            found.append(f"{name}: does not apply to a {kind(t.feature)} feature")
        if datums == "none" and t.datums:
            found.append(f"{name}: a form tolerance takes no datums")
        if datums == "required" and not t.datums:
            found.append(f"{name}: needs a datum")
        if len(set(t.datums)) != len(t.datums) or len(t.datums) > 3:
            found.append(f"{name}: datums {' '.join(t.datums)} repeat or exceed three")
        for letter in t.datums:
            if letter not in pmi.datums:
                found.append(f"{name}: datum {letter} is not indicated")
            elif pmi.datums[letter] == t.feature:
                found.append(f"{name}: references its own datum {letter}")
        for letter in t.datum_material:
            if letter in pmi.targets:
                found.append(f"{name}: datum {letter} rests on targets, not a size")
            elif letter not in t.datums:
                found.append(
                    f"{name}: modifies datum {letter}, which it does not reference"
                )
            elif kind(pmi.datums.get(letter, "")) not in OF_SIZE:
                found.append(f"{name}: datum {letter} is no feature of size to modify")
        if t.value == 0 and not t.material:
            found.append(f"{name}: a zero tolerance needs a material modifier")
        if t.material and kind(t.feature) not in OF_SIZE:
            found.append(f"{name}: material modifiers need a feature of size")
        if t.diameter and kind(t.feature) not in AXES:
            found.append(f"{name}: a cylindrical zone needs an axis")
        if t.projected is not None and (
            kind(t.feature) not in AXES
            or t.characteristic
            not in {"position", "perpendicularity", "parallelism", "angularity"}
        ):
            found.append(
                f"{name}: a projected zone needs the location or orientation of an axis"
            )
        if {"all_around", "all_over"} & set(
            t.modifiers
        ) and not t.characteristic.startswith("profile"):
            found.append(f"{name}: all around and all over apply to profiles")
        if {"all_around", "all_over"} <= set(t.modifiers):
            found.append(f"{name}: all around or all over, not both")
        if "tangent_plane" in t.modifiers and kind(t.feature) != "plane":
            found.append(f"{name}: a tangent plane needs a planar feature")
        if len(set(t.modifiers)) != len(t.modifiers):
            found.append(f"{name}: modifiers repeat")
    found += [
        f"general specification: datum {letter} is not indicated"
        for letter in pmi.general.datums
        if letter not in pmi.datums
    ]
    return found


def translate(pmi: PMI, profile: str) -> tuple[PMI, list[str]]:
    """The PMI restated in the other profile, and a sentence for each change.

    ISO GPS to ASME Y14.5-2018: coaxiality and concentricity become position of the
    axis, ⌀ zone, same datums and modifiers (concentricity controls median points, so
    approximately); symmetry becomes position of the median plane. Sizes keep ISO 8015
    independency by stating Ⓘ, and an envelope Ⓔ becomes Rule #1's default. Position
    and profile frames sharing their datum references, simultaneous in ASME, keep ISO's
    separate zones as SEP REQT. Frames with a combined zone, any cross section or
    reciprocity have no ASME counterpart: they are left out and listed.

    ASME Y14.5-2018 to ISO GPS: sizes of features of size keep Rule #1 by stating Ⓔ,
    and an independency Ⓘ becomes ISO 8015's default; frames sharing their datum
    references are listed, because ISO does not make them simultaneous.
    """
    if profile == pmi.profile:
        return pmi, []
    to_asme, notes = profile == ASME, []
    of_size = {name for name, f in pmi.features.items() if f.kind in OF_SIZE}
    sizes = []
    for size in pmi.sizes:
        old = size.requirement or ("envelope" if not to_asme else "independency")
        if size.feature not in of_size:
            sizes.append(size)
            continue
        # The meaning to keep: ISO's default is independency, ASME's the envelope.
        default = "envelope" if to_asme else "independency"
        stated = "" if old == default else old
        if size.requirement != stated:
            notes.append(
                f"size of {size.feature}: states "
                + (
                    f"{stated} explicitly"
                    if stated
                    else f"nothing, {old} now the default"
                )
            )
        sizes.append(size.model_copy(update={"requirement": stated}))
    tolerances = []
    for t in pmi.tolerances:
        name = f"{t.characteristic} of {t.feature}"
        if to_asme and NOT_ASME & set(t.modifiers):
            lacking = ", ".join(sorted(NOT_ASME & set(t.modifiers)))
            notes.append(f"{name}: left out; ASME Y14.5-2018 has no {lacking}")
            continue
        if to_asme and t.characteristic in ("coaxiality", "concentricity", "symmetry"):
            notes.append(
                f"{name}: becomes position"
                + (
                    ", which controls the axis, not median points"
                    if t.characteristic == "concentricity"
                    else ""
                )
            )
            t = t.model_copy(update={"characteristic": "position"})
        tolerances.append(t)
    shared: dict[tuple, list[int]] = {}
    for n, t in enumerate(tolerances):
        if t.datums and t.characteristic in (
            "position",
            "profile_line",
            "profile_surface",
        ):
            key = (t.datums, tuple(sorted(t.datum_material.items())))
            shared.setdefault(key, []).append(n)
    for group in (g for g in shared.values() if len(g) > 1):
        for n in group:
            t = tolerances[n]
            name = f"{t.characteristic} of {t.feature}"
            if to_asme and "separate_requirement" not in t.modifiers:
                notes.append(
                    f"{name}: SEP REQT keeps it apart from frames to the same datums"
                )
                tolerances[n] = t.model_copy(
                    update={"modifiers": (*t.modifiers, "separate_requirement")}
                )
            elif not to_asme and "separate_requirement" not in t.modifiers:
                notes.append(
                    f"{name}: ASME made it simultaneous with frames to the same datums; "
                    "ISO does not"
                )
    notes.append(
        "general specification: "
        + (
            "ISO 22081 becomes an unless-otherwise-specified note"
            if to_asme
            else "the unless-otherwise-specified note becomes ISO 22081"
        )
    )
    translated = pmi.model_copy(
        update={
            "profile": profile,
            "sizes": tuple(sizes),
            "tolerances": tuple(tolerances),
        }
    )
    return translated, notes


def specs(pmi: PMI) -> dict[str, dict]:
    """How to find each PMI feature again in a model.

    A plane by its outward normal and offset; holes and shafts by axis and diameter;
    a width by its normal, median offset and width; surfaces by their faces.
    """
    found: dict[str, dict] = {}
    for name, f in pmi.features.items():
        if isinstance(f, Plane):
            found[name] = {
                "kind": "plane",
                "normal": list(f.normal),
                "offset": _dot(f.normal, f.point),
            }
        elif isinstance(f, Holes):
            found[name] = {"kind": f.kind, "axis": list(f.axis), "diameter": f.diameter}
        elif isinstance(f, Width):
            found[name] = {
                "kind": "width",
                "normal": list(f.normal),
                "offset": _dot(f.normal, f.center),
                "width": f.width,
                "internal": f.internal,
            }
        else:
            found[name] = {
                "kind": "surfaces",
                "faces": [face.model_dump(mode="json") for face in f.faces],
            }
    return found


def features(found: Mapping[str, Any]) -> tuple[dict[str, Feature], list[str]]:
    """Validated fingerprints, and the names that matched no geometry or several."""
    failed = [
        f"{name}: {spec['matches']} matches in the model, not exactly one"
        for name, spec in found.items()
        if "matches" in spec
    ]
    ok = {name: spec for name, spec in found.items() if "matches" not in spec}
    return FEATURES.validate_json(json.dumps(ok)), failed


def moved(pmi: PMI, measured: Mapping[str, Feature]) -> list[str]:
    """Features the model no longer holds as the PMI recorded them."""

    def rounded(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 4)
        if isinstance(value, (list, tuple)):
            return [rounded(v) for v in value]
        return (
            {k: rounded(v) for k, v in value.items()}
            if isinstance(value, dict)
            else value
        )

    return [
        f"{name}: not in the model as the PMI recorded it"
        for name, feature in pmi.features.items()
        if name not in measured
        or rounded(measured[name].model_dump()) != rounded(feature.model_dump())
    ]


def _dot(a: Any, b: Any) -> float:
    return sum(x * y for x, y in zip(a, b))


def _num(value: float) -> str:
    """ISO 129-1 value in mm: two decimals at most, no trailing zeros."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


@cache
def _font(height: float) -> Any:
    from ezdxf.fonts import fonts

    return fonts.make_font(FONT, cap_height=height)


def _width(text: str, height: float = H) -> float:
    return _font(height).text_width(text.replace("%%c", "Ø"))


def _clean(view: dict) -> dict:
    """Drop hidden edges a visible edge covers; straighten polylines seen edge-on."""

    def straight(points: list) -> bool:
        (x0, y0), (x1, y1) = points[0], points[-1]
        length = math.hypot(x1 - x0, y1 - y0)
        return length > 1e-9 and all(
            abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) / length < 1e-6
            for x, y in points
        )

    def covers(v: list, h: list) -> bool:
        (ax, ay, bx, by), length = v, math.hypot(v[2] - v[0], v[3] - v[1])
        dx, dy = (bx - ax) / length, (by - ay) / length
        return all(
            abs((x - ax) * dy - (y - ay) * dx) < 1e-6
            and -1e-6 <= (x - ax) * dx + (y - ay) * dy <= length + 1e-6
            for x, y in ((h[0], h[1]), (h[2], h[3]))
        )

    out: dict = {"rows": view["rows"]}
    for kind in ("visible", "hidden"):
        edges = view[kind]
        lines, polylines = list(edges["lines"]), []
        for points in edges["polylines"]:
            if straight(points):
                lines.append([*points[0], *points[-1]])
            else:
                polylines.append(points)
        unique = {}
        for line in lines:
            a, b = sorted((tuple(line[:2]), tuple(line[2:])))
            unique[tuple(round(c, 6) for c in (*a, *b))] = [*a, *b]
        circles = {
            tuple(round(c, 6) for c in circle): circle for circle in edges["circles"]
        }
        out[kind] = {
            "lines": [
                line for line in unique.values() if math.dist(line[:2], line[2:]) > 1e-6
            ],
            "circles": list(circles.values()),
            "polylines": polylines,
        }
    visible = out["visible"]
    out["hidden"]["lines"] = [
        h
        for h in out["hidden"]["lines"]
        if not any(covers(v, h) for v in visible["lines"])
    ]
    seen = {tuple(round(c, 6) for c in circle) for circle in visible["circles"]}
    out["hidden"]["circles"] = [
        c for c in out["hidden"]["circles"] if tuple(round(x, 6) for x in c) not in seen
    ]
    return out


def _bounds(view: dict) -> tuple[float, float, float, float]:
    us, vs = [], []
    for kind in ("visible", "hidden"):
        edges = view[kind]
        for x0, y0, x1, y1 in edges["lines"]:
            us += [x0, x1]
            vs += [y0, y1]
        for x, y, r in edges["circles"]:
            us += [x - r, x + r]
            vs += [y - r, y + r]
        for points in edges["polylines"]:
            us += [p[0] for p in points]
            vs += [p[1] for p in points]
    return min(us), min(vs), max(us), max(vs)


def _edge_on(plane: Plane, rows: Any) -> tuple[int, float] | None:
    """(0, c) when the plane shows as the vertical line u = c, (1, c) horizontal."""
    if abs(_dot(rows[2], plane.normal)) > 1e-6:
        return None
    for i in (0, 1):
        if abs(abs(_dot(rows[i], plane.normal)) - 1) < 1e-6:
            return i, _dot(rows[i], plane.point)
    return None


def _spans(view: dict, line: tuple[int, float]) -> list[tuple[float, float]]:
    """Extents along a plane's edge-on line of the visible edges lying on it."""
    i, c = line
    return [
        tuple(sorted((a[1 - i], b[1 - i])))
        for x0, y0, x1, y1 in view["visible"]["lines"]
        if abs((a := (x0, y0))[i] - c) < 1e-6 and abs((b := (x1, y1))[i] - c) < 1e-6
    ]


TEXT_MODIFIERS = {  # Written after the value, ISO 1101
    "common_zone": "CZ",
    "separate_requirement": "SZ",
    "statistical": "ST",
    "line_element": "LE",
    "any_cross_section": "ACS",
}
CIRCLED_MODIFIERS = {"reciprocity": "R", "free_state": "F", "tangent_plane": "T"}


def _tokens(t: Tolerance) -> list[tuple[str, str]]:
    """The tolerance cell in order: value, zone and requirement modifiers, ISO 1101."""
    tokens = [("text", ("%%c" if t.diameter else "") + _num(t.value))]
    tokens += [("text", TEXT_MODIFIERS[m]) for m in t.modifiers if m in TEXT_MODIFIERS]
    if t.projected is not None:
        tokens += [("circle", "P"), ("text", _num(t.projected))]
    if t.material:
        tokens.append(("circle", t.material))
    tokens += [
        ("circle", CIRCLED_MODIFIERS[m]) for m in t.modifiers if m in CIRCLED_MODIFIERS
    ]
    return tokens


def _token_width(token: tuple[str, str]) -> float:
    return 3.8 if token[0] == "circle" else _width(token[1])


def _cells(t: Tolerance) -> tuple[list[tuple[str, str]], float, float, list[float]]:
    """A frame's cell tokens, tolerance cell width, whole width and datum cell widths."""
    tokens = _tokens(t)
    cell = 3 + sum(map(_token_width, tokens)) + (len(tokens) - 1)
    datums = [2 * H + (4.5 if letter in t.datum_material else 0) for letter in t.datums]
    return tokens, cell, 2 * H + cell + sum(datums), datums


def _deviations(upper: float, lower: float) -> str:
    """Deviations as drawn, ISO 129-1: ±t when symmetric, otherwise upper/lower with
    a zero deviation unsigned."""
    if abs(upper + lower) < 1e-9:
        return f"±{_num(upper)}"
    return "/".join("0" if x == 0 else f"{x:+g}" for x in (upper, lower))


def _size_text(size: Size, feature: Feature) -> str:
    """A size as drawn: count and Ø for holes and shafts, R for radii, then tolerance."""
    if isinstance(feature, Holes):
        count = f"{len(feature.centers)}× " if len(feature.centers) > 1 else ""
        nominal = f"{count}%%c{_num(feature.diameter)}"
    elif isinstance(feature, Width):
        nominal = _num(feature.width)
    else:
        nominal = f"R{_num(getattr(feature, 'radius', None) or 0)}"
    return f"{nominal} {size.fit or _deviations(size.upper or 0, size.lower or 0)}"


def _requirement(sizes: Any, profile: str) -> str:
    """Ⓔ or Ⓘ letters for sizes whose requirement departs from the profile's default."""
    default = "envelope" if profile == ASME else "independency"
    return "".join(
        {"envelope": "E", "independency": "I"}[s.requirement]
        for s in sizes
        if s.requirement not in ("", default)
    )


def _circumcentre(a: Any, b: Any, c: Any) -> tuple[float, float] | None:
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    sa, sb, sc = (p[0] ** 2 + p[1] ** 2 for p in (a, b, c))
    return (
        (sa * (b[1] - c[1]) + sb * (c[1] - a[1]) + sc * (a[1] - b[1])) / d,
        (sa * (c[0] - b[0]) + sb * (a[0] - c[0]) + sc * (b[0] - a[0])) / d,
    )


def _plan(pmi: PMI, sheet: Sheet, views: dict) -> dict[str, dict[str, list[dict]]]:
    """Every annotation, by view and side, before the layout gives it a place."""
    plan: dict[str, dict[str, list[dict]]] = {v: {s: [] for s in SIDES} for v in views}

    def plane(name: str) -> Plane:
        feature = pmi.features[name]
        if not isinstance(feature, Plane):
            raise TypeError(f"{name} is not a plane")
        return feature

    def edge_on(name: str, view: str) -> tuple[int, float]:
        line = _edge_on(plane(name), views[view]["rows"])
        if line is None or not _spans(views[view], line):
            raise ValueError(f"{name} does not show edge-on in the {view} view")
        return line

    def outward(name: str, view: str) -> str:
        rows, n = views[view]["rows"], plane(name).normal
        u, v = _dot(rows[0], n), _dot(rows[1], n)
        return (
            ("right" if u > 0 else "left")
            if abs(u) > 0.5
            else ("above" if v > 0 else "below")
        )

    def anchor(line: tuple[int, float], view: str, at: float) -> tuple[float, float]:
        """A point along the plane's longest visible edge, clear of hole centre lines."""
        low, high = max(_spans(views[view], line), key=lambda s: s[1] - s[0])
        rows, i = views[view]["rows"], line[0]
        crossings = [
            _dot(rows[1 - i], p)
            for f in pmi.features.values()
            if isinstance(f, Holes)
            for p in f.centers
        ]
        along = next(
            (
                x
                for x in (
                    low + (high - low) * f for f in (at, at - 0.1, at + 0.1, at - 0.2)
                )
                if all(abs(x - c) >= 0.08 * (high - low) for c in crossings)
            ),
            low + (high - low) * at,
        )
        return (line[1], along) if i == 0 else (along, line[1])

    def showing(name: str) -> str:
        """The first view showing a plane edge-on."""
        for view in views:
            if _edge_on(plane(name), views[view]["rows"]):
                return view
        raise ValueError(f"{name} shows edge-on in no view")

    def nearer(view: str, low: float, high: float, i: int) -> str:
        """The side nearer an extent across lines of orientation i (0: vertical)."""
        u0, v0, u1, v1 = _bounds(views[view])
        if i == 0:
            return "above" if v1 - high <= low - v0 else "below"
        return "right" if u1 - high <= low - u0 else "left"

    def plane_end(view: str, line: tuple[int, float], side: str) -> tuple[float, float]:
        """Where a dimension on that side meets an edge-on plane."""
        i, c = line
        spans = _spans(views[view], line)
        end = (
            max(s[1] for s in spans)
            if side in ("above", "right")
            else min(s[0] for s in spans)
        )
        return (c, end) if i == 0 else (end, c)

    def located(a: str, b: str) -> tuple:
        """View, side, axis, end points and clearances to dimension a distance in."""
        for view, shown in views.items():
            rows, marks = shown["rows"], []
            for name in (a, b):  # A plane edge-on, or one hole's axis seen end-on
                f = pmi.features[name]
                line = _edge_on(f, rows) if isinstance(f, Plane) else None
                if line is not None and _spans(shown, line):
                    marks.append(("line", line, 0.0))
                elif (
                    isinstance(f, Holes)
                    and len(f.centers) == 1
                    and abs(abs(_dot(rows[2], f.axis)) - 1) < 1e-6
                ):
                    at = (_dot(rows[0], f.centers[0]), _dot(rows[1], f.centers[0]))
                    marks.append(("point", at, f.diameter / 2))
            lines = {m[1][0] for m in marks if m[0] == "line"}
            points = [m[1] for m in marks if m[0] == "point"]
            if len(marks) < 2 or len(lines) > 1:
                continue
            if lines:
                i = lines.pop()
            elif abs(points[0][1] - points[1][1]) < 1e-6:
                i = 0
            elif abs(points[0][0] - points[1][0]) < 1e-6:
                i = 1
            else:
                continue  # Two axes not in line with a sheet axis
            across = [
                v
                for kind, m, _ in marks
                for v in (
                    [x for span in _spans(shown, m) for x in span]
                    if kind == "line"
                    else [m[1 - i]]
                )
            ]
            side = nearer(view, min(across), max(across), i)
            ends = [
                plane_end(view, m, side) if kind == "line" else m
                for kind, m, _ in marks
            ]
            return view, side, i, ends, tuple(r for *_, r in marks)
        raise ValueError(
            f"location of {b} from {a}: no view shows it along a sheet axis"
        )

    def shown_together(planes: list[Plane], name: str) -> tuple[str, list]:
        """The first view showing all the planes edge-on, all one way."""
        for view, shown in views.items():
            lines = [_edge_on(p, shown["rows"]) for p in planes]
            if (
                all(line is not None and _spans(shown, line) for line in lines)
                and len({line[0] for line in lines if line}) == 1
            ):
                return view, lines
        raise ValueError(f"{name} shows edge-on in no view")

    def arc(f: Surfaces, name: str) -> tuple[str, tuple[float, float]]:
        """A view showing a set's cylinder as an arc, and the arc's midpoint there."""
        best = None
        for view in views:
            rows = views[view]["rows"]
            for face in (f for f in f.faces if f.surface == "Cylinder"):
                at = (_dot(rows[0], face.point), _dot(rows[1], face.point))
                for points in views[view]["visible"]["polylines"]:
                    mid = points[len(points) // 2]
                    centre = _circumcentre(points[0], mid, points[-1])
                    if centre is None or abs(math.dist(centre, mid) - f.radius) > 1e-3:
                        continue
                    gap = math.dist(mid, at)  # The face's centroid lies by its arc
                    if gap < f.radius and (best is None or gap < best[0]):
                        best = (gap, view, (mid[0], mid[1]))
        if best is None:
            raise ValueError(f"{name}: no view shows its radius as an arc")
        return best[1], best[2]

    for letter, name in sorted(pmi.datums.items()):
        if not isinstance(pmi.features[name], Plane):
            continue  # Features of size carry theirs at their size or callout
        view = sheet.datum_views.get(letter) or showing(name)
        line = edge_on(name, view)
        plan[view][outward(name, view)].append(
            {
                "kind": "datum",
                "letter": letter,
                "feature": name,
                "at": anchor(line, view, 0.5),
            }
        )
    for n, t in enumerate(pmi.tolerances):
        if isinstance(pmi.features.get(t.feature), Plane):
            view = showing(t.feature)
            line = edge_on(t.feature, view)
            plan[view][outward(t.feature, view)].append(
                {
                    "kind": "frame",
                    "id": n,
                    "tolerance": t,
                    "at": anchor(line, view, 0.25),
                }
            )
    for d in sheet.dimensions:
        lines = [edge_on(name, d.view) for name in d.planes]
        if lines[0][0] != lines[1][0] or (lines[0][0] == 0) != (
            d.side in ("above", "below")
        ):
            raise ValueError(f"{d.planes} cannot be dimensioned {d.side} in {d.view}")
        ends = []
        for line in lines:
            i, c = line
            low = min(s[0] for s in _spans(views[d.view], line))
            high = max(s[1] for s in _spans(views[d.view], line))
            end = high if d.side in ("above", "right") else low
            ends.append((c, end) if i == 0 else (end, c))
        plan[d.view][d.side].append(
            {
                "kind": "dim",
                "axis": lines[0][0],
                "points": ends,
                "radii": (0.0, 0.0),
                "text": _num(abs(lines[1][1] - lines[0][1])),
                "length": abs(lines[1][1] - lines[0][1]),
                "basic": False,
            }
        )
    for c in sheet.callouts:
        holes = pmi.features[c.feature]
        rows = views[c.view]["rows"]
        if (
            not isinstance(holes, Holes)
            or abs(abs(_dot(rows[2], holes.axis)) - 1) > 1e-6
        ):
            raise ValueError(f"{c.view} does not look along the {c.feature} axes")
        centers = [(_dot(rows[0], p), _dot(rows[1], p)) for p in holes.centers]
        sizes = [_size_text(s, holes) for s in pmi.sizes if s.feature == c.feature]
        frames = [
            (n, t) for n, t in enumerate(pmi.tolerances) if t.feature == c.feature
        ]
        circled = _requirement(
            [s for s in pmi.sizes if s.feature == c.feature], pmi.profile
        )
        width = max(
            [_width(" ".join(sizes)) + 4.5 * len(circled)]
            + [_cells(t)[2] for _, t in frames]
        )
        plan[c.view][c.side].append(
            {
                "kind": "callout",
                "feature": c.feature,
                "centers": centers,
                "radius": holes.diameter / 2,
                "text": " ".join(sizes),
                "circled": circled,
                "frames": frames,
                "width": width + 2,
                "datums": sorted(k for k, v in pmi.datums.items() if v == c.feature),
            }
        )
        u0, v0, u1, v1 = _bounds(views[c.view])
        for t in (t for _, t in frames if t.characteristic == "position"):
            for letter in t.datums:
                line = _edge_on(plane(pmi.datums[letter]), rows)
                if line is None:
                    continue  # The primary datum faces the viewer: it orients, not locates.
                i, at = line
                values = sorted(
                    {round(p[i], 6) for p in centers}, key=lambda x: abs(x - at)
                )
                if i == 0:  # Vertical datum line: horizontal dimensions above or below.
                    vs = [p[1] for p in centers]
                    side = "above" if v1 - max(vs) < min(vs) - v0 - 1e-6 else "below"
                    spans = _spans(views[c.view], line)
                    end = (
                        max(s[1] for s in spans)
                        if side == "above"
                        else min(s[0] for s in spans)
                    )
                    datum_point = (at, end)
                else:
                    us = [p[0] for p in centers]
                    side = "right" if u1 - max(us) < min(us) - u0 - 1e-6 else "left"
                    spans = _spans(views[c.view], line)
                    end = (
                        max(s[1] for s in spans)
                        if side == "right"
                        else min(s[0] for s in spans)
                    )
                    datum_point = (end, at)
                for value in values:
                    hole = next(p for p in centers if abs(p[i] - value) < 1e-6)
                    plan[c.view][side].append(
                        {
                            "kind": "dim",
                            "axis": i,
                            "points": [datum_point, hole],
                            "radii": (0.0, holes.diameter / 2),
                            "text": _num(abs(value - at)),
                            "length": abs(value - at),
                            "basic": True,
                        }
                    )
    for name, f in pmi.features.items():
        sizes = [_size_text(s, f) for s in pmi.sizes if s.feature == name]
        frames = [(n, t) for n, t in enumerate(pmi.tolerances) if t.feature == name]
        letters = sorted(k for k, v in pmi.datums.items() if v == name)
        if isinstance(f, Width) and (sizes or frames or letters):
            # A width's size, and its median plane's frames and datums in line with it.
            faces = [
                Plane(
                    point=tuple(
                        c + s * x * f.width / 2 for c, x in zip(f.center, f.normal)
                    ),
                    normal=f.normal,
                    area=f.area,
                )
                for s in (-1, 1)
            ]
            view, lines = shown_together(faces, name)
            spans = [s for line in lines for s in _spans(views[view], line)]
            i = lines[0][0]
            side = nearer(view, min(s[0] for s in spans), max(s[1] for s in spans), i)
            plan[view][side].append(
                {
                    "kind": "width",
                    "feature": name,
                    "axis": i,
                    "points": [plane_end(view, line, side) for line in lines],
                    "text": " ".join(sizes) or _num(f.width),
                    "circled": _requirement(
                        [s for s in pmi.sizes if s.feature == name], pmi.profile
                    ),
                    "length": f.width,
                    "frames": frames,
                    "datums": letters,
                }
            )
        elif isinstance(f, Surfaces) and f.radius is not None and (sizes or frames):
            # A radius callout: its leader ends on the arc.
            view, tip = arc(f, name)
            u0, _, u1, _ = _bounds(views[view])
            width = max([_width(t) for t in sizes] + [_cells(t)[2] for _, t in frames])
            plan[view]["right" if u1 - tip[0] <= tip[0] - u0 else "left"].append(
                {
                    "kind": "callout",
                    "feature": name,
                    "centers": [tip],
                    "radius": 0.0,
                    "text": " ".join(sizes),
                    "frames": frames,
                    "width": width + 2,
                    "datums": [],
                }
            )
    for x in pmi.locations:
        nominal = distance(*(pmi.features[n] for n in x.between))
        view, side, axis, ends, radii = located(*x.between)
        plan[view][side].append(
            {
                "kind": "dim",
                "axis": axis,
                "points": ends,
                "radii": radii,
                "text": f"{_num(nominal or 0)} {_deviations(x.upper, x.lower)}",
                "length": nominal or 0,
                "basic": False,
            }
        )
    for letter, targets in sorted(pmi.targets.items()):
        for n, target in enumerate(targets, start=1):
            view = next(
                (
                    v
                    for v in views
                    if _dot(views[v]["rows"][2], target.normal) > 1 - 1e-6
                ),
                None,
            )
            if view is None:
                raise ValueError(f"datum target {letter}{n}: no view faces it")
            rows = views[view]["rows"]

            def uv(p: Any, rows: Any = rows) -> tuple[float, float]:
                return _dot(rows[0], p), _dot(rows[1], p)

            at, shape = uv(target.point), {}
            if target.kind == "line":
                end = [
                    p + d * (target.length or 0)
                    for p, d in zip(target.point, target.direction or ())
                ]
                shape["line"] = (at, uv(end))
                at = tuple((a + b) / 2 for a, b in zip(at, uv(end)))
            elif target.kind == "circle":
                shape["circle"] = (at, (target.length or 0) / 2)
            elif target.kind == "rectangle":
                d = target.direction or (1.0, 0.0, 0.0)
                n_ = target.normal
                across = (
                    n_[1] * d[2] - n_[2] * d[1],
                    n_[2] * d[0] - n_[0] * d[2],
                    n_[0] * d[1] - n_[1] * d[0],
                )
                half = ((target.length or 0) / 2, (target.width or 0) / 2)
                shape["rectangle"] = [
                    uv(
                        [
                            p + a * d[k] * half[0] + b * across[k] * half[1]
                            for k, p in enumerate(target.point)
                        ]
                    )
                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))
                ]
            else:
                shape["point"] = at
            u0, v0, u1, v1 = _bounds(views[view])
            gaps = {
                "left": at[0] - u0,
                "right": u1 - at[0],
                "below": at[1] - v0,
                "above": v1 - at[1],
            }
            plan[view][min(gaps, key=lambda k: gaps[k])].append(
                {
                    "kind": "target",
                    "letter": letter,
                    "number": n,
                    "target": target,
                    "feature": pmi.datums[letter],
                    "at": at,
                    "shape": shape,
                }
            )
    if pmi.profile == ASME:  # Unidirectional: vertical dimensions' text stands upright
        for sides in plan.values():
            for items in sides.values():
                for item in items:
                    if item["kind"] in ("dim", "width") and item["axis"] == 1:
                        text = _width(item["text"]) + 4.5 * len(item.get("circled", ""))
                        item["beside"] = max(0.0, text + 1 - H)
    return plan


TARGET = 1.6 * H  # Radius of the ISO 5459 datum target frame


def _stack(items: list[dict], beside: bool) -> float:
    """Give each annotation on one side its offset from the view; return the margin."""
    order = {"datum": 0, "frame": 1, "target": 1, "dim": 2, "width": 2, "callout": 3}
    items.sort(key=lambda item: (order[item["kind"]], item.get("length", 0.0)))
    used, line = 0.0, None
    for item in items:
        if item["kind"] == "datum":
            item["offset"], used = 0.0, max(used, 15.0)
        elif item["kind"] == "frame":
            item["offset"] = used + 5
            used = (
                item["offset"] + (_cells(item["tolerance"])[2] if beside else 2 * H) + 2
            )
        elif item["kind"] == "target":
            item["offset"] = used + 5
            used = item["offset"] + 2 * TARGET + 2
        elif item["kind"] in ("dim", "width"):
            line = (
                (used + 10 if used == 0 else used + 8)
                if line is None
                else max(line + 8, used + 3)
            )
            item["offset"] = line
            used = line + 5 + item.get("beside", 0.0)
            frames = [_cells(t)[2] for _, t in item.get("frames", ())]
            if frames:  # In line with the dimension line, then outward
                used = max(
                    used,
                    line + 4 + (max(frames) if beside else len(frames) * (2 * H + 1)),
                )
        else:
            item["offset"] = used + 5
            used = item["offset"] + item["width"]
    return used + 3 if items else 3.0


def _place(
    views: dict,
    plan: dict,
    scale: float,
    blocked: tuple,
    sheet: Paper,
    first_angle: bool = False,
) -> dict[str, tuple[float, float]] | None:
    """View origins at this scale, clear of the title and revision blocks.

    Third angle (ISO 5456-2 method A): the view from above above the front view, the
    view from the right on its right. First angle (method E): below and on its left.
    """
    margins = {
        v: {
            side: _stack(items, side in ("left", "right"))
            for side, items in plan[v].items()
        }
        for v in views
    }
    bounds = {v: _bounds(views[v]) for v in views}
    size = {
        v: ((b[2] - b[0]) * scale, (b[3] - b[1]) * scale) for v, b in bounds.items()
    }
    front, top, right = bounds["FRONT"], bounds["TOP"], bounds["RIGHT"]
    m = margins
    origin = {"FRONT": (0.0, 0.0)}
    if first_angle:
        origin["TOP"] = (
            (top[0] - front[0]) * scale,
            -size["TOP"][1] - max(10.0, m["FRONT"]["below"] + m["TOP"]["above"]),
        )
        origin["RIGHT"] = (
            -size["RIGHT"][0] - max(10.0, m["FRONT"]["left"] + m["RIGHT"]["right"]),
            (right[1] - front[1]) * scale,
        )
    else:
        origin["TOP"] = (
            (top[0] - front[0]) * scale,
            size["FRONT"][1] + max(10.0, m["FRONT"]["above"] + m["TOP"]["below"]),
        )
        origin["RIGHT"] = (
            size["FRONT"][0] + max(10.0, m["FRONT"]["right"] + m["RIGHT"]["left"]),
            (right[1] - front[1]) * scale,
        )

    def box(v: str, dx: float, dy: float) -> tuple[float, float, float, float]:
        (x, y), (w, h), mm = origin[v], size[v], m[v]
        return (
            x + dx - mm["left"],
            y + dy - mm["below"],
            x + dx + w + mm["right"],
            y + dy + h + mm["above"],
        )

    x0, y0, x1, y1 = (c + d for c, d in zip(sheet.frame, (5, 5, -5, -5)))
    # Prefer the placement nearest the centre of the space left of the title block,
    # or above the blocks when they take the frame's width (A4 upright).
    low = [r[3] for r in blocked if r[0] - x0 <= 100]
    if low:
        centre = ((x0 + x1) / 2, (max(low) + y1) / 2)
    else:
        centre = ((x0 + sheet.title[0]) / 2, (y0 + y1) / 2)
    boxes = [box(v, 0, 0) for v in views]
    width = max(b[2] for b in boxes) - min(b[0] for b in boxes)
    height = max(b[3] for b in boxes) - min(b[1] for b in boxes)
    if width > x1 - x0 or height > y1 - y0:
        return None
    best = None
    left, bottom = min(b[0] for b in boxes), min(b[1] for b in boxes)
    for i in range(0, int(x1 - x0 - width) + 1, 2):
        for j in range(0, int(y1 - y0 - height) + 1, 2):
            dx, dy = x0 + i - left, y0 + j - bottom
            placed = [box(v, dx, dy) for v in views]
            if any(
                b[0] < r[2] and r[0] < b[2] and b[1] < r[3] and r[1] < b[3]
                for b in placed
                for r in blocked
            ):
                continue
            middle = (
                (min(b[0] for b in placed) + max(b[2] for b in placed)) / 2,
                (min(b[1] for b in placed) + max(b[3] for b in placed)) / 2,
            )
            score = math.dist(centre, middle)
            if best is None or score < best[0]:
                best = (score, dx, dy)
    if best is None:
        return None
    _, dx, dy = best
    return {v: (origin[v][0] + dx, origin[v][1] + dy) for v in views}


def _line(space: Any, a: Any, b: Any, layer: str = "DIMENSION") -> None:
    space.add_line(a, b, dxfattribs={"layer": layer})


def _text(
    space: Any,
    text: str,
    at: Any,
    *,
    height: float = H,
    align: str = "LEFT",
    rotation: float = 0.0,
    layer: str = "TEXT",
) -> Any:
    from ezdxf.enums import TextEntityAlignment

    entity = space.add_text(
        text,
        height=height,
        dxfattribs={"style": "ISO", "layer": layer, "rotation": rotation},
    )
    return entity.set_placement(at, align=TextEntityAlignment[align])


def _box(
    space: Any, x0: float, y0: float, x1: float, y1: float, layer: str = "DIMENSION"
) -> None:
    space.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        close=True,
        dxfattribs={"layer": layer},
    )


def _arrow(
    space: Any, tip: Any, toward: Any, size: tuple[float, float] = ARROW
) -> None:
    """A closed filled arrowhead with its tip at tip, pointing along unit toward."""
    (x, y), (dx, dy) = tip, toward
    length, half = size
    bx, by = x - dx * length, y - dy * length
    space.add_solid(
        [(x, y), (bx - dy * half, by + dx * half), (bx + dy * half, by - dx * half)],
        dxfattribs={"layer": "DIMENSION"},
    )


def _dimension(
    space: Any,
    axis: int,
    points: list,
    at: float,
    text: str,
    *,
    basic: bool,
    clear: tuple[float, float],
    unidirectional: bool = False,
    circled: str = "",
) -> None:
    """ISO 129-1 linear dimension between two sheet points along axis 0 (x) or 1 (y).

    The dimension line runs at coordinate `at`; extension lines start clear[i] off each
    point and run 2 mm past it. Text sits above the line, or left of it reading from
    the right; unidirectional text (ASME Y14.5) stands upright beside a vertical line.
    Basic (theoretically exact) dimensions are framed; circled letters (Ⓔ, Ⓘ) follow
    the text.
    """
    j = 1 - axis
    for point, gap in zip(points, clear):
        s = 1 if at > point[j] else -1
        start, end = list(point), list(point)
        start[j] += s * gap
        end[j] = at + s * 2
        _line(space, start, end)
    a, b = sorted(p[axis] for p in points)

    def pt(c: float) -> tuple[float, float]:
        return (c, at) if axis == 0 else (at, c)

    unit = (1.0, 0.0) if axis == 0 else (0.0, 1.0)
    back = (-unit[0], -unit[1])
    if b - a >= 2 * ARROW[0] + 2:
        _line(space, pt(a), pt(b))
        _arrow(space, pt(a), back)
        _arrow(space, pt(b), unit)
    else:  # Too short for arrows inside: put them outside, pointing in.
        _line(space, pt(a - ARROW[0] - 3), pt(b + ARROW[0] + 3))
        _arrow(space, pt(a), unit)
        _arrow(space, pt(b), back)
    w, e = _width(text), 0.8
    if w + 2 * e + 1 <= b - a:
        low = (a + b - w) / 2
    else:  # No room between the extension lines: beyond the far one, line under it.
        low = b + ARROW[0] + 1
        _line(space, pt(b), pt(low + w + e))
    if axis == 1 and unidirectional:
        s = 1 if at > points[0][0] else -1  # Beyond the line, away from the feature
        total = w + 4.5 * len(circled)
        x, y = (at + 1.5 if s > 0 else at - 1.5 - total), (a + b - H) / 2
        _text(space, text, (x, y))
        for k, letter in enumerate(circled):
            _circled(space, letter, (x + w + 3 + 4.5 * k, y + H / 2))
        if basic:
            _box(space, x - e, y - e, x + w + e, y + H + e)
        return
    place = (low, at + 1) if axis == 0 else (at - 1, low)
    _text(space, text, place, rotation=0.0 if axis == 0 else 90.0)
    for k, letter in enumerate(circled):
        along = low + w + 3 + 4.5 * k
        _circled(
            space,
            letter,
            (along, at + 1 + H / 2) if axis == 0 else (at - 1 - H / 2, along),
        )
    if basic:
        if axis == 0:
            _box(space, low - e, at + 1 - e, low + w + e, at + 1 + H + e)
        else:
            _box(space, at - 1 - H - e, low - e, at - 1 + e, low + w + e)


def _symbol(space: Any, characteristic: str, cx: float, cy: float) -> None:
    """ISO 1101 symbol strokes, centred in a frame's first cell."""
    s = 2.4
    attribs = {"layer": "DIMENSION"}

    def stroke(*points: tuple[float, float]) -> None:
        space.add_lwpolyline(
            [(cx + x * s, cy + y * s) for x, y in points], dxfattribs=attribs
        )

    if characteristic == "flatness":
        stroke((-1, -0.4), (0.55, -0.4), (1, 0.4), (-0.55, 0.4), (-1, -0.4))
    elif characteristic == "parallelism":
        stroke((-0.85, -0.8), (-0.15, 0.8))
        stroke((0.15, -0.8), (0.85, 0.8))
    elif characteristic == "perpendicularity":
        stroke((-1, -0.8), (1, -0.8))
        stroke((0, -0.8), (0, 0.9))
    elif characteristic == "position":
        space.add_circle((cx, cy), 0.6 * s, dxfattribs=attribs)
        stroke((-1, 0), (1, 0))
        stroke((0, -1), (0, 1))
    elif characteristic == "profile_surface":
        space.add_arc((cx, cy - 0.45 * s), 0.95 * s, 0, 180, dxfattribs=attribs)
        stroke((-0.95, -0.45), (0.95, -0.45))
    elif characteristic == "profile_line":
        space.add_arc((cx, cy - 0.45 * s), 0.95 * s, 0, 180, dxfattribs=attribs)
    elif characteristic == "straightness":
        stroke((-1, 0), (1, 0))
    elif characteristic == "circularity":
        space.add_circle((cx, cy), 0.85 * s, dxfattribs=attribs)
    elif characteristic == "cylindricity":
        space.add_circle((cx, cy), 0.55 * s, dxfattribs=attribs)
        stroke((-1, -0.85), (-0.25, 0.85))
        stroke((0.25, -0.85), (1, 0.85))
    elif characteristic == "angularity":
        stroke((1, -0.75), (-1, -0.75), (0.75, 0.85))
    elif characteristic in ("concentricity", "coaxiality"):
        space.add_circle((cx, cy), 0.45 * s, dxfattribs=attribs)
        space.add_circle((cx, cy), 0.9 * s, dxfattribs=attribs)
    elif characteristic == "symmetry":
        stroke((-1, 0), (1, 0))
        stroke((-0.6, 0.5), (0.6, 0.5))
        stroke((-0.6, -0.5), (0.6, -0.5))
    elif characteristic in ("circular_runout", "total_runout"):
        starts = (-0.75,) if characteristic == "circular_runout" else (-0.95, -0.3)
        if characteristic == "total_runout":
            stroke((-1, -0.85), (0.45, -0.85))
        for x0 in starts:
            stroke((x0, -0.85), (x0 + 0.95, 0.55))
            ux, uy = 0.56, 0.83  # The stroke's direction
            end = (cx + (x0 + 0.95) * s, cy + 0.55 * s)
            _arrow(space, (end[0] + ux * 1.2, end[1] + uy * 1.2), (ux, uy), (1.2, 0.45))


def _frame(
    doc: Any, space: Any, name: str, at: Any, t: Tolerance, attribs: dict
) -> float:
    """A feature control frame block with its meaning in invisible attributes."""
    block = doc.blocks.new(name)
    h = 2 * H
    tokens, cell, width, datum_cells = _cells(t)
    _symbol(block, t.characteristic, h / 2, h / 2)
    x = h + 1.5
    for token in tokens:
        if token[0] == "circle":
            _circled(block, token[1], (x + 1.9, h / 2))
        else:
            _text(block, token[1], (x, (h - H) / 2))
        x += _token_width(token) + 1
    x = h + cell
    for letter, size in zip(t.datums, datum_cells):
        _line(block, (x, 0), (x, h))
        if letter in t.datum_material:
            _text(block, letter, (x + 1.5, (h - H) / 2))
            _circled(
                block, t.datum_material[letter], (x + 1.5 + _width(letter) + 2.4, h / 2)
            )
        else:
            _text(block, letter, (x + h / 2, h / 2), align="MIDDLE_CENTER")
        x += size
    _line(block, (h, 0), (h, h))
    _box(block, 0, 0, width, h)
    _attributes(doc, space, block, name, at, attribs)
    return width


def _circled(space: Any, letter: str, center: tuple[float, float]) -> None:
    """A modifier letter in a circle: M, L, P, F, T or R."""
    space.add_circle(center, 1.9, dxfattribs={"layer": "DIMENSION"})
    _text(space, letter, center, height=2.5, align="MIDDLE_CENTER")


def _attributes(
    doc: Any, space: Any, block: Any, name: str, at: Any, values: dict
) -> Any:
    for tag in values:
        block.add_attdef(
            tag,
            (0, 0),
            dxfattribs={"height": 2.5, "flags": 1, "style": "ISO", "layer": "TEXT"},
        )
    ref = space.add_blockref(name, at, dxfattribs={"layer": "DIMENSION"})
    return ref.add_auto_attribs(values)


def _frame_attribs(t: Tolerance) -> dict[str, str]:
    return {
        "FEATURE": t.feature,
        "CHARACTERISTIC": t.characteristic,
        "VALUE": _num(t.value),
        "ZONE": "DIAMETER" if t.diameter else "",
        "MATERIAL": t.material,
        "DATUMS": " ".join(
            f"{d}({t.datum_material[d]})" if d in t.datum_material else d
            for d in t.datums
        ),
        "MODIFIERS": " ".join(t.modifiers),
        "PROJECTED": _num(t.projected) if t.projected is not None else "",
    }


def _title_block(doc: Any, msp: Any, sheet: Sheet, scale: float, at: Any) -> None:
    """ISO 7200 fields; values are visible, editable attributes."""
    block = doc.blocks.new("TITLE_BLOCK")
    cells = {  # Tag: label, x0, y0, x1, y1 within the 180 x 40 block
        "OWNER": ("Legal owner", 0, 30, 50, 40),
        "CREATOR": ("Created by", 0, 20, 50, 30),
        "APPROVER": ("Approved by", 0, 10, 50, 20),
        "REFERENCE": ("Technical reference", 0, 0, 50, 10),
        "TITLE": ("Title", 50, 20, 120, 40),
        "MATERIAL": ("Material", 50, 10, 95, 20),
        "MASS": ("Mass", 95, 10, 120, 20),
        "TYPE": ("Document type", 50, 0, 95, 10),
        "SCALE": ("Scale", 95, 0, 120, 10),
        "STATUS": ("Document status", 120, 30, 180, 40),
        "NUMBER": ("Identification number", 120, 10, 180, 30),
        "REVISION": ("Rev", 120, 0, 135, 10),
        "DATE": ("Date of issue", 135, 0, 165, 10),
        "SHEET": ("Sheet", 165, 0, 180, 10),
    }
    scale_text = f"{_num(scale)}:1" if scale > 1 else f"1:{_num(1 / scale)}"
    values = {
        "OWNER": sheet.owner,
        "CREATOR": sheet.creator,
        "APPROVER": sheet.approver,
        "REFERENCE": sheet.reference,
        "TITLE": sheet.title,
        "MATERIAL": sheet.material,
        "MASS": f"{sheet.mass_kg:.3g} kg",
        "TYPE": sheet.document_type,
        "SCALE": scale_text,
        "STATUS": sheet.status,
        "NUMBER": sheet.number,
        "REVISION": sheet.revision,
        "DATE": sheet.date,
        "SHEET": "1/1",
    }
    for tag, (label, x0, y0, x1, y1) in cells.items():
        _box(block, x0, y0, x1, y1, layer="TITLE")
        _text(block, label, (x0 + 1, y1 - 0.8), height=2.5, align="TOP_LEFT")
        big = tag in ("TITLE", "NUMBER")
        height = 5.0 if big and _width(values[tag], 5.0) < x1 - x0 - 3 else H
        squeeze = min(1.0, (x1 - x0 - 3) / max(_width(values[tag], height), 1e-9))
        block.add_attdef(
            tag,
            (x0 + 1.5, y0 + 1.5 if not big else (y0 + y1 - height) / 2 - 1),
            dxfattribs={
                "height": height,
                "width": squeeze,
                "style": "ISO",
                "layer": "TEXT",
            },
        )
    _box(block, 0, 0, 180, 40, layer="FRAME")
    ref = msp.add_blockref("TITLE_BLOCK", at, dxfattribs={"layer": "TITLE"})
    ref.add_auto_attribs(values)


def undrawn(pmi: PMI, sheet: Sheet) -> list[str]:
    """PMI this drawing compiler cannot place: refused, never left off silently.

    It draws datums on planes, on holes and shafts under their callouts and on widths
    in line with their size; datum targets on planes, in the view facing them; sizes
    of holes and shafts in callouts, widths as dimensions and radii at their arc;
    frames the same ways; and toleranced locations between planes and single axes.
    Not drawn: datums on surface sets, frames on sets without one radius, and
    locations of median planes.
    """
    found = []
    callouts = {c.feature for c in sheet.callouts}
    for letter in pmi.targets:
        if not isinstance(pmi.features.get(pmi.datums.get(letter, "")), Plane):
            found.append(f"datum {letter}: targets are drawn on planes only")
    for letter, name in pmi.datums.items():
        feature = pmi.features.get(name)
        if isinstance(feature, Surfaces):
            found.append(f"datum {letter}: datums on surface sets are not drawn")
        elif isinstance(feature, Holes) and name not in callouts:
            found.append(f"datum {letter}: no callout places {name}")
    found += [
        f"size of {size.feature}: no callout places it"
        for size in pmi.sizes
        if isinstance(pmi.features.get(size.feature), Holes)
        and size.feature not in callouts
    ]
    for location in pmi.locations:
        if any(isinstance(pmi.features.get(n), Width) for n in location.between):
            a, b = location.between
            found.append(f"location of {b} from {a}: median planes are not dimensioned")
    for t in pmi.tolerances:
        feature = pmi.features.get(t.feature)
        if pmi.profile == ASME and {"separate_requirement", "line_element"} & set(
            t.modifiers
        ):
            found.append(
                f"{t.characteristic} of {t.feature}: ASME's SEP REQT and EACH ELEMENT "
                "notes under frames are not drawn yet"
            )
        if isinstance(feature, Holes) and t.feature not in callouts:
            found.append(f"{t.characteristic} of {t.feature}: no callout places it")
        elif isinstance(feature, Surfaces) and feature.radius is None:
            found.append(
                f"{t.characteristic} of {t.feature}: frames on surface sets without "
                "one radius are not drawn"
            )
    return found


def compile_drawing(pmi: PMI, sheet: Sheet, views: dict) -> Any:
    """The DXF drawing: views, dimensions, datums, frames, notes and title block.

    views maps FRONT, TOP and RIGHT to their rows (model axes to sheet right, up and
    toward the viewer) and visible and hidden edges at 1:1. Raises ValueError when
    the PMI is malformed or the views do not fit an A3 sheet at an ISO 5455 scale.
    """
    import ezdxf

    if found := problems(pmi) + undrawn(pmi, sheet):
        raise ValueError("; ".join(found))
    views = {name: _clean(view) for name, view in views.items()}
    plan = _plan(pmi, sheet, views)
    space = paper(*PAPER[sheet.size])
    title, notes, frame = space.title, space.notes, space.frame
    # Revisions top right; on an upright sheet, above the notes, clear of the centring
    # mark.
    rows = 7 * (1 + len(sheet.revisions))
    top = frame[3] if title[0] - frame[0] > 100 else notes[3] + rows
    blocked = (
        (title[0], title[1], notes[2], notes[3]),
        (title[0], top - rows, frame[2], top),
    )
    for scale in SCALES:
        origins = _place(
            views, plan, scale, blocked, space, sheet.projection == "first"
        )
        if origins is not None:
            break
    else:
        raise ValueError(
            f"The views do not fit an {sheet.size} sheet at any ISO 5455 scale"
        )

    doc = ezdxf.new("R2018", units=4)  # Millimetres
    doc.header["$MEASUREMENT"] = 1
    doc.linetypes.add("DASHED_ISO", pattern=[4.5, 3.0, -1.5], description="Dashed")
    doc.linetypes.add(
        "CENTER_ISO", pattern=[18.0, 12.0, -2.0, 2.0, -2.0], description="Long dash dot"
    )
    doc.linetypes.add(
        "PHANTOM_ISO",
        pattern=[21.0, 12.0, -3.0, 0.0, -3.0, 0.0, -3.0],
        description="Long dash double dot",
    )
    for name, (linetype, weight) in LAYERS.items():
        doc.layers.add(name, linetype=linetype, lineweight=weight)
    doc.styles.add("ISO", font=FONT)
    msp = doc.modelspace()

    # Sheet edge (thin, for extents), frame and centring marks: ISO 5457.
    _box(msp, 0, 0, *space.sheet, layer="SHEET")
    _box(msp, *frame, layer="FRAME")
    cx, cy = (frame[0] + frame[2]) / 2, (frame[1] + frame[3]) / 2
    for a, b in (
        ((0, cy), (frame[0] + 5, cy)),
        ((space.sheet[0], cy), (frame[2] - 5, cy)),
        ((cx, 0), (cx, frame[1] + (0 if title[0] <= cx <= title[2] else 5))),
        ((cx, space.sheet[1]), (cx, frame[3] - 5)),
    ):
        _line(msp, a, b, layer="FRAME")

    for name, view in views.items():
        _draw_view(doc, msp, pmi, view, plan[name], origins[name], scale)
    _title_block(doc, msp, sheet, scale, title[:2])
    _notes(doc, msp, pmi, notes, sheet.projection)
    _revisions(msp, sheet, title[0], top)
    return doc


def _draw_view(
    doc: Any,
    msp: Any,
    pmi: PMI,
    view: dict,
    plan: dict[str, list[dict]],
    origin: tuple[float, float],
    scale: float,
) -> None:
    u0, v0, u1, v1 = _bounds(view)
    ox, oy = origin
    rows = view["rows"]

    def sheet(u: float, v: float) -> tuple[float, float]:
        return ox + (u - u0) * scale, oy + (v - v0) * scale

    for kind, layer in (("hidden", "HIDDEN"), ("visible", "VISIBLE")):
        edges = view[kind]
        for x0, y0, x1, y1 in edges["lines"]:
            _line(msp, sheet(x0, y0), sheet(x1, y1), layer=layer)
        for x, y, r in edges["circles"]:
            msp.add_circle(sheet(x, y), r * scale, dxfattribs={"layer": layer})
        for points in edges["polylines"]:
            msp.add_lwpolyline([sheet(*p) for p in points], dxfattribs={"layer": layer})

    over = 2.5 / scale  # Centre lines run 2.5 mm past the outline.
    for feature in pmi.features.values():
        if not isinstance(feature, Holes):
            continue
        centers = [(_dot(rows[0], p), _dot(rows[1], p)) for p in feature.centers]
        r = feature.diameter / 2
        if abs(abs(_dot(rows[2], feature.axis)) - 1) < 1e-6:
            for i in (0, 1):  # One centre line per row and per column of holes.
                groups: dict[float, list[float]] = {}
                for p in centers:
                    groups.setdefault(round(p[1 - i], 6), []).append(p[i])
                for fixed, along in groups.items():
                    a, b = min(along) - r - over, max(along) + r + over
                    ends = (
                        ((a, fixed), (b, fixed)) if i == 0 else ((fixed, a), (fixed, b))
                    )
                    _line(msp, sheet(*ends[0]), sheet(*ends[1]), layer="CENTER")
        else:
            du, dv = _dot(rows[0], feature.axis), _dot(rows[1], feature.axis)
            half = feature.length / 2 + over
            for u, v in centers:
                _line(
                    msp,
                    sheet(u - du * half, v - dv * half),
                    sheet(u + du * half, v + dv * half),
                    layer="CENTER",
                )

    edge = {
        "left": ox,
        "right": ox + (u1 - u0) * scale,
        "below": oy,
        "above": oy + (v1 - v0) * scale,
    }
    for side, items in plan.items():
        sx, sy = SIDES[side]
        for item in items:
            out = edge[side] + (sx or sy) * item["offset"]
            if item["kind"] == "datum":
                _datum(doc, msp, item, sheet(*item["at"]), (sx, sy), edge[side])
            elif item["kind"] == "frame":
                t = item["tolerance"]
                tip = sheet(*item["at"])
                corner = (tip[0], out) if sy else (out, tip[1])
                _line(msp, tip, corner)
                _arrow(msp, tip, (-sx, -sy))
                # All around and all over: one or two circles where the leader bends.
                for r in (1.5, 2.2)[
                    : ("all_around" in t.modifiers) + 2 * ("all_over" in t.modifiers)
                ]:
                    msp.add_circle(corner, r, dxfattribs={"layer": "DIMENSION"})
                at = (
                    (corner[0], corner[1] - (2 * H if sy < 0 else 0))
                    if sy
                    else (
                        corner[0] - (_cells(t)[2] if sx < 0 else 0),
                        corner[1] - H,
                    )
                )
                _frame(doc, msp, f"FCF_{item['id']}", at, t, _frame_attribs(t))
            elif item["kind"] == "dim":
                points = [sheet(*p) for p in item["points"]]
                clear = tuple(GAP + r * scale for r in item["radii"])
                _dimension(
                    msp,
                    item["axis"],
                    points,
                    out,
                    item["text"],
                    basic=item["basic"],
                    clear=clear,
                    unidirectional=pmi.profile == ASME,
                )
            elif item["kind"] == "width":
                points = [sheet(*p) for p in item["points"]]
                _dimension(
                    msp,
                    item["axis"],
                    points,
                    out,
                    item["text"],
                    basic=False,
                    clear=(GAP, GAP),
                    unidirectional=pmi.profile == ASME,
                    circled=item["circled"],
                )
                _in_line(doc, msp, item, points, out, (sx, sy))
            elif item["kind"] == "target":
                _target(doc, msp, item, sheet, scale, out, (sx, sy))
            else:
                _callout(doc, msp, item, sheet, scale, out, sx)


def _datum(doc: Any, msp: Any, item: dict, at: Any, toward: Any, edge: float) -> None:
    """ISO 5459 datum feature indicator: filled triangle, leader, framed letter."""
    letter, (dx, dy) = item["letter"], toward
    block = doc.blocks.new(f"DATUM_{letter}")
    # The leader reaches from the feature line past the view edge to the frame.
    reach = abs(edge - (at[0] if dx else at[1]))
    px, py = -dy, dx
    block.add_solid(
        [(px * 2, py * 2), (-px * 2, -py * 2), (dx * 3.5, dy * 3.5)],
        dxfattribs={"layer": "DIMENSION"},
    )
    near = reach + 6.5
    _line(block, (dx * 3.5, dy * 3.5), (dx * near, dy * near))
    cx, cy = dx * (near + H), dy * (near + H)
    _box(block, cx - H, cy - H, cx + H, cy + H)
    _text(block, letter, (cx, cy), align="MIDDLE_CENTER")
    _attributes(
        doc,
        msp,
        block,
        f"DATUM_{letter}",
        at,
        {"LETTER": letter, "FEATURE": item["feature"]},
    )


def _callout(
    doc: Any, msp: Any, item: dict, sheet: Any, scale: float, out: float, sx: int
) -> None:
    """A hole callout: leader to the hole nearest the side, size above, frames below."""
    points = [sheet(*p) for p in item["centers"]]
    hole = (
        min(points, key=lambda p: p[0]) if sx < 0 else max(points, key=lambda p: p[0])
    )
    width = item["width"]
    near = out
    land_y = hole[1] + 6
    x0 = near - width if sx < 0 else near
    _line(msp, (x0, land_y), (x0 + width, land_y))
    end = (near, land_y)
    dx, dy = hole[0] - end[0], hole[1] - end[1]
    length = math.hypot(dx, dy)
    r = item["radius"] * scale
    tip = (hole[0] - dx / length * r, hole[1] - dy / length * r)
    _line(msp, end, tip)
    _arrow(msp, tip, (dx / length, dy / length))
    _text(msp, item["text"], (x0 + 1, land_y + 1))
    for k, letter in enumerate(item.get("circled", "")):
        x = x0 + 1 + _width(item["text"]) + 3 + 4.5 * k
        _circled(msp, letter, (x, land_y + 1 + H / 2))
    y = land_y - 1 - 2 * H
    for n, t in item["frames"]:
        _frame(doc, msp, f"FCF_{n}", (x0 + 1, y), t, _frame_attribs(t))
        y -= 2 * H + 1
    # A datum on the feature of size: its indicator hangs under the frames, or under
    # the size when there are none (ISO 5459).
    bottom = y + 2 * H + 1 if item["frames"] else land_y
    for k, letter in enumerate(item.get("datums", ())):
        at = (x0 + 1 + 2 * H + 4 * H * k, bottom)
        _datum(
            doc,
            msp,
            {"letter": letter, "feature": item["feature"]},
            at,
            (0, -1),
            at[1] - 1,
        )


def _in_line(
    doc: Any, msp: Any, item: dict, points: list, at: float, toward: tuple[int, int]
) -> None:
    """A median plane's frames and datums, in line with its width's dimension line.

    ISO 1101 and ISO 5459: the leader or the datum triangle meets the extension line
    at the dimension line. Both go off the near end, the far one keeping any text
    that does not fit between the extension lines; a datum on a toleranced width
    hangs from its frames.
    """
    axis, (sx, sy) = item["axis"], toward
    out = sy if axis == 0 else sx  # Away from the view, across the dimension line
    a = min(p[axis] for p in points)

    def pt(along: float, across: float) -> tuple[float, float]:
        return (along, across) if axis == 0 else (across, along)

    letters = [{"letter": k, "feature": item["feature"]} for k in item["datums"]]
    if not item["frames"]:
        for k, letter in enumerate(letters):
            _datum(doc, msp, letter, pt(a, at), pt(-1, 0), a - 3 - 4 * H * k)
        return
    bend = pt(a - 6, at)
    _line(msp, pt(a, at), bend)
    _arrow(msp, pt(a, at), pt(1, 0))
    corner = pt(a - 6, at + out * (3 + H)) if axis == 0 else pt(a - 6, at + out * 3)
    _line(msp, bend, corner)
    x, y = corner
    for n, t in item["frames"]:
        width = _cells(t)[2]
        if axis == 0:  # Frames stack outward, the first meeting the leader at its side
            origin = (x - width, y - H)
            y += out * (2 * H + 1)
        else:
            origin = (x if out > 0 else x - width, y - H)
            y -= 2 * H + 1
        _frame(doc, msp, f"FCF_{n}", origin, t, _frame_attribs(t))
        edge = (origin, width)
    (fx, fy), width = edge
    for k, letter in enumerate(letters):  # On the outermost frame, facing outward
        if axis == 0:
            base = (fx + 2 * H + 4 * H * k, fy + (2 * H if out > 0 else 0))
            _datum(doc, msp, letter, base, (0, out), base[1] + out)
        else:
            base = (fx + 2 * H + 4 * H * k, fy)
            _datum(doc, msp, letter, base, (0, -1), base[1] - 1)


def _target(
    doc: Any,
    msp: Any,
    item: dict,
    sheet: Any,
    scale: float,
    out: float,
    toward: tuple[int, int],
) -> None:
    """An ISO 5459 datum target in the view facing it, and its frame on a leader.

    A point is a cross; a line runs between crosses; an area is hatched within a long
    dashed double dotted outline. The frame shows the area's size above and the
    target's letter and number below.
    """
    shape, (sx, sy), t = item["shape"], toward, item["target"]

    def cross(p: tuple[float, float]) -> None:
        for dx, dy in ((1.5, 1.5), (1.5, -1.5)):
            _line(msp, (p[0] - dx, p[1] - dy), (p[0] + dx, p[1] + dy), layer="VISIBLE")

    if "point" in shape:
        cross(sheet(*shape["point"]))
    elif "line" in shape:
        ends = [sheet(*p) for p in shape["line"]]
        _line(msp, *ends, layer="PHANTOM")
        for p in ends:
            cross(p)
    else:
        hatch = msp.add_hatch(dxfattribs={"layer": "DIMENSION"})
        hatch.set_pattern_fill("ANSI31", scale=0.3)
        if "circle" in shape:
            centre, r = sheet(*shape["circle"][0]), shape["circle"][1] * scale
            msp.add_circle(centre, r, dxfattribs={"layer": "PHANTOM"})
            hatch.paths.add_edge_path().add_arc(centre, r, 0, 360)
        else:
            corners = [sheet(*p) for p in shape["rectangle"]]
            msp.add_lwpolyline(corners, close=True, dxfattribs={"layer": "PHANTOM"})
            hatch.paths.add_polyline_path(corners, is_closed=True)
    tip = sheet(*item["at"])
    corner = (tip[0], out) if sy else (out, tip[1])
    _line(msp, tip, corner)
    letter, n = item["letter"], item["number"]
    name = f"TARGET_{letter}{n}"
    block = doc.blocks.new(name)
    centre = (sx * TARGET, sy * TARGET)
    block.add_circle(centre, TARGET, dxfattribs={"layer": "DIMENSION"})
    _line(block, (centre[0] - TARGET, centre[1]), (centre[0] + TARGET, centre[1]))
    size = {
        "circle": f"%%c{_num(t.length or 0)}",
        "rectangle": f"{_num(t.length or 0)}×{_num(t.width or 0)}",
    }
    if t.kind in size:
        _text(
            block,
            size[t.kind],
            (centre[0], centre[1] + 1.2),
            height=2.5,
            align="BOTTOM_CENTER",
        )
    _text(
        block,
        f"{letter}{n}",
        (centre[0], centre[1] - 1.2),
        height=2.5,
        align="TOP_CENTER",
    )
    _attributes(
        doc,
        msp,
        block,
        name,
        corner,
        {
            "LETTER": letter,
            "NUMBER": str(n),
            "KIND": t.kind,
            "FEATURE": item["feature"],
        },
    )


def _notes(doc: Any, msp: Any, pmi: PMI, box: tuple, projection: str) -> None:
    """Projection symbol, units and the tolerancing references above the title block."""
    x0, y0, x1, y1 = box
    _box(msp, x0, y0, x1, y1, layer="TITLE")
    # ISO 5456-2 symbol: a truncated cone, narrow end left, and its end view; third
    # angle puts the end view left of the cone, first angle right of it.
    cx, cy = x0 + 9, y0 + 12
    circles, cone = (cx, cx + 9) if projection == "third" else (cx + 19, cx - 1)
    for r in (2.5, 5.0):
        msp.add_circle((circles, cy), r, dxfattribs={"layer": "VISIBLE"})
    msp.add_lwpolyline(
        [(cone, cy - 2.5), (cone + 10, cy - 5), (cone + 10, cy + 5), (cone, cy + 2.5)],
        close=True,
        dxfattribs={"layer": "VISIBLE"},
    )
    _line(msp, (cx - 7, cy), (cx + 26, cy), layer="CENTER")

    _text(msp, "Dimensions in mm", (x0 + 1.5, y0 + 1.5), height=2.5)
    g, asme = pmi.general, pmi.profile == ASME
    _text(msp, "ASME Y14.5-2018" if asme else "ISO 8015", (x0 + 40, y0 + 17.5))
    _text(
        msp,
        f"Unless otherwise specified: sizes ±{_num(g.size)}"
        if asme
        else f"General tolerances ISO 22081: sizes ±{_num(g.size)}",
        (x0 + 40, y0 + 10.5),
    )
    general = Tolerance(
        feature="*", characteristic="profile_surface", value=g.profile, datums=g.datums
    )
    width = _frame(
        doc,
        msp,
        "GENERAL",
        (x0 + 40, y0 + 1),
        general,
        {
            "SIZE": _num(g.size),
            "PROFILE": _num(g.profile),
            "DATUMS": " ".join(g.datums),
        },
    )
    if asme:  # ISO 22081 says this itself; an ASME drawing states it
        _text(msp, "all untoleranced surfaces", (x0 + 42 + width, y0 + 2.5), height=2.5)


def _revisions(msp: Any, sheet: Sheet, x0: float, top: float) -> None:
    """Revision history table in the top-right corner."""
    columns = (
        ("Rev", 0, 15),
        ("Description", 15, 120),
        ("Date", 120, 150),
        ("Approved", 150, 180),
    )
    rows = [("Rev", "Description", "Date", "Approved")] + [
        (rev, text, date, sheet.approver) for rev, text, date in sheet.revisions
    ]
    for n, row in enumerate(rows):
        y1 = top - 7 * n
        for value, (_, a, b) in zip(row, columns):
            _box(msp, x0 + a, y1 - 7, x0 + b, y1, layer="TITLE")
            if value:
                _text(msp, value, (x0 + a + 1.5, y1 - 5), height=2.5 if n == 0 else H)


def write(doc: Any, dxf: Path, svg_path: Path, pdf_path: Path | None = None) -> None:
    """Save the DXF, its SVG rendering and, given a path, its PDF for printing."""
    doc.saveas(dxf)
    svg_path.write_text(svg(dxf), encoding="utf-8")
    if pdf_path is not None:
        pdf_path.write_bytes(pdf(dxf))


def _render_config() -> Any:
    from ezdxf.addons.drawing.config import (
        BackgroundPolicy,
        ColorPolicy,
        Configuration,
        LineweightPolicy,
    )

    return Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=ColorPolicy.BLACK,
        lineweight_policy=LineweightPolicy.ABSOLUTE,
    )


def _sheet_of(doc: Any) -> tuple[float, float]:
    """A compiled drawing's sheet size, from its edge on the SHEET layer."""
    edge = next(
        (e for e in doc.modelspace().query("LWPOLYLINE") if e.dxf.layer == "SHEET"),
        None,
    )
    if edge is None:
        return PAPER["A3"]
    points = list(edge.get_points("xy"))
    return max(x for x, _ in points), max(y for _, y in points)


def svg(path: Path) -> str:
    """The DXF rendered as an SVG of its sheet for review, black on white."""
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext, layout
    from ezdxf.addons.drawing import svg as svg_backend

    doc = ezdxf.readfile(path)
    backend = svg_backend.SVGBackend()
    Frontend(RenderContext(doc), backend, config=_render_config()).draw_layout(
        doc.modelspace()
    )
    page = layout.Page(*_sheet_of(doc), layout.Units.mm, margins=layout.Margins.all(0))
    return backend.get_string(page)


def pdf(path: Path) -> bytes:
    """The DXF rendered as a vector PDF of its sheet at 1:1, black on white.

    A minimal PDF writer behind ezdxf's drawing frontend, which turns text into
    filled outlines: no font embedding and no further dependency. PyMuPDF, ezdxf's
    PDF backend, is AGPL, and matplotlib fills glyphs such as Ø solid.
    """
    import zlib

    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.backend import BackendInterface
    from ezdxf.path import Command

    ops: list[str] = [
        "2.83465 0 0 2.83465 0 0 cm 0 J 1 j"
    ]  # mm, butt caps, round joins

    def colour(hex_colour: str) -> str:
        return " ".join(
            f"{int(hex_colour[k : k + 2], 16) / 255:.3f}" for k in (1, 3, 5)
        )

    def trace(path: Any) -> None:
        ops.append(f"{path.start.x:.3f} {path.start.y:.3f} m")
        current = path.start
        for cmd in path.commands():
            end = cmd.end
            if cmd.type == Command.MOVE_TO:
                ops.append(f"{end.x:.3f} {end.y:.3f} m")
            elif cmd.type == Command.LINE_TO:
                ops.append(f"{end.x:.3f} {end.y:.3f} l")
            else:  # Quadratic curves become cubic ones
                c1, c2 = (
                    (cmd.ctrl1, cmd.ctrl2)
                    if cmd.type == Command.CURVE4_TO
                    else (
                        current + (cmd.ctrl - current) * (2 / 3),
                        end + (cmd.ctrl - end) * (2 / 3),
                    )
                )
                ops.append(
                    f"{c1.x:.3f} {c1.y:.3f} {c2.x:.3f} {c2.y:.3f} {end.x:.3f} {end.y:.3f} c"
                )
            current = end

    def stroke(points: list, props: Any) -> None:
        width = max(props.lineweight, 0.13)
        ops.append(f"{width:.3f} w {colour(props.color)} RG")
        ops.append(
            " ".join(
                f"{x:.3f} {y:.3f} {o}"
                for (x, y), o in zip(points, "m" + "l" * len(points))
            )
        )
        ops.append("S")

    class Writer(BackendInterface):
        def configure(self, config: Any) -> None: ...
        def enter_entity(self, entity: Any, properties: Any) -> None: ...
        def exit_entity(self, entity: Any) -> None: ...
        def set_background(self, color: Any) -> None: ...
        def draw_image(self, image_data: Any, properties: Any) -> None: ...
        def clear(self) -> None: ...
        def finalize(self) -> None: ...

        def draw_point(self, pos: Any, properties: Any) -> None:
            stroke([(pos.x, pos.y), (pos.x + 0.1, pos.y)], properties)

        def draw_line(self, start: Any, end: Any, properties: Any) -> None:
            stroke([(start.x, start.y), (end.x, end.y)], properties)

        def draw_solid_lines(self, lines: Any, properties: Any) -> None:
            for start, end in lines:
                self.draw_line(start, end, properties)

        def draw_path(self, path: Any, properties: Any) -> None:
            ops.append(
                f"{max(properties.lineweight, 0.13):.3f} w {colour(properties.color)} RG"
            )
            trace(path)
            ops.append("S")

        def draw_filled_paths(self, paths: Any, properties: Any) -> None:
            ops.append(f"{colour(properties.color)} rg")
            for p in paths:
                trace(p)
                ops.append("h")
            ops.append("f*")  # Even-odd: counters and crossings stay open

        def draw_filled_polygon(self, points: Any, properties: Any) -> None:
            vertices = [(v.x, v.y) for v in points.vertices()]
            ops.append(f"{colour(properties.color)} rg")
            ops.append(
                " ".join(
                    f"{x:.3f} {y:.3f} {o}"
                    for (x, y), o in zip(vertices, "m" + "l" * len(vertices))
                )
            )
            ops.append("h f*")

    doc = ezdxf.readfile(path)
    Frontend(RenderContext(doc), Writer(), config=_render_config()).draw_layout(
        doc.modelspace()
    )
    content = zlib.compress("\n".join(ops).encode("ascii"))
    width, height = (round(x * 72 / 25.4, 3) for x in _sheet_of(doc))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
        "/Contents 4 0 R /Resources << >> >>".encode(),
        f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode()
        + content
        + b"\nendstream",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def outlines(
    item: "Tolerance | str | tuple[str, str]",
) -> list[list[tuple[float, float]]]:
    """An annotation drawn as on the drawing, as polylines in mm from its origin.

    A frame (a Tolerance) with its bottom left corner at the origin, a string set
    from there, or ("datum", letter): its framed letter. Text is its glyph outlines.
    For graphical PMI in AP242, which has no fonts.
    """
    import ezdxf
    from ezdxf import path as paths
    from ezdxf.addons import text2path

    doc = ezdxf.new("R2018")
    doc.styles.add("ISO", font=FONT)
    msp = doc.modelspace()
    if isinstance(item, Tolerance):
        _frame(doc, msp, "FRAME", (0, 0), item, {})
    elif isinstance(item, str):
        _text(msp, item, (0, 0))
    else:
        _box(msp, 0, 0, 2 * H, 2 * H)
        _text(msp, item[1], (H, H), align="MIDDLE_CENTER")
    found: list[list[tuple[float, float]]] = []

    def walk(entities: Any) -> None:
        for e in entities:
            kind = e.dxftype()
            if kind == "INSERT":
                walk(e.virtual_entities())
                continue
            if kind == "TEXT":
                drawn = text2path.make_paths_from_entity(e)
            elif kind in ("LINE", "LWPOLYLINE", "CIRCLE", "ARC", "SOLID"):
                drawn = [paths.make_path(e)]
            else:
                continue
            for path in drawn:
                for part in path.sub_paths():
                    points = [(v.x, v.y) for v in part.flattening(0.1)]
                    if len(points) > 1:
                        found.append(points)

    walk(msp)
    return found


def conformance(path: Path, pmi: PMI) -> dict[str, bool]:
    """Read a DXF back and check it against the PMI and the supported drawing subset."""
    import ezdxf
    from ezdxf import bbox

    doc = ezdxf.readfile(path)
    auditor = doc.audit()
    msp = doc.modelspace()
    inserts = list(msp.query("INSERT"))
    frame = paper(*_sheet_of(doc)).frame

    def attribs(ref: Any) -> dict[str, str]:
        return {a.dxf.tag: a.dxf.text for a in ref.attribs}

    title = next((attribs(i) for i in inserts if i.dxf.name == "TITLE_BLOCK"), {})
    frames = sorted(
        json.dumps(attribs(i), sort_keys=True)
        for i in inserts
        if i.dxf.name.startswith("FCF_")
    )
    expected = sorted(
        json.dumps(_frame_attribs(t), sort_keys=True) for t in pmi.tolerances
    )
    datums = {
        a["LETTER"]: a["FEATURE"]
        for i in inserts
        if i.dxf.name.startswith("DATUM_") and (a := attribs(i))
    }
    general = next((attribs(i) for i in inserts if i.dxf.name == "GENERAL"), {})
    g = pmi.general
    texts = [e for block in doc.blocks for e in block.query("TEXT ATTDEF")] + [
        a for i in inserts for a in i.attribs
    ]
    scales = {f"{_num(s)}:1" if s > 1 else f"1:{_num(1 / s)}" for s in SCALES}
    required = (
        "OWNER",
        "CREATOR",
        "TITLE",
        "TYPE",
        "STATUS",
        "NUMBER",
        "REVISION",
        "DATE",
        "SHEET",
    )
    sizes = [_size_text(s, pmi.features[s.feature]) for s in pmi.sizes]
    locations = [
        f"{_num(distance(*(pmi.features[n] for n in x.between)) or 0)} "
        f"{_deviations(x.upper, x.lower)}"
        for x in pmi.locations
    ]
    targets = sorted(
        json.dumps(attribs(i), sort_keys=True)
        for i in inserts
        if i.dxf.name.startswith("TARGET_")
    )
    expected_targets = sorted(
        json.dumps(
            {"LETTER": k, "NUMBER": str(n), "KIND": t.kind, "FEATURE": pmi.datums[k]},
            sort_keys=True,
        )
        for k, ts in pmi.targets.items()
        for n, t in enumerate(ts, start=1)
    )
    shown = {e.dxf.text for e in msp.query("TEXT")}
    inside = all(
        (box := bbox.extents([e])).has_data
        and frame[0] - 1e-6 <= box.extmin.x
        and box.extmax.x <= frame[2] + 1e-6
        and frame[1] - 1e-6 <= box.extmin.y
        and box.extmax.y <= frame[3] + 1e-6
        for e in msp
        if e.dxf.layer not in ("FRAME", "SHEET")
    )
    return {
        "drawing: DXF audit finds no errors": not auditor.has_errors,
        "drawing: millimetres at an ISO 5455 scale": doc.header["$INSUNITS"] == 4
        and title.get("SCALE") in scales,
        "drawing: ISO 7200 title block complete": all(
            title.get(tag) for tag in required
        )
        and title.get("STATUS") in STATUSES
        and (title.get("STATUS") != "Released" or bool(title.get("APPROVER"))),
        "drawing: every geometrical specification of the PMI is shown": frames
        == expected
        and general
        == {
            "SIZE": _num(g.size),
            "PROFILE": _num(g.profile),
            "DATUMS": " ".join(g.datums),
        },
        "drawing: every datum a specification references is indicated (ISO 5459)": datums
        == dict(pmi.datums)
        and all(letter in datums for t in pmi.tolerances for letter in t.datums)
        and targets == expected_targets,
        "drawing: every size and toleranced location of the PMI is shown": all(
            text in shown for text in sizes + locations
        ),
        "drawing: everything lies inside the ISO 5457 frame": inside,
        "drawing: lettering at least 2.5 mm (ISO 3098)": all(
            e.dxf.height >= 2.5 - 1e-9 for e in texts
        ),
    }
