"""PDR-R12 state/frame/mass reporting correction; preserve checker 01.

Authorization: 66c7448f443f44ac9a016a1b384593a2 revision 1.
Human diagnostic: 49ab555137c7475890307e8e5f93f7d3 revision 1.
Historical failed verify_command request: b7d6f20b863f491c9545257a292c241a.

Confirmed reporting issue: checker 01 can emit outcome='passed' alongside
four deliberately unperformed null checks. The runtime consistency validator
requires a nonempty all-true checks map for a passed outcome. Execution and
JSON parsing were not the reported failure. No dependency change is needed
for this correction, and no new engineering authorization is inferred.

Caller audit: checker 01's main invokes hashes and run_checks, then prints
one result. This new entry point calls that same main unchanged, captures its
stdout, and changes only a passed outcome containing null checks to
inconclusive. Its checks and explanation are retained, with a reporting note
appended to the explanation. Existing callers and source files are unchanged.
No tolerance, fixture, plant implementation or analytical oracle is changed.

Publish this entry point before invoking verify_command:
  python -B software/pdr_r12_plant/verify_state_frames_mass_r12_02.py
Use repository='6dof_hopper', workdir='.'. Include artifact Refs for BOTH
checker files, configuration, fixture providers and all eight plant modules.
PINNED values below are file hashes, not Guacamole Ref hashes.

No files are written. Stdout contains exactly one VerificationResult JSON;
measurements, provenance and exceptions go to stderr. Preserve historical
failed requests and logs. When registering evidence, copy this execution's
actual outcome and explanation exactly. No vehicle or review acceptance.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import traceback
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
PREDECESSOR = 'verify_state_frames_mass_r12_01.py'
PINNED = {
    PREDECESSOR: '2d078567740c319776f97d5f17b7a8e54844a21a8a6a3e3f626917da701bba5c',
    'analytical_fixture_config_r12_01.json': '397133a2ab342cf35a29c4758adcb0e3f52682cc96dc85dfd0710323247b54c5',
    'analytical_fixture_models_r12_01.py': '25ae16b4a9fbfe42a1e083f952316a8d26cc69559fbef11f62c871f997d0e517',
    'repaired_hopper_r12/helpers/math.py': '281a5578b6d33c45578350429cb30ead28ba6a378c571c2c6929c60819ceecfb',
    'repaired_hopper_r12/simulation/state.py': 'b62a1a4fcc70a4a88e07f77996e955a64184891ce614957c85ccb7d63e90f294',
    'repaired_hopper_r12/chassis/hopper.py': 'f2b6e4b54634220105655e994e3ff5c78e84c60084879696a25ef39fdc29ff05',
    'repaired_hopper_r12/propulsion/propulsion.py': 'd860528b277893bbfe59527b7fcc2017955cc66681d3994fb66744a8006271de',
    'repaired_hopper_r12/propulsion/propeller.py': 'ce7be67ceae3866ecf402ee03b7812c3ea1e39c216ca5d412322af53d586ae3b',
    'repaired_hopper_r12/propulsion/actuators.py': 'bacfd1457ea3d24ae82d4868f3418b46c967fc2442d83d36e96973467645be78',
    'repaired_hopper_r12/simulation/environment.py': 'ba795b5d1d5344a1ecf5b2b5cc122255234d5ff394fb0dc41ee3366196aac03c',
    'repaired_hopper_r12/simulation/simulation.py': 'a186c50ab7c5500e7da14bb5c98a5c2772ff97d63645558be3cfdc3b6e5ca1a8',
}
UNPERFORMED = (
    'propulsion_and_actuator_analytical_checks_in_this_program',
    'numerical_trajectory_checks_in_this_program',
    'vehicle_closed_loop_mission_acceptance',
    'vehicle_physical_validation',
)


def read_bytes(relative):
    path = ROOT / relative
    if path.is_symlink() or ROOT not in path.resolve().parents:
        raise ValueError('Unexpected artifact path: ' + relative)
    return path.read_bytes()


def snapshot():
    return {
        name: hashlib.sha256(read_bytes(name)).hexdigest()
        for name in list(PINNED) + [Path(__file__).name]
    }


def main():
    before = snapshot()
    for name, expected in PINNED.items():
        if before[name] != expected:
            raise ValueError('Pinned artifact mismatch; review required: ' + name)
    raw = read_bytes(PREDECESSOR)
    if hashlib.sha256(raw).hexdigest() != PINNED[PREDECESSOR]:
        raise ValueError('Predecessor changed before loading')

    # Execute exactly the inspected, hash-checked predecessor bytes. Its
    # __main__ guard does not run until main is called explicitly below.
    module = ModuleType('pdr_r12_preserved_state_frame_mass_checker_01')
    module.__file__ = str(ROOT / PREDECESSOR)
    with redirect_stdout(sys.stderr):
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    captured = io.StringIO()
    with redirect_stdout(captured):
        module.main()
    result = json.loads(captured.getvalue())
    if not isinstance(result, dict) or set(result) != {'outcome', 'explanation', 'checks'}:
        raise ValueError('Unexpected predecessor result fields')
    if result['outcome'] not in ('passed', 'failed', 'unperformed', 'inconclusive'):
        raise ValueError('Unexpected predecessor outcome')
    if not isinstance(result['explanation'], str):
        raise ValueError('Predecessor explanation must be text')
    checks = result['checks']
    if not isinstance(checks, dict) or not checks:
        raise ValueError('Predecessor must return nonempty checks')
    if any(value is not None and type(value) is not bool for value in checks.values()):
        raise ValueError('Unexpected check value type')
    null_names = {name for name, value in checks.items() if value is None}
    if null_names != set(UNPERFORMED):
        raise ValueError('Unperformed scope changed; review before correction')

    original_outcome = result['outcome']
    if original_outcome == 'passed':
        if any(value is False for value in checks.values()):
            raise ValueError('Unexpected passed outcome with failed checks')
        result['outcome'] = 'inconclusive'
    # Never promote failed, unperformed or inconclusive results to passed.
    result['explanation'] += (
        ' Reporting correction 02 preserves all four null checks and all '
        'analytical checks; a passed outcome with null checks is reported '
        'as inconclusive under the clarified runtime contract.'
    )
    after = snapshot()
    if after != before:
        raise ValueError('Listed artifacts changed during verification')
    print(json.dumps({
        'reporting_correction': 'Outcome consistency only; no tests removed or changed',
        'diagnostic_source': '49ab555137c7475890307e8e5f93f7d3 revision 1',
        'historical_failed_request': 'b7d6f20b863f491c9545257a292c241a',
        'predecessor_outcome': original_outcome,
        'emitted_outcome': result['outcome'],
        'true_check_count': sum(value is True for value in checks.values()),
        'false_check_count': sum(value is False for value in checks.values()),
        'preserved_null_checks': sorted(null_names),
        'file_sha256_before': before,
        'file_sha256_after': after,
        'preservation_scope': 'Listed r12 artifacts only, not whole-checkout cleanliness',
        'controller_executed': False,
        'physical_acceptance': 'not_assessed',
    }, allow_nan=False, sort_keys=True), file=sys.stderr)
    print(json.dumps(result, allow_nan=False, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({
            'outcome': 'failed',
            'explanation': (
                'Reporting-correction entry point failed: '
                + type(error).__name__ + ': ' + str(error)
                + '. No corrected verification or physical acceptance is established; '
                'historical checker and failed request remain preserved.'
            ),
            'checks': dict(
                {'reporting_correction_completed': False},
                **{name: None for name in UNPERFORMED},
            ),
        }, allow_nan=False, sort_keys=True))
