"""Verify the retained M4-02 diagnostic evidence chain, preserving failures.

Run through verify_command with every referenced artifact in tool inputs.
This program reads actual saved files, checks their digests, and recomputes
verdicts from retained numerical measurements. It does NOT rerun OCCT, inspect
new geometry, verify M4-03 candidates, or establish physical qualification.
No files are written. Stdout contains exactly one VerificationResult JSON;
diagnostics are sent to stderr. The original failed diagnostic is preserved.

Authority: system_model:system@4; work plan 99f7bb629eef45b89fa38d27c803868c@1;
interface decision 88561ff8b3ba4e8286cebd95a93e3b08@1.
"""
import sys
sys.dont_write_bytecode = True
import json
import math
import hashlib
import itertools
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    'audit': ('analysis/pdr_cad_trade/diagnostic_geometry_audit_m4_02.json',
              'b02696dcde92f2d91754c5517a8a3f259781e7ee52abf0eb4afa6e1eccfa6b10'),
    'audit_program': ('cad/pdr_trade/diagnostic_geometry_audit_m4_02.py',
                      '62250cbd093f319183d66d355b70e24b52a6c492ef31e18161f57de2ece3a07b'),
    'report': ('analysis/pdr_cad_trade/diagnostic_s2_c14_t_d330_m4_01.json',
               'e855cbe95009582ee9206cac22eeb153a7a649682608093c55295180bc7780fb'),
    'fcstd': ('cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_01.FCStd',
              '45dbd41ccba904f73bcec91d50cc8af0677ea426baadfbfa8ffe865fa9404b3e'),
    'step': ('cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_01.step',
             '67356901777acf1a7a8853314fa4af95b4c043b5ed087f693158f247573571d2'),
    'drawing': ('cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_01_arrangement.svg',
                'd5d2408ea177b56ca04ab3cb19e8b573b4783a16b128cd4ce22f648328d4445e'),
    'kernel': ('cad/pdr_trade/structural_kernel_m4_01.py',
               '26269836fe1ced116669ce58f2295682162f65103e80da1ae1a95d20028e9c90'),
    'builder': ('cad/pdr_trade/structural_candidate_builder_m4_01.py',
                'a89e657da1cee7a31be68e116303bbb1d5f7d22eed9c61716f7ca41faa60711a')
}
MODEL = {'kind':'system_model', 'id':'system', 'revision':4,
         'sha256':'e89e68e192965d8e012cc1213e59c02610f55042ad26d7392ebef0401237ee75'}
