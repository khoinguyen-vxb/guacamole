"""
here diffrent rocket components will be inited from classes
like a nosecone, from noseocne class, with all of its properties
the total component mass and inertia, cg can be cacluated here
"""

"""
    component schema:

    each component should have the following data

    - name
    - all geometric properties verbosely
        - radius
        - diameter
        - thickness
        - length
        - geometric angles
        - geometric lengths
    - material
    - y_upper(x), which draws the x-y axis profile of the shape
    - y_lower(x), which draws the assoiated bottom profile, so each profile has some thickness
    - plot, which is a wrapper for the solver/plotting functions plots the x-y profile
    - volume, calculates resolved or extruded volumes in x-y-z space
    - mass, uses material density and volume to compute mass
    - inertia, uses anayltical/numeric methods to compute inertia
    - cg

    note:
        there should not be any varaibles called "variable_override",
        rather the user should be able to simply do, for example:
            component.set_volume(50.0)


"""


import math
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from .CAD_variables import ComponentType
from .materials import (
    ABS,
    GAS_CONSTANT,
    Aluminum,
    Material_Fluid,
    Material_Solid,
    Nylon,
)
from .units import (
    DecimalPercent,
    Degrees,
    Density,
    Meters,
    MolarMass,
    NonDimensional,
    Percent,
    Radians,
    Temperature,
    Time,
    Volume,
)


# ---------------------------------------------------------------------------
# Numerical mass-property helper for axisymmetric shells.
#
# Given y_upper(x) and y_lower(x) (outer and inner radii along the axis of
# symmetry), this returns (volume, cg, I_lateral, I_axial) computed by
# trapezoidal integration over n stations in [x_min, x_max].
#
#   - cg is measured from x_min, along the axis of symmetry.
#   - I_axial is about the symmetry axis.
#   - I_lateral is about a lateral axis through the CG.
#
# Each axial station is treated as an annular disc of mass
#     dm = density · π · (Ro² − Ri²) · dx
# whose moment about its own diameter is dm·(Ro²+Ri²)/4 (exact for an annular
# disc).  Parallel axis adds dm·(x − cg)² to get I_lateral about the body CG.
# ---------------------------------------------------------------------------
def _shell_axisymmetric_props(y_upper, y_lower, x_min, x_max, density, n: int = 400):
    density = float(density)  # SI_UNIT __mul__ can't broadcast over numpy arrays
    xs = np.linspace(x_min, x_max, n)
    ru = np.array([y_upper(x) for x in xs])
    rl = np.array([y_lower(x) for x in xs])

    dA = np.pi * (ru**2 - rl**2)  # cross-sectional ring area
    volume = float(np.trapezoid(dA, xs))
    if volume <= 0.0:
        return 0.0, 0.0, 0.0, 0.0

    cg = float(np.trapezoid(dA * xs, xs) / volume)

    I_axial = float(density * np.trapezoid(np.pi * (ru**4 - rl**4) / 2.0, xs))

    dm = density * dA  # density per unit x
    I_d = dm * (ru**2 + rl**2) / 4.0  # disc moment about its diameter
    I_par = dm * (xs - cg) ** 2  # parallel axis to body CG
    I_lateral = float(np.trapezoid(I_d + I_par, xs))

    return volume, cg, I_lateral, I_axial


# ---------------------------------------------------------------------------
# Numerical mass-property helper for extruded planforms (e.g. fins).
#
# A planform sits in the (chord, span) = (x, y) plane and is bounded at
# each span station y ∈ [y_min, y_max] by a leading edge x_le(y) and a
# trailing edge x_te(y).  The body extends symmetrically about z=0 in
# the thickness direction with a chord-position-dependent cross section
# t(s, c), where s is the chord position from the local LE and
# c = x_te(y) − x_le(y) is the local chord.
#
#   mass element :  dm = ρ · t(s, c) · ds · dy
#   z extent     :  z ∈ [−t/2, +t/2]   (used for the I_z term)
#
# Returns (volume, cg_x, cg_y, I_lateral, I_axial), where
#   - cg_x is in the global chord coordinate (NOT relative to local LE)
#   - cg_y is measured from y_min along the span direction
#   - I_lateral is about a span-aligned (y-direction) axis through the CG
#   - I_axial   is about a chord-aligned (x-direction) axis through the CG
# ---------------------------------------------------------------------------
def _extruded_planform_props(
    x_le_fn,
    x_te_fn,
    thickness_fn,
    y_min,
    y_max,
    density,
    n_y: int = 200,
    n_s: int = 100,
):
    density = float(density)
    ys = np.linspace(y_min, y_max, n_y)
    x_le = np.array([x_le_fn(y) for y in ys])
    x_te = np.array([x_te_fn(y) for y in ys])
    local_chord = x_te - x_le

    # Per-span-station moments of the cross section over s ∈ [0, c(y)]
    A_cs = np.zeros_like(ys)  # ∫ t(s,c) ds                — area of cs
    M1_s = np.zeros_like(ys)  # ∫ s · t(s,c) ds            — first moment
    M2_s = np.zeros_like(ys)  # ∫ s² · t(s,c) ds           — second moment
    M_t3 = np.zeros_like(ys)  # ∫ t(s,c)³ ds               — for the z² term

    s_norm = np.linspace(0.0, 1.0, n_s)
    for i in range(len(ys)):
        c = float(local_chord[i])
        if c <= 0.0:
            continue
        ss = s_norm * c
        ts = np.array([thickness_fn(float(s), c) for s in ss])
        A_cs[i] = float(np.trapezoid(ts, ss))
        M1_s[i] = float(np.trapezoid(ts * ss, ss))
        M2_s[i] = float(np.trapezoid(ts * ss**2, ss))
        M_t3[i] = float(np.trapezoid(ts**3, ss))

    volume = float(np.trapezoid(A_cs, ys))
    if volume <= 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    cg_x = float(np.trapezoid(x_le * A_cs + M1_s, ys) / volume)
    cg_y = float(np.trapezoid(ys * A_cs, ys) / volume)

    # I_lateral = ρ · ∫∫∫ ((x − cg_x)² + z²) dV
    # in-plane part: ∫_y [(x_le−cg_x)² A_cs + 2(x_le−cg_x) M1_s + M2_s] dy
    in_plane_lat = (x_le - cg_x) ** 2 * A_cs + 2.0 * (x_le - cg_x) * M1_s + M2_s
    I_lat_in_plane = density * float(np.trapezoid(in_plane_lat, ys))
    # z² part: ∫_z² dV = ∫_y ∫_0^c (t³/12) ds dy
    I_z = density * float(np.trapezoid(M_t3 / 12.0, ys))
    I_lateral = I_lat_in_plane + I_z

    # I_axial = ρ · ∫∫∫ ((y − cg_y)² + z²) dV
    # in-plane part: ∫_y (y − cg_y)² · A_cs(y) dy
    I_ax_in_plane = density * float(np.trapezoid((ys - cg_y) ** 2 * A_cs, ys))
    I_axial = I_ax_in_plane + I_z

    return volume, cg_x, cg_y, I_lateral, I_axial


# ---------------------------------------------------------------------------
# Wing cross sections
# ---------------------------------------------------------------------------
#
# A wing's cross section is its thickness profile across the local chord.
# It's separate from the planform (which is the shape in the chord-span
# plane). The cross section is defined parametrically AT THE ROOT CHORD,
# and the wing scales it down at every span station so the proportions
# stay identical and the cross section always spans the local chord
# from leading edge to trailing edge.
#
# Concretely:
#   - At the root (local_chord = root_chord) the cross section is exactly
#     what the user specified.
#   - At the tip (local_chord = tip_chord) the cross section is the same
#     SHAPE but scaled by (tip_chord / root_chord) — narrower in the
#     chord direction; thickness stays at the user-supplied value
#     unless a kind chooses otherwise.
#
# Subclasses implement ``evaluate(s, local_chord, root_chord) -> float``,
# returning the local thickness at chord-from-LE position ``s``.
#
# The thin sub-hierarchy here (Slab, SupersonicWedge) is intentional —
# upcoming aerofoil cross sections (e.g. NACA 4-digit symmetric) plug in
# as another subclass of WingCrossSection without touching the wing
# classes themselves.
# ---------------------------------------------------------------------------


@dataclass
class WingCrossSection:
    """
    Abstract wing cross section.

    Subclasses override :meth:`evaluate` to return the local thickness
    at chord-from-LE position ``s`` (in metres) for a given
    ``local_chord`` and ``root_chord``. The scaling convention is up
    to the subclass; the default behaviour for chord-aligned features
    (wedge lengths, leading-edge radii, ...) is to scale them linearly
    with ``local_chord / root_chord`` so the cross section is
    proportional at every span station.
    """

    name: str = "abstract cross section"

    def evaluate(self, s: float, local_chord: float, root_chord: float) -> float:
        raise NotImplementedError(
            f"{type(self).__name__}.evaluate() is not implemented"
        )

    # convenience — call the cross section like a function
    def __call__(self, s: float, local_chord: float, root_chord: float) -> float:
        return self.evaluate(s, local_chord, root_chord)

    def plot(
        self,
        local_chord: float,
        root_chord: float,
        ax=None,
        options: dict = None,
    ):
        """
        Plot the cross section profile at a given local chord, against
        the matching root chord (used by subclasses that scale features
        with local_chord / root_chord).

        options keys (all optional):
            n         : int   — chord sample count (default 200)
            show      : bool  — call plt.show() at the end (standalone only;
                                default True)
            title     : str   — plot title (standalone only)
            color     : str | tuple — line/fill colour (default 'darkviolet')
            y_offset  : float — vertical offset added to the (±t/2) profile,
                                useful for stacking several spans
            label     : str   — legend label
            alpha     : float — fill alpha (default 0.35)

        Returns: ``(fig, ax)`` if standalone, else ``ax``.
        """
        import matplotlib.pyplot as plt

        opts = {
            "n": 200,
            "show": True,
            "title": f"{self.name} (chord = {local_chord:.4f} m)",
            "color": "darkviolet",
            "alpha": 0.35,
            "y_offset": 0.0,
            "label": None,
        }
        if options:
            opts.update(options)

        ss = np.linspace(0.0, local_chord, int(opts["n"]))
        ts = np.array([self.evaluate(float(s), local_chord, root_chord) for s in ss])
        y_offset = float(opts["y_offset"])
        upper = ts / 2.0 + y_offset
        lower = -ts / 2.0 + y_offset

        standalone = ax is None
        if standalone:
            fig, ax = plt.subplots()

        label = (
            opts["label"] if opts["label"] is not None else f"c = {local_chord:.4f} m"
        )
        ax.fill_between(ss, lower, upper, color=opts["color"], alpha=opts["alpha"])
        ax.plot(ss, upper, color=opts["color"], label=label)
        ax.plot(ss, lower, color=opts["color"])

        if standalone:
            ax.set_aspect("equal")
            ax.set_title(opts["title"])
            ax.set_xlabel("chord position from LE (m)")
            ax.set_ylabel("thickness (m)")
            ax.grid(True)
            ax.legend(loc="best")
            if opts["show"]:
                plt.show()
            return fig, ax
        return ax


@dataclass
class SlabCrossSection(WingCrossSection):
    """
    Constant-thickness slab — a rectangular cross section.

    The thickness is the same at every chord position and at every span
    station. Useful for plain plate fins or as a baseline before
    moving to a wedge / aerofoil.

    Attributes:
        thickness: Meters    (max thickness through the chord)
    """

    thickness: float = 0.0
    name: str = "Slab"

    def evaluate(self, s: float, local_chord: float, root_chord: float) -> float:
        if s < 0.0 or s > local_chord or local_chord <= 0.0:
            return 0.0
        return float(self.thickness)


@dataclass
class SupersonicWedgeCrossSection(WingCrossSection):
    """
    Wedge–flat–wedge ('<==>') supersonic cross section.

    LE and TE wedges of given chord-length (specified at the wing's
    ROOT chord) ramp linearly from 0 thickness to ``thickness`` and
    back to 0; the flat in between is the constant-max-thickness
    region.

    The wedge lengths SCALE linearly with ``local_chord / root_chord``
    so the cross section's proportions are preserved at every span
    station — at the root the wedges are exactly what the user
    supplied; at the tip they are scaled by ``tip_chord / root_chord``
    (and the flat between them shrinks by the same factor).

    Setting ``le_wedge_length`` and ``te_wedge_length`` to 0 reduces
    this to a plain :class:`SlabCrossSection`.

    Edge cases:
        - If the local chord shrinks below the (already-scaled) wedge
          sum (e.g. a near-pointed tip), the two wedges are scaled
          again so they meet, yielding a full diamond cross section
          with no flat region.

    Attributes:
        thickness: Meters             (max thickness through the flat)
        le_wedge_length: Meters       (LE wedge length at root_chord)
        te_wedge_length: Meters       (TE wedge length at root_chord)
    """

    thickness: float = 0.0
    le_wedge_length: float = 0.0
    te_wedge_length: float = 0.0
    name: str = "Supersonic Wedge"

    def evaluate(self, s: float, local_chord: float, root_chord: float) -> float:
        if s < 0.0 or s > local_chord or local_chord <= 0.0:
            return 0.0
        scale = local_chord / root_chord if root_chord > 0.0 else 1.0
        le = float(self.le_wedge_length) * scale
        te = float(self.te_wedge_length) * scale
        if le + te > local_chord and (le + te) > 0:
            scale2 = local_chord / (le + te)
            le *= scale2
            te *= scale2
        if le > 0.0 and s < le:
            return float(self.thickness) * s / le
        if te > 0.0 and s > local_chord - te:
            return float(self.thickness) * (local_chord - s) / te
        return float(self.thickness)


