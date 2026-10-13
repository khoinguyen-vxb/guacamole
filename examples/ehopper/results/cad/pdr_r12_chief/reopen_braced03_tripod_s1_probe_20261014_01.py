'''Independent, read-only inspection of one published revision-03 CAD candidate.

Run through freecad_run(headless=True). Declare this generated output:
  cad/pdr_r12_chief/reopen_braced03_tripod_s1_measurements_20261014_01.json

Include this source and BOTH tested native/STEP artifact Refs in execution
inputs. No generator module is imported. Original CAD is never saved/exported.
The parameter perturbation is in memory only. This program records geometric
observations, not a VerificationResult. Subsequently publish the measurements
and retain an artifact-bound checker executed through verify_command.

Scope: nominal separate tube components, not complete or manufactured vehicle.
Interpenetrating members are reported, not interpreted as accepted joints.
Reference rotor/yoke envelopes contribute no mass. Density is an assumption.
The 25 poses are neutral and a 15-degree resultant-cone boundary sampled every
15 degrees of azimuth. They are exploratory hypotheses, not selected travel,
continuous swept-volume certification or physical acceptance criteria.
'''

import hashlib
import itertools
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
SOURCE = ROOT / 'cad/pdr_r12_chief/reopen_braced03_tripod_s1_probe_20261014_01.py'
BASE = ROOT / 'cad/pdr_r12_chief/braced_candidates_03'
NATIVE = BASE / 'G_INTERMEDIATE_D279_TRIPOD_S1.FCStd'
STEP = BASE / 'G_INTERMEDIATE_D279_TRIPOD_S1_tubes.step'
OUTPUT = ROOT / 'cad/pdr_r12_chief/reopen_braced03_tripod_s1_measurements_20261014_01.json'
EXPECTED_HASHES = {
    NATIVE: '346ee2ffacfd6c75dc09a9fe23942b6bad059b8baf922a11f1b9f3746883f23a',
    STEP: '210f8ab1107b9551f464d1cbd164386eb7e8fc2b57cc490459460c9f615c87dd',
}
DENSITY_KG_M3 = 1600.0
# Numerical inspection thresholds only, not physical clearance requirements.
PLACEMENT_COMPARISON_MM = 1e-8
CONTACT_DISTANCE_MM = 1e-7
REPORTED_OVERLAP_THRESHOLD_MM3 = 1e-7


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': digest(path)}


def xyz(point):
    result = [float(point.x), float(point.y), float(point.z)]
    if not all(math.isfinite(x) for x in result):
        raise ValueError('Nonfinite geometry coordinate')
    return result


def matrix3(matrix):
    return [[float(getattr(matrix, 'A%d%d' % (i+1, j+1)))
             for j in range(3)] for i in range(3)]


def bound(shape):
    box = shape.BoundBox
    return [[float(getattr(box, axis+'Min')), float(getattr(box, axis+'Max'))]
            for axis in ('X', 'Y', 'Z')]


def world_shape(obj):
    # Independently establish the leaf-placement premise before replacing its
    # placement with global placement. Do not blindly double-transform Shape.
    shape = obj.Shape.copy()
    if shape.isNull():
        raise ValueError('Null shape: '+obj.Name)
    points = [App.Vector(0, 0, 0), App.Vector(1, 0, 0),
              App.Vector(0, 1, 0), App.Vector(0, 0, 1)]
    error = max((shape.Placement.multVec(p)-obj.Placement.multVec(p)).Length
                for p in points)
    if error > PLACEMENT_COMPARISON_MM:
        raise ValueError('Unsupported leaf/shape placement relationship: '+obj.Name)
    shape.Placement = obj.getGlobalPlacement()
    return shape


def solid_record(solid, label):
    volume = float(solid.Volume)
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError('Unusable solid volume: '+label)
    geometric = matrix3(solid.MatrixOfInertia)
    if not all(math.isfinite(x) for row in geometric for x in row):
        raise ValueError('Nonfinite solid inertia: '+label)
    return {
        'label': label, 'valid': bool(solid.isValid()),
        'volume_mm3': volume, 'cg_CAD_mm': xyz(solid.CenterOfMass),
        'bounding_box_CAD_mm': bound(solid),
        'geometric_inertia_reported_mm5': geometric,
        'mass_at_assumed_density_kg': volume*DENSITY_KG_M3*1e-9,
        'I_about_CG_CAD_kg_m2': [[x*DENSITY_KG_M3*1e-15 for x in row]
                                for row in geometric],
    }


