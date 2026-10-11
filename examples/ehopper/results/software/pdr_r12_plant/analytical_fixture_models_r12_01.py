"""Synthetic providers and construction helpers for PDR-R12 plant checks.

Authorization: 66c7448f443f44ac9a016a1b384593a2 r1.
Audit: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 r1.
Caller reconciliation: PDR-R12-PLANT-CALLER-RECONCILIATION-02 r1.
Frames: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal: 28e10be57d6548a3aa5be06c96f6d0d0 r1.

Reconciled from the historical fixture providers inspected in readers
51af21da198e41a2a3fd13f4dde8837a and c1f75c35f5814e3a924278437e1861dc.
Original checkouts and historical outputs remain unchanged.

Import from software/pdr_r12_plant so the adjacent repaired_hopper_r12
namespace package is used. No historical plant package is imported.

Reviewed new caller paths:
  initial_snapshots -> State.from_euler and ActuatorState;
  FrozenFixtureMass.snapshot -> Hopper.mass_properties;
  PrescribedFixtureEnvironment.sample -> Simulation.evaluate;
  SyntheticPairedMap.evaluate -> Propellor.evaluate;
  build_fixture -> current r12 constructors, including separated origins;
  solver_options -> the explicit r12 solve_ode numerical interface.

All numerical model inputs come from the supplied analytical configuration.
No default vehicle geometry, mass, inertia, travel or calibration is supplied.
A checker must derive independent expectations rather than use these provider
functions as their own oracle. Explicit checker variants must retain their
configuration overrides. No integration, output writing or verification occurs
on import. No controller is implemented or tuned.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

import numpy as np

from repaired_hopper_r12.chassis.hopper import (
    AssemblyKinematics, Hopper, MassProperties,
)
from repaired_hopper_r12.helpers.math import finite_array
from repaired_hopper_r12.propulsion.actuators import (
    ACTUATOR_STATE_SCHEMA, ActuatorState, LagParameters, LaggedActuators,
)
from repaired_hopper_r12.propulsion.propeller import (
    GEOMETRY_SCHEMA, CoaxialGeometry, Propellor,
)
from repaired_hopper_r12.propulsion.propulsion import (
    AppliedLoad, CoaxialConditions, CoaxialPerformance, REQUIRED_DOMAIN_CHECKS,
)
from repaired_hopper_r12.simulation.environment import EnvironmentSample
from repaired_hopper_r12.simulation.simulation import (
    PLANT_STATE_SCHEMA, PLANT_UNITS, Simulation,
)
from repaired_hopper_r12.simulation.state import STATE_VECTOR_SCHEMA, State


CONFIG_SCHEMA = 'pdr_r12_analytical_fixture_config_v1'
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
    """Check fixture scope and interface identity, not test acceptance.

    Concrete constructors validate their numerical fields. Unknown vehicle
    data must not be relabelled as a fixture to bypass the preliminary gate.
    This function does not mutate configuration status or fill missing data.
    """
    if not isinstance(config, dict) or config.get('schema') != CONFIG_SCHEMA:
        raise ValueError('Explicit supported r12 fixture schema required')
    if config.get('model_scope') != 'analytical_fixture':
        raise ValueError('These providers are restricted to analytical fixtures')
    if config.get('vehicle_baseline') is not False:
        raise ValueError('Configuration must explicitly exclude a vehicle baseline')
    if config.get('controller_enabled') is not False:
        raise ValueError('No controller is authorized in this fixture')
    if config.get('physical_acceptance') != 'not_assessed':
        raise ValueError('Fixture configuration must not claim physical acceptance')
    _text(config.get('provenance'), 'fixture provenance')
    for section in (
        'implementation_contract', 'frame_contract', 'mass_properties',
        'geometry', 'lag_parameters', 'environment', 'synthetic_paired_map',
        'solver', 'test_vectors', 'analytical_test_tolerances',
    ):
        if not isinstance(config.get(section), dict):
            raise ValueError('Required configuration object: ' + section)
    contract = config['implementation_contract']
    expected = {
        'package': 'repaired_hopper_r12',
        'state_schema': STATE_VECTOR_SCHEMA,
        'actuator_schema': ACTUATOR_STATE_SCHEMA,
        'plant_schema': PLANT_STATE_SCHEMA,
        'geometry_schema': GEOMETRY_SCHEMA,
    }
    for name, value in expected.items():
        if contract.get(name) != value:
            raise ValueError('Configuration/implementation mismatch: ' + name)
    if contract.get('historical_geometry_keywords_permitted') is not False:
        raise ValueError('Historical geometry keywords must be explicitly excluded')
    if any(name in config['geometry'] for name in ('pivot_B0_m', 'hub_offsets_M_m')):
        raise ValueError('Historical geometry requires explicit schema migration')
    frame = config['frame_contract']
    rotation = finite_array(frame['CAD_to_body_rotation'], (3, 3), 'R_BC')
    if not np.array_equal(rotation, np.diag([1.0, -1.0, -1.0])):
        raise ValueError('Configuration conflicts with retained CAD/body rotation')
    if frame.get('rotor_order') != ['upper', 'lower']:
        raise ValueError('Explicit upper/lower rotor ordering required')
    if tuple(config['solver']['atol_units']) != PLANT_UNITS:
        raise ValueError('Absolute tolerance units do not match the plant vector')
    for section in (
        'mass_properties', 'geometry', 'lag_parameters',
        'environment', 'synthetic_paired_map',
    ):
        if config[section].get('model_scope') != 'analytical_fixture':
            raise ValueError('Mixed fixture/vehicle scope in ' + section)


def load_fixture_config(path):
    """Read editable JSON without defaults, duplicate keys or status updates.

    The runner/checker must retain the actual file hash and include the
    configuration artifact Ref in its verification inputs.
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
    """Constant rigid-body fixture, not a moving-mass vehicle provider.

    Core MassProperties validation requires explicit zero CG/inertia rates
    and relative momentum for rigid_body_fixture. A checker exercising
    nonzero property derivatives must construct a separate consistent
    provider or an explicitly instantaneous algebraic fixture.
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
    """Prescribed conditions with actual requested hub-location echoes.

    Ordered hub winds are prescribed ambient values, not an induced-flow
    solution. Voltage, SOC, auxiliary demand and temperatures do not evolve.
    Empty additional loads mean deliberately omitted effects, not evidence
    that vehicle aerodynamics, contact or disturbances are absent.
    """

    prototype: EnvironmentSample

    def __post_init__(self):
        if not isinstance(self.prototype, EnvironmentSample):
            raise TypeError('Explicit EnvironmentSample prototype required')
        if self.prototype.model_scope != 'analytical_fixture':
            raise ValueError('Prescribed environment is fixture-only')

    @classmethod
    def from_config(cls, parameters):
        values = dict(parameters)
        if 'hub_positions_L_m' in values:
            raise ValueError('Actual hub locations must come from plant kinematics')
        values['additional_external_loads'] = tuple(
            AppliedLoad(**entry) for entry in values['additional_external_loads']
        )
        # Placeholders only for constructor validation; sample replaces them.
        return cls(EnvironmentSample(
            hub_positions_L_m=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            **values,
        ))

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
    """Invented coupled map for analytical/interface verification ONLY.

    For rotor i and other rotor j, using actual speed magnitudes:
      d_i = 1 + chi_i*(Omega_j/Omega_ref)^2
      T_i = kT_i*Omega_i^2/d_i; Q_i = kQ_i*Omega_i^2/d_i
      I_motor_i = I_idle_i + Q_i/Kt_i
      I_bus_i = I_idle_i + Q_i*Omega_i/(efficiency_i*V_bus)

    Cross-coupling deliberately exercises simultaneous pair evaluation;
    it is not measured coaxial interference. Received spacing, inflow,
    density and temperatures do not affect these synthetic functions.
    Current is quasi-steady arithmetic, excluding kinetic-energy transients,
    duty/voltage closure, sag and auxiliary loads. Idle-current arithmetic
    at zero speed is not a physical ESC off-state model.

    Required domain flags are supplied explicitly, including unresolved
    values. Injecting flags for policy tests does not validate a domain.
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
            _text(name, 'domain check name')
            if name in checks:
                raise ValueError('Duplicate domain check: ' + name)
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
            raise ValueError('Synthetic map is not an electrical transient model')
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
            raise ValueError('Synthetic map cannot consume vehicle conditions')
        # Propellor validates configured spin signs before invoking this map.
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
    """Preserve every configured nonzero rigid-body and actuator component."""
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
    """Construct the actual r12 plant without integration or implicit trim.

    Explicit initial snapshots are mandatory. The geometry constructor uses
    outer_origin_B0_m, outer_to_inner_outer_m and
    hub_offsets_from_inner_M_m, never historical single-pivot keywords.
    This builder deliberately uses a rigid fixture mass provider; nonzero
    mass-property derivatives require a different explicit provider.
    """
    validate_fixture_config(config)
    properties = MassProperties(**config['mass_properties'])
    hopper = Hopper(
        installed_mass_kg=properties.mass_kg,
        mass_property_provider=FrozenFixtureMass(properties),
        model_scope='analytical_fixture',
        ledger_reference='Synthetic fixture, not vehicle ledger: ' + config['provenance'],
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
    """Return explicit numerical options, not a controller update cadence.

    The caller supplies interval, immutable held command, output sampling,
    dense-output and event choices. Numerical results and convergence must
    be examined independently; no integration occurs in this helper.
    """
    validate_fixture_config(config)
    settings = config['solver']
    return {
        'method': settings['method'],
        'rtol': settings['rtol'],
        'atol': list(settings['atol']),
        'max_step_s': settings['max_step_s'],
    }
