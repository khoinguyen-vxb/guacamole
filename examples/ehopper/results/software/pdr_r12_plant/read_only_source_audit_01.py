"""Fresh static source/caller inventory; no plant imports or repairs.

Execute separately through Guacamole, repository='6dof_hopper':
  python -B software/pdr_r12_plant/read_only_source_audit_01.py
Use sandbox workdir='.' and declare both generated outputs:
  software/pdr_r12_plant/source_inventory_r12_01.json
  software/pdr_r12_plant/affected_caller_index_r12_01.md

Read discovered caller implementations before modifying plant code.
This program does not reproduce failures, check dependencies, integrate a
plant, verify analytical results, or establish physical acceptance.
"""
from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tokenize

ROOTS = {
    'original_hopper': Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper'),
    'pendulum_reference': Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/PendulumControlProject'),
    'historical_r9': Path('/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant'),
}
OUT = Path(__file__).resolve().parent
MANIFEST = OUT / 'source_inventory_r12_01.json'
INDEX = OUT / 'affected_caller_index_r12_01.md'
EXCLUDED = {
    '.git', '.venv', 'venv', '.tox', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'node_modules',
}
SETUP_NAMES = {'pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt', 'uv.lock', 'README.md'}
TARGETS = {
    'Simulation', 'trajectory_ode', 'solve_ode', 'State', 'update_state',
    'unpack_state', 'from_euler', 'from_vector', 'to_vector',
    'quarternion_to_dcm', 'quaternion_to_dcm', 'euler_to_quaternion',
    'normalize_quaternion', 'hamilton_product', 'quaternion_derivative',
    'gimbal_to_body', 'fixed_datum_kinematics',
    'cad_point_to_body_datum_m', 'body_datum_point_to_cad_mm',
    'cad_inertia_to_body_kg_m2',
    'Hopper', 'MassProperties', 'AssemblyKinematics', 'mass_properties',
    'Propulsion', 'Propellor', 'Propeller', 'CoaxialGeometry',
    'application_points_B0_m', 'hub_velocities_relative_air_M_m_s',
    'get_mass', 'get_local_cg', 'get_thrust_and_moment', 'mass', 'CG', 'inertia',
    'Aerodynamics', 'determine_at_point', 'solve_ivp',
    'ActuatorState', 'LagParameters', 'LaggedActuators',
    'AppliedLoad', 'CoaxialConditions', 'CoaxialPerformance',
    'EnvironmentSample', 'EnvironmentProvider',
    'initial_snapshots', 'build_fixture', 'solver_options',
    'FrozenFixtureMass', 'PrescribedFixtureEnvironment', 'SyntheticPairedMap',
    'evaluate', 'snapshot', 'sample',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover(root):
    files, symlinks = [], []
    def visit(directory):
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            relative = str(path.relative_to(root))
            if path.is_symlink():
                symlinks.append(relative)
            elif path.is_dir():
                if path.name not in EXCLUDED:
                    visit(path)
            elif path.is_file() and (path.suffix == '.py' or path.name in SETUP_NAMES):
                files.append(path)
    visit(root)
    return files, symlinks


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return (prefix + '.' if prefix else '') + node.attr
    return ''


class Scan(ast.NodeVisitor):
    def __init__(self, source, aliases):
        self.source = source
        self.aliases = aliases
        self.scope = []
        self.definitions = []
        self.calls = []
        self.references = []
        self.dynamic_sites = []

    def definition(self, node, kind):
        name = '.'.join(self.scope + [node.name])
        self.definitions.append({
            'name': name, 'kind': kind,
            'line': node.lineno, 'end_line': node.end_lineno,
        })
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node):
        self.definition(node, 'class')

    def visit_FunctionDef(self, node):
        self.definition(node, 'function')

    def visit_AsyncFunctionDef(self, node):
        self.definition(node, 'async_function')

    def record(self, node, target):
        return {
            'scope': '.'.join(self.scope) or '<module>',
            'line': node.lineno, 'end_line': node.end_lineno,
            'target': target,
            'source': ast.get_source_segment(self.source, node),
        }

    def relevant(self, name):
        if not name:
            return False
        first, *rest = name.split('.')
        expanded = self.aliases.get(first, first)
        if rest:
            expanded += '.' + '.'.join(rest)
        return name.split('.')[-1] in TARGETS or expanded.split('.')[-1] in TARGETS

    def visit_Call(self, node):
        target = dotted(node.func)
        if self.relevant(target):
            self.calls.append(self.record(node, target))
        if target in {'getattr', 'setattr', 'eval', 'exec', '__import__'} or target.endswith('.import_module'):
            self.dynamic_sites.append(self.record(node, target))
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and self.relevant(node.id):
            self.references.append(self.record(node, node.id))

    def visit_Attribute(self, node):
        name = dotted(node)
        if isinstance(node.ctx, ast.Load) and self.relevant(name):
            self.references.append(self.record(node, name))
        self.generic_visit(node)


