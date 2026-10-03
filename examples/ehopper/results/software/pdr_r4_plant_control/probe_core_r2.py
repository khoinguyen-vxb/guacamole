#!/usr/bin/env python3
"""Corrected PDR diagnostic launcher; not a plant repair.

Run with repository='6dof_hopper', command[0]='python', and -B, from the
sandbox task directory. Requires the retained, editable probe_core.py beside
this file. Applies two explicit in-memory changes to that diagnostic program:
  1. Preserve selected-interpreter site-packages during import-path filtering.
  2. Write results to results_core_r2 instead of overwriting the first run.

The original probe and all supplied repositories remain unchanged. The first
run's missing-import results are contaminated by a harness error and cannot
establish missing installations. No integrated or physical acceptance is made.
"""
import sys
sys.dont_write_bytecode = True

import hashlib
from pathlib import Path
import sysconfig

_R2_TASK = Path(__file__).resolve().parent
_R2_CORE = _R2_TASK / 'probe_core.py'
_R2_EXPECTED_CORE_SHA256 = '5e4013bce605ae55d8d85c7f844eda10cb336db167d49b2e3615dbabbe44166f'
_R2_BYTES = _R2_CORE.read_bytes()
_R2_CORE_SHA256 = hashlib.sha256(_R2_BYTES).hexdigest()
if _R2_CORE_SHA256 != _R2_EXPECTED_CORE_SHA256:
    raise RuntimeError('Retained probe_core.py changed; inspect it before updating this launcher')

_R2_SITE_ROOTS = {
    Path(value).resolve()
    for key, value in sysconfig.get_paths().items()
    if key in {'purelib', 'platlib'} and value
}
_R2_PATH_AUDIT = {}


def _r2_resolve_import_path(path):
    return Path(path or Path.cwd()).resolve()


def _r2_correct_import_path(original, source, pendulum):
    """Exclude checkout shortcuts, not this interpreter's dependency paths."""
    source = source.resolve()
    pendulum = pendulum.resolve()
    retained = [str(source)]
    removed = []
    protected = []
    for entry in original:
        resolved = _r2_resolve_import_path(entry)
        is_site_path = any(
            resolved == root or resolved.is_relative_to(root)
            for root in _R2_SITE_ROOTS
        )
        if is_site_path:
            retained.append(entry)
            protected.append(entry)
        elif resolved == source:
            continue  # Already present exactly once as the import root.
        elif resolved.is_relative_to(source) or resolved.is_relative_to(pendulum):
            removed.append(entry)
        else:
            retained.append(entry)

    resolved_retained = {_r2_resolve_import_path(entry) for entry in retained}
    for entry in protected:
        if _r2_resolve_import_path(entry) not in resolved_retained:
            raise RuntimeError('Diagnostic path filtering removed an interpreter dependency path')
    if source / 'simulation' in resolved_retained:
        raise RuntimeError('simulation/ shortcut would mask the original State import defect')

    _R2_PATH_AUDIT.update({
        'selected_interpreter_site_roots': sorted(str(root) for root in _R2_SITE_ROOTS),
        'protected_original_site_paths': protected,
        'removed_checkout_shortcuts': removed,
        'all_original_selected_site_paths_preserved': True,
        'method': 'preserve sysconfig purelib/platlib paths before excluding source subdirectory shortcuts',
    })
    return retained


_R2_SOURCE = _R2_BYTES.decode('utf-8')
_R2_REPLACEMENTS = [
    (
        "OUT = TASK / 'results'",
        "OUT = TASK / 'results_core_r2'",
    ),
    (
        "sys.path[:] = [str(SOURCE)] + [p for p in sys.path if not under(p, SOURCE) and not under(p, PENDULUM)]",
        "sys.path[:] = _r2_correct_import_path(original_sys_path, SOURCE, PENDULUM)",
    ),
]
for before, after in _R2_REPLACEMENTS:
    if _R2_SOURCE.count(before) != 1:
        raise RuntimeError('Expected exactly one diagnostic-harness replacement target: ' + before)
    _R2_SOURCE = _R2_SOURCE.replace(before, after, 1)

print('R2 corrects the probe import-path filter; prior missing imports are not installation evidence.', file=sys.stderr)
exec(compile(_R2_SOURCE, str(_R2_CORE) + ' [R2 diagnostic harness]', 'exec'), globals(), globals())

# The core uses __file__, so probe_source_sha256 identifies this launcher.
# Retain the original core hash and both exact changes to make the run reproducible.
REPORT['diagnostic_harness_correction'] = {
    'revision': 2,
    'launcher_path': str(Path(__file__).resolve()),
    'launcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'retained_core_path': str(_R2_CORE),
    'retained_core_sha256': _R2_CORE_SHA256,
    'in_memory_replacements': [{'before': before, 'after': after} for before, after in _R2_REPLACEMENTS],
    'path_audit': _R2_PATH_AUDIT,
    'previous_observation_ref': {
        'kind': 'tool_result',
        'id': 'd6f6a9e2716147788d519d24a01c8c31',
        'revision': 1,
        'sha256': '36721c97cc89d2ee04f6dbbe8ee55d6ceca9cb68472666902e8e8fb9272e63c1',
    },
    'previous_run_interpretation': 'The first probe removed the selected interpreter site-packages. Its import failures do not establish absent dependencies or reproduce downstream plant defects.',
    'original_probe_and_results_preserved': True,
    'plant_source_modified': False,
    'integrated_plant_test_performed': False,
    'physical_test_performed': False,
}
write_json(OUT / 'probe_results_core.json', REPORT)
print('Corrected raw diagnostics saved separately under results_core_r2; review individual outcomes.', file=sys.stderr)
