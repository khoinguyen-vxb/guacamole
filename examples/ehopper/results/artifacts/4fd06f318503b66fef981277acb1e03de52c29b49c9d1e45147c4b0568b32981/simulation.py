"""Preliminary sandbox repair of 6dof_hopper/simulation/simulation.py.

Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1, RC01-RC15.
Original source/callers: retained source_inventory.json and source_callers.md.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal decision: 84ef41fdd3fd4266ada43df2ace64a48 r1.

Intentional migration:
  Explicit package-relative imports replace the invalid top-level State import.
  One authoritative initial rigid-body and actuator state is preserved.
  The RHS decodes numeric arrays; it never treats them as State objects.
  Time comes from the solver argument, not undefined self.time.
  Position/velocity are local NED components at instantaneous whole-vehicle G.
  Full inertia and internal relative momentum come from one mass snapshot.
  Propulsion is evaluated at actual rotor/gimbal states and actual hub inflow.
  Applied loads are shifted to G exactly once; internal reactions are not
  added as external whole-vehicle moments. No cylinder aero is imported.
  solve_ode returns the actual SciPy result, including events/dense output.

The present implementation permits ANALYTICAL FIXTURES ONLY. Its actuator
realization is uncalibrated and the environment does not close a dynamic
battery/thermal model. No vehicle feasibility, mission or hardware acceptance
is implied. This restriction must not be bypassed by relabelling vehicle data.

No PID is implemented, tuned or evaluated here. One immutable HeldCommand
is captured for an entire integration interval. A later fixed-cadence outer
scheduler must update controller memory once at t_k, integrate to t_(k+1),
and carry the accepted endpoint into a new Simulation instance. It must not
reset actuator states or update PID memory from adaptive RHS calls.

This module performs no file writes, logging, history accumulation, automatic
quaternion renormalization or installation changes. Writing it is not a test.
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


PLANT_STATE_SCHEMA = 'pdr_r9_cg_ned_frd_wxyz_fixture_actuators_v1'
PLANT_STATE_SIZE = STATE_SIZE + ACTUATOR_STATE_SIZE
PLANT_COMPONENTS = STATE_COMPONENTS + ACTUATOR_COMPONENTS
PLANT_UNITS = STATE_UNITS + ACTUATOR_UNITS
DOMAIN_POLICIES = (
    'require_reported_admissible',
    'allow_unresolved_analytical_fixture',
)


class ModelDomainError(ValueError):
    """Known invalid or disallowed unresolved operating domain.

    This stops the calculation; it is not converted into clipped thrust,
    an accepted operating point or a successful integration result.
    """


class IntegrationFailure(RuntimeError):
    """Solver failure retaining its actual result for diagnostic inspection."""

    def __init__(self, message, solution):
        super().__init__(message)
        self.solution = solution


def _finite_scalar(value, name, *, positive=False):
    number = float(value)
    if not np.isfinite(number) or (positive and number <= 0.0):
        raise ValueError(f'{name} must be finite' + (' and positive' if positive else ''))
    return number


def pack_state(state, actuator_state):
    """Combine explicitly typed snapshots; preserve every stored component.

    There are 13 rigid-body and 6 actuator components. Quaternion norm
    error is retained, not normalized away. This is not a legacy-state
    importer: the body/local velocity migration must be explicit upstream.
    """
    if not isinstance(state, State) or not isinstance(actuator_state, ActuatorState):
        raise TypeError('Explicit State and ActuatorState required')
    return np.concatenate((state.as_vector(), actuator_state.as_vector()))


def unpack_state(vector, *, schema):
    """Decode the versioned 19-component plant vector without side effects."""
    if schema != PLANT_STATE_SCHEMA:
        raise ValueError('Explicit supported plant-state schema required')
    values = finite_array(vector, (PLANT_STATE_SIZE,), 'plant state')
    return (
        State.from_vector(values[:STATE_SIZE], schema=STATE_VECTOR_SCHEMA),
        ActuatorState.from_vector(values[STATE_SIZE:], schema=ACTUATOR_STATE_SCHEMA),
    )


@dataclass(frozen=True, slots=True)
class PlantEvaluation:
    """One immutable evaluation, not accepted-step history or verification.

    Re-evaluate explicitly at accepted solution samples for reporting. RHS
    trial evaluations must not be interpreted as a trajectory or integrated
    to obtain energy. Electrical properties below are instantaneous bus
    arithmetic, not battery/thermal acceptance or mission endurance.
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
        derivative = finite_array(self.derivative, (PLANT_STATE_SIZE,), 'plant derivative')
        object.__setattr__(self, 'derivative', tuple(float(x) for x in derivative))
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
    """Pure analytical plant plus an explicit one-command solver boundary.

    Providers must be pure: identical arguments must produce identical
    outputs regardless of evaluation order. Frozen records alone cannot
    prove purity of arbitrary user-supplied provider implementations.
    The retained checker must test repeatability and lack of state mutation.

    Initial quaternion tolerance is a numerical input, dimensionless. The
    initial quaternion must already be unit within that tolerance; nothing
    is silently normalized. For an explicitly normalized initialization,
    use State.with_normalized_orientation before constructing Simulation
    and retain that initialization policy in the fixture configuration.

    Domain policies govern provider REPORTED admissibility only. False is
    always rejected. None is permitted only under the explicitly named
    analytical-fixture policy. Even all True reports do not independently
    establish calibrated map validity or complete electrical feasibility:
    the paired-map battery-current check excludes auxiliary consumers.

    No structural or contact model is supplied. Events may mark analytical
    surfaces, but an event is not a landing/impact validation model.
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
            raise ValueError('This preliminary Simulation permits analytical fixtures only')
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
        """Return an owned copy; do not discard nonzero initialization."""
        return pack_state(self.initial_state, self.initial_actuator_state)

    def evaluate(self, *, time_s, vector, command):
        """Pure force/momentum/actuator evaluation at the supplied time/state.

        The same actual AssemblyKinematics is used for mass properties,
        hub positions/velocities, paired propulsion and angular momentum.
        No PID memory, energy accumulator or previous evaluation time exists.
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
        # Reject a provider substituting commands for actual states or using
        # inconsistent component order/signs. Derivatives must match the
        # same six-state realization advanced by solve_ivp.
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
        points_B0 = self.propulsion.geometry.application_points_B0_m(kinematics)
        arms_B = points_B0 - np.asarray(mass.cg_B0_m)
        hub_positions = finite_array(
            state.position_G_L_m + (R_LB @ arms_B.T).T,
            (2, 3), 'hub positions in L',
        )
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
            provenance=('Rotor plus explicitly supplied nonpropulsive external loads; '
                        + propulsion.provenance + '; ' + environment.provenance),
        )
        acceleration_L = (
            R_LB @ np.asarray(wrench.force_B_N) / mass.mass_kg
            + np.array([0.0, 0.0, environment.gravity_m_s2])
        )
        # Local CG velocity has NO body-velocity -omega cross v term.
        # Angular momentum includes I_dot and prescribed relative momentum;
        # no second motor/servo reaction torque is added here.
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
        """SciPy-compatible numerical RHS with an explicitly held command."""
        return np.asarray(self.evaluate(
            time_s=time_s, vector=vector, command=command,
        ).derivative, dtype=float)

    def solve_ode(self, *, time_span_s, command, method, rtol, atol,
                  max_step_s, sample_times_s=None, dense_output=False,
                  events=None, raise_on_failure=True):
        """Integrate ONE held-command interval; return the actual OdeResult.

        Required numerical inputs:
          method: 'RK45' or 'DOP853'; no vectorized RHS/Jacobian perturbation.
          rtol: positive dimensionless relative tolerance less than one.
          atol: 19 positive absolute tolerances in PLANT_UNITS order.
          max_step_s: positive finite maximum step duration in seconds.
        These are numerical fixture settings, not selected control cadence.

        time_span_s is [t_start, t_end], strictly increasing. Initialization
        is exactly initial_vector() at t_start, including every nonzero
        position, velocity, attitude, angular rate and actuator component.
        Repeated calls restart from this same initial vector; they do not
        silently continue a previous result. An outer scheduler must carry
        the accepted endpoint explicitly, e.g. with dataclasses.replace.

        sample_times_s, when supplied, must be strictly increasing and lie
        in the interval. They are OUTPUT times, not controller sample times.
        dense_output and events are passed to SciPy. Events receive (t,y)
        with the full 19-component vector and must also be pure. Their
        terminal/direction attributes retain the SciPy semantics.

        A terminal event is returned with status=1; it is not treated as an
        integration failure or as evidence of physical landing acceptance.
        If sample_times omits the event endpoint, use y_events, or dense
        output when enabled, rather than assuming result.y[:,-1] is that
        endpoint. For event-free cadence intervals, request the endpoint.

        On solver failure, raise IntegrationFailure with .solution retained,
        unless raise_on_failure=False explicitly requests the failed result.
        Provider/domain exceptions propagate; they do not manufacture a
        completed OdeResult. Inspect numerical convergence independently.

        Actuator domains are not silently clipped during integration.
        Explicit RK trial stages may leave a physical state domain with an
        overly large step; select suitable max_step/tolerances and verify
        convergence. This implementation is not an event-driven hard-stop
        or complementarity solver.
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
        # Validate initial providers/domains without retaining mutable history.
        self.evaluate(time_s=span[0], vector=initial, command=command)

        def held_rhs(time_s, vector):
            return self.trajectory_ode(time_s, vector, command=command)

        solution = solve_ivp(
            held_rhs, tuple(float(x) for x in span), initial,
            method=method, t_eval=times, dense_output=dense_output,
            events=event_functions, vectorized=False,
            rtol=relative, atol=absolute, max_step=maximum_step,
        )
        # Add interpretation metadata without replacing, projecting or
        # normalizing any raw solver samples, dense output or event states.
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
            'physical_acceptance': 'not_assessed',
            'limitations': (
                'Provider-reported domains are not independent verification.',
                'Actuator lag is an uncalibrated analytical realization.',
                'Internal-motion accuracy depends on supplied momentum terms.',
                'Complete electrical/thermal evolution and contact are not supplied.',
                'No vehicle, mission, structural or hardware acceptance is inferred.',
            ),
        }
        if not solution.success and raise_on_failure:
            raise IntegrationFailure(str(solution.message), solution)
        return solution
