"""Explicit NED/FRD frame helpers for the preliminary PDR-R12 repair.

Authorization: 66c7448f443f44ac9a016a1b384593a2 r1.
Pre-edit evidence: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 r1 and
PDR-R12-PLANT-CALLER-RECONCILIATION-02 r1.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal convention: 28e10be57d6548a3aa5be06c96f6d0d0 r1.

Reconciled from the inspected historical r9 helpers/math.py, SHA-256
7941782e298900bdbbe35383aaa376a9679e225b6e85247c191b3a53486755a6.
Original audited helpers/math.py, SHA-256
5e6420ade1c4d642762ba4d6b0812a80f2f693a58151bbf16a4274efb521239a.
Neither source is modified. Writing this module is not a verification pass.

L: fixed launch-ground North-East-Down frame.
B: structure-fixed Forward-Right-Down axes.
q_LB: scalar-first Hamilton [w,x,y,z]; R_LB maps B components into L.
qdot = 0.5 * q_LB Hamilton-product [0, omega_B].
Euler inputs: named radians; R_LB = Rz(yaw) Ry(pitch) Rx(roll).
CAD C: forward-left-up; R_BC = diag(1,-1,-1), determinant +1.

Migration obligations: State and Simulation callers must use the named
radian interface and explicit DCM direction. Numeric serialization must
preserve raw quaternion norm error. The deprecated misspelled helper keeps
the original algebraic R_BL default, not its uninitialized-variable defect.

No vehicle geometry, mass, inertia, travel, gains or calibration is selected.
"""
from __future__ import annotations

import warnings

import numpy as np


def finite_array(value, shape, name):
    """Return an owned finite floating-point array of exactly shape."""
    result = np.array(value, dtype=float, copy=True)
    if result.shape != shape:
        raise ValueError(f'{name} must have shape {shape}; got {result.shape}')
    if not np.all(np.isfinite(result)):
        raise ValueError(f'{name} must contain only finite values')
    return result


def normalize_quaternion(q_LB):
    """Return a unit wxyz copy, rejecting zero/nonfinite inputs.

    Scaling before norm evaluation avoids squaring very large or very small
    raw components. Do not call this implicitly during state serialization.
    q and -q are both retained as valid orientation representations.
    """
    q = finite_array(q_LB, (4,), 'q_LB')
    scale = float(np.max(np.abs(q)))
    if scale == 0.0:
        raise ValueError('q_LB cannot be the zero quaternion')
    scaled = q / scale
    return scaled / np.linalg.norm(scaled)


def hamilton_product(left, right):
    """Hamilton product of wxyz arrays; neither operand is normalized.

    In particular [0, omega_B] is not a unit orientation quaternion.
    """
    a = finite_array(left, (4,), 'left quaternion')
    b = finite_array(right, (4,), 'right quaternion')
    with np.errstate(over='raise', invalid='raise'):
        scalar = a[0] * b[0] - np.dot(a[1:], b[1:])
        vector = a[0] * b[1:] + b[0] * a[1:] + np.cross(a[1:], b[1:])
    return finite_array(np.concatenate(([scalar], vector)), (4,), 'product')


def quaternion_derivative(q_LB, omega_B_rad_s):
    """Raw integration-quaternion derivative in 1/s; no state mutation.

    No normalization or norm-feedback correction is applied. The solver's
    raw norm drift must be measured separately at accepted output samples.
    """
    q = finite_array(q_LB, (4,), 'q_LB')
    if not np.any(q):
        raise ValueError('q_LB cannot be the zero quaternion')
    omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
    return 0.5 * hamilton_product(q, np.concatenate(([0.0], omega)))


def euler_to_quaternion(*, roll_rad, pitch_rad, yaw_rad):
    """Unit q_LB for Rz(yaw) Ry(pitch) Rx(roll); named radians only."""
    angles = finite_array([roll_rad, pitch_rad, yaw_rad], (3,), 'Euler radians')
    cr, cp, cy = np.cos(angles / 2.0)
    sr, sp, sy = np.sin(angles / 2.0)
    return normalize_quaternion([
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ])


def quaternion_to_dcm(q_LB):
    """Return R_LB, satisfying v_L = R_LB @ v_B.

    Normalize a local copy for rotation evaluation only. The caller's raw
    state and its measurable quaternion norm error remain unchanged.
    """
    w, x, y, z = normalize_quaternion(q_LB)
    return np.array([
        [1.0 - 2.0 * (y*y + z*z), 2.0 * (x*y - w*z), 2.0 * (x*z + w*y)],
        [2.0 * (x*y + w*z), 1.0 - 2.0 * (x*x + z*z), 2.0 * (y*z - w*x)],
        [2.0 * (x*z - w*y), 2.0 * (y*z + w*x), 1.0 - 2.0 * (x*x + y*y)],
    ], dtype=float)


def quarternion_to_dcm(quarternion, transpose=False):
    """Deprecated spelling: R_BL by default, R_LB with transpose=True.

    Preserves the inspected original matrix direction. New plant callers
    must use quaternion_to_dcm(q_LB), or its explicit transpose.
    """
    if not isinstance(transpose, (bool, np.bool_)):
        raise TypeError('transpose must be a boolean')
    warnings.warn(
        'Use quaternion_to_dcm(q_LB) for R_LB; its .T is R_BL.',
        DeprecationWarning,
        stacklevel=2,
    )
    rotation = quaternion_to_dcm(quarternion)
    return rotation if transpose else rotation.T


