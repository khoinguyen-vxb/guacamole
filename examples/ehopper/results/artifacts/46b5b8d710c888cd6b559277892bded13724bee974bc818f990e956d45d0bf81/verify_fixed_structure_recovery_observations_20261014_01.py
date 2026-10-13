"""Independent arithmetic checks of retained PDR-r12 recovery observations.

Publish this editable source, then run through verify_command with:
 repository='6dof_hopper', workdir='.', timeout_s=120
 command=['python', 'cad/pdr_r12_chief/verify_fixed_structure_recovery_observations_20261014_01.py']
Include this checker, the recovery configuration and recovery observations
artifact Refs in tool inputs. These are the only files this program reads.

No CAD binary is opened, hashed or independently geometrically verified here.
The FreeCAD producer supplies solid observations; this checker independently
reconstructs nominal tube endpoints, annular-cylinder mass properties and
assembly arithmetic from the configuration. Observation correspondence is
not full native/STEP shape equivalence or material certification.

Numerical tolerances are regression tolerances, not physical design margins.
Reference-envelope screens remain labelled as such. Untrimmed intersections
are not accepted joints; subtotal properties are not complete vehicle data.
No source files, configuration, CAD or observations are modified.
Only VerificationResult JSON is printed to stdout; diagnostics use stderr.
"""

import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = 'cad/pdr_r12_chief/fixed_structure_recovery_config_20261014_01.json'
REPORT = 'cad/pdr_r12_chief/fixed_structure_recovery_20261014_01/cad_measurements_01.json'
EXPECTED_HASHES = {
    CONFIG: '2b6a62913891cdc60857936148a29d6ef499af19d73258c6aac6482acbeaf3af',
    REPORT: '60da379e512b545cd20a176815e478f2d8dfe9d854243d36a2c880a39a1cc0b6',
}
TOL = {'length_mm': 1e-6, 'volume_mm3': 1e-5,
       'mass_kg': 1e-12, 'inertia_kg_m2': 1e-10, 'relative': 1e-9}
CHECKS = {}


def check(name, condition, details=None):
    if name in CHECKS:
        raise ValueError('Duplicate check: ' + name)
    CHECKS[name] = None if condition is None else bool(condition)
    if details is not None or condition is not True:
        print(json.dumps({'check': name, 'result': CHECKS[name],
                          'details': details}, allow_nan=False), file=sys.stderr)


def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite input number')
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Expected finite number')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Nonfinite number')
    return value


def flat(value):
    if isinstance(value, (list, tuple)):
        return [x for item in value for x in flat(item)]
    return [number(value)]


def close(a, b, atol):
    aa, bb = flat(a), flat(b)
    return len(aa) == len(bb) and all(
        abs(x-y) <= atol + TOL['relative']*abs(y)
        for x, y in zip(aa, bb))


def compare(name, observed, expected, atol):
    aa, bb = flat(observed), flat(expected)
    check(name, close(observed, expected, atol), {
        'maximum_absolute_error': max((abs(x-y) for x, y in zip(aa, bb)), default=0.0),
        'observed_scalar_count': len(aa), 'expected_scalar_count': len(bb),
        'absolute_tolerance': atol, 'relative_tolerance': TOL['relative'],
        'scope': 'Numerical regression only'})


def radial(radius, degrees, z):
    angle = math.radians(degrees)
    return [radius*math.cos(angle), radius*math.sin(angle), z]


def nominal_members(config, geometry, landing, spine, combination):
    rules = config['construction_rules']
    ring_z = geometry['ring_attachment_z_mm'] + combination['ring_elevation_increment_mm']
    ring_r = geometry['ring_attachment_radius_mm']
    fraction = config['bounded_matrix']['junction_fraction_A_to_F']
    spread = combination['brace_root_azimuth_offset_deg']
    members = {}
    for index, phi in enumerate(landing['leg_azimuths_deg'], 1):
        a = radial(ring_r, phi, ring_z)
        f = radial(geometry['foot_socket_radius_mm'], phi, geometry['foot_socket_z_mm'])
        length = math.sqrt(sum((x-y)**2 for x, y in zip(a, f)))
        outward = [(a[i]-f[i])/length for i in range(3)]
        start = [a[i]+rules['main_tube_extension_beyond_A_mm']*outward[i] for i in range(3)]
        end = [f[i]-rules['main_tube_extension_beyond_F_mm']*outward[i] for i in range(3)]
        members['MainLeg_%02d' % index] = (start, end, rules['main_tube_section_outer_inner_mm'])
        junction = [a[i]+fraction*(f[i]-a[i]) for i in range(3)]
        for suffix, sign in [('Plus', 1), ('Minus', -1)]:
            root = radial(ring_r, phi+sign*spread, ring_z)
            members['Brace_%02d_%s' % (index, suffix)] = (
                root, junction, rules['brace_tube_section_outer_inner_mm'])
    for index, (x, y) in enumerate(spine['xy_CAD_mm'], 1):
        z = ring_z + rules['spine_bottom_above_ring_mm']
        members['Spine_%02d' % index] = (
            [x, y, z], [x, y, z+rules['spine_length_mm']], spine['section_outer_inner_mm'])
    return members


