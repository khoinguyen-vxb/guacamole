# Current static caller reconciliation

Model r4; static evidence only.

## original_hopper/main.py
SHA256 67ebbf79c219721eb1f0cc6e4817b8fb218488b6dec4bbd25a1f0faee6527dbc

L2-2 | main | print
L6-6 | <module> | main

## original_hopper/aero/aero.py
SHA256 9008c26ea2c2c26e1e26441ee17f27872e1d34bf1c0d9cb7179ce285d6e2b53f

Import L1: import numpy as np
L90-90 | Aerodynamics.determine_at_point | np.asarray
L91-91 | Aerodynamics.determine_at_point | np.asarray
L92-95 | Aerodynamics.determine_at_point | np.asarray
L96-96 | Aerodynamics.determine_at_point | np.asarray
L98-98 | Aerodynamics.determine_at_point | np.asarray
L99-99 | Aerodynamics.determine_at_point | np.linalg.norm
L102-102 | Aerodynamics.determine_at_point | ValueError
L106-106 | Aerodynamics.determine_at_point | np.linalg.norm
L109-109 | Aerodynamics.determine_at_point | np.zeros
L109-109 | Aerodynamics.determine_at_point | np.zeros
L120-120 | Aerodynamics.determine_at_point | np.dot
L125-125 | Aerodynamics.determine_at_point | np.linalg.norm
L136-136 | Aerodynamics.determine_at_point | np.zeros
L139-139 | Aerodynamics.determine_at_point | np.clip
L153-153 | Aerodynamics.determine_at_point | np.cross
L160-160 | Aerodynamics.determine_at_point | np.zeros
L162-162 | Aerodynamics.determine_at_point | abs
L170-170 | Aerodynamics.determine_at_point | np.log
L214-214 | Aerodynamics.determine_at_point | np.sign
L218-218 | Aerodynamics.determine_at_point | np.cross
L224-224 | Aerodynamics.determine_at_point | np.dot
L227-227 | Aerodynamics.determine_at_point | np.linalg.norm
L229-229 | Aerodynamics.determine_at_point | np.zeros
L233-233 | Aerodynamics.determine_at_point | np.dot
L241-241 | Aerodynamics.determine_at_point | abs
L241-241 | Aerodynamics.determine_at_point | abs

## original_hopper/chassis/hopper.py
SHA256 6e2b2f93e98b844ce04f68d26b704c65270e9329e1abff76caa45cbcd5dcf0bd

Import L1: from dataclasses import dataclass, field
Import L2: from typing import Optional
Import L4: import numpy as np
Import L6: from propulsion.propulsion import Propulsion
L25-27 | Hopper | field
L26-26 | Hopper | np.zeros
L31-31 | Hopper.__post_init__ | np.asarray
L32-32 | Hopper.__post_init__ | np.asarray
L33-36 | Hopper.__post_init__ | np.asarray
L39-39 | Hopper.__post_init__ | getattr
L40-40 | Hopper.__post_init__ | ValueError
L46-46 | Hopper.mass | self.propulsion.get_mass
L49-49 | Hopper.CG | self.cg.copy
L52-52 | Hopper.inertia | np.diag
L58-58 | Hopper.get_thrust_and_moment | self.propulsion.get_thrust_and_moment

## original_hopper/helpers/constants.py
SHA256 4853ae63f4d7df5254af6fbab9b46dd31ca60aa722dd3580643064bfce9523a4


## original_hopper/helpers/math.py
SHA256 5e6420ade1c4d642762ba4d6b0812a80f2f693a58151bbf16a4274efb521239a

Import L1: from numpy.typing import NDArray
Import L2: import numpy as np
L13-13 | quarternion_to_dcm | np.array
L13-13 | quarternion_to_dcm | np.linalg.norm
L19-19 | quarternion_to_dcm | np.square
L19-19 | quarternion_to_dcm | np.square
L19-19 | quarternion_to_dcm | np.square
L19-19 | quarternion_to_dcm | np.square
L24-24 | quarternion_to_dcm | np.square
L24-24 | quarternion_to_dcm | np.square
L24-24 | quarternion_to_dcm | np.square
L24-24 | quarternion_to_dcm | np.square
L29-29 | quarternion_to_dcm | np.square
L29-29 | quarternion_to_dcm | np.square
L29-29 | quarternion_to_dcm | np.square
L29-29 | quarternion_to_dcm | np.square
L32-32 | quarternion_to_dcm | np.array
L35-35 | quarternion_to_dcm | np.transpose
L43-43 | euler_to_quaternion | np.deg2rad
L49-49 | euler_to_quaternion | np.cos
L49-49 | euler_to_quaternion | np.cos
L49-49 | euler_to_quaternion | np.cos
L49-51 | euler_to_quaternion | np.sin
L51-51 | euler_to_quaternion | np.sin
L51-51 | euler_to_quaternion | np.sin
L52-52 | euler_to_quaternion | np.cos
L52-52 | euler_to_quaternion | np.cos
L52-52 | euler_to_quaternion | np.sin
L52-54 | euler_to_quaternion | np.sin
L54-54 | euler_to_quaternion | np.sin
L54-54 | euler_to_quaternion | np.cos
L55-55 | euler_to_quaternion | np.cos
L55-55 | euler_to_quaternion | np.sin
L55-55 | euler_to_quaternion | np.cos
L55-57 | euler_to_quaternion | np.sin
L57-57 | euler_to_quaternion | np.cos
L57-57 | euler_to_quaternion | np.sin
L58-58 | euler_to_quaternion | np.sin
L58-58 | euler_to_quaternion | np.cos
L58-58 | euler_to_quaternion | np.cos
L58-60 | euler_to_quaternion | np.cos
L60-60 | euler_to_quaternion | np.sin
L60-60 | euler_to_quaternion | np.sin
L63-63 | euler_to_quaternion | np.array
L66-66 | euler_to_quaternion | np.array
L66-66 | euler_to_quaternion | np.linalg.norm

## original_hopper/propulsion/propeller.py
SHA256 caa5ee91e46d102b8ebe0c02e1dfec0ecdca18e2c423791fca6f2c19100ae7b6

Import L1: from propulsion.propulsion import Propulsion
L15-15 | Propellor.__init__ | Call(func=Name(id='super', ctx=Load())).__init__
L15-15 | Propellor.__init__ | super

## original_hopper/propulsion/propulsion.py
SHA256 e07b895d8399016a3b0511afb195d7ebf992050cef04ab3015600347f01750ce

Import L1: from enum import Enum, auto, unique
Import L2: from abc import ABC, abstractmethod
L6-6 | PropulsionType | auto
L7-7 | PropulsionType | auto

## original_hopper/scripts/ehopper.py
SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855


## original_hopper/simulation/simulation.py
SHA256 087767eef40f728775d5bd8ee597a6e0a8c0769fe4d2d6ab2a060d06692f86ca

Import L1: import numpy as np
Import L2: from helpers.math import quarternion_to_dcm, euler_to_quaternion
Import L3: from helpers.constants import GRAVITY
Import L4: from state import State
Import L5: from scipy.integrate import solve_ivp
L17-17 | Simulation.trajectory_ode | self.state.update_state
L20-20 | Simulation.trajectory_ode | print
L22-22 | Simulation.trajectory_ode | np.array
L23-23 | Simulation.trajectory_ode | np.array
L25-25 | Simulation.trajectory_ode | np.array
L27-27 | Simulation.trajectory_ode | np.array
L35-35 | Simulation.trajectory_ode | np.linalg.norm
L37-37 | Simulation.trajectory_ode | quarternion_to_dcm
L46-46 | Simulation.trajectory_ode | atmosphere.speed_of_sound
L47-47 | Simulation.trajectory_ode | atmosphere.density
L48-48 | Simulation.trajectory_ode | atmosphere.dynamic_viscosity
L50-52 | Simulation.trajectory_ode | np.asarray
L51-51 | Simulation.trajectory_ode | atmosphere.wind_velocity
L59-59 | Simulation.trajectory_ode | np.linalg.norm
L75-75 | Simulation.trajectory_ode | np.arctan2
L77-77 | Simulation.trajectory_ode | np.arcsin
L77-77 | Simulation.trajectory_ode | np.clip
L79-81 | Simulation.trajectory_ode | np.array
L91-91 | Simulation.trajectory_ode | self.hopper.mass
L92-92 | Simulation.trajectory_ode | np.asarray
L92-92 | Simulation.trajectory_ode | self.hopper.CG
L93-93 | Simulation.trajectory_ode | np.asarray
L93-93 | Simulation.trajectory_ode | self.hopper.inertia
L96-96 | Simulation.trajectory_ode | self.hopper.get_thrust_and_moment
L98-105 | Simulation.trajectory_ode | self.aero.determine_at_point
L114-114 | Simulation.trajectory_ode | np.array
L120-120 | Simulation.trajectory_ode | np.cross
L124-127 | Simulation.trajectory_ode | np.linalg.solve
L126-126 | Simulation.trajectory_ode | np.cross
L129-131 | Simulation.trajectory_ode | np.concatenate
L134-134 | Simulation.solve_ode | euler_to_quaternion
L136-141 | Simulation.solve_ode | np.array
L142-142 | Simulation.solve_ode | State
L144-153 | Simulation.solve_ode | solve_ivp

