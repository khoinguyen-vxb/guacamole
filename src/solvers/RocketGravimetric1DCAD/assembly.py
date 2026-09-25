"""
Assembly of rocket components in the (x, y, eta) frame.

There are TWO frames in play here. They share names but mean different
things; the plotter and the placement API talk to different ones.

PLACEMENT FRAME — inputs to ``Assembly.add()``
----------------------------------------------
    x    axial position along the rocket (nose to tail), m.
    y    radial offset from the local body surface, m. Positive is
         outward; negative embeds the component into the wall (e.g. a
         fin root sitting -slot_depth inside the boat tail). 0 is flush.
         For axisymmetric components y is meaningless and conventionally
         left at 0.
    eta  arc-length around the body circumference, m. Period is
         2 * pi * r_ref where r_ref is ``Assembly.reference_radius``,
         held CONSTANT across the assembly so a fin's angular station
         stays fixed even where the body tapers under it. Four fins
         equally spaced around the body take eta_k = k * (2*pi*r_ref)/N.

SLICING FRAME — inputs to ``plot_xy(eta)`` and ``plot_xn(y)``
-------------------------------------------------------------
``plot_xy(eta_slice)``  renders the (x, y) cross section at azimuth
                        ``eta_slice`` in the placement frame.
``plot_xn(y_slice)``    renders the (x, eta) "unrolled" cross section
                        at radial layer ``y_slice``, where ``y_slice``
                        is CENTERLINE-RADIAL — measured from the rocket
                        axis, NOT from the local body surface.

The same axis convention is used by both plots: the y axis on the page
is centerline-radial in plot_xy, and the y argument of plot_xn is the
slice level on that same axis. So:
    y_slice = 0                rocket centerline (always empty)
    y_slice = body_outer_r     the outer skin
    y_slice in [inner_r, outer_r]   inside the wall of an axisymmetric
                                    component at all x where it covers
The placement-frame y (offset from surface) is converted internally
when needed: r_centerline = body_radius_at(p.x) + p.y.

GEOMETRY PRIMITIVES — what the plotter asks each component for
--------------------------------------------------------------
Axisymmetric components (body tubes, nose cones, boat tails, ...):
    y_upper(x), y_lower(x)   outer and inner radii at axial position x
                             in centerline-radial coords. The wall fills
                             [y_lower(x), y_upper(x)] independent of eta.
    Slicing implication for plot_xn(y_slice):
      * if y_lower(x) <= y_slice <= y_upper(x) the wall fills the entire
        eta band [0, 2*pi*r_ref] at this x;
      * otherwise nothing at this x.
    For shapes whose cross section varies with x (boat tail, nose cone)
    the y_slice may fall in the wall over only a narrow range of x —
    the unrolled view shows a thin strip there, not a full-length
    rectangle.

Wing components (TrapezoidalFins):
    eta_upper(x, y), eta_lower(x, y)   eta thickness extent (offset
                             from the fin's own eta centerline) at
                             fin-local chord x and span y. Returns
                             ±thickness(x at span y) / 2 inside the
                             planform; NaN outside.
    For the wedge-flat-wedge cross section the strip narrows toward
    the LE/TE wedges and is full-thickness in the flat region.
    (y_upper(x, eta) / y_lower(x, eta) — span extent at a thickness
     slice — are the dual queries needed by plot_xy. Not yet
     implemented; plot_xy still uses the thin-slice eta_tol shortcut.)

PLOT_XN COMPOSITION
-------------------
For each placement at (p.x, p.y, p.eta):
  axisymmetric: scan x_local in [0, length], evaluate y_lower / y_upper,
    mask where y_slice is in the local wall, fill the strip [0, period]
    across those x.
  wing: y_span = y_slice - (body_radius_at(p.x) + p.y); skip if y_span
    is outside [0, height]. Otherwise scan x_local, query
    eta_lower(x_local, y_span) / eta_upper(x_local, y_span), and fill
    the strip [p.eta + eta_lower, p.eta + eta_upper] modulo
    period = 2*pi*r_ref. The strip is split at the seam (eta=0 and
    eta=period) when it wraps — so a fin at p.eta=0 renders as two
    strips, one near 0 and one near period, instead of one strip
    straddling negative eta off the unrolled strip.

MASS PROPERTIES
---------------
Mass, CG, and inertias are computed by component build-up. Each
placement is mapped from xyn -> cylindrical -> xyz so the assembly
inertias compose in real Cartesian space (parallel-axis theorem on
3x3 tensors). A symmetric layout — body on centerline, N equally
spaced fins — produces cg_xyz = (X_cg, 0, 0) and I_yy = I_zz; any
drift flags an asymmetric layout.

Axisymmetric placements have a diagonal local inertia
diag(I_axial, I_lateral, I_lateral); their tensor in xyz is the same
(their symmetry axis already coincides with the rocket x-axis).

Fin placements have local frame (chord = x, span = y, thickness = z)
with diagonal local inertia diag(I_axial, I_lateral, I_axial +
I_lateral) — the third entry is the perpendicular-axis approximation
for a thin plate. The fin is then rotated by theta = eta / r_ref
around the rocket x-axis to align its span with the radial direction
in xyz.
"""

