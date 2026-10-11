'''PDR-r12 CAD-first braced landing-gear candidates.

Run ONLY through the supplied headless freecad_run backend.
This is a candidate generator and measurement recorder, NOT a verification
program or a selected/fabrication-ready vehicle. No structural solver is run.

Native FCStd contains editable Part::Cylinder/Part::Cut tube features and
nested App::Part gimbal placements. Tube radii are spreadsheet-driven; bore
height follows outer-cylinder height. Node coordinates/orientations are
configuration-derived at generation, not a fully constrained CAD sketch.
Edit configuration and regenerate into a fresh RUN_TAG to change topology.

STEP exports contain nominal physical tube components ONLY. Rotor slabs,
yoke capsules, joint spheres, contact markers and the attachment-ring guide
are references, never hardware or mass. Ideal chord-length braces can
interpenetrate at proposed junctions: report those intersections, do not
silently invent trimming, fittings, adhesive joints or mounting interfaces.

All exports must be declared in the subsequent freecad_run.outputs list:
eight candidate IDs, each with .FCStd, _tubes.step and _arrangement.svg;
plus cad_measurements_01.json and output_manifest_01.json in OUT.
'''

import hashlib
import itertools
import json
import math
import os
from pathlib import Path
from xml.sax.saxutils import escape

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
SOURCE = ROOT / 'cad/pdr_r12_chief/build_braced_candidates_01.py'
CONFIG = ROOT / 'analysis/pdr_r12_chief/braced_leg_study_config_01.json'
CONFIG_SHA256 = '8e5f5c75aea67512ffe8d4371c21d1915640b5aea06df2346d28df13eeadb048'
RUN_TAG = 'braced_candidates_01'
OUT = ROOT / 'cad/pdr_r12_chief' / RUN_TAG
TOPOLOGY_ID = 'B45_F080'
SPINE_LENGTH_MM = 300.0
SPINE_BOTTOM_ABOVE_RING_MM = 20.0
SLAB_HALF_THICKNESS_MM = 10.0
JOINT_ENVELOPE_RADIUS_MM = 20.0
YOKE_ENVELOPE_RADIUS_MM = 7.0
YOKE_OUTBOARD_OFFSET_MM = 30.0
OVERLAP_REPORT_THRESHOLD_MM3 = 1e-7
S = (1.0, -1.0, -1.0)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def v(a):
    return App.Vector(*[float(x) for x in a])


def xyz(a):
    return [float(a.x), float(a.y), float(a.z)]


def add(a, b):
    return [a[i] + b[i] for i in range(3)]


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def scale(a, k):
    return [k * x for x in a]


def norm(a):
    return math.sqrt(sum(x*x for x in a))


def radial(r, phi_deg, z):
    p = math.radians(phi_deg)
    return [r * math.cos(p), r * math.sin(p), z]


def hidden(obj):
    if getattr(obj, 'ViewObject', None) is not None:
        obj.ViewObject.Visibility = False


def classify(obj, scope):
    obj.addProperty('App::PropertyString', 'EvidenceScope', 'Provenance')
    obj.EvidenceScope = scope


def world_shape(obj):
    # Shape already includes the leaf object's Placement. Apply ancestors
    # only, avoiding double rotation/translation of the leaf geometry.
    shape = obj.Shape.copy()
    ancestors = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    shape.Placement = ancestors.multiply(shape.Placement)
    return shape


def parameters(doc):
    sheet = doc.addObject('Spreadsheet::Sheet', 'Parameters')
    values = [('Rout_08', '4 mm'), ('Rin_08', '3 mm'), ('Rout_14', '7 mm'),
              ('Rin_14', '6 mm'), ('SpineLength', str(SPINE_LENGTH_MM) + ' mm')]
    for row, (alias, value) in enumerate(values, 1):
        sheet.set('A' + str(row), alias)
        sheet.set('B' + str(row), value)
        sheet.setAlias('B' + str(row), alias)
    return sheet


