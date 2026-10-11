"""Explicit synthetic providers and construction helpers for PDR-R9 checks.

Run/import only from the sandbox software/pdr_r9_plant directory. This module
uses the repaired_hopper namespace package beside it, not the original plant.
No supplied checkout is modified. No controller or mission simulation runs.

Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.
Architecture decision: 84ef41fdd3fd4266ada43df2ace64a48 r1.

New callers reviewed against the repaired interfaces:
  initial_snapshots -> State.from_euler and ActuatorState;
  FrozenFixtureMass.snapshot -> Hopper.mass_properties;
  PrescribedFixtureEnvironment.sample -> Simulation.evaluate;
  SyntheticPairedMap.evaluate -> Propellor.evaluate;
  build_fixture -> Hopper, Propellor, LaggedActuators and Simulation.

All numerical inputs come from the explicitly synthetic configuration.
There are no selected vehicle parameters or historical travel/arm defaults.
The checker must compute its expectations independently rather than use
these implementation functions as its analytical oracle. This module does
not print passes, write results, or perform verification on import.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

import numpy as np

from repaired_hopper.chassis.hopper import AssemblyKinematics, Hopper, MassProperties
from repaired_hopper.helpers.math import finite_array
from repaired_hopper.propulsion.actuators import ActuatorState, LagParameters, LaggedActuators
from repaired_hopper.propulsion.propeller import CoaxialGeometry, Propellor
from repaired_hopper.propulsion.propulsion import (
    AppliedLoad, CoaxialConditions, CoaxialPerformance, REQUIRED_DOMAIN_CHECKS,
)
from repaired_hopper.simulation.environment import EnvironmentSample
from repaired_hopper.simulation.simulation import PLANT_UNITS, Simulation
from repaired_hopper.simulation.state import State


CONFIG_SCHEMA = 'pdr_r9_analytical_fixture_config_v1'
MAP_MODEL = 'coupled_rational_speed_fixture_v1'


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def _finite_time(value):
    result = float(value)
    if not np.isfinite(result):
        raise ValueError('time_s must be finite')
    return result


def _pair(value, name, *, positive=False, nonnegative=False):
    values = finite_array(value, (2,), name)
    if positive and np.any(values <= 0.0):
        raise ValueError(f'{name} must be positive')
    if nonnegative and np.any(values < 0.0):
        raise ValueError(f'{name} must be nonnegative')
    return tuple(float(x) for x in values)


def _unique_json_object(entries):
    result = {}
    for key, value in entries:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError('Nonfinite JSON constant: ' + value)


def validate_fixture_config(config):
    """Check scope/ordering, not physical feasibility or test acceptance."""
    if not isinstance(config, dict) or config.get('schema') != CONFIG_SCHEMA:
        raise ValueError('Explicit supported analytical fixture schema required')
    if config.get('model_scope') != 'analytical_fixture':
        raise ValueError('Vehicle data must not be run through these fixtures')
    if config.get('vehicle_baseline') is not False:
        raise ValueError('Fixture must explicitly exclude a vehicle baseline')
    if config.get('controller_enabled') is not False:
        raise ValueError('No controller is authorized in this fixture')
    if config.get('physical_acceptance') != 'not_assessed':
        raise ValueError('Fixture configuration must not claim physical acceptance')
    _text(config.get('provenance'), 'fixture provenance')
    for section in (
        'frame_contract', 'mass_properties', 'geometry', 'lag_parameters',
        'environment', 'synthetic_paired_map', 'solver', 'test_vectors',
        'analytical_test_tolerances',
    ):
        if not isinstance(config.get(section), dict):
            raise ValueError('Required configuration object: ' + section)
    frame = config['frame_contract']
    rotation = finite_array(frame['CAD_to_body_rotation'], (3, 3), 'R_BC')
    if not np.array_equal(rotation, np.diag([1.0, -1.0, -1.0])):
        raise ValueError('Configuration conflicts with the current CAD/body frame contract')
    if frame.get('rotor_order') != ['upper', 'lower']:
        raise ValueError('Explicit upper/lower rotor ordering required')
    if tuple(config['solver']['atol_units']) != PLANT_UNITS:
        raise ValueError('Absolute solver tolerance units do not match the plant vector')
    for section in ('mass_properties', 'geometry', 'lag_parameters',
                    'environment', 'synthetic_paired_map'):
        if config[section].get('model_scope') != 'analytical_fixture':
            raise ValueError('Mixed fixture/vehicle scope in ' + section)


def load_fixture_config(path):
    """Read an editable JSON input; callers retain its actual artifact hash.

    No numerical defaults or automatic updates to its test-status text are
    applied. Missing fields fail explicitly. The returned dictionary is
    caller-owned; construction helpers do not mutate it.
    """
    config = json.loads(
        Path(path).read_text(encoding='utf-8'),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )
    validate_fixture_config(config)
    return config


@dataclass(frozen=True, slots=True)
class FrozenFixtureMass:
    """Constant rigid-body fixture, including explicitly omitted momentum.

    Frozen mass/CG/inertia are NOT a complete model of moving rotors and
    gimbals. Their prescribed response can be tested numerically with this
    provider, but this cannot establish articulated-vehicle accuracy.
    Nonzero property derivatives require a different, consistent provider;
    they must not be attached to a supposedly constant snapshot.
    """

    properties: MassProperties

    def __post_init__(self):
        if not isinstance(self.properties, MassProperties):
            raise TypeError('Explicit MassProperties required')
        if (self.properties.model_scope != 'analytical_fixture'
                or self.properties.dynamics_mode != 'rigid_body_fixture'):
            raise ValueError('FrozenFixtureMass requires a rigid analytical fixture')

    def snapshot(self, *, time_s, kinematics):
        _finite_time(time_s)
        if not isinstance(kinematics, AssemblyKinematics):
            raise TypeError('Explicit AssemblyKinematics required')
        return self.properties


@dataclass(frozen=True, slots=True)
class PrescribedFixtureEnvironment:
    """Time-independent fixture conditions, with actual hub-location echoes.

    Ambient wind is prescribed separately for the two ordered hubs; it is
    not a spatial weather or induced-flow solution. Voltage, SOC, auxiliary
    current and temperatures are prescribed, not dynamically reconciled.
    Additional loads, when supplied explicitly, are body-coordinate loads
    about the named structural datum. Empty loads remain a model omission.

    prototype hub positions are validation placeholders, never evaluation
    outputs. sample always replaces them with the requested actual positions.
    No previous time, energy integral or mutable provider history exists.
    """

    prototype: EnvironmentSample

    def __post_init__(self):
        if not isinstance(self.prototype, EnvironmentSample):
            raise TypeError('Explicit EnvironmentSample prototype required')
        if self.prototype.model_scope != 'analytical_fixture':
            raise ValueError('This prescribed environment is fixture-only')

    @classmethod
    def from_config(cls, parameters):
        values = dict(parameters)
        if 'hub_positions_L_m' in values:
            raise ValueError('Hub positions must come from actual plant kinematics')
        values['additional_external_loads'] = tuple(
            AppliedLoad(**entry) for entry in values['additional_external_loads']
        )
        # Only constructor validation uses these placeholders. sample below
        # unconditionally substitutes the actual locations from Simulation.
        prototype = EnvironmentSample(
            hub_positions_L_m=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            **values,
        )
        return cls(prototype)

    def sample(self, *, time_s, state, mass_properties, kinematics,
               hub_positions_L_m):
        _finite_time(time_s)
        if not isinstance(state, State):
            raise TypeError('Explicit instantaneous-CG State required')
        if not isinstance(mass_properties, MassProperties):
            raise TypeError('Explicit MassProperties required')
        if mass_properties.model_scope != 'analytical_fixture':
            raise ValueError('Fixture environment cannot supply vehicle conditions')
        if not isinstance(kinematics, AssemblyKinematics):
            raise TypeError('Explicit AssemblyKinematics required')
        positions = finite_array(hub_positions_L_m, (2, 3), 'hub_positions_L_m')
        return replace(self.prototype, hub_positions_L_m=positions)


@dataclass(frozen=True, slots=True)
class SyntheticPairedMap:
    """Invented coupled functions for load/interface regression tests ONLY.

    For each rotor i and the other rotor j:
      d_i = 1 + chi_i * (abs(omega_j) / omega_ref)^2
      T_i = kT_i * omega_i^2 / d_i
      Q_i = kQ_i * omega_i^2 / d_i
      I_motor_i = I_idle_i + Q_i / Kt_i
      I_bus_i = I_idle_i + Q_i*abs(omega_i)/(efficiency_i*V_bus)

    The denominator deliberately couples both actual rotor speeds. It is
    NOT measured coaxial interference. The inputs for spacing, density,
    inflow and temperature are received but do not affect these synthetic
    equations. Motor/ESC kinetic-energy transients and battery sag are not
    solved; current outputs are quasi-steady arithmetic estimates only.

    Domain flags are supplied explicitly and carried through without being
    upgraded. A checker may inject True/False to test policy handling, but
    those flags never become independent physical-domain evidence.
    """

    thrust_coefficient_N_s2_rad2: tuple[float, float]
    drag_torque_coefficient_N_m_s2_rad2: tuple[float, float]
    cross_interference_coefficient: tuple[float, float]
    reference_speed_rad_s: float
    synthetic_efficiency: tuple[float, float]
    motor_torque_constant_N_m_A: tuple[float, float]
    idle_current_A: tuple[float, float]
    domain_checks: tuple
    provenance: str
    limitations: tuple[str, ...]
    model_scope: str

    def __post_init__(self):
        if self.model_scope != 'analytical_fixture':
            raise ValueError('Synthetic propulsion is not a vehicle performance map')
        for name in (
            'thrust_coefficient_N_s2_rad2',
            'drag_torque_coefficient_N_m_s2_rad2',
            'cross_interference_coefficient', 'idle_current_A',
        ):
            object.__setattr__(self, name, _pair(
                getattr(self, name), name, nonnegative=True,
            ))
        for name in ('synthetic_efficiency', 'motor_torque_constant_N_m_A'):
            object.__setattr__(self, name, _pair(
                getattr(self, name), name, positive=True,
            ))
        if any(value > 1.0 for value in self.synthetic_efficiency):
            raise ValueError('Synthetic efficiency must be in (0,1]')
        reference = float(self.reference_speed_rad_s)
        if not np.isfinite(reference) or reference <= 0.0:
            raise ValueError('reference_speed_rad_s must be finite and positive')
        object.__setattr__(self, 'reference_speed_rad_s', reference)
        checks = {}
        for entry in self.domain_checks:
            if not isinstance(entry, (tuple, list)) or len(entry) != 2:
                raise TypeError('Domain checks require name/value pairs')
            name, flag = entry
            if name in checks:
                raise ValueError('Duplicate domain check: ' + str(name))
            if flag is not None and type(flag) is not bool:
                raise TypeError('Domain flags must be bool or None')
            checks[name] = flag
        if set(checks) != set(REQUIRED_DOMAIN_CHECKS):
            raise ValueError('Exactly the required domain flags must be supplied')
        object.__setattr__(self, 'domain_checks', tuple(
            (name, checks[name]) for name in REQUIRED_DOMAIN_CHECKS
        ))
        _text(self.provenance, 'map provenance')
        if isinstance(self.limitations, str):
            raise TypeError('limitations must be a sequence of strings')
        limitations = tuple(_text(item, 'limitation') for item in self.limitations)
        if not limitations:
            raise ValueError('Explicit synthetic-map limitations required')
        object.__setattr__(self, 'limitations', limitations)

    @classmethod
    def from_config(cls, parameters):
        if parameters['model'] != MAP_MODEL:
            raise ValueError('Unsupported synthetic paired-map model')
        if parameters['electrical_response_model'] != 'quasi_steady_estimate':
            raise ValueError('This synthetic implementation is not an electrical transient model')
        names = (
            'thrust_coefficient_N_s2_rad2',
            'drag_torque_coefficient_N_m_s2_rad2',
            'cross_interference_coefficient', 'reference_speed_rad_s',
            'synthetic_efficiency', 'motor_torque_constant_N_m_A',
            'idle_current_A', 'provenance', 'limitations', 'model_scope',
        )
        values = {name: parameters[name] for name in names}
        values['domain_checks'] = tuple(parameters['reported_domain_checks'].items())
        return cls(**values)

    def evaluate(self, *, time_s, kinematics, conditions):
        _finite_time(time_s)
        if not isinstance(kinematics, AssemblyKinematics):
            raise TypeError('Explicit actual AssemblyKinematics required')
        if not isinstance(conditions, CoaxialConditions):
            raise TypeError('Explicit paired CoaxialConditions required')
        if conditions.model_scope != self.model_scope:
            raise ValueError('Synthetic map cannot consume vehicle operating conditions')
        speed = np.abs(np.asarray(kinematics.rotor_signed_speed_rad_s))
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            denominator = (
                1.0 + np.asarray(self.cross_interference_coefficient)
                * (speed[::-1] / self.reference_speed_rad_s) ** 2
            )
            effective_speed_squared = speed ** 2 / denominator
            thrust = np.asarray(self.thrust_coefficient_N_s2_rad2) * effective_speed_squared
            drag = np.asarray(self.drag_torque_coefficient_N_m_s2_rad2) * effective_speed_squared
            motor_current = (
                np.asarray(self.idle_current_A)
                + drag / np.asarray(self.motor_torque_constant_N_m_A)
            )
            bus_current = (
                np.asarray(self.idle_current_A)
                + drag * speed
                / (np.asarray(self.synthetic_efficiency) * conditions.bus_voltage_V)
            )
        return CoaxialPerformance(
            conditions=conditions,
            thrust_N=thrust,
            aerodynamic_drag_torque_N_m=drag,
            motor_current_A=motor_current,
            rotor_bus_current_A=bus_current,
            electrical_response_model='quasi_steady_estimate',
            domain_checks=self.domain_checks,
            provenance=self.provenance,
            limitations=self.limitations,
        )


def initial_snapshots(config):
    """Construct every nonzero initial component from the actual JSON input."""
    validate_fixture_config(config)
    values = config['test_vectors']['nonzero_initialization']
    state = State.from_euler(
        position_G_L_m=values['position_G_L_m'],
        velocity_G_L_m_s=values['velocity_G_L_m_s'],
        roll_rad=values['roll_rad'], pitch_rad=values['pitch_rad'],
        yaw_rad=values['yaw_rad'], omega_B_rad_s=values['omega_B_rad_s'],
    )
    actuators = ActuatorState(
        rotor_speed_magnitude_rad_s=values['rotor_speed_magnitude_rad_s'],
        demand_filter_gimbal_rad=values['demand_filter_gimbal_rad'],
        actual_gimbal_rad=values['actual_gimbal_rad'],
    )
    return state, actuators


def build_fixture(config, *, initial_state, initial_actuator_state):
    """Build the real repaired plant with explicitly supplied initialization.

    This helper does not integrate, infer trim, choose gains, accept a map,
    or substitute fixture values for missing vehicle inputs. Checker variants
    should make explicit copies/replacements and record all overrides.
    """
    validate_fixture_config(config)
    properties = MassProperties(**config['mass_properties'])
    hopper = Hopper(
        installed_mass_kg=properties.mass_kg,
        mass_property_provider=FrozenFixtureMass(properties),
        model_scope='analytical_fixture',
        ledger_reference='Synthetic fixture, not a vehicle ledger: ' + config['provenance'],
    )
    propulsion = Propellor(
        geometry=CoaxialGeometry(**config['geometry']),
        performance_map=SyntheticPairedMap.from_config(config['synthetic_paired_map']),
    )
    return Simulation(
        hopper=hopper,
        propulsion=propulsion,
        actuator_model=LaggedActuators(LagParameters(**config['lag_parameters'])),
        environment_provider=PrescribedFixtureEnvironment.from_config(config['environment']),
        initial_state=initial_state,
        initial_actuator_state=initial_actuator_state,
        initial_quaternion_unit_tolerance=config['solver']['initial_quaternion_unit_tolerance'],
        domain_policy=config['solver']['domain_policy'],
    )


def solver_options(config):
    """Return explicit solve_ode numerical options, not a control cadence.

    Span, held command, output samples, dense-output choice and events must
    be supplied by the runner/checker. Simulation validates these numerical
    options at execution. No integration occurs in this helper.
    """
    validate_fixture_config(config)
    settings = config['solver']
    return {
        'method': settings['method'],
        'rtol': settings['rtol'],
        'atol': list(settings['atol']),
        'max_step_s': settings['max_step_s'],
    }
