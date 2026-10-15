"""Preliminary native-solid candidate builder M4-01; NOT acceptance evidence.

Uses structural_kernel_m4_01.py. Run this saved script through freecad_run,
headless=True. Its diagnostic main produces exactly these requested outputs:
  cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_01.FCStd
  cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_01.step
  cad/pdr_trade/diagnostic_s2_c14_t_d330_m4_01_arrangement.svg
  analysis/pdr_cad_trade/diagnostic_s2_c14_t_d330_m4_01.json
The FreeCAD tool separately captures its execution log.

build_candidate() supports all 1..4 spine counts, three study sections,
tripod/quadpod and both 279.4/330.2 mm rotor diameters. The diagnostic main
intentionally builds ONE case before a subsequent saved matrix runner.
No source checkout, prior file or previous candidate is overwritten.

Revision applicability: reuse the inspected M2 study as hypotheses only.
Current authority is kernel.AUTHORITY: system r4 and recovered decisions.
Changes from M2 hypotheses: outer/inner rings are 12 mm thick; the bypass
headers are explicit printed solids; lower motor interface/rotor move down
12 mm to accommodate a nonintersecting header/plate stack. These are proposed
geometry changes, not selected interfaces or verified improvements.
"""
import sys
sys.dont_write_bytecode = True
import os
import math
import json
import hashlib
from pathlib import Path
from html import escape
import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
sys.path.insert(0, str(ROOT/'cad/pdr_trade'))
import structural_kernel_m4_01 as K

SECTIONS = {
    'C08': {'od':8.0, 'id':6.0, 'rho':1600.0, 'material':'CFRP_RW',
            'density_sensitivity_kg_m3':[1400,1800]},
    'C14': {'od':14.0, 'id':12.0, 'rho':1600.0, 'material':'CFRP_RW',
            'density_sensitivity_kg_m3':[1400,1800]},
    'AL12': {'od':12.0, 'id':10.0, 'rho':2700.0, 'material':'AL_6063T5',
             'density_sensitivity_kg_m3':[2650,2750]}
}
CONFIG = {
    'schema':'hopper_candidate_geometry_hypothesis/1',
    'authority':K.AUTHORITY,
    'status':'Unselected geometry and material study; no hardware qualification',
    'length_unit':'mm',
    'datum_C_mm':[0,0,0],
    'outer_origin_C_mm':[0,0,-45],
    'outer_to_inner_C_neutral_mm':[0,0,-15],
    'inner_origin_C_neutral_mm':[0,0,-60],
    'rotor_plane_z_C_mm':[-155,-297],
    'spine_length_mm':300,
    'spine_centre_radius_mm':92,
    'fixed_ring_radii_mm':[85,100],
    'fixed_ring_z_mm':[-4,0],
    'leg_attachment_radius_mm':100,
    'leg_attachment_z_mm':-2,
    'foot_sphere_centre_radius_mm':380,
    'foot_sphere_centre_z_mm':-380,
    'foot_sphere_radius_mm':10,
    'leg_tube_od_id_mm':[8,6],
    'joint_socket_length_mm':25,
    'tube_end_inset_mm':2,
    'printed_density_kg_m3':1250,
    'printed_density_sensitivity_kg_m3':[1150,1400],
    'steel_density_kg_m3':7850,
    'steel_density_sensitivity_kg_m3':[7700,8000],
    'cfrp_density_kg_m3':1600,
    'rotor_slab_half_thickness_mm':10,
    'bypass_arm_radius_increment_mm':30,
    'joint_diametral_clearance_mm':0.2,
    'gimbal_study_joint_limits_deg':{'alpha':[-15,15],'beta':[-15,15]},
    'travel_status':'Independent study joint limits, not a resultant cone or hardware rating',
    'material_status':'Unqualified nominal densities and sensitivity hypotheses; no design allowables',
    'price_status':'No prices assigned by this geometry script; unknown purchases are not zero',
    'source_reuse':'M2 configuration is an inspected historical proposal, not current authority',
    'commercial_basis':{
        'observation_date':'2026-10-15',
        'basis':'Peer PROP-CAD-IF-M2-02; current applicability must be reconciled with published sourcing',
        'motor':{'part':'Original SunnySky X2814 KV900 / SS-X2814-900, not III/V3',
                 'url':'https://sunnyskyusa.com/products/sunnysky-x2814-brushless-motors',
                 'mass_kg':0.108,'body_diameter_mm':35,'body_length_mm':36,
                 'overall_length_mm':54,'shaft_diameter_mm':4,
                 'mounting_pattern':None,'mass_inclusions':'Unresolved accessories and retention'},
        'propellers':{'diameter_variants_mm':[279.4,330.2],
                      'parts':['LP11055E','LP11055EP','LP13065E','LP13065EP'],
                      'urls':['https://www.apcprop.com/product/11x5-5e/',
                              'https://www.apcprop.com/product/11x5-5ep/',
                              'https://www.apcprop.com/product/13x6-5e/',
                              'https://www.apcprop.com/product/13x6-5ep/'],
                      'each_mass_oz':[0.81,1.06],
                      'hub_diameter_thickness_bore_in':[0.80,0.41,0.25],
                      'blade_shape':'Artificial distribution proxy; not manufacturer blade geometry',
                      'mass_inclusions':'Adapter-ring inclusion unresolved'},
        'esc':{'part':'Hobbywing 80060442','quantity':2,
               'envelope_mm':[60,25,8],'mass_each_kg':0.036,
               'url':'https://www.hobbywing.com/en/products/skywalker-v2-series274',
               'mass_inclusions':'Lead and connector inclusion unresolved'},
        'battery':{'variant':'Peer B02: Zeee 3S 5200 mAh 50C Deans two-pack',
                   'installed_quantity':1,'purchased_battery_count':2,
                   'envelope_mm':[132,43,29],'mass_each_kg':0.343,
                   'status':'Comparison only; exact product handle and supply evidence remain peer-owned'},
        'servos':{'variant':'Peer EMAX ES08MA II standard-voltage analog comparison',
                  'mass_each_kg':0.012,'mass_sensitivity_kg':[0.011,0.013],
                  'envelope_status':'35 x 20 x 35 mm packaging hypotheses, NOT supplier dimensions',
                  'loaded_capability':None},
        'currency':None,'stock_status':'Not reassessed by this CAD script',
        'tax_shipping':'No monetary subtotal; supplier tax basis and shipping exclusions remain sourcing-ledger fields'}
}


