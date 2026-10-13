"""Reporting-only recovery of nested measurements from retained r12 logs.

Authorization: work plan 66c7448f443f44ac9a016a1b384593a2 revision 1,
task pdr_r12_preliminary_plant. Chief reporting request: message
bbb56ba5caab4a97a04d81fded4878d3, 2026-10-13.

Pre-edit inspection: collector 01 parse_diagnostics accepts only top-level
check/details records. State/frame stderr instead contains a measurements
mapping in its first JSON object. run_checker passes stderr to that parser;
main and markdown consume its empty measured list. This is a reporting-schema
omission, not missing numerical observations or a demonstrated plant defect.
The collector and its callers were inspected in job_inputs
9c7690f30f754c6eb4bda0b79f8cbfc0 revision 1. Raw content was inspected through
readers 6f63042cfa2a46fc82f0c7c920b37753 and 8b0e2a4a8cf949f39628cc4cd5fab548.

This new standalone entry point reads existing logs and digest only. It does
not import or execute checkers, plant modules, the old collector or subprocesses.
It does not modify their files, outcomes, thresholds or existing reports.
No new VerificationResult or physical acceptance is produced.

Run with Guacamole execute, repository='6dof_hopper', workdir='.', argv:
python -B software/pdr_r12_plant/extract_retained_state_frame_measurements_r12_02.py
Declare both outputs:
software/pdr_r12_plant/test_logs_r12_reporting_02/state_frame_measurements_r12_02.json
software/pdr_r12_plant/test_logs_r12_reporting_02/state_frame_measurements_r12_02.md
Existing output paths are refused. Diagnostics go to stderr; stdout is a short
reporting status, not a verification result. Stdlib only; no installation needed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parents[1]
LABEL = 'state_frames_mass_02'
RAW = HERE / 'test_logs_r12_01/checker_raw_logs_r12_01.txt'
OLD = HERE / 'test_logs_r12_01/measured_error_digest_r12_01.json'
OUT = HERE / 'test_logs_r12_reporting_02'
DEST_JSON = OUT / 'state_frame_measurements_r12_02.json'
DEST_MD = OUT / 'state_frame_measurements_r12_02.md'
PINS = {
    RAW: '27762a320fb432f4cd3e8374dacd4eda2ea6b3c4ca0ab441baf718453b128ee7',
    OLD: '7c63d5d1164a7f3b7d232de1012b68cc5d44134f4b918736c266a81a420abad4',
}
EVIDENCE_REF = {
    'kind': 'evidence',
    'id': 'PDR-R12-PLANT-STATE-FRAME-MASS-VERIFICATION-02',
    'revision': 1,
    'sha256': 'f88c9b7bd0de0369d9cc436f64b3063d550107bbd994c48c1d03ae57ac4f20de',
}
ROOT_CAUSE = (
    'Collector 01 parse_diagnostics recognizes top-level check/details objects '
    'only. The retained state/frame stderr stores observations under a '
    'measurements mapping. Its entries therefore never reached measured_row '
    'or the old digest tables. Numerical observations were retained, not absent.'
)
SCOPE = (
    'Reporting-only extraction from the retained collector-01 re-execution logs. '
    'No tests are rerun and no plant, checker, fixture or acceptance threshold '
    'is changed. This addendum repairs the missing state/frame measurement table '
    'only; other checker tables and all registered verification outcomes remain '
    'unchanged. The registered outcome remains inconclusive. Synthetic analytical '
    'fixtures and proposed numerical regression tolerances are not calibrated '
    'vehicle inputs or human-agreed vehicle acceptance limits. No PID tuning, '
    'mission, hardware or PDR/CDR acceptance is implied.'
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_pinned(path):
    require(path.is_file() and not path.is_symlink(), 'Invalid input: ' + str(path))
    data = path.read_bytes()
    require(sha(data) == PINS[path], 'Input differs from retained file: ' + str(path))
    return data


def strict_json(text):
    def reject_constant(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject_constant,
                      object_pairs_hook=unique_pairs)


def block(raw, stream):
    pattern = (r'^===== BEGIN ' + LABEL + ' ' + stream
               + r' \(bytes=(\d+), sha256=([0-9a-f]{64}), '
               + r'returncode=0, timed_out=False\) =====\n')
    matches = list(re.finditer(pattern, raw, flags=re.MULTILINE))
    require(len(matches) == 1, 'Expected one retained ' + stream + ' block')
    start = matches[0]
    closing = '===== END ' + LABEL + ' ' + stream + ' ====='
    endings = list(re.finditer('^' + re.escape(closing) + '$',
                              raw[start.end():], flags=re.MULTILINE))
    require(len(endings) == 1, 'Expected one closing ' + stream + ' delimiter')
    end = start.end() + endings[0].start()
    payload = raw[start.end():end]
    encoded = payload.encode('utf-8')
    require(len(encoded) == int(start.group(1)), 'Archived stream byte mismatch')
    require(sha(encoded) == start.group(2), 'Archived stream hash mismatch')
    return payload, {
        'stream': stream, 'bytes': len(encoded), 'sha256': sha(encoded),
        'first_content_line_in_raw_log': raw.count('\n', 0, start.end()) + 1,
    }


def number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def markdown(report):
    summary = report['summary']
    lines = [
        '# PDR r12 state/frame measurement reporting reconciliation 02', '',
        'Generated UTC: ' + report['generated_utc'], '', SCOPE, '',
        '## Confirmed reporting root cause', '', ROOT_CAUSE, '',
        'The original digest recorded zero state/frame measured rows. This is '
        'not evidence of zero error. This addendum reads the existing archived '
        'measurements mapping; it does not regenerate measurements.', '',
        '## Provenance', '',
        '- Source: `software/pdr_r12_plant/test_logs_r12_01/checker_raw_logs_r12_01.txt`.',
        '- Original digest: `software/pdr_r12_plant/test_logs_r12_01/measured_error_digest_r12_01.json`.',
        '- Raw-log and digest file hashes are pinned and checked before/after extraction.',
        '- Selected archived stream byte lengths and hashes are checked against their headers.',
        '- Exact source lines, JSON keys and unrounded observations are retained in the companion JSON.',
        '- Registered evidence: `' + EVIDENCE_REF['id'] + '` revision 1.',
        '- Retained result: **' + report['retained_result']['outcome'] + '**; '
        + str(summary['true_checks']) + ' true, ' + str(summary['false_checks'])
        + ' false, ' + str(summary['null_checks']) + ' null checks.', '',
        'Registered explanation, preserved from retained stdout:', '',
        report['retained_result']['explanation'], '',
        '## Recovered observations', '',
        'Numerical rows: ' + str(summary['numerical_rows']) + '. Deliberate '
        'negative-fixture records: ' + str(summary['negative_fixture_records'])
        + '. Other measurement records: ' + str(summary['other_measurement_records']) + '.',
        'Recorded numerical errors within their recorded tolerance: '
        + str(summary['within_recorded_tolerance']) + '; outside: '
        + str(summary['outside_recorded_tolerance']) + '.', '',
        'Counts describe existing observations, not new verification. Negative '
        'fixtures are expected rejection observations, not measured-error rows. '
        'Completion checks need not have numerical observations.', '',
        '| Check | Recorded maximum absolute error | Recorded tolerance | Unit | Raw-log line |',
        '|---|---:|---:|---|---:|',
    ]
    for row in report['numerical_measurements']:
        detail = row['recorded_details']
        lines.append('| %s | %.17g | %.17g | %s | %d |' % (
            row['check'], detail['max_absolute_error'], detail['tolerance'],
            str(detail['unit']).replace('|', '/'), row['raw_log_line']))
    lines += ['', '## Explicitly unperformed checks', '']
    lines += ['- ' + name for name, value in report['retained_result']['checks'].items()
              if value is None]
    lines += ['', '## Scope and preservation', '',
              'Original logs, digest, checkers and source remain separate. The '
              'README and PID proposal references to the original missing table '
              'describe digest 01; use this addendum for the recovered state/frame '
              'rows. Neither document nor the original digest is overwritten.', '',
              'Vehicle mass/articulated momentum, geometry, rotor assignments, '
              'calibrated propulsion, loaded actuator limits, electrical/thermal '
              'closure, aerodynamic/contact inputs and proposal dispositions '
              'remain downstream Chief-owned dependencies.', '']
    return '\n'.join(lines)


def main():
    require((SANDBOX / 'software/pdr_r12_plant').resolve() == HERE,
            'Unexpected sandbox layout')
    require(not OUT.is_symlink(), 'Output directory must not be a symlink')
    for path in (DEST_JSON, DEST_MD):
        require(not path.exists() and not path.is_symlink(),
                'Preserve existing output: ' + str(path))
    before = {path: read_pinned(path) for path in PINS}
    raw = before[RAW].decode('utf-8')
    old = strict_json(before[OLD].decode('utf-8'))
    old_runs = [run for run in old['runs'] if run['label'] == LABEL]
    require(len(old_runs) == 1, 'Expected one state/frame entry in original digest')
    require(old_runs[0]['diagnostics']['measured'] == [],
            'Original digest is not the inspected empty-table case')
    stdout, stdout_location = block(raw, 'stdout')
    stderr, stderr_location = block(raw, 'stderr')
    result = strict_json(stdout)
    require(result['outcome'] == 'inconclusive', 'Unexpected retained outcome')
    checks = result['checks']
    require(isinstance(checks, dict) and checks, 'Missing archived checks')
    require(all(value is None or type(value) is bool for value in checks.values()),
            'Invalid archived check value')
    require(result['outcome'] == old_runs[0]['result']['outcome']
            and result['explanation'] == old_runs[0]['result']['explanation'],
            'Retained result differs from original digest')
    rows, negatives, other, context = [], [], [], []
    names = set()
    mappings = 0
    for line_number, text in enumerate(stderr.splitlines(), start=1):
        if not text.strip():
            continue
        obj = strict_json(text)
        require(isinstance(obj, dict), 'Expected stderr JSON object')
        raw_line = stderr_location['first_content_line_in_raw_log'] + line_number - 1
        context.append({'raw_log_line': raw_line,
                        'diagnostics_without_measurements': {
                            key: value for key, value in obj.items() if key != 'measurements'}})
        if 'measurements' not in obj:
            continue
        mappings += 1
        require(isinstance(obj['measurements'], dict), 'Invalid measurements mapping')
        for name, details in obj['measurements'].items():
            require(name not in names, 'Duplicate measurement name: ' + name)
            names.add(name)
            require(name in checks, 'Measurement has no retained check: ' + name)
            require(isinstance(details, dict), 'Invalid measurement details')
            row = {'check': name, 'retained_check_value': checks[name],
                   'raw_log_line': raw_line, 'stderr_line': line_number,
                   'json_path': ['measurements', name], 'recorded_details': details}
            if details.get('deliberate_negative_fixture') is True:
                negatives.append(row)
            elif 'max_absolute_error' in details and 'tolerance' in details:
                error, tolerance = details['max_absolute_error'], details['tolerance']
                require(number(error) and error >= 0 and number(tolerance)
                        and tolerance >= 0 and isinstance(details.get('unit'), str),
                        'Invalid numerical observation: ' + name)
                row['reported_error_within_recorded_tolerance'] = error <= tolerance
                rows.append(row)
            else:
                other.append(row)
    require(mappings == 1 and rows, 'Expected existing nested numerical observations')
    for path in PINS:
        require(read_pinned(path) == before[path], 'Input changed during extraction')
    summary = {
        'measurement_mapping_count': mappings,
        'numerical_rows': len(rows), 'negative_fixture_records': len(negatives),
        'other_measurement_records': len(other),
        'within_recorded_tolerance': sum(row['reported_error_within_recorded_tolerance'] for row in rows),
        'outside_recorded_tolerance': sum(not row['reported_error_within_recorded_tolerance'] for row in rows),
        'true_checks': sum(value is True for value in checks.values()),
        'false_checks': sum(value is False for value in checks.values()),
        'null_checks': sum(value is None for value in checks.values()),
    }
    report = {
        'schema': 'pdr_r12_retained_state_frame_reporting_reconciliation_v2',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'work_plan': '66c7448f443f44ac9a016a1b384593a2 revision 1',
        'chief_message': 'bbb56ba5caab4a97a04d81fded4878d3',
        'scope': SCOPE, 'root_cause': ROOT_CAUSE,
        'tests_rerun': False, 'verification_registered': False,
        'physical_acceptance': 'not_assessed',
        'registered_verification_ref': EVIDENCE_REF,
        'input_files': [{'path': path.relative_to(SANDBOX).as_posix(),
                         'file_sha256': PINS[path], 'unchanged_during_extraction': True}
                        for path in PINS],
        'extractor_file_sha256': sha(Path(__file__).read_bytes()),
        'archived_streams': [stdout_location, stderr_location],
        'retained_result': result, 'summary': summary,
        'numerical_measurements': sorted(rows, key=lambda row: row['check']),
        'negative_fixture_observations': sorted(negatives, key=lambda row: row['check']),
        'other_measurement_observations': sorted(other, key=lambda row: row['check']),
        'retained_diagnostic_context': context,
    }
    json_text = json.dumps(report, indent=2, allow_nan=False) + '\n'
    md_text = markdown(report)
    OUT.mkdir(exist_ok=True)
    with DEST_JSON.open('x', encoding='utf-8') as stream:
        stream.write(json_text)
    with DEST_MD.open('x', encoding='utf-8') as stream:
        stream.write(md_text)
    print(json.dumps({'status': 'reporting_reconciliation_written',
                      'outputs': [path.relative_to(SANDBOX).as_posix()
                                  for path in (DEST_JSON, DEST_MD)],
                      'summary': summary, 'tests_rerun': False,
                      'verification_registered': False,
                      'retained_outcome': result['outcome']}, allow_nan=False))


if __name__ == '__main__':
    main()