import math
from dataclasses import dataclass

import numpy as np

from .CAD_variables import ComponentType, ReferenceFrame
from .frames_of_refrence import xyn_to_xyz


def _component_length(comp) -> float:
    for attr in (
        "total_length",
        "boattail_length",
        "grain_length",
        "cone_length",
        "diverging_length",
        "root_chord",
        "length",
        "packed_length",
        "rail_length",
    ):
        if hasattr(comp, attr):
            return float(getattr(comp, attr))
    raise AttributeError(f"Cannot determine length of {type(comp).__name__}")


def _is_axisymmetric(comp) -> bool:
    """
    True if a component is axisymmetric in the rocket frame (mass distributed
    uniformly over the circumference). Decided by the component's
    `component_type` ClassVar; new directional kinds (vanes, lugs, off-axis
    payloads) just declare ComponentType.WING (or a future enum value) to
    opt out without touching this file.
    """
    return (
        getattr(comp, "component_type", ComponentType.AXISYMMETRIC)
        == ComponentType.AXISYMMETRIC
    )


def _is_protrusion(comp) -> bool:
    """True if the component is a PROTRUSION (rail button, lug, etc.)."""
    return (
        getattr(comp, "component_type", ComponentType.AXISYMMETRIC)
        == ComponentType.PROTRUSION
    )


def _parallel_axis(I_at_cm: np.ndarray, mass: float, d: np.ndarray) -> np.ndarray:
    """
    3D parallel-axis theorem.
    Given an inertia tensor `I_at_cm` about a body's CM and a displacement
    vector `d` from the CM to some other point P, returns the inertia
    tensor about P:
        I_P = I_cm + m * (|d|^2 * I_3 - d (x) d)
    """
    return I_at_cm + mass * (float(d @ d) * np.eye(3) - np.outer(d, d))


def _rotation_about_x(theta: float) -> np.ndarray:
    """3x3 rotation by `theta` (rad) around the rocket axial (x) axis."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


@dataclass
class Placement:
    """A component placed in an assembly with its (x, y, eta) offsets (m)."""

    component: object
    x: float = 0.0
    y: float = 0.0
    eta: float = 0.0


@dataclass
class _Item:
    """An entry in an assembly's unified item list."""

    component: object
    x: float = 0.0
    y: float = 0.0
    eta: float = 0.0
    is_sub_asm: bool = False
    uses_tip_ref: bool = False
    explicit_frame: bool = False