def polar(radius, degrees, z):
    a = math.radians(degrees)
    return K.vector((radius*math.cos(a), radius*math.sin(a), z))


def between(a,b,distance_from_a):
    delta = b-a
    return a + delta*(float(distance_from_a)/delta.Length)


def tube(c,name,a,b,od,id_):
    return c.tube(name,K.xyz(a),K.xyz(b),od,id_)


def cut_many(c,name,base,tools):
    result = base
    for i, tool in enumerate(tools):
        result = c.subtract(name+'_Cut%d'%i,result,tool)
    return result


def material(c,obj,owner='fixed_airframe',rho=1250,material_name='PETG_PRINTED'):
    return c.register(obj,'manufactured_solid',owner,'CAD_material',density=rho,
        provenance='Unselected study material '+material_name+'; density is an explicit hypothesis',
        uncertainty='No supplier-qualified laminate, print, joint, strength or density bounds',
        interface_status='Custom study geometry; fits, retention and load capability unqualified')


def commercial(c,obj,owner,mass,basis):
    return c.register(obj,'commercial_envelope',owner,'commercial_claim',mass_override=mass,
        provenance=basis+'; peer-reported observation dated 2026-10-15; not a selected component',
        uncertainty='Mass inclusion and geometric distribution unresolved; uniform-volume inertia approximation',
        interface_status='No commercial hole pattern or attachment acceptance')


def sphere(c,name,centre,radius):
    obj = c.doc.addObject('Part::Sphere',name)
    obj.Radius = radius
    obj.Placement.Base = centre
    return obj


def beam_xy(c,name,a,b,width,height,z):
    delta = b-a
    obj = c.box(name,[0,-width/2,0],[delta.Length,width,height])
    obj.Placement = App.Placement(App.Vector(a.x,a.y,z),
        App.Rotation(App.Vector(0,0,1),math.degrees(math.atan2(delta.y,delta.x))))
    return obj


