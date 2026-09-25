"""
Builds a rocket Assembly from the JSON rocket configuration schema.

The expected input is either the full design-point JSON document or the
``rocket_configuration`` object inside it. The rocket configuration contains
top-level metadata, a list of stage ids, and one stage object per id. Each
stage contains a ``components`` mapping whose values are the component config
objects used to construct the CAD assembly.

Components are added to a single Assembly with tip_of_parent_component so they
stack sequentially nose-to-tail. Optional position_x / position_y /
position_eta keys in each component config override the default 0.0 offset
(e.g. fins that overlap the boattail axially, embed into the body wall
radially, or sit at a specific azimuth).

Wing-type components (trapezoidal_fins, wing) accept an optional ``n_fins``
key — when given, the builder emits N placements equally spaced around the
body circumference, anchored to the chained x of the first one. Likewise
rail_button accepts ``n_buttons``.

Any axisymmetric component config can also carry a ``mass`` key — when present
it overrides the density-derived mass via ``set_mass()`` after construction.
"""

import math
import json
from pathlib import Path

from .CAD_variables import CADComponentType, ComponentType, ReferenceFrame
from .assembly import Assembly
from .components import (
    Bulkhead,
    BodyTube,
    CappedCylindricalTank,
    CircularPort,
    ConicalBoatTail,
    ConicalNoseCone,
    ConvergingDivergingConicalNozzle,
    CylindricalTank,
    DivergingConicalNozzle,
    DrogueParachute,
    HybridFuelGrain,
    LVHaackNoseCone,
    LaunchRail,
    MainParachute,
    MassComponent,
    OgiveNoseCone,
    RailButton,
    ShockCord,
    TrapezoidalFins,
    TubeCoupler,
    VonKarmanBoatTail,
    VonKarmanNoseCone,
    Wing,
    make_wing_cross_section,
)
from .materials import (
    ABS,
    Aluminum,
    Cardboard,
    CarbonFiber,
    Fiberglass,
    Graphite,
    Nylon,
    Phenolic,
    Steel,
)

_MATERIALS = {
    'aluminum':    Aluminum,
    'phenolic':    Phenolic,
    'fiberglass':  Fiberglass,
    'cardboard':   Cardboard,
    'steel':       Steel,
    'carbon_fiber': CarbonFiber,
    'graphite':    Graphite,
    'abs':         ABS,
    'nylon':       Nylon,
}


def _get_material(name: str):
    cls = _MATERIALS.get(name.lower())
    if cls is None:
        raise ValueError(f"Unknown material '{name}'. Valid: {list(_MATERIALS)}")
    return cls()


def _build_cross_section(cfg: dict):
    """
    Build a WingCrossSection from a wing/fin JSON component entry.

    If ``cross_section_type`` is given, it is dispatched explicitly via
    :func:`make_wing_cross_section`. Otherwise the type is inferred:
    a slab if both wedge lengths are zero/absent, otherwise a
    supersonic-wedge. Returns ``None`` if the user supplied no cross
    section info at all (caller falls back to the component's own
    auto-build behaviour).
    """
    kind = cfg.get('cross_section_type')
    if kind is not None:
        return make_wing_cross_section(
            kind=str(kind),
            thickness=float(cfg.get('thickness', 0.0)),
            le_wedge_length=float(cfg.get('le_wedge_length', 0.0)),
            te_wedge_length=float(cfg.get('te_wedge_length', 0.0)),
        )
    return None


def _apply_mass_overrides(comp, cfg: dict):
    """Apply optional mass / I_lateral / I_axial / cg overrides from JSON."""
    if 'mass' in cfg:
        comp.set_mass(float(cfg['mass']))
    if 'cg' in cfg:
        comp.set_cg(float(cfg['cg']))
    if 'CG' in cfg:
        comp.set_cg(float(cfg['CG']))
    if 'I_lateral' in cfg:
        comp.set_I_lateral(float(cfg['I_lateral']))
    if 'I_axial' in cfg:
        comp.set_I_axial(float(cfg['I_axial']))


def _load_builder_config(config) -> dict:
    """Load a JSON builder config from a path or return the mapping directly."""
    if isinstance(config, (str, Path)):
        path = Path(config)
        if path.suffix.lower() != ".json":
            raise ValueError(
                f"build_rocket only supports JSON input files, got '{path.suffix or '<none>'}'."
            )
        return json.loads(path.read_text())

    if isinstance(config, dict):
        return config

    raise TypeError("build_rocket expects a JSON mapping or a path to a .json file.")


