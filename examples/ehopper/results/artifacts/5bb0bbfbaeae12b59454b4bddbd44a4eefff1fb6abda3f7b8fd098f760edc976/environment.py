"""Explicit environment and nonpropulsive-load interface for PDR-R9.

New supporting module for audited Simulation defects RC13/RC14.
Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.

The repaired Simulation caller must sample this provider using the actual
instantaneous hub positions, then calculate hub-relative air velocities
with Propellor.hub_velocities_relative_air_M_m_s. No legacy cylindrical
Aerodynamics implementation is imported or selected automatically.

This file supplies contracts, not vehicle parameters or concrete environment
models. A zero-load analytical fixture must explicitly identify omitted
loads; calm ambient air does not imply zero rotor-wake or rotational loads.
No numerical, hardware or mission acceptance is claimed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
from ..helpers.math import finite_array
from ..propulsion.propulsion import AppliedLoad, CoaxialConditions
from .state import State


ENVIRONMENT_SCHEMA = 'pdr_r9_explicit_environment_external_loads_v1'


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
    """Immutable environmental/electrical inputs at one plant evaluation.

    L is launch-ground NED. Uniform gravity acts as [0,0,+gravity_m_s2]
    in L and has no net moment about the instantaneous complete-vehicle CG.
    Zero gravity is permitted only for explicitly labelled analytical tests.

    hub_positions_L_m and wind_at_hubs_L_m_s have shape (2,3), ordered
    upper then lower. Wind is ambient air velocity in L, NOT hub-relative
    airspeed and NOT induced disk velocity. Echo the positions requested
    by Simulation so it can reject a sample for different hub locations.
    The paired propulsion map separately owns its induced-flow treatment.

    bus_voltage_V is actual shared terminal voltage. Auxiliary bus current
    includes tilt actuators, avionics and other nonpropulsion consumers,
    expressed on that same bus after any regulator losses. It excludes
    motor/ESC branches. Total battery current therefore needs the sum of
    auxiliary current and both propulsion branch currents exactly once.

    These electrical inputs may be prescribed for an analytical fixture.
    Supplying SOC and temperatures does not integrate their evolution or
    solve battery sag. A coupled electrical provider must reconcile voltage
    with simultaneous propulsion/auxiliary demand without RHS call-history
    dependence. Extra dynamic electrical states require a versioned extension
    of the plant state, not hidden mutable provider memory.

    additional_external_loads contains ONLY nonpropulsive external loads,
    such as explicitly modelled exposed-structure aerodynamic forces.
    Each application point is expressed in B relative to fixed O_B0, as
    required by AppliedLoad. Its free couple must not already contain r x F.
    Do not include uniform gravity, the separately evaluated rotor loads,
    internal servo/motor reactions, or a second copy of their moments.

    Empty additional loads are a deliberate modelling omission, not a
    demonstrated absence of aerodynamic/contact/disturbance loads. The
    nonpropulsive_load_model and limitations must identify that omission.
    Ground contact and touchdown validity are not provided by this contract.
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
            object.__setattr__(self, name,
                               tuple(tuple(float(x) for x in row) for row in values))
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
        """Build paired-map conditions from this same immutable sample.

        Simulation supplies spacing from actual CoaxialGeometry and hub
        velocities computed from its current state, mass properties,
        gimbal motion and this sample's ambient wind. Do not substitute
        commanded rotor/gimbal states or assumed zero hub velocities.

        Auxiliary load is NOT a field of the preliminary CoaxialConditions
        contract. Consequently its battery-current domain flag alone cannot
        establish complete-vehicle electrical feasibility. A later coupled
        provider/checker must include auxiliary current explicitly.
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
        """Arithmetic accounting only; no battery-current acceptance implied."""
        currents = finite_array(rotor_bus_current_A, (2,), 'rotor_bus_current_A')
        if np.any(currents < 0.0):
            raise ValueError('Regeneration is outside this preliminary contract')
        return _scalar(
            self.auxiliary_bus_current_A + float(np.sum(currents)),
            'total_bus_current_A', nonnegative=True,
        )

    def total_bus_power_W(self, rotor_bus_current_A):
        """Power on the common bus; not integrated mission energy/endurance."""
        return _scalar(
            self.bus_voltage_V * self.total_bus_current_A(rotor_bus_current_A),
            'total_bus_power_W', nonnegative=True,
        )


class EnvironmentProvider(Protocol):
    """Pure provider evaluated at actual hub locations and instantaneous G.

    Repeated identical arguments must yield identical samples. Adaptive
    integration may repeat times, evaluate trial states, reject steps and
    revisit earlier times. Do not integrate energy, thermal states, PID
    memory or noise generators by counting calls or subtracting last time.

    hub_positions_L_m is an owned (2,3) array supplied by Simulation:
      p_hub_i,L = p_G,L + R_LB * (r_B0i - r_B0G).
    Its contents must not be mutated. Return them in EnvironmentSample.

    Return aerodynamic/contact/disturbance loads only when an explicit
    model and its applicability are supplied. This protocol does not make
    the original cylinder model suitable for the exposed structure.
    """

    def sample(self, *, time_s: float, state: State,
               mass_properties: MassProperties,
               kinematics: AssemblyKinematics,
               hub_positions_L_m: np.ndarray) -> EnvironmentSample:
        ...