def shape_records(shape, label):
    solids = list(shape.Solids)
    if not solids:
        raise ValueError('No solids: '+label)
    return [solid_record(s, label+'/solid_%d' % (i+1))
            for i, s in enumerate(solids)]


def aggregate(rows):
    mass = sum(r['mass_at_assumed_density_kg'] for r in rows)
    cg = [sum(r['mass_at_assumed_density_kg']*r['cg_CAD_mm'][i]
              for r in rows)/mass for i in range(3)]
    inertia = [[0.0]*3 for _ in range(3)]
    for row in rows:
        d = [(row['cg_CAD_mm'][i]-cg[i])*1e-3 for i in range(3)]
        d2 = sum(x*x for x in d)
        for i in range(3):
            for j in range(3):
                inertia[i][j] += row['I_about_CG_CAD_kg_m2'][i][j]
                inertia[i][j] += row['mass_at_assumed_density_kg']*((d2 if i == j else 0)-d[i]*d[j])
    return {'member_sum_mass_kg': mass, 'partial_CG_CAD_mm': cg,
            'I_about_partial_CG_CAD_kg_m2': inertia,
            'scope': 'Separate nominal tube solid sum; overlapping members are not union-corrected or accepted manufactured joints.'}


def rotate_x(point, angle):
    x, y, z = point
    c, s = math.cos(angle), math.sin(angle)
    return [x, c*y-s*z, s*y+c*z]


def rotate_minus_y(point, angle):
    x, y, z = point
    c, s = math.cos(angle), math.sin(angle)
    return [c*x-s*z, y, s*x+c*z]


def pose_list():
    result = [(0.0, 0.0)]
    theta = math.radians(15.0)
    for az_deg in range(0, 360, 15):
        az = math.radians(az_deg)
        alpha = math.asin(math.sin(theta)*math.cos(az))
        beta = math.atan2(math.sin(theta)*math.sin(az), math.cos(theta))
        result.append((math.degrees(alpha), math.degrees(beta)))
    return result


def set_pose(doc, outer, inner, origin, offset, alpha, beta):
    outer.Placement = App.Placement(origin, App.Rotation(App.Vector(1, 0, 0), alpha))
    inner.Placement = App.Placement(offset, App.Rotation(App.Vector(0, -1, 0), beta))
    doc.recompute()