def _normalize_builder_config(config) -> dict:
    """
    Normalize the JSON rocket configuration into the builder's flat assembly list.

    Accepted shapes:
    - full JSON design point containing ``rocket_configuration``
    - bare ``rocket_configuration`` mapping
    """
    loaded = _load_builder_config(config)
    rocket_cfg = loaded.get("rocket_configuration", loaded)

    if not isinstance(rocket_cfg, dict):
        raise TypeError("rocket_configuration must be a mapping.")

    metadata = rocket_cfg.get("metadata", {})
    stage_ids = rocket_cfg.get("stages", [])
    if not isinstance(stage_ids, list):
        raise TypeError("rocket_configuration.stages must be a list of stage ids.")

    assemblies = []
    for stage_id in stage_ids:
        if stage_id not in rocket_cfg:
            raise KeyError(f"Stage id '{stage_id}' is listed in stages but missing from rocket_configuration.")
        stage_cfg = rocket_cfg[stage_id]
        if not isinstance(stage_cfg, dict):
            raise TypeError(f"Stage '{stage_id}' must be a mapping.")

        component_mapping = stage_cfg.get("components", {})
        if not isinstance(component_mapping, dict):
            raise TypeError(f"Stage '{stage_id}' components must be a mapping.")

        components = []
        for component_key, component_cfg in component_mapping.items():
            if not isinstance(component_cfg, dict):
                continue
            entry = dict(component_cfg)
            entry.setdefault("name", component_key)
            entry.setdefault("id", component_key)
            components.append(entry)

        assemblies.append(
            {
                "id": stage_cfg.get("id", stage_id),
                "name": stage_cfg.get("name", stage_id),
                "overrides": dict(stage_cfg.get("overrides", {})),
                "component": components,
            }
        )

    return {
        "name": metadata.get("name", "Rocket"),
        "id": metadata.get("id"),
        "assembly": assemblies,
    }


