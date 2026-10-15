# Remaining source inspection excerpts

Model r4. Returned text must be reviewed; inclusion is not inspection acceptance.

## original_hopper/main.py
Origin: /home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/main.py
SHA256: 67ebbf79c219721eb1f0cc6e4817b8fb218488b6dec4bbd25a1f0faee6527dbc
UTF-8 text character interval [0,89); total characters 89.
```python
def main():
    print("Hello from 6dof-hopper!")


if __name__ == "__main__":
    main()

```
Complete text returned.

## original_hopper/aero/aero.py
Origin: /home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/aero/aero.py
SHA256: 9008c26ea2c2c26e1e26441ee17f27872e1d34bf1c0d9cb7179ce285d6e2b53f
UTF-8 text character interval [0,8596); total characters 8596.
```python
import numpy as np


class Aerodynamics:
    def __init__(self, hopper):
        self.hopper = hopper

    def determine_at_point(
        self,
        air_velocity_body,
        angular_rates_body,
        density,
        dynamic_viscosity,
        speed_of_sound,
        cg,
        inner_diameter=0,
        tube_axis_body=(1, 0, 0),
        closed_front=True,
        front_pressure_cd=0.8,
    ):
        """
        Calculate aerodynamic force and moment of a cylindrical tube.

        Uses:
            OpenRocket equation 3.26 for cylindrical body lift
            OpenRocket equation 3.58 for pitch/yaw damping
            OpenRocket equations 3.78, 3.82-3.85 for skin friction

        Assumptions:
            - air_velocity_body is vehicle velocity relative to air
            - all vectors are expressed in body coordinates
            - body +x is normally the tube longitudinal axis
            - force and moment are returned in body coordinates
            - tube is circular and axisymmetric

        Parameters
        ----------
        air_velocity_body : array_like, shape (3,)
            Vehicle velocity relative to air in body coordinates [m/s].

        angular_rates_body : array_like, shape (3,)
            Body angular rates [p, q, r] in body coordinates [rad/s].

        density : float
            Air density [kg/m^3].

        dynamic_viscosity : float
            Dynamic viscosity [Pa.s].

        speed_of_sound : float
            Local speed of sound [m/s].

        tube_length : float
            Tube length [m].

        outer_diameter : float
            Tube outer diameter [m].

        tube_center_body : array_like, shape (3,)
            Tube geometric-centre position relative to the body datum [m].

        cg_body : array_like, shape (3,)
            Vehicle CG position relative to the same body datum [m].

        inner_diameter : float
            Tube inner diameter [m].

        tube_axis_body : array_like, shape (3,)
            Unit vector along the tube longitudinal axis.

        closed_front : bool
            If True, use the full circular frontal area.
            If False, use the annular tube-wall area.

        front_pressure_cd : float
            Pressure-drag coefficient of the front face.
            OpenRocket gives approximately 0.8 for a flat blunt face.

        Returns
        -------
        force_body : ndarray, shape (3,)
            Total tube aerodynamic force [N].

        moment_body : ndarray, shape (3,)
            Total tube aerodynamic moment about the vehicle CG [N.m].
        """

        epsilon = 1e-10

        velocity = np.asarray(air_velocity_body, dtype=float)
        omega = np.asarray(angular_rates_body, dtype=float)
        tube_center = np.asarray(
            self.hopper.tube_center_body,
            dtype=float,
        )
        cg = np.asarray(cg, dtype=float)

        tube_axis = np.asarray(tube_axis_body, dtype=float)
        axis_norm = np.linalg.norm(tube_axis)

        if axis_norm < epsilon:
            raise ValueError("tube_axis_body cannot be a zero vector")

        tube_axis /= axis_norm

        air_speed = np.linalg.norm(velocity)

        if air_speed < epsilon:
            return np.zeros(3), np.zeros(3)

        dynamic_pressure = 0.5 * density * air_speed**2

        # Vector from vehicle CG to the tube centre/CP.
        r_cp = tube_center - cg

        # ------------------------------------------------------------------
        # Resolve airflow into axial and transverse components
        # ------------------------------------------------------------------

        axial_velocity_scalar = np.dot(velocity, tube_axis)

        axial_velocity = axial_velocity_scalar * tube_axis

        crossflow_velocity = velocity - axial_velocity
        crossflow_speed = np.linalg.norm(crossflow_velocity)

        # ------------------------------------------------------------------
        # Cylindrical body normal force: OpenRocket equation 3.26
        #
        # CN = K (D L / Aref) sin(alpha)^2
        # N  = q Aref CN
        #
        # K approximately 1.1
        # ------------------------------------------------------------------

        normal_force = np.zeros(3)

        if crossflow_speed > epsilon:
            sin_alpha = np.clip(crossflow_speed / air_speed, 0, 1)

            normal_force_magnitude = (
                dynamic_pressure
                * 1.1
                * self.hopper.outer_diameter
                * self.hopper.length
                * sin_alpha**2
            )

            normal_force = (
                -normal_force_magnitude * crossflow_velocity / crossflow_speed
            )

        static_moment = np.cross(r_cp, normal_force)

        # ------------------------------------------------------------------
        # Axial skin-friction drag
        # OpenRocket equations 3.78 and 3.82-3.85
        # ------------------------------------------------------------------

        axial_force = np.zeros(3)

        axial_speed = abs(axial_velocity_scalar)

        if axial_speed > epsilon:
            reynolds = density * axial_speed * self.hopper.length / dynamic_viscosity

            if reynolds < 1e4:
                skin_friction_coefficient = 1.48e-2
            else:
                skin_friction_coefficient = 1 / (1.5 * np.log(reynolds) - 5.6) ** 2

            mach = axial_speed / speed_of_sound

            # Compressibility correction
            if mach < 1:
                corrected_skin_friction = skin_friction_coefficient * (
                    1 - 0.1 * mach**2
                )
            else:
                corrected_skin_friction = (
                    skin_friction_coefficient / (1 + 0.15 * mach**2) ** 0.58
                )

            wetted_area = np.pi * self.hopper.outer_diameter * self.hopper.length

            fineness_ratio = self.hopper.length / self.hopper.outer_diameter

            body_shape_correction = 1 + 1 / (2 * fineness_ratio)

            axial_dynamic_pressure = 0.5 * density * axial_speed**2

            skin_friction_drag = (
                axial_dynamic_pressure
                * corrected_skin_friction
                * body_shape_correction
                * wetted_area
            )

            # Frontal pressure drag
            if closed_front:
                frontal_area = np.pi * self.hopper.outer_diameter**2 / 4
            else:
                frontal_area = (
                    np.pi
                    * (self.hopper.outer_diameter**2 - self.hopper.inner_diameter**2)
                    / 4
                )

            pressure_drag = axial_dynamic_pressure * front_pressure_cd * frontal_area

            total_axial_drag = skin_friction_drag + pressure_drag

            # Oppose the axial component of motion.
            axial_direction = np.sign(axial_velocity_scalar) * tube_axis

            axial_force = -total_axial_drag * axial_direction

        axial_moment = np.cross(r_cp, axial_force)

        # ------------------------------------------------------------------
        # Pitch/yaw damping: analytical form of OpenRocket equation 3.58
        # ------------------------------------------------------------------

        omega_axial = np.dot(omega, tube_axis) * tube_axis

        omega_transverse = omega - omega_axial
        omega_transverse_magnitude = np.linalg.norm(omega_transverse)

        damping_moment = np.zeros(3)

        if omega_transverse_magnitude > epsilon:
            # Tube-end positions measured longitudinally from the CG.
            tube_center_from_cg = np.dot(r_cp, tube_axis)

            first_end = tube_center_from_cg - self.hopper.length / 2

            second_end = tube_center_from_cg + self.hopper.length / 2

            # Integral of |x|^3 dx over the complete tube.
            distance_integral = (
                second_end * abs(second_end) ** 3 - first_end * abs(first_end) ** 3
            ) / 4

            damping_coefficient = (
                0.5 * density * 1.1 * self.hopper.outer_diameter * distance_integral
            )

            damping_moment = (
                -damping_coefficient * omega_transverse_magnitude * omega_transverse
            )

        # ------------------------------------------------------------------
        # Total force and moment about vehicle CG
        # ------------------------------------------------------------------

        force_body = normal_force + axial_force

        moment_body = static_moment + axial_moment + damping_moment

        return force_body, moment_body

```
Complete text returned.