def tube(doc, group, name, a, b, section, role, height_expression=None):
    delta = sub(b, a)
    length = norm(delta)
    if length <= 0:
        raise ValueError('Nonpositive tube length: ' + name)
    outer = doc.addObject('Part::Cylinder', name + '_Outer')
    inner = doc.addObject('Part::Cylinder', name + '_Bore')
    outer.setExpression('Radius', 'Parameters.' + ('Rout_08' if section == '08_06' else 'Rout_14'))
    inner.setExpression('Radius', 'Parameters.' + ('Rin_08' if section == '08_06' else 'Rin_14'))
    outer.Height = length
    if height_expression:
        outer.setExpression('Height', height_expression)
    inner.Placement.Base = App.Vector(0, 0, -1)
    inner.setExpression('Height', outer.Name + '.Height + 2 mm')
    result = doc.addObject('Part::Cut', name)
    result.Base = outer
    result.Tool = inner
    result.Placement = App.Placement(v(a), App.Rotation(App.Vector(0, 0, 1), v(delta)))
    group.addObject(result)
    classify(result, 'Nominal physical CFRP tube hypothesis; joint machining and retention unresolved')
    result.addProperty('App::PropertyString', 'MemberRole', 'Provenance')
    result.MemberRole = role
    result.addProperty('App::PropertyString', 'SectionNominalMM', 'Provenance')
    result.SectionNominalMM = section
    result.addProperty('App::PropertyVector', 'NominalStartCADmm', 'Provenance')
    result.addProperty('App::PropertyVector', 'NominalEndCADmm', 'Provenance')
    result.NominalStartCADmm = v(a)
    result.NominalEndCADmm = v(b)
    hidden(outer)
    hidden(inner)
    return result, outer


def sphere(doc, group, name, center, radius, scope):
    obj = doc.addObject('Part::Sphere', name)
    obj.Radius = radius
    obj.Placement.Base = v(center)
    group.addObject(obj)
    classify(obj, scope)
    return obj


def cylinder(doc, group, name, a, b, radius, scope):
    obj = doc.addObject('Part::Cylinder', name)
    d = sub(b, a)
    obj.Radius = radius
    obj.Height = norm(d)
    obj.Placement = App.Placement(v(a), App.Rotation(App.Vector(0, 0, 1), v(d)))
    group.addObject(obj)
    classify(obj, scope)
    return obj


def measure_component(obj, density):
    shape = world_shape(obj)
    solids = list(shape.Solids)
    if not solids:
        raise ValueError('Physical component has no solids: ' + obj.Name)
    items = []
    for solid in solids:
        if solid.Volume <= 0:
            raise ValueError('Nonpositive solid volume: ' + obj.Name)
        # Generic Part.Shape/Compound COM and inertia are deliberately unused.
        cm = xyz(solid.CenterOfMass)
        mat = solid.MatrixOfInertia
        raw = [[float(getattr(mat, 'A' + str(i+1) + str(j+1))) for j in range(3)] for i in range(3)]
        rho_mm = density * 1e-9
        items.append({'volume_mm3': float(solid.Volume), 'valid': bool(solid.isValid()),
                      'mass_kg': rho_mm * float(solid.Volume), 'cg_CAD_mm': cm,
                      'I_CG_kg_mm2': [[rho_mm*x for x in row] for row in raw]})
    return {'name': obj.Name, 'section_nominal_mm': obj.SectionNominalMM,
            'role': obj.MemberRole, 'density_assumption_kg_m3': density,
            'shape_valid': bool(shape.isValid()), 'solids': items}


