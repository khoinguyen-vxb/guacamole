"""Bounded PDR-r12 fixed-structure CAD recovery, source revision 01.

Run subsequently through freecad_run(headless=True). This action's creation
of this source does not execute it. No original source or baseline is changed.

The published configuration authorizes 24 NEW tube/reference candidates;
eight DZ000_B45 baselines remain in braced_candidates_03 without regeneration.
This generator is NOT a verification program or a vehicle selection.

Declare all 99 expected outputs in the subsequent execution action:
  directory: cad/pdr_r12_chief/fixed_structure_recovery_20261014_01/
  IDs: {G_INTERMEDIATE_D279,G_WIDE_D330}_{TRIPOD,QUADPOD}_{S1,S4}_
       {DZ000_B30,DZ060_B45,DZ060_B30}
  each ID: .FCStd, _tubes.step, _arrangement.svg,
           _drawing_diagnostics_03.json
  plus: cad_measurements_01.json, generation_provenance_01.json,
        output_manifest_01.json
The diagnostic suffix 03 identifies the retained renderer, not a CAD baseline.
Do not fabricate missing exports when a case fails. Preserve partial outputs,
report failed cases and inspect missing_outputs and the actual execution log.

Physical ring/support/joint hypotheses remain a subsequent integration gate.
Reference envelopes have no mass. Untrimmed tube intersections are reported,
not accepted as manufactured joints. Stock schedules are preliminary feasible
packing upper bounds, not optimized procurement or finished-cut instructions.
"""