def _make_component(cfg: dict):
    """Dispatch on cfg['type'] and construct the matching component."""
    t = CADComponentType.from_value(cfg['type'])

    if t is CADComponentType.DIVERGING_CONICAL_NOZZLE:
        comp = DivergingConicalNozzle(
            throat_diameter=cfg['throat_diameter'],
            outer_diameter=cfg['outer_diameter'],
            cone_length=cfg['cone_length'],
            diverging_angle_deg=cfg['diverging_angle_deg'],
            material=_get_material(cfg['material']),
            name=cfg.get('name', 'Diverging Conical Nozzle'),
        )
    elif t is CADComponentType.CONVERGING_DIVERGING_CONICAL_NOZZLE:
        comp = ConvergingDivergingConicalNozzle(
            chamber_diameter=cfg['chamber_diameter'],
            throat_diameter=cfg['throat_diameter'],
            outer_diameter=cfg['outer_diameter'],
            converging_length=cfg['converging_length'],
            diverging_length=cfg['diverging_length'],
            diverging_angle_deg=cfg['diverging_angle_deg'],
            material=_get_material(cfg['material']),
            name=cfg.get('name', 'Converging-Diverging Conical Nozzle'),
        )
    elif t is CADComponentType.HYBRID_FUEL_GRAIN:
        comp = HybridFuelGrain(
            grain_outer_diameter=cfg['grain_outer_diameter'],
            grain_length=cfg['grain_length'],
            infill_density=cfg['infill_density'],
            port_geometry=CircularPort(diameter=cfg['grain_inner_diameter']),
            material=_get_material(cfg.get('material', 'abs')),
            name=cfg.get('name', 'Hybrid Fuel Grain'),
        )
    elif t is CADComponentType.CYLINDRICAL_TANK:
        comp = CylindricalTank(
            inner_diameter=cfg['inner_diameter'],
            length=cfg['length'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
            name=cfg.get('name', 'Cylindrical Tank'),
        )
    elif t is CADComponentType.CAPPED_CYLINDRICAL_TANK:
        comp = CappedCylindricalTank(
            outer_diameter=cfg['inner_diameter'] + 2.0 * cfg['wall_thickness'],
            length=cfg['length'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
            name=cfg.get('name', 'Capped Cylindrical Tank'),
        )
    elif t is CADComponentType.VONKARMAN_NOSECONE:
        comp = VonKarmanNoseCone(
            length=cfg['length'],
            base_radius=cfg['base_radius'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
        )
    elif t is CADComponentType.OGIVE_NOSECONE:
        comp = OgiveNoseCone(
            length=cfg['length'],
            base_radius=cfg['base_radius'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
        )
    elif t is CADComponentType.CONICAL_NOSECONE:
        comp = ConicalNoseCone(
            length=cfg['length'],
            base_radius=cfg['base_radius'],
            material=_get_material(cfg['material']),
        )
    elif t is CADComponentType.LVHAACK_NOSECONE:
        comp = LVHaackNoseCone(
            length=cfg['length'],
            base_radius=cfg['base_radius'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
        )
    elif t is CADComponentType.BODY_TUBE:
        comp = BodyTube(
            outer_diameter=cfg['outer_diameter'],
            length=cfg['length'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
        )
    elif t is CADComponentType.TUBE_COUPLER:
        comp = TubeCoupler(
            outer_diameter=cfg['outer_diameter'],
            length=cfg['length'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
            name=cfg.get('name', 'Tube Coupler'),
        )
    elif t is CADComponentType.BULKHEAD:
        comp = Bulkhead(
            diameter=cfg['diameter'],
            thickness=cfg['thickness'],
            material=_get_material(cfg['material']),
            name=cfg.get('name', 'Bulkhead'),
        )
    elif t is CADComponentType.MASS_COMPONENT:
        comp = MassComponent(
            diameter=cfg['diameter'],
            length=cfg['length'],
            material=_get_material(cfg.get('material', 'aluminum')),
            name=cfg.get('name', 'Mass Component'),
        )
    elif t is CADComponentType.SHOCK_CORD:
        comp = ShockCord(
            shock_cord_length=cfg['shock_cord_length'],
            packed_length=cfg['packed_length'],
            packed_radius=cfg['packed_radius'],
            material=_get_material(cfg.get('material', 'nylon')),
            name=cfg.get('name', 'Shock Cord'),
        )
    elif t is CADComponentType.DROGUE_PARACHUTE:
        comp = DrogueParachute(
            parachute_radius=cfg['parachute_radius'],
            cd=cfg['cd'],
            packed_length=cfg['packed_length'],
            packed_radius=cfg['packed_radius'],
            material=_get_material(cfg.get('material', 'nylon')),
            name=cfg.get('name', 'Drogue'),
            trigger=cfg.get('trigger', 'apogee'),
            lag=cfg.get('lag', 1.0),
        )
    elif t is CADComponentType.MAIN_PARACHUTE:
        comp = MainParachute(
            trigger=cfg['trigger'],
            parachute_radius=cfg['parachute_radius'],
            cd=cfg['cd'],
            packed_length=cfg['packed_length'],
            packed_radius=cfg['packed_radius'],
            material=_get_material(cfg.get('material', 'nylon')),
            lag=cfg.get('lag', 1.0),
            name=cfg.get('name', 'Main'),
        )
    elif t is CADComponentType.VONKARMAN_BOATTAIL:
        comp = VonKarmanBoatTail(
            boattail_top_diameter=cfg['top_diameter'],
            boattail_bottom_diameter=cfg['bottom_diameter'],
            boattail_length=cfg['length'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
        )
    elif t is CADComponentType.CONICAL_BOATTAIL:
        comp = ConicalBoatTail(
            boattail_top_diameter=cfg['top_diameter'],
            boattail_bottom_diameter=cfg['bottom_diameter'],
            boattail_length=cfg['length'],
            wall_thickness=cfg['wall_thickness'],
            material=_get_material(cfg['material']),
        )
    elif t is CADComponentType.TRAPEZOIDAL_FINS:
        comp = TrapezoidalFins(
            sweep=cfg['sweep'],
            height=cfg['height'],
            root_chord=cfg['root_chord'],
            tip_chord=cfg['tip_chord'],
            cant_angle=cfg.get('cant_angle', 0.0),
            thickness=cfg['thickness'],
            le_wedge_length=cfg.get('le_wedge_length', 0.0),
            te_wedge_length=cfg.get('te_wedge_length', 0.0),
            cross_section=_build_cross_section(cfg),
            material=_get_material(cfg['material']),
            name=cfg.get('name', 'Trapezoidal Fins'),
        )
    elif t is CADComponentType.WING:
        comp = Wing(
            sweep=cfg['sweep'],
            root_chord=cfg['root_chord'],
            tip_chord=cfg['tip_chord'],
            cant_angle=cfg.get('cant_angle', 0.0),
            thickness=cfg['thickness'],
            material=_get_material(cfg['material']),
            span=cfg.get('span'),
            aspect_ratio=cfg.get('aspect_ratio'),
            le_wedge_length=cfg.get('le_wedge_length', 0.0),
            te_wedge_length=cfg.get('te_wedge_length', 0.0),
            cross_section=_build_cross_section(cfg),
            name=cfg.get('name', 'Wing'),
        )
    elif t is CADComponentType.RAIL_BUTTON:
        comp = RailButton(
            button_diameter=cfg['button_diameter'],
            button_height=cfg['button_height'],
            material=_get_material(cfg.get('material', 'aluminum')),
            name=cfg.get('name', 'Rail Button'),
        )
    elif t is CADComponentType.LAUNCH_RAIL:
        comp = LaunchRail(
            rail_length=cfg['rail_length'],
            packed_volume=cfg['packed_volume'],
            packed_radius=cfg['packed_radius'],
            material=_get_material(cfg.get('material', 'aluminum')),
            rail_inclination=cfg.get('rail_inclination', 90.0),
            rail_heading=cfg.get('rail_heading', 90.0),
            name=cfg.get('name', 'Launch Rail'),
        )
    else:
        raise ValueError(f"Unknown component type '{t}'")

    _apply_mass_overrides(comp, cfg)
    return comp


def _add_directional_set(rocket: Assembly, comp, comp_cfg: dict, count: int):
    """
    Add `count` copies of a directional component (fin/wing/rail button)
    around the body circumference. The first copy is placed at the
    user-supplied position_eta; subsequent copies share the chained x
    of the first and step around eta by 2*pi*r_ref / count.

    All copies share the same component object — Assembly only stores a
    reference, and mass/inertia properties are read fresh per placement
    by `_placement_cg_xyz` / `_placement_inertia_at_self_cg_xyz`, so the
    sharing is safe.
    """
    eta0 = float(comp_cfg.get('position_eta', 0.0))
    py = float(comp_cfg.get('position_y', 0.0))
    px = float(comp_cfg.get('position_x', 0.0))

    # Compute absolute x from the last placement's tail
    if rocket.placements:
        last = rocket.placements[-1]
        abs_x = last.x + _length(last.component) + px
    else:
        abs_x = px

    rocket.add(
        comp,
        position_x=abs_x,
        position_y=py,
        position_eta=eta0,
        reference_frame=ReferenceFrame.NOSE_TO_TAIL,
    )
    first = rocket.placements[-1]
    if count <= 1:
        return

    # Anchor subsequent copies to the same global x as the first placement.
    r_ref = rocket.reference_radius
    if r_ref <= 0.0:
        return  # no body to anchor eta to; skip the spacing
    eta_step = 2.0 * math.pi * r_ref / count

    for k in range(1, count):
        rocket.add(
            comp,
            position_x=first.x,
            position_y=py,
            position_eta=eta0 + k * eta_step,
            reference_frame=ReferenceFrame.NOSE_TO_TAIL,
        )


def _length(comp):
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
    return 0.0


def build_rocket(config: dict) -> Assembly:
    """
    Loop through every normalized JSON stage in order, then every component
    within it, and add each component to the rocket Assembly using the
    bottom_of_parent_component reference frame.

    Each created :class:`Placement` is tagged with an ``assembly_name``
    attribute identifying which stage it came from. The plotting helpers below
    use this tag to group placements by assembly (one colour per assembly,
    legend, etc.) without changing the Assembly class itself, which is
    intentionally a flat list of placements.
    """
    normalized = _normalize_builder_config(config)
    rocket = Assembly(normalized.get('name', 'Rocket'))
    rocket.id = normalized.get('id')

    for asm_cfg in normalized.get('assembly', []):
        asm_name = asm_cfg.get('name', 'Unnamed Assembly')
        asm_id = asm_cfg.get('id')
        n_before = len(rocket.placements)
        for comp_cfg in asm_cfg.get('component', []):
            comp = _make_component(comp_cfg)
            comp.id = comp_cfg.get('id')
            t = CADComponentType.from_value(comp_cfg['type'])
            if t in (CADComponentType.TRAPEZOIDAL_FINS, CADComponentType.WING):
                n = int(comp_cfg.get('n_fins', 1))
                _add_directional_set(rocket, comp, comp_cfg, n)
            elif t is CADComponentType.RAIL_BUTTON:
                n = int(comp_cfg.get('n_buttons', 1))
                _add_directional_set(rocket, comp, comp_cfg, n)
            else:
                # Compute absolute x from the last placement's tail
                if rocket.placements:
                    last = rocket.placements[-1]
                    abs_x = (
                        last.x
                        + _length(last.component)
                        + float(comp_cfg.get('position_x', 0.0))
                    )
                else:
                    abs_x = float(comp_cfg.get('position_x', 0.0))
                rocket.add(
                    comp,
                    position_x=abs_x,
                    position_y=float(comp_cfg.get('position_y', 0.0)),
                    position_eta=float(comp_cfg.get('position_eta', 0.0)),
                    reference_frame=ReferenceFrame.NOSE_TO_TAIL,
                )
        for p in rocket.placements[n_before:]:
            p.assembly_name = asm_name
            p.assembly_id = asm_id
            p.component_id = getattr(p.component, 'id', None)

        if asm_cfg.get('overrides'):
            _apply_mass_overrides(rocket, asm_cfg['overrides'])
    return rocket


# =========================================================================
# Plotting — assembly-aware side views built on top of Assembly's geometry
# primitives. Lives in builder.py (not assembly.py) because grouping by
# Stage grouping is the *builder's* concept; Assembly itself is just a
# flat list of placements.
# =========================================================================


def _ordered_assembly_names(rocket: Assembly) -> list[str]:
    """Distinct assembly_name tags in placement order."""
    seen: list[str] = []
    for p in rocket.placements:
        name = getattr(p, 'assembly_name', 'Unnamed Assembly')
        if name not in seen:
            seen.append(name)
    return seen


def _assembly_color_map(rocket: Assembly, palette=None) -> dict[str, str]:
    """Map each assembly_name -> colour, in order, cycling through palette."""
    from CAD.style import ASSEMBLY_PALETTE, color_for_assembly

    pal = palette if palette is not None else ASSEMBLY_PALETTE
    names = _ordered_assembly_names(rocket)
    if palette is None:
        return {n: color_for_assembly(i) for i, n in enumerate(names)}
    return {n: pal[i % len(pal)] for i, n in enumerate(names)}


def _is_internal(comp) -> bool:
    """
    True if a component is an internal (inside-the-skin) part — bulkhead,
    coupler, parachute, mass blob, shock cord. Marked at the class level
    via ``is_inner: ClassVar[bool]`` on the component class. Anything
    that doesn't declare it (body tubes, nose cones, fins, rail buttons)
    is treated as external.
    """
    return bool(getattr(comp, 'is_inner', False))


def _placement_alpha(p, opts: dict) -> float:
    """External placements use ``external_alpha``; internal use ``internal_alpha``."""
    return float(
        opts['internal_alpha'] if _is_internal(p.component) else opts['external_alpha']
    )


def _draw_axisymmetric(ax, rocket, p, color, alpha, n: int):
    """Render an axisymmetric placement onto ``ax`` (XY side view)."""
    import numpy as np

    from CAD.simple_matplotlib import simple_2d_component_plot

    comp = p.component
    comp_len = _length(comp)
    xs_global = np.linspace(p.x, p.x + comp_len, n)
    y_upper_fn = lambda xg, _c=comp, _ox=p.x: float(_c.y_upper(xg - _ox))
    y_lower_fn = lambda xg, _c=comp, _ox=p.x: float(_c.y_lower(xg - _ox))
    simple_2d_component_plot(
        xs_global,
        y_upper_fn,
        y_lower_fn,
        options={'ax': ax, 'color': color, 'alpha': alpha},
    )


def _draw_directional(ax, rocket, p, color, alpha, n: int):
    """
    Render a WING / PROTRUSION placement onto ``ax`` (XY side view).

    Pure projection: the placement's eta is used only to decide whether
    the planform sits above (eta in [0, period/2)) or below (eta in
    [period/2, period)) the rocket axis. This way every directional
    component is visible on a single side view, even when multiple fins
    in the same assembly are equally spaced around the body — they
    overlap but read as one shape because they share the assembly's
    colour.
    """
    import numpy as np

    comp = p.component
    comp_len = _length(comp)
    r_root = rocket._body_radius_at(p.x) + p.y

    xs_local = np.linspace(0.0, comp_len, n)
    xs_global = p.x + xs_local
    y_span = np.array([float(comp.y_upper(xl)) for xl in xs_local])

    r_ref = rocket.reference_radius
    period = 2.0 * math.pi * r_ref if r_ref > 0.0 else 0.0
    if period > 0.0:
        eta_mod = p.eta % period
        sign = 1.0 if eta_mod < period / 2.0 else -1.0
    else:
        sign = 1.0

    ax.fill_between(
        xs_global,
        sign * r_root,
        sign * (r_root + y_span),
        color=color,
        alpha=alpha,
        linewidth=0,
    )
    ax.plot(xs_global, sign * (r_root + y_span), color=color, alpha=alpha)
    ax.plot(
        xs_global,
        np.full_like(xs_global, sign * r_root),
        color=color,
        alpha=alpha,
    )


def _draw_placement(ax, rocket, p, color, alpha, n: int):
    comp = p.component
    ctype = getattr(comp, 'component_type', ComponentType.AXISYMMETRIC)
    if ctype == ComponentType.AXISYMMETRIC:
        _draw_axisymmetric(ax, rocket, p, color, alpha, n)
    else:
        _draw_directional(ax, rocket, p, color, alpha, n)


def _placement_extent(rocket, p) -> tuple[float, float, float, float]:
    """
    (x0, x1, y_top, y_bottom) of a placement in the side-view coords —
    used for label anchoring. y_top is the upward-projected outer edge,
    y_bottom is the downward-projected one (mirror).
    """
    comp = p.component
    comp_len = _length(comp)
    ctype = getattr(comp, 'component_type', ComponentType.AXISYMMETRIC)
    if ctype == ComponentType.AXISYMMETRIC:
        if hasattr(comp, 'y_upper'):
            mids = [comp_len * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
            try:
                y_top = max(float(comp.y_upper(m)) for m in mids)
            except Exception:
                y_top = 0.0
        else:
            y_top = 0.0
        return (p.x, p.x + comp_len, y_top, -y_top)
    # WING / PROTRUSION — uses the body radius at p.x as anchor
    r_root = rocket._body_radius_at(p.x) + p.y
    if hasattr(comp, 'y_upper'):
        mids = [comp_len * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
        try:
            y_span = max(float(comp.y_upper(m)) for m in mids)
        except Exception:
            y_span = 0.0
    else:
        y_span = getattr(comp, 'height', 0.0)
    r_ref = rocket.reference_radius
    period = 2.0 * math.pi * r_ref if r_ref > 0.0 else 0.0
    if period > 0.0 and (p.eta % period) >= period / 2.0:
        return (p.x, p.x + comp_len, 0.0, -(r_root + y_span))
    return (p.x, p.x + comp_len, r_root + y_span, 0.0)


def plot_rocket(rocket: Assembly, options: dict = None):
    """
    Side view of the rocket with each stage rendered in a
    distinct colour from :data:`plotting.style.ASSEMBLY_PALETTE`. Internal
    components (bulkheads, couplers, mass blobs, parachutes, shock cords)
    are drawn at ``internal_alpha`` to suggest they live inside the body
    skin; everything else is drawn at ``external_alpha``. The legend lives
    OUTSIDE the axes box so it never occludes the rocket geometry.

    options keys (all optional):
        show              : bool  — call plt.show() (default True)
        title             : str   — plot title
        figsize           : (W, H) — figure size in inches (default (12, 4))
        external_alpha    : float — outer-shell components (default from style)
        internal_alpha    : float — inner components       (default from style)
        N                 : int   — discretisation per component (default 300)
        palette           : tuple[str] — override the assembly colour palette
        legend_loc        : str   — anchor for the outside legend
                                    (default 'center left' anchored at (1.02, 0.5))
        ax                : matplotlib Axes — render into this axes; the caller
                                    drives titles, legend, and show().

    Returns: fig, ax
    """
    import matplotlib.pyplot as plt

    from CAD.style import EXTERNAL_ALPHA, INTERNAL_ALPHA

    opts = {
        'show': True,
        'title': f'{rocket.name} — side view',
        'figsize': (12, 4),
        'external_alpha': EXTERNAL_ALPHA,
        'internal_alpha': INTERNAL_ALPHA,
        'N': 300,
        'palette': None,
        'legend_loc': 'center left',
        'ax': None,
    }
    if options:
        opts.update(options)

    color_map = _assembly_color_map(rocket, palette=opts['palette'])

    own_axes = opts['ax'] is None
    if own_axes:
        fig, ax = plt.subplots(figsize=opts['figsize'])
    else:
        ax = opts['ax']
        fig = ax.figure

    # External first, internal second → internal stays on top in z-order, so
    # bulkheads and coupler walls aren't hidden behind the body tube.
    externals = [p for p in rocket.placements if not _is_internal(p.component)]
    internals = [p for p in rocket.placements if _is_internal(p.component)]
    for p in externals + internals:
        name = getattr(p, 'assembly_name', 'Unnamed Assembly')
        color = color_map.get(name, '#7f7f7f')
        alpha = _placement_alpha(p, opts)
        _draw_placement(ax, rocket, p, color, alpha, opts['N'])

    # Legend: one entry per assembly, in placement order. Placed outside the axes
    # box so it never sits on top of the rocket.
    handles = [
        plt.Line2D([0], [0], color=color_map[name], linewidth=8, alpha=opts['external_alpha'])
        for name in _ordered_assembly_names(rocket)
    ]
    labels = _ordered_assembly_names(rocket)
    ax.legend(
        handles,
        labels,
        loc=opts['legend_loc'],
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        title='Assemblies',
    )

    ax.set_title(opts['title'])
    ax.set_xlabel('x (m)')
    ax.set_ylabel('y (m)')
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.axhline(0.0, color='#8a8a8a', linewidth=0.6, alpha=0.7)
    ax.set_xlim(-0.02 * rocket.total_length, 1.02 * rocket.total_length)

    if own_axes:
        # Make room on the right for the outside legend.
        fig.subplots_adjust(right=0.82)
        if opts['show']:
            plt.show()
    return fig, ax


def _assign_label_lanes(rocket: Assembly, n_lanes: int = 4):
    """
    Assign each placement to a "lane" so that label callouts don't overlap.

    Returns a list of (placement, side, lane_idx) tuples — side is +1 for
    above, -1 for below the rocket. lane_idx 0 is closest to the rocket;
    higher means farther out. Adjacent placements alternate sides so the
    callouts spread instead of stacking, and within each side the lane
    cycles 0..n_lanes-1 so any n_lanes consecutive placements on the same
    side end up at n_lanes different heights.
    """
    items = []
    for i, p in enumerate(rocket.placements):
        x0, x1, _y_top, _y_bot = _placement_extent(rocket, p)
        items.append((i, 0.5 * (x0 + x1), p))
    items.sort(key=lambda t: t[1])

    out = []
    upper_count = 0
    lower_count = 0
    for k, (_idx, _xc, p) in enumerate(items):
        if k % 2 == 0:
            side = 1
            lane = upper_count % n_lanes
            upper_count += 1
        else:
            side = -1
            lane = lower_count % n_lanes
            lower_count += 1
        out.append((p, side, lane))
    return out


def plot_rocket_detail(rocket: Assembly, options: dict = None):
    """
    A detailed side view of the rocket — same colours and alpha
    convention as :func:`plot_rocket`, but with:

      * tighter major+minor grid
      * each placement labelled with its component name via an arrow
        callout, lanes assigned so callouts don't overlap
      * an inset axes in the bottom-left showing the cross section of
        the wings (overlaid root and tip stations) so the cross-section
        shape is legible alongside the rocket layout

    options keys (all optional):
        show              : bool   — call plt.show() (default True)
        title             : str    — plot title
        figsize           : (W, H) — figure size in inches (default (16, 6))
        external_alpha    : float  — outer-shell alpha (default from style)
        internal_alpha    : float  — inner alpha       (default from style)
        N                 : int    — sample count per component (default 300)
        palette           : tuple[str] — override colour palette
        label_fontsize    : float  — annotation font size (default 8)
        show_inset        : bool   — render the wing-cross-section inset
                                    (default True)
        inset_rect        : (x, y, w, h) in axes fraction — inset bbox
                                    (default (0.02, 0.04, 0.30, 0.35))

    Returns: fig, ax
    """
    import matplotlib.pyplot as plt
    import numpy as np

    from CAD.style import (
        ANNOTATION_COLOR,
        CENTERLINE_COLOR,
        EXTERNAL_ALPHA,
        GRID_COLOR,
        INTERNAL_ALPHA,
    )

    opts = {
        'show': True,
        'title': f'{rocket.name} — detail',
        # Tall figure so the lane-stacked callouts above and below the
        # rocket get real vertical room — at aspect='equal' the rocket's
        # x/y ratio dominates, and a short figure squashes the labels.
        'figsize': (16, 10),
        'external_alpha': EXTERNAL_ALPHA,
        'internal_alpha': INTERNAL_ALPHA,
        'N': 300,
        'palette': None,
        'label_fontsize': 9,
        'show_inset': True,
        'inset_rect': (0.02, 0.05, 0.22, 0.40),
    }
    if options:
        opts.update(options)

    # Underlying side view first (no legend yet — we'll add it after the
    # callouts so the legend appears outside everything).
    fig, ax = plt.subplots(figsize=opts['figsize'])
    plot_rocket(
        rocket,
        options={
            'ax': ax,
            'show': False,
            'title': opts['title'],
            'external_alpha': opts['external_alpha'],
            'internal_alpha': opts['internal_alpha'],
            'N': opts['N'],
            'palette': opts['palette'],
        },
    )

    # Tighter grid — minor ticks at 50 mm, major at 250 mm. Aspect is
    # already equal from plot_rocket, so the same spacing applies in y.
    ax.grid(False)
    from matplotlib.ticker import AutoMinorLocator, MultipleLocator

    ax.xaxis.set_major_locator(MultipleLocator(0.25))
    ax.xaxis.set_minor_locator(MultipleLocator(0.05))
    ax.yaxis.set_major_locator(MultipleLocator(0.05))
    ax.yaxis.set_minor_locator(AutoMinorLocator(5))
    ax.grid(True, which='major', color=GRID_COLOR, linewidth=0.8)
    ax.grid(True, which='minor', color=GRID_COLOR, linewidth=0.4, alpha=0.7)
    ax.axhline(0.0, color=CENTERLINE_COLOR, linewidth=0.6, alpha=0.8)

    # Component callouts. Each placement's text sits in a lane stacked
    # outside the rocket envelope, with an arrow pointing to its
    # geometric centre. Lanes alternate upper/lower so labels don't
    # bunch; labels rotated 30° so wide names take less x space.
    n_lanes = 5
    r_max = max(
        max(_placement_extent(rocket, p)[2] for p in rocket.placements),
        -min(_placement_extent(rocket, p)[3] for p in rocket.placements),
        1e-6,
    )
    # Push the first lane clear of the rocket envelope (including any fin
    # span), then space the rest at a healthy fraction of r_max so each
    # lane is visually distinct.
    base_offset = r_max + max(0.05, 0.20 * r_max)
    lane_step = max(0.035, 0.20 * r_max)

    duplicate_seen: set[int] = set()
    for p, side, lane in _assign_label_lanes(rocket, n_lanes=n_lanes):
        # If two placements share the same component object (e.g. four
        # fins of the same TrapezoidalFins instance), label only once —
        # the legend already groups them by assembly colour.
        comp_id = id(p.component)
        if comp_id in duplicate_seen:
            continue
        duplicate_seen.add(comp_id)

        x0, x1, y_top, y_bot = _placement_extent(rocket, p)
        x_center = 0.5 * (x0 + x1)
        if side > 0:
            y_target = max(y_top, 0.0) + 0.004
            y_text = base_offset + lane * lane_step
            rotation = 30.0
            ha, va = 'left', 'bottom'
        else:
            y_target = min(y_bot, 0.0) - 0.004
            y_text = -(base_offset + lane * lane_step)
            rotation = -30.0
            ha, va = 'left', 'top'

        comp_name = getattr(p.component, 'name', type(p.component).__name__)
        ax.annotate(
            comp_name,
            xy=(x_center, y_target),
            xytext=(x_center, y_text),
            fontsize=opts['label_fontsize'],
            color=ANNOTATION_COLOR,
            ha=ha,
            va=va,
            rotation=rotation,
            rotation_mode='anchor',
            arrowprops=dict(
                arrowstyle='-',
                color=ANNOTATION_COLOR,
                alpha=0.5,
                linewidth=0.6,
                shrinkA=2.0,
                shrinkB=2.0,
            ),
        )

    # Expand y limits to accommodate the outermost lane plus a margin
    # for the rotated text bounding box.
    y_pad = 0.10
    y_lim = base_offset + (n_lanes - 1) * lane_step + y_pad
    ax.set_ylim(-y_lim, y_lim)

    # Wing cross-section inset (bottom-left). Overlay root and tip
    # stations of every TrapezoidalFins / Wing in the rocket.
    if opts['show_inset']:
        wings = [p for p in rocket.placements
                 if isinstance(p.component, (TrapezoidalFins, Wing))]
        if wings:
            color_map = _assembly_color_map(rocket, palette=opts['palette'])
            inset = ax.inset_axes(opts['inset_rect'])
            seen_components = set()
            for p in wings:
                comp = p.component
                if id(comp) in seen_components:
                    continue
                seen_components.add(id(comp))
                color = color_map.get(getattr(p, 'assembly_name', ''), '#7f7f7f')
                span_max = float(getattr(comp, 'height', 0.0)) or float(
                    getattr(comp, 'span', 0.0)
                )
                if span_max <= 0.0:
                    continue
                stations = np.linspace(0.0, span_max, 4)
                for sp in stations:
                    comp.plot_cross_section(
                        float(sp),
                        ax=inset,
                        options={
                            'label': None,
                            'align_le': False,
                            'y_offset': float(sp),
                            'alpha': 0.55,
                            'color': color,
                        },
                    )
            inset.set_aspect('equal')
            inset.set_title(
                'Wing cross sections', fontsize=opts['label_fontsize']
            )
            inset.tick_params(labelsize=max(6, opts['label_fontsize'] - 2))
            inset.set_xlabel(
                'chord (m)', fontsize=max(6, opts['label_fontsize'] - 1)
            )
            inset.set_ylabel(
                'span (m)', fontsize=max(6, opts['label_fontsize'] - 1)
            )
            inset.grid(True, alpha=0.3)
            inset.set_facecolor((1.0, 1.0, 1.0, 0.92))

    # Legend (re-issued so it sits above any annotation lanes that creep
    # to the right edge).
    handles = [
        plt.Line2D([0], [0], color=_assembly_color_map(rocket, palette=opts['palette'])[name],
                   linewidth=8, alpha=opts['external_alpha'])
        for name in _ordered_assembly_names(rocket)
    ]
    labels = _ordered_assembly_names(rocket)
    ax.legend(handles, labels, loc='center left',
              bbox_to_anchor=(1.02, 0.5), frameon=False, title='Assemblies')

    fig.subplots_adjust(right=0.82)

    if opts['show']:
        plt.show()
    return fig, ax


if __name__ == '__main__':
    from settings import Settings

    json_path = Settings.ROOT_DIR / "JSON" / "GalahDP.json"
    config = json.loads(json_path.read_text())

    rocket = build_rocket(config)

    print(f"Total length : {rocket.total_length:.3f} m")
    print(f"Mass         : {rocket.mass:.3f} kg")
    print(f"CG (axial)   : {rocket.cg:.3f} m from tip")
    Xcg, Ycg, Zcg = rocket.cg_xyz
    print(f"CG xyz       : ({Xcg:+.4f}, {Ycg:+.4e}, {Zcg:+.4e}) m")
    print(f"I_lateral    : {rocket.I_lateral:.6f} kg.m^2")
    print(f"I_axial      : {rocket.I_axial:.6f} kg.m^2")
    print(f"# placements : {len(rocket.placements)}")
    for p in rocket.placements:
        print(
            f"    {type(p.component).__name__:24s}  "
            f"x={p.x:+.3f}  y={p.y:+.3f}  eta={p.eta:+.3f}  "
            f"name={p.component.name!r}"
        )

    # ----------------------------------------------------------------
    # Builder-driven side views: per-assembly colour, internal alpha,
    # outside legend. The detail variant adds component callouts and
    # an inset of the wing cross sections.
    # ----------------------------------------------------------------
    import os
    save_dir = os.environ.get("CAD_PLOT_DIR")

    fig1, _ = plot_rocket(rocket, options={"show": save_dir is None})
    fig2, _ = plot_rocket_detail(rocket, options={"show": save_dir is None})
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        # No bbox_inches='tight': honour the requested figsize so the
        # detail view has real vertical room for callouts.
        fig1.savefig(os.path.join(save_dir, "rocket_overview.png"), dpi=130)
        fig2.savefig(os.path.join(save_dir, "rocket_detail.png"), dpi=130)
        print(f"saved plots to {save_dir}")