## original_hopper/helpers/constants.py
Origin: /home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/helpers/constants.py
SHA256: 4853ae63f4d7df5254af6fbab9b46dd31ca60aa722dd3580643064bfce9523a4
UTF-8 text character interval [0,17); total characters 17.
```python
GRAVITY = 9.8065

```
Complete text returned.

## original_hopper/scripts/ehopper.py
Origin: /home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/scripts/ehopper.py
SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
UTF-8 text character interval [0,0); total characters 0.
```python

```
Complete text returned.

## original_hopper/test/__init__.py
Origin: /home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/test/__init__.py
SHA256: d72bcd69d0ed6d706e690574d1dbdedf15ab740d5ce705aad834bd1b91b3d76e
UTF-8 text character interval [0,28); total characters 28.
```python
"""Project test modules."""

```
Complete text returned.

## original_hopper/test/test_pythrust.py
Origin: /home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/test/test_pythrust.py
SHA256: a3590eef1c8b2d922a54464d7254205ca046c4af4e42f4bde815a67cec690a0d
UTF-8 text character interval [0,3924); total characters 3924.
```python
"""Minimal PyThrust test: thrust from RPM or commanded voltage.

Run this from the PyThrust repository root after: python -m pip install -e .
"""

import math
from pathlib import Path
import sys

PYTHRUST_ROOT = Path(__file__).resolve().parents[1] / "PyThrust"
sys.path.insert(0, str(PYTHRUST_ROOT))

from pythrust.battery import FixedVoltageBattery
from pythrust.propellers import PropellerDatabase
from pythrust.propulsion import MotorSpec, PropellerSpec, PropulsionSolver, SystemSpec

# =============================================================================
# EDIT THESE INPUTS
# =============================================================================

PROPELLER_ID = "APC_13x6.5E"

MOTOR_KV_RPM_PER_V = 860.0
MOTOR_RESISTANCE_OHM = 0.0258
MOTOR_NO_LOAD_CURRENT_A = 1.3
MOTOR_MAX_CURRENT_A = 65.0

BATTERY_VOLTAGE_V = 14.8
SYSTEM_RESISTANCE_OHM = 0.05  # ESC + battery + wires + connectors

AIR_DENSITY_KG_M3 = 1.225
AIRSPEED_MPS = 0.0  # 0.0 for a static/hover test


# =============================================================================
# INITIALISE PYTHRUST
# =============================================================================

propeller_database = PropellerDatabase()
propeller_database.load(
    PYTHRUST_ROOT / "data/propellers/apc_202602",
    strict=False,
)

propeller_data = propeller_database.get(PROPELLER_ID)
if propeller_data is None:
    raise KeyError(f"Could not find propeller data for {PROPELLER_ID}")

motor = MotorSpec(
    kv_rpm_per_v=MOTOR_KV_RPM_PER_V,
    resistance_ohm=MOTOR_RESISTANCE_OHM,
    no_load_current_a=MOTOR_NO_LOAD_CURRENT_A,
    current_max_a=MOTOR_MAX_CURRENT_A,
)

battery = FixedVoltageBattery(voltage_v=BATTERY_VOLTAGE_V)
electrical_system = SystemSpec(resistance_ohm=SYSTEM_RESISTANCE_OHM)
propeller = PropellerSpec(
    diameter_m=propeller_data.diameter_m,
    pitch_m=propeller_data.pitch_m,
    blade_count=propeller_data.metadata.blade_count,
)
solver = PropulsionSolver()


# =============================================================================
# CALL THESE TWO FUNCTIONS
# =============================================================================


def results_at_rpm(rpm: float) -> dict:
    """Return propeller thrust and torque at a prescribed RPM."""
    if rpm <= 0.0:
        return {"rpm": 0.0, "thrust_n": 0.0, "torque_nm": 0.0}

    n = rpm / 60.0
    diameter = propeller.diameter_m
    advance_ratio = AIRSPEED_MPS / (n * diameter)
    ct, cp = propeller_data.get_coefficients(rpm, advance_ratio)

    thrust_n = ct * AIR_DENSITY_KG_M3 * n**2 * diameter**4
    torque_nm = cp * AIR_DENSITY_KG_M3 * n**2 * diameter**5 / (2.0 * math.pi)

    return {
        "rpm": rpm,
        "thrust_n": thrust_n,
        "torque_nm": torque_nm,
    }


def results_at_voltage(commanded_voltage_v: float) -> dict:
    """Return equilibrium RPM, thrust and current for an ESC voltage command."""
    if not 0.0 <= commanded_voltage_v <= BATTERY_VOLTAGE_V:
        raise ValueError(f"Voltage must be between 0 and {BATTERY_VOLTAGE_V} V")

    if commanded_voltage_v == 0.0:
        return {
            "commanded_voltage_v": 0.0,
            "rpm": 0.0,
            "thrust_n": 0.0,
            "motor_current_a": 0.0,
            "feasible": True,
        }

    point = solver.solve_operating_point(
        motor=motor,
        battery=battery,
        system=electrical_system,
        propeller=propeller,
        prop_entry=propeller_data,
        rho=AIR_DENSITY_KG_M3,
        airspeed_mps=AIRSPEED_MPS,
        throttle=commanded_voltage_v / BATTERY_VOLTAGE_V,
    )

    return {
        "commanded_voltage_v": commanded_voltage_v,
        "rpm": point.rpm,
        "thrust_n": point.thrust_n,
        "motor_current_a": point.motor_current_a,
        "feasible": point.is_feasible,
    }


if __name__ == "__main__":
    print("At 6000 RPM:", results_at_rpm(6000.0))
    print("At 10 V:", results_at_voltage(10.0))

```
Complete text returned.

