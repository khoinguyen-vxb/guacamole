"""Current dependency/import and original-defect diagnostic, M4-04.

Authority: system_model:system@4; work plan
99f7bb629eef45b89fa38d27c803868c@1; interface
88561ff8b3ba4e8286cebd95a93e3b08@1.
Pre-edit report: PDR-PLANT-PRE-EDIT-AUDIT-M4-03@1.

Run: python -B software/pdr_plant/capability_probe_m4_04.py
Repository: 6dof_hopper; sandbox workdir: .
Declare output: software/pdr_plant/capability_report_m4_04.json

No installation, original-source edit, vehicle simulation or physical test.
Private AST isolation is explicitly distinguished from unmodified imports.
This produces diagnostic observations, NOT a VerificationResult.
"""
from __future__ import annotations

import ast
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import sys
import traceback
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parents[1]
PROJECT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper')
ORIGINAL = PROJECT / 'tooling/6dof_hopper'
RECOVERED = SANDBOX / 'previous_run'
OUTPUT = HERE / 'capability_report_m4_04.json'
INVENTORY = HERE / 'source_inventory_m4_02.json'
INVENTORY_SHA256 = '9731f6ace67462d60dfe929d9e3d610abfc85429234421a4ed04c636354ccd77'
ROOTS = {
    'original_hopper': ORIGINAL,
    'pendulum_reference': PROJECT / 'tooling/PendulumControlProject',
    'recovered_previous_run': RECOVERED,
    'archived_notes': PROJECT / 'context/previous_run',
}
# Include pre-existing caches so creation/change of bytecode is observable.
# Environments and Git metadata remain outside this bounded comparison.
EXCLUDED = {'.git', '.venv', 'venv', 'env', 'node_modules'}
AUTHORITY = {
    'system_model': {'kind':'system_model', 'id':'system', 'revision':4,
        'sha256':'e89e68e192965d8e012cc1213e59c02610f55042ad26d7392ebef0401237ee75'},
    'work_plan': {'kind':'decision', 'id':'99f7bb629eef45b89fa38d27c803868c', 'revision':1,
        'sha256':'e5af8e2f56f7c851b65518b129f39550be73911f56461279cbbb1e85e1cdd5f0'},
    'interface': {'kind':'decision', 'id':'88561ff8b3ba4e8286cebd95a93e3b08', 'revision':1,
        'sha256':'ad6662afab9685585264c86e052c246996d23f4369c6432b56094a42a9187c04'},
}


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def snapshot():
    files, omissions = {}, []
    for label, root in ROOTS.items():
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError('Protected root unavailable or symlink: ' + str(root))
        for current, dirs, names in os.walk(root, followlinks=False):
            current = Path(current)
            kept = []
            for name in sorted(dirs):
                path = current / name
                if name in EXCLUDED or path.is_symlink():
                    omissions.append([label, path.relative_to(root).as_posix(),
                                      'excluded directory or un-followed symlink'])
                else:
                    kept.append(name)
            dirs[:] = kept
            for name in sorted(names):
                path = current / name
                rel = path.relative_to(root).as_posix()
                if path.is_symlink() or not path.is_file():
                    omissions.append([label, rel, 'not a regular non-symlink file'])
                    continue
                if len(files) >= 25000:
                    raise RuntimeError('Protected-file inventory bound exceeded')
                before = path.stat()
                value = digest(path)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError('File changed during snapshot: ' + str(path))
                files[(label, rel)] = value
    return files, omissions


def inventory_digest(files):
    rows = [[a, b, value] for (a, b), value in sorted(files.items())]
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def changes(before, after):
    return {
        'changed': [{'root':k[0], 'path':k[1], 'before_sha256':before[k],
                     'after_sha256':after[k]} for k in sorted(before.keys() & after.keys())
                    if before[k] != after[k]],
        'added': [{'root':k[0], 'path':k[1], 'sha256':after[k]}
                  for k in sorted(after.keys() - before.keys())],
        'missing': [{'root':k[0], 'path':k[1], 'sha256':before[k]}
                    for k in sorted(before.keys() - after.keys())],
    }


