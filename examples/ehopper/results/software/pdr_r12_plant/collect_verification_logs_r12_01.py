"""Capture r12 checker logs and tabulate their measured errors.

Authorization: work plan 66c7448f443f44ac9a016a1b384593a2 revision 1, task
pdr_r12_preliminary_plant, deliverable PDR-R12-PLANT-CONTROL (artifact kind
test_logs). Frames: decision f046cc4fe5294a6f9a61027529056f61 revision 1.

LOG COLLECTOR, NOT A VERIFICATION PROGRAM. It re-executes the four published
r12 checker entry points, each in its own subprocess with this interpreter and
environment, retains their complete stdout/stderr, and tabulates the measured
errors that the checkers print as JSON diagnostics on stderr. Registered
verification outcomes remain these verify_command evidence records:
  PDR-R12-PLANT-STATE-FRAME-MASS-VERIFICATION-02     request 21ca2850ef224d3bbb276822db3dd2ff
  PDR-R12-PLANT-PROPULSION-INTERFACE-VERIFICATION-01 request 9de4362ce7284d998d70953f1d4599fa
  PDR-R12-PLANT-SOLVER-OPEN-LOOP-VERIFICATION-01     request a0229a233f1947cea5f61cd143ae5ffc
  PDR-R12-PLANT-ACTUATOR-RESPONSE-VERIFICATION-01    request 477c2f40ce7242cb9a9a8810e17993e3
Those registered runs returned VerificationResult JSON only; their stderr
measurements were not retained as artifacts. The re-runs execute the same
files, whose SHA-256 values are compared with the published file hashes before
and after execution. Agreement with a registered outcome is a reproducibility
observation, not new acceptance evidence. Exit status is recorded but is never
treated as a verification pass.

Run through Guacamole execute with repository='6dof_hopper', workdir='.':
  python -B software/pdr_r12_plant/collect_verification_logs_r12_01.py
Declare these outputs; existing files are never overwritten:
  software/pdr_r12_plant/test_logs_r12_01/checker_raw_logs_r12_01.txt
  software/pdr_r12_plant/test_logs_r12_01/measured_error_digest_r12_01.json
  software/pdr_r12_plant/test_logs_r12_01/measured_error_digest_r12_01.md
Only a short JSON status is printed to stdout.

All fixtures are synthetic analytical fixtures. Tolerances are the proposed
numerical regression thresholds in analytical_fixture_config_r12_01.json, not
human-agreed vehicle acceptance limits. No PID tuning, vehicle mission,
electrical/thermal endurance, physical validation or PDR/CDR acceptance is
tested or implied.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

sys.dont_write_bytecode = True
NL = chr(10)  # newline character, kept free of escape sequences
HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parents[1]
RELATIVE_HERE = 'software/pdr_r12_plant'
OUT = HERE / 'test_logs_r12_01'
RAW = OUT / 'checker_raw_logs_r12_01.txt'
DIGEST_JSON = OUT / 'measured_error_digest_r12_01.json'
DIGEST_MD = OUT / 'measured_error_digest_r12_01.md'
PER_CHECKER_TIMEOUT_S = 1500.0
TOP_ROWS = 12
SCOPE = (
    'Test-log capture and measured-error tabulation only. Registered '
    'verification outcomes are the verify_command evidence records named per '
    'checker; these re-executions of the same hash-pinned files retain the '
    'stdout/stderr and measured errors that the registered runs did not retain '
    'as artifacts. All fixtures are synthetic analytical fixtures. Tolerances '
    'are proposed numerical regression thresholds from '
    'analytical_fixture_config_r12_01.json, not human-agreed vehicle acceptance '
    'limits. Process exit status is not a verification pass. No PID tuning, '
    'vehicle closed-loop mission, electrical/thermal endurance, physical '
    'validation or PDR/CDR acceptance is tested or implied.'
)
PUBLISHED_FILE_SHA256 = {
    'analytical_fixture_config_r12_01.json':
        '397133a2ab342cf35a29c4758adcb0e3f52682cc96dc85dfd0710323247b54c5',
    'analytical_fixture_models_r12_01.py':
        '25ae16b4a9fbfe42a1e083f952316a8d26cc69559fbef11f62c871f997d0e517',
    'repaired_hopper_r12/helpers/math.py':
        '281a5578b6d33c45578350429cb30ead28ba6a378c571c2c6929c60819ceecfb',
    'repaired_hopper_r12/simulation/state.py':
        'b62a1a4fcc70a4a88e07f77996e955a64184891ce614957c85ccb7d63e90f294',
    'repaired_hopper_r12/chassis/hopper.py':
        'f2b6e4b54634220105655e994e3ff5c78e84c60084879696a25ef39fdc29ff05',
    'repaired_hopper_r12/propulsion/propulsion.py':
        'd860528b277893bbfe59527b7fcc2017955cc66681d3994fb66744a8006271de',
    'repaired_hopper_r12/propulsion/propeller.py':
        'ce7be67ceae3866ecf402ee03b7812c3ea1e39c216ca5d412322af53d586ae3b',
    'repaired_hopper_r12/propulsion/actuators.py':
        'bacfd1457ea3d24ae82d4868f3418b46c967fc2442d83d36e96973467645be78',
    'repaired_hopper_r12/simulation/environment.py':
        'ba795b5d1d5344a1ecf5b2b5cc122255234d5ff394fb0dc41ee3366196aac03c',
    'repaired_hopper_r12/simulation/simulation.py':
        'a186c50ab7c5500e7da14bb5c98a5c2772ff97d63645558be3cfdc3b6e5ca1a8',
    'verify_state_frames_mass_r12_01.py':
        '2d078567740c319776f97d5f17b7a8e54844a21a8a6a3e3f626917da701bba5c',
    'verify_state_frames_mass_r12_02.py':
        '040db6b78e888996bd05ec1cf975d2d5cb2d3d0ead6c41f6ad72a3205fbe91d1',
    'verify_propulsion_interfaces_r12_01.py':
        '99e8ff520f11c09957ebe1eadaa583f260e8b36d4d8095d33669653d0e049615',
    'verify_solver_open_loop_r12_01.py':
        'e18851bfbec6bde60ff99f40bde4fc95645300544f7c5736e7323e92f226a1e7',
    'verify_actuator_response_r12_01.py':
        'b23611266cdb84cb1d226eb9ffa2b5d6a4559956895f4538884471b181a3a03c',
}
CHECKERS = (
    {'label': 'state_frames_mass_02',
     'path': 'verify_state_frames_mass_r12_02.py',
     'artifact': 'PDR-R12-PLANT-STATE-FRAME-MASS-VERIFIER-02',
     'registered_evidence': 'PDR-R12-PLANT-STATE-FRAME-MASS-VERIFICATION-02',
     'registered_request': '21ca2850ef224d3bbb276822db3dd2ff',
     'registered_outcome': 'inconclusive', 'registered_true_checks': 83},
    {'label': 'propulsion_interfaces_01',
     'path': 'verify_propulsion_interfaces_r12_01.py',
     'artifact': 'PDR-R12-PLANT-PROPULSION-INTERFACE-VERIFIER-01',
     'registered_evidence': 'PDR-R12-PLANT-PROPULSION-INTERFACE-VERIFICATION-01',
     'registered_request': '9de4362ce7284d998d70953f1d4599fa',
     'registered_outcome': 'inconclusive', 'registered_true_checks': 151},
    {'label': 'solver_open_loop_01',
     'path': 'verify_solver_open_loop_r12_01.py',
     'artifact': 'PDR-R12-PLANT-SOLVER-OPEN-LOOP-VERIFIER-01',
     'registered_evidence': 'PDR-R12-PLANT-SOLVER-OPEN-LOOP-VERIFICATION-01',
     'registered_request': 'a0229a233f1947cea5f61cd143ae5ffc',
     'registered_outcome': 'inconclusive', 'registered_true_checks': 146},
    {'label': 'actuator_response_01',
     'path': 'verify_actuator_response_r12_01.py',
     'artifact': 'PDR-R12-PLANT-ACTUATOR-RESPONSE-VERIFIER-01',
     'registered_evidence': 'PDR-R12-PLANT-ACTUATOR-RESPONSE-VERIFICATION-01',
     'registered_request': '477c2f40ce7242cb9a9a8810e17993e3',
     'registered_outcome': 'inconclusive', 'registered_true_checks': 116},
)
ERROR_HEADER = ['check', 'measured error', 'tolerance', 'unit',
                'error/tolerance', 'within']


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def observed_hashes():
    observed = {}
    for relative in PUBLISHED_FILE_SHA256:
        path = HERE / relative
        if path.is_symlink() or not path.is_file():
            observed[relative] = None
        else:
            observed[relative] = sha256_bytes(path.read_bytes())
    return observed


def distribution(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return 'not found'


def finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def bump(counter, key):
    counter[key] = counter.get(key, 0) + 1


def parse_result(stdout_text):
    """Summarize the checker's own VerificationResult; never reinterpret it."""
    summary = {'parsed': False}
    try:
        value = json.loads(stdout_text)
    except ValueError as error:
        summary['parse_error'] = str(error)[:300]
        return summary
    checks = value.get('checks') if isinstance(value, dict) else None
    if not isinstance(checks, dict):
        summary['parse_error'] = 'stdout is not one object with a checks map'
        return summary
    summary.update({
        'parsed': True,
        'outcome': value.get('outcome'),
        'explanation': value.get('explanation'),
        'check_count': len(checks),
        'true_count': sum(1 for v in checks.values() if v is True),
        'false_checks': sorted(k for k, v in checks.items() if v is False),
        'null_checks': sorted(k for k, v in checks.items() if v is None),
        'non_boolean_checks': sorted(
            k for k, v in checks.items() if not (v is None or isinstance(v, bool))),
    })
    return summary