def tray_with_collars(c,name,spine_xy,section,z,size,collar_bottom,collar_top):
    plate = c.box(name+'_Plate',[-size[0]/2,-size[1]/2,z],[size[0],size[1],4])
    raw = [plate]
    bores = []
    for i,p in enumerate(spine_xy):
        a = App.Vector(p.x,p.y,collar_bottom)
        b = App.Vector(p.x,p.y,collar_top)
        raw.append(c.cylinder(name+'_Collar%d'%i,K.xyz(a),K.xyz(b),section['od']/2+3))
        direction = App.Vector(p.x,p.y,0)
        direction.normalize()
        raw.append(beam_xy(c,name+'_Arm%d'%i,direction*25,App.Vector(p.x,p.y,0),10,4,z))
        bores.append(c.cylinder(name+'_SpineBore%d'%i,
            [p.x,p.y,collar_bottom-1],[p.x,p.y,collar_top+1],section['od']/2+0.1))
    return cut_many(c,name,c.fuse(name+'_Raw',raw),bores)


def build_candidate(spine_count, section_id, leg_count, rotor_diameter_mm, label):
    if spine_count not in (1,2,3,4) or leg_count not in (3,4):
        raise ValueError('Outside authorized structural comparison')
    if section_id not in SECTIONS or rotor_diameter_mm not in (279.4,330.2):
        raise ValueError('Unknown study section or rotor branch')
    c = K.Candidate('PDR_'+label,label,CONFIG['datum_C_mm'])
    s = SECTIONS[section_id]
    spine_expr = c.length_parameter('SpineLength',CONFIG['spine_length_mm'])
    spine_xy = [polar(92,360*i/spine_count,0) for i in range(spine_count)]
    stock = {'spines':[], 'landing_legs':[], 'bypass_arms':[]}
    contacts, leg_axes = [], []
    azimuths = [90,210,330] if leg_count==3 else [45,135,225,315]

    # One fixed leg-attachment ring. Its upper plane is z=0; D is fixed there.
    fixed_ring = c.tube('LegRingCore',[0,0,-4],[0,0,0],200,170)
    ring_raw, ring_bores = [fixed_ring], []
    for i,angle in enumerate(azimuths):
        start = polar(100,angle,-2)
        end = polar(380,angle,-380)
        direction = end-start
        length = direction.Length
        direction.normalize()
        leg_axes.append((start,end,direction,length))
        ring_raw.append(c.cylinder('LegSocketOuter%d'%i,K.xyz(start),K.xyz(start+direction*25),7))
        ring_bores.append(c.cylinder('LegSocketBore%d'%i,
            K.xyz(start-direction*10),K.xyz(start+direction*26),4.1))
    ring = cut_many(c,'FixedLegAttachment',c.fuse('FixedLegAttachmentRaw',ring_raw),ring_bores)
    material(c,ring)
    ring.addProperty('App::PropertyString','DatumReference')
    ring.DatumReference = 'Upper reference plane z_C=0 mm intersects neutral centreline at FixedDatumD'

    for i,(start,end,direction,length) in enumerate(leg_axes):
        leg = tube(c,'LandingTube%d'%i,start+direction*2,end-direction*2,8,6)
        material(c,leg,rho=1600,material_name='CFRP_RW assumed')
        stock['landing_legs'].append(length-4)
        socket = c.cylinder('FootSocket%d'%i,K.xyz(end-direction*25),K.xyz(end),7)
        ball = sphere(c,'FootBall%d'%i,end,10)
        foot_raw = c.fuse('FootRaw%d'%i,[socket,ball])
        bore = c.cylinder('FootBore%d'%i,K.xyz(end-direction*26),K.xyz(end-direction),4.1)
        material(c,c.subtract('Foot%d'%i,foot_raw,bore))
        contacts.append([end.x,end.y,end.z-10])

    for i,p in enumerate(spine_xy):
        spine = c.tube('Spine%d'%i,K.xyz(p),[p.x,p.y,300],s['od'],s['id'],spine_expr)
        material(c,spine,rho=s['rho'],material_name=s['material'])
        stock['spines'].append(300.0)
    material(c,tray_with_collars(c,'BatterySupport',spine_xy,s,24,[90,70],0,32))
    material(c,tray_with_collars(c,'ElectronicsSupport',spine_xy,s,211,[80,70],201,225))
    material(c,c.box('BatteryBottomPad',[-22.5,-15.5,28],[45,31,4]))
    for sign in (-1,1):
        x = 22.5 if sign>0 else -25.5
        material(c,c.box('BatteryLowerGuide'+str(sign),[x,-17.5,32],[3,35,18]))
    battery = c.box('BatteryEnvelope',[-21.5,-14.5,32],[43,29,132])
    commercial(c,battery,'fixed_airframe',0.343,'Zeee B02 comparison, one installed battery only')
    for i,z in enumerate((65,140)):
        outer = c.box('BatteryStrapOuter%d'%i,[-25.5,-18.5,z],[51,37,8])
        inner = c.box('BatteryStrapVoid%d'%i,[-23.5,-16.5,z-1],[47,33,10])
        strap = c.subtract('BatteryStrap%d'%i,outer,inner)
        material(c,strap,rho=1150,material_name='Generic strap material, assumed; fastening unresolved')

    for i,y in enumerate((-40,15)):
        material(c,c.box('ESCShelf%d'%i,[40,y,28],[18,25,4]))
        esc = c.box('ESCEnvelope%d'%i,[45,y,32],[8,25,60])
        commercial(c,esc,'fixed_airframe',0.036,'Hobbywing 80060442; envelope axes permuted for vertical installation')
    electronics = c.box('UnselectedElectronicsEnvelope',[-22.5,-22.5,215],[45,45,20])
    c.register(electronics,'commercial_envelope','fixed_airframe','unknown',
        provenance='Packaging reservation only, not selected controller/sensors/receiver',
        uncertainty='Mass, interfaces and functions unresolved')

    # Custom bearing geometry only: no invented commercial bearing designation.
    fixed_supports = []
    outer_pin_tools = []
    for j,sign in enumerate((-1,1)):
        xmin = 65 if sign>0 else -96
        bridge = c.box('FixedPivotBridge%d'%j,[xmin,-7,-12],[31,14,8])
        xmin2 = 65 if sign>0 else -77
        block = c.box('FixedPivotBlock%d'%j,[xmin2,-7,-53],[12,14,41])
        hole = c.cylinder('FixedPivotHousingBore%d'%j,
            [sign*64,0,-45],[sign*78,0,-45],4.1)
        support = c.subtract('FixedPivotSupport%d'%j,
            c.fuse('FixedPivotSupportRaw%d'%j,[bridge,block]),hole)
        material(c,support)
        bush = c.tube('OuterPivotBushing%d'%j,[sign*65,0,-45],[sign*77,0,-45],8,5.2)
        material(c,bush,rho=1250,material_name='Printed bushing hypothesis; wear/friction unresolved')
        pin = c.cylinder('OuterPivotPin%d'%j,[sign*54,0,-45],[sign*82,0,-45],2.5)
        material(c,pin,'outer_gimbal',7850,'Generic steel pin; retention unresolved')
        outer_pin_tools.append(c.cylinder('OuterRingPinBore%d'%j,
            [sign*50,0,-45],[sign*64,0,-45],2.6))
        fixed_supports.append(support.Name)

    outer_ring = c.tube('OuterRingCore',[0,0,-51],[0,0,-39],120,104)
    outer_raw = [outer_ring]
    outer_bores = list(outer_pin_tools)
    for j,sign in enumerate((-1,1)):
        ymin = 46 if sign>0 else -60
        outer_raw.append(c.box('InnerPivotLug%d'%j,[-7,ymin,-69],[14,14,24]))
        outer_bores.append(c.cylinder('InnerPivotHousingBore%d'%j,
            [0,sign*45,-60],[0,sign*61,-60],4.1))
        bush = c.tube('InnerPivotBushing%d'%j,[0,sign*46,-60],[0,sign*60,-60],8,5.2)
        material(c,bush,'outer_gimbal',1250,'Printed bushing hypothesis')
        pin = c.cylinder('InnerPivotPin%d'%j,[0,sign*36,-60],[0,sign*64,-60],2.5)
        material(c,pin,'inner_module_nonspinning',7850,'Generic steel pin; retention unresolved')
    outer = cut_many(c,'OuterGimbal',c.fuse('OuterGimbalRaw',outer_raw),outer_bores)
    material(c,outer,'outer_gimbal')
    inner_ring = c.tube('InnerRingCore',[0,0,-66],[0,0,-54],84,68)
    inner_bridge = c.box('InnerCarrierBridge',[-40,-6,-66],[80,12,12])
    inner_raw = c.fuse('InnerCarrierRaw',[inner_ring,inner_bridge])
    inner_holes = [c.cylinder('InnerRingPinBore%d'%j,
        [0,sign*30,-60],[0,sign*45,-60],2.6) for j,sign in enumerate((-1,1))]
    material(c,cut_many(c,'InnerCarrier',inner_raw,inner_holes),'inner_module_nonspinning')
    suspension = c.tube('CentralSuspension',[0,0,-83],[0,0,-66],14,10)
    material(c,suspension,'inner_module_nonspinning',1600,'CFRP hypothetical custom section, procurement unresolved')

    radius = rotor_diameter_mm/2
    arm_radius = radius+30
    for name,z in (('UpperHeader',-95),('LowerHeader',-237)):
        material(c,c.box(name,[-arm_radius-8,-6,z],[2*arm_radius+16,12,12]),'inner_module_nonspinning')
    for j,sign in enumerate((-1,1)):
        x = sign*arm_radius
        arm = c.tube('BypassArm%d'%j,[x,0,-225],[x,0,-95],8,6)
        material(c,arm,'inner_module_nonspinning',1600,'CFRP_RW assumed')
        stock['bypass_arms'].append(130)
        for k,(a,b) in enumerate(((-119,-95),(-225,-201))):
            socket = c.tube('BypassSocket%d_%d'%(j,k),[x,0,a],[x,0,b],14,8.2)
            material(c,socket,'inner_module_nonspinning')

    rotor_names, propeller_names, motor_names = [], [], []
    for i,(plate_z,rotor_z) in enumerate(((-99,-155),(-241,-297))):
        owner = ('upper_spinning_group','lower_spinning_group')[i]
        material(c,c.box('UnresolvedMotorPlate%d'%i,[-20,-20,plate_z],[40,40,4]),'inner_module_nonspinning')
        # Motor-to-plate 2 mm gap deliberately exposes the unresolved interface.
        motor_top = plate_z-2
        motor_body = c.cylinder('MotorBody%d'%i,[0,0,motor_top-36],[0,0,motor_top],17.5)
        shaft = c.cylinder('MotorShaftProxy%d'%i,[0,0,motor_top-54],[0,0,motor_top-36],2)
        motor = c.fuse('MotorEnvelope%d'%i,[motor_body,shaft])
        commercial(c,motor,'inner_module_nonspinning',0.108,
            'Original SunnySky X2814 KV900; shaft projection is an unverified distribution hypothesis')
        motor_names.append(motor.Name)
        c.omissions.append(motor.Name+': internal rotating/stationary mass split unknown; module lump is bookkeeping only')
        hub = c.tube('PropHubProxy%d'%i,[0,0,rotor_z-5.207],[0,0,rotor_z+5.207],20.32,6.35)
        blade_bar = c.box('PropBladeBar%d'%i,[-radius,-10,rotor_z-1.25],[2*radius,20,2.5])
        blade_disc = c.cylinder('PropBladeClip%d'%i,[0,0,rotor_z-1.25],[0,0,rotor_z+1.25],radius)
        blade = c.doc.addObject('Part::Common','PropBladeProxy%d'%i)
        blade.Base,blade.Tool = blade_bar,blade_disc
        prop_raw = c.fuse('PropProxyRaw%d'%i,[hub,blade])
        prop_bore = c.cylinder('PropBore%d'%i,[0,0,rotor_z-6],[0,0,rotor_z+6],3.175)
        prop = c.subtract('PropellerDistributionProxy%d'%i,prop_raw,prop_bore)
        mass_oz = 0.81 if rotor_diameter_mm==279.4 else 1.06
        commercial(c,prop,owner,mass_oz*0.028349523125,
            'APC candidate propeller mass; artificial blade distribution, not manufacturer inertia')
        propeller_names.append(prop.Name)
        sweep = c.cylinder('RotorSweptSlab%d'%i,[0,0,rotor_z-10],[0,0,rotor_z+10],radius)
        c.register(sweep,'nonmass_envelope',owner,'nonmass',
            provenance='Unqualified rigid swept slab, full disc including hub region',
            uncertainty='Blade flex, mounting tolerances and retention not qualified')
        rotor_names.append(sweep.Name)

    for i,(minimum,owner) in enumerate((([55,-40,2],'fixed_airframe'),([-17.5,44,-31],'outer_gimbal'))):
        servo = c.box('ActuatorPackagingEnvelope%d'%i,minimum,[35,20,35])
        commercial(c,servo,owner,0.012,
            'EMAX ES08MA II candidate mass; envelope dimensions are packaging assumptions only')
    cable = c.tube('CentralWiringAllowance',[0,0,0],[0,0,180],10,6)
    c.register(cable,'nonmass_envelope','fixed_airframe','nonmass',
        provenance='Fixed cable-routing reservation only, not a complete harness',
        uncertainty='Moving-joint cable loops, strain relief and bend radii not modeled')

    c.omissions.extend([
        'Motor plate hole patterns, adapters, shaft engagement and opposite-spin retention unresolved',
        'Commercial motor/ESC/prop accessory mass inclusions not reconciled',
        'Servo mounts, horns, rod ends, links, linkage ratio and loaded response unresolved',
        'Pivot axial retainers and bearing fits not realized; pins alone are not retained assemblies',
        'Complete controller, sensors, receiver/abort and regulation/distribution/protection not selected',
        'Additional power/signal wiring, connectors, insulation and moving cable loops incomplete',
        'Adhesive, clamp bolts, nuts, washers and positive tube anti-rotation not included',
        'Battery strap closure and upper lateral restraint not realized',
        'Material and joint qualification, leg compliance and dynamic contact not established',
        'Integrated contra-rotating commercial branch still awaits applicable mounting/rotor-offset evidence'
    ])
    c.doc.recompute()
    # Explicit visibility: only registered final geometry, not CSG operands.
    registered = {row['object_name'] for row in c.rows}
    for obj in c.doc.Objects:
        if hasattr(obj,'ViewObject') and obj.ViewObject is not None:
            obj.ViewObject.Visibility = obj.Name in registered and not obj.Name.startswith('RotorSwept')
    c.metadata = {
        'configuration':CONFIG,'section':s,'spine_count':spine_count,
        'landing_leg_count':leg_count,'gimbal_axis_count':2,
        'rotor_diameter_mm':rotor_diameter_mm,'payload_mass_kg':0,
        'neutral_foot_contact_proxies_C_mm':contacts,
        'contact_assumption':'Sphere-bottom points at neutral attitude only; articulate actual foot solids for tilted contact',
        'stock_finished_lengths_mm':stock,
        'rotor_object_names':rotor_names,'propeller_proxy_names':propeller_names,
        'motor_envelope_names':motor_names,
        'load_path':'Fixed ring -> fixed pivot brackets -> x pins -> outer ring/lugs -> y pins -> inner carrier -> central suspension/header -> two bypass arms/lower header -> motor interface plates; commercial motor connections unresolved',
        'interface_status':'Blank motor plates, generic pivots and actuator reservations are NOT accepted interfaces',
        'rotor_spin_assignment':None,
        'joint_origins_body_m':{'r_DOx':[0,0,0.045],'d_OxOy_outer':[0,0,0.015]},
        'rotor_offsets_inner_body_m':[[0,0,0.095],[0,0,0.237]],
        'full_matrix_rule':'1..4 spines x C08/C14/AL12 x 3/4 legs x 279.4/330.2 mm = 48 candidates',
        'parameter_edit_scope':'SpineLength changes tube lengths only; tray positions are independent native parameters. This is not a claim of automatic whole-assembly redesign.'
    }
    return c


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arrangement_svg(c,path):
    """Orthographic line projection from actual registered shapes, not a photo.
    This is an arrangement drawing, not a fabrication/mounting release.
    """
    c.doc.recompute()
    elements = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1000" viewBox="0 0 1400 1000">',
        '<rect width="1400" height="1000" fill="white"/>',
        '<g font-family="sans-serif" font-size="16" fill="black">',
        '<text x="25" y="28">'+escape(c.candidate_id)+' — unselected arrangement, CAD mm</text>',
        '<text x="25" y="53">Native-solid projections; commercial shapes are proxies. NOT FOR FABRICATION.</text>',
        '<text x="25" y="78">Front: +C x right, +C z up. Top: +C x right, +C y up. D=(0,0,0) fixed.</text>',
        '</g>']
    scale = 0.78
    for view,origin in (('front',(350,390)),('top',(1040,470))):
        for row in c.rows:
            if row['role']=='nonmass_envelope':
                continue
            shape = c.doc.getObject(row['object_name']).Shape
            color = '#156082' if row['role']=='manufactured_solid' else '#ad6500'
            for edge in shape.Edges:
                points = edge.discretize(Deflection=1.0)
                if len(points)<2:
                    continue
                coords = []
                for p in points:
                    ordinate = p.z if view=='front' else p.y
                    coords.append('%.3f,%.3f'%(origin[0]+scale*p.x,origin[1]-scale*ordinate))
                elements.append('<polyline points="'+' '.join(coords)+'" fill="none" stroke="'+color+'" stroke-width="0.6"/>')
        ox,oy = origin
        elements.append('<path d="M %g %g h 18 M %g %g v 18" stroke="red"/>'%(ox-9,oy,ox,oy-9))
        elements.append('<text x="%g" y="%g" font-size="15">D / %s</text>'%(ox+12,oy-10,view))
    meta = c.metadata
    notes = [
        'Study: %d spines, %d CFRP legs; rotor diameter %.1f mm.'%(meta['spine_count'],meta['landing_leg_count'],meta['rotor_diameter_mm']),
        'Outer pivot C=(0,0,-45) mm; inner neutral C=(0,0,-60) mm; alpha about body x, beta about carried y.',
        'Rotor planes C z=-155/-297 mm. Joint travel study +/-15 deg EACH; clearance not established by this drawing.',
        'Blue: custom material solids. Brown: commercial/distribution proxies. Swept slabs omitted from linework and mass.',
        'Motor patterns, servo mounts/linkages, pivot retention, harness and joint qualification remain unresolved.',
        'Lengths are mm. Body point conversion: 0.001 diag(1,-1,-1) (p_C-D_C). No dimensions obtained from imagery.'
    ]
    for i,note in enumerate(notes):
        elements.append('<text x="25" y="%d" font-family="sans-serif" font-size="15">%s</text>'%(850+23*i,escape(note)))
    elements.append('</svg>')
    path.write_text('\n'.join(elements),encoding='utf-8')


