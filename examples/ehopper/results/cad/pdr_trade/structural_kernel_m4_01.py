"""PDR CAD native-CSG and measurement kernel, revision M4-01.

Source creation is not execution or verification. A separate saved runner must
supply explicit candidate configuration and declare every generated output to
freecad_run. No supplier interfaces or hardware selections are established here.
Native primitives, booleans and Spreadsheet expressions avoid custom Proxy
requirements when an FCStd document is reopened.

Authority: system_model:system@4,
work plan decision:99f7bb629eef45b89fa38d27c803868c@1,
interface decision:88561ff8b3ba4e8286cebd95a93e3b08@1.
CAD coordinates are forward-left-up, mm. Body is forward-right-down, SI.
"""
import sys
sys.dont_write_bytecode = True
import json
import math
from pathlib import Path
import FreeCAD as App
import Part

AUTHORITY = {
    'system_model': {'kind':'system_model','id':'system','revision':4,
        'sha256':'e89e68e192965d8e012cc1213e59c02610f55042ad26d7392ebef0401237ee75'},
    'work_plan': {'kind':'decision','id':'99f7bb629eef45b89fa38d27c803868c','revision':1,
        'sha256':'e5af8e2f56f7c851b65518b129f39550be73911f56461279cbbb1e85e1cdd5f0'},
    'interface': {'kind':'decision','id':'88561ff8b3ba4e8286cebd95a93e3b08','revision':1,
        'sha256':'ad6662afab9685585264c86e052c246996d23f4369c6432b56094a42a9187c04'}
}
GROUPS = ('fixed_airframe', 'outer_gimbal', 'inner_module_nonspinning',
          'upper_spinning_group', 'lower_spinning_group')
SIGNS = (1.0, -1.0, -1.0)


def vector(p):
    return App.Vector(*[float(x) for x in p])


def xyz(v):
    return [float(v.x), float(v.y), float(v.z)]


def zeros():
    return [[0.0 for _ in range(3)] for _ in range(3)]


