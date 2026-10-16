"""PDR M4 fixed-D analytical plant: simulation/simulation.py.

Current authority: system_model:system revision 4;
work-plan 99f7bb629eef45b89fa38d27c803868c revision 1;
interface 88561ff8b3ba4e8286cebd95a93e3b08 revision 1.
Pre-edit audit: PDR-PLANT-PRE-EDIT-AUDIT-M4-03 revision 1.

Reused from inspected previous_run/repaired_hopper_r12/simulation/simulation.py.
Recovered file SHA256: a186c50ab7c5500e7da14bb5c98a5c2772ff97d63645558be3cfdc3b6e5ca1a8
Original checkout and recovered files remain unchanged. The recovered module
header is retained as historical provenance in migration_manifest_m4_05.json.

Migration: explicit fixed plate/ring datum D replaces the recovered neutral-CG
reference semantics; coordinated datum-related identifiers and schema strings
are versioned across all eight modules. L is NED, B is FRD, q_LB is scalar-first
Hamilton, and R_LB maps B components into L. Translation remains at instantaneous
complete-vehicle CG G. D is fixed to the airframe and never follows G.

D is the neutral propulsion centreline intersection with the upper reference
plane of the FIXED leg-attachment plate/ring. Its numerical CAD location is an
explicit input, not a selected coordinate. CAD C is forward-left-up in mm;
r_B[m] = 0.001*diag(1,-1,-1)*(p_C[mm]-D_C[mm]).

This migration does not add vehicle dynamics, a calibrated propulsion map,
realizable ESC commands, loaded servo capability, battery/thermal evolution or
contact. Analytical-only runtime guards are retained. No fixture is vehicle
data merely because it executes. New fixtures/checkers must use these schemas.
Generation, syntax compilation and imports are not analytical verification,
physical validation, requirement satisfaction or review acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from ..chassis.hopper import Hopper, MassProperties
from ..helpers.math import finite_array, quaternion_derivative, quaternion_to_dcm
from ..propulsion.actuators import (
    ACTUATOR_COMPONENTS,
    ACTUATOR_STATE_SCHEMA,
    ACTUATOR_STATE_SIZE,
    ACTUATOR_UNITS,
    ActuatorEvaluation,
    ActuatorModel,
    ActuatorState,
    HeldCommand,
    LaggedActuators,
)
from ..propulsion.propeller import Propellor
from ..propulsion.propulsion import (
    ExternalWrench,
    PropulsionEvaluation,
    resolve_applied_loads,
)
from .environment import EnvironmentProvider, EnvironmentSample
from .state import STATE_COMPONENTS, STATE_SIZE, STATE_UNITS, STATE_VECTOR_SCHEMA, State


PLANT_STATE_SCHEMA = 'hopper_m4_fixed_D_cg_ned_frd_wxyz_fixture_actuators_v1'
PLANT_STATE_SIZE = STATE_SIZE + ACTUATOR_STATE_SIZE
PLANT_COMPONENTS = STATE_COMPONENTS + ACTUATOR_COMPONENTS
PLANT_UNITS = STATE_UNITS + ACTUATOR_UNITS
DOMAIN_POLICIES = (
    'require_reported_admissible',
    'allow_unresolved_analytical_fixture',
)


class ModelDomainError(ValueError):
    """Known violation or disallowed unresolved provider-reported domain.

    Do not convert this exception into clipped performance or an accepted
    operating point. Reported admissibility is not independent verification.
    """


class IntegrationFailure(RuntimeError):
    """Numerical solver failure retaining the actual result for inspection."""

    def __init__(self, message, solution):
        super().__init__(message)
        self.solution = solution


def _finite_scalar(value, name, *, positive=False):
    number = float(value)
    if not np.isfinite(number) or (positive and number <= 0.0):
        raise ValueError(f'{name} must be finite' + (' and positive' if positive else ''))
    return number


def pack_state(state, actuator_state):
    """Pack owned snapshots without resetting or normalizing any component.

    Order is thirteen rigid-body followed by six actuator components.
    This is not an importer for original body-velocity state vectors.
    """
    if not isinstance(state, State) or not isinstance(actuator_state, ActuatorState):
        raise TypeError('Explicit State and ActuatorState required')
    return np.concatenate((state.as_vector(), actuator_state.as_vector()))


def unpack_state(vector, *, schema):
    """Decode the explicit nineteen-component M4 schema without mutation."""
    if schema != PLANT_STATE_SCHEMA:
        raise ValueError('Explicit supported plant-state schema required')
    values = finite_array(vector, (PLANT_STATE_SIZE,), 'plant state')
    return (
        State.from_vector(values[:STATE_SIZE], schema=STATE_VECTOR_SCHEMA),
        ActuatorState.from_vector(values[STATE_SIZE:], schema=ACTUATOR_STATE_SCHEMA),
    )


@dataclass(frozen=True, slots=True)
class PlantEvaluation:
    """One evaluation, not accepted-step history or verification evidence.

    Re-evaluate accepted solution samples explicitly for reporting. Do not
    integrate RHS call history to obtain energy: adaptive stages may repeat,
    arrive out of order or be rejected. Electrical properties here are only
    instantaneous shared-bus arithmetic, not a battery/thermal solution.
    """

    derivative: tuple[float, ...]
    state: State
    actuator_state: ActuatorState
    actuator: ActuatorEvaluation
    mass_properties: MassProperties
    environment: EnvironmentSample
    propulsion: PropulsionEvaluation
    external_wrench: ExternalWrench

    def __post_init__(self):
        values = finite_array(self.derivative, (PLANT_STATE_SIZE,), 'plant derivative')
        object.__setattr__(self, 'derivative', tuple(float(x) for x in values))
        for name, expected in (
            ('state', State), ('actuator_state', ActuatorState),
            ('actuator', ActuatorEvaluation), ('mass_properties', MassProperties),
            ('environment', EnvironmentSample), ('propulsion', PropulsionEvaluation),
            ('external_wrench', ExternalWrench),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f'Invalid {name} in PlantEvaluation')

    @property
    def total_bus_current_A(self):
        return self.environment.total_bus_current_A(
            self.propulsion.performance.rotor_bus_current_A,
        )

    @property
    def total_bus_power_W(self):
        return self.environment.total_bus_power_W(
            self.propulsion.performance.rotor_bus_current_A,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Simulation:
    """Pure analytical plant with explicit initialization and held commands.

    Every provider must be pure: identical inputs must give identical outputs
    independently of call order. Frozen records cannot establish the purity
    of arbitrary providers; retained analytical checks must test it.

    Initial quaternion tolerance is explicit and dimensionless. Nothing is
    silently normalized. An intentional initial normalization must occur
    upstream and be documented; later raw norm drift remains measurable.

    Domain policies apply to provider REPORTED flags. False is always
    rejected; None is allowed only by the named analytical-fixture policy.
    Even all True flags do not establish complete electrical feasibility:
    the paired-map battery-current flag excludes auxiliary consumers.

    Translation refers to instantaneous complete-vehicle G, not fixed D.
    Mission scoring must separately apply fixed_datum_kinematics with current
    CG offset and offset rate. An event alone is not a contact/landing model.
    """

    hopper: Hopper
    propulsion: Propellor
    actuator_model: ActuatorModel
    environment_provider: EnvironmentProvider
    initial_state: State
    initial_actuator_state: ActuatorState
    initial_quaternion_unit_tolerance: float
    domain_policy: str

    def __post_init__(self):
        if not isinstance(self.hopper, Hopper):
            raise TypeError('Explicit Hopper required')
        if not isinstance(self.propulsion, Propellor):
            raise TypeError('Explicit common-gimbal Propellor required')
        if not isinstance(self.initial_state, State):
            raise TypeError('Explicit initial instantaneous-CG State required')
        if not isinstance(self.initial_actuator_state, ActuatorState):
            raise TypeError('Explicit initial ActuatorState required')
        if (self.hopper.model_scope != 'analytical_fixture'
                or self.propulsion.geometry.model_scope != 'analytical_fixture'):
            raise ValueError('Preliminary Simulation permits analytical fixtures only')
        if not callable(getattr(self.actuator_model, 'evaluate', None)):
            raise TypeError('actuator_model must implement evaluate')
        if not callable(getattr(self.environment_provider, 'sample', None)):
            raise TypeError('environment_provider must implement sample')
        if self.domain_policy not in DOMAIN_POLICIES:
            raise ValueError('Explicit supported domain_policy required')
        tolerance = _finite_scalar(
            self.initial_quaternion_unit_tolerance,
            'initial_quaternion_unit_tolerance', positive=True,
        )
        if tolerance >= 1.0:
            raise ValueError('Initial quaternion tolerance must be less than one')
        object.__setattr__(self, 'initial_quaternion_unit_tolerance', tolerance)
        norm = float(np.linalg.norm(self.initial_state.q_LB))
        if not np.isfinite(norm) or abs(norm - 1.0) > tolerance:
            raise ValueError('Initial quaternion is not unit within explicit tolerance')
        if isinstance(self.actuator_model, LaggedActuators):
            parameters = self.actuator_model.parameters
            if parameters.rotor_spin_signs != self.propulsion.geometry.spin_signs:
                raise ValueError('Actuator and propulsion rotor spin signs differ')
            parameters.validate_state(self.initial_actuator_state)

    def initial_vector(self):
        """Owned copy of every initial rigid-body and actuator component."""
        return pack_state(self.initial_state, self.initial_actuator_state)

    def evaluate(self, *, time_s, vector, command):
        """Evaluate derivatives at supplied time, state and held command.

        One actual AssemblyKinematics reaches mass, geometry, environment
        and propulsion evaluations. One mass snapshot supplies translation,
        moment arms and whole-vehicle angular-momentum balance. No previous
        time, controller integral or accumulated trajectory is retained.
        """
        time = _finite_scalar(time_s, 'time_s')
        if not isinstance(command, HeldCommand):
            raise TypeError('An immutable HeldCommand is required')
        state, actuator_state = unpack_state(vector, schema=PLANT_STATE_SCHEMA)
        actuator = self.actuator_model.evaluate(
            time_s=time, state=actuator_state, command=command,
        )
        if not isinstance(actuator, ActuatorEvaluation):
            raise TypeError('Actuator model must return ActuatorEvaluation')
        if actuator.model_scope != self.hopper.model_scope:
            raise ValueError('Actuator and mass-property scopes differ')
        kinematics = actuator.kinematics
        signs = np.asarray(self.propulsion.geometry.spin_signs)
        # Reject commands substituted for actual states, wrong rotor ordering,
        # and derivatives inconsistent with the six integrated actuator states.
        consistency_pairs = (
            (kinematics.gimbal_rad, actuator_state.actual_gimbal_rad),
            (kinematics.gimbal_rate_rad_s, actuator.derivative[4:6]),
            (kinematics.rotor_signed_speed_rad_s,
             signs * np.asarray(actuator_state.rotor_speed_magnitude_rad_s)),
            (kinematics.rotor_signed_acceleration_rad_s2,
             signs * np.asarray(actuator.derivative[:2])),
        )
        if any(not np.array_equal(a, b) for a, b in consistency_pairs):
            raise ValueError('Actuator kinematics do not match actual state/derivative')
        self.propulsion.geometry.validate_spin_kinematics(kinematics)
        mass = self.hopper.mass_properties(time_s=time, kinematics=kinematics)
        R_LB = quaternion_to_dcm(state.q_LB)
        points_D = self.propulsion.geometry.application_points_D_m(kinematics)
        with np.errstate(over='raise', invalid='raise'):
            arms_B = points_D - np.asarray(mass.cg_D_m)
            hub_positions = state.position_G_L_m + (R_LB @ arms_B.T).T
        hub_positions = finite_array(hub_positions, (2, 3), 'hub positions in L')
        environment = self.environment_provider.sample(
            time_s=time, state=state, mass_properties=mass,
            kinematics=kinematics, hub_positions_L_m=hub_positions.copy(),
        )
        if not isinstance(environment, EnvironmentSample):
            raise TypeError('Environment provider must return EnvironmentSample')
        if environment.model_scope != mass.model_scope:
            raise ValueError('Environment and mass-property scopes differ')
        if not np.array_equal(environment.hub_positions_L_m, hub_positions):
            raise ValueError('Environment sample does not match requested hub locations')
        hub_velocities = self.propulsion.hub_velocities_relative_air_M_m_s(
            state=state, mass_properties=mass, kinematics=kinematics,
            wind_at_hubs_L_m_s=environment.wind_at_hubs_L_m_s,
        )
        conditions = environment.coaxial_conditions(
            rotor_axial_spacing_m=self.propulsion.geometry.axial_spacing_m,
            rotor_velocity_relative_air_M_m_s=hub_velocities,
        )
        propulsion = self.propulsion.evaluate(
            time_s=time, kinematics=kinematics, conditions=conditions,
        )
        performance = propulsion.performance
        failed = [name for name, flag in performance.domain_checks if flag is False]
        unresolved = [name for name, flag in performance.domain_checks if flag is None]
        if failed:
            raise ModelDomainError('Reported propulsion domain violation: ' + ', '.join(failed))
        if unresolved and self.domain_policy == 'require_reported_admissible':
            raise ModelDomainError('Unresolved propulsion domains: ' + ', '.join(unresolved))
        wrench = resolve_applied_loads(
            loads=propulsion.rotor_loads + environment.additional_external_loads,
            mass_properties=mass,
            provenance=('Rotor and explicitly supplied nonpropulsive external loads; '
                        + propulsion.provenance + '; ' + environment.provenance),
        )
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            acceleration_L = (
                R_LB @ np.asarray(wrench.force_B_N) / mass.mass_kg
                + np.array([0.0, 0.0, environment.gravity_m_s2])
            )
        # Local CG velocity has no body-coordinate -omega cross v term.
        # Uniform gravity has no moment about complete-vehicle G. External
        # rotor aerodynamic couples are already included exactly once.
        # Internal servo/motor reactions are not extra external moments.
        angular_acceleration_B = mass.angular_acceleration_B_rad_s2(
            omega_B_rad_s=state.omega_B_rad_s,
            external_moment_B_G_N_m=wrench.moment_B_G_N_m,
        )
        derivative = np.concatenate((
            state.velocity_G_L_m_s,
            acceleration_L,
            quaternion_derivative(state.q_LB, state.omega_B_rad_s),
            angular_acceleration_B,
            np.asarray(actuator.derivative),
        ))
        return PlantEvaluation(
            derivative=derivative, state=state, actuator_state=actuator_state,
            actuator=actuator, mass_properties=mass, environment=environment,
            propulsion=propulsion, external_wrench=wrench,
        )

    def trajectory_ode(self, time_s, vector, *, command):
        """SciPy numerical RHS; decode its array and return an owned array."""
        return np.asarray(self.evaluate(
            time_s=time_s, vector=vector, command=command,
        ).derivative, dtype=float)

    def solve_ode(self, *, time_span_s, command, method, rtol, atol,
                  max_step_s, sample_times_s=None, dense_output=False,
                  events=None, raise_on_failure=True):
        """Integrate one held-command interval and return the actual OdeResult.

        Required numerical inputs: method ('RK45' or 'DOP853'), positive
        dimensionless rtol<1, nineteen positive atol values in PLANT_UNITS
        order, and positive finite max_step_s. These are solver settings,
        not controller cadence, physical tolerances or accepted vehicle limits.

        time_span_s must increase. The state at its start is exactly
        initial_vector(). Repeated calls restart there; no implicit continuation
        occurs. A later scheduler must carry the accepted endpoint explicitly,
        including all actuator states, into a new Simulation instance.

        sample_times_s are output times, NOT control update times. Events take
        (t,y) with nineteen components and must be pure; SciPy terminal and
        direction attributes are retained. status=1 denotes an event, not a
        solver failure and not accepted landing. If t_eval omits the event
        endpoint, use y_events or enabled dense output, not the last y column.

        On numerical failure, raise IntegrationFailure retaining .solution,
        unless raise_on_failure=False requests the failed result. Provider
        exceptions propagate without manufacturing a completed solution.

        No actual actuator-state clipping or quaternion renormalization occurs.
        Explicit RK trial stages may leave a model domain with excessive step
        size. Check tolerances and convergence independently; this is not a
        hard-stop/complementarity integrator or a coupled joint-load solver.
        """
        span = finite_array(time_span_s, (2,), 'time_span_s')
        if span[1] <= span[0]:
            raise ValueError('time_span_s must be strictly increasing')
        if not isinstance(command, HeldCommand):
            raise TypeError('An immutable HeldCommand is required')
        if method not in ('RK45', 'DOP853'):
            raise ValueError('Supported explicit methods are RK45 and DOP853')
        relative = _finite_scalar(rtol, 'rtol', positive=True)
        if relative >= 1.0:
            raise ValueError('rtol must be less than one')
        absolute = finite_array(atol, (PLANT_STATE_SIZE,), 'atol in PLANT_UNITS')
        if np.any(absolute <= 0.0):
            raise ValueError('All component absolute tolerances must be positive')
        maximum_step = _finite_scalar(max_step_s, 'max_step_s', positive=True)
        if type(dense_output) is not bool or type(raise_on_failure) is not bool:
            raise TypeError('dense_output and raise_on_failure must be bool')
        times = None
        if sample_times_s is not None:
            times = np.array(sample_times_s, dtype=float, copy=True)
            if (times.ndim != 1 or times.size == 0
                    or not np.all(np.isfinite(times))
                    or not np.all(np.diff(times) > 0.0)
                    or times[0] < span[0] or times[-1] > span[1]):
                raise ValueError('Invalid sample_times_s')
        if events is None or callable(events):
            event_functions = events
        else:
            event_functions = tuple(events)
            if not all(callable(event) for event in event_functions):
                raise TypeError('Every event must be callable')
        initial = self.initial_vector()
        self.evaluate(time_s=span[0], vector=initial, command=command)

        def held_rhs(time_s, vector):
            return self.trajectory_ode(time_s, vector, command=command)

        solution = solve_ivp(
            held_rhs, tuple(float(x) for x in span), initial,
            method=method, t_eval=times, dense_output=dense_output,
            events=event_functions, vectorized=False,
            rtol=relative, atol=absolute, max_step=maximum_step,
        )
        # Add interpretation metadata without replacing or projecting any raw
        # samples, event states, dense output or numerical failure information.
        solution.plant_context = {
            'schema': PLANT_STATE_SCHEMA,
            'components': PLANT_COMPONENTS,
            'units': PLANT_UNITS,
            'model_scope': 'analytical_fixture',
            'domain_policy': self.domain_policy,
            'requested_held_command': {
                'rotor_speed_magnitude_rad_s': command.rotor_speed_magnitude_rad_s,
                'gimbal_rad': command.gimbal_rad,
            },
            'initial_quaternion_unit_tolerance': self.initial_quaternion_unit_tolerance,
            'quaternion_samples_renormalized': False,
            'controller_updates_performed': 0,
            'translation_reference': 'instantaneous complete-vehicle CG G',
            'mission_scoring_reference': 'fixed D; separate conversion required',
            'physical_acceptance': 'not_assessed',
            'limitations': (
                'Provider-reported domains are not independent verification.',
                'Actuator response is an uncalibrated analytical realization.',
                'Articulated accuracy depends on supplied I_dot and relative momentum.',
                'Complete electrical/thermal evolution and contact are not supplied.',
                'No vehicle, mission, structural or hardware acceptance is inferred.',
            ),
        }
        if not solution.success and raise_on_failure:
            raise IntegrationFailure(str(solution.message), solution)
        return solution
