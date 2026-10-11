"""Read-only source/caller audit for PDR-R9; no plant imports or repairs.

Run from the sandbox using repository='6dof_hopper' and argv beginning:
  python -B software/pdr_r9_plant/audit_sources.py
Declare generated outputs:
  software/pdr_r9_plant/source_inventory.json
  software/pdr_r9_plant/source_callers.md

The manifest covers Python sources and setup/documentation files, not every
binary/data file in the checkout. Source hashes establish the observed baseline,
not historical cleanliness. No hardware or numerical acceptance is assessed.
"""
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tokenize

ROOTS = {
    '6dof_hopper': Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper'),
    'PendulumControlProject': Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/PendulumControlProject'),
}
OUT = Path(__file__).resolve().parent
MANIFEST = OUT / 'source_inventory.json'
REPORT = OUT / 'source_callers.md'
EXCLUDED_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules'}
SETUP_NAMES = {'pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt', 'uv.lock', 'README.md'}
TARGETS = {
    'Simulation', 'trajectory_ode', 'solve_ode', 'State', 'update_state',
    'unpack_state', 'quarternion_to_dcm', 'quaternion_to_dcm',
    'euler_to_quaternion', 'Hopper', 'Propulsion', 'Propellor', 'Propeller',
    'get_mass', 'get_local_cg', 'get_thrust_and_moment', 'mass', 'CG',
    'inertia', 'Aerodynamics', 'determine_at_point', 'solve_ivp',
}
MODULES = {'simulation', 'state', 'helpers', 'chassis', 'propulsion', 'aero'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover(root):
    found, symlinks = [], []
    def visit(directory):
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            if path.is_symlink():
                symlinks.append(str(path.relative_to(root)))
            elif path.is_dir():
                if path.name not in EXCLUDED_DIRS:
                    visit(path)
            elif path.is_file() and (path.suffix == '.py' or path.name in SETUP_NAMES):
                found.append(path)
    visit(root)
    return found, symlinks


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return (prefix + '.' if prefix else '') + node.attr
    return ''


class Inventory(ast.NodeVisitor):
    def __init__(self, source):
        self.source = source
        self.scope = []
        self.definitions = []
        self.calls = []
        self.imports = []

    def definition(self, node, kind):
        qualified = '.'.join(self.scope + [node.name])
        self.definitions.append({'name': qualified, 'kind': kind, 'line': node.lineno, 'end_line': node.end_lineno})
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node):
        self.definition(node, 'class')

    def visit_FunctionDef(self, node):
        self.definition(node, 'function')

    def visit_AsyncFunctionDef(self, node):
        self.definition(node, 'async_function')

    def visit_Call(self, node):
        target = dotted(node.func)
        if target and target.split('.')[-1] in TARGETS:
            self.calls.append({'scope': '.'.join(self.scope) or '<module>', 'target': target, 'line': node.lineno, 'expression': ast.get_source_segment(self.source, node)})
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({'module': alias.name, 'name': None, 'asname': alias.asname, 'line': node.lineno})

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.imports.append({'module': '.' * node.level + (node.module or ''), 'name': alias.name, 'asname': alias.asname, 'line': node.lineno})


for output in (MANIFEST, REPORT):
    if output.exists() or output.is_symlink():
        raise FileExistsError('Preserve existing audit output; use a reviewed new version: ' + str(output))
for root in ROOTS.values():
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    if OUT == root.resolve() or root.resolve() in OUT.parents:
        raise ValueError('Audit outputs must not be inside a supplied checkout')