def positive(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(name + ' must be finite and positive')
    return value


def tensor(matrix):
    return [[float(getattr(matrix, 'A%d%d' % (i+1, j+1)))
             for j in range(3)] for i in range(3)]


def parallel_axis(mass, displacement_m):
    r = displacement_m
    r2 = sum(x*x for x in r)
    return [[mass * ((r2 if i == j else 0.0) - r[i]*r[j])
             for j in range(3)] for i in range(3)]


def aggregate(properties):
    """Aggregate known mass rows only, in CAD axes and about their combined CG."""
    if not properties:
        return None
    mass = sum(p['mass_kg'] for p in properties)
    positive(mass, 'aggregate mass')
    cg = [sum(p['mass_kg']*p['centroid_C_mm'][i] for p in properties)/mass
          for i in range(3)]
    inertia = zeros()
    for p in properties:
        shift = parallel_axis(p['mass_kg'],
            [(p['centroid_C_mm'][i]-cg[i])*0.001 for i in range(3)])
        for i in range(3):
            for j in range(3):
                inertia[i][j] += p['inertia_centroid_C_kg_m2'][i][j] + shift[i][j]
    return {'mass_kg':mass, 'centroid_C_mm':cg,
            'inertia_centroid_C_kg_m2':inertia}


def to_body(properties, datum_C_mm):
    """Rotate centroidal tensor; do not silently shift it to datum D."""
    if properties is None:
        return None
    return {
        'mass_kg':properties['mass_kg'],
        'r_DG_B_m':[0.001*SIGNS[i]*(properties['centroid_C_mm'][i]-datum_C_mm[i])
                    for i in range(3)],
        'inertia_centroid_B_kg_m2':[
            [SIGNS[i]*SIGNS[j]*properties['inertia_centroid_C_kg_m2'][i][j]
             for j in range(3)] for i in range(3)],
        'reference':'Centroid of these accounted components, not necessarily complete vehicle G'
    }


def geometry_properties(shape, density_kg_m3=None, override_mass_kg=None):
    """Use each actual Solid; never assume a generic Compound has inertia.

    OCCT uniform-volume inertia is mm^5. Density multiplication uses 1e-15
    to obtain kg m^2. An override replaces material mass, with a declared
    uniform-volume distribution approximation across this envelope.
    """
    if density_kg_m3 is not None and override_mass_kg is not None:
        raise ValueError('Mass override and material density are mutually exclusive')
    solids = list(shape.Solids)
    if not solids or not shape.isValid() or any(not s.isValid() for s in solids):
        raise ValueError('Mass properties require actual valid solids')
    volume = sum(float(s.Volume) for s in solids)
    positive(volume, 'solid volume')
    if override_mass_kg is not None:
        density = positive(override_mass_kg, 'override mass')/(volume*1e-9)
        method = 'commercial_or_assumed_mass_override_uniform_envelope_distribution'
    elif density_kg_m3 is not None:
        density = positive(density_kg_m3, 'density')
        method = 'density_weighted_actual_solids'
    else:
        return None
    pieces = []
    for s in solids:
        raw = tensor(s.MatrixOfInertia)
        pieces.append({
            'mass_kg':float(s.Volume)*density*1e-9,
            'centroid_C_mm':xyz(s.CenterOfMass),
            'inertia_centroid_C_kg_m2':[
                [raw[i][j]*density*1e-15 for j in range(3)] for i in range(3)]})
    result = aggregate(pieces)
    result.update({'volume_mm3':volume, 'solid_count':len(solids), 'mass_method':method})
    return result


class Candidate:
    """Native editable candidate plus explicit accounting manifest.

    Only registered final objects enter accounting/export. Boolean operands do
    not enter twice. Swept/wiring envelopes are not installed material. Unknown
    physical component masses remain unknown, and omissions are separately kept.
    All objects use neutral absolute CAD coordinates; articulation is evaluated
    on copies with the selected group transformations.
    """
    def __init__(self, document_name, candidate_id, datum_C_mm=(0,0,0)):
        self.doc = App.newDocument(document_name)
        self.candidate_id = candidate_id
        self.datum = list(datum_C_mm)
        self.sheet = self.doc.addObject('Spreadsheet::Sheet', 'Parameters')
        self.parameter_cells = {}
        self.rows = []
        self.omissions = []
        datum = self.doc.addObject('PartDesign::CoordinateSystem', 'FixedDatumD')
        datum.Label = 'Fixed scoring datum D; CAD +X is marked-forward direction'
        datum.Placement.Base = vector(datum_C_mm)
        datum.addProperty('App::PropertyString', 'Definition')
        datum.Definition = ('Neutral propulsion centreline intersection with upper plane '
                            'of fixed leg-attachment plate/ring; runner must implement this')

    def length_parameter(self, name, value_mm):
        value_mm = positive(value_mm, name)
        if name not in self.parameter_cells:
            row = len(self.parameter_cells)+1
            self.sheet.set('A%d' % row, name)
            cell = 'B%d' % row
            self.sheet.setAlias(cell, name)
            self.parameter_cells[name] = cell
        self.sheet.set(self.parameter_cells[name], '%.12g mm' % value_mm)
        return 'Parameters.' + name

    def cylinder(self, name, start, end, radius_mm, height_expression=None):
        axis = vector(end)-vector(start)
        length = positive(axis.Length, name+' length')
        obj = self.doc.addObject('Part::Cylinder', name)
        obj.Radius = positive(radius_mm, name+' radius')
        obj.Height = length
        obj.Placement = App.Placement(vector(start), App.Rotation(App.Vector(0,0,1), axis))
        if height_expression is not None:
            obj.setExpression('Height', height_expression)
        return obj

    def tube(self, name, start, end, od_mm, id_mm, height_expression=None):
        if not 0 < float(id_mm) < float(od_mm):
            raise ValueError('Tube requires 0 < ID < OD')
        outer = self.cylinder(name+'_Outer', start, end, od_mm/2, height_expression)
        inner = self.cylinder(name+'_Bore', start, end, id_mm/2, height_expression)
        obj = self.doc.addObject('Part::Cut', name)
        obj.Base, obj.Tool = outer, inner
        return obj

    def box(self, name, minimum_C_mm, size_mm):
        obj = self.doc.addObject('Part::Box', name)
        obj.Length, obj.Width, obj.Height = [positive(x, name+' size') for x in size_mm]
        obj.Placement.Base = vector(minimum_C_mm)
        return obj

    def fuse(self, name, objects):
        if len(objects) < 2:
            raise ValueError('Fuse requires at least two objects')
        obj = self.doc.addObject('Part::MultiFuse', name)
        obj.Shapes = list(objects)
        return obj

    def subtract(self, name, base, tool):
        obj = self.doc.addObject('Part::Cut', name)
        obj.Base, obj.Tool = base, tool
        return obj

    def register(self, obj, role, owner, mass_class, density=None, mass_override=None,
                 provenance='', uncertainty='', interface_status='unresolved'):
        if owner not in GROUPS:
            raise ValueError('Unknown ownership group: '+owner)
        if role not in ('manufactured_solid', 'commercial_envelope', 'nonmass_envelope'):
            raise ValueError('Unknown geometry role')
        if mass_class not in ('CAD_material', 'commercial_claim', 'explicit_assumption', 'unknown', 'nonmass'):
            raise ValueError('Unknown mass class')
        if any(r['object_name'] == obj.Name for r in self.rows):
            raise ValueError('Duplicate registered object')
        if density is not None and mass_override is not None:
            raise ValueError('Do not add commercial mass to envelope-density mass')
        if role == 'nonmass_envelope':
            if density is not None or mass_override is not None or mass_class != 'nonmass':
                raise ValueError('Nonmass envelopes must not carry installed mass')
        elif mass_class == 'nonmass':
            raise ValueError('Installed component cannot be silently nonmass')
        if mass_class == 'unknown' and (density is not None or mass_override is not None):
            raise ValueError('Separate unknown sourced mass from assumed scenarios')
        if role != 'nonmass_envelope' and mass_class != 'unknown' and density is None and mass_override is None:
            raise ValueError('Known/assumed mass class requires a numerical basis')
        for field, value in (('OwnershipGroup',owner), ('GeometryRole',role),
                             ('InterfaceStatus',interface_status), ('MassBasis',provenance)):
            obj.addProperty('App::PropertyString', field, 'PDR accounting')
            setattr(obj, field, value)
        self.rows.append({'object_name':obj.Name, 'instance_id':obj.Name,
            'role':role, 'owner':owner, 'mass_class':mass_class,
            'density_kg_m3':density, 'mass_override_kg':mass_override,
            'provenance':provenance, 'uncertainty':uncertainty,
            'interface_status':interface_status})
        return obj

    def measure(self):
        self.doc.recompute()
        rows, known, unresolved = [], [], list(self.omissions)
        for record in self.rows:
            row = dict(record)
            obj = self.doc.getObject(row['object_name'])
            shape = obj.Shape
            solids = list(shape.Solids)
            row['geometry'] = {
                'shape_valid':bool(shape.isValid()),
                'solid_count':len(solids),
                'individual_solids_valid':[bool(s.isValid()) for s in solids],
                'volume_mm3':sum(float(s.Volume) for s in solids),
                'bounds_C_mm':[shape.BoundBox.XMin, shape.BoundBox.YMin, shape.BoundBox.ZMin,
                               shape.BoundBox.XMax, shape.BoundBox.YMax, shape.BoundBox.ZMax]}
            row['properties'] = None
            if row['role'] != 'nonmass_envelope':
                if row['mass_class'] == 'unknown':
                    unresolved.append(row['instance_id']+': mass unresolved')
                elif not solids or not shape.isValid() or any(not s.isValid() for s in solids):
                    unresolved.append(row['instance_id']+': invalid/non-solid geometry prevents mass calculation')
                else:
                    row['properties'] = geometry_properties(shape, row['density_kg_m3'], row['mass_override_kg'])
                    known.append(row)
            rows.append(row)
        subtotal = aggregate([r['properties'] for r in known])
        classes = {c:aggregate([r['properties'] for r in known if r['mass_class']==c])
                   for c in ('CAD_material','commercial_claim','explicit_assumption')}
        groups = {g:aggregate([r['properties'] for r in known if r['owner']==g]) for g in GROUPS}
        return {'schema':'hopper_cad_measurements/1', 'authority':AUTHORITY,
            'candidate_id':self.candidate_id, 'datum_C_mm':self.datum,
            'rows':rows, 'accounted_partial_mass_properties':subtotal,
            'accounted_partial_body_properties':to_body(subtotal,self.datum),
            'mass_class_subtotals':classes, 'group_partial_properties':groups,
            'unresolved_rows':unresolved,
            'supported_complete_installed_mass_kg':None,
            'complete_ledger_reconciliation':'Not established by this kernel',
            'physical_qualification':None,
            'continuous_clearance':None,
            'warning':'Calculated properties cover registered accounted geometry only; no geometry acceptance inferred'}

    def export(self, sandbox, fcstd_relative, step_relative, report_relative):
        root = Path(sandbox).resolve()
        paths = [root/p for p in (fcstd_relative,step_relative,report_relative)]
        for path in paths:
            if not path.resolve().is_relative_to(root):
                raise ValueError('Output outside sandbox')
            if path.exists():
                raise FileExistsError('Preserve previous output: '+str(path))
            path.parent.mkdir(parents=True,exist_ok=True)
        report = self.measure()
        objects = [self.doc.getObject(r['object_name']) for r in self.rows
                   if r['role'] != 'nonmass_envelope']
        if not objects:
            raise ValueError('No installed geometry to export')
        report['step_representation'] = ('Registered manufactured solids and labelled commercial '
            'envelope substitutes; excludes swept/wiring nonmass envelopes and boolean operands')
        report['export_object_names'] = [o.Name for o in objects]
        self.doc.saveAs(str(paths[0]))
        Part.export(objects,str(paths[1]))
        paths[2].write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        return report


def articulated_shape(shape, owner, alpha_deg, beta_deg, outer_origin_C_mm,
                      outer_to_inner_C_neutral_mm):
    """Transform neutral absolute CAD geometry using distinct joint origins.

    CAD equivalent of body Rx(alpha)Ry(beta) is Rx(alpha)Ry(-beta).
    The outer-to-inner translation experiences outer rotation only.
    """
    if owner not in GROUPS:
        raise ValueError('Unknown ownership group')
    result = shape.copy()
    if owner == 'fixed_airframe':
        return result
    origin = vector(outer_origin_C_mm)
    offset = vector(outer_to_inner_C_neutral_mm)
    rx = App.Rotation(App.Vector(1,0,0),float(alpha_deg))
    if owner == 'outer_gimbal':
        rotation = rx
        translation = origin-rotation.multVec(origin)
    else:
        rotation = rx.multiply(App.Rotation(App.Vector(0,1,0),-float(beta_deg)))
        neutral_inner = origin+offset
        moving_inner = origin+rx.multVec(offset)
        translation = moving_inner-rotation.multVec(neutral_inner)
    transform = App.Placement(translation,rotation)
    result.Placement = transform.multiply(result.Placement)
    return result


def clearance_witness(shape_a, shape_b, name_a, name_b, pose):
    """Actual shape distance and intersection volume at one pose, not a bound."""
    distance, pairs, information = shape_a.distToShape(shape_b)
    common = shape_a.common(shape_b)
    return {'pair':[name_a,name_b], 'pose':dict(pose),
        'distance_mm':float(distance),
        'nearest_point_pairs_C_mm':[[xyz(a),xyz(b)] for a,b in pairs],
        'common_solid_volume_mm3':sum(float(s.Volume) for s in common.Solids),
        'common_shape_valid':bool(common.isValid()),
        'distance_support_information':repr(information),
        'scope':'Single sampled pose; zero distance alone does not establish volumetric penetration'}


def support_polygon(contact_xy_mm, cg_xy_mm):
    """Convex hull, minimum directional width, and signed CG edge margins.

    Point contacts only. No friction, compliance, load-sharing or stability
    acceptance is inferred. Use actual projected contact coordinates from runner.
    """
    points = sorted(set((float(p[0]),float(p[1])) for p in contact_xy_mm))
    def cross(o,a,b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    if len(points) < 3:
        return {'hull_xy_mm':points,'minimum_width_mm':0.0,
                'signed_CG_edge_margin_mm':None,'two_dimensional_support':False}
    lower, upper = [], []
    for p in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:
            lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1]+upper[:-1]
    if len(hull)<3:
        return {'hull_xy_mm':hull,'minimum_width_mm':0.0,
                'signed_CG_edge_margin_mm':None,'two_dimensional_support':False}
    widths, margins = [], []
    for a,b in zip(hull,hull[1:]+hull[:1]):
        dx,dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx,dy)
        nx,ny = -dy/length,dx/length
        projections = [nx*p[0]+ny*p[1] for p in hull]
        widths.append(max(projections)-min(projections))
        margins.append(nx*(cg_xy_mm[0]-a[0])+ny*(cg_xy_mm[1]-a[1]))
    return {'hull_xy_mm':hull,'minimum_width_mm':min(widths),
            'signed_CG_edge_margin_mm':min(margins), 'all_edge_margins_mm':margins,
            'two_dimensional_support':True,
            'interpretation':'Study geometry, not an adopted stance-width or contact acceptance criterion'}