class Assembly:
    """An ordered (tip-to-tail) list of components in the (x, y, eta) frame."""

    def __init__(self, name: str):
        self.name = name
        self._items: list[_Item] = []
        self._mass_override: float | None = None
        self._cg_override: float | None = None
        self._I_lateral_override: float | None = None
        self._I_axial_override: float | None = None

    @property
    def placements(self) -> list[Placement]:
        """Direct component placements (backward compat)."""
        return [
            Placement(component=i.component, x=i.x, y=i.y, eta=i.eta)
            for i in self._items
            if not i.is_sub_asm
        ]

    @property
    def _sub_assemblies(self) -> list[tuple]:
        """Sub-assembly tuples (backward compat)."""
        return [(i.component, i.x, i.y, i.eta) for i in self._items if i.is_sub_asm]

    def _all_placements(self) -> list[Placement]:
        """Return all placements in order, expanding sub-assemblies."""
        result: list[Placement] = []
        for item in self._items:
            if not item.is_sub_asm:
                result.append(
                    Placement(
                        component=item.component, x=item.x, y=item.y, eta=item.eta
                    )
                )
            else:
                sub_asm = item.component
                x_off, y_off, eta_off = item.x, item.y, item.eta
                sub_parent = sub_asm._get_parent()
                sub_parent_x = sub_parent.x if sub_parent else 0.0
                for sub_p in sub_asm._all_placements():
                    if not hasattr(sub_p, "assembly_name"):
                        sub_p.assembly_name = sub_asm.name
                    new_p = Placement(
                        component=sub_p.component,
                        x=x_off + (sub_p.x - sub_parent_x),
                        y=sub_p.y + y_off,
                        eta=sub_p.eta + eta_off,
                    )
                    new_p.assembly_name = sub_p.assembly_name
                    result.append(new_p)
        return result

    def _get_parent(self) -> Placement | None:
        """Return the first component, searching sub-assemblies if needed."""
        for item in self._items:
            if not item.is_sub_asm:
                return Placement(
                    component=item.component, x=item.x, y=item.y, eta=item.eta
                )
            parent = item.component._get_parent()
            if parent is not None:
                return parent
        return None

    def _get_last_parent(self) -> tuple[float, Placement] | None:
        """Return (x_offset, parent) of the last item in the list."""
        if not self._items:
            return None
        last = self._items[-1]
        if not last.is_sub_asm:
            return (
                last.x,
                Placement(component=last.component, x=last.x, y=last.y, eta=last.eta),
            )
        parent = last.component._get_parent()
        if parent is None:
            return None
        return (last.x, parent)

    def add(
        self,
        component,
        position_x: float = 0.0,
        position_y: float = 0.0,
        position_eta: float = 0.0,
        reference_frame: ReferenceFrame | str | None = None,
    ) -> None:
        """
        Append a component or sub-assembly to the assembly.

        All items are stored in a single ordered list.

        If *reference_frame* is not given (the default), the item stacks
        sequentially after the last parent using BOTTOM positioning.
        If *reference_frame* is explicitly given, the item measures from
        the assembly's parent component (TIP or BOTTOM).
        """
        explicit_frame = reference_frame is not None
        if reference_frame is None:
            if _is_axisymmetric(component) or isinstance(component, Assembly):
                reference_frame = ReferenceFrame.BOTTOM_OF_PARENT_COMPONENT
            else:
                reference_frame = ReferenceFrame.NOSE_TO_TAIL
        reference_frame = ReferenceFrame.from_value(reference_frame)

        is_sub_asm = isinstance(component, Assembly)

        parent = self._get_parent()
        if reference_frame is ReferenceFrame.NOSE_TO_TAIL:
            x = position_x
        elif not explicit_frame:
            # Default: sequential stacking after the last parent.
            last = self._get_last_parent()
            if last is not None:
                last_x, last_parent = last
                x = last_x + _component_length(last_parent.component) + position_x
            elif parent is not None:
                x = parent.x + position_x
            else:
                x = position_x
        elif reference_frame is ReferenceFrame.TIP_OF_PARENT_COMPONENT and parent is not None:
            x = parent.x + position_x
        elif reference_frame is ReferenceFrame.BOTTOM_OF_PARENT_COMPONENT and parent is not None:
            x = parent.x + _component_length(parent.component) + position_x
        else:
            x = position_x

        self._items.append(
            _Item(
                component=component,
                x=x,
                y=position_y,
                eta=position_eta,
                is_sub_asm=is_sub_asm,
                explicit_frame=explicit_frame,
                uses_tip_ref=(
                    explicit_frame
                    and not is_sub_asm
                    and reference_frame is ReferenceFrame.TIP_OF_PARENT_COMPONENT
                ),
            )
        )

    @property
    def components(self) -> list:
        """Component objects in placement order (offsets stripped)."""
        return [p.component for p in self._all_placements()]

    @property
    def total_length(self) -> float:
        """Distance from the assembly's x = 0 to the aft-most placement's tail."""
        all_placements = self._all_placements()
        if not all_placements:
            return 0.0
        return max(p.x + _component_length(p.component) for p in all_placements)

    @property
    def reference_radius(self) -> float:
        """
        Reference body radius used to map eta -> theta (eta = theta * r_ref)
        across the whole assembly. Defined as the max outer radius of any
        axisymmetric placement, sampled at five equispaced chord stations.
        For a typical rocket this is the body-tube radius.

        Anchoring eta to a single radius — rather than the local r_body —
        keeps a fin's angular station fixed even where the body tapers
        under it (boat tail, transition), and makes the unrolled x-eta
        plot a uniform rectangle instead of curving with the taper.
        """
        r_max = 0.0
        for p in self._all_placements():
            comp = p.component
            if not _is_axisymmetric(comp):
                continue
            if not hasattr(comp, "y_upper"):
                continue
            comp_len = _component_length(comp)
            for f in (0.0, 0.25, 0.5, 0.75, 1.0):
                try:
                    r = float(comp.y_upper(f * comp_len))
                except Exception:
                    continue
                if r > r_max:
                    r_max = r
        return r_max

    # -----------------------------------------------------------------
    # Body-radius lookup (for fin eta -> theta conversion)
    # -----------------------------------------------------------------

    def _body_radius_at(self, x_global: float) -> float:
        """
        Outer body radius at a global x position, taken from the nearest
        axisymmetric placement that covers that x. Falls back to the aft
        end of the most-recent body in front of x_global if no body
        spans x_global directly. Returns 0.0 if no body components exist
        at all.
        """
        candidates = [
            p
            for p in self._all_placements()
            if _is_axisymmetric(p.component) and hasattr(p.component, "y_upper")
        ]
        for p in candidates:
            comp_len = _component_length(p.component)
            x_local = x_global - p.x
            if 0.0 <= x_local <= comp_len:
                return float(p.component.y_upper(x_local))
        for p in reversed(candidates):
            comp_len = _component_length(p.component)
            if p.x + comp_len <= x_global:
                return float(p.component.y_upper(comp_len))
        return 0.0

    # -----------------------------------------------------------------
    # Per-placement helpers (CG and inertia tensor in global xyz)
    # -----------------------------------------------------------------

    def _placement_cg_xyz(self, p: Placement) -> np.ndarray:
        """Global (X, Y, Z) position of a placement's CG (m)."""
        comp = p.component
        if _is_axisymmetric(comp):
            return np.array([p.x + float(comp.cg), 0.0, 0.0])
        # Fin: chord_cg adds along x; span_cg sits at radial r above the
        # body surface; theta is set by eta and the reference radius
        # (NOT the local body radius — see Assembly.reference_radius).
        # The fin's root sits at the body radius taken at the fin's
        # leading edge (a single value), so the root edge is a straight
        # line along the chord — a rigid plate, not following the taper.
        r_body = self._body_radius_at(p.x)
        r_ref = self.reference_radius
        x_cg = p.x + float(comp.cg)
        y_total = p.y + float(comp.cg_span)
        _, Y, Z = xyn_to_xyz(x_cg, y_total, p.eta, r_body, r_ref=r_ref)
        return np.array([x_cg, Y, Z])

    def _placement_inertia_at_self_cg_xyz(self, p: Placement) -> np.ndarray:
        """3x3 inertia tensor of a placement, in xyz, about its OWN CG."""
        comp = p.component
        I_axial = float(comp.I_axial)
        I_lateral = float(comp.I_lateral)
        if _is_axisymmetric(comp):
            return np.diag([I_axial, I_lateral, I_lateral])
        # Directional component (wing or protrusion) local frame:
        #   x = chord, y = span, z = thickness/eta.
        # I_xx = about chord (= comp.I_axial)
        # I_yy = about span  (= comp.I_lateral)
        # I_zz depends on the geometry kind:
        #   WING (thin plate): I_zz ~= I_xx + I_yy by the perpendicular-axis
        #     theorem.
        #   PROTRUSION (thick — e.g. a rail-button cylinder lying on its
        #     side): I_zz == I_xx by the cylinder's symmetry; the thin-
        #     plate approximation does NOT apply.
        if _is_protrusion(comp):
            I_local = np.diag([I_axial, I_lateral, I_axial])
        else:
            I_local = np.diag([I_axial, I_lateral, I_axial + I_lateral])
        # Rotate around the rocket x-axis so the local span aligns with
        # the radial direction at angle theta = eta / r_ref. Using the
        # reference radius keeps the component's angular station fixed
        # even if the body tapers under it.
        r_ref = self.reference_radius
        theta = p.eta / r_ref if r_ref > 0.0 else 0.0
        R = _rotation_about_x(theta)
        return R @ I_local @ R.T

    # -----------------------------------------------------------------
    # Public mass / CG / inertia
    # -----------------------------------------------------------------

    def set_mass(self, value: float | None) -> None:
        self._mass_override = None if value is None else float(value)

    def set_cg(self, value: float | None) -> None:
        self._cg_override = None if value is None else float(value)

    def set_I_lateral(self, value: float | None) -> None:
        self._I_lateral_override = None if value is None else float(value)

    def set_I_axial(self, value: float | None) -> None:
        self._I_axial_override = None if value is None else float(value)

    @property
    def mass(self) -> float:
        """Total mass (kg)."""
        if self._mass_override is not None:
            return self._mass_override
        return sum(
            float(p.component.mass)
            for p in self._all_placements()
            if hasattr(p.component, "mass")
        )

    @property
    def cg_xyz(self) -> tuple[float, float, float]:
        """
        Component-build-up CG in global xyz (m).
        For an axisymmetric rocket with a symmetric fin layout, the Y and
        Z components should be ~0 by construction; non-zero values flag
        an asymmetric layout.
        """
        M = self.mass
        if M == 0.0:
            return (0.0, 0.0, 0.0)
        weighted = np.zeros(3)
        for p in self._all_placements():
            comp = p.component
            if not (hasattr(comp, "mass") and hasattr(comp, "cg")):
                continue
            weighted += float(comp.mass) * self._placement_cg_xyz(p)
        cg = weighted / M
        return (float(cg[0]), float(cg[1]), float(cg[2]))

    @property
    def cg(self) -> float:
        """Axial CG (m, from assembly x = 0). Convenience scalar = cg_xyz[0]."""
        if self._cg_override is not None:
            return self._cg_override
        return self.cg_xyz[0]

    @property
    def inertia_xyz(self) -> tuple[float, float, float]:
        """
        Diagonal of the assembly inertia tensor (kg.m^2), about the
        assembly CG, in global xyz: (I_xx, I_yy, I_zz). For an axisymmetric
        rocket I_yy and I_zz should match closely; a noticeable split
        flags an asymmetric mass distribution.
        """
        cg = np.array(self.cg_xyz)
        I_total = np.zeros((3, 3))
        for p in self._all_placements():
            comp = p.component
            if not (
                hasattr(comp, "mass")
                and hasattr(comp, "cg")
                and hasattr(comp, "I_axial")
                and hasattr(comp, "I_lateral")
            ):
                continue
            I_self = self._placement_inertia_at_self_cg_xyz(p)
            comp_cg = self._placement_cg_xyz(p)
            d = cg - comp_cg
            I_total += _parallel_axis(I_self, float(comp.mass), d)
        return (float(I_total[0, 0]), float(I_total[1, 1]), float(I_total[2, 2]))

    @property
    def I_axial(self) -> float:
        """Roll inertia (kg.m^2) about the rocket x-axis through the CG."""
        if self._I_axial_override is not None:
            return self._I_axial_override
        return self.inertia_xyz[0]

    @property
    def I_lateral(self) -> float:
        """
        Pitch / yaw inertia (kg.m^2) about a transverse axis through the CG.
        Reported as the average of I_yy and I_zz; for an axisymmetric
        rocket they should already be equal.
        """
        if self._I_lateral_override is not None:
            return self._I_lateral_override
        _, Iyy, Izz = self.inertia_xyz
        return 0.5 * (Iyy + Izz)

    # -----------------------------------------------------------------
    # Tree printing
    # -----------------------------------------------------------------

    def print_tree(self, *, _root: bool = True):
        """Print the assembly tree with ASCII art."""
        if _root:
            print(self.name)
        else:
            parent_name = self._parent_component_name() or "?"
            print(f"{self.name} (parent: {parent_name})")
        self._print_tree_inner("", is_root=_root)

    def _parent_component_name(self) -> str | None:
        parent = self._get_parent()
        if parent is None:
            return None
        return getattr(parent.component, "name", type(parent.component).__name__)

    @staticmethod
    def _fmt_offset(x: float) -> str:
        s = f"{x:.3f}".rstrip("0").rstrip(".")
        return f"+{s}" if not s.startswith("-") and not s.startswith("+") else s

    def _print_tree_inner(
        self, prefix: str, *, is_root: bool = False, parent_name: str | None = None
    ):
        # Find the first component (the parent) — may come from a sub-assembly.
        first_comp = None
        for item in self._items:
            if item.is_sub_asm:
                p = item.component._get_parent()
                if p is not None:
                    first_comp = p.component
                    break
            else:
                first_comp = item.component
                break

        # Assembly-level parent for direct components (TIP_OF_PARENT_COMPONENT).
        if parent_name is None:
            asm_parent = self._get_parent()
            parent_name = (
                getattr(asm_parent.component, "name", "?") if asm_parent else "?"
            )

        for i, item in enumerate(self._items):
            is_last = i == len(self._items) - 1
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "
            off = self._fmt_offset(item.x)
            if item.is_sub_asm:
                sub_asm = item.component
                sub_parent_name = sub_asm._parent_component_name() or "?"
                if item.explicit_frame:
                    ref_name = parent_name
                else:
                    ref_name = self._last_item_parent_name_before(i) or parent_name
                suffix = f" [from: {ref_name}]" if i > 0 else ""
                print(
                    f"{prefix}{connector}({off}m) {sub_asm.name} (parent: {sub_parent_name}){suffix}"
                )
                sub_asm._print_tree_inner(
                    prefix + extension, parent_name=sub_parent_name
                )
            else:
                name = getattr(item.component, "name", type(item.component).__name__)
                if item.component is first_comp and i == 0:
                    line = f"{connector}({off}m) {name} (parent)"
                elif item.explicit_frame:
                    # Explicit TIP/BOTTOM: measured from assembly parent.
                    line = f"{connector}({off}m) {name} [from: {parent_name}]"
                else:
                    # Default: sequential stacking after last parent.
                    ref_name = self._last_item_parent_name_before(i) or parent_name
                    line = f"{connector}({off}m) {name} [from: {ref_name}]"
                print(f"{prefix}{line}")

    def _last_item_parent_name_before(self, index: int) -> str | None:
        """Parent name of the last item before the given index."""
        for j in range(index - 1, -1, -1):
            item = self._items[j]
            if item.is_sub_asm:
                p = item.component._get_parent()
                if p is not None:
                    return getattr(p.component, "name", type(p.component).__name__)
            else:
                return getattr(item.component, "name", type(item.component).__name__)
        return None

    # -----------------------------------------------------------------
    # Plotting — 2D cross sections
    # -----------------------------------------------------------------

    def plot_xy(self, eta: float = 0.0, options: dict = None):
        """
        XY cross section of the assembly at the given eta arc-length —
        the "side view" through the rocket at azimuthal slice eta.

        Axisymmetric components are always shown (their xy profile is
        independent of eta). Wing-type components (fins) appear if their
        own eta offset coincides with the slice plane within ``eta_tol``
        — once above the rocket axis when eta_fin == eta, and once below
        when eta_fin == eta + pi * r_body (the diametrically opposite
        side). At eta = 0 with four fins at (0, pi*r/2, pi*r, 3*pi*r/2)
        you see two fins (one above, one below); at eta = pi*r/4 you see
        none.

        If placements carry ``assembly_name`` tags (e.g. from composing
        sub-assemblies), each assembly is drawn in a distinct colour from
        ``ASSEMBLY_PALETTE`` and a legend is added.

        options keys (all optional):
            show       : bool  — call plt.show() at the end (default True)
            title      : str   — plot title
            xlabel     : str   — x-axis label
            ylabel     : str   — y-axis label
            color      : str   — single colour applied to every component
                                 (overrides per-assembly colouring)
            body_alpha : float — wall fill alpha (default 0.35)
            wing_alpha : float — fin fill alpha (default 0.85)
            eta_tol    : float — arc-length tolerance for matching fins to
                                 the slice plane (default 1e-3 m)
            N          : int   — discretisation per component (default 300)

        Returns: fig, ax
        """
        import matplotlib.pyplot as plt

        from .simple_matplotlib import simple_2d_component_plot
        from .style import ASSEMBLY_PALETTE

        opts = {
            "show": True,
            "title": f"{self.name} — xy plane @ eta = {eta:.4f} m",
            "xlabel": "x (m)",
            "ylabel": "y (m)",
            "color": None,
            "body_alpha": 0.8,
            "wing_alpha": 0.9,
            "eta_tol": 1e-3,
            "N": 300,
        }
        if options:
            opts.update(options)

        N = opts["N"]
        eta_tol = opts["eta_tol"]
        r_ref = self.reference_radius

        # Determine whether to colour by assembly or use a single colour.
        all_placements = self._all_placements()
        has_tags = any(hasattr(p, "assembly_name") for p in all_placements)
        if opts["color"] is not None:
            # Explicit colour overrides per-assembly colouring.
            color_map = None
        elif has_tags:
            seen: list[str] = []
            for p in all_placements:
                name = getattr(p, "assembly_name", self.name)
                if name not in seen:
                    seen.append(name)
            color_map = {
                name: ASSEMBLY_PALETTE[i % len(ASSEMBLY_PALETTE)]
                for i, name in enumerate(seen)
            }
        else:
            color_map = None

        fig, ax = plt.subplots()

        for p in all_placements:
            comp = p.component
            comp_len = _component_length(comp)

            if color_map is not None:
                name = getattr(p, "assembly_name", self.name)
                color = color_map.get(name, "#7f77f7")
            else:
                color = opts["color"] or "darkviolet"

            if _is_axisymmetric(comp):
                xs_global = np.linspace(p.x, p.x + comp_len, N)
                y_upper = lambda xg, _c=comp, _ox=p.x: float(_c.y_upper(xg - _ox))
                y_lower = lambda xg, _c=comp, _ox=p.x: float(_c.y_lower(xg - _ox))
                simple_2d_component_plot(
                    xs_global,
                    y_upper,
                    y_lower,
                    options={
                        "ax": ax,
                        "color": color,
                        "alpha": opts["body_alpha"],
                    },
                )
                continue

            if r_ref <= 0.0:
                continue
            period = 2.0 * math.pi * r_ref
            delta = (p.eta - eta) % period
            shows_above = delta < eta_tol or delta > period - eta_tol
            shows_below = abs(delta - period / 2.0) < eta_tol
            if not (shows_above or shows_below):
                continue

            r_root = self._body_radius_at(p.x) + p.y

            xs_local = np.linspace(0.0, comp_len, N)
            xs_global = p.x + xs_local
            y_span = np.array([float(comp.y_upper(xl)) for xl in xs_local])

            sign = 1.0 if shows_above else -1.0
            ax.fill_between(
                xs_global,
                sign * r_root,
                sign * (r_root + y_span),
                color=color,
                alpha=opts["wing_alpha"],
            )

        # Legend: one entry per assembly, using a coloured line.
        if color_map is not None:
            handles = [
                plt.Line2D([0], [0], color=c, linewidth=8, alpha=opts["body_alpha"])
                for c in color_map.values()
            ]
            ax.legend(
                handles,
                list(color_map.keys()),
                loc="center left",
                bbox_to_anchor=(1.02, 0.5),
                frameon=False,
                title="Assemblies",
            )
            fig.subplots_adjust(right=0.82)

        ax.set_title(opts["title"])
        ax.set_xlabel(opts["xlabel"])
        ax.set_ylabel(opts["ylabel"])
        ax.set_aspect("equal")
        ax.grid(True)

        if opts["show"]:
            plt.show()
        return fig, ax

    def plot_xn(self, y: float = 0.0, options: dict = None):
        """
        X-eta cross section of the assembly at the centerline-radial
        layer ``y`` — the rocket "unrolled" into the (x, eta) strip.

        ``y`` is measured from the rocket centerline (the same axis as
        plot_xy's y axis), not from the body surface. Slicing at y = 0
        is the rocket axis (always empty); slicing at y in
        [inner_r(x), outer_r(x)] cuts through an axisymmetric wall;
        slicing at y in [r_root, r_root + height] cuts through a fin.

        See the module docstring for the geometry primitives used and
        the seam-wrap split for fins crossing eta = 0.

        If placements carry ``assembly_name`` tags, each assembly is
        drawn in a distinct colour from ``ASSEMBLY_PALETTE`` and a
        legend is added.

        options keys (all optional):
            show       : bool  — call plt.show() at the end (default True)
            title      : str   — plot title
            xlabel     : str   — x-axis label
            ylabel     : str   — y-axis label (eta)
            color      : str   — single colour applied to every component
                                 (overrides per-assembly colouring)
            body_alpha : float — body strip alpha (default 0.20)
            wing_alpha : float — fin fill alpha (default 0.85)
            N          : int   — discretisation per component (default 300)

        Returns: fig, ax
        """
        import matplotlib.pyplot as plt

        from .style import ASSEMBLY_PALETTE

        opts = {
            "show": True,
            "title": f"{self.name} — x-eta plane @ y = {y:.4f} m",
            "xlabel": "x (m)",
            "ylabel": "eta (m)",
            "color": None,
            "body_alpha": 0.20,
            "wing_alpha": 0.85,
            "N": 300,
        }
        if options:
            opts.update(options)

        N = opts["N"]
        r_ref = self.reference_radius
        period = 2.0 * math.pi * r_ref

        # Determine whether to colour by assembly or use a single colour.
        all_placements = self._all_placements()
        has_tags = any(hasattr(p, "assembly_name") for p in all_placements)
        if opts["color"] is not None:
            color_map = None
        elif has_tags:
            seen: list[str] = []
            for p in all_placements:
                name = getattr(p, "assembly_name", self.name)
                if name not in seen:
                    seen.append(name)
            color_map = {
                name: ASSEMBLY_PALETTE[i % len(ASSEMBLY_PALETTE)]
                for i, name in enumerate(seen)
            }
        else:
            color_map = None

        fig, ax = plt.subplots()

        if r_ref <= 0.0:
            ax.set_title(opts["title"])
            ax.set_xlabel(opts["xlabel"])
            ax.set_ylabel(opts["ylabel"])
            ax.set_aspect("equal")
            ax.grid(True)
            if opts["show"]:
                plt.show()
            return fig, ax

        for p in all_placements:
            comp = p.component
            comp_len = _component_length(comp)

            if color_map is not None:
                name = getattr(p, "assembly_name", self.name)
                color = color_map.get(name, "#7f77f7")
            else:
                color = opts["color"] or "darkviolet"

            if _is_axisymmetric(comp):
                if not (hasattr(comp, "y_upper") and hasattr(comp, "y_lower")):
                    continue
                xs_local = np.linspace(0.0, comp_len, N)
                xs_global = p.x + xs_local
                yu = np.array([float(comp.y_upper(xl)) for xl in xs_local])
                yl = np.array([float(comp.y_lower(xl)) for xl in xs_local])
                in_wall = (yl <= y) & (y <= yu)
                if not in_wall.any():
                    continue
                ax.fill_between(
                    xs_global,
                    0.0,
                    period,
                    where=in_wall,
                    color=color,
                    alpha=opts["body_alpha"],
                )
                continue

            height = getattr(comp, "height", None)
            if height is None:
                continue
            r_root = self._body_radius_at(p.x) + p.y
            y_span = y - r_root
            if y_span < 0.0 or y_span > height:
                continue
            if not (hasattr(comp, "eta_upper") and hasattr(comp, "eta_lower")):
                continue

            xs_local = np.linspace(0.0, comp_len, N)
            xs_global = p.x + xs_local
            eu_local = np.array([float(comp.eta_upper(xl, y_span)) for xl in xs_local])
            el_local = np.array([float(comp.eta_lower(xl, y_span)) for xl in xs_local])
            valid = ~(np.isnan(eu_local) | np.isnan(el_local))
            if not valid.any():
                continue

            c_mod = p.eta % period
            eta_lo = np.where(valid, c_mod + el_local, c_mod)
            eta_hi = np.where(valid, c_mod + eu_local, c_mod)

            in_band_lo = np.maximum(eta_lo, 0.0)
            in_band_hi = np.minimum(eta_hi, period)
            mask_in = valid & (in_band_hi > in_band_lo)
            if mask_in.any():
                ax.fill_between(
                    xs_global,
                    in_band_lo,
                    in_band_hi,
                    where=mask_in,
                    color=color,
                    alpha=opts["wing_alpha"],
                )

            mask_below = valid & (eta_lo < 0.0)
            if mask_below.any():
                wrap_below_lo = period + np.minimum(eta_lo, 0.0)
                wrap_below_hi = np.full_like(eta_lo, period)
                ax.fill_between(
                    xs_global,
                    wrap_below_lo,
                    wrap_below_hi,
                    where=mask_below,
                    color=color,
                    alpha=opts["wing_alpha"],
                )

            mask_above = valid & (eta_hi > period)
            if mask_above.any():
                wrap_above_lo = np.zeros_like(eta_hi)
                wrap_above_hi = np.maximum(eta_hi - period, 0.0)
                ax.fill_between(
                    xs_global,
                    wrap_above_lo,
                    wrap_above_hi,
                    where=mask_above,
                    color=color,
                    alpha=opts["wing_alpha"],
                )

        # Legend: one entry per assembly, using a coloured line.
        if color_map is not None:
            handles = [
                plt.Line2D([0], [0], color=c, linewidth=8, alpha=opts["body_alpha"])
                for c in color_map.values()
            ]
            ax.legend(
                handles,
                list(color_map.keys()),
                loc="center left",
                bbox_to_anchor=(1.02, 0.5),
                frameon=False,
                title="Assemblies",
            )
            fig.subplots_adjust(right=0.82)

        ax.set_title(opts["title"])
        ax.set_xlabel(opts["xlabel"])
        ax.set_ylabel(opts["ylabel"])
        ax.set_aspect("equal")
        ax.grid(True)
        ax.set_xlim(0.0, self.total_length)
        ax.set_ylim(0.0, period)

        if opts["show"]:
            plt.show()
        return fig, ax