def analytic_tube(start, end, diameters, density):
    delta = [end[i]-start[i] for i in range(3)]
    length = math.sqrt(sum(x*x for x in delta))
    outer, inner = [x/2 for x in diameters]
    if not length > 0 or not outer > inner >= 0:
        raise ValueError('Invalid nominal tube')
    direction = [x/length for x in delta]
    volume = math.pi*(outer*outer-inner*inner)*length
    mass = density*volume*1e-9
    axial = mass*(outer*outer+inner*inner)*0.5e-6
    transverse = mass*(3*(outer*outer+inner*inner)+length*length)/12*1e-6
    tensor = [[(transverse if i == j else 0.0)
               +(axial-transverse)*direction[i]*direction[j]
               for j in range(3)] for i in range(3)]
    return {'length': length, 'volume': volume, 'mass': mass,
            'cg': [(start[i]+end[i])/2 for i in range(3)], 'tensor': tensor}


def observed_tensor(solid):
    raw = solid['I_CG_kg_mm2']
    if len(raw) != 3 or any(len(row) != 3 for row in raw):
        raise ValueError('Expected 3x3 observed tensor')
    return [[number(x)*1e-6 for x in row] for row in raw]


def compare_solid(prefix, solid, expected):
    check(prefix+'/reported_validity', solid['valid'] is True)
    compare(prefix+'/volume_mm3', solid['volume_mm3'], expected['volume'], TOL['volume_mm3'])
    compare(prefix+'/mass_kg', solid['mass_kg'], expected['mass'], TOL['mass_kg'])
    compare(prefix+'/centroid_mm', solid['cg_CAD_mm'], expected['cg'], TOL['length_mm'])
    compare(prefix+'/tensor_kg_m2', observed_tensor(solid), expected['tensor'], TOL['inertia_kg_m2'])


def aggregate(expected):
    mass = sum(row['mass'] for row in expected.values())
    cg = [sum(row['mass']*row['cg'][i] for row in expected.values())/mass for i in range(3)]
    tensor = [[0.0]*3 for _ in range(3)]
    for row in expected.values():
        d = [(row['cg'][i]-cg[i])*1e-3 for i in range(3)]
        d2 = sum(x*x for x in d)
        for i in range(3):
            for j in range(3):
                tensor[i][j] += row['tensor'][i][j] + row['mass']*((d2 if i == j else 0)-d[i]*d[j])
    return mass, cg, tensor


def compare_sum(prefix, observed, expected):
    mass, cg, tensor = expected
    compare(prefix+'/mass_kg', observed['mass_kg'], mass, TOL['mass_kg'])
    compare(prefix+'/centroid_mm', observed['cg_CAD_mm'], cg, TOL['length_mm'])
    compare(prefix+'/CAD_tensor_kg_m2', observed['I_CAD_about_partial_CG_kg_m2'], tensor, TOL['inertia_kg_m2'])
    signs = [1, -1, -1]
    rotated = [[signs[i]*tensor[i][j]*signs[j] for j in range(3)] for i in range(3)]
    compare(prefix+'/FRD_tensor_kg_m2', observed['I_FRD_rotated_about_same_partial_CG_kg_m2'], rotated, TOL['inertia_kg_m2'])
    check(prefix+'/complete_vehicle_properties_unset',
          observed['complete_vehicle_mass_kg'] is None
          and observed['complete_vehicle_CG_C0_mm'] is None
          and observed['configuration_dependent_vehicle_inertia'] is None)


