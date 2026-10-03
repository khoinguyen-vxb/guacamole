#!/usr/bin/env python3
"""PDR-only diagnostics of the original checkout; NOT a repaired simulator.

Run using Guacamole execute, repository='6dof_hopper', argv[0]='python',
with -B and a sandbox working directory. This program creates raw measurement
artifacts; a separate verify_command program must assess those artifacts.
There is no plant repair, PID implementation, gain tuning or physical test.
All expected exceptions are recorded rather than converted into capability passes.
"""
import sys
sys.dont_write_bytecode = True

import ast
import contextlib
import datetime
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import tempfile
import traceback
from types import SimpleNamespace

TASK = Path(__file__).resolve().parent
SOURCE = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper')
PENDULUM = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/PendulumControlProject')
OUT = TASK / 'results'
if Path.cwd().resolve().is_relative_to(SOURCE) or Path.cwd().resolve().is_relative_to(PENDULUM):
    raise RuntimeError('Probe working directory must not be inside a supplied checkout')
OUT.mkdir(parents=True, exist_ok=True)
CACHE = tempfile.TemporaryDirectory(prefix='diagnostic_cache_', dir=TASK)
cache_path = Path(CACHE.name)
for key, value in {
    'PYTHONDONTWRITEBYTECODE': '1',
    'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
    'MPLBACKEND': 'Agg',
    'MPLCONFIGDIR': str(cache_path / 'matplotlib'),
    'XDG_CACHE_HOME': str(cache_path / 'xdg'),
    'NUMBA_CACHE_DIR': str(cache_path / 'numba'),
    'OPENMDAO_REPORTS': '0',
}.items():
    os.environ[key] = value

# Retain standard-library/site-package paths but remove source subdirectory
# shortcuts. In particular, simulation/ must not make 'from state' work.
original_sys_path = list(sys.path)
def under(path, root):
    try:
        return Path(path or os.getcwd()).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False
sys.path[:] = [str(SOURCE)] + [p for p in sys.path if not under(p, SOURCE) and not under(p, PENDULUM)]

REPORT = {
    'schema': 'pdr_r4_plant_control.probes/1',
    'stage': 'PDR diagnosis only',
    'utc_started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_root': str(SOURCE),
    'pendulum_root': str(PENDULUM),
    'probe_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'probes': {},
    'limitations': [
        'No integrated plant, controller, mission, geometry or hardware acceptance test is performed.',
        'Normal imports and diagnostic imports using temporary in-memory shims are reported separately.',
        'AST call indexing cannot prove the absence of dynamic imports, reflection or runtime aliasing.',
        'Source manifests exclude .git and virtual environments; they include pre-existing bytecode caches.',
        'PyThrust execution and pytest are deferred and must not be inferred from dependency imports.',
    ],
}

def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, 'tolist'):
        return json_value(value.tolist())
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return repr(value)

