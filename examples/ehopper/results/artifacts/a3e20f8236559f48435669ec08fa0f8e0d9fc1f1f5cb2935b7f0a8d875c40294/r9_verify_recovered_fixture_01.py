"""Artifact-bound analytical verification of the recovered BOX FIXTURE ONLY.

Run with verify_command, using Python and this saved script. Include the current
artifact Refs for this checker, FCStd, STEP and measurement JSON in tool inputs.
Uses only the Python standard library; creates/modifies no files.
Stdout: exactly one VerificationResult JSON object. Diagnostics: stderr.

Authorization: decision 98d7c43a499d4584a77132cd5ac96874 r1.
Measurement execution: efc4d368c50148a1956a668335b9dab3.
Reviewed measurement reader: 73865ae816f64f079d472423fcc92850.
Content digests below are ProducedFile digests, NOT artifact-record Ref hashes.

This checks analytical consistency of actual hash-bound FreeCAD readbacks.
It does not rerun FreeCAD or claim independent CAD-kernel validation, GUI-addon
availability, vehicle geometry acceptance, material validation or flight safety.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    'native': 'cad/pdr_r9_chief/r9_recovered_fixture_01.FCStd',
    'step': 'cad/pdr_r9_chief/r9_recovered_fixture_01.step',
    'measurements': 'cad/pdr_r9_chief/r9_recovered_fixture_01_measurements.json',
}
DIGESTS = {
    'native': 'ca4d55acb1b40ae8fc33cba740ee34374d3a4d300b9ff7f4b0c064868b5a90d9',
    'step': '0a3dc72fb44cd901427a4ad9186287991bd592d7aaf19d4104d0775486635bf4',
    'measurements': '9d7a716061aff386f61188d492bd4cdb7317c3e42e285d868d16402c330d2524',
}
RECOVERY_PROGRAM = {
    'path': 'cad/pdr_r9_chief/r9_fixture_recovery_01.py',
    'sha256': '43157a8f20996bf9f5c59b1f1cc0f4637902c45c862d20043f2b6da2d099042b',
}
# Independent design expectations from the reviewed numerical fixture definition.
# Never derive expected dimensions, density or translation from measured values.
DIMS_MM = [10.0, 20.0, 30.0]
BASE_MM = [11.0, 17.0, 23.0]
DENSITY_KG_M3 = 2700.0  # Numerical fixture assumption, not a material selection.
REL_TOL = 1e-9
ABS_TOL = {
    'length_mm': 1e-6,
    'volume_mm3': 1e-5,
    'geometric_inertia_mm5': 1e-5,
    'mass_kg': 1e-12,
    'inertia_kg_m2': 1e-16,
    'dimensionless': 1e-12,
}
CHECKS = {}
DIAGNOSTICS = {}


def check(name, condition):
    if name in CHECKS:
        raise ValueError('Duplicate check name: ' + name)
    CHECKS[name] = bool(condition)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def compare(name, actual, expected, absolute):
    errors = []

    def visit(a, e):
        if isinstance(e, list):
            if not isinstance(a, list) or len(a) != len(e):
                return False
            results = [visit(av, ev) for av, ev in zip(a, e)]
            return all(results)
        if not numeric(a):
            return False
        error = abs(float(a) - float(e))
        errors.append(error)
        return math.isclose(a, e, rel_tol=REL_TOL, abs_tol=absolute)

    valid = visit(actual, expected)
    check(name, valid)
    DIAGNOSTICS[name] = {
        'maximum_absolute_error': max(errors) if errors else None,
        'absolute_tolerance': absolute,
        'relative_tolerance': REL_TOL,
    }


def expected_box(dimensions_mm):
    a, b, c = dimensions_mm
    volume_mm3 = a * b * c
    geometric_diagonal = [
        volume_mm3 * (b*b + c*c) / 12.0,
        volume_mm3 * (a*a + c*c) / 12.0,
        volume_mm3 * (a*a + b*b) / 12.0,
    ]
    # Independently compute SI inertia from SI dimensions and mass, rather than
    # scaling the geometric tensor with the same expression as the CAD reader.
    am, bm, cm = [v / 1000.0 for v in dimensions_mm]
    mass_kg = DENSITY_KG_M3 * am * bm * cm
    si_diagonal = [
        mass_kg * (bm*bm + cm*cm) / 12.0,
        mass_kg * (am*am + cm*cm) / 12.0,
        mass_kg * (am*am + bm*bm) / 12.0,
    ]
    return {
        'volume_mm3': volume_mm3,
        'bbox_min_mm': list(BASE_MM),
        'bbox_max_mm': [p+d for p, d in zip(BASE_MM, dimensions_mm)],
        'bbox_size_mm': list(dimensions_mm),
        'cg_mm': [p+d/2.0 for p, d in zip(BASE_MM, dimensions_mm)],
        'geometric_inertia_about_solid_cg_mm5': [
            [geometric_diagonal[i] if i == j else 0.0 for j in range(3)]
            for i in range(3)
        ],
        'mass_kg': mass_kg,
        'inertia_about_solid_cg_kg_m2': [
            [si_diagonal[i] if i == j else 0.0 for j in range(3)]
            for i in range(3)
        ],
    }


def check_geometry(prefix, observed, dimensions_mm):
    if not isinstance(observed, dict):
        check(prefix + '.measurement_present', False)
        return
    check(prefix + '.single_solid',
          type(observed.get('solid_count')) is int and observed['solid_count'] == 1)
    check(prefix + '.measured_solid_type', observed.get('measured_shape_type') == 'Solid')
    # These are actual kernel observations from the hash-bound measurement run,
    # not an inherited VerificationResult or a process-exit acceptance flag.
    check(prefix + '.kernel_reported_validity',
          observed.get('input_shape_valid') is True and observed.get('solid_valid') is True)
    compare(prefix + '.density_assumption', observed.get('assumed_density_kg_m3'),
            DENSITY_KG_M3, 1e-9)
    expected = expected_box(dimensions_mm)
    for field in ('bbox_min_mm', 'bbox_max_mm', 'bbox_size_mm', 'cg_mm'):
        compare(prefix + '.' + field, observed.get(field), expected[field], ABS_TOL['length_mm'])
    for field, unit_key in (
        ('volume_mm3', 'volume_mm3'),
        ('geometric_inertia_about_solid_cg_mm5', 'geometric_inertia_mm5'),
        ('mass_kg', 'mass_kg'),
        ('inertia_about_solid_cg_kg_m2', 'inertia_kg_m2'),
    ):
        compare(prefix + '.' + field, observed.get(field), expected[field], ABS_TOL[unit_key])


def reject_constant(value):
    raise ValueError('Non-finite JSON constant: ' + value)


def verify():
    paths = {}
    actual_digests = {}
    for key, relative in FILES.items():
        path = ROOT / relative
        path.resolve().relative_to(ROOT)
        regular = path.is_file() and not path.is_symlink()
        check('inputs.' + key + '.regular_file', regular)
        if not regular:
            raise FileNotFoundError('Required fixture input unavailable: ' + relative)
        paths[key] = path
        actual_digests[key] = digest(path)
        check('inputs.' + key + '.published_content_digest', actual_digests[key] == DIGESTS[key])
    DIAGNOSTICS['actual_input_sha256'] = actual_digests
    if any(actual_digests[k] != DIGESTS[k] for k in FILES):
        return  # Do not trust or interpret altered measurement contents.

    with paths['measurements'].open(encoding='utf-8') as stream:
        report = json.load(stream, parse_constant=reject_constant)
    check('report.schema', report.get('schema') == 'r9_recovered_fixture_measurements_v1')
    check('report.fixture_only', report.get('vehicle_baseline') is False)
    check('report.no_physical_acceptance_claim', report.get('physical_acceptance') == 'not_assessed')
    check('report.measurement_status',
          report.get('status') == 'measurements_only_independent_verification_pending')
    check('report.recorded_recovery_program', report.get('recovery_program') == RECOVERY_PROGRAM)
    check('report.recovered_paths',
          report.get('recovered_paths') == {k: FILES[k] for k in ('native', 'step')})
    expected_export_hashes = {k: DIGESTS[k] for k in ('native', 'step')}
    for field in ('recovered_sha256_before_readback', 'recovered_sha256_after_readback',
                  'source_sha256_before', 'source_sha256_after'):
        check('report.' + field + '.consistent', report.get(field) == expected_export_hashes)
    # Original r8 files are not inputs to this checker. Source-preservation fields
    # above are checked for consistency only, not remeasured source preservation.
    check('report.source_paths', report.get('source_paths') == {
        'native': 'cad/pdr_r8_cad/r8_solid_fixture_01.FCStd',
        'step': 'cad/pdr_r8_cad/r8_solid_fixture_01.step',
    })

    contract = report['fixture_contract']
    compare('contract.dimensions_mm', contract.get('dimensions_mm'), DIMS_MM, ABS_TOL['length_mm'])
    compare('contract.translation_mm', contract.get('translation_mm'), BASE_MM, ABS_TOL['length_mm'])
    compare('contract.rotation_xyzw', contract.get('rotation_quaternion_xyzw'),
            [0.0, 0.0, 0.0, 1.0], ABS_TOL['dimensionless'])
    compare('contract.density', contract.get('assumed_density_kg_m3'), DENSITY_KG_M3, 1e-9)
    check('contract.density_scope', contract.get('density_scope') == 'numerical units fixture only')
    check('report.units', report.get('units') == {
        'geometry_length': 'mm', 'geometry_volume': 'mm^3',
        'geometric_inertia': 'mm^5', 'density': 'kg/m^3',
        'mass': 'kg', 'density_weighted_inertia': 'kg m^2',
        'volume_to_m3': 1e-9, 'geometric_inertia_to_m5': 1e-15,
        'inertia_reference': 'individual solid center of mass, CAD axes',
    })

    native = report['native_reopened']
    check_geometry('native', native, DIMS_MM)
    check_geometry('step', report['step_reimported'], DIMS_MM)
    check('native.object_identity', native.get('object_type') == 'Part::Box'
          and native.get('object_name') == 'UnitsFixtureBox')
    check('native.one_geometry_object', type(native.get('geometry_object_count')) is int
          and native['geometry_object_count'] == 1)
    dimensions = native.get('editable_dimensions_mm', {})
    for name, expected in zip(('Length', 'Width', 'Height'), DIMS_MM):
        compare('native.parameter.' + name, dimensions.get(name), expected, ABS_TOL['length_mm'])
    compare('native.placement_base_mm', native.get('placement_base_mm'), BASE_MM, ABS_TOL['length_mm'])
    compare('native.placement_rotation_xyzw', native.get('placement_quaternion_xyzw'),
            [0.0, 0.0, 0.0, 1.0], ABS_TOL['dimensionless'])
    check_geometry('native.restored', native.get('restored_geometry'), DIMS_MM)

    probes = native.get('in_memory_edit_probes_not_saved')
    names = ('Length', 'Width', 'Height')
    complete = (isinstance(probes, list) and len(probes) == 3
                and all(isinstance(p, dict) for p in probes)
                and sorted(p.get('parameter', '') for p in probes) == sorted(names))
    check('native.edit_probes.complete_unique_set', complete)
    if complete:
        for probe in probes:
            name = probe['parameter']
            index = names.index(name)
            changed = list(DIMS_MM)
            changed[index] += 1.0
            prefix = 'native.edit.' + name
            compare(prefix + '.original_mm', probe.get('original_mm'),
                    DIMS_MM[index], ABS_TOL['length_mm'])
            for field in ('requested_mm', 'readback_mm'):
                compare(prefix + '.' + field, probe.get(field),
                        changed[index], ABS_TOL['length_mm'])
            check_geometry(prefix + '.geometry', probe.get('geometry'), changed)

    # Rehash the actual tested files to detect changes during verification.
    for key, path in paths.items():
        check('inputs.' + key + '.unchanged_during_verification',
              digest(path) == actual_digests[key])
    DIAGNOSTICS['independent_baseline_expectations'] = expected_box(DIMS_MM)
    DIAGNOSTICS['scope'] = 'Analytical box fixture and unit conversion only; not vehicle acceptance.'


def main():
    exception = None
    try:
        verify()
    except Exception as exc:
        exception = type(exc).__name__
        CHECKS['verification_completed'] = False
        # Do not dump environment variables, credentials or unrelated file data.
        print('Fixture verification incomplete: ' + exception, file=sys.stderr)
    else:
        CHECKS['verification_completed'] = True
    print(json.dumps(DIAGNOSTICS, sort_keys=True, allow_nan=False), file=sys.stderr)
    if exception is not None:
        outcome = 'inconclusive'
    else:
        outcome = 'passed' if all(CHECKS.values()) else 'failed'
    failed = [name for name, value in CHECKS.items() if not value]
    explanation = (
        'Scope: hash-bound recovered rectangular-prism fixture only. '
        'Analytical expectations independently test FreeCAD readback volume, bounding box, '
        'centroid, full centroidal inertia, density/unit conversions and three parameter edits '
        'with restoration. Absolute and relative errors are on stderr. '
        'The checker does not rerun FreeCAD; source-preservation records are checked for '
        'consistency, not remeasured. No GUI, vehicle, mounting, clearance, strength, '
        'material-property or flight acceptance is established. '
        + ('Incomplete due to ' + exception + '. ' if exception else '')
        + 'Failed or incomplete checks: ' + (', '.join(failed) if failed else 'none')
    )
    print(json.dumps({'outcome': outcome, 'explanation': explanation, 'checks': CHECKS},
                     sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