def check_candidate(config, result, specification):
    geometry, landing, spine, combination = specification
    prefix = result['candidate_id']
    actual_geometry = dict(geometry)
    actual_geometry['ring_attachment_z_mm'] += combination['ring_elevation_increment_mm']
    check(prefix+'/configured_geometry', result['geometry_hypothesis'] == actual_geometry)
    check(prefix+'/configured_landing', result['landing_arrangement'] == landing)
    check(prefix+'/configured_combination', result['approved_recovery_combination'] == combination)
    members = nominal_members(config, geometry, landing, spine, combination)
    density = config['comparison_observations']['density_assumption_kg_m3']
    expected = {name: analytic_tube(*spec, density) for name, spec in members.items()}
    cuts = result['CAD_nominal_cut_list']
    check(prefix+'/cut_inventory', len(cuts) == len(members)
          and {row['component'] for row in cuts} == set(members))
    for cut in cuts:
        name = cut['component']
        start, end, diameters = members[name]
        compare(prefix+'/'+name+'/start_mm', cut['nominal_start_CAD_mm'], start, TOL['length_mm'])
        compare(prefix+'/'+name+'/end_mm', cut['nominal_end_CAD_mm'], end, TOL['length_mm'])
        compare(prefix+'/'+name+'/diameters_mm', [cut['outer_diameter_mm'], cut['inner_diameter_mm']], diameters, TOL['length_mm'])
        compare(prefix+'/'+name+'/length_mm', cut['CAD_nominal_tube_length_mm'], expected[name]['length'], TOL['length_mm'])
    reopened = result['additional_reopened_observations']
    for stage, components in [('generated', result['components_at_density_1600']),
                              ('reopened', reopened['reopened_native_components'])]:
        check(prefix+'/'+stage+'/inventory', len(components) == len(members)
              and {c['name'] for c in components} == set(members))
        for component in components:
            name = component['name']
            check(prefix+'/'+stage+'/'+name+'/one_valid_shape',
                  component['shape_valid'] is True and len(component['solids']) == 1)
            if len(component['solids']) != 1:
                raise ValueError('Unexpected component solid count')
            compare_solid(prefix+'/'+stage+'/'+name, component['solids'][0], expected[name])
    sums = aggregate(expected)
    for label, observed in [
        ('generated_sum', result['nominal_tube_component_sum']),
        ('first_reopen_sum', result['reopened_native_component_sum']),
        ('additional_reopen_sum', reopened['reopened_native_partial_sum']),
        ('STEP_sum', reopened['STEP_uniform_assumed_density_partial_sum'])]:
        compare_sum(prefix+'/'+label, observed, sums)
    step_components = reopened['STEP_solid_components']
    check(prefix+'/STEP/solid_count', len(step_components) == len(members))
    check(prefix+'/STEP/reported_shape_validity', reopened['STEP_shape_valid'] is True)
    unused = set(range(len(step_components)))
    for name, reference in expected.items():
        matches = []
        for index in sorted(unused):
            rows = step_components[index]['solids']
            if len(rows) != 1:
                continue
            row = rows[0]
            if (close(row['volume_mm3'], reference['volume'], TOL['volume_mm3'])
                    and close(row['cg_CAD_mm'], reference['cg'], TOL['length_mm'])
                    and close(observed_tensor(row), reference['tensor'], TOL['inertia_kg_m2'])):
                matches.append(index)
        check(prefix+'/STEP/'+name+'/unique_observation_match', len(matches) == 1)
        if len(matches) == 1:
            index = matches[0]
            unused.remove(index)
            compare_solid(prefix+'/STEP/'+name, step_components[index]['solids'][0], reference)
    check(prefix+'/STEP/no_unmatched_observations', not unused)
    check(prefix+'/reported_read_only_preservation', reopened['input_bytes_unchanged'] is True
          and reopened['inputs_before'] == reopened['inputs_after'])
    edit = result['reopened_edit_recompute_observations']
    delta = math.pi*(edit['outer_radius_after_mm']**2-edit['outer_radius_before_mm']**2)*edit['length_mm']
    compare(prefix+'/edit/volume_change_mm3', edit['edited_volume_mm3']-edit['before_volume_mm3'], delta, TOL['volume_mm3'])
    compare(prefix+'/edit/restored_volume_mm3', edit['restored_volume_mm3'], edit['before_volume_mm3'], TOL['volume_mm3'])
    intersections = result['physical_component_intersections']
    check(prefix+'/reported_intersection_computation_errors_absent', not intersections['errors'])
    check(prefix+'/screen/reported_untrimmed_tubes_noninterpenetrating', not intersections['intersections'],
          {'pair_count': len(intersections['intersections']), 'scope': 'Producer observations; unfinished nominal joints, not accepted hardware'})
    clearance = result['clearance_samples']
    check(prefix+'/reported_clearance_computation_errors_absent', not clearance['errors'])
    for moving, fixed in itertools.product(
            ['upper_rotor', 'lower_rotor', 'yoke_capsule_envelope'],
            ['physical_tubes', 'assumed_joint_envelopes']):
        key = moving+'__to__'+fixed
        row = clearance['minimum_distances'][key]
        distance = number(row['minimum_distance_mm'])
        check(prefix+'/screen/reported_sampled_positive_separation/'+key, distance > 1e-7,
              {'reported_minimum_mm': distance, 'witness': row,
               'scope': 'Numerical noncontact screen of assumed envelopes, not physical clearance acceptance'})
    check(prefix+'/scope/continuous_loaded_interface_acceptance_unset',
          all(clearance[key] is None for key in
              ['continuous_clearance', 'loaded_clearance', 'mounting_interface_acceptance']))
    check(prefix+'/scope/integration_gate_still_unsatisfied',
          result['integrated_physical_ring_support_joint_gate_satisfied'] is False)


