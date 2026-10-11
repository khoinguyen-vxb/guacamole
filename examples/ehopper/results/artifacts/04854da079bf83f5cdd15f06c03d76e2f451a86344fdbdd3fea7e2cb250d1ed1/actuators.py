"""Bounded analytical actuator dynamics for the sandbox PDR-R9 plant.

New module supporting audited RC11/RC12 and the repaired Simulation caller.
Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal architecture: 84ef41fdd3fd4266ada43df2ace64a48 r1.

This concrete response model is ANALYTICAL-FIXTURE ONLY. It supplies no
vehicle defaults, hardware selection, calibrated response or test passes.
All parameters and initial actuator states must be supplied explicitly.
A vehicle response model requires separately reviewed/calibrated evidence.

State ordering (six SI scalars):
  [upper speed magnitude, lower speed magnitude] in rad/s,
  [alpha demand-filter state, beta demand-filter state] in rad,
  [actual alpha, actual beta] in rad.
The demand-filter states are internal numerical states, not extra joints.

Motor dynamics: first-order speed response with bounded acceleration and
bounded speed command. Gimbal dynamics: two cascaded, common-progress
first-order filters, each with rate limits. Actual generalized-coordinate
rates and accelerations are derived from the second filter. Both mechanical
joint limits AND the resultant thrust-vector cone constrain commands.

evaluate is pure. It does not advance state, retain history or update any
controller integral. A later integrator must advance the six states, using
one immutable HeldCommand over each control interval. Controller sampling
and anti-windup belong outside adaptive ODE RHS evaluations.

No actuator torque is returned as an external whole-vehicle moment. The
returned AssemblyKinematics must also reach the mass-property provider for
consistent I_dot, h_rel and h_rel_dot, or an explicit reduced approximation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..chassis.hopper import AssemblyKinematics
from ..helpers.math import finite_array


ACTUATOR_STATE_SCHEMA = 'pdr_r9_fixture_motor_gimbal_cascade_v1'
ACTUATOR_STATE_SIZE = 6
ACTUATOR_COMPONENTS = (
    'upper_rotor_speed_magnitude_rad_s',
    'lower_rotor_speed_magnitude_rad_s',
    'alpha_demand_filter_rad', 'beta_demand_filter_rad',
    'alpha_actual_rad', 'beta_actual_rad',
)
ACTUATOR_UNITS = ('rad/s', 'rad/s', 'rad', 'rad', 'rad', 'rad')


def _pair(value, name, *, positive=False):
    array = finite_array(value, (2,), name)
    if positive and np.any(array <= 0.0):
        raise ValueError(f'{name} must be positive')
    return tuple(float(x) for x in array)


def _positive(value, name):
    number = float(value)
    if not np.isfinite(number) or number <= 0.0:
        raise ValueError(f'{name} must be finite and positive')
    return number


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


@dataclass(frozen=True, slots=True)
class HeldCommand:
    """Requested speed magnitudes and joint angles, held between samples.

    Entries are upper/lower rotor and alpha/beta respectively. Finite
    out-of-range requests are allowed here so saturation can be explicit.
    Negative requested rotor speeds are limited to zero, not rotor reversal.
    This is a speed-response abstraction, NOT an ESC PWM/voltage interface
    or evidence that the chosen hardware regulates speed internally.
    """

    rotor_speed_magnitude_rad_s: tuple[float, float]
    gimbal_rad: tuple[float, float]

    def __post_init__(self):
        for name in ('rotor_speed_magnitude_rad_s', 'gimbal_rad'):
            object.__setattr__(self, name, _pair(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class ActuatorState:
    """Immutable actuator snapshot; no implicit clipping or normalization."""

    rotor_speed_magnitude_rad_s: tuple[float, float]
    demand_filter_gimbal_rad: tuple[float, float]
    actual_gimbal_rad: tuple[float, float]

    def __post_init__(self):
        for name in (
            'rotor_speed_magnitude_rad_s',
            'demand_filter_gimbal_rad', 'actual_gimbal_rad',
        ):
            object.__setattr__(self, name, _pair(getattr(self, name), name))
        if any(x < 0.0 for x in self.rotor_speed_magnitude_rad_s):
            raise ValueError('Actual rotor speed magnitudes cannot be negative')

    def as_vector(self):
        return np.array(
            self.rotor_speed_magnitude_rad_s
            + self.demand_filter_gimbal_rad + self.actual_gimbal_rad,
            dtype=float,
        )

    @classmethod
    def from_vector(cls, vector, *, schema):
        if schema != ACTUATOR_STATE_SCHEMA:
            raise ValueError('Explicit supported actuator-state schema required')
        values = finite_array(vector, (ACTUATOR_STATE_SIZE,), 'actuator state')
        return cls(values[:2], values[2:4], values[4:6])


@dataclass(frozen=True, slots=True)
class LagParameters:
    """Explicit numerical fixture parameters; no selected vehicle values.

    Motor time constants: s; speed caps: rad/s; acceleration caps: rad/s^2.
    Gimbal filter time constants: s; joint/cone limits: rad; generalized
    rate limits: rad/s; generalized acceleration limits: rad/s^2.

    Each gimbal filter uses a COMMON scalar progress factor for alpha/beta,
    preserving a straight-line direction toward its instantaneous target.
    Independent axis lag factors are intentionally not used: they can leave
    the feasible resultant-cone region even with feasible endpoints.

    The effective rate r_i for BOTH filters is conservatively restricted to
    min(requested_rate_i, acceleration_limit_i * output_lag_s / 4).
    This bounds the output-filter acceleration by the requested cap; it is
    not an optimized actuator model or an identification of a real servo.

    The ideal feasible angle set is convex for |alpha|, |beta| < pi/2:
      -log(cos(alpha)) - log(cos(beta)) <= -log(cos(cone)).
    Intersect it with the joint-limit rectangle. Each filter points toward
    a feasible target, so the continuous-time model preserves feasibility.
    Numerical integrator stages still require appropriate tolerances and
    step-size convergence checks; invalid states are not silently clipped.
    """

    rotor_spin_signs: tuple[int, int]
    motor_time_constant_s: tuple[float, float]
    rotor_speed_limit_rad_s: tuple[float, float]
    rotor_acceleration_limit_rad_s2: tuple[float, float]
    gimbal_demand_lag_s: float
    gimbal_output_lag_s: float
    joint_lower_rad: tuple[float, float]
    joint_upper_rad: tuple[float, float]
    resultant_cone_limit_rad: float
    gimbal_rate_limit_rad_s: tuple[float, float]
    gimbal_acceleration_limit_rad_s2: tuple[float, float]
    model_scope: str
    provenance: str
    limitations: tuple[str, ...]

    def __post_init__(self):
        signs = tuple(self.rotor_spin_signs)
        if (len(signs) != 2 or any(type(x) is not int for x in signs)
                or set(signs) != {-1, 1}):
            raise ValueError('Opposite integer spin signs about common +z_M required')
        object.__setattr__(self, 'rotor_spin_signs', signs)
        for name in (
            'motor_time_constant_s', 'rotor_speed_limit_rad_s',
            'rotor_acceleration_limit_rad_s2', 'gimbal_rate_limit_rad_s',
            'gimbal_acceleration_limit_rad_s2',
        ):
            object.__setattr__(self, name, _pair(
                getattr(self, name), name, positive=True,
            ))
        for name in ('gimbal_demand_lag_s', 'gimbal_output_lag_s',
                     'resultant_cone_limit_rad'):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        for name in ('joint_lower_rad', 'joint_upper_rad'):
            object.__setattr__(self, name, _pair(getattr(self, name), name))
        lower = np.asarray(self.joint_lower_rad)
        upper = np.asarray(self.joint_upper_rad)
        if (np.any(lower >= upper) or np.any(lower > 0.0)
                or np.any(upper < 0.0)):
            raise ValueError('Each joint interval must contain zero and have positive width')
        if np.any(lower <= -np.pi / 2.0) or np.any(upper >= np.pi / 2.0):
            raise ValueError('This fixture requires joint limits strictly inside +/- pi/2')
        if self.resultant_cone_limit_rad >= np.pi / 2.0:
            raise ValueError('Resultant cone must be strictly less than pi/2')
        if self.model_scope != 'analytical_fixture':
            raise ValueError('This uncalibrated lag implementation is analytical-fixture only')
        _text(self.provenance, 'provenance')
        if isinstance(self.limitations, str):
            raise TypeError('limitations must be a sequence of strings')
        limits = tuple(_text(x, 'limitation') for x in self.limitations)
        if not limits:
            raise ValueError('Explicit model limitations are required')
        object.__setattr__(self, 'limitations', limits)
        # Reject numerical overflow/underflow rather than lose a bound.
        self.effective_gimbal_rate_rad_s()

    def effective_gimbal_rate_rad_s(self):
        with np.errstate(over='raise', invalid='raise', under='raise'):
            acceleration_bound = (
                np.asarray(self.gimbal_acceleration_limit_rad_s2)
                * (self.gimbal_output_lag_s / 4.0)
            )
            rates = np.minimum(self.gimbal_rate_limit_rad_s, acceleration_bound)
        return np.asarray(_pair(rates, 'effective gimbal rate', positive=True))

    def angles_are_admissible(self, angles):
        values = finite_array(angles, (2,), 'gimbal angles')
        # Floating-point allowance only, not mechanical clearance/margin.
        epsilon = 64.0 * np.finfo(float).eps
        lower = np.asarray(self.joint_lower_rad)
        upper = np.asarray(self.joint_upper_rad)
        return bool(
            np.all(values >= lower - epsilon)
            and np.all(values <= upper + epsilon)
            and np.cos(values[0]) * np.cos(values[1])
            >= np.cos(self.resultant_cone_limit_rad) - epsilon
        )

    def bound_command(self, command):
        """Clip speed/joints, then radially reduce angles to the exact cone.

        Radial reduction toward zero preserves the joint intervals because
        each contains zero. This is a deterministic conservative limiter,
        not a least-squares control allocator or an authority assessment.
        Return the bounded request; callers retain the original request for
        saturation/anti-windup diagnostics. Lagged achieved output differs.
        """
        if not isinstance(command, HeldCommand):
            raise TypeError('An immutable HeldCommand is required')
        speed = np.clip(command.rotor_speed_magnitude_rad_s,
                        0.0, self.rotor_speed_limit_rad_s)
        angles = np.clip(command.gimbal_rad, self.joint_lower_rad,
                         self.joint_upper_rad)
        cone_cos = np.cos(self.resultant_cone_limit_rad)
        if np.cos(angles[0]) * np.cos(angles[1]) < cone_cos:
            low, high = 0.0, 1.0
            for _ in range(64):
                middle = 0.5 * (low + high)
                trial = middle * angles
                if np.cos(trial[0]) * np.cos(trial[1]) >= cone_cos:
                    low = middle
                else:
                    high = middle
            angles = low * angles
        result = HeldCommand(speed, angles)
        if not self.angles_are_admissible(result.gimbal_rad):
            raise ArithmeticError('Command limiter produced inadmissible angles')
        return result

    def validate_state(self, state):
        if not isinstance(state, ActuatorState):
            raise TypeError('Explicit ActuatorState required')
        speeds = np.asarray(state.rotor_speed_magnitude_rad_s)
        if np.any(speeds > np.asarray(self.rotor_speed_limit_rad_s)):
            raise ValueError('Actual rotor speed exceeds configured fixture limit')
        for angles in (state.demand_filter_gimbal_rad, state.actual_gimbal_rad):
            if not self.angles_are_admissible(angles):
                raise ValueError('Actuator state leaves joint/cone domain; no silent clipping')


def _common_progress_rate(current, target, *, tau_s, rate_limits):
    """Vector first-order filter with common rate-limited progress.

    Return rate plus quantities needed for its directional derivative.
    duration=max(tau, max_i(abs(target_i-current_i)/rate_limit_i)).
    The rate is (target-current)/duration, including at zero error.
    """
    delta = np.asarray(target) - np.asarray(current)
    ratios = np.abs(delta) / rate_limits
    largest = float(np.max(ratios))
    duration = max(tau_s, largest)
    rate = delta / duration
    return rate, delta, ratios, largest, duration


def _output_acceleration(*, rate, delta, ratios, largest, duration,
                         tau_s, rate_limits, target_rate):
    """Right directional derivative of the continuous output-rate map.

    At tied rate constraints use the largest directional derivative of the
    active max terms. At the lag/rate transition include the constant lag
    term's zero derivative. Acceleration can change discontinuously, but
    actual angle and rate remain continuous across held-command changes.
    """
    delta_rate = np.asarray(target_rate) - rate
    duration_rate = 0.0
    if largest >= tau_s:
        active = ratios == largest
        slopes = np.sign(delta[active]) * delta_rate[active] / rate_limits[active]
        duration_rate = float(np.max(slopes))
        if largest == tau_s:
            duration_rate = max(0.0, duration_rate)
    return delta_rate / duration - (delta / duration) * (duration_rate / duration)


@dataclass(frozen=True, slots=True)
class ActuatorEvaluation:
    """Pure derivative, actual kinematics and command-limiter diagnostics.

    command_limited ordering is upper speed, lower speed, alpha, beta.
    This reports static command limiting, not electrical feasibility or
    achieved wrench. Anti-windup must additionally account for allocation,
    lag and actual achieved thrust/torque in the later controller proposal.
    """

    derivative: tuple[float, ...]
    kinematics: AssemblyKinematics
    bounded_command: HeldCommand
    command_limited: tuple[bool, bool, bool, bool]
    model_scope: str

    def __post_init__(self):
        derivative = finite_array(self.derivative, (ACTUATOR_STATE_SIZE,), 'derivative')
        object.__setattr__(self, 'derivative', tuple(float(x) for x in derivative))
        if not isinstance(self.kinematics, AssemblyKinematics):
            raise TypeError('Explicit AssemblyKinematics required')
        if not isinstance(self.bounded_command, HeldCommand):
            raise TypeError('Explicit bounded HeldCommand required')
        flags = tuple(self.command_limited)
        if len(flags) != 4 or any(type(x) is not bool for x in flags):
            raise TypeError('Four boolean command-limited flags required')
        object.__setattr__(self, 'command_limited', flags)
        if self.model_scope != 'analytical_fixture':
            raise ValueError('Fixture actuator evaluation cannot represent a vehicle baseline')


class ActuatorModel(Protocol):
    """Pure response interface for the preliminary six-state realization.

    A future calibrated realization with different state dimensions must
    version its state contract and update Simulation/checker callers.
    """

    def evaluate(self, *, time_s: float, state: ActuatorState,
                 command: HeldCommand) -> ActuatorEvaluation:
        ...


@dataclass(frozen=True, slots=True)
class LaggedActuators:
    """Analytical motor lag and bounded, smooth-output gimbal response.

    In an unlimited channel the motor speed error decays exponentially
    with its configured time constant. For equal gimbal stage time
    constants tau, a rest-to-step response without limiting is
      angle(t)=target+(initial-target)*(1+t/tau)*exp(-t/tau).
    These provide independent analytical verification fixtures.

    For either gimbal filter, each rate magnitude is <= r_i. For the output
    filter, delta_dot_i is therefore bounded by 2*r_i. When rate-limited by
    channel j, abs(delta_i/delta_j)<=r_i/r_j. Its acceleration is bounded
    by 4*r_i/tau_output; the effective-rate construction enforces the given
    acceleration cap. This proof is for the continuous mathematical model,
    not evidence that its numerical implementation has passed a test.

    Initial actual angle/rate cannot be specified independently in this
    realization: the demand-filter state and actual angle determine rate.
    Preserve and report both initial states; do not silently set them equal.

    Limitations: prescribed response, not a motor electrical or joint-load
    solution; no backlash, compliance, friction, deadband, delay or thermal
    dynamics; no rotor reversal/windmilling; no feedback from mechanical
    load into this response. Coaxial/electrical limits are checked by the
    separate paired map and are not established by these speed bounds.
    """

    parameters: LagParameters

    def __post_init__(self):
        if not isinstance(self.parameters, LagParameters):
            raise TypeError('Explicit LagParameters required')

    def evaluate(self, *, time_s, state, command):
        time = float(time_s)
        if not np.isfinite(time):
            raise ValueError('time_s must be finite')
        params = self.parameters
        params.validate_state(state)
        bounded = params.bound_command(command)
        effective_rates = params.effective_gimbal_rate_rad_s()
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            motor_rate = (
                np.asarray(bounded.rotor_speed_magnitude_rad_s)
                - np.asarray(state.rotor_speed_magnitude_rad_s)
            ) / np.asarray(params.motor_time_constant_s)
            motor_rate = np.clip(
                motor_rate, -np.asarray(params.rotor_acceleration_limit_rad_s2),
                np.asarray(params.rotor_acceleration_limit_rad_s2),
            )
            demand_rate, _, _, _, _ = _common_progress_rate(
                state.demand_filter_gimbal_rad, bounded.gimbal_rad,
                tau_s=params.gimbal_demand_lag_s, rate_limits=effective_rates,
            )
            actual_rate, delta, ratios, largest, duration = _common_progress_rate(
                state.actual_gimbal_rad, state.demand_filter_gimbal_rad,
                tau_s=params.gimbal_output_lag_s, rate_limits=effective_rates,
            )
            actual_acceleration = _output_acceleration(
                rate=actual_rate, delta=delta, ratios=ratios,
                largest=largest, duration=duration,
                tau_s=params.gimbal_output_lag_s, rate_limits=effective_rates,
                target_rate=demand_rate,
            )
        actual_acceleration = finite_array(
            actual_acceleration, (2,), 'actual gimbal acceleration',
        )
        acceleration_cap = np.asarray(params.gimbal_acceleration_limit_rad_s2)
        if np.any(np.abs(actual_acceleration) > acceleration_cap * (1.0 + 1e-12)):
            raise ArithmeticError('Gimbal acceleration bound violated; do not clip evidence')
        signs = np.asarray(params.rotor_spin_signs)
        kinematics = AssemblyKinematics(
            gimbal_rad=state.actual_gimbal_rad,
            gimbal_rate_rad_s=actual_rate,
            gimbal_acceleration_rad_s2=actual_acceleration,
            rotor_signed_speed_rad_s=(
                signs * np.asarray(state.rotor_speed_magnitude_rad_s)
            ),
            rotor_signed_acceleration_rad_s2=signs * motor_rate,
        )
        requested = command.rotor_speed_magnitude_rad_s + command.gimbal_rad
        limited = bounded.rotor_speed_magnitude_rad_s + bounded.gimbal_rad
        return ActuatorEvaluation(
            derivative=np.concatenate((motor_rate, demand_rate, actual_rate)),
            kinematics=kinematics,
            bounded_command=bounded,
            command_limited=tuple(a != b for a, b in zip(requested, limited)),
            model_scope=params.model_scope,
        )