## original_hopper/simulation/state.py
SHA256 7b8713aecd017a7ff1f0b3ad4e14e1c63c716d1181a6df516d25b7a7d1973b2a

L32-32 | State.update_state | self.x_arr.append
L33-33 | State.update_state | self.y_arr.append
L34-34 | State.update_state | self.z_arr.append
L35-35 | State.update_state | self.u_arr.append
L36-36 | State.update_state | self.v_arr.append
L37-37 | State.update_state | self.w_arr.append
L38-38 | State.update_state | self.q0_arr.append
L39-39 | State.update_state | self.q1_arr.append
L40-40 | State.update_state | self.q2_arr.append
L41-41 | State.update_state | self.q3_arr.append
L42-42 | State.update_state | self.p_arr.append
L43-43 | State.update_state | self.q_arr.append
L44-44 | State.update_state | self.r_arr.append

## original_hopper/test/__init__.py
SHA256 d72bcd69d0ed6d706e690574d1dbdedf15ab740d5ce705aad834bd1b91b3d76e


## original_hopper/test/test_pythrust.py
SHA256 a3590eef1c8b2d922a54464d7254205ca046c4af4e42f4bde815a67cec690a0d

Import L6: import math
Import L7: from pathlib import Path
Import L8: import sys
Import L13: from pythrust.battery import FixedVoltageBattery
Import L14: from pythrust.propellers import PropellerDatabase
Import L15: from pythrust.propulsion import MotorSpec, PropellerSpec, PropulsionSolver, SystemSpec
L10-10 | <module> | Call(func=Name(id='Path', ctx=Load()), args=[Name(id='__file__', ctx=Load())]).resolve
L10-10 | <module> | Path
L11-11 | <module> | sys.path.insert
L11-11 | <module> | str
L39-39 | <module> | PropellerDatabase
L40-43 | <module> | propeller_database.load
L45-45 | <module> | propeller_database.get
L47-47 | <module> | KeyError
L49-54 | <module> | MotorSpec
L56-56 | <module> | FixedVoltageBattery
L57-57 | <module> | SystemSpec
L58-62 | <module> | PropellerSpec
L63-63 | <module> | PropulsionSolver
L79-79 | results_at_rpm | propeller_data.get_coefficients
L94-94 | results_at_voltage | ValueError
L105-114 | results_at_voltage | solver.solve_operating_point
L126-126 | <module> | print
L126-126 | <module> | results_at_rpm
L127-127 | <module> | print
L127-127 | <module> | results_at_voltage

## recovered_previous_run/repaired_hopper_r12/chassis/hopper.py
SHA256 f2b6e4b54634220105655e994e3ff5c78e84c60084879696a25ef39fdc29ff05

Import L28: from __future__ import annotations
Import L30: from dataclasses import dataclass
Import L31: from typing import Protocol
Import L33: import numpy as np
Import L35: from ..helpers.math import finite_array
L48-48 | _positive_scalar | float
L49-49 | _positive_scalar | np.isfinite
L50-50 | _positive_scalar | ValueError
L55-55 | _text | isinstance
L55-55 | _text | value.strip
L56-56 | _text | ValueError
L61-61 | _vector_tuple | tuple
L61-61 | _vector_tuple | float
L61-61 | _vector_tuple | finite_array
L71-71 | _symmetric_matrix_tuple | finite_array
L72-72 | _symmetric_matrix_tuple | float
L72-72 | _symmetric_matrix_tuple | np.max
L72-72 | _symmetric_matrix_tuple | np.abs
L75-75 | _symmetric_matrix_tuple | ValueError
L76-76 | _symmetric_matrix_tuple | tuple
L76-76 | _symmetric_matrix_tuple | tuple
L76-76 | _symmetric_matrix_tuple | float
L78-78 | _symmetric_matrix_tuple | np.max
L78-78 | _symmetric_matrix_tuple | np.abs
L79-79 | _symmetric_matrix_tuple | ValueError
L81-81 | _symmetric_matrix_tuple | np.linalg.eigvalsh
L82-82 | _symmetric_matrix_tuple | np.min
L83-83 | _symmetric_matrix_tuple | ValueError
L85-85 | _symmetric_matrix_tuple | ValueError
L86-86 | _symmetric_matrix_tuple | tuple
L86-86 | _symmetric_matrix_tuple | tuple
L86-86 | _symmetric_matrix_tuple | float
L120-120 | AssemblyKinematics.__post_init__ | object.__setattr__
L120-120 | AssemblyKinematics.__post_init__ | _vector_tuple
L120-120 | AssemblyKinematics.__post_init__ | getattr
L89-89 | AssemblyKinematics | dataclass
L176-176 | MassProperties.__post_init__ | object.__setattr__
L176-176 | MassProperties.__post_init__ | _positive_scalar
L181-181 | MassProperties.__post_init__ | object.__setattr__
L181-181 | MassProperties.__post_init__ | _vector_tuple
L181-181 | MassProperties.__post_init__ | getattr
L182-184 | MassProperties.__post_init__ | object.__setattr__
L182-184 | MassProperties.__post_init__ | _symmetric_matrix_tuple
L185-187 | MassProperties.__post_init__ | object.__setattr__
L185-187 | MassProperties.__post_init__ | _symmetric_matrix_tuple
L189-189 | MassProperties.__post_init__ | ValueError
L191-191 | MassProperties.__post_init__ | ValueError
L192-192 | MassProperties.__post_init__ | _text
L193-193 | MassProperties.__post_init__ | isinstance
L194-194 | MassProperties.__post_init__ | TypeError
L195-195 | MassProperties.__post_init__ | tuple
L195-195 | MassProperties.__post_init__ | _text
L197-197 | MassProperties.__post_init__ | ValueError
L198-198 | MassProperties.__post_init__ | object.__setattr__
L201-201 | MassProperties.__post_init__ | ValueError
L206-206 | MassProperties.__post_init__ | np.any
L206-206 | MassProperties.__post_init__ | np.asarray
L206-206 | MassProperties.__post_init__ | getattr
L207-207 | MassProperties.__post_init__ | ValueError
L210-210 | MassProperties.__post_init__ | np.any
L210-210 | MassProperties.__post_init__ | np.asarray
L210-210 | MassProperties.__post_init__ | getattr
L211-211 | MassProperties.__post_init__ | ValueError
L219-219 | MassProperties.moment_arm_m | finite_array
L220-220 | MassProperties.moment_arm_m | np.errstate
L221-221 | MassProperties.moment_arm_m | np.asarray
L222-222 | MassProperties.moment_arm_m | finite_array
L226-226 | MassProperties.angular_momentum_B_kg_m2_s | finite_array
L227-227 | MassProperties.angular_momentum_B_kg_m2_s | np.errstate
L228-228 | MassProperties.angular_momentum_B_kg_m2_s | np.asarray
L229-229 | MassProperties.angular_momentum_B_kg_m2_s | np.asarray
L230-230 | MassProperties.angular_momentum_B_kg_m2_s | finite_array
L249-249 | MassProperties.angular_acceleration_B_rad_s2 | finite_array
L250-250 | MassProperties.angular_acceleration_B_rad_s2 | finite_array
L251-251 | MassProperties.angular_acceleration_B_rad_s2 | np.asarray
L252-252 | MassProperties.angular_acceleration_B_rad_s2 | np.asarray
L253-253 | MassProperties.angular_acceleration_B_rad_s2 | self.angular_momentum_B_kg_m2_s
L254-254 | MassProperties.angular_acceleration_B_rad_s2 | np.errstate
L255-255 | MassProperties.angular_acceleration_B_rad_s2 | np.cross
L256-256 | MassProperties.angular_acceleration_B_rad_s2 | np.asarray
L257-257 | MassProperties.angular_acceleration_B_rad_s2 | finite_array
L258-258 | MassProperties.angular_acceleration_B_rad_s2 | finite_array
L258-258 | MassProperties.angular_acceleration_B_rad_s2 | np.linalg.solve
L123-123 | MassProperties | dataclass
L301-303 | Hopper.__post_init__ | object.__setattr__
L301-303 | Hopper.__post_init__ | _positive_scalar
L305-305 | Hopper.__post_init__ | ValueError
L306-306 | Hopper.__post_init__ | _text
L307-307 | Hopper.__post_init__ | callable
L307-307 | Hopper.__post_init__ | getattr
L308-308 | Hopper.__post_init__ | TypeError
L316-316 | Hopper.mass_properties | float
L317-317 | Hopper.mass_properties | np.isfinite
L318-318 | Hopper.mass_properties | ValueError
L319-319 | Hopper.mass_properties | isinstance
L320-320 | Hopper.mass_properties | TypeError
L321-321 | Hopper.mass_properties | self.mass_property_provider.snapshot
L322-322 | Hopper.mass_properties | isinstance
L323-323 | Hopper.mass_properties | TypeError
L325-325 | Hopper.mass_properties | ValueError
L326-326 | Hopper.mass_properties | abs
L327-327 | Hopper.mass_properties | ValueError
L280-280 | Hopper | dataclass

