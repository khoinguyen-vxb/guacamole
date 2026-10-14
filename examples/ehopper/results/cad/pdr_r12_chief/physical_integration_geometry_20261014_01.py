"""Preliminary PDR-r12 physical-integration geometry module.

Import from a separately saved sandbox driver run through freecad_run.
Importing this module creates no document and writes no files. Calling
build_document(sandbox) constructs one exploratory native feature tree.
The driver must declare all saved/exported files as tool outputs.

This module does NOT verify geometry, save/export CAD, select a vehicle,
compute accepted mass properties or establish manufacturing feasibility.
It implements the exact hash-pinned configuration below. In particular,
it does not repair unsuccessful geometry by moving datums or suppressing
intersections. Separate manufactured parts are never fused together.

Native Part::Cylinder, Part::Box, Part::MultiFuse and Part::Cut features
need no custom Python proxy when reopened. Spreadsheet radius expressions
propagate through tubes, bores and adhesive layers. Topology and most
placements are configuration-derived: edit configuration and regenerate
at fresh paths to change them. This is not a fully constrained assembly.
"""

import hashlib
import json
import math
from pathlib import Path

import FreeCAD as App
import Part

CONFIG_RELATIVE = 'cad/pdr_r12_chief/physical_integration_prototype_config_20261014_01.json'
CONFIG_SHA256 = 'be78fc14b24b01cd824e1bf90625c415176b27ecae2dca26dff8ac790de1e9b0'
DOCUMENT_NAME = 'PDRR12PhysicalIntegrationPrototype01'


def vec(p):
    return App.Vector(*[float(x) for x in p])


def add(a, b):
    return [a[i] + b[i] for i in range(3)]


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def mul(a, k):
    return [float(k) * x for x in a]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    if not math.isfinite(n) or n <= 0:
        raise ValueError('Invalid construction direction')
    return mul(a, 1.0 / n)


def along(p, direction, distance):
    return add(p, mul(direction, distance))


def radial(radius, degrees, z):
    angle = math.radians(degrees)
    return [radius * math.cos(angle), radius * math.sin(angle), z]


def visibility(obj, visible):
    view = getattr(obj, 'ViewObject', None)
    if view is not None:
        view.Visibility = visible


def property_value(obj, typename, name, value, group='Evidence'):
    if name not in obj.PropertiesList:
        obj.addProperty(typename, name, group)
    setattr(obj, name, value)


def load_configuration(sandbox):
    root = Path(sandbox).resolve()
    path = (root / CONFIG_RELATIVE).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Configuration is outside sandbox')
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != CONFIG_SHA256:
        raise ValueError('Configuration bytes differ from the supported published prototype')
    cfg = json.loads(raw.decode('utf-8'))
    if cfg['schema'] != 'hopper_preliminary_physical_integration_configuration/1':
        raise ValueError('Unsupported configuration schema')
    return cfg


