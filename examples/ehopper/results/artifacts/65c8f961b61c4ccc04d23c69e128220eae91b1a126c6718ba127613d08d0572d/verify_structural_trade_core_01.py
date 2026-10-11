"""Artifact-bound verification of the preliminary r12 structural core.

Publish the configuration, supplier register, analysis source, results and this
checker before invoking verify_command; include every tested artifact Ref.
Stdout contains only VerificationResult JSON. Diagnostics use stderr.
No source checkout is changed. No CAD or physical acceptance is evaluated.
The independent checks do not call the analysis compute() implementation.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import math
from collections import Counter
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
D = Decimal
CHECKS = {}
FAILURES = []


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def near(a, b, name, atol=1e-12, rtol=2e-9):
    require(not isinstance(a, bool) and isinstance(a, (int, float)), name + ': not numeric')
    require(math.isfinite(a) and math.isfinite(b), name + ': nonfinite')
    require(abs(a-b) <= atol + rtol*abs(b), name + ': numerical mismatch')


def vector(a, b, name, atol=1e-12):
    require(len(a) == len(b), name + ': length mismatch')
    for x, y in zip(a, b):
        near(x, y, name, atol)


def run_check(name, function):
    try:
        function()
        CHECKS[name] = True
    except Exception as exc:
        CHECKS[name] = False
        FAILURES.append(name + ': ' + type(exc).__name__ + ': ' + str(exc))
        print(FAILURES[-1], file=sys.stderr)


def path_in_root(name):
    p = Path(name)
    p = (ROOT/p).resolve() if not p.is_absolute() else p.resolve()
    p.relative_to(ROOT)
    return p


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_object(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'Duplicate JSON key: ' + key)
        out[key] = value
    return out


def parse(raw):
    def reject(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=strict_object, parse_constant=reject)


def index(rows, key):
    out = {}
    for row in rows:
        k = key(row)
        require(k not in out, 'Duplicate result row: ' + str(k))
        out[k] = row
    return out


def cents(value):
    return str(value.quantize(D('0.01'), rounding=ROUND_HALF_UP))


def section(product):
    ro, ri = product['od_mm']/2000, product['id_mm']/2000
    require(ro > ri >= 0, 'Invalid annular section')
    return math.pi*(ro*ro-ri*ri), math.pi*(ro**4-ri**4)/4


def leg_length(seed, geometry):
    span = math.hypot(seed['foot_radius_mm']-seed['leg_attachment_radius_mm'],
                      seed['leg_attachment_z_mm']-geometry['foot_tube_socket_reference_z_mm'])
    return span + geometry['leg_root_insertion_extension_mm'] + geometry['leg_foot_insertion_extension_mm']


@lru_cache(maxsize=None)
def optimal_bins(weights, capacity):
    """Independent exhaustive subset-partition dynamic program."""
    if any(w > capacity for w in weights):
        return None
    n = len(weights)
    require(0 < n <= 16, 'Packing verifier supports 1 through 16 pieces per product')
    sums = [0]*(1 << n)
    for mask in range(1, 1 << n):
        bit = mask & -mask
        sums[mask] = sums[mask ^ bit] + weights[bit.bit_length()-1]
    @lru_cache(maxsize=None)
    def solve(mask):
        if mask == 0:
            return 0
        if sums[mask] <= capacity:
            return 1
        first = mask & -mask
        rest = mask ^ first
        sub = rest
        best = mask.bit_count()
        while True:
            group = first | sub
            if sums[group] <= capacity:
                best = min(best, 1 + solve(mask ^ group))
            if sub == 0:
                break
            sub = (sub-1) & rest
        return best
    return solve((1 << n)-1)


def charge_um(length_mm, kerf_mm):
    return int(((D(str(length_mm))+D(str(kerf_mm)))*1000).to_integral_value(rounding=ROUND_CEILING))


def verify_sections(cfg, result):
    products = {p['id']: p for p in cfg['supplier_candidates']}
    require(set(result['sections']) == set(products), 'Section coverage')
    for pid, p in products.items():
        area, inertia = section(p)
        got = result['sections'][pid]
        near(got['area_m2'], area, pid+' area', 1e-20)
        near(got['I_m4'], inertia, pid+' inertia', 1e-24)
        near(got['J_m4'], 2*inertia, pid+' polar inertia', 1e-24)
        material = cfg['material_sensitivity_inputs'][p['material']]
        for field, parameter, inputs, factor in [
            ('linear_mass_kg_m','density_kg_m3','density_kg_m3',area),
            ('EI_N_m2','E_Pa','axial_E_Pa',inertia),
            ('GJ_N_m2','G_Pa','effective_G_Pa',2*inertia)]:
            require([x[parameter] for x in got[field]] == material[inputs], pid+' property cases')
            for row in got[field]:
                near(row['value'], row[parameter]*factor, pid+' '+field)
        require(got['material_acceptance'] is None, 'Unsupported material acceptance')


def verify_spines(cfg, result):
    geom = cfg['geometry_hypotheses']
    products = [p for p in cfg['supplier_candidates'] if 'spine' in p['roles']]
    rows = index(result['spine_models'], lambda r: (r['layout'],r['product'],r['length_mm']))
    expected = list(itertools.product(geom['spine_layouts'],products,geom['spine_finished_lengths_mm']))
    require(len(rows) == len(expected), 'Spine model coverage')
    ks = cfg['load_and_stability_sensitivities']['effective_length_factors_for_Euler_screen']
    for layout, product, length in expected:
        row = rows[(layout['id'],product['id'],length)]
        if 'xy_mm' in layout:
            pts = [[v/1000 for v in xy] for xy in layout['xy_mm']]
        else:
            pts = [[layout['radius_mm']/1000*math.cos(math.radians(t)),
                    layout['radius_mm']/1000*math.sin(math.radians(t))] for t in layout['azimuths_deg']]
        require(len(pts) == layout['count'], 'Spine input count')
        require(len(row['xy_m']) == len(pts), 'Spine output count')
        for actual, expected_point in zip(row['xy_m'],pts):
            vector(actual,expected_point,'Spine placement')
        centre = [sum(p[j] for p in pts)/len(pts) for j in range(2)]
        vector(row['section_centroid_xy_m'],centre,'Spine section centroid')
        area, inertia = section(product)
        xx = sum(inertia+area*(p[1]-centre[1])**2 for p in pts)
        yy = sum(inertia+area*(p[0]-centre[0])**2 for p in pts)
        xy = -sum(area*(p[0]-centre[0])*(p[1]-centre[1]) for p in pts)
        es = cfg['material_sensitivity_inputs'][product['material']]['axial_E_Pa']
        require([x['E_Pa'] for x in row['cases']] == es, 'Spine modulus coverage')
        for case in row['cases']:
            e = case['E_Pa']
            near(case['independent_member_EI_sum_N_m2'],len(pts)*e*inertia,'Independent EI')
            vector(case['ideal_shear_coupled_EI_matrix_N_m2'][0],[e*xx,e*xy],'Coupled EI row 0')
            vector(case['ideal_shear_coupled_EI_matrix_N_m2'][1],[e*xy,e*yy],'Coupled EI row 1')
            eig = case['ideal_shear_coupled_principal_EI_N_m2']
            require(len(eig) == 2 and 0 < eig[0] <= eig[1], 'Principal EI ordering')
            near(sum(eig),e*(xx+yy),'Principal EI trace')
            near(eig[0]*eig[1],e*e*(xx*yy-xy*xy),'Principal EI determinant')
            require([v['K'] for v in case['individual_member_Euler_cases']] == ks, 'Spine Euler cases')
            for v in case['individual_member_Euler_cases']:
                near(v['critical_load_N'],math.pi**2*e*inertia/(v['K']*length/1000)**2,'Spine Euler load')
        require(row['assembly_acceptance'] is None, 'Unsupported frame acceptance')


def verify_candidates(cfg, result):
    geom, account = cfg['geometry_hypotheses'], cfg['purchase_and_mass_accounting']
    spines = [p for p in cfg['supplier_candidates'] if 'spine' in p['roles']]
    legs = [p for p in cfg['supplier_candidates'] if 'leg' in p['roles']]
    rows = index(result['candidates'],lambda r:r['id'])
    combinations = list(itertools.product(geom['layout_seeds'],geom['landing_arrangements'],geom['spine_layouts'],geom['spine_finished_lengths_mm'],spines,legs))
    require(result['candidate_count'] == len(rows) == len(combinations), 'Candidate enumeration')
    for seed, arrangement, layout, length, sp, lp in combinations:
        cid = '|'.join([seed['id'],arrangement['id'],layout['id'],'L'+str(length),sp['id'],lp['id']])
        row = rows[cid]
        for key,value in [('seed',seed['id']),('arrangement',arrangement['id']),('spine_layout',layout['id']),('spine_product',sp['id']),('leg_product',lp['id']),('spine_length_mm',length)]:
            require(row[key] == value, cid+' identity '+key)
        leg_mm = leg_length(seed,geom)
        near(row['leg_length_mm'],leg_mm,'Finished leg length')
        expected_groups = {}
        for product,count,cut,role in [(sp,layout['count'],length,'spine'),(lp,arrangement['count'],leg_mm,'leg')]:
            group = expected_groups.setdefault(product['id'],{'product':product,'cuts':{}})
            group['cuts'].update({role+'_'+str(j+1):cut for j in range(count)})
        purchases = index(row['purchase_groups'],lambda r:r['product_id'])
        mass_rows = index(row['tube_mass_groups'],lambda r:r['product_id'])
        require(set(mass_rows) == set(expected_groups), 'Mass ownership coverage')
        require(set(purchases) <= set(expected_groups), 'Unexpected purchased product')
        displayed, policy = D(0), D(0)
        net_confirmed, feasible = True, True
        low, high = 0.0, 0.0
        for pid, expected_group in expected_groups.items():
            product, cuts = expected_group['product'],expected_group['cuts']
            mass_row = mass_rows[pid]
            installed = sum(cuts.values())/1000
            volume = installed*section(product)[0]
            near(mass_row['installed_length_m'],installed,'Installed length')
            near(mass_row['tube_volume_m3'],volume,'Tube volume',1e-20)
            densities = cfg['material_sensitivity_inputs'][product['material']]['density_kg_m3']
            require([m['density_kg_m3'] for m in mass_row['mass_cases']] == densities, 'Density cases')
            for m in mass_row['mass_cases']:
                near(m['mass_kg'],m['density_kg_m3']*volume,'Installed mass')
            low += min(densities)*volume
            high += max(densities)*volume
            allowance = product.get('screening_purchase_allowance')
            stock = product['purchased_length_mm'] if product['purchased_length_mm'] is not None else allowance['stock_length_mm']
            capacity = int(((D(str(stock))-2*D(str(account['end_trim_each_end_per_stock_mm'])))*1000).to_integral_value(rounding=ROUND_FLOOR))
            weights = tuple(sorted(charge_um(v,account['kerf_per_finished_piece_mm']) for v in cuts.values()))
            optimum = optimal_bins(weights,capacity)
            if optimum is None:
                feasible = False
                require(pid not in purchases, 'Infeasible product incorrectly purchased')
                continue
            purchase = purchases[pid]
            packing = purchase['packing']
            require(packing['feasible'] is True, 'Feasible stock mislabeled')
            require(packing['stock_count'] == len(packing['schedule']) == optimum, 'Nonoptimal stock count')
            require(packing['usable_stock_um'] == capacity, 'Stock capacity')
            require(packing['volume_lower_bound_count'] == (sum(weights)+capacity-1)//capacity, 'Stock lower bound')
            remaining = []
            for w in sorted(weights,reverse=True):
                for j,r in enumerate(remaining):
                    if r >= w:
                        remaining[j] -= w
                        break
                else:
                    remaining.append(capacity-w)
            require(packing['first_fit_upper_bound_count'] == len(remaining), 'First-fit upper bound')
            labels = []
            for stock_row in packing['schedule']:
                require(stock_row['pieces'], 'Empty stock schedule')
                require(stock_row['end_trim_each_mm'] == account['end_trim_each_end_per_stock_mm'], 'End trim')
                require(stock_row['kerf_per_piece_mm'] == account['kerf_per_finished_piece_mm'], 'Kerf')
                charged, physical = 0, 2*D(str(account['end_trim_each_end_per_stock_mm']))
                for piece in stock_row['pieces']:
                    label = piece['label']
                    require(label in cuts, 'Unexpected cut label')
                    labels.append(label)
                    near(piece['finished_length_mm'],cuts[label],'Cut length')
                    expected_charge = charge_um(cuts[label],account['kerf_per_finished_piece_mm'])
                    require(piece['charged_length_um'] == expected_charge, 'Outward-rounded cut consumption')
                    charged += expected_charge
                    physical += D(str(piece['finished_length_mm']))+D(str(account['kerf_per_finished_piece_mm']))
                require(charged <= capacity and physical <= D(str(stock)), 'Overfilled stock')
                require(stock_row['rounded_usable_remaining_um'] == capacity-charged, 'Rounded offcut')
                require(abs(D(stock_row['unrounded_unused_length_mm'])-(D(str(stock))-physical)) < D('0.00000001'), 'Physical offcut')
            require(Counter(labels) == Counter(cuts.keys()), 'Lost or duplicated cuts')
            price = D(str(product['price_displayed'] if 'price_displayed' in product else allowance['price_per_whole_tube']))
            subtotal = price*optimum
            confirmed = product['currency_status'].startswith('Confirmed') and product['tax_basis']=='Includes 10 percent GST' and allowance is None
            net = subtotal/D('1.10') if confirmed else subtotal
            require(purchase['stock_length_mm'] == stock, 'Stock length identity')
            require(purchase['price_is_variant_allowance'] == (allowance is not None), 'Allowance disclosure')
            require(purchase['tax_deduction_applied'] == confirmed, 'Tax evidence policy')
            require(purchase['currency_status'] == product['currency_status'], 'Currency qualification')
            require(purchase['source_url'] == product['url'] and purchase['access_date'] == product['access_date'], 'Price provenance')
            require(purchase['displayed_or_allowance_subtotal'] == cents(subtotal), 'Displayed subtotal')
            require(D(purchase['policy_subtotal_unrounded']) == net, 'Policy subtotal')
            displayed += subtotal
            policy += net
            net_confirmed = net_confirmed and confirmed
        vector(row['tube_only_mass_sensitivity_extrema_kg'],[low,high],'Tube-only mass range')
        require(bool(row['rejection_reasons']) == (not feasible), 'Stock rejection coverage')
        require(row['tube_only_displayed_or_allowance_subtotal_assuming_AUD'] == (cents(displayed) if feasible else None), 'Candidate displayed subtotal')
        require(row['tube_only_policy_subtotal_assuming_AUD'] == (cents(policy) if feasible else None), 'Candidate policy subtotal')
        require(row['confirmed_tax_exclusive_tube_subtotal_AUD'] == (cents(policy) if feasible and net_confirmed else None), 'Unsubstantiated confirmed net cost')
        for field in ('structural_acceptance','rotor_clearance_acceptance','whole_vehicle_budget_acceptance'):
            require(row[field] is None,'Unsupported candidate acceptance')
        expected_restrictions = {p['id']:p.get('supplier_restriction','Laminate and joint allowables unverified') for p in (sp,lp)}
        require({v['product_id']:v['text'] for v in row['supplier_restrictions']} == expected_restrictions,'Supplier restriction preservation')


def support_edges(hull, point):
    values = []
    for a,b in zip(hull,hull[1:]+hull[:1]):
        dx,dy = b[0]-a[0],b[1]-a[1]
        length = math.hypot(dx,dy)
        require(length > 0,'Zero polygon edge')
        normal = [-dy/length,dx/length]
        values.append((normal,normal[0]*(point[0]-a[0])+normal[1]*(point[1]-a[1])))
    return values


def verify_support(cfg,result):
    geom,loads = cfg['geometry_hypotheses'],cfg['load_and_stability_sensitivities']
    rows = index(result['support_studies'],lambda r:(r['seed'],r['arrangement']))
    require(len(rows) == len(geom['layout_seeds'])*len(geom['landing_arrangements']),'Support study coverage')
    directions = [i*loads['CG_offset_azimuth_step_deg'] for i in range(math.ceil(360/loads['CG_offset_azimuth_step_deg'])) if i*loads['CG_offset_azimuth_step_deg']<360]
    def point_key(p):
        return tuple(round(v,11) for v in p)
    expected_cg = {}
    for offset in loads['horizontal_CG_offset_magnitudes_mm']:
        for angle in ([0] if offset == 0 else directions):
            p = [offset/1000*math.cos(math.radians(angle)),offset/1000*math.sin(math.radians(angle))]
            expected_cg[point_key(p)] = (p,angle)
    for seed,arr in itertools.product(geom['layout_seeds'],geom['landing_arrangements']):
        study = rows[(seed['id'],arr['id'])]
        r = seed['foot_radius_mm']/1000
        contacts = [[r*math.cos(math.radians(a)),r*math.sin(math.radians(a))] for a in arr['azimuths_deg']]
        require(len(study['contact_xy_m']) == len(contacts),'Contact count')
        for a,b in zip(study['contact_xy_m'],contacts):
            vector(a,b,'Contact position')
        expected_subsets = {'all_contacts':list(range(arr['count']))}
        expected_subsets.update({'without_foot_'+str(j):[i for i in range(arr['count']) if i!=j] for j in range(arr['count'])})
        subsets = index(study['cases'],lambda x:x['id'])
        require(set(subsets) == set(expected_subsets),'Contact subset coverage')
        for label,active in expected_subsets.items():
            row = subsets[label]
            require(row['active_feet'] == active,'Active feet')
            hull = row['hull_xy_m']
            require(Counter(point_key(p) for p in hull) == Counter(point_key(contacts[i]) for i in active),'Support hull vertices')
            require(row['nondegenerate_2D_support'] == (len(active)>=3),'Support dimensionality')
            if len(active)<3:
                require(row['CG_cases']==[],'Invented 2D margin for line support')
                continue
            for j in range(len(hull)):
                a,b,c = hull[j],hull[(j+1)%len(hull)],hull[(j+2)%len(hull)]
                require((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])>0,'Hull must be convex CCW')
            origin = support_edges(hull,[0,0])
            origin_margin = min(m for n,m in origin)
            widths = []
            for n,m in origin:
                projections = [sum(x*y for x,y in zip(n,p)) for p in hull]
                widths.append(max(projections)-min(projections))
            near(row['origin_min_signed_edge_margin_m'],origin_margin,'Origin support margin')
            near(row['minimum_polygon_width_m'],min(widths),'Minimum polygon width')
            if label=='all_contacts':
                near(origin_margin,r*math.cos(math.pi/arr['count']),'Regular support inradius')
                near(min(widths),r*(1.5 if arr['count']==3 else math.sqrt(2)),'Regular support width')
            elif arr['count']==4:
                near(origin_margin,0,'Three-of-four centre lies on diagonal',1e-12)
            comparisons = index(row['disc_comparisons'],lambda x:x['propeller_id'])
            require(set(comparisons) == {p['id'] for p in geom['propeller_envelopes']},'Disc comparison coverage')
            for prop in geom['propeller_envelopes']:
                c = comparisons[prop['id']]
                diameter = prop['diameter_mm']/1000
                near(c['diameter_m'],diameter,'Disc diameter')
                require(c['minimum_width_exceeds_disc_diameter'] == (min(widths)>diameter),'Directional stance comparison')
                require(c['origin_centred_disc_fits_inside_contact_polygon'] == (origin_margin>diameter/2),'Disc containment comparison')
            cg_rows = index(row['CG_cases'],lambda x:point_key(x['xy_m']))
            require(set(cg_rows) == set(expected_cg),'CG position coverage')
            for key,(point,angle) in expected_cg.items():
                c = cg_rows[key]
                vector(c['xy_m'],point,'CG position')
                near(c['offset_azimuth_deg'],angle,'CG azimuth')
                edges = support_edges(hull,point)
                require(len(c['edge_margins'])==len(edges),'Edge margin coverage')
                for actual,(normal,margin) in zip(c['edge_margins'],edges):
                    vector(actual['inward_normal'],normal,'Edge normal')
                    near(actual['signed_edge_margin_m'],margin,'Signed edge margin')
                minimum = min(m for n,m in edges)
                near(c['min_signed_edge_margin_m'],minimum,'Minimum CG edge margin')
                tips = c['ideal_edge_tipping_angles']
                require(len(tips)==len(loads['prescribed_complete_vehicle_CG_height_mm']),'Tipping height cases')
                for t,h in zip(tips,loads['prescribed_complete_vehicle_CG_height_mm']):
                    near(t['CG_height_m'],h/1000,'CG height')
                    near(t['angle_deg'],math.degrees(math.atan2(minimum,h/1000)),'Ideal tipping angle')
                shares = c['triangle_vertical_reaction_fractions_in_hull_order']
                if len(hull)==3:
                    require(shares is not None and len(shares)==3,'Triangle reactions missing')
                    near(sum(shares),1,'Reaction force balance')
                    for j in range(2):
                        near(sum(w*p[j] for w,p in zip(shares,hull)),point[j],'Reaction moment balance')
                    require(c['triangle_compressive_equilibrium_with_1e_minus_12_tolerance']==(min(shares)>=-1e-12),'Compressive reaction classification')
                else:
                    require(shares is None and c['triangle_compressive_equilibrium_with_1e_minus_12_tolerance'] is None,'Four-foot load sharing invented')
                radial = c['directional_boundary_distances']
                if minimum>1e-12:
                    require(len(radial)==len(directions),'Missing interior radial margins')
                elif minimum < -1e-12:
                    require(radial==[],'Radial interior margin for exterior CG')
                if radial:
                    require(len(radial)==len(directions),'Radial direction coverage')
                    for item,theta in zip(radial,directions):
                        near(item['direction_deg'],theta,'Radial direction')
                        v = [math.cos(math.radians(theta)),math.sin(math.radians(theta))]
                        ray = item['ray_to_boundary_m']
                        require(ray>=-1e-12,'Negative interior ray')
                        end = [point[j]+ray*v[j] for j in range(2)]
                        terminal = [m for n,m in support_edges(hull,end)]
                        require(min(terminal)>=-1e-10 and min(abs(m) for m in terminal)<=1e-10,'Ray endpoint is not on polygon boundary')


def landing_metrics(seed,geom,product,force):
    dr = (seed['foot_radius_mm']-seed['leg_attachment_radius_mm'])/1000
    z = seed['leg_attachment_z_mm']/1000
    socket_z = geom['foot_tube_socket_reference_z_mm']/1000
    length = math.hypot(dr,z-socket_z)
    ux,uz = -dr/length,(z-socket_z)/length
    fx,fy,fz = force
    axial = ux*fx+uz*fz
    transverse = math.sqrt(max(0,fx*fx+fy*fy+fz*fz-axial*axial))
    moment = [z*fy,-z*fx-dr*fz,dr*fy]
    torsion = ux*moment[0]+uz*moment[2]
    bending = math.sqrt(max(0,sum(v*v for v in moment)-torsion*torsion))
    end = [socket_z*fy,-socket_z*fx,0]
    end_torsion = ux*end[0]
    end_bending = math.sqrt(max(0,sum(v*v for v in end)-end_torsion*end_torsion))
    area,inertia = section(product)
    radius = product['od_mm']/2000
    return {
        'compressive_axial_N':max(0,axial),
        'absolute_axial_N':abs(axial),
        'transverse_N':transverse,
        'root_bending_N_m':bending,
        'absolute_root_torsion_N_m':abs(torsion),
        'nominal_combined_axial_bending_stress_Pa':abs(axial)/area+bending*radius/inertia,
        'nominal_isotropic_torsional_stress_proxy_Pa':abs(torsion)*radius/(2*inertia),
        'socket_transverse_displacement_times_E_Pa_m':transverse*length**3/(3*inertia)+end_bending*length**2/(2*inertia)
    },moment,length


def verify_landing(cfg,result):
    geom,loads = cfg['geometry_hypotheses'],cfg['load_and_stability_sensitivities']
    products = [p for p in cfg['supplier_candidates'] if 'leg' in p['roles']]
    rows = index(result['landing_studies'],lambda r:(r['seed'],r['arrangement'],r['product']))
    combinations = list(itertools.product(geom['layout_seeds'],geom['landing_arrangements'],products))
    require(len(rows)==len(combinations),'Landing study coverage')
    for seed,arr,product in combinations:
        study = rows[(seed['id'],arr['id'],product['id'])]
        near(study['representative_leg']['finished_length_mm'],leg_length(seed,geom),'Representative leg length')
        cases = index(study['cases'],lambda c:(c['mass_kg'],c['load_case']))
        require(len(cases)==2*len(loads['prescribed_complete_vehicle_mass_kg']),'Landing case coverage')
        for mass in loads['prescribed_complete_vehicle_mass_kg']:
            for label,fraction in [('assumed_symmetric_all_feet',1/arr['count']),('full_reaction_first_contact_leg',1.0)]:
                case = cases[(mass,label)]
                near(case['assumed_total_reaction_fraction'],fraction,'Reaction fraction')
                maxima = {}
                valid_witnesses = set()
                for speed,stop_mm,peak,lateral in itertools.product(loads['touchdown_vertical_speed_m_s'],loads['effective_vertical_stopping_distance_mm'],loads['dynamic_force_peak_multiplier'],loads['lateral_to_vertical_contact_force_ratio_cases']):
                    vertical = fraction*mass*(loads['gravity_m_s2']+peak*speed**2/(2*stop_mm/1000))
                    for angle in ([0] if lateral==0 else [0,90,180,270]):
                        force = [vertical*lateral*math.cos(math.radians(angle)),vertical*lateral*math.sin(math.radians(angle)),vertical]
                        values,moment,length = landing_metrics(seed,geom,product,force)
                        for key,value in values.items():
                            maxima[key] = max(maxima.get(key,-math.inf),value)
                        valid_witnesses.add((speed,stop_mm,peak,lateral,angle))
                require(set(case['extrema'])==set(maxima),'Demand extrema coverage')
                for key,maximum in maxima.items():
                    item = case['extrema'][key]
                    near(item['value'],maximum,'Demand maximum '+key)
                    w = item['witness']
                    require(w['mass_kg']==mass,'Witness mass')
                    signature = (w['vertical_speed_m_s'],w['stopping_distance_mm'],w['dynamic_peak_multiplier'],w['lateral_vertical_ratio'],w['lateral_direction_deg'])
                    require(signature in valid_witnesses,'Witness outside prescribed cases')
                    speed,stop,peak,lateral,angle = signature
                    vertical = fraction*mass*(loads['gravity_m_s2']+peak*speed**2/(2*stop/1000))
                    force = [vertical*lateral*math.cos(math.radians(angle)),vertical*lateral*math.sin(math.radians(angle)),vertical]
                    vector(w['leg_force_CAD_N'],force,'Witness force')
                    values,moment,length = landing_metrics(seed,geom,product,force)
                    vector(w['root_moment_CAD_N_m'],moment,'Witness moment')
                    near(item['value'],values[key],'Witness attains extremum '+key)
                es = cfg['material_sensitivity_inputs'][product['material']]['axial_E_Pa']
                require([v['E_Pa'] for v in case['material_responses']]==es,'Landing modulus cases')
                inertia = section(product)[1]
                for response in case['material_responses']:
                    e = response['E_Pa']
                    displacement = maxima['socket_transverse_displacement_times_E_Pa_m']/e
                    near(response['linear_socket_displacement_magnitude_bound_m'],displacement,'Socket displacement bound')
                    near(response['displacement_to_span_ratio'],displacement/length,'Displacement/span')
                    screens = response['Euler_compression_screens']
                    require([v['K'] for v in screens]==loads['effective_length_factors_for_Euler_screen'],'Landing Euler cases')
                    for screen in screens:
                        critical = math.pi**2*e*inertia/(screen['K']*length)**2
                        near(screen['critical_N'],critical,'Leg Euler proxy')
                        near(screen['maximum_demand_over_ideal_Euler'],maxima['compressive_axial_N']/critical,'Demand/Euler proxy')
        require(study['structural_acceptance'] is None,'Unsupported landing structural acceptance')


def verify_fixtures(program):
    # Import only the hash-checked sandbox source; never its CLI or compute().
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('r12_structural_core_under_test',program)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for lengths,stock,trim,kerf in [([600,600,600],1000,0,0),([600,400,600,400],1000,0,0),([300,300,300],1000,5,3),([987],1000,5,3),([987.0001],1000,5,3)]:
        cuts = [{'label':'fixture_'+str(j),'finished_length_mm':v} for j,v in enumerate(lengths)]
        actual = module.exact_pack(cuts,stock,trim,kerf)
        capacity = int((D(str(stock))-2*D(str(trim)))*1000)
        optimum = optimal_bins(tuple(sorted(charge_um(v,kerf) for v in lengths)),capacity)
        require(actual['feasible']==(optimum is not None),'Packing fixture feasibility')
        if optimum is not None:
            require(actual['stock_count']==optimum,'Packing fixture optimum')
    square = module.convex_hull([[1,1],[-1,1],[1,-1],[-1,-1],[0,0]])
    require(len(square)==4,'Hull fixture retains interior point')
    near(min(v['signed_edge_margin_m'] for v in module.margins(square,[0,0])),1,'Square support fixture')
    near(min(v['signed_edge_margin_m'] for v in module.margins(square,[2,0])),-1,'Exterior support fixture')
    triangle = [[0,0],[2,0],[0,2]]
    vector(module.triangle_shares(triangle,[0.5,0.5]),[0.5,0.25,0.25],'Triangle equilibrium fixture')
    rejected = False
    try:
        module.section({'od_mm':6,'id_mm':6,'material':'unused'}, {})
    except ValueError:
        rejected = True
    require(rejected,'Invalid annular section not rejected')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    defaults = {
        'config':('analysis/pdr_r12_chief/structural_trade_config_01.json','20ad1f5170c8a8309a3211d3c99e1a6754707b64ee98a2c5c5398ad519d27377'),
        'program':('analysis/pdr_r12_chief/structural_trade_core_01.py','88c126b6e564c7704e18d26c228c9caa0a489da47f95075cbfd429e676431fee'),
        'results':('analysis/pdr_r12_chief/structural_trade_core_results_01.json','c0b7337c5726d379fd13a7ff0a79f48f691796a5cd3b41ac740da0e9a5b8d2b2'),
        'register':('analysis/pdr_r12_chief/structural_tube_supplier_register_2026-10-11_01.md','642ac064c1b3f587de508fd02d788acf928c073b2e6b3c5fa01de05ec8a4da75')
    }
    for name,(path,expected) in defaults.items():
        parser.add_argument('--'+name,default=path)
        parser.add_argument('--'+name+'-sha256',default=expected)
    args = parser.parse_args()
    paths,raw,hashes = {},{},{}
    for name in defaults:
        paths[name] = path_in_root(getattr(args,name))
        raw[name] = paths[name].read_bytes()
        hashes[name] = digest(raw[name])
        require(hashes[name]==getattr(args,name+'_sha256'),'Artifact hash mismatch: '+name)
    CHECKS['declared_artifact_hashes'] = True
    cfg,result = parse(raw['config']),parse(raw['results'])
    def provenance():
        require(cfg['schema']=='hopper_r12_structural_trade_inputs_v1','Configuration schema')
        require(result['schema']=='hopper_r12_structural_trade_core_results_v1','Results schema')
        actual = result['actual_inputs']
        for name in ('config','program'):
            require(actual[name+'_sha256']==hashes[name],'Recorded '+name+' hash')
            require(path_in_root(actual[name+'_path'])==paths[name],'Recorded '+name+' path')
        require(actual['supplier_register_sha256']==hashes['register'],'Recorded register hash')
        require(path_in_root(actual['supplier_register_path'])==paths['register'],'Recorded register path')
        require(cfg['provenance']['supplier_register_file_sha256']==hashes['register'],'Configuration register hash')
        require(path_in_root(cfg['provenance']['supplier_register_path'])==paths['register'],'Configuration register path')
        require(result['supplier_candidates_with_original_provenance']==cfg['supplier_candidates'],'Supplier provenance changed')
        require(result['input_provenance']==cfg['provenance'],'Input provenance changed')
        require(result['selected_candidate'] is None,'Analysis selected a winner')
        require(result['whole_vehicle_cost_AUD'] is None and result['whole_vehicle_mass_kg'] is None,'Partial ledger presented as complete')
        require(result['physical_validation']=='unperformed','Unsupported physical validation')
        account = cfg['purchase_and_mass_accounting']
        require(account['PETG_cost_exempt'] is True and account['PETG_installed_mass_exempt'] is False,'PETG accounting')
    run_check('provenance_and_scope',provenance)
    run_check('annular_sections_and_property_sensitivities',lambda:verify_sections(cfg,result))
    run_check('spine_section_and_Euler_proxies',lambda:verify_spines(cfg,result))
    run_check('candidate_coverage_exact_stock_cost_and_tube_mass',lambda:verify_candidates(cfg,result))
    run_check('support_polygons_reactions_and_tipping_proxies',lambda:verify_support(cfg,result))
    run_check('sampled_landing_demands_and_witnesses',lambda:verify_landing(cfg,result))
    run_check('independent_analytical_and_invalid_input_fixtures',lambda:verify_fixtures(paths['program']))
    print(json.dumps({'tested_file_sha256':hashes,'checker_sha256':digest(Path(__file__).read_bytes()),
                      'candidate_count_observed':result.get('candidate_count'),
                      'scope':'Arithmetic and explicitly stated reduced models only; no engineering selection or physical acceptance'}),file=sys.stderr)


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        CHECKS['checker_completed'] = False
        FAILURES.append(type(exc).__name__+': '+str(exc))
        print(FAILURES[-1],file=sys.stderr)
    CHECKS.update({
        'actual_CAD_solids_and_full_travel_clearances':None,
        'material_joint_and_landing_strength':None,
        'complete_vehicle_mass_energy_and_budget':None,
        'physical_validation':None
    })
    outcome = 'failed' if any(value is False for value in CHECKS.values()) else 'inconclusive'
    explanation = ('Scoped numerical checks failed: '+ '; '.join(FAILURES)) if FAILURES else (
        'The executed arithmetic, artifact-integrity and analytical-fixture checks passed for the stated stage-1 models. '
        'Overall engineering acceptance remains inconclusive: CAD clearances, material/joint strength, complete vehicle budgets and physical tests are unperformed. '
        'Landing demands cover the configured discrete lateral directions, not continuous load maxima. Supplier prices and properties are inherited evidence, not newly verified quotations or allowables.')
    print(json.dumps({'outcome':outcome,'explanation':explanation,'checks':CHECKS},allow_nan=False))
