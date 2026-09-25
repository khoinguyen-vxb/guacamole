import matplotlib.pyplot as plt


def simple_2d_component_plot(x_values, y_upper, y_lower, options: dict = None):
    """
    Args:
        x_values: numpy linspace to discretize the space
              eg: xs = np.linspace(0, bt.boattail_length, 300)

        y_upper: callable y_upper(x) -> radius, the outer profile
        y_lower: callable y_lower(x) -> radius, the inner / bottom profile
                 (returns 0 for solid components — y_lower encodes the wall
                 thickness, so this helper does not take a wall_thickness option)

        options keys (all optional):
            show   : bool  — call plt.show() at the end (default True).
                             Ignored when ``ax`` is supplied — the caller
                             drives the figure lifecycle.
            title  : str   — plot title (default "Component Profile").
                             Ignored when ``ax`` is supplied.
            xlabel : str   — x-axis label. Ignored when ``ax`` is supplied.
            ylabel : str   — y-axis label. Ignored when ``ax`` is supplied.
            color  : str   — line / fill colour
            alpha  : float — fill alpha (default 1.0). Useful when several
                             components share an ``ax`` and need to be
                             visually distinguished.
            ax     : matplotlib Axes — if supplied, draw onto this axes
                             instead of creating a new figure. The caller
                             is then responsible for title, labels,
                             aspect, grid, and show().

    Returns: fig, ax
    """

    opts = {
        "show": True,
        "title": "Component Profile",
        "xlabel": "x (m)",
        "ylabel": "radius (m)",
        "color": "darkviolet",
        "alpha": 1.0,
        "ax": None,
    }
    if options:
        opts.update(options)

    yu = [y_upper(x) for x in x_values]
    yl = [y_lower(x) for x in x_values]
    color = opts["color"]
    alpha = opts["alpha"]

    own_axes = opts["ax"] is None
    if own_axes:
        fig, ax = plt.subplots()
    else:
        ax = opts["ax"]
        fig = ax.figure

    # Line and fill are drawn at the SAME alpha so the component reads as a
    # single solid shape rather than an outlined hull. This keeps the visual
    # thickness of thin parts (skins, fin wedges) honest — a fully-opaque
    # stroke around a translucent fill would otherwise dominate when the
    # wall is much thinner than the line width.
    ax.fill_between(x_values, yl, yu, color=color, alpha=alpha, linewidth=0)
    ax.fill_between(
        x_values,
        [-y for y in yu],
        [-y for y in yl],
        color=color,
        alpha=alpha,
        linewidth=0,
    )

    if own_axes:
        ax.set_title(opts["title"])
        ax.set_xlabel(opts["xlabel"])
        ax.set_ylabel(opts["ylabel"])
        ax.set_aspect("equal")
        ax.grid(True)
        if opts["show"]:
            plt.show()
    return fig, ax
