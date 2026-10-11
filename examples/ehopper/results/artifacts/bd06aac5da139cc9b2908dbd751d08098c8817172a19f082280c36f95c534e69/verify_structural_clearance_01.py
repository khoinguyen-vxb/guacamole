"""Independent artifact-bound checks for the r12 rigid-envelope study.

Publish this checker before verify_command. Include the configuration, analysis
source, stored results and checker artifact Refs in that tool action's inputs.
Run from the sandbox with python -B. No files are written by this checker.
Stdout contains only VerificationResult JSON; diagnostics use stderr.

Independent reconstruction and distance calculations do not call analyze_case.
The analysis module is imported only for explicitly labelled function fixtures.
Numerical comparisons are floating-point tests, not interval-arithmetic proofs.
Finer sampling reports observed changes; it does not assert physical convergence.
"""
import contextlib
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/pdr_r12_chief'
EXPECTED = {
    'structural_trade_config_01.json': '20ad1f5170c8a8309a3211d3c99e1a6754707b64ee98a2c5c5398ad519d27377',
    'structural_clearance_screen_01.py': '2472159b83732ee9e446193e173d11d91b38c52778217a064012de2eac44b6ed',
    'structural_clearance_screen_results_offset20_01.json': '8b9aa30187fa501a5d8f01b31b938759b02bac987bde453074b1d942ae20cb79',
}
CHECKS = {}
ERRORS = []
METRICS = {}
TOL = 2e-8  # m: numerical comparison tolerance, not a clearance allowance.
EPS = 1e-9  # m: debit explicitly used by the tested analysis.
np = None
CFG = RESULT = None
CONTEXTS = []


def require(ok, message):
    if not bool(ok):
        raise AssertionError(message)


def near(a, b, message, atol=TOL):
    aa, bb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    require(aa.shape == bb.shape, message + ': shape mismatch')
    require(np.isfinite(aa).all() and np.isfinite(bb).all(), message + ': nonfinite')
    require(np.all(np.abs(aa-bb) <= atol), message + ': numerical mismatch')


def check(name, fn):
    try:
        fn()
        CHECKS[name] = True
    except Exception as exc:
        CHECKS[name] = False
        message = name + ': ' + type(exc).__name__ + ': ' + str(exc)
        ERRORS.append(message)
        print(message, file=sys.stderr)


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Nonfinite JSON constant: ' + value)


def load_json(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=strict_pairs,
                      parse_constant=reject_constant)


def indexed(rows, key='id'):
    result = {}
    for row in rows:
        identity = row[key]
        require(identity not in result, 'Duplicate identity: ' + identity)
        result[identity] = row
    return result


