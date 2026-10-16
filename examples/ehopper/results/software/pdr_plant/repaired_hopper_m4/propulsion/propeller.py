"""PDR M4 fixed-D analytical plant: propulsion/propeller.py.

Current authority: system_model:system revision 4;
work-plan 99f7bb629eef45b89fa38d27c803868c revision 1;
interface 88561ff8b3ba4e8286cebd95a93e3b08 revision 1.
Pre-edit audit: PDR-PLANT-PRE-EDIT-AUDIT-M4-03 revision 1.

Reused from inspected previous_run/repaired_hopper_r12/propulsion/propeller.py.
Recovered file SHA256: ce7be67ceae3866ecf402ee03b7812c3ea1e39c216ca5d412322af53d586ae3b
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

import numpy as np

from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
from ..helpers.math import finite_array, gimbal_to_body, quaternion_to_dcm
from ..simulation.state import State
from .propulsion import (
    AppliedLoad,
    CoaxialConditions,
    CoaxialPerformance,
    CoaxialPerformanceMap,
    Propulsion,
    PropulsionEvaluation,
)


GEOMETRY_SCHEMA = 'hopper_m4_fixed_D_separated_origin_common_gimbal_v1'


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def _kinematics(value):
    if not isinstance(value, AssemblyKinematics):
        raise TypeError('Explicit actual AssemblyKinematics required')
    return value


@dataclass(frozen=True, slots=True)
class CoaxialGeometry:
    """Ideal rigid common-gimbal geometry with explicit joint translations.

    B is structure-fixed FRD. D is the FIXED airframe datum, not moving G.
    A is the outer carried frame: R_BA=Rx(alpha). M is the inner/module
    frame: R_BM=Rx(alpha)Ry(beta). All lengths are metres.

    outer_origin_D_m locates the body-fixed outer x-axis origin O_x,
    relative to D and expressed in B.
    outer_to_inner_outer_m is d_OxOy, the displacement from O_x to inner
    y-axis origin O_y, expressed in A and constant in that carried frame.
    hub_offsets_from_inner_M_m gives the ordered U/L hub positions measured
    from O_y and expressed in M.

      r_D,i = r_D,Ox + R_BA d_OxOy + R_BM r_Oy,i,M.

    Coincident origins require an explicit zero displacement; there is no
    coincident-axis default. Both hubs lie on one module-parallel z line;
    that line need not pass through either joint origin. Module +z points
    down at neutral. Lower hub z must exceed upper hub z.

    U identifies the rotor nearer the structure at neutral; L identifies
    the rotor nearer the ground. These identities persist through motion.
    spin_signs are opposite integers about the SAME module +z axis, not
    visual CW/CCW labels without a specified viewing direction.

    This ideal model excludes compliance, axis misalignment and linkage
    deformation. Hub force application points are reduced-model assumptions,
    not established aerodynamic centres for all inflows. Geometry validation
    does not verify bottom placement, clearances or hardware realizability.
    Those require the current complete assembly and Chief-selected inputs.
    """

    outer_origin_D_m: tuple[float, float, float]
    outer_to_inner_outer_m: tuple[float, float, float]
    hub_offsets_from_inner_M_m: tuple
    spin_signs: tuple[int, int]
    model_scope: str
    provenance: str

    def __post_init__(self):
        for name in ('outer_origin_D_m', 'outer_to_inner_outer_m'):
            values = finite_array(getattr(self, name), (3,), name)
            object.__setattr__(self, name, tuple(float(x) for x in values))
        hubs = finite_array(
            self.hub_offsets_from_inner_M_m, (2, 3),
            'hub_offsets_from_inner_M_m',
        )
        signs = tuple(self.spin_signs)
        if (len(signs) != 2 or any(type(x) is not int for x in signs)
                or set(signs) != {-1, 1}):
            raise ValueError('Supply opposite integer spin signs about common +z_M')
        with np.errstate(over='raise', invalid='raise'):
            separation = hubs[1] - hubs[0]
        if separation[2] <= 0.0:
            raise ValueError('U/L ordering requires positive axial spacing')
        # Roundoff allowance only, not an alignment or manufacturing margin.
        scale = float(np.max(np.abs(hubs)))
        if np.max(np.abs(separation[:2])) > 32.0 * np.finfo(float).eps * scale:
            raise ValueError('This ideal model requires coaxial hub offsets')
        if self.model_scope not in MODEL_SCOPES:
            raise ValueError('Unknown model_scope')
        _text(self.provenance, 'geometry provenance')
        object.__setattr__(self, 'hub_offsets_from_inner_M_m', tuple(
            tuple(float(x) for x in row) for row in hubs
        ))
        object.__setattr__(self, 'spin_signs', signs)

    @property
    def axial_spacing_m(self):
        """Positive U-to-L spacing along module +z; independent of tilt."""
        return (self.hub_offsets_from_inner_M_m[1][2]
                - self.hub_offsets_from_inner_M_m[0][2])

    def outer_rotation_BA(self, kinematics):
        """Outer carried frame into B: Rx(alpha), without inner rotation."""
        motion = _kinematics(kinematics)
        return gimbal_to_body(alpha_rad=motion.gimbal_rad[0], beta_rad=0.0)

    def rotation_BM(self, kinematics):
        """Module into B: outer x followed by carried inner y."""
        motion = _kinematics(kinematics)
        alpha, beta = motion.gimbal_rad
        return gimbal_to_body(alpha_rad=alpha, beta_rad=beta)

    def joint_origins_D_m(self, kinematics):
        """Return outer and inner origins, both expressed in B from D."""
        rotation_outer = self.outer_rotation_BA(kinematics)
        outer = np.asarray(self.outer_origin_D_m)
        with np.errstate(over='raise', invalid='raise'):
            inner = outer + rotation_outer @ np.asarray(self.outer_to_inner_outer_m)
        return finite_array(np.vstack((outer, inner)), (2, 3), 'joint origins')

    def application_points_D_m(self, kinematics):
        """Return actual U/L hub points from the separated-origin contract."""
        inner = self.joint_origins_D_m(kinematics)[1]
        rotation = self.rotation_BM(kinematics)
        with np.errstate(over='raise', invalid='raise'):
            points = inner + (
                rotation @ np.asarray(self.hub_offsets_from_inner_M_m).T
            ).T
        return finite_array(points, (2, 3), 'rotor application points')

    def application_point_rates_D_m_s(self, kinematics):
        """Body-component derivatives caused by internal joint motion.

        These are NOT inertial hub velocities and do not include airframe
        rotation, CG translation or wind. For d_B=Rx(alpha)d_OxOy and
        s_i,B=R_BM r_Oy,i,M:

          r_dot_D,i = alpha_dot e_x cross d_B
                       + omega_MB,B cross s_i,B,
          omega_MB,B = [alpha_dot, cos(alpha) beta_dot,
                        sin(alpha) beta_dot].

        Inner-axis motion does not rotate d_OxOy. Applying omega_MB,B cross
        to the entire outer-origin hub arm would therefore be incorrect
        for general separated origins.
        """
        motion = _kinematics(kinematics)
        alpha = motion.gimbal_rad[0]
        alpha_rate, beta_rate = motion.gimbal_rate_rad_s
        rotation_outer = self.outer_rotation_BA(motion)
        rotation = self.rotation_BM(motion)
        with np.errstate(over='raise', invalid='raise'):
            joint_offset_B = rotation_outer @ np.asarray(self.outer_to_inner_outer_m)
            module_offsets_B = (
                rotation @ np.asarray(self.hub_offsets_from_inner_M_m).T
            ).T
            outer_omega_B = np.array([alpha_rate, 0.0, 0.0])
            module_omega_B = np.array([
                alpha_rate, np.cos(alpha) * beta_rate,
                np.sin(alpha) * beta_rate,
            ])
            rates = (np.cross(outer_omega_B, joint_offset_B)
                     + np.cross(module_omega_B, module_offsets_B))
        return finite_array(rates, (2, 3), 'application-point component rates')

    def validate_spin_kinematics(self, kinematics):
        """Reject reverse spin and acceleration out of the zero-speed boundary.

        Deceleration of a spinning rotor is allowed. Speed/acceleration
        caps belong to the response model and performance-domain checks.
        Windmilling, rotor reversal and regeneration require an extension.
        """
        motion = _kinematics(kinematics)
        signs = np.asarray(self.spin_signs)
        speeds = signs * np.asarray(motion.rotor_signed_speed_rad_s)
        acceleration = signs * np.asarray(motion.rotor_signed_acceleration_rad_s2)
        if np.any(speeds < 0.0):
            raise ValueError('Actual rotor speed opposes configured spin direction')
        if np.any((speeds == 0.0) & (acceleration < 0.0)):
            raise ValueError('Rotor acceleration leaves the allowed zero-speed boundary')


@dataclass(frozen=True, slots=True)
class Propellor(Propulsion):
    """Concrete external-load adapter retaining the original class spelling.

    The paired map receives BOTH actual rotor states simultaneously. It
    owns coaxial interference, calibration and electrical assumptions.
    This adapter does not double isolated thrust or independently clip
    thrust, drag torque and current into a supposedly feasible response.

    Provider-reported domain flags remain tri-state observations. The plant
    must apply its explicit policy; neither True nor an unknown flag is
    independent evidence of calibrated vehicle feasibility.

    Installed rotor/motor mass belongs to the complete-vehicle ledger.
    External air-on-rotor torque occurs here exactly once. Motor and servo
    reactions are internal, not additional external whole-vehicle couples.
    Their effects require consistent relative momentum in MassProperties,
    or an explicitly documented reduced articulated approximation.
    """

    geometry: CoaxialGeometry
    performance_map: CoaxialPerformanceMap

    def __post_init__(self):
        if not isinstance(self.geometry, CoaxialGeometry):
            raise TypeError('Explicit separated-origin CoaxialGeometry required')
        if not callable(getattr(self.performance_map, 'evaluate', None)):
            raise TypeError('performance_map must implement evaluate')

    def hub_velocities_relative_air_M_m_s(
        self, *, state, mass_properties, kinematics, wind_at_hubs_L_m_s,
    ):
        """Actual hub velocity relative to ambient air, resolved in M.

        Supply wind at the two actual hub positions in local NED axes.
        It is ambient wind, not induced disk flow. The coupled performance
        map must separately declare its wake and interference treatment.

          v_i,B = R_BL(v_G,L - wind_i,L)
                  + omega_B cross (r_D,i-r_D,G)
                  + r_dot_D,i - r_dot_D,G.

        The final result is R_MB v_i,B. Internal point rates use the
        separated joint origins; CG component rates exclude the body-rate
        cross term. All inputs must refer to the same evaluation instant.
        """
        if not isinstance(state, State):
            raise TypeError('Explicit instantaneous-CG State required')
        if not isinstance(mass_properties, MassProperties):
            raise TypeError('Explicit MassProperties snapshot required')
        if mass_properties.model_scope != self.geometry.model_scope:
            raise ValueError('Fixture and vehicle scopes must not be mixed')
        self.geometry.validate_spin_kinematics(kinematics)
        wind = finite_array(wind_at_hubs_L_m_s, (2, 3), 'wind_at_hubs_L_m_s')
        rotation = self.geometry.rotation_BM(kinematics)
        R_BL = quaternion_to_dcm(state.q_LB).T
        points = self.geometry.application_points_D_m(kinematics)
        point_rates = self.geometry.application_point_rates_D_m_s(kinematics)
        velocities = []
        for index in range(2):
            arm = mass_properties.moment_arm_m(points[index])
            with np.errstate(over='raise', invalid='raise'):
                local_relative = state.velocity_G_L_m_s - wind[index]
                velocity_B = (
                    R_BL @ local_relative
                    + np.cross(state.omega_B_rad_s, arm)
                    + point_rates[index]
                    - np.asarray(mass_properties.cg_rate_D_m_s)
                )
                velocities.append(rotation.T @ velocity_B)
        return finite_array(velocities, (2, 3), 'hub-relative module velocities')

    def evaluate(self, *, time_s, kinematics, conditions):
        """Map actual paired motion to external forces/couples at actual hubs.

        Return application points relative to fixed D. Do not resolve
        their moments here using a cached or assumed CG. The plant resolves
        all loads once with the same current mass snapshot used in dynamics.
        """
        time = float(time_s)
        if not np.isfinite(time):
            raise ValueError('time_s must be finite')
        self.geometry.validate_spin_kinematics(kinematics)
        if not isinstance(conditions, CoaxialConditions):
            raise TypeError('Explicit CoaxialConditions required')
        if conditions.model_scope != self.geometry.model_scope:
            raise ValueError('Geometry and operating-condition scopes differ')
        expected_spacing = self.geometry.axial_spacing_m
        if abs(conditions.rotor_axial_spacing_m - expected_spacing) > 1e-12 * expected_spacing:
            raise ValueError('Performance-map spacing differs from actual geometry')
        performance = self.performance_map.evaluate(
            time_s=time, kinematics=kinematics, conditions=conditions,
        )
        if not isinstance(performance, CoaxialPerformance):
            raise TypeError('Paired map must return CoaxialPerformance')
        if performance.conditions != conditions:
            raise ValueError('Paired map returned different operating conditions')
        rotation = self.geometry.rotation_BM(kinematics)
        points = self.geometry.application_points_D_m(kinematics)
        loads = []
        for index, spin_sign in enumerate(self.geometry.spin_signs):
            thrust = performance.thrust_N[index]
            drag = performance.aerodynamic_drag_torque_N_m[index]
            with np.errstate(over='raise', invalid='raise'):
                force_B = rotation @ np.array([0.0, 0.0, -thrust])
                aerodynamic_couple_B = rotation @ np.array([
                    0.0, 0.0, -spin_sign * drag,
                ])
            loads.append(AppliedLoad(
                force_B_N=force_B,
                application_point_D_m=points[index],
                free_moment_B_N_m=aerodynamic_couple_B,
                model_scope=self.geometry.model_scope,
                provenance=(('upper' if index == 0 else 'lower')
                            + ' rotor; geometry: ' + self.geometry.provenance
                            + '; paired map: ' + performance.provenance),
            ))
        return PropulsionEvaluation(
            performance=performance,
            rotor_loads=tuple(loads),
            provenance=('Separated-origin common-gimbal external rotor loads; '
                        + self.geometry.provenance
                        + '; paired map: ' + performance.provenance),
        )