def aggregate(components):
    solids = [s for c in components for s in c['solids']]
    mass = sum(s['mass_kg'] for s in solids)
    cg = [sum(s['mass_kg'] * s['cg_CAD_mm'][i] for s in solids) / mass for i in range(3)]
    inertia = [[0.0]*3 for _ in range(3)]
    for solid in solids:
        d = sub(solid['cg_CAD_mm'], cg)
        d2 = sum(x*x for x in d)
        for i in range(3):
            for j in range(3):
                inertia[i][j] += solid['I_CG_kg_mm2'][i][j] + solid['mass_kg'] * ((d2 if i == j else 0.0) - d[i]*d[j])
    inertia_si = [[x*1e-6 for x in row] for row in inertia]
    return {'scope': 'Sum of nominal separate tube components only; not assembled or complete vehicle mass',
            'mass_kg': mass, 'cg_CAD_mm': cg,
            'I_CAD_about_partial_CG_kg_m2': inertia_si,
            'I_FRD_rotated_about_same_partial_CG_kg_m2': [[S[i]*inertia_si[i][j]*S[j] for j in range(3)] for i in range(3)],
            'complete_vehicle_CG_C0_mm': None, 'complete_vehicle_mass_kg': None,
            'configuration_dependent_vehicle_inertia': None}


def bbox_gap(a, b):
    aa, bb = a.BoundBox, b.BoundBox
    return math.sqrt(sum(max(getattr(aa, ax+'Min')-getattr(bb, ax+'Max'),
                             getattr(bb, ax+'Min')-getattr(aa, ax+'Max'), 0.0)**2
                         for ax in ('X', 'Y', 'Z')))


def physical_intersections(physical):
    shapes = [(o.Name, world_shape(o)) for o in physical]
    hits, errors = [], []
    narrow = 0
    for (na, a), (nb, b) in itertools.combinations(shapes, 2):
        if bbox_gap(a, b) > 1e-7:
            continue
        narrow += 1
        try:
            volume = float(a.common(b).Volume)
            if volume > OVERLAP_REPORT_THRESHOLD_MM3:
                hits.append({'a': na, 'b': nb, 'intersection_volume_mm3': volume})
        except Exception as exc:
            errors.append({'a': na, 'b': nb, 'error': type(exc).__name__ + ': ' + str(exc)})
    return {'pair_count': len(shapes)*(len(shapes)-1)//2, 'narrow_phase_count': narrow,
            'intersections': hits, 'errors': errors,
            'interpretation': 'An intersection is not an accepted joint. Volumes are pairwise and must not be summed as a unique overlap correction. Nominal component mass is not an accepted assembled mass.'}


def poses(cones):
    result = {(0.0, 0.0)}
    for cone in cones:
        theta = math.radians(cone)
        for k in (0.5, 1.0):
            for az_deg in range(0, 360, 15):
                az = math.radians(az_deg)
                alpha = math.asin(math.sin(k*theta) * math.cos(az))
                beta = math.atan2(math.sin(k*theta) * math.sin(az), math.cos(k*theta))
                result.add((round(math.degrees(alpha), 10), round(math.degrees(beta), 10)))
    return sorted(result)


def set_pose(outer, inner, origin, offset, alpha_deg, beta_deg):
    # S Rx(alpha) Ry(beta) S = Rx(alpha) Ry(-beta), S=diag(1,-1,-1).
    # Inner-origin offset is carried by outer rotation, not by both rotations.
    outer.Placement = App.Placement(v(origin), App.Rotation(App.Vector(1, 0, 0), alpha_deg))
    inner.Placement = App.Placement(v(offset), App.Rotation(App.Vector(0, -1, 0), beta_deg))