## recovered_previous_run/repaired_hopper_r12/helpers/math.py
SHA256 281a5578b6d33c45578350429cb30ead28ba6a378c571c2c6929c60819ceecfb

Import L29: from __future__ import annotations
Import L31: import warnings
Import L33: import numpy as np
L38-38 | finite_array | np.array
L40-40 | finite_array | ValueError
L41-41 | finite_array | np.all
L41-41 | finite_array | np.isfinite
L42-42 | finite_array | ValueError
L53-53 | normalize_quaternion | finite_array
L54-54 | normalize_quaternion | float
L54-54 | normalize_quaternion | np.max
L54-54 | normalize_quaternion | np.abs
L56-56 | normalize_quaternion | ValueError
L58-58 | normalize_quaternion | np.linalg.norm
L66-66 | hamilton_product | finite_array
L67-67 | hamilton_product | finite_array
L68-68 | hamilton_product | np.errstate
L69-69 | hamilton_product | np.dot
L70-70 | hamilton_product | np.cross
L71-71 | hamilton_product | finite_array
L71-71 | hamilton_product | np.concatenate
L80-80 | quaternion_derivative | finite_array
L81-81 | quaternion_derivative | np.any
L82-82 | quaternion_derivative | ValueError
L83-83 | quaternion_derivative | finite_array
L84-84 | quaternion_derivative | hamilton_product
L84-84 | quaternion_derivative | np.concatenate
L89-89 | euler_to_quaternion | finite_array
L90-90 | euler_to_quaternion | np.cos
L91-91 | euler_to_quaternion | np.sin
L92-97 | euler_to_quaternion | normalize_quaternion
L106-106 | quaternion_to_dcm | normalize_quaternion
L107-111 | quaternion_to_dcm | np.array
L120-120 | quarternion_to_dcm | isinstance
L121-121 | quarternion_to_dcm | TypeError
L122-126 | quarternion_to_dcm | warnings.warn
L127-127 | quarternion_to_dcm | quaternion_to_dcm
L140-140 | gimbal_to_body | finite_array
L141-141 | gimbal_to_body | np.cos
L142-142 | gimbal_to_body | np.sin
L143-147 | gimbal_to_body | np.array
L152-152 | cad_to_body_rotation | np.diag
L162-162 | cad_point_to_body_datum_m | finite_array
L163-163 | cad_point_to_body_datum_m | finite_array
L164-164 | cad_point_to_body_datum_m | np.errstate
L165-165 | cad_point_to_body_datum_m | cad_to_body_rotation
L166-166 | cad_point_to_body_datum_m | finite_array
L171-171 | body_datum_point_to_cad_mm | finite_array
L172-172 | body_datum_point_to_cad_mm | finite_array
L173-173 | body_datum_point_to_cad_mm | np.errstate
L174-174 | body_datum_point_to_cad_mm | cad_to_body_rotation
L175-175 | body_datum_point_to_cad_mm | finite_array
L191-191 | cad_inertia_to_body_kg_m2 | finite_array
L192-192 | cad_inertia_to_body_kg_m2 | float
L192-192 | cad_inertia_to_body_kg_m2 | np.max
L192-192 | cad_inertia_to_body_kg_m2 | np.abs
L194-194 | cad_inertia_to_body_kg_m2 | ValueError
L196-196 | cad_inertia_to_body_kg_m2 | np.max
L196-196 | cad_inertia_to_body_kg_m2 | np.abs
L197-197 | cad_inertia_to_body_kg_m2 | ValueError
L200-200 | cad_inertia_to_body_kg_m2 | ValueError
L201-201 | cad_inertia_to_body_kg_m2 | float
L202-202 | cad_inertia_to_body_kg_m2 | np.isfinite
L203-203 | cad_inertia_to_body_kg_m2 | ValueError
L207-207 | cad_inertia_to_body_kg_m2 | ValueError
L210-210 | cad_inertia_to_body_kg_m2 | ValueError
L211-211 | cad_inertia_to_body_kg_m2 | cad_to_body_rotation
L212-212 | cad_inertia_to_body_kg_m2 | np.errstate
L214-214 | cad_inertia_to_body_kg_m2 | finite_array
L215-215 | cad_inertia_to_body_kg_m2 | float
L215-215 | cad_inertia_to_body_kg_m2 | np.max
L215-215 | cad_inertia_to_body_kg_m2 | np.abs
L216-216 | cad_inertia_to_body_kg_m2 | np.min
L216-216 | cad_inertia_to_body_kg_m2 | np.linalg.eigvalsh
L217-217 | cad_inertia_to_body_kg_m2 | ValueError
L236-236 | fixed_datum_kinematics | finite_array
L237-237 | fixed_datum_kinematics | finite_array
L238-238 | fixed_datum_kinematics | finite_array
L239-239 | fixed_datum_kinematics | finite_array
L240-240 | fixed_datum_kinematics | finite_array
L241-241 | fixed_datum_kinematics | quaternion_to_dcm
L242-242 | fixed_datum_kinematics | np.errstate
L244-244 | fixed_datum_kinematics | np.cross
L246-246 | fixed_datum_kinematics | finite_array
L247-247 | fixed_datum_kinematics | finite_array

## recovered_previous_run/repaired_hopper_r12/propulsion/actuators.py
SHA256 bacfd1457ea3d24ae82d4868f3418b46c967fc2442d83d36e96973467645be78