def load_inputs():
    global CFG, RESULT
    raw = {}
    for name, digest in EXPECTED.items():
        raw[name] = (BASE/name).read_bytes()
        require(hashlib.sha256(raw[name]).hexdigest() == digest,
                'Artifact hash mismatch: ' + name)
    CFG = load_json(raw['structural_trade_config_01.json'])
    RESULT = load_json(raw['structural_clearance_screen_results_offset20_01.json'])
    require(CFG['schema'] == 'hopper_r12_structural_trade_inputs_v1', 'Config schema')
    require(RESULT['schema'] == 'hopper_r12_clearance_screen_results_v1', 'Results schema')
    actual = RESULT['actual_inputs']
    for label, name in [('config', 'structural_trade_config_01.json'),
                        ('program', 'structural_clearance_screen_01.py')]:
        require(actual[label+'_path'] == 'analysis/pdr_r12_chief/'+name, 'Input path')
        require(actual[label+'_sha256'] == EXPECTED[name], 'Input digest provenance')
    require(actual['outer_to_inner_neutral_C_mm'] == [0, 0, -20], 'Study offset identity')
    require(RESULT['input_provenance'] == CFG['provenance'], 'Configuration provenance')
    require(RESULT['propeller_envelope_provenance'] == CFG['geometry_hypotheses']['propeller_envelopes'], 'Propeller provenance')
    require(RESULT['selected_candidate'] is None, 'Unjustified selection')
    require(RESULT['complete_geometry_acceptance'] is None, 'Unjustified geometry acceptance')
    require(RESULT['structural_acceptance'] is None, 'Unjustified structural acceptance')
    require(RESULT['physical_validation'] == 'unperformed', 'Physical status')
    require(RESULT['envelope_assumptions']['scope_of_overlap'], 'Missing overlap qualification')
    require(RESULT['limitations'], 'Missing scope limitations')
    METRICS['comparison_tolerance_m'] = TOL
    METRICS['checker_file_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def matrices(poses):
    """Direct CAD expression of diag(1,-1,-1) Rx(a)Ry(b) diag(1,-1,-1)."""
    poses = np.asarray(poses, dtype=float).reshape((-1, 2))
    a, b = poses[:, 0], poses[:, 1]
    ca, sa, cb, sb = np.cos(a), np.sin(a), np.cos(b), np.sin(b)
    r = np.zeros((len(poses), 3, 3))
    r[:, 0, 0], r[:, 0, 2] = cb, -sb
    r[:, 1, 0], r[:, 1, 1], r[:, 1, 2] = -sa*sb, ca, -sa*cb
    r[:, 2, 0], r[:, 2, 1], r[:, 2, 2] = ca*sb, sa, ca*cb
    return r


def prepare(poses, origin, offset):
    poses = np.asarray(poses, dtype=float).reshape((-1, 2))
    a = poses[:, 0]
    dx, dy, dz = offset
    carried_offset = np.column_stack((np.full(len(a), dx),
                                     np.cos(a)*dy-np.sin(a)*dz,
                                     np.sin(a)*dy+np.cos(a)*dz))
    return matrices(poses), np.asarray(origin)+carried_offset


def inverse_points(point, r, translated_origin, offset):
    return np.einsum('nji,nj->ni', r, np.asarray(point)-translated_origin)+offset


def forward_points(point, r, translated_origin, offset):
    return translated_origin+np.einsum('nij,j->ni', r, np.asarray(point)-offset)


def pose_grid(limit_deg, step_deg=1.0, boundary_deg=5.0):
    """Build the grid and independently parameterize its spherical boundary."""
    theta = math.radians(limit_deg)
    count = math.floor(limit_deg/step_deg+1e-12)
    rows = {}
    def add(a, b):
        rows[(round(a, 12), round(b, 12))] = (a, b)
    for i, j in itertools.product(range(-count, count+1), repeat=2):
        a, b = math.radians(i*step_deg), math.radians(j*step_deg)
        if math.cos(a)*math.cos(b) >= math.cos(theta)-1e-14:
            add(a, b)
    for j in range(math.ceil(360/boundary_deg)):
        phi = math.radians(j*boundary_deg)
        nx = math.sin(theta)*math.cos(phi)
        ny = math.sin(theta)*math.sin(phi)
        cb = math.sqrt(max(0, 1-nx*nx))
        b = math.atan2(nx, cb)
        a = math.asin(max(-1, min(1, -ny/cb)))
        add(a, b)
    return np.asarray([rows[k] for k in sorted(rows)])


def body_grid(max_deg, polar_deg, azimuth_deg):
    polar = [j*polar_deg for j in range(math.floor(max_deg/polar_deg)+1)]
    polar = sorted(set(polar+[0.0, max_deg]))
    azimuth = [j*azimuth_deg for j in range(math.ceil(360/azimuth_deg))
               if j*azimuth_deg < 360]
    labels, vectors = [], []
    for g in polar:
        for a in ([0.0] if g == 0 else azimuth):
            gg, aa = math.radians(g), math.radians(a)
            labels.append((g, a))
            vectors.append((math.sin(gg)*math.cos(aa), math.sin(gg)*math.sin(aa), math.cos(gg)))
    dg = max((b-a for a, b in zip(polar, polar[1:])), default=0)/2
    da = max(b-a for a, b in zip(azimuth, azimuth[1:]+[azimuth[0]+360]))/2
    cover = 2*math.sin(math.radians(dg)/2)+2*math.sin(math.radians(max_deg))*math.sin(math.radians(da)/2)
    return labels, np.asarray(vectors), cover


def primitive(identity, group, a, b, radius):
    return dict(id=identity, group=group, a_C_m=list(a), b_C_m=list(b), radius_m=radius)


def geometry(seed, landing, prop):
    g = CFG['geometry_hypotheses']
    leg_radius = max(p['od_mm'] for p in CFG['supplier_candidates'] if 'leg' in p['roles'])/2000
    spine_radius = max(p['od_mm'] for p in CFG['supplier_candidates'] if 'spine' in p['roles'])/2000
    fixed, feet = [], []
    for j, azimuth in enumerate(landing['azimuths_deg']):
        az = math.radians(azimuth)
        xy = np.asarray([math.cos(az), math.sin(az)])
        root = np.r_[xy*seed['leg_attachment_radius_mm']/1000, seed['leg_attachment_z_mm']/1000]
        socket = np.r_[xy*seed['foot_radius_mm']/1000, g['foot_tube_socket_reference_z_mm']/1000]
        axis = (root-socket)/np.linalg.norm(root-socket)
        a = socket-axis*g['leg_foot_insertion_extension_mm']/1000
        b = root+axis*g['leg_root_insertion_extension_mm']/1000
        fixed.append(primitive('leg_'+str(j), 'legs', a, b, leg_radius))
        foot = np.r_[socket[:2], g['foot_centre_z_mm']/1000]
        feet.append(foot)
        fixed.append(primitive('foot_'+str(j), 'feet', foot, foot, g['foot_contact_radius_mm']/1000))
    z = (seed['leg_attachment_z_mm']+g['spine_lower_end_above_leg_attachment_mm'])/1000
    length = max(g['spine_finished_lengths_mm'])/1000
    for layout in g['spine_layouts']:
        xy = layout.get('xy_mm')
        if xy is None:
            xy = [[layout['radius_mm']*math.cos(math.radians(t)),
                   layout['radius_mm']*math.sin(math.radians(t))] for t in layout['azimuths_deg']]
        require(len(xy) == layout['count'], 'Spine count')
        for j, (x, y) in enumerate(xy):
            fixed.append(primitive(layout['id']+'_spine_'+str(j), 'spines_'+layout['id'],
                                   [x/1000, y/1000, z], [x/1000, y/1000, z+length], spine_radius))
    y = g['moving_support_topology_hypothesis']
    require(y['yoke_upright_module_azimuths_deg'] == [0, 180], 'Unsupported yoke hypothesis')
    x = prop['diameter_mm']/2000+y['yoke_upright_centre_radius_beyond_propeller_tip_mm']/1000
    h = (seed['upper_rotor_drop_from_pivot_mm']+seed['rotor_plane_separation_mm']/2)/1000
    radius = y['yoke_upright_screening_outer_radius_mm']/1000
    moving = [primitive('yoke_left', 'moving_yoke', [-x,0,0], [-x,0,-h], radius),
              primitive('yoke_right', 'moving_yoke', [x,0,0], [x,0,-h], radius),
              primitive('yoke_top_crossmember', 'moving_yoke', [-x,0,0], [x,0,0], radius),
              primitive('yoke_carrier', 'moving_yoke', [-x,0,-h], [x,0,-h], radius)]
    return fixed, moving, np.asarray(feet)


def compare_primitives(actual, expected):
    aa, ee = indexed(actual), indexed(expected)
    require(set(aa) == set(ee), 'Primitive coverage')
    for key, value in ee.items():
        require(aa[key]['group'] == value['group'], 'Primitive ownership')
        for field in ('a_C_m', 'b_C_m', 'radius_m'):
            near(aa[key][field], value[field], key+' '+field, 1e-12)


def cylinder_distance(points, centre, radius, half):
    q = np.asarray(points)-centre
    radial = np.maximum(np.hypot(q[..., 0], q[..., 1])-radius, 0)
    axial = np.maximum(np.abs(q[..., 2])-half, 0)
    return np.hypot(radial, axial)


def cylinder_segment_min(a, b, centre, radius, half):
    """Independent convex one-dimensional minimization, vectorized by pose.

    Distance to a closed convex cylinder is convex along an affine segment.
    Ternary bracketing shrinks the minimizer interval. The residual half interval
    times segment length bounds remaining location error in exact arithmetic.
    A separate numerical tolerance accounts for ordinary floating-point tests.
    """
    a, b = np.atleast_2d(a), np.atleast_2d(b)
    delta = b-a
    left, right = np.zeros(len(a)), np.ones(len(a))
    for unused in range(60):
        u, v = (2*left+right)/3, (left+2*right)/3
        fu = cylinder_distance(a+u[:, None]*delta, centre, radius, half)
        fv = cylinder_distance(a+v[:, None]*delta, centre, radius, half)
        keep_left = fu <= fv
        left, right = np.where(keep_left, left, u), np.where(keep_left, v, right)
    middle = cylinder_distance(a+((left+right)/2)[:, None]*delta, centre, radius, half)
    best = np.minimum(middle, np.minimum(cylinder_distance(a, centre, radius, half),
                                        cylinder_distance(b, centre, radius, half)))
    residual = np.linalg.norm(delta, axis=1)*(right-left)/2+1e-12
    return best-residual, best+residual


def segment_segment_min(a, b, c, d):
    """Constrained quadratic minimum: four edges and the interior stationary point."""
    a, b = np.atleast_2d(a), np.atleast_2d(b)
    c, d = np.broadcast_to(c, a.shape), np.broadcast_to(d, a.shape)
    u, v, w = b-a, d-c, a-c
    A, B, C = np.sum(u*u, 1), np.sum(u*v, 1), np.sum(v*v, 1)
    D, E = np.sum(u*w, 1), np.sum(v*w, 1)
    def div(numerator, denominator):
        return np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator != 0)
    def distance(s, t):
        return np.linalg.norm(w+s[:, None]*u-t[:, None]*v, axis=1)
    z, o = np.zeros(len(a)), np.ones(len(a))
    values = [distance(z, np.clip(div(E, C), 0, 1)),
              distance(o, np.clip(div(E+B, C), 0, 1)),
              distance(np.clip(div(-D, A), 0, 1), z),
              distance(np.clip(div(B-D, A), 0, 1), o)]
    det = A*C-B*B
    s, t = div(B*E-C*D, det), div(A*E-B*D, det)
    valid = (det > 1e-14*A*C) & (det > 0) & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
    values.append(np.where(valid, distance(s, t), np.inf))
    answer = np.min(values, axis=0)
    require(np.isfinite(answer).all(), 'Nonfinite segment distance')
    return answer-1e-12, answer+1e-12


