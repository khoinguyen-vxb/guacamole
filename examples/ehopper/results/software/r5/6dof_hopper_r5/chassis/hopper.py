from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from propulsion.propulsion import Propulsion


@dataclass
class Hopper:
    """Mass properties and external geometry of the hopper."""

    propulsion: Propulsion
    cg: np.ndarray
    mass_wo_propellant: float
    moment_arm: np.ndarray
    Ixx: float
    Iyy: float
    Izz: float
    cd: float
    csa: float
    length: float
    outer_diameter: float
    inner_diameter: float = 0.0
    tube_center_body: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=float)
    )
    reference_length: Optional[float] = None

    def __post_init__(self):
        self.cg = np.asarray(self.cg, dtype=float)
        self.moment_arm = np.asarray(self.moment_arm, dtype=float)
        self.tube_center_body = np.asarray(
            self.tube_center_body,
            dtype=float,
        )

        for name in ("cg", "moment_arm", "tube_center_body"):
            if getattr(self, name).shape != (3,):
                raise ValueError(f"{name} must be a three-element vector")

        if self.reference_length is None:
            self.reference_length = self.length

    def mass(self, time: float) -> float:
        return self.mass_wo_propellant + self.propulsion.get_mass(time)

    def CG(self, time: float) -> np.ndarray:
        return self.cg.copy()

    def inertia(self, time: float) -> np.ndarray:
        return np.diag((self.Ixx, self.Iyy, self.Izz))

    def get_thrust_and_moment(
        self,
        time: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        return self.propulsion.get_thrust_and_moment(time)