def sweep(doc, physical, joints, rotors, yoke, outer, inner, geom, contacts, cone_values):
    fixed = [('physical_tubes', o.Name, world_shape(o)) for o in physical]
    fixed += [('assumed_joint_envelopes', o.Name, world_shape(o)) for o in joints]
    minima = {}
    counts = {'distance_evaluations': 0, 'safe_bbox_prunes': 0}
    ground = {'minimum_z_mm': None, 'witness': None}
    errors = []
    pose_list = poses(cone_values)
    body_cases = [(0.0, 0.0)] + [(5.0, float(a)) for a in range(0, 360, 45)]
    origin = geom['outer_joint_origin_CAD_mm']
    offset = geom['neutral_outer_to_inner_origin_CAD_mm']
    try:
        for alpha, beta in pose_list:
            set_pose(outer, inner, origin, offset, alpha, beta)
            doc.recompute()
            moving = [(name, world_shape(obj)) for name, obj in rotors.items()]
            moving.append(('yoke_capsule_envelope', Part.makeCompound([world_shape(o) for o in yoke])))
            for moving_name, shape in moving:
                for category, fixed_name, fixed_shape in fixed:
                    key = moving_name + '__to__' + category
                    old = minima.get(key)
                    if old is not None and bbox_gap(shape, fixed_shape) > old['minimum_distance_mm']:
                        counts['safe_bbox_prunes'] += 1
                        continue
                    try:
                        dist, witnesses, _ = shape.distToShape(fixed_shape)
                        counts['distance_evaluations'] += 1
                        if old is None or dist < old['minimum_distance_mm']:
                            hit = {'minimum_distance_mm': float(dist), 'fixed_component': fixed_name,
                                   'alpha_deg': alpha, 'beta_deg': beta,
                                   'witness_points_CAD_mm': [xyz(p) for p in witnesses[0]] if witnesses else None}
                            if dist <= 1e-7:
                                hit['intersection_volume_mm3'] = float(shape.common(fixed_shape).Volume)
                            minima[key] = hit
                    except Exception as exc:
                        errors.append({'moving': moving_name, 'fixed': fixed_name, 'alpha_deg': alpha,
                                       'beta_deg': beta, 'error': type(exc).__name__ + ': ' + str(exc)})
            for tilt, az in body_cases:
                r = App.Rotation(v(radial(1.0, az, 0.0)), tilt)
                shift = -min(r.multVec(v(p)).z for p in contacts)
                body_placement = App.Placement(App.Vector(0, 0, shift), r)
                for name, rotor in moving[:2]:
                    transformed = rotor.copy()
                    transformed.Placement = body_placement.multiply(transformed.Placement)
                    zmin = float(transformed.BoundBox.ZMin)
                    if ground['minimum_z_mm'] is None or zmin < ground['minimum_z_mm']:
                        ground = {'minimum_z_mm': zmin,
                                  'witness': {'rotor': name, 'alpha_deg': alpha, 'beta_deg': beta,
                                              'body_tilt_deg': tilt, 'body_axis_azimuth_deg': az,
                                              'vertical_shift_mm': shift}}
    finally:
        set_pose(outer, inner, origin, offset, 0.0, 0.0)
        doc.recompute()
    return {'evidence_level': 'Sampled native CAD distances and rotor bounding-box ground minima, not continuous bounds',
            'resultant_cones_deg': cone_values, 'joint_samples_alpha_beta_deg': pose_list,
            'body_ground_samples_tilt_axis_azimuth_deg': body_cases,
            'ground_construction': 'Rotate entire nominal geometry; translate until lowest nominal point foot touches flat Z=0. Other feet may be above ground. No contact dynamics, pad compression or loaded deformation.',
            'rotor_slab_half_thickness_mm': SLAB_HALF_THICKNESS_MM,
            'joint_envelope_radius_mm': JOINT_ENVELOPE_RADIUS_MM,
            'minimum_distances': minima, 'ground': ground, 'counts': counts, 'errors': errors,
            'continuous_clearance': None, 'loaded_clearance': None, 'mounting_interface_acceptance': None}