def main():
    if not OUTPUT.resolve().is_relative_to(SANDBOX.resolve()):
        raise ValueError('Output must be inside the sandbox')
    if OUTPUT.exists():
        raise FileExistsError('Preserve earlier report; use a new probe/output version')
    if digest(INVENTORY) != INVENTORY_SHA256:
        raise ValueError('Published source inventory file digest differs')
    inventory = json.loads(INVENTORY.read_text(encoding='utf-8'))
    baseline = {(r['root'], r['path']):r['sha256'] for r in inventory['files']}
    before, omissions_before = snapshot()
    baseline_mismatches = [
        {'root':k[0], 'path':k[1], 'inventory_sha256':v, 'current_sha256':before.get(k)}
        for k, v in sorted(baseline.items()) if before.get(k) != v
    ]
    report = {
        'schema':'hopper.plant_capability_diagnostic/1',
        'authority':AUTHORITY,
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'probe_sha256':digest(Path(__file__)),
        'inventory_path':str(INVENTORY),
        'inventory_sha256':INVENTORY_SHA256,
        'interpreter':{'executable':sys.executable, 'version':sys.version,
                       'implementation':platform.python_implementation(),
                       'dont_write_bytecode':sys.dont_write_bytecode,
                       'cwd':str(Path.cwd())},
        'distribution_metadata':{},
        'observations':[],
        'baseline_mismatches':baseline_mismatches,
        'physical_acceptance':'not_assessed',
        'plant_regression_performed':False,
        'limitations':[
            'Diagnostic report, not a VerificationResult or complete plant regression.',
            'Distribution metadata alone does not establish import or execution capability.',
            'Private import isolation and solver stubs do not show the original plant runs.',
            'All reproduction inputs are synthetic, not selected vehicle parameters.',
            'Recovered-package imports do not validate its analytical model or scope.',
            'Preservation covers enumerated regular files, including caches; excludes environments, Git metadata and un-followed symlinks.',
            'No installation, source checkout modification, PID tuning or hardware test is performed.',
        ],
    }
    modules = {}

    def observe(identifier, mode, function, expectation=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        row = {'id':identifier, 'mode':mode}
        if expectation is not None:
            row['source_based_expectation_not_result'] = expectation
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                row['value'] = function()
            row['observation_status'] = 'returned'
        except Exception as exc:
            row.update(observation_status='raised', exception_type=type(exc).__name__,
                       exception_message=str(exc), traceback=traceback.format_exc())
        row['captured_stdout'] = stdout.getvalue()
        row['captured_stderr'] = stderr.getvalue()
        report['observations'].append(row)
        return row

    def skipped(identifier, reason):
        report['observations'].append({'id':identifier,
            'observation_status':'not_performed', 'reason':reason})

    def load_module(key, name, expected_file=None):
        module = importlib.import_module(name)
        actual = getattr(module, '__file__', None)
        if expected_file is not None and (actual is None or
                Path(actual).resolve() != expected_file.resolve()):
            raise ImportError('Unexpected module origin for ' + name + ': ' + str(actual))
        modules[key] = module
        return {'module':name, 'file':actual,
                'module_version':str(getattr(module, '__version__', 'not exposed'))}

    try:
        for name in ('numpy', 'scipy', 'pytest', 'matplotlib', 'openmdao', 'black', 'uv'):
            try:
                report['distribution_metadata'][name] = {
                    'version':importlib.metadata.version(name), 'import_established':False}
            except importlib.metadata.PackageNotFoundError:
                report['distribution_metadata'][name] = {
                    'version':None, 'status':'distribution metadata not found',
                    'import_established':False}

        if baseline_mismatches:
            skipped('target_execution', 'Source differs from inspected inventory; review changes before importing')
        else:
            for name in ('numpy', 'scipy', 'scipy.integrate', 'pytest'):
                observe('import_' + name, 'actual dependency import',
                        lambda name=name: load_module(name, name))

            if 'numpy' in modules and 'scipy.integrate' in modules:
                def numerical_smoke():
                    np = modules['numpy']
                    solution = modules['scipy.integrate'].solve_ivp(
                        lambda t, y: np.array([2.0*t]), (0.0, 1.0), [3.0],
                        t_eval=[0.0, 0.25, 1.0], dense_output=True,
                        rtol=1e-10, atol=1e-12, max_step=0.1)
                    expected = 3.0 + solution.t**2
                    return {'fixture':'Standalone y_dot=2*t, y(0)=3; not hopper dynamics',
                            'success':bool(solution.success), 'status':int(solution.status),
                            'message':str(solution.message),
                            'result_type':type(solution).__module__ + '.' + type(solution).__name__,
                            'times_s':solution.t.tolist(), 'values':solution.y.tolist(),
                            'max_absolute_error':float(np.max(np.abs(solution.y[0]-expected))),
                            'dense_value_at_0p5':solution.sol(0.5).tolist(),
                            'nfev':int(solution.nfev)}
                observe('standalone_scipy_numerical_smoke', 'actual numerical execution; not plant verification', numerical_smoke)
            else:
                skipped('standalone_scipy_numerical_smoke', 'Required numerical imports unavailable')

            # Explicit source-root selection; never inject a top-level state alias.
            sys.path.insert(0, str(ORIGINAL))
            original_modules = (
                ('original_math', 'helpers.math', 'helpers/math.py'),
                ('original_state', 'simulation.state', 'simulation/state.py'),
                ('original_propulsion', 'propulsion.propulsion', 'propulsion/propulsion.py'),
                ('original_propeller', 'propulsion.propeller', 'propulsion/propeller.py'),
                ('original_hopper', 'chassis.hopper', 'chassis/hopper.py'),
                ('original_aero', 'aero.aero', 'aero/aero.py'),
                ('original_simulation', 'simulation.simulation', 'simulation/simulation.py'),
            )
            for key, name, rel in original_modules:
                observe('import_' + key, 'unmodified original module import',
                        lambda key=key, name=name, rel=rel:
                            load_module(key, name, ORIGINAL / rel),
                        'Original Simulation has an unresolved top-level State import'
                        if key == 'original_simulation' else None)

            np = modules.get('numpy')
            if np is not None and 'original_math' in modules:
                math_module = modules['original_math']
                observe('RC06_original_DCM_local_name', 'direct original function call',
                        lambda: math_module.quarternion_to_dcm(np.array([1.,0.,0.,0.])),
                        'UnboundLocalError from quaternions before assignment')
                observe('RC07_original_Euler_signature', 'direct original function call',
                        lambda: math_module.euler_to_quaternion(0.1, 0.2, 0.3),
                        'TypeError for three positional arguments')
                def euler_order():
                    observed = math_module.euler_to_quaternion([10.0, 0.0, 0.0])
                    half = np.deg2rad(10.0)/2.0
                    documented_roll = np.array([np.cos(half),np.sin(half),0.,0.])
                    return {'input_documented_roll_pitch_yaw_deg':[10.,0.,0.],
                            'actual_quaternion_wxyz':observed.tolist(),
                            'expected_for_documented_pure_roll_wxyz':documented_roll.tolist(),
                            'component_max_difference':float(np.max(np.abs(observed-documented_roll)))}
                observe('RC08_original_Euler_order', 'direct original function call', euler_order)

            if np is not None and 'original_state' in modules:
                State = modules['original_state'].State
                initial = (1.,2.,-3.,0.4,-0.5,0.6,1.,0.,0.,0.,0.1,-0.2,0.3)
                observe('RC04_original_update_signature', 'direct original function call',
                        lambda: State(*initial).update_state(np.asarray(initial)),
                        'TypeError because update_state requires thirteen scalar arguments')
                def history_mutation():
                    state = State(*initial)
                    before_lengths = [len(state.x_arr),len(state.q0_arr)]
                    state.update_state(*initial)
                    return {'before_history_lengths':before_lengths,
                            'after_history_lengths':[len(state.x_arr),len(state.q0_arr)],
                            'scope':'Direct update_state call only; original RHS remains blocked'}
                observe('RC11_original_history_mutation', 'direct original function call', history_mutation)

                if 'original_math' in modules and 'scipy.integrate' in modules:
                    def private_simulation_probe():
                        path = ORIGINAL / 'simulation/simulation.py'
                        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
                        removed = [n for n in tree.body if isinstance(n, ast.ImportFrom)
                                   and n.level == 0 and n.module == 'state']
                        if len(removed) != 1 or [a.name for a in removed[0].names] != ['State']:
                            raise ValueError('Unexpected source import; re-audit before isolation')
                        tree.body = [n for n in tree.body if n is not removed[0]]
                        namespace = {'__name__':'private_original_simulation_probe', 'State':State}
                        exec(compile(tree, str(path)+' [private import isolation]', 'exec'), namespace)
                        Simulation = namespace['Simulation']

                        def construct():
                            return Simulation(State(*initial), object(), object(), object())

                        observe('RC02_original_initial_state_discard',
                                'private namespace: only failing State import replaced',
                                lambda: {'supplied_initial_vector':list(initial),
                                         'stored_state_is_none':construct().state is None})
                        observe('RC03_original_undefined_time',
                                'private namespace: only failing State import replaced',
                                lambda: construct().trajectory_ode(0.0, np.asarray(initial)),
                                'AttributeError for undefined self.time')

                        def numeric_object_mismatch():
                            simulation = construct()
                            simulation.time = 0.0
                            return simulation.trajectory_ode(0.0, np.asarray(initial))
                        observe('RC05_original_numeric_vector_attributes',
                                'private namespace plus synthetic self.time=0 to expose next defect',
                                numeric_object_mismatch,
                                'AttributeError from treating numeric vector as State')

                        def update_call_mismatch():
                            simulation = construct()
                            simulation.time = 1.0
                            simulation.state = State(*initial)
                            return simulation.trajectory_ode(1.0, np.asarray(initial))
                        observe('RC04_original_RHS_update_call',
                                'private namespace plus explicit state/time isolation',
                                update_call_mismatch,
                                'TypeError at original update_state(vector) call')
                        observe('RC07_original_solver_Euler_call',
                                'private namespace: only failing State import replaced',
                                lambda: construct().solve_ode(0.1,0.2,0.3,1.0),
                                'TypeError at original Euler conversion call')

                        def solver_boundary_instrumentation():
                            captured = {}
                            sentinel = object()
                            def euler_stub(*args):
                                captured['Euler_arguments'] = list(args)
                                return np.array([1.,0.,0.,0.])
                            def solver_stub(**kwargs):
                                captured['solver_y0'] = list(kwargs['y0'])
                                captured['solver_t_span'] = list(kwargs['t_span'])
                                return sentinel
                            saved = namespace['euler_to_quaternion'], namespace['solve_ivp']
                            namespace['euler_to_quaternion'] = euler_stub
                            namespace['solve_ivp'] = solver_stub
                            try:
                                simulation = construct()
                                returned = simulation.solve_ode(0.1,0.2,0.3,1.0)
                                captured.update(return_is_none=returned is None,
                                                returned_solver_sentinel=returned is sentinel,
                                                stored_state_after_call=list(simulation.state.unpack_state()),
                                                constructor_input=list(initial),
                                                actual_integration_performed=False)
                                return captured
                            finally:
                                namespace['euler_to_quaternion'], namespace['solve_ivp'] = saved
                        observe('RC09_RC10_original_reset_and_discard',
                                'private namespace with explicitly stubbed Euler and solver; NOT integration',
                                solver_boundary_instrumentation)
                        return {'original_file_sha256':digest(path),
                                'removed_import':ast.unparse(removed[0]),
                                'source_files_written':False,
                                'sys_modules_state_alias_inserted':False}
                    observe('private_original_import_isolation',
                            'instrumented in-memory source; not unmodified module execution',
                            private_simulation_probe)

            if 'original_propeller' in modules and 'original_propulsion' in modules:
                observe('RC12_original_abstract_propeller', 'direct original constructor call',
                        lambda: modules['original_propeller'].Propellor(
                            modules['original_propulsion'].PropulsionType.PROPELLER,
                            100.,0.1,1.,10.,10.,0.1),
                        'TypeError for unimplemented abstract methods; numbers are synthetic')

            if np is not None and 'original_hopper' in modules:
                def hopper_alias():
                    cg = np.array([0.1,0.2,0.3])
                    arm = np.array([0.,0.,0.2])
                    centre = np.array([0.4,0.5,0.6])
                    hopper = modules['original_hopper'].Hopper(
                        propulsion=object(), cg=cg, mass_wo_propellant=1.,
                        moment_arm=arm, Ixx=0.1, Iyy=0.1, Izz=0.1,
                        cd=1., csa=0.1, length=1., outer_diameter=0.1,
                        tube_center_body=centre)
                    prior = hopper.cg.copy()
                    shared = bool(np.shares_memory(cg,hopper.cg))
                    cg[0] = 0.9
                    return {'fixture':'Synthetic ownership diagnostic only',
                            'cg_shares_input_memory':shared, 'cg_before':prior.tolist(),
                            'cg_after_caller_mutation':hopper.cg.tolist(),
                            'arm_shares_input_memory':bool(np.shares_memory(arm,hopper.moment_arm)),
                            'centre_shares_input_memory':bool(np.shares_memory(centre,hopper.tube_center_body))}
                observe('RC13_original_Hopper_aliasing', 'direct original constructor and input mutation', hopper_alias)

            if np is not None and 'original_aero' in modules:
                def aero_diagnostics():
                    axis = np.array([2.,0.,0.])
                    before_axis = axis.copy()
                    aero = modules['original_aero'].Aerodynamics(
                        SimpleNamespace(tube_center_body=np.zeros(3)))
                    force, moment = aero.determine_at_point(
                        air_velocity_body=np.zeros(3), angular_rates_body=np.array([0.,1.,0.]),
                        density=1.225, dynamic_viscosity=1.8e-5,
                        speed_of_sound=340., cg=np.zeros(3), tube_axis_body=axis)
                    return {'fixture':'Synthetic zero-translation, nonzero-rotation diagnostic',
                            'caller_axis_before':before_axis.tolist(), 'caller_axis_after':axis.tolist(),
                            'returned_force_N':force.tolist(), 'returned_moment_N_m':moment.tolist(),
                            'interpretation':'Observes input mutation and early-return behavior, not physical drag validity'}
                observe('RC14_original_aero_alias_and_early_return', 'direct original function call', aero_diagnostics)

            sys.path.insert(0, str(RECOVERED))
            for rel in ('helpers/math.py','simulation/state.py','chassis/hopper.py',
                        'propulsion/propulsion.py','propulsion/propeller.py',
                        'propulsion/actuators.py','simulation/environment.py','simulation/simulation.py'):
                name = 'repaired_hopper_r12.' + rel[:-3].replace('/', '.')
                observe('import_' + name, 'unmodified recovered module import only',
                        lambda name=name, rel=rel:
                            load_module(name, name, RECOVERED / 'repaired_hopper_r12' / rel))
    finally:
        after, omissions_after = snapshot()
        report['preservation'] = {
            'roots':{label:str(root) for label,root in ROOTS.items()},
            'regular_file_count_before':len(before), 'regular_file_count_after':len(after),
            'content_manifest_digest_before':inventory_digest(before),
            'content_manifest_digest_after':inventory_digest(after),
            'delta':changes(before,after),
            'omissions_before':omissions_before, 'omissions_after':omissions_after,
            'bytecode_writes_disabled':bool(sys.dont_write_bytecode),
            'scope':'Diagnostic comparison, not registered source-preservation verification',
        }
        with OUTPUT.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps({'report':str(OUTPUT.relative_to(SANDBOX)),
                      'observations_recorded':len(report['observations']),
                      'verification_result':False,
                      'physical_acceptance':'not_assessed'}))


if __name__ == '__main__':
    main()
