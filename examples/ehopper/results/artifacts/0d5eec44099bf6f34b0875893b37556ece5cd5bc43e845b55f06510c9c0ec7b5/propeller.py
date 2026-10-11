"""Concrete coaxial external-load adapter for the sandbox PDR-R9 plant.

Audited original: 6dof_hopper/propulsion/propeller.py
Original SHA-256: caa5ee91e46d102b8ebe0c02e1dfec0ecdca18e2c423791fca6f2c19100ae7b6
Pre-edit audit: PDR-R9-PLANT-PRE-EDIT-AUDIT-01 r1, RC08/RC11/RC12.
Frame decision: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal decision: 84ef41fdd3fd4266ada43df2ace64a48 r1.

Intentional API migration:
  The unusable legacy constructor's discarded electrical arguments are NOT
  accepted. Supply explicit geometry and a coupled CoaxialPerformanceMap.
  The inherited incomplete mass/CG/time-only wrench methods are replaced by
  evaluate(time_s, kinematics, conditions), with keyword-only arguments.
  Hopper no longer forwards propulsion loads or adds propulsion mass.
  Simulation must resolve this evaluation about its current CG snapshot.

This file maps actual rotor/gimbal states into external loads. A separate
actuator model must evolve those states with lag and saturation. This is
not a direct command-to-thrust model and contains no calibrated map, motor
response, vehicle dimensions, historical lever arm or travel defaults.
No numerical or physical verification is claimed by writing this file.
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


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


@dataclass(frozen=True, slots=True)
class CoaxialGeometry:
    """Ideal intersecting-axis common-gimbal geometry, in SI.

    pivot_B0_m is a FIXED structural point relative to O_B0, not relative
    to the moving CG. hub_offsets_M_m contains upper/lower application
    points measured from the pivot in module axes M. Their common thrust
    line may be offset from the pivot but both hubs must be coaxial.
    +z_M points down at neutral: lower hub z must exceed upper hub z.

    spin_signs are exactly +1/-1 about the SAME +z_M axis. A supplier's
    visual CW/CCW label must be converted with its viewing direction.

    The model assumes a body-fixed pivot and ideal intersecting joint axes.
    Bearing compliance, nonintersecting axes and linkage offsets require a
    revised geometry/kinematics provider; they are not silently represented.
    Hub points are force application points of this reduced rotor model,
    not independently established aerodynamic centers under all inflows.
    """

    pivot_B0_m: tuple[float, float, float]
    hub_offsets_M_m: tuple
    spin_signs: tuple[int, int]
    model_scope: str
    provenance: str

    def __post_init__(self):
        pivot = finite_array(self.pivot_B0_m, (3,), 'pivot_B0_m')
        hubs = finite_array(self.hub_offsets_M_m, (2, 3), 'hub_offsets_M_m')
        signs = tuple(self.spin_signs)
        if (len(signs) != 2 or any(type(x) is not int for x in signs)
                or set(signs) != {-1, 1}):
            raise ValueError('Supply opposite integer spin signs about common +z_M')
        with np.errstate(over='raise', invalid='raise'):
            separation = hubs[1] - hubs[0]
        if separation[2] <= 0.0:
            raise ValueError('Upper/lower hub ordering requires positive axial spacing')
        # Roundoff allowance only, NOT a manufacturing/alignment acceptance.
        scale = float(np.max(np.abs(hubs)))
        if np.max(np.abs(separation[:2])) > 32.0 * np.finfo(float).eps * scale:
            raise ValueError('This ideal model requires coaxial hub offsets')
        if self.model_scope not in MODEL_SCOPES:
            raise ValueError('Unknown model_scope')
        _text(self.provenance, 'provenance')
        object.__setattr__(self, 'pivot_B0_m', tuple(float(x) for x in pivot))
        object.__setattr__(self, 'hub_offsets_M_m',
                           tuple(tuple(float(x) for x in row) for row in hubs))
        object.__setattr__(self, 'spin_signs', signs)

    @property
    def axial_spacing_m(self):
        return self.hub_offsets_M_m[1][2] - self.hub_offsets_M_m[0][2]

    def rotation_BM(self, kinematics):
        if not isinstance(kinematics, AssemblyKinematics):
            raise TypeError('Explicit AssemblyKinematics required')
        alpha, beta = kinematics.gimbal_rad
        return gimbal_to_body(alpha_rad=alpha, beta_rad=beta)

    def application_points_B0_m(self, kinematics):
        rotation = self.rotation_BM(kinematics)
        points = (np.asarray(self.pivot_B0_m)
                  + (rotation @ np.asarray(self.hub_offsets_M_m).T).T)
        return finite_array(points, (2, 3), 'application points')

    def validate_spin_kinematics(self, kinematics):
        """Reject reverse spin and acceleration out of the zero-speed boundary.

        Deceleration while spinning is permitted. Speed/acceleration limits
        belong to the actuator model and the performance validity checks.
        Windmilling and rotor reversal are outside this preliminary model.
        """
        if not isinstance(kinematics, AssemblyKinematics):
            raise TypeError('Explicit AssemblyKinematics required')
        signs = np.asarray(self.spin_signs)
        speeds = signs * np.asarray(kinematics.rotor_signed_speed_rad_s)
        acceleration = signs * np.asarray(kinematics.rotor_signed_acceleration_rad_s2)
        if np.any(speeds < 0.0):
            raise ValueError('Actual rotor speed opposes configured spin direction')
        if np.any((speeds == 0.0) & (acceleration < 0.0)):
            raise ValueError('Rotor acceleration leaves the allowed zero-speed boundary')


@dataclass(frozen=True, slots=True)
class Propellor(Propulsion):
    """Concrete paired-rotor adapter; retain original class spelling.

    The map evaluates BOTH actual rotor states simultaneously and owns its
    coaxial/electrical treatment. No doubling of isolated-rotor thrust or
    torque/current clipping is performed here. Map admissibility remains
    an explicit tri-state report; this adapter does not convert unknown
    domains or known violations into accepted vehicle operating points.

    Mass belongs to the complete-vehicle ledger, not this adapter. External
    air-on-rotor torque is included exactly once. Motor/servo reactions and
    rotor acceleration torque must NOT be added as extra external couples.
    Their whole-vehicle effects require consistent relative momentum terms
    in MassProperties, or an explicitly documented reduced approximation.
    """

    geometry: CoaxialGeometry
    performance_map: CoaxialPerformanceMap

    def __post_init__(self):
        if not isinstance(self.geometry, CoaxialGeometry):
            raise TypeError('Explicit CoaxialGeometry required')
        if not callable(getattr(self.performance_map, 'evaluate', None)):
            raise TypeError('performance_map must implement evaluate')

    def hub_velocities_relative_air_M_m_s(
        self, *, state, mass_properties, kinematics, wind_at_hubs_L_m_s,
    ):
        """Return each hub's ambient-air-relative velocity in module axes.

        wind_at_hubs_L_m_s is an explicit (2,3) array in local NED axes,
        sampled at the two actual hub locations. Uniform wind must still
        be supplied twice. Induced flow/wake is NOT added here: the paired
        performance map must specify whether/how it accounts for that.

        For fixed pivot P and hub offset d_i in M:
          r_B0i = r_B0P + R_BM*d_i
          r_dot_B0i = omega_MB,B cross (R_BM*d_i)
          v_i,B = R_BL*v_G,L + omega_B cross (r_B0i-r_B0G)
                  + r_dot_B0i - r_dot_B0G.

        omega_MB,B = [alpha_dot, cos(alpha)*beta_dot,
                      sin(alpha)*beta_dot]. Generalized angle rates are
        not interchangeable with angular-velocity vector components.
        The CG-offset derivative excludes the body-rotation cross term.
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
        points = self.geometry.application_points_B0_m(kinematics)
        offsets_B = (rotation @ np.asarray(self.geometry.hub_offsets_M_m).T).T
        alpha = kinematics.gimbal_rad[0]
        alpha_rate, beta_rate = kinematics.gimbal_rate_rad_s
        relative_omega_B = np.array([
            alpha_rate, np.cos(alpha) * beta_rate, np.sin(alpha) * beta_rate,
        ])
        velocities = []
        for index in range(2):
            arm = mass_properties.moment_arm_m(points[index])
            local_relative = state.velocity_G_L_m_s - wind[index]
            velocity_B = (
                R_BL @ local_relative
                + np.cross(state.omega_B_rad_s, arm)
                + np.cross(relative_omega_B, offsets_B[index])
                - np.asarray(mass_properties.cg_rate_B0_m_s)
            )
            velocities.append(rotation.T @ velocity_B)
        return finite_array(velocities, (2, 3), 'hub-relative module velocities')

    def evaluate(self, *, time_s, kinematics, conditions):
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
        points = self.geometry.application_points_B0_m(kinematics)
        loads = []
        for index, spin_sign in enumerate(self.geometry.spin_signs):
            thrust = performance.thrust_N[index]
            drag = performance.aerodynamic_drag_torque_N_m[index]
            loads.append(AppliedLoad(
                force_B_N=rotation @ np.array([0.0, 0.0, -thrust]),
                application_point_B0_m=points[index],
                free_moment_B_N_m=rotation @ np.array([0.0, 0.0, -spin_sign * drag]),
                model_scope=self.geometry.model_scope,
                provenance=(('upper' if index == 0 else 'lower')
                            + ' rotor; geometry: ' + self.geometry.provenance
                            + '; paired map: ' + performance.provenance),
            ))
        return PropulsionEvaluation(
            performance=performance,
            rotor_loads=tuple(loads),
            provenance=('Common-gimbal external rotor loads; geometry: '
                        + self.geometry.provenance
                        + '; paired map: ' + performance.provenance),
        )