def cutting_schedule(lengths_mm, stock_length_mm, end_trim_mm, kerf_per_piece_mm):
    """Feasible best-fit-decreasing packing; explicitly not proof of optimum.

    Call separately for each identical purchased material/section/variant.
    Lengths must already include required insertion/finished-part allowances.
    Every piece consumes one stated kerf; both stock ends consume stated trim.
    """
    stock = positive(stock_length_mm,'stock length')
    trim,kerf = float(end_trim_mm),float(kerf_per_piece_mm)
    if not math.isfinite(trim+kerf) or min(trim,kerf)<0:
        raise ValueError('Trim and kerf must be finite and nonnegative')
    usable = positive(stock-2*trim,'usable stock length')
    items = sorted([(positive(x,'finished length'),i) for i,x in enumerate(lengths_mm)],reverse=True)
    bins = []
    for length,index in items:
        consumption = length+kerf
        if consumption>usable:
            return {'feasible':False,'oversize_piece_index':index,'length_mm':length,
                    'stock_length_mm':stock,'optimality_proven':False}
        choices = [(b['remaining_mm']-consumption,j) for j,b in enumerate(bins)
                   if b['remaining_mm']>=consumption]
        if choices:
            _,j = min(choices)
        else:
            bins.append({'pieces':[],'remaining_mm':usable})
            j = len(bins)-1
        bins[j]['pieces'].append({'piece_index':index,'finished_length_mm':length,'kerf_mm':kerf})
        bins[j]['remaining_mm'] -= consumption
    return {'feasible':True,'stock_count':len(bins),'stock_length_mm':stock,
            'end_trim_each_mm':trim,'bins':bins,'optimality_proven':False,
            'cost_AUD':None,'note':'Whole-stock quantities only; exact sourced net price remains separate'}
