"""
    Reference and coordinate frames for the cad_1d package.

    Two distinct concepts live here:

    1. ASSEMBLY REFERENCE FRAMES
       Tags that select how `position_x` is interpreted in
       `Assembly.add()`. They describe *placement intent*, not a
       coordinate system.

    2. COORDINATE FRAMES + CONVERSIONS
       Three frames are used end-to-end when reasoning about a rocket:

       xyn (x, y, eta) — the assembly authoring frame
           x    axial position along the rocket (m)
           y    radial offset from body surface (m, positive outward;
                negative embeds into the wall, e.g. fin slot fit)
           eta  arc-length around the body (m, period 2*pi*r at radius r)

       cylindrical (x, r, theta) — natural for axisymmetric pieces
           x      axial (same as xyn)
           r      radial distance from rocket centerline (m)
           theta  azimuthal angle (rad, period 2*pi)

       xyz (X, Y, Z) — Cartesian, used for vector mechanics: forces,
           torques, inertia tensors, parallel-axis sums.
           X      axial (= x)
           Y      Y = r * cos(theta)
           Z      Z = r * sin(theta)

    Conversion path: xyn -> cylindrical -> xyz. Two steps because the
    xyn -> cylindrical step requires a body radius (to map eta to an
    angle and to anchor y to the surface), whereas cylindrical -> xyz
    is purely a rotation. Inertia tensors are summed in xyz so that
    parallel-axis terms compose naturally across the whole assembly.
"""

import math

from .CAD_variables import REFERENCE_FRAMES, ReferenceFrame as ReferenceFrameEnum

class ReferenceFrame:
    """
    Used for assembly. Ensures components are assembled with the same
    reference frame, e.g.

        rocket.add_body_tube(
            BodyTube(),
            position=ReferenceFrame(0.5, ReferenceFrameEnum.TIP_OF_PARENT_COMPONENT),
        )
    """

    def __init__(self, value, reference_frame):
        normalized = ReferenceFrameEnum.from_value(reference_frame)
        self.value = value
        self.reference_frame = normalized
        self.print = f"{self.value} {self.reference_frame.value}"

    def __repr__(self):
        return str(self.value)


# ---------------------------------------------------------------------------
# Coordinate-frame conversions
# ---------------------------------------------------------------------------

COORDINATE_FRAMES = ("xyn", "cylindrical", "xyz")


def xyn_to_cylindrical(
    x: float,
    y: float,
    eta: float,
    r_body: float,
    r_ref: float | None = None,
) -> tuple[float, float, float]:
    """
    Map a point in the assembly (x, y, eta) frame to cylindrical (x, r, theta).

    `y` is interpreted as a radial offset from the LOCAL body surface of
    radius `r_body` (positive outward; negative embeds into the wall),
    so the radial position is r = r_body + y.

    `eta` is interpreted as an arc-length around the body. It is mapped
    to an angle by theta = eta / r_ref, where `r_ref` is a chosen
    reference radius held CONSTANT across the assembly. Anchoring eta
    to a single reference (rather than the local r_body) keeps a fin's
    angular position fixed even where the body tapers under it — for
    example a fin spanning a body tube and a boattail stays at one
    physical theta along its whole chord.

    `r_ref` defaults to `r_body` for backwards compatibility — i.e. the
    legacy "eta = arc-length at the local radius" convention. Pass a
    fixed `r_ref` (e.g. `Assembly.reference_radius`) to use the global
    convention.

    `r_body` (or `r_ref`) may be 0 (no body to attach to, e.g. a fin
    floating in space); in that degenerate case theta is set to 0 and
    `eta` is silently dropped.
    """
    if r_ref is None:
        r_ref = r_body
    r = r_body + y
    theta = eta / r_ref if r_ref > 0.0 else 0.0
    return x, r, theta


def cylindrical_to_xyz(
    x: float, r: float, theta: float
) -> tuple[float, float, float]:
    """Map cylindrical (x, r, theta) to Cartesian (X, Y, Z)."""
    return x, r * math.cos(theta), r * math.sin(theta)


def degrees_to_eta(degrees: float, r_ref: float) -> float:
    """Convert an azimuthal angle in degrees to eta (arc-length) at radius *r_ref*."""
    return math.radians(degrees) * r_ref


def xyn_to_xyz(
    x: float,
    y: float,
    eta: float,
    r_body: float,
    r_ref: float | None = None,
) -> tuple[float, float, float]:
    """Compose: xyn -> cylindrical -> xyz. See `xyn_to_cylindrical`."""
    return cylindrical_to_xyz(
        *xyn_to_cylindrical(x, y, eta, r_body, r_ref=r_ref)
    )