def coverage():
    g, contract, nc = CFG['geometry_hypotheses'], CFG['clearance_evaluation_contract'], RESULT['numerical_controls']
    require(nc['gimbal_grid_step_deg'] == 1 and nc['gimbal_boundary_azimuth_step_deg'] == 5, 'Unexpected gimbal sampling')
    require(nc['spatial_step_mm'] == 4 and nc['body_polar_step_deg'] == 1, 'Study resolution identity')
    near(nc['numerical_distance_debit_m'], EPS, 'Numerical debit', 1e-15)
    require(CFG['units_and_frames']['R_BC'] == [[1,0,0],[0,-1,0],[0,0,-1]], 'Frame configuration')
    require(RESULT['frame_and_kinematics']['R_BC'] == CFG['units_and_frames']['R_BC'], 'Frame provenance')
    require(RESULT['frame_and_kinematics']['R_BM'] == 'Rx(alpha) Ry(beta)', 'Gimbal order')
    near(RESULT['frame_and_kinematics']['neutral_offset_body_m'], [0,0,0.02], 'Offset unit/frame conversion', 1e-12)
    poses = {}
    for limit in g['gimbal_resultant_cone_limits_deg']:
        actual = np.asarray([[r['alpha_rad'],r['beta_rad']] for r in RESULT['gimbal_pose_samples'][str(limit)]])
        expected = pose_grid(limit)
        require(len({tuple(np.round(p,12)) for p in actual}) == len(actual), 'Duplicate pose')
        require({tuple(np.round(p,12)) for p in actual} == {tuple(np.round(p,12)) for p in expected}, 'Incomplete pose domain')
        require(np.all(np.abs(actual) <= math.radians(limit)+1e-12), 'Pose outside near-neutral branch')
        require(np.all(np.cos(actual[:,0])*np.cos(actual[:,1]) >= math.cos(math.radians(limit))-1e-12), 'Pose outside cone')
        poses[limit] = actual
    require(set(RESULT['gimbal_pose_samples']) == {str(x) for x in poses}, 'Unexpected cone')
    labels, k, kcover = body_grid(max(contract['landing_body_tilt_deg']), 1, contract['landing_tilt_azimuth_step_deg'])
    rows = RESULT['body_vertical_samples']
    require([(r['tilt_deg'],r['vertical_azimuth_deg']) for r in rows] == labels, 'Body sample coverage')
    near([r['vertical_covector_C'] for r in rows], k, 'Body vertical directions', 1e-12)
    near(nc['body_vertical_covector_cover'], kcover, 'Body covering debit', 1e-12)
    combinations = list(itertools.product(g['layout_seeds'], g['landing_arrangements'], g['propeller_envelopes'],
                                          g['gimbal_resultant_cone_limits_deg'], g['rotor_swept_slab_half_thickness_mm']))
    cases = indexed(RESULT['cases'])
    require(len(cases) == RESULT['case_count'] == len(combinations), 'Case count')
    for seed, landing, prop, cone, half in combinations:
        identity = '|'.join([seed['id'],landing['id'],prop['id'],'cone_'+str(cone),'half_'+str(half)])
        case = cases[identity]
        for field, value in [('seed',seed['id']),('landing_arrangement',landing['id']),('propeller_envelope',prop['id']),
                             ('resultant_cone_deg',cone),('rotor_slab_half_thickness_mm',half)]:
            require(case[field] == value, identity+' field '+field)
        fixed, moving, feet = geometry(seed, landing, prop)
        compare_primitives(case['static_capsule_hypotheses'], fixed)
        compare_primitives(case['module_carried_capsule_hypotheses_relative_to_outer_at_neutral'], moving)
        origin, offset = np.asarray([0,0,seed['pivot_z_mm']/1000]), np.asarray([0,0,-0.02])
        near(case['outer_origin_C_m'], origin, 'Outer origin', 1e-12)
        near(case['outer_to_inner_neutral_C_m'], offset, 'Joint displacement', 1e-12)
        drop, spacing = seed['upper_rotor_drop_from_pivot_mm']/1000, seed['rotor_plane_separation_mm']/1000
        centres = {'U':np.asarray([0,0,-drop]), 'L':np.asarray([0,0,-drop-spacing])}
        require(set(case['neutral_rotor_centres_relative_to_outer_C_m']) == set(centres), 'Rotor identities')
        for name, value in centres.items():
            near(case['neutral_rotor_centres_relative_to_outer_C_m'][name], value, 'Rotor centre', 1e-12)
        near(case['rotor_to_rotor_axial_slab_gap_m'], spacing-2*half/1000, 'Rotor slab separation', 1e-12)
        require(case['complete_geometry_acceptance'] is None, 'Case acceptance')
        fixed, moving = indexed(fixed), indexed(moving)
        pairs = indexed(case['moving_to_fixed_screens'], 'pair')
        require(set(pairs) == {a+'::'+b for a in list(centres)+list(moving) for b in fixed}, 'Moving/fixed pair coverage')
        invariant = indexed(case['rotor_to_yoke_invariant_screens'], 'pair')
        require(set(invariant) == {a+'::'+b for a in centres for b in moving}, 'Invariant pair coverage')
        ground = indexed(case['ground_screens'], 'pair')
        require(set(ground) == {'U::level_ground','L::level_ground'}, 'Ground coverage')
        CONTEXTS.append(dict(case=case, fixed=fixed, moving=moving, centres=centres, feet=feet, origin=origin,
                             offset=offset, poses=poses[cone], k=k, klabels=labels, kcover=kcover, pairs=pairs,
                             invariant=invariant, ground=ground, radius=prop['diameter_mm']/2000,
                             half=half/1000, reference_minima={}))
    METRICS['case_count'] = len(CONTEXTS)
    METRICS['gimbal_pose_counts'] = {str(key):len(value) for key,value in poses.items()}
    METRICS['body_pose_count'] = len(labels)


