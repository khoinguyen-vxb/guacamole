"""Two actual engineering calculations, registered without a domain adapter.

uv run python examples/cross_domain.py
uv run python examples/cross_domain.py --mcp --workspace .guacamole/mcp
"""

import argparse
import asyncio
from pathlib import Path
from typing import Annotated

from pydantic import Field

from guacamole import Model, Project, ToolRegistry
from guacamole.tools.mcp import ToolSession, serve_stdio

type Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Deflection(Model):
    tip_m: float = Field(
        allow_inf_nan=False, description="Transverse tip displacement in m"
    )


def cantilever(
    force_n: float, length_m: Positive, youngs_pa: Positive, inertia_m4: Positive
) -> Deflection:
    """Euler-Bernoulli tip deflection for a slender cantilever with a transverse tip load."""
    return Deflection(tip_m=force_n * length_m**3 / (3 * youngs_pa * inertia_m4))


def temperature_rise(power_w: Positive, resistance_k_w: Positive) -> float:
    """Steady temperature rise in kelvin for a lumped thermal resistance."""
    return power_w * resistance_k_w


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp", action="store_true")
    parser.add_argument(
        "--workspace", type=Path, default=Path(".guacamole/cross-domain")
    )
    args = parser.parse_args()
    tools = ToolRegistry()
    beam = tools.register(cantilever, tags=("structures",), retry_safe=True)
    thermal = tools.register(temperature_rise, tags=("thermal",), retry_safe=True)
    with Project(args.workspace, tools=tools) as project:
        if args.mcp:
            await serve_stdio(ToolSession(project))
        else:
            print(
                await project.call(
                    beam,
                    {
                        "force_n": 10.0,
                        "length_m": 2.0,
                        "youngs_pa": 200e9,
                        "inertia_m4": 1e-6,
                    },
                )
            )
            print(await project.call(thermal, {"power_w": 20.0, "resistance_k_w": 0.5}))


if __name__ == "__main__":
    asyncio.run(main())
