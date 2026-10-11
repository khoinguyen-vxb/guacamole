"""Explicit rigid-body state for the sandbox PDR-R9 repaired hopper.

Original audited module: 6dof_hopper/simulation/state.py
Original SHA-256: 7b8713aecd017a7ff1f0b3ad4e14e1c63c716d1181a6df516d25b7a7d1973b2a
Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1, RC02/RC04/RC05/RC08/RC09.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.

Intentional API migration:
  State construction is keyword-only with explicit units and frames.
  The original thirteen positional arguments are NOT accepted: original
  u/v/w were body-resolved, whereas this schema uses local NED velocity.
  Simulation.solve_ode and trajectory_ode must migrate together.
  update_state and mutable history arrays are removed. Construct a new State
  from an accepted sample instead; adaptive RHS evaluations must not log
  trajectory history or mutate controller state.

Serialization preserves all thirteen components, including quaternion norm
error. Quaternion normalization is available only as an explicit operation.
Actuator states are separate from this thirteen-component rigid-body state.
No vehicle parameters, controller settings or test passes are supplied here.
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


STATE_VECTOR_SCHEMA = 'pdr_r9_cg_ned_frd_wxyz_v1'
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
    """Immutable snapshot; numeric accessors return independent arrays.

    Position and velocity refer to the instantaneous COMPLETE-vehicle CG G,
    expressed in the launch-ground NED frame L. Body angular velocity is
    expressed in structure-fixed FRD axes B. q_LB is scalar-first Hamilton
    and maps body vectors to local vectors.

    Internally store immutable bytes, not caller-owned mutable arrays.
    A nonzero, nonunit quaternion is retained to permit measurement of ODE
    norm drift. The integration entry point must separately enforce its
    initial-quaternion policy; serialization must never hide that drift.
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
        """Decode an explicitly identified thirteen-component SI vector.

        Require the schema even for arrays of the expected length: shape
        alone cannot distinguish legacy body velocity from local velocity.
        This operation neither normalizes orientation nor records history.
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
        """Construct with named radian Euler angles and all initial states.

        R_LB = Rz(yaw) Ry(pitch) Rx(roll). This is an initialization
        convenience, not an Euler-angle integration representation.
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
        """Explicit body-to-local velocity conversion at the SAME CG.

        This is not a general legacy-file importer. The caller must first
        establish that its position and velocity refer to instantaneous G.
        A fixed structural datum requires additional CG-offset kinematics;
        a rotation alone cannot change the reference point of velocity.
        """
        velocity_B = finite_array(velocity_G_B_m_s, (3,), 'velocity_G_B_m_s')
        return cls(
            position_G_L_m=position_G_L_m,
            velocity_G_L_m_s=quaternion_to_dcm(q_LB) @ velocity_B,
            q_LB=q_LB,
            omega_B_rad_s=omega_B_rad_s,
        )

    def as_vector(self):
        """Return an owned float64 array in STATE_COMPONENTS order."""
        return np.frombuffer(self._data, dtype=np.float64).copy()

    def unpack_state(self):
        """Return the NEW schema as thirteen scalars, without side effects.

        Retaining this method name does not imply legacy frame compatibility.
        Pair any persisted vector with STATE_VECTOR_SCHEMA and STATE_UNITS.
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
        """Resolve the same CG velocity in B; do not change its origin."""
        return quaternion_to_dcm(self.q_LB).T @ self.velocity_G_L_m_s

    def with_normalized_orientation(self):
        """Return an explicitly normalized copy; leave this snapshot intact.

        Do not apply this to reported solver samples before measuring their
        raw norm error. No automatic normalization occurs in serialization.
        """
        return type(self)(
            position_G_L_m=self.position_G_L_m,
            velocity_G_L_m_s=self.velocity_G_L_m_s,
            q_LB=normalize_quaternion(self.q_LB),
            omega_B_rad_s=self.omega_B_rad_s,
        )