Import L31: from __future__ import annotations
Import L33: from dataclasses import dataclass
Import L34: from typing import Protocol
Import L36: import numpy as np
Import L38: from ..chassis.hopper import AssemblyKinematics
Import L39: from ..helpers.math import finite_array
L54-54 | _pair | finite_array
L55-55 | _pair | np.any
L56-56 | _pair | ValueError
L57-57 | _pair | tuple
L57-57 | _pair | float
L61-61 | _positive | float
L62-62 | _positive | np.isfinite
L63-63 | _positive | ValueError
L68-68 | _text | isinstance
L68-68 | _text | value.strip
L69-69 | _text | ValueError
L88-88 | HeldCommand.__post_init__ | object.__setattr__
L88-88 | HeldCommand.__post_init__ | _pair
L88-88 | HeldCommand.__post_init__ | getattr
L73-73 | HeldCommand | dataclass
L109-109 | ActuatorState.__post_init__ | object.__setattr__
L109-109 | ActuatorState.__post_init__ | _pair
L109-109 | ActuatorState.__post_init__ | getattr
L110-110 | ActuatorState.__post_init__ | any
L111-111 | ActuatorState.__post_init__ | ValueError
L114-118 | ActuatorState.as_vector | np.array
L123-123 | ActuatorState.from_vector | ValueError
L124-124 | ActuatorState.from_vector | finite_array
L125-129 | ActuatorState.from_vector | cls
L91-91 | ActuatorState | dataclass
L174-174 | LagParameters.__post_init__ | tuple
L175-175 | LagParameters.__post_init__ | len
L175-175 | LagParameters.__post_init__ | any
L175-175 | LagParameters.__post_init__ | type
L176-176 | LagParameters.__post_init__ | set
L177-177 | LagParameters.__post_init__ | ValueError
L178-178 | LagParameters.__post_init__ | object.__setattr__
L184-186 | LagParameters.__post_init__ | object.__setattr__
L184-186 | LagParameters.__post_init__ | _pair
L185-185 | LagParameters.__post_init__ | getattr
L189-189 | LagParameters.__post_init__ | object.__setattr__
L189-189 | LagParameters.__post_init__ | _positive
L189-189 | LagParameters.__post_init__ | getattr
L191-191 | LagParameters.__post_init__ | object.__setattr__
L191-191 | LagParameters.__post_init__ | _pair
L191-191 | LagParameters.__post_init__ | getattr
L192-192 | LagParameters.__post_init__ | np.asarray
L193-193 | LagParameters.__post_init__ | np.asarray
L194-194 | LagParameters.__post_init__ | np.any
L194-194 | LagParameters.__post_init__ | np.any
L195-195 | LagParameters.__post_init__ | np.any
L196-196 | LagParameters.__post_init__ | ValueError
L197-197 | LagParameters.__post_init__ | np.any
L197-197 | LagParameters.__post_init__ | np.any
L198-198 | LagParameters.__post_init__ | ValueError
L200-200 | LagParameters.__post_init__ | ValueError
L202-202 | LagParameters.__post_init__ | ValueError
L203-203 | LagParameters.__post_init__ | _text
L204-204 | LagParameters.__post_init__ | isinstance
L205-205 | LagParameters.__post_init__ | TypeError
L206-206 | LagParameters.__post_init__ | tuple
L206-206 | LagParameters.__post_init__ | _text
L208-208 | LagParameters.__post_init__ | ValueError
L209-209 | LagParameters.__post_init__ | object.__setattr__
L210-210 | LagParameters.__post_init__ | self.effective_gimbal_rate_rad_s
L213-213 | LagParameters.effective_gimbal_rate_rad_s | np.errstate
L215-215 | LagParameters.effective_gimbal_rate_rad_s | np.asarray
L218-218 | LagParameters.effective_gimbal_rate_rad_s | np.minimum
L219-219 | LagParameters.effective_gimbal_rate_rad_s | np.asarray
L219-219 | LagParameters.effective_gimbal_rate_rad_s | _pair
L222-222 | LagParameters.angles_are_admissible | finite_array
L223-223 | LagParameters.angles_are_admissible | np.finfo
L225-230 | LagParameters.angles_are_admissible | bool
L226-226 | LagParameters.angles_are_admissible | np.all
L226-226 | LagParameters.angles_are_admissible | np.asarray
L227-227 | LagParameters.angles_are_admissible | np.all
L227-227 | LagParameters.angles_are_admissible | np.asarray
L228-228 | LagParameters.angles_are_admissible | np.cos
L228-228 | LagParameters.angles_are_admissible | np.cos
L229-229 | LagParameters.angles_are_admissible | np.cos
L240-240 | LagParameters.bound_command | isinstance
L241-241 | LagParameters.bound_command | TypeError
L242-243 | LagParameters.bound_command | np.clip
L244-245 | LagParameters.bound_command | np.clip
L246-246 | LagParameters.bound_command | np.cos
L247-247 | LagParameters.bound_command | np.cos
L247-247 | LagParameters.bound_command | np.cos
L249-249 | LagParameters.bound_command | range
L252-252 | LagParameters.bound_command | np.cos
L252-252 | LagParameters.bound_command | np.cos
L257-259 | LagParameters.bound_command | HeldCommand
L260-260 | LagParameters.bound_command | self.angles_are_admissible
L261-261 | LagParameters.bound_command | ArithmeticError
L265-265 | LagParameters.validate_state | isinstance
L266-266 | LagParameters.validate_state | TypeError
L267-268 | LagParameters.validate_state | np.any
L267-267 | LagParameters.validate_state | np.asarray
L268-268 | LagParameters.validate_state | np.asarray
L269-269 | LagParameters.validate_state | ValueError
L271-271 | LagParameters.validate_state | self.angles_are_admissible
L272-272 | LagParameters.validate_state | ValueError
L132-132 | LagParameters | dataclass
L277-277 | _common_progress_rate | np.asarray
L277-277 | _common_progress_rate | np.asarray
L278-278 | _common_progress_rate | np.abs
L279-279 | _common_progress_rate | float
L279-279 | _common_progress_rate | np.max
L280-280 | _common_progress_rate | max
L293-293 | _output_acceleration | np.asarray
L297-297 | _output_acceleration | np.sign
L298-298 | _output_acceleration | float
L298-298 | _output_acceleration | np.max
L300-300 | _output_acceleration | max
L320-320 | ActuatorEvaluation.__post_init__ | finite_array
L321-321 | ActuatorEvaluation.__post_init__ | object.__setattr__
L321-321 | ActuatorEvaluation.__post_init__ | tuple
L321-321 | ActuatorEvaluation.__post_init__ | float
L322-322 | ActuatorEvaluation.__post_init__ | isinstance
L323-323 | ActuatorEvaluation.__post_init__ | TypeError
L324-324 | ActuatorEvaluation.__post_init__ | isinstance
L325-325 | ActuatorEvaluation.__post_init__ | TypeError
L326-326 | ActuatorEvaluation.__post_init__ | tuple
L327-327 | ActuatorEvaluation.__post_init__ | len
L327-327 | ActuatorEvaluation.__post_init__ | any
L327-327 | ActuatorEvaluation.__post_init__ | type
L328-328 | ActuatorEvaluation.__post_init__ | TypeError
L329-329 | ActuatorEvaluation.__post_init__ | object.__setattr__
L331-331 | ActuatorEvaluation.__post_init__ | ValueError
L304-304 | ActuatorEvaluation | dataclass
L371-371 | LaggedActuators.__post_init__ | isinstance
L372-372 | LaggedActuators.__post_init__ | TypeError
L375-375 | LaggedActuators.evaluate | float
L376-376 | LaggedActuators.evaluate | np.isfinite
L377-377 | LaggedActuators.evaluate | ValueError
L379-379 | LaggedActuators.evaluate | params.validate_state
L380-380 | LaggedActuators.evaluate | params.bound_command
L381-381 | LaggedActuators.evaluate | params.effective_gimbal_rate_rad_s
L382-382 | LaggedActuators.evaluate | np.errstate
L384-384 | LaggedActuators.evaluate | np.asarray
L385-385 | LaggedActuators.evaluate | np.asarray
L386-386 | LaggedActuators.evaluate | np.asarray
L387-390 | LaggedActuators.evaluate | np.clip
L388-388 | LaggedActuators.evaluate | np.asarray
L389-389 | LaggedActuators.evaluate | np.asarray
L391-394 | LaggedActuators.evaluate | _common_progress_rate
L395-398 | LaggedActuators.evaluate | _common_progress_rate
L399-404 | LaggedActuators.evaluate | _output_acceleration
L405-407 | LaggedActuators.evaluate | finite_array
L408-408 | LaggedActuators.evaluate | np.asarray
L409-409 | LaggedActuators.evaluate | np.any
L409-409 | LaggedActuators.evaluate | np.abs
L410-410 | LaggedActuators.evaluate | ArithmeticError
L411-411 | LaggedActuators.evaluate | np.asarray
L412-420 | LaggedActuators.evaluate | AssemblyKinematics
L417-417 | LaggedActuators.evaluate | np.asarray
L423-429 | LaggedActuators.evaluate | ActuatorEvaluation
L424-424 | LaggedActuators.evaluate | np.concatenate
L427-427 | LaggedActuators.evaluate | tuple
L427-427 | LaggedActuators.evaluate | zip
L347-347 | LaggedActuators | dataclass

