"""Prepare and perform a baseline-checked PDR r5 source copy.

Run python -B tools/copy_source.py plan, then inspect copy_plan.json.
Declare every path in its declared_copy_outputs before executing copy mode.
No supplied Python module is imported or executed. Existing outputs are never
silently replaced. A failed copy can leave partial outputs for inspection.
"""
import argparse
import json
import os
from pathlib import Path
import sys

if not sys.dont_write_bytecode:
    raise RuntimeError('Run Python with -B')

from hash_tree import digest_file

SOURCE = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper')
HERE = Path(__file__).resolve().parents[1]
EXPECTED_ROOT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/r5')
DESTINATION = HERE / '6dof_hopper_r5'
BASELINE = HERE / 'supplied_hashes_before.json'
BASELINE_SHA256 = 'ab5d979836a7bd447c213d3c60f38d5475d674c9a5cbcfdfa862de677a3dc317'
PLAN = HERE / 'copy_plan.json'
MANIFEST = HERE / 'copy_manifest_initial.json'


def save_new_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return digest_file(path)['sha256']


def inventory():
    if HERE != EXPECTED_ROOT.resolve(strict=True):
        raise RuntimeError('Unexpected sandbox location')
    if SOURCE.is_symlink():
        raise RuntimeError('Supplied root must not be a symlink')
    if digest_file(BASELINE)['sha256'] != BASELINE_SHA256:
        raise RuntimeError('Baseline file hash differs from recorded execution')
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    if baseline['source_root'] != str(SOURCE.resolve(strict=True)):
        raise RuntimeError('Baseline refers to a different supplied root')
    records, exclusions = [], []

    def walk_error(error):
        raise error

    for directory, dirnames, filenames in os.walk(SOURCE, followlinks=False, onerror=walk_error):
        base = Path(directory)
        retained = []
        for name in sorted(dirnames):
            path = base / name
            relative = path.relative_to(SOURCE).as_posix()
            if path.is_symlink():
                raise RuntimeError(f'Unexpected source directory symlink: {relative}')
            if name == 'PyThrust' or name == '__pycache__' or name.startswith('.'):
                exclusions.append({'path': relative, 'reason': 'PyThrust_read_only_dependency' if name == 'PyThrust' else 'cache_or_dot_directory'})
            else:
                retained.append(name)
        dirnames[:] = retained
        for name in sorted(filenames):
            path = base / name
            relative = path.relative_to(SOURCE).as_posix()
            if path.is_symlink():
                raise RuntimeError(f'Unexpected source file symlink: {relative}')
            if name.endswith(('.pyc', '.pyo')):
                exclusions.append({'path': relative, 'reason': 'bytecode_file'})
                continue
            if not path.is_file():
                raise RuntimeError(f'Unsupported source entry: {relative}')
            digest = digest_file(path)
            if baseline['files'].get(relative) != digest:
                raise RuntimeError(f'Source no longer matches baseline: {relative}')
            records.append({'relative_path': relative, **digest})
    records.sort(key=lambda row: row['relative_path'])
    if not records:
        raise RuntimeError('Refusing an empty source copy')
    return {
        'schema': 'hopper_source_copy_plan_r5_v1',
        'source_root': str(SOURCE),
        'destination_root': str(DESTINATION),
        'baseline_path': 'software/r5/supplied_hashes_before.json',
        'baseline_sha256': BASELINE_SHA256,
        'files': records,
        'excluded_entries': sorted(exclusions, key=lambda row: row['path']),
        'pythrust_policy': 'Excluded from copy; subsequent configuration must hold its absolute read-only path.',
        'declared_copy_outputs': [
            'software/r5/6dof_hopper_r5/' + row['relative_path'] for row in records
        ] + ['software/r5/copy_manifest_initial.json']
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan', 'copy'))
    args = parser.parse_args()
    current = inventory()
    if args.mode == 'plan':
        if DESTINATION.exists() or DESTINATION.is_symlink():
            raise FileExistsError(DESTINATION)
        sha256 = save_new_json(PLAN, current)
        print(json.dumps({'path': 'software/r5/copy_plan.json', 'sha256': sha256,
                          'file_count': len(current['files']),
                          'declared_copy_outputs': current['declared_copy_outputs']}, sort_keys=True))
        return

    saved = json.loads(PLAN.read_text(encoding='utf-8'))
    if saved != current:
        raise RuntimeError('Source enumeration differs from inspected copy plan')
    if DESTINATION.exists() or DESTINATION.is_symlink() or MANIFEST.exists():
        raise FileExistsError('Copy destination or initial manifest already exists')
    DESTINATION.mkdir()
    copied = []
    for row in saved['files']:
        relative = Path(row['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe relative path')
        source = SOURCE / relative
        target = DESTINATION / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as reader, target.open('xb') as writer:
            for block in iter(lambda: reader.read(1024 * 1024), b''):
                writer.write(block)
        expected = {key: row[key] for key in ('sha256', 'size_bytes')}
        if digest_file(source) != expected or digest_file(target) != expected:
            raise RuntimeError(f'Copy hash mismatch: {relative}')
        copied.append({'path': 'software/r5/6dof_hopper_r5/' + relative.as_posix(),
                       'source_relative_path': relative.as_posix(), **expected})
    manifest = {
        'schema': 'hopper_source_copy_manifest_r5_v1',
        'status': 'Unmodified initial copy; not a repaired or verified plant',
        'copy_script_sha256': digest_file(Path(__file__))['sha256'],
        'copy_plan_sha256': digest_file(PLAN)['sha256'],
        'baseline_sha256': BASELINE_SHA256,
        'source_root': str(SOURCE),
        'file_count': len(copied),
        'files': copied,
        'excluded_entries': saved['excluded_entries'],
        'content_preservation': 'Byte-for-byte copying; filesystem timestamps and permissions are not certified.',
        'physical_validation': 'unperformed'
    }
    sha256 = save_new_json(MANIFEST, manifest)
    print(json.dumps({'path': 'software/r5/copy_manifest_initial.json',
                      'sha256': sha256, 'file_count': len(copied),
                      'copy_hashes_match_baseline': True}, sort_keys=True))


if __name__ == '__main__':
    main()