def extent_and_cover(ctx, moving):
    d = ctx['offset']
    if moving in ctx['centres']:
        q = ctx['centres'][moving]-d
        extent = math.hypot(np.hypot(q[0],q[1])+ctx['radius'], abs(q[2])+ctx['half'])
    else:
        item = ctx['moving'][moving]
        extent = max(np.linalg.norm(np.asarray(item['a_C_m'])-d),np.linalg.norm(np.asarray(item['b_C_m'])-d))+item['radius_m']
    cover = 2*math.sin(math.radians(1)/2)*(np.linalg.norm(d)+2*extent)
    return extent, cover


def pair_reference(ctx, pair, preparation):
    moving, fixed = pair.split('::')
    item = ctx['fixed'][fixed]
    r, origin = preparation
    a = inverse_points(item['a_C_m'],r,origin,ctx['offset'])
    b = inverse_points(item['b_C_m'],r,origin,ctx['offset'])
    radius = item['radius_m']
    if moving in ctx['centres']:
        lo,hi = cylinder_segment_min(a,b,ctx['centres'][moving],ctx['radius'],ctx['half'])
    else:
        other = ctx['moving'][moving]
        lo,hi = segment_segment_min(a,b,other['a_C_m'],other['b_C_m'])
        radius += other['radius_m']
    return lo-radius,hi-radius