## recovered_previous_run/repaired_hopper_r12/propulsion/propeller.py
SHA256 ce7be67ceae3866ecf402ee03b7812c3ea1e39c216ca5d412322af53d586ae3b

Import L31: from __future__ import annotations
Import L33: from dataclasses import dataclass
Import L35: import numpy as np
Import L37: from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
Import L38: from ..helpers.math import finite_array, gimbal_to_body, quaternion_to_dcm
Import L39: from ..simulation.state import State
Import L40: from .propulsion import AppliedLoad, CoaxialConditions, CoaxialPerformance, CoaxialPerformanceMap, Propulsion, PropulsionEvaluation
L54-54 | _text | isinstance
L54-54 | _text | value.strip
L55-55 | _text | ValueError
L60-60 | _kinematics | isinstance
L61-61 | _kinematics | TypeError
L108-108 | CoaxialGeometry.__post_init__ | finite_array
L108-108 | CoaxialGeometry.__post_init__ | getattr
L109-109 | CoaxialGeometry.__post_init__ | object.__setattr__
L109-109 | CoaxialGeometry.__post_init__ | tuple
L109-109 | CoaxialGeometry.__post_init__ | float
L110-113 | CoaxialGeometry.__post_init__ | finite_array
L114-114 | CoaxialGeometry.__post_init__ | tuple
L115-115 | CoaxialGeometry.__post_init__ | len
L115-115 | CoaxialGeometry.__post_init__ | any
L115-115 | CoaxialGeometry.__post_init__ | type
L116-116 | CoaxialGeometry.__post_init__ | set
L117-117 | CoaxialGeometry.__post_init__ | ValueError
L118-118 | CoaxialGeometry.__post_init__ | np.errstate
L121-121 | CoaxialGeometry.__post_init__ | ValueError
L123-123 | CoaxialGeometry.__post_init__ | float
L123-123 | CoaxialGeometry.__post_init__ | np.max
L123-123 | CoaxialGeometry.__post_init__ | np.abs
L124-124 | CoaxialGeometry.__post_init__ | np.max
L124-124 | CoaxialGeometry.__post_init__ | np.abs
L124-124 | CoaxialGeometry.__post_init__ | np.finfo
L125-125 | CoaxialGeometry.__post_init__ | ValueError
L127-127 | CoaxialGeometry.__post_init__ | ValueError
L128-128 | CoaxialGeometry.__post_init__ | _text
L129-131 | CoaxialGeometry.__post_init__ | object.__setattr__
L129-131 | CoaxialGeometry.__post_init__ | tuple
L130-130 | CoaxialGeometry.__post_init__ | tuple
L130-130 | CoaxialGeometry.__post_init__ | float
L132-132 | CoaxialGeometry.__post_init__ | object.__setattr__
L142-142 | CoaxialGeometry.outer_rotation_BA | _kinematics
L143-143 | CoaxialGeometry.outer_rotation_BA | gimbal_to_body
L147-147 | CoaxialGeometry.rotation_BM | _kinematics
L149-149 | CoaxialGeometry.rotation_BM | gimbal_to_body
L153-153 | CoaxialGeometry.joint_origins_B0_m | self.outer_rotation_BA
L154-154 | CoaxialGeometry.joint_origins_B0_m | np.asarray
L155-155 | CoaxialGeometry.joint_origins_B0_m | np.errstate
L156-156 | CoaxialGeometry.joint_origins_B0_m | np.asarray
L157-157 | CoaxialGeometry.joint_origins_B0_m | finite_array
L157-157 | CoaxialGeometry.joint_origins_B0_m | np.vstack
L161-161 | CoaxialGeometry.application_points_B0_m | self.joint_origins_B0_m
L162-162 | CoaxialGeometry.application_points_B0_m | self.rotation_BM
L163-163 | CoaxialGeometry.application_points_B0_m | np.errstate
L165-165 | CoaxialGeometry.application_points_B0_m | np.asarray
L167-167 | CoaxialGeometry.application_points_B0_m | finite_array
L185-185 | CoaxialGeometry.application_point_rates_B0_m_s | _kinematics
L188-188 | CoaxialGeometry.application_point_rates_B0_m_s | self.outer_rotation_BA
L189-189 | CoaxialGeometry.application_point_rates_B0_m_s | self.rotation_BM
L190-190 | CoaxialGeometry.application_point_rates_B0_m_s | np.errstate
L191-191 | CoaxialGeometry.application_point_rates_B0_m_s | np.asarray
L193-193 | CoaxialGeometry.application_point_rates_B0_m_s | np.asarray
L195-195 | CoaxialGeometry.application_point_rates_B0_m_s | np.array
L196-199 | CoaxialGeometry.application_point_rates_B0_m_s | np.array
L197-197 | CoaxialGeometry.application_point_rates_B0_m_s | np.cos
L198-198 | CoaxialGeometry.application_point_rates_B0_m_s | np.sin
L200-200 | CoaxialGeometry.application_point_rates_B0_m_s | np.cross
L201-201 | CoaxialGeometry.application_point_rates_B0_m_s | np.cross
L202-202 | CoaxialGeometry.application_point_rates_B0_m_s | finite_array
L211-211 | CoaxialGeometry.validate_spin_kinematics | _kinematics
L212-212 | CoaxialGeometry.validate_spin_kinematics | np.asarray
L213-213 | CoaxialGeometry.validate_spin_kinematics | np.asarray
L214-214 | CoaxialGeometry.validate_spin_kinematics | np.asarray
L215-215 | CoaxialGeometry.validate_spin_kinematics | np.any
L216-216 | CoaxialGeometry.validate_spin_kinematics | ValueError
L217-217 | CoaxialGeometry.validate_spin_kinematics | np.any
L218-218 | CoaxialGeometry.validate_spin_kinematics | ValueError
L65-65 | CoaxialGeometry | dataclass
L245-245 | Propellor.__post_init__ | isinstance
L246-246 | Propellor.__post_init__ | TypeError
L247-247 | Propellor.__post_init__ | callable
L247-247 | Propellor.__post_init__ | getattr
L248-248 | Propellor.__post_init__ | TypeError
L267-267 | Propellor.hub_velocities_relative_air_M_m_s | isinstance
L268-268 | Propellor.hub_velocities_relative_air_M_m_s | TypeError
L269-269 | Propellor.hub_velocities_relative_air_M_m_s | isinstance
L270-270 | Propellor.hub_velocities_relative_air_M_m_s | TypeError
L272-272 | Propellor.hub_velocities_relative_air_M_m_s | ValueError
L273-273 | Propellor.hub_velocities_relative_air_M_m_s | self.geometry.validate_spin_kinematics
L274-274 | Propellor.hub_velocities_relative_air_M_m_s | finite_array
L275-275 | Propellor.hub_velocities_relative_air_M_m_s | self.geometry.rotation_BM
L276-276 | Propellor.hub_velocities_relative_air_M_m_s | quaternion_to_dcm
L277-277 | Propellor.hub_velocities_relative_air_M_m_s | self.geometry.application_points_B0_m
L278-278 | Propellor.hub_velocities_relative_air_M_m_s | self.geometry.application_point_rates_B0_m_s
L280-280 | Propellor.hub_velocities_relative_air_M_m_s | range
L281-281 | Propellor.hub_velocities_relative_air_M_m_s | mass_properties.moment_arm_m
L282-282 | Propellor.hub_velocities_relative_air_M_m_s | np.errstate
L286-286 | Propellor.hub_velocities_relative_air_M_m_s | np.cross
L288-288 | Propellor.hub_velocities_relative_air_M_m_s | np.asarray
L290-290 | Propellor.hub_velocities_relative_air_M_m_s | velocities.append
L291-291 | Propellor.hub_velocities_relative_air_M_m_s | finite_array
L300-300 | Propellor.evaluate | float
L301-301 | Propellor.evaluate | np.isfinite
L302-302 | Propellor.evaluate | ValueError
L303-303 | Propellor.evaluate | self.geometry.validate_spin_kinematics
L304-304 | Propellor.evaluate | isinstance
L305-305 | Propellor.evaluate | TypeError
L307-307 | Propellor.evaluate | ValueError
L309-309 | Propellor.evaluate | abs
L310-310 | Propellor.evaluate | ValueError
L311-313 | Propellor.evaluate | self.performance_map.evaluate
L314-314 | Propellor.evaluate | isinstance
L315-315 | Propellor.evaluate | TypeError
L317-317 | Propellor.evaluate | ValueError
L318-318 | Propellor.evaluate | self.geometry.rotation_BM
L319-319 | Propellor.evaluate | self.geometry.application_points_B0_m
L321-321 | Propellor.evaluate | enumerate
L324-324 | Propellor.evaluate | np.errstate
L325-325 | Propellor.evaluate | np.array
L326-328 | Propellor.evaluate | np.array
L329-337 | Propellor.evaluate | loads.append
L329-337 | Propellor.evaluate | AppliedLoad
L338-344 | Propellor.evaluate | PropulsionEvaluation
L340-340 | Propellor.evaluate | tuple
L221-221 | Propellor | dataclass