def measured_row(name, details, line, error_key):
    error, tolerance = details.get(error_key), details.get('tolerance')
    row = {
        'check': name, 'stderr_line': line, 'error_field': error_key,
        'measured_error': error, 'tolerance': tolerance,
        'unit': details.get('unit'), 'within_tolerance': None,
        'error_to_tolerance_ratio': None, 'exact_comparison': False,
    }
    if finite_number(error) and finite_number(tolerance):
        row['within_tolerance'] = bool(error <= tolerance)
        if tolerance > 0:
            ratio = float(error) / float(tolerance)
            row['error_to_tolerance_ratio'] = ratio if math.isfinite(ratio) else None
        else:
            row['exact_comparison'] = True
            if error == 0:
                row['error_to_tolerance_ratio'] = 0.0
    for key in ('actual_at_max_error', 'expected_at_max_error'):
        if key in details:
            row[key] = details[key]
    return row


def summarize(rows):
    rated = [r for r in rows if r['error_to_tolerance_ratio'] is not None]
    worst = max(rated, key=lambda r: r['error_to_tolerance_ratio'], default=None)
    units = {}
    for r in rows:
        bump(units, str(r['unit']))
    return {
        'measured_rows': len(rows),
        'within_tolerance': sum(1 for r in rows if r['within_tolerance'] is True),
        'outside_tolerance': sum(1 for r in rows if r['within_tolerance'] is False),
        'undetermined': sum(1 for r in rows if r['within_tolerance'] is None),
        'zero_tolerance_exact_comparisons': sum(1 for r in rows if r['exact_comparison']),
        'worst_ratio': None if worst is None else worst['error_to_tolerance_ratio'],
        'worst_check': None if worst is None else worst['check'],
        'rows_by_unit': dict(sorted(units.items())),
    }


