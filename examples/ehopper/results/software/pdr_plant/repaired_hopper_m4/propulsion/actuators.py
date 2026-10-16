"""PDR M4 fixed-D analytical plant: propulsion/actuators.py.

Current authority: system_model:system revision 4;
work-plan 99f7bb629eef45b89fa38d27c803868c revision 1;
interface 88561ff8b3ba4e8286cebd95a93e3b08 revision 1.
Pre-edit audit: PDR-PLANT-PRE-EDIT-AUDIT-M4-03 revision 1.

Reused from inspected previous_run/repaired_hopper_r12/propulsion/actuators.py.
Recovered file SHA256: bacfd1457ea3d24ae82d4868f3418b46c967fc2442d83d36e96973467645be78
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
from typing import Protocol

import numpy as np

from ..chassis.hopper import AssemblyKinematics
from ..helpers.math import finite_array


ACTUATOR_STATE_SCHEMA = 'hopper_m4_fixed_D_fixture_motor_gimbal_cascade_v1'
ACTUATOR_STATE_SIZE = 6
ACTUATOR_COMPONENTS = (
    'upper_rotor_speed_magnitude_rad_s',
    'lower_rotor_speed_magnitude_rad_s',
    'alpha_demand_filter_rad', 'beta_demand_filter_rad',
    'alpha_actual_rad', 'beta_actual_rad',
)
ACTUATOR_UNITS = ('rad/s', 'rad/s', 'rad', 'rad', 'rad', 'rad')


def _pair(value, name, *, positive=False):
    values = finite_array(value, (2,), name)
    if positive and np.any(values <= 0.0):
        raise ValueError(f'{name} must be positive')
    return tuple(float(x) for x in values)


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
    """Requested rotor speed magnitudes and generalized gimbal angles.

    Rotor order is upper/lower; gimbal order is alpha/beta. Finite requests
    outside limits are permitted so limiting can be reported explicitly.
    Negative speed requests are limited to zero, not interpreted as reversal.
    The command is held constant by the integration caller, not by RHS memory.
    """

    rotor_speed_magnitude_rad_s: tuple[float, float]
    gimbal_rad: tuple[float, float]

    def __post_init__(self):
        for name in ('rotor_speed_magnitude_rad_s', 'gimbal_rad'):
            object.__setattr__(self, name, _pair(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class ActuatorState:
    """Owned immutable snapshot; never silently clip actual states.

    Initial actual rate is determined by the difference between demand-filter
    and actual-angle states. It is not an independently assignable state in
    this realization. Preserve both pairs rather than resetting them equal.
    """

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
        return cls(
            rotor_speed_magnitude_rad_s=values[:2],
            demand_filter_gimbal_rad=values[2:4],
            actual_gimbal_rad=values[4:6],
        )


@dataclass(frozen=True, slots=True)
class LagParameters:
    """Explicit synthetic response inputs, not selected vehicle parameters.

    SI units are encoded in field names. Spin signs are opposite integers
    about the SAME module +z axis; physical CW/CCW labels require a stated
    viewing direction. No historical travel, time constant or limit defaults.

    Motors use first-order speed response with acceleration caps. Gimbal
    response uses two cascaded filters with a common scalar progress factor
    per stage. This preserves each stage's direction toward its target rather
    than independently lagging axes into an infeasible resultant tilt.

    Effective rates for BOTH stages are conservatively restricted to
      r_i = min(requested_rate_i, acceleration_limit_i * output_lag_s / 4).
    Thus the continuous output acceleration bound 4*r_i/output_lag_s does
    not exceed the supplied cap. This is a mathematical fixture construction,
    not a fitted servo model or a claim that requested rates are attained.

    Within |alpha|,|beta|<pi/2 the resultant cone is the convex set
      -log(cos(alpha))-log(cos(beta)) <= -log(cos(cone_limit)).
    Intersect it with the joint rectangle. Feasible initial filter states
    and targets yield continuous-time feasibility; numerical stages still
    require independent domain and step-size-convergence checks.
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
            raise ValueError('Fixture joint limits must be strictly inside +/- pi/2')
        if self.resultant_cone_limit_rad >= np.pi / 2.0:
            raise ValueError('Resultant cone must be strictly less than pi/2')
        if self.model_scope != 'analytical_fixture':
            raise ValueError('Uncalibrated lag realization is analytical-fixture only')
        _text(self.provenance, 'provenance')
        if isinstance(self.limitations, str):
            raise TypeError('limitations must be a sequence of strings')
        limitations = tuple(_text(x, 'limitation') for x in self.limitations)
        if not limitations:
            raise ValueError('Explicit model limitations are required')
        object.__setattr__(self, 'limitations', limitations)
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
        epsilon = 64.0 * np.finfo(float).eps
        # Roundoff allowance only, not mechanical clearance or travel margin.
        return bool(
            np.all(values >= np.asarray(self.joint_lower_rad) - epsilon)
            and np.all(values <= np.asarray(self.joint_upper_rad) + epsilon)
            and np.cos(values[0]) * np.cos(values[1])
            >= np.cos(self.resultant_cone_limit_rad) - epsilon
        )

    def bound_command(self, command):
        """Limit speed/joints, then radially reduce angles into the cone.

        Joint intervals contain zero, so radial reduction preserves them.
        This deterministic limiter is not a control allocator or a proof of
        simultaneous thrust/yaw authority. Retain requested and bounded
        commands separately for later saturation/anti-windup diagnostics.
        """
        if not isinstance(command, HeldCommand):
            raise TypeError('An immutable HeldCommand is required')
        speed = np.clip(command.rotor_speed_magnitude_rad_s,
                        0.0, self.rotor_speed_limit_rad_s)
        angles = np.clip(command.gimbal_rad,
                         self.joint_lower_rad, self.joint_upper_rad)
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
        result = HeldCommand(
            rotor_speed_magnitude_rad_s=speed, gimbal_rad=angles,
        )
        if not self.angles_are_admissible(result.gimbal_rad):
            raise ArithmeticError('Command limiter produced inadmissible angles')
        return result

    def validate_state(self, state):
        if not isinstance(state, ActuatorState):
            raise TypeError('Explicit ActuatorState required')
        if np.any(np.asarray(state.rotor_speed_magnitude_rad_s)
                  > np.asarray(self.rotor_speed_limit_rad_s)):
            raise ValueError('Actual rotor speed exceeds the configured fixture limit')
        for angles in (state.demand_filter_gimbal_rad, state.actual_gimbal_rad):
            if not self.angles_are_admissible(angles):
                raise ValueError('Actuator state leaves joint/cone domain; no silent clipping')