class NativeGraph:
    """Native feature construction and explicit physical ownership only."""

    def __init__(self, doc, cfg):
        self.doc = doc
        self.cfg = cfg
        self.construction = doc.addObject('App::DocumentObjectGroup', 'ConstructionFeatures')
        self.physical_group = doc.addObject('App::DocumentObjectGroup', 'PhysicalComponents')
        self.diagnostic_group = doc.addObject('App::DocumentObjectGroup', 'NonMassDiagnostics')
        self.physical = []
        self.parts = []
        self.interfaces = []
        self.tubes = []
        self.joints = []
        self.references = []
        self.diagnostics = []
        self.through_tools = []
        self.sheet = self.make_parameters()

    def make_parameters(self):
        g = self.cfg['immutable_reference_geometry']
        p = self.cfg['physical_part_hypotheses']
        gap = self.cfg['bond_and_retention_hypotheses']['nominal_radial_bond_gap_mm']
        root = p['printed_root_ring_spider']
        junction = p['brace_junction_fittings']
        shared_socket_radii = [root['integral_main_root_sockets']['outer_radius_mm'],
                               root['integral_brace_root_sockets']['outer_radius_mm'],
                               junction['main_sleeve_outer_radius_mm'],
                               junction['branch_socket_outer_radius_mm']]
        if any(abs(x - shared_socket_radii[0]) > 1e-12 for x in shared_socket_radii):
            raise ValueError('Supported configuration requires equal shared socket radii')
        if g['main_tube_OD_ID_mm'] != g['brace_tube_OD_ID_mm']:
            raise ValueError('Supported prototype uses the same leg/brace section')
        expected_bore = g['main_tube_OD_ID_mm'][0] / 2 + gap
        configured_bores = [root['integral_main_root_sockets']['blind_bore_radius_mm'],
                            root['integral_brace_root_sockets']['blind_bore_radius_mm'],
                            junction['main_through_bore_radius_mm'],
                            junction['branch_blind_bore_radius_mm'],
                            p['foot_bodies']['blind_bore_radius_mm']]
        if any(abs(x - expected_bore) > 1e-12 for x in configured_bores):
            raise ValueError('Configured socket bore and bond-gap hypotheses disagree')
        if abs(p['spine_pedestal']['blind_bore_radius_mm'] - g['spine_OD_ID_mm'][0]/2 - gap) > 1e-12:
            raise ValueError('Configured spine bore and bond gap disagree')
        values = [
            ('LegTubeOuterRadius', g['main_tube_OD_ID_mm'][0]/2),
            ('LegTubeInnerRadius', g['main_tube_OD_ID_mm'][1]/2),
            ('SpineTubeOuterRadius', g['spine_OD_ID_mm'][0]/2),
            ('SpineTubeInnerRadius', g['spine_OD_ID_mm'][1]/2),
            ('NominalBondGap', gap),
            ('SharedSocketOuterRadius', shared_socket_radii[0]),
            ('JunctionWebRadius', 5.0),
            ('FootSocketOuterRadius', p['foot_bodies']['socket_outer_radius_mm']),
            ('SpineTubeLength', length(sub(g['spine_end_CAD_mm'], g['spine_start_CAD_mm']))),
            ('RingOuterRadius', root['annulus_inner_outer_radius_mm'][1]),
            ('RingInnerRadius', root['annulus_inner_outer_radius_mm'][0]),
            ('FootPadRadius', p['foot_pads']['radius_mm'])
        ]
        aliases = [x[0].casefold() for x in values]
        if len(aliases) != len(set(aliases)):
            raise ValueError('Spreadsheet aliases must be case-insensitively distinct')
        sheet = self.doc.addObject('Spreadsheet::Sheet', 'Parameters')
        for row, (alias, value) in enumerate(values, 1):
            sheet.set('A%d' % row, alias)
            sheet.set('B%d' % row, '%.12g mm' % value)
            sheet.setAlias('B%d' % row, alias)
            sheet.set('C%d' % row, 'Exploratory configuration hypothesis; not manufacturing acceptance')
        return sheet

    def new(self, typename, name):
        if self.doc.getObject(name) is not None:
            raise ValueError('Duplicate native object name: ' + name)
        obj = self.doc.addObject(typename, name)
        self.construction.addObject(obj)
        visibility(obj, False)
        return obj

    def cylinder(self, name, a, b, radius=None, radius_expression=None, height_expression=None):
        delta = sub(b, a)
        h = length(delta)
        if h <= 0:
            raise ValueError('Nonpositive cylinder length: ' + name)
        obj = self.new('Part::Cylinder', name)
        obj.Height = h
        if radius_expression is not None:
            obj.setExpression('Radius', radius_expression)
        else:
            obj.Radius = float(radius)
        if height_expression is not None:
            obj.setExpression('Height', height_expression)
        obj.Placement = App.Placement(vec(a), App.Rotation(App.Vector(0, 0, 1), vec(delta)))
        return obj

    def box(self, name, intervals, rotation_deg=0.0):
        obj = self.new('Part::Box', name)
        dims = [intervals[k][1] - intervals[k][0] for k in ('X', 'Y', 'Z')]
        if min(dims) <= 0:
            raise ValueError('Nonpositive box dimension: ' + name)
        obj.Length, obj.Width, obj.Height = dims
        base = vec([intervals[k][0] for k in ('X', 'Y', 'Z')])
        placement = App.Placement(base, App.Rotation())
        if rotation_deg:
            placement = App.Placement(App.Vector(0, 0, 0),
                                      App.Rotation(App.Vector(0, 0, 1), rotation_deg)).multiply(placement)
        obj.Placement = placement
        return obj

    def fuse(self, name, features):
        if len(features) < 2:
            raise ValueError('Explicit fuse requires at least two features')
        obj = self.new('Part::MultiFuse', name)
        obj.Shapes = list(features)
        return obj

    def cut(self, name, base, tools):
        if not tools:
            raise ValueError('Cut requires a tool')
        tool = tools[0] if len(tools) == 1 else self.fuse(name + '_CuttingToolUnion', tools)
        obj = self.new('Part::Cut', name)
        obj.Base = base
        obj.Tool = tool
        return obj

    def annular(self, name, a, b, outer_expression, inner_expression, height_expression=None):
        direction = unit(sub(b, a))
        outer = self.cylinder(name + '_Outer', a, b, radius_expression=outer_expression,
                              height_expression=height_expression)
        # Cutting-tool extensions lie outside this annulus; they do not add
        # manufactured material or change its specified end planes.
        inner = self.cylinder(name + '_Void', along(a, direction, -1), along(b, direction, 1),
                              radius_expression=inner_expression,
                              height_expression=outer.Name + '.Height + 2 mm')
        return self.cut(name, outer, [inner])

    def physical_part(self, obj, material, role, metadata=None):
        density = self.cfg['material_and_mass_ownership']['density_assumptions_kg_m3'][material]
        self.construction.removeObject(obj)
        self.physical_group.addObject(obj)
        property_value(obj, 'App::PropertyBool', 'CountsInStructuralSubtotal', True)
        property_value(obj, 'App::PropertyString', 'MaterialHypothesis', material)
        property_value(obj, 'App::PropertyFloat', 'AssumedDensityKgM3', float(density))
        property_value(obj, 'App::PropertyString', 'MovingGroup', 'fixed_airframe')
        property_value(obj, 'App::PropertyString', 'PhysicalRole', role)
        property_value(obj, 'App::PropertyString', 'EvidenceScope',
                       'Exploratory component; validity, joints, strength and acceptance unestablished')
        visibility(obj, True)
        self.physical.append(obj)
        self.parts.append({'name': obj.Name, 'material_hypothesis': material,
                           'assumed_density_kg_m3': density, 'role': role,
                           'moving_group': 'fixed_airframe', 'metadata': metadata or {}})
        return obj

    def intended_contact(self, a, b, description):
        self.interfaces.append({'a': a.Name, 'b': b.Name,
                                'intended_interface': description,
                                'contact_observed': None, 'interpenetration_accepted': False,
                                'retention_qualified': False})

    def adhesive(self, name, a, b, tube, host, tube_radius_expression, engagement, stop=False):
        obj = self.annular(name, a, b,
                           tube_radius_expression + ' + Parameters.NominalBondGap',
                           tube_radius_expression)
        self.physical_part(obj, 'unspecified_adhesive_density_hypothesis',
                           'Separate nominal annular bond layer',
                           {'start_CAD_mm': a, 'end_CAD_mm': b,
                            'nominal_engagement_mm': engagement,
                            'adhesive_product': None, 'qualified_strength': None})
        self.intended_contact(tube, obj, 'Tube outer surface / adhesive inner surface')
        self.intended_contact(obj, host, 'Adhesive outer surface / fitting bore')
        if stop:
            self.intended_contact(tube, host, 'Specified axial end stop; not secondary positive retention')
        return obj

    def diagnostic(self, obj, description):
        self.construction.removeObject(obj)
        self.diagnostic_group.addObject(obj)
        property_value(obj, 'App::PropertyBool', 'CountsInStructuralSubtotal', False)
        property_value(obj, 'App::PropertyString', 'EvidenceScope', description)
        visibility(obj, False)
        self.diagnostics.append(obj)
        return obj

    def through_cutter(self, name, host, axis_point, axis_direction, radius=None, radius_expression=None):
        # Extend a computational cutter beyond the host's entire bounding
        # box. This is not a proposed physical clearance or engagement.
        self.doc.recompute()
        if host.Shape.isNull():
            raise ValueError('Cannot construct through bore: host shape is null: ' + host.Name)
        direction = unit(axis_direction)
        bb = host.Shape.BoundBox
        corners = [[x, y, z] for x in (bb.XMin, bb.XMax)
                   for y in (bb.YMin, bb.YMax) for z in (bb.ZMin, bb.ZMax)]
        projections = [dot(sub(p, axis_point), direction) for p in corners]
        a = along(axis_point, direction, min(projections)-1.0)
        b = along(axis_point, direction, max(projections)+1.0)
        tool = self.cylinder(name, a, b, radius=radius, radius_expression=radius_expression)
        self.through_tools.append({'name': tool.Name, 'host': host.Name,
                                   'start_CAD_mm': a, 'end_CAD_mm': b,
                                   'outside_bbox_extension_mm': 1.0,
                                   'scope': 'Computational through-cut tool, not physical material or acceptance margin'})
        return tool


