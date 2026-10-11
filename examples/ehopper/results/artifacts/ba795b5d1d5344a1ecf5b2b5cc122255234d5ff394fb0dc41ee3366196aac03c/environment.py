"""Explicit environment and nonpropulsive-load interface for PDR-R12.

Authorization: 66c7448f443f44ac9a016a1b384593a2 revision 1.
Audit: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 revision 1.
Caller reconciliation: PDR-R12-PLANT-CALLER-RECONCILIATION-02 revision 1.
Frame contract: f046cc4fe5294a6f9a61027529056f61 revision 1.
Gimbal contract: 28e10be57d6548a3aa5be06c96f6d0d0 revision 1.

Reconciled from the recovered r9 simulation/environment.py inspected in
reader 2b75af1479394623b11026be2eec2f9a revision 1. Original checkouts and
historical outputs remain unchanged.

Affected callers: Simulation.evaluate, fixture environment construction,
and PrescribedFixtureEnvironment.sample. Simulation must request a sample
at actual separated-origin hub locations, then calculate air-relative hub
velocities using the same State, MassProperties and AssemblyKinematics.

No legacy cylindrical Aerodynamics model is imported or implicitly selected.
This module supplies contracts, not a calibrated environmental, battery,
thermal or contact model. Writing it is not verification or acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
from ..helpers.math import finite_array
from ..propulsion.propulsion import AppliedLoad, CoaxialConditions
from .state import State


ENVIRONMENT_SCHEMA = 'pdr_r12_explicit_environment_external_loads_v1'


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def _scalar(value, name, *, positive=False, nonnegative=False):
    number = float(value)
    if not np.isfinite(number):
        raise ValueError(f'{name} must be finite')
    if positive and number <= 0.0:
        raise ValueError(f'{name} must be positive')
    if nonnegative and number < 0.0:
        raise ValueError(f'{name} must be nonnegative')
    return number


@dataclass(frozen=True, slots=True)
class EnvironmentSample:
    """Immutable environmental/electrical inputs at one evaluation instant.

    L is launch-ground NED. Uniform gravity is [0,0,+gravity_m_s2] in L
    and contributes no net moment about instantaneous complete-vehicle G.
    Zero gravity is permitted only for explicitly labelled analytical tests.

    hub_positions_L_m and wind_at_hubs_L_m_s are ordered [U,L], each with
    shape (2,3). U/L identify components at neutral and persist through
    articulation. Echo the exact hub positions requested by Simulation;
    this enables rejection of samples evaluated at different locations.
    Wind is AMBIENT air velocity in L, not air-relative vehicle velocity,
    induced disk flow or an assumed common velocity for both hubs.
    The simultaneous propulsion map owns its wake/interference treatment.

    bus_voltage_V is actual shared terminal voltage, not nominal battery
    voltage. auxiliary_bus_current_A includes gimbal actuators, avionics
    and other nonpropulsion consumers, referred to this same bus including
    regulator losses. It excludes both motor/ESC branch currents. Complete
    battery current sums these three contributions exactly once.

    Prescribed voltage, SOC and temperatures are acceptable fixture inputs,
    not a battery-sag or thermal-evolution solution. A vehicle provider must
    reconcile terminal voltage with simultaneous propulsion/auxiliary load.
    Additional electrical dynamic states require an explicit state-schema
    extension, not hidden mutable provider history.

    additional_external_loads contains ONLY nonpropulsive external point
    forces/free couples with explicit provenance, such as an exposed-frame
    aerodynamic model. Points use body FRD coordinates relative to O_B0;
    free couples exclude application-point cross products. Do not include
    uniform gravity, a duplicate rotor wrench or internal motor/servo
    reactions. Simulation resolves each point force about current G once.

    An empty additional-load sequence deliberately omits these effects; it
    does not prove their physical absence. nonpropulsive_load_model and
    limitations must identify the approximation. Calm ambient conditions
    alone do not establish negligible rotor-wake or rotational loads.
    Contact, leg deformation and touchdown validity are not supplied here.
    """

    gravity_m_s2: float
    air_density_kg_m3: float
    hub_positions_L_m: tuple
    wind_at_hubs_L_m_s: tuple
    bus_voltage_V: float
    auxiliary_bus_current_A: float
    state_of_charge: float
    motor_temperature_K: tuple[float, float]
    esc_temperature_K: tuple[float, float]
    battery_temperature_K: float
    additional_external_loads: tuple[AppliedLoad, ...]
    model_scope: str
    electrical_model: str
    nonpropulsive_load_model: str
    provenance: str
    limitations: tuple[str, ...]

    def __post_init__(self):
        if self.model_scope not in MODEL_SCOPES:
            raise ValueError('Unknown model_scope')
        gravity = _scalar(self.gravity_m_s2, 'gravity_m_s2', nonnegative=True)
        if self.model_scope != 'analytical_fixture' and gravity == 0.0:
            raise ValueError('Zero gravity is restricted to analytical fixtures')
        object.__setattr__(self, 'gravity_m_s2', gravity)
        for name in ('air_density_kg_m3', 'bus_voltage_V', 'battery_temperature_K'):
            object.__setattr__(self, name, _scalar(
                getattr(self, name), name, positive=True,
            ))
        object.__setattr__(self, 'auxiliary_bus_current_A', _scalar(
            self.auxiliary_bus_current_A, 'auxiliary_bus_current_A',
            nonnegative=True,
        ))
        soc = _scalar(self.state_of_charge, 'state_of_charge')
        if not 0.0 <= soc <= 1.0:
            raise ValueError('state_of_charge must be in [0,1]')
        object.__setattr__(self, 'state_of_charge', soc)
        for name in ('hub_positions_L_m', 'wind_at_hubs_L_m_s'):
            values = finite_array(getattr(self, name), (2, 3), name)
            object.__setattr__(self, name, tuple(
                tuple(float(x) for x in row) for row in values
            ))
        for name in ('motor_temperature_K', 'esc_temperature_K'):
            values = finite_array(getattr(self, name), (2,), name)
            if np.any(values <= 0.0):
                raise ValueError(f'{name} must contain positive kelvin temperatures')
            object.__setattr__(self, name, tuple(float(x) for x in values))
        loads = tuple(self.additional_external_loads)
        if not all(isinstance(load, AppliedLoad) for load in loads):
            raise TypeError('Additional external loads must be AppliedLoad records')
        if any(load.model_scope != self.model_scope for load in loads):
            raise ValueError('Environment and additional-load scopes differ')
        object.__setattr__(self, 'additional_external_loads', loads)
        for name in ('electrical_model', 'nonpropulsive_load_model', 'provenance'):
            _text(getattr(self, name), name)
        if isinstance(self.limitations, str):
            raise TypeError('limitations must be a sequence of strings')
        limitations = tuple(_text(item, 'limitation') for item in self.limitations)
        if not limitations:
            raise ValueError('Explicit environment/model limitations are required')
        object.__setattr__(self, 'limitations', limitations)

    def coaxial_conditions(self, *, rotor_axial_spacing_m,
                           rotor_velocity_relative_air_M_m_s):
        """Build paired operating conditions from this same immutable sample.

        Simulation supplies spacing from actual CoaxialGeometry and hub
        velocities computed from actual rigid-body and actuator states,
        current CG/CG-rate, separated-origin geometry and sampled wind.
        Commanded angles/speeds are not substitutes for those actual states.

        Auxiliary current is NOT part of the preliminary CoaxialConditions
        schema. Its battery-current domain flag therefore cannot establish
        complete-vehicle electrical feasibility. Complete electrical closure
        and its checker must separately account for auxiliary demand.
        """
        return CoaxialConditions(
            air_density_kg_m3=self.air_density_kg_m3,
            bus_voltage_V=self.bus_voltage_V,
            rotor_axial_spacing_m=rotor_axial_spacing_m,
            rotor_velocity_relative_air_M_m_s=rotor_velocity_relative_air_M_m_s,
            state_of_charge=self.state_of_charge,
            motor_temperature_K=self.motor_temperature_K,
            esc_temperature_K=self.esc_temperature_K,
            battery_temperature_K=self.battery_temperature_K,
            model_scope=self.model_scope,
            provenance=self.provenance,
        )

    def total_bus_current_A(self, rotor_bus_current_A):
        """Sum paired motor/ESC branches and auxiliary bus demand once.

        Arithmetic accounting only: this does not check a battery current
        rating, model sag or establish winding-current/thermal feasibility.
        Regeneration is outside this preliminary powered-lift contract.
        """
        currents = finite_array(rotor_bus_current_A, (2,), 'rotor_bus_current_A')
        if np.any(currents < 0.0):
            raise ValueError('Regeneration is outside this preliminary contract')
        with np.errstate(over='raise', invalid='raise'):
            total = self.auxiliary_bus_current_A + float(np.sum(currents))
        return _scalar(total, 'total_bus_current_A', nonnegative=True)

    def total_bus_power_W(self, rotor_bus_current_A):
        """Instantaneous shared-bus power, not integrated mission energy.

        Integrate energy using explicit states or accepted-time quadrature,
        never by accumulating adaptive RHS evaluations or their call count.
        """
        power = self.bus_voltage_V * self.total_bus_current_A(rotor_bus_current_A)
        return _scalar(power, 'total_bus_power_W', nonnegative=True)


class EnvironmentProvider(Protocol):
    """Pure provider evaluated at actual hub locations and instantaneous G.

    Repeated identical arguments must produce identical samples regardless
    of evaluation order. Adaptive ODE methods may revisit times, reject
    steps and evaluate intermediate trial states. Do not evolve energy,
    thermal states, PID memory or noise generators by subtracting a saved
    previous time or counting calls.

    Simulation supplies an owned (2,3) hub-position array:
      p_hub_i,L = p_G,L + R_LB (r_B0,i - r_B0,G).
    r_B0,i follows the actual separated-origin common-gimbal geometry.
    Do not mutate the array; echo its values in EnvironmentSample.

    Any aerodynamic, disturbance or contact load requires a named model,
    explicit application point and applicability limitations. This protocol
    does not make the original cylinder model suitable for the exposed
    structure, and does not supply a dynamically coupled electrical solver.
    """

    def sample(self, *, time_s: float, state: State,
               mass_properties: MassProperties,
               kinematics: AssemblyKinematics,
               hub_positions_L_m: np.ndarray) -> EnvironmentSample:
        ...
