"""Explicit frame helpers for the sandbox PDR-R9 repaired hopper.

Original audited module: 6dof_hopper/helpers/math.py
Original SHA-256: 5e6420ade1c4d642762ba4d6b0812a80f2f693a58151bbf16a4274efb521239a
Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 revision 1, RC06-RC09.
Frame decision: f046cc4fe5294a6f9a61027529056f61 revision 1.
Gimbal decision: 84ef41fdd3fd4266ada43df2ace64a48 revision 1.

Conventions:
  L = local North-East-Down; B = structure-fixed Forward-Right-Down.
  q_LB = scalar-first Hamilton quaternion [w,x,y,z].
  R_LB maps body components to local components.
  qdot_LB = 0.5 * q_LB Hamilton-product [0, omega_B].
  Euler angles are radians; R_LB = Rz(yaw) Ry(pitch) Rx(roll).
  CAD C = forward, left, up; R_BC = diag(1,-1,-1), det=+1.

Intentional API migration:
  euler_to_quaternion now requires named radian arguments. The audited
  Simulation.solve_ode caller must be migrated; legacy degree/vector calls
  are NOT silently accepted.
  quaternion_to_dcm returns R_LB. The deprecated misspelled legacy helper
  retains its original algebraic R_BL default, with transpose=True giving
  R_LB. New plant callers must use the correctly spelled explicit contract.

No vehicle dimensions, actuator limits, controller gains or calibration
values are selected here. This file's existence establishes no test pass.
"""
from __future__ import annotations

import warnings

import numpy as np


def finite_array(value, shape, name):
    """Return an owned finite float array with exactly the required shape."""
    result = np.array(value, dtype=float, copy=True)
    if result.shape != shape:
        raise ValueError(f'{name} must have shape {shape}; got {result.shape}')
    if not np.all(np.isfinite(result)):
        raise ValueError(f'{name} must contain only finite values')
    return result


def normalize_quaternion(q_LB):
    """Return unit wxyz quaternion; reject zero/nonfinite input.

    Scale first to avoid overflow/underflow in the norm. No sign selection
    is imposed: q and -q represent the same rotation. State serialization
    must not call this implicitly, because that would hide norm drift.
    """
    q = finite_array(q_LB, (4,), 'q_LB')
    scale = float(np.max(np.abs(q)))
    if scale == 0.0:
        raise ValueError('q_LB cannot be the zero quaternion')
    scaled = q / scale
    return scaled / np.linalg.norm(scaled)


def hamilton_product(left, right):
    """Hamilton product of two wxyz arrays; do not normalize either input.

    Pure angular-velocity quaternions are not unit orientations.
    """
    a = finite_array(left, (4,), 'left quaternion')
    b = finite_array(right, (4,), 'right quaternion')
    with np.errstate(over='raise', invalid='raise'):
        scalar = a[0] * b[0] - np.dot(a[1:], b[1:])
        vector = a[0] * b[1:] + b[0] * a[1:] + np.cross(a[1:], b[1:])
    return finite_array(np.concatenate(([scalar], vector)), (4,), 'product')


def quaternion_derivative(q_LB, omega_B_rad_s):
    """Orientation derivative in 1/s using the raw integration quaternion.

    No normalization, feedback correction, logging or mutable state occurs
    here. The caller must measure integration norm error rather than hide it.
    """
    q = finite_array(q_LB, (4,), 'q_LB')
    if not np.any(q):
        raise ValueError('q_LB cannot be the zero quaternion')
    omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
    return 0.5 * hamilton_product(q, np.concatenate(([0.0], omega)))


def euler_to_quaternion(*, roll_rad, pitch_rad, yaw_rad):
    """Return unit q_LB for Rz(yaw) Ry(pitch) Rx(roll), all in radians."""
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
    """Return R_LB: v_L = R_LB @ v_B, from a nonzero wxyz quaternion.

    Normalization is local to this rotation calculation and does not alter
    the caller's state or its separately measurable quaternion norm.
    """
    w, x, y, z = normalize_quaternion(q_LB)
    return np.array([
        [1.0 - 2.0 * (y*y + z*z), 2.0 * (x*y - w*z), 2.0 * (x*z + w*y)],
        [2.0 * (x*y + w*z), 1.0 - 2.0 * (x*x + z*z), 2.0 * (y*z - w*x)],
        [2.0 * (x*z - w*y), 2.0 * (y*z + w*x), 1.0 - 2.0 * (x*x + y*y)],
    ], dtype=float)