def write_json(path, value):
    if not path.resolve().is_relative_to(TASK):
        raise ValueError('Output escaped task sandbox')
    path.write_text(json.dumps(json_value(value), indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')

def manifest(root):
    files = {}
    excluded = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        base = Path(current)
        for name in list(directories):
            path = base / name
            relative = str(path.relative_to(root))
            if name in {'.git', '.venv', 'venv', '.env'}:
                directories.remove(name)
                excluded.append(relative)
            elif path.is_symlink():
                directories.remove(name)
                files[relative] = {'symlink': os.readlink(path)}
        for name in filenames:
            path = base / name
            relative = str(path.relative_to(root))
            if path.is_symlink():
                files[relative] = {'symlink': os.readlink(path)}
            else:
                stat = path.stat()
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                files[relative] = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'sha256': digest.hexdigest()}
    return {'root': str(root), 'exists': root.is_dir(), 'excluded_directories': sorted(excluded), 'files': files}

def probe(identifier, description, operation, diagnostic_only=False):
    out, err = io.StringIO(), io.StringIO()
    record = {'description': description, 'diagnostic_only': diagnostic_only}
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            record['result'] = json_value(operation())
        record['execution'] = 'returned'
    except Exception as exc:
        record.update(execution='raised', exception=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
    record['captured_stdout'] = out.getvalue()
    record['captured_stderr'] = err.getvalue()
    REPORT['probes'][identifier] = record
    print(identifier + ': ' + record['execution'], file=sys.stderr)
    return record

BEFORE = {name: manifest(root) for name, root in [('6dof_hopper', SOURCE), ('PendulumControlProject', PENDULUM)]}
write_json(OUT / 'source_manifest_before.json', BEFORE)

def dependency_identity():
    distributions = ['numpy', 'scipy', 'matplotlib', 'openmdao', 'pytest', 'black', 'uv', 'setuav-pythrust']
    versions = {}
    for name in distributions:
        try:
            versions[name] = {'version': importlib.metadata.version(name)}
        except importlib.metadata.PackageNotFoundError:
            versions[name] = {'version': None, 'reason': 'distribution metadata not found'}
    imports = {}
    for name in ['numpy', 'scipy', 'scipy.integrate', 'matplotlib', 'openmdao', 'openmdao.api', 'pytest', 'black']:
        capture_out, capture_err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(capture_out), contextlib.redirect_stderr(capture_err):
                module = importlib.import_module(name)
            imports[name] = {'imported': True, 'file': getattr(module, '__file__', None), 'module_version': getattr(module, '__version__', None)}
        except Exception as exc:
            imports[name] = {'imported': False, 'exception': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
        imports[name]['stdout'] = capture_out.getvalue()
        imports[name]['stderr'] = capture_err.getvalue()
    return {
        'sys_executable': sys.executable, 'executable_resolved': str(Path(sys.executable).resolve()),
        'python_version': sys.version, 'implementation': platform.python_implementation(),
        'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
        'virtual_environment_active': sys.prefix != sys.base_prefix,
        'cwd': str(Path.cwd()), 'source_directory_present': SOURCE.is_dir(),
        'original_sys_path': original_sys_path, 'probe_sys_path': list(sys.path),
        'bytecode_disabled': sys.dont_write_bytecode, 'distribution_metadata': versions,
        'actual_imports': imports, 'pytest_executed': False,
        'cache_policy': 'temporary directories inside task sandbox, removed at completion',
        'python_requirement': '>=3.13, as declared in source pyproject.toml',
        'python_meets_declared_minimum': sys.version_info[:2] >= (3, 13),
    }

probe('P00', 'Backend identity, distribution metadata and actual imports, separately', dependency_identity)
probe('P01', 'Import original gravity constant', lambda: {'gravity_value': importlib.import_module('helpers.constants').GRAVITY, 'unit': 'm/s^2'})
probe('P02', 'Import original helpers.math', lambda: {'module_file': importlib.import_module('helpers.math').__file__})
probe('P03', 'Call original quarternion_to_dcm on identity quaternion', lambda: importlib.import_module('helpers.math').quarternion_to_dcm([1.0, 0.0, 0.0, 0.0]))
probe('P04', 'Call Euler helper with the exact three-argument pattern in solve_ode', lambda: importlib.import_module('helpers.math').euler_to_quaternion(0.0, 0.0, 0.0))

def euler_axis():
    import numpy as np
    q = importlib.import_module('helpers.math').euler_to_quaternion([10.0, 0.0, 0.0])
    return {'input': [10, 0, 0], 'input_unit': 'deg', 'quaternion_scalar_first': q, 'dominant_axis_for_first_element': ['x', 'y', 'z'][int(np.argmax(np.abs(q[1:])))]}
probe('P05', 'Measure the rotation axis associated with the first Euler-vector element', euler_axis)

def state_update():
    import numpy as np
    State = importlib.import_module('simulation.state').State
    state = State(*([0.0] * 13))
    return state.update_state(np.zeros(13))
probe('P06', 'Call State.update_state with the single ndarray used by trajectory_ode', state_update)
probe('P07', 'Normal simulation import with repository root but not simulation/ on sys.path', lambda: {'module_file': importlib.import_module('simulation.simulation').__file__})

@contextlib.contextmanager
def diagnostic_simulation():
    # Import-only shim. The source file and its executable body are unchanged.
    State = importlib.import_module('simulation.state').State
    sentinel = object()
    previous = sys.modules.get('state', sentinel)
    sys.modules['state'] = importlib.import_module('simulation.state')
    try:
        spec = importlib.util.spec_from_file_location('_pdr_diagnostic_simulation', SOURCE / 'simulation/simulation.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module.Simulation, State
    finally:
        if previous is sentinel:
            sys.modules.pop('state', None)
        else:
            sys.modules['state'] = previous

def simulation_case(case):
    import numpy as np
    with diagnostic_simulation() as (Simulation, State):
        supplied = State(*([0.0] * 6 + [1.0, 0.0, 0.0, 0.0] + [0.0] * 3))
        simulation = Simulation(supplied, None, None, None)
        if case == 'constructor':
            return {'state_attribute_is_none': simulation.state is None, 'supplied_state_preserved': simulation.state is supplied}
        if case == 'fresh_rhs':
            return simulation.trajectory_ode(0.0, np.zeros(13))
        if case == 'time_zero':
            simulation.time = 0.0
            return simulation.trajectory_ode(0.0, np.zeros(13))
        if case == 'time_one':
            simulation.time = 1.0
            simulation.state = supplied
            return simulation.trajectory_ode(1.0, np.zeros(13))
        if case == 'solve':
            return simulation.solve_ode(0.0, 0.0, 0.0, 1.0)
        raise ValueError(case)
for identifier, case in [('P08a', 'constructor'), ('P08b', 'fresh_rhs'), ('P08c', 'time_zero'), ('P08d', 'time_one'), ('P08e', 'solve')]:
    probe(identifier, 'Diagnostic import shim; case=' + case + '; no source repair', lambda c=case: simulation_case(c), True)

SIM_TREE = ast.parse((SOURCE / 'simulation/simulation.py').read_text(encoding='utf-8'))
def return_inspection():
    method = next(node for node in ast.walk(SIM_TREE) if isinstance(node, ast.FunctionDef) and node.name == 'solve_ode')
    returns = [node.lineno for node in ast.walk(method) if isinstance(node, ast.Return)]
    return {'solve_ode_has_return': bool(returns), 'return_lines': returns, 'function_line': method.lineno}
probe('P09', 'AST inspection of integration-result return', return_inspection)

def propeller_construction():
    from propulsion.propeller import Propellor
    from propulsion.propulsion import PropulsionType
    return Propellor(PropulsionType.PROPELLER, 860.0, 0.0258, 1.3, 65.0, 14.8, 0.05)
probe('P10', 'Instantiate original Propellor using demonstration electrical values, not a hardware selection', propeller_construction)

def make_hopper(propulsion):
    import numpy as np
    from chassis.hopper import Hopper
    return Hopper(propulsion=propulsion, cg=np.zeros(3), mass_wo_propellant=1.0, moment_arm=np.array([0.0, 0.0, 0.2]), Ixx=0.01, Iyy=0.02, Izz=0.03, cd=0.8, csa=0.01, length=1.0, outer_diameter=0.1)

def literal_contract(through_hopper=False):
    from propulsion.propulsion import Propulsion, PropulsionType
    class LiteralSignatures(Propulsion):
        def get_mass(t):
            return 1.0
        def get_local_cg():
            return [0.2, 0.0, 0.0]
        def get_thrust_and_moment(t):
            return [0.0] * 3, [0.0] * 3
    propulsion = LiteralSignatures(PropulsionType.PROPELLER)
    return make_hopper(propulsion).mass(0.0) if through_hopper else propulsion.get_mass(0.0)
probe('P11', 'Literal implementation of declared abstract signature: direct bound call', literal_contract)
probe('P11b', 'Literal implementation of declared abstract signature: actual Hopper.mass caller', lambda: literal_contract(True))

def aerodynamic_case(mutation=False):
    import numpy as np
    from aero.aero import Aerodynamics
    geometry = SimpleNamespace(length=1.0, outer_diameter=0.1, inner_diameter=0.0, tube_center_body=np.zeros(3))
    aero = Aerodynamics(geometry)
    common = {'angular_rates_body': np.array([0.0, 1.0, 0.0]), 'density': 1.225, 'dynamic_viscosity': 1.81e-5, 'speed_of_sound': 340.0, 'cg': np.zeros(3)}
    if mutation:
        axis = np.array([2.0, 0.0, 0.0])
        before = axis.copy()
        aero.determine_at_point(air_velocity_body=np.array([1.0, 0.0, 0.0]), tube_axis_body=axis, **common)
        return {'caller_axis_before': before, 'caller_axis_after': axis, 'caller_array_mutated': not np.array_equal(before, axis)}
    zero = aero.determine_at_point(air_velocity_body=np.zeros(3), **common)
    near = aero.determine_at_point(air_velocity_body=np.array([1e-6, 0.0, 0.0]), **common)
    return {'velocity_unit': 'm/s', 'rate_unit': 'rad/s', 'force_unit': 'N', 'moment_unit': 'N*m', 'zero_speed_force_moment': zero, 'near_zero_force_moment': near, 'moment_zero_at_zero_airspeed': bool(np.all(zero[1] == 0)), 'moment_nonzero_at_1e-6_mps': bool(np.any(near[1] != 0))}
probe('P12', 'Compare original aerodynamic moments at zero and near-zero airspeed', aerodynamic_case)
probe('P13', 'Detect mutation of caller-provided aerodynamic tube axis', lambda: aerodynamic_case(True))

def mass_ownership():
    import numpy as np
    from propulsion.propulsion import Propulsion, PropulsionType
    class WorkingStub(Propulsion):
        def get_mass(self, t):
            return 1.0
        def get_local_cg(self):
            return np.array([0.2, 0.0, 0.0])
        def get_thrust_and_moment(self, t):
            return np.zeros(3), np.zeros(3)
    hopper = make_hopper(WorkingStub(PropulsionType.PROPELLER))
    expected_cg = np.array([0.1, 0.0, 0.0])
    actual_cg = hopper.CG(0.0)
    return {'airframe_mass_kg': 1.0, 'stub_propulsion_mass_kg': 1.0, 'returned_mass_kg': hopper.mass(0.0), 'returned_cg_m': actual_cg, 'composite_cg_expected_if_stub_is_added_m': expected_cg, 'cg_ignores_propulsion_mass': bool(np.array_equal(actual_cg, hopper.cg) and not np.array_equal(actual_cg, expected_cg)), 'returned_inertia_kg_m2': hopper.inertia(0.0), 'inertia_offdiagonal_representable': any(name in hopper.__dataclass_fields__ for name in ['Ixy', 'Ixz', 'Iyz'])}
probe('P14', 'Measure original Hopper mass and CG ownership using an explicit diagnostic stub', mass_ownership, True)

AFFECTED = {'Simulation', 'State', 'trajectory_ode', 'solve_ode', 'update_state', 'unpack_state', 'euler_to_quaternion', 'quarternion_to_dcm', 'Hopper', 'mass', 'CG', 'inertia', 'get_mass', 'get_local_cg', 'get_thrust_and_moment', 'Propellor', 'Propulsion', 'Aerodynamics', 'determine_at_point'}
INDEX = {'schema': 'pdr_r4_plant_control.source_index/1', 'modules': {}, 'method': 'AST call-name and attribute-name index; conservative, not dynamic call-graph proof'}
CORE_TREES = {}
for relative, metadata in BEFORE['6dof_hopper']['files'].items():
    if not relative.endswith('.py') or 'symlink' in metadata:
        continue
    path = SOURCE / relative
    entry = {'sha256': metadata['sha256'], 'scope': 'PyThrust' if relative.startswith('PyThrust/') else 'hopper'}
    try:
        text = path.read_text(encoding='utf-8')
        tree = ast.parse(text)
        entry['calls'] = []
        entry['affected_references'] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                entry['calls'].append({'line': node.lineno, 'callee': ast.unparse(node.func)})
            if isinstance(node, ast.Name) and node.id in AFFECTED:
                entry['affected_references'].append({'line': node.lineno, 'name': node.id})
            elif isinstance(node, ast.Attribute) and node.attr in AFFECTED:
                entry['affected_references'].append({'line': node.lineno, 'name': ast.unparse(node)})
        if entry['scope'] == 'hopper':
            CORE_TREES[relative] = (text, tree)
    except Exception as exc:
        entry['read_or_parse_error'] = {'exception': type(exc).__name__, 'message': str(exc)}
    INDEX['modules'][relative] = entry

# Locate the static evidence in the existing, editable register; never import it.
def load_register():
    register_path = TASK / 'defect_register.py'
    tree = ast.parse(register_path.read_text(encoding='utf-8'))
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'REGISTER' for target in node.targets))
    return ast.literal_eval(assignment.value)

def locate_register_evidence():
    register = load_register()
    located = []
    for item in register['defects'] + register['observations']:
        for assertion in item.get('evidence', []):
            path = SOURCE / assertion['file']
            result = {'id': item['id'], 'file': assertion['file'], 'assertion': assertion}
            if 'exists' in assertion:
                result['exists_observed'] = path.exists()
            if 'size_bytes' in assertion:
                result['size_bytes_observed'] = path.stat().st_size if path.exists() else None
            if 'contains' in assertion or 'not_contains' in assertion:
                lines = path.read_text(encoding='utf-8').splitlines()
                result['contains_locations'] = {needle: [number for number, line in enumerate(lines, 1) if needle in line] for needle in assertion.get('contains', [])}
                result['not_contains_locations'] = {needle: [number for number, line in enumerate(lines, 1) if needle in line] for needle in assertion.get('not_contains', [])}
            located.append(result)
    return {'register_sha256': hashlib.sha256((TASK / 'defect_register.py').read_bytes()).hexdigest(), 'locations': located}
probe('STATIC', 'Locate defect-register evidence in current source files; no execution conclusions', locate_register_evidence)

def caller_summary():
    callers = []
    moment_uses = []
    for name, (text, tree) in CORE_TREES.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id == 'Simulation') or (isinstance(node.func, ast.Attribute) and node.func.attr == 'Simulation')):
                if name != 'simulation/simulation.py':
                    callers.append({'file': name, 'line': node.lineno})
            if isinstance(node, ast.Attribute) and node.attr == 'moment_arm' and name != 'chassis/hopper.py':
                moment_uses.append({'file': name, 'line': node.lineno})
    rhs = next(node for node in ast.walk(SIM_TREE) if isinstance(node, ast.FunctionDef) and node.name == 'trajectory_ode')
    stores = {node.id for node in ast.walk(rhs) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
    loads = {node.id for node in ast.walk(rhs) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    return {'simulation_class_callers_outside_module': len(callers), 'caller_locations': callers, 'moment_arm_used_outside_chassis_hopper': bool(moment_uses), 'moment_arm_locations': moment_uses, 'unused_rhs_names': sorted(stores - loads), 'core_python_files_indexed': sorted(CORE_TREES), 'pythrust_python_files_indexed_separately': sum(v['scope'] == 'PyThrust' for v in INDEX['modules'].values())}
probe('P15', 'AST caller and unused-variable index, with nested PyThrust separated', caller_summary)

def missing_interfaces():
    environment, controls, nested = [], [], []
    for name, entry in INDEX['modules'].items():
        if entry['scope'] == 'PyThrust':
            if 'atmosphere' in name.lower():
                nested.append(name)
            continue
        if name not in CORE_TREES:
            continue
        for node in ast.walk(CORE_TREES[name][1]):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                location = {'file': name, 'line': node.lineno, 'name': node.name}
                if 'environment' in low or 'atmosphere' in low:
                    environment.append(location)
                if any(word in low for word in ['controller', 'pid', 'actuator', 'gimbal', 'servo']):
                    controls.append(location)
    return {'environment_definitions_outside_pythrust': len(environment), 'environment_definitions': environment, 'controller_or_actuator_symbols_outside_pythrust': len(controls), 'controller_or_actuator_definitions': controls, 'pythrust_atmosphere_paths': nested}
probe('P16', 'Search definitions for environment and controller/actuator interfaces', missing_interfaces)

# This probe evaluates source expressions, not a modified integrated plant.
def attitude_formula_diagnostic():
    import numpy as np
    from scipy.integrate import solve_ivp
    from scipy.spatial.transform import Rotation
    math_source = (SOURCE / 'helpers/math.py').read_text(encoding='utf-8')
    tree = ast.parse(math_source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'quarternion_to_dcm')
    function.args.args[0].arg = 'quaternions'
    function.args.args[0].annotation = None
    isolated = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {'np': np}
    exec(compile(isolated, '<diagnostic parameter-name shim; original formula>', 'exec'), namespace)
    q = np.array([0.7, 0.2, -0.3, 0.4]); q /= np.linalg.norm(q)
    dcm = namespace['quarternion_to_dcm'](q)
    independent = Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix().T
    assignments = {node.targets[0].id: node.value for node in ast.walk(SIM_TREE) if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    rate_matrix = eval(compile(ast.Expression(assignments['quaternion_rate_matrix']), '<original quaternion-rate matrix>', 'eval'), {'np': np, 'p': 0.0, 'q': 0.0, 'r': 0.2})
    rate_expression = compile(ast.Expression(assignments['quaternion_dot']), '<original quaternion derivative>', 'eval')
    correction_gain = ast.literal_eval(assignments['correction_gain'])
    def rhs(t, quaternion):
        return eval(rate_expression, {'np': np, 'quaternion_rate_matrix': rate_matrix, 'quaternion': quaternion, 'quaternion_norm_error': 1.0 - quaternion @ quaternion, 'correction_gain': correction_gain})
    sol = solve_ivp(rhs, (0.0, 10.0), [1.0, 0.0, 0.0, 0.0], rtol=1e-11, atol=1e-13, max_step=0.01)
    if not sol.success:
        raise RuntimeError(sol.message)
    expected = np.array([np.cos(1.0), 0.0, 0.0, np.sin(1.0)])
    error = float(np.max(np.abs(sol.y[:, -1] - expected)))
    matrix_error = float(np.max(np.abs(dcm - independent)))
    orthogonality_error = float(np.max(np.abs(dcm @ dcm.T - np.eye(3))))
    return {'diagnostic_change': 'One in-memory AST parameter rename solely to expose the existing DCM formula; no file modified', 'dcm_max_absolute_error': matrix_error, 'dcm_orthogonality_max_error': orthogonality_error, 'dcm_equals_transpose_of_body_to_world': matrix_error < 1e-12, 'dcm_orthonormal': orthogonality_error < 1e-12, 'kinematics_matches_analytic_yaw': error < 1e-9, 'quaternion_component_max_error': error, 'max_quaternion_norm_error': float(np.max(np.abs(np.linalg.norm(sol.y, axis=0) - 1.0))), 'duration_s': 10.0, 'body_yaw_rate_rad_s': 0.2, 'integrated_original_plant': False}
probe('P17', 'Isolated attitude-formula diagnostics with explicit in-memory name shim', attitude_formula_diagnostic, True)

def pendulum_inventory():
    definitions, hopper_hits, pid_hits = [], [], []
    for relative, metadata in BEFORE['PendulumControlProject']['files'].items():
        if not relative.endswith(('.py', '.md', '.txt')) or 'symlink' in metadata:
            continue
        path = PENDULUM / relative
        text = path.read_text(encoding='utf-8')
        for number, line in enumerate(text.splitlines(), 1):
            if 'hopper' in line.lower():
                hopper_hits.append({'file': relative, 'line': number, 'text': line})
            if 'pid' in line.lower():
                pid_hits.append({'file': relative, 'line': number, 'text': line})
        if relative.endswith('.py'):
            tree = ast.parse(text)
            definitions.extend({'file': relative, 'line': node.lineno, 'name': node.name} for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef)))
    return {'hopper_references_found': bool(hopper_hits), 'hopper_references': hopper_hits, 'pid_text_references': pid_hits, 'python_definitions': definitions, 'pendulum_execution_performed': False}
probe('P18', 'Index pendulum reference contents without executing GUI or user-input entry points', pendulum_inventory)

for identifier, description in [('P19', 'PyThrust import and database probe'), ('P20', 'Original PyThrust demonstration execution'), ('P21', 'pytest collection and execution')]:
    REPORT['probes'][identifier] = {'description': description, 'execution': 'unperformed', 'reason': 'Deferred to a separate inspected-backend probe; not inferred from P00 imports'}

AFTER = {name: manifest(root) for name, root in [('6dof_hopper', SOURCE), ('PendulumControlProject', PENDULUM)]}
changes = {}
for name in BEFORE:
    old, new = BEFORE[name]['files'], AFTER[name]['files']
    changes[name] = {'added': sorted(set(new) - set(old)), 'removed': sorted(set(old) - set(new)), 'modified': sorted(path for path in set(old) & set(new) if old[path] != new[path])}
unchanged = all(not paths for delta in changes.values() for paths in delta.values())
REPORT['probes']['M0'] = {'description': 'Before/after file hashes, sizes and mtimes over recorded manifest scope', 'execution': 'returned', 'result': {'source_tree_unchanged': unchanged, 'changes': changes, 'excluded': {name: BEFORE[name]['excluded_directories'] for name in BEFORE}}}
REPORT['utc_finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
write_json(OUT / 'source_manifest_after.json', AFTER)
write_json(OUT / 'source_index.json', INDEX)
write_json(OUT / 'probe_results_core.json', REPORT)
CACHE.cleanup()
print('Raw diagnostic artifacts saved; no integrated or physical acceptance asserted.', file=sys.stderr)