records = []
roots_report = {}
baselines = {}
for repository, root in ROOTS.items():
    files, symlinks = discover(root)
    baselines[repository] = {str(p.relative_to(root)): digest(p) for p in files}
    roots_report[repository] = {'path': str(root), 'excluded_symlinks': symlinks, 'file_count': len(files)}
    for path in files:
        relative = str(path.relative_to(root))
        item = {'repository': repository, 'path': relative, 'sha256': baselines[repository][relative], 'bytes': path.stat().st_size}
        if path.suffix == '.py':
            with tokenize.open(path) as stream:
                source = stream.read()
            item['line_count'] = len(source.splitlines())
            try:
                tree = ast.parse(source, filename=str(path))
                visitor = Inventory(source)
                visitor.visit(tree)
                item.update(definitions=visitor.definitions, affected_call_candidates=visitor.calls, imports=visitor.imports, parse_error=None)
                relevant_import = any(
                    entry['name'] in TARGETS or any(part in MODULES for part in entry['module'].split('.'))
                    for entry in visitor.imports
                )
                owned_core = repository == '6dof_hopper' and 'PyThrust' not in path.relative_to(root).parts
                relevant_definition = any(entry['name'].split('.')[-1] in TARGETS for entry in visitor.definitions)
                if owned_core or visitor.calls or relevant_import or relevant_definition:
                    item['source_for_manual_review'] = source
            except SyntaxError as error:
                item['parse_error'] = {'line': error.lineno, 'message': error.msg}
                item['source_for_manual_review'] = source
        records.append(item)

# Re-enumerate and rehash to detect changed, added or removed in-scope files.
unchanged = {}
for repository, root in ROOTS.items():
    files_after, symlinks_after = discover(root)
    after = {str(p.relative_to(root)): digest(p) for p in files_after}
    unchanged[repository] = after == baselines[repository] and symlinks_after == roots_report[repository]['excluded_symlinks']

result = {
    'schema': 'pdr_r9_source_inventory_v1',
    'observed_at_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Python sources and named setup/documentation files in both supplied repositories; nested PyThrust included',
    'excluded_directories': sorted(EXCLUDED_DIRS),
    'roots': roots_report,
    'source_unchanged_during_audit': unchanged,
    'imports_attempted': False,
    'plant_execution_attempted': False,
    'physical_acceptance': 'not_assessed',
    'limitations': [
        'Call candidates require manual review; attribute names are not resolved to runtime types.',
        'Dynamic dispatch, generated code and callers outside these roots are not excluded.',
        'Symlinks are listed but not followed; any relevant target needs a separate supplied-source review.',
        'Hash equality measures preservation during this audit only; retain this baseline for post-repair comparison.',
        'Binary/data files and excluded directories are outside this source-manifest scope.',
    ],
    'files': records,
}
lines = ['# PDR-R9 source and caller inventory', '', 'Status: static diagnostic evidence only; no imports, numerical verification or repairs.', '', '## Preservation scope', '', result['scope'], '', 'Observed unchanged during this read: ' + json.dumps(unchanged, sort_keys=True), '', '## Python inventory and candidate callers', '']
for item in records:
    if not item['path'].endswith('.py'):
        continue
    lines.extend(['### ' + item['repository'] + '/' + item['path'], '', 'SHA-256: `' + item['sha256'] + '`', ''])
    if item.get('parse_error'):
        lines.append('PARSE ERROR: ' + json.dumps(item['parse_error']))
    for definition in item.get('definitions', []):
        lines.append('- Definition `' + definition['name'] + '` at lines ' + str(definition['line']) + '-' + str(definition['end_line']) + '.')
    for call in item.get('affected_call_candidates', []):
        lines.append('- Candidate caller `' + call['scope'] + '` -> `' + call['target'] + '` at line ' + str(call['line']) + '.')
    lines.append('')
    if 'source_for_manual_review' in item:
        lines.extend(['Full source for manual caller review:', '', '```python'])
        lines.extend(str(number) + ': ' + line for number, line in enumerate(item['source_for_manual_review'].splitlines(), 1))
        lines.extend(['```', ''])
lines.extend(['## Limitations', ''] + ['- ' + text for text in result['limitations']])
with MANIFEST.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write('\n')
with REPORT.open('x', encoding='utf-8') as stream:
    stream.write('\n'.join(lines) + '\n')
print(json.dumps({'status': 'static_audit_completed', 'files': len(records), 'source_unchanged_during_audit': unchanged, 'physical_acceptance': 'not_assessed'}, allow_nan=False))
