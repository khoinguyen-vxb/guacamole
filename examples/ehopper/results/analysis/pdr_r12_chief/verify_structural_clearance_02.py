"""R12 clearance-verification correction entrypoint 02.

Retains and hash-pins verify_structural_clearance_01.py as an editable dependency.
Historical failed verification: cb2e1250292e4b6e976a56cfc7541ce8.
Root cause: integer fixture endpoints propagate to zeros_like(numerator), so
np.divide cannot store floating-point quotients in the integer output buffer.
Affected callers: pair_reference and independent_reference_fixtures.

Only the segment-distance input boundary changes: all four endpoints become
float64 before the unchanged reference algorithm runs. Original fixtures,
artifact hashes, comparison tolerances, geometry checks and acceptance scope
remain intact. Additional integer/float/batched/degenerate fixtures are included.
No original files, stored results or supplied repositories are modified.

Publish this entrypoint, then use verify_command with artifact Refs for BOTH
checker files, the configuration, analysis source and stored results. Execution
of this source has not been established merely by writing it.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
PREDECESSOR_NAME = 'verify_structural_clearance_01.py'
PREDECESSOR_SHA256 = 'bd06aac5da139cc9b2908dbd751d08098c8817172a19f082280c36f95c534e69'
FAILED_REQUEST = 'cb2e1250292e4b6e976a56cfc7541ce8'


def main():
    here = Path(__file__).resolve()
    predecessor = here.with_name(PREDECESSOR_NAME)
    self_digest = hashlib.sha256(here.read_bytes()).hexdigest()
    raw = predecessor.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PREDECESSOR_SHA256:
        raise ValueError('Historical checker hash mismatch; do not reuse an unreviewed version')

    spec = importlib.util.spec_from_file_location('r12_clearance_verifier_preserved_01', predecessor)
    module = importlib.util.module_from_spec(spec)
    # Compile the exact hash-checked bytes. The original main guard does not run.
    with contextlib.redirect_stdout(sys.stderr):
        exec(compile(raw, str(predecessor), 'exec'), module.__dict__)

    original_distance = module.segment_segment_min
    original_fixtures = module.independent_reference_fixtures
    original_unchanged = module.unchanged_inputs

    def segment_segment_float64(a, b, c, d):
        np = module.np  # Established by the original main's capability check.
        endpoints = [np.asarray(value, dtype=np.float64) for value in (a, b, c, d)]
        for value in endpoints:
            module.require(value.ndim in (1, 2) and value.shape[-1] == 3,
                           'Segment endpoint must have shape (3,) or (N,3)')
            module.require(np.isfinite(value).all(), 'Nonfinite segment endpoint')
        # The existing constrained-quadratic algorithm is unchanged. Its
        # zeros_like output buffers now inherit floating-point dtype.
        return original_distance(*endpoints)

    module.segment_segment_min = segment_segment_float64

    def reference_fixtures_with_dtype_regressions():
        original_fixtures()
        np = module.np
        cases = [
            (([-1,0,0], [1,0,0], [0,-1,0], [0,1,0]), 0.0),
            (([0,0,0], [2,2,0], [1,0,0], [1,0,0]), math.sqrt(0.5)),
            (([0,0,0], [1,0,0], [2,1,0], [2,1,0]), math.sqrt(2)),
            (([0,0,0], [1,0,0], [0,2,0], [1,2,0]), 2.0),
            (([0,0,0], [0,0,0], [1,0,0], [1,0,0]), 1.0),
        ]
        count = 0
        for endpoints, expected in cases:
            reference = None
            for representation in ('integer_lists', 'int64_arrays', 'float64_arrays'):
                if representation == 'integer_lists':
                    values = [list(v) for v in endpoints]
                else:
                    dtype = np.int64 if representation == 'int64_arrays' else np.float64
                    values = [np.asarray(v, dtype=dtype) for v in endpoints]
                before = [np.asarray(v).copy() for v in values]
                lower, upper = module.segment_segment_min(*values)
                module.require(lower.shape == upper.shape == (1,), 'Regression result shape')
                module.require(lower[0]-module.TOL <= expected <= upper[0]+module.TOL,
                               'Analytical distance regression: '+representation)
                module.require(np.issubdtype(lower.dtype, np.floating) and
                               np.issubdtype(upper.dtype, np.floating), 'Distance output dtype')
                if reference is None:
                    reference = (lower.copy(), upper.copy())
                else:
                    module.near(lower, reference[0], 'Integer/float lower-bound agreement')
                    module.near(upper, reference[1], 'Integer/float upper-bound agreement')
                for old, current in zip(before, values):
                    module.require(np.array_equal(old, np.asarray(current)), 'Endpoint input mutated')
                count += 1

        batched = [np.asarray([case[0][j] for case in cases], dtype=np.int64) for j in range(4)]
        before = [v.copy() for v in batched]
        expected = np.asarray([case[1] for case in cases], dtype=np.float64)
        lower, upper = module.segment_segment_min(*batched)
        module.require(lower.shape == upper.shape == expected.shape, 'Batched regression shape')
        module.require(np.all(lower-module.TOL <= expected) and np.all(expected <= upper+module.TOL),
                       'Batched analytical distance regression')
        for old, current in zip(before, batched):
            module.require(np.array_equal(old, current), 'Batched endpoint input mutated')
        count += 1

        for invalid in ([float('nan'),0,0], [0,0]):
            try:
                module.segment_segment_min(invalid, [1,0,0], [0,1,0], [1,1,0])
            except AssertionError:
                pass
            else:
                raise AssertionError('Invalid segment endpoint was not rejected')
        module.METRICS['additional_dtype_regression_comparisons'] = count
        module.METRICS['additional_invalid_endpoint_cases'] = 2

    module.independent_reference_fixtures = reference_fixtures_with_dtype_regressions

    def unchanged_with_checker_dependencies():
        original_unchanged()
        module.require(hashlib.sha256(predecessor.read_bytes()).hexdigest() == PREDECESSOR_SHA256,
                       'Historical checker changed during verification')
        module.require(hashlib.sha256(here.read_bytes()).hexdigest() == self_digest,
                       'Correction entrypoint changed during verification')

    module.unchanged_inputs = unchanged_with_checker_dependencies
    module.METRICS.update(
        correction_entrypoint_file_sha256=self_digest,
        preserved_checker_file_sha256=PREDECESSOR_SHA256,
        historical_failed_verification_request=FAILED_REQUEST,
        correction_scope='Float64 endpoint boundary; unchanged reference algorithm and original checks',
    )

    # Buffer the original main's output so even an unexpected exception cannot
    # leave partial output followed by a second result object on stdout.
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        module.main()
    result = json.loads(captured.getvalue())
    if set(result) != {'outcome', 'explanation', 'checks'}:
        raise ValueError('Unexpected VerificationResult fields')
    if result['outcome'] not in ('passed', 'failed', 'unperformed', 'inconclusive'):
        raise ValueError('Unexpected verification outcome')
    if not isinstance(result['explanation'], str) or not isinstance(result['checks'], dict):
        raise ValueError('Invalid VerificationResult types')
    if any(value is not None and not isinstance(value, bool) for value in result['checks'].values()):
        raise ValueError('Invalid check value')
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        diagnostic = type(exc).__name__+': '+str(exc)
        print(diagnostic, file=sys.stderr)
        print(json.dumps({
            'outcome': 'failed',
            'explanation': 'Correction entrypoint failed: '+diagnostic+'. No verification or physical acceptance is inferred. Historical failed result remains preserved.',
            'checks': {'correction_entrypoint_completed': False, 'clearance_study_acceptance': None, 'physical_validation': None}
        }, allow_nan=False))
