import numpy as np


class Aerodynamics:
    def __init__(self, hopper):
        self.hopper = hopper

    def determine_at_point(
        self,
        air_velocity_body,
        angular_rates_body,
        density,
        dynamic_viscosity,
        speed_of_sound,
        cg,
        inner_diameter=0,
        tube_axis_body=(1, 0, 0),
        closed_front=True,
        front_pressure_cd=0.8,
    ):
        """
        Calculate aerodynamic force and moment of a cylindrical tube.

        Uses:
            OpenRocket equation 3.26 for cylindrical body lift
            OpenRocket equation 3.58 for pitch/yaw damping
            OpenRocket equations 3.78, 3.82-3.85 for skin friction

        Assumptions:
            - air_velocity_body is vehicle velocity relative to air
            - all vectors are expressed in body coordinates
            - body +x is normally the tube longitudinal axis
            - force and moment are returned in body coordinates
            - tube is circular and axisymmetric

        Parameters
        ----------
        air_velocity_body : array_like, shape (3,)
            Vehicle velocity relative to air in body coordinates [m/s].

        angular_rates_body : array_like, shape (3,)
            Body angular rates [p, q, r] in body coordinates [rad/s].

        density : float
            Air density [kg/m^3].

        dynamic_viscosity : float
            Dynamic viscosity [Pa.s].

        speed_of_sound : float
            Local speed of sound [m/s].

        tube_length : float
            Tube length [m].

        outer_diameter : float
            Tube outer diameter [m].

        tube_center_body : array_like, shape (3,)
            Tube geometric-centre position relative to the body datum [m].

        cg_body : array_like, shape (3,)
            Vehicle CG position relative to the same body datum [m].

        inner_diameter : float
            Tube inner diameter [m].

        tube_axis_body : array_like, shape (3,)
            Unit vector along the tube longitudinal axis.

        closed_front : bool
            If True, use the full circular frontal area.
            If False, use the annular tube-wall area.

        front_pressure_cd : float
            Pressure-drag coefficient of the front face.
            OpenRocket gives approximately 0.8 for a flat blunt face.

        Returns
        -------
        force_body : ndarray, shape (3,)
            Total tube aerodynamic force [N].

        moment_body : ndarray, shape (3,)
            Total tube aerodynamic moment about the vehicle CG [N.m].
        """

        epsilon = 1e-10

        velocity = np.asarray(air_velocity_body, dtype=float)
        omega = np.asarray(angular_rates_body, dtype=float)
        tube_center = np.asarray(
            self.hopper.tube_center_body,
            dtype=float,
        )
        cg = np.asarray(cg, dtype=float)

        tube_axis = np.asarray(tube_axis_body, dtype=float)
        axis_norm = np.linalg.norm(tube_axis)

        if axis_norm < epsilon:
            raise ValueError("tube_axis_body cannot be a zero vector")

        tube_axis /= axis_norm

        air_speed = np.linalg.norm(velocity)

        if air_speed < epsilon:
            return np.zeros(3), np.zeros(3)

        dynamic_pressure = 0.5 * density * air_speed**2

        # Vector from vehicle CG to the tube centre/CP.
        r_cp = tube_center - cg

        # ------------------------------------------------------------------
        # Resolve airflow into axial and transverse components
        # ------------------------------------------------------------------

        axial_velocity_scalar = np.dot(velocity, tube_axis)

        axial_velocity = axial_velocity_scalar * tube_axis

        crossflow_velocity = velocity - axial_velocity
        crossflow_speed = np.linalg.norm(crossflow_velocity)

        # ------------------------------------------------------------------
        # Cylindrical body normal force: OpenRocket equation 3.26
        #
        # CN = K (D L / Aref) sin(alpha)^2
        # N  = q Aref CN
        #
        # K approximately 1.1
        # ------------------------------------------------------------------

        normal_force = np.zeros(3)

        if crossflow_speed > epsilon:
            sin_alpha = np.clip(crossflow_speed / air_speed, 0, 1)

            normal_force_magnitude = (
                dynamic_pressure
                * 1.1
                * self.hopper.outer_diameter
                * self.hopper.length
                * sin_alpha**2
            )

            normal_force = (
                -normal_force_magnitude * crossflow_velocity / crossflow_speed
            )

        static_moment = np.cross(r_cp, normal_force)

        # ------------------------------------------------------------------
        # Axial skin-friction drag
        # OpenRocket equations 3.78 and 3.82-3.85
        # ------------------------------------------------------------------

        axial_force = np.zeros(3)

        axial_speed = abs(axial_velocity_scalar)

        if axial_speed > epsilon:
            reynolds = density * axial_speed * self.hopper.length / dynamic_viscosity

            if reynolds < 1e4:
                skin_friction_coefficient = 1.48e-2
            else:
                skin_friction_coefficient = 1 / (1.5 * np.log(reynolds) - 5.6) ** 2

            mach = axial_speed / speed_of_sound

            # Compressibility correction
            if mach < 1:
                corrected_skin_friction = skin_friction_coefficient * (
                    1 - 0.1 * mach**2
                )
            else:
                corrected_skin_friction = (
                    skin_friction_coefficient / (1 + 0.15 * mach**2) ** 0.58
                )

            wetted_area = np.pi * self.hopper.outer_diameter * self.hopper.length

            fineness_ratio = self.hopper.length / self.hopper.outer_diameter

            body_shape_correction = 1 + 1 / (2 * fineness_ratio)

            axial_dynamic_pressure = 0.5 * density * axial_speed**2

            skin_friction_drag = (
                axial_dynamic_pressure
                * corrected_skin_friction
                * body_shape_correction
                * wetted_area
            )

            # Frontal pressure drag
            if closed_front:
                frontal_area = np.pi * self.hopper.outer_diameter**2 / 4
            else:
                frontal_area = (
                    np.pi
                    * (self.hopper.outer_diameter**2 - self.hopper.inner_diameter**2)
                    / 4
                )

            pressure_drag = axial_dynamic_pressure * front_pressure_cd * frontal_area

            total_axial_drag = skin_friction_drag + pressure_drag

            # Oppose the axial component of motion.
            axial_direction = np.sign(axial_velocity_scalar) * tube_axis

            axial_force = -total_axial_drag * axial_direction

        axial_moment = np.cross(r_cp, axial_force)

        # ------------------------------------------------------------------
        # Pitch/yaw damping: analytical form of OpenRocket equation 3.58
        # ------------------------------------------------------------------

        omega_axial = np.dot(omega, tube_axis) * tube_axis

        omega_transverse = omega - omega_axial
        omega_transverse_magnitude = np.linalg.norm(omega_transverse)

        damping_moment = np.zeros(3)

        if omega_transverse_magnitude > epsilon:
            # Tube-end positions measured longitudinally from the CG.
            tube_center_from_cg = np.dot(r_cp, tube_axis)

            first_end = tube_center_from_cg - self.hopper.length / 2

            second_end = tube_center_from_cg + self.hopper.length / 2

            # Integral of |x|^3 dx over the complete tube.
            distance_integral = (
                second_end * abs(second_end) ** 3 - first_end * abs(first_end) ** 3
            ) / 4

            damping_coefficient = (
                0.5 * density * 1.1 * self.hopper.outer_diameter * distance_integral
            )

            damping_moment = (
                -damping_coefficient * omega_transverse_magnitude * omega_transverse
            )

        # ------------------------------------------------------------------
        # Total force and moment about vehicle CG
        # ------------------------------------------------------------------

        force_body = normal_force + axial_force

        moment_body = static_moment + axial_moment + damping_moment

        return force_body, moment_body
