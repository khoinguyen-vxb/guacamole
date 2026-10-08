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
