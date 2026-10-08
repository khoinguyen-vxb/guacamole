import numpy as np
from helpers.math import quarternion_to_dcm, euler_to_quaternion
from helpers.constants import GRAVITY
from state import State
from scipy.integrate import solve_ivp


class Simulation:
    def __init__(self, state: State, environment, hopper, aero):
        self.state = None
        self.environment = environment
        self.hopper = hopper
        self.aero = aero

    def trajectory_ode(self, time, state):
        if self.time != 0:
            self.state.update_state(state)

        if self.state == None:
            print("bricked")

        position = np.array([state.x, state.y, state.z], dtype=float)
        velocity_body = np.array([state.u, state.v, state.w], dtype=float)

        quaternion = np.array([state.q0, state.q1, state.q2, state.q3], dtype=float)

        angular_rates = np.array([state.p, state.q, state.r], dtype=float)

        p, q, r = angular_rates

        # Preserve the original norm error for feedback correction.
        quaternion_norm_error = 1 - quaternion @ quaternion

        # Use a unit quaternion when generating the DCM.
        quaternion_unit = quaternion / np.linalg.norm(quaternion)

        TBL = quarternion_to_dcm(quaternion_unit)
        TLB = TBL.T

        # Environment
        height = -position[2]
        altitude = self.environment.elevation + height

        atmosphere = self.environment.atmosphere

        speed_of_sound = atmosphere.speed_of_sound(altitude)
        density = atmosphere.density(altitude)
        dynamic_viscosity = atmosphere.dynamic_viscosity(altitude)

        wind_velocity_local = np.asarray(
            atmosphere.wind_velocity(altitude), dtype=float
        )

        # Relative airflow
        rocket_velocity_local = TLB @ velocity_body
        air_velocity_local = rocket_velocity_local - wind_velocity_local
        air_velocity_body = TBL @ air_velocity_local

        air_speed = np.linalg.norm(air_velocity_body)

        if air_speed < 1e-8:
            mach = 0
            dynamic_pressure = 0
            reynolds = 0
            alpha = 0
            beta = 0
        else:
            mach = air_speed / speed_of_sound
            dynamic_pressure = 0.5 * density * air_speed**2

            reynolds = (
                density * air_speed * self.hopper.reference_length / dynamic_viscosity
            )

            alpha = np.arctan2(air_velocity_body[2], air_velocity_body[0])

            beta = np.arcsin(np.clip(air_velocity_body[1] / air_speed, -1, 1))

        quaternion_rate_matrix = np.array(
            [[0, -p, -q, -r], [p, 0, r, -q], [q, -r, 0, p], [r, q, -p, 0]]
        )

        correction_gain = 0.5

        quaternion_dot = (
            0.5 * quaternion_rate_matrix @ quaternion
            + correction_gain * quaternion_norm_error * quaternion
        )

        # Mass properties
        mass = self.hopper.mass(time)
        cg = np.asarray(self.hopper.CG(time))
        inertia = np.asarray(self.hopper.inertia(time))

        # Forces and moments must all be in body coordinates
        prop_force, prop_moment = self.hopper.get_thrust_and_moment(time)

        aero_force, aero_moment = self.aero.determine_at_point(
            air_velocity_body=air_velocity_body,
            angular_rates_body=angular_rates,
            density=density,
            dynamic_viscosity=dynamic_viscosity,
            speed_of_sound=speed_of_sound,
            cg=cg,
        )

        total_force_body = aero_force + prop_force
        total_moment_body = aero_moment + prop_moment

        # Translational kinematics
        position_dot = TLB @ velocity_body

        # Translational dynamics
        gravity_local = np.array([0, 0, GRAVITY])
        gravity_body = TBL @ gravity_local

        velocity_dot = (
            total_force_body / mass
            + gravity_body
            - np.cross(angular_rates, velocity_body)
        )

        # Rotational dynamics
        body_rate_dot = np.linalg.solve(
            inertia,
            total_moment_body - np.cross(angular_rates, inertia @ angular_rates),
        )

        return np.concatenate(
            (position_dot, velocity_dot, quaternion_dot, body_rate_dot)
        )

    def solve_ode(self, init_roll, init_pitch, init_yaw, t_max):
        q = euler_to_quaternion(init_roll, init_pitch, init_yaw)
        initial_state = (0, 0, 0, 0, 0, 0, q[0], q[1], q[2], q[3], 0, 0, 0)
        absolute_tolerance = np.array(
            [1e-6] * 3  # position
            + [1e-7] * 3  # velocity
            + [1e-9] * 4  # quaternion
            + [1e-8] * 3  # angular rates
        )
        self.state = State(*initial_state)

        solution = solve_ivp(
            fun=self.trajectory_ode,
            t_span=(0.0, t_max),
            y0=initial_state,
            method="RK45",
            rtol=1e-7,
            atol=absolute_tolerance,
            max_step=0.01,
            dense_output=True,
        )