def inspect_source(path):
    with tokenize.open(path) as stream:
        source = stream.read()
    tree = ast.parse(source, filename=str(path))
    aliases, imports = {}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split('.')[0]
                aliases[local] = alias.name if alias.asname else local
                imports.append({'line': node.lineno, 'module': alias.name, 'local': local})
        elif isinstance(node, ast.ImportFrom):
            module = '.' * node.level + (node.module or '')
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = module + '.' + alias.name
                imports.append({'line': node.lineno, 'module': module, 'name': alias.name, 'local': local})
    visitor = Scan(source, aliases)
    visitor.visit(tree)
    return {
        'line_count': len(source.splitlines()),
        'imports': imports,
        'definitions': visitor.definitions,
        'candidate_calls': visitor.calls,
        'candidate_symbol_references': visitor.references,
        'dynamic_sites_requiring_review': visitor.dynamic_sites,
        'parse_error': None,
    }


def main():
    for destination in (MANIFEST, INDEX):
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('Preserve existing output: ' + str(destination))
    for name, root in ROOTS.items():
        if not root.is_dir() or root.is_symlink():
            raise ValueError('Expected an accessible nonsymlink source root: ' + name)
        if OUT == root.resolve() or root.resolve() in OUT.parents:
            raise ValueError('Outputs must not be inside audited roots')

    records, baselines, root_records = [], {}, {}
    for name, root in ROOTS.items():
        files, symlinks = discover(root)
        baselines[name] = {str(p.relative_to(root)): sha(p) for p in files}
        root_records[name] = {
            'path': str(root), 'file_count': len(files),
            'excluded_symlinks': symlinks,
        }
        for path in files:
            relative = str(path.relative_to(root))
            record = {
                'root': name, 'path': relative, 'absolute_path': str(path),
                'sha256': baselines[name][relative], 'bytes': path.stat().st_size,
            }
            if path.suffix == '.py':
                try:
                    record.update(inspect_source(path))
                except (SyntaxError, UnicodeError) as error:
                    record['parse_error'] = {
                        'type': type(error).__name__,
                        'line': getattr(error, 'lineno', None),
                        'message': str(error),
                    }
            records.append(record)

    unchanged = {}
    for name, root in ROOTS.items():
        after_files, after_symlinks = discover(root)
        after = {str(p.relative_to(root)): sha(p) for p in after_files}
        unchanged[name] = (
            after == baselines[name]
            and after_symlinks == root_records[name]['excluded_symlinks']
        )

    limitations = [
        'Static candidate index, not a resolved runtime call graph or completed manual caller review.',
        'Generic method names may identify unrelated callers; inspect their actual implementations.',
        'Import-alias expansion is conservative and scope-insensitive; rebinding requires manual review.',
        'Dynamic calls, wildcard imports, generated code and callers outside the roots are not excluded.',
        'Symlinks are listed but not followed; relevant targets require separate inspection.',
        'Only Python and named setup/documentation files are hashed; binary/data files are outside this scope.',
        'Hash equality describes this audit interval, not historical checkout cleanliness.',
        'No dependency imports, original failure reproduction, plant execution or physical verification occur.',
    ]
    result = {
        'schema': 'pdr_r12_static_source_audit_v1',
        'observed_at_utc': datetime.now(timezone.utc).isoformat(),
        'work_plan': '66c7448f443f44ac9a016a1b384593a2 revision 1',
        'roots': root_records, 'excluded_directories': sorted(EXCLUDED),
        'target_symbols': sorted(TARGETS),
        'source_unchanged_during_audit': unchanged,
        'plant_imports_attempted': False, 'numerical_execution_attempted': False,
        'physical_acceptance': 'not_assessed',
        'limitations': limitations, 'files': records,
    }
    lines = [
        '# PDR r12 fresh static affected-caller index', '',
        'Status: static evidence only; manual caller review remains required.', '',
        'Observed preservation during this audit: ' + json.dumps(unchanged, sort_keys=True), '',
        'Full imports, definitions and symbol references are in source_inventory_r12_01.json.',
        'Read the original files at the locations below before accepting a repair.', '',
    ]
    for record in records:
        if not record['path'].endswith('.py'):
            continue
        lines.extend([
            '## ' + record['root'] + '/' + record['path'], '',
            'Read path: `' + record['absolute_path'] + '`',
            'SHA-256: `' + record['sha256'] + '`', '',
        ])
        if record.get('parse_error'):
            lines.append('PARSE ERROR: ' + json.dumps(record['parse_error']))
        for call in record.get('candidate_calls', []):
            lines.append('- Lines ' + str(call['line']) + '-' + str(call['end_line'])
                         + ': `' + call['scope'] + '` calls `' + call['target'] + '`.')
        references = sorted({
            (entry['line'], entry['scope'], entry['target'])
            for entry in record.get('candidate_symbol_references', [])
        })
        if references:
            lines.append('- Symbol-reference locations: ' + '; '.join(
                str(line) + ' ' + scope + ' -> ' + target
                for line, scope, target in references
            ))
        for site in record.get('dynamic_sites_requiring_review', []):
            lines.append('- Dynamic-site review: line ' + str(site['line']) + ', `' + site['target'] + '`.')
        lines.append('')
    lines.extend(['## Limitations', ''] + ['- ' + item for item in limitations])
    with MANIFEST.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    with INDEX.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines) + '\n')
    print(json.dumps({
        'status': 'static_inventory_generated', 'files': len(records),
        'source_unchanged_during_audit': unchanged,
        'manual_caller_review_complete': False,
        'physical_acceptance': 'not_assessed',
    }, allow_nan=False))


if __name__ == '__main__':
    main()