def main():
    documents = {}
    for path, expected in EXPECTED_HASHES.items():
        raw = (ROOT/path).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        check('identity/'+path, actual == expected)
        if actual != expected:
            raise ValueError('Identity mismatch; evaluation stopped')
        documents[path] = json.loads(raw)
        finite_tree(documents[path])
    config, report = documents[CONFIG], documents[REPORT]
    check('schema/config', config['schema'] == 'hopper_bounded_fixed_structure_recovery/1')
    check('schema/report', report['schema'] == 'hopper_bounded_fixed_structure_recovery_observations/1')
    specifications = {}
    for geometry, landing, spine, combination in itertools.product(
            config['geometry_baselines'], config['landing_arrangements'],
            config['spine_hypotheses'], config['bounded_matrix']['combinations']):
        if combination['treatment'] != 'new_candidate':
            continue
        cid = '_'.join([geometry['id'], landing['id'], spine['id'], combination['id']])
        specifications[cid] = (geometry, landing, spine, combination)
    candidates = report['candidates']
    check('matrix/exact_24_candidate_inventory', len(specifications) == len(candidates) == 24
          and {row['candidate_id'] for row in candidates} == set(specifications))
    check('execution/reported_processing_complete', report['processing_complete'] is True)
    check('execution/reported_failed_cases_absent', report['failed_cases'] == [] and report['failed_case_count'] == 0)
    check('execution/reported_success_count', report['successful_observation_count'] == 24)
    check('scope/physical_margin_not_approved', config['comparison_observations']['physical_clearance_acceptance_mm'] is None)
    for candidate in candidates:
        check_candidate(config, candidate, specifications[candidate['candidate_id']])
    check('evaluation/completed', True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        check('evaluation/exception_free', False,
              {'type': type(exc).__name__, 'message': str(exc)})
    for scope in ['independent_CAD_binary_geometry_inspection', 'physical_ring_support_joint_integration',
                  'complete_vehicle_mass_CG_inertia', 'continuous_loaded_and_ground_clearance',
                  'structural_and_hardware_validation', 'complete_cost_energy_budget', 'PDR_CDR_acceptance']:
        check('unperformed/'+scope, None)
    failed = [name for name, value in CHECKS.items() if value is False]
    outcome = 'failed' if failed else 'inconclusive'
    print(json.dumps({'failed_checks': failed, 'numerical_tolerances': TOL}, allow_nan=False), file=sys.stderr)
    explanation = (
        'Hash-bound checks of retained recovery observations against independently reconstructed '
        'nominal annular-tube geometry and mass-property arithmetic. '
        + ('At least one performed check is unsatisfied; see checks and stderr diagnostics. ' if failed
           else 'Performed boolean checks are satisfied; required unperformed scopes remain null. ')
        + 'CAD binaries were not inspected by this checker. Reported sampled reference-envelope separation '
        'and untrimmed-tube intersections are screens, not manufactured-hardware collision conclusions '
        'or accepted joints. Assumed-density tube subtotals are not complete vehicle properties. '
        'Physical integration, continuous loaded clearance, structural validation, complete budget '
        'and review acceptance remain unperformed.'
    )
    print(json.dumps({'outcome': outcome, 'explanation': explanation, 'checks': CHECKS}, allow_nan=False))
