"""PDR-R9 dependency/import diagnostics; not physical verification.

Invoke through execute with repository='6dof_hopper', workdir='.', and:
  [python, -B, software/pdr_r9_plant/capability_probe_01.py]
Declare output software/pdr_r9_plant/capability_report_01.json.

Original modules are imported but their plant functions are not executed.
This script never installs dependencies, repairs modules or runs controllers.
"""
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
MANIFEST = OUT / 'source_inventory.json'
REPORT = OUT / 'capability_report_01.json'
if REPORT.exists() or REPORT.is_symlink():
    raise FileExistsError('Preserve existing diagnostic report: ' + str(REPORT))
manifest_bytes = MANIFEST.read_bytes()
manifest = json.loads(manifest_bytes)
ROOT = Path(manifest['roots']['6dof_hopper']['path']).resolve()


def snapshot():
    """Only the files named by the retained source inventory are measured."""
    result = {}
    for item in manifest['files']:
        root = Path(manifest['roots'][item['repository']]['path']).resolve()
        path = root / item['path']
        key = item['repository'] + '/' + item['path']
        result[key] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


baseline = {item['repository'] + '/' + item['path']: item['sha256']
            for item in manifest['files']}
before = snapshot()
changed_before = sorted(key for key in baseline if before[key] != baseline[key])
observations = []


def attempt_import(name, expected_path=None):
    entry = {'module': name, 'status': 'not_attempted'}
    try:
        if expected_path is not None:
            spec = importlib.util.find_spec(name)
            origin = None if spec is None else spec.origin
            entry['resolved_origin'] = origin
            if origin is None or Path(origin).resolve() != expected_path.resolve():
                entry['status'] = 'rejected_unexpected_module_origin'
                observations.append(entry)
                return
        module = importlib.import_module(name)
        entry.update(status='imported', origin=getattr(module, '__file__', None))
    except Exception as error:
        entry.update(status='import_failed', exception_type=type(error).__name__,
                     message=str(error)[:500])
        print(name + ': ' + entry['exception_type'] + ': ' + entry['message'], file=sys.stderr)
    observations.append(entry)


versions = {}
for distribution in ('numpy', 'scipy', 'pytest', 'matplotlib', 'openmdao', 'black', 'uv'):
    try:
        versions[distribution] = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        versions[distribution] = None

# Do not import changed original sources under an obsolete audit baseline.
if not changed_before:
    for name in ('numpy', 'scipy', 'scipy.integrate', 'pytest'):
        attempt_import(name)
    for name, relative_path in (
        ('helpers.math', 'helpers/math.py'),
        ('simulation.state', 'simulation/state.py'),
        ('propulsion.propulsion', 'propulsion/propulsion.py'),
        ('propulsion.propeller', 'propulsion/propeller.py'),
        ('chassis.hopper', 'chassis/hopper.py'),
        ('aero.aero', 'aero/aero.py'),
        ('simulation.simulation', 'simulation/simulation.py'),
    ):
        attempt_import(name, ROOT / relative_path)
else:
    print('Original-source baseline differs; imports withheld pending review.', file=sys.stderr)

after = snapshot()
changed_during = sorted(key for key in before if before[key] != after[key])
changed_from_baseline = sorted(key for key in baseline if after[key] != baseline[key])
report = {
    'schema': 'pdr_r9_import_capability_observations_v1',
    'observed_at_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'diagnostic_observations_only',
    'interpreter': {
        'executable': sys.executable,
        'version': platform.python_version(),
        'implementation': platform.python_implementation(),
        'declared_project_requirement': 'Python >=3.13',
        'dont_write_bytecode': sys.dont_write_bytecode,
    },
    'installed_distribution_versions': versions,
    'import_observations': observations,
    'source_inventory': {
        'path': 'software/pdr_r9_plant/source_inventory.json',
        'sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'measured_file_count': len(baseline),
        'scope': 'Only files named in the retained source inventory; no whole-checkout claim.',
        'changed_before_imports': changed_before,
        'changed_during_imports': changed_during,
        'changed_from_baseline_after_imports': changed_from_baseline,
    },
    'plant_functions_executed': False,
    'controller_executed': False,
    'numerical_verification': 'unperformed',
    'physical_acceptance': 'not_assessed',
    'limitations': [
        'Distribution metadata does not establish importability or numerical correctness.',
        'Successful imports do not establish a working plant or valid physical model.',
        'Original Simulation import may fail on its audited top-level State import; no workaround is injected.',
        'Source preservation observations exclude unlisted files, new files, caches, environments and binary/data files.',
        'Matplotlib, OpenMDAO, Black and uv versions are metadata observations only; their imports are not tested here.',
        'No installation changes are attempted; missing required dependencies need a human installation request.',
    ],
}
with REPORT.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps(report, allow_nan=False))