def quarternion_to_dcm(quarternion, transpose=False):
    """Deprecated spelling: R_BL by default, R_LB if transpose=True.

    This preserves the original matrix direction, not the original typo
    failure. New code should use quaternion_to_dcm(q) or its explicit .T.
    """
    if not isinstance(transpose, (bool, np.bool_)):
        raise TypeError('transpose must be a boolean')
    warnings.warn(
        'Use quaternion_to_dcm(q_LB) for R_LB; its .T is R_BL.',
        DeprecationWarning,
        stacklevel=2,
    )
    R_LB = quaternion_to_dcm(quarternion)
    return R_LB if transpose else R_LB.T


def gimbal_to_body(*, alpha_rad, beta_rad):
    """Return R_BM=Rx(alpha)Ry(beta), not two space-fixed rotations.

    Alpha is about the outer body-fixed x axis; beta is about the inner
    carried y axis. Neutral module axes coincide with B. Limits are the
    actuator model's responsibility, not silently supplied here.
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
    """Return a fresh proper R_BC matrix; no translation or scaling."""
    return np.diag([1.0, -1.0, -1.0])


def cad_point_to_body_datum_m(point_C_mm, neutral_cg_C_mm):
    """CAD mm point -> body m relative to fixed neutral-CG datum O_B0.

    The neutral complete-vehicle CG must be supplied, never assumed zero.
    """
    point = finite_array(point_C_mm, (3,), 'point_C_mm')
    origin = finite_array(neutral_cg_C_mm, (3,), 'neutral_cg_C_mm')
    return finite_array(
        cad_to_body_rotation() @ (0.001 * (point - origin)),
        (3,), 'body datum point',
    )


def body_datum_point_to_cad_mm(point_B0_m, neutral_cg_C_mm):
    """Inverse of cad_point_to_body_datum_m; output is in CAD mm."""
    point = finite_array(point_B0_m, (3,), 'point_B0_m')
    origin = finite_array(neutral_cg_C_mm, (3,), 'neutral_cg_C_mm')
    return finite_array(
        origin + 1000.0 * (cad_to_body_rotation().T @ point),
        (3,), 'CAD point',
    )


def cad_inertia_to_body_kg_m2(inertia_C, *, input_unit, density_kg_m3=None):
    """Rotate full inertia about the SAME reference point and convert to SI.

    input_unit must be 'kg m^2', 'kg mm^2' or geometric 'mm^5'. For mm^5,
    the supplied uniform density must be finite and positive. Nonuniform
    assemblies require separately density-weighted component aggregation.
    This function does not perform a parallel-axis shift or validate mass
    ownership; the mass-property interface must establish those separately.
    """
    inertia = finite_array(inertia_C, (3, 3), 'inertia_C')
    magnitude = float(np.max(np.abs(inertia)))
    if magnitude == 0.0:
        raise ValueError('inertia_C cannot be identically zero')
    if np.max(np.abs(inertia - inertia.T)) > 1e-12 * magnitude:
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
        raise ValueError('unsupported inertia unit; explicit units are required')
    R_BC = cad_to_body_rotation()
    result = finite_array(R_BC @ (factor * inertia) @ R_BC.T, (3, 3), 'inertia_B')
    if np.min(np.linalg.eigvalsh(result)) <= 0.0:
        raise ValueError('complete-body inertia must be positive definite')
    return result


def fixed_datum_kinematics(*, position_G_L_m, velocity_G_L_m_s, q_LB,
                          omega_B_rad_s, offset_B0G_B_m,
                          offset_rate_B0G_B_m_s):
    """Convert instantaneous-CG translation to fixed structural datum O_B0.

    offset_rate is the component derivative in B caused by configuration
    change; it does NOT already contain omega cross offset. All quantities
    refer to the same instant. No articulated dynamics are inferred.
    """
    p_G = finite_array(position_G_L_m, (3,), 'position_G_L_m')
    v_G = finite_array(velocity_G_L_m_s, (3,), 'velocity_G_L_m_s')
    omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
    offset = finite_array(offset_B0G_B_m, (3,), 'offset_B0G_B_m')
    offset_rate = finite_array(offset_rate_B0G_B_m_s, (3,), 'offset_rate_B0G_B_m_s')
    R_LB = quaternion_to_dcm(q_LB)
    p_O = p_G - R_LB @ offset
    v_O = v_G - R_LB @ (np.cross(omega, offset) + offset_rate)
    return (finite_array(p_O, (3,), 'position_O_L_m'),
            finite_array(v_O, (3,), 'velocity_O_L_m_s'))