def parse_diagnostics(stderr_text):
    """Tabulate JSON diagnostic lines; retain examples of all other lines."""
    measured, unpaired, negatives, shape_failures, unparsed = [], [], [], [], []
    other_keys = {}
    json_lines = check_lines = 0
    for number, line in enumerate(stderr_text.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except ValueError:
            unparsed.append({'line': number, 'text': text[:240]})
            continue
        json_lines += 1
        if not isinstance(value, dict):
            bump(other_keys, '<non-object JSON>')
            continue
        name, details = value.get('check'), value.get('details')
        if not (isinstance(name, str) and isinstance(details, dict)):
            for key in value:
                bump(other_keys, str(key))
            continue
        check_lines += 1
        if details.get('deliberate_negative_fixture') is True:
            negatives.append({'check': name, 'exception': details.get('exception')})
            continue
        if details.get('shape_or_finiteness_failure') is True:
            shape_failures.append({'check': name, 'stderr_line': number})
            continue
        error_fields = sorted(k for k, v in details.items()
                              if 'error' in k.lower() and finite_number(v))
        if 'max_absolute_error' in details:
            measured.append(measured_row(name, details, number, 'max_absolute_error'))
        elif len(error_fields) == 1 and 'tolerance' in details:
            measured.append(measured_row(name, details, number, error_fields[0]))
        elif error_fields:
            unpaired.append({'check': name, 'stderr_line': number,
                             'fields': {k: details[k] for k in error_fields},
                             'detail_keys': sorted(details)})
        else:
            bump(other_keys, '<check details without top-level error fields>')
    return {
        'stderr_json_lines': json_lines,
        'check_diagnostic_lines': check_lines,
        'measured': measured,
        'measured_summary': summarize(measured),
        'unpaired_error_fields': unpaired,
        'deliberate_negative_fixture_checks': negatives,
        'shape_or_finiteness_failures': shape_failures,
        'other_diagnostic_key_counts': dict(sorted(other_keys.items())),
        'unparsed_line_count': len(unparsed),
        'unparsed_examples': unparsed[:20],
    }


def run_checker(spec, environment):
    relative = RELATIVE_HERE + '/' + spec['path']
    command = [sys.executable, '-B', relative]
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(command, cwd=SANDBOX, env=environment,
                                   capture_output=True, check=False,
                                   timeout=PER_CHECKER_TIMEOUT_S)
        stdout, stderr = completed.stdout, completed.stderr
        returncode = completed.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b'', error.stderr or b''
        returncode, timed_out = None, True
    duration = time.monotonic() - started
    stdout_text = stdout.decode('utf-8', errors='replace')
    stderr_text = stderr.decode('utf-8', errors='replace')
    result = parse_result(stdout_text)
    record = dict(spec)
    record.update({
        'checker_file': relative,
        'command': ['python', '-B', relative],
        'started_utc': started_utc,
        'duration_s': round(duration, 3),
        'returncode': returncode,
        'timed_out': timed_out,
        'stdout_bytes': len(stdout), 'stdout_sha256': sha256_bytes(stdout),
        'stderr_bytes': len(stderr), 'stderr_sha256': sha256_bytes(stderr),
        'result': result,
        'outcome_matches_registered': result.get('outcome') == spec['registered_outcome'],
        'true_count_matches_registered':
            result.get('true_count') == spec['registered_true_checks'],
        'diagnostics': parse_diagnostics(stderr_text),
    })
    return record, stdout_text, stderr_text


def fmt(value):
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return '0' if value == 0.0 else format(value, '.3e')
    return str(value).replace('|', '/')


def table(header, rows):
    lines = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    for row in rows:
        lines.append('| ' + ' | '.join(fmt(x) for x in row) + ' |')
    return lines


def ranked(rows):
    return sorted(rows, key=lambda r: (r['within_tolerance'] is not False,
                                       -(r['error_to_tolerance_ratio'] or 0.0),
                                       r['check']))


def counts(result):
    if not result.get('parsed'):
        return 'unparsed'
    return '%d/%d/%d' % (result['true_count'], len(result['false_checks']),
                         len(result['null_checks']))


def error_rows(rows):
    return [[x['check'], x['measured_error'], x['tolerance'], x['unit'],
             x['error_to_tolerance_ratio'], x['within_tolerance']] for x in rows]


def markdown(digest):
    env = digest['environment']
    lines = [
        '# PDR r12 plant checker logs and measured errors (digest 01)', '',
        'Generated (UTC): ' + digest['generated_utc'], '',
        'Collector: `' + digest['collector'] + '`. Raw stdout/stderr: `'
        + digest['raw_log'] + '`. Structured digest: `' + digest['digest_json'] + '`.',
        '',
        '**Scope.** ' + SCOPE, '',
        '## Execution environment', '',
        '- Interpreter: `' + env['interpreter'] + '`, ' + env['implementation']
        + ' ' + env['python_version'],
        '- numpy ' + env['numpy'] + ', scipy ' + env['scipy']
        + ' (distribution metadata)',
        '- Platform: ' + env['platform'],
        '- Checker working directory: `' + env['checker_cwd']
        + '`; PYTHONDONTWRITEBYTECODE=1; one subprocess per checker', '',
        '## Artifact binding', '',
        'File SHA-256 values, not Guacamole Ref hashes; 12-character prefixes '
        'shown, full values in the JSON digest. All equal: '
        + fmt(digest['artifact_binding_all_match']) + '.', '',
    ]
    lines += table(['file', 'published', 'before runs', 'after runs', 'all equal'], [
        [b['file'], b['published_sha256'][:12],
         (b['observed_before'] or 'missing')[:12],
         (b['observed_after'] or 'missing')[:12], b['matches_published']]
        for b in digest['artifact_binding']])
    lines += ['', '## Checker re-runs', '',
              'Outcomes and counts are copied from each re-run VerificationResult and '
              'are not reinterpreted. Registered evidence is unchanged.', '']
    lines += table(
        ['checker', 'registered evidence (request)', 'registered outcome',
         're-run outcome', 'true/false/null', 'return code', 'timed out',
         'duration (s)', 'measured rows', 'outside tolerance',
         'worst error/tolerance', 'worst check'],
        [[r['label'], r['registered_evidence'] + ' (' + r['registered_request'] + ')',
          r['registered_outcome'], r['result'].get('outcome'), counts(r['result']),
          r['returncode'], r['timed_out'], '%.1f' % r['duration_s'],
          r['diagnostics']['measured_summary']['measured_rows'],
          r['diagnostics']['measured_summary']['outside_tolerance'],
          r['diagnostics']['measured_summary']['worst_ratio'],
          r['diagnostics']['measured_summary']['worst_check']]
         for r in digest['runs']])
    lines += ['', '## Unperformed (null) and false checks', '']
    for r in digest['runs']:
        result = r['result']
        lines.append('- ' + r['label'] + ': null = '
                     + (', '.join(result.get('null_checks', [])) or 'none')
                     + '; false = '
                     + (', '.join(result.get('false_checks', [])) or 'none'))
    lines += ['', '## Largest error-to-tolerance ratios', '',
              'Ratios use the proposed regression tolerance. Zero-tolerance rows are '
              'exact comparisons, reported with ratio 0 when exactly equal.', '']
    for r in digest['runs']:
        summary = r['diagnostics']['measured_summary']
        lines += ['### ' + r['label'], '',
                  'Rows %d; within %d; outside %d; undetermined %d; exact comparisons '
                  '%d; rows by unit %s.' % (
                      summary['measured_rows'], summary['within_tolerance'],
                      summary['outside_tolerance'], summary['undetermined'],
                      summary['zero_tolerance_exact_comparisons'],
                      json.dumps(summary['rows_by_unit'], sort_keys=True)), '']
        lines += table(ERROR_HEADER,
                       error_rows(ranked(r['diagnostics']['measured'])[:TOP_ROWS]))
        lines.append('')
    lines += ['## Other diagnostics', '']
    for r in digest['runs']:
        d = r['diagnostics']
        lines.append(
            '- %s: stderr JSON lines %d; check diagnostics %d; deliberate negative '
            'fixtures %d; shape/finiteness failures %d; error fields without a '
            'paired tolerance %d; unparsed stderr lines %d.' % (
                r['label'], d['stderr_json_lines'], d['check_diagnostic_lines'],
                len(d['deliberate_negative_fixture_checks']),
                len(d['shape_or_finiteness_failures']),
                len(d['unpaired_error_fields']), d['unparsed_line_count']))
    lines += ['', '## Complete measured-error tables', '']
    for r in digest['runs']:
        rows = sorted(r['diagnostics']['measured'], key=lambda x: x['check'])
        lines += ['### ' + r['label'] + ' (sorted by check name)', '']
        lines += table(ERROR_HEADER, error_rows(rows))
        lines.append('')
    lines += [
        '## Interpretation limits', '',
        '- Oracles are those labelled by each checker: closed-form analytical '
        'expectations, finite differences, refinement or alternate-method '
        'agreement. Numerical agreement is not independent physical validation.',
        '- Limits observed at output samples and dense midpoints are not continuous '
        'certification.',
        '- Fixture masses, geometry, paired-map coefficients, actuator parameters and '
        'tolerances are synthetic; none is a selected vehicle input.',
        '- Re-run outcomes neither replace nor upgrade the registered inconclusive '
        'evidence; null checks remain unperformed.',
        '- No PID tuning, vehicle mission, electrical/thermal, structural, physical '
        'or PDR/CDR acceptance follows from these logs.',
    ]
    return NL.join(lines) + NL


def main():
    for destination in (RAW, DIGEST_JSON, DIGEST_MD):
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('Preserve existing output: ' + str(destination))
    if (SANDBOX / RELATIVE_HERE).resolve() != HERE:
        raise RuntimeError('Unexpected sandbox layout')
    if OUT.is_symlink():
        raise RuntimeError('Output directory must not be a symlink')
    OUT.mkdir(exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    before = observed_hashes()
    environment = dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    collected = [run_checker(spec, environment) for spec in CHECKERS]
    after = observed_hashes()
    binding = [{
        'file': RELATIVE_HERE + '/' + relative,
        'published_sha256': published,
        'observed_before': before[relative],
        'observed_after': after[relative],
        'matches_published': before[relative] == published and after[relative] == published,
    } for relative, published in PUBLISHED_FILE_SHA256.items()]
    runs = [record for record, _, _ in collected]
    digest = {
        'schema': 'pdr_r12_checker_log_digest_v1',
        'generated_utc': generated,
        'work_plan': '66c7448f443f44ac9a016a1b384593a2 revision 1',
        'task': 'pdr_r12_preliminary_plant',
        'collector': RELATIVE_HERE + '/' + Path(__file__).name,
        'raw_log': RAW.relative_to(SANDBOX).as_posix(),
        'digest_json': DIGEST_JSON.relative_to(SANDBOX).as_posix(),
        'digest_markdown': DIGEST_MD.relative_to(SANDBOX).as_posix(),
        'scope': SCOPE,
        'verification_registered_by_this_program': False,
        'physical_acceptance': 'not_assessed',
        'environment': {
            'interpreter': sys.executable,
            'implementation': platform.python_implementation(),
            'python_version': platform.python_version(),
            'numpy': distribution('numpy'),
            'scipy': distribution('scipy'),
            'platform': platform.platform(),
            'checker_cwd': str(SANDBOX),
            'pythonpath': os.environ.get('PYTHONPATH', ''),
        },
        'artifact_binding': binding,
        'artifact_binding_all_match': all(b['matches_published'] for b in binding),
        'runs': runs,
    }
    raw = ['PDR r12 plant checker raw logs (collector 01), generated ' + generated + '.',
           SCOPE, '']
    for record, stdout_text, stderr_text in collected:
        for stream_name, text in (('stdout', stdout_text), ('stderr', stderr_text)):
            raw.append('===== BEGIN %s %s (bytes=%d, sha256=%s, returncode=%s, '
                       'timed_out=%s) =====' % (
                           record['label'], stream_name, record[stream_name + '_bytes'],
                           record[stream_name + '_sha256'], record['returncode'],
                           record['timed_out']))
            raw.append(text.rstrip(NL))
            raw.append('===== END %s %s =====' % (record['label'], stream_name))
            raw.append('')
    with RAW.open('x', encoding='utf-8') as stream:
        stream.write(NL.join(raw) + NL)
    with DIGEST_JSON.open('x', encoding='utf-8') as stream:
        json.dump(digest, stream, indent=2, allow_nan=False)
        stream.write(NL)
    with DIGEST_MD.open('x', encoding='utf-8') as stream:
        stream.write(markdown(digest))
    print(json.dumps({
        'status': 'logs_collected',
        'artifact_binding_all_match': digest['artifact_binding_all_match'],
        'outputs': [digest['raw_log'], digest['digest_json'], digest['digest_markdown']],
        'runs': [{
            'label': r['label'], 'returncode': r['returncode'],
            'timed_out': r['timed_out'], 'duration_s': r['duration_s'],
            'outcome': r['result'].get('outcome'),
            'true_false_null': counts(r['result']),
            'outcome_matches_registered': r['outcome_matches_registered'],
            'true_count_matches_registered': r['true_count_matches_registered'],
            'measured_rows': r['diagnostics']['measured_summary']['measured_rows'],
            'outside_tolerance': r['diagnostics']['measured_summary']['outside_tolerance'],
            'worst_ratio': r['diagnostics']['measured_summary']['worst_ratio'],
            'unparsed_stderr_lines': r['diagnostics']['unparsed_line_count'],
        } for r in runs],
        'verification_registered_by_this_program': False,
        'physical_acceptance': 'not_assessed',
    }, allow_nan=False, sort_keys=True))


if __name__ == '__main__':
    main()
