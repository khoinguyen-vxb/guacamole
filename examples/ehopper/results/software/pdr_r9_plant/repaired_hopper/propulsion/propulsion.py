"""Explicit propulsion/load contracts for the sandbox PDR-R9 plant.

Audited original: 6dof_hopper/propulsion/propulsion.py
Original SHA-256: e07b895d8399016a3b0511afb195d7ebf992050cef04ab3015600347f01750ce
Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1, RC08/RC11/RC12.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal decision: 84ef41fdd3fd4266ada43df2ace64a48 r1.

Intentional API migration:
  Replace the incomplete get_mass/get_local_cg/get_thrust_and_moment ABC.
  Mass belongs exclusively to Hopper's complete installed-mass ledger.
  Propellor must implement evaluate with the explicit contract below.
  Simulation must request this evaluation and resolve its applied loads
  about the SAME instantaneous CG used for the mass-property snapshot.
  The old time-only Hopper forwarding caller is deliberately removed.

There are no motor, battery, propeller, geometry or thermal defaults here.
An interface or a provider-reported admissibility flag is not independent
verification, calibration, vehicle acceptance or a working propulsion model.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
from ..helpers.math import finite_array


PROPULSION_SCHEMA = 'pdr_r9_external_coaxial_loads_v1'
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

    All components use structure-fixed FRD axes B. application_point_B0_m
    is relative to the fixed neutral-CG structural datum, NOT instantaneous
    G. free_moment_B_N_m contains no application-point cross-product term.

    For a rotor, the free couple is the air-on-rotor aerodynamic torque:
        R_BM @ [0, 0, -spin_sign * drag_torque_magnitude].
    spin_sign is defined about the common +z_M axis, not by an ambiguous
    visual CW/CCW label. The point force is R_BM @ [0, 0, -thrust].

    Motor/servo reactions are internal to the complete vehicle. Do NOT
    enter them here. Relative rotor/joint angular momentum and its rate
    belong in the mass-property/momentum interface instead.
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
    """Resolved total external load; moment is already about G.

    A caller must not add another CG/application-point shift. Gravity is
    normally handled separately by the local translational equation;
    uniform gravity has no net moment about the complete-vehicle CG.
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

    Passing an explicit empty sequence represents deliberately omitted
    loads; the required provenance must identify that assumption. No
    environmental, aerodynamic or actuator loads are added implicitly.
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
    """Simultaneous pair operating conditions, all in SI.

    Stable rotor ordering is [upper, lower]. Module M coincides with B at
    zero gimbal angles and maps into B through Rx(alpha)Ry(beta).

    rotor_velocity_relative_air_M_m_s contains each hub's velocity relative
    to ambient air, resolved in M. It must include body rotation and any
    prescribed internal-motion contribution appropriate to that hub.
    This is NOT automatically the induced velocity through the disk.
    The paired map must document its induced-flow/coaxial-interference
    treatment and validity; two isolated-rotor maps cannot simply be added.

    bus_voltage_V is actual shared terminal voltage, not nominal pack
    voltage or an independent per-rotor supply. A battery model supplying
    this value must reconcile sag with simultaneous branch/auxiliary load.
    Temperature inputs do not establish a thermal evolution model.
    Explicit fixture values are permissible only with analytical scope.
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
    """Paired-map response at ACTUAL actuator states, not held setpoints.

    Thrust and aerodynamic drag torque are nonnegative magnitudes. The
    concrete propulsion model applies the configured spin signs to torque.
    A zero drag magnitude at zero speed is allowed; windmilling, reverse
    thrust, regeneration and negative branch current are outside this
    preliminary contract and require a separately reviewed extension.

    motor_current_A and rotor_bus_current_A are distinct quantities: ESC
    duty and losses can make winding current differ from battery-branch
    current. Bus currents include each motor/ESC branch, but EXCLUDE tilt
    actuators, avionics and other auxiliary loads. Those must be included
    once by the complete electrical/energy budget.

    electrical_response_model identifies whether currents include transient
    acceleration effects or are merely quasi-steady estimates. A steady
    operating-point solver alone cannot establish acceleration current.
    Aerodynamic drag power Q*abs(omega) likewise is not total transient
    motor shaft power when rotor kinetic energy is changing.

    domain_checks records provider-reported checks, not independent test
    results. Each required check is True, False or None (unresolved).
    Unknown thermal limits must remain None, not automatically True.
    Consumers must explicitly decide how unresolved domains are handled;
    this record supplies no automatic permission to run a vehicle case.
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
        entries = tuple(self.domain_checks)
        checks = {}
        for entry in entries:
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
        object.__setattr__(self, 'domain_checks',
                           tuple((name, checks[name]) for name in REQUIRED_DOMAIN_CHECKS))
        _text(self.provenance, 'provenance')
        object.__setattr__(self, 'limitations', _limitations(self.limitations))

    @property
    def model_scope(self):
        return self.conditions.model_scope

    @property
    def reported_admissibility(self):
        """False if any known violation; None if unresolved; otherwise True.

        This summarizes provider reports only, not physical validation.
        """
        values = tuple(value for _, value in self.domain_checks)
        if any(value is False for value in values):
            return False
        if any(value is None for value in values):
            return None
        return True

    @property
    def propulsion_bus_power_W(self):
        """Actual-bus V times summed branch A; excludes auxiliary power."""
        power = self.conditions.bus_voltage_V * sum(self.rotor_bus_current_A)
        return _scalar(power, 'propulsion_bus_power_W')


class CoaxialPerformanceMap(Protocol):
    """Pure coupled map; repeated identical inputs must return identical data.

    Evaluate the upper/lower pair together. Declare source/calibration,
    interpolation/extrapolation policy, spacing and flow domains, electrical
    assumptions and all losses. Do not extrapolate silently or independently
    clip thrust/torque/current into an apparently feasible operating point.

    Kinematics carries actual SIGNED rotor speeds and accelerations about
    common +z_M, plus gimbal motion. The concrete model must enforce its
    configured counter-rotation signs, including at zero speed.
    """

    def evaluate(self, *, time_s: float, kinematics: AssemblyKinematics,
                 conditions: CoaxialConditions) -> CoaxialPerformance:
        ...


@dataclass(frozen=True, slots=True)
class PropulsionEvaluation:
    """Two rotor external loads, upper then lower, and paired performance.

    Application points must be computed from the current module geometry
    and gimbal angles. This record deliberately does not cache a moment
    about a potentially different CG. Resolve it using the current snapshot.
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
        return resolve_applied_loads(
            loads=self.rotor_loads,
            mass_properties=mass_properties,
            provenance=self.provenance,
        )


class Propulsion(ABC):
    """External-load provider, not a mass ledger or actuator integrator.

    A separate actuator model evolves actual rotor/gimbal states from
    immutable held commands with explicit lag and saturation. That model
    supplies AssemblyKinematics here and to the mass-property provider.
    The plant must use consistent kinematics for both evaluations.

    evaluate must have no controller-integral updates, trajectory logging,
    mutable call history or implicit numerical vehicle defaults. It returns
    external rotor loads only. Rotor acceleration and gimbal reactions are
    accounted for through whole-vehicle angular momentum, not extra loads.
    """

    @abstractmethod
    def evaluate(self, *, time_s: float, kinematics: AssemblyKinematics,
                 conditions: CoaxialConditions) -> PropulsionEvaluation:
        raise NotImplementedError