def pose_index(poses, witness):
    target = np.asarray([witness['alpha_rad'],witness['beta_rad']])
    matches = np.flatnonzero(np.max(np.abs(poses-target),axis=1) < 2e-11)
    require(len(matches) == 1, 'Witness must identify one tested pose')
    return int(matches[0])


def row_consistency(row, debit):
    lo,hi = row['minimum_sampled_lower_bound_m'],row['minimum_sampled_upper_bound_m']
    require(math.isfinite(lo) and math.isfinite(hi) and lo <= hi+TOL, 'Invalid reported interval')
    near(row['travel_cover_debit_m'],debit,'Travel covering debit',1e-12)
    near(row['continuous_domain_lower_bound_m'],lo-debit,'Continuous bound arithmetic',1e-12)
    threshold = RESULT['study_clearance_threshold_mm']/1000
    state = ('rigid_hypothesis_lower_bound_meets_study_threshold' if lo-debit >= threshold else
             'sampled_outer_envelope_overlap_or_touch' if hi <= 0 else 'inconclusive_at_study_threshold')
    require(row['screen_classification'] == state, 'Classification arithmetic')
    require(row['physical_acceptance'] is None, 'Unsupported physical acceptance')
    require(row['methods'], 'Missing method disclosure')


def check_interval(row, lo, hi, debit, poses=None):
    row_consistency(row,debit)
    got_lo,got_hi = row['minimum_sampled_lower_bound_m'],row['minimum_sampled_upper_bound_m']
    require(got_lo <= float(np.min(lo))+TOL, 'Lower bound exceeds independent minimum: '+row['pair'])
    require(got_hi >= float(np.min(hi))-TOL, 'Upper bound below independent minimum: '+row['pair'])
    if poses is not None:
        i = pose_index(poses,row['lower_bound_witness'])
        j = pose_index(poses,row['upper_bound_witness'])
        require(got_lo <= float(lo[i])+TOL,'Invalid lower-bound witness')
        require(got_hi >= float(hi[j])-TOL,'Invalid upper-bound witness')
    METRICS['checked_distance_rows'] = METRICS.get('checked_distance_rows',0)+1
    METRICS['largest_reported_sampled_interval_width_m'] = max(METRICS.get('largest_reported_sampled_interval_width_m',0),got_hi-got_lo)


def distance_checks():
    for ctx in CONTEXTS:
        preparation = prepare(ctx['poses'],ctx['origin'],ctx['offset'])
        for pair,row in ctx['pairs'].items():
            lo,hi = pair_reference(ctx,pair,preparation)
            cover = extent_and_cover(ctx,pair.split('::')[0])[1]
            check_interval(row,lo,hi,cover,ctx['poses'])
            ctx['reference_minima'][pair] = float(np.min((lo+hi)/2))
        for pair,row in ctx['invariant'].items():
            rotor,yoke = pair.split('::')
            item = ctx['moving'][yoke]
            lo,hi = cylinder_segment_min(item['a_C_m'],item['b_C_m'],ctx['centres'][rotor],ctx['radius'],ctx['half'])
            check_interval(row,lo-item['radius_m'],hi-item['radius_m'],0)
        print('Checked distance bounds: '+ctx['case']['id'],file=sys.stderr)


