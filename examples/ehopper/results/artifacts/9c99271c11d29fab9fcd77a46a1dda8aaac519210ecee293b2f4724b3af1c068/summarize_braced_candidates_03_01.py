"""Summarize stored revision-03 CAD observations without rerunning geometry.

Execute through the granted execute tool, with workdir='.'. Declare output:
analysis/pdr_r12_chief/braced_candidates_03_observation_digest_01.json

Include this source and the producing CAD tool_result in execution inputs.
This is NOT a verification program. It reads measurement/manifest JSON only;
it does not reopen FCStd/STEP, establish drawing completeness, certify
clearances, select a candidate or establish complete vehicle mass.
Preserve original inputs and existing outputs.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve()
DIRECTORY = ROOT / 'cad/pdr_r12_chief/braced_candidates_03'
MEASUREMENTS = DIRECTORY / 'cad_measurements_01.json'
MANIFEST = DIRECTORY / 'output_manifest_01.json'
OUTPUT = ROOT / 'analysis/pdr_r12_chief/braced_candidates_03_observation_digest_01.json'


def identity(path):
    return {'path': str(path.relative_to(ROOT)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def boolean_counts(values):
    values = list(values)
    return {'true': sum(v is True for v in values),
            'false': sum(v is False for v in values),
            'other': sum(v is not True and v is not False for v in values)}


def summarize(candidate):
    components = candidate['components_at_density_1600']
    solids = [solid for component in components for solid in component['solids']]
    clearance = candidate['clearance_samples']
    intersections = candidate['physical_component_intersections']
    step = candidate['step_readback']
    edit = candidate['reopened_edit_recompute_observations']
    observed_delta = edit['edited_volume_mm3'] - edit['before_volume_mm3']
    return {
        'candidate_id': candidate['candidate_id'],
        'status': candidate['status'],
        'geometry_hypothesis': candidate['geometry_hypothesis'],
        'landing_arrangement': candidate['landing_arrangement'],
        'spine_hypothesis': candidate['spine_hypothesis'],
        'brace_topology': candidate['brace_topology'],
        'native_component_names': candidate['native_component_names'],
        'reported_native_shape_validity_counts': boolean_counts(c['shape_valid'] for c in components),
        'reported_native_solid_validity_counts': boolean_counts(s['valid'] for s in solids),
        'density_assumptions_kg_m3': sorted(set(c['density_assumption_kg_m3'] for c in components)),
        'nominal_tube_component_sum': candidate['nominal_tube_component_sum'],
        'reopened_native_component_sum': candidate['reopened_native_component_sum'],
        'density_sensitivities': candidate['density_sensitivities'],
        'physical_component_intersections': intersections,
        'clearance_observations': {
            'evidence_level': clearance['evidence_level'],
            'resultant_cones_deg': clearance['resultant_cones_deg'],
            'joint_sample_count': len(clearance['joint_samples_alpha_beta_deg']),
            'body_ground_samples_tilt_axis_azimuth_deg': clearance['body_ground_samples_tilt_axis_azimuth_deg'],
            'ground_construction': clearance['ground_construction'],
            'rotor_slab_half_thickness_mm': clearance['rotor_slab_half_thickness_mm'],
            'joint_envelope_radius_mm': clearance['joint_envelope_radius_mm'],
            'minimum_distances': clearance['minimum_distances'],
            'ground': clearance['ground'],
            'counts': clearance['counts'],
            'errors': clearance['errors'],
            'continuous_clearance': clearance['continuous_clearance'],
            'loaded_clearance': clearance['loaded_clearance'],
            'mounting_interface_acceptance': clearance['mounting_interface_acceptance']
        },
        'neutral_moving_envelope_gaps': candidate['neutral_moving_envelope_gaps'],
        'reopened_edit_recompute_observations': edit,
        'edit_arithmetic_from_stored_observations': {
            'observed_delta_volume_mm3': observed_delta,
            'delta_minus_reported_analytical_delta_mm3': observed_delta - edit['analytical_delta_volume_mm3'],
            'restored_minus_initial_volume_mm3': edit['restored_volume_mm3'] - edit['before_volume_mm3'],
            'scope': 'Arithmetic on stored observations only; not an independent recompute test.'
        },
        'step_readback': step,
        'drawing_projection_revision03': candidate['drawing_projection_revision03'],
        'missing_mass_and_interfaces': candidate['missing_mass_and_interfaces'],
        'acceptance_as_recorded': candidate['acceptance'],
        'reported_candidate_file_identities': candidate['files']
    }


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve existing digest: ' + str(OUTPUT))
    report = read_json(MEASUREMENTS)
    manifest = read_json(MANIFEST)
    rows = [summarize(candidate) for candidate in report['candidates']]
    digest = {
        'schema': 'hopper_braced_candidate_observation_digest/1',
        'generated_at_UTC': datetime.now(timezone.utc).isoformat(),
        'status': 'Stored observations summarized; no verification or selection performed',
        'inputs': [identity(SOURCE), identity(MEASUREMENTS), identity(MANIFEST)],
        'authority_as_recorded': report['authority'],
        'frame_as_recorded': report['frame'],
        'generator_revision_provenance': report['generator_revision_provenance'],
        'source_scope': report['scope'],
        'units': {'length': 'mm', 'mass': 'kg', 'density': 'kg/m^3',
                  'aggregate_inertia': 'kg m^2', 'volume': 'mm^3', 'angle': 'deg'},
        'limitations': [
            'No FCStd or STEP file is reopened by this program.',
            'Validity, editability and clearance values are reported by the CAD generator, not independently verified here.',
            'Tube sums exclude fittings, ring, gimbal, equipment and other installed items; they are not complete vehicle mass or CG.',
            'Overlapping tube components are not accepted joints or corrected assembled mass.',
            'Rotor slabs, yoke capsules and joint spheres are assumed non-mass reference envelopes.',
            'Distance observations are sampled, not continuous or loaded clearance certification.',
            'Drawing omissions remain unresolved; SVG production alone is not a complete drawing.',
            'All original null acceptance fields are retained; no PDR/CDR or physical acceptance is inferred.'
        ],
        'unmodeled_alternatives_retained': report['unmodeled_alternatives_retained'],
        'manifest_file_count': len(manifest['files']),
        'candidate_count': len(rows),
        'candidates': rows
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('x', encoding='utf-8') as stream:
        json.dump(digest, stream, indent=2, allow_nan=False)
        stream.write('\n')

    # Compact console observations for Chief review. These are not checks.
    console_rows = []
    for row in rows:
        gaps = row['clearance_observations']
        mass = row['nominal_tube_component_sum']
        overlap = row['physical_component_intersections']
        drawing = row['drawing_projection_revision03']
        console_rows.append({
            'candidate_id': row['candidate_id'],
            'partial_tube_mass_kg': mass['mass_kg'],
            'partial_tube_CG_CAD_mm': mass['cg_CAD_mm'],
            'partial_tube_inertia_CAD_kg_m2': mass['I_CAD_about_partial_CG_kg_m2'],
            'native_solid_validity_counts': row['reported_native_solid_validity_counts'],
            'step_solid_count': row['step_readback']['solid_count'],
            'step_validity_counts': boolean_counts(row['step_readback']['solid_validity']),
            'reported_tube_intersection_count': len(overlap['intersections']),
            'intersection_error_count': len(overlap['errors']),
            'sampled_minimum_distances_with_witnesses': gaps['minimum_distances'],
            'sampled_ground': gaps['ground'],
            'clearance_error_count': len(gaps['errors']),
            'neutral_moving_envelope_gaps': row['neutral_moving_envelope_gaps'],
            'edit_arithmetic': row['edit_arithmetic_from_stored_observations'],
            'drawing_omitted_edge_count': drawing['omitted_edge_count'],
            'drawing_fallback_edge_count': drawing['fallback_edge_count'],
            'drawing_object_error_count': drawing['object_error_count'],
            'drawing_renderer_error': drawing['renderer_error'],
            'complete_vehicle_mass_kg': mass['complete_vehicle_mass_kg'],
            'acceptance_as_recorded': row['acceptance_as_recorded']
        })
    print(json.dumps({'status': digest['status'], 'output': identity(OUTPUT),
                      'candidate_count': len(rows), 'candidates': console_rows},
                     separators=(',', ':'), allow_nan=False))


if __name__ == '__main__':
    main()
