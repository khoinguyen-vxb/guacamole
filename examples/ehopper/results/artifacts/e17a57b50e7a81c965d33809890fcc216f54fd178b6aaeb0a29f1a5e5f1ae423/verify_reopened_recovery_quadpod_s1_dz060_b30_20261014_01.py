"""Artifact-bound checks of the reopened recovery quadpod observations.

Publish this source, then run through verify_command:
 repository='6dof_hopper', workdir='.', timeout_s=120
 command=['python', 'cad/pdr_r12_chief/verify_reopened_recovery_quadpod_s1_dz060_b30_20261014_01.py']
Include this checker and all six dependency artifact Refs in tool inputs:
 retained tripod verifier, retained tripod probe, recovery probe adapter,
 recovery observations, recovery native FCStd and recovery STEP.

This program reads actual artifact bytes. It reuses the inspected numerical
helpers from the hash-pinned tripod verifier without calling that verifier's
candidate-specific main or entry point. It does not import a CAD generator,
execute either probe, run FreeCAD, modify inputs or write files.

All comparisons use retained numerical regression tolerances, not approved
physical margins. Tube-only mass uses assumed density. Positive sampled
reference-envelope separation is not continuous or loaded clearance.
Untrimmed tube intersections remain an explicitly failing screen, not accepted
joints. No vehicle selection or physical/review acceptance is established.
Only VerificationResult JSON goes to stdout; diagnostics go to stderr.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 'cad/pdr_r12_chief/'
CANDIDATE = 'G_INTERMEDIATE_D279_QUADPOD_S1_DZ060_B30'
NATIVE = BASE + 'fixed_structure_recovery_20261014_01/' + CANDIDATE + '.FCStd'
STEP = BASE + 'fixed_structure_recovery_20261014_01/' + CANDIDATE + '_tubes.step'
HELPERS = BASE + 'verify_reopened_braced03_tripod_s1_20261014_01.py'
TEMPLATE = BASE + 'reopen_braced03_tripod_s1_probe_20261014_01.py'
PROBE = BASE + 'reopen_recovery_quadpod_s1_dz060_b30_probe_20261014_01.py'
REPORT = BASE + 'reopen_recovery_quadpod_s1_dz060_b30_observations_20261014_01.json'
# These are file-byte hashes, distinct from runtime record hashes.
EXPECTED = {
    HELPERS: 'a1c7a73af47a43df2eeacdde3a699508f50ddb8ae43686a5a641db72a169d9d2',
    TEMPLATE: '64a732bfa4bdb1725fdcefc3788e91d98ffcf1fc8c0783e45358367a55ca2ccc',
    PROBE: 'b4b25f9cf8a0811d047e924b9ebcee0efe185e67561514f656e743cfeb0537f0',
    NATIVE: '5e6943237c8d740bdd42f6528ddb2751f9e537622961d6cda23c51a2f1eb80db',
    STEP: '0dc0b0cd74199184c01676ca5461f9860c345eddaa909cfb117156c9d2f6d8bf',
    REPORT: '718b347ca44f2a1db937b154c1bfb4ceabc3b8d544cf0d6e326d8111af92c4c6',
}
CHECKS = {}
EXCLUDED = [
    'Independent re-execution of FreeCAD or either observation probe',
    'Full native/STEP geometric equivalence or certified material assignments',
    'Complete installed vehicle mass, CG, inertia and articulated momentum',
    'Manufactured joints, physical ring/supports, mounting and retention interfaces',
    'Continuous, loaded, joint-package and ground clearance',
    'Structural, propulsion, electrical, thermal and flight validation',
    'Complete budget compliance and human PDR/CDR acceptance',
]


def check(name, condition, details=None):
    if name in CHECKS:
        raise ValueError('Duplicate check name: ' + name)
    CHECKS[name] = bool(condition)
    if details is not None or not condition:
        print(json.dumps({'check': name, 'satisfied': bool(condition),
                          'details': details}, allow_nan=False), file=sys.stderr)


def expected_poses():
    # Equivalent independent reconstruction of the configured four cone radii.
    samples = {(0.0, 0.0)}
    for theta_deg in (5.0, 7.5, 10.0, 15.0):
        theta = math.radians(theta_deg)
        for azimuth_deg in range(0, 360, 15):
            azimuth = math.radians(azimuth_deg)
            alpha = math.asin(math.sin(theta) * math.cos(azimuth))
            beta = math.atan2(math.sin(theta) * math.sin(azimuth), math.cos(theta))
            samples.add((round(math.degrees(alpha), 10),
                         round(math.degrees(beta), 10)))
    return [list(p) for p in sorted(samples)]


def check_adapter(report, identities, template_bytes):
    adapter = report['inspection_adapter']
    check('adapter/retained_probe_identity', adapter['retained_probe'] == identities[TEMPLATE])
    check('adapter/source_identity', adapter['adapter_source'] == identities[PROBE])
    check('adapter/work_plan', adapter['work_plan'] == '66c7448f443f44ac9a016a1b384593a2 r1')
    check('adapter/development_decision', adapter['development_decision'] == '43d5a1d12e424f9ca9f24ed2e7f1981d r1')
    check('adapter/sampling_contract', adapter['sampling'] == {
        'resultant_cones_deg': [10, 15], 'cone_fractions': [0.5, 1.0],
        'azimuth_step_deg': 15, 'neutral_included': True,
        'expected_pose_count': 97, 'continuous_domain_certified': False})
    replacements = [
        ('for i in range(1, 4):', 'for i in range(1, 5):'),
        ('if {o.Name for o in objects} != expected_names or len(objects) != 10:',
         'if {o.Name for o in objects} != expected_names or len(objects) != 13:'),
        ("'candidate_id': 'G_INTERMEDIATE_D279_TRIPOD_S1',",
         "'candidate_id': 'G_INTERMEDIATE_D279_QUADPOD_S1_DZ060_B30',"),
        ("'source': identity(SOURCE), 'inputs_before': before,",
         "'source': identity(SOURCE), 'inspection_adapter': ADAPTER_PROVENANCE, 'inputs_before': before,"),
        ("'scope': 'Native reference primitives versus actual native tubes at 25 poses. Primitive overlap volumes must not be summed as a unique compound volume.',",
         "'scope': 'Native reference primitives versus actual native tubes at %d finite poses. Primitive overlap volumes must not be summed as a unique compound volume.' % len(samples),"),
    ]
    recorded = [(r['old'], r['new']) for r in adapter['text_substitutions']]
    check('adapter/five_recorded_source_substitutions', recorded == replacements)
    revised = template_bytes.decode('utf-8')
    for index, (old, new) in enumerate(replacements, 1):
        matched = revised.count(old) == 1
        check('adapter/substitution_%d_unique' % index, matched)
        if not matched:
            raise ValueError('Cannot reconstruct retained inspection source transformation')
        revised = revised.replace(old, new, 1)
    observed_hash = hashlib.sha256(revised.encode('utf-8')).hexdigest()
    check('adapter/transformed_template_identity',
          observed_hash == adapter['executed_template_sha256'],
          {'reconstructed_sha256': observed_hash,
           'scope': 'Source transformation consistency only; no probe execution'})


def main():
    blobs, identities = {}, {}
    for path, expected in EXPECTED.items():
        raw = (ROOT / path).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        blobs[path] = raw
        identities[path] = {'path': path, 'sha256': actual}
        check('identity/' + path, actual == expected)
    if not all(CHECKS.values()):
        raise ValueError('Artifact identity mismatch; evaluation stopped before loading helpers')

    # The inspected helper source is evaluated under a non-entry-point name.
    # Its old candidate-specific main is deliberately never called.
    h = {'__name__': 'retained_reopened_cad_numerical_helpers',
         '__file__': str(ROOT / HELPERS)}
    exec(compile(blobs[HELPERS].decode('utf-8'), str(ROOT / HELPERS), 'exec'), h)
    h['CHECKS'] = CHECKS
    compare, close = h['compare'], h['close']
    number, vector, matrix = h['number'], h['vector'], h['matrix']
    tol = h['TOL']
    print(json.dumps({'retained_numerical_tolerances': tol,
                      'helper_identity': identities[HELPERS]}, allow_nan=False), file=sys.stderr)

    def reject_constant(value):
        raise ValueError('Nonfinite JSON constant: ' + value)

    report = json.loads(blobs[REPORT].decode('utf-8'), parse_constant=reject_constant)
    check('report/schema', report['schema'] == 'hopper_independent_reopened_cad_observations/1')
    check('report/candidate', report['candidate_id'] == CANDIDATE)
    check('report/units', report['units'] == {
        'length': 'mm', 'volume': 'mm^3', 'mass': 'kg',
        'geometric_inertia': 'mm^5', 'mass_inertia': 'kg m^2', 'angle': 'deg'})
    expected_inputs = [identities[NATIVE], identities[STEP]]
    check('provenance/before_inputs', report['inputs_before'] == expected_inputs)
    check('provenance/after_inputs', report['inputs_after'] == expected_inputs)
    check('provenance/probe', report['source'] == identities[PROBE])
    check('provenance/reported_preservation', report['input_bytes_unchanged'] is True)
    check_adapter(report, identities, blobs[TEMPLATE])

    frame = report['frame']
    check('frame/CAD_to_FRD_rotation', frame['R_BC'] == [[1,0,0],[0,-1,0],[0,0,-1]])
    check('frame/CAD_rotation', frame['CAD_rotation'] == 'Rx(alpha)Ry(-beta)')
    check('frame/complete_CG_not_substituted', frame['complete_vehicle_neutral_CG'] is None)
    origins = report['observed_neutral_joint_origins']
    compare('geometry/outer_origin_hypothesis_mm', vector(origins['outer_CAD_mm']), [0,0,340], tol['centroid_mm'])
    compare('geometry/carried_origin_offset_hypothesis_mm', vector(origins['outer_to_inner_local_mm']), [0,0,-20], tol['centroid_mm'])
    for rotor, center in [('upper_rotor', [0,0,230]), ('lower_rotor', [0,0,110])]:
        compare('geometry/' + rotor + '_neutral_center_mm',
                vector(report['neutral_rotor_centers_CAD_mm'][rotor]), center, tol['centroid_mm'])
    rho = number(report['density_assumption_kg_m3'])
    compare('mass/retained_density_assumption_kg_m3', rho, 1600, 0)
    h['analytic_box_fixture'](report)

    names = {'Spine_01'}
    for i in range(1, 5):
        names.add('MainLeg_%02d' % i)
        names.update('Brace_%02d_%s' % (i, side) for side in ('Plus', 'Minus'))
    inventory = report['native_component_inventory']
    check('inventory/thirteen_expected_native_components',
          len(inventory) == 13 and {r['name'] for r in inventory} == names)
    check('inventory/reported_one_valid_solid_per_component',
          all(r['shape_valid'] is True and r['solid_count'] == 1 for r in inventory))
    native, step = report['native_solids'], report['step_solids']
    check('inventory/thirteen_native_and_STEP_solids', len(native) == len(step) == 13)
    check('inventory/native_labels', {r['label'] for r in native} == {n + '/solid_1' for n in names})
    check('inventory/reported_STEP_shape_validity', report['step_shape_valid'] is True)
    native_sum = h['aggregate'](native, rho, 'native')
    step_sum = h['aggregate'](step, rho, 'STEP')
    h['compare_aggregate']('native_sum', native_sum, report['native_nominal_tube_sum'])
    h['compare_aggregate']('STEP_sum', step_sum, report['step_uniform_density_comparison_sum'])
    compare('comparison/component_sum_mass_kg', step_sum[0], native_sum[0], tol['mass_kg'], tol['relative'])
    compare('comparison/component_sum_centroid_mm', step_sum[1], native_sum[1], tol['centroid_mm'])
    compare('comparison/component_sum_tensor_kg_m2', step_sum[2], native_sum[2], tol['inertia_kg_m2'])
    unused, matches = set(range(len(step))), []
    for row in native:
        candidates = [j for j in unused
                      if close(vector(step[j]['cg_CAD_mm']), vector(row['cg_CAD_mm']), tol['centroid_mm'])
                      and close(step[j]['volume_mm3'], row['volume_mm3'], tol['volume_mm3'], tol['relative'])
                      and close(matrix(step[j]['I_about_CG_CAD_kg_m2']),
                                matrix(row['I_about_CG_CAD_kg_m2']), tol['inertia_kg_m2'])]
        if len(candidates) != 1:
            break
        j = candidates[0]
        unused.remove(j)
        matches.append({'native_label': row['label'], 'STEP_observation_index': j})
    check('comparison/unique_observation_correspondence',
          len(matches) == len(native) == len(step) and not unused,
          {'matches': matches, 'scope': 'Volume/centroid/tensor agreement, not full geometric equivalence'})

    edit = report['unsaved_parameter_edit']
    check('edit/target_and_cell', edit['cell'] == 'Parameters.B1' and edit['target'] == 'MainLeg_01')
    before, after, length = number(edit['radius_before_mm']), number(edit['radius_after_mm']), number(edit['length_mm'])
    check('edit/positive_length', length > 0)
    compare('edit/radius_before_mm', before, 4, tol['centroid_mm'])
    compare('edit/radius_after_mm', after, 4.04, tol['centroid_mm'])
    compare('edit/radius_restored_mm', edit['radius_restored_mm'], before, tol['centroid_mm'])
    delta = math.pi * (after * after - before * before) * length
    compare('edit/observed_volume_delta_mm3',
            number(edit['volume_after_mm3']) - number(edit['volume_before_mm3']),
            delta, tol['volume_mm3'], tol['relative'])
    compare('edit/restored_volume_mm3', edit['volume_restored_mm3'], edit['volume_before_mm3'], tol['volume_mm3'])
    original_target = next(r for r in native if r['label'] == 'MainLeg_01/solid_1')
    compare('edit/baseline_matches_native_volume_mm3', edit['volume_before_mm3'],
            original_target['volume_mm3'], tol['volume_mm3'])
    check('edit/reported_unsaved', edit['source_document_saved'] is False)

    samples = report['sampled_clearance']
    expected = expected_poses()
    poses = samples['joint_poses_alpha_beta_deg']
    dimensions_ok = len(poses) == len(expected) == 97 and all(isinstance(p, list) and len(p) == 2 for p in poses)
    check('sampling/97_two_angle_poses', dimensions_ok)
    if not dimensions_ok:
        raise ValueError('Unexpected sampled pose dimensions')
    compare('sampling/configured_pose_list_deg', poses, expected, tol['angle_deg'])
    kinematics = samples['kinematics_observations']
    compare('sampling/kinematic_pose_list_deg',
            [[r['alpha_deg'], r['beta_deg']] for r in kinematics], expected, tol['angle_deg'])
    residuals = [number(r['maximum_center_transform_difference_mm']) for r in kinematics]
    check('sampling/reported_centroid_transform_residuals',
          len(residuals) == 97 and all(0 <= x <= tol['kinematic_residual_mm'] for x in residuals),
          {'maximum_mm': max(residuals) if residuals else None,
           'numerical_tolerance_mm': tol['kinematic_residual_mm']})
    moving_names = {'upper_rotor', 'lower_rotor'}
    moving_names.update('YokeEnvelope_%02d' % i for i in range(1, 5))
    moving_names.update('YokeEndEnvelope_%02d' % i for i in range(1, 5))

    def sampled_pose(row):
        return any(close([row['alpha_deg'], row['beta_deg']], p, tol['angle_deg']) for p in poses)

    witnesses = samples['positive_common_volume_witnesses']
    check('sampling/overlap_witness_integrity', all(
        r['fixed'] in names and r['moving'] in moving_names
        and number(r['common_volume_mm3']) > 1e-7
        and 0 <= number(r['distance_mm']) <= 1e-7 and sampled_pose(r)
        for r in witnesses))
    minima = samples['minima_to_physical_tubes']
    check('sampling/minimum_categories', set(minima) == {'upper_rotor', 'lower_rotor', 'yoke_primitive_envelopes'})
    for category, row in minima.items():
        correct_moving = (row['moving'] == category if category in ('upper_rotor', 'lower_rotor')
                          else row['moving'] in moving_names and row['moving'].startswith('Yoke'))
        check('sampling/' + category + '_minimum_record_integrity',
              row['fixed'] in names and correct_moving and sampled_pose(row)
              and number(row['distance_mm']) >= 0)
    for rotor in ('upper_rotor', 'lower_rotor'):
        row = minima[rotor]
        check('screen/' + rotor + '_reported_sampled_positive_separation',
              number(row['distance_mm']) > 1e-7 and not any(r['moving'] == rotor for r in witnesses),
              {'reported_minimum_mm': row['distance_mm'],
               'scope': 'Finite sampled reference-envelope observations only'})
    yoke_hits = [r for r in witnesses if r['moving'].startswith('Yoke')]
    check('screen/yoke_reported_sampled_positive_separation',
          number(minima['yoke_primitive_envelopes']['distance_mm']) > 1e-7 and not yoke_hits,
          {'reported_minimum_mm': minima['yoke_primitive_envelopes']['distance_mm'],
           'overlap_witness_count': len(yoke_hits),
           'scope': 'Assumed envelope, not installed hardware or continuous clearance'})
    tube_hits = report['tube_intersections']
    check('sampling/tube_intersection_record_integrity', all(
        r['a'] in names and r['b'] in names and r['a'] != r['b']
        and number(r['common_volume_mm3']) > 1e-7 for r in tube_hits))
    pairs = [tuple(sorted((r['a'], r['b']))) for r in tube_hits]
    check('sampling/tube_intersection_pairs_unique', len(pairs) == len(set(pairs)))
    check('screen/nominal_untrimmed_tube_solids_noninterpenetrating', not tube_hits,
          {'reported_pair_count': len(tube_hits),
           'scope': 'Unfinished nominal joints; pair volumes are not summed or waived'})

    for field in ('continuous_clearance', 'loaded_clearance', 'joint_envelope_clearance', 'ground_clearance'):
        check('scope/' + field + '_unperformed_preserved', samples[field] is None)
    check('scope/numerical_reporting_thresholds', report['numeric_reporting_thresholds'] == {
        'leaf_placement_comparison_mm': 1e-8, 'contact_distance_mm': 1e-7,
        'reported_overlap_mm3': 1e-7, 'physical_acceptance_threshold': None})
    expected_unperformed = {
        'complete_vehicle_mass_CG_inertia', 'manufactured_joints', 'mounting_interfaces',
        'continuous_loaded_clearance', 'structural_qualification',
        'physical_validation', 'PDR_CDR_acceptance'}
    unperformed = report['unperformed_acceptance']
    check('scope/unperformed_acceptance_preserved',
          set(unperformed) == expected_unperformed and all(v is None for v in unperformed.values()))
    for path in EXPECTED:
        check('preservation/' + path,
              hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == identities[path]['sha256'])
    check('evaluation/completed', True)


if __name__ == '__main__':
    print(json.dumps({'scope': 'Recovery quadpod hash-bound observation consistency and interference screens',
                      'unperformed_scopes': EXCLUDED}), file=sys.stderr)
    try:
        main()
    except Exception as exc:
        check('evaluation/exception_free', False,
              {'type': type(exc).__name__, 'message': str(exc)})
    failed = [name for name, value in CHECKS.items() if not value]
    outcome = 'failed' if failed or not CHECKS else 'passed'
    explanation = (
        'Scoped checks of hash-bound reopened recovery quadpod observations, source provenance and numerical arithmetic. '
        + ('Unsatisfied checks: ' + ', '.join(failed) + '. ' if failed else 'All performed checks satisfied. ')
        + 'Numerical helpers are reused from the retained hash-pinned verifier; neither FreeCAD nor the probes are rerun. '
        'Reported envelope distances cover finite samples only. Tube intersections concern untrimmed nominal members, '
        'not accepted joints. Mass and inertia are separate-tube sums at assumed density, not complete vehicle properties. '
        'Full geometric equivalence, physical ring/support and mounting integration, continuous/loaded/ground clearance, '
        'structural and hardware validation, complete budget and review acceptance are unperformed and excluded from acceptance checks.'
    )
    print(json.dumps({'outcome': outcome, 'explanation': explanation, 'checks': CHECKS}, allow_nan=False))