def make_wing_cross_section(
    kind: str = "slab",
    *,
    thickness: float = 0.0,
    le_wedge_length: float = 0.0,
    te_wedge_length: float = 0.0,
    name: str | None = None,
) -> WingCrossSection:
    """
    Factory: pick a cross-section subclass by string ``kind``. Used by
    the TOML/builder layer to dispatch on a single ``cross_section_type``
    key without leaking the class hierarchy into the TOML schema.

    Currently:
        'slab'              -> :class:`SlabCrossSection`
        'supersonic_wedge'  -> :class:`SupersonicWedgeCrossSection`

    Future:
        'aerofoil_naca4_symmetric' will plug in here.

    If ``kind`` is 'supersonic_wedge' but both wedge lengths are zero,
    the result is functionally equivalent to a slab — the factory
    returns the wedge object anyway so the underlying class can be
    introspected.
    """
    k = kind.lower().strip()
    if k == "slab":
        cs = SlabCrossSection(thickness=thickness)
    elif k in ("supersonic_wedge", "wedge", "supersonic"):
        cs = SupersonicWedgeCrossSection(
            thickness=thickness,
            le_wedge_length=le_wedge_length,
            te_wedge_length=te_wedge_length,
        )
    else:
        raise ValueError(
            f"Unknown WingCrossSection kind '{kind}'. "
            "Valid: 'slab', 'supersonic_wedge'."
        )
    if name is not None:
        cs.name = name
    return cs