def ground_values(ctx, rotor, poses, k):
    r,origin = prepare(poses,ctx['origin'],ctx['offset'])
    centre = forward_points(ctx['centres'][rotor],r,origin,ctx['offset'])
    normal = r[:,:,2]
    cosine = np.clip(normal@k.T,-1,1)
    support = centre@k.T-ctx['radius']*np.sqrt(np.maximum(0,1-cosine*cosine))-ctx['half']*np.abs(cosine)
    foot_radius = CFG['geometry_hypotheses']['foot_contact_radius_mm']/1000
    lowest_foot = np.min(ctx['feet']@k.T,axis=0)-foot_radius
    return support-lowest_foot


def ground_checks():
    contract = CFG['clearance_evaluation_contract']
    for ctx in CONTEXTS:
        for rotor in ctx['centres']:
            row = ctx['ground'][rotor+'::level_ground']
            values = ground_values(ctx,rotor,ctx['poses'],ctx['k'])
            minimum = float(np.min(values))
            extent,cover = extent_and_cover(ctx,rotor)
            body_radius = np.linalg.norm(ctx['origin'])+np.linalg.norm(ctx['offset'])+extent+max(np.linalg.norm(f) for f in ctx['feet'])
            row_consistency(row,cover+ctx['kcover']*body_radius)
            near(row['minimum_sampled_lower_bound_m'],minimum-EPS,'Ground sample minimum')
            near(row['minimum_sampled_upper_bound_m'],minimum+EPS,'Ground sample maximum bound')
            for field in ('lower_bound_witness','upper_bound_witness'):
                w = row[field]
                i = pose_index(ctx['poses'],w)
                label = (w['body_tilt_deg'],w['vertical_azimuth_deg'])
                require(label in ctx['klabels'],'Ground witness body pose')
                j = ctx['klabels'].index(label)
                near(values[i,j],minimum,'Ground witness minimum')
            debit_rows = row['ground_consumption_sensitivities']
            require([x['additional_debit_mm'] for x in debit_rows] == contract['additional_ground_clearance_consumption_sensitivity_mm'],'Ground debit coverage')
            for item in debit_rows:
                near(item['continuous_rigid_lower_bound_after_debit_m'],row['continuous_domain_lower_bound_m']-item['additional_debit_mm']/1000,'Ground debit arithmetic',1e-12)
                require(item['basis'],'Missing debit qualification')
            ctx['reference_minima'][rotor+'::level_ground'] = minimum
    METRICS['checked_ground_rows'] = 2*len(CONTEXTS)


def independent_reference_fixtures():
    for a,b,expected in [([2,0,-1],[2,0,1],1),([-2,0,0],[2,0,0],0),
                         ([0,0,2],[0,0,3],1.5),([2,0,1.5],[2,0,1.5],math.sqrt(2))]:
        lo,hi = cylinder_segment_min(a,b,np.zeros(3),1,0.5)
        require(lo[0]-TOL <= expected <= hi[0]+TOL,'Cylinder analytical fixture')
    for a,b,c,d,expected in [([-1,0,0],[1,0,0],[0,-1,0],[0,1,0],0),
                             ([0,0,0],[1,0,0],[0,2,0],[1,2,0],2),
                             ([0,0,0],[0,0,0],[1,0,0],[1,0,0],1)]:
        lo,hi = segment_segment_min(a,b,c,d)
        require(lo[0]-TOL <= expected <= hi[0]+TOL,'Segment analytical fixture')
    # Upright cylinder over level feet: bottom height minus contact plane.
    context = dict(origin=np.asarray([0,0,0.4]),offset=np.asarray([0,0,-0.02]),
                   centres={'L':np.asarray([0,0,-0.2])},radius=0.15,half=0.01,
                   feet=np.asarray([[0.3,0,0.005],[-0.3,0,0.005],[0,0.3,0.005]]))
    require(CFG['geometry_hypotheses']['foot_contact_radius_mm'] == 5,'Fixture foot-radius premise')
    near(ground_values(context,'L',np.asarray([[0,0]]),np.asarray([[0,0,1]])),[[0.19]],'Level-ground support fixture')