## recovered_previous_run/repaired_hopper_r12/propulsion/propulsion.py
SHA256 d860528b277893bbfe59527b7fcc2017955cc66681d3994fb66744a8006271de

Import L28: from __future__ import annotations
Import L30: from abc import ABC, abstractmethod
Import L31: from dataclasses import dataclass
Import L32: from typing import Protocol
Import L34: import numpy as np
Import L36: from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
Import L37: from ..helpers.math import finite_array
L55-55 | _text | isinstance
L55-55 | _text | value.strip
L56-56 | _text | ValueError
L62-62 | _scope | ValueError
L67-67 | _scalar | float
L68-68 | _scalar | np.isfinite
L69-69 | _scalar | ValueError
L74-74 | _vector | finite_array
L75-75 | _vector | np.any
L76-76 | _vector | ValueError
L77-77 | _vector | np.any
L78-78 | _vector | ValueError
L79-79 | _vector | tuple
L79-79 | _vector | float
L83-83 | _limitations | isinstance
L84-84 | _limitations | TypeError
L85-85 | _limitations | tuple
L85-85 | _limitations | _text
L87-87 | _limitations | ValueError
L116-116 | AppliedLoad.__post_init__ | object.__setattr__
L116-116 | AppliedLoad.__post_init__ | _vector
L116-116 | AppliedLoad.__post_init__ | getattr
L117-117 | AppliedLoad.__post_init__ | _scope
L118-118 | AppliedLoad.__post_init__ | _text
L91-91 | AppliedLoad | dataclass
L137-137 | ExternalWrench.__post_init__ | object.__setattr__
L137-137 | ExternalWrench.__post_init__ | _vector
L137-137 | ExternalWrench.__post_init__ | getattr
L138-138 | ExternalWrench.__post_init__ | _scope
L139-139 | ExternalWrench.__post_init__ | _text
L121-121 | ExternalWrench | dataclass
L149-149 | resolve_applied_loads | isinstance
L150-150 | resolve_applied_loads | TypeError
L151-151 | resolve_applied_loads | _text
L152-152 | resolve_applied_loads | np.zeros
L153-153 | resolve_applied_loads | np.zeros
L154-154 | resolve_applied_loads | tuple
L155-155 | resolve_applied_loads | isinstance
L156-156 | resolve_applied_loads | TypeError
L158-158 | resolve_applied_loads | ValueError
L159-159 | resolve_applied_loads | np.asarray
L160-160 | resolve_applied_loads | mass_properties.moment_arm_m
L161-161 | resolve_applied_loads | np.errstate
L163-163 | resolve_applied_loads | np.cross
L163-163 | resolve_applied_loads | np.asarray
L164-169 | resolve_applied_loads | ExternalWrench
L213-215 | CoaxialConditions.__post_init__ | object.__setattr__
L213-215 | CoaxialConditions.__post_init__ | _scalar
L214-214 | CoaxialConditions.__post_init__ | getattr
L216-216 | CoaxialConditions.__post_init__ | _scalar
L218-218 | CoaxialConditions.__post_init__ | ValueError
L219-219 | CoaxialConditions.__post_init__ | object.__setattr__
L220-223 | CoaxialConditions.__post_init__ | finite_array
L224-225 | CoaxialConditions.__post_init__ | object.__setattr__
L225-225 | CoaxialConditions.__post_init__ | tuple
L225-225 | CoaxialConditions.__post_init__ | tuple
L225-225 | CoaxialConditions.__post_init__ | float
L227-229 | CoaxialConditions.__post_init__ | object.__setattr__
L227-229 | CoaxialConditions.__post_init__ | _vector
L228-228 | CoaxialConditions.__post_init__ | getattr
L230-230 | CoaxialConditions.__post_init__ | _scope
L231-231 | CoaxialConditions.__post_init__ | _text
L172-172 | CoaxialConditions | dataclass
L271-271 | CoaxialPerformance.__post_init__ | isinstance
L272-272 | CoaxialPerformance.__post_init__ | TypeError
L277-279 | CoaxialPerformance.__post_init__ | object.__setattr__
L277-279 | CoaxialPerformance.__post_init__ | _vector
L278-278 | CoaxialPerformance.__post_init__ | getattr
L283-283 | CoaxialPerformance.__post_init__ | ValueError
L285-285 | CoaxialPerformance.__post_init__ | tuple
L286-286 | CoaxialPerformance.__post_init__ | isinstance
L286-286 | CoaxialPerformance.__post_init__ | len
L287-287 | CoaxialPerformance.__post_init__ | TypeError
L289-289 | CoaxialPerformance.__post_init__ | _text
L291-291 | CoaxialPerformance.__post_init__ | ValueError
L292-292 | CoaxialPerformance.__post_init__ | type
L293-293 | CoaxialPerformance.__post_init__ | TypeError
L295-295 | CoaxialPerformance.__post_init__ | set
L295-295 | CoaxialPerformance.__post_init__ | set
L296-296 | CoaxialPerformance.__post_init__ | ValueError
L297-299 | CoaxialPerformance.__post_init__ | object.__setattr__
L297-299 | CoaxialPerformance.__post_init__ | tuple
L300-300 | CoaxialPerformance.__post_init__ | _text
L301-301 | CoaxialPerformance.__post_init__ | object.__setattr__
L301-301 | CoaxialPerformance.__post_init__ | _limitations
L313-313 | CoaxialPerformance.reported_admissibility | tuple
L314-314 | CoaxialPerformance.reported_admissibility | any
L316-316 | CoaxialPerformance.reported_admissibility | any
L323-323 | CoaxialPerformance.propulsion_bus_power_W | sum
L324-324 | CoaxialPerformance.propulsion_bus_power_W | _scalar
L234-234 | CoaxialPerformance | dataclass
L362-362 | PropulsionEvaluation.__post_init__ | isinstance
L363-363 | PropulsionEvaluation.__post_init__ | TypeError
L364-364 | PropulsionEvaluation.__post_init__ | tuple
L365-365 | PropulsionEvaluation.__post_init__ | len
L365-365 | PropulsionEvaluation.__post_init__ | all
L365-365 | PropulsionEvaluation.__post_init__ | isinstance
L366-366 | PropulsionEvaluation.__post_init__ | ValueError
L367-367 | PropulsionEvaluation.__post_init__ | any
L368-368 | PropulsionEvaluation.__post_init__ | ValueError
L369-369 | PropulsionEvaluation.__post_init__ | object.__setattr__
L370-370 | PropulsionEvaluation.__post_init__ | _text
L374-378 | PropulsionEvaluation.wrench_about_cg | resolve_applied_loads
L348-348 | PropulsionEvaluation | dataclass

