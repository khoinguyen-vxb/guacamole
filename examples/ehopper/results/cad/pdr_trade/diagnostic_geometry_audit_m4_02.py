"""Artifact-bound diagnostic audit M4-02; preserves the original assembly.

Run this saved script through headless freecad_run. Declare this output:
  analysis/pdr_cad_trade/diagnostic_geometry_audit_m4_02.json
The tool captures its own execution log. No CAD file is modified or exported.
Python stdout contains one VerificationResult-shaped object; FreeCAD may emit
additional native diagnostics in the tool log. Registration through
verify_command remains a separate runtime step, not inferred from execution.

This is a coarse diagnostic of ONE unselected candidate, not the complete
structural trade, continuous clearance, mounting approval or physical testing.
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import math
import hashlib
import itertools
from pathlib import Path
import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
sys.path.insert(0, str(ROOT/'cad/pdr_trade'))
import structural_kernel_m4_01 as K

STEM = 'diagnostic_s2_c14_t_d330_m4_01'
OUTPUT = ROOT/'analysis/pdr_cad_trade/diagnostic_geometry_audit_m4_02.json'
INPUTS = {
    'fcstd':('cad/pdr_trade/'+STEM+'.FCStd', '45dbd41ccba904f73bcec91d50cc8af0677ea426baadfbfa8ffe865fa9404b3e'),
    'step':('cad/pdr_trade/'+STEM+'.step', '67356901777acf1a7a8853314fa4af95b4c043b5ed087f693158f247573571d2'),
    'report':('analysis/pdr_cad_trade/'+STEM+'.json', 'e855cbe95009582ee9206cac22eeb153a7a649682608093c55295180bc7780fb'),
    'kernel':('cad/pdr_trade/structural_kernel_m4_01.py', '26269836fe1ced116669ce58f2295682162f65103e80da1ae1a95d20028e9c90')
}
# Computational diagnostics only, not fabrication tolerances or project limits.
TOL = {'contact_mm':1e-7, 'intersection_volume_mm3':1e-5,
       'volume_relative':1e-5, 'volume_absolute_mm3':1e-4,
       'fixture_position_mm':1e-7, 'fixture_inertia_kg_m2':1e-12,
       'parameter_length_mm':1e-7}
POSES = [{'alpha_deg':a,'beta_deg':b} for a in (-15.0,0.0,15.0)
         for b in (-15.0,0.0,15.0)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xyz(v):
    return [float(v.x),float(v.y),float(v.z)]


def add(a,b):
    return [a[i]+b[i] for i in range(3)]


def sub(a,b):
    return [a[i]-b[i] for i in range(3)]


def rx(p,a):
    c,s = math.cos(a),math.sin(a)
    return [p[0],c*p[1]-s*p[2],s*p[1]+c*p[2]]


def ry(p,b):
    c,s = math.cos(b),math.sin(b)
    return [c*p[0]+s*p[2],p[1],-s*p[0]+c*p[2]]


def expected_point(p,owner,a,b,outer,offset):
    # Independent trigonometric reference in CAD FLU coordinates.
    a,b = math.radians(a),math.radians(b)
    if owner=='fixed_airframe':
        return list(p)
    if owner=='outer_gimbal':
        return add(outer,rx(sub(p,outer),a))
    return add(add(outer,rx(offset,a)),rx(ry(sub(p,add(outer,offset)),-b),a))


def transform(shape,owner,pose,outer,offset):
    # Build a placement independently from the kernel's translation expression.
    if owner=='fixed_airframe':
        return shape.copy()
    a,b = pose['alpha_deg'],pose['beta_deg']
    r = App.Rotation(App.Vector(1,0,0),a)
    if owner!='outer_gimbal':
        r = r.multiply(App.Rotation(App.Vector(0,1,0),-b))
    translated_origin = expected_point([0,0,0],owner,a,b,outer,offset)
    result = shape.copy()
    result.Placement = App.Placement(App.Vector(*translated_origin),r).multiply(result.Placement)
    return result


def bounds(shape):
    b = shape.BoundBox
    return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]


def bbox_gap(a,b):
    x,y = bounds(a),bounds(b)
    return math.sqrt(sum(max(0.0,x[i]-y[i+3],y[i]-x[i+3])**2 for i in range(3)))


def pair_measure(a,b,na,nb,pose):
    distance,pairs,info = a.distToShape(b)
    volume = 0.0
    common_valid = None
    if distance <= TOL['contact_mm']:
        common = a.common(b)
        volume = sum(float(s.Volume) for s in common.Solids)
        common_valid = bool(common.isValid())
    return {'pair':[na,nb],'pose':dict(pose),'distance_mm':float(distance),
        'common_volume_mm3':volume,'common_valid_when_computed':common_valid,
        'nearest_points_C_mm':[[xyz(p),xyz(q)] for p,q in pairs],
        'distance_support_information':repr(info)}


def worse(new,old):
    if old is None:
        return True
    if new['distance_mm'] < old['distance_mm']-TOL['contact_mm']:
        return True
    return (abs(new['distance_mm']-old['distance_mm']) <= TOL['contact_mm']
            and new['common_volume_mm3'] > old['common_volume_mm3'])


def matrix_values(m):
    return [[float(getattr(m,'A%d%d'%(i+1,j+1))) for j in range(3)] for i in range(3)]


def fixture_tests():
    checks,observations = {},{}
    size = [10.0,20.0,30.0]
    centre = [20.0,-35.0,50.0]
    rotation = App.Rotation(App.Vector(1,2,3),37)
    box = Part.makeBox(*size,App.Vector(-5,-10,-15))
    box.Placement = App.Placement(App.Vector(*centre),rotation)
    measured = K.geometry_properties(box,density_kg_m3=2000)
    mass = 2000*10*20*30*1e-9
    principal = [mass*(size[1]**2+size[2]**2)*1e-6/12,
                 mass*(size[0]**2+size[2]**2)*1e-6/12,
                 mass*(size[0]**2+size[1]**2)*1e-6/12]
    R = matrix_values(rotation.toMatrix())
    expected_I = [[sum(R[i][k]*principal[k]*R[j][k] for k in range(3))
                   for j in range(3)] for i in range(3)]
    cg_error = max(abs(measured['centroid_C_mm'][i]-centre[i]) for i in range(3))
    inertia_error = max(abs(measured['inertia_centroid_C_kg_m2'][i][j]-expected_I[i][j])
                        for i in range(3) for j in range(3))
    checks['synthetic_rotated_box_mass_centroid_full_inertia'] = (
        abs(measured['mass_kg']-mass)<1e-12 and cg_error<TOL['fixture_position_mm']
        and inertia_error<TOL['fixture_inertia_kg_m2'])
    body = K.to_body(measured,[3,4,5])
    expected_cg = [0.001*(1,-1,-1)[i]*(centre[i]-[3,4,5][i]) for i in range(3)]
    body_I_error = max(abs(body['inertia_centroid_B_kg_m2'][i][j]
        -(1,-1,-1)[i]*(1,-1,-1)[j]*expected_I[i][j]) for i in range(3) for j in range(3))
    checks['synthetic_CAD_to_body_point_and_centroidal_tensor'] = (
        max(abs(body['r_DG_B_m'][i]-expected_cg[i]) for i in range(3))<1e-10
        and body_I_error<TOL['fixture_inertia_kg_m2'])
    override = K.geometry_properties(box,override_mass_kg=0.075)
    checks['commercial_mass_override_replaces_density_mass'] = abs(override['mass_kg']-0.075)<1e-12
    observations['box'] = {'measured':measured,'expected_mass_kg':mass,
        'expected_centroid_C_mm':centre,'expected_inertia_C_kg_m2':expected_I,
        'centroid_error_mm':cg_error,'maximum_inertia_error_kg_m2':inertia_error}
    outer,offset,p = [7,-3,-41],[4,-6,-17],[31,29,-123]
    errors = []
    for owner in K.GROUPS:
        target = expected_point(p,owner,17,-23,outer,offset)
        result = K.articulated_shape(Part.Vertex(App.Vector(*p)),owner,17,-23,outer,offset)
        actual = xyz(result.Vertexes[0].Point)
        errors.append({'owner':owner,'expected_C_mm':target,'actual_C_mm':actual,
            'maximum_error_mm':max(abs(actual[i]-target[i]) for i in range(3))})
    checks['synthetic_noncommuting_separated_origin_kinematics'] = all(
        r['maximum_error_mm']<TOL['fixture_position_mm'] for r in errors)
    observations['separated_origin_fixture'] = errors
    return checks,observations


def cylindrical_faces(shape):
    out = []
    for i,face in enumerate(shape.Faces):
        surface = face.Surface
        if type(surface).__name__=='Cylinder':
            out.append({'face_index':i,'radius_mm':float(surface.Radius),
                'axis_C':xyz(surface.Axis),'axis_location_C_mm':xyz(surface.Center),
                'face_area_mm2':float(face.Area)})
    return out


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve previous output: '+str(OUTPUT))
    before = {key:sha(ROOT/entry[0]) for key,entry in INPUTS.items()}
    if any(before[key]!=entry[1] for key,entry in INPUTS.items()):
        raise ValueError('Input digest mismatch; do not audit changed artifacts as this revision')
    report = json.loads((ROOT/INPUTS['report'][0]).read_text(encoding='utf-8'))
    doc = App.openDocument(str(ROOT/INPUTS['fcstd'][0]))
    doc.recompute()
    records = report['rows']
    if len({r['object_name'] for r in records})!=len(records):
        raise ValueError('Duplicate accounting identity')
    rows = {r['object_name']:r for r in records}
    shapes = {}
    inventory = []
    metadata_matches = True
    for name,row in rows.items():
        obj = doc.getObject(name)
        if obj is None:
            raise ValueError('Missing registered object '+name)
        shape = obj.Shape.copy()
        shapes[name] = shape
        metadata_matches = metadata_matches and (
            obj.OwnershipGroup==row['owner'] and obj.GeometryRole==row['role'])
        inventory.append({'name':name,'shape_valid':bool(shape.isValid()),
            'solid_count':len(shape.Solids),
            'solids_valid':[bool(s.isValid()) for s in shape.Solids],
            'volume_mm3':sum(float(s.Volume) for s in shape.Solids),
            'bounds_C_mm':bounds(shape)})
    physical = [n for n,r in rows.items() if r['role']!='nonmass_envelope']
    meta = report['candidate_metadata']
    cfg = meta['configuration']
    outer,offset = cfg['outer_origin_C_mm'],cfg['outer_to_inner_C_neutral_mm']
    rotors = meta['rotor_object_names']
    props = meta['propeller_proxy_names']
    motors = meta['motor_envelope_names']
    wiring = [n for n,r in rows.items() if r['role']=='nonmass_envelope' and n not in rotors]
    checks,fixtures = fixture_tests()
    checks['input_file_digests_match'] = True
    checks['ownership_and_role_match_saved_manifest'] = bool(metadata_matches)
    checks['registered_native_objects_are_valid_solids'] = all(
        r['shape_valid'] and r['solid_count']>0 and all(r['solids_valid']) for r in inventory)

    step = Part.read(str(ROOT/INPUTS['step'][0]))
    source_volume = sum(float(s.Volume) for n in physical for s in shapes[n].Solids)
    step_volume = sum(float(s.Volume) for s in step.Solids)
    step_error = abs(step_volume-source_volume)
    checks['STEP_valid_solids_and_registered_count'] = (
        bool(step.isValid()) and all(s.isValid() for s in step.Solids)
        and len(step.Solids)==sum(len(shapes[n].Solids) for n in physical))
    checks['STEP_volume_agreement_computational_tolerance'] = (
        step_error <= TOL['volume_absolute_mm3']+TOL['volume_relative']*source_volume)

    # Every distinct installed-object pair is considered. No overlap whitelist.
    neutral = []
    neutral_pair_count = 0
    for a,b in itertools.combinations(physical,2):
        neutral_pair_count += 1
        if bbox_gap(shapes[a],shapes[b])<=TOL['contact_mm']:
            neutral.append(pair_measure(shapes[a],shapes[b],a,b,{'alpha_deg':0,'beta_deg':0}))
    neutral_failures = [r for r in neutral if r['common_volume_mm3']>TOL['intersection_volume_mm3']]
    checks['neutral_distinct_installed_objects_no_volumetric_overlap'] = not neutral_failures

    # Cross-group physical intersections are checked at each declared pose.
    cross_pairs = [(a,b) for a,b in itertools.combinations(physical,2)
                   if rows[a]['owner']!=rows[b]['owner']]
    mechanism_near,rotor_minima,rotor_failures,hub_interfaces = [],{},[],[]
    rotor_evaluations = 0
    posed = []
    for pose in POSES:
        current = {n:transform(s,rows[n]['owner'],pose,outer,offset) for n,s in shapes.items()}
        posed.append((pose,current))
        for a,b in cross_pairs:
            if bbox_gap(current[a],current[b])<=TOL['contact_mm']:
                mechanism_near.append(pair_measure(current[a],current[b],a,b,pose))
        for i,rotor in enumerate(rotors):
            # Own prop proxy is contained intentionally in its swept envelope.
            # Own motor is audited separately: full-disc hub occupancy is not
            # silently waived or called accepted mounting/retention geometry.
            obstacles = [n for n in physical if n not in (props[i],motors[i])] + wiring
            for obstacle in obstacles:
                result = pair_measure(current[rotor],current[obstacle],rotor,obstacle,pose)
                rotor_evaluations += 1
                key = rotor+' / '+obstacle
                if worse(result,rotor_minima.get(key)):
                    rotor_minima[key] = result
                if result['distance_mm']<=TOL['contact_mm']:
                    rotor_failures.append(result)
            hub_interfaces.append(pair_measure(current[rotor],current[motors[i]],rotor,motors[i],pose))
        result = pair_measure(current[rotors[0]],current[rotors[1]],rotors[0],rotors[1],pose)
        key = 'rotor / rotor'
        if worse(result,rotor_minima.get(key)):
            rotor_minima[key] = result
        if result['distance_mm']<=TOL['contact_mm']:
            rotor_failures.append(result)
    mechanism_failures = [r for r in mechanism_near
                          if r['common_volume_mm3']>TOL['intersection_volume_mm3']]
    checks['sampled_cross_group_installed_objects_no_volumetric_overlap'] = not mechanism_failures
    checks['sampled_rotor_external_obstacles_positive_separation'] = not rotor_failures

    wiring_conflicts = []
    for wire in wiring:
        for name in physical:
            if bbox_gap(shapes[wire],shapes[name])<=TOL['contact_mm']:
                result = pair_measure(shapes[wire],shapes[name],wire,name,{'alpha_deg':0,'beta_deg':0})
                if result['common_volume_mm3']>TOL['intersection_volume_mm3']:
                    wiring_conflicts.append(result)
    checks['represented_neutral_wiring_reservations_do_not_intersect_installed_solids'] = not wiring_conflicts

    # Measured custom surfaces and paired fits; these are not vendor interfaces.
    interface_names = [n for n in physical if any(k in n for k in
        ('Pivot','Gimbal','Carrier','MotorPlate','Spine','LandingTube','Foot'))]
    surfaces = {n:cylindrical_faces(shapes[n]) for n in interface_names}
    fits = []
    for i in (0,1):
        for a,b in [('OuterPivotPin%d'%i,'OuterPivotBushing%d'%i),
                    ('InnerPivotPin%d'%i,'InnerPivotBushing%d'%i),
                    ('UnresolvedMotorPlate%d'%i,'MotorEnvelope%d'%i)]:
            fits.append(pair_measure(shapes[a],shapes[b],a,b,{'alpha_deg':0,'beta_deg':0}))

    # Parameter edit is local to the existing documented tube parameter.
    sheet = doc.getObject('Parameters')
    spine_names = [n for n in physical if n.startswith('Spine')]
    original_volumes = {n:float(doc.getObject(n).Shape.Volume) for n in spine_names}
    sheet.set('B1','310 mm')
    doc.recompute()
    edits = []
    for name in spine_names:
        s = doc.getObject(name).Shape
        edits.append({'name':name,'old_volume_mm3':original_volumes[name],
            'new_volume_mm3':float(s.Volume),'new_z_extent_mm':float(s.BoundBox.ZLength),
            'valid':bool(s.isValid()),
            'volume_ratio_error':abs(float(s.Volume)/original_volumes[name]-310/300)})
    checks['reopened_local_spine_parameter_edit_recomputes'] = bool(edits) and all(
        r['valid'] and abs(r['new_z_extent_mm']-310)<TOL['parameter_length_mm']
        and r['volume_ratio_error']<1e-10 for r in edits)
    sheet.set('B1','300 mm')
    doc.recompute()

    # Ground diagnostics use bounds of actual transformed rotor/foot solids.
    # Axial shortening moves each FOOT toward its attachment by the specified
    # amount. This is prescribed geometry, not a force/compliance solution;
    # deformed leg/wiring envelopes remain unresolved.
    feet = ['Foot%d'%i for i in range(meta['landing_leg_count'])]
    directions = [doc.getObject('LandingTube%d_Outer'%i).Placement.Rotation.multVec(App.Vector(0,0,1))
                  for i in range(len(feet))]
    compression = {'none':[0.0]*len(feet),'all_axial_10mm':[10.0]*len(feet),
                   'all_axial_20mm':[20.0]*len(feet)}
    for i in range(len(feet)):
        compression['foot%d_axial_20mm'%i] = [20.0 if j==i else 0.0 for j in range(len(feet))]
    body_poses = [(0.0,0.0)]+[(tilt,float(az)) for tilt in (5.0,10.0) for az in range(0,360,45)]
    terrain_heights = [0.0,10.0,20.0]
    ground_reductions,ground_minima = [],{}
    for tilt,azimuth in body_poses:
        phi = math.radians(azimuth)
        body_rotation = App.Rotation(App.Vector(-math.sin(phi),math.cos(phi),0),tilt)
        body_placement = App.Placement(App.Vector(0,0,0),body_rotation)
        for cname,shortenings in compression.items():
            foot_lows = []
            for i,name in enumerate(feet):
                foot = shapes[name].copy()
                shortening = App.Placement(directions[i]*(-shortenings[i]),App.Rotation())
                foot.Placement = body_placement.multiply(shortening).multiply(foot.Placement)
                foot_lows.append(float(foot.BoundBox.ZMin))
            ground_in_rotated_C = min(foot_lows)
            contacting = [feet[i] for i,z in enumerate(foot_lows)
                          if abs(z-ground_in_rotated_C)<=1e-6]
            for pose,current in posed:
                for rotor in rotors:
                    rotor_shape = current[rotor].copy()
                    rotor_shape.Placement = body_placement.multiply(rotor_shape.Placement)
                    rotor_low = float(rotor_shape.BoundBox.ZMin)
                    for terrain in terrain_heights:
                        value = rotor_low-ground_in_rotated_C-terrain
                        result = {'rotor':rotor,'gimbal_pose':pose,'body_tilt_deg':tilt,
                            'body_tilt_azimuth_C_deg':azimuth,'compression_case':cname,
                            'axial_foot_shortening_mm':shortenings,
                            'foot_minimum_z_rotated_C_mm':foot_lows,
                            'first_contact_foot_names':contacting,
                            'airframe_vertical_translation_to_contact_mm':-ground_in_rotated_C,
                            'rotor_minimum_z_rotated_C_mm':rotor_low,
                            'separate_obstacle_plane_above_foot_ground_mm':terrain,
                            'clearance_to_obstacle_plane_mm':value}
                        key = (rotor,tilt,cname,terrain)
                        # Store the governing pose for each declared sensitivity cell.
                        existing = ground_minima.get(key)
                        if existing is None or value<existing['clearance_to_obstacle_plane_mm']:
                            ground_minima[key] = result
    ground_reductions = list(ground_minima.values())
    minimum_ground = min(r['clearance_to_obstacle_plane_mm'] for r in ground_reductions)
    checks['sampled_prescribed_foot_geometry_rotor_ground_separation'] = minimum_ground>TOL['contact_mm']

    App.closeDocument(doc.Name)
    after = {key:sha(ROOT/entry[0]) for key,entry in INPUTS.items()}
    checks['tested_artifact_files_preserved'] = before==after
    checks.update({
        'REQ-VEHICLE-CAD: complete_commercial_mount_compatibility':None,
        'REQ-VEHICLE-CAD: complete_installed_mass_and_momentum_interface':None,
        'REQ-LANDING-GEAR-ARRANGEMENT: continuous_full_envelope_clearance':None,
        'REQ-LANDING-CONTACT-CLEARANCE: dynamic_approach_and_settling':None,
        'physical_joint_strength_and_landing_tests':None,
        'loaded_blade_leg_and_wiring_deformation':None,
        'complete_moving_harness_clearance':None,
        'commercial_hub_and_shaft_retention_clearance':None
    })
    failed = [name for name,value in checks.items() if value is False]
    verdict = {'outcome':'failed' if failed else 'passed',
        'explanation':('Artifact-bound computational diagnostic only. '
            'All performed checks are reported; null checks were not performed. '
            'Nine gimbal samples do not establish continuous clearance. '
            'No hardware qualification, design selection or review acceptance. '
            'Failed checks: '+('; '.join(failed) if failed else 'none')),
        'checks':checks,
        'measurements':{
            'diagnostic_minimum_sampled_ground_clearance':{'value':minimum_ground,'unit':'mm'},
            'diagnostic_STEP_volume_difference':{'value':step_error,'unit':'mm^3'},
            'diagnostic_neutral_overlap_pair_count':{'value':len(neutral_failures),'unit':''},
            'diagnostic_sampled_rotor_contact_witness_count':{'value':len(rotor_failures),'unit':''}}}
    data = {
        'schema':'hopper_cad_diagnostic_geometry_audit/1','authority':K.AUTHORITY,
        'status':'Executed diagnostic observations, conditional on stated model and computational tolerances',
        'candidate_id':STEM,'input_files':{k:{'path':v[0],'sha256':before[k]} for k,v in INPUTS.items()},
        'audit_source_sha256':sha(ROOT/'cad/pdr_trade/diagnostic_geometry_audit_m4_02.py'),
        'computational_tolerances':TOL,'verification_result':verdict,
        'native_inventory':inventory,'synthetic_fixtures':fixtures,
        'STEP':{'solid_count':len(step.Solids),'native_registered_volume_mm3':source_volume,
                'imported_volume_mm3':step_volume,'absolute_difference_mm3':step_error},
        'neutral_pair_count_considered':neutral_pair_count,
        'neutral_AABB_near_pair_measurements':neutral,
        'neutral_overlap_witnesses':neutral_failures,
        'gimbal_sample_poses':POSES,
        'cross_group_pair_count_per_pose':len(cross_pairs),
        'sampled_cross_group_AABB_near_measurements':mechanism_near,
        'sampled_cross_group_overlap_witnesses':mechanism_failures,
        'rotor_external_pair_evaluations':rotor_evaluations,
        'rotor_external_pair_sampled_minima':list(rotor_minima.values()),
        'rotor_external_contact_or_overlap_witnesses':rotor_failures,
        'own_motor_full_slab_interface_measurements':hub_interfaces,
        'rotor_exclusion_policy':'Only own artificial prop distribution and own motor envelope are excluded from external-obstacle scoring. Own motor full-slab intersections are separately retained, unresolved, and not accepted. Other rotor swept slabs are checked against each other. No material overlap is waived in the installed-object tests.',
        'wiring_reservation_overlap_witnesses':wiring_conflicts,
        'custom_interface_cylindrical_surfaces':surfaces,
        'custom_fit_and_unresolved_motor_gap_measurements':fits,
        'parameter_edit_observations':edits,
        'ground':{'body_samples':body_poses,'gimbal_samples':POSES,
            'compression_cases_axial_mm':compression,'obstacle_plane_heights_mm':terrain_heights,
            'sensitivity_cell_minimum_witnesses':ground_reductions,
            'underlying_pose_count':len(body_poses)*len(POSES)*len(compression)*len(terrain_heights)*len(rotors),
            'method':'Rotate actual geometry. Prescribe foot shortening along each actual tube axis. Translate the airframe until the lowest compressed foot geometry reaches the level foot-ground plane. A separately specified raised horizontal obstacle plane represents rotor-area terrain sensitivity, not an inferred terrain surface from foot heights.',
            'limitations':'Bounding-box extrema are geometric observations. No contact forces, stiffness, damping, friction, equilibrium or settling are solved. Deformed legs and cables are not checked. One-foot shortening is a sensitivity, not evidence of achievable or stable compression. Positive samples are not continuous clearance.'},
        'continuous_clearance':None,
        'mass_scope':'Existing source report remains partial; this audit does not fill missing mass rows or qualify material densities.',
        'physical_qualification':None,
        'artifact_files_preserved':before==after}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(verdict,allow_nan=False))


if __name__=='__main__':
    main()
