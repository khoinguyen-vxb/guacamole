"""Complete-vehicle mass properties for the sandbox PDR-R9 plant.

Audited original: 6dof_hopper/chassis/hopper.py
Original SHA-256: 6e2b2f93e98b844ce04f68d26b704c65270e9329e1abff76caa45cbcd5dcf0bd
Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1, RC08/RC12.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal decision: 84ef41fdd3fd4266ada43df2ace64a48 r1.

Intentional API migration, affecting Simulation.trajectory_ode:
  Replace separate mass(time), CG(time), inertia(time) calls with ONE
  mass_properties(time_s=..., kinematics=...) snapshot. This avoids mixing
  properties from different configurations or provider evaluations.
  The installed mass includes propulsion, battery and all other equipment
  exactly once. There is no additional propulsion.get_mass() contribution.
  Propulsion loads belong to an explicit external-wrench interface, not this
  mass-property object. The old get_thrust_and_moment forwarding is removed.
  Cylinder dimensions and legacy aerodynamic coefficients are not retained
  as implicit descriptions of the required exposed structure.

All vector components use structure-fixed FRD axes B. CG coordinates are
relative to the FIXED neutral-CG structural datum O_B0. Inertia and angular
momentum are about instantaneous complete-vehicle CG G. SI units throughout.
No numerical vehicle inputs or physical validation are supplied by this file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..helpers.math import finite_array


MASS_PROPERTY_SCHEMA = 'pdr_r9_complete_vehicle_instantaneous_cg_v1'
MODEL_SCOPES = ('analytical_fixture', 'provisional_vehicle')
DYNAMICS_MODES = (
    'rigid_body_fixture',
    'prescribed_internal_momentum',
    'reduced_articulated',
)


def _positive_scalar(value, name):
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f'{name} must be finite and positive')
    return result


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def _vector_tuple(value, size, name):
    return tuple(float(x) for x in finite_array(value, (size,), name))


def _symmetric_matrix_tuple(value, name, *, require_inertia=False):
    matrix = finite_array(value, (3, 3), name)
    scale = float(np.max(np.abs(matrix)))
    if scale == 0.0:
        if require_inertia:
            raise ValueError(f'{name} must be positive definite')
        return tuple(tuple(float(x) for x in row) for row in matrix)
    scaled = matrix / scale
    if np.max(np.abs(scaled - scaled.T)) > 1e-12:
        raise ValueError(f'{name} must be symmetric; no silent symmetrization')
    if require_inertia:
        eigenvalues = np.linalg.eigvalsh(scaled)
        if np.min(eigenvalues) <= 0.0:
            raise ValueError(f'{name} must be positive definite')
        # A physical inertia tensor also obeys the principal-moment triangle
        # inequalities. Permit only roundoff-sized violation in scaled units.
        if eigenvalues[-1] > eigenvalues[0] + eigenvalues[1] + 1e-12:
            raise ValueError(f'{name} violates principal-moment triangle inequality')
    return tuple(tuple(float(x) for x in row) for row in matrix)


@dataclass(frozen=True, slots=True)
class AssemblyKinematics:
    """Prescribed internal motion supplied by the actuator model.

    Gimbal order is [alpha, beta], with R_BM=Rx(alpha)Ry(beta): outer
    body-fixed x rotation and inner carried y rotation. Rates and
    accelerations are generalized-coordinate derivatives, NOT components
    of a single angular-velocity vector.

    Rotor entries have stable upper/lower ordering. Speeds and their
    derivatives are SIGNED about the common +z_M axis. They describe spin
    relative to the module, not total inertial rotor angular velocity.
    Counter-rotation and permitted spin directions are checked by the
    propulsion model. Zero vectors must be supplied explicitly for fixtures.

    This is an interface, not a joint-load or multibody dynamics solution.
    """

    gimbal_rad: tuple[float, float]
    gimbal_rate_rad_s: tuple[float, float]
    gimbal_acceleration_rad_s2: tuple[float, float]
    rotor_signed_speed_rad_s: tuple[float, float]
    rotor_signed_acceleration_rad_s2: tuple[float, float]

    def __post_init__(self):
        for name in (
            'gimbal_rad', 'gimbal_rate_rad_s', 'gimbal_acceleration_rad_s2',
            'rotor_signed_speed_rad_s', 'rotor_signed_acceleration_rad_s2',
        ):
            object.__setattr__(self, name, _vector_tuple(getattr(self, name), 2, name))


@dataclass(frozen=True, slots=True)
class MassProperties:
    """One immutable complete-vehicle mass-property/momentum snapshot.

    inertia_B_G_kg_m2 is the full locked-configuration inertia about G,
    including moving parts and rotor mass exactly once. Its derivative is
    the derivative of its B components due to internal configuration motion;
    it does not include a body-to-local rotation derivative.

    relative_momentum_B_kg_m2_s is h_rel in H_B=I_B,G*omega_B+h_rel.
    It includes relative spin, joint motion and moving-mass contributions
    required by the selected model. relative_momentum_rate_B_N_m is the
    derivative of those B components, excluding omega_B cross h_rel.
    Do NOT use motor/servo reaction torque as an additional external moment.

    Modes:
      rigid_body_fixture: analytical rigid-body model, with all property
        derivatives and relative momentum explicitly zero; not a vehicle.
      prescribed_internal_momentum: provider supplies I_dot, h_rel and
        h_rel_dot consistently for its prescribed internal motion. This
        label is not a claim of validated or dynamically coupled joints.
      reduced_articulated: h_rel and h_rel_dot are explicitly neglected.
        Configuration-dependent inertia and I_dot may be supplied, but
        those alone do not represent articulated dynamics completely.

    Every mode requires provenance and limitations. No omitted term or
    numerical vehicle input is silently filled with zero.
    """

    mass_kg: float
    cg_B0_m: tuple[float, float, float]
    cg_rate_B0_m_s: tuple[float, float, float]
    inertia_B_G_kg_m2: tuple
    inertia_rate_B_G_kg_m2_s: tuple
    relative_momentum_B_kg_m2_s: tuple[float, float, float]
    relative_momentum_rate_B_N_m: tuple[float, float, float]
    model_scope: str
    dynamics_mode: str
    provenance: str
    limitations: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'mass_kg', _positive_scalar(self.mass_kg, 'mass_kg'))
        for name in (
            'cg_B0_m', 'cg_rate_B0_m_s',
            'relative_momentum_B_kg_m2_s', 'relative_momentum_rate_B_N_m',
        ):
            object.__setattr__(self, name, _vector_tuple(getattr(self, name), 3, name))
        object.__setattr__(self, 'inertia_B_G_kg_m2', _symmetric_matrix_tuple(
            self.inertia_B_G_kg_m2, 'inertia_B_G_kg_m2', require_inertia=True,
        ))
        object.__setattr__(self, 'inertia_rate_B_G_kg_m2_s', _symmetric_matrix_tuple(
            self.inertia_rate_B_G_kg_m2_s, 'inertia_rate_B_G_kg_m2_s',
        ))
        if self.model_scope not in MODEL_SCOPES:
            raise ValueError('Unknown model_scope')
        if self.dynamics_mode not in DYNAMICS_MODES:
            raise ValueError('Unknown dynamics_mode')
        _text(self.provenance, 'provenance')
        if isinstance(self.limitations, str):
            raise TypeError('limitations must be a sequence of nonempty strings')
        limitations = tuple(_text(x, 'limitation') for x in self.limitations)
        if not limitations:
            raise ValueError('Explicit model limitations are required')
        object.__setattr__(self, 'limitations', limitations)
        if self.dynamics_mode == 'rigid_body_fixture':
            if self.model_scope != 'analytical_fixture':
                raise ValueError('A rigid_body_fixture cannot represent a vehicle baseline')
            for name in (
                'cg_rate_B0_m_s', 'inertia_rate_B_G_kg_m2_s',
                'relative_momentum_B_kg_m2_s', 'relative_momentum_rate_B_N_m',
            ):
                if np.any(np.asarray(getattr(self, name)) != 0.0):
                    raise ValueError(f'rigid_body_fixture requires explicit zero {name}')
        if self.dynamics_mode == 'reduced_articulated':
            for name in ('relative_momentum_B_kg_m2_s', 'relative_momentum_rate_B_N_m'):
                if np.any(np.asarray(getattr(self, name)) != 0.0):
                    raise ValueError('Use prescribed_internal_momentum for retained h_rel terms')

    def moment_arm_m(self, application_point_B0_m):
        """Application point minus instantaneous CG, both relative to O_B0."""
        point = finite_array(application_point_B0_m, (3,), 'application_point_B0_m')
        return finite_array(point - np.asarray(self.cg_B0_m), (3,), 'moment arm')

    def angular_momentum_B_kg_m2_s(self, omega_B_rad_s):
        omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
        momentum = np.asarray(self.inertia_B_G_kg_m2) @ omega
        momentum += np.asarray(self.relative_momentum_B_kg_m2_s)
        return finite_array(momentum, (3,), 'total angular momentum')

    def angular_acceleration_B_rad_s2(self, *, omega_B_rad_s,
                                     external_moment_B_G_N_m):
        """Whole-vehicle angular-momentum balance about instantaneous G.

        I*omega_dot = M_ext - omega cross (I*omega+h_rel)
                      - I_dot*omega - h_rel_dot.

        M_ext includes external aerodynamic rotor torque and r_G cross F,
        each exactly once. Internal actuator torque is NOT an external load.
        The caller/provider owns consistency of prescribed internal motion.
        This helper does not solve coupled joint accelerations or joint loads.
        """
        omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
        moment = finite_array(external_moment_B_G_N_m, (3,), 'external_moment_B_G_N_m')
        inertia = np.asarray(self.inertia_B_G_kg_m2)
        inertia_rate = np.asarray(self.inertia_rate_B_G_kg_m2_s)
        momentum = self.angular_momentum_B_kg_m2_s(omega)
        rhs = (moment - np.cross(omega, momentum) - inertia_rate @ omega
               - np.asarray(self.relative_momentum_rate_B_N_m))
        return finite_array(np.linalg.solve(inertia, rhs), (3,), 'angular acceleration')


class MassPropertyProvider(Protocol):
    """Pure provider: repeated identical inputs must produce identical data.

    Return properties derived from a traceable complete installed-mass
    ledger, including articulated offsets and full inertia about G.
    No trajectory history, controller memory or random sampling belongs here.
    Numerical derivatives, if used, need independently assessed accuracy.
    """

    def snapshot(self, *, time_s: float,
                 kinematics: AssemblyKinematics) -> MassProperties:
        ...


@dataclass(frozen=True, slots=True)
class Hopper:
    """Constant-total-mass electric vehicle or explicitly labelled fixture.

    installed_mass_kg is the reconciled COMPLETE ledger total. A separately
    purchased spare battery is not installed mass. Battery energy depletion
    does not remove propellant; a variable-total-mass model is out of scope.
    Vehicle values must come from current Chief/CAD/propulsion artifacts.
    """

    installed_mass_kg: float
    mass_property_provider: MassPropertyProvider
    model_scope: str
    ledger_reference: str

    def __post_init__(self):
        object.__setattr__(self, 'installed_mass_kg', _positive_scalar(
            self.installed_mass_kg, 'installed_mass_kg',
        ))
        if self.model_scope not in MODEL_SCOPES:
            raise ValueError('Unknown model_scope')
        _text(self.ledger_reference, 'ledger_reference')
        if not callable(getattr(self.mass_property_provider, 'snapshot', None)):
            raise TypeError('mass_property_provider must expose snapshot')

    def mass_properties(self, *, time_s, kinematics):
        time = float(time_s)
        if not np.isfinite(time):
            raise ValueError('time_s must be finite')
        if not isinstance(kinematics, AssemblyKinematics):
            raise TypeError('Explicit AssemblyKinematics required')
        result = self.mass_property_provider.snapshot(time_s=time, kinematics=kinematics)
        if not isinstance(result, MassProperties):
            raise TypeError('Mass-property provider must return MassProperties')
        if result.model_scope != self.model_scope:
            raise ValueError('Fixture and provisional-vehicle scopes must not be mixed')
        if abs(result.mass_kg - self.installed_mass_kg) > 1e-12 * self.installed_mass_kg:
            raise ValueError('Snapshot mass differs from constant complete installed mass')
        return result
