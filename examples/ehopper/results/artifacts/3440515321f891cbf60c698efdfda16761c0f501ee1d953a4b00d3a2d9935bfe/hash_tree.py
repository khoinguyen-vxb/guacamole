"""Read-only supplied-checkout hashing for the PDR r5 simulator worker.

Run with python -B. Outputs must be beneath results/software/r5.
Excluded directories are not traversed, but their metadata is recorded.
Symlinks are recorded without following them; their targets are not certified.
This baseline starts after backend interpreter initialization, not before it.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper')
OUTPUT_ROOT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/r5')


def digest_file(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, key) != getattr(after, key) for key in keys):
        raise RuntimeError(f'File changed while hashing: {path}')
    return {'sha256': digest.hexdigest(), 'size_bytes': after.st_size}


def excluded_metadata(path, reason):
    info = path.lstat()
    return {'reason': reason, 'mtime_ns': info.st_mtime_ns,
            'ctime_ns': info.st_ctime_ns, 'size_bytes': info.st_size}


def snapshot():
    root = SOURCE.resolve(strict=True)
    files, excluded, symlinks = {}, {}, {}

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
                symlinks[relative] = {'target': os.readlink(path), 'kind': 'directory'}
            elif name == '__pycache__' or name.startswith('.'):
                reason = 'bytecode_cache' if name == '__pycache__' else 'dot_directory'
                excluded[relative] = excluded_metadata(path, reason)
            else:
                retained.append(name)
        dirnames[:] = retained
        for name in sorted(filenames):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                symlinks[relative] = {'target': os.readlink(path), 'kind': 'file'}
            elif name.endswith('.pyc'):
                excluded[relative] = excluded_metadata(path, 'bytecode_file')
            elif path.is_file():
                files[relative] = digest_file(path)
            else:
                raise RuntimeError(f'Unsupported non-regular entry: {path}')
    return {
        'schema': 'supplied_checkout_hashes_r5_v1',
        'source_root': str(root),
        'observed_at_utc': datetime.now(timezone.utc).isoformat(),
        'python_executable': sys.executable,
        'bytecode_disabled': bool(sys.dont_write_bytecode),
        'files': dict(sorted(files.items())),
        'file_count': len(files),
        'excluded_entries': dict(sorted(excluded.items())),
        'symlinks_not_followed': dict(sorted(symlinks.items())),
        'limitations': [
            'Observation starts after backend interpreter initialization.',
            'Excluded directory contents are not hashed; metadata changes are only signals, not a complete audit of those contents.',
            'Symlink targets are not followed or certified.',
            'The walk is not an atomic filesystem snapshot; individual files are checked for concurrent changes while hashing.',
            'Hash equality is source-preservation evidence, not plant or hardware validation.'
        ]
    }


def mapping_difference(before, after):
    old, new = set(before), set(after)
    return {'added': sorted(new - old), 'removed': sorted(old - new),
            'changed': sorted(key for key in old & new if before[key] != after[key])}


def output_path(value):
    path = Path(value).resolve()
    root = OUTPUT_ROOT.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f'Output must be beneath {root}')
    return path


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    # Never silently replace a previous baseline or comparison.
    with path.open('xb') as stream:
        stream.write(encoded)
    return {'path': str(path), 'sha256': hashlib.sha256(encoded).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--compare')
    parser.add_argument('--comparison-output')
    args = parser.parse_args()
    if not sys.dont_write_bytecode:
        parser.error('Run Python with -B')
    if bool(args.compare) != bool(args.comparison_output):
        parser.error('--compare and --comparison-output must be supplied together')
    destination = output_path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    comparison_destination = output_path(args.comparison_output) if args.compare else None
    if comparison_destination and (comparison_destination.exists() or comparison_destination == destination):
        raise ValueError('Comparison output must be a distinct new file')
    baseline = None
    if args.compare:
        baseline_path = output_path(args.compare)
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        if baseline['source_root'] != str(SOURCE.resolve(strict=True)):
            raise ValueError('Baseline source root differs')
    current = snapshot()
    outputs = [write_json(destination, current)]
    summary = {'file_count': current['file_count'],
               'symlink_count': len(current['symlinks_not_followed']),
               'excluded_entry_count': len(current['excluded_entries'])}
    if baseline is not None:
        changes = mapping_difference(baseline['files'], current['files'])
        comparison = {
            'schema': 'supplied_checkout_comparison_r5_v1',
            'before_file': str(baseline_path),
            'before_file_sha256': digest_file(baseline_path)['sha256'],
            'after_file': str(destination),
            'after_file_sha256': outputs[0]['sha256'],
            'source_root': current['source_root'],
            'source_and_data_changes': changes,
            'source_and_data_hashes_unchanged': not any(changes.values()),
            'excluded_entry_metadata_changes': mapping_difference(baseline['excluded_entries'], current['excluded_entries']),
            'symlink_changes': mapping_difference(baseline['symlinks_not_followed'], current['symlinks_not_followed']),
            'limitations': current['limitations']
        }
        outputs.append(write_json(comparison_destination, comparison))
        summary['source_and_data_hashes_unchanged'] = comparison['source_and_data_hashes_unchanged']
    summary['outputs'] = outputs
    print(json.dumps(summary, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
