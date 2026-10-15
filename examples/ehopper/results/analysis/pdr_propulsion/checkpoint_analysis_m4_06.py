"""Preliminary propulsion checkpoint calculation; source revision M4-06.

STANDARD-LIBRARY entry point, independent of PyThrust:
  python -B checkpoint_analysis_m4_06.py
Defaults read the adjacent published checkpoint inputs and inspected motor register.
All six output paths below must be declared in the later execute action. Existing
outputs are never overwritten. No installation, network request or source-checkout
modification is performed. This program is not a verification program.

Authority comes from the current configuration, not the historical heading in the
motor register. Outputs are conditional arithmetic, not selected hardware, actual
CAD mass, flight results, supplier quotations or physical qualification.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import csv
import hashlib
import io
import itertools
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parents[1]
INPUT_DIGEST = 'fb3e1b0fbbcefdacdd0c8185bab40a9693148a1f90fda6dcf67c7fd3d5adeb16'
REGISTER_DIGEST = '52c3613c431909985efd361ca5cf89c7cbccdf0a02b12bb50fbb125d748279ab'
INPUT_REF = {'kind':'artifact','id':'PDR-PROPULSION-CHECKPOINT-INPUTS-M4-05',
             'revision':1,'sha256':'8af2841536f741da3194d586786d6dd0fabfaddf0da6f28b27d7bbe80547bda8'}
REGISTER_REF = {'kind':'tool_result','id':'80202d78fc454f8a94a2e06668bf2caf',
                'revision':1,'sha256':'5a91c5a53e23be5e2d11a65eee8e046be531ab74d131c68056f46db2294903cd'}
OUTPUT_NAMES = (
    'installed_component_ledger_m4_06.json',
    'whole_purchase_ledger_m4_06.json',
    'ground_purchase_ledger_m4_06.json',
    'paired_sensitivity_m4_06.csv',
    'checkpoint_results_m4_06.json',
    'checkpoint_report_m4_06.md')
EPS_N = 1e-10  # Representation roundoff only; not a physical/map extrapolation allowance.
CENTRAL_RESERVE_THRUST_MULTIPLIER = 1.20  # Unapproved diagnostic, not an acceptance criterion.


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_bound(path, expected):
    path = path.resolve()
    if not path.is_relative_to(SANDBOX):
        raise ValueError('Input outside shared output sandbox: ' + str(path))
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError('Input digest changed; inspect and revise the analysis provenance: ' + str(path))
    return json.loads(raw), {'path':str(path.relative_to(SANDBOX)), 'sha256':digest(raw)}


def encode(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8')


def money(value):
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def extend_span(span, value):
    if value is None:
        return span
    return [value, value] if span is None else [min(span[0], value), max(span[1], value)]


def interpolate(table, thrust_N, gravity):
    rows = [(r[1] * gravity / 1000.0, r[0], r[2]) for r in table['rows']]
    if thrust_N < rows[0][0] - EPS_N or thrust_N > rows[-1][0] + EPS_N:
        return None
    t = min(max(thrust_N, rows[0][0]), rows[-1][0])
    for lo, hi in zip(rows, rows[1:]):
        if lo[0] <= t <= hi[0]:
            f = (t - lo[0]) / (hi[0] - lo[0])
            return {'vendor_test_current_A':lo[1] + f * (hi[1] - lo[1]),
                    'vendor_test_electrical_power_W':lo[2] + f * (hi[2] - lo[2])}
    raise ArithmeticError('Interpolation interval not found')


def paired_point(total_N, delta_Q_Nm, parameters, table, gravity):
    # Synthetic spin convention only: sigma_upper=+1, sigma_lower=-1 about M+z.
    # delta_Q = Q_lower-Q_upper is then the module +z aerodynamic couple.
    # Actual purchased spin assignments remain unselected.
    tu, tl, qu, ql, ellu, elll = parameters
    a, b = qu * ellu, ql * elll
    den = tu * b + tl * a
    xu = (b * total_N - tl * delta_Q_Nm) / den
    xl = (a * total_N + tu * delta_Q_Nm) / den
    pu, pl = interpolate(table, xu, gravity), interpolate(table, xl, gravity)
    if pu is None or pl is None:
        return None
    Tupper, Tlower = tu * xu, tl * xl
    Qupper, Qlower = a * xu, b * xl
    return {
        'isolated_equivalent_thrust_upper_N':xu,
        'isolated_equivalent_thrust_lower_N':xl,
        'coupled_thrust_upper_N':Tupper, 'coupled_thrust_lower_N':Tlower,
        'synthetic_aero_drag_upper_Nm':Qupper, 'synthetic_aero_drag_lower_Nm':Qlower,
        'synthetic_delta_Q_Nm':Qlower - Qupper,
        'collective_residual_N':Tupper + Tlower - total_N,
        'couple_residual_Nm':Qlower - Qupper - delta_Q_Nm,
        'upper_vendor_test_current_A':pu['vendor_test_current_A'],
        'lower_vendor_test_current_A':pl['vendor_test_current_A'],
        'summed_vendor_test_current_A':pu['vendor_test_current_A'] + pl['vendor_test_current_A'],
        'test_voltage_power_proxy_W':pu['vendor_test_electrical_power_W'] + pl['vendor_test_electrical_power_W']}


def paired_domain(parameters, table, gravity):
    tu, tl, qu, ql, ellu, elll = parameters
    a, b = qu * ellu, ql * elll
    den = tu * b + tl * a
    low = table['rows'][0][1] * gravity / 1000.0
    high = table['rows'][-1][1] * gravity / 1000.0
    return {
        'torque_balanced_collective_min_N':max(low * den / b, low * den / a),
        'torque_balanced_collective_max_N':min(high * den / b, high * den / a)}


def yaw_interval(total_N, parameters, table, gravity):
    tu, tl, qu, ql, ellu, elll = parameters
    a, b = qu * ellu, ql * elll
    den = tu * b + tl * a
    low = table['rows'][0][1] * gravity / 1000.0
    high = table['rows'][-1][1] * gravity / 1000.0
    lower = max((b * total_N - den * high) / tl, (den * low - a * total_N) / tu)
    upper = min((b * total_N - den * low) / tl, (den * high - a * total_N) / tu)
    if lower > upper:
        return None
    result = {'minimum_delta_Q_Nm':lower, 'maximum_delta_Q_Nm':upper,
              'torque_balanced_trim_in_interval':lower <= 0 <= upper,
              'symmetric_about_trim_Nm':min(-lower, upper) if lower <= 0 <= upper else None}
    result['negative_endpoint'] = paired_point(total_N, lower, parameters, table, gravity)
    result['positive_endpoint'] = paired_point(total_N, upper, parameters, table, gravity)
    return result


def mission(mass_kg, propulsion_W, auxiliary_W, cfg):
    p = cfg['proposed_analysis_parameters']
    m = p['mission_energy_proxy']
    extra_J = mass_kg * p['standard_gravity_m_s2'] * m['climb_height_m'] / m['climb_potential_energy_efficiency']
    definitions = [
        ('spool_up', m['spool_up_s'], m['spool_up_mean_hover_power_fraction'], 0.0),
        ('climb', m['climb_s'], 1.0, extra_J),
        ('acquisition_allowance', m['acquisition_allowance_s'], 1.0, 0.0),
        ('uninterrupted_hover', m['hover_duration_s'], 1.0, 0.0),
        ('descent', m['descent_s'], 1.0, 0.0),
        ('touchdown_settling_allowance', m['touchdown_settling_allowance_s'], 1.0, 0.0)]
    stages = []
    for name, duration, factor, extra in definitions:
        stages.append({'stage':name, 'duration_s':duration,
                       'propulsion_energy_J':propulsion_W * factor * duration + extra,
                       'auxiliary_bus_energy_J':auxiliary_W * duration})
    return {'duration_s':sum(s['duration_s'] for s in stages), 'stages':stages,
            'propulsion_energy_Wh':sum(s['propulsion_energy_J'] for s in stages) / 3600.0,
            'auxiliary_energy_Wh':sum(s['auxiliary_bus_energy_J'] for s in stages) / 3600.0,
            'total_energy_Wh':sum(s['propulsion_energy_J'] + s['auxiliary_bus_energy_J'] for s in stages) / 3600.0,
            'unresolved_transient_electrical_correction_Wh':None,
            'qualification':'Sizing proxy only; no trajectory, acquisition, contact, rotor spin-up or thermal verification.'}


def electrical_sensitivity(power_W, cells, p):
    result = []
    for cell_V, resistance in itertools.product(p['open_circuit_cell_voltage_V'], p['battery_pack_resistance_ohm']):
        voc = cell_V * cells
        discriminant = voc * voc - 4 * resistance * power_W
        row = {'open_circuit_V':voc, 'pack_resistance_ohm':resistance,
               'assumed_constant_terminal_power_W':power_W,
               'high_voltage_solution_V':None, 'battery_current_A':None,
               'below_exploratory_cell_floor':None}
        if discriminant >= 0:
            voltage = 0.5 * (voc + math.sqrt(discriminant))
            row.update(high_voltage_solution_V=voltage, battery_current_A=power_W / voltage,
                       below_exploratory_cell_floor=voltage / cells < p['exploratory_loaded_cell_floor_V'])
        result.append(row)
    return result


def energy_grid(mass, power, nominal_Wh, cfg):
    p = cfg['proposed_analysis_parameters']
    rows = []
    for aux, fraction, reserve in itertools.product(p['auxiliary_bus_power_W'], p['terminal_usable_energy_fraction'], p['proposed_reserve_fractions']):
        energy = mission(mass, power, aux, cfg)['total_energy_Wh']
        usable = nominal_Wh * fraction
        rows.append({'auxiliary_bus_power_W':aux, 'terminal_usable_fraction':fraction,
                     'withheld_fraction_of_usable_energy':reserve,
                     'mission_proxy_Wh':energy, 'terminal_usable_Wh':usable,
                     'after_withheld_reserve_margin_Wh':usable * (1 - reserve) - energy})
    return rows


def energy_allowable_power(mass, nominal_Wh, cfg):
    # Algebraic energy envelope, usable even when a propulsion map is absent.
    zero = mission(mass, 0.0, 0.0, cfg)
    unit = mission(mass, 1.0, 0.0, cfg)
    effective_s = (unit['total_energy_Wh'] - zero['total_energy_Wh']) * 3600.0
    p = cfg['proposed_analysis_parameters']
    rows = []
    for aux, fraction, reserve in itertools.product(p['auxiliary_bus_power_W'], p['terminal_usable_energy_fraction'], p['proposed_reserve_fractions']):
        nonhover = mission(mass, 0.0, aux, cfg)['total_energy_Wh']
        allowance = nominal_Wh * fraction * (1 - reserve) - nonhover
        rows.append({'auxiliary_bus_power_W':aux, 'terminal_usable_fraction':fraction,
                     'withheld_fraction_of_usable_energy':reserve,
                     'maximum_constant_hover_propulsion_proxy_W':allowance * 3600.0 / effective_s,
                     'effective_propulsion_duration_s':effective_s})
    return rows


def purchase_row(part, packages, units_per_pack, observations, selected_observation=None, note=''):
    normalized = []
    for observation in observations:
        q = dict(observation)
        net = None
        if q.get('currency') == 'AUD' and q.get('tax_included') is True and q.get('tax_fraction') is not None and q.get('amount') is not None:
            net = Decimal(str(q['amount'])) / (Decimal('1') + Decimal(str(q['tax_fraction'])))
        q['calculated_unrounded_net_AUD_per_listing'] = str(net) if net is not None else None
        normalized.append(q)
    cost = None
    if selected_observation is not None and packages is not None:
        net = normalized[selected_observation]['calculated_unrounded_net_AUD_per_listing']
        if net is not None:
            cost = Decimal(net) * Decimal(packages)
    return {'part_or_category':part, 'whole_purchase_packages':packages,
            'units_per_package':units_per_pack, 'observations':normalized,
            'accounting_observation_index':selected_observation,
            'unrounded_net_AUD_contribution':str(cost) if cost is not None else None,
            'note':note, 'supplier_or_component_selected':False}


def build_ledgers(cfg, register):
    options = {r['id']:r for r in cfg['component_options']}
    sources = {r['id']:r for r in cfg['new_sources']}
    motor_prices = {r.get('component'):r for r in register['price_observations'] if r.get('component')}
    installed, purchases, cases = [], [], []
    for branch, servo_id, controller_id in itertools.product(
            cfg['propulsion_branches'],
            ['SERVO_HITEC_35245S','SERVO_EMAX_0102003010'],
            ['CONTROLLER_WING_MINI','CONTROLLER_H743_WLITE']):
        design = branch['id'] + '__' + servo_id + '__' + controller_id
        servo, controller = options[servo_id], options[controller_id]
        rows = []
        def add(instance, part, mass, source, note=''):
            rows.append({'instance_id':instance, 'part':part, 'claimed_mass_g':mass,
                         'classification':'vendor_claim_not_measured', 'source':source,
                         'CAD_ownership_group':None, 'note':note})
        for i in range(branch['motor_quantity']):
            add('motor_assembly_' + str(i+1), branch['motor'], branch['motor_claimed_mass_g_each'], branch['source'],
                'Commercial total replaces envelope mass; fixed/spinning subdivisions and accessories unresolved.')
        add('installed_battery', branch['battery_candidate'], branch['battery_claimed_mass_g_each'], branch['source'], 'Exactly one battery supplies airborne mass and energy.')
        for i in range(2):
            add('ESC_' + str(i+1), 'Hobbywing 80060442', options['ESC_80060442']['claimed_mass_g_each'], options['ESC_80060442']['source'])
            add('gimbal_servo_' + str(i+1), servo_id, servo['claimed_mass_g_each'], servo['source'])
        if 'installed_subassemblies' in controller:
            for item in controller['installed_subassemblies']:
                add('controller_' + item['id'], controller_id + '/' + item['id'], item['claimed_mass_g'], controller['source'])
        else:
            add('controller_package', controller_id, controller['claimed_mass_g_each'], controller['source'])
        for key in ['RECEIVER_RP1_V2','GNSS_M10Q_5883','RANGE_TFMINI_S']:
            add(key, key, options[key]['claimed_mass_g_each'], options[key]['source'])
        subtotal = sum(r['claimed_mass_g'] for r in rows) / 1000.0
        design_cases = []
        for index, label in enumerate(['low_allowance','central_allowance','high_allowance']):
            allowances = [{'category':r['id'], 'assumed_mass_g':r['study_mass_g'][index],
                           'actual_mass_g':r['actual_mass_g']} for r in cfg['installed_remainder_ledger']['rows']]
            mass = subtotal + sum(r['assumed_mass_g'] for r in allowances) / 1000.0
            c = {'case_id':design + '__' + label, 'design_id':design, 'branch_id':branch['id'],
                 'allowance_level':label, 'study_installed_mass_kg':mass,
                 'vendor_claim_subtotal_kg':subtotal, 'allowance_rows':allowances,
                 'supported_complete_installed_mass_kg':None, 'payload_mass_kg':0.0}
            cases.append(c)
            design_cases.append(c)
        installed.append({'design_id':design, 'selected':False, 'vendor_claim_instances':rows,
                          'study_mass_cases':design_cases,
                          'unknown_unallocated_mass_kg':None,
                          'qualification':'Category enumeration is not a complete component audit. Allowances are not guaranteed bounds. Integrated-module propeller/accessory inclusion can overlap until reconciled. No inertia or physical ownership split is established.'})
        motor_key = 'HIMAX_CR28161100' if branch['table_id'] is None else 'SS_X2814_900_ORIGINAL'
        mp = dict(motor_prices[motor_key])
        mp['source_url'] = next(s['url'] for s in register['sources'] if s['id'] == mp['source'])
        mp['access_date'] = register['access_date']
        purchase = [purchase_row(branch['motor'], branch['motor_quantity'], 1, [mp], note='Currency unresolved; no AUD conversion.'),
                    purchase_row(branch['battery_candidate'], 1, 2, [], note='Whole required two-battery package. Display observations remain in M2-03; normalized currency/tax-resolved quotation unavailable.'),
                    purchase_row('ESC_80060442', 2, 1, options['ESC_80060442']['price_options'], 1,
                                 'Hobbytech tax-supported price is an unavailable-stock cost observation, not supplier selection. Alternative Hobby Station export tax remains unresolved.'),
                    purchase_row(servo_id, 2, 1, [servo['price']], 0 if servo_id == 'SERVO_HITEC_35245S' else None)]
        if branch['table_id'] is not None:
            for prop in branch['propeller_candidates']:
                purchase.append(purchase_row(prop, 1, 1, [], note='Exact handedness/retention and normalized quotation unresolved; do not assign an assumed currency.'))
        else:
            purchase.append(purchase_row('CR28161100 included propeller package', 0, None, [], note='No separate propeller purchase charged in this package scenario; rear identity and package completeness remain unresolved. This exclusion does not resolve installed mass.'))
        for part, sid in [(controller_id, 'E03' if controller_id == 'CONTROLLER_WING_MINI' else 'E02'),
                          ('RECEIVER_RP1_V2','E04'), ('GNSS_M10Q_5883','E05'), ('RANGE_TFMINI_S','E07')]:
            purchase.append(purchase_row(part, 1, 1, [sources[sid]]))
        for r in cfg['installed_remainder_ledger']['rows']:
            if r['id'] == 'propellers_pair':
                continue
            purchase.append(purchase_row(r['id'], None, None, [], note=r.get('notes','') + ' Whole pack/spool/stock quantities unresolved; split PETG-exempt printed parts from purchased hardware.'))
        known = sum((Decimal(r['unrounded_net_AUD_contribution']) for r in purchase if r['unrounded_net_AUD_contribution'] is not None), Decimal('0'))
        unresolved = [r['part_or_category'] for r in purchase if r['unrounded_net_AUD_contribution'] is None and r['whole_purchase_packages'] != 0]
        purchases.append({'design_id':design, 'rows':purchase,
                          'known_unrounded_net_AUD_subtotal':str(known),
                          'known_net_AUD_subtotal_rounded':money(known),
                          'unresolved_cost_rows':unresolved,
                          'purchased_vehicle_hardware_materials_cost':None,
                          'budget_compliance':None, 'procurement_readiness':None,
                          'qualification':'Incomplete subtotal, with unavailable-stock observations. No whole-vehicle cost, procurement feasibility or selection is established.'})
    return installed, purchases, cases


def analyze_case(case, branch, table, cfg, writer):
    p = cfg['proposed_analysis_parameters']
    g = p['standard_gravity_m_s2']
    mass, target = case['study_installed_mass_kg'], case['study_installed_mass_kg'] * g
    nominal = branch['nominal_voltage_V'] * branch['capacity_Ah']
    result = {'case_id':case['case_id'], 'branch_id':branch['id'],
              'study_installed_mass_kg':mass, 'required_neutral_hover_thrust_N':target,
              'nominal_label_battery_energy_Wh':nominal,
              'energy_allowable_hover_power':energy_allowable_power(mass, nominal, cfg),
              'central_grid_case':None, 'sweep':None}
    if table is None:
        result['performance_status'] = 'Unavailable: no integrated-module paired map. Mass and algebraic energy envelopes only; no SunnySky curve substitution.'
        return result
    grids = [p['thrust_interference_upper'], p['thrust_interference_lower'],
             p['torque_interference_upper'], p['torque_interference_lower'],
             p['synthetic_isolated_Q_over_T_m'], p['synthetic_isolated_Q_over_T_m']]
    central = tuple(values[len(values)//2] for values in grids)
    sweep = {'evaluated_parameter_combinations':0, 'in_isolated_table_domain':0,
             'outside_isolated_table_domain':0,
             'torque_balanced_collective_max_N_span':None,
             'in_domain_hover_power_W_span':None,
             'in_domain_central_aux_mission_proxy_Wh_span':None,
             'synthetic_symmetric_yaw_Nm_span':None}
    aux = p['auxiliary_bus_power_W'][1]
    for params in itertools.product(*grids):
        sweep['evaluated_parameter_combinations'] += 1
        domain = paired_domain(params, table, g)
        sweep['torque_balanced_collective_max_N_span'] = extend_span(sweep['torque_balanced_collective_max_N_span'], domain['torque_balanced_collective_max_N'])
        point = paired_point(target, 0.0, params, table, g)
        row = dict(zip(['kT_upper','kT_lower','kQ_upper','kQ_lower','ell_upper_m','ell_lower_m'], params))
        row.update(case_id=case['case_id'], mass_kg=mass, target_N=target,
                   balanced_min_N=domain['torque_balanced_collective_min_N'],
                   balanced_max_N=domain['torque_balanced_collective_max_N'],
                   balanced_max_to_weight=domain['torque_balanced_collective_max_N']/target,
                   trim_in_table_domain=point is not None)
        yaw, reserved_yaw, energy = None, None, None
        if point is None:
            sweep['outside_isolated_table_domain'] += 1
        else:
            sweep['in_isolated_table_domain'] += 1
            yaw = yaw_interval(target, params, table, g)
            reserved_yaw = yaw_interval(CENTRAL_RESERVE_THRUST_MULTIPLIER * target, params, table, g)
            power = point['test_voltage_power_proxy_W']
            energy = mission(mass, power, aux, cfg)
            row.update(upper_isolated_equivalent_N=point['isolated_equivalent_thrust_upper_N'],
                       lower_isolated_equivalent_N=point['isolated_equivalent_thrust_lower_N'],
                       upper_drag_Nm=point['synthetic_aero_drag_upper_Nm'], lower_drag_Nm=point['synthetic_aero_drag_lower_Nm'],
                       upper_vendor_current_A=point['upper_vendor_test_current_A'], lower_vendor_current_A=point['lower_vendor_test_current_A'],
                       paired_power_proxy_W=power, central_aux_bus_W=aux,
                       central_aux_mission_proxy_Wh=energy['total_energy_Wh'],
                       collective_residual_N=point['collective_residual_N'], couple_residual_Nm=point['couple_residual_Nm'])
            if yaw:
                row.update(yaw_min_Nm=yaw['minimum_delta_Q_Nm'], yaw_max_Nm=yaw['maximum_delta_Q_Nm'],
                           yaw_symmetric_Nm=yaw['symmetric_about_trim_Nm'])
                for label, endpoint in [('yaw_negative',yaw['negative_endpoint']),('yaw_positive',yaw['positive_endpoint'])]:
                    if endpoint:
                        row[label+'_upper_vendor_current_A'] = endpoint['upper_vendor_test_current_A']
                        row[label+'_lower_vendor_current_A'] = endpoint['lower_vendor_test_current_A']
                        row[label+'_power_proxy_W'] = endpoint['test_voltage_power_proxy_W']
                sweep['synthetic_symmetric_yaw_Nm_span'] = extend_span(sweep['synthetic_symmetric_yaw_Nm_span'], yaw['symmetric_about_trim_Nm'])
            if reserved_yaw:
                row['yaw_symmetric_at_1p20_weight_Nm'] = reserved_yaw['symmetric_about_trim_Nm']
            row['margin_Wh_at_0p70_usable_0p10_withheld'] = nominal * p['terminal_usable_energy_fraction'][1] * (1 - p['proposed_reserve_fractions'][1]) - energy['total_energy_Wh']
            sweep['in_domain_hover_power_W_span'] = extend_span(sweep['in_domain_hover_power_W_span'], power)
            sweep['in_domain_central_aux_mission_proxy_Wh_span'] = extend_span(sweep['in_domain_central_aux_mission_proxy_Wh_span'], energy['total_energy_Wh'])
        writer.writerow(row)
        if params == central:
            result['central_grid_case'] = {'parameters':dict(zip(['kT_upper','kT_lower','kQ_upper','kQ_lower','ell_upper_m','ell_lower_m'], params)),
                'table_voltage_V':table['voltage_V'], 'domain':domain, 'trim':point,
                'simultaneous_yaw_at_hover':yaw,
                'simultaneous_yaw_at_1p20_weight':reserved_yaw,
                'central_auxiliary_mission_proxy':energy,
                'energy_reserve_sensitivity':energy_grid(mass, point['test_voltage_power_proxy_W'], nominal, cfg) if point else None,
                'constant_power_voltage_sensitivity':electrical_sensitivity(point['test_voltage_power_proxy_W'] + aux, 3 if branch['nominal_voltage_V'] == 11.1 else 4, p) if point else None}
    result['sweep'] = sweep
    result['performance_status'] = 'Synthetic paired correction model over vendor isolated table domain; not calibrated coupled performance.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=HERE/'checkpoint_inputs_m4_20261015_05.json')
    parser.add_argument('--motor-register', type=Path, default=HERE/'source_register_m2_20261015_04_motor_data_esc_followup.json')
    parser.add_argument('--output-dir', type=Path, default=HERE)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if not out.is_relative_to(SANDBOX):
        raise ValueError('Output directory outside sandbox')
    paths = {name:out/name for name in OUTPUT_NAMES}
    if any(path.exists() for path in paths.values()):
        raise FileExistsError('Preserve previous outputs; choose a new task-specific output directory')
    cfg, input_file = load_bound(args.inputs, INPUT_DIGEST)
    register, register_file = load_bound(args.motor_register, REGISTER_DIGEST)
    if cfg['authority']['system_model']['revision'] != 4 or cfg['authority']['work_plan']['id'] != '99f7bb629eef45b89fa38d27c803868c':
        raise ValueError('Unexpected analysis authority')
    if cfg['proposed_analysis_parameters']['mission_energy_proxy']['hover_duration_s'] != 300:
        raise ValueError('Unexpected hover duration in this checkpoint')
    for table in cfg['isolated_tables']:
        if any(b[1] <= a[1] for a,b in zip(table['rows'],table['rows'][1:])):
            raise ValueError('Thrust table must be strictly increasing')
        if any(not math.isclose(r[0]*table['voltage_V'], r[2], rel_tol=1e-12, abs_tol=1e-9) for r in table['rows']):
            raise ValueError('Input table current/power mismatch')
    provenance = {'authority':cfg['authority'], 'input_ref':INPUT_REF, 'motor_register_read_ref':REGISTER_REF,
                  'input_files':[input_file,register_file],
                  'program_file':{'path':str(Path(__file__).resolve().relative_to(SANDBOX)), 'sha256':digest(Path(__file__).read_bytes())},
                  'source_observation_access_date':'2026-10-15',
                  'historical_register_assessment':'Only inspected vendor observations are reused for unchanged component questions. Historical model/plan headings are not current authority.'}
    installed, purchases, cases = build_ledgers(cfg, register)
    fields = ['case_id','mass_kg','target_N','kT_upper','kT_lower','kQ_upper','kQ_lower','ell_upper_m','ell_lower_m',
              'balanced_min_N','balanced_max_N','balanced_max_to_weight','trim_in_table_domain',
              'upper_isolated_equivalent_N','lower_isolated_equivalent_N','upper_drag_Nm','lower_drag_Nm',
              'upper_vendor_current_A','lower_vendor_current_A','paired_power_proxy_W','central_aux_bus_W',
              'central_aux_mission_proxy_Wh','collective_residual_N','couple_residual_Nm',
              'yaw_min_Nm','yaw_max_Nm','yaw_symmetric_Nm',
              'yaw_negative_upper_vendor_current_A','yaw_negative_lower_vendor_current_A','yaw_negative_power_proxy_W',
              'yaw_positive_upper_vendor_current_A','yaw_positive_lower_vendor_current_A','yaw_positive_power_proxy_W',
              'yaw_symmetric_at_1p20_weight_Nm','margin_Wh_at_0p70_usable_0p10_withheld']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    tables = {t['id']:t for t in cfg['isolated_tables']}
    branches = {b['id']:b for b in cfg['propulsion_branches']}
    results = [analyze_case(c, branches[c['branch_id']], tables.get(branches[c['branch_id']]['table_id']), cfg, writer) for c in cases]
    limitations = [
        'No hardware, supplier, topology or controller is selected. Central grid values are not recommended or calibrated values.',
        'Masses combine commercial claims with enumerated allowances, not actual complete CAD mass. Unknown omissions and accessory overlap remain.',
        'Paired T_i=kT_i*Tiso_i and Q_i=kQ_i*ell_i*Tiso_i are independent exploratory corrections. Torque coefficients are not measured or inferred from KV/current.',
        'The paired model is neutral-axis, static and at each isolated test voltage. Rotor spacing, inflow, density correction, articulation, gyroscopic coupling and blade deformation are not resolved.',
        'Yaw results preserve collective thrust while changing both rotor loads. They are constrained by table range, not a qualified electrical/thermal or command envelope.',
        'Vendor test-current boundaries are unknown. Treating summed test input power as propulsion bus demand is an explicit study assumption; it is not motor phase-current evidence.',
        'Thevenin solutions assume constant terminal power and the high-voltage root. Off-test-voltage thrust is unsupported. Algebraic voltage existence is not vehicle feasibility.',
        'The energy proxy includes all named mission stages and auxiliary bus power once. Usable fraction is terminal energy inclusive of battery losses; I-squared-R energy is not subtracted again.',
        'Rotor transient electrical energy, actuator load histories and SOC-dependent battery response remain unresolved. Proxy margins cannot establish endurance compliance.',
        'SunnySky 40 A/30 s and Himax 20 A/15 s are not 300-second thermal qualifications. ESC catalogue ratings do not qualify installed cooling or duty.',
        'The 1.20-weight collective diagnostic and energy reserve grids are unapproved sensitivities, not acceptance limits.',
        'Motor/ESC lag and command-delay parameters are retained but not dynamically simulated here. No realizable command mapping is established.',
        'GNSS/range/receiver alternatives do not establish position accuracy, safety-rated abort, compatible regulated rails or runnable hopper firmware.',
        'Ground equipment remains separately enumerated but unpriced. Whole minimum purchase quantities and many vehicle quotations remain unresolved.',
        'No PyThrust execution, dependency installation, physical calibration, flight test, geometry acceptance or independent verification is performed by this program.']
    payloads = {}
    payloads[OUTPUT_NAMES[0]] = encode({'schema':'hopper.installed_checkpoint/1', 'provenance':provenance,
        'configurations':installed, 'limitations':limitations[:2]})
    payloads[OUTPUT_NAMES[1]] = encode({'schema':'hopper.purchase_checkpoint/1', 'provenance':provenance,
        'accounting_rules':cfg['accounting_rules'], 'rounding':'Decimal ROUND_HALF_UP to 0.01 AUD after summing unrounded available contributions',
        'configurations':purchases, 'complete_budget_compliance':None})
    payloads[OUTPUT_NAMES[2]] = encode({'schema':'hopper.ground_purchase_checkpoint/1', 'provenance':provenance,
        'items':cfg['ground_purchase_ledger'], 'complete_ground_total_AUD':None,
        'status':'Unpriced work remaining; no equipment presumed owned; separate from vehicle cap.'})
    payloads[OUTPUT_NAMES[3]] = stream.getvalue().encode('utf-8')
    summary = {'schema':'hopper.propulsion_checkpoint_results/1', 'provenance':provenance,
        'selected_configuration':None, 'results':results, 'limitations':limitations,
        'sweep_design':'Full Cartesian grid of independent upper/lower kT, kQ and synthetic isolated Q/T parameters for every mass scenario with an isolated table.',
        'CSV_missing_values':'Empty cells mean unsupported/unavailable, not zero. trim_in_table_domain is only an interpolation-domain observation.',
        'interpolation_boundary_roundoff_N':EPS_N,
        'diagnostic_collective_to_weight':CENTRAL_RESERVE_THRUST_MULTIPLIER,
        'dynamic_parameters_retained_not_executed':{k:cfg['proposed_analysis_parameters'][k] for k in ['motor_ESC_response_time_s','command_transport_delay_s','response_boundary']},
        'physical_qualification':None, 'complete_procurement_compliance':None,
        'CAD_mass_reconciliation':None, 'independent_verification':None,
        'output_file_digests':{name:digest(raw) for name,raw in payloads.items()}}
    payloads[OUTPUT_NAMES[4]] = encode(summary)
    lines = ['# PDR propulsion numerical checkpoint M4-06', '',
             'Conditional arithmetic only. No selected vehicle, complete cost, actual CAD mass or physical qualification.', '',
             '## Central-grid results for each central mass-allowance configuration', '',
             '| Configuration | Study mass kg | Required neutral thrust N | Propulsion proxy W | Full mission proxy Wh at 10 W auxiliaries | Synthetic symmetric yaw N m |',
             '|---|---:|---:|---:|---:|---:|']
    for r in results:
        if not r['case_id'].endswith('__central_allowance'):
            continue
        c = r['central_grid_case']
        trim = c['trim'] if c else None
        yaw = c['simultaneous_yaw_at_hover'] if c else None
        power = f"{trim['test_voltage_power_proxy_W']:.3f}" if trim else 'unavailable'
        energy = f"{c['central_auxiliary_mission_proxy']['total_energy_Wh']:.3f}" if trim else 'unavailable'
        yawtext = f"{yaw['symmetric_about_trim_Nm']:.6f}" if yaw and yaw['symmetric_about_trim_Nm'] is not None else 'unavailable'
        lines.append(f"| {r['case_id']} | {r['study_installed_mass_kg']:.4f} | {r['required_neutral_hover_thrust_N']:.4f} | {power} | {energy} | {yawtext} |")
    lines += ['', '## Partial procurement observations', '']
    for r in purchases:
        lines.append('- ' + r['design_id'] + ': known ex-tax subtotal AUD ' + r['known_net_AUD_subtotal_rounded'] + '; ' + str(len(r['unresolved_cost_rows'])) + ' unresolved cost rows. This is not the total vehicle cost.')
    lines += ['', '## Evidence boundaries and remaining work', ''] + ['- ' + x for x in limitations]
    lines += ['', 'Next: publish actual outputs, execute an independent artifact-bound checker, send the numerical checkpoint to the Chief, reconcile actual CAD mass/ownership, complete procurement and ground pricing, and obtain missing supplier/calibration data.']
    payloads[OUTPUT_NAMES[5]] = ('\n'.join(lines) + '\n').encode('utf-8')
    out.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_NAMES:
        with paths[name].open('xb') as handle:
            handle.write(payloads[name])
    print(json.dumps({'status':'calculation_outputs_written_not_verified',
                      'mass_cases':len(cases),
                      'paired_parameter_rows':sum(r['sweep']['evaluated_parameter_combinations'] for r in results if r['sweep']),
                      'outputs':[str(paths[n].relative_to(SANDBOX)) for n in OUTPUT_NAMES],
                      'physical_acceptance':'not_assessed'}, allow_nan=False))


if __name__ == '__main__':
    main()
