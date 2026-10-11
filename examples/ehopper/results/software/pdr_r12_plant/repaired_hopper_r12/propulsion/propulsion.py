"""Explicit propulsion/load contracts for the preliminary PDR-R12 plant.

Authorization: 66c7448f443f44ac9a016a1b384593a2 revision 1.
Audit: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 revision 1.
Caller reconciliation: PDR-R12-PLANT-CALLER-RECONCILIATION-02 revision 1.
Frame contract: f046cc4fe5294a6f9a61027529056f61 revision 1.
Gimbal contract: 28e10be57d6548a3aa5be06c96f6d0d0 revision 1.

Original propulsion/propulsion.py SHA-256:
e07b895d8399016a3b0511afb195d7ebf992050cef04ab3015600347f01750ce
Recovered r9 propulsion/propulsion.py SHA-256:
930f02ef368640a533ced862ff1868b7a11166698c90d57fc2214393207e6a60
Both sources remain unchanged. This module reconciles the inspected r9
interface into the separate r12 package; writing it is not verification.

Migration affecting Propellor, Hopper, Simulation and fixture providers:
  * Replace the incomplete mass/CG/time-only propulsion ABC with evaluate.
  * Installed mass belongs exclusively to Hopper's complete vehicle ledger.
  * Evaluate the coupled pair at ACTUAL rotor/gimbal states, not commands.
  * Return explicit external point forces and aerodynamic free couples.
  * Resolve each load about the SAME instantaneous complete-vehicle CG once.
  * Obtain application points from actual separated-origin gimbal geometry.
  * Internal motor/servo reactions are not additional external moments.

No vehicle parameters, isolated-thrust doubling, calibrated map, hardware
selection, numerical pass or physical acceptance is supplied here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
from ..helpers.math import finite_array


PROPULSION_SCHEMA = 'pdr_r12_external_coaxial_loads_v1'
REQUIRED_DOMAIN_CHECKS = (
    'coaxial_map_domain',
    'rotor_speed',
    'bus_voltage',
    'motor_current',
    'esc_current',
    'battery_current',
    'motor_thermal',
    'esc_thermal',
    'battery_thermal',
)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def _scope(value):
    if value not in MODEL_SCOPES:
        raise ValueError('Unknown model_scope')
    return value


def _scalar(value, name, *, positive=False):
    number = float(value)
    if not np.isfinite(number) or (positive and number <= 0.0):
        raise ValueError(f'Invalid {name}')
    return number


def _vector(value, size, name, *, nonnegative=False, positive=False):
    array = finite_array(value, (size,), name)
    if nonnegative and np.any(array < 0.0):
        raise ValueError(f'{name} must be nonnegative')
    if positive and np.any(array <= 0.0):
        raise ValueError(f'{name} must be positive')
    return tuple(float(x) for x in array)


def _limitations(value):
    if isinstance(value, str):
        raise TypeError('limitations must be a sequence, not a string')
    result = tuple(_text(x, 'limitation') for x in value)
    if not result:
        raise ValueError('Explicit limitations are required')
    return result


@dataclass(frozen=True, slots=True)
class AppliedLoad:
    """One EXTERNAL point force and optional external free couple.

    Components use structure-fixed FRD axes B. The application point is
    measured in metres from fixed structural datum O_B0, NOT from moving G.
    free_moment_B_N_m excludes the application-point cross-product term.

    Powered rotor i uses F_i,B = R_BM [0,0,-T_i], T_i >= 0, and external
    air-on-rotor torque R_BM [0,0,-sigma_i Q_i], Q_i >= 0. sigma_i is the
    signed spin direction about common +z_M, not an unspecified CW label.

    Do not enter internal servo/motor reaction torque here. Its whole-vehicle
    effects require consistent relative angular momentum and derivatives
    in the mass-property interface, or an explicitly stated approximation.
    """

    force_B_N: tuple[float, float, float]
    application_point_B0_m: tuple[float, float, float]
    free_moment_B_N_m: tuple[float, float, float]
    model_scope: str
    provenance: str

    def __post_init__(self):
        for name in ('force_B_N', 'application_point_B0_m', 'free_moment_B_N_m'):
            object.__setattr__(self, name, _vector(getattr(self, name), 3, name))
        _scope(self.model_scope)
        _text(self.provenance, 'provenance')


@dataclass(frozen=True, slots=True)
class ExternalWrench:
    """Resolved external force and moment ALREADY about instantaneous G.

    Do not apply another reference-point shift to this moment. Uniform
    gravity is handled separately in local translation and contributes no
    net moment about complete-vehicle G in this uniform-field approximation.
    """

    force_B_N: tuple[float, float, float]
    moment_B_G_N_m: tuple[float, float, float]
    model_scope: str
    provenance: str

    def __post_init__(self):
        for name in ('force_B_N', 'moment_B_G_N_m'):
            object.__setattr__(self, name, _vector(getattr(self, name), 3, name))
        _scope(self.model_scope)
        _text(self.provenance, 'provenance')


def resolve_applied_loads(*, loads, mass_properties, provenance):
    """Sum F and (application_point - instantaneous_CG) cross F + couple.

    An explicit empty sequence deliberately omits these loads; provenance
    must identify the assumption. Nothing adds environmental or internal
    actuator loads implicitly. Every application point and CG uses O_B0.
    """
    if not isinstance(mass_properties, MassProperties):
        raise TypeError('Explicit MassProperties snapshot required')
    _text(provenance, 'provenance')
    force = np.zeros(3)
    moment = np.zeros(3)
    for load in tuple(loads):
        if not isinstance(load, AppliedLoad):
            raise TypeError('Each load must be AppliedLoad')
        if load.model_scope != mass_properties.model_scope:
            raise ValueError('Fixture and vehicle scopes must not be mixed')
        force_i = np.asarray(load.force_B_N)
        arm = mass_properties.moment_arm_m(load.application_point_B0_m)
        with np.errstate(over='raise', invalid='raise'):
            force += force_i
            moment += np.cross(arm, force_i) + np.asarray(load.free_moment_B_N_m)
    return ExternalWrench(
        force_B_N=force,
        moment_B_G_N_m=moment,
        model_scope=mass_properties.model_scope,
        provenance=provenance,
    )


@dataclass(frozen=True, slots=True)
class CoaxialConditions:
    """Simultaneous paired operating conditions in SI units.

    Stable order is upper/nearer-structure rotor U, then lower/nearer-ground
    rotor L, identified at neutral and retained through articulation.
    Module M maps into B through R_BM=Rx(alpha)Ry(beta).

    rotor_velocity_relative_air_M_m_s contains each actual hub's velocity
    relative to AMBIENT air, resolved in M. Include body rotation, actual
    separated-joint kinematics and configuration-dependent CG motion.
    It is not automatically induced disk flow. The coupled performance map
    owns its wake/interference treatment and calibrated operating domain.

    bus_voltage_V is the actual shared terminal voltage, not nominal pack
    voltage or an independent per-rotor supply. Electrical closure must
    reconcile simultaneous motor/ESC and auxiliary demand. SOC and supplied
    temperatures alone establish neither battery nor thermal evolution.

    Auxiliary current is not included in this preliminary record; therefore
    its battery-current domain report cannot by itself establish complete
    vehicle electrical feasibility. The environment/electrical interface
    must account for auxiliary consumers separately, exactly once.
    """

    air_density_kg_m3: float
    bus_voltage_V: float
    rotor_axial_spacing_m: float
    rotor_velocity_relative_air_M_m_s: tuple
    state_of_charge: float
    motor_temperature_K: tuple[float, float]
    esc_temperature_K: tuple[float, float]
    battery_temperature_K: float
    model_scope: str
    provenance: str

    def __post_init__(self):
        for name in (
            'air_density_kg_m3', 'bus_voltage_V',
            'rotor_axial_spacing_m', 'battery_temperature_K',
        ):
            object.__setattr__(self, name, _scalar(
                getattr(self, name), name, positive=True,
            ))
        soc = _scalar(self.state_of_charge, 'state_of_charge')
        if not 0.0 <= soc <= 1.0:
            raise ValueError('state_of_charge must be in [0,1]')
        object.__setattr__(self, 'state_of_charge', soc)
        velocity = finite_array(
            self.rotor_velocity_relative_air_M_m_s, (2, 3),
            'rotor_velocity_relative_air_M_m_s',
        )
        object.__setattr__(self, 'rotor_velocity_relative_air_M_m_s',
                           tuple(tuple(float(x) for x in row) for row in velocity))
        for name in ('motor_temperature_K', 'esc_temperature_K'):
            object.__setattr__(self, name, _vector(
                getattr(self, name), 2, name, positive=True,
            ))
        _scope(self.model_scope)
        _text(self.provenance, 'provenance')


@dataclass(frozen=True, slots=True)
class CoaxialPerformance:
    """Coupled-map response at ACTUAL actuator states, not held setpoints.

    Thrust and aerodynamic drag torque are nonnegative magnitudes; the
    concrete adapter applies spin signs and actual module orientation.
    Reverse thrust, windmilling, regeneration and negative branch currents
    require a separately reviewed extension, not silent clipping here.

    motor_current_A means winding current. rotor_bus_current_A means each
    motor/ESC branch's current on the shared bus, including ESC effects but
    excluding servos, avionics and other auxiliary consumers. They need not
    be equal. Total auxiliary current belongs to complete electrical closure.

    electrical_response_model distinguishes quasi-steady current estimates
    from a supplied dynamic model. The label alone does not validate either.
    Q*abs(omega) is aerodynamic drag power, not total transient shaft power
    when rotor kinetic energy changes. Acceleration-current effects must be
    included by a suitable provider or explicitly left unresolved.

    domain_checks contains provider REPORTED flags, not independent test
    evidence: True, False or None for each required domain. Unknown thermal
    or electrical limits must remain None. Consumers choose an explicit
    policy; this object supplies no permission for vehicle operation.
    """

    conditions: CoaxialConditions
    thrust_N: tuple[float, float]
    aerodynamic_drag_torque_N_m: tuple[float, float]
    motor_current_A: tuple[float, float]
    rotor_bus_current_A: tuple[float, float]
    electrical_response_model: str
    domain_checks: tuple
    provenance: str
    limitations: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.conditions, CoaxialConditions):
            raise TypeError('Explicit CoaxialConditions required')
        for name in (
            'thrust_N', 'aerodynamic_drag_torque_N_m',
            'motor_current_A', 'rotor_bus_current_A',
        ):
            object.__setattr__(self, name, _vector(
                getattr(self, name), 2, name, nonnegative=True,
            ))
        if self.electrical_response_model not in (
            'quasi_steady_estimate', 'dynamic_model',
        ):
            raise ValueError('Explicit electrical-response model required')
        checks = {}
        for entry in tuple(self.domain_checks):
            if not isinstance(entry, (tuple, list)) or len(entry) != 2:
                raise TypeError('domain_checks must contain name/value pairs')
            name, value = entry
            _text(name, 'domain check name')
            if name in checks:
                raise ValueError('Duplicate domain check: ' + name)
            if value is not None and type(value) is not bool:
                raise TypeError('Domain checks must be bool or None')
            checks[name] = value
        if set(checks) != set(REQUIRED_DOMAIN_CHECKS):
            raise ValueError('Supply exactly the required domain checks')
        object.__setattr__(self, 'domain_checks', tuple(
            (name, checks[name]) for name in REQUIRED_DOMAIN_CHECKS
        ))
        _text(self.provenance, 'provenance')
        object.__setattr__(self, 'limitations', _limitations(self.limitations))

    @property
    def model_scope(self):
        return self.conditions.model_scope

    @property
    def reported_admissibility(self):
        """False for any known violation, None if unresolved, otherwise True.

        This summarizes provider reports only, not independent verification.
        """
        values = tuple(value for _, value in self.domain_checks)
        if any(value is False for value in values):
            return False
        if any(value is None for value in values):
            return None
        return True

    @property
    def propulsion_bus_power_W(self):
        """Shared terminal V times summed branch A; excludes auxiliary power."""
        power = self.conditions.bus_voltage_V * sum(self.rotor_bus_current_A)
        return _scalar(power, 'propulsion_bus_power_W')


class CoaxialPerformanceMap(Protocol):
    """Pure paired map: identical inputs must yield identical outputs.

    Evaluate U and L simultaneously. Retain traceable source/calibration,
    interpolation/extrapolation policy, spacing and inflow domains, loss
    parameters and electrical assumptions. Do not double isolated thrust,
    assume equal RPM cancels torque, extrapolate silently or independently
    clip thrust, torque and current into an apparently feasible response.

    AssemblyKinematics carries actual SIGNED rotor speeds/accelerations
    about common +z_M and actual gimbal motion. The concrete adapter checks
    its configured counter-rotation signs, including zero-speed boundaries.
    Model extensions needing additional dynamic states must version the
    state/interface contract, not hide their evolution in mutable history.
    """

    def evaluate(self, *, time_s: float, kinematics: AssemblyKinematics,
                 conditions: CoaxialConditions) -> CoaxialPerformance:
        ...


@dataclass(frozen=True, slots=True)
class PropulsionEvaluation:
    """Two external rotor loads, U then L, and their paired performance.

    Application points come from actual gimbal angles and explicit outer/
    inner origins. Do not cache a moment about a different CG. Resolve loads
    using the same complete-vehicle mass snapshot as the plant dynamics.
    """

    performance: CoaxialPerformance
    rotor_loads: tuple[AppliedLoad, AppliedLoad]
    provenance: str

    def __post_init__(self):
        if not isinstance(self.performance, CoaxialPerformance):
            raise TypeError('Explicit CoaxialPerformance required')
        loads = tuple(self.rotor_loads)
        if len(loads) != 2 or not all(isinstance(x, AppliedLoad) for x in loads):
            raise ValueError('Exactly two ordered rotor AppliedLoads required')
        if any(x.model_scope != self.performance.model_scope for x in loads):
            raise ValueError('Load and performance scopes differ')
        object.__setattr__(self, 'rotor_loads', loads)
        _text(self.provenance, 'provenance')

    def wrench_about_cg(self, mass_properties):
        """Resolve these external loads once about the supplied instantaneous G."""
        return resolve_applied_loads(
            loads=self.rotor_loads,
            mass_properties=mass_properties,
            provenance=self.provenance,
        )


class Propulsion(ABC):
    """External-load provider, not a mass ledger or actuator integrator.

    A separate response model evolves actual motor/gimbal states from an
    immutable held command with explicit lag, saturation and calibration
    boundaries. It supplies the SAME AssemblyKinematics to this provider
    and the mass-property provider.

    evaluate must not update PID memory, integrate energy by call count,
    append trajectory history or apply implicit numerical vehicle defaults.
    External aerodynamic rotor couples occur here exactly once. Internal
    reactions, rotor spin and articulated motion belong in whole-vehicle
    momentum bookkeeping, not an extra independent external torque.
    """

    @abstractmethod
    def evaluate(self, *, time_s: float, kinematics: AssemblyKinematics,
                 conditions: CoaxialConditions) -> PropulsionEvaluation:
        raise NotImplementedError