import copy
import hashlib
import itertools
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
THIS = ROOT / 'cad/pdr_r12_chief/build_fixed_structure_recovery_20261014_01.py'
BASE = ROOT / 'cad/pdr_r12_chief/build_braced_candidates_01.py'
RENDERER = ROOT / 'cad/pdr_r12_chief/build_braced_candidates_03.py'
CONFIG = ROOT / 'cad/pdr_r12_chief/fixed_structure_recovery_config_20261014_01.json'
PARENT = ROOT / 'analysis/pdr_r12_chief/braced_leg_study_config_01.json'
EXPECTED_HASHES = {
    BASE: 'dd275ef7747ca385671ad870169cb038921ead8357ec0d486612e55d40c054b7',
    RENDERER: '6e8e78493d292d5e7a639d671991ea3a665fbe0df0f59879aabfd0406ea48bbd',
    CONFIG: '2b6a62913891cdc60857936148a29d6ef499af19d73258c6aac6482acbeaf3af',
    PARENT: '8e5f5c75aea67512ffe8d4371c21d1915640b5aea06df2346d28df13eeadb048',
}
SUFFIXES = ('.FCStd', '_tubes.step', '_arrangement.svg', '_drawing_diagnostics_03.json')
NUMERIC_MATCH_TOLERANCES = {
    'centroid_mm': 1e-6, 'volume_mm3': 1e-5, 'inertia_kg_m2': 1e-10,
    'scope': 'Numerical observation correspondence only; not physical acceptance.',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(path):
    return {'path': str(Path(path).relative_to(ROOT)), 'sha256': sha(path)}


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def finite(value):
    value = float(value)
    require(math.isfinite(value), 'Nonfinite observation')
    return value


def preflight():
    for path, expected in EXPECTED_HASHES.items():
        require(sha(path) == expected, 'Inspected input identity mismatch: ' + str(path.relative_to(ROOT)))
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    parent = json.loads(PARENT.read_text(encoding='utf-8'))
    require(config['schema'] == 'hopper_bounded_fixed_structure_recovery/1', 'Unexpected recovery schema')
    require(config['geometry_baselines'] == parent['geometry_hypotheses'], 'Geometry baselines differ')
    require(config['landing_arrangements'] == parent['landing_arrangements'], 'Landing arrangements differ')
    require(config['bounded_matrix']['junction_fraction_A_to_F'] == 0.8, 'Unexpected brace junction fraction')
    combinations = config['bounded_matrix']['combinations']
    actual = [(c['id'], c['ring_elevation_increment_mm'], c['brace_root_azimuth_offset_deg'], c['treatment']) for c in combinations]
    require(actual == [
        ('DZ000_B45', 0, 45, 'retain_existing_baseline'),
        ('DZ000_B30', 0, 30, 'new_candidate'),
        ('DZ060_B45', 60, 45, 'new_candidate'),
        ('DZ060_B30', 60, 30, 'new_candidate')], 'Unauthorized matrix change')
    require(config['bounded_matrix']['maximum_new_candidate_count'] == 24, 'Unexpected candidate bound')
    require(config['bounded_matrix']['retained_baseline_count'] == 8, 'Unexpected baseline count')
    require(config['bounded_matrix']['automatic_search_expansion'] is False, 'Automatic expansion is forbidden')
    spines = config['spine_hypotheses']
    require([s['id'] for s in spines] == ['S1', 'S4'], 'Unexpected spine set')
    require(spines[0]['section_outer_inner_mm'] == [14, 12] and spines[0]['xy_CAD_mm'] == [[0, 0]], 'S1 differs from inspected implementation')
    require(spines[1]['section_outer_inner_mm'] == [8, 6] and spines[1]['xy_CAD_mm'] == [[-45, -45], [-45, 45], [45, -45], [45, 45]], 'S4 differs from inspected implementation')
    rules = config['construction_rules']
    for key, value in {
        'main_tube_section_outer_inner_mm': [8, 6],
        'brace_tube_section_outer_inner_mm': [8, 6],
        'main_tube_extension_beyond_A_mm': 15,
        'main_tube_extension_beyond_F_mm': 5,
        'spine_bottom_above_ring_mm': 20,
        'spine_length_mm': 300,
        'shared_root_coordinate_tolerance_mm': 1e-6,
    }.items():
        require(rules[key] == value, 'Inherited construction constant differs: ' + key)
    obs = config['comparison_observations']
    for key, value in {
        'density_assumption_kg_m3': 1600,
        'density_sensitivities_kg_m3': [1400, 1600, 1800],
        'resultant_cone_hypotheses_deg': [10, 15],
        'sample_cone_fractions': [0.5, 1.0],
        'sample_azimuth_step_deg': 15,
        'include_neutral_pose': True,
        'ground_body_tilt_hypotheses_deg': [0, 5],
        'ground_tilt_axis_azimuth_step_deg': 45,
    }.items():
        require(obs[key] == value, 'Inherited observation constant differs: ' + key)
    envelopes = config['retained_reference_envelopes']
    for key, value in {
        'rotor_slab_half_thickness_mm': 10,
        'joint_sphere_radius_mm': 20,
        'yoke_capsule_radius_mm': 7,
        'yoke_outboard_offset_beyond_rotor_radius_mm': 30,
    }.items():
        require(envelopes[key] == value, 'Reference envelope changed: ' + key)
    out = ROOT / config['execution_and_verification']['new_output_directory']
    require(out.parent == ROOT / 'cad/pdr_r12_chief', 'Unexpected output parent')
    if out.exists():
        raise FileExistsError('Preserve previous/partial output directory: ' + str(out))
    return config, parent, out


def load_inspected_functions(out):
    raw = BASE.read_text(encoding='utf-8')
    patched = raw
    changes = []
    for old, new in [('R8', 'TubeOuterRadiusEight'), ('r8', 'TubeBoreRadiusEight'),
                     ('R14', 'TubeOuterRadiusFourteen'), ('r14', 'TubeBoreRadiusFourteen')]:
        require(patched.count(repr(old)) == 2, 'Unexpected alias occurrence count: ' + old)
        patched = patched.replace(repr(old), repr(new))
        changes.append({'kind': 'retained_alias_repair', 'old': old, 'new': new, 'count': 2})
    old_cid = "    cid = geom['id'] + '_' + arrangement['id'] + '_' + spine_id\n"
    new_cid = "    cid = geom['id'] + '_' + arrangement['id'] + '_' + spine_id + '_' + topology['recovery_combination_id']\n"
    require(patched.count(old_cid) == 1, 'Candidate identifier substitution mismatch')
    patched = patched.replace(old_cid, new_cid, 1)
    drawing_call = '    arrangement_svg(drawing, cid, physical, joints + feet + [ring] + list(rotors.values()) + yoke, geom)\n'
    export_block = '    doc.recompute()\n    doc.saveAs(str(native))\n    Part.export(physical, str(step))\n'
    require(patched.count(drawing_call + export_block) == 1, 'Export-order substitution mismatch')
    patched = patched.replace(drawing_call + export_block, export_block + drawing_call, 1)
    ns = {'__name__': 'bounded_recovery_base_functions', '__file__': str(BASE)}
    exec(compile(patched, str(BASE) + ' [bounded recovery substitutions]', 'exec'), ns)
    ns.update(SOURCE=THIS, OUT=out, RUN_TAG=out.name)
    renderer = {'__name__': 'bounded_recovery_renderer_functions', '__file__': str(RENDERER)}
    exec(compile(RENDERER.read_text(encoding='utf-8'), str(RENDERER), 'exec'), renderer)
    renderer.update(THIS=THIS, OUT=out, DRAWINGS={})
    ns['arrangement_svg'] = lambda path, cid, physical, refs, geom: renderer['diagnostic_drawing'](ns, path, cid, physical, refs, geom)
    changes.extend([
        {'kind': 'identifier', 'description': 'Append approved recovery-combination ID; leave geometry baseline ID unchanged.'},
        {'kind': 'export_order', 'description': 'Retain revision-03 native/STEP-before-rendering ordering.'},
        {'kind': 'renderer', 'description': 'Reuse inspected revision-03 diagnostic functions without executing their main.'},
    ])
    return ns, renderer, {
        'base_source': identity(BASE), 'renderer_source': identity(RENDERER),
        'entry_point': identity(THIS), 'substitutions': changes,
        'executed_base_source_sha256': hashlib.sha256(patched.encode('utf-8')).hexdigest(),
        'main_functions_called': 'This file main only; neither historical module main is called.',
    }


def candidate_specs(config):
    specs = []
    retained = []
    for geom, arrangement, spine, combination in itertools.product(
            config['geometry_baselines'], config['landing_arrangements'],
            config['spine_hypotheses'], config['bounded_matrix']['combinations']):
        baseline_id = geom['id'] + '_' + arrangement['id'] + '_' + spine['id']
        cid = baseline_id + '_' + combination['id']
        if combination['treatment'] == 'retain_existing_baseline':
            retained.append({'candidate_id': cid, 'existing_baseline_id': baseline_id,
                             'directory': config['preserved_baseline']['directory'],
                             'treatment': 'Reference only; not opened, regenerated or modified by this run.'})
        else:
            specs.append((cid, copy.deepcopy(geom), copy.deepcopy(arrangement), spine['id'], copy.deepcopy(combination)))
    require(len(specs) == 24 and len(retained) == 8, 'Bounded product count mismatch')
    require(len({s[0] for s in specs}) == 24, 'Duplicate candidate output IDs')
    return specs, retained


def solid_record(solid, density):
    volume = finite(solid.Volume)
    require(volume > 0, 'Nonpositive observed solid volume')
    cm = solid.CenterOfMass
    mat = solid.MatrixOfInertia
    raw = [[finite(getattr(mat, 'A' + str(i+1) + str(j+1))) for j in range(3)] for i in range(3)]
    return {'volume_mm3': volume, 'valid': bool(solid.isValid()),
            'mass_kg': density * 1e-9 * volume,
            'cg_CAD_mm': [finite(cm.x), finite(cm.y), finite(cm.z)],
            'I_CG_kg_mm2': [[density * 1e-9 * x for x in row] for row in raw]}


def correspondence(native_components, step_components):
    native = [(c['name'], s) for c in native_components for s in c['solids']]
    remaining = set(range(len(step_components)))
    matches, ambiguous = [], []
    for name, a in native:
        eligible = []
        for j in sorted(remaining):
            b = step_components[j]['solids'][0]
            dv = abs(a['volume_mm3'] - b['volume_mm3'])
            dc = max(abs(x-y) for x, y in zip(a['cg_CAD_mm'], b['cg_CAD_mm']))
            di = max(abs(a['I_CG_kg_mm2'][r][c] - b['I_CG_kg_mm2'][r][c]) * 1e-6 for r in range(3) for c in range(3))
            if dv <= NUMERIC_MATCH_TOLERANCES['volume_mm3'] and dc <= NUMERIC_MATCH_TOLERANCES['centroid_mm'] and di <= NUMERIC_MATCH_TOLERANCES['inertia_kg_m2']:
                eligible.append((j, dv, dc, di))
        if len(eligible) == 1:
            j, dv, dc, di = eligible[0]
            remaining.remove(j)
            matches.append({'native_component': name, 'STEP_observation_index_0_based': j,
                            'volume_difference_mm3': dv, 'max_centroid_difference_mm': dc,
                            'max_tensor_difference_kg_m2': di})
        else:
            ambiguous.append({'native_component': name, 'eligible_STEP_indices': [v[0] for v in eligible]})
    return {'tolerances': NUMERIC_MATCH_TOLERANCES, 'matches': matches,
            'unmatched_or_ambiguous_native': ambiguous, 'unmatched_STEP_indices': sorted(remaining),
            'unique_observation_correspondence': len(matches) == len(native) == len(step_components) and not remaining,
            'scope': 'Volume, centroid and inertia correspondence only; not full shape equivalence or material provenance.'}


def reopen_measurements(ns, result, out, density):
    cid = result['candidate_id']
    native = out / (cid + '.FCStd')
    step = out / (cid + '_tubes.step')
    before = [identity(native), identity(step)]
    doc = App.openDocument(str(native))
    cuts, components = [], []
    try:
        doc.recompute()
        for name in result['native_component_names']:
            obj = doc.getObject(name)
            require(obj is not None, 'Missing reopened component: ' + name)
            outer = doc.getObject(name + '_Outer')
            bore = doc.getObject(name + '_Bore')
            require(outer is not None and bore is not None, 'Missing editable cylinder features: ' + name)
            components.append(ns['measure_component'](obj, density))
            cuts.append({'component': name, 'section_nominal_mm': str(obj.SectionNominalMM),
                         'outer_diameter_mm': 2 * finite(outer.Radius),
                         'inner_diameter_mm': 2 * finite(bore.Radius),
                         'CAD_nominal_tube_length_mm': finite(outer.Height),
                         'role': str(obj.MemberRole),
                         'nominal_start_CAD_mm': ns['xyz'](obj.NominalStartCADmm),
                         'nominal_end_CAD_mm': ns['xyz'](obj.NominalEndCADmm),
                         'finished_cut_length_accepted': False})
    finally:
        App.closeDocument(doc.Name)
    shape = Part.read(str(step))
    step_components = [{'name': 'STEP_unmapped_%02d' % i, 'solids': [solid_record(s, density)]}
                       for i, s in enumerate(shape.Solids, 1)]
    require(bool(step_components), 'STEP contains no solids')
    after = [identity(native), identity(step)]
    require(before == after, 'Read-only native/STEP measurement changed input bytes')
    return cuts, {
        'inputs_before': before, 'inputs_after': after, 'input_bytes_unchanged': True,
        'reopened_native_components': components,
        'reopened_native_partial_sum': ns['aggregate'](components),
        'STEP_shape_valid': bool(shape.isValid()), 'STEP_solid_components': step_components,
        'STEP_uniform_assumed_density_partial_sum': ns['aggregate'](step_components),
        'correspondence': correspondence(components, step_components),
        'scope': 'Additional reopened solid observations; same measurement convention, not an independent verification program. STEP does not supply material assignments.',
    }


def baseline_length(member_name, baseline_geom, arrangement, ns):
    if member_name.startswith('Spine_'):
        return 300.0
    index = int(member_name.split('_')[1]) - 1
    phi = arrangement['leg_azimuths_deg'][index]
    a = ns['radial'](baseline_geom['ring_attachment_radius_mm'], phi, baseline_geom['ring_attachment_z_mm'])
    f = ns['radial'](baseline_geom['foot_socket_radius_mm'], phi, baseline_geom['foot_socket_z_mm'])
    if member_name.startswith('MainLeg_'):
        return ns['norm'](ns['sub'](f, a)) + 20.0
    j = ns['add'](a, ns['scale'](ns['sub'](f, a), 0.8))
    sign = 1 if member_name.endswith('_Plus') else -1
    b = ns['radial'](baseline_geom['ring_attachment_radius_mm'], phi + sign * 45, baseline_geom['ring_attachment_z_mm'])
    return ns['norm'](ns['sub'](j, b))


def stock_scenarios(cuts, parent):
    contract = parent['mass_and_procurement_contract']
    stock_mm = finite(contract['stock_length_allowance_mm'])
    trim_mm = finite(contract['stock_end_trim_each_end_mm'])
    kerf_mm = finite(contract['kerf_per_cut_mm'])
    capacity_um = math.floor((stock_mm - 2*trim_mm) * 1000)
    require(capacity_um > 0, 'Nonpositive stock capacity')
    scenarios = []
    for debit in contract['brace_stock_sensitivity_extra_length_per_member_mm']:
        sections = {}
        for row in cuts:
            extra = finite(debit) if row['component'].startswith('Brace_') else 0.0
            reservation_um = math.ceil((row['CAD_nominal_tube_length_mm'] + extra + kerf_mm) * 1000)
            item = {'component': row['component'], 'CAD_nominal_length_mm': row['CAD_nominal_tube_length_mm'],
                    'brace_sensitivity_extra_mm': extra, 'kerf_mm': kerf_mm,
                    'rounded_reserved_length_um': reservation_um}
            sections.setdefault(row['section_nominal_mm'], []).append(item)
        results = []
        for section, members in sorted(sections.items()):
            too_long = [r for r in members if r['rounded_reserved_length_um'] > capacity_um]
            bins = []
            if not too_long:
                for item in sorted(members, key=lambda r: (-r['rounded_reserved_length_um'], r['component'])):
                    target = next((b for b in bins if b['remaining_um'] >= item['rounded_reserved_length_um']), None)
                    if target is None:
                        target = {'cuts': [], 'remaining_um': capacity_um}
                        bins.append(target)
                    target['cuts'].append(item)
                    target['remaining_um'] -= item['rounded_reserved_length_um']
            results.append({'section_nominal_mm': section, 'overlength_members': too_long,
                            'whole_stock_count_feasible_upper_bound': len(bins) if not too_long else None,
                            'length_only_stock_count_lower_bound': math.ceil(sum(r['rounded_reserved_length_um'] for r in members) / capacity_um),
                            'schedule': bins, 'optimality_established': False})
        scenarios.append({'brace_extra_length_per_member_mm': debit, 'sections': results})
    return {'stock_length_assumption_mm': stock_mm, 'end_trim_each_end_mm': trim_mm,
            'kerf_per_cut_mm': kerf_mm, 'usable_length_um': capacity_um,
            'method': 'First-fit decreasing; lengths rounded upward to 1 micrometre, not a proven minimum-bin solution.',
            'scenarios': scenarios,
            'scope': 'Jointly packs same-section legs, braces and spines for each candidate. Assumes common stock product; supplier variant, finished cuts and fitting overlaps remain unresolved.',
            'currency': 'AUD', 'new_price_observation': False, 'purchase_cost_AUD': None,
            'vehicle_budget_compliance': None}


def main():
    config, parent, out = preflight()
    specs, retained = candidate_specs(config)
    ns, renderer, source_provenance = load_inspected_functions(out)
    inputs_before = [identity(p) for p in EXPECTED_HASHES]
    expected_paths = [str((out / (cid + suffix)).relative_to(ROOT))
                      for cid, _, _, _, _ in specs for suffix in SUFFIXES]
    expected_paths += [str((out / name).relative_to(ROOT)) for name in
                       ('cad_measurements_01.json', 'generation_provenance_01.json', 'output_manifest_01.json')]
    require(len(expected_paths) == len(set(expected_paths)) == 99, 'Expected-output inventory mismatch')
    out.mkdir(parents=True)
    provenance = {
        'schema': 'hopper_bounded_recovery_generation_provenance/1',
        'generated_at_UTC': datetime.now(timezone.utc).isoformat(),
        'authority': config['authority'], 'inputs': inputs_before,
        'generator': source_provenance, 'expected_output_paths': expected_paths,
        'retained_baselines': retained,
        'geometry_changes': 'Only approved ring elevation and brace-root phasing; spine bases follow ring. All rotor hubs, gimbal origins, feet and moving-yoke definitions remain fixed.',
        'integration_completion_gate': config['integration_completion_gate'],
        'acceptance': 'Not assessed; generated tube/reference candidates are not an integrated vehicle.',
    }
    dump(out / 'generation_provenance_01.json', provenance)
    report = {
        'schema': 'hopper_bounded_fixed_structure_recovery_observations/1',
        'generated_at_UTC': datetime.now(timezone.utc).isoformat(),
        'authority': config['authority'], 'inputs': inputs_before,
        'source_provenance': source_provenance, 'FreeCAD_version': list(App.Version()),
        'units_and_frames': config['units_and_frames'], 'retained_baselines': retained,
        'expected_new_candidate_count': 24, 'candidates': [], 'failed_cases': [],
        'processing_complete': False,
        'integration_completion_gate': config['integration_completion_gate'],
        'evidence_boundary': 'Partial nominal tube solids and assumed reference envelopes only. No complete-mass, structural, continuous/loaded-clearance, budget, hardware or review acceptance.',
    }
    measurements_path = out / 'cad_measurements_01.json'
    legacy_config = copy.deepcopy(parent)
    legacy_config['clearance_contract']['resultant_cone_hypotheses_deg'] = config['comparison_observations']['resultant_cone_hypotheses_deg']
    legacy_config['sections_and_material_sensitivities']['density_kg_m3'] = config['comparison_observations']['density_sensitivities_kg_m3']
    seed_topology = next(t for t in parent['topologies'] if t['id'] == 'B45_F080')
    for cid, baseline_geom, arrangement, spine_id, combination in specs:
        open_before = set(App.listDocuments())
        try:
            geom = copy.deepcopy(baseline_geom)
            geom['ring_attachment_z_mm'] += combination['ring_elevation_increment_mm']
            require(all(geom[k] == baseline_geom[k] for k in geom if k != 'ring_attachment_z_mm'), 'Unauthorized geometry mutation')
            topology = copy.deepcopy(seed_topology)
            topology.update(id='B%d_F080' % combination['brace_root_azimuth_offset_deg'],
                            brace_root_azimuth_offset_deg=combination['brace_root_azimuth_offset_deg'],
                            recovery_combination_id=combination['id'])
            result = ns['candidate'](legacy_config, geom, arrangement, spine_id, topology)
            require(result['candidate_id'] == cid, 'Unexpected output identifier')
            diagnostic = renderer['DRAWINGS'][cid]
            result['retained_renderer_diagnostics'] = diagnostic
            result['files'].append(diagnostic['diagnostics'])
            cuts, reopened = reopen_measurements(ns, result, out, config['comparison_observations']['density_assumption_kg_m3'])
            for row in cuts:
                old = baseline_length(row['component'], baseline_geom, arrangement, ns)
                row['analytical_DZ000_B45_comparator_length_mm'] = old
                row['length_change_from_analytical_baseline_mm'] = row['CAD_nominal_tube_length_mm'] - old
                row['baseline_comparator_scope'] = 'Reconstructed from the pinned baseline construction rules; not a fresh baseline CAD measurement.'
            result.update(approved_recovery_combination=combination,
                          unchanged_geometry_baseline=baseline_geom,
                          additional_reopened_observations=reopened,
                          CAD_nominal_cut_list=cuts,
                          preliminary_stock_scenarios=stock_scenarios(cuts, parent),
                          integrated_physical_ring_support_joint_gate_satisfied=False)
            report['candidates'].append(result)
            print(json.dumps({'candidate': cid, 'status': 'observations recorded; acceptance not assessed'}), file=sys.stderr)
        except Exception as exc:
            existing = [identity(out / (cid + suffix)) for suffix in SUFFIXES if (out / (cid + suffix)).is_file()]
            failure = {'candidate_id': cid, 'combination': combination,
                       'exception_type': type(exc).__name__, 'message': str(exc),
                       'partial_output_files': existing,
                       'disposition': 'Preserved unsuccessful case; no automatic retry, geometry change or substitute export.'}
            report['failed_cases'].append(failure)
            print(json.dumps(failure), file=sys.stderr)
        finally:
            for name in set(App.listDocuments()) - open_before:
                App.closeDocument(name)
        dump(measurements_path, report)
    inputs_after = [identity(p) for p in EXPECTED_HASHES]
    require(inputs_before == inputs_after, 'Historical/configuration input bytes changed during execution')
    report.update(processing_complete=True, inputs_after=inputs_after,
                  input_bytes_unchanged=True, successful_observation_count=len(report['candidates']),
                  failed_case_count=len(report['failed_cases']))
    dump(measurements_path, report)
    manifest_path = out / 'output_manifest_01.json'
    existing = [identity(ROOT / p) for p in expected_paths if ROOT / p != manifest_path and (ROOT / p).is_file()]
    missing = [p for p in expected_paths if ROOT / p != manifest_path and not (ROOT / p).is_file()]
    dump(manifest_path, {
        'schema': 'hopper_bounded_recovery_output_manifest/1',
        'files': existing, 'manifest_path': str(manifest_path.relative_to(ROOT)),
        'expected_output_paths': expected_paths, 'missing_expected_outputs': missing,
        'successful_observation_count': len(report['candidates']),
        'failed_case_count': len(report['failed_cases']),
        'evidence_boundary': 'File production and measurements are not VerificationResult evidence. Publish actual artifacts and use an editable artifact-bound checker through verify_command; retain all unsuccessful screens.'})
    print(json.dumps({'measurements': str(measurements_path.relative_to(ROOT)),
                      'manifest': str(manifest_path.relative_to(ROOT)),
                      'successful_observation_count': len(report['candidates']),
                      'failed_case_count': len(report['failed_cases']),
                      'missing_output_count': len(missing), 'acceptance': 'not established'}))


if __name__ == '__main__':
    main()