def gimbal_to_body(*, alpha_rad, beta_rad):
    """Return R_BM = Rx(alpha) Ry(beta).

    Alpha rotates about outer body-fixed +x; beta rotates about the carried
    inner +y. Module axes coincide with B at neutral. This function supplies
    rotation only: separated joint origins require explicit translations in
    the geometry provider, not an assumed coincident pivot. Joint/cone
    limits belong to the actuator interface, not this rotation helper.
    """
    angles = finite_array([alpha_rad, beta_rad], (2,), 'gimbal radians')
    ca, cb = np.cos(angles)
    sa, sb = np.sin(angles)
    return np.array([
        [cb, 0.0, sb],
        [sa * sb, ca, -sa * cb],
        [-ca * sb, sa, ca * cb],
    ], dtype=float)


def cad_to_body_rotation():
    """Fresh proper R_BC; no translation, length scaling or articulation."""
    return np.diag([1.0, -1.0, -1.0])


def cad_point_to_body_datum_m(point_C_mm, neutral_cg_C_mm):
    """CAD point in mm -> B coordinates in m relative to fixed O_B0.

    O_B0 coincides with the complete-vehicle neutral CG once derived from
    the actual assembly. That numerical CAD origin is required explicitly;
    it is never assumed zero or moved with the instantaneous CG.
    """
    point = finite_array(point_C_mm, (3,), 'point_C_mm')
    origin = finite_array(neutral_cg_C_mm, (3,), 'neutral_cg_C_mm')
    with np.errstate(over='raise', invalid='raise'):
        result = cad_to_body_rotation() @ (0.001 * (point - origin))
    return finite_array(result, (3,), 'body datum point')


def body_datum_point_to_cad_mm(point_B0_m, neutral_cg_C_mm):
    """Inverse point conversion, returning CAD mm using the same datum."""
    point = finite_array(point_B0_m, (3,), 'point_B0_m')
    origin = finite_array(neutral_cg_C_mm, (3,), 'neutral_cg_C_mm')
    with np.errstate(over='raise', invalid='raise'):
        result = origin + 1000.0 * (cad_to_body_rotation().T @ point)
    return finite_array(result, (3,), 'CAD point')


def cad_inertia_to_body_kg_m2(inertia_C, *, input_unit, density_kg_m3=None):
    """Convert and rotate full inertia about the SAME reference point.

    Supported units: 'kg m^2', 'kg mm^2', or geometric 'mm^5'. Geometric
    inertia requires an explicit positive uniform density in kg/m^3.
    Nonuniform assemblies need component-wise density weighting and
    aggregation first. Already mass-weighted input must not receive density
    a second time. No parallel-axis shift or mass-ownership audit occurs.

    This helper checks symmetry and positive definiteness. Complete-body
    physical-inertia consistency, including principal-moment triangle
    inequalities, belongs to the mass-property validation interface.
    """
    inertia = finite_array(inertia_C, (3, 3), 'inertia_C')
    magnitude = float(np.max(np.abs(inertia)))
    if magnitude == 0.0:
        raise ValueError('inertia_C cannot be identically zero')
    scaled = inertia / magnitude
    if np.max(np.abs(scaled - scaled.T)) > 1e-12:
        raise ValueError('inertia_C must be symmetric; no silent symmetrization')
    if input_unit == 'mm^5':
        if density_kg_m3 is None:
            raise ValueError('geometric mm^5 requires explicit uniform density')
        density = float(density_kg_m3)
        if not np.isfinite(density) or density <= 0.0:
            raise ValueError('density_kg_m3 must be finite and positive')
        factor = density * 1e-15
    elif input_unit in ('kg m^2', 'kg mm^2'):
        if density_kg_m3 is not None:
            raise ValueError('mass-weighted inertia must not be density-weighted again')
        factor = 1.0 if input_unit == 'kg m^2' else 1e-6
    else:
        raise ValueError('Unsupported inertia unit; explicit units are required')
    rotation = cad_to_body_rotation()
    with np.errstate(over='raise', invalid='raise'):
        result = rotation @ (factor * inertia) @ rotation.T
    result = finite_array(result, (3, 3), 'inertia_B_kg_m2')
    result_scale = float(np.max(np.abs(result)))
    if result_scale == 0.0 or np.min(np.linalg.eigvalsh(result / result_scale)) <= 0.0:
        raise ValueError('Converted complete-body inertia must be positive definite')
    return result


def fixed_datum_kinematics(*, position_G_L_m, velocity_G_L_m_s, q_LB,
                          omega_B_rad_s, offset_B0G_B_m,
                          offset_rate_B0G_B_m_s):
    """Convert instantaneous complete-vehicle CG translation to fixed O_B0.

    All inputs refer to the same instant. offset_rate is the derivative of
    offset components in B caused by configuration motion; it excludes
    omega cross offset. Omitting it generally corrupts datum velocity.

      p_O = p_G - R_LB r_B0G
      v_O = v_G - R_LB (omega_B cross r_B0G + r_dot_B0G)

    These kinematics do not establish a valid articulated dynamics model.
    Later mission tracking uses this fixed datum, not configuration-varying G.
    """
    p_G = finite_array(position_G_L_m, (3,), 'position_G_L_m')
    v_G = finite_array(velocity_G_L_m_s, (3,), 'velocity_G_L_m_s')
    omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
    offset = finite_array(offset_B0G_B_m, (3,), 'offset_B0G_B_m')
    offset_rate = finite_array(offset_rate_B0G_B_m_s, (3,), 'offset_rate_B0G_B_m_s')
    rotation = quaternion_to_dcm(q_LB)
    with np.errstate(over='raise', invalid='raise'):
        p_O = p_G - rotation @ offset
        v_O = v_G - rotation @ (np.cross(omega, offset) + offset_rate)
    return (
        finite_array(p_O, (3,), 'position_O_L_m'),
        finite_array(v_O, (3,), 'velocity_O_L_m_s'),
    )
