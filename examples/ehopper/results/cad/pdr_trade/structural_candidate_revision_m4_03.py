"""Preserved candidate revision M4-03: generation and coarse diagnostics.

Run only through a saved-script freecad_run with all outputs declared.
The default main creates TWO unselected diagnostic candidates, not the full
48-case trade. build_candidate() retains all authorized spine/section/leg and
study-diameter alternatives for a later matrix runner.

Declare these nine outputs:
 cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_03.FCStd
 cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_03.step
 cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_03_arrangement.svg
 analysis/pdr_cad_trade/diagnostic_s2_c14_t_d330_m4_03.json
 cad/pdr_trade/diagnostic_s2_c14_q_d330_m4_03.FCStd
 cad/pdr_trade/diagnostic_s2_c14_q_d330_m4_03.step
 cad/pdr_trade/diagnostic_s2_c14_q_d330_m4_03_arrangement.svg
 analysis/pdr_cad_trade/diagnostic_s2_c14_q_d330_m4_03.json
 analysis/pdr_cad_trade/diagnostic_comparison_m4_03.json
The runtime captures its own execution log. Originals remain unchanged.

Evidence motivating changes: diagnostic_geometry_audit_m4_02.json, file digest
b02696dcde92f2d91754c5517a8a3f259781e7ee52abf0eb4afa6e1eccfa6b10.
Measured failures were upper rotor versus landing tubes, ESCShelf0 versus the
fixed actuator proxy, and CentralWiringAllowance versus battery/support/pad.
No old failure is reclassified as passing by this source revision.

Additional source-inspection finding: base beam_xy() replaced the Box placement
and consequently lost its intended local -width/2 offset. This revision centres
tray arms explicitly. Consequences require fresh measurement, not inference.
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import math
import hashlib
import itertools
import copy
from pathlib import Path
import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
SOURCE_FILES = {
    'kernel': ('cad/pdr_trade/structural_kernel_m4_01.py',
        '26269836fe1ced116669ce58f2295682162f65103e80da1ae1a95d20028e9c90'),
    'base_builder': ('cad/pdr_trade/structural_candidate_builder_m4_01.py',
        'a89e657da1cee7a31be68e116303bbb1d5f7d22eed9c61716f7ca41faa60711a'),
    'audit_helpers': ('cad/pdr_trade/diagnostic_geometry_audit_m4_02.py',
        '62250cbd093f319183d66d355b70e24b52a6c492ef31e18161f57de2ece3a07b')
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


for identity, (relative, expected) in SOURCE_FILES.items():
    if sha(ROOT / relative) != expected:
        raise ValueError('Inspected source changed: ' + identity)
sys.path.insert(0, str(ROOT / 'cad/pdr_trade'))
import structural_kernel_m4_01 as K
import structural_candidate_builder_m4_01 as B
import diagnostic_geometry_audit_m4_02 as A

LAYOUT = {
    'schema': 'hopper_cad_layout_revision/1',
    'revision': 'M4-03',
    'authority': K.AUTHORITY,
    'status': 'Unselected design hypotheses; not measured outcomes or acceptance',
    'units': 'mm unless specified',
    'leg_attachment_radius_mm': 150.0,
    'leg_attachment_z_mm': -2.0,
    'foot_sphere_centre_radius_mm': 440.0,
    'foot_sphere_centre_z_mm': -400.0,
    'foot_sphere_radius_mm': 10.0,
    'outrigger_inner_radius_mm': 90.0,
    'outrigger_end_extension_mm': 8.0,
    'outrigger_width_mm': 16.0,
    'outrigger_thickness_mm': 8.0,
    'outrigger_upper_z_mm': 0.0,
    'fixed_actuator_minimum_C_mm': [-90.0, -40.0, 4.0],
    'fixed_harness_radius_from_centre_mm': 72.0,
    'fixed_harness_envelope_radius_mm': 5.0,
    'fixed_harness_z_mm': [8.0, 200.0],
    'harness_azimuth_rule_deg': '180 / spine_count; halfway between adjacent spine rays',
    'origin_and_rotor_positions': 'Unchanged from inspected M4-01 generator',
    'design_change_rationale': [
        'Move leg sockets radially outward on explicit solid outriggers, rather than reducing the tested gimbal domain or excluding collided legs.',
        'Move the fixed actuator packaging proxy away from the witnessed ESC shelf overlap; commercial mounts remain unresolved.',
        'Replace the central annular wiring reservation by a full cylindrical routing reservation outside the battery, between spine rays.',
        'Centre tray arms about their intended rays after identifying a placement-offset error in the base helper.'
    ],
    'trade_penalties_to_measure': [
        'Outrigger mass, cantilever demand and local ring attachment loads',
        'Longer or differently inclined legs and whole-stock cutting consequences',
        'Mounting access, actuator linkage feasibility and remaining cable continuity'
    ],
    'unresolved': [
        'Outrigger dimensions and printed material are not strength-qualified.',
        'Fixed harness reservation is one disconnected packaging segment, not a complete electrical harness.',
        'No commercial mounting pattern, motor mass subdivision or propeller retention is supplied by this revision.',
        'The generic reference battery remains the 3S comparison proxy. A 279.4 mm geometry variant is not automatically a reconciled 4S vehicle.'
    ]
}


def configure_cylinder(obj, start, end):
    axis = end - start
    if axis.Length <= 0:
        raise ValueError('Nonpositive cylinder length')
    obj.Height = axis.Length
    obj.Placement = App.Placement(start, App.Rotation(App.Vector(0, 0, 1), axis))


def radial_beam(c, name, angle_deg, r0, r1, width, thickness, upper_z):
    if r1 <= r0:
        raise ValueError('Invalid outrigger interval')
    rotation = App.Rotation(App.Vector(0, 0, 1), angle_deg)
    start = B.polar(r0, angle_deg, upper_z - thickness)
    obj = c.box(name, [0, 0, 0], [r1-r0, width, thickness])
    obj.Placement = App.Placement(
        start + rotation.multVec(App.Vector(0, -width/2, 0)), rotation)
    return obj


def build_candidate(spine_count, section_id, leg_count, rotor_diameter_mm, label,
                    layout=None):
    settings = copy.deepcopy(LAYOUT if layout is None else layout)
    c = B.build_candidate(spine_count, section_id, leg_count, rotor_diameter_mm, label)
    c.metadata = copy.deepcopy(c.metadata)
    cfg = c.metadata['configuration']
    azimuths = [90, 210, 330] if leg_count == 3 else [45, 135, 225, 315]
    new_lengths, contacts, demand_coefficients = [], [], []
    raw_ring = c.doc.getObject('FixedLegAttachmentRaw')
    ring_members = list(raw_ring.Shapes)

    for i, angle in enumerate(azimuths):
        start = B.polar(settings['leg_attachment_radius_mm'], angle,
                        settings['leg_attachment_z_mm'])
        end = B.polar(settings['foot_sphere_centre_radius_mm'], angle,
                      settings['foot_sphere_centre_z_mm'])
        axis = end - start
        joint_length = axis.Length
        direction = axis * (1.0 / joint_length)
        endpoints = {
            'LegSocketOuter%d' % i: (start, start + direction*25),
            'LegSocketBore%d' % i: (start - direction*10, start + direction*26),
            'LandingTube%d_Outer' % i: (start + direction*2, end - direction*2),
            'LandingTube%d_Bore' % i: (start + direction*2, end - direction*2),
            'FootSocket%d' % i: (end - direction*25, end),
            'FootBore%d' % i: (end - direction*26, end - direction)
        }
        for name, (a, b) in endpoints.items():
            obj = c.doc.getObject(name)
            if obj is None:
                raise ValueError('Expected native object missing: ' + name)
            configure_cylinder(obj, a, b)
        ball = c.doc.getObject('FootBall%d' % i)
        ball.Placement.Base = end
        ball.Radius = settings['foot_sphere_radius_mm']
        ring_members.append(radial_beam(c, 'LegOutriggerM403_%d' % i, angle,
            settings['outrigger_inner_radius_mm'],
            settings['leg_attachment_radius_mm'] + settings['outrigger_end_extension_mm'],
            settings['outrigger_width_mm'], settings['outrigger_thickness_mm'],
            settings['outrigger_upper_z_mm']))
        new_lengths.append(joint_length - 4.0)
        contacts.append([end.x, end.y, end.z - ball.Radius.Value])
        # Unit vertical reaction at the sphere-bottom point, not a selected load.
        # Forces are in CAD axes; the coefficient has units m and multiplies N.
        foot_point = App.Vector(*contacts[-1])
        arm_m = (foot_point - start) * 0.001
        moment_per_N = arm_m.cross(App.Vector(0, 0, 1))
        axial_per_N = abs(direction.z)
        demand_coefficients.append({
            'leg': i, 'attachment_C_mm': K.xyz(start),
            'neutral_contact_proxy_C_mm': contacts[-1],
            'tube_direction_C': K.xyz(direction),
            'joint_spacing_mm': joint_length,
            'finished_tube_length_mm': joint_length - 4.0,
            'axial_force_magnitude_per_vertical_reaction_N': axial_per_N,
            'transverse_force_magnitude_per_vertical_reaction_N': math.sqrt(max(0, 1-axial_per_N**2)),
            'attachment_moment_C_Nm_per_vertical_reaction_N': K.xyz(moment_per_N),
            'scope': 'Static force-resolution coefficients only. Entire reaction may act at one foot; do not divide by leg count. No contact-force magnitude or joint strength is established.'
        })
    raw_ring.Shapes = ring_members

    centering_changes = []
    for obj in c.doc.Objects:
        if obj.Name.startswith(('BatterySupport_Arm', 'ElectronicsSupport_Arm')):
            original = K.xyz(obj.Placement.Base)
            shift = obj.Placement.Rotation.multVec(App.Vector(0, -obj.Width.Value/2, 0))
            placement = obj.Placement
            placement.Base = placement.Base + shift
            obj.Placement = placement
            centering_changes.append({'object': obj.Name,
                'old_base_C_mm': original, 'new_base_C_mm': K.xyz(obj.Placement.Base)})

    c.doc.getObject('ActuatorPackagingEnvelope0').Placement.Base = App.Vector(
        *settings['fixed_actuator_minimum_C_mm'])

    # Remove only from this new in-memory derivative document. The original
    # saved FCStd and source programs remain untouched. Full cylinder avoids
    # treating the centre of a cable-bundle reservation as empty space.
    c.rows = [r for r in c.rows if r['object_name'] != 'CentralWiringAllowance']
    for name in ('CentralWiringAllowance', 'CentralWiringAllowance_Outer',
                 'CentralWiringAllowance_Bore'):
        if c.doc.getObject(name) is not None:
            c.doc.removeObject(name)
    cable_angle = 180.0 / spine_count
    cable_start = B.polar(settings['fixed_harness_radius_from_centre_mm'], cable_angle,
                         settings['fixed_harness_z_mm'][0])
    cable_end = B.polar(settings['fixed_harness_radius_from_centre_mm'], cable_angle,
                       settings['fixed_harness_z_mm'][1])
    cable = c.cylinder('FixedHarnessRoutingReservationM403', K.xyz(cable_start),
        K.xyz(cable_end), settings['fixed_harness_envelope_radius_mm'])
    c.register(cable, 'nonmass_envelope', 'fixed_airframe', 'nonmass',
        provenance='Full cylindrical packaging reservation; not sourced wire dimensions or installed material',
        uncertainty='Endpoints, branching, moving loops, strain relief and bend radii remain unresolved',
        interface_status='One exploratory routing segment only')

    cfg.update({
        'leg_attachment_radius_mm': settings['leg_attachment_radius_mm'],
        'leg_attachment_z_mm': settings['leg_attachment_z_mm'],
        'foot_sphere_centre_radius_mm': settings['foot_sphere_centre_radius_mm'],
        'foot_sphere_centre_z_mm': settings['foot_sphere_centre_z_mm'],
        'foot_sphere_radius_mm': settings['foot_sphere_radius_mm'],
        'layout_revision': settings
    })
    c.metadata['neutral_foot_contact_proxies_C_mm'] = contacts
    c.metadata['stock_finished_lengths_mm']['landing_legs'] = new_lengths
    c.metadata['first_contact_unit_reaction_coefficients'] = demand_coefficients
    c.metadata['tray_arm_centering_changes'] = centering_changes
    c.metadata['fixed_harness_reservation'] = {
        'start_C_mm': K.xyz(cable_start), 'end_C_mm': K.xyz(cable_end),
        'radius_mm': settings['fixed_harness_envelope_radius_mm'],
        'complete_harness': False}
    c.metadata['revision_status'] = 'Geometry changes require new checks; original failed configuration remains retained'
    c.metadata['load_path'] += '; leg sockets now connect through explicit radial outriggers fused to the fixed ring'
    c.metadata['reference_battery_boundary'] = settings['unresolved'][-1]
    c.omissions.extend([
        'New radial outrigger cantilever, ring junction and printed-material strength unqualified',
        'Marked-forward physical registration detail remains to be implemented beyond the named datum/frame annotation',
        'Revised harness segment is not a complete connected installation'
    ])
    c.doc.recompute()
    visible = {r['object_name'] for r in c.rows if r['role'] != 'nonmass_envelope'}
    for obj in c.doc.Objects:
        if hasattr(obj, 'ViewObject') and obj.ViewObject is not None:
            obj.ViewObject.Visibility = obj.Name in visible
    return c


def coarse_reopened_diagnostics(doc, report):
    """Measure actual reopened native shapes; reuse inspected audit helpers.

    Not an independent verification program, not continuous clearance, and not
    a relaxation of the recorded failed diagnostic. All detected failures stay.
    """
    records = {r['object_name']: r for r in report['rows']}
    shapes = {n: doc.getObject(n).Shape.copy() for n in records}
    physical = [n for n, r in records.items() if r['role'] != 'nonmass_envelope']
    meta = report['candidate_metadata']
    cfg = meta['configuration']
    rotors = meta['rotor_object_names']
    props = meta['propeller_proxy_names']
    motors = meta['motor_envelope_names']
    wires = [n for n, r in records.items() if r['role'] == 'nonmass_envelope' and n not in rotors]
    neutral_overlaps, wire_overlaps, rotor_contacts = [], [], []
    neutral_near, mechanism_overlaps, own_hub = [], [], []
    minimum_by_pair = {}
    for a, b in itertools.combinations(physical, 2):
        if A.bbox_gap(shapes[a], shapes[b]) <= A.TOL['contact_mm']:
            measured = A.pair_measure(shapes[a], shapes[b], a, b,
                                      {'alpha_deg': 0, 'beta_deg': 0})
            neutral_near.append(measured)
            if measured['common_volume_mm3'] > A.TOL['intersection_volume_mm3']:
                neutral_overlaps.append(measured)
    for wire in wires:
        for name in physical:
            if A.bbox_gap(shapes[wire], shapes[name]) <= A.TOL['contact_mm']:
                measured = A.pair_measure(shapes[wire], shapes[name], wire, name,
                                          {'alpha_deg': 0, 'beta_deg': 0})
                if measured['common_volume_mm3'] > A.TOL['intersection_volume_mm3']:
                    wire_overlaps.append(measured)
    pairs = [(a, b) for a, b in itertools.combinations(physical, 2)
             if records[a]['owner'] != records[b]['owner']]
    for pose in A.POSES:
        current = {n: A.transform(s, records[n]['owner'], pose,
            cfg['outer_origin_C_mm'], cfg['outer_to_inner_C_neutral_mm'])
            for n, s in shapes.items()}
        for a, b in pairs:
            if A.bbox_gap(current[a], current[b]) <= A.TOL['contact_mm']:
                measured = A.pair_measure(current[a], current[b], a, b, pose)
                if measured['common_volume_mm3'] > A.TOL['intersection_volume_mm3']:
                    mechanism_overlaps.append(measured)
        for i, rotor in enumerate(rotors):
            for obstacle in [n for n in physical if n not in (props[i], motors[i])] + wires:
                measured = A.pair_measure(current[rotor], current[obstacle], rotor, obstacle, pose)
                key = rotor + ' / ' + obstacle
                if A.worse(measured, minimum_by_pair.get(key)):
                    minimum_by_pair[key] = measured
                if measured['distance_mm'] <= A.TOL['contact_mm']:
                    rotor_contacts.append(measured)
            own_hub.append(A.pair_measure(current[rotor], current[motors[i]],
                                          rotor, motors[i], pose))
        measured = A.pair_measure(current[rotors[0]], current[rotors[1]],
                                  rotors[0], rotors[1], pose)
        if A.worse(measured, minimum_by_pair.get('rotor / rotor')):
            minimum_by_pair['rotor / rotor'] = measured
        if measured['distance_mm'] <= A.TOL['contact_mm']:
            rotor_contacts.append(measured)
    return {
        'scope': 'Coarse diagnostics on reopened shapes, not independent acceptance evidence',
        'gimbal_sample_poses': A.POSES,
        'computational_tolerances': A.TOL,
        'neutral_installed_pair_count_considered': len(physical)*(len(physical)-1)//2,
        'neutral_near_pair_measurements': neutral_near,
        'neutral_overlap_witnesses': neutral_overlaps,
        'sampled_cross_group_overlap_witnesses': mechanism_overlaps,
        'wiring_reservation_overlap_witnesses': wire_overlaps,
        'rotor_pair_sampled_minima': list(minimum_by_pair.values()),
        'rotor_contact_or_overlap_witnesses': rotor_contacts,
        'own_motor_full_slab_interface_measurements': own_hub,
        'exclusion_policy': 'Own prop distribution and own motor are excluded only from external-obstacle scoring. Own motor slab occupancy is reported separately and remains unresolved. No installed-material overlap is waived.',
        'diagnostic_flags': {
            'neutral_no_volumetric_overlap': not neutral_overlaps,
            'sampled_cross_group_no_volumetric_overlap': not mechanism_overlaps,
            'represented_fixed_wiring_no_volumetric_overlap': not wire_overlaps,
            'sampled_rotor_external_positive_separation': not rotor_contacts
        },
        'continuous_clearance': None,
        'ground_and_deformed_leg_domain': None,
        'physical_qualification': None
    }


def paths_for(stem):
    return {
        'fcstd': 'cad/pdr_trade/' + stem + '.FCStd',
        'step': 'cad/pdr_trade/' + stem + '.step',
        'drawing': 'cad/pdr_trade/' + stem + '_arrangement.svg',
        'report': 'analysis/pdr_cad_trade/' + stem + '.json'
    }


def generate_one(leg_count, stem):
    files = paths_for(stem)
    c = build_candidate(2, 'C14', leg_count, 330.2, stem)
    report = c.export(ROOT, files['fcstd'], files['step'], files['report'])
    report['candidate_metadata'] = c.metadata
    cg = report['accounted_partial_mass_properties']['centroid_C_mm']
    contacts = c.metadata['neutral_foot_contact_proxies_C_mm']
    report['partial_CG_support_polygon'] = K.support_polygon([p[:2] for p in contacts], cg[:2])
    report['one_foot_removed_support'] = [K.support_polygon(
        [p[:2] for j, p in enumerate(contacts) if i != j], cg[:2]) for i in range(leg_count)]
    report['support_scope'] = 'Neutral point proxies and partial-mass centroid only; compliance and four-foot load sharing unresolved'
    stock = c.metadata['stock_finished_lengths_mm']
    report['spine_cutting_schedule'] = K.cutting_schedule(stock['spines'], 1000, 5, 3)
    report['leg_and_bypass_cutting_schedule'] = K.cutting_schedule(
        stock['landing_legs'] + stock['bypass_arms'], 1000, 5, 3)
    report['stock_scope'] = 'C14 spines and C08 leg/bypass hypotheses; nominal 1000 mm stock, 5 mm trim each end, 3 mm per-piece kerf. Feasible packing is not proven optimal. Exact variants, central suspension stock and other purchases remain unresolved.'
    B.arrangement_svg(c, ROOT/files['drawing'])
    App.closeDocument(c.doc.Name)
    doc = App.openDocument(str(ROOT/files['fcstd']))
    doc.recompute()
    report['reopened_coarse_diagnostics'] = coarse_reopened_diagnostics(doc, report)
    native = []
    for row in report['rows']:
        shape = doc.getObject(row['object_name']).Shape
        native.append({'name': row['object_name'], 'role': row['role'],
            'valid': bool(shape.isValid()), 'solid_count': len(shape.Solids),
            'individual_solids_valid': [bool(s.isValid()) for s in shape.Solids],
            'volume_mm3': sum(float(s.Volume) for s in shape.Solids)})
    step = Part.read(str(ROOT/files['step']))
    report['reopen_observations'] = {
        'native_objects': native, 'STEP_valid': bool(step.isValid()),
        'STEP_solid_count': len(step.Solids),
        'STEP_individual_solids_valid': [bool(s.isValid()) for s in step.Solids],
        'STEP_volume_mm3': sum(float(s.Volume) for s in step.Solids),
        'native_registered_volume_mm3': sum(r['volume_mm3'] for r in native if r['role'] != 'nonmass_envelope')
    }
    old_volume = float(doc.getObject('Spine0').Shape.Volume)
    doc.getObject('Parameters').set('B1', '310 mm')
    doc.recompute()
    edited = doc.getObject('Spine0').Shape
    report['local_parameter_edit_observations'] = {
        'parameter': 'SpineLength', 'old_mm': 300, 'edited_mm': 310,
        'old_volume_mm3': old_volume, 'edited_volume_mm3': float(edited.Volume),
        'edited_z_extent_mm': float(edited.BoundBox.ZLength),
        'edited_valid': bool(edited.isValid()),
        'scope': 'Native tube parameter only; assembly-wide regeneration uses the saved builder parameters. Candidate file is not overwritten.'
    }
    doc.getObject('Parameters').set('B1', '300 mm')
    doc.recompute()
    App.closeDocument(doc.Name)
    report['artifact_file_sha256'] = {k: sha(ROOT/files[k]) for k in ('fcstd', 'step', 'drawing')}
    report['generation_source_sha256'] = {k: sha(ROOT/v[0]) for k, v in SOURCE_FILES.items()}
    report['generation_source_sha256']['revision_generator'] = sha(ROOT/'cad/pdr_trade/structural_candidate_revision_m4_03.py')
    report['unperformed_checks'] = [
        'Full 48-case structural comparison and integrated-module branch',
        'Independent artifact-bound verification through verify_command',
        'Revised geometry ground clearance under body attitude, compression and terrain domains',
        'Continuous articulated clearance and qualified deformation/tolerance allowances',
        'Complete connected moving harness, linkages and retention',
        'Complete installed mass, momentum ownership and purchase reconciliation',
        'Commercial mounting compatibility and physical structural/contact tests',
        'GUI view pixel inspection'
    ]
    (ROOT/files['report']).write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return {'candidate_id': stem, 'files': files,
        'file_sha256': {k: sha(ROOT/v) for k, v in files.items()},
        'accounted_partial_mass_properties': report['accounted_partial_mass_properties'],
        'supported_complete_installed_mass_kg': None,
        'partial_CG_support_polygon': report['partial_CG_support_polygon'],
        'diagnostic_flags': report['reopened_coarse_diagnostics']['diagnostic_flags'],
        'selection': None}


def main():
    cases = [(3, 'diagnostic_s2_c14_t_d330_m4_03'),
             (4, 'diagnostic_s2_c14_q_d330_m4_03')]
    index_path = ROOT/'analysis/pdr_cad_trade/diagnostic_comparison_m4_03.json'
    destinations = [ROOT/rel for _, stem in cases for rel in paths_for(stem).values()] + [index_path]
    for path in destinations:
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError('Output outside sandbox')
        if path.exists():
            raise FileExistsError('Preserve prior output: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
    results = [generate_one(count, stem) for count, stem in cases]
    index = {'schema': 'hopper_cad_diagnostic_comparison/1', 'authority': K.AUTHORITY,
        'layout_hypothesis': LAYOUT, 'candidates': results,
        'scope': 'Two revised actual-solid diagnostics only. Neither configuration is selected. Failures remain in each report.',
        'full_trade_complete': False, 'physical_qualification': None,
        'source_files_preserved': all(sha(ROOT/v[0]) == v[1] for v in SOURCE_FILES.values())}
    index_path.write_text(json.dumps(index, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'outputs': [str(p.relative_to(ROOT)) for p in destinations],
        'candidate_diagnostics': [{k: r[k] for k in ('candidate_id', 'diagnostic_flags')} for r in results],
        'scope': index['scope']}, allow_nan=False))


if __name__ == '__main__':
    main()
