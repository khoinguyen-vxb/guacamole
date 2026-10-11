"""Explicit instantaneous-CG state for the preliminary PDR r12 plant.

Original audited module: 6dof_hopper/simulation/state.py
Original SHA-256: 7b8713aecd017a7ff1f0b3ad4e14e1c63c716d1181a6df516d25b7a7d1973b2a
Recovered implementation: pdr_r9_plant/repaired_hopper/simulation/state.py
Recovered SHA-256: 3b5a37931c66e32c2f5bb4b68bd47b8da71417e31dfe11a4b06fddb1c4f62425
Audit: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 revision 1.
Caller reconciliation: PDR-R12-PLANT-CALLER-RECONCILIATION-02 revision 1.
Authorization: 66c7448f443f44ac9a016a1b384593a2 revision 1.
Frame contract: f046cc4fe5294a6f9a61027529056f61 revision 1.

Migration affecting Simulation construction, solve_ode, trajectory_ode and
fixture/runner callers:
  * Construction is keyword-only, with explicit units, frames and origin.
  * All thirteen supplied rigid-body components are retained.
  * Original body-resolved u/v/w are NOT interpreted as local NED velocity.
  * Numeric decoding requires the r12 schema, not merely matching length.
  * Mutable update_state/history accumulation is deliberately removed.
  * Euler initialization uses named radian arguments; integration uses q.
  * Serialization preserves quaternion norm error rather than hiding it.

Actuator states are separate; the combined plant must preserve them too.
Fixed-airframe-datum mission scoring requires CG-offset kinematics and is
not obtained by renaming position_G_L_m. No vehicle inputs, PID gains,
verification results or physical acceptance are supplied by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..helpers.math import (
    euler_to_quaternion,
    finite_array,
    normalize_quaternion,
    quaternion_to_dcm,
)


STATE_VECTOR_SCHEMA = 'pdr_r12_cg_ned_frd_wxyz_v1'
STATE_SIZE = 13
STATE_COMPONENTS = (
    'position_G_north_m', 'position_G_east_m', 'position_G_down_m',
    'velocity_G_north_m_s', 'velocity_G_east_m_s', 'velocity_G_down_m_s',
    'q_LB_w', 'q_LB_x', 'q_LB_y', 'q_LB_z',
    'omega_B_x_rad_s', 'omega_B_y_rad_s', 'omega_B_z_rad_s',
)
STATE_UNITS = ('m',) * 3 + ('m/s',) * 3 + ('1',) * 4 + ('rad/s',) * 3


@dataclass(frozen=True, slots=True, init=False)
class State:
    """Immutable snapshot with owned numerical serialization.

    Position and velocity refer to instantaneous COMPLETE-vehicle CG G,
    expressed in launch-ground NED axes L. Angular velocity is expressed
    in structure-fixed FRD axes B. Scalar-first Hamilton q_LB represents
    the body-to-local rotation R_LB.

    Immutable bytes prevent caller-owned arrays or returned views from
    changing this snapshot. Accessors return independent arrays.

    A finite nonzero quaternion is stored without normalization, including
    nonunit solver samples. The solver boundary must separately check the
    initial-quaternion tolerance. This permissive serialization policy is
    not permission to start integration from an arbitrary nonunit attitude.
    """

    _data: bytes = field(repr=False)

    def __init__(self, *, position_G_L_m, velocity_G_L_m_s,
                 q_LB, omega_B_rad_s):
        position = finite_array(position_G_L_m, (3,), 'position_G_L_m')
        velocity = finite_array(velocity_G_L_m_s, (3,), 'velocity_G_L_m_s')
        quaternion = finite_array(q_LB, (4,), 'q_LB')
        omega = finite_array(omega_B_rad_s, (3,), 'omega_B_rad_s')
        if not np.any(quaternion):
            raise ValueError('q_LB cannot be the zero quaternion')
        vector = np.concatenate((position, velocity, quaternion, omega))
        object.__setattr__(self, '_data', vector.astype(np.float64).tobytes())

    @classmethod
    def from_vector(cls, vector, *, schema):
        """Decode exactly thirteen SI components under the explicit schema.

        Shape alone cannot distinguish original body velocity from r12
        local velocity, or a fixed-datum state from a CG state. No implicit
        legacy conversion, quaternion projection or history update occurs.
        """
        if schema != STATE_VECTOR_SCHEMA:
            raise ValueError('Unsupported or ambiguous state-vector schema')
        values = finite_array(vector, (STATE_SIZE,), 'state vector')
        return cls(
            position_G_L_m=values[0:3],
            velocity_G_L_m_s=values[3:6],
            q_LB=values[6:10],
            omega_B_rad_s=values[10:13],
        )

    @classmethod
    def from_euler(cls, *, position_G_L_m, velocity_G_L_m_s,
                   roll_rad, pitch_rad, yaw_rad, omega_B_rad_s):
        """Initialize using R_LB=Rz(yaw)Ry(pitch)Rx(roll), in radians.

        Preserve all position, velocity and angular-rate inputs. Euler
        angles are an initialization interface, not integration states.
        """
        return cls(
            position_G_L_m=position_G_L_m,
            velocity_G_L_m_s=velocity_G_L_m_s,
            q_LB=euler_to_quaternion(
                roll_rad=roll_rad, pitch_rad=pitch_rad, yaw_rad=yaw_rad,
            ),
            omega_B_rad_s=omega_B_rad_s,
        )

    @classmethod
    def from_body_velocity(cls, *, position_G_L_m, velocity_G_B_m_s,
                           q_LB, omega_B_rad_s):
        """Explicitly rotate velocity components at the SAME instantaneous G.

        This is not an automatic original-state importer. The caller must
        establish the velocity's reference point. A fixed-datum velocity
        requires CG-offset and offset-rate terms as well as a rotation.
        """
        velocity_B = finite_array(velocity_G_B_m_s, (3,), 'velocity_G_B_m_s')
        return cls(
            position_G_L_m=position_G_L_m,
            velocity_G_L_m_s=quaternion_to_dcm(q_LB) @ velocity_B,
            q_LB=q_LB,
            omega_B_rad_s=omega_B_rad_s,
        )

    def as_vector(self):
        """Return an owned float64 array in STATE_COMPONENTS order.

        Stored quaternion components are returned exactly; normalization
        for rotation calculations must not erase measured integration drift.
        """
        return np.frombuffer(self._data, dtype=np.float64).copy()

    def unpack_state(self):
        """Return thirteen scalars in the NEW schema, without side effects.

        The retained method name does not imply original frame compatibility.
        Persist STATE_VECTOR_SCHEMA and STATE_UNITS alongside saved vectors.
        """
        return tuple(float(value) for value in self.as_vector())

    @property
    def position_G_L_m(self):
        return self.as_vector()[0:3]

    @property
    def velocity_G_L_m_s(self):
        return self.as_vector()[3:6]

    @property
    def q_LB(self):
        return self.as_vector()[6:10]

    @property
    def omega_B_rad_s(self):
        return self.as_vector()[10:13]

    def velocity_G_B_m_s(self):
        """Resolve the same CG velocity in B without changing its origin."""
        return quaternion_to_dcm(self.q_LB).T @ self.velocity_G_L_m_s

    def with_normalized_orientation(self):
        """Return an explicitly normalized copy, leaving this state intact.

        Use only under a documented initialization/projection policy. Do not
        normalize reported solver samples before measuring raw norm error.
        """
        return type(self)(
            position_G_L_m=self.position_G_L_m,
            velocity_G_L_m_s=self.velocity_G_L_m_s,
            q_LB=normalize_quaternion(self.q_LB),
            omega_B_rad_s=self.omega_B_rad_s,
        )