@dataclass
class DivergingConicalNozzle:
    """
    A diverging-only conical nozzle — the supersonic section attached
    downstream of a separate combustion chamber / throat assembly.

    Built as a solid cylindrical billet (typically graphite) with a single
    frustum void machined out on a lathe. Throat sits at x=0 (narrow end of
    the void), exit at x=cone_length (wide end). The outer cylinder is the
    structural material; the void is the hot-gas flow path.

    Attributes:
        - user defined -
        throat_diameter: Meters
        outer_diameter: Meters         (graphite billet outer diameter)
        cone_length: Meters            (axial length of the diverging section)
        diverging_angle_deg: Degrees   (half-angle of the diverging frustum)
        material: Material_Solid
        name: str

        - automatically calculated -
        throat_radius: Meters
        outer_radius: Meters
        exit_diameter: Meters
        exit_radius: Meters
        diverging_angle_rad: Radians
        slant_length: Meters
        eps: NonDimensional            (area expansion ratio (exit/throat)²)
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    throat_diameter: Meters
    outer_diameter: Meters
    cone_length: Meters
    diverging_angle_deg: Degrees
    material: Material_Solid
    name: str = "Diverging Conical Nozzle"
    throat_radius: Meters = field(init=False)
    outer_radius: Meters = field(init=False)
    exit_diameter: Meters = field(init=False)
    exit_radius: Meters = field(init=False)
    diverging_angle_rad: Radians = field(init=False)
    slant_length: Meters = field(init=False)
    eps: NonDimensional = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.throat_radius = self.throat_diameter / 2.0
        self.outer_radius = self.outer_diameter / 2.0
        self.diverging_angle_rad = math.radians(self.diverging_angle_deg)
        self.exit_radius = self.throat_radius + self.cone_length * math.tan(
            self.diverging_angle_rad
        )
        self.exit_diameter = self.exit_radius * 2.0
        self.slant_length = math.sqrt(
            self.cone_length**2 + (self.exit_radius - self.throat_radius) ** 2
        )
        self.eps = (self.exit_radius / self.throat_radius) ** 2
        if self.outer_radius < self.exit_radius:
            raise ValueError(
                f"{self.name}: outer_radius ({self.outer_radius:.4f} m) must "
                f"be at least exit_radius ({self.exit_radius:.4f} m) so the "
                "billet contains the diverging void."
            )

    # --- override setters (schema: no `*_override` field; use set_xxx) ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    # --- analytical material volume = cylinder − frustum void ---
    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        Rt, Re, Ro, h = (
            self.throat_radius,
            self.exit_radius,
            self.outer_radius,
            self.cone_length,
        )
        cylinder = math.pi * Ro**2 * h
        void_frustum = math.pi * h / 3.0 * (Rt**2 + Rt * Re + Re**2)
        return cylinder - void_frustum

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        """CG of the (cylinder − frustum void) body, measured from the throat face."""
        if self._cg is not None:
            return self._cg
        _, cg, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.cone_length, self.material.density
        )
        return cg

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        _, _, I_lat, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.cone_length, self.material.density
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        _, _, _, I_ax = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.cone_length, self.material.density
        )
        return I_ax

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius of the graphite billet — constant cylinder."""
        return self.outer_radius

    def y_lower(self, x: Meters) -> Meters:
        """Inner (void) radius — diverging frustum, throat at x=0 → exit at x=cone_length."""
        return self.throat_radius + x * math.tan(self.diverging_angle_rad)

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class ConvergingDivergingConicalNozzle:
    """
    A full converging–diverging (de Laval) conical nozzle, machined from a
    single solid cylindrical billet (typically graphite) by spinning two
    frustum voids on a lathe — one converging from the chamber to the
    throat, one diverging from the throat to the exit.

    Layout along the axis (x measured from the chamber-side face):
        x = 0                   chamber face   (radius = chamber_radius)
        x = converging_length   throat         (radius = throat_radius)
        x = total_length        exit face      (radius = exit_radius)

    The outer cylinder is the structural material; both voids are the
    hot-gas flow path.

    Attributes:
        - user defined -
        chamber_diameter: Meters       (entry diameter at the converging face)
        throat_diameter: Meters
        outer_diameter: Meters         (graphite billet outer diameter)
        converging_length: Meters
        diverging_length: Meters
        diverging_angle_deg: Degrees   (half-angle of the diverging frustum)
        material: Material_Solid
        name: str

        - automatically calculated -
        chamber_radius, throat_radius, outer_radius: Meters
        exit_diameter, exit_radius: Meters
        total_length: Meters
        converging_angle_rad, converging_angle_deg: Radians/Degrees
        diverging_angle_rad: Radians
        converging_slant_length, diverging_slant_length: Meters
        eps: NonDimensional            (area expansion ratio (exit/throat)²)
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    chamber_diameter: Meters
    throat_diameter: Meters
    outer_diameter: Meters
    converging_length: Meters
    diverging_length: Meters
    diverging_angle_deg: Degrees
    material: Material_Solid
    name: str = "Converging-Diverging Conical Nozzle"
    chamber_radius: Meters = field(init=False)
    throat_radius: Meters = field(init=False)
    outer_radius: Meters = field(init=False)
    exit_diameter: Meters = field(init=False)
    exit_radius: Meters = field(init=False)
    total_length: Meters = field(init=False)
    converging_angle_rad: Radians = field(init=False)
    converging_angle_deg: Degrees = field(init=False)
    diverging_angle_rad: Radians = field(init=False)
    converging_slant_length: Meters = field(init=False)
    diverging_slant_length: Meters = field(init=False)
    eps: NonDimensional = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.chamber_radius = self.chamber_diameter / 2.0
        self.throat_radius = self.throat_diameter / 2.0
        self.outer_radius = self.outer_diameter / 2.0
        self.total_length = self.converging_length + self.diverging_length

        self.diverging_angle_rad = math.radians(self.diverging_angle_deg)
        self.exit_radius = self.throat_radius + self.diverging_length * math.tan(
            self.diverging_angle_rad
        )
        self.exit_diameter = self.exit_radius * 2.0

        # converging side: chamber → throat over converging_length
        self.converging_angle_rad = math.atan(
            (self.chamber_radius - self.throat_radius) / self.converging_length
        )
        self.converging_angle_deg = math.degrees(self.converging_angle_rad)

        self.converging_slant_length = math.sqrt(
            self.converging_length**2 + (self.chamber_radius - self.throat_radius) ** 2
        )
        self.diverging_slant_length = math.sqrt(
            self.diverging_length**2 + (self.exit_radius - self.throat_radius) ** 2
        )
        self.eps = (self.exit_radius / self.throat_radius) ** 2

        max_void_radius = max(self.chamber_radius, self.exit_radius)
        if self.outer_radius < max_void_radius:
            raise ValueError(
                f"{self.name}: outer_radius ({self.outer_radius:.4f} m) must "
                f"be at least max(chamber_radius, exit_radius) "
                f"({max_void_radius:.4f} m) so the billet contains both voids."
            )

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    # --- analytical material volume = cylinder − converging void − diverging void ---
    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        Rc, Rt, Re, Ro = (
            self.chamber_radius,
            self.throat_radius,
            self.exit_radius,
            self.outer_radius,
        )
        Lc, Ld = self.converging_length, self.diverging_length
        cylinder = math.pi * Ro**2 * self.total_length
        void_converging = math.pi * Lc / 3.0 * (Rc**2 + Rc * Rt + Rt**2)
        void_diverging = math.pi * Ld / 3.0 * (Rt**2 + Rt * Re + Re**2)
        return cylinder - void_converging - void_diverging

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        """CG of the (cylinder − two voids) body, measured from the chamber face."""
        if self._cg is not None:
            return self._cg
        _, cg, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.total_length, self.material.density
        )
        return cg

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        _, _, I_lat, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.total_length, self.material.density
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        _, _, _, I_ax = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.total_length, self.material.density
        )
        return I_ax

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius of the graphite billet — constant cylinder."""
        return self.outer_radius

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner (void) radius along the axis: linear taper chamber → throat
        over the converging section, then linear flare throat → exit over
        the diverging section.
        """
        if x <= self.converging_length:
            t = x / self.converging_length
            return self.chamber_radius + (self.throat_radius - self.chamber_radius) * t
        t = (x - self.converging_length) / self.diverging_length
        return self.throat_radius + (self.exit_radius - self.throat_radius) * t

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


# ---------------------------------------------------------------------------
# Port geometry for hybrid fuel grains
# ---------------------------------------------------------------------------
#
# A port geometry describes the cross-sectional shape of the combustion
# port (central void) inside a hybrid fuel grain.  The simplest case is
# a circular port (constant inner radius); more complex shapes like
# cruciform, star, finocyl, and wagon-wheel vary the inner radius with
# the azimuthal angle eta.
#
# Port geometry classes are intentionally lightweight — they store the
# shape parameters and provide the port cross-section profile.  The
# heavy maths (area, perimeter, regression) lives in the hybrid solver
# module, not here.
#
# Subclasses implement ``_build_polygon()`` which returns a Shapely
# ``Polygon`` representing the port boundary.  The polygon's exterior
# coordinates are used for plotting.
# ---------------------------------------------------------------------------

from shapely.affinity import rotate as shapely_rotate
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union


@dataclass
class PortGeometry:
    """
    Abstract base for fuel grain port geometries.

    Subclasses override :meth:`_build_polygon` to return a Shapely
    ``Polygon`` of the port cross-section.
    """

    name: str = "abstract port geometry"

    def _build_polygon(self) -> Polygon:
        """Return a Shapely Polygon of the port boundary."""
        raise NotImplementedError(
            f"{type(self).__name__}._build_polygon() is not implemented"
        )

    def plot(
        self,
        grain_outer_radius: Meters | None = None,
        ax=None,
        options: dict = None,
    ):
        """
        Plot the port cross-section in the (Y, Z) plane.

        If *grain_outer_radius* is given the grain boundary is drawn as
        a dashed circle for reference.

        options keys (all optional):
            show        : bool  — call plt.show() at the end (standalone only)
            title       : str   — plot title
            color       : str   — port fill colour (default 'steelblue')
            grain_color : str   — grain boundary colour (default 'gray')
            alpha       : float — fill alpha (default 0.35)

        Returns: ``(fig, ax)`` if standalone, else ``ax``.
        """
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle as MplCircle

        opts = {
            "show": True,
            "title": f"{self.name} Cross-Section",
            "material_color": "lightgray",
            "port_color": "white",
            "edge_color": "black",
        }
        if options:
            opts.update(options)

        poly = self._build_polygon()

        standalone = ax is None
        if standalone:
            fig, ax = plt.subplots(figsize=(6, 6))

        # 1. fill the grain outer circle (material)
        if grain_outer_radius is not None and grain_outer_radius > 0:
            ax.add_patch(
                MplCircle(
                    (0, 0),
                    grain_outer_radius,
                    fill=True,
                    facecolor=opts["material_color"],
                    edgecolor=opts["edge_color"],
                    linewidth=1.0,
                )
            )

        # 2. fill the port shape white (void) — cut out from the material
        def _fill_port(p):
            x, y = p.exterior.xy
            ax.fill(x, y, color=opts["port_color"], edgecolor=opts["edge_color"], linewidth=0.8)

        if hasattr(poly, "exterior"):
            _fill_port(poly)
        else:
            for part in poly.geoms:
                _fill_port(part)

        ax.set_aspect("equal")
        ax.set_title(opts["title"])
        ax.set_xlabel("Y (m)")
        ax.set_ylabel("Z (m)")
        ax.grid(True, alpha=0.3)

        if standalone:
            if opts["show"]:
                plt.show()
            return fig, ax
        return ax


@dataclass
class CircularPort(PortGeometry):
    """
    Circular port — constant inner radius at all azimuthal angles.

    Attributes:
        diameter: Meters   (port diameter, equal to grain_inner_diameter)
    """

    diameter: Meters = 0.0
    name: str = "Circular Port"

    @property
    def radius(self) -> Meters:
        return self.diameter / 2.0

    def _build_polygon(self) -> Polygon:
        return Point(0, 0).buffer(self.radius, resolution=100)


@dataclass
class CruciformPort(PortGeometry):
    """
    Cruciform port — circular hub with *n_arms* symmetric, tapered arms.

    Each arm extends radially from the hub edge by ``slot_length`` and
    tapers from the hub radius to a tip of half-width
    ``slot_width_tip / 2``.  A Bezier ``smoothness`` parameter controls
    how rounded the arm shoulders are (0 = sharp, 1 = very round).

    Attributes:
        hub_diameter: Meters       (central hub diameter)
        slot_length: Meters        (radial extension of each arm from hub edge)
        slot_width_tip: Meters     (full width at the arm tip)
        smoothness: NonDimensional (Bezier shoulder curvature, 0–1)
        n_arms: int                (number of symmetric arms)
    """

    hub_diameter: Meters = 0.0
    slot_length: Meters = 0.0
    slot_width_tip: Meters = 0.0
    smoothness: NonDimensional = 0.0
    n_arms: int = 4
    name: str = "Cruciform Port"

    @property
    def hub_radius(self) -> Meters:
        return self.hub_diameter / 2.0

    @property
    def arm_outer_radius(self) -> Meters:
        """Radial distance from centre to the tip of each arm."""
        return self.hub_radius + self.slot_length

    def _bezier(self, p0, p1, p2, p3, t):
        return (
            (1 - t) ** 3 * p0
            + 3 * (1 - t) ** 2 * t * p1
            + 3 * (1 - t) * t**2 * p2
            + t**3 * p3
        )

    def _generate_arm(self, angle_deg, steps=20) -> Polygon:
        theta = np.deg2rad(angle_deg)
        direction = np.array([np.cos(theta), np.sin(theta)])
        perp = np.array([-np.sin(theta), np.cos(theta)])

        center = np.array([0.0, 0.0])
        tip_center = (self.hub_radius + self.slot_length) * direction
        arm_length = np.linalg.norm(tip_center - center)

        tip_left = tip_center + (self.slot_width_tip / 2) * perp
        tip_right = tip_center - (self.slot_width_tip / 2) * perp
        offset = self.smoothness * arm_length

        ctrl1 = center + offset * perp
        ctrl2 = tip_left + offset * perp
        left = [
            self._bezier(center, ctrl1, ctrl2, tip_left, t)
            for t in np.linspace(0, 1, steps)
        ]

        ctrl3 = tip_right - offset * perp
        ctrl4 = center - offset * perp
        right = [
            self._bezier(tip_right, ctrl3, ctrl4, center, t)
            for t in np.linspace(0, 1, steps)
        ]

        coords = np.vstack([left, right])
        return Polygon(coords).buffer(0)

    def _build_polygon(self) -> Polygon:
        hub = Point(0, 0).buffer(self.hub_radius, resolution=100)
        arms = [
            self._generate_arm(angle_deg=i * 360 / self.n_arms)
            for i in range(self.n_arms)
        ]
        return unary_union([hub] + arms)


@dataclass
class StarPort(PortGeometry):
    """
    Star port — a star-shaped void with *n_points* tips.

    The inner radius varies sinusoidally between ``inner_radius`` (at
    the valleys) and ``outer_radius`` (at the tips).

    Attributes:
        n_points: int             (number of star tips)
        inner_radius: Meters      (radius at valleys between tips)
        outer_radius: Meters      (radius at tips)
    """

    n_points: int = 5
    inner_radius: Meters = 0.0
    outer_radius: Meters = 0.0
    name: str = "Star Port"

    def _build_polygon(self) -> Polygon:
        angle_step = math.pi / self.n_points
        xs: list[float] = []
        ys: list[float] = []
        for i in range(2 * self.n_points):
            r = self.outer_radius if i % 2 == 0 else self.inner_radius
            angle = i * angle_step
            xs.append(r * math.cos(angle))
            ys.append(r * math.sin(angle))
        xs.append(xs[0])
        ys.append(ys[0])
        return Polygon(list(zip(xs, ys)))


@dataclass
class FinocylPort(PortGeometry):
    """
    Finocyl (fin-on-cylinder) port — circular hub with straight radial
    fins (constant-width rectangular fins, not tapered like cruciform).

    Attributes:
        hub_diameter: Meters   (central hub diameter)
        fin_height: Meters     (radial height of each fin from hub edge)
        fin_width: Meters      (tangential width of each fin)
        n_fins: int            (number of radial fins)
    """

    hub_diameter: Meters = 0.0
    fin_height: Meters = 0.0
    fin_width: Meters = 0.0
    n_fins: int = 4
    name: str = "Finocyl Port"

    @property
    def hub_radius(self) -> Meters:
        return self.hub_diameter / 2.0

    def _build_polygon(self) -> Polygon:
        hub = Point(0, 0).buffer(self.hub_radius, resolution=100)

        half_w = self.fin_width / 2
        strut = Polygon(
            [
                (self.hub_radius - 1e-3, -half_w),
                (self.hub_radius + self.fin_height, -half_w),
                (self.hub_radius + self.fin_height, half_w),
                (self.hub_radius - 1e-3, half_w),
            ]
        )

        parts = [hub]
        for i in range(self.n_fins):
            angle = i * (360 / self.n_fins)
            parts.append(shapely_rotate(strut, angle, origin=(0, 0)))

        return unary_union(parts)


@dataclass
class HybridFuelGrain:
    """
    Solid fuel grain for a hybrid rocket engine — annular cylinder
    (outer = grain wall, inner = combustion port).

    `material` is the printed plastic (defaults to ABS, density 1036.48 kg/m³).
    The effective mass density is `material.density × infill_factor`, since the
    grain is FDM-printed at less than 100 % infill.

    The inner void shape is defined by *port_geometry* (e.g.
    :class:`CruciformPort`, :class:`CircularPort`).  The equivalent
    circular inner radius is derived from the port area for the
    axisymmetric shell helper.

    Attributes:
        - user defined -
        grain_outer_diameter: Meters   (GRAIN_DIAMETER)
        grain_length: Meters           (GRAIN_LENGTH)
        infill_density: Percent        (ABS_INFILL_DENSITY, 0–1 or 0–100)
        material: Material_Solid
        port_geometry: PortGeometry    (inner void shape)

        - automatically calculated -
        grain_outer_radius: Meters
        grain_inner_radius: Meters     (equivalent circular radius from port area)
        infill_factor: DecimalPercent
        effective_density: Density
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    grain_outer_diameter: Meters
    grain_length: Meters
    infill_density: Percent
    port_geometry: PortGeometry
    material: Material_Solid = field(default_factory=ABS)
    name: str = "Hybrid Fuel Grain"
    grain_outer_radius: Meters = field(init=False)
    grain_inner_radius: Meters = field(init=False)
    infill_factor: DecimalPercent = field(init=False)
    effective_density: Density = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.grain_outer_radius = max(self.grain_outer_diameter / 2.0, 1e-4)
        self._refresh_inner_radius()

        self.infill_factor = min(
            max(
                (
                    self.infill_density / 100.0
                    if self.infill_density > 1.5
                    else self.infill_density
                ),
                0.05,
            ),
            1.0,
        )
        self.effective_density = float(self.material.density) * float(
            self.infill_factor
        )

    def _refresh_inner_radius(self) -> None:
        """Keep the compatibility diameter and port geometry in sync."""
        port_poly = self.port_geometry._build_polygon()
        port_area = port_poly.area
        self.grain_inner_radius = min(
            max(math.sqrt(port_area / math.pi), 1e-6),
            self.grain_outer_radius * 0.95,
        )

    @property
    def grain_inner_diameter(self) -> Meters:
        return 2.0 * self.grain_inner_radius

    @grain_inner_diameter.setter
    def grain_inner_diameter(self, value: Meters) -> None:
        if isinstance(self.port_geometry, CircularPort):
            self.port_geometry.diameter = value
        elif hasattr(self.port_geometry, "hub_diameter"):
            self.port_geometry.hub_diameter = value
        else:
            raise AttributeError(
                f"{type(self.port_geometry).__name__} has no diameter-compatible input."
            )
        self._refresh_inner_radius()

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        Ro, Ri, L = self.grain_outer_radius, self.grain_inner_radius, self.grain_length
        return math.pi * (Ro**2 - Ri**2) * L

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.effective_density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.grain_length / 2.0

    @property
    def I_lateral(self):
        """Annular cylinder about its CG, perpendicular to the axis."""
        if self._I_lateral is not None:
            return self._I_lateral
        Ro, Ri, L = self.grain_outer_radius, self.grain_inner_radius, self.grain_length
        return (self.mass / 12.0) * (3.0 * (Ro**2 + Ri**2) + L**2)

    @property
    def I_axial(self):
        """Annular cylinder about its symmetry axis."""
        if self._I_axial is not None:
            return self._I_axial
        Ro, Ri = self.grain_outer_radius, self.grain_inner_radius
        return (self.mass / 2.0) * (Ro**2 + Ri**2)

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius — constant along the grain length."""
        return self.grain_outer_radius

    def y_lower(self, x: Meters) -> Meters:
        """
        Equivalent circular inner radius from the port geometry area.

        Use :meth:`port_profile_xy` to get the actual port shape at a
        given azimuthal angle.
        """
        return self.grain_inner_radius

    def port_profile_xy(
        self, eta: Radians, n_points: int = 200
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Return the port cross-section boundary at azimuthal angle *eta*.

        Delegates to ``self.port_geometry._build_polygon()`` and returns
        the exterior coordinates.
        """
        poly = self.port_geometry._build_polygon()
        if hasattr(poly, "exterior"):
            return np.array(poly.exterior.xy[0]), np.array(poly.exterior.xy[1])
        # MultiPolygon — return the largest part
        largest = max(poly.geoms, key=lambda p: p.area)
        return np.array(largest.exterior.xy[0]), np.array(largest.exterior.xy[1])

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class CylindricalTank:
    """
    Cylindrical oxidizer tank closed by two flat circular end caps of the same
    wall thickness as the cylinder.

    Example usage (rocketpy_api.py):
        tank_geometry = rocketpy.CylindricalTank(radius=tank.inner_radius, height=tank.length, spherical_caps=False)
        oxidizer_tank = MassBasedTank(name="N2O Tank", geometry=tank_geometry, ...)

    Attributes:
        - user defined -
        inner_diameter: Meters
        length: Meters
        wall_thickness: Meters
        material: Material_Solid

        - automatically calculated -
        inner_radius: Meters
        outer_radius: Meters
        outer_diameter: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    inner_diameter: Meters
    length: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Cylindrical Tank"
    inner_radius: Meters = field(init=False)
    outer_radius: Meters = field(init=False)
    outer_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.inner_radius = self.inner_diameter / 2.0
        self.outer_radius = self.inner_radius + self.wall_thickness
        self.outer_diameter = self.outer_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def _shell_volume(self):
        return math.pi * (self.outer_radius**2 - self.inner_radius**2) * self.length

    @property
    def _cap_volume(self):
        """Volume of one flat circular end cap (solid disc, radius=outer_radius)."""
        return math.pi * self.outer_radius**2 * self.wall_thickness

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return self._shell_volume + 2.0 * self._cap_volume

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):  # distance from front face → length/2 by symmetry
        if self._cg is not None:
            return self._cg
        return self.length / 2.0

    @property
    def I_lateral(self):  # about CG, perpendicular to axis
        if self._I_lateral is not None:
            return self._I_lateral
        Ro, Ri, L, t = (
            self.outer_radius,
            self.inner_radius,
            self.length,
            self.wall_thickness,
        )
        rho = self.material.density
        m_shell = rho * self._shell_volume
        m_cap = rho * self._cap_volume
        # Hollow cylinder shell about its own CG (coincides with tank CG)
        I_shell = (m_shell / 12.0) * (3.0 * (Ro**2 + Ri**2) + L**2)
        # Each flat cap: solid disc (radius Ro, thickness t)
        # Cap centre is at distance L/2 + t/2 from the tank CG
        d = L / 2.0 + t / 2.0
        I_cap_own = (m_cap / 12.0) * (3.0 * Ro**2 + t**2)
        I_each_cap = I_cap_own + m_cap * d**2
        return I_shell + 2.0 * I_each_cap

    @property
    def I_axial(self):  # about roll axis
        if self._I_axial is not None:
            return self._I_axial
        Ro, Ri = self.outer_radius, self.inner_radius
        rho = self.material.density
        m_shell = rho * self._shell_volume
        m_cap = rho * self._cap_volume
        # Hollow cylinder shell
        I_shell = (m_shell / 2.0) * (Ro**2 + Ri**2)
        # Each flat cap: solid disc  I = (m/2) R²
        I_cap = (m_cap / 2.0) * Ro**2
        return I_shell + 2.0 * I_cap

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius at axial position x from the front face. x ∈ [0, length]."""
        return self.outer_radius

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner radius at axial position x. Returns 0 inside the flat end caps
        (x ∈ [0, t] or [length-t, length]) and inner_radius along the cylindrical body.
        """
        t, L = self.wall_thickness, self.length
        if x < t or x > L - t:
            return 0.0
        return self.inner_radius

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class CappedCylindricalTank:
    """
    Cylindrical oxidizer tank closed by two hemispherical end caps of the same
    wall thickness as the cylinder. Stronger under pressure than flat caps and
    encloses more interior volume for a given cylinder length.

    Attributes:
        - user defined -
        inner_diameter: Meters
        length: Meters           (cylinder body length, not including hemisphere protrusion)
        wall_thickness: Meters
        material: Material_Solid

        - automatically calculated -
        inner_radius: Meters
        outer_radius: Meters
        outer_diameter: Meters
        total_length: Meters     (length + 2 × outer_radius)

    Inertia formulas used:
        Hemispherical shell (Ri, Ro):
            I_axial = I_lat_about_flat_base = m · (2/5) · (Ro⁵ − Ri⁵) / (Ro³ − Ri³)
            CG from flat base = (3/8) · (Ro⁴ − Ri⁴) / (Ro³ − Ri³)
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    outer_diameter: Meters
    length: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Capped Cylindrical Tank"
    inner_radius: Meters = field(init=False)
    outer_radius: Meters = field(init=False)
    inner_diameter: Meters = field(init=False)
    total_length: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.inner_diameter = self.outer_diameter - 2.0 * self.wall_thickness
        self.inner_radius = self.inner_diameter / 2.0
        self.outer_radius = self.inner_radius + self.wall_thickness
        self.total_length = self.length + 2.0 * self.outer_radius

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def _shell_volume(self):
        return math.pi * (self.outer_radius**2 - self.inner_radius**2) * self.length

    @property
    def _hemi_volume(self):
        """Volume of one hemispherical shell (structural material only)."""
        return (2.0 * math.pi / 3.0) * (self.outer_radius**3 - self.inner_radius**3)

    @property
    def _hemi_cg(self):
        """CG of one hemispherical shell from its flat base face."""
        Ro, Ri = self.outer_radius, self.inner_radius
        return (3.0 / 8.0) * (Ro**4 - Ri**4) / (Ro**3 - Ri**3)

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return self._shell_volume + 2.0 * self._hemi_volume

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):  # distance from front cylinder face → length/2 by symmetry
        if self._cg is not None:
            return self._cg
        return self.length / 2.0

    @property
    def I_lateral(self):  # about CG, perpendicular to axis
        if self._I_lateral is not None:
            return self._I_lateral
        Ro, Ri, L = self.outer_radius, self.inner_radius, self.length
        rho = self.material.density
        m_shell = rho * self._shell_volume
        m_hemi = rho * self._hemi_volume
        cg_h = self._hemi_cg
        # Hollow cylinder shell about its own CG (coincides with tank CG)
        I_shell = (m_shell / 12.0) * (3.0 * (Ro**2 + Ri**2) + L**2)
        # Hemispherical shell I about lateral axis through its flat base centre:
        #   I_base = m · (2/5) · (Ro⁵ − Ri⁵) / (Ro³ − Ri³)
        I_hemi_base = m_hemi * (2.0 / 5.0) * (Ro**5 - Ri**5) / (Ro**3 - Ri**3)
        # Shift to hemisphere own CG, then parallel-axis to tank CG (distance = L/2 + cg_h)
        I_hemi_own = I_hemi_base - m_hemi * cg_h**2
        d = L / 2.0 + cg_h
        I_each_hemi = I_hemi_own + m_hemi * d**2
        return I_shell + 2.0 * I_each_hemi

    @property
    def I_axial(self):  # about roll axis
        if self._I_axial is not None:
            return self._I_axial
        Ro, Ri, L = self.outer_radius, self.inner_radius, self.length
        rho = self.material.density
        m_shell = rho * self._shell_volume
        m_hemi = rho * self._hemi_volume
        # Hollow cylinder shell
        I_shell = (m_shell / 2.0) * (Ro**2 + Ri**2)
        # Hemispherical shell: I_axial = m · (2/5) · (Ro⁵ − Ri⁵) / (Ro³ − Ri³)
        I_hemi = m_hemi * (2.0 / 5.0) * (Ro**5 - Ri**5) / (Ro**3 - Ri**3)
        return I_shell + 2.0 * I_hemi

    def y_upper(self, x: Meters) -> Meters:
        """
        Outer radius at axial position x from the front dome tip.
        x ∈ [0, total_length]:
          [0, outer_radius]              — front hemisphere
          [outer_radius, outer_radius+length] — cylinder body
          [outer_radius+length, total_length] — rear hemisphere
        """
        Ro, L = self.outer_radius, self.length
        if x <= Ro:
            return math.sqrt(Ro**2 - (Ro - x) ** 2)
        elif x <= Ro + L:
            return Ro
        else:
            return math.sqrt(max(Ro**2 - (x - (Ro + L)) ** 2, 0.0))

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner radius at axial position x. The inner hemispheres are concentric
        with the outer ones (constant ⊥ thickness ⇒ same centre, radius=Ri).
          [0, t]                       — solid front dome tip → 0
          [t, Ro]                      — front inner hemisphere
          [Ro, Ro+L]                   — cylinder inner wall → Ri
          [Ro+L, total_length-t]       — rear inner hemisphere
          [total_length-t, total_length] — solid rear dome tip → 0
        """
        Ro, Ri, L, t = (
            self.outer_radius,
            self.inner_radius,
            self.length,
            self.wall_thickness,
        )
        if x < t:
            return 0.0
        if x <= Ro:
            return math.sqrt(max(Ri**2 - (Ro - x) ** 2, 0.0))
        if x <= Ro + L:
            return Ri
        if x <= self.total_length - t:
            return math.sqrt(max(Ri**2 - (x - (Ro + L)) ** 2, 0.0))
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class ConicalNoseCone:
    """
    A conical nose cone — straight taper from base to tip. Treated as solid
    until SDFs land for shell thickness.

    Attributes:
        - user defined -
        length: Meters
        base_radius: Meters
        material: Material_Solid
        name: str

        - automatically calculated -
        base_diameter: Meters
        fineness_ratio: NonDimensional
        half_angle_rad: Radians
        half_angle_deg: Degrees
        slant_length: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    length: Meters
    base_radius: Meters
    material: Material_Solid
    name: str = "Conical Nose Cone"
    base_diameter: Meters = field(init=False)
    fineness_ratio: NonDimensional = field(init=False)
    half_angle_rad: Radians = field(init=False)
    half_angle_deg: Degrees = field(init=False)
    slant_length: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)
    _surface_area: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.base_diameter = self.base_radius * 2.0
        self.fineness_ratio = self.length / self.base_diameter
        self.half_angle_rad = math.atan(self.base_radius / self.length)
        self.half_angle_deg = math.degrees(self.half_angle_rad)
        self.slant_length = math.sqrt(self.length**2 + self.base_radius**2)

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    def set_surface_area(self, value: float | None) -> None:
        self._surface_area = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return (1.0 / 3.0) * math.pi * self.base_radius**2 * self.length

    @property
    def surface_area(self):  # lateral surface only
        if self._surface_area is not None:
            return self._surface_area
        return math.pi * self.base_radius * self.slant_length

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        """CG of a solid cone, measured from the tip. cg = 3L/4."""
        if self._cg is not None:
            return self._cg
        return 3.0 * self.length / 4.0

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        # Solid cone (apex at x=0) — closed form, about CG perpendicular to axis:
        #   I_lat = (3/80) M (4 R² + L²)   [classic result]
        M, R, L = self.mass, self.base_radius, self.length
        return (3.0 / 80.0) * M * (4.0 * R**2 + L**2)

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        # Solid cone about its symmetry axis:  I_ax = (3/10) M R²
        return (3.0 / 10.0) * self.mass * self.base_radius**2

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius at axial position x from the tip."""
        return self.base_radius * x / self.length

    def y_lower(self, x: Meters) -> Meters:
        """Conical nose cone has no wall_thickness — treated as solid."""
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class OgiveNoseCone:
    r"""
        A tangent ogive nose cone — profile is an arc of a circle tangent to the body tube.

        Attributes:
            - user defined -
            length: Meters
            base_radius: Meters
            wall_thickness: Meters

            - automatically calculated -
            base_diameter: Meters
            fineness_ratio: NonDimensional
            ogive_radius: Meters       (radius of the circular arc defining the outer profile)
            inner_radius: Meters
            inner_ogive_radius: Meters

            formula for tangent ogive:
            \begin{aligned}
                \rho & =\frac{R+\frac{L^2}{R}}{2} \\
                y & =\sqrt{\rho^2+x(2 L-x)-L^2}+R-\rho
            \end{aligned}
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    length: Meters
    base_radius: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Ogive Nose Cone"
    base_diameter: Meters = field(init=False)
    fineness_ratio: NonDimensional = field(init=False)
    ogive_radius: Meters = field(init=False)
    ogive_diameter: Meters = field(init=False)
    inner_radius: Meters = field(init=False)
    inner_diameter: Meters = field(init=False)
    inner_ogive_radius: Meters = field(init=False)
    inner_ogive_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)
    _surface_area: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.base_diameter = self.base_radius * 2.0
        self.fineness_ratio = self.length / self.base_diameter
        self.ogive_radius = (self.base_radius**2 + self.length**2) / (
            2.0 * self.base_radius
        )
        self.ogive_diameter = self.ogive_radius * 2.0
        self.inner_radius = self.base_radius - self.wall_thickness
        self.inner_diameter = self.inner_radius * 2.0
        self.inner_ogive_radius = (self.inner_radius**2 + self.length**2) / (
            2.0 * self.inner_radius
        )
        self.inner_ogive_diameter = self.inner_ogive_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    def set_surface_area(self, value: float | None) -> None:
        self._surface_area = value

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius of the ogive profile at axial position x from the tip."""
        return (
            math.sqrt(self.ogive_radius**2 - (self.length - x) ** 2)
            + self.base_radius
            - self.ogive_radius
        )

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner profile by perpendicular offset of y_upper at the same x.
        Slope is sampled with central differences (two y_upper calls at
        x±h); cos(theta) = 1/sqrt(1 + slope²) is the radial component of
        the perpendicular offset, so the wall has constant *perpendicular*
        thickness — what a real laid-up or machined wall actually has,
        rather than the constant *vertical* offset which over-counts
        material on sloped sections.
        """
        L = self.length
        h = 1e-7
        x_lo = max(x - h, 0.0)
        x_hi = min(x + h, L)
        span = x_hi - x_lo
        if span <= 0.0:
            return max(self.y_upper(x), 0.0)
        m = (self.y_upper(x_hi) - self.y_upper(x_lo)) / span
        cos_theta = 1.0 / math.sqrt(1.0 + m * m)
        return max(self.y_upper(x) - self.wall_thickness * cos_theta, 0.0)

    @property
    def volume(self):
        """Shell volume — numerical, perpendicular wall thickness via y_lower."""
        if self._volume is not None:
            return self._volume
        vol, _, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.length, self.material.density
        )
        return vol

    @property
    def surface_area(self):  # outer lateral surface only
        if self._surface_area is not None:
            return self._surface_area
        rho, R, L = self.ogive_radius, self.base_radius, self.length
        return 2.0 * math.pi * rho * (L + (R - rho) * math.asin(L / rho))

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        """Numerical CG from the tip — analytical form is messy for a shell ogive."""
        if self._cg is not None:
            return self._cg
        _, cg, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.length, self.material.density
        )
        return cg

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        _, _, I_lat, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.length, self.material.density
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        _, _, _, I_ax = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.length, self.material.density
        )
        return I_ax

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class VonKarmanNoseCone:
    """
    A Von Karman (Haack series, C=0) nose cone — minimises wave drag for a given length and base diameter.

    Attributes:
        - user defined -
        length: Meters
        base_radius: Meters
        wall_thickness: Meters

        - automatically calculated -
        base_diameter: Meters
        fineness_ratio: NonDimensional
        inner_radius: Meters

    Haack series (C=0):
        x(θ) = L/2 · (1 - cos(θ))
        y(θ) = R/√π · √(θ - sin(2θ)/2)
        V(R,L) = π·R²·L/2                   [closed-form, C=0 term vanishes]
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    length: Meters
    base_radius: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Von Karman Nose Cone"
    base_diameter: Meters = field(init=False)
    fineness_ratio: NonDimensional = field(init=False)
    inner_radius: Meters = field(init=False)
    inner_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)
    _surface_area: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.base_diameter = self.base_radius * 2.0
        self.fineness_ratio = self.length / self.base_diameter
        self.inner_radius = self.base_radius - self.wall_thickness
        self.inner_diameter = self.inner_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    def set_surface_area(self, value: float | None) -> None:
        self._surface_area = value

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius of the Von Karman profile at axial position x from the tip."""
        theta = math.acos(1.0 - 2.0 * x / self.length)
        return (self.base_radius / math.sqrt(math.pi)) * math.sqrt(
            theta - math.sin(2.0 * theta) / 2.0
        )

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner profile by perpendicular offset of y_upper at the same x.
        Slope is sampled with central differences (two y_upper calls at
        x±h); cos(theta) = 1/sqrt(1 + slope²) is the radial component of
        the perpendicular offset.
        """
        L = self.length
        h = 1e-7
        x_lo = max(x - h, 0.0)
        x_hi = min(x + h, L)
        span = x_hi - x_lo
        if span <= 0.0:
            return max(self.y_upper(x), 0.0)
        m = (self.y_upper(x_hi) - self.y_upper(x_lo)) / span
        cos_theta = 1.0 / math.sqrt(1.0 + m * m)
        return max(self.y_upper(x) - self.wall_thickness * cos_theta, 0.0)

    @property
    def volume(self):
        """Shell volume — numerical, perpendicular wall thickness via y_lower."""
        if self._volume is not None:
            return self._volume
        eps = self.length * 1e-6
        vol, _, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return vol

    @property
    def surface_area(self):
        """Numerical surface of revolution (the Haack-series area has no clean closed form)."""
        if self._surface_area is not None:
            return self._surface_area
        # avoid x=0 / x=L where acos derivatives blow up; sample slightly inside
        eps = self.length * 1e-6
        xs = np.linspace(eps, self.length - eps, 400)
        ys = np.array([self.y_upper(x) for x in xs])
        dy = np.gradient(ys, xs)
        return float(np.trapezoid(2.0 * np.pi * ys * np.sqrt(1.0 + dy**2), xs))

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        eps = self.length * 1e-6
        _, cg, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return cg

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        eps = self.length * 1e-6
        _, _, I_lat, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        eps = self.length * 1e-6
        _, _, _, I_ax = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return I_ax

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class LVHaackNoseCone:
    """
    An LV-Haack (Haack series, C=1/3) nose cone — minimises volume for a given length and base diameter.

    Attributes:
        - user defined -
        length: Meters
        base_radius: Meters
        wall_thickness: Meters

        - automatically calculated -
        base_diameter: Meters
        fineness_ratio: NonDimensional
        inner_radius: Meters

    Haack series (C=1/3):
        x(θ) = L/2 · (1 - cos(θ))
        y(θ) = R/√π · √(θ - sin(2θ)/2 + 1/3·sin³(θ))
        V(R,L) = π·R²·L/2 · (1 + 1/8) = 9π·R²·L/16  [closed-form]
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    length: Meters
    base_radius: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "LV-Haack Nose Cone"
    base_diameter: Meters = field(init=False)
    fineness_ratio: NonDimensional = field(init=False)
    inner_radius: Meters = field(init=False)
    inner_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)
    _surface_area: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.base_diameter = self.base_radius * 2.0
        self.fineness_ratio = self.length / self.base_diameter
        self.inner_radius = self.base_radius - self.wall_thickness
        self.inner_diameter = self.inner_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    def set_surface_area(self, value: float | None) -> None:
        self._surface_area = value

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius of the LV-Haack profile at axial position x from the tip."""
        theta = math.acos(1.0 - 2.0 * x / self.length)
        return (self.base_radius / math.sqrt(math.pi)) * math.sqrt(
            theta - math.sin(2.0 * theta) / 2.0 + (1.0 / 3.0) * math.sin(theta) ** 3
        )

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner profile by perpendicular offset of y_upper at the same x.
        Slope is sampled with central differences (two y_upper calls at
        x±h); cos(theta) = 1/sqrt(1 + slope²) is the radial component of
        the perpendicular offset.
        """
        L = self.length
        h = 1e-7
        x_lo = max(x - h, 0.0)
        x_hi = min(x + h, L)
        span = x_hi - x_lo
        if span <= 0.0:
            return max(self.y_upper(x), 0.0)
        m = (self.y_upper(x_hi) - self.y_upper(x_lo)) / span
        cos_theta = 1.0 / math.sqrt(1.0 + m * m)
        return max(self.y_upper(x) - self.wall_thickness * cos_theta, 0.0)

    @property
    def volume(self):
        """Shell volume — numerical, perpendicular wall thickness via y_lower."""
        if self._volume is not None:
            return self._volume
        eps = self.length * 1e-6
        vol, _, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return vol

    @property
    def surface_area(self):
        """Numerical surface of revolution (no clean closed form for the Haack series)."""
        if self._surface_area is not None:
            return self._surface_area
        eps = self.length * 1e-6
        xs = np.linspace(eps, self.length - eps, 400)
        ys = np.array([self.y_upper(x) for x in xs])
        dy = np.gradient(ys, xs)
        return float(np.trapezoid(2.0 * np.pi * ys * np.sqrt(1.0 + dy**2), xs))

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        eps = self.length * 1e-6
        _, cg, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return cg

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        eps = self.length * 1e-6
        _, _, I_lat, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        eps = self.length * 1e-6
        _, _, _, I_ax = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, eps, self.length - eps, self.material.density
        )
        return I_ax

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class BodyTube:
    """
    A cylindrical body tube section.

    Attributes:
        - user defined -
        outer_diameter: Meters
        length: Meters
        wall_thickness: Meters
        material: Material_Solid

        - automatically calculated -
        outer_radius: Meters
        inner_radius: Meters
        inner_diameter: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    outer_diameter: Meters
    length: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Body Tube"
    outer_radius: Meters = field(init=False)
    inner_radius: Meters = field(init=False)
    inner_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.outer_radius = self.outer_diameter / 2.0
        self.inner_radius = self.outer_radius - self.wall_thickness
        self.inner_diameter = self.inner_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return math.pi * (self.outer_radius**2 - self.inner_radius**2) * self.length

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.length / 2.0

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        Ro, Ri, L = self.outer_radius, self.inner_radius, self.length
        m = self.mass
        return (m / 12.0) * (3.0 * (Ro**2 + Ri**2) + L**2)

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        Ro, Ri = self.outer_radius, self.inner_radius
        return (self.mass / 2.0) * (Ro**2 + Ri**2)

    def y_upper(self, x: Meters) -> Meters:
        return self.outer_radius

    def y_lower(self, x: Meters) -> Meters:
        return self.inner_radius

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


def generate_freeform_fins(
    sweep_deg: float,
    height: float,
    root_chord: float,
    tip_chord: float,
) -> tuple[tuple[float, float], ...]:
    """
    Return the four trapezoid corner points in the conventional order:
    A=root LE, B=root TE, C=tip TE, D=tip LE.
    """
    sweep_offset = math.tan(math.radians(float(sweep_deg))) * float(height)

    A = (0.0, 0.0)
    B = (float(root_chord), 0.0)
    C = (sweep_offset + float(tip_chord), float(height))
    D = (sweep_offset, float(height))
    return (A, B, C, D)


def _upper_y_from_points(points: list[tuple[float, float]], x: float) -> float:
    """
    Return the upper envelope y-value of a polygonal fin planform at chord x.
    Assumes points are ordered around the outer boundary.
    """
    ys: list[float] = []
    n = len(points)
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        if x0 == x1:
            if x == x0:
                ys.extend([float(y0), float(y1)])
            continue
        if min(x0, x1) <= x <= max(x0, x1):
            t = (x - x0) / (x1 - x0)
            ys.append(y0 + (y1 - y0) * t)
    return max(ys) if ys else 0.0


@dataclass
class TrapezoidalFins:
    """
    Fins with a trapezium planform and a parametric cross section
    extruded normal to the planform.

    Planform (the X marks are the corner points used internally):

        X______X
       /       |
      /        |
     /         |
    X__________X

    Cross section is delegated to a :class:`WingCrossSection` instance
    — pass one in via ``cross_section``, or omit it to have one
    auto-built from ``thickness`` / ``le_wedge_length`` /
    ``te_wedge_length`` (slab if both wedge lengths are zero, otherwise
    supersonic wedge).

    The cross section parameters are interpreted at the ROOT chord and
    are scaled by the cross-section subclass at every span station so
    the cross section spans the local chord LE-to-TE; in particular the
    cross section at the tip is naturally smaller than at the root by
    the chord ratio.

    Attributes:
        - user defined -
        sweep, cant_angle: Degrees
        height, root_chord, tip_chord: Meters
        thickness: Meters              (max thickness — used by the
                                        auto-built cross section)
        le_wedge_length: Meters        (LE wedge length at root_chord;
                                        auto-built supersonic-wedge only)
        te_wedge_length: Meters        (TE wedge length at root_chord;
                                        auto-built supersonic-wedge only)
        cross_section: WingCrossSection | None
                                       (explicit cross section; if None,
                                        built from thickness / wedges)
        material: Material_Solid
        name: str

        - automatically calculated -
        planform_area: Meters²
        avg_chord: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.WING

    sweep: Degrees
    height: Meters
    root_chord: Meters
    tip_chord: Meters
    cant_angle: Degrees
    thickness: Meters
    material: Material_Solid
    le_wedge_length: Meters = 0.0
    te_wedge_length: Meters = 0.0
    cross_section: WingCrossSection | None = None
    name: str = "Trapezoidal Fins"
    planform_area: Meters = field(init=False)
    avg_chord: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        A, B, C, D = generate_freeform_fins(
            self.sweep, self.height, self.root_chord, self.tip_chord
        )
        self._sweep_offset = float(D[0])
        self.points = [
            A,
            D,
            C,
            B,
        ]
        self.planform_area = (self.root_chord + self.tip_chord) * self.height / 2.0
        self.avg_chord = (self.root_chord + self.tip_chord) / 2.0
        if self.cross_section is None:
            if float(self.le_wedge_length) > 0.0 or float(self.te_wedge_length) > 0.0:
                self.cross_section = SupersonicWedgeCrossSection(
                    thickness=float(self.thickness),
                    le_wedge_length=float(self.le_wedge_length),
                    te_wedge_length=float(self.te_wedge_length),
                )
            else:
                self.cross_section = SlabCrossSection(thickness=float(self.thickness))

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    # --- planform & cross-section helpers used by the extrusion integrator ---
    def _x_le_at_span(self, y: Meters) -> Meters:
        """Leading-edge chord position at span y (linear from p0 → p1)."""
        return self._sweep_offset * y / self.height

    def _x_te_at_span(self, y: Meters) -> Meters:
        """Trailing-edge chord position at span y (linear from p3 → p2)."""
        return self.root_chord + (
            (self._sweep_offset + self.tip_chord - self.root_chord) * y / self.height
        )

    def cross_section_thickness(self, s: Meters, local_chord: Meters) -> Meters:
        """
        Local thickness at chord-from-LE position ``s`` for a given
        ``local_chord``. Delegates to the wing's :class:`WingCrossSection`
        with the fin's root chord as the scaling reference (so wedges
        and other chord-aligned features are in proportion at every
        span station).
        """
        return float(
            self.cross_section.evaluate(
                float(s), float(local_chord), float(self.root_chord)
            )
        )

    @property
    def volume(self):
        """Volume of one fin via numerical extrusion of the cross section."""
        if self._volume is not None:
            return self._volume
        vol, _, _, _, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            self.height,
            self.material.density,
        )
        return vol

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        """
        CG of one fin in the chord direction, measured from the root LE (x=0).
        Computed numerically from the cross-section extrusion. The
        spanwise CG is reported separately via :attr:`cg_span` and is
        what the assembly uses to place the fin radially in xyz.
        """
        if self._cg is not None:
            return self._cg
        _, cg_x, _, _, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            self.height,
            self.material.density,
        )
        return cg_x

    @property
    def cg_span(self) -> Meters:
        """
        Spanwise CG of one fin, measured from the root (y_local = 0) toward
        the tip. Used by the assembly's parallel-axis sums to position the
        fin's mass at the correct radial station above the body surface.
        """
        _, _, cg_y, _, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            self.height,
            self.material.density,
        )
        return cg_y

    @property
    def I_lateral(self):
        """About a span-aligned axis through the fin CG."""
        if self._I_lateral is not None:
            return self._I_lateral
        _, _, _, I_lat, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            self.height,
            self.material.density,
        )
        return I_lat

    @property
    def I_axial(self):
        """About a chord-aligned axis through the fin CG."""
        if self._I_axial is not None:
            return self._I_axial
        _, _, _, _, I_ax = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            self.height,
            self.material.density,
        )
        return I_ax

    def y_upper(self, x: Meters) -> Meters:
        """
        Span at chord position x from the full fin polygon envelope.
        """
        return _upper_y_from_points(self.points, float(x))

    def y_lower(self, x: Meters) -> Meters:
        """Fin root sits flush against the body — no offset."""
        return 0.0

    def eta_upper(self, x: Meters, y: Meters) -> Meters:
        """
        Upper eta extent (offset from the fin's eta centerline) at fin-local
        chord ``x`` and span ``y``. Returns NaN when (x, y) lies outside the
        fin's planform — at chord x there is no material at this span.

        For the wedge-flat-wedge cross section this is +thickness(x at span y) / 2.
        """
        if y < 0.0 or y > self.height:
            return float("nan")
        x_le = self._x_le_at_span(y)
        x_te = self._x_te_at_span(y)
        if x < x_le or x > x_te:
            return float("nan")
        local_chord = x_te - x_le
        if local_chord <= 0.0:
            return float("nan")
        return self.cross_section_thickness(x - x_le, local_chord) / 2.0

    def eta_lower(self, x: Meters, y: Meters) -> Meters:
        """Lower eta extent at fin-local (x, y); mirror of ``eta_upper``."""
        eu = self.eta_upper(x, y)
        return eu if eu != eu else -eu  # NaN propagates

    def plot(self, x_values, options: dict = None):
        import matplotlib.pyplot as plt

        opts = {
            "show": True,
            "title": f"{self.name} Planform",
            "color": "darkviolet",
        }
        if options:
            opts.update(options)
        color = opts["color"]
        y_vals = [self.y_upper(x) for x in x_values]
        fig, ax = plt.subplots()
        ax.fill_between(x_values, 0, y_vals, color=color, alpha=1)
        # draw the closed polygon outline
        px = [p[0] for p in self.points] + [self.points[0][0]]
        py = [p[1] for p in self.points] + [self.points[0][1]]
        ax.plot(px, py, color=color)
        ax.set_aspect("equal")
        ax.set_title(opts["title"])
        ax.set_xlabel("chord (m)")
        ax.set_ylabel("span (m)")
        ax.grid(True)
        if opts["show"]:
            plt.show()
        return fig, ax

    def plot_cross_section(self, span: Meters, ax=None, options: dict = None):
        """
        Plot the cross section at span station ``span`` (measured from
        the root, in [0, height]). Delegates to the wing's
        :class:`WingCrossSection` instance for the thickness profile.

        options keys (all optional):
            n         : int   — chord sample count (default 200)
            show      : bool  — call plt.show() at the end (standalone only;
                                default True)
            title     : str   — plot title (standalone only)
            color     : str | tuple — line/fill colour (default 'darkviolet')
            align_le  : bool  — origin at local LE (True, default) or at the
                                root LE / global chord frame (False)
            y_offset  : float — vertical offset added to the (±t/2) profile,
                                useful for stacking several span stations at
                                their physical spanwise positions (default 0)
            label     : str   — legend label (default 'y = {span:.3f} m')
            alpha     : float — fill alpha (default 0.35)

        If ``ax`` is None, creates a fresh figure/axes and renders it.
        Otherwise, the cross section is added to ``ax`` (so several span
        stations can be overlaid on a single plot) and ``show`` is ignored.
        """
        import matplotlib.pyplot as plt

        if span < 0.0 or span > self.height:
            raise ValueError(
                f"{self.name}: span={span:.4f} m outside fin "
                f"(valid range: [0, {self.height:.4f} m])"
            )

        opts = {
            "n": 200,
            "show": True,
            "title": f"{self.name} Cross Section",
            "color": "darkviolet",
            "align_le": True,
            "y_offset": 0.0,
            "label": None,
            "alpha": 0.35,
        }
        if options:
            opts.update(options)

        x_le = self._x_le_at_span(span)
        x_te = self._x_te_at_span(span)
        local_chord = x_te - x_le
        if local_chord <= 0:
            raise ValueError(
                f"{self.name}: local chord at span={span:.4f} m is non-positive"
            )

        ss = np.linspace(0.0, local_chord, int(opts["n"]))
        ts = np.array([self.cross_section_thickness(float(s), local_chord) for s in ss])
        xs = ss if opts["align_le"] else ss + x_le
        y_offset = float(opts["y_offset"])
        upper = ts / 2.0 + y_offset
        lower = -ts / 2.0 + y_offset

        standalone = ax is None
        if standalone:
            fig, ax = plt.subplots()

        label = opts["label"] if opts["label"] is not None else f"y = {span:.3f} m"
        ax.fill_between(xs, lower, upper, color=opts["color"], alpha=opts["alpha"])
        ax.plot(xs, upper, color=opts["color"], label=label)
        ax.plot(xs, lower, color=opts["color"])

        if standalone:
            ax.set_aspect("equal")
            ax.set_title(opts["title"])
            ax.set_xlabel(
                "chord position from local LE (m)"
                if opts["align_le"]
                else "chord position from root LE (m)"
            )
            ax.set_ylabel("thickness (m)")
            ax.grid(True)
            ax.legend(loc="best")
            if opts["show"]:
                plt.show()
            return fig, ax
        return ax