def box_inertia_fixture():
    # Analytic, translated/rotated box checks centroid and tensor conventions.
    box = Part.makeBox(10, 20, 30)
    rotation = App.Rotation(App.Vector(1, 2, 3), 31)
    placement = App.Placement(App.Vector(12, -7, 19), rotation)
    box.Placement = placement
    r = matrix3(rotation.toMatrix())
    diag = [6000*(20**2+30**2)/12,
            6000*(10**2+30**2)/12,
            6000*(10**2+20**2)/12]
    expected = [[sum(r[i][k]*diag[k]*r[j][k] for k in range(3))
                 for j in range(3)] for i in range(3)]
    return {'observed': shape_records(box, 'analytic_box'),
            'expected_volume_mm3': 6000.0,
            'expected_CG_CAD_mm': xyz(placement.multVec(App.Vector(5, 10, 15))),
            'expected_geometric_inertia_about_CG_mm5': expected,
            'scope': 'Numerical convention fixture, not vehicle structural validation.'}


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve previous output: '+str(OUTPUT))
    for path, expected in EXPECTED_HASHES.items():
        if digest(path) != expected:
            raise ValueError('Published input identity mismatch: '+str(path))
    before = [identity(NATIVE), identity(STEP)]
    report = {
        'schema': 'hopper_independent_reopened_cad_observations/1',
        'generated_at_UTC': datetime.now(timezone.utc).isoformat(),
        'source': identity(SOURCE), 'inputs_before': before,
        'FreeCAD_version': [str(x) for x in App.Version()],
        'candidate_id': 'G_INTERMEDIATE_D279_TRIPOD_S1',
        'density_assumption_kg_m3': DENSITY_KG_M3,
        'units': {'length': 'mm', 'volume': 'mm^3', 'mass': 'kg',
                  'geometric_inertia': 'mm^5', 'mass_inertia': 'kg m^2', 'angle': 'deg'},
        'frame': {'CAD_axes': '+X forward, +Y left, +Z up',
                  'R_BC': [[1,0,0],[0,-1,0],[0,0,-1]],
                  'CAD_rotation': 'Rx(alpha)Ry(-beta)',
                  'point_transform': 'O + Rx(alpha)*(d + Ry(-beta)*p_inner)',
                  'complete_vehicle_neutral_CG': None},
        'numeric_reporting_thresholds': {
            'leaf_placement_comparison_mm': PLACEMENT_COMPARISON_MM,
            'contact_distance_mm': CONTACT_DISTANCE_MM,
            'reported_overlap_mm3': REPORTED_OVERLAP_THRESHOLD_MM3,
            'physical_acceptance_threshold': None},
        'box_inertia_fixture': box_inertia_fixture(),
    }
    doc = App.openDocument(str(NATIVE))
    try:
        doc.recompute()
        group = doc.getObject('NominalTubeComponents')
        if group is None:
            raise ValueError('Missing physical component group')
        objects = list(group.Group)
        expected_names = {'Spine_01'}
        for i in range(1, 4):
            expected_names.add('MainLeg_%02d' % i)
            expected_names.update('Brace_%02d_%s' % (i, suffix)
                                  for suffix in ('Plus', 'Minus'))
        if {o.Name for o in objects} != expected_names or len(objects) != 10:
            raise ValueError('Physical component inventory differs from inspected candidate')
        physical = [(o.Name, world_shape(o)) for o in objects]
        native_rows = [row for name, shape in physical for row in shape_records(shape, name)]
        report['native_component_inventory'] = [
            {'name': o.Name, 'role': str(o.MemberRole),
             'shape_valid': bool(world_shape(o).isValid()),
             'solid_count': len(world_shape(o).Solids)} for o in objects]
        report['native_solids'] = native_rows
        report['native_nominal_tube_sum'] = aggregate(native_rows)
        step_shape = Part.read(str(STEP))
        step_rows = shape_records(step_shape, 'STEP_unmapped_solid')
        report['step_shape_valid'] = bool(step_shape.isValid())
        report['step_solids'] = step_rows
        report['step_uniform_density_comparison_sum'] = aggregate(step_rows)
        report['step_mass_scope'] = 'Uniform-density comparison of the tube-only export; STEP itself supplies no material assignment. Solid order is not a component mapping.'
        report['tube_intersections'] = []
        for (na, a), (nb, b) in itertools.combinations(physical, 2):
            volume = float(a.common(b).Volume)
            if volume > REPORTED_OVERLAP_THRESHOLD_MM3:
                report['tube_intersections'].append({'a': na, 'b': nb, 'common_volume_mm3': volume})
        outer = doc.getObject('OuterJointReference')
        inner = doc.getObject('InnerJointReference')
        origin, offset = outer.Placement.Base, inner.Placement.Base
        report['observed_neutral_joint_origins'] = {
            'outer_CAD_mm': xyz(origin), 'outer_to_inner_local_mm': xyz(offset)}
        report['expected_generator_hypothesis_joint_origins'] = {
            'outer_CAD_mm': [0,0,340], 'outer_to_inner_local_mm': [0,0,-20]}
        moving = [doc.getObject(name) for name in ('upper_rotor', 'lower_rotor')]
        moving += [doc.getObject('YokeEnvelope_%02d' % i) for i in range(1,5)]
        moving += [doc.getObject('YokeEndEnvelope_%02d' % i) for i in range(1,5)]
        if any(o is None for o in moving):
            raise ValueError('Missing moving reference envelope')
        report['neutral_rotor_centers_CAD_mm'] = {
            o.Name: xyz(world_shape(o).Solids[0].CenterOfMass) for o in moving[:2]}
        minima, overlaps, kinematics = {}, [], []
        samples = pose_list()
        for alpha, beta in samples:
            set_pose(doc, outer, inner, origin, offset, alpha, beta)
            pose_error = 0.0
            for obj in moving:
                shape = world_shape(obj)
                local_center = xyz(obj.Shape.Solids[0].CenterOfMass)
                rotated = rotate_minus_y(local_center, math.radians(beta))
                shifted = [xyz(offset)[i]+rotated[i] for i in range(3)]
                expected_center = rotate_x(shifted, math.radians(alpha))
                expected_center = [xyz(origin)[i]+expected_center[i] for i in range(3)]
                observed_center = xyz(shape.Solids[0].CenterOfMass)
                pose_error = max(pose_error, max(abs(observed_center[i]-expected_center[i]) for i in range(3)))
                category = obj.Name if obj.Name in ('upper_rotor','lower_rotor') else 'yoke_primitive_envelopes'
                for name, fixed_shape in physical:
                    distance = float(shape.distToShape(fixed_shape)[0])
                    row = {'moving': obj.Name, 'fixed': name,
                           'alpha_deg': alpha, 'beta_deg': beta,
                           'distance_mm': distance}
                    if category not in minima or distance < minima[category]['distance_mm']:
                        minima[category] = dict(row)
                    if distance <= CONTACT_DISTANCE_MM:
                        volume = float(shape.common(fixed_shape).Volume)
                        if volume > REPORTED_OVERLAP_THRESHOLD_MM3:
                            row['common_volume_mm3'] = volume
                            overlaps.append(row)
            kinematics.append({'alpha_deg': alpha, 'beta_deg': beta,
                               'maximum_center_transform_difference_mm': pose_error})
        report['sampled_clearance'] = {
            'joint_poses_alpha_beta_deg': samples,
            'minima_to_physical_tubes': minima,
            'positive_common_volume_witnesses': overlaps,
            'kinematics_observations': kinematics,
            'scope': 'Native reference primitives versus actual native tubes at 25 poses. Primitive overlap volumes must not be summed as a unique compound volume.',
            'continuous_clearance': None, 'loaded_clearance': None,
            'joint_envelope_clearance': None, 'ground_clearance': None}
        set_pose(doc, outer, inner, origin, offset, 0.0, 0.0)
        sheet = doc.getObject('Parameters')
        target = doc.getObject('MainLeg_01')
        cylinder = doc.getObject('MainLeg_01_Outer')
        radius_before = float(cylinder.Radius)
        length = float(cylinder.Height)
        volume_before = float(world_shape(target).Volume)
        try:
            sheet.set('B1', '4.04 mm')
            doc.recompute()
            radius_after = float(cylinder.Radius)
            volume_after = float(world_shape(target).Volume)
        finally:
            sheet.set('B1', '%.17g mm' % radius_before)
            doc.recompute()
        report['unsaved_parameter_edit'] = {
            'cell': 'Parameters.B1', 'target': target.Name,
            'radius_before_mm': radius_before, 'radius_after_mm': radius_after,
            'radius_restored_mm': float(cylinder.Radius), 'length_mm': length,
            'volume_before_mm3': volume_before, 'volume_after_mm3': volume_after,
            'volume_restored_mm3': float(world_shape(target).Volume),
            'analytical_delta_volume_mm3': math.pi*(radius_after**2-radius_before**2)*length,
            'source_document_saved': False}
    finally:
        App.closeDocument(doc.Name)
    report['inputs_after'] = [identity(NATIVE), identity(STEP)]
    report['input_bytes_unchanged'] = report['inputs_after'] == before
    report['unperformed_acceptance'] = {
        'complete_vehicle_mass_CG_inertia': None, 'manufactured_joints': None,
        'mounting_interfaces': None, 'continuous_loaded_clearance': None,
        'structural_qualification': None, 'physical_validation': None,
        'PDR_CDR_acceptance': None}
    report['evidence_boundary'] = 'Fresh reopened-artifact observations only. No geometry or physical acceptance is inferred from process completion. A separate retained verifier must evaluate actual inputs and these observations.'
    with OUTPUT.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': identity(OUTPUT),
                      'status': 'observations recorded; acceptance not assessed'}))


if __name__ == '__main__':
    main()
