"""
Plotting palette and style helpers.

The palette is a small set of distinguishable colours used to colour
each assembly of a rocket distinctly in :mod:`solvers.cad_1d.builder`'s
``plot_rocket`` / ``plot_rocket_detail``. Order is chosen for visual
contrast between adjacent slots, so a rocket's nose-to-tail assembly
sequence cycles through colours that read clearly side-by-side.

``ASSEMBLY_PALETTE`` is the canonical ordered list. Use
:func:`color_for_assembly` to pick a colour from it by index (with
modulo, so longer rocket compositions cycle round); or build your own
``{assembly_name: colour}`` map and pass it to ``plot_rocket``.
"""


ASSEMBLY_PALETTE: tuple[str, ...] = (
    "#1f77b4",   # steel blue        (nosecone-ish)
    "#d62728",   # crimson           (forward bay)
    "#2ca02c",   # mid green         (avionics)
    "#ff7f0e",   # vivid orange      (recovery)
    "#9467bd",   # muted violet      (payload)
    "#17becf",   # cyan              (tank bay)
    "#bcbd22",   # olive             (engine bay)
    "#8c564b",   # umber             (boattail)
    "#e377c2",   # pink              (canards)
    "#7f7f7f",   # neutral grey      (rail buttons)
    "#393b79",   # navy              (fin can)
    "#637939",   # forest            (fallback)
)


# Wireframe / annotation colours — used by plot_rocket_detail for grid,
# centerline, and arrow text.
GRID_COLOR = "#cfd2d4"
CENTERLINE_COLOR = "#8a8a8a"
ANNOTATION_COLOR = "#222222"


# Alpha conventions for the rocket plots. Internal (inner) components
# are drawn slightly translucent to suggest they live inside an outer
# tube; everything else is fully opaque.
EXTERNAL_ALPHA = 1.0
INTERNAL_ALPHA = 0.8


def color_for_assembly(index: int) -> str:
    """Return the palette colour for the assembly at position ``index``."""
    return ASSEMBLY_PALETTE[index % len(ASSEMBLY_PALETTE)]