def arrangement_svg(path, candidate_id, physical, reference_objects, geom):
    # Project actual native shape edges, not a separately reconstructed drawing.
    lines = []
    for style, objects in [('physical', physical), ('reference', reference_objects)]:
        for obj in objects:
            for edge in world_shape(obj).Edges:
                if edge.Degenerated:  # preview fix: sphere pole edges have no length
                    continue
                points = edge.discretize(Number=20)
                if len(points) >= 2:
                    lines.append((style, [xyz(p) for p in points]))
    all_points = [p for _, line in lines for p in line]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="850" viewBox="0 0 1200 850">',
             '<rect width="1200" height="850" fill="white"/>',
             '<g font-family="sans-serif" fill="#111">',
             '<text x="25" y="28" font-size="17">' + escape(candidate_id) + '</text>',
             '<text x="25" y="50" font-size="12">Preliminary arrangement, units mm. Not a manufacturing drawing. No hidden-line removal.</text>',
             '<text x="25" y="70" font-size="12">Dark: nominal CFRP tubes. Orange: non-mass rotor, yoke and joint references; interfaces unresolved.</text>']
    for axes, box, title in [((0, 2), (25, 110, 550, 640), 'CAD X-Z side projection'),
                              ((0, 1), (625, 110, 550, 640), 'CAD X-Y top projection')]:
        i, j = axes
        xmin, xmax = min(p[i] for p in all_points), max(p[i] for p in all_points)
        ymin, ymax = min(p[j] for p in all_points), max(p[j] for p in all_points)
        x, y, w, h = box
        factor = min((w-20)/max(xmax-xmin, 1.0), (h-50)/max(ymax-ymin, 1.0))
        parts.append('<text x="%g" y="%g" font-size="13">%s</text>' % (x, y-12, title))
        for style, points in lines:
            coords = ' '.join('%.3f,%.3f' % (x+10+(p[i]-xmin)*factor, y+10+(ymax-p[j])*factor) for p in points)
            color = '#172a3a' if style == 'physical' else '#bc6800'
            dash = '' if style == 'physical' else ' stroke-dasharray="4 3"'
            parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="0.8"%s/>' % (coords, color, dash))
        parts.append('<path d="M %g %g h %g" stroke="black"/><text x="%g" y="%g" font-size="12">100 mm</text>' % (x+10, y+h-15, 100*factor, x+10, y+h+2))
    parts.append('<text x="25" y="815" font-size="12">Nominal rotor diameter %.1f mm; foot radius %.1f mm; ring attachment Z %.1f mm. Values are hypotheses.</text>' % (geom['rotor_diameter_mm'], geom['foot_socket_radius_mm'], geom['ring_attachment_z_mm']))
    parts.append('</g></svg>')
    Path(path).write_text('\n'.join(parts) + '\n', encoding='utf-8')