## recovered_previous_run/repaired_hopper_r12/simulation/environment.py
SHA256 ba795b5d1d5344a1ecf5b2b5cc122255234d5ff394fb0dc41ee3366196aac03c

Import L22: from __future__ import annotations
Import L24: from dataclasses import dataclass
Import L25: from typing import Protocol
Import L27: import numpy as np
Import L29: from ..chassis.hopper import AssemblyKinematics, MassProperties, MODEL_SCOPES
Import L30: from ..helpers.math import finite_array
Import L31: from ..propulsion.propulsion import AppliedLoad, CoaxialConditions
Import L32: from .state import State
L39-39 | _text | isinstance
L39-39 | _text | value.strip
L40-40 | _text | ValueError
L45-45 | _scalar | float
L46-46 | _scalar | np.isfinite
L47-47 | _scalar | ValueError
L49-49 | _scalar | ValueError
L51-51 | _scalar | ValueError
L116-116 | EnvironmentSample.__post_init__ | ValueError
L117-117 | EnvironmentSample.__post_init__ | _scalar
L119-119 | EnvironmentSample.__post_init__ | ValueError
L120-120 | EnvironmentSample.__post_init__ | object.__setattr__
L122-124 | EnvironmentSample.__post_init__ | object.__setattr__
L122-124 | EnvironmentSample.__post_init__ | _scalar
L123-123 | EnvironmentSample.__post_init__ | getattr
L125-128 | EnvironmentSample.__post_init__ | object.__setattr__
L125-128 | EnvironmentSample.__post_init__ | _scalar
L129-129 | EnvironmentSample.__post_init__ | _scalar
L131-131 | EnvironmentSample.__post_init__ | ValueError
L132-132 | EnvironmentSample.__post_init__ | object.__setattr__
L134-134 | EnvironmentSample.__post_init__ | finite_array
L134-134 | EnvironmentSample.__post_init__ | getattr
L135-137 | EnvironmentSample.__post_init__ | object.__setattr__
L135-137 | EnvironmentSample.__post_init__ | tuple
L136-136 | EnvironmentSample.__post_init__ | tuple
L136-136 | EnvironmentSample.__post_init__ | float
L139-139 | EnvironmentSample.__post_init__ | finite_array
L139-139 | EnvironmentSample.__post_init__ | getattr
L140-140 | EnvironmentSample.__post_init__ | np.any
L141-141 | EnvironmentSample.__post_init__ | ValueError
L142-142 | EnvironmentSample.__post_init__ | object.__setattr__
L142-142 | EnvironmentSample.__post_init__ | tuple
L142-142 | EnvironmentSample.__post_init__ | float
L143-143 | EnvironmentSample.__post_init__ | tuple
L144-144 | EnvironmentSample.__post_init__ | all
L144-144 | EnvironmentSample.__post_init__ | isinstance
L145-145 | EnvironmentSample.__post_init__ | TypeError
L146-146 | EnvironmentSample.__post_init__ | any
L147-147 | EnvironmentSample.__post_init__ | ValueError
L148-148 | EnvironmentSample.__post_init__ | object.__setattr__
L150-150 | EnvironmentSample.__post_init__ | _text
L150-150 | EnvironmentSample.__post_init__ | getattr
L151-151 | EnvironmentSample.__post_init__ | isinstance
L152-152 | EnvironmentSample.__post_init__ | TypeError
L153-153 | EnvironmentSample.__post_init__ | tuple
L153-153 | EnvironmentSample.__post_init__ | _text
L155-155 | EnvironmentSample.__post_init__ | ValueError
L156-156 | EnvironmentSample.__post_init__ | object.__setattr__
L172-183 | EnvironmentSample.coaxial_conditions | CoaxialConditions
L192-192 | EnvironmentSample.total_bus_current_A | finite_array
L193-193 | EnvironmentSample.total_bus_current_A | np.any
L194-194 | EnvironmentSample.total_bus_current_A | ValueError
L195-195 | EnvironmentSample.total_bus_current_A | np.errstate
L196-196 | EnvironmentSample.total_bus_current_A | float
L196-196 | EnvironmentSample.total_bus_current_A | np.sum
L197-197 | EnvironmentSample.total_bus_current_A | _scalar
L205-205 | EnvironmentSample.total_bus_power_W | self.total_bus_current_A
L206-206 | EnvironmentSample.total_bus_power_W | _scalar
L55-55 | EnvironmentSample | dataclass

## recovered_previous_run/repaired_hopper_r12/simulation/simulation.py
SHA256 a186c50ab7c5500e7da14bb5c98a5c2772ff97d63645558be3cfdc3b6e5ca1a8

