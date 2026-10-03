#!/usr/bin/env python3
"""PDR backend diagnostics, not a plant repair or an acceptance verifier.

Use Guacamole execute with repository='6dof_hopper', command[0]='python',
-B, and workdir='software/pdr_r4_plant_control'. Declare these outputs:
  software/pdr_r4_plant_control/results_backend/source_manifest_before.json
  software/pdr_r4_plant_control/results_backend/source_manifest_after.json
  software/pdr_r4_plant_control/results_backend/probe_results_backend.json

Imports, subprocess outcomes and raw output are recorded separately. A later
editable verify_command program must assess these artifacts. No installation,
plant repair, controller implementation, tuning or physical test is performed.
"""
import sys
sys.dont_write_bytecode = True

import contextlib
import datetime
import hashlib
import importlib
import importlib.metadata
import inspect
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import traceback

TASK = Path(__file__).resolve().parent
SOURCE = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper')
PYTHRUST = SOURCE / 'PyThrust'
OUT = TASK / 'results_backend'


def save(path, value):
    if not path.resolve().is_relative_to(TASK):
        raise ValueError('Output escaped task directory')
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def manifest(root):
    files, excluded = {}, []
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
                continue
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1048576), b''):
                    digest.update(block)
            stat = path.stat()
            files[relative] = {'sha256': digest.hexdigest(), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    return {'root': str(root), 'exists': root.is_dir(), 'excluded_directories': sorted(excluded), 'files': files}


def attempt(description, operation):
    stdout, stderr = io.StringIO(), io.StringIO()
    result = {'description': description, 'acceptance_assessed': False}
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result['result'] = operation()
        result['execution'] = 'returned'
    except Exception as exc:
        result.update(execution='raised', exception=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
    result['captured_stdout'] = stdout.getvalue()
    result['captured_stderr'] = stderr.getvalue()
    return result


def module_imports():
    results = {}
    names = ['pythrust', 'pythrust.battery', 'pythrust.propellers', 'pythrust.propulsion', 'pythrust.propulsion.solver']
    for name in names:
        def operation(module_name=name):
            module = importlib.import_module(module_name)
            filename = getattr(module, '__file__', None)
            return {
                'imported': True,
                'file': filename,
                'resolved_file': str(Path(filename).resolve()) if filename else None,
                'from_supplied_pythrust': bool(filename and Path(filename).resolve().is_relative_to(PYTHRUST.resolve())),
                'version': getattr(module, '__version__', None),
            }
        results[name] = attempt('Actual import of ' + name, operation)
    return {'sys_path': list(sys.path), 'modules': results}


def database_probe():
    from pythrust.propellers import PropellerDatabase
    from pythrust.propulsion import PropulsionSolver
    data_directory = PYTHRUST / 'data/propellers/apc_202602'
    database = PropellerDatabase()
    loaded = database.load(data_directory, strict=False)
    identifiers = database.list_propellers()
    entry = database.get('APC_13x6.5E')
    sample = None
    if entry is not None:
        ct, cp = entry.get_coefficients(6000.0, 0.0)
        sample = {
            'id': entry.metadata.id,
            'diameter_m': float(entry.diameter_m),
            'pitch_m': float(entry.pitch_m),
            'blade_count': int(entry.metadata.blade_count),
            'rpm_levels': [float(value) for value in entry.rpm_levels],
            'query_rpm': 6000.0,
            'advance_ratio': 0.0,
            'ct_dimensionless': float(ct),
            'cp_dimensionless': float(cp),
        }
    return {
        'data_directory': str(data_directory),
        'data_directory_exists': data_directory.is_dir(),
        'strict_loader': False,
        'load_return': bool(loaded),
        'is_loaded': bool(database.is_loaded),
        'propeller_count': int(database.propeller_count),
        'listed_identifier_count': len(identifiers),
        'sample_entry': sample,
        'solver_signature': str(inspect.signature(PropulsionSolver.solve_operating_point)),
        'scope': 'Database access and coefficient lookup only; not dataset validation, propulsion acceptance or coaxial calibration',
    }


def run_process(command, environment, timeout_s):
    result = {'command': command, 'cwd': str(TASK), 'timeout_s': timeout_s, 'timed_out': False, 'acceptance_assessed': False}
    try:
        process = subprocess.run(command, cwd=TASK, env=environment, capture_output=True, text=True, timeout=timeout_s, check=False)
        result.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        result.update(returncode=None, timed_out=True, stdout=decode(exc.stdout), stderr=decode(exc.stderr))
    return result


def main():
    if Path.cwd().resolve() != TASK:
        raise RuntimeError('Run from the sandbox task directory')
    if TASK.is_relative_to(SOURCE.resolve()):
        raise RuntimeError('Task directory must be outside the source checkout')
    if not SOURCE.is_dir():
        raise RuntimeError('Supplied source checkout is unavailable')
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        'schema': 'pdr_r4_plant_control.backend_diagnostics/1',
        'stage': 'PDR diagnosis only',
        'utc_started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'probe_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_root': str(SOURCE),
        'pythrust_root': str(PYTHRUST),
        'backend': {
            'repository_selection': '6dof_hopper; selection must also be checked against the execute job inputs',
            'sys_executable': sys.executable,
            'resolved_executable': str(Path(sys.executable).resolve()),
            'python_version': sys.version,
            'implementation': platform.python_implementation(),
            'prefix': sys.prefix,
            'base_prefix': sys.base_prefix,
            'cwd': str(Path.cwd()),
            'original_sys_path': list(sys.path),
            'bytecode_disabled': sys.dont_write_bytecode,
        },
        'probes': {},
        'limitations': [
            'No integrated hopper, sampled controller, mission or physical test is performed.',
            'The original demonstration uses illustrative isolated-rotor parameters, not a selected or calibrated coaxial vehicle.',
            'Only the hopper test/ directory is passed to pytest; the nested PyThrust test suite is not assessed.',
            'A zero subprocess return code is process evidence only, not physical acceptance.',
            'A pytest no-tests-collected outcome is not a passing test suite.',
            'The non-strict database loader can skip invalid entries; a successful load does not validate the whole dataset.',
            'The earlier core probe import-path error is not repeated: no interpreter site-package paths are filtered out.',
            'Source manifest coverage excludes .git and virtual-environment directories, and includes pre-existing bytecode caches.',
        ],
    }
    before = manifest(SOURCE)
    save(OUT / 'source_manifest_before.json', before)
    original_path = list(sys.path)
    original_environment = os.environ.copy()
    try:
        with tempfile.TemporaryDirectory(prefix='backend_probe_cache_', dir=TASK) as cache:
            cache = Path(cache)
            policy = {
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                'MPLBACKEND': 'Agg',
                'MPLCONFIGDIR': str(cache / 'matplotlib'),
                'XDG_CACHE_HOME': str(cache / 'xdg'),
                'NUMBA_CACHE_DIR': str(cache / 'numba'),
                'OPENMDAO_REPORTS': '0',
                'TMPDIR': str(cache),
            }
            os.environ.update(policy)
            report['backend']['cache_policy'] = policy
            try:
                report['backend']['setuav_pythrust_distribution_version'] = importlib.metadata.version('setuav-pythrust')
            except importlib.metadata.PackageNotFoundError:
                report['backend']['setuav_pythrust_distribution_version'] = None

            # Preserve the natural repository-selected interpreter import path.
            report['probes']['P19_default_imports'] = module_imports()

            # Assess explicit checkout resolution separately, without pretending
            # it proves a normal installation. Clear only this package's modules.
            for name in list(sys.modules):
                if name == 'pythrust' or name.startswith('pythrust.'):
                    del sys.modules[name]
            sys.path.insert(0, str(PYTHRUST))
            importlib.invalidate_caches()
            report['probes']['P19_explicit_checkout_imports'] = module_imports()
            report['probes']['P19_database'] = attempt('Load supplied database and inspect solver interface', database_probe)
            sys.path[:] = original_path

            environment = os.environ.copy()
            # Clear pytest argument injection, preserve PYTHONPATH and all selected
            # interpreter dependency paths. No installation commands are run.
            environment['PYTEST_ADDOPTS'] = ''
            demo_command = [sys.executable, '-B', str(SOURCE / 'test/test_pythrust.py')]
            report['probes']['P20'] = attempt(
                'Execute the original supplied demonstration from a sandbox cwd',
                lambda: run_process(demo_command, environment, 180.0),
            )
            pytest_command = [
                sys.executable, '-B', '-m', 'pytest',
                '-p', 'no:cacheprovider', '--import-mode=importlib',
                '--rootdir', str(TASK), '--confcutdir', str(TASK),
                '-o', 'addopts=', '-q', str(SOURCE / 'test'),
            ]
            def pytest_operation():
                result = run_process(pytest_command, environment, 180.0)
                result['pytest_returncode'] = result['returncode']
                result['suite_scope'] = str(SOURCE / 'test')
                result['nested_pythrust_suite_executed'] = False
                return result
            report['probes']['P21'] = attempt('Actually invoke pytest on the hopper test directory', pytest_operation)
    except Exception as exc:
        report['harness_exception'] = {'exception': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    finally:
        sys.path[:] = original_path
        os.environ.clear()
        os.environ.update(original_environment)
        after = manifest(SOURCE)
        save(OUT / 'source_manifest_after.json', after)
        old, new = before['files'], after['files']
        changes = {
            'added': sorted(set(new) - set(old)),
            'removed': sorted(set(old) - set(new)),
            'modified': sorted(name for name in set(old) & set(new) if old[name] != new[name]),
        }
        report['probes']['M0'] = {
            'description': 'Source file hash, size and mtime comparison within the stated manifest scope',
            'changes': changes,
            'source_tree_unchanged': not any(changes.values()),
            'excluded_directories': before['excluded_directories'],
        }
        report['utc_finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(OUT / 'probe_results_backend.json', report)
    for name, result in report['probes'].items():
        print(name + ': diagnostics recorded; inspect the JSON artifact', file=sys.stderr)
    print('No integrated or physical acceptance asserted.', file=sys.stderr)


if __name__ == '__main__':
    main()