def build_document(sandbox):
    cfg = load_configuration(sandbox)
    if DOCUMENT_NAME in App.listDocuments():
        raise ValueError('Preserve existing open document: ' + DOCUMENT_NAME)
    doc = App.newDocument(DOCUMENT_NAME)
    graph = NativeGraph(doc, cfg)
    g = cfg['immutable_reference_geometry']
    p = cfg['physical_part_hypotheses']
    petg = 'PETG_assumed_full_density'
    leg_outer = 'Parameters.LegTubeOuterRadius'
    leg_inner = 'Parameters.LegTubeInnerRadius'
    bore = leg_outer + ' + Parameters.NominalBondGap'
    socket_outer = 'Parameters.SharedSocketOuterRadius'
    nodes = []

    contract = doc.addObject('App::DocumentObjectGroup', 'EvidenceContract')
    for name, value in [
        ('ConfigurationSHA256', CONFIG_SHA256),
        ('ConfigurationPath', CONFIG_RELATIVE),
        ('DevelopmentDecision', '9aaf88cc8ecf4e8ab82a66cdae8731b1 revision 1'),
        ('WorkPlan', '66c7448f443f44ac9a016a1b384593a2 revision 1'),
        ('CADFrame', '+X forward, +Y left, +Z up; lengths mm'),
        ('CADToBodyRotation', 'diag(1,-1,-1); position scale 0.001 m/mm; complete neutral CG unknown'),
        ('EvidenceBoundary', 'Unselected partial structural prototype. No geometry, strength, budget or flight acceptance.'),
        ('ParametricScope', 'Native radius/bore/bond and spine-length expressions; configuration-derived topology and placements')
    ]:
        property_value(contract, 'App::PropertyString', name, value)

    # CFRP members remain separate physical parts, including at joints.
    for index, phi in enumerate(g['leg_azimuths_deg'], 1):
        a = radial(g['ring_attachment_radius_mm'], phi, g['ring_attachment_z_mm'])
        f = radial(g['foot_socket_radius_mm'], phi, g['foot_socket_z_mm'])
        u = unit(sub(f, a))
        j = add(a, mul(sub(f, a), g['junction_fraction_A_to_F']))
        ma = along(a, u, -g['main_extension_above_A_mm'])
        mb = along(f, u, g['main_extension_past_F_mm'])
        main = graph.annular('MainLeg_%02d' % index, ma, mb, leg_outer, leg_inner)
        graph.physical_part(main, 'CFRP', 'Continuous main landing tube',
                            {'start_CAD_mm': ma, 'end_CAD_mm': mb, 'nominal_cut_length_mm': length(sub(mb, ma))})
        graph.tubes.append({'name': main.Name, 'section_OD_ID_mm': g['main_tube_OD_ID_mm'],
                            'start_CAD_mm': ma, 'end_CAD_mm': mb, 'cut_length_mm': length(sub(mb, ma))})
        row = {'index': index, 'phi_deg': phi, 'A': a, 'F': f, 'J': j, 'u': u,
               'main': main, 'main_start': ma, 'main_end': mb, 'branches': []}
        for suffix, sign in [('Plus', 1), ('Minus', -1)]:
            b = radial(g['ring_attachment_radius_mm'], phi+sign*g['brace_root_offset_deg'], g['ring_attachment_z_mm'])
            direction = unit(sub(j, b))
            end = along(j, direction, -cfg['construction_coordinates']['brace_cutback_from_J_mm'])
            brace = graph.annular('Brace_%02d_%s' % (index, suffix), b, end, leg_outer, leg_inner)
            graph.physical_part(brace, 'CFRP', 'Brace with explicit junction cutback',
                                {'start_CAD_mm': b, 'end_CAD_mm': end, 'nominal_cut_length_mm': length(sub(end, b))})
            graph.tubes.append({'name': brace.Name, 'section_OD_ID_mm': g['brace_tube_OD_ID_mm'],
                                'start_CAD_mm': b, 'end_CAD_mm': end, 'cut_length_mm': length(sub(end, b))})
            legacy = graph.annular('LegacyUntrimmedBrace_%02d_%s' % (index, suffix), b, j, leg_outer, leg_inner)
            graph.diagnostic(legacy, 'Old untrimmed B-to-J geometry only; excluded from all physical exports and mass sums')
            row['branches'].append({'suffix': suffix, 'B': b, 'v': direction, 'end': end, 'tube': brace})
        nodes.append(row)

    spine = graph.annular('Spine_01', g['spine_start_CAD_mm'], g['spine_end_CAD_mm'],
                          'Parameters.SpineTubeOuterRadius', 'Parameters.SpineTubeInnerRadius',
                          'Parameters.SpineTubeLength')
    graph.physical_part(spine, 'CFRP', 'Single-spine prototype, not spine-count selection')
    graph.tubes.append({'name': spine.Name, 'section_OD_ID_mm': g['spine_OD_ID_mm'],
                        'start_CAD_mm': g['spine_start_CAD_mm'], 'end_CAD_mm': g['spine_end_CAD_mm'],
                        'cut_length_mm': length(sub(g['spine_end_CAD_mm'], g['spine_start_CAD_mm']))})

    # One intentionally continuous printed root ring/spider, with all its
    # bores subtracted from the entire same printed part after union.
    rp = p['printed_root_ring_spider']
    z0, z1 = rp['z_interval_mm']
    ring_annulus = graph.annular('RootRingAnnulus', [0,0,z0], [0,0,z1],
                                 'Parameters.RingOuterRadius', 'Parameters.RingInnerRadius')
    raw_ring = [ring_annulus, graph.cylinder('RootRingCentralHub', [0,0,z0], [0,0,z1], rp['central_hub_radius_mm'])]
    for index, phi in enumerate(rp['spoke_azimuths_deg'], 1):
        raw_ring.append(graph.box('RootRingSpoke_%02d' % index,
                                  {'X': rp['spoke_radial_extent_mm'],
                                   'Y': [-rp['spoke_width_mm']/2, rp['spoke_width_mm']/2], 'Z': [z0,z1]}, phi))
    ring_bores = []
    for row in nodes:
        i, a, u = row['index'], row['A'], row['u']
        raw_ring.append(graph.cylinder('MainRootBoss_%02d' % i, along(a,u,-18), along(a,u,15), radius_expression=socket_outer))
        tool = graph.cylinder('MainRootBlindBore_%02d' % i, along(a,u,-15), along(a,u,15), radius_expression=bore)
        ring_bores.append(tool)
        for branch in row['branches']:
            tag = '%02d_%s' % (i, branch['suffix'])
            b, direction = branch['B'], branch['v']
            raw_ring.append(graph.cylinder('BraceRootBoss_' + tag, along(b,direction,-3), along(b,direction,30), radius_expression=socket_outer))
            ring_bores.append(graph.cylinder('BraceRootBlindBore_' + tag, b, along(b,direction,30), radius_expression=bore))
    ring = graph.cut('PrintedRootRingSpider', graph.fuse('RootRingUnbored', raw_ring), ring_bores)
    graph.physical_part(ring, petg, 'One-piece preliminary root ring, spider and integral sockets',
                        {'bore_tool_names': [o.Name for o in ring_bores], 'manufacturing_and_connectivity_accepted': False})
    for row in nodes:
        i, a, u = row['index'], row['A'], row['u']
        graph.adhesive('Bond_MainRoot_%02d' % i, along(a,u,-15), along(a,u,15), row['main'], ring, leg_outer, 30, True)
        for branch in row['branches']:
            b, direction = branch['B'], branch['v']
            graph.adhesive('Bond_BraceRoot_%02d_%s' % (i,branch['suffix']), b, along(b,direction,30),
                           branch['tube'], ring, leg_outer, 30, True)

    # Each brace-junction fitting is one manufactured hypothesis. Union
    # applies only to its sleeve, branches and webs, never to CFRP tubes.
    for row in nodes:
        i, j, u = row['index'], row['J'], row['u']
        raw = [graph.cylinder('JunctionMainSleeve_%02d' % i, along(j,u,-110), along(j,u,25), radius_expression=socket_outer)]
        tools = []
        branch_tools = []
        for branch in row['branches']:
            tag, direction = '%02d_%s' % (i,branch['suffix']), branch['v']
            raw.append(graph.cylinder('JunctionBranchBoss_' + tag, along(j,direction,-110), along(j,direction,-67), radius_expression=socket_outer))
            branch_bore = graph.cylinder('JunctionBranchBlindBore_' + tag, along(j,direction,-110), along(j,direction,-70), radius_expression=bore)
            tools.append(branch_bore)
            branch_tools.append(branch_bore.Name)
            web_start = along(j,direction,-90)
            projection = along(j,u,dot(sub(web_start,j),u))
            raw.append(graph.cylinder('JunctionWeb_' + tag, web_start, projection, radius_expression='Parameters.JunctionWebRadius'))
        unbored = graph.fuse('JunctionUnbored_%02d' % i, raw)
        main_bore = graph.through_cutter('JunctionMainThroughBore_%02d' % i, unbored, j, u, radius_expression=bore)
        tools.append(main_bore)
        fitting = graph.cut('BraceJunctionFitting_%02d' % i, unbored, tools)
        graph.physical_part(fitting, petg, 'Separate sleeve/two-branch printed junction hypothesis',
                            {'main_bore_tool': main_bore.Name, 'branch_bore_tools': branch_tools,
                             'assembly_access_demonstrated': False, 'web_strength_qualified': False})
        graph.adhesive('Bond_JunctionMain_%02d' % i, along(j,u,-110), along(j,u,25),
                       row['main'], fitting, leg_outer, 135)
        for branch in row['branches']:
            direction = branch['v']
            graph.adhesive('Bond_JunctionBrace_%02d_%s' % (i,branch['suffix']),
                           along(j,direction,-110), along(j,direction,-70), branch['tube'], fitting, leg_outer, 40, True)
        graph.joints.append({'fitting': fitting.Name, 'J_CAD_mm': j,
                             'main_tube': row['main'].Name, 'main_bore_tool': main_bore.Name,
                             'branch_tubes': [b['tube'].Name for b in row['branches']],
                             'branch_bore_tools': branch_tools,
                             'branch_cut_endpoints_CAD_mm': [b['end'] for b in row['branches']],
                             'bore_separation_observed': None, 'assembly_access_observed': None})

    # Mirrored fixed-side supports. The exploratory bearing aperture does
    # not identify a purchased bearing, shaft, moving carrier or actuator.
    support_cfg = p['fixed_gimbal_supports']
    supports = []
    for sign, suffix in [(1,'PositiveX'), (-1,'NegativeX')]:
        raw = []
        for key, label in [('positive_X_top_beam_box_mm','Beam'), ('positive_X_column_box_mm','Column')]:
            intervals = {axis: list(pair) for axis,pair in support_cfg[key].items()}
            if sign < 0:
                intervals['X'] = [-intervals['X'][1], -intervals['X'][0]]
            raw.append(graph.box('FixedSupport%s_%s' % (label,suffix), intervals))
        h = support_cfg['positive_X_bearing_housing']
        center = list(h['axis_center_CAD_mm'])
        center[0] *= sign
        axis = [sign,0,0]
        raw.append(graph.cylinder('FixedSupportHousing_' + suffix,
                                  along(center,axis,-h['axial_length_mm']/2), along(center,axis,h['axial_length_mm']/2),
                                  h['outer_radius_mm']))
        unbored = graph.fuse('FixedSupportUnbored_' + suffix, raw)
        tool = graph.through_cutter('FixedSupportThroughBore_' + suffix, unbored, center, axis,
                                    radius=h['through_bore_radius_mm'])
        support = graph.cut('FixedGimbalSupport_' + suffix, unbored, [tool])
        graph.physical_part(support, petg, 'Fixed-side ring-to-outer-axis support hypothesis',
                            {'bore_tool': tool.Name, 'bearing_product': None, 'attachment_fasteners': None})
        graph.intended_contact(ring, support, 'Support top beam / ring underside at CAD Z=427 mm; attachment hardware unresolved')
        supports.append(support)

    # Separate spine pedestal and finite foot/pad geometry.
    sp = p['spine_pedestal']
    base = graph.cylinder('SpinePedestalBase', [0,0,sp['base_z_interval_mm'][0]], [0,0,sp['base_z_interval_mm'][1]], sp['base_radius_mm'])
    neck = graph.cylinder('SpinePedestalNeck', [0,0,sp['neck_z_interval_mm'][0]], [0,0,sp['neck_z_interval_mm'][1]], sp['neck_outer_radius_mm'])
    tool = graph.cylinder('SpinePedestalBlindBore', [0,0,sp['bore_z_interval_mm'][0]], [0,0,sp['bore_z_interval_mm'][1]],
                          radius_expression='Parameters.SpineTubeOuterRadius + Parameters.NominalBondGap')
    pedestal = graph.cut('SpinePedestal', graph.fuse('SpinePedestalUnbored',[base,neck]), [tool])
    graph.physical_part(pedestal, petg, 'Separate spine pedestal with blind socket')
    graph.intended_contact(pedestal, ring, 'Pedestal base / central spider at CAD Z=433 mm; fasteners unresolved')
    graph.adhesive('Bond_SpinePedestal', [0,0,450], [0,0,485], spine, pedestal,
                   'Parameters.SpineTubeOuterRadius', sp['spine_engagement_mm'], True)

    pads = []
    feet = []
    fp = p['foot_bodies']
    pp = p['foot_pads']
    for row in nodes:
        i, f, u = row['index'], row['F'], row['u']
        base = graph.cylinder('FootBase_%02d' % i, [f[0],f[1],fp['base_z_interval_mm'][0]],
                               [f[0],f[1],fp['base_z_interval_mm'][1]], fp['base_radius_mm'])
        socket = graph.cylinder('FootSocket_%02d' % i, along(f,u,-25), along(f,u,8),
                                 radius_expression='Parameters.FootSocketOuterRadius')
        tool = graph.cylinder('FootBlindBore_%02d' % i, along(f,u,-25), along(f,u,5), radius_expression=bore)
        foot = graph.cut('PrintedFoot_%02d' % i, graph.fuse('FootUnbored_%02d' % i,[base,socket]), [tool])
        graph.physical_part(foot, petg, 'Separate printed foot with inclined blind socket')
        pad = graph.cylinder('FootPad_%02d' % i, [f[0],f[1],pp['z_interval_mm'][0]],
                              [f[0],f[1],pp['z_interval_mm'][1]], radius_expression='Parameters.FootPadRadius')
        graph.physical_part(pad, 'unspecified_compliant_pad_density_hypothesis',
                            'Finite rigid pad shape representing an unspecified compliant product',
                            {'compression_model': None, 'friction': None, 'attachment_product': None})
        graph.adhesive('Bond_Foot_%02d' % i, along(f,u,-25), along(f,u,5), row['main'], foot, leg_outer, 30, True)
        graph.intended_contact(foot, pad, 'Printed foot base / pad top at CAD Z=6 mm; attachment and compression unresolved')
        feet.append(foot)
        pads.append(pad)

    # Retained non-mass moving envelopes. They are inner-group references,
    # not a physical carrier, gimbal load path or a completed propulsion CAD.
    outer = doc.addObject('App::Part','OuterJointReference')
    inner = doc.addObject('App::Part','InnerJointReference')
    outer.addObject(inner)
    outer.Placement = App.Placement(vec(g['outer_joint_origin_CAD_mm']),App.Rotation())
    inner.Placement = App.Placement(vec(g['outer_to_inner_local_CAD_mm']),App.Rotation())
    neutral_inner = add(g['outer_joint_origin_CAD_mm'],g['outer_to_inner_local_CAD_mm'])

    def moving_reference(obj, description):
        graph.construction.removeObject(obj)
        inner.addObject(obj)
        property_value(obj,'App::PropertyBool','CountsInStructuralSubtotal',False)
        property_value(obj,'App::PropertyString','MovingGroup','inner_gimbal_reference')
        property_value(obj,'App::PropertyString','EvidenceScope',description)
        visibility(obj,True)
        graph.references.append(obj)
        return obj

    rotors = {}
    for name, key in [('UpperRotorEnvelope','upper_rotor_neutral_hub_CAD_mm'),
                      ('LowerRotorEnvelope','lower_rotor_neutral_hub_CAD_mm')]:
        hub = sub(g[key],neutral_inner)
        half = g['rotor_slab_half_thickness_mm']
        obj = graph.cylinder(name,add(hub,[0,0,-half]),add(hub,[0,0,half]),g['rotor_diameter_mm']/2)
        rotors[name] = moving_reference(obj,'Retained non-mass swept rotor slab; not an actual propeller or motor')
    yoke = []
    corners = [sub(point,neutral_inner) for point in g['yoke_neutral_corners_CAD_mm']]
    for i,(a,b) in enumerate(g['yoke_edges_corner_indices'],1):
        obj = graph.cylinder('YokeEnvelope_%02d' % i,corners[a],corners[b],g['yoke_capsule_radius_mm'])
        yoke.append(moving_reference(obj,'Retained non-mass yoke capsule primitive; not physical structural material'))
    for i,point in enumerate(corners,1):
        obj = graph.new('Part::Sphere','YokeEndEnvelope_%02d' % i)
        obj.Radius = g['yoke_capsule_radius_mm']
        obj.Placement.Base = vec(point)
        yoke.append(moving_reference(obj,'Retained non-mass capsule end sphere'))

    doc.recompute()
    # This inventory expectation catches implementation omissions, not
    # invalid, disconnected, colliding or unmanufacturable geometry.
    if len(graph.physical) != 58:
        raise ValueError('Prototype inventory mismatch: expected 58 separately owned physical components')
    for obj in graph.construction.Group:
        visibility(obj,False)
    for obj in graph.diagnostics:
        visibility(obj,False)
    for obj in graph.physical + graph.references:
        visibility(obj,True)

    return {
        'document': doc, 'configuration': cfg, 'configuration_sha256': CONFIG_SHA256,
        'physical_objects': graph.physical, 'component_ledger': graph.parts,
        'intended_interfaces': graph.interfaces, 'tube_cut_hypotheses': graph.tubes,
        'joint_geometry_index': graph.joints, 'through_cutting_tool_index': graph.through_tools,
        'diagnostic_objects': graph.diagnostics, 'moving_reference_objects': graph.references,
        'rotor_objects': rotors, 'yoke_objects': yoke, 'outer_joint': outer, 'inner_joint': inner,
        'pad_objects': pads, 'foot_objects': feet, 'root_ring': ring, 'support_objects': supports,
        'assembly_access_demonstrated': None, 'positive_retention_qualified': None,
        'complete_vehicle_mass_kg': None, 'complete_vehicle_CG_CAD_mm': None,
        'complete_vehicle_inertia_kg_m2': None, 'geometry_acceptance': None,
        'unperformed': [
            'Saving and reopening native and STEP artifacts',
            'Actual individual-solid validity, connectivity and volume inspection',
            'Physical pair distances/intersections and intended contact observations',
            'Bore separation, residual webs, insertion and assembly access',
            'Material-based partial mass, CG and full inertia reconciliation',
            'Retained 97-pose moving-envelope and finite-pad ground sampling',
            'Continuous, loaded and manufacturing-tolerance clearance',
            'Joint, material, printed-part and structural qualification',
            'Complete installed mass, propulsion energy, procurement and review acceptance'
        ]
    }


if __name__ == '__main__':
    raise RuntimeError('Geometry module only. Use a separately saved freecad_run driver with explicit output declarations.')
