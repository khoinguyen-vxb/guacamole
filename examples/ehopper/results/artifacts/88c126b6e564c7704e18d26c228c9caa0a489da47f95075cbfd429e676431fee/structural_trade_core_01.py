"""Preliminary structural trade, stage 1: members, stock and support.

Standard-library-only analysis. No component selection or physical acceptance.
Run through Guacamole execute, declaring the chosen results JSON in outputs.
A separate artifact-bound verification program must check these results.
Geometry clearance, CAD and whole-vehicle budgets are NOT evaluated here.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parents[2]
D = Decimal


def within_root(name):
    p = Path(name)
    p = (ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    p.relative_to(ROOT)
    return p


def sha(data):
    return hashlib.sha256(data).hexdigest()


def positive(x, name, zero=False):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(name + ': expected numeric value')
    if not math.isfinite(x) or (x < 0 if zero else x <= 0):
        raise ValueError(name + ': invalid magnitude')
    return float(x)


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def cross2(a, b):
    return a[0]*b[1]-a[1]*b[0]


def money(x):
    return str(x.quantize(D('0.01'), rounding=ROUND_HALF_UP))


def exact_pack(cuts, stock_mm, trim_each_mm, kerf_mm):
    """Exact minimum bin count for outward-rounded, one-kerf-per-piece model."""
    capacity = int(((D(str(stock_mm))-2*D(str(trim_each_mm)))*1000).to_integral_value(rounding=ROUND_FLOOR))
    if capacity <= 0:
        raise ValueError('Nonpositive usable stock length')
    items = []
    for c in cuts:
        positive(c['finished_length_mm'], 'cut length')
        w = int(((D(str(c['finished_length_mm']))+D(str(kerf_mm)))*1000).to_integral_value(rounding=ROUND_CEILING))
        items.append(dict(c, charged_length_um=w))
    items.sort(key=lambda c: (-c['charged_length_um'], c['label']))
    if not items:
        raise ValueError('Empty stock group')
    oversized = [c['label'] for c in items if c['charged_length_um'] > capacity]
    if oversized:
        return {'feasible': False, 'reason': 'Cuts exceed usable whole stock', 'oversized_cuts': oversized}
    lower = (sum(c['charged_length_um'] for c in items)+capacity-1)//capacity
    # First-fit descending supplies only an upper bound.
    upper_bins, upper_remaining = [], []
    for i, c in enumerate(items):
        j = next((j for j, rem in enumerate(upper_remaining) if rem >= c['charged_length_um']), None)
        if j is None:
            upper_bins.append([i])
            upper_remaining.append(capacity-c['charged_length_um'])
        else:
            upper_bins[j].append(i)
            upper_remaining[j] -= c['charged_length_um']
    visited = 0
    chosen = None
    for count in range(lower, len(upper_bins)+1):
        bins = [[] for _ in range(count)]
        remaining = [capacity]*count
        def place(i):
            nonlocal visited
            visited += 1
            if i == len(items):
                return [list(b) for b in bins]
            seen = set()
            w = items[i]['charged_length_um']
            for j in range(count):
                rem = remaining[j]
                if rem < w or rem in seen:
                    continue
                seen.add(rem)
                remaining[j] -= w
                bins[j].append(i)
                found = place(i+1)
                if found is not None:
                    return found
                bins[j].pop()
                remaining[j] += w
                if rem == capacity:
                    break
            return None
        chosen = place(0)
        if chosen is not None:
            break
    if chosen is None:
        raise RuntimeError('Packing search failed despite feasible upper bound')
    schedule = []
    recovered = []
    for indices in chosen:
        pieces = [items[i] for i in indices]
        recovered.extend(c['label'] for c in pieces)
        physical_used = 2*D(str(trim_each_mm))+sum((D(str(c['finished_length_mm']))+D(str(kerf_mm)) for c in pieces), D(0))
        if physical_used > D(str(stock_mm)):
            raise RuntimeError('Packing violates unrounded stock consumption')
        schedule.append({'pieces': pieces, 'end_trim_each_mm': trim_each_mm,
                         'kerf_per_piece_mm': kerf_mm,
                         'unrounded_unused_length_mm': str(D(str(stock_mm))-physical_used),
                         'rounded_usable_remaining_um': capacity-sum(c['charged_length_um'] for c in pieces)})
    if sorted(recovered) != sorted(c['label'] for c in cuts):
        raise RuntimeError('Packing lost or duplicated a cut')
    return {'feasible': True, 'stock_count': len(chosen), 'volume_lower_bound_count': lower,
            'first_fit_upper_bound_count': len(upper_bins), 'search_nodes': visited,
            'optimality': 'Exact for outward-rounded 1 micrometre model, not necessarily the unrounded model',
            'usable_stock_um': capacity, 'schedule': schedule}


def section(p, materials):
    od = positive(p['od_mm'], 'OD')*0.001
    inner = positive(p['id_mm'], 'ID', True)*0.001
    if inner >= od:
        raise ValueError('Tube ID must be below OD')
    a = math.pi*(od*od-inner*inner)/4
    i = math.pi*(od**4-inner**4)/64
    mat = materials[p['material']]
    for field in ('density_kg_m3', 'axial_E_Pa', 'effective_G_Pa'):
        if not mat[field]:
            raise ValueError('Empty property sensitivity')
        for v in mat[field]:
            positive(v, field)
    return {'area_m2': a, 'I_m4': i, 'J_m4': 2*i,
            'linear_mass_kg_m': [{'density_kg_m3': rho, 'value': rho*a} for rho in mat['density_kg_m3']],
            'EI_N_m2': [{'E_Pa': e, 'value': e*i} for e in mat['axial_E_Pa']],
            'GJ_N_m2': [{'G_Pa': g, 'value': g*2*i} for g in mat['effective_G_Pa']],
            'material_acceptance': None}


def spine_points(layout):
    if 'xy_mm' in layout:
        pts = layout['xy_mm']
    else:
        r = positive(layout['radius_mm'], 'spine radius')
        pts = [[r*math.cos(math.radians(a)), r*math.sin(math.radians(a))] for a in layout['azimuths_deg']]
    if len(pts) != layout['count'] or not 1 <= layout['count'] <= 4:
        raise ValueError('Spine count mismatch')
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in pts):
        raise ValueError('Invalid spine coordinates')
    return [[v*0.001 for v in p] for p in pts]


def spine_proxy(layout, p, length_mm, sec, materials, ks):
    pts = spine_points(layout)
    n = len(pts)
    centre = [sum(p[j] for p in pts)/n for j in range(2)]
    dxdy = [sub(p, centre) for p in pts]
    a, i = sec['area_m2'], sec['I_m4']
    xx = n*i+a*sum(q[1]**2 for q in dxdy)
    yy = n*i+a*sum(q[0]**2 for q in dxdy)
    xy = -a*sum(q[0]*q[1] for q in dxdy)
    root = math.hypot(xx-yy, 2*xy)
    eig = [(xx+yy-root)/2, (xx+yy+root)/2]
    length = positive(length_mm, 'spine length')*0.001
    cases = []
    for e in materials[p['material']]['axial_E_Pa']:
        cases.append({'E_Pa': e, 'independent_member_EI_sum_N_m2': e*n*i,
                      'ideal_shear_coupled_EI_matrix_N_m2': [[e*xx,e*xy],[e*xy,e*yy]],
                      'ideal_shear_coupled_principal_EI_N_m2': [e*v for v in eig],
                      'individual_member_Euler_cases': [{'K': k, 'critical_load_N': math.pi**2*e*i/(k*length)**2} for k in ks]})
    return {'layout': layout['id'], 'product': p['id'], 'length_mm': length_mm,
            'xy_m': pts, 'section_centroid_xy_m': centre, 'cases': cases,
            'limitations': 'Perfect shear coupling is a proxy, not established jointed-frame stiffness. Euler values are individual ideal members, not assembled-frame capacities. Torsional stiffness cannot be inferred from rail spacing.',
            'assembly_acceptance': None}


def leg_geometry(seed, geom, azimuth_deg):
    t = math.radians(azimuth_deg)
    c, s = math.cos(t), math.sin(t)
    a = [seed['leg_attachment_radius_mm']*c, seed['leg_attachment_radius_mm']*s, seed['leg_attachment_z_mm']]
    f = [seed['foot_radius_mm']*c, seed['foot_radius_mm']*s, geom['foot_tube_socket_reference_z_mm']]
    delta = sub(a, f)
    free = norm(delta)
    if free <= 0:
        raise ValueError('Zero leg span')
    u = [v/free for v in delta]
    top = [a[j]+geom['leg_root_insertion_extension_mm']*u[j] for j in range(3)]
    bottom = [f[j]-geom['leg_foot_insertion_extension_mm']*u[j] for j in range(3)]
    contact = [seed['foot_radius_mm']*c, seed['foot_radius_mm']*s, 0]
    return {'attachment_m': [v*0.001 for v in a], 'socket_m': [v*0.001 for v in f],
            'contact_m': [v*0.001 for v in contact], 'axis_foot_to_root': u,
            'tube_top_m': [v*0.001 for v in top], 'tube_bottom_m': [v*0.001 for v in bottom],
            'clamp_to_socket_length_m': free*0.001,
            'finished_length_mm': free+geom['leg_root_insertion_extension_mm']+geom['leg_foot_insertion_extension_mm']}


def convex_hull(points):
    pts = sorted(set(tuple(p) for p in points))
    if len(pts) < 3:
        return pts
    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and cross2(sub(out[-1], out[-2]), sub(p, out[-1])) <= 0:
                out.pop()
            out.append(p)
        return out
    return half(pts)[:-1]+half(reversed(pts))[:-1]


def margins(hull, point):
    if len(hull) < 3:
        return None
    out = []
    for a, b in zip(hull, hull[1:]+hull[:1]):
        edge = sub(b, a)
        le = norm(edge)
        if le <= 0:
            raise ValueError('Degenerate hull edge')
        out.append({'inward_normal': [-edge[1]/le, edge[0]/le],
                    'signed_edge_margin_m': cross2(edge, sub(point,a))/le})
    return out


def triangle_shares(hull, p):
    if len(hull) != 3:
        return None
    a, b, c = hull
    den = cross2(sub(b,a), sub(c,a))
    if den <= 0:
        raise ValueError('Triangle is not counterclockwise')
    return [cross2(sub(b,p),sub(c,p))/den,
            cross2(sub(c,p),sub(a,p))/den,
            cross2(sub(a,p),sub(b,p))/den]


def support_study(seed, arrangement, geom, loads):
    contacts = [leg_geometry(seed, geom, a)['contact_m'][:2] for a in arrangement['azimuths_deg']]
    if len(contacts) != arrangement['count']:
        raise ValueError('Landing count mismatch')
    subsets = [('all_contacts', list(range(len(contacts))))]
    subsets += [('without_foot_'+str(j), [i for i in range(len(contacts)) if i != j]) for j in range(len(contacts))]
    rows = []
    step = positive(loads['CG_offset_azimuth_step_deg'], 'CG angular step')
    directions = [math.radians(i*step) for i in range(math.ceil(360/step)) if i*step < 360]
    for label, active in subsets:
        hull = convex_hull([contacts[i] for i in active])
        row = {'id': label, 'active_feet': active, 'hull_xy_m': hull, 'nondegenerate_2D_support': len(hull) >= 3, 'CG_cases': []}
        if len(hull) < 3:
            row['limitation'] = 'Point/line support is not a positive two-dimensional stability margin.'
            rows.append(row)
            continue
        origin_edges = margins(hull, [0,0])
        row['origin_min_signed_edge_margin_m'] = min(e['signed_edge_margin_m'] for e in origin_edges)
        widths = []
        for e in origin_edges:
            projections = [dot(p,e['inward_normal']) for p in hull]
            widths.append(max(projections)-min(projections))
        row['minimum_polygon_width_m'] = min(widths)
        row['disc_comparisons'] = [{'propeller_id': p['id'], 'diameter_m': p['diameter_mm']*0.001,
                                   'minimum_width_exceeds_disc_diameter': min(widths)>p['diameter_mm']*0.001,
                                   'origin_centred_disc_fits_inside_contact_polygon': row['origin_min_signed_edge_margin_m']>p['diameter_mm']*0.0005}
                                  for p in geom['propeller_envelopes']]
        for offset_mm in loads['horizontal_CG_offset_magnitudes_mm']:
            for angle in ([0] if offset_mm == 0 else directions):
                p = [offset_mm*0.001*math.cos(angle), offset_mm*0.001*math.sin(angle)]
                edges = margins(hull,p)
                minimum = min(e['signed_edge_margin_m'] for e in edges)
                shares = triangle_shares(hull,p)
                radial = []
                if minimum >= 0:
                    for theta in directions:
                        v = [math.cos(theta),math.sin(theta)]
                        bounds = [e['signed_edge_margin_m']/(-dot(e['inward_normal'],v)) for e in edges if dot(e['inward_normal'],v)<-1e-14]
                        radial.append({'direction_deg': math.degrees(theta), 'ray_to_boundary_m': min(bounds)})
                row['CG_cases'].append({'xy_m': p, 'offset_azimuth_deg': math.degrees(angle),
                                        'min_signed_edge_margin_m': minimum,
                                        'edge_margins': edges, 'directional_boundary_distances': radial,
                                        'ideal_edge_tipping_angles': [{'CG_height_m': h*0.001, 'angle_deg': math.degrees(math.atan2(minimum,h*0.001))} for h in loads['prescribed_complete_vehicle_CG_height_mm']],
                                        'triangle_vertical_reaction_fractions_in_hull_order': shares,
                                        'triangle_compressive_equilibrium_with_1e_minus_12_tolerance': None if shares is None else min(shares)>=-1e-12})
        rows.append(row)
    return {'seed': seed['id'], 'arrangement': arrangement['id'], 'contact_xy_m': contacts, 'cases': rows,
            'limitations': 'Rigid level-ground point-contact statics only. Negative edge margin is not generally Euclidean signed distance. Four-foot load sharing is indeterminate without compliance. Three-foot reactions are barycentric, not automatically one third. Impact dynamics remain unmodelled.'}


def landing_study(seed, arrangement, geom, loads, product, sec, materials):
    # Axisymmetric geometry permits a representative leg at azimuth zero.
    leg = leg_geometry(seed, geom, 0)
    u, a, f, contact = (leg[k] for k in ('axis_foot_to_root','attachment_m','socket_m','contact_m'))
    length = leg['clamp_to_socket_length_m']
    area, inertia = sec['area_m2'], sec['I_m4']
    radius = product['od_mm']*0.0005
    rows = []
    for mass in loads['prescribed_complete_vehicle_mass_kg']:
        for case, fraction in [('assumed_symmetric_all_feet',1/arrangement['count']),('full_reaction_first_contact_leg',1.0)]:
            extreme = {}
            def retain(name, value, witness):
                if name not in extreme or value>extreme[name]['value']:
                    extreme[name] = {'value': value, 'witness': witness}
            for velocity, stop_mm, peak, lateral in itertools.product(loads['touchdown_vertical_speed_m_s'], loads['effective_vertical_stopping_distance_mm'], loads['dynamic_force_peak_multiplier'], loads['lateral_to_vertical_contact_force_ratio_cases']):
                stop = positive(stop_mm,'stopping distance')*0.001
                total = mass*loads['gravity_m_s2']+peak*mass*velocity**2/(2*stop)
                for direction in ([0] if lateral==0 else [0,90,180,270]):
                    phi = math.radians(direction)
                    force = [fraction*total*lateral*math.cos(phi), fraction*total*lateral*math.sin(phi),fraction*total]
                    axial = dot(force,u)
                    transverse = sub(force,[axial*x for x in u])
                    root_moment = cross(sub(contact,a),force)
                    torsion = dot(root_moment,u)
                    bend = norm(sub(root_moment,[torsion*x for x in u]))
                    end_couple = cross(sub(contact,f),force)
                    end_bend = norm(sub(end_couple,[dot(end_couple,u)*x for x in u]))
                    witness = {'mass_kg':mass,'vertical_speed_m_s':velocity,'stopping_distance_mm':stop_mm,
                               'dynamic_peak_multiplier':peak,'lateral_vertical_ratio':lateral,
                               'lateral_direction_deg':direction,'leg_force_CAD_N':force,'root_moment_CAD_N_m':root_moment}
                    retain('compressive_axial_N',max(axial,0),witness)
                    retain('absolute_axial_N',abs(axial),witness)
                    retain('transverse_N',norm(transverse),witness)
                    retain('root_bending_N_m',bend,witness)
                    retain('absolute_root_torsion_N_m',abs(torsion),witness)
                    retain('nominal_combined_axial_bending_stress_Pa',abs(axial)/area+bend*radius/inertia,witness)
                    retain('nominal_isotropic_torsional_stress_proxy_Pa',abs(torsion)*radius/sec['J_m4'],witness)
                    # Magnitude bound at tube socket for the stated linear cantilever.
                    retain('socket_transverse_displacement_times_E_Pa_m',norm(transverse)*length**3/(3*inertia)+end_bend*length**2/(2*inertia),witness)
            responses = []
            for e in materials[product['material']]['axial_E_Pa']:
                responses.append({'E_Pa':e,
                                  'linear_socket_displacement_magnitude_bound_m':extreme['socket_transverse_displacement_times_E_Pa_m']['value']/e,
                                  'displacement_to_span_ratio':extreme['socket_transverse_displacement_times_E_Pa_m']['value']/(e*length),
                                  'Euler_compression_screens':[{'K':k,'critical_N':math.pi**2*e*inertia/(k*length)**2,
                                                                'maximum_demand_over_ideal_Euler':extreme['compressive_axial_N']['value']/(math.pi**2*e*inertia/(k*length)**2)} for k in loads['effective_length_factors_for_Euler_screen']]})
            rows.append({'mass_kg':mass,'load_case':case,'assumed_total_reaction_fraction':fraction,'extrema':extreme,'material_responses':responses})
    return {'seed':seed['id'],'arrangement':arrangement['id'],'product':product['id'],'representative_leg':leg,'cases':rows,
            'limitations':'Point-mass stopping-force sensitivity, not coupled landing simulation. Lateral forces sampled radially inward/outward and tangentially both ways, not a continuous azimuth maximum. Root clamp at attachment; ground reaction at foot contact includes foot/socket eccentricity. Linear displacement is at the socket, not total contact compliance; large deflections invalidate linear theory. Isotropic stress proxies are not CFRP failure criteria. Joint strength and three-contact dynamic load sharing are unassessed.',
            'structural_acceptance':None}


def compute(cfg):
    if cfg['schema'] != 'hopper_r12_structural_trade_inputs_v1':
        raise ValueError('Unsupported input schema')
    geom, loads, account = (cfg[k] for k in ('geometry_hypotheses','load_and_stability_sensitivities','purchase_and_mass_accounting'))
    if cfg['units_and_frames']['configuration_lengths'] != 'mm':
        raise ValueError('Expected mm configuration')
    if account['PETG_cost_exempt'] is not True or account['PETG_installed_mass_exempt'] is not False:
        raise ValueError('PETG accounting does not match current requirement')
    products = cfg['supplier_candidates']
    if len({p['id'] for p in products}) != len(products):
        raise ValueError('Duplicate supplier candidate IDs')
    materials = cfg['material_sensitivity_inputs']
    sections = {p['id']:section(p,materials) for p in products}
    spines = [p for p in products if 'spine' in p['roles']]
    legs = [p for p in products if 'leg' in p['roles']]
    if not spines or not legs or any(not p['material'].startswith('CFRP_') for p in legs):
        raise ValueError('Invalid spine/leg candidate set')
    if sorted(s['count'] for s in geom['spine_layouts']) != [1,2,3,4]:
        raise ValueError('Must compare one through four spines')
    if sorted(s['count'] for s in geom['landing_arrangements']) != [3,4]:
        raise ValueError('Must compare tripod and quadpod')
    positive(account['kerf_per_finished_piece_mm'],'kerf',True)
    positive(account['end_trim_each_end_per_stock_mm'],'trim',True)
    for k in loads['effective_length_factors_for_Euler_screen']:
        positive(k,'effective length factor')
    for seed in geom['layout_seeds']:
        for field in ('pivot_z_mm','leg_attachment_z_mm','leg_attachment_radius_mm','foot_radius_mm'):
            positive(seed[field],field)
        if seed['foot_radius_mm']<=seed['leg_attachment_radius_mm'] or seed['leg_attachment_z_mm']<=seed['pivot_z_mm']:
            raise ValueError('Seed does not have splayed legs attached above pivot')
    spine_models = [spine_proxy(s,p,length,sections[p['id']],materials,loads['effective_length_factors_for_Euler_screen'])
                    for s,p,length in itertools.product(geom['spine_layouts'],spines,geom['spine_finished_lengths_mm'])]
    support = [support_study(seed,arr,geom,loads) for seed,arr in itertools.product(geom['layout_seeds'],geom['landing_arrangements'])]
    landing = [landing_study(seed,arr,geom,loads,p,sections[p['id']],materials) for seed,arr,p in itertools.product(geom['layout_seeds'],geom['landing_arrangements'],legs)]
    candidates = []
    for seed,arr,layout,length,sp,lp in itertools.product(geom['layout_seeds'],geom['landing_arrangements'],geom['spine_layouts'],geom['spine_finished_lengths_mm'],spines,legs):
        leg = leg_geometry(seed,geom,0)
        cid = '|'.join([seed['id'],arr['id'],layout['id'],'L'+str(length),sp['id'],lp['id']])
        groups = {}
        for p,count,cutlength,role in [(sp,layout['count'],length,'spine'),(lp,arr['count'],leg['finished_length_mm'],'leg')]:
            group = groups.setdefault(p['id'],{'product':p,'cuts':[]})
            group['cuts'].extend({'label':role+'_'+str(i+1),'finished_length_mm':cutlength} for i in range(count))
        purchase, massgroups, rejection = [], [], []
        displayed_total, policy_total = D(0), D(0)
        complete_net_evidence = True
        for pid, group in sorted(groups.items()):
            p = group['product']
            if p['currency'] != 'AUD':
                raise ValueError('Foreign-currency tube needs explicit conversion policy')
            allowance = p.get('screening_purchase_allowance')
            stock = p['purchased_length_mm'] if p['purchased_length_mm'] is not None else allowance['stock_length_mm']
            price = D(str(p['price_displayed'] if 'price_displayed' in p else allowance['price_per_whole_tube']))
            packing = exact_pack(group['cuts'],stock,account['end_trim_each_end_per_stock_mm'],account['kerf_per_finished_piece_mm'])
            if not packing['feasible']:
                rejection.append(pid+': '+packing['reason'])
            else:
                subtotal = price*packing['stock_count']
                confirmed_net = p['currency_status'].startswith('Confirmed') and p['tax_basis']=='Includes 10 percent GST' and allowance is None
                policy_sub = subtotal/D('1.10') if confirmed_net else subtotal
                displayed_total += subtotal
                policy_total += policy_sub
                complete_net_evidence = complete_net_evidence and confirmed_net
                purchase.append({'product_id':pid,'stock_length_mm':stock,'packing':packing,
                                 'price_is_variant_allowance':allowance is not None,'currency_status':p['currency_status'],
                                 'displayed_or_allowance_subtotal':money(subtotal),'policy_subtotal_unrounded':str(policy_sub),
                                 'tax_deduction_applied':confirmed_net,'source_url':p['url'],'access_date':p['access_date']})
            installed = sum(c['finished_length_mm'] for c in group['cuts'])*0.001
            volume = sections[pid]['area_m2']*installed
            massgroups.append({'product_id':pid,'installed_length_m':installed,'tube_volume_m3':volume,
                               'mass_cases':[{'density_kg_m3':rho,'mass_kg':rho*volume} for rho in materials[p['material']]['density_kg_m3']]})
        low = sum(min(c['mass_kg'] for c in g['mass_cases']) for g in massgroups)
        high = sum(max(c['mass_kg'] for c in g['mass_cases']) for g in massgroups)
        candidates.append({'id':cid,'seed':seed['id'],'arrangement':arr['id'],'spine_layout':layout['id'],
                           'spine_product':sp['id'],'leg_product':lp['id'],'spine_length_mm':length,
                           'leg_length_mm':leg['finished_length_mm'],'purchase_groups':purchase,'tube_mass_groups':massgroups,
                           'tube_only_mass_sensitivity_extrema_kg':[low,high],
                           'rejection_reasons':rejection,
                           'tube_only_displayed_or_allowance_subtotal_assuming_AUD':None if rejection else money(displayed_total),
                           'tube_only_policy_subtotal_assuming_AUD':None if rejection else money(policy_total),
                           'confirmed_tax_exclusive_tube_subtotal_AUD':money(policy_total) if complete_net_evidence and not rejection else None,
                           'supplier_restrictions':[{'product_id':p['id'],'text':p.get('supplier_restriction','Laminate and joint allowables unverified')} for p in {sp['id']:sp,lp['id']:lp}.values()],
                           'structural_acceptance':None,'rotor_clearance_acceptance':None,'whole_vehicle_budget_acceptance':None})
    return {'schema':'hopper_r12_structural_trade_core_results_v1',
            'status':'Unselected preliminary calculations; verification and physical acceptance not established',
            'supplier_candidates_with_original_provenance':products,'input_provenance':cfg['provenance'],
            'units':{'length':'m unless a field explicitly says mm or um','mass':'kg','force':'N','moment':'N m','stress':'Pa','section_inertia':'m^4','cost':'AUD only where confirmed; otherwise explicitly assumed AUD'},
            'scope':'Stage 1 only: stock schedules, tube-only mass, ideal member proxies, level-ground support and landing demand sensitivities',
            'sections':sections,'spine_models':spine_models,'support_studies':support,'landing_studies':landing,
            'candidate_count':len(candidates),'candidates':candidates,'selected_candidate':None,
            'rounding_policy':'Decimal monetary arithmetic; ROUND_HALF_UP to cents after summing unrounded subtotals. Cut-plus-kerf rounded upward to 1 micrometre; usable stock rounded downward.',
            'pending_work':['Independent artifact-bound checker and deliberately invalid fixtures',
                            'Gimbal-cone rotor/leg/yoke/structure and ground clearance, sampled poses plus continuous bounds',
                            'Actual editable FCStd/STEP solids and recompute verification',
                            'Joint, brace, plate, mounting and equipment-access assessment',
                            'Full installed mass, CG, inertia and moving-group ownership',
                            'Complete priced vehicle BOM, mission energy and actuator-load reconciliation',
                            'Material/laminate and joint qualification; loaded landing and propulsion tests'],
            'whole_vehicle_cost_AUD':None,'whole_vehicle_mass_kg':None,'physical_validation':'unperformed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='analysis/pdr_r12_chief/structural_trade_config_01.json')
    parser.add_argument('--expected-config-sha256',required=True)
    parser.add_argument('--output',default='analysis/pdr_r12_chief/structural_trade_core_results_01.json')
    args = parser.parse_args()
    inp, out = within_root(args.config), within_root(args.output)
    if out.exists():
        raise FileExistsError('Choose a fresh results filename: '+str(out))
    raw = inp.read_bytes()
    if sha(raw) != args.expected_config_sha256:
        raise ValueError('Configuration hash differs from declared input')
    cfg = json.loads(raw.decode('utf-8'),parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON constant '+x)))
    register = within_root(cfg['provenance']['supplier_register_path'])
    register_hash = sha(register.read_bytes())
    if register_hash != cfg['provenance']['supplier_register_file_sha256']:
        raise ValueError('Supplier register hash mismatch')
    result = compute(cfg)
    result['actual_inputs'] = {'config_path':str(inp.relative_to(ROOT)),'config_sha256':sha(raw),
                              'supplier_register_path':str(register.relative_to(ROOT)),'supplier_register_sha256':register_hash,
                              'program_path':str(Path(__file__).resolve().relative_to(ROOT)),
                              'program_sha256':sha(Path(__file__).read_bytes())}
    encoded = json.dumps(result,indent=2,allow_nan=False)+'\n'
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as handle:
        handle.write(encoded)
    print(json.dumps({'analysis_output':str(out.relative_to(ROOT)),'candidate_count':result['candidate_count'],
                      'verification':'not performed by this analysis program','physical_acceptance':'not assessed'}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        raise