def _common_progress_rate(current, target, *, tau_s, rate_limits):
    """Rate=(target-current)/max(tau,max_i(abs(error_i)/rate_limit_i))."""
    delta = np.asarray(target) - np.asarray(current)
    ratios = np.abs(delta) / rate_limits
    largest = float(np.max(ratios))
    duration = max(tau_s, largest)
    return delta / duration, delta, ratios, largest, duration


def _output_acceleration(*, rate, delta, ratios, largest, duration,
                         tau_s, rate_limits, target_rate):
    """Right directional derivative of the output-stage rate map.

    At a tie, differentiate the maximum using the largest active directional
    derivative. Include zero for the constant-lag term at its transition.
    Acceleration may jump at a change of active constraint, but actual angle
    and rate remain continuous across held-command changes in this model.
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
    """Pure derivative, actual kinematics and static-limiter diagnostics.

    command_limited order: upper speed, lower speed, alpha, beta. These
    flags do not establish electrical feasibility or achieved wrench.
    Later anti-windup must also account for allocation and actuator lag.
    """

    derivative: tuple[float, ...]
    kinematics: AssemblyKinematics
    bounded_command: HeldCommand
    command_limited: tuple[bool, bool, bool, bool]
    model_scope: str

    def __post_init__(self):
        values = finite_array(self.derivative, (ACTUATOR_STATE_SIZE,), 'derivative')
        object.__setattr__(self, 'derivative', tuple(float(x) for x in values))
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
    """Pure response interface for this preliminary six-state realization.

    A calibrated model needing electrical states, delay, separate joint rates
    or other dimensions must version the state contract and migrate the
    Simulation/checker callers. Do not hide dynamic states in provider memory.
    """

    def evaluate(self, *, time_s: float, state: ActuatorState,
                 command: HeldCommand) -> ActuatorEvaluation:
        ...


@dataclass(frozen=True, slots=True)
class LaggedActuators:
    """Uncalibrated motor lag and bounded common-gimbal response.

    Unlimited motor error decays exponentially with motor_time_constant_s.
    With equal gimbal stage time constants tau and equal resting initial
    filter/actual angles, an unlimited constant-target response is
      angle(t)=target+(initial-target)*(1+t/tau)*exp(-t/tau).
    These are analytical expectations, not reported test outcomes.

    Each filter rate satisfies abs(rate_i)<=r_i. Output-stage error rate is
    bounded by 2*r_i; differentiating its common duration bounds acceleration
    by 4*r_i/output_lag_s. Numerical verification remains necessary.

    Omitted: loaded electrical/joint dynamics, mechanical torque limits,
    backlash, compliance, friction, deadband, transport delay and thermal
    evolution. No reverse spin, windmilling or regeneration is represented.
    Speed limits alone do not establish current, voltage or thermal limits.
    Internal response is prescribed, not coupled back from mechanical loads.
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