@dataclass
class VonKarmanBoatTail:
    """
        boat tail is reverse nosecone, but that is cut before
        it reaches a point

        <- nosecone | nozzle ->
                |--------\
          top   |         |  bottom
                |--------/


        [boattail]
        boattail_bottom_diameter = 0.12246
        bottail_length = 0.35
        boattail_position = 3.3338
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    boattail_bottom_diameter: Meters
    boattail_top_diameter: Meters
    boattail_length: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Von Karman Boattail"
    boattail_bottom_radius: Meters = field(init=False)
    boattail_top_radius: Meters = field(init=False)
    inner_top_radius: Meters = field(init=False)
    inner_top_diameter: Meters = field(init=False)
    inner_bottom_radius: Meters = field(init=False)
    inner_bottom_diameter: Meters = field(init=False)
    normalized_bottom_radius: NonDimensional = field(init=False)
    _theta_at_bottom: float = field(init=False, repr=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.boattail_bottom_radius = self.boattail_bottom_diameter / 2.0
        self.boattail_top_radius = self.boattail_top_diameter / 2.0
        self.inner_top_radius = self.boattail_top_radius - self.wall_thickness
        self.inner_top_diameter = self.inner_top_radius * 2.0
        self.inner_bottom_radius = self.boattail_bottom_radius - self.wall_thickness
        self.inner_bottom_diameter = self.inner_bottom_radius * 2.0
        # target = normalised radius, used to back calculate the theta
        # that gives that radius. equations are in Wikipedia
        self.normalized_bottom_radius = (
            self.boattail_bottom_radius / self.boattail_top_radius
        )
        self._theta_at_bottom = self._solve_theta(self.normalized_bottom_radius)

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        vol, _, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.boattail_length, self.material.density
        )
        return vol

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        _, cg, _, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.boattail_length, self.material.density
        )
        return cg

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        _, _, I_lat, _ = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.boattail_length, self.material.density
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        _, _, _, I_ax = _shell_axisymmetric_props(
            self.y_upper, self.y_lower, 0.0, self.boattail_length, self.material.density
        )
        return I_ax

    @staticmethod
    def _solve_theta(normalized_bottom_radius: float) -> float:
        """
        Bisection search for the theta that cuts the Von Karman nosecone at the
        bottom of the boattail (i.e. at the requested normalised radius).
        Equations are on Wikipedia.
        """
        lo, hi = 1e-9, math.pi - 1e-9
        for _ in range(60):
            mid = (lo + hi) / 2.0
            if (
                math.sqrt((mid - math.sin(2.0 * mid) / 2.0) / math.pi)
                < normalized_bottom_radius
            ):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    def y_upper(self, x: Meters) -> Meters:
        """
        Outer radius at axial position x from the top (wide) end.
        x must be in [0, boattail_length].
        """
        theta = math.acos(
            x * (1.0 + math.cos(self._theta_at_bottom)) / self.boattail_length - 1.0
        )
        return self.boattail_top_radius * math.sqrt(
            (theta - math.sin(2.0 * theta) / 2.0) / math.pi
        )

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner profile by perpendicular offset of y_upper at the same x.
        Slope is sampled with central differences (two y_upper calls at
        x±h); cos(theta) = 1/sqrt(1 + slope²) is the radial component of
        the perpendicular offset, so the wall has constant *perpendicular*
        thickness rather than a constant vertical offset.
        """
        L = self.boattail_length
        h = 1e-7
        x_lo = max(x - h, 0.0)
        x_hi = min(x + h, L)
        span = x_hi - x_lo
        if span <= 0.0:
            return max(self.y_upper(x), 0.0)
        m = (self.y_upper(x_hi) - self.y_upper(x_lo)) / span
        cos_theta = 1.0 / math.sqrt(1.0 + m * m)
        return max(self.y_upper(x) - self.wall_thickness * cos_theta, 0.0)

    def plot(self, x_values, options: dict = None):
        """
        Plot the boattail profile.

        options keys (all optional):
            show   : bool — call plt.show() at the end (default True)
            title  : str  — plot title (defaults to f"{self.name} Profile")
            xlabel : str  — x-axis label
            ylabel : str  — y-axis label
            color  : str  — line / fill colour
        """
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class DrogueParachute:
    """
    Drogue parachute.

    The packed bundle is modelled as a box: a packed_length × packed_radius
    rectangular 2-D profile that revolves into a uniform cylinder. The box
    *is* the packed volume — V = π · packed_radius² · packed_length —
    which also feeds mass and the uniform-cylinder inertia.

    Attributes:
        - user defined -
        parachute_radius: Meters       (deployed canopy radius)
        cd: NonDimensional
        packed_length: Meters          (axial extent of the packed box)
        packed_radius: Meters          (radial extent of the packed box)
        material: Material_Solid
        trigger: str = "apogee"
        lag: Time
        name: str

        - automatically calculated -
        parachute_diameter: Meters
        packed_diameter: Meters

    [recovery]
     drogue_cds = 0.836
     parachute_drogue_radius = 0.38
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC
    is_inner: ClassVar[bool] = True

    parachute_radius: Meters
    cd: NonDimensional
    packed_length: Meters
    packed_radius: Meters
    material: Material_Solid = field(default_factory=Nylon)
    name: str = "Drogue"
    trigger: str = "apogee"
    lag: Time = field(default=1.0)
    parachute_diameter: Meters = field(init=False)
    packed_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.parachute_diameter = self.parachute_radius * 2.0
        self.packed_diameter = self.packed_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        """Volume of the revolved box (uniform cylinder)."""
        if self._volume is not None:
            return self._volume
        return math.pi * self.packed_radius**2 * self.packed_length

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.packed_length / 2.0

    @property
    def I_lateral(self):
        """Uniform cylinder about the packed-box CG, perpendicular to axis."""
        if self._I_lateral is not None:
            return self._I_lateral
        m, R, L = self.mass, self.packed_radius, self.packed_length
        return (m / 12.0) * (3.0 * R**2 + L**2)

    @property
    def I_axial(self):
        """Uniform cylinder about the symmetry axis."""
        if self._I_axial is not None:
            return self._I_axial
        return self.mass / 2.0 * self.packed_radius**2

    def y_upper(self, x: Meters) -> Meters:
        """Box profile — packed_radius across the entire packed_length."""
        return self.packed_radius

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Parachute (packed)"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class MainParachute:
    """
    Main parachute. Same packed-box model as `DrogueParachute` — the
    packed_length × packed_radius rectangle defines a revolved cylinder
    whose volume *is* the packed volume. Differs only in trigger semantics
    (altitude rather than apogee).

    Attributes:
        - user defined -
        trigger: Time                  (deploy altitude)
        parachute_radius: Meters       (deployed canopy radius)
        cd: NonDimensional
        packed_length: Meters          (axial extent of the packed box)
        packed_radius: Meters          (radial extent of the packed box)
        material: Material_Solid
        lag: Time
        name: str

        - automatically calculated -
        parachute_diameter: Meters
        packed_diameter: Meters

    [recovery]
    main_cds = 3.3
    main_trigger = 396.24
    parachute_main_radius = 1.5
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC
    is_inner: ClassVar[bool] = True

    trigger: Time
    parachute_radius: Meters
    cd: NonDimensional
    packed_length: Meters
    packed_radius: Meters
    material: Material_Solid = field(default_factory=Nylon)
    lag: Time = field(default=1.0)
    name: str = "Main"
    parachute_diameter: Meters = field(init=False)
    packed_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.parachute_diameter = self.parachute_radius * 2.0
        self.packed_diameter = self.packed_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        """Volume of the revolved box (uniform cylinder)."""
        if self._volume is not None:
            return self._volume
        return math.pi * self.packed_radius**2 * self.packed_length

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.packed_length / 2.0

    @property
    def I_lateral(self):
        """Uniform cylinder about the packed-box CG, perpendicular to axis."""
        if self._I_lateral is not None:
            return self._I_lateral
        m, R, L = self.mass, self.packed_radius, self.packed_length
        return (m / 12.0) * (3.0 * R**2 + L**2)

    @property
    def I_axial(self):
        """Uniform cylinder about the symmetry axis."""
        if self._I_axial is not None:
            return self._I_axial
        return self.mass / 2.0 * self.packed_radius**2

    def y_upper(self, x: Meters) -> Meters:
        """Box profile — packed_radius across the entire packed_length."""
        return self.packed_radius

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Parachute (packed)"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class MassComponent:
    """
    A general axisymmetric solid cylinder used to represent unsupported
    mass objects — avionics bays, payloads, batteries, anything whose
    geometry isn't worth modelling explicitly. The cylinder is solid;
    if the user knows the mass directly (more common than the density
    of the lumped object) they can override it via :meth:`set_mass`.

    Attributes:
        - user defined -
        diameter: Meters
        length: Meters
        material: Material_Solid       (defaults to Aluminum; only used
                                        if mass isn't overridden)
        name: str

        - automatically calculated -
        radius: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC
    is_inner: ClassVar[bool] = True

    diameter: Meters
    length: Meters
    material: Material_Solid = field(default_factory=Aluminum)
    name: str = "Mass Component"
    radius: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.radius = self.diameter / 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return math.pi * self.radius**2 * self.length

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.length / 2.0

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        m, R, L = self.mass, self.radius, self.length
        return (m / 12.0) * (3.0 * R**2 + L**2)

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        return self.mass / 2.0 * self.radius**2

    def y_upper(self, x: Meters) -> Meters:
        return self.radius

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class TubeCoupler:
    """
    A short body tube that lives INSIDE a body tube — used to couple two
    body tubes together end-to-end. Geometrically identical to a body
    tube (hollow cylinder), but conceptually an "inner component": its
    outer diameter is smaller than the surrounding body tube's inner
    diameter, so it does not define the rocket's outer envelope.

    Attributes:
        - user defined -
        outer_diameter: Meters
        length: Meters
        wall_thickness: Meters
        material: Material_Solid

        - automatically calculated -
        outer_radius: Meters
        inner_radius: Meters
        inner_diameter: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC
    is_inner: ClassVar[bool] = True

    outer_diameter: Meters
    length: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Tube Coupler"
    outer_radius: Meters = field(init=False)
    inner_radius: Meters = field(init=False)
    inner_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.outer_radius = self.outer_diameter / 2.0
        self.inner_radius = self.outer_radius - self.wall_thickness
        self.inner_diameter = self.inner_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return math.pi * (self.outer_radius**2 - self.inner_radius**2) * self.length

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.length / 2.0

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        Ro, Ri, L = self.outer_radius, self.inner_radius, self.length
        m = self.mass
        return (m / 12.0) * (3.0 * (Ro**2 + Ri**2) + L**2)

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        Ro, Ri = self.outer_radius, self.inner_radius
        return (self.mass / 2.0) * (Ro**2 + Ri**2)

    def y_upper(self, x: Meters) -> Meters:
        return self.outer_radius

    def y_lower(self, x: Meters) -> Meters:
        return self.inner_radius

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class Bulkhead:
    """
    A solid circular plate sitting INSIDE a body tube to compartmentalize
    the rocket — separating bays, anchoring tanks, etc. Treated as an
    inner component (its diameter is the bulkhead's own outer diameter,
    typically equal to the surrounding body tube's inner diameter).

    The plate's axial extent (``thickness``) is also exposed as ``length``
    so the assembly's ``_component_length`` lookup picks it up
    automatically when chaining via tip_of_parent_component.

    Attributes:
        - user defined -
        diameter: Meters
        thickness: Meters             (axial extent of the plate)
        material: Material_Solid

        - automatically calculated -
        radius: Meters
        length: Meters                (= thickness; alias for assembly chaining)
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC
    is_inner: ClassVar[bool] = True

    diameter: Meters
    thickness: Meters
    material: Material_Solid
    name: str = "Bulkhead"
    radius: Meters = field(init=False)
    length: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.radius = self.diameter / 2.0
        self.length = self.thickness

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return math.pi * self.radius**2 * self.thickness

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.thickness / 2.0

    @property
    def I_lateral(self):
        # Solid disc: I = m/12 (3 R² + t²) about a diameter through CG.
        if self._I_lateral is not None:
            return self._I_lateral
        m, R, t = self.mass, self.radius, self.thickness
        return (m / 12.0) * (3.0 * R**2 + t**2)

    @property
    def I_axial(self):
        # Solid disc: I = m/2 R² about its symmetry axis.
        if self._I_axial is not None:
            return self._I_axial
        return self.mass / 2.0 * self.radius**2

    def y_upper(self, x: Meters) -> Meters:
        return self.radius

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class ConicalBoatTail:
    """
    A linear-taper boat tail — a hollow cone frustum with constant
    perpendicular wall thickness. The structural sibling of
    :class:`VonKarmanBoatTail` without the curved contour; cheaper to
    machine and easier to reason about analytically.

    Geometry (top = wide end, bottom = narrow end, exhaust exits the
    bottom):

        |----------\\
        |           \\
        |            \\----
        |     <---- aft

    Attributes:
        - user defined -
        boattail_top_diameter: Meters
        boattail_bottom_diameter: Meters
        boattail_length: Meters
        wall_thickness: Meters
        material: Material_Solid

        - automatically calculated -
        boattail_top_radius: Meters
        boattail_bottom_radius: Meters
        inner_top_radius: Meters
        inner_bottom_radius: Meters
        inner_top_diameter: Meters
        inner_bottom_diameter: Meters
        half_angle_rad: Radians          (taper half-angle from the axis)
        half_angle_deg: Degrees
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    boattail_top_diameter: Meters
    boattail_bottom_diameter: Meters
    boattail_length: Meters
    wall_thickness: Meters
    material: Material_Solid
    name: str = "Conical Boattail"
    boattail_top_radius: Meters = field(init=False)
    boattail_bottom_radius: Meters = field(init=False)
    inner_top_radius: Meters = field(init=False)
    inner_bottom_radius: Meters = field(init=False)
    inner_top_diameter: Meters = field(init=False)
    inner_bottom_diameter: Meters = field(init=False)
    half_angle_rad: Radians = field(init=False)
    half_angle_deg: Degrees = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.boattail_top_radius = self.boattail_top_diameter / 2.0
        self.boattail_bottom_radius = self.boattail_bottom_diameter / 2.0
        self.inner_top_radius = self.boattail_top_radius - self.wall_thickness
        self.inner_top_diameter = self.inner_top_radius * 2.0
        self.inner_bottom_radius = self.boattail_bottom_radius - self.wall_thickness
        self.inner_bottom_diameter = self.inner_bottom_radius * 2.0
        self.half_angle_rad = math.atan(
            (self.boattail_top_radius - self.boattail_bottom_radius)
            / self.boattail_length
        )
        self.half_angle_deg = math.degrees(self.half_angle_rad)

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        vol, _, _, _ = _shell_axisymmetric_props(
            self.y_upper,
            self.y_lower,
            0.0,
            self.boattail_length,
            self.material.density,
        )
        return vol

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        _, cg, _, _ = _shell_axisymmetric_props(
            self.y_upper,
            self.y_lower,
            0.0,
            self.boattail_length,
            self.material.density,
        )
        return cg

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        _, _, I_lat, _ = _shell_axisymmetric_props(
            self.y_upper,
            self.y_lower,
            0.0,
            self.boattail_length,
            self.material.density,
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        _, _, _, I_ax = _shell_axisymmetric_props(
            self.y_upper,
            self.y_lower,
            0.0,
            self.boattail_length,
            self.material.density,
        )
        return I_ax

    def y_upper(self, x: Meters) -> Meters:
        """Outer radius at axial position x from the top (wide) end."""
        t = x / self.boattail_length
        return (
            self.boattail_top_radius
            + (self.boattail_bottom_radius - self.boattail_top_radius) * t
        )

    def y_lower(self, x: Meters) -> Meters:
        """
        Inner radius at axial position x. Constant perpendicular wall
        thickness — radial offset of the inner contour is
        ``wall_thickness * cos(half_angle)``.
        """
        t = x / self.boattail_length
        outer = (
            self.boattail_top_radius
            + (self.boattail_bottom_radius - self.boattail_top_radius) * t
        )
        return max(outer - self.wall_thickness * math.cos(self.half_angle_rad), 0.0)

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class ShockCord:
    """
    Recovery shock cord (rope tying the rocket halves to the parachute
    bridle). Modelled like a parachute's packed bundle — a packed_length
    × packed_radius rectangular profile that revolves into a uniform
    cylinder — but adds the deployed cord length explicitly so the
    propagation / reefing solver knows how much rope is actually paid
    out at separation.

    Attributes:
        - user defined -
        shock_cord_length: Meters       (deployed rope length)
        packed_length: Meters           (axial extent of the packed bundle)
        packed_radius: Meters           (radial extent of the packed bundle)
        material: Material_Solid        (defaults to Nylon)
        name: str

        - automatically calculated -
        packed_diameter: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC
    is_inner: ClassVar[bool] = True

    shock_cord_length: Meters
    packed_length: Meters
    packed_radius: Meters
    material: Material_Solid = field(default_factory=Nylon)
    name: str = "Shock Cord"
    packed_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.packed_diameter = self.packed_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def length(self) -> float:
        """Axial extent (= packed_length) for assembly chaining."""
        return self.packed_length

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return math.pi * self.packed_radius**2 * self.packed_length

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.packed_length / 2.0

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        m, R, L = self.mass, self.packed_radius, self.packed_length
        return (m / 12.0) * (3.0 * R**2 + L**2)

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        return self.mass / 2.0 * self.packed_radius**2

    def y_upper(self, x: Meters) -> Meters:
        return self.packed_radius

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} (packed)"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


@dataclass
class Wing:
    """
    A general trapezoidal wing — same planform as :class:`TrapezoidalFins`
    but parametrized in aerodynamicist terms (sweep, span, root chord,
    tip chord, taper ratio). Cross section is the same wedge–flat–wedge
    as the fins.

    The wing is a wing-typed component — it lives at a specific eta and
    rotates around the rocket x-axis. Use it for canards, control
    surfaces, or aerodynamically-tuned alternative fin sets.

    Attributes:
        - user defined -
        sweep, cant_angle: Degrees
        span: Meters                          (required)
        taper_ratio: float                    (tip_chord / root_chord, required)
        root_chord: Meters                    (at least one of root/tip required;
                                               the other is derived from taper_ratio)
        tip_chord: Meters
        thickness: Meters                     (max thickness through the flat)
        le_wedge_length: Meters               (LE wedge chord-length, default 0)
        te_wedge_length: Meters               (TE wedge chord-length, default 0)
        cross_section: WingCrossSection       (optional; built from wedge/slab
                                               params when omitted)
        material: Material_Solid
        name: str

        - automatically calculated -
        aspect_ratio: float                   (span / avg_chord)
        height: Meters                         (alias = span; used by
                                                Assembly.plot_xy fin renderer)
        planform_area: Meters²
        avg_chord: Meters
    """

    component_type: ClassVar[ComponentType] = ComponentType.WING

    sweep: Degrees
    cant_angle: Degrees
    taper_ratio: float
    material: Material_Solid
    span: Meters | None = None
    root_chord: Meters | None = None
    tip_chord: Meters | None = None
    thickness: Meters = 0.0
    le_wedge_length: Meters = 0.0
    te_wedge_length: Meters = 0.0
    cross_section: WingCrossSection | None = None
    name: str = "Wing"
    aspect_ratio: NonDimensional = field(init=False)
    height: Meters = field(init=False)
    planform_area: Meters = field(init=False)
    avg_chord: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        tr = float(self.taper_ratio)
        # Derive the missing chord from taper_ratio when only one is given.
        if self.root_chord is not None and self.tip_chord is None:
            self.tip_chord = float(self.root_chord) * tr
        elif self.tip_chord is not None and self.root_chord is None:
            self.root_chord = float(self.tip_chord) / tr
        elif self.root_chord is None and self.tip_chord is None:
            raise ValueError(
                f"{self.name}: at least one of root_chord / tip_chord is required."
            )
        if self.span is None:
            raise ValueError(f"{self.name}: span is required.")
        avg_c = (float(self.root_chord) + float(self.tip_chord)) / 2.0
        self.aspect_ratio = float(self.span) / avg_c if avg_c > 0 else 0.0
        self.height = float(self.span)
        A, B, C, D = generate_freeform_fins(
            self.sweep, self.span, self.root_chord, self.tip_chord
        )
        self._sweep_offset = float(D[0])
        self.planform_area = (
            (float(self.root_chord) + float(self.tip_chord)) * float(self.span) / 2.0
        )
        self.avg_chord = avg_c
        self.points = [
            A,
            D,
            C,
            B,
        ]
        if self.cross_section is None:
            if float(self.le_wedge_length) > 0.0 or float(self.te_wedge_length) > 0.0:
                self.cross_section = SupersonicWedgeCrossSection(
                    thickness=float(self.thickness),
                    le_wedge_length=float(self.le_wedge_length),
                    te_wedge_length=float(self.te_wedge_length),
                )
            else:
                self.cross_section = SlabCrossSection(thickness=float(self.thickness))

    # --- override setters ---

    def set_name(self, value: str) -> None:
        self.name = value

    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    # --- planform & cross-section helpers used by the extrusion integrator ---
    def _x_le_at_span(self, y: Meters) -> Meters:
        return self._sweep_offset * y / float(self.span)

    def _x_te_at_span(self, y: Meters) -> Meters:
        return float(self.root_chord) + (
            (self._sweep_offset + float(self.tip_chord) - float(self.root_chord))
            * y
            / float(self.span)
        )

    def cross_section_thickness(self, s: Meters, local_chord: Meters) -> Meters:
        return float(
            self.cross_section.evaluate(
                float(s), float(local_chord), float(self.root_chord)
            )
        )

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        vol, _, _, _, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            float(self.span),
            self.material.density,
        )
        return vol

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        _, cg_x, _, _, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            float(self.span),
            self.material.density,
        )
        return cg_x

    @property
    def cg_span(self) -> Meters:
        _, _, cg_y, _, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            float(self.span),
            self.material.density,
        )
        return cg_y

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        _, _, _, I_lat, _ = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            float(self.span),
            self.material.density,
        )
        return I_lat

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        _, _, _, _, I_ax = _extruded_planform_props(
            self._x_le_at_span,
            self._x_te_at_span,
            self.cross_section_thickness,
            0.0,
            float(self.span),
            self.material.density,
        )
        return I_ax

    def y_upper(self, x: Meters) -> Meters:
        return _upper_y_from_points(self.points, float(x))

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def eta_upper(self, x: Meters, y: Meters) -> Meters:
        if y < 0.0 or y > float(self.span):
            return float("nan")
        x_le = self._x_le_at_span(y)
        x_te = self._x_te_at_span(y)
        if x < x_le or x > x_te:
            return float("nan")
        local_chord = x_te - x_le
        if local_chord <= 0.0:
            return float("nan")
        return self.cross_section_thickness(x - x_le, local_chord) / 2.0

    def eta_lower(self, x: Meters, y: Meters) -> Meters:
        eu = self.eta_upper(x, y)
        return eu if eu != eu else -eu

    def plot(self, x_values, options: dict = None):
        import matplotlib.pyplot as plt

        opts = {
            "show": True,
            "title": f"{self.name} Planform",
            "color": "darkviolet",
        }
        if options:
            opts.update(options)
        color = opts["color"]
        y_vals = [self.y_upper(x) for x in x_values]
        fig, ax = plt.subplots()
        ax.fill_between(x_values, 0, y_vals, color=color, alpha=1)
        px = [p[0] for p in self.points] + [self.points[0][0]]
        py = [p[1] for p in self.points] + [self.points[0][1]]
        ax.plot(px, py, color=color)
        ax.set_aspect("equal")
        ax.set_title(opts["title"])
        ax.set_xlabel("chord (m)")
        ax.set_ylabel("span (m)")
        ax.grid(True)
        if opts["show"]:
            plt.show()
        return fig, ax

    def plot_cross_section(self, span: Meters, ax=None, options: dict = None):
        """
        Plot the cross section at span station ``span`` (measured from
        the root, in [0, span]). Mirrors :meth:`TrapezoidalFins.plot_cross_section`
        but for the wing planform. See that method's docstring for the
        ``options`` keys.
        """
        import matplotlib.pyplot as plt

        if span < 0.0 or span > float(self.span):
            raise ValueError(
                f"{self.name}: span={span:.4f} m outside wing "
                f"(valid range: [0, {float(self.span):.4f} m])"
            )
        opts = {
            "n": 200,
            "show": True,
            "title": f"{self.name} Cross Section",
            "color": "darkviolet",
            "align_le": True,
            "y_offset": 0.0,
            "label": None,
            "alpha": 0.35,
        }
        if options:
            opts.update(options)

        x_le = self._x_le_at_span(span)
        x_te = self._x_te_at_span(span)
        local_chord = x_te - x_le
        if local_chord <= 0:
            raise ValueError(
                f"{self.name}: local chord at span={span:.4f} m is non-positive"
            )

        ss = np.linspace(0.0, local_chord, int(opts["n"]))
        ts = np.array([self.cross_section_thickness(float(s), local_chord) for s in ss])
        xs = ss if opts["align_le"] else ss + x_le
        y_offset = float(opts["y_offset"])
        upper = ts / 2.0 + y_offset
        lower = -ts / 2.0 + y_offset

        standalone = ax is None
        if standalone:
            fig, ax = plt.subplots()
        label = opts["label"] if opts["label"] is not None else f"y = {span:.3f} m"
        ax.fill_between(xs, lower, upper, color=opts["color"], alpha=opts["alpha"])
        ax.plot(xs, upper, color=opts["color"], label=label)
        ax.plot(xs, lower, color=opts["color"])
        if standalone:
            ax.set_aspect("equal")
            ax.set_title(opts["title"])
            ax.set_xlabel(
                "chord position from local LE (m)"
                if opts["align_le"]
                else "chord position from root LE (m)"
            )
            ax.set_ylabel("thickness (m)")
            ax.grid(True)
            ax.legend(loc="best")
            if opts["show"]:
                plt.show()
            return fig, ax
        return ax


@dataclass
class RailButton:
    """
    A small cylindrical protrusion bolted to the body that engages the
    launch rail. Two of these (forward and aft) sit on a single eta
    azimuth and guide the rocket up the rail.

    Geometry — a solid cylinder with axis pointing radially OUTWARD from
    the body:
        chord direction (x):   cylinder footprint diameter (= button_diameter)
        span direction (y):    cylinder height (= button_height)
        eta direction (z):     cylinder cross-section, ranges over
                               ±sqrt((d/2)² − (s − d/2)²) at chord pos s

    The rail button is a PROTRUSION — like a wing it lives at a specific
    eta and rotates around the rocket x-axis, but its eta-direction
    extent is comparable to its chord-direction extent (it is NOT a
    thin plate). The assembly composes its inertia tensor accordingly
    (see ComponentType.PROTRUSION).

    Attributes:
        - user defined -
        button_diameter: Meters         (cylindrical footprint diameter)
        button_height: Meters           (radial protrusion height)
        material: Material_Solid        (defaults to Aluminum)
        name: str

        - automatically calculated -
        button_radius: Meters
        root_chord: Meters              (= button_diameter; for assembly chaining)
        height: Meters                  (= button_height; alias for fin renderer)
    """

    component_type: ClassVar[ComponentType] = ComponentType.PROTRUSION

    button_diameter: Meters
    button_height: Meters
    material: Material_Solid = field(default_factory=Aluminum)
    name: str = "Rail Button"
    button_radius: Meters = field(init=False)
    root_chord: Meters = field(init=False)
    height: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.button_radius = self.button_diameter / 2.0
        self.root_chord = self.button_diameter
        self.height = self.button_height

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        # Solid cylinder: V = π r² h
        if self._volume is not None:
            return self._volume
        return math.pi * self.button_radius**2 * self.button_height

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        # Chord-direction CG: middle of the footprint (button is symmetric).
        if self._cg is not None:
            return self._cg
        return self.button_diameter / 2.0

    @property
    def cg_span(self) -> Meters:
        # Span-direction CG: middle of the cylinder height.
        return self.button_height / 2.0

    @property
    def I_lateral(self):
        # Lateral = about the cylinder's symmetry axis (the radial = span axis).
        # I_y = (1/2) m r²
        if self._I_lateral is not None:
            return self._I_lateral
        m, r = self.mass, self.button_radius
        return 0.5 * m * r**2

    @property
    def I_axial(self):
        # Axial = about a chord-aligned axis through the CG.
        # For a cylinder of radius r and height h with axis along y:
        #   I_x = (1/12) m (3 r² + h²)
        if self._I_axial is not None:
            return self._I_axial
        m, r, h = self.mass, self.button_radius, self.button_height
        return (m / 12.0) * (3.0 * r**2 + h**2)

    # --- planform queries (used by Assembly's wing-style plotting) ---
    def y_upper(self, x: Meters) -> Meters:
        """Span (radial) extent at chord position x. Constant = button_height
        across the full footprint, 0 outside [0, button_diameter]."""
        if x < 0.0 or x > self.button_diameter:
            return 0.0
        return self.button_height

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def eta_upper(self, x: Meters, y: Meters) -> Meters:
        """Eta extent at footprint position x and span y. Inside the
        cylinder this is the chord that cuts the circular footprint at
        chord offset (x − r) from the center: ±sqrt(r² − (x − r)²).
        Returns NaN outside the cylinder's footprint or span."""
        if y < 0.0 or y > self.button_height:
            return float("nan")
        if x < 0.0 or x > self.button_diameter:
            return float("nan")
        r = self.button_radius
        d2 = r**2 - (x - r) ** 2
        if d2 < 0.0:
            return float("nan")
        return math.sqrt(d2)

    def eta_lower(self, x: Meters, y: Meters) -> Meters:
        eu = self.eta_upper(x, y)
        return eu if eu != eu else -eu

    def plot(self, x_values, options: dict = None):
        import matplotlib.pyplot as plt

        opts = {
            "show": True,
            "title": f"{self.name} (footprint)",
            "color": "tab:olive",
        }
        if options:
            opts.update(options)
        # draw the circular footprint in the (chord, eta) plane
        n = 200
        thetas = np.linspace(0.0, 2.0 * np.pi, n)
        r = self.button_radius
        xs = r + r * np.cos(thetas)
        es = r * np.sin(thetas)
        fig, ax = plt.subplots()
        ax.fill(xs, es, color=opts["color"], alpha=0.5)
        ax.plot(xs, es, color=opts["color"])
        ax.set_aspect("equal")
        ax.set_title(opts["title"])
        ax.set_xlabel("chord (m)")
        ax.set_ylabel("eta (m)")
        ax.grid(True)
        if opts["show"]:
            plt.show()
        return fig, ax


@dataclass
class LaunchRail:
    """
    8020components.com-style extruded aluminium launch rail.

    The rail's cross-section is non-axisymmetric (T-slot extrusion); the user
    therefore supplies a packed_volume and a packed_length × packed_radius
    rectangle for the 2-D profile, in the same spirit as the parachute classes.

    rail_length      = 5.10
    rail_inclination = 84.0
    rail_heading     = 90.0
    """

    component_type: ClassVar[ComponentType] = ComponentType.AXISYMMETRIC

    rail_length: Meters
    packed_volume: Volume  # actual material volume (handles the T-slot voids)
    packed_radius: Meters  # rectangle profile half-width (for plotting)
    material: Material_Solid = field(default_factory=Aluminum)
    rail_inclination: Degrees = field(default=90.0)
    rail_heading: Degrees = field(default=90.0)
    name: str = "Launch Rail"
    packed_diameter: Meters = field(init=False)
    _volume: float | None = field(default=None, init=False, repr=False)
    _mass: float | None = field(default=None, init=False, repr=False)
    _cg: float | None = field(default=None, init=False, repr=False)
    _I_lateral: float | None = field(default=None, init=False, repr=False)
    _I_axial: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.packed_diameter = self.packed_radius * 2.0

    # --- override setters ---
    def set_volume(self, value: float | None) -> None:
        self._volume = value

    def set_mass(self, value: float | None) -> None:
        self._mass = value

    def set_cg(self, value: float | None) -> None:
        self._cg = value

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral = value

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial = value

    @property
    def volume(self):
        if self._volume is not None:
            return self._volume
        return float(self.packed_volume)

    @property
    def mass(self):
        if self._mass is not None:
            return self._mass
        return self.material.density * self.volume

    @property
    def cg(self):
        if self._cg is not None:
            return self._cg
        return self.rail_length / 2.0

    @property
    def I_lateral(self):
        if self._I_lateral is not None:
            return self._I_lateral
        m, R, L = self.mass, self.packed_radius, self.rail_length
        return (m / 12.0) * (3.0 * R**2 + L**2)

    @property
    def I_axial(self):
        if self._I_axial is not None:
            return self._I_axial
        return self.mass / 2.0 * self.packed_radius**2

    def y_upper(self, x: Meters) -> Meters:
        return self.packed_radius

    def y_lower(self, x: Meters) -> Meters:
        return 0.0

    def plot(self, x_values, options: dict = None):
        from archive.plotting.simple_matplotlib import simple_2d_component_plot

        opts = {"show": True, "title": f"{self.name} Profile"}
        if options:
            opts.update(options)
        return simple_2d_component_plot(x_values, self.y_upper, self.y_lower, opts)


if __name__ == "__main__":
    import numpy as np
    from cad_1d.materials import Aluminum, Nylon, Steel

    al = Aluminum()

    def _report(comp, x_extent: float, title: str | None = None):
        """Print common mass-properties and plot the 2-D profile."""
        print(f"\n--- {comp.name} ---")
        print(f"  volume     = {comp.volume:.6e} m^3")
        print(f"  mass       = {comp.mass:.6f} kg")
        print(f"  cg         = {comp.cg:.6f} m")
        print(f"  I_lateral  = {comp.I_lateral:.6e} kg.m^2")
        print(f"  I_axial    = {comp.I_axial:.6e} kg.m^2")
        xs = np.linspace(0.0, x_extent, 300)
        comp.plot(xs, options={"title": title or comp.name})

    # --- DivergingConicalNozzle (graphite billet, single frustum void) ---
    div_nozzle = DivergingConicalNozzle(
        throat_diameter=0.04,
        outer_diameter=0.12,
        cone_length=0.10,
        diverging_angle_deg=15.0,
        material=al,
    )
    print(
        f"[DivergingConicalNozzle] throat_d={div_nozzle.throat_diameter:.4f}  "
        f"exit_d={div_nozzle.exit_diameter:.4f}  "
        f"outer_d={div_nozzle.outer_diameter:.4f}  "
        f"slant={div_nozzle.slant_length:.4f}  eps={div_nozzle.eps:.3f}"
    )
    _report(div_nozzle, div_nozzle.cone_length, "Diverging Conical Nozzle")

    # --- ConvergingDivergingConicalNozzle (de Laval, two frustum voids) ---
    cd_nozzle = ConvergingDivergingConicalNozzle(
        chamber_diameter=0.10,
        throat_diameter=0.04,
        outer_diameter=0.12,
        converging_length=0.05,
        diverging_length=0.10,
        diverging_angle_deg=15.0,
        material=al,
    )
    print(
        f"[ConvergingDivergingConicalNozzle] "
        f"chamber_d={cd_nozzle.chamber_diameter:.4f}  "
        f"throat_d={cd_nozzle.throat_diameter:.4f}  "
        f"exit_d={cd_nozzle.exit_diameter:.4f}  "
        f"outer_d={cd_nozzle.outer_diameter:.4f}  "
        f"L_conv={cd_nozzle.converging_length:.4f}  "
        f"L_div={cd_nozzle.diverging_length:.4f}  "
        f"conv_angle_deg={cd_nozzle.converging_angle_deg:.2f}  "
        f"eps={cd_nozzle.eps:.3f}"
    )
    _report(cd_nozzle, cd_nozzle.total_length, "Converging-Diverging Conical Nozzle")

    # --- HybridFuelGrain ---
    grain = HybridFuelGrain(
        grain_outer_diameter=0.09525,
        grain_inner_diameter=0.04,
        grain_length=0.438,
        infill_density=95,
    )
    print(
        f"[HybridFuelGrain] outer_d={grain.grain_outer_diameter:.4f}  "
        f"inner_d={grain.grain_inner_diameter:.4f}  "
        f"infill={grain.infill_factor:.3f}  "
        f"rho_eff={grain.effective_density:.1f}"
    )
    _report(grain, grain.grain_length, "Hybrid Fuel Grain")

    # --- CylindricalTank ---
    tank = CylindricalTank(
        inner_diameter=0.15,
        length=0.60,
        wall_thickness=0.003,
        material=al,
    )
    print(
        f"[CylindricalTank] inner_d={tank.inner_diameter:.4f}  "
        f"outer_d={tank.outer_diameter:.4f}  L={tank.length:.4f}"
    )
    _report(tank, tank.length, "Cylindrical Tank (flat caps)")

    # --- CappedCylindricalTank ---
    capped = CappedCylindricalTank(
        inner_diameter=0.15,
        length=0.60,
        wall_thickness=0.003,
        material=al,
    )
    print(
        f"[CappedCylindricalTank] inner_d={capped.inner_diameter:.4f}  "
        f"outer_d={capped.outer_diameter:.4f}  L={capped.length:.4f}  "
        f"total_L={capped.total_length:.4f}"
    )
    _report(capped, capped.total_length, "Capped Cylindrical Tank (hemi caps)")

    # --- ConicalNoseCone ---
    cnose = ConicalNoseCone(
        length=0.30,
        base_radius=0.08,
        material=al,
    )
    print(
        f"[ConicalNoseCone] L={cnose.length:.4f}  "
        f"base_d={cnose.base_diameter:.4f}  "
        f"half_angle_deg={cnose.half_angle_deg:.2f}  "
        f"slant={cnose.slant_length:.4f}"
    )
    _report(cnose, cnose.length, "Conical Nose Cone")

    # --- OgiveNoseCone ---
    ogive = OgiveNoseCone(
        length=0.30,
        base_radius=0.08,
        wall_thickness=0.003,
        material=al,
    )
    print(
        f"[OgiveNoseCone] L={ogive.length:.4f}  base_d={ogive.base_diameter:.4f}  "
        f"inner_d={ogive.inner_diameter:.4f}  "
        f"ogive_d={ogive.ogive_diameter:.4f}  "
        f"inner_ogive_d={ogive.inner_ogive_diameter:.4f}"
    )
    _report(ogive, ogive.length, "Ogive Nose Cone")

    # --- VonKarmanNoseCone ---
    vknose = VonKarmanNoseCone(
        length=0.30,
        base_radius=0.08,
        wall_thickness=0.003,
        material=al,
    )
    print(
        f"[VonKarmanNoseCone] L={vknose.length:.4f}  "
        f"base_d={vknose.base_diameter:.4f}  inner_d={vknose.inner_diameter:.4f}"
    )
    _report(vknose, vknose.length, "Von Karman Nose Cone")

    # --- LVHaackNoseCone ---
    lvh = LVHaackNoseCone(
        length=0.30,
        base_radius=0.08,
        wall_thickness=0.003,
        material=al,
    )
    print(
        f"[LVHaackNoseCone] L={lvh.length:.4f}  "
        f"base_d={lvh.base_diameter:.4f}  inner_d={lvh.inner_diameter:.4f}"
    )
    _report(lvh, lvh.length, "LV-Haack Nose Cone")

    # --- BodyTube ---
    tube = BodyTube(
        outer_diameter=0.16,
        length=1.20,
        wall_thickness=0.003,
        material=al,
    )
    print(
        f"[BodyTube] outer_d={tube.outer_diameter:.4f}  "
        f"inner_d={tube.inner_diameter:.4f}  L={tube.length:.4f}"
    )
    _report(tube, tube.length, "Body Tube")

    # --- TrapezoidalFins (rectangular slab cross section: both wedge_lengths = 0) ---
    fins_slab = TrapezoidalFins(
        sweep=30,
        height=0.17,
        root_chord=0.37,
        tip_chord=0.2,
        cant_angle=0,
        thickness=0.005,
        material=al,
        name="Trapezoidal Fins (slab)",
    )
    print(
        f"[TrapezoidalFins slab] root={fins_slab.root_chord:.4f}  "
        f"tip={fins_slab.tip_chord:.4f}  h={fins_slab.height:.4f}  "
        f"thickness={fins_slab.thickness:.4f}  area={fins_slab.planform_area:.5f}"
    )
    _report(fins_slab, fins_slab.root_chord, "Trapezoidal Fins (slab)")

    # --- TrapezoidalFins with <==> wedge-flat-wedge cross section ---
    fins_wedge = TrapezoidalFins(
        sweep=30,
        height=0.17,
        root_chord=0.37,
        tip_chord=0.2,
        cant_angle=0,
        thickness=0.005,
        le_wedge_length=0.05,
        te_wedge_length=0.04,
        material=al,
        name="Trapezoidal Fins (wedge)",
    )
    print(
        f"[TrapezoidalFins wedge] thickness={fins_wedge.thickness:.4f}  "
        f"le_wedge={fins_wedge.le_wedge_length:.4f}  "
        f"te_wedge={fins_wedge.te_wedge_length:.4f}  "
        f"area={fins_wedge.planform_area:.5f}"
    )
    _report(fins_wedge, fins_wedge.root_chord, "Trapezoidal Fins (<==> wedge)")

    # --- stack wedge fin cross sections at their physical span positions ---
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    spans = np.linspace(0.0, fins_wedge.height, 5)
    for sp in spans:
        fins_wedge.plot_cross_section(
            sp,
            ax=ax,
            options={
                "label": f"y = {sp * 1000:.0f} mm",
                "align_le": True,
                "y_offset": sp,
            },
        )
    ax.set_aspect("equal")
    ax.set_title(f"{fins_wedge.name}: cross sections stacked by span")
    ax.set_xlabel("chord position from local LE (m)")
    ax.set_ylabel("span position (m)")
    ax.grid(True)
    ax.legend(loc="best")
    plt.show()

    # --- VonKarmanBoatTail ---
    bt = VonKarmanBoatTail(
        boattail_bottom_diameter=0.12246,
        boattail_top_diameter=0.16,
        boattail_length=0.35,
        wall_thickness=0.003,
        material=al,
    )
    print(
        f"[VonKarmanBoatTail] top_d={bt.boattail_top_diameter:.4f}  "
        f"bottom_d={bt.boattail_bottom_diameter:.4f}  L={bt.boattail_length:.4f}  "
        f"inner_top_d={bt.inner_top_diameter:.4f}  "
        f"inner_bottom_d={bt.inner_bottom_diameter:.4f}"
    )
    _report(bt, bt.boattail_length, "Von Karman Boattail")

    # --- DrogueParachute (box profile = packed volume) ---
    drogue = DrogueParachute(
        parachute_radius=0.38,
        cd=0.836,
        packed_length=0.20,
        packed_radius=0.05,
    )
    print(
        f"[DrogueParachute] canopy_d={drogue.parachute_diameter:.4f}  "
        f"packed_L={drogue.packed_length:.4f}  "
        f"packed_d={drogue.packed_diameter:.4f}"
    )
    _report(drogue, drogue.packed_length, "Drogue Parachute (packed)")

    # --- MainParachute (box profile = packed volume) ---
    main_chute = MainParachute(
        trigger=396.24,
        parachute_radius=1.5,
        cd=3.3,
        packed_length=0.30,
        packed_radius=0.07,
    )
    print(
        f"[MainParachute] canopy_d={main_chute.parachute_diameter:.4f}  "
        f"packed_L={main_chute.packed_length:.4f}  "
        f"packed_d={main_chute.packed_diameter:.4f}  "
        f"trigger_alt={main_chute.trigger:.2f}"
    )
    _report(main_chute, main_chute.packed_length, "Main Parachute (packed)")

    # --- LaunchRail ---
    rail = LaunchRail(
        rail_length=5.10,
        packed_volume=0.0015,
        packed_radius=0.04,
    )
    print(
        f"[LaunchRail] L={rail.rail_length:.4f}  "
        f"packed_d={rail.packed_diameter:.4f}  "
        f"incl={rail.rail_inclination:.1f}  heading={rail.rail_heading:.1f}"
    )
    _report(rail, rail.rail_length, "Launch Rail")
