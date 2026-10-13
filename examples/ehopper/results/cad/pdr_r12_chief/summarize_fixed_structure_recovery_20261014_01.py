"""Summarize retained bounded CAD observations; do not execute CAD.

Subsequent execution through execute:
  repository='6dof_hopper', workdir='.'
  command=['python', 'cad/pdr_r12_chief/summarize_fixed_structure_recovery_20261014_01.py']
Declare both output files listed below. Include this source, the producing
CAD tool-result Ref and the configuration Ref in execution inputs.

This is a reporting program, NOT a verification program. It reads only the
configuration and measurement JSON. Producer-reported geometry observations
are not independently reproduced. No thresholds, geometry, source data,
material properties or candidate selections are changed.
"""

import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'cad/pdr_r12_chief'
MEASUREMENTS = DIRECTORY / 'fixed_structure_recovery_20261014_01/cad_measurements_01.json'
CONFIG = DIRECTORY / 'fixed_structure_recovery_config_20261014_01.json'
OUTPUT_JSON = DIRECTORY / 'fixed_structure_recovery_digest_20261014_01.json'
OUTPUT_MD = DIRECTORY / 'fixed_structure_recovery_digest_20261014_01.md'
EXPECTED = {
    MEASUREMENTS: '60da379e512b545cd20a176815e478f2d8dfe9d854243d36a2c880a39a1cc0b6',
    CONFIG: '2b6a62913891cdc60857936148a29d6ef499af19d73258c6aac6482acbeaf3af',
}
BOUNDARY = (
    'Digest of retained producer observations only; no FreeCAD rerun or '
    'independent geometry verification. Mass is the nominal separate-tube '
    'subtotal at assumed density, not assembled or complete vehicle mass. '
    'Distances are sampled assumed-envelope observations, not continuous or '
    'loaded-clearance acceptance. Tube overlaps are not accepted joints. '
    'Physical ring/support/joint integration remains required before '
    'structural down-selection. No budget, structural, hardware or review '
    'acceptance is established.'
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pinned(path):
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != EXPECTED[path]:
        raise ValueError('Input identity mismatch: ' + str(path.relative_to(ROOT)))
    return json.loads(raw.decode('utf-8'))


def minimum_if_complete(mapping, keys):
    values = []
    for key in keys:
        record = mapping.get(key)
        if not isinstance(record, dict):
            return None
        value = record.get('minimum_distance_mm')
        if not isinstance(value, (float, int)) or not math.isfinite(value):
            return None
        values.append(value)
    return min(values)


def summarize(candidate):
    mass = candidate['nominal_tube_component_sum']
    clearance = candidate['clearance_samples']
    minima = clearance['minimum_distances']
    overlap = candidate['physical_component_intersections']
    reopened = candidate['additional_reopened_observations']
    correspondence = reopened['correspondence']
    components = candidate['components_at_density_1600']
    stock = candidate['preliminary_stock_scenarios']
    stock_rows = []
    for scenario in stock['scenarios']:
        sections = scenario['sections']
        counts = [s['whole_stock_count_feasible_upper_bound'] for s in sections]
        total = sum(counts) if counts and all(type(n) is int for n in counts) else None
        stock_rows.append({
            'brace_extra_length_per_member_mm': scenario['brace_extra_length_per_member_mm'],
            'total_whole_stock_count_feasible_upper_bound': total,
            'sections': [{
                'section_nominal_mm': s['section_nominal_mm'],
                'whole_stock_count_feasible_upper_bound': s['whole_stock_count_feasible_upper_bound'],
                'length_only_stock_count_lower_bound': s['length_only_stock_count_lower_bound'],
                'overlength_members': s['overlength_members'],
                'optimality_established': s['optimality_established'],
            } for s in sections],
        })
    diagnostics = candidate['retained_renderer_diagnostics']
    return {
        'candidate_id': candidate['candidate_id'],
        'source_locator': 'candidates[candidate_id=' + candidate['candidate_id'] + ']',
        'geometry_hypothesis': candidate['geometry_hypothesis'],
        'approved_recovery_combination': candidate['approved_recovery_combination'],
        'density_assumption_kg_m3': 1600,
        'nominal_tube_component_sum': mass,
        'density_sensitivities': candidate['density_sensitivities'],
        'producer_reported_invalid_component_names': [c['name'] for c in components if not c['shape_valid']],
        'producer_reported_invalid_solid_count': sum(not s['valid'] for c in components for s in c['solids']),
        'producer_reported_native_component_count': len(components),
        'producer_reported_STEP_readback': candidate['step_readback'],
        'producer_reported_reopen_input_bytes_unchanged': reopened['input_bytes_unchanged'],
        'producer_reported_unique_native_STEP_observation_correspondence': correspondence['unique_observation_correspondence'],
        'unmatched_or_ambiguous_native': correspondence['unmatched_or_ambiguous_native'],
        'unmatched_STEP_indices': correspondence['unmatched_STEP_indices'],
        'producer_reported_edit_recompute_observations': candidate['reopened_edit_recompute_observations'],
        'tube_intersection_count': len(overlap['intersections']),
        'tube_intersection_witnesses': overlap['intersections'],
        'tube_intersection_errors': overlap['errors'],
        'sampled_rotor_to_tubes_minimum_mm': minimum_if_complete(minima, ['upper_rotor__to__physical_tubes', 'lower_rotor__to__physical_tubes']),
        'sampled_rotor_to_joint_envelopes_minimum_mm': minimum_if_complete(minima, ['upper_rotor__to__assumed_joint_envelopes', 'lower_rotor__to__assumed_joint_envelopes']),
        'sampled_yoke_to_tubes_minimum_mm': minimum_if_complete(minima, ['yoke_capsule_envelope__to__physical_tubes']),
        'sampled_yoke_to_joint_envelopes_minimum_mm': minimum_if_complete(minima, ['yoke_capsule_envelope__to__assumed_joint_envelopes']),
        'sampled_minimum_distance_witnesses': minima,
        'sampled_ground_observation': clearance['ground'],
        'ground_construction': clearance['ground_construction'],
        'sampled_joint_pose_count': len(clearance['joint_samples_alpha_beta_deg']),
        'sampled_body_ground_case_count': len(clearance['body_ground_samples_tilt_axis_azimuth_deg']),
        'clearance_errors': clearance['errors'],
        'neutral_moving_envelope_gaps': candidate['neutral_moving_envelope_gaps'],
        'drawing_diagnostic_keys': sorted(diagnostics),
        'drawing_diagnostics_file': diagnostics['diagnostics'],
        'drawing_limitation': 'Consult the retained per-candidate diagnostic file; this digest does not inspect the SVG or infer absence of omissions.',
        'stock_length_assumption_mm': stock['stock_length_assumption_mm'],
        'stock_method': stock['method'],
        'stock_scenarios': stock_rows,
        'purchase_cost_AUD': stock['purchase_cost_AUD'],
        'vehicle_budget_compliance': stock['vehicle_budget_compliance'],
        'integrated_physical_ring_support_joint_gate_satisfied': candidate['integrated_physical_ring_support_joint_gate_satisfied'],
        'missing_mass_and_interfaces': candidate['missing_mass_and_interfaces'],
        'producer_reported_acceptance': candidate['acceptance'],
        'producer_reported_files': candidate['files'],
    }


def fmt(value, digits=3):
    return 'unknown' if value is None else format(value, '.' + str(digits) + 'f')


def main():
    for output in (OUTPUT_JSON, OUTPUT_MD):
        if output.exists():
            raise FileExistsError('Preserve existing digest: ' + str(output))
    config = read_pinned(CONFIG)
    report = read_pinned(MEASUREMENTS)
    if report['schema'] != 'hopper_bounded_fixed_structure_recovery_observations/1':
        raise ValueError('Unexpected measurement schema')
    expected_ids = [
        '_'.join((g['id'], a['id'], s['id'], c['id']))
        for g, a, s, c in itertools.product(
            config['geometry_baselines'], config['landing_arrangements'],
            config['spine_hypotheses'], config['bounded_matrix']['combinations'])
        if c['treatment'] == 'new_candidate'
    ]
    rows = [summarize(c) for c in report['candidates']]
    observed_ids = [r['candidate_id'] for r in rows]
    failed_ids = [f['candidate_id'] for f in report['failed_cases']]
    inputs = [{'path': str(p.relative_to(ROOT)), 'sha256': expected} for p, expected in EXPECTED.items()]
    digest = {
        'schema': 'hopper_bounded_recovery_observation_digest/1',
        'scope': BOUNDARY,
        'source_generated_at_UTC': report['generated_at_UTC'],
        'authority': report['authority'],
        'inputs': inputs,
        'digest_source': {'path': str(Path(__file__).resolve().relative_to(ROOT)), 'sha256': sha(Path(__file__).resolve())},
        'units': {'mass': 'kg', 'geometry': 'mm', 'inertia': 'kg m^2', 'purchase_cost': 'AUD'},
        'units_and_frames': report['units_and_frames'],
        'producer_processing_complete': report['processing_complete'],
        'producer_successful_observation_count': report['successful_observation_count'],
        'producer_failed_case_count': report['failed_case_count'],
        'parsed_candidate_count': len(rows),
        'configured_new_candidate_count': len(expected_ids),
        'duplicate_observed_ids': sorted({cid for cid in observed_ids if observed_ids.count(cid) > 1}),
        'configured_ids_without_observations': sorted(set(expected_ids) - set(observed_ids)),
        'unexpected_observed_ids': sorted(set(observed_ids) - set(expected_ids)),
        'ids_both_observed_and_failed': sorted(set(observed_ids) & set(failed_ids)),
        'failed_cases': report['failed_cases'],
        'retained_baselines': report['retained_baselines'],
        'baseline_comparison_limit': 'Eight retained baselines were not read or regenerated by this digest; no fresh baseline numerical comparison is asserted.',
        'integration_completion_gate': report['integration_completion_gate'],
        'candidates': rows,
        'selection': None,
        'physical_acceptance': 'not_assessed',
    }
    lines = [
        '# Bounded fixed-structure CAD observations', '', BOUNDARY, '',
        'Source measurement SHA-256: `' + EXPECTED[MEASUREMENTS] + '`.', '',
        'Parsed observation records: ' + str(len(rows)) +
        '; configured new candidates: ' + str(len(expected_ids)) +
        '; producer-recorded failed cases: ' + str(report['failed_case_count']) + '.', '',
        'All distances below are producer-reported sampled nominal observations in mm. '
        'Mass is a tube subtotal in kg at the hypothetical density 1600 kg/m^3. '
        'Ground values use the source flat-ground/point-foot construction, without loaded deflection.', '',
        '| Candidate | Tube kg | Partial CG Z mm | Rotor/tube mm | Yoke/tube mm | Yoke/joint mm | Ground mm | Tube overlap pairs |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        mass = row['nominal_tube_component_sum']
        lines.append('| ' + ' | '.join([
            row['candidate_id'], fmt(mass['mass_kg'], 6), fmt(mass['cg_CAD_mm'][2]),
            fmt(row['sampled_rotor_to_tubes_minimum_mm']),
            fmt(row['sampled_yoke_to_tubes_minimum_mm']),
            fmt(row['sampled_yoke_to_joint_envelopes_minimum_mm']),
            fmt(row['sampled_ground_observation']['minimum_z_mm']),
            str(row['tube_intersection_count']),
        ]) + ' |')
    lines.extend(['', '## Stock observations', '',
                  'Counts are feasible packing upper bounds for assumed 1000 mm stock, '
                  'not proven minimum purchases or accepted finished cuts. Costs remain unresolved.', '',
                  '| Candidate | Brace extra mm : total stock count |', '|---|---|'])
    for row in rows:
        values = ['%s : %s' % (s['brace_extra_length_per_member_mm'],
                              s['total_whole_stock_count_feasible_upper_bound'])
                  for s in row['stock_scenarios']]
        lines.append('| ' + row['candidate_id'] + ' | ' + '; '.join(values) + ' |')
    lines.extend(['', '## Evidence limits and next gate', '',
                  '- The JSON digest retains clearance witnesses, failed cases, overlap records, '
                  'edit observations, correspondence exceptions and reported artifact identities.',
                  '- Drawing diagnostics require separate review; textual reporting is not visual inspection.',
                  '- Add explicit physical ring/support/joint hypotheses and mass ownership before integrated comparison.',
                  '- Retain S2/S3, aluminium-spine and larger-section alternatives in the overall trade.',
                  '- No configuration, travel limit, component purchase or review baseline is selected.', ''])
    json_text = json.dumps(digest, indent=2, allow_nan=False) + '\n'
    markdown = '\n'.join(lines)
    for path, expected in EXPECTED.items():
        if sha(path) != expected:
            raise ValueError('Input changed during reporting: ' + str(path))
    with OUTPUT_JSON.open('x', encoding='utf-8') as handle:
        handle.write(json_text)
    with OUTPUT_MD.open('x', encoding='utf-8') as handle:
        handle.write(markdown)
    print(markdown)
    print('JSON detail: ' + str(OUTPUT_JSON.relative_to(ROOT)))
    print('Markdown: ' + str(OUTPUT_MD.relative_to(ROOT)))


if __name__ == '__main__':
    main()
