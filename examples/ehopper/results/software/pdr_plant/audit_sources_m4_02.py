"""Read-only source/caller reconciliation; no target imports or verification.

Authority: system_model:system@4; work plan
99f7bb629eef45b89fa38d27c803868c@1; interface
88561ff8b3ba4e8286cebd95a93e3b08@1.
Preserves audit_sources_01.py and its historical inventory unchanged.
Run with python -B from the results sandbox. Declare OUTPUT_NAMES.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

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
EXCLUDED = {'.git', '.venv', 'venv', 'env', '__pycache__', '.pytest_cache',
            '.mypy_cache', '.ruff_cache', 'node_modules'}
OUTPUT_NAMES = ('source_inventory_m4_02.json', 'caller_index_m4_02.md',
                'remaining_source_review_m4_02.md', 'preservation_delta_m4_02.json')
AUTHORITY = {
    'system_model': {'kind': 'system_model', 'id': 'system', 'revision': 4,
        'sha256': 'e89e68e192965d8e012cc1213e59c02610f55042ad26d7392ebef0401237ee75'},
    'work_plan': {'kind': 'decision', 'id': '99f7bb629eef45b89fa38d27c803868c', 'revision': 1,
        'sha256': 'e5af8e2f56f7c851b65518b129f39550be73911f56461279cbbb1e85e1cdd5f0'},
    'interface': {'kind': 'decision', 'id': '88561ff8b3ba4e8286cebd95a93e3b08', 'revision': 1,
        'sha256': 'ad6662afab9685585264c86e052c246996d23f4369c6432b56094a42a9187c04'},
}
# These paths have already been returned by readers. This set is a reading
# aid, not a claim of runtime verification or a reason to skip hashing.
RETURNED_ORIGINAL = {
    'helpers/math.py', 'simulation/state.py', 'simulation/simulation.py',
    'chassis/hopper.py', 'propulsion/propulsion.py', 'propulsion/propeller.py',
}
RETURNED_RECOVERED = {
    'repaired_hopper_r12/' + p for p in RETURNED_ORIGINAL
} | {'repaired_hopper_r12/propulsion/actuators.py',
     'repaired_hopper_r12/simulation/environment.py'}
TARGETS = {
    'Simulation', 'State', 'Hopper', 'Propulsion', 'Propellor',
    'MassProperties', 'AssemblyKinematics', 'CoaxialGeometry',
    'CoaxialConditions', 'CoaxialPerformance', 'PropulsionEvaluation',
    'AppliedLoad', 'ExternalWrench', 'HeldCommand', 'ActuatorState',
    'ActuatorEvaluation', 'LagParameters', 'LaggedActuators',
    'EnvironmentSample', 'PlantEvaluation', 'IntegrationFailure',
    'trajectory_ode', 'solve_ode', 'update_state', 'from_vector',
    'from_euler', 'pack_state', 'unpack_state', 'euler_to_quaternion',
    'quarternion_to_dcm', 'quaternion_to_dcm', 'quaternion_derivative',
    'fixed_datum_kinematics', 'cad_point_to_body_datum_m',
    'body_datum_point_to_cad_mm', 'cad_inertia_to_body_kg_m2',
    'get_mass', 'get_local_cg', 'get_thrust_and_moment',
    'mass_properties', 'resolve_applied_loads',
    'angular_acceleration_B_rad_s2', 'application_points_B0_m',
    'application_point_rates_B0_m_s', 'hub_velocities_relative_air_M_m_s',
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return (prefix + '.' if prefix else '') + node.attr
    return ast.dump(node, include_attributes=False)[:240]


class Index(ast.NodeVisitor):
    def __init__(self):
        self.scope, self.definitions, self.imports, self.calls = [], [], [], []

    def definition(self, node, kind):
        self.definitions.append({'kind': kind, 'name': '.'.join(self.scope + [node.name]),
                                 'line': node.lineno, 'end_line': node.end_lineno})
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node):
        self.definition(node, 'class')

    def visit_FunctionDef(self, node):
        self.definition(node, 'function')

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node):
        self.imports.append({'line': node.lineno, 'text': ast.unparse(node)})

    visit_ImportFrom = visit_Import

    def visit_Call(self, node):
        name = dotted(node.func)
        self.calls.append({'line': node.lineno, 'end_line': node.end_lineno,
                           'scope': '.'.join(self.scope) or '<module>',
                           'callee_spelling': name,
                           'target_spelling_match': name.rsplit('.', 1)[-1] in TARGETS})
        self.generic_visit(node)


def main():
    paths = [HERE / name for name in OUTPUT_NAMES]
    if any(p.exists() for p in paths):
        raise FileExistsError('Preserve existing outputs; use a new audit version')
    old_path = HERE / 'source_inventory_01.json'
    old = json.loads(old_path.read_text(encoding='utf-8'))
    if not isinstance(old.get('files'), list):
        raise ValueError('Historical inventory lacks the expected files list')
    previous = {(r['root'], r['path']): r['sha256'] for r in old['files']}
    rows, omissions, review, index_lines = [], [], [], []
    root_status = {}
    review_budget = 256000
    for label, root in ROOTS.items():
        root_status[label] = {'path': str(root), 'exists': root.is_dir(),
                              'symlink': root.is_symlink()}
        if not root.is_dir() or root.is_symlink():
            omissions.append({'root': label, 'path': '.', 'reason': 'unavailable or symlink root'})
            continue
        for current, dirs, names in os.walk(root, followlinks=False):
            current = Path(current)
            keep = []
            for name in sorted(dirs):
                p = current / name
                if name in EXCLUDED or p.is_symlink():
                    omissions.append({'root': label, 'path': p.relative_to(root).as_posix(),
                                      'reason': 'excluded directory or un-followed symlink'})
                else:
                    keep.append(name)
            dirs[:] = keep
            for name in sorted(names):
                p = current / name
                rel = p.relative_to(root).as_posix()
                if p.is_symlink() or not p.is_file():
                    omissions.append({'root': label, 'path': rel, 'reason': 'not a regular non-symlink file'})
                    continue
                if len(rows) >= 20000:
                    raise RuntimeError('File bound exceeded; no complete inventory written')
                before = p.stat()
                row = {'root': label, 'path': rel, 'size_bytes': before.st_size, 'sha256': sha(p)}
                text = None
                if p.suffix == '.py':
                    if before.st_size > 2000000:
                        row['static_index_error'] = 'Exceeds 2000000-byte parse bound'
                    else:
                        try:
                            text = p.read_text(encoding='utf-8-sig')
                            visitor = Index()
                            visitor.visit(ast.parse(text, filename=str(p)))
                            row.update(definitions=visitor.definitions, imports=visitor.imports,
                                       calls=visitor.calls)
                        except (SyntaxError, UnicodeError) as exc:
                            row['static_index_error'] = type(exc).__name__ + ': ' + str(exc)
                after = p.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError('Source changed during read: ' + str(p))
                rows.append(row)
                matches = [c for c in row.get('calls', []) if c['target_spelling_match']]
                plant_file = (label == 'original_hopper' and not rel.startswith('PyThrust/')) or label == 'recovered_previous_run'
                if p.suffix == '.py' and (plant_file or matches):
                    index_lines += [f'## {label}/{rel}', f'SHA256 {row["sha256"]}', '']
                    for imp in row.get('imports', []):
                        index_lines.append(f'Import L{imp["line"]}: {imp["text"]}')
                    for call in row.get('calls', []):
                        index_lines.append(f'L{call["line"]}-{call["end_line"]} | {call["scope"]} | {call["callee_spelling"]}')
                    if 'static_index_error' in row:
                        index_lines.append('INDEX GAP: ' + row['static_index_error'])
                    index_lines.append('')
                returned = ((label == 'original_hopper' and rel in RETURNED_ORIGINAL)
                            or (label == 'recovered_previous_run' and rel in RETURNED_RECOVERED))
                unchanged = previous.get((label, rel)) == row['sha256']
                if text is not None and (plant_file or matches) and not (returned and unchanged):
                    count = min(16000, len(text), max(0, review_budget))
                    review_budget -= count
                    review += [f'## {label}/{rel}', f'Origin: {p}', f'SHA256: {row["sha256"]}',
                               f'UTF-8 text character interval [0,{count}); total characters {len(text)}.',
                               '```python', text[:count], '```',
                               ('Complete text returned.' if count == len(text) else
                                f'READING GAP: continue read_text at character offset {count}.'), '']
    current_hashes = {(r['root'], r['path']): r['sha256'] for r in rows}
    changed = [{'root': k[0], 'path': k[1], 'before_sha256': previous[k],
                'current_sha256': current_hashes[k]} for k in sorted(previous.keys() & current_hashes.keys())
               if previous[k] != current_hashes[k]]
    delta = {'schema': 'hopper.source_preservation_delta/1', 'authority': AUTHORITY,
             'historical_baseline_path': str(old_path), 'historical_baseline_sha256': sha(old_path),
             'changed': changed,
             'added': [{'root': k[0], 'path': k[1]} for k in sorted(current_hashes.keys() - previous.keys())],
             'missing': [{'root': k[0], 'path': k[1]} for k in sorted(previous.keys() - current_hashes.keys())],
             'limitations': ['Content comparison only for inventoried regular files.',
                            'Does not establish cleanliness before the historical baseline.',
                            'Excluded directories, environments and symlinks are outside this comparison.',
                            'This diagnostic is not a VerificationResult.']}
    inventory = {'schema': 'hopper.source_inventory/2', 'authority': AUTHORITY,
                 'created_utc': datetime.now(timezone.utc).isoformat(), 'roots': root_status,
                 'files': rows, 'omissions': omissions, 'excluded_directory_names': sorted(EXCLUDED),
                 'limitations': ['All parsed call spellings are retained; runtime edges are not resolved.',
                                'Aliases, dynamic dispatch, generated code and external callers require review.',
                                'No target imports, dependency tests, plant execution or physical tests occurred.']}
    payloads = [json.dumps(inventory, indent=2),
                '# Current static caller reconciliation\n\nModel r4; static evidence only.\n\n' + '\n'.join(index_lines),
                '# Remaining source inspection excerpts\n\nModel r4. Returned text must be reviewed; inclusion is not inspection acceptance.\n\n' + '\n'.join(review),
                json.dumps(delta, indent=2)]
    for path, content in zip(paths, payloads):
        with path.open('x', encoding='utf-8') as stream:
            stream.write(content + '\n')
    print(json.dumps({'files_inventoried': len(rows), 'changed_files': len(changed),
                      'outputs': [str(p.relative_to(SANDBOX)) for p in paths],
                      'target_modules_imported': False, 'verification_performed': False}))


if __name__ == '__main__':
    main()