if __name__ == "__main__":
    from .components import BodyTube, TrapezoidalFins, VonKarmanBoatTail
    from .materials import Aluminum

    al = Aluminum()

    body = BodyTube(
        outer_diameter=0.16,
        length=0.40,
        wall_thickness=0.003,
        material=al,
    )
    boattail = VonKarmanBoatTail(
        boattail_top_diameter=0.16,
        boattail_bottom_diameter=0.12246,
        boattail_length=0.35,
        wall_thickness=0.003,
        material=al,
    )
    fins = TrapezoidalFins(
        sweep=30,
        height=0.17,
        root_chord=0.37,
        tip_chord=0.2,
        cant_angle=0,
        thickness=0.02,
        le_wedge_length=0.05,
        te_wedge_length=0.04,
        material=al,
    )

    asm = Assembly("Fin Can")
    asm.add(body)
    asm.add(boattail)

    fin_x = body.length - 0.05
    r = body.outer_radius
    eta_step = 2.0 * math.pi * r / 4.0
    for k in range(4):
        asm.add(
            fins,
            position_x=fin_x,
            position_y=-0.04,
            position_eta=k * eta_step,
            reference_frame=ReferenceFrame.NOSE_TO_TAIL,
        )

    Ixx, Iyy, Izz = asm.inertia_xyz
    Xcg, Ycg, Zcg = asm.cg_xyz
    print(f"Assembly: {asm.name}")
    print(f"  total_length = {asm.total_length:.3f} m")
    print(f"  mass         = {asm.mass:.3f} kg")
    print(f"  cg_xyz       = ({Xcg:+.4f}, {Ycg:+.4e}, {Zcg:+.4e}) m")
    print(f"  inertia_xyz  = ({Ixx:.5e}, {Iyy:.5e}, {Izz:.5e}) kg.m^2")
    print(f"  I_axial      = {asm.I_axial:.5e} kg.m^2")
    print(f"  I_lateral    = {asm.I_lateral:.5e} kg.m^2")
    print(f"  placements   = {len(asm.placements)}")
    for p in asm.placements:
        print(
            f"    {type(p.component).__name__:24s}  "
            f"x={p.x:+.3f}  y={p.y:+.3f}  eta={p.eta:+.3f}"
        )

    # -----------------------------------------------------------------
    # Cross-section demos
    # -----------------------------------------------------------------
    # plot_xy at three azimuths:
    #   eta = 0           — slice through fins 0 (above) and 2 (below)
    #   eta = eta_step    — slice through fins 1 (above) and 3 (below)
    #   eta = eta_step/2  — slice between fins; only the body should appear
    asm.plot_xy(eta=0.0)
    asm.plot_xy(eta=eta_step)
    asm.plot_xy(eta=eta_step / 2.0)

    # Same xy slice with a different colour to show the option propagates
    # to every component in the assembly.
    asm.plot_xy(eta=0.0, options={"color": "teal"})

    # plot_xn at five centerline-radial layers (y measured from the rocket
    # axis — same axis as plot_xy's y axis):
    #   y = 0.0000  rocket centerline: empty (no material on the axis)
    #   y = 0.0785  1.5 mm into the body tube wall (outer=0.080, inner=0.077):
    #               body band fills the full eta strip; fins at this y have
    #               span_pos = 0.0785 - (0.080 + (-0.04)) = 0.0385 m up the
    #               span. Fin 0 sits at p.eta = 0 — its thickness band wraps
    #               the seam and renders as two strips, near eta=0 and near
    #               eta=2*pi*r_ref
    #   y = 0.0700  below the body tube's inner radius (0.077): no body-tube
    #               wall, but the boat tail tapers from 0.080 to 0.0612, so
    #               y=0.070 falls inside the boat-tail wall over a narrow x
    #               band — a thin strip rather than a full-length rectangle
    #   y = 0.1300  above the body, inside the fin span (root=0.040,
    #               tip=0.210). Body band empty; fins at span_pos = 0.090
    #   y = 0.2200  above the fin tips: empty
    asm.plot_xn(y=0.0)
    asm.plot_xn(y=0.0785)
    asm.plot_xn(y=0.0700)
    asm.plot_xn(y=0.1300)
    asm.plot_xn(y=0.2200)