Import L34: from __future__ import annotations
Import L36: from dataclasses import dataclass
Import L38: import numpy as np
Import L39: from scipy.integrate import solve_ivp
Import L41: from ..chassis.hopper import Hopper, MassProperties
Import L42: from ..helpers.math import finite_array, quaternion_derivative, quaternion_to_dcm
Import L43: from ..propulsion.actuators import ACTUATOR_COMPONENTS, ACTUATOR_STATE_SCHEMA, ACTUATOR_STATE_SIZE, ACTUATOR_UNITS, ActuatorEvaluation, ActuatorModel, ActuatorState, HeldCommand, LaggedActuators
Import L54: from ..propulsion.propeller import Propellor
Import L55: from ..propulsion.propulsion import ExternalWrench, PropulsionEvaluation, resolve_applied_loads
Import L60: from .environment import EnvironmentProvider, EnvironmentSample
Import L61: from .state import STATE_COMPONENTS, STATE_SIZE, STATE_UNITS, STATE_VECTOR_SCHEMA, State
L86-86 | IntegrationFailure.__init__ | Call(func=Name(id='super', ctx=Load())).__init__
L86-86 | IntegrationFailure.__init__ | super
L91-91 | _finite_scalar | float
L92-92 | _finite_scalar | np.isfinite
L93-93 | _finite_scalar | ValueError
L103-103 | pack_state | isinstance
L103-103 | pack_state | isinstance
L104-104 | pack_state | TypeError
L105-105 | pack_state | np.concatenate
L105-105 | pack_state | state.as_vector
L105-105 | pack_state | actuator_state.as_vector
L111-111 | unpack_state | ValueError
L112-112 | unpack_state | finite_array
L114-114 | unpack_state | State.from_vector
L115-115 | unpack_state | ActuatorState.from_vector
L139-139 | PlantEvaluation.__post_init__ | finite_array
L140-140 | PlantEvaluation.__post_init__ | object.__setattr__
L140-140 | PlantEvaluation.__post_init__ | tuple
L140-140 | PlantEvaluation.__post_init__ | float
L147-147 | PlantEvaluation.__post_init__ | isinstance
L147-147 | PlantEvaluation.__post_init__ | getattr
L148-148 | PlantEvaluation.__post_init__ | TypeError
L152-154 | PlantEvaluation.total_bus_current_A | self.environment.total_bus_current_A
L158-160 | PlantEvaluation.total_bus_power_W | self.environment.total_bus_power_W
L119-119 | PlantEvaluation | dataclass
L195-195 | Simulation.__post_init__ | isinstance
L196-196 | Simulation.__post_init__ | TypeError
L197-197 | Simulation.__post_init__ | isinstance
L198-198 | Simulation.__post_init__ | TypeError
L199-199 | Simulation.__post_init__ | isinstance
L200-200 | Simulation.__post_init__ | TypeError
L201-201 | Simulation.__post_init__ | isinstance
L202-202 | Simulation.__post_init__ | TypeError
L205-205 | Simulation.__post_init__ | ValueError
L206-206 | Simulation.__post_init__ | callable
L206-206 | Simulation.__post_init__ | getattr
L207-207 | Simulation.__post_init__ | TypeError
L208-208 | Simulation.__post_init__ | callable
L208-208 | Simulation.__post_init__ | getattr
L209-209 | Simulation.__post_init__ | TypeError
L211-211 | Simulation.__post_init__ | ValueError
L212-215 | Simulation.__post_init__ | _finite_scalar
L217-217 | Simulation.__post_init__ | ValueError
L218-218 | Simulation.__post_init__ | object.__setattr__
L219-219 | Simulation.__post_init__ | float
L219-219 | Simulation.__post_init__ | np.linalg.norm
L220-220 | Simulation.__post_init__ | np.isfinite
L220-220 | Simulation.__post_init__ | abs
L221-221 | Simulation.__post_init__ | ValueError
L222-222 | Simulation.__post_init__ | isinstance
L225-225 | Simulation.__post_init__ | ValueError
L226-226 | Simulation.__post_init__ | parameters.validate_state
L230-230 | Simulation.initial_vector | pack_state
L240-240 | Simulation.evaluate | _finite_scalar
L241-241 | Simulation.evaluate | isinstance
L242-242 | Simulation.evaluate | TypeError
L243-243 | Simulation.evaluate | unpack_state
L244-246 | Simulation.evaluate | self.actuator_model.evaluate
L247-247 | Simulation.evaluate | isinstance
L248-248 | Simulation.evaluate | TypeError
L250-250 | Simulation.evaluate | ValueError
L252-252 | Simulation.evaluate | np.asarray
L259-259 | Simulation.evaluate | np.asarray
L261-261 | Simulation.evaluate | np.asarray
L263-263 | Simulation.evaluate | any
L263-263 | Simulation.evaluate | np.array_equal
L264-264 | Simulation.evaluate | ValueError
L265-265 | Simulation.evaluate | self.propulsion.geometry.validate_spin_kinematics
L266-266 | Simulation.evaluate | self.hopper.mass_properties
L267-267 | Simulation.evaluate | quaternion_to_dcm
L268-268 | Simulation.evaluate | self.propulsion.geometry.application_points_B0_m
L269-269 | Simulation.evaluate | np.errstate
L270-270 | Simulation.evaluate | np.asarray
L272-272 | Simulation.evaluate | finite_array
L273-276 | Simulation.evaluate | self.environment_provider.sample
L275-275 | Simulation.evaluate | hub_positions.copy
L277-277 | Simulation.evaluate | isinstance
L278-278 | Simulation.evaluate | TypeError
L280-280 | Simulation.evaluate | ValueError
L281-281 | Simulation.evaluate | np.array_equal
L282-282 | Simulation.evaluate | ValueError
L283-286 | Simulation.evaluate | self.propulsion.hub_velocities_relative_air_M_m_s
L287-290 | Simulation.evaluate | environment.coaxial_conditions
L291-293 | Simulation.evaluate | self.propulsion.evaluate
L298-298 | Simulation.evaluate | ModelDomainError
L298-298 | Simulation.evaluate | Constant(value=', ').join
L300-300 | Simulation.evaluate | ModelDomainError
L300-300 | Simulation.evaluate | Constant(value=', ').join
L301-306 | Simulation.evaluate | resolve_applied_loads
L307-307 | Simulation.evaluate | np.errstate
L309-309 | Simulation.evaluate | np.asarray
L310-310 | Simulation.evaluate | np.array
L316-319 | Simulation.evaluate | mass.angular_acceleration_B_rad_s2
L320-326 | Simulation.evaluate | np.concatenate
L323-323 | Simulation.evaluate | quaternion_derivative
L325-325 | Simulation.evaluate | np.asarray
L327-331 | Simulation.evaluate | PlantEvaluation
L335-337 | Simulation.trajectory_ode | np.asarray
L335-337 | Simulation.trajectory_ode | self.evaluate
L369-369 | Simulation.solve_ode | finite_array
L371-371 | Simulation.solve_ode | ValueError
L372-372 | Simulation.solve_ode | isinstance
L373-373 | Simulation.solve_ode | TypeError
L375-375 | Simulation.solve_ode | ValueError
L376-376 | Simulation.solve_ode | _finite_scalar
L378-378 | Simulation.solve_ode | ValueError
L379-379 | Simulation.solve_ode | finite_array
L380-380 | Simulation.solve_ode | np.any
L381-381 | Simulation.solve_ode | ValueError
L382-382 | Simulation.solve_ode | _finite_scalar
L383-383 | Simulation.solve_ode | type
L383-383 | Simulation.solve_ode | type
L384-384 | Simulation.solve_ode | TypeError
L387-387 | Simulation.solve_ode | np.array
L389-389 | Simulation.solve_ode | np.all
L389-389 | Simulation.solve_ode | np.isfinite
L390-390 | Simulation.solve_ode | np.all
L390-390 | Simulation.solve_ode | np.diff
L392-392 | Simulation.solve_ode | ValueError
L393-393 | Simulation.solve_ode | callable
L396-396 | Simulation.solve_ode | tuple
L397-397 | Simulation.solve_ode | all
L397-397 | Simulation.solve_ode | callable
L398-398 | Simulation.solve_ode | TypeError
L399-399 | Simulation.solve_ode | self.initial_vector
L400-400 | Simulation.solve_ode | self.evaluate
L403-403 | Simulation.solve_ode.held_rhs | self.trajectory_ode
L405-410 | Simulation.solve_ode | solve_ivp
L406-406 | Simulation.solve_ode | tuple
L406-406 | Simulation.solve_ode | float
L438-438 | Simulation.solve_ode | IntegrationFailure
L438-438 | Simulation.solve_ode | str
L163-163 | Simulation | dataclass

## recovered_previous_run/repaired_hopper_r12/simulation/state.py
SHA256 b62a1a4fcc70a4a88e07f77996e955a64184891ce614957c85ccb7d63e90f294

Import L27: from __future__ import annotations
Import L29: from dataclasses import dataclass, field
Import L31: import numpy as np
Import L33: from ..helpers.math import euler_to_quaternion, finite_array, normalize_quaternion, quaternion_to_dcm
L70-70 | State | field
L74-74 | State.__init__ | finite_array
L75-75 | State.__init__ | finite_array
L76-76 | State.__init__ | finite_array
L77-77 | State.__init__ | finite_array
L78-78 | State.__init__ | np.any
L79-79 | State.__init__ | ValueError
L80-80 | State.__init__ | np.concatenate
L81-81 | State.__init__ | object.__setattr__
L81-81 | State.__init__ | Call(func=Attribute(value=Name(id='vector', ctx=Load()), attr='astype', ctx=Load()), args=[Attribute(value=Name(id='np', ctx=Load()), attr='float64', ctx=Load())]).tobytes
L81-81 | State.__init__ | vector.astype
L92-92 | State.from_vector | ValueError
L93-93 | State.from_vector | finite_array
L94-99 | State.from_vector | cls
L109-116 | State.from_euler | cls
L112-114 | State.from_euler | euler_to_quaternion
L127-127 | State.from_body_velocity | finite_array
L128-133 | State.from_body_velocity | cls
L130-130 | State.from_body_velocity | quaternion_to_dcm
L141-141 | State.as_vector | Call(func=Attribute(value=Name(id='np', ctx=Load()), attr='frombuffer', ctx=Load()), args=[Attribute(value=Name(id='self', ctx=Load()), attr='_data', ctx=Load())], keywords=[keyword(arg='dtype', value=Attribute(value=Name(id='np', ctx=Load(.copy
L141-141 | State.as_vector | np.frombuffer
L149-149 | State.unpack_state | tuple
L149-149 | State.unpack_state | float
L149-149 | State.unpack_state | self.as_vector
L153-153 | State.position_G_L_m | self.as_vector
L157-157 | State.velocity_G_L_m_s | self.as_vector
L161-161 | State.q_LB | self.as_vector
L165-165 | State.omega_B_rad_s | self.as_vector
L169-169 | State.velocity_G_B_m_s | quaternion_to_dcm
L177-182 | State.with_normalized_orientation | Call(func=Name(id='type', ctx=Load()), args=[Name(id='self', ctx=Load())])
L177-177 | State.with_normalized_orientation | type
L180-180 | State.with_normalized_orientation | normalize_quaternion
L52-52 | State | dataclass

