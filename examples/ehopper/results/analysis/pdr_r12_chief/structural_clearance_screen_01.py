"""R12 stage-2 rigid-envelope analysis, not CAD or physical acceptance.

Use Guacamole execute and declare the chosen output JSON. A separate editable
artifact-bound checker must verify this program and its results before use.
No vehicle selection is made. Joint translation is a required explicit input.
The neutral geometry retains the configured rotor drops from the outer origin.
All dimensions, including nonzero joint offsets, remain comparison hypotheses.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
EPS_M = 1e-9  # Numerical debit, not a physical tolerance or formal FP proof.
S = (1.0, -1.0, -1.0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def add(a, b):
    return tuple(x+y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def scale(a, k):
    return tuple(k*x for x in a)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def mv(a, v):
    return tuple(dot(row, v) for row in a)


def transpose(a):
    return tuple(zip(*a))


def mmul(a, b):
    bt = transpose(b)
    return tuple(tuple(dot(row, col) for col in bt) for row in a)


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return ((1,0,0),(0,c,-s),(0,s,c))


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return ((c,0,s),(0,1,0),(-s,0,c))


def conjugate_to_cad(a):
    return tuple(tuple(S[i]*a[i][j]*S[j] for j in range(3)) for i in range(3))


def rotation(alpha, beta):
    return conjugate_to_cad(mmul(rx(alpha), ry(beta)))


def point_segment_distance(p, a, b):
    v = sub(b, a)
    vv = dot(v, v)
    t = 0.0 if vv == 0 else max(0.0, min(1.0, dot(sub(p,a),v)/vv))
    return norm(sub(p, add(a, scale(v,t))))


def box_distance(a, b, lo, hi):
    # Segment's AABB versus the target's AABB: conservative distance lower bound.
    gaps = [max(lo[j]-max(a[j],b[j]), min(a[j],b[j])-hi[j], 0.0) for j in range(3)]
    return norm(gaps)


def cylinder_distance(p, centre, radius, half_height):
    q = sub(p, centre)
    dr = max(math.hypot(q[0],q[1])-radius, 0.0)
    dz = max(abs(q[2])-half_height, 0.0)
    return math.hypot(dr,dz)


def segment_bounds(a, b, distance, coarse_lower, refine_below, spatial_step):
    """Bounds on minimum distance from an axis segment to a closed target.

    Each distance function used here is 1-Lipschitz. Equal-spaced axis samples
    have covering radius L/(2N), including both endpoints. Subtracting this
    radius from the sampled minimum supplies a geometric lower bound.
    A coarse AABB/slab bound can avoid unnecessary refinement when already clear.
    """
    upper = min(distance(a), distance(b))
    lower = max(0.0, coarse_lower)
    if lower >= refine_below:
        return lower, upper, 'coarse_geometric_bound'
    length = norm(sub(b,a))
    if length == 0:
        return upper, upper, 'point_distance'
    n = max(1, math.ceil(length/spatial_step))
    delta = sub(b,a)
    for j in range(1,n):
        upper = min(upper, distance(add(a,scale(delta,j/n))))
        if upper == 0:
            break
    lower = max(lower, upper-length/(2*n), 0.0)
    require(lower <= upper+1e-8, 'Inconsistent segment bounds')
    return min(lower,upper), upper, 'axis_samples_with_covering_radius'


def segment_cylinder_bounds(a,b,centre,radius,half_height,refine_below,step):
    z0,z1 = a[2]-centre[2],b[2]-centre[2]
    slab_bound = max(min(z0,z1)-half_height, -max(z0,z1)-half_height, 0.0)
    lo = (centre[0]-radius,centre[1]-radius,centre[2]-half_height)
    hi = (centre[0]+radius,centre[1]+radius,centre[2]+half_height)
    lower = max(slab_bound,box_distance(a,b,lo,hi))
    return segment_bounds(a,b,lambda p:cylinder_distance(p,centre,radius,half_height),lower,refine_below,step)


def segment_segment_bounds(a,b,c,d,refine_below,step):
    lo = tuple(min(c[j],d[j]) for j in range(3))
    hi = tuple(max(c[j],d[j]) for j in range(3))
    return segment_bounds(a,b,lambda p:point_segment_distance(p,c,d),box_distance(a,b,lo,hi),refine_below,step)


def cone_poses(limit_deg, step_deg=1.0, boundary_step_deg=5.0):
    require(0 < limit_deg < 89, 'Cone bound must be between 0 and 89 degrees')
    require(0 < step_deg <= limit_deg, 'Invalid angular grid step')
    limit,step = math.radians(limit_deg),math.radians(step_deg)
    count = math.floor(limit_deg/step_deg+1e-12)
    poses = {}
    def retain(a,b):
        require(math.cos(a)*math.cos(b) >= math.cos(limit)-1e-12, 'Pose outside cone')
        poses[(round(a,12),round(b,12))] = (a,b)
    for i,j in itertools.product(range(-count,count+1),repeat=2):
        a,b = i*step,j*step
        if math.cos(a)*math.cos(b) >= math.cos(limit)-1e-14:
            retain(a,b)
    # Parameterize the complete resultant-tilt boundary by module +z in FRD.
    for j in range(math.ceil(360/boundary_step_deg)):
        phi = math.radians(j*boundary_step_deg)
        b = math.asin(math.sin(limit)*math.cos(phi))
        a = math.atan2(-math.sin(limit)*math.sin(phi),math.cos(limit))
        retain(a,b)
    return [poses[k] for k in sorted(poses)]


def pose_cover_m(d, radius_about_inner_origin, grid_step_rad):
    # p=O+A(alpha)*d+R(alpha,beta)*r. Round each angle toward zero to
    # a retained grid point: it remains inside cos(a)cos(b)>=cos(limit).
    # Both angle changes are < grid_step. Triangle inequality bounds the
    # Hausdorff displacement of every point in the declared moving envelope.
    return 2*math.sin(grid_step_rad/2)*(norm(d)+2*radius_about_inner_origin)


def slab_radius_about_inner(centre,d,radius,half_height):
    q = sub(centre,d)
    return math.hypot(math.hypot(q[0],q[1])+radius,abs(q[2])+half_height)


def body_vertical_samples(max_tilt_deg,polar_step_deg,azimuth_step_deg):
    require(0 <= max_tilt_deg < 89, 'Invalid airframe tilt interval')
    require(0 < polar_step_deg <= 10 and 0 < azimuth_step_deg <= 90, 'Invalid body sampling')
    gamma = [j*polar_step_deg for j in range(math.floor(max_tilt_deg/polar_step_deg)+1)]
    gamma = sorted(set(gamma+[0.0,max_tilt_deg]))
    az = [j*azimuth_step_deg for j in range(math.ceil(360/azimuth_step_deg)) if j*azimuth_step_deg < 360]
    rows = []
    for g in gamma:
        for a in ([0.0] if g == 0 else az):
            gr,ar = math.radians(g),math.radians(a)
            k = (math.sin(gr)*math.cos(ar),math.sin(gr)*math.sin(ar),math.cos(gr))
            rows.append({'tilt_deg':g,'vertical_azimuth_deg':a,'vertical_covector_C':k})
    dg = max((b-a for a,b in zip(gamma,gamma[1:])),default=0.0)/2
    da = max(b-a for a,b in zip(az,az[1:]+[az[0]+360]))/2
    # Bound distance between vertical unit covectors for nearest polar/azimuth samples.
    cover = 2*math.sin(math.radians(dg)/2)+2*math.sin(math.radians(max_tilt_deg))*math.sin(math.radians(da)/2)
    return rows,cover


def primitive(name,group,a,b,radius):
    return {'id':name,'group':group,'a_C_m':tuple(a),'b_C_m':tuple(b),'radius_m':radius}


def static_parts(seed,arrangement,geom,leg_radius,spine_radius):
    parts,feet = [],[]
    for j,angle in enumerate(arrangement['azimuths_deg']):
        t = math.radians(angle)
        c,s = math.cos(t),math.sin(t)
        a = (seed['leg_attachment_radius_mm']*c/1000,seed['leg_attachment_radius_mm']*s/1000,seed['leg_attachment_z_mm']/1000)
        f = (seed['foot_radius_mm']*c/1000,seed['foot_radius_mm']*s/1000,geom['foot_tube_socket_reference_z_mm']/1000)
        u = scale(sub(a,f),1/norm(sub(a,f)))
        top = add(a,scale(u,geom['leg_root_insertion_extension_mm']/1000))
        bottom = sub(f,scale(u,geom['leg_foot_insertion_extension_mm']/1000))
        parts.append(primitive('leg_'+str(j),'legs',bottom,top,leg_radius))
        centre = (f[0],f[1],geom['foot_centre_z_mm']/1000)
        feet.append(centre)
        parts.append(primitive('foot_'+str(j),'feet',centre,centre,geom['foot_contact_radius_mm']/1000))
    # The longest candidate encloses each shorter coaxial tube hypothesis.
    length = max(geom['spine_finished_lengths_mm'])/1000
    z = (seed['leg_attachment_z_mm']+geom['spine_lower_end_above_leg_attachment_mm'])/1000
    for layout in geom['spine_layouts']:
        xy = layout.get('xy_mm')
        if xy is None:
            xy = [(layout['radius_mm']*math.cos(math.radians(a)),layout['radius_mm']*math.sin(math.radians(a))) for a in layout['azimuths_deg']]
        require(len(xy)==layout['count'],'Spine count mismatch')
        for j,(x,y) in enumerate(xy):
            parts.append(primitive(layout['id']+'_spine_'+str(j),'spines_'+layout['id'],(x/1000,y/1000,z),(x/1000,y/1000,z+length),spine_radius))
    return parts,feet


def yoke_parts(seed,geom,rotor_radius):
    hypothesis = geom['moving_support_topology_hypothesis']
    require(hypothesis['yoke_upright_module_azimuths_deg']==[0,180], 'This yoke screen requires the configured two opposite uprights')
    radius = hypothesis['yoke_upright_screening_outer_radius_mm']/1000
    x = rotor_radius+hypothesis['yoke_upright_centre_radius_beyond_propeller_tip_mm']/1000
    carrier_drop = (seed['upper_rotor_drop_from_pivot_mm']+seed['rotor_plane_separation_mm']/2)/1000
    # Coordinates relative to outer origin at neutral. All four pieces are
    # module-carried envelope hypotheses, NOT a designed gimbal interface.
    return [primitive('yoke_left','moving_yoke',(-x,0,0),(-x,0,-carrier_drop),radius),
            primitive('yoke_right','moving_yoke',(x,0,0),(x,0,-carrier_drop),radius),
            primitive('yoke_top_crossmember','moving_yoke',(-x,0,0),(x,0,0),radius),
            primitive('yoke_carrier','moving_yoke',(-x,0,-carrier_drop),(x,0,-carrier_drop),radius)]


def update(rows,key,lower,upper,travel_cover,witness,method):
    require(lower <= upper+1e-8,'Invalid clearance interval')
    row = rows.setdefault(key,{'minimum_sampled_lower_bound_m':math.inf,'minimum_sampled_upper_bound_m':math.inf,'travel_cover_debit_m':travel_cover,'methods':set()})
    require(abs(row['travel_cover_debit_m']-travel_cover)<1e-12,'Inconsistent travel bound')
    lower,upper = lower-EPS_M,upper+EPS_M
    if lower < row['minimum_sampled_lower_bound_m']:
        row['minimum_sampled_lower_bound_m'] = lower
        row['lower_bound_witness'] = witness
    if upper < row['minimum_sampled_upper_bound_m']:
        row['minimum_sampled_upper_bound_m'] = upper
        row['upper_bound_witness'] = witness
    row['methods'].add(method)


def finish_rows(rows,threshold):
    out = []
    for key,row in sorted(rows.items()):
        row = dict(row)
        row['pair'] = key
        row['methods'] = sorted(row['methods'])
        lower = row['minimum_sampled_lower_bound_m']-row['travel_cover_debit_m']
        row['continuous_domain_lower_bound_m'] = lower
        if lower >= threshold:
            state = 'rigid_hypothesis_lower_bound_meets_study_threshold'
        elif row['minimum_sampled_upper_bound_m'] <= 0:
            state = 'sampled_outer_envelope_overlap_or_touch'
        else:
            state = 'inconclusive_at_study_threshold'
        row['screen_classification'] = state
        row['physical_acceptance'] = None
        out.append(row)
    return out


def analyze_case(seed,arr,geom,prop,cone_deg,half_mm,d,poses,body_rows,k_cover,leg_radius,spine_radius,spatial_step):
    radius,half = prop['diameter_mm']/2000,half_mm/1000
    threshold = geom['preliminary_rigid_clearance_threshold_mm']/1000
    origin = (0,0,seed['pivot_z_mm']/1000)
    upper_drop = seed['upper_rotor_drop_from_pivot_mm']/1000
    spacing = seed['rotor_plane_separation_mm']/1000
    rotors = {'U':(0,0,-upper_drop),'L':(0,0,-upper_drop-spacing)}
    parts,feet = static_parts(seed,arr,geom,leg_radius,spine_radius)
    yokes = yoke_parts(seed,geom,radius)
    step_rad = math.radians(1.0)
    rotor_extent = {name:slab_radius_about_inner(c,d,radius,half) for name,c in rotors.items()}
    rotor_cover = {name:pose_cover_m(d,v,step_rad) for name,v in rotor_extent.items()}
    yoke_extent = {p['id']:max(norm(sub(p['a_C_m'],d)),norm(sub(p['b_C_m'],d)))+p['radius_m'] for p in yokes}
    yoke_cover = {name:pose_cover_m(d,v,step_rad) for name,v in yoke_extent.items()}
    rows,ground,invariant = {},{},{}
    foot_radius = geom['foot_contact_radius_mm']/1000
    foot_norm = max(norm(f) for f in feet)
    ground_samples = [(b,min(dot(b['vertical_covector_C'],f)-foot_radius for f in feet)) for b in body_rows]
    for name,centre in rotors.items():
        for y in yokes:
            lo,hi,method = segment_cylinder_bounds(y['a_C_m'],y['b_C_m'],centre,radius,half,math.inf,spatial_step)
            update(invariant,name+'::'+y['id'],lo-y['radius_m'],hi-y['radius_m'],0.0,{'configuration':'neutral; invariant under common rigid articulation'},method)
    for alpha,beta in poses:
        r = rotation(alpha,beta)
        rt = transpose(r)
        a = conjugate_to_cad(rx(alpha))
        ad = mv(a,d)
        witness = {'alpha_rad':alpha,'beta_rad':beta}
        def inverse(point):
            # Neutral offset corresponding to the current fixed CAD point.
            return add(d,mv(rt,sub(sub(point,origin),ad)))
        def forward(neutral_offset):
            return add(add(origin,ad),mv(r,sub(neutral_offset,d)))
        for part in parts:
            p,q = inverse(part['a_C_m']),inverse(part['b_C_m'])
            for name,centre in rotors.items():
                debit = rotor_cover[name]
                lo,hi,method = segment_cylinder_bounds(p,q,centre,radius,half,threshold+part['radius_m']+debit,spatial_step)
                update(rows,name+'::'+part['id'],lo-part['radius_m'],hi-part['radius_m'],debit,witness,method)
            for y in yokes:
                debit = yoke_cover[y['id']]
                total_radius = part['radius_m']+y['radius_m']
                lo,hi,method = segment_segment_bounds(p,q,y['a_C_m'],y['b_C_m'],threshold+total_radius+debit,spatial_step)
                update(rows,y['id']+'::'+part['id'],lo-total_radius,hi-total_radius,debit,witness,method)
        normal = mv(r,(0,0,1))
        for name,centre in rotors.items():
            c = forward(centre)
            # Bound body-tilt sampling error using support-function Lipschitz
            # constants about the fixed CAD origin, then add gimbal covering.
            world_extent_bound = norm(origin)+norm(d)+rotor_extent[name]
            continuous_debit = rotor_cover[name]+k_cover*(world_extent_bound+foot_norm)
            for body,foot_lowest in ground_samples:
                k = body['vertical_covector_C']
                kn = max(-1.0,min(1.0,dot(k,normal)))
                rotor_lowest = dot(k,c)-radius*math.sqrt(max(0.0,1-kn*kn))-half*abs(kn)
                gap = rotor_lowest-foot_lowest
                w = dict(witness,body_tilt_deg=body['tilt_deg'],vertical_azimuth_deg=body['vertical_azimuth_deg'])
                update(ground,name+'::level_ground',gap,gap,continuous_debit,w,'exact_cylinder_support_at_sampled_pose')
    ground_rows = finish_rows(ground,threshold)
    debits = geom.get('additional_ground_clearance_consumption_sensitivity_mm')
    # The existing configuration stores the ground debit in the clearance contract,
    # so the caller adds those sensitivity rows separately.
    return {'id':'|'.join([seed['id'],arr['id'],prop['id'],'cone_'+str(cone_deg),'half_'+str(half_mm)]),
            'seed':seed['id'],'landing_arrangement':arr['id'],'propeller_envelope':prop['id'],
            'resultant_cone_deg':cone_deg,'rotor_slab_half_thickness_mm':half_mm,
            'outer_origin_C_m':origin,'outer_to_inner_neutral_C_m':d,
            'static_capsule_hypotheses':parts,'module_carried_capsule_hypotheses_relative_to_outer_at_neutral':yokes,
            'neutral_rotor_centres_relative_to_outer_C_m':rotors,
            'rotor_to_rotor_axial_slab_gap_m':spacing-2*half,
            'rotor_to_rotor_note':'Exact common-frame slab separation for the declared equal coaxial envelopes; blade flexibility and runout are unverified.',
            'moving_to_fixed_screens':finish_rows(rows,threshold),
            'rotor_to_yoke_invariant_screens':finish_rows(invariant,threshold),
            'ground_screens':ground_rows,'complete_geometry_acceptance':None}


def safe_path(name):
    p = Path(name)
    p = (ROOT/p).resolve() if not p.is_absolute() else p.resolve()
    p.relative_to(ROOT)
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='analysis/pdr_r12_chief/structural_trade_config_01.json')
    parser.add_argument('--expected-config-sha256',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--study-id',required=True)
    parser.add_argument('--outer-to-inner-cad-mm',nargs=3,type=float,required=True,
                        help='Explicit unselected neutral joint-origin displacement, expressed in CAD/outer axes; never inherited as calibrated geometry')
    parser.add_argument('--spatial-step-mm',type=float,default=4.0)
    parser.add_argument('--body-polar-step-deg',type=float,default=1.0)
    args = parser.parse_args()
    inp,out = safe_path(args.config),safe_path(args.output)
    require(not out.exists(),'Choose a fresh output filename')
    raw = inp.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    require(actual_hash==args.expected_config_sha256,'Configuration hash mismatch')
    cfg = json.loads(raw.decode('utf-8'))
    require(cfg['schema']=='hopper_r12_structural_trade_inputs_v1','Unsupported configuration')
    require(cfg['units_and_frames']['configuration_lengths']=='mm','Expected mm configuration')
    require(cfg['units_and_frames']['R_BC']==[[1,0,0],[0,-1,0],[0,0,-1]],'Unexpected frame convention')
    require(all(math.isfinite(v) for v in args.outer_to_inner_cad_mm),'Nonfinite joint offset')
    require(math.isfinite(args.spatial_step_mm) and 0 < args.spatial_step_mm <= 10,'Invalid spatial step')
    geom,contract = cfg['geometry_hypotheses'],cfg['clearance_evaluation_contract']
    d = tuple(v/1000 for v in args.outer_to_inner_cad_mm)
    leg_products = [p for p in cfg['supplier_candidates'] if 'leg' in p['roles']]
    spine_products = [p for p in cfg['supplier_candidates'] if 'spine' in p['roles']]
    require(leg_products and spine_products,'Missing tube candidates')
    leg_radius = max(p['od_mm'] for p in leg_products)/2000
    spine_radius = max(p['od_mm'] for p in spine_products)/2000
    poses = {limit:cone_poses(limit) for limit in geom['gimbal_resultant_cone_limits_deg']}
    body_rows,k_cover = body_vertical_samples(max(contract['landing_body_tilt_deg']),args.body_polar_step_deg,contract['landing_tilt_azimuth_step_deg'])
    cases = []
    combinations = list(itertools.product(geom['layout_seeds'],geom['landing_arrangements'],geom['propeller_envelopes'],geom['gimbal_resultant_cone_limits_deg'],geom['rotor_swept_slab_half_thickness_mm']))
    for index,(seed,arr,prop,cone,half) in enumerate(combinations):
        require(seed['leg_attachment_z_mm']>seed['pivot_z_mm'],'Leg attachment must be above outer origin')
        require(seed['rotor_plane_separation_mm']>0,'Invalid rotor spacing')
        case = analyze_case(seed,arr,geom,prop,cone,half,d,poses[cone],body_rows,k_cover,leg_radius,spine_radius,args.spatial_step_mm/1000)
        for row in case['ground_screens']:
            row['ground_consumption_sensitivities'] = [
                {'additional_debit_mm':v,'continuous_rigid_lower_bound_after_debit_m':row['continuous_domain_lower_bound_m']-v/1000,
                 'basis':'Unvalidated compression/terrain/tolerance sensitivity, not a flight margin'}
                for v in contract['additional_ground_clearance_consumption_sensitivity_mm']]
        cases.append(case)
        print('Completed rigid-envelope case '+str(index+1)+'/'+str(len(combinations)),file=sys.stderr)
    result = {
        'schema':'hopper_r12_clearance_screen_results_v1','study_id':args.study_id,
        'status':'Unselected rigid-envelope calculations; independent verification not yet performed',
        'actual_inputs':{'config_path':str(inp.relative_to(ROOT)),'config_sha256':actual_hash,
                        'program_path':str(Path(__file__).resolve().relative_to(ROOT)),
                        'program_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        'outer_to_inner_neutral_C_mm':args.outer_to_inner_cad_mm},
        'input_provenance':cfg['provenance'],
        'propeller_envelope_provenance':geom['propeller_envelopes'],
        'units':{'computed_lengths':'m','configuration_lengths':'mm','joint_angles':'rad','named_deg_fields':'deg'},
        'frame_and_kinematics':{
            'R_BC':cfg['units_and_frames']['R_BC'],
            'R_BM':'Rx(alpha) Ry(beta)',
            'R_C':'transpose(R_BC) R_BM R_BC',
            'point_C':'O_C + A_C(alpha) d_C + R_C(alpha,beta) (p_neutral_relative_to_O_C - d_C)',
            'A_C':'transpose(R_BC) Rx(alpha) R_BC',
            'neutral_offset_body_m':tuple(S[j]*d[j] for j in range(3)),
            'joint_offset_status':'Coincident-origin analytical geometry fixture only' if norm(d)==0 else 'Explicit unselected noncoincident-origin geometry hypothesis',
            'instantaneous_CG_and_mass_properties':'Not computed or assumed by this geometry-only program'},
        'envelope_assumptions':{
            'rotors':'Finite solid swept circular slabs; not actual blade solids or calibrated flex envelopes',
            'tubes':'Solid capsules enclose the ideal hollow tubes, including their extended endpoints',
            'leg_tube_outer_radius_used_m':leg_radius,'spine_tube_outer_radius_used_m':spine_radius,
            'spines':'Each topology screened with maximum configured length and maximum candidate OD; no material or stock selection',
            'feet':'Unselected spherical feet using the configured centre height and contact radius; no actual foot shape is established',
            'yoke':'Four module-carried capsule hypotheses only; all crossmembers use the configured upright radius. No bearing, motor mount or joint interface is established',
            'scope_of_overlap':'Outer-envelope overlap is not automatically intersection of actual hollow tubes or hardware',
            'scope_of_clear':'Bounds apply only to declared rigid hypotheses, not omitted components or deformed hardware'},
        'numerical_controls':{'spatial_step_mm':args.spatial_step_mm,'gimbal_grid_step_deg':1.0,
                              'gimbal_boundary_azimuth_step_deg':5.0,'body_polar_step_deg':args.body_polar_step_deg,
                              'body_vertical_covector_cover':k_cover,'numerical_distance_debit_m':EPS_M},
        'gimbal_pose_samples':{str(limit):[{'alpha_rad':a,'beta_rad':b} for a,b in data] for limit,data in poses.items()},
        'body_vertical_samples':body_rows,
        'continuous_bound_basis':[
            'For each in-cone alpha,beta, rounding both magnitudes toward zero reaches an included 1-degree grid point still inside the cone; each angular difference is at most one grid step.',
            'Moving-envelope Hausdorff displacement is bounded by 2*sin(step/2)*(norm(d)+2*r_max), where r_max bounds every envelope point relative to the inner origin.',
            'Axis-sampled distance lower bounds subtract half the sample spacing because distance to a closed set is 1-Lipschitz.',
            'Ground support uses the finite cylinder support function and translates the complete rigid vehicle until its lowest modeled spherical foot touches the same plane.',
            'The body-tilt bound covers every tilt from zero to the maximum configured tilt, not just endpoints, using nearest polar/azimuth vertical-covector samples and support-function radius bounds.',
            'Floating-point calculations include a small explicit numerical debit but are not interval-arithmetic proofs; independent analytical fixtures and CAD reconciliation remain required.'
        ],
        'study_clearance_threshold_mm':geom['preliminary_rigid_clearance_threshold_mm'],
        'case_count':len(cases),'cases':cases,'selected_candidate':None,
        'complete_geometry_acceptance':None,'structural_acceptance':None,'physical_validation':'unperformed',
        'limitations':[
            'This analysis does not rehabilitate the large-deflection unbraced landing-leg sensitivities from stage 1. Braced or otherwise revised load paths require their own geometry, mass, procurement and joint assessment.',
            'Leg attachment ring/plate, gimbal bearings and frames, braces, servos, links, motor bodies, adapters, shafts, equipment, sensors and wiring are not modeled.',
            'Rotor/shaft interfaces cannot be waived as intentional collisions without actual bore, adapter and retention evidence.',
            'Neither sampled overlaps nor loose continuous bounds justify an actuation-concept change. Retain the common gimbal and seek human agreement before any conflicting change.',
            'No FCStd/STEP export, mounting acceptance, material qualification, complete vehicle mass/energy/cost result or review acceptance is produced.',
            'A separate checker must test the actual configuration, program and results, including transform identities, noncoincident offsets, analytical support functions, deliberately colliding cases and convergence under finer sampling.'
        ]
    }
    encoded = json.dumps(result,indent=2,allow_nan=False)+'\n'
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as handle:
        handle.write(encoded)
    print(json.dumps({'analysis_output':str(out.relative_to(ROOT)),'case_count':len(cases),
                      'independent_verification':'not performed','physical_acceptance':'not assessed'}))


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        raise
