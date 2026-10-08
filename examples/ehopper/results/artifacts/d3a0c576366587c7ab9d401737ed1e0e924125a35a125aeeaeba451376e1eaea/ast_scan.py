"""Read-only AST inventory of supplied and copied hopper source.

Run with python -B tools/ast_scan.py --output caller_scan_before.json.
After repairs use a distinct output, e.g. caller_scan_after.json.
All Python files in each tree are scanned, including read-only PyThrust in
its supplied location. Dot-directories and bytecode caches are excluded.
No scanned module is imported or executed. Results identify static caller
candidates and callback references, not a complete runtime call graph.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tokenize

HERE = Path(__file__).resolve().parents[1]
EXPECTED_OUTPUT_ROOT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/r5')
SUPPLIED = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper')
DEFAULT_TARGETS = {
    'Simulation', 'State', 'Hopper', 'Propulsion', 'Propellor', 'Aerodynamics',
    'trajectory_ode', 'solve_ode', 'update_state', 'unpack_state',
    'quarternion_to_dcm', 'quaternion_to_dcm', 'euler_to_quaternion',
    'mass', 'CG', 'inertia', 'get_mass', 'get_local_cg',
    'get_thrust_and_moment', 'determine_at_point',
}


def expression(node):
    return ast.unparse(node)


def imports_in(tree):
    records = []
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                local = item.asname or item.name.split('.')[0]
                qualified = item.name if item.asname else local
                aliases.setdefault(local, set()).add(qualified)
                records.append({'line': node.lineno, 'local_name': local,
                                'imported_name': item.name, 'relative_level': 0})
        elif isinstance(node, ast.ImportFrom):
            prefix = '.' * node.level + (node.module or '')
            for item in node.names:
                local = item.asname or item.name
                qualified = prefix + ('.' if node.module else '') + item.name
                aliases.setdefault(local, set()).add(qualified)
                records.append({'line': node.lineno, 'local_name': local,
                                'imported_name': qualified,
                                'relative_level': node.level})
    return sorted(records, key=lambda row: (row['line'], row['local_name'])), aliases


class InventoryVisitor(ast.NodeVisitor):
    def __init__(self, relative_path, targets, aliases):
        self.relative_path = relative_path
        self.targets = targets
        self.aliases = aliases
        self.scope = []
        self.definitions = []
        self.calls = []
        self.references = []

    def location(self, node):
        return {
            'path': self.relative_path,
            'line': node.lineno,
            'end_line': getattr(node, 'end_lineno', node.lineno),
            'column_zero_based': node.col_offset,
            'enclosing_syntactic_scope': '.'.join(self.scope) or '<module>',
        }

    def candidate_names(self, node):
        name = expression(node)
        candidates = {name}
        if isinstance(node, (ast.Name, ast.Attribute)):
            head, separator, tail = name.partition('.')
            for qualified in self.aliases.get(head, ()):
                candidates.add(qualified + (separator + tail if separator else ''))
        return sorted(candidates)

    def matched_targets(self, node):
        return sorted({name.rsplit('.', 1)[-1]
                       for name in self.candidate_names(node)} & self.targets)

    def visit_ClassDef(self, node):
        record = self.location(node)
        record.update(kind='class', name=node.name,
                      qualified_syntactic_name='.'.join(self.scope + [node.name]),
                      bases=[expression(base) for base in node.bases])
        self.definitions.append(record)
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        record = self.location(node)
        record.update(kind='async_function' if isinstance(node, ast.AsyncFunctionDef)
                      else 'function', name=node.name,
                      qualified_syntactic_name='.'.join(self.scope + [node.name]),
                      arguments=expression(node.args))
        self.definitions.append(record)
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self.scope.append('<lambda@' + str(node.lineno) + '>')
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node):
        record = self.location(node)
        record.update(kind='call', callable_expression=expression(node.func),
                      import_expanded_candidates=self.candidate_names(node.func),
                      matched_targets=self.matched_targets(node.func))
        self.calls.append(record)
        if record['matched_targets']:
            self.references.append(record.copy())
        self.generic_visit(node)

    def reference(self, node):
        matched = self.matched_targets(node)
        if matched:
            record = self.location(node)
            record.update(kind='symbol_reference', expression=expression(node),
                          import_expanded_candidates=self.candidate_names(node),
                          matched_targets=matched)
            self.references.append(record)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.reference(node)

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Load):
            self.reference(node)
        self.generic_visit(node)


def scan(root, targets):
    if root.is_symlink():
        raise RuntimeError('Refusing a symlink scan root: ' + str(root))
    root = root.resolve(strict=True)
    files, excluded, errors = [], [], []
    candidates = {target: [] for target in sorted(targets)}

    def walk_error(error):
        raise error

    for directory, dirnames, filenames in os.walk(root, followlinks=False,
                                                 onerror=walk_error):
        base = Path(directory)
        retained = []
        for name in sorted(dirnames):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                excluded.append({'path': relative, 'reason': 'symlink_not_followed'})
                errors.append({'path': relative, 'reason': 'Unscanned directory symlink'})
            elif name.startswith('.') or name == '__pycache__':
                excluded.append({'path': relative, 'reason': 'dot_directory_or_cache'})
            else:
                retained.append(name)
        dirnames[:] = retained
        for name in sorted(filenames):
            if not name.endswith('.py'):
                continue
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                excluded.append({'path': relative, 'reason': 'symlink_not_followed'})
                errors.append({'path': relative, 'reason': 'Unscanned Python symlink'})
                continue
            raw = path.read_bytes()
            record = {'path': relative, 'size_bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest(),
                      'dependency_source': relative.startswith('PyThrust/')}
            try:
                with tokenize.open(path) as stream:
                    source = stream.read()
                if path.read_bytes() != raw:
                    raise RuntimeError('Source changed during AST read')
                tree = ast.parse(source, filename=str(path))
                imports, aliases = imports_in(tree)
                visitor = InventoryVisitor(relative, targets, aliases)
                visitor.visit(tree)
                record.update(parse_success=True, imports=imports,
                              definitions=visitor.definitions, calls=visitor.calls)
                for reference in visitor.references:
                    for target in reference['matched_targets']:
                        candidates[target].append(reference)
            except (SyntaxError, UnicodeError, LookupError, RuntimeError) as error:
                record.update(parse_success=False, error_type=type(error).__name__,
                              error=str(error))
                errors.append({'path': relative, 'reason': str(error),
                               'error_type': type(error).__name__})
            files.append(record)
    files.sort(key=lambda row: row['path'])
    for values in candidates.values():
        values.sort(key=lambda row: (row['path'], row['line'],
                                    row['column_zero_based'], row['kind']))
    return {
        'root': str(root), 'python_file_count': len(files), 'files': files,
        'excluded_entries': excluded, 'parse_or_coverage_errors': errors,
        'caller_and_reference_candidates_by_target': candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--target', action='append', default=[],
                        help='Additional symbol name to index; repeat as needed')
    args = parser.parse_args()
    if not sys.dont_write_bytecode:
        parser.error('Run Python with -B')
    if HERE != EXPECTED_OUTPUT_ROOT.resolve(strict=True):
        raise RuntimeError('Unexpected script location')
    destination = Path(args.output).resolve()
    if not destination.is_relative_to(HERE):
        raise ValueError('Output must be beneath software/r5')
    if destination.exists():
        raise FileExistsError(destination)
    targets = DEFAULT_TARGETS | set(args.target)
    trees = {
        'supplied': scan(SUPPLIED, targets),
        'modified_copy': scan(HERE / '6dof_hopper_r5', targets),
    }
    report = {
        'schema': 'hopper_static_caller_inventory_r5_v1',
        'status': 'Static source inventory; manual caller review still required',
        'scanner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python_version': sys.version, 'bytecode_disabled': True,
        'targets': sorted(targets), 'trees': trees,
        'limitations': [
            'Terminal-name matches are candidates, not resolved object identities.',
            'Import aliases are conservatively expanded without lexical shadowing analysis.',
            'Symbol references include callbacks, annotations, bases and ordinary reads; they are not all calls.',
            'Enclosing scopes are syntactic; decorators and default expressions execute in their defining scope.',
            'Assignment aliases, reflective calls, dynamic dispatch and external callers are not fully resolved.',
            'Supplied PyThrust is scanned read-only; it is intentionally absent from the copied tree.',
            'This program does not import source modules, check dependencies or verify plant physics.',
        ],
    }
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(encoded)
    summary = {'path': str(destination),
               'sha256': hashlib.sha256(encoded).hexdigest(),
               'trees': {key: {'python_file_count': value['python_file_count'],
                               'error_count': len(value['parse_or_coverage_errors'])}
                         for key, value in trees.items()}}
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    for label, tree in trees.items():
        for error in tree['parse_or_coverage_errors']:
            print(json.dumps({'tree': label, **error}), file=sys.stderr)
    if any(tree['parse_or_coverage_errors'] for tree in trees.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