def source_function_fixtures():
    spec = importlib.util.spec_from_file_location('r12_clearance_under_test',BASE/'structural_clearance_screen_01.py')
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
    poses = np.asarray([[0,0],[0.2,-0.15],[-0.1,0.3],[math.pi/2,0],[0,math.pi/2]])
    r = matrices(poses)
    for i,(a,b) in enumerate(poses):
        near(module.rotation(float(a),float(b)),r[i],'Source rotation fixture',1e-12)
        near(r[i]@r[i].T,np.eye(3),'Orthogonal rotation',1e-12)
        near(np.linalg.det(r[i]),1,'Proper rotation',1e-12)
    # Noncoincident origins in all axes; test round trips and conservative motion coverage.
    rng = np.random.default_rng(12011)
    maximum_ratio = 0.0
    for unused in range(200):
        a,b = rng.uniform(-0.17,0.17,2)
        p = np.asarray([[a,b],[math.trunc(a/math.radians(1))*math.radians(1),math.trunc(b/math.radians(1))*math.radians(1)]])
        origin,offset,point = rng.uniform(-0.4,0.4,3),rng.uniform(-0.03,0.03,3),rng.uniform(-0.2,0.2,3)
        rr,oo = prepare(p,origin,offset)
        world = forward_points(point,rr,oo,offset)
        for j in range(2):
            near(inverse_points(world[j],rr[j:j+1],oo[j:j+1],offset)[0],point,'Noncoincident round trip',1e-12)
        radius = float(np.linalg.norm(point-offset))
        bound = 2*math.sin(math.radians(1)/2)*(float(np.linalg.norm(offset))+2*radius)
        near(module.pose_cover_m(tuple(offset),radius,math.radians(1)),bound,'Source covering expression',1e-12)
        displacement = float(np.linalg.norm(world[0]-world[1]))
        require(displacement <= bound+TOL,'Motion bound fixture')
        maximum_ratio = max(maximum_ratio,displacement/bound)
    METRICS['fixture_maximum_displacement_to_cover_ratio'] = maximum_ratio
    a,b,c = (-0.2,-0.1,0.2),(0.2,0.1,0),np.zeros(3)
    lo,hi = cylinder_segment_min(a,b,c,0.1,0.03)
    widths = []
    for step in (0.02,0.01,0.005):
        lower,upper,method = module.segment_cylinder_bounds(a,b,tuple(c),0.1,0.03,math.inf,step)
        require(lower <= hi[0]+TOL and upper >= lo[0]-TOL,'Source spatial bounds fixture')
        require(upper-lower <= step/2+TOL,'Spatial covering width')
        widths.append(upper-lower)
    METRICS['fixture_spatial_interval_widths_m'] = widths
    for fn,args in [(module.cone_poses,(0,)),(module.cone_poses,(90,)),(module.cone_poses,(10,0)),
                    (module.body_vertical_samples,(90,1,15)),(module.body_vertical_samples,(5,0,15))]:
        try:
            fn(*args)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid sampling input was not rejected')
    # Intentional collision fixtures violate the vehicle layout on purpose.
    g = CFG['geometry_hypotheses']
    seed = dict(g['layout_seeds'][0],leg_attachment_radius_mm=0,foot_radius_mm=0)
    body = [dict(tilt_deg=0,vertical_azimuth_deg=0,vertical_covector_C=(0,0,1))]
    fixture = module.analyze_case(seed,g['landing_arrangements'][0],g,g['propeller_envelopes'][0],10,5,
                                  (0,0,-0.02),[(0,0)],body,0,0.005,0.007,0.004)
    collision = indexed(fixture['moving_to_fixed_screens'],'pair')['U::leg_0']
    require(collision['minimum_sampled_upper_bound_m'] < 0,'Deliberate rotor/leg collision undetected')
    require(collision['screen_classification'] == 'sampled_outer_envelope_overlap_or_touch','Collision misclassified')
    seed['pivot_z_mm'] = seed['upper_rotor_drop_from_pivot_mm']+seed['rotor_plane_separation_mm']-30
    fixture = module.analyze_case(seed,g['landing_arrangements'][0],g,g['propeller_envelopes'][0],10,5,
                                  (0,0,-0.02),[(0,0)],body,0,0.005,0.007,0.004)
    ground = indexed(fixture['ground_screens'],'pair')['L::level_ground']
    require(ground['minimum_sampled_upper_bound_m'] < -0.03,'Deliberate ground collision undetected')