def candidate(config, geom, arrangement, spine_id, topology):
    cid = geom['id'] + '_' + arrangement['id'] + '_' + spine_id
    doc = App.newDocument(cid)
    sheet = parameters(doc)
    physical_group = doc.addObject('App::DocumentObjectGroup', 'NominalTubeComponents')
    reference_group = doc.addObject('App::DocumentObjectGroup', 'NonMassFixedReferences')
    physical, contacts, joint_coords = [], [], []
    main_outers = []
    ring_r, ring_z = geom['ring_attachment_radius_mm'], geom['ring_attachment_z_mm']
    foot_r, foot_z = geom['foot_socket_radius_mm'], geom['foot_socket_z_mm']
    frac = topology['junction_fraction_A_to_F']
    spread = topology['brace_root_azimuth_offset_deg']
    for idx, phi in enumerate(arrangement['leg_azimuths_deg'], 1):
        a, f = radial(ring_r, phi, ring_z), radial(foot_r, phi, foot_z)
        j = add(a, scale(sub(f, a), frac))
        outward_up = scale(sub(a, f), 1.0/norm(sub(a, f)))
        obj, outer = tube(doc, physical_group, 'MainLeg_%02d' % idx,
                          add(a, scale(outward_up, 15)), sub(f, scale(outward_up, 5)), '08_06', 'continuous main leg with preliminary insertion extensions')
        physical.append(obj)
        main_outers.append(outer)
        for suffix, sign in [('Plus', 1), ('Minus', -1)]:
            b = radial(ring_r, phi + sign*spread, ring_z)
            obj, _ = tube(doc, physical_group, 'Brace_%02d_%s' % (idx, suffix), b, j, '08_06', 'untrimmed ideal B-J brace chord; fittings and finished cuts unresolved')
            physical.append(obj)
            joint_coords.append(b)
        joint_coords.extend([a, j, f])
        contacts.append(radial(foot_r, phi, geom['foot_contact_z_mm']))
    spine_xy = [(0.0, 0.0)] if spine_id == 'S1' else list(itertools.product((-45.0, 45.0), repeat=2))
    section = '14_12' if spine_id == 'S1' else '08_06'
    for idx, (x, y) in enumerate(spine_xy, 1):
        a = [x, y, ring_z + SPINE_BOTTOM_ABOVE_RING_MM]
        b = add(a, [0, 0, SPINE_LENGTH_MM])
        obj, _ = tube(doc, physical_group, 'Spine_%02d' % idx, a, b, section,
                      'spine hypothesis; root pedestal and equipment retention unresolved', 'Parameters.SpineLength')
        physical.append(obj)
        joint_coords.append(a)
    merged = []
    for point in joint_coords:
        if not any(norm(sub(point, old)) <= 1e-6 for old in merged):
            merged.append(point)
    joints = [sphere(doc, reference_group, 'JointEnvelope_%02d' % i, p, JOINT_ENVELOPE_RADIUS_MM,
                     'Non-mass packaging sphere; not a fitting, restraint, joint strength or manufacturability claim')
              for i, p in enumerate(merged, 1)]
    feet = [sphere(doc, reference_group, 'ContactMarker_%02d' % i, add(p, [0, 0, 5]), 5,
                   'Non-mass nominal foot-contact marker; actual foot geometry/compliance unknown')
            for i, p in enumerate(contacts, 1)]
    ring = doc.addObject('Part::Feature', 'AttachmentRingGuide')
    ring.Shape = Part.Wire([Part.makeCircle(ring_r, App.Vector(0, 0, ring_z))])
    reference_group.addObject(ring)
    classify(ring, 'Zero-volume attachment locus only; ring/plate section, supports, joints and mass unresolved')
    outer = doc.addObject('App::Part', 'OuterJointReference')
    inner = doc.addObject('App::Part', 'InnerJointReference')
    outer.addObject(inner)
    classify(outer, 'Outer body +X rotation; CAD +X. Placement editable. Angles are uncalibrated hypotheses.')
    classify(inner, 'Carried body +Y rotation; CAD -Y. Separate joint-origin offset retained.')
    origin = geom['outer_joint_origin_CAD_mm']
    offset = geom['neutral_outer_to_inner_origin_CAD_mm']
    inner_neutral = add(origin, offset)
    set_pose(outer, inner, origin, offset, 0.0, 0.0)
    radius = geom['rotor_diameter_mm']/2.0
    rotors = {}
    for key, field in [('upper_rotor', 'upper_rotor_neutral_hub_CAD_mm'), ('lower_rotor', 'lower_rotor_neutral_hub_CAD_mm')]:
        hub = sub(geom[field], inner_neutral)
        rotors[key] = cylinder(doc, inner, key, add(hub, [0, 0, -SLAB_HALF_THICKNESS_MM]),
                               add(hub, [0, 0, SLAB_HALF_THICKNESS_MM]), radius,
                               'Non-mass full swept rotor slab, not a propeller solid or motor interface')
    xr = radius + YOKE_OUTBOARD_OFFSET_MM
    topz = origin[2]
    botz = (geom['upper_rotor_neutral_hub_CAD_mm'][2] + geom['lower_rotor_neutral_hub_CAD_mm'][2])/2.0
    corners = [[-xr, 0, topz], [xr, 0, topz], [-xr, 0, botz], [xr, 0, botz]]
    local = [sub(p, inner_neutral) for p in corners]
    yoke = []
    for idx, (i, j) in enumerate([(0, 1), (2, 3), (0, 2), (1, 3)], 1):
        yoke.append(cylinder(doc, inner, 'YokeEnvelope_%02d' % idx, local[i], local[j], YOKE_ENVELOPE_RADIUS_MM,
                             'Non-mass parent-concept yoke capsule envelope; not a sized load path'))
    for idx, point in enumerate(local, 1):
        yoke.append(sphere(doc, inner, 'YokeEndEnvelope_%02d' % idx, point, YOKE_ENVELOPE_RADIUS_MM,
                           'Non-mass capsule end envelope'))
    doc.recompute()
    initial_components = [measure_component(o, 1600.0) for o in physical]
    overlap = physical_intersections(physical)
    clearance = sweep(doc, physical, joints, rotors, yoke, outer, inner, geom, contacts,
                      config['clearance_contract']['resultant_cone_hypotheses_deg'])
    neutral_moving_gaps = {}
    yoke_shape = Part.makeCompound([world_shape(o) for o in yoke])
    for name, rotor in rotors.items():
        neutral_moving_gaps[name + '_to_yoke_mm'] = float(world_shape(rotor).distToShape(yoke_shape)[0])
    neutral_moving_gaps['upper_to_lower_rotor_mm'] = float(world_shape(rotors['upper_rotor']).distToShape(world_shape(rotors['lower_rotor']))[0])
    native = OUT / (cid + '.FCStd')
    step = OUT / (cid + '_tubes.step')
    drawing = OUT / (cid + '_arrangement.svg')
    names = [o.Name for o in physical]
    first_tube_name, first_outer_name = physical[0].Name, main_outers[0].Name
    arrangement_svg(drawing, cid, physical, joints + feet + [ring] + list(rotors.values()) + yoke, geom)
    doc.recompute()
    doc.saveAs(str(native))
    Part.export(physical, str(step))
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(native))
    try:
        reopened.recompute()
        reopened_objects = [reopened.getObject(name) for name in names]
        reopened_components = [measure_component(o, 1600.0) for o in reopened_objects]
        target = reopened.getObject(first_tube_name)
        length_mm = float(reopened.getObject(first_outer_name).Height)
        baseline_volume = float(world_shape(target).Volume)
        reopened.getObject('Parameters').set('B1', '4.04 mm')
        reopened.recompute()
        edited_volume = float(world_shape(target).Volume)
        reopened.getObject('Parameters').set('B1', '4 mm')
        reopened.recompute()
        restored_volume = float(world_shape(target).Volume)
        edit_observation = {'scope': 'Unsaved reopened-document radius perturbation; nominal output file unchanged',
                            'target': first_tube_name, 'outer_radius_before_mm': 4.0, 'outer_radius_after_mm': 4.04,
                            'length_mm': length_mm, 'before_volume_mm3': baseline_volume,
                            'edited_volume_mm3': edited_volume, 'restored_volume_mm3': restored_volume,
                            'analytical_delta_volume_mm3': math.pi*(4.04**2-4.0**2)*length_mm}
    finally:
        App.closeDocument(reopened.Name)
    step_shape = Part.read(str(step))
    step_solids = list(step_shape.Solids)
    result = {'candidate_id': cid, 'status': 'unselected_preliminary_nominal_tube_CAD',
              'geometry_hypothesis': geom, 'landing_arrangement': arrangement, 'brace_topology': topology,
              'spine_hypothesis': {'id': spine_id, 'section_mm': section, 'xy_mm': spine_xy,
                                   'length_mm': SPINE_LENGTH_MM, 'bottom_above_ring_mm': SPINE_BOTTOM_ABOVE_RING_MM},
              'fixed_joint_reference_centers_CAD_mm': merged, 'nominal_contact_points_CAD_mm': contacts,
              'native_component_names': names, 'components_at_density_1600': initial_components,
              'nominal_tube_component_sum': aggregate(initial_components),
              'reopened_native_component_sum': aggregate(reopened_components),
              'density_sensitivities': [], 'physical_component_intersections': overlap,
              'clearance_samples': clearance, 'neutral_moving_envelope_gaps': neutral_moving_gaps,
              'reopened_edit_recompute_observations': edit_observation,
              'step_readback': {'solid_count': len(step_solids),
                                'solid_volumes_mm3': sorted(float(s.Volume) for s in step_solids),
                                'solid_validity': [bool(s.isValid()) for s in step_solids],
                                'note': 'No generic Shape COM/inertia access. STEP has no established material mapping; no STEP vehicle mass inferred.'},
              'missing_mass_and_interfaces': ['ring/plate and supports', 'root, shared-root and junction fittings',
                                               'spine pedestals', 'feet and pads', 'fasteners/inserts/adhesives',
                                               'gimbal and bearing hardware', 'actuators and links',
                                               'motors/propellers/ESCs/battery', 'avionics and harness',
                                               'retention and loaded joint response'],
              'acceptance': {'complete_assembly': None, 'assembled_mass': None, 'continuous_clearance': None,
                             'structural_qualification': None, 'budget': None, 'physical_validation': None,
                             'PDR_CDR': None},
              'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in (native, step, drawing)]}
    # All modeled physical components have the same assumed CFRP density.
    # Scaling is explicit and does not add any missing material or hardware.
    base = result['nominal_tube_component_sum']
    for rho in config['sections_and_material_sensitivities']['density_kg_m3']:
        ratio = float(rho)/1600.0
        result['density_sensitivities'].append({'density_assumption_kg_m3': rho,
            'nominal_tube_mass_kg': base['mass_kg']*ratio, 'cg_CAD_mm': base['cg_CAD_mm'],
            'I_CAD_about_partial_CG_kg_m2': [[ratio*x for x in row] for row in base['I_CAD_about_partial_CG_kg_m2']]})
    return result


def main():
    if sha(CONFIG) != CONFIG_SHA256:
        raise ValueError('Braced configuration differs from the inspected published file')
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    topology = next(t for t in config['topologies'] if t['id'] == TOPOLOGY_ID)
    if OUT.exists():
        raise FileExistsError('Preserve previous/partial outputs; choose a fresh RUN_TAG: ' + str(OUT))
    OUT.mkdir(parents=True)
    report = {'schema': 'hopper_braced_candidate_cad_measurements/1', 'prepared_date': '2026-10-12',
              'authority': config['authority'],
              'priority_source': '51a1c7e564004f9fbd3db6ae44325332 r1: CAD first, existing plan retained',
              'inputs': [{'path': str(CONFIG.relative_to(ROOT)), 'sha256': sha(CONFIG)},
                         {'path': str(SOURCE.relative_to(ROOT)), 'sha256': sha(SOURCE)}],
              'frame': {'CAD_axes': '+X forward, +Y left, +Z up; nominal foot plane Z=0',
                        'R_BC': [[1,0,0],[0,-1,0],[0,0,-1]],
                        'body_gimbal_rotation': 'Rx(alpha)Ry(beta)',
                        'CAD_gimbal_rotation': 'Rx(alpha)Ry(-beta)',
                        'point_formula_CAD': 'O_outer + Rx(alpha)*d_outer_inner + Rx(alpha)*Ry(-beta)*r_inner_point',
                        'complete_vehicle_neutral_CG_C0_mm': None,
                        'eventual_CAD_to_body_position_m': '0.001*R_BC*(p_CAD_mm-CG_C0_mm); CG_C0 is not the partial tube CG'},
              'scope': 'Eight exploratory native tube-component candidates. Actual solids measured; fittings, load paths and equipment incomplete. No automatic down-selection.',
              'unmodeled_alternatives_retained': ['S2/S3 spines', 'aluminium spine comparison', 'B60_F080', 'B45_F065', 'B45_F090', 'larger-section unbraced comparator'],
              'candidates': []}
    for geom in config['geometry_hypotheses']:
        for arrangement in config['landing_arrangements']:
            for spine_id in ('S1', 'S4'):
                report['candidates'].append(candidate(config, geom, arrangement, spine_id, topology))
    measurements = OUT / 'cad_measurements_01.json'
    dump(measurements, report)
    files = [f for item in report['candidates'] for f in item['files']]
    files.append({'path': str(measurements.relative_to(ROOT)), 'sha256': sha(measurements)})
    manifest = OUT / 'output_manifest_01.json'
    dump(manifest, {'schema': 'hopper_candidate_output_manifest/1', 'files': files,
                    'manifest_path': str(manifest.relative_to(ROOT)),
                    'evidence_boundary': 'Produced files and measurements are not a VerificationResult. Retain an editable artifact-bound checker and execute it through verify_command before recording verification evidence.'})
    print(json.dumps({'candidate_count': len(report['candidates']), 'measurements': str(measurements.relative_to(ROOT)),
                      'manifest': str(manifest.relative_to(ROOT)), 'acceptance': 'not established'}))


if __name__ == '__main__':
    main()
