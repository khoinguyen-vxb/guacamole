"""Quaternion helpers for the PDR r5 plant; angles are radians.

Convention: scalar-first Hamilton q_LB = [w, x, y, z], body to local.
Local axes are North-East-Down; structure body axes are forward-right-down.
An upright vehicle pointing north has q_LB = [1, 0, 0, 0].
R_LB maps body components to local components; C_BL = R_LB.T.
Euler construction uses R_LB = Rz(yaw) @ Ry(pitch) @ Rx(roll).

The legacy misspelled quarternion_to_dcm name remains available. Both it
and quaternion_to_dcm return C_BL by default, preserving the old intended
DCM direction. New callers should prefer the direction-named functions.
All functions are pure: no input mutation, logging or controller updates.
"""
import numpy as np


def _finite_vector(value, size, name):
    array = np.array(value, dtype=float, copy=True)
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ValueError(f'{name} must be a finite {size}-element vector')
    return array


def normalize_quaternion(quaternion):
    """Return a unit q_LB without modifying or sign-canonicalizing its input.

    Reject a zero or nonfinite quaternion. Scaling before calculating the
    norm avoids overflow/underflow when normalizing finite nonzero inputs.
    This conversion does not replace or normalize an integrated state.
    """
    q = _finite_vector(quaternion, 4, 'quaternion')
    scale = float(np.max(np.abs(q)))
    if scale == 0.0:
        raise ValueError('quaternion must be nonzero')
    scaled = q / scale
    return scaled / np.linalg.norm(scaled)


def quaternion_body_to_local(quaternion):
    """Return R_LB, so v_local = R_LB @ v_body, for scalar-first q_LB."""
    w, x, y, z = normalize_quaternion(quaternion)
    return np.array([
        [1.0 - 2.0 * (y*y + z*z), 2.0 * (x*y - w*z),
         2.0 * (x*z + w*y)],
        [2.0 * (x*y + w*z), 1.0 - 2.0 * (x*x + z*z),
         2.0 * (y*z - w*x)],
        [2.0 * (x*z - w*y), 2.0 * (y*z + w*x),
         1.0 - 2.0 * (x*x + y*y)],
    ], dtype=float)


def quaternion_local_to_body(quaternion):
    """Return C_BL, so v_body = C_BL @ v_local, for scalar-first q_LB."""
    return quaternion_body_to_local(quaternion).T


def quaternion_to_dcm(quaternion, transpose=False):
    """Compatibility interface: C_BL by default, R_LB if transpose=True."""
    matrix = quaternion_local_to_body(quaternion)
    return matrix.T if transpose else matrix


def quarternion_to_dcm(quarternion, transpose=False):
    """Legacy spelling and keyword retained; fixed undefined-variable defect.

    Returns local-to-body C_BL unless transpose=True. The input represents
    body-to-local attitude q_LB; quaternion and matrix directions differ.
    """
    return quaternion_to_dcm(quarternion, transpose=transpose)


def euler_to_quaternion(roll, pitch, yaw):
    """Construct scalar-first Hamilton q_LB from three explicit radians.

    Uses the yaw-pitch-roll (3-2-1) convention:
    R_LB = Rz(yaw) @ Ry(pitch) @ Rx(roll).
    This equals intrinsic Z-Y-X or extrinsic X-Y-Z rotation with the
    corresponding angle ordering. No implicit degree conversion occurs.
    Euler angles are interface quantities, not the integrated state;
    their chart is singular at pitch = +/- pi/2.
    """
    angles = _finite_vector((roll, pitch, yaw), 3, 'roll, pitch, yaw')
    cr, cp, cy = np.cos(0.5 * angles)
    sr, sp, sy = np.sin(0.5 * angles)
    return normalize_quaternion(np.array([
        cr*cp*cy + sr*sp*sy,
        sr*cp*cy - cr*sp*sy,
        cr*sp*cy + sr*cp*sy,
        cr*cp*sy - sr*sp*cy,
    ], dtype=float))


def quaternion_derivative(quaternion, angular_rates_body,
                          norm_feedback_gain_per_s=0.0):
    """Return qdot_LB = 0.5*q_LB Hamilton-product [0, omega_B].

    omega_B is structure angular velocity relative to the local frame,
    expressed in body axes, in rad/s. The optional numerical feedback is
    k*(1 - q dot q)*q, where k is nonnegative in 1/s. Setting k=0 disables
    feedback. The raw quaternion is retained in the kinematics: this
    function does not silently renormalize the ODE state.
    """
    q = _finite_vector(quaternion, 4, 'quaternion')
    if not np.any(q != 0.0):
        raise ValueError('quaternion must be nonzero')
    omega = _finite_vector(angular_rates_body, 3, 'angular_rates_body')
    gain_array = np.asarray(norm_feedback_gain_per_s, dtype=float)
    if gain_array.shape != ():
        raise ValueError('norm feedback gain must be a scalar')
    gain = float(gain_array)
    if not np.isfinite(gain) or gain < 0.0:
        raise ValueError('norm feedback gain must be finite and nonnegative')
    with np.errstate(over='raise', invalid='raise'):
        try:
            derivative = 0.5 * np.concatenate((
                np.array([-np.dot(q[1:], omega)]),
                q[0] * omega + np.cross(q[1:], omega),
            ))
            if gain != 0.0:
                derivative += gain * (1.0 - np.dot(q, q)) * q
        except FloatingPointError as error:
            raise ValueError('quaternion derivative exceeds numerical range') from error
    if not np.all(np.isfinite(derivative)):
        raise ValueError('quaternion derivative is nonfinite')
    return derivative
