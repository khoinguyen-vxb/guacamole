"""PDR M4 fixed-D analytical plant: simulation/state.py.

Current authority: system_model:system revision 4;
work-plan 99f7bb629eef45b89fa38d27c803868c revision 1;
interface 88561ff8b3ba4e8286cebd95a93e3b08 revision 1.
Pre-edit audit: PDR-PLANT-PRE-EDIT-AUDIT-M4-03 revision 1.

Reused from inspected previous_run/repaired_hopper_r12/simulation/state.py.
Recovered file SHA256: b62a1a4fcc70a4a88e07f77996e955a64184891ce614957c85ccb7d63e90f294
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

from dataclasses import dataclass, field

import numpy as np

from ..helpers.math import (
    euler_to_quaternion,
    finite_array,
    normalize_quaternion,
    quaternion_to_dcm,
)


STATE_VECTOR_SCHEMA = 'hopper_m4_fixed_D_cg_ned_frd_wxyz_v1'
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

        Shape alone cannot distinguish original body velocity from M4
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
