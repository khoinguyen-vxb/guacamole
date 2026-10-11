"""Artifact-bound state/frame/mass analytical checks for PDR-R12.

Run through Guacamole verify_command with repository='6dof_hopper':
  python -B software/pdr_r12_plant/verify_state_frames_mass_r12_01.py
Use sandbox workdir='.'. Include this checker, fixture configuration,
fixture providers and all eight imported plant-module artifact Refs in inputs.
Publish those artifacts before verification; file hashes are not Ref hashes.

Authorization: 66c7448f443f44ac9a016a1b384593a2 r1.
Audits: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 r1 and
PDR-R12-PLANT-CALLER-RECONCILIATION-02 r1.
Frames: f046cc4fe5294a6f9a61027529056f61 r1.

New caller audit: invokes named-radian State initialization, explicit vector
schemas, owned serialization, Simulation construction/initial_vector,
frame helpers, MassProperties angular balance and fixed-datum conversion.
It does not invoke solve_ode or modify existing implementation files.

Independent oracles use elementary axis matrices, component Hamilton algebra,
angular-momentum residuals and finite-difference datum velocities. Inputs and
numerical thresholds come from analytical_fixture_config_r12_01.json.
Synthetic invalid inputs are deliberate rejection fixtures, not vehicle data.

Only one VerificationResult JSON object is printed to stdout. Actual hashes,
measurements and exceptions go to stderr. No files are written by this program.
A scoped analytical pass is not propulsion, trajectory, vehicle or review
acceptance. Additional verification programs must cover the omitted areas.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import platform
import sys
import traceback
import warnings

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'analytical_fixture_config_r12_01.json'
MODULE_FILES = {
    'repaired_hopper_r12.helpers.math': 'repaired_hopper_r12/helpers/math.py',
    'repaired_hopper_r12.simulation.state': 'repaired_hopper_r12/simulation/state.py',
    'repaired_hopper_r12.chassis.hopper': 'repaired_hopper_r12/chassis/hopper.py',
    'repaired_hopper_r12.propulsion.propulsion': 'repaired_hopper_r12/propulsion/propulsion.py',
    'repaired_hopper_r12.propulsion.propeller': 'repaired_hopper_r12/propulsion/propeller.py',
    'repaired_hopper_r12.propulsion.actuators': 'repaired_hopper_r12/propulsion/actuators.py',
    'repaired_hopper_r12.simulation.environment': 'repaired_hopper_r12/simulation/environment.py',
    'repaired_hopper_r12.simulation.simulation': 'repaired_hopper_r12/simulation/simulation.py',
    'analytical_fixture_models_r12_01': 'analytical_fixture_models_r12_01.py',
}


def hashes():
    paths = list(MODULE_FILES.values()) + [CONFIG.name, Path(__file__).name]
    result = {}
    for relative in paths:
        path = ROOT / relative
        resolved = path.resolve()
        if ROOT not in resolved.parents or path.is_symlink():
            raise ValueError('Unexpected artifact path: ' + relative)
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class Recorder:
    def __init__(self):
        self.checks = {}
        self.measurements = {}
        self.exceptions = []

    def check(self, name, condition, details=None):
        if name in self.checks:
            raise ValueError('Duplicate check name: ' + name)
        self.checks[name] = bool(condition)
        if details is not None:
            self.measurements[name] = details

    def near(self, name, actual, expected, tolerance, unit):
        import numpy as np
        a = np.asarray(actual, dtype=float)
        b = np.asarray(expected, dtype=float)
        limit = float(tolerance)
        finite = bool(np.all(np.isfinite(a)) and np.all(np.isfinite(b)))
        if not np.isfinite(limit) or limit < 0.0:
            raise ValueError('Invalid checker tolerance: ' + name)
        if a.shape != b.shape or not finite:
            self.check(name, False, {
                'actual_shape': list(a.shape), 'expected_shape': list(b.shape),
                'finite': finite, 'unit': unit, 'tolerance': limit,
            })
            return
        error = float(np.max(np.abs(a - b))) if a.size else 0.0
        self.check(name, error <= limit, {
            'max_absolute_error': error, 'tolerance': limit, 'unit': unit,
            'actual': a.tolist(), 'expected': b.tolist(),
        })

    def rejects(self, name, operation, exception_type=ValueError):
        try:
            operation()
        except exception_type as error:
            self.check(name, True, {
                'deliberate_negative_fixture': True,
                'exception_type': type(error).__name__, 'message': str(error),
            })
        except Exception:
            self.check(name, False, {'unexpected_exception': True})
            raise
        else:
            self.check(name, False, {'expected_exception_not_raised': True})

    def group(self, name, operation):
        try:
            operation()
        except Exception as error:
            self.check(name + '.completed', False)
            self.exceptions.append({
                'group': name, 'type': type(error).__name__, 'message': str(error),
            })
            traceback.print_exc(file=sys.stderr)
        else:
            self.check(name + '.completed', True)


def run_checks(recorder, modules):
    import numpy as np
    math = modules['repaired_hopper_r12.helpers.math']
    states = modules['repaired_hopper_r12.simulation.state']
    chassis = modules['repaired_hopper_r12.chassis.hopper']
    actuator = modules['repaired_hopper_r12.propulsion.actuators']
    plant = modules['repaired_hopper_r12.simulation.simulation']
    fixtures = modules['analytical_fixture_models_r12_01']
    config = fixtures.load_fixture_config(CONFIG)
    original_config = deepcopy(config)
    tolerances = config['analytical_test_tolerances']
    vectors = config['test_vectors']
    State = states.State
    MassProperties = chassis.MassProperties
    initial, initial_actuator = fixtures.initial_snapshots(config)
    model = fixtures.build_fixture(
        config, initial_state=initial, initial_actuator_state=initial_actuator,
    )

    def cross(a, b):
        return np.array([
            a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0],
        ])

    def product(a, b):
        w, x, y, z = a
        v, i, j, k = b
        return np.array([
            w*v-x*i-y*j-z*k,
            w*i+x*v+y*k-z*j,
            w*j-x*k+y*v+z*i,
            w*k+x*j-y*i+z*v,
        ])

    def axis_matrix(axis, angle):
        c, s = np.cos(angle), np.sin(angle)
        if axis == 0:
            return np.array([[1,0,0],[0,c,-s],[0,s,c]], dtype=float)
        if axis == 1:
            return np.array([[c,0,s],[0,1,0],[-s,0,c]], dtype=float)
        return np.array([[c,-s,0],[s,c,0],[0,0,1]], dtype=float)

    def euler_matrix(angles):
        roll, pitch, yaw = angles
        return axis_matrix(2, yaw) @ axis_matrix(1, pitch) @ axis_matrix(0, roll)

    def euler_quaternion(angles):
        roll, pitch, yaw = np.asarray(angles) / 2.0
        qx = [np.cos(roll), np.sin(roll), 0, 0]
        qy = [np.cos(pitch), 0, np.sin(pitch), 0]
        qz = [np.cos(yaw), 0, 0, np.sin(yaw)]
        return product(product(qz, qy), qx)

    def state_checks():
        v = vectors['nonzero_initialization']
        expected_q = euler_quaternion([v['roll_rad'], v['pitch_rad'], v['yaw_rad']])
        recorder.near('state.euler_initialization', initial.q_LB, expected_q,
                      tolerances['rotation_matrix_max_absolute'], '1')
        expected = np.concatenate((
            v['position_G_L_m'], v['velocity_G_L_m_s'], initial.q_LB,
            v['omega_B_rad_s'], v['rotor_speed_magnitude_rad_s'],
            v['demand_filter_gimbal_rad'], v['actual_gimbal_rad'],
        ))
        recorder.near('state.all_initial_components', model.initial_vector(), expected,
                      tolerances['state_roundtrip_absolute'], 'mixed SI; PLANT_UNITS')
        decoded = plant.unpack_state(expected, schema=plant.PLANT_STATE_SCHEMA)
        recorder.near('state.plant_roundtrip', plant.pack_state(*decoded), expected,
                      tolerances['state_roundtrip_absolute'], 'mixed SI; PLANT_UNITS')
        source = initial.as_vector()
        saved = source.copy()
        owned = State.from_vector(source, schema=states.STATE_VECTOR_SCHEMA)
        source[:] = 0.0
        returned = owned.as_vector()
        returned[:] = 0.0
        position = owned.position_G_L_m
        position[:] = 0.0
        recorder.near('state.owned_input_and_outputs', owned.as_vector(), saved,
                      0.0, 'mixed SI; STATE_UNITS')
        copy = model.initial_vector()
        copy[:] = 0.0
        recorder.near('state.simulation_initial_copy', model.initial_vector(), expected,
                      0.0, 'mixed SI; PLANT_UNITS')
        raw = saved.copy()
        raw[6:10] *= vectors['rotation_identities']['nonunit_quaternion_scale']
        nonunit = State.from_vector(raw, schema=states.STATE_VECTOR_SCHEMA)
        recorder.near('state.raw_norm_error_preserved', nonunit.as_vector(), raw,
                      0.0, 'mixed SI; STATE_UNITS')
        recorder.rejects('state.nonunit_initial_solver_boundary',
                         lambda: replace(model, initial_state=nonunit))
        recorder.rejects('state.ambiguous_schema',
                         lambda: State.from_vector(saved, schema='legacy'))
        recorder.rejects('state.wrong_shape',
                         lambda: State.from_vector(saved[:-1], schema=states.STATE_VECTOR_SCHEMA))
        invalid = saved.copy()
        invalid[6:10] = 0.0
        recorder.rejects('state.zero_quaternion',
                         lambda: State.from_vector(invalid, schema=states.STATE_VECTOR_SCHEMA))
        invalid_nan = saved.copy()
        invalid_nan[0] = float('nan')
        recorder.rejects('state.nonfinite',
                         lambda: State.from_vector(invalid_nan, schema=states.STATE_VECTOR_SCHEMA))
        body_velocity = np.array(v['velocity_G_L_m_s'])
        rotated = State.from_body_velocity(
            position_G_L_m=v['position_G_L_m'], velocity_G_B_m_s=body_velocity,
            q_LB=expected_q, omega_B_rad_s=v['omega_B_rad_s'],
        )
        R = euler_matrix([v['roll_rad'], v['pitch_rad'], v['yaw_rad']])
        recorder.near('state.explicit_body_velocity_migration',
                      rotated.velocity_G_L_m_s, R @ body_velocity,
                      tolerances['kinematic_velocity_error_m_s'], 'm/s')
        recorder.near('state.inverse_velocity_resolution',
                      rotated.velocity_G_B_m_s(), body_velocity,
                      tolerances['kinematic_velocity_error_m_s'], 'm/s')
        actuator_values = initial_actuator.as_vector()
        rebuilt = actuator.ActuatorState.from_vector(
            actuator_values, schema=actuator.ACTUATOR_STATE_SCHEMA,
        )
        actuator_values[:] = 0.0
        recorder.near('state.actuator_ownership', rebuilt.as_vector(),
                      initial_actuator.as_vector(), 0.0, 'rad/s, rad/s, rad, rad, rad, rad')

    def frame_checks():
        v = vectors['rotation_identities']
        tol = tolerances['rotation_matrix_max_absolute']
        cases = [[0.0,0.0,0.0], v['noncommuting_euler_rad'], v['second_euler_rad']]
        for axis in range(3):
            angles = [0.0,0.0,0.0]
            angles[axis] = v['isolated_axis_angle_rad']
            cases.append(angles)
        for index, angles in enumerate(cases):
            q = math.euler_to_quaternion(
                roll_rad=angles[0], pitch_rad=angles[1], yaw_rad=angles[2],
            )
            R = math.quaternion_to_dcm(q)
            prefix = 'frame.case_' + str(index)
            recorder.near(prefix+'.quaternion', q, euler_quaternion(angles), tol, '1')
            recorder.near(prefix+'.direction', R, euler_matrix(angles), tol, '1')
            recorder.near(prefix+'.orthogonality', R.T @ R, np.eye(3), tol, '1')
            recorder.near(prefix+'.determinant', np.linalg.det(R), 1.0, tol, '1')
            recorder.near(prefix+'.double_cover', math.quaternion_to_dcm(-q), R, tol, '1')
        a = euler_quaternion(v['noncommuting_euler_rad'])
        b = euler_quaternion(v['second_euler_rad'])
        ab = math.hamilton_product(a, b)
        recorder.near('frame.hamilton_components', ab, product(a,b), tol, '1')
        recorder.near('frame.hamilton_composition', math.quaternion_to_dcm(ab),
                      euler_matrix(v['noncommuting_euler_rad'])
                      @ euler_matrix(v['second_euler_rad']), tol, '1')
        omega = np.array(vectors['nonzero_initialization']['omega_B_rad_s'])
        recorder.near('frame.quaternion_derivative',
                      math.quaternion_derivative(a, omega),
                      0.5*product(a, np.concatenate(([0.0], omega))), tol, '1/s')
        recorder.near('frame.norm_derivative_identity',
                      np.dot(a, math.quaternion_derivative(a, omega)), 0.0, tol, '1/s')
        for index, scale in enumerate(v['normalization_extreme_scales']):
            recorder.near('frame.scaled_normalization_'+str(index),
                          math.normalize_quaternion(a*scale), a, tol, '1')
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', DeprecationWarning)
            old_default = math.quarternion_to_dcm(a)
            old_transposed = math.quarternion_to_dcm(a, transpose=True)
        recorder.check('frame.deprecated_warning', len(caught) == 2)
        R = euler_matrix(v['noncommuting_euler_rad'])
        recorder.near('frame.legacy_default_direction', old_default, R.T, tol, '1')
        recorder.near('frame.legacy_transpose_direction', old_transposed, R, tol, '1')
        alpha, beta = vectors['offset_kinematics']['gimbal_rad']
        recorder.near('frame.carried_gimbal_order',
                      math.gimbal_to_body(alpha_rad=alpha, beta_rad=beta),
                      axis_matrix(0,alpha) @ axis_matrix(1,beta), tol, '1')

    def cad_checks():
        v = vectors['CAD_conversion']
        R = np.diag([1.0,-1.0,-1.0])
        point = np.array(v['point_C_mm'])
        origin = np.array(v['neutral_cg_C_mm'])
        converted = math.cad_point_to_body_datum_m(point, origin)
        recorder.near('cad.proper_rotation', math.cad_to_body_rotation(), R,
                      tolerances['rotation_matrix_max_absolute'], '1')
        recorder.near('cad.point_units_and_datum', converted, R @ (point-origin)/1000.0,
                      tolerances['kinematic_position_error_m'], 'm')
        recorder.near('cad.point_roundtrip',
                      math.body_datum_point_to_cad_mm(converted, origin), point,
                      tolerances['CAD_point_roundtrip_error_mm'], 'mm')
        geometric = np.array(v['geometric_inertia_C_mm5'])
        density = v['density_kg_m3']
        weighted_mm = geometric*density*1e-9
        weighted_si = weighted_mm*1e-6
        expected = R @ weighted_si @ R.T
        for unit, tensor, kwargs in (
            ('mm^5', geometric, {'density_kg_m3': density}),
            ('kg mm^2', weighted_mm, {}),
            ('kg m^2', weighted_si, {}),
        ):
            recorder.near('cad.inertia_'+unit,
                          math.cad_inertia_to_body_kg_m2(tensor, input_unit=unit, **kwargs),
                          expected, tolerances['inertia_conversion_error_kg_m2'], 'kg m^2')
        recorder.rejects('cad.missing_density',
                         lambda: math.cad_inertia_to_body_kg_m2(geometric, input_unit='mm^5'))
        recorder.rejects('cad.duplicate_density', lambda:
                         math.cad_inertia_to_body_kg_m2(weighted_si,
                             input_unit='kg m^2', density_kg_m3=density))

    def mass_checks():
        base = MassProperties(**config['mass_properties'])
        v = vectors['momentum_balance']
        sample = replace(base,
            inertia_rate_B_G_kg_m2_s=v['inertia_rate_B_G_kg_m2_s'],
            relative_momentum_B_kg_m2_s=v['relative_momentum_B_kg_m2_s'],
            relative_momentum_rate_B_N_m=v['relative_momentum_rate_B_N_m'],
            dynamics_mode=v['dynamics_mode'],
        )
        I = np.array(sample.inertia_B_G_kg_m2)
        Idot = np.array(sample.inertia_rate_B_G_kg_m2_s)
        omega = np.array(v['omega_B_rad_s'])
        h = np.array(sample.relative_momentum_B_kg_m2_s)
        hdot = np.array(sample.relative_momentum_rate_B_N_m)
        moment = np.array(v['external_moment_B_G_N_m'])
        acceleration = sample.angular_acceleration_B_rad_s2(
            omega_B_rad_s=omega, external_moment_B_G_N_m=moment,
        )
        residual = I @ acceleration + cross(omega, I @ omega+h) + Idot @ omega + hdot - moment
        recorder.near('mass.full_momentum_residual', residual, np.zeros(3),
                      tolerances['angular_momentum_residual_N_m'], 'N m')
        recorder.near('mass.total_angular_momentum',
                      sample.angular_momentum_B_kg_m2_s(omega), I @ omega+h,
                      tolerances['angular_momentum_residual_N_m'], 'kg m^2/s')
        recorder.check('mass.off_diagonal_fixture_exercised',
                       bool(np.any(I-np.diag(np.diag(I)))))
        point = np.array(vectors['external_point_load']['application_point_B0_m'])
        offset = np.array(vectors['offset_kinematics']['cg_B0_m'])
        shifted = replace(sample, cg_B0_m=offset)
        recorder.near('mass.actual_cg_relative_arm', shifted.moment_arm_m(point), point-offset,
                      tolerances['kinematic_position_error_m'], 'm')
        recorder.rejects('mass.rigid_fixture_rejects_internal_momentum',
                         lambda: replace(sample, dynamics_mode='rigid_body_fixture'))
        scale = float(np.trace(I)/3.0)
        recorder.rejects('mass.nonphysical_principal_moments',
                         lambda: replace(base, inertia_B_G_kg_m2=np.diag([scale,scale,3*scale])))
        recorder.rejects('mass.zero_installed_mass', lambda: replace(base, mass_kg=0.0))

    def datum_checks():
        v = vectors['offset_kinematics']
        p = initial.position_G_L_m
        velocity = initial.velocity_G_L_m_s
        omega = initial.omega_B_rad_s
        init = vectors['nonzero_initialization']
        R = euler_matrix([init['roll_rad'],init['pitch_rad'],init['yaw_rad']])
        cg = np.array(v['cg_B0_m'])
        cg_rate = np.array(v['cg_rate_B0_m_s'])
        step = float(v['finite_difference_time_step_s'])
        if not np.isfinite(step) or step <= 0.0:
            raise ValueError('Positive finite difference step required')
        magnitude = float(np.linalg.norm(omega))
        def position_at(dt):
            if magnitude == 0.0:
                increment = np.eye(3)
            else:
                axis = omega/magnitude
                K = np.array([[0,-axis[2],axis[1]],
                              [axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
                angle = magnitude*dt
                increment = np.eye(3)+np.sin(angle)*K+(1-np.cos(angle))*(K@K)
            return p+velocity*dt-R @ increment @ (cg+cg_rate*dt)
        actual_p, actual_v = math.fixed_datum_kinematics(
            position_G_L_m=p, velocity_G_L_m_s=velocity, q_LB=initial.q_LB,
            omega_B_rad_s=omega, offset_B0G_B_m=cg,
            offset_rate_B0G_B_m_s=cg_rate,
        )
        recorder.near('datum.position', actual_p, position_at(0.0),
                      tolerances['kinematic_position_error_m'], 'm')
        for index, dt in enumerate((step, step/2.0)):
            expected_v = (position_at(dt)-position_at(-dt))/(2*dt)
            recorder.near('datum.finite_difference_velocity_'+str(index),
                          actual_v, expected_v,
                          tolerances['kinematic_velocity_error_m_s'], 'm/s')
        recorder.near('datum.analytic_velocity', actual_v,
                      velocity-R @ (cross(omega,cg)+cg_rate),
                      tolerances['kinematic_velocity_error_m_s'], 'm/s')

    def configuration_checks():
        changed = deepcopy(config)
        changed['controller_enabled'] = True
        recorder.rejects('configuration.controller_gate',
                         lambda: fixtures.validate_fixture_config(changed))
        old = deepcopy(config)
        old['geometry']['pivot_B0_m'] = old['geometry']['outer_origin_B0_m']
        recorder.rejects('configuration.old_geometry_keyword',
                         lambda: fixtures.validate_fixture_config(old))
        recorder.check('configuration.not_mutated', config == original_config)

    for name, operation in (
        ('state',state_checks), ('frame',frame_checks), ('cad',cad_checks),
        ('mass',mass_checks), ('datum',datum_checks),
        ('configuration',configuration_checks),
    ):
        recorder.group(name, operation)


def main():
    recorder = Recorder()
    before = None
    setup_complete = False
    try:
        with redirect_stdout(sys.stderr):
            before = hashes()
            sys.path.insert(0, str(ROOT))
            modules = {}
            for name, relative in MODULE_FILES.items():
                module = importlib.import_module(name)
                if Path(module.__file__).resolve() != (ROOT/relative).resolve():
                    raise ImportError('Unexpected module origin: ' + name)
                modules[name] = module
            setup_complete = True
            run_checks(recorder, modules)
    except Exception as error:
        recorder.check('checker.setup_or_dispatch_completed', False)
        recorder.exceptions.append({
            'group': 'setup_or_dispatch', 'type': type(error).__name__,
            'message': str(error),
        })
        traceback.print_exc(file=sys.stderr)
    try:
        after = hashes()
        recorder.check('artifacts.unchanged_during_checks', before is not None and before == after)
    except Exception as error:
        after = None
        recorder.check('artifacts.unchanged_during_checks', False)
        recorder.exceptions.append({'group':'final_hashes','type':type(error).__name__,
                                    'message':str(error)})
    tested = dict(recorder.checks)
    outcome = ('inconclusive' if not setup_complete else
               'passed' if tested and all(tested.values()) else 'failed')
    recorder.checks.update({
        'propulsion_and_actuator_analytical_checks_in_this_program': None,
        'numerical_trajectory_checks_in_this_program': None,
        'vehicle_closed_loop_mission_acceptance': None,
        'vehicle_physical_validation': None,
    })
    diagnostics = {
        'scope': 'state/frame/mass algebra and fixed-datum kinematics only',
        'interpreter': {'executable':sys.executable,'version':platform.python_version()},
        'input_file_sha256_before':before, 'input_file_sha256_after':after,
        'measurements':recorder.measurements, 'exceptions':recorder.exceptions,
        'source_preservation_scope':'Only listed r12 artifacts are rehashed here.',
        'controller_executed':False, 'physical_acceptance':'not_assessed',
    }
    print(json.dumps(diagnostics, allow_nan=False, sort_keys=True), file=sys.stderr)
    result = {
        'outcome':outcome,
        'explanation': (
            'Scoped analytical software checks only: '
            + str(sum(tested.values())) + '/' + str(len(tested))
            + ' recorded boolean checks satisfied. Measurements and actual file hashes '
            'are on stderr. Null checks are explicitly unperformed by this program. '
            'No propulsion/trajectory pass, vehicle validity, PID tuning, mission '
            'acceptance or PDR/CDR acceptance is inferred.'
        ),
        'checks':recorder.checks,
    }
    print(json.dumps(result, allow_nan=False, sort_keys=True))


if __name__ == '__main__':
    main()
