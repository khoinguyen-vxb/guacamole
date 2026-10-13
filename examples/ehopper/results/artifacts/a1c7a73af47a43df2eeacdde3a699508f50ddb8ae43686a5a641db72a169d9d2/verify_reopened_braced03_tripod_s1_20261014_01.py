"""Hash-bound reopened-observation checks and nominal interference screens.

Run subsequently through verify_command, repository='6dof_hopper', workdir='.',
command=['python', 'cad/pdr_r12_chief/verify_reopened_braced03_tripod_s1_20261014_01.py'].
Include this checker, probe, measurements, native FCStd and STEP artifact Refs
in tool inputs. Publish this source before verification.

This standard-library program reads actual artifact bytes and independently
recomputes arithmetic from retained FreeCAD solid observations. It does NOT
rerun FreeCAD, independently prove probe correctness, establish full geometric
equivalence, or provide physical validation. The preceding FreeCAD probe is
the geometry-observation producer. No source or CAD artifact is modified.

All tolerances below are numerical regression tolerances, NOT human-approved
physical margins. Reference envelopes are not actual hardware. Intersecting
nominal tubes remain unfinished joint hypotheses. Unperformed acceptance
scopes are excluded from the boolean checks and explicitly reported.
Only a VerificationResult JSON object goes to stdout; diagnostics use stderr.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 'cad/pdr_r12_chief/'
NATIVE = BASE + 'braced_candidates_03/G_INTERMEDIATE_D279_TRIPOD_S1.FCStd'
STEP = BASE + 'braced_candidates_03/G_INTERMEDIATE_D279_TRIPOD_S1_tubes.step'
PROBE = BASE + 'reopen_braced03_tripod_s1_probe_20261014_01.py'
REPORT = BASE + 'reopen_braced03_tripod_s1_measurements_20261014_01.json'
EXPECTED = {
    NATIVE: '346ee2ffacfd6c75dc09a9fe23942b6bad059b8baf922a11f1b9f3746883f23a',
    STEP: '210f8ab1107b9551f464d1cbd164386eb7e8fc2b57cc490459460c9f615c87dd',
    PROBE: '64a732bfa4bdb1725fdcefc3788e91d98ffcf1fc8c0783e45358367a55ca2ccc',
    REPORT: '95af54d50b019d47c54bf7c2e8128c054dfc2faacd3ad841aea6ce2d71787c1c',
}
TOL = {
    'centroid_mm': 1e-6,
    'volume_mm3': 1e-5,
    'mass_kg': 1e-12,
    'inertia_kg_m2': 1e-10,
    'fixture_geometric_inertia_mm5': 1e-4,
    'kinematic_residual_mm': 1e-8,
    'angle_deg': 1e-9,
    'relative': 1e-9,
}
EXCLUDED = [
    'Independent re-execution of the FreeCAD probe by this checker',
    'Full native/STEP geometric equivalence or component material mapping',
    'Complete vehicle mass, CG, inertia and articulated momentum',
    'Manufactured joints, actual mounting interfaces and structural qualification',
    'Continuous, loaded, joint-package and ground clearance',
    'Actual hardware collisions inferred solely from reference-envelope overlap',
    'Physical testing, flight safety and PDR/CDR acceptance',
]
CHECKS = {}


def check(name, condition, details=None):
    if name in CHECKS:
        raise ValueError('Duplicate check name: ' + name)
    CHECKS[name] = bool(condition)
    if details is not None or not condition:
        print(json.dumps({'check': name, 'satisfied': bool(condition),
                          'details': details}, allow_nan=False), file=sys.stderr)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Expected numerical value')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Nonfinite numerical value')
    return value


def vector(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError('Expected three-vector')
    return [number(x) for x in value]


def matrix(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError('Expected 3x3 matrix')
    return [vector(row) for row in value]


def flatten(value):
    if isinstance(value, list):
        return [x for item in value for x in flatten(item)]
    return [number(value)]


def close(a, b, atol, rtol=0.0):
    aa, bb = flatten(a), flatten(b)
    return len(aa) == len(bb) and all(
        abs(x-y) <= atol + rtol*abs(y) for x, y in zip(aa, bb))


def compare(name, a, b, atol, rtol=0.0):
    aa, bb = flatten(a), flatten(b)
    error = max((abs(x-y) for x, y in zip(aa, bb)), default=0.0)
    check(name, close(a, b, atol, rtol), {
        'maximum_absolute_error': error, 'absolute_tolerance': atol,
        'relative_tolerance': rtol, 'numerical_regression_only': True})


def aggregate(rows, rho, prefix):
    parts = []
    for index, row in enumerate(rows, 1):
        label = prefix + '/solid_%02d' % index
        volume = number(row['volume_mm3'])
        if volume <= 0:
            raise ValueError('Nonpositive solid volume')
        cg = vector(row['cg_CAD_mm'])
        geometric = matrix(row['geometric_inertia_reported_mm5'])
        mass = volume*rho*1e-9
        inertia = [[x*rho*1e-15 for x in line] for line in geometric]
        check(label + '/reported_validity', row['valid'] is True)
        compare(label + '/density_conversion_kg', row['mass_at_assumed_density_kg'],
                mass, TOL['mass_kg'], TOL['relative'])
        compare(label + '/inertia_conversion_kg_m2',
                matrix(row['I_about_CG_CAD_kg_m2']), inertia,
                TOL['inertia_kg_m2'], TOL['relative'])
        compare(label + '/tensor_symmetry', inertia,
                [[inertia[j][i] for j in range(3)] for i in range(3)],
                TOL['inertia_kg_m2'])
        parts.append((mass, cg, inertia))
    if not parts:
        raise ValueError('Empty solid observations')
    mass = sum(p[0] for p in parts)
    cg = [sum(m*c[i] for m, c, _ in parts)/mass for i in range(3)]
    inertia = [[0.0]*3 for _ in range(3)]
    for m, c, tensor in parts:
        d = [(c[i]-cg[i])*1e-3 for i in range(3)]
        d2 = sum(x*x for x in d)
        for i in range(3):
            for j in range(3):
                inertia[i][j] += tensor[i][j] + m*((d2 if i == j else 0)-d[i]*d[j])
    return mass, cg, inertia


def compare_aggregate(prefix, calculated, recorded):
    m, cg, inertia = calculated
    compare(prefix + '/mass_kg', recorded['member_sum_mass_kg'], m,
            TOL['mass_kg'], TOL['relative'])
    compare(prefix + '/centroid_mm', vector(recorded['partial_CG_CAD_mm']), cg,
            TOL['centroid_mm'])
    compare(prefix + '/tensor_kg_m2', matrix(recorded['I_about_partial_CG_CAD_kg_m2']),
            inertia, TOL['inertia_kg_m2'], TOL['relative'])


def analytic_box_fixture(report):
    rows = report['box_inertia_fixture']['observed']
    check('fixture/one_box_solid', len(rows) == 1)
    if len(rows) != 1:
        raise ValueError('Unexpected fixture inventory')
    row = rows[0]
    u = [x/math.sqrt(14.0) for x in (1.0, 2.0, 3.0)]
    c, s = math.cos(math.radians(31)), math.sin(math.radians(31))
    skew = [[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]]
    rotation = [[c*(1 if i == j else 0)+(1-c)*u[i]*u[j]+s*skew[i][j]
                 for j in range(3)] for i in range(3)]
    center = [t+sum(rotation[i][j]*[5,10,15][j] for j in range(3))
              for i, t in enumerate([12, -7, 19])]
    diagonal = [6000*(20**2+30**2)/12,
                6000*(10**2+30**2)/12,
                6000*(10**2+20**2)/12]
    tensor = [[sum(rotation[i][k]*diagonal[k]*rotation[j][k] for k in range(3))
               for j in range(3)] for i in range(3)]
    compare('fixture/volume_mm3', row['volume_mm3'], 6000, TOL['volume_mm3'])
    compare('fixture/centroid_mm', vector(row['cg_CAD_mm']), center, TOL['centroid_mm'])
    compare('fixture/rotated_CG_tensor_mm5',
            matrix(row['geometric_inertia_reported_mm5']), tensor,
            TOL['fixture_geometric_inertia_mm5'], TOL['relative'])
    check('fixture/reported_validity', row['valid'] is True)


def main():
    identities = {}
    for path, expected in EXPECTED.items():
        actual = hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        identities[path] = {'path': path, 'sha256': actual}
        check('identity/' + path, actual == expected)
    if not all(CHECKS.values()):
        raise ValueError('Artifact identity mismatch; observation evaluation stopped')
    report = json.loads((ROOT/REPORT).read_text(encoding='utf-8'),
                        parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    check('report/schema', report['schema'] == 'hopper_independent_reopened_cad_observations/1')
    check('report/candidate', report['candidate_id'] == 'G_INTERMEDIATE_D279_TRIPOD_S1')
    check('report/units', report['units'] == {
        'length':'mm','volume':'mm^3','mass':'kg','geometric_inertia':'mm^5',
        'mass_inertia':'kg m^2','angle':'deg'})
    expected_inputs = [identities[NATIVE], identities[STEP]]
    check('provenance/before_inputs', report['inputs_before'] == expected_inputs)
    check('provenance/after_inputs', report['inputs_after'] == expected_inputs)
    check('provenance/probe', report['source'] == identities[PROBE])
    check('provenance/reported_preservation', report['input_bytes_unchanged'] is True)
    check('frame/CAD_to_FRD_rotation', report['frame']['R_BC'] == [[1,0,0],[0,-1,0],[0,0,-1]])
    check('frame/complete_CG_not_substituted', report['frame']['complete_vehicle_neutral_CG'] is None)
    rho = number(report['density_assumption_kg_m3'])
    compare('mass/retained_density_assumption_kg_m3', rho, 1600, 0)
    analytic_box_fixture(report)
    names = {'Spine_01'}
    for i in range(1, 4):
        names.add('MainLeg_%02d' % i)
        names.update('Brace_%02d_%s' % (i, side) for side in ('Plus','Minus'))
    inventory = report['native_component_inventory']
    check('inventory/ten_expected_native_components',
          len(inventory) == 10 and {r['name'] for r in inventory} == names)
    check('inventory/reported_one_valid_solid_per_component',
          all(r['shape_valid'] is True and r['solid_count'] == 1 for r in inventory))
    native, step = report['native_solids'], report['step_solids']
    check('inventory/ten_native_and_step_solids', len(native) == len(step) == 10)
    check('inventory/native_labels',
          {r['label'] for r in native} == {n+'/solid_1' for n in names})
    check('inventory/reported_STEP_shape_validity', report['step_shape_valid'] is True)
    native_sum = aggregate(native, rho, 'native')
    step_sum = aggregate(step, rho, 'STEP')
    compare_aggregate('native_sum', native_sum, report['native_nominal_tube_sum'])
    compare_aggregate('STEP_sum', step_sum, report['step_uniform_density_comparison_sum'])
    compare('comparison/component_sum_mass_kg', step_sum[0], native_sum[0], TOL['mass_kg'], TOL['relative'])
    compare('comparison/component_sum_centroid_mm', step_sum[1], native_sum[1], TOL['centroid_mm'])
    compare('comparison/component_sum_tensor_kg_m2', step_sum[2], native_sum[2], TOL['inertia_kg_m2'])
    # Unique tolerance-based correspondence; never assume STEP solid order.
    unused = set(range(len(step)))
    matches = []
    for row in native:
        candidates = [j for j in unused
                      if close(vector(step[j]['cg_CAD_mm']), vector(row['cg_CAD_mm']), TOL['centroid_mm'])
                      and close(step[j]['volume_mm3'], row['volume_mm3'], TOL['volume_mm3'], TOL['relative'])
                      and close(matrix(step[j]['I_about_CG_CAD_kg_m2']),
                                matrix(row['I_about_CG_CAD_kg_m2']), TOL['inertia_kg_m2'])]
        if len(candidates) != 1:
            break
        j = candidates[0]
        unused.remove(j)
        matches.append({'native_label':row['label'],'STEP_observation_index':j})
    check('comparison/unique_observation_correspondence',
          len(matches) == len(native) == len(step) and not unused,
          {'matches':matches,'scope':'Volume/centroid/tensor agreement, not complete geometry equivalence'})
    edit = report['unsaved_parameter_edit']
    check('edit/target_and_cell', edit['cell'] == 'Parameters.B1' and edit['target'] == 'MainLeg_01')
    before, after = number(edit['radius_before_mm']), number(edit['radius_after_mm'])
    length = number(edit['length_mm'])
    compare('edit/radius_before_mm', before, 4, TOL['centroid_mm'])
    compare('edit/radius_after_mm', after, 4.04, TOL['centroid_mm'])
    compare('edit/radius_restored_mm', edit['radius_restored_mm'], before, TOL['centroid_mm'])
    delta = math.pi*(after*after-before*before)*length
    compare('edit/observed_volume_delta_mm3',
            number(edit['volume_after_mm3'])-number(edit['volume_before_mm3']),
            delta, TOL['volume_mm3'], TOL['relative'])
    compare('edit/restored_volume_mm3', edit['volume_restored_mm3'], edit['volume_before_mm3'], TOL['volume_mm3'])
    check('edit/reported_unsaved', edit['source_document_saved'] is False)
    samples = report['sampled_clearance']
    expected_poses = [[0.0,0.0]]
    theta = math.radians(15)
    for azimuth in range(0,360,15):
        az = math.radians(azimuth)
        expected_poses.append([
            math.degrees(math.asin(math.sin(theta)*math.cos(az))),
            math.degrees(math.atan2(math.sin(theta)*math.sin(az),math.cos(theta)))])
    poses = samples['joint_poses_alpha_beta_deg']
    check('sampling/pose_dimensions', len(poses) == 25 and all(len(p) == 2 for p in poses))
    compare('sampling/exploratory_pose_list_deg', poses, expected_poses, TOL['angle_deg'])
    kinematics = samples['kinematics_observations']
    compare('sampling/kinematic_pose_list_deg',
            [[r['alpha_deg'],r['beta_deg']] for r in kinematics], expected_poses, TOL['angle_deg'])
    residuals = [number(r['maximum_center_transform_difference_mm']) for r in kinematics]
    check('sampling/reported_centroid_transform_residuals',
          len(residuals) == 25 and all(0 <= x <= TOL['kinematic_residual_mm'] for x in residuals),
          {'maximum_mm':max(residuals),'tolerance_mm':TOL['kinematic_residual_mm']})
    witnesses = samples['positive_common_volume_witnesses']
    moving_names = {'upper_rotor','lower_rotor'}
    moving_names.update('YokeEnvelope_%02d' % i for i in range(1,5))
    moving_names.update('YokeEndEnvelope_%02d' % i for i in range(1,5))
    check('sampling/overlap_witness_integrity', all(
        r['fixed'] in names and r['moving'] in moving_names
        and number(r['common_volume_mm3']) > 1e-7
        and 0 <= number(r['distance_mm']) <= 1e-7
        and any(close([r['alpha_deg'],r['beta_deg']],p,TOL['angle_deg']) for p in poses)
        for r in witnesses))
    yoke_hits = [r for r in witnesses if r['moving'].startswith('Yoke')]
    check('screen/assumed_yoke_envelope_noninterference_at_observed_poses', not yoke_hits,
          {'witness_count':len(yoke_hits), 'first_witness':yoke_hits[0] if yoke_hits else None,
           'scope':'Reference-envelope interference screen; not an actual hardware collision claim'})
    tube_hits = report['tube_intersections']
    check('sampling/tube_intersection_record_integrity', all(
        r['a'] in names and r['b'] in names and r['a'] != r['b']
        and number(r['common_volume_mm3']) > 1e-7 for r in tube_hits))
    check('screen/nominal_untrimmed_tube_solids_noninterpenetrating', not tube_hits,
          {'pair_count':len(tube_hits),'scope':'Unfinished nominal joints; pair volumes are not summed'})
    for rotor in ('upper_rotor','lower_rotor'):
        row = samples['minima_to_physical_tubes'][rotor]
        check('screen/' + rotor + '_reported_sampled_positive_separation',
              number(row['distance_mm']) > 1e-7
              and not any(r['moving'] == rotor for r in witnesses),
              {'reported_minimum_mm':row['distance_mm'],
               'scope':'Reported sampled separation only; no continuous or physical margin acceptance'})
    for field in ('continuous_clearance','loaded_clearance','joint_envelope_clearance','ground_clearance'):
        check('scope/' + field + '_unperformed_preserved', samples[field] is None)
    check('scope/physical_acceptance_threshold_unset',
          report['numeric_reporting_thresholds']['physical_acceptance_threshold'] is None)
    check('evaluation/completed', True)


if __name__ == '__main__':
    print(json.dumps({'scope':'Hash-bound observation consistency and nominal interference screening',
                      'numerical_tolerances':TOL,'unperformed_scopes':EXCLUDED}), file=sys.stderr)
    try:
        main()
    except Exception as exc:
        check('evaluation/exception_free', False, {'type':type(exc).__name__,'message':str(exc)})
    failed = [name for name, value in CHECKS.items() if not value]
    outcome = 'failed' if failed or not CHECKS else 'passed'
    explanation = (
        'Scoped checks of hash-bound reopened CAD observations and numerical arithmetic; '
        + ('unsatisfied checks: ' + ', '.join(failed) + '. ' if failed else 'All performed checks satisfied. ')
        + 'Yoke-envelope overlaps concern assumed reference geometry; tube overlaps concern untrimmed nominal members. '
        'Neither establishes manufactured hardware collisions or acceptable joints. '
        'Mass is a separate-tube component sum at assumed density, not complete or as-built vehicle mass. '
        'This checker does not rerun FreeCAD. Continuous/loaded/ground clearance, mounting interfaces, '
        'structural qualification, physical testing and review acceptance are unperformed and excluded from checks.'
    )
    print(json.dumps({'outcome':outcome,'explanation':explanation,'checks':CHECKS}, allow_nan=False))
