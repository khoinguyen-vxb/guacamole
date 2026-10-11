"""PDR r12 interpreter/dependency/import observations, not verification.

Run through Guacamole execute, repository='6dof_hopper', workdir='.', argv:
  python -B software/pdr_r12_plant/capability_probe_r12_01.py
Declare output:
  software/pdr_r12_plant/capability_report_r12_01.json

Uses the fresh r12 source inventory. Imports only dependency modules and
inspected original modules; does not call plant functions, patch imports,
install packages, run controllers or modify supplied/historical sources.
An exit code of zero means the diagnostic report was written, not that all
imports succeeded, analytical tests passed or a physical model is valid.
"""
from __future__ import annotations

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
MANIFEST = OUT / 'source_inventory_r12_01.json'
REPORT = OUT / 'capability_report_r12_01.json'
EXPECTED_MANIFEST_SHA256 = 'bb0b8971ec6eefd8db186ac73f89e5c4b3f26e7791cba59a986f673486fb282b'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(manifest):
    """Measure only inventoried files; never import or rewrite them."""
    values = {}
    for item in manifest['files']:
        root = Path(manifest['roots'][item['root']]['path']).resolve()
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid inventory-relative path')
        path = root / relative
        key = item['root'] + '/' + item['path']
        if key in values:
            raise ValueError('Duplicate inventory entry: ' + key)
        resolved = path.resolve()
        if root not in resolved.parents or path.is_symlink():
            raise ValueError('Inventory path escapes root or became a symlink: ' + key)
        values[key] = digest(path) if path.is_file() else None
    return values


def attempt_import(name, *, category, expected_path=None):
    observation = {'module': name, 'category': category, 'status': 'not_attempted'}
    try:
        if expected_path is not None:
            spec = importlib.util.find_spec(name)
            origin = None if spec is None else spec.origin
            observation['resolved_origin'] = origin
            if origin is None or Path(origin).resolve() != expected_path.resolve():
                observation['status'] = 'rejected_unexpected_module_origin'
                print(name + ': unexpected or missing module origin', file=sys.stderr)
                return observation
        module = importlib.import_module(name)
        origin = getattr(module, '__file__', None)
        observation['loaded_origin'] = origin
        if expected_path is not None and (
            origin is None or Path(origin).resolve() != expected_path.resolve()
        ):
            observation['status'] = 'rejected_unexpected_loaded_origin'
            print(name + ': unexpected loaded module origin', file=sys.stderr)
            return observation
        observation['status'] = 'imported'
    except Exception as error:
        observation.update(
            status='import_failed',
            exception_type=type(error).__name__,
            message=str(error)[:1000],
        )
        print(name + ': ' + observation['exception_type'] + ': '
              + observation['message'], file=sys.stderr)
    return observation


def main():
    if REPORT.exists() or REPORT.is_symlink():
        raise FileExistsError('Preserve existing report: ' + str(REPORT))
    raw = MANIFEST.read_bytes()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    if manifest_hash != EXPECTED_MANIFEST_SHA256:
        raise ValueError('Fresh inventory changed; review it before capability execution')
    manifest = json.loads(raw)
    if manifest['schema'] != 'pdr_r12_static_source_audit_v1':
        raise ValueError('Unsupported source inventory schema')
    root = Path(manifest['roots']['original_hopper']['path']).resolve()
    for record in manifest['roots'].values():
        audited_root = Path(record['path']).resolve()
        if OUT == audited_root or audited_root in OUT.parents:
            raise ValueError('Diagnostic outputs must not be inside audited roots')

    baseline = {
        item['root'] + '/' + item['path']: item['sha256']
        for item in manifest['files']
    }
    before = snapshot(manifest)
    changed_before = sorted(key for key in baseline if before[key] != baseline[key])
    versions = {}
    for distribution in ('numpy', 'scipy', 'pytest', 'matplotlib', 'openmdao', 'black', 'uv'):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None

    # Dependency capability remains distinct from original source defects.
    observations = [
        attempt_import(name, category='dependency')
        for name in ('numpy', 'scipy', 'scipy.integrate', 'pytest')
    ]
    original_modules = (
        ('helpers.math', 'helpers/math.py'),
        ('simulation.state', 'simulation/state.py'),
        ('propulsion.propulsion', 'propulsion/propulsion.py'),
        ('propulsion.propeller', 'propulsion/propeller.py'),
        ('chassis.hopper', 'chassis/hopper.py'),
        ('aero.aero', 'aero/aero.py'),
        ('simulation.simulation', 'simulation/simulation.py'),
    )
    if changed_before:
        print('Inventoried sources differ from the audit; original imports withheld.',
              file=sys.stderr)
        observations.extend({
            'module': name,
            'category': 'original_source_module',
            'status': 'withheld_source_baseline_changed',
        } for name, _ in original_modules)
    else:
        for name, relative in original_modules:
            observations.append(attempt_import(
                name, category='original_source_module', expected_path=root / relative,
            ))

    after = snapshot(manifest)
    changed_during = sorted(key for key in before if after[key] != before[key])
    changed_after = sorted(key for key in baseline if after[key] != baseline[key])
    report = {
        'schema': 'pdr_r12_capability_observations_v1',
        'observed_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'diagnostic_observations_only',
        'work_plan': '66c7448f443f44ac9a016a1b384593a2 revision 1',
        'interpreter': {
            'executable': sys.executable,
            'version': platform.python_version(),
            'implementation': platform.python_implementation(),
            'declared_project_requirement': 'Python >=3.13',
            'meets_declared_python_minimum': sys.version_info[:2] >= (3, 13),
            'dont_write_bytecode': sys.dont_write_bytecode,
        },
        'installed_distribution_versions': versions,
        'import_observations': observations,
        'original_import_workarounds_applied': False,
        'original_module_imports_attempted': not bool(changed_before),
        'original_plant_functions_executed': False,
        'repaired_plant_imports_attempted': False,
        'numerical_plant_execution_attempted': False,
        'controller_executed': False,
        'analytical_verification': 'unperformed',
        'vehicle_physical_validity': 'not_assessed',
        'review_acceptance': 'not_claimed',
        'source_preservation': {
            'inventory_path': 'software/pdr_r12_plant/source_inventory_r12_01.json',
            'inventory_sha256': manifest_hash,
            'measured_file_count': len(baseline),
            'changed_before_imports': changed_before,
            'changed_during_imports': changed_during,
            'changed_from_baseline_after_imports': changed_after,
            'scope': 'Only existing files named by the fresh r12 inventory.',
        },
        'diagnostic_program_sha256': digest(Path(__file__)),
        'limitations': [
            'Distribution metadata is not proof of importability, compatible APIs or numerical correctness.',
            'Only NumPy, SciPy, scipy.integrate and pytest dependency imports are attempted.',
            'Matplotlib, OpenMDAO, Black and uv are metadata observations only.',
            'Original-module import failures are separate from dependency availability.',
            'The audited top-level State import is not repaired or bypassed for this diagnostic.',
            'Successful imports do not establish a runnable original plant or a valid physical model.',
            'No original plant-function failure reproduction or repaired analytical test occurs.',
            'Source preservation excludes unlisted/new files, caches, environments and binary/data files.',
            'No environment dump, installation changes or historical-output writes are performed.',
            'Missing required installations must be requested through the Chief, not installed here.',
        ],
    }
    with REPORT.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(report, allow_nan=False))


if __name__ == '__main__':
    main()
