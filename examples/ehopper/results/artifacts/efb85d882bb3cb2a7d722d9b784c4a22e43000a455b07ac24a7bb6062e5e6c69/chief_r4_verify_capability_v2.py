"""Check retained synthetic FreeCAD capability artifacts, not the vehicle.

Revision 2 preserves the original probe checks and numerical tolerances.
Only in-scope boolean checks participate in its outcome. Vehicle geometry,
mass properties and physical validation remain unperformed and outside scope.

Run through verify_command with this source, the retained probe generator,
measurements, native file and STEP artifact references in tool inputs.
Stdout contains exactly one VerificationResult JSON object. Diagnostics use
stderr. This program writes no files and does not rerun the geometry kernel.
Recorded geometry observations are bound to current native/STEP files by their
captured paths, sizes and SHA256 digests.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

SCHEMA = 'chief_freecad_capability_measurements_v1'
EXPECTED_SCOPE = 'Synthetic backend probe only; no vehicle acceptance or physical validation.'
EXPECTED_DIMENSIONS_MM = (10.0, 20.0, 30.0)
EDIT_LENGTH_MM = 11.0
DIMENSION_ABS_TOL_MM = 1.0e-8
VOLUME_ABS_TOL_MM3 = 1.0e-6
REL_TOL = 1.0e-9
PATHS = {
    'measurements': 'cad/chief_r4_capability/measurements.json',
    'native': 'cad/chief_r4_capability/probe.FCStd',
    'step': 'cad/chief_r4_capability/probe.step',
}


def finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def close_number(actual, expected, absolute_tolerance):
    return (finite_number(actual)
            and math.isclose(actual, expected, rel_tol=REL_TOL,
                             abs_tol=absolute_tolerance))


def close_vector(actual, expected):
    return (isinstance(actual, (list, tuple))
            and len(actual) == len(expected)
            and all(close_number(a, e, DIMENSION_ABS_TOL_MM)
                    for a, e in zip(actual, expected)))


def mapping(value):
    return value if isinstance(value, dict) else {}


def confined_path(sandbox, relative):
    path = (sandbox / relative).resolve(strict=True)
    path.relative_to(sandbox)
    if not path.is_file():
        raise ValueError('Expected a regular artifact file: ' + relative)
    return path


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def inspect_geometry(checks, prefix, geometry, dimensions):
    geometry = mapping(geometry)
    bounds = mapping(geometry.get('bounding_box_mm'))
    count = geometry.get('solid_count')
    checks[prefix + '_non_null'] = geometry.get('is_null') is False
    checks[prefix + '_valid'] = geometry.get('is_valid') is True
    checks[prefix + '_one_solid'] = type(count) is int and count == 1
    checks[prefix + '_analytical_volume'] = close_number(
        geometry.get('volume_mm3'), math.prod(dimensions), VOLUME_ABS_TOL_MM3)
    checks[prefix + '_bounding_minimum'] = close_vector(
        bounds.get('minimum'), (0.0, 0.0, 0.0))
    checks[prefix + '_bounding_maximum'] = close_vector(
        bounds.get('maximum'), dimensions)
    checks[prefix + '_bounding_lengths'] = close_vector(
        bounds.get('lengths'), dimensions)


def verify(sandbox, checks):
    paths = {key: confined_path(sandbox, relative)
             for key, relative in PATHS.items()}
    if paths['measurements'].stat().st_size > 1024 * 1024:
        raise ValueError('Probe measurement report exceeds the bounded reader limit')
    with paths['measurements'].open('r', encoding='utf-8') as stream:
        report = json.load(stream)
    if not isinstance(report, dict):
        raise ValueError('Measurement report must be a JSON object')

    checks['measurement_schema'] = report.get('schema') == SCHEMA
    checks['synthetic_scope_explicit'] = report.get('scope') == EXPECTED_SCOPE
    checks['capture_completed'] = report.get('execution_completed') is True
    checks['capture_final_stage'] = report.get('last_stage') == 'completed'
    checks['capture_cleanup_without_errors'] = report.get('cleanup_errors') == []
    units = mapping(report.get('units'))
    checks['length_units_mm'] = units.get('dimensions') == 'mm'
    checks['volume_units_mm3'] = units.get('volume') == 'mm^3'
    checks['configured_box_dimensions'] = close_vector(
        report.get('configured_dimensions_mm'), EXPECTED_DIMENSIONS_MM)
    checks['configured_edit_length'] = close_number(
        report.get('edit_test_length_mm'), EDIT_LENGTH_MM, DIMENSION_ABS_TOL_MM)

    artifacts = mapping(report.get('artifacts'))
    for key in ('native', 'step'):
        metadata = mapping(artifacts.get(key))
        actual_size = paths[key].stat().st_size
        checks[key + '_reported_path_matches'] = metadata.get('path') == PATHS[key]
        checks[key + '_nonempty_file'] = actual_size > 0
        expected_size = metadata.get('size_bytes')
        checks[key + '_size_matches_capture'] = (
            type(expected_size) is int and expected_size == actual_size)
        checks[key + '_sha256_matches_capture'] = (
            metadata.get('sha256') == digest(paths[key]))

    observations = mapping(report.get('observations'))
    edited_dimensions = (EDIT_LENGTH_MM,) + EXPECTED_DIMENSIONS_MM[1:]
    stages = (
        ('created', EXPECTED_DIMENSIONS_MM),
        ('native_reopened', EXPECTED_DIMENSIONS_MM),
        ('native_edited', edited_dimensions),
        ('native_restored', EXPECTED_DIMENSIONS_MM),
    )
    volumes = {}
    for stage, dimensions in stages:
        observation = mapping(observations.get(stage))
        parameters = mapping(observation.get('parameters'))
        geometry = mapping(observation.get('geometry'))
        checks[stage + '_parametric_box_type'] = parameters.get('type_id') == 'Part::Box'
        checks[stage + '_parameters'] = close_vector(
            parameters.get('dimensions_mm'), dimensions)
        inspect_geometry(checks, stage, geometry, dimensions)
        volume = geometry.get('volume_mm3')
        volumes[stage] = volume if finite_number(volume) else None

    step_geometry = mapping(observations.get('step_reopened'))
    inspect_geometry(checks, 'step_reopened', step_geometry, EXPECTED_DIMENSIONS_MM)
    step_volume = step_geometry.get('volume_mm3')
    volumes['step_reopened'] = step_volume if finite_number(step_volume) else None
    original_geometry = mapping(mapping(observations.get('native_reopened')).get('geometry'))
    edited_geometry = mapping(mapping(observations.get('native_edited')).get('geometry'))
    original_volume = original_geometry.get('volume_mm3')
    edited_volume = edited_geometry.get('volume_mm3')
    checks['native_edit_changes_volume_by_expected_amount'] = (
        finite_number(original_volume) and finite_number(edited_volume)
        and close_number(edited_volume - original_volume,
                         math.prod(edited_dimensions) - math.prod(EXPECTED_DIMENSIONS_MM),
                         VOLUME_ABS_TOL_MM3))
    checks['input_evaluation_completed'] = True
    if not all(type(value) is bool for value in checks.values()):
        raise TypeError('In-scope check values must be booleans')
    failed = [name for name, value in checks.items() if value is False]
    explanation = (
        'Synthetic FreeCAD capability capture only. Current native and STEP files '
        'are checked against capture paths, sizes and SHA256 digests. Recorded '
        'reopened geometry, parametric editing and restoration are compared with '
        'analytical box expectations: length tolerance 1e-8 mm, volume tolerance '
        '1e-6 mm^3, relative tolerance 1e-9. Observed volumes in mm^3: '
        + json.dumps(volumes, sort_keys=True, allow_nan=False)
        + '. The outcome applies only to these synthetic artifact checks. '
        'This program does not rerun the geometry kernel or establish GUI '
        'availability. Vehicle fit, rotor clearance, mounting interfaces, strength, '
        'mass/CG/inertia and physical hardware validation are outside scope and '
        'remain unperformed by this probe. Failed in-scope checks: '
        + (', '.join(failed) if failed else 'none') + '.')
    return {'outcome': 'failed' if failed else 'passed',
            'explanation': explanation, 'checks': checks}


def main():
    checks = {}
    try:
        if len(sys.argv) > 2:
            raise ValueError('Usage: chief_r4_verify_capability_v2.py [sandbox_directory]')
        sandbox = (Path(sys.argv[1]) if len(sys.argv) == 2
                   else Path(__file__).resolve().parents[1]).resolve(strict=True)
        result = verify(sandbox, checks)
    except Exception as exc:
        print('Capability verification could not complete: '
              + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        checks['input_evaluation_completed'] = False
        result = {
            'outcome': 'inconclusive',
            'explanation': 'The synthetic capability artifacts could not be fully '
                           'evaluated; see stderr. No capability or vehicle acceptance '
                           'is established. Physical hardware validation remains '
                           'unperformed. Error type: ' + type(exc).__name__,
            'checks': checks,
        }
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