def diagnostic_main():
    stem = 'diagnostic_s2_c14_t_d330_m4_01'
    files = {
        'fcstd':'cad/pdr_trade/'+stem+'.FCStd',
        'step':'cad/pdr_trade/'+stem+'.step',
        'drawing':'cad/pdr_trade/'+stem+'_arrangement.svg',
        'report':'analysis/pdr_cad_trade/'+stem+'.json'
    }
    for rel in files.values():
        path = ROOT/rel
        if path.exists():
            raise FileExistsError('Preserve existing output: '+str(path))
        path.parent.mkdir(parents=True,exist_ok=True)
    c = build_candidate(2,'C14',3,330.2,stem)
    report = c.export(ROOT,files['fcstd'],files['step'],files['report'])
    report['candidate_metadata'] = c.metadata
    cg = report['accounted_partial_mass_properties']['centroid_C_mm']
    contacts = c.metadata['neutral_foot_contact_proxies_C_mm']
    report['partial_CG_support_polygon'] = K.support_polygon([p[:2] for p in contacts],cg[:2])
    report['one_foot_removed_support'] = [K.support_polygon(
        [p[:2] for j,p in enumerate(contacts) if j!=i],cg[:2]) for i in range(len(contacts))]
    report['support_scope'] = 'Accounted partial-mass centroid and neutral point-contact proxy; not complete-vehicle stability'
    report['spine_cutting_schedule'] = K.cutting_schedule(c.metadata['stock_finished_lengths_mm']['spines'],1000,5,3)
    report['leg_and_bypass_cutting_schedule'] = K.cutting_schedule(
        c.metadata['stock_finished_lengths_mm']['landing_legs']+c.metadata['stock_finished_lengths_mm']['bypass_arms'],1000,5,3)
    report['cutting_limitations'] = 'Spine/leg stock separated here even when sections match; matrix runner must consolidate identical purchased variants. Central suspension and other stock remain unresolved.'
    arrangement_svg(c,ROOT/files['drawing'])
    document_name = c.doc.Name
    expected = report['export_object_names']
    expected_volume = sum(row['geometry']['volume_mm3'] for row in report['rows'] if row['role']!='nonmass_envelope')
    App.closeDocument(document_name)
    reopened = App.openDocument(str(ROOT/files['fcstd']))
    reopened.recompute()
    reopened_rows = []
    for name in expected:
        obj = reopened.getObject(name)
        if obj is None:
            reopened_rows.append({'name':name,'exists':False})
            continue
        solids = list(obj.Shape.Solids)
        reopened_rows.append({'name':name,'exists':True,'solid_count':len(solids),
            'shape_valid':bool(obj.Shape.isValid()),'solids_valid':[bool(s.isValid()) for s in solids],
            'volume_mm3':sum(float(s.Volume) for s in solids)})
    step = Part.read(str(ROOT/files['step']))
    report['reopen_observations'] = {
        'fcstd_objects':reopened_rows,
        'step_shape_valid':bool(step.isValid()),
        'step_solid_count':len(step.Solids),
        'step_individual_solids_valid':[bool(s.isValid()) for s in step.Solids],
        'step_volume_mm3':sum(float(s.Volume) for s in step.Solids),
        'expected_registered_volume_mm3':expected_volume,
        'scope':'Measurements only; independent artifact-bound verification still required'}
    # Test a declared edit without overwriting the preserved candidate file.
    sheet = reopened.getObject('Parameters')
    original_volume = float(reopened.getObject('Spine0').Shape.Volume)
    sheet.set('B1','310 mm')
    reopened.recompute()
    edited = reopened.getObject('Spine0')
    report['parameter_edit_observations'] = {
        'parameter':'Parameters.SpineLength','original_mm':300,'edited_mm':310,
        'original_spine_volume_mm3':original_volume,
        'edited_spine_volume_mm3':float(edited.Shape.Volume),
        'edited_spine_z_extent_mm':float(edited.Shape.BoundBox.ZLength),
        'edited_shape_valid':bool(edited.Shape.isValid()),
        'expected_volume_ratio':310/300,
        'saved_candidate_modified':False,
        'scope':'Tube length only, not a whole-assembly adaptation check'}
    sheet.set('B1','300 mm')
    reopened.recompute()
    App.closeDocument(reopened.Name)
    report['artifact_file_sha256'] = {key:digest(ROOT/files[key]) for key in ('fcstd','step','drawing')}
    report['generation_source_sha256'] = {
        'builder':digest(ROOT/'cad/pdr_trade/structural_candidate_builder_m4_01.py'),
        'kernel':digest(ROOT/'cad/pdr_trade/structural_kernel_m4_01.py')}
    report['unperformed_checks'] = [
        'Unintended material overlap and custom mounting-interface measurements',
        'Both rotor envelopes versus structure/mechanism/wiring over articulated domain',
        'Ground clearance under body tilt, compression and terrain sensitivity',
        'Continuous clearance bounds and fabrication/deformation allowances',
        'Complete mass/cost reconciliation and commercial accessory inclusion',
        'All 48 structural alternatives and integrated-module branch',
        'Independent unit/frame/inertia fixtures and verify_command acceptance',
        'GUI screenshot inspection and all physical load/contact tests']
    (ROOT/files['report']).write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'candidate':stem,'outputs':list(files.values()),
        'scope':'Diagnostic generation and reopen observations only; no geometry or physical acceptance'},allow_nan=False))


if __name__ == '__main__':
    diagnostic_main()
