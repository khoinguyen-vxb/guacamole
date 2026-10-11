"""Complete-vehicle mass and momentum interfaces for the PDR-R12 repair.

Authorization: 66c7448f443f44ac9a016a1b384593a2 r1.
Pre-edit evidence: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 r1 and
PDR-R12-PLANT-CALLER-RECONCILIATION-02 r1.
Frame contract: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal contract: 28e10be57d6548a3aa5be06c96f6d0d0 r1.

Reconciled from inspected historical chassis/hopper.py, SHA-256
2c2b09a5993ccedea61cf543fe2f342f079a646d877bf65cba19dc302ae39432.
Original audited chassis/hopper.py, SHA-256
6e2b2f93e98b844ce04f68d26b704c65270e9329e1abff76caa45cbcd5dcf0bd.
Supplied and historical sources remain unchanged.

Migration affecting Simulation.trajectory_ode/evaluate and fixture builders:
  Replace separate mass(time), CG(time), inertia(time) calls with one
  mass_properties(time_s=..., kinematics=...) snapshot.
  Complete installed mass includes propulsion, battery and every installed
  item exactly once. Do not add a separate propulsion.get_mass term.
  Propulsion loads are external point forces/free couples, not members of
  this mass ledger. Legacy time-only wrench forwarding is not retained.
  Full inertia is about instantaneous complete-vehicle CG G in FRD axes B.
  CG coordinates are relative to fixed neutral-CG airframe datum O_B0.

This module supplies no numerical vehicle inputs or articulated mass model.
Neither writing it nor satisfying its validation establishes physical validity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..helpers.math import finite_array


MASS_PROPERTY_SCHEMA = 'pdr_r12_complete_vehicle_instantaneous_cg_v1'
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
    """Own a finite symmetric matrix; optionally require physical inertia.

    Symmetry and triangle allowances are numerical roundoff allowances,
    not engineering uncertainty or permission to omit products of inertia.
    No silent diagonalization or symmetrization is performed.
    """
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
        if eigenvalues[-1] > eigenvalues[0] + eigenvalues[1] + 1e-12:
            raise ValueError(f'{name} violates principal-moment triangle inequality')
    return tuple(tuple(float(x) for x in row) for row in matrix)


@dataclass(frozen=True, slots=True)
class AssemblyKinematics:
    """One actual internal-motion sample supplied by the actuator model.

    Gimbal order is [alpha, beta], R_BM=Rx(alpha)Ry(beta). Alpha is about
    body-fixed outer +x and beta about carried inner +y. Generalized rates
    and accelerations are NOT components of one angular-velocity vector.
    Separate joint-origin translations belong in the geometry and mass
    providers; these angle fields do not imply intersecting joint axes.

    Stable rotor order is [upper, lower], identifying physical components
    in neutral configuration. Speeds and accelerations are SIGNED about
    common +z_M and relative to the module, not inertial rotor rates.
    Physical spin assignments require viewing-direction evidence. The
    propulsion interface checks configured counter-rotation signs.

    All fields are required explicitly, including zeros for a fixture.
    This record does not solve coupled joint dynamics or bearing loads.
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
    """Immutable complete-vehicle snapshot about instantaneous CG G.

    All vector/tensor components use structure-fixed FRD axes B. cg_B0_m
    locates G relative to fixed O_B0, the neutral complete-vehicle CG datum.
    cg_rate_B0_m_s is the derivative of those B components due to internal
    motion, excluding omega_B cross cg_B0_m. It is required for fixed-datum
    and hub velocity conversions; it is not the local translational state.

    inertia_B_G_kg_m2 is full locked-configuration inertia about G,
    including rotor and other moving masses exactly once. Its derivative
    is the derivative of B components due to internal configuration motion,
    not an additional body-to-local rotational derivative.

    H_B = I_B,G*omega_B + h_rel. relative_momentum_B_kg_m2_s is h_rel:
    relative rotor spin, joint motion and moving-mass contributions required
    by the chosen model, all about the same instantaneous G.
    relative_momentum_rate_B_N_m is its B-component derivative, EXCLUDING
    omega_B cross h_rel. Its consistency with prescribed accelerations is
    the mass-provider's responsibility; this record cannot establish it.

    Modes:
      rigid_body_fixture: explicitly synthetic rigid-body model. CG/inertia
        derivatives and relative momentum terms must be supplied as zero.
        Prescribed actuator motion does not make this complete articulated
        dynamics; its neglected moving-group effects must remain labelled.
      prescribed_internal_momentum: provider supplies consistent I_dot,
        h_rel and h_rel_dot for prescribed internal motion. This is not a
        claim of dynamically coupled or physically verified joint motion.
      reduced_articulated: h_rel and h_rel_dot are explicitly neglected.
        Configuration-dependent inertia and I_dot may be supplied, but
        these alone are not complete articulated dynamics. Neglected rotor
        gyroscopic and moving-mass effects need an applicability assessment.

    No term defaults silently to zero. Explicit provenance and limitations
    are mandatory. Internal motor/servo torques are NOT external moments.
    Vehicle ledger ownership must be reconciled separately by the Chief.
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
        """Application point minus instantaneous G, both relative to O_B0.

        Do not substitute a historical scalar lever arm or shift an already
        CG-referenced wrench a second time. Geometry supplies actual points.
        """
        point = finite_array(application_point_B0_m, (3,), 'application_point_B0_m')
        with np.errstate(over='raise', invalid='raise'):
            arm = point - np.asarray(self.cg_B0_m)
        return finite_array(arm, (3,), 'moment arm')

    def angular_momentum_B_kg_m2_s(self, omega_B_rad_s):
        """Total angular momentum about G, expressed in B."""
        omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
        with np.errstate(over='raise', invalid='raise'):
            momentum = np.asarray(self.inertia_B_G_kg_m2) @ omega
            momentum += np.asarray(self.relative_momentum_B_kg_m2_s)
        return finite_array(momentum, (3,), 'total angular momentum')

    def angular_acceleration_B_rad_s2(self, *, omega_B_rad_s,
                                     external_moment_B_G_N_m):
        """Whole-vehicle angular-momentum balance about instantaneous G.

        I*omega_dot = M_ext - omega cross (I*omega+h_rel)
                      - I_dot*omega - h_rel_dot.

        M_ext includes external aerodynamic rotor couples and r_G cross F,
        each exactly once. Uniform gravity has no net moment about complete
        vehicle G. Internal actuator reaction torques must not be added as
        independent external couples; their effects require consistent
        internal momentum terms or a documented reduced approximation.

        This solves body acceleration for the supplied snapshot, not the
        coupled joint accelerations, loads or servo feasibility. Independent
        analytical checks remain required, including off-diagonal inertia.
        """
        omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
        moment = finite_array(external_moment_B_G_N_m, (3,), 'external_moment_B_G_N_m')
        inertia = np.asarray(self.inertia_B_G_kg_m2)
        inertia_rate = np.asarray(self.inertia_rate_B_G_kg_m2_s)
        momentum = self.angular_momentum_B_kg_m2_s(omega)
        with np.errstate(over='raise', invalid='raise'):
            rhs = (moment - np.cross(omega, momentum) - inertia_rate @ omega
                   - np.asarray(self.relative_momentum_rate_B_N_m))
        rhs = finite_array(rhs, (3,), 'angular momentum balance RHS')
        return finite_array(np.linalg.solve(inertia, rhs), (3,), 'angular acceleration')


class MassPropertyProvider(Protocol):
    """Pure provider of one complete-vehicle mass/momentum snapshot.

    Repeated identical inputs must yield identical data, independent of RHS
    evaluation order. Providers must use the same actual joint/rotor motion
    and separated-origin geometry as the propulsion interface. Numerical
    derivatives require their own convergence and consistency checks.

    No controller integrals, previous-time accumulators, mutable trajectory
    history or random sampling belong here. For vehicle use, derive inputs
    from a traceable complete installed-mass ledger and explicit moving-group
    ownership. This protocol neither supplies those data nor validates them.
    """

    def snapshot(self, *, time_s: float,
                 kinematics: AssemblyKinematics) -> MassProperties:
        ...


@dataclass(frozen=True, slots=True)
class Hopper:
    """Constant-total-mass electric assembly or labelled analytical fixture.

    installed_mass_kg is the reconciled COMPLETE installed total, including
    the flight battery and propulsion once. A purchased spare battery is not
    installed mass. Energy depletion does not remove propellant here;
    variable-total-mass dynamics are outside this preliminary interface.

    ledger_reference must identify the actual ledger or explicitly synthetic
    fixture provenance. The numeric equality check prevents inconsistent
    snapshot totals, but cannot detect double-counting within a supplied
    ledger or establish hardware completeness.
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
        """Evaluate once and return one consistent immutable snapshot.

        Simulation must use this same snapshot for translational mass,
        CG-relative applied loads, angular balance and datum conversions.
        """
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