UNPERFORMED = {
    'fresh_OCCT_geometry_recomputation_by_this_program': None,
    'M4_03_revised_candidate_verification': None,
    'REQ-VEHICLE-CAD: complete_commercial_mount_compatibility': None,
    'REQ-VEHICLE-CAD: complete_installed_mass_and_momentum_interface': None,
    'REQ-LANDING-GEAR-ARRANGEMENT: continuous_full_envelope_clearance': None,
    'REQ-LANDING-CONTACT-CLEARANCE: dynamic_approach_and_settling': None,
    'complete_moving_harness_and_linkage_clearance': None,
    'commercial_hub_shaft_retention_compatibility': None,
    'physical_strength_contact_and_deformation_tests': None
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def close(a, b, absolute=1e-9, relative=1e-9):
    return (math.isfinite(float(a)) and math.isfinite(float(b))
            and abs(a-b) <= absolute + relative*max(abs(a),abs(b)))


def witness_key(w):
    p = w['pose']
    return (tuple(w['pair']), float(p['alpha_deg']), float(p['beta_deg']))


def matching_witnesses(actual, retained):
    a = {witness_key(w): w for w in actual}
    b = {witness_key(w): w for w in retained}
    return (len(a)==len(actual) and len(b)==len(retained) and a.keys()==b.keys()
            and all(close(a[k]['distance_mm'],b[k]['distance_mm'])
                    and close(a[k]['common_volume_mm3'],b[k]['common_volume_mm3'])
                    for k in a))


def result(checks, measurements, explanation, inconclusive=False):
    performed = [v for v in checks.values() if v is not None]
    if any(v is False for v in performed):
        outcome = 'failed'
    elif inconclusive:
        outcome = 'inconclusive'
    elif performed:
        outcome = 'passed'
    else:
        outcome = 'unperformed'
    return {'outcome':outcome, 'explanation':explanation,
            'checks':checks, 'measurements':measurements}


def run():
    checks = {}
    measurements = {}
    try:
        raw = {name:(ROOT/entry[0]).read_bytes() for name,entry in FILES.items()}
        checks['actual_artifact_file_digest_binding'] = all(
            digest(raw[name])==entry[1] for name,entry in FILES.items())
        if not checks['actual_artifact_file_digest_binding']:
            checks.update(UNPERFORMED)
            return result(checks, measurements,
                'Artifact digest mismatch. No retained geometry verdict was evaluated.')
        audit = json.loads(raw['audit'])
        report = json.loads(raw['report'])
        checks['retained_model_revision_binding'] = all(
            doc['authority']['system_model']==MODEL for doc in (audit,report))
        checks['audit_input_and_program_binding'] = (
            all(audit['input_files'][name]['path']==FILES[name][0]
                and audit['input_files'][name]['sha256']==FILES[name][1]
                for name in ('fcstd','step','report','kernel'))
            and audit['audit_source_sha256']==FILES['audit_program'][1])
        checks['generation_report_file_binding'] = (
            all(report['artifact_file_sha256'][name]==FILES[name][1]
                for name in ('fcstd','step','drawing'))
            and all(report['generation_source_sha256'][name]==FILES[name][1]
                    for name in ('kernel','builder')))
        tol = audit['computational_tolerances']
        # Reuse the declared diagnostic tolerances, not a new acceptance limit.
        checks['declared_diagnostic_tolerances_unchanged'] = (
            tol['contact_mm']==1e-7 and tol['intersection_volume_mm3']==1e-5
            and tol['volume_relative']==1e-5 and tol['volume_absolute_mm3']==1e-4)
        rows = {r['object_name']:r for r in report['rows']}
        inventory = {r['name']:r for r in audit['native_inventory']}
        checks['retained_native_inventory_identity_and_volume'] = (
            len(rows)==len(report['rows']) and len(inventory)==len(audit['native_inventory'])
            and rows.keys()==inventory.keys()
            and all(close(r['geometry']['volume_mm3'],inventory[n]['volume_mm3'],
                          absolute=1e-4,relative=1e-8) for n,r in rows.items()))
        checks['retained_native_solid_validity_observations'] = all(
            r['shape_valid'] and r['solid_count']>0
            and len(r['solids_valid'])==r['solid_count'] and all(r['solids_valid'])
            for r in inventory.values())
        physical = [n for n,r in rows.items() if r['role']!='nonmass_envelope']
        source_volume = sum(inventory[n]['volume_mm3'] for n in physical)
        expected_solids = sum(inventory[n]['solid_count'] for n in physical)
        step = audit['STEP']
        step_error = abs(step['imported_volume_mm3']-source_volume)
        checks['retained_STEP_count_and_volume_agreement'] = (
            step['solid_count']==expected_solids
            and close(step['native_registered_volume_mm3'],source_volume,absolute=1e-4)
            and step_error<=tol['volume_absolute_mm3']+tol['volume_relative']*source_volume)
        measurements['retained_STEP_volume_difference'] = {'value':step_error,'unit':'mm^3'}

        # Independently aggregate the retained component masses and centroidal
        # tensors. This checks arithmetic, not density/material qualification.
        known = [r for r in rows.values() if r['properties'] is not None]
        mass_ok = True
        for row in known:
            p = row['properties']
            if row['mass_override_kg'] is not None:
                expected_mass = row['mass_override_kg']
                mass_ok = mass_ok and row['density_kg_m3'] is None
            else:
                expected_mass = row['geometry']['volume_mm3']*row['density_kg_m3']*1e-9
            mass_ok = mass_ok and close(p['mass_kg'],expected_mass,absolute=1e-12)
        checks['retained_component_mass_arithmetic_no_override_addition'] = mass_ok
        m = sum(r['properties']['mass_kg'] for r in known)
        cg = [sum(r['properties']['mass_kg']*r['properties']['centroid_C_mm'][i]
                  for r in known)/m for i in range(3)]
        inertia = [[0.0]*3 for _ in range(3)]
        for row in known:
            p = row['properties']
            r = [(p['centroid_C_mm'][i]-cg[i])*0.001 for i in range(3)]
            r2 = sum(v*v for v in r)
            for i in range(3):
                for j in range(3):
                    inertia[i][j] += p['inertia_centroid_C_kg_m2'][i][j] + p['mass_kg']*(
                        (r2 if i==j else 0.0)-r[i]*r[j])
        total = report['accounted_partial_mass_properties']
        checks['retained_partial_mass_CG_full_inertia_aggregation'] = (
            close(m,total['mass_kg'],absolute=1e-12)
            and all(close(cg[i],total['centroid_C_mm'][i]) for i in range(3))
            and all(close(inertia[i][j],total['inertia_centroid_C_kg_m2'][i][j],
                          absolute=1e-12) for i in range(3) for j in range(3)))
        signs = (1,-1,-1)
        body = report['accounted_partial_body_properties']
        datum = report['datum_C_mm']
        checks['retained_CAD_mm_to_body_SI_conversion'] = (
            all(close(body['r_DG_B_m'][i],0.001*signs[i]*(cg[i]-datum[i]),absolute=1e-12)
                for i in range(3))
            and all(close(body['inertia_centroid_B_kg_m2'][i][j],
                          signs[i]*signs[j]*inertia[i][j],absolute=1e-12)
                    for i in range(3) for j in range(3)))
        checks['incomplete_mass_remains_explicit'] = (
            report['supported_complete_installed_mass_kg'] is None
            and bool(report['unresolved_rows'])
            and all(r['properties'] is None for r in rows.values()
                    if r['role']=='nonmass_envelope' or r['mass_class']=='unknown'))
        measurements['accounted_partial_mass_not_vehicle_mass'] = {'value':m,'unit':'kg'}

        poses = audit['gimbal_sample_poses']
        pose_set = {(p['alpha_deg'],p['beta_deg']) for p in poses}
        checks['retained_nine_pose_domain_identity'] = (
            len(poses)==9 and pose_set==set(itertools.product((-15.0,0.0,15.0),repeat=2)))
        expected_cross = sum(rows[a]['owner']!=rows[b]['owner']
                             for a,b in itertools.combinations(physical,2))
        meta = report['candidate_metadata']
        rotors = meta['rotor_object_names']
        wires = [n for n,r in rows.items() if r['role']=='nonmass_envelope' and n not in rotors]
        expected_rotor_evaluations = len(poses)*len(rotors)*(len(physical)-2+len(wires))
        checks['retained_declared_pair_coverage_counts'] = (
            audit['neutral_pair_count_considered']==len(physical)*(len(physical)-1)//2
            and audit['cross_group_pair_count_per_pose']==expected_cross
            and audit['rotor_external_pair_evaluations']==expected_rotor_evaluations)

        neutral_bad = [w for w in audit['neutral_AABB_near_pair_measurements']
                       if w['common_volume_mm3']>tol['intersection_volume_mm3']]
        cross_bad = [w for w in audit['sampled_cross_group_AABB_near_measurements']
                     if w['common_volume_mm3']>tol['intersection_volume_mm3']]
        checks['retained_overlap_witness_lists_match_measurements'] = (
            matching_witnesses(neutral_bad,audit['neutral_overlap_witnesses'])
            and matching_witnesses(cross_bad,audit['sampled_cross_group_overlap_witnesses']))
        checks['retained_neutral_installed_objects_no_volumetric_overlap'] = not neutral_bad
        checks['retained_sampled_cross_group_objects_no_volumetric_overlap'] = not cross_bad
        minima = audit['rotor_external_pair_sampled_minima']
        rotor_witnesses = audit['rotor_external_contact_or_overlap_witnesses']
        checks['retained_rotor_external_positive_sampled_separation'] = bool(minima) and all(
            w['distance_mm']>tol['contact_mm'] for w in minima)
        checks['retained_rotor_failure_witness_consistency'] = (
            all(w['distance_mm']<=tol['contact_mm'] for w in rotor_witnesses)
            and checks['retained_rotor_external_positive_sampled_separation']==(len(rotor_witnesses)==0))
        wire_witnesses = audit['wiring_reservation_overlap_witnesses']
        checks['retained_wiring_failure_witness_validity'] = all(
            w['common_volume_mm3']>tol['intersection_volume_mm3'] for w in wire_witnesses)
        # A retained positive-volume witness proves diagnostic failure. An empty
        # witness list alone would not prove complete wiring clearance.
        checks['retained_represented_wiring_no_observed_overlap'] = (
            False if wire_witnesses else None)
        measurements['retained_neutral_overlap_pair_count'] = {'value':len(neutral_bad),'unit':''}
        measurements['retained_rotor_contact_witness_count'] = {'value':len(rotor_witnesses),'unit':''}
        measurements['retained_wiring_overlap_witness_count'] = {'value':len(wire_witnesses),'unit':''}

        edits = audit['parameter_edit_observations']
        checks['retained_local_parameter_edit_measurements'] = bool(edits) and all(
            r['valid'] and close(r['new_z_extent_mm'],310,absolute=1e-7,relative=0)
            and close(r['new_volume_mm3']/r['old_volume_mm3'],310/300,
                      absolute=1e-10,relative=0) for r in edits)
        cells = audit['ground']['sensitivity_cell_minimum_witnesses']
        recomputed = [w['rotor_minimum_z_rotated_C_mm']-min(w['foot_minimum_z_rotated_C_mm'])
                      -w['separate_obstacle_plane_above_foot_ground_mm'] for w in cells]
        checks['retained_ground_witness_arithmetic'] = bool(cells) and all(
            close(value,w['clearance_to_obstacle_plane_mm'],absolute=1e-9)
            for value,w in zip(recomputed,cells))
        checks['retained_prescribed_foot_geometry_positive_sampled_ground_separation'] = (
            bool(recomputed) and min(recomputed)>tol['contact_mm'])
        measurements['retained_minimum_sampled_ground_clearance'] = {
            'value':min(recomputed),'unit':'mm'}
        checks['retained_continuous_and_physical_results_not_claimed'] = (
            audit['continuous_clearance'] is None and audit['physical_qualification'] is None)
        checks['tested_files_unchanged_during_check'] = all(
            digest((ROOT/entry[0]).read_bytes())==entry[1] for entry in FILES.values())
        checks.update(UNPERFORMED)
        failures = [k for k,v in checks.items() if v is False]
        print('Retained diagnostic failures: '+ '; '.join(failures),file=sys.stderr)
        return result(checks,measurements,
            'Digest-bound verification of retained M4-02 measurements and evidence-chain arithmetic. '
            'Failure verdicts are recomputed from collision witnesses, not copied from process status. '
            'No new OCCT solve was performed. Original candidate remains failed; no claim is made '
            'for revised M4-03 candidates. Nine sampled joint poses and prescribed foot geometry '
            'do not establish continuous clearance, dynamic landing, complete vehicle properties, '
            'commercial mounting compatibility, hardware qualification or review acceptance.')
    except Exception:
        traceback.print_exc(file=sys.stderr)
        checks.update(UNPERFORMED)
        return result(checks,measurements,
            'Evidence-chain checker could not complete; see stderr. No missing check is treated as passed.',
            inconclusive=True)


if __name__=='__main__':
    print(json.dumps(run(),allow_nan=False))
