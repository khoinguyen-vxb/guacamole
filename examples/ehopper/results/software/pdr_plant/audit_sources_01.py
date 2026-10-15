"""Read-only source inventory and candidate caller discovery.

Current authority: system revision 1; work plan
b8988137b7274bddb05c87f7884c81fd revision 1.
No target module is imported or executed. No verification is claimed.
Run from the results sandbox with python -B. Declare both output files.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parents[1]
PROJECT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper')
ROOTS = {
    'original_hopper': PROJECT / 'tooling/6dof_hopper',
    'pendulum_reference': PROJECT / 'tooling/PendulumControlProject',
    'recovered_previous_run': SANDBOX / 'previous_run',
    'archived_notes': PROJECT / 'context/previous_run',
}
EXCLUDED_DIR_NAMES = {
    '.git', '.venv', 'venv', 'env', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'node_modules',
}
MAX_FILES = 20000
MAX_PYTHON_BYTES = 2000000
TARGET_NAMES = {
    'Simulation', 'State', 'Hopper', 'Propulsion', 'Propellor', 'Propeller',
    'MassProperties', 'AssemblyKinematics', 'CoaxialGeometry',
    'CoaxialConditions', 'CoaxialPerformance', 'PropulsionEvaluation',
    'AppliedLoad', 'ExternalWrench', 'HeldCommand', 'ActuatorState',
    'ActuatorEvaluation', 'LagParameters', 'LaggedActuators',
    'EnvironmentSample', 'EnvironmentProvider', 'PlantEvaluation',
    'ModelDomainError', 'IntegrationFailure',
    'trajectory_ode', 'solve_ode', 'update_state', 'as_vector', 'from_vector',
    'from_euler', 'initial_vector', 'pack_state', 'unpack_state',
    'euler_to_quaternion', 'quarternion_to_dcm', 'quaternion_to_dcm',
    'quaternion_derivative', 'fixed_datum_kinematics',
    'mass_properties', 'get_mass', 'mass', 'CG', 'inertia',
    'get_thrust_and_moment', 'get_local_cg', 'determine_at_point',
    'resolve_applied_loads', 'angular_acceleration_B_rad_s2',
    'application_points_B0_m', 'hub_velocities_relative_air_M_m_s',
    'coaxial_conditions', 'validate_spin_kinematics',
    'build_fixture', 'initial_snapshots', 'solver_options',
}


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return (prefix + '.' if prefix else '') + node.attr
    return ''


class IndexVisitor(ast.NodeVisitor):
    def __init__(self, text):
        self.text = text
        self.scope = []
        self.definitions = []
        self.imports = []
        self.candidates = []

    def visit_ClassDef(self, node):
        self.definitions.append({
            'kind': 'class', 'name': '.'.join(self.scope + [node.name]),
            'line': node.lineno, 'end_line': node.end_lineno,
        })
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self.definitions.append({
            'kind': 'function', 'name': '.'.join(self.scope + [node.name]),
            'line': node.lineno, 'end_line': node.end_lineno,
        })
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node):
        self.imports.append({'line': node.lineno, 'text': ast.unparse(node)})

    visit_ImportFrom = visit_Import

    def visit_Call(self, node):
        name = dotted(node.func)
        if name and name.rsplit('.', 1)[-1] in TARGET_NAMES:
            segment = ast.get_source_segment(self.text, node) or name
            self.candidates.append({
                'line': node.lineno, 'end_line': node.end_lineno,
                'scope': '.'.join(self.scope) or '<module>',
                'callee_spelling': name,
                'source_excerpt': segment[:1200],
                'excerpt_truncated': len(segment) > 1200,
            })
        self.generic_visit(node)


def main():
    outputs = [HERE / 'source_inventory_01.json', HERE / 'candidate_callers_01.md']
    if any(path.exists() for path in outputs):
        raise FileExistsError('Use a new version; refusing to overwrite audit outputs')
    files = []
    omissions = []
    root_status = {}
    for label, root in ROOTS.items():
        root_status[label] = {'path': str(root), 'exists': root.is_dir()}
        if not root.is_dir():
            omissions.append({'root': label, 'path': '.', 'reason': 'root unavailable'})
            continue
        if root.is_symlink():
            omissions.append({'root': label, 'path': '.', 'reason': 'symlink root not followed', 'target': os.readlink(root)})
            continue
        for current, directories, names in os.walk(root, followlinks=False):
            current = Path(current)
            kept = []
            for name in sorted(directories):
                path = current / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    omissions.append({'root': label, 'path': relative, 'reason': 'directory symlink not followed', 'target': os.readlink(path)})
                elif name in EXCLUDED_DIR_NAMES:
                    omissions.append({'root': label, 'path': relative, 'reason': 'explicit excluded directory'})
                else:
                    kept.append(name)
            directories[:] = kept
            for name in sorted(names):
                path = current / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    omissions.append({'root': label, 'path': relative, 'reason': 'file symlink not followed', 'target': os.readlink(path)})
                    continue
                if not path.is_file():
                    omissions.append({'root': label, 'path': relative, 'reason': 'not a regular file'})
                    continue
                if len(files) >= MAX_FILES:
                    raise RuntimeError('Inventory file bound exceeded; no complete inventory written')
                before = path.stat()
                row = {'root': label, 'path': relative, 'size_bytes': before.st_size, 'sha256': digest(path)}
                if path.suffix == '.py':
                    if before.st_size > MAX_PYTHON_BYTES:
                        row['static_index_error'] = 'Python source exceeds explicit size bound'
                    else:
                        try:
                            text = path.read_text(encoding='utf-8-sig')
                            visitor = IndexVisitor(text)
                            visitor.visit(ast.parse(text, filename=str(path)))
                            row['definitions'] = visitor.definitions
                            row['imports'] = visitor.imports
                            row['candidate_calls'] = visitor.candidates
                        except (SyntaxError, UnicodeError) as exc:
                            row['static_index_error'] = f'{type(exc).__name__}: {exc}'
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError(f'Source changed while inventoried: {path}')
                files.append(row)
    result = {
        'schema': 'pdr_plant_source_inventory_v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'authority': {'system_revision': 1, 'work_plan': 'b8988137b7274bddb05c87f7884c81fd', 'work_plan_revision': 1},
        'purpose': 'Current read-only preservation baseline and static candidate discovery; not execution or verification evidence',
        'roots': root_status,
        'excluded_directory_names': sorted(EXCLUDED_DIR_NAMES),
        'limits': {'maximum_files': MAX_FILES, 'maximum_python_parse_bytes': MAX_PYTHON_BYTES},
        'target_names': sorted(TARGET_NAMES),
        'limitations': [
            'Only listed regular files are content-hashed; exclusions and symlinks are explicit.',
            'Baseline does not establish historical checkout cleanliness or unchanged state before this run.',
            'Calls are spelling matches, not resolved runtime edges; aliases, dynamic dispatch and generated code require further review.',
            'Source parsing does not establish imports, installed dependencies, successful execution or physical validity.',
            'Discovered caller source must be inspected before affected implementation edits.',
        ],
        'omissions': omissions,
        'files': files,
    }
    lines = ['# Current plant candidate caller inventory', '',
             'Generated by audit_sources_01.py. Static candidates only; not a complete runtime call graph.',
             'Authority: system revision 1; work plan b8988137b7274bddb05c87f7884c81fd revision 1.',
             'File hashes and full definition/import indices are in source_inventory_01.json.', '',
             '## Root availability', '']
    for label, info in root_status.items():
        lines.append(f"- {label}: exists={info['exists']}; {info['path']}")
    lines += ['', '## Candidate callers', '']
    count = 0
    for row in files:
        calls = row.get('candidate_calls', [])
        if not calls and 'static_index_error' not in row:
            continue
        lines += [f"### {row['root']}/{row['path']}", f"SHA-256: {row['sha256']}", '']
        if 'static_index_error' in row:
            lines.append('INDEX GAP: ' + row['static_index_error'])
        for call in calls:
            count += 1
            lines.append(f"- L{call['line']}–{call['end_line']} | {call['scope']} | {call['callee_spelling']}")
        lines.append('')
    lines += ['## Explicit omissions', '']
    for item in omissions:
        lines.append(f"- {item['root']}/{item['path']}: {item['reason']}")
    lines += ['', 'No target module was imported or executed. No analytical or physical test result is claimed.', '']
    outputs[0].write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    outputs[1].write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'files_inventoried': len(files), 'candidate_calls': count, 'omissions': len(omissions), 'outputs': [str(path.relative_to(SANDBOX)) for path in outputs], 'verification_performed': False}))


if __name__ == '__main__':
    main()