def finer_sampling():
    g,contract = CFG['geometry_hypotheses'],CFG['clearance_evaluation_contract']
    maximum_cone = max(g['gimbal_resultant_cone_limits_deg'])
    maximum_half = max(g['rotor_swept_slab_half_thickness_mm'])
    unused,kfine,unused_cover = body_grid(max(contract['landing_body_tilt_deg']),0.5,
                                         contract['landing_tilt_azimuth_step_deg']/2)
    largest_pair_change = largest_ground_change = 0.0
    pairs_checked = cases_checked = 0
    for ctx in CONTEXTS:
        case = ctx['case']
        if case['resultant_cone_deg'] != maximum_cone or case['rotor_slab_half_thickness_mm'] != maximum_half:
            continue
        # Union preserves every original pose, avoiding false monotonicity assumptions.
        union = {tuple(np.round(p,12)):tuple(p) for p in pose_grid(maximum_cone,0.5,2.5)}
        union.update({tuple(np.round(p,12)):tuple(p) for p in ctx['poses']})
        fine = np.asarray(list(union.values()))
        preparation = prepare(fine,ctx['origin'],ctx['offset'])
        groups = [
            [p for p in ctx['pairs'] if p.startswith(('U::leg_','L::leg_'))],
            [p for p in ctx['pairs'] if p.startswith('yoke_') and '::leg_' in p],
            [p for p in ctx['pairs'] if p.startswith('yoke_') and '::S' in p],
        ]
        for group in groups:
            pair = min(group,key=lambda p:ctx['reference_minima'][p])
            lo,hi = pair_reference(ctx,pair,preparation)
            minimum = float(np.min((lo+hi)/2))
            original = ctx['reference_minima'][pair]
            require(minimum <= original+TOL,'Nested distance samples increased minimum')
            require(float(np.min(lo)) >= ctx['pairs'][pair]['continuous_domain_lower_bound_m']-TOL,
                    'Finer samples violate reported continuous bound: '+case['id']+' '+pair)
            largest_pair_change = max(largest_pair_change,original-minimum)
            pairs_checked += 1
        for rotor in ctx['centres']:
            minimum = float(np.min(ground_values(ctx,rotor,fine,kfine)))
            pair = rotor+'::level_ground'
            original = ctx['reference_minima'][pair]
            require(minimum <= original+TOL,'Nested ground samples increased minimum')
            require(minimum >= ctx['ground'][pair]['continuous_domain_lower_bound_m']-TOL,
                    'Finer ground samples violate reported continuous bound')
            largest_ground_change = max(largest_ground_change,original-minimum)
        cases_checked += 1
    METRICS.update(finer_sampling_case_count=cases_checked,finer_sampling_selected_pair_count=pairs_checked,
                   maximum_observed_pair_minimum_change_m=largest_pair_change,
                   maximum_observed_ground_minimum_change_m=largest_ground_change)
    require(cases_checked > 0 and pairs_checked == 3*cases_checked,'Finer sampling coverage')


def unchanged_inputs():
    for name,digest in EXPECTED.items():
        require(hashlib.sha256((BASE/name).read_bytes()).hexdigest() == digest,'Input changed during verification: '+name)


def main():
    global np
    try:
        with contextlib.redirect_stdout(sys.stderr):
            import numpy as numpy_module
        np = numpy_module
        CHECKS['numpy_import_capability'] = True
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        print(json.dumps(dict(outcome='inconclusive',explanation='NumPy import failed; no artifact or geometry checks were performed. Request installation assistance rather than changing the environment.',checks={'numpy_import_capability':False,'geometry_checks':None})))
        return
    check('artifact_hashes_provenance_and_scope',load_inputs)
    if CHECKS['artifact_hashes_provenance_and_scope']:
        check('independent_distance_and_ground_reference_fixtures',independent_reference_fixtures)
        check('geometry_units_frames_and_case_coverage',coverage)
        check('source_rotation_cover_collision_and_invalid_input_fixtures',source_function_fixtures)
        if CHECKS.get('geometry_units_frames_and_case_coverage') and CHECKS.get('independent_distance_and_ground_reference_fixtures'):
            check('all_stored_moving_fixed_and_invariant_distance_bounds',distance_checks)
            check('all_stored_ground_support_bounds_and_witnesses',ground_checks)
            if CHECKS.get('all_stored_moving_fixed_and_invariant_distance_bounds') and CHECKS.get('all_stored_ground_support_bounds_and_witnesses'):
                check('selected_actual_cases_finer_sampling_respects_bounds',finer_sampling)
        check('tested_inputs_unchanged',unchanged_inputs)
    for name in ('actual_FCStd_STEP_solids_and_mounting_interfaces','omitted_components_and_loaded_clearances',
                 'material_joint_and_landing_strength','complete_vehicle_mass_energy_and_budget','physical_validation'):
        CHECKS[name] = None
    failed = any(value is False for value in CHECKS.values())
    explanation = ('One or more numerical/artifact checks failed; do not rely on the clearance study until corrected. ' if failed else
                   'Executed numerical and artifact checks passed within the declared scope; overall engineering acceptance remains inconclusive. ')
    explanation += ('The checked objects are unselected rigid-envelope hypotheses, not actual complete CAD or hardware. '
                    'Negative lower bounds alone are not collisions. Outer-envelope overlap is not automatically actual hollow-tube intersection. '
                    'Finer sampling covers selected limiting pairs and ground cases; measured changes are reported, not a physical convergence claim. '
                    'Continuous bounds rely on the documented near-neutral angular domain and geometric covering arguments, not formal interval arithmetic. '
                    'No new supplier, strength, budget, review or flight acceptance is established. Metrics: '+json.dumps(METRICS,separators=(',',':'),allow_nan=False))
    if ERRORS:
        explanation += ' Errors: '+'; '.join(ERRORS)
    print(json.dumps(dict(outcome='failed' if failed else 'inconclusive',explanation=explanation,checks=CHECKS),allow_nan=False))


if __name__ == '__main__':
    main()
