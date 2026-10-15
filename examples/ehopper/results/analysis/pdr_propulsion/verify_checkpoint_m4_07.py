"""Independent arithmetic/accounting checker for propulsion checkpoint M4-06.

Run through verify_command after publishing this editable program:
    python -B verify_checkpoint_m4_07.py

Reads the actual nine digest-bound files listed below. Does not import or invoke
checkpoint_analysis_m4_06.py, use PyThrust, access the network, install packages,
modify supplied sources, or write results. Stdout contains one VerificationResult;
diagnostics go to stderr. Independent formulas check the produced numerical data,
not aerodynamic validity or engineering feasibility. Floating-point tolerances
below concern arithmetic reproduction only, not approved simulation tolerances.
Authority: system model r4; work plan 99f7bb629eef45b89fa38d27c803868c r1;
interface decision 88561ff8b3ba4e8286cebd95a93e3b08 r1.
"""
import sys
sys.dont_write_bytecode = True
import csv
import hashlib
import itertools
import json
import math
import traceback
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = {
    'checkpoint_inputs_m4_20261015_05.json': 'fb3e1b0fbbcefdacdd0c8185bab40a9693148a1f90fda6dcf67c7fd3d5adeb16',
    'source_register_m2_20261015_04_motor_data_esc_followup.json': '52c3613c431909985efd361ca5cf89c7cbccdf0a02b12bb50fbb125d748279ab',
    'checkpoint_analysis_m4_06.py': '53bd5a04ab58a28c101fc809c2bf87a0ec27057e302053aa3843e9cf1660cc4b',
    'installed_component_ledger_m4_06.json': 'b64f324bb7a132b6856cdc625adc98074ce5b313fff8bd7d6659d9686ee8b3ce',
    'whole_purchase_ledger_m4_06.json': 'c59bfa4c7774b4ce71200ef3a70f4799d2023b8073575e60287b332936376256',
    'ground_purchase_ledger_m4_06.json': '637a18ca2c484fd38880b7485bacc5ed23d54788a7743f6df6ac9695829fb4dc',
    'paired_sensitivity_m4_06.csv': '2795c5d9fe36bcaf72e40077ada82557c8d8b3674a2bb264f34cb6755fcfda56',
    'checkpoint_results_m4_06.json': '45d5a52b5bfba590d84250322591cb3db97aa8bc1ca80bfc6a364ea2b7b5baa8',
    'checkpoint_report_m4_06.md': '50f3ce91607ce4dc5b66620328bb6d6eb8547141e96be7e59c58dd0327c6f705'
}
CHECKS = {}
MEASUREMENTS = {}
FAILURES = []
RTOL = 2e-10
ATOL = 2e-9
BOUNDARY_N = 1e-10


def check(category, condition, detail=''):
    passed = bool(condition)
    CHECKS[category] = CHECKS.get(category, True) and passed
    if not passed:
        FAILURES.append(category + ': ' + detail)
        if len(FAILURES) <= 40:
            print(FAILURES[-1], file=sys.stderr)


def equal(category, actual, expected, detail=''):
    if expected is None or isinstance(expected, (str, bool)):
        check(category, actual == expected and (expected is not None or actual is None), detail)
    elif isinstance(expected, (int, float)):
        check(category, isinstance(actual, (int, float)) and not isinstance(actual, bool)
              and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=RTOL, abs_tol=ATOL),
              detail + ': ' + repr(actual) + ' versus ' + repr(expected))
    elif isinstance(expected, list):
        check(category, isinstance(actual, list) and len(actual) == len(expected), detail + ' list length')
        if isinstance(actual, list) and len(actual) == len(expected):
            for i, (a, e) in enumerate(zip(actual, expected)):
                equal(category, a, e, detail + '[' + str(i) + ']')
    elif isinstance(expected, dict):
        check(category, isinstance(actual, dict), detail + ' object')
        if isinstance(actual, dict):
            for key, value in expected.items():
                check(category, key in actual, detail + '/' + key + ' present')
                if key in actual:
                    equal(category, actual[key], value, detail + '/' + key)
    else:
        raise TypeError('Unsupported comparison type')


def money(value):
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def interp(table, thrust, g):
    knots = [r[1] * g / 1000 for r in table['rows']]
    if thrust < knots[0] - BOUNDARY_N or thrust > knots[-1] + BOUNDARY_N:
        return None
    x = min(knots[-1], max(knots[0], thrust))
    for i in range(len(knots) - 1):
        if x <= knots[i + 1]:
            left, right = table['rows'][i:i + 2]
            left_weight = (knots[i + 1] - x) / (knots[i + 1] - knots[i])
            return (left_weight * left[0] + (1 - left_weight) * right[0],
                    left_weight * left[2] + (1 - left_weight) * right[2])
    raise ArithmeticError('No interpolation segment')


def point(T, dq, pars, table, g):
    tu, tl, qu, ql, eu, el = pars
    a, b = qu * eu, ql * el
    # Eliminate lower isolated thrust from torque balance, independently of
    # the analysis program's determinant-form allocation.
    x = (T - tl * dq / b) / (tu + tl * a / b)
    y = (dq + a * x) / b
    up, low = interp(table, x, g), interp(table, y, g)
    if up is None or low is None:
        return None
    return {
        'isolated_equivalent_thrust_upper_N': x,
        'isolated_equivalent_thrust_lower_N': y,
        'coupled_thrust_upper_N': tu * x,
        'coupled_thrust_lower_N': tl * y,
        'synthetic_aero_drag_upper_Nm': a * x,
        'synthetic_aero_drag_lower_Nm': b * y,
        'synthetic_delta_Q_Nm': b * y - a * x,
        'collective_residual_N': tu * x + tl * y - T,
        'couple_residual_Nm': b * y - a * x - dq,
        'upper_vendor_test_current_A': up[0],
        'lower_vendor_test_current_A': low[0],
        'summed_vendor_test_current_A': up[0] + low[0],
        'test_voltage_power_proxy_W': up[1] + low[1]
    }


def domain(pars, table, g):
    tu, tl, qu, ql, eu, el = pars
    ratio = qu * eu / (ql * el)
    lo, hi = [table['rows'][i][1] * g / 1000 for i in (0, -1)]
    coefficient = tu + tl * ratio
    return {'torque_balanced_collective_min_N': coefficient * max(lo, lo / ratio),
            'torque_balanced_collective_max_N': coefficient * min(hi, hi / ratio)}


def yaw(T, pars, table, g):
    tu, tl, qu, ql, eu, el = pars
    a, b = qu * eu, ql * el
    lo, hi = [table['rows'][i][1] * g / 1000 for i in (0, -1)]
    # Intersect the upper-thrust interval with the lower-thrust limits at fixed T.
    xmin = max(lo, (T - tl * hi) / tu)
    xmax = min(hi, (T - tl * lo) / tu)
    if xmin > xmax:
        return None
    def couple(x):
        return b * (T - tu * x) / tl - a * x
    qmin, qmax = couple(xmax), couple(xmin)
    balanced = qmin <= 0 <= qmax
    return {'minimum_delta_Q_Nm': qmin, 'maximum_delta_Q_Nm': qmax,
            'torque_balanced_trim_in_interval': balanced,
            'symmetric_about_trim_Nm': min(-qmin, qmax) if balanced else None,
            'negative_endpoint': point(T, qmin, pars, table, g),
            'positive_endpoint': point(T, qmax, pars, table, g)}


def mission(mass, power, aux, cfg):
    p = cfg['proposed_analysis_parameters']
    m = p['mission_energy_proxy']
    grav_J = mass * p['standard_gravity_m_s2'] * m['climb_height_m'] / m['climb_potential_energy_efficiency']
    schedule = [
        ('spool_up', m['spool_up_s'], m['spool_up_mean_hover_power_fraction']),
        ('climb', m['climb_s'], 1),
        ('acquisition_allowance', m['acquisition_allowance_s'], 1),
        ('uninterrupted_hover', m['hover_duration_s'], 1),
        ('descent', m['descent_s'], 1),
        ('touchdown_settling_allowance', m['touchdown_settling_allowance_s'], 1)]
    stages = [{'stage': name, 'duration_s': t,
               'propulsion_energy_J': power * t * factor + (grav_J if name == 'climb' else 0),
               'auxiliary_bus_energy_J': aux * t} for name, t, factor in schedule]
    duration = math.fsum(t for _, t, _ in schedule)
    effective = math.fsum(t * factor for _, t, factor in schedule)
    return {'duration_s': duration, 'stages': stages,
            'propulsion_energy_Wh': (power * effective + grav_J) / 3600,
            'auxiliary_energy_Wh': aux * duration / 3600,
            'total_energy_Wh': (power * effective + grav_J + aux * duration) / 3600,
            'unresolved_transient_electrical_correction_Wh': None}, effective, grav_J


def energy_rows(mass, power, nominal, cfg, envelope=False):
    p = cfg['proposed_analysis_parameters']
    answer = []
    for aux, fraction, reserve in itertools.product(p['auxiliary_bus_power_W'],
            p['terminal_usable_energy_fraction'], p['proposed_reserve_fractions']):
        m, effective, grav = mission(mass, power, aux, cfg)
        base = {'auxiliary_bus_power_W': aux, 'terminal_usable_fraction': fraction,
                'withheld_fraction_of_usable_energy': reserve}
        if envelope:
            base.update(maximum_constant_hover_propulsion_proxy_W=
                (3600 * nominal * fraction * (1 - reserve) - grav - aux * m['duration_s']) / effective,
                effective_propulsion_duration_s=effective)
        else:
            base.update(mission_proxy_Wh=m['total_energy_Wh'], terminal_usable_Wh=nominal * fraction,
                after_withheld_reserve_margin_Wh=nominal * fraction * (1 - reserve) - m['total_energy_Wh'])
        answer.append(base)
    return answer


def voltage_rows(power, cells, p):
    answer = []
    for cell_v, resistance in itertools.product(p['open_circuit_cell_voltage_V'], p['battery_pack_resistance_ohm']):
        voc = cell_v * cells
        d = voc * voc - 4 * resistance * power
        row = {'open_circuit_V': voc, 'pack_resistance_ohm': resistance,
               'assumed_constant_terminal_power_W': power, 'high_voltage_solution_V': None,
               'battery_current_A': None, 'below_exploratory_cell_floor': None}
        if d >= 0:
            current = 2 * power / (voc + math.sqrt(d))
            voltage = voc - resistance * current
            row.update(high_voltage_solution_V=voltage, battery_current_A=current,
                below_exploratory_cell_floor=voltage / cells < p['exploratory_loaded_cell_floor_V'])
        answer.append(row)
    return answer


def main():
    raw = {}
    for name, expected in FILES.items():
        data = (HERE / name).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        check('Artifact file digests match the inspected checkpoint', actual == expected, name)
        raw[name] = data
    if CHECKS['Artifact file digests match the inspected checkpoint'] is False:
        raise ValueError('Digest mismatch: inspect changed files before numerical comparison')
    docs = {name: json.loads(data) for name, data in raw.items() if name.endswith('.json')}
    cfg = docs['checkpoint_inputs_m4_20261015_05.json']
    reg = docs['source_register_m2_20261015_04_motor_data_esc_followup.json']
    installed = docs['installed_component_ledger_m4_06.json']
    purchase = docs['whole_purchase_ledger_m4_06.json']
    ground = docs['ground_purchase_ledger_m4_06.json']
    results = docs['checkpoint_results_m4_06.json']
    report = raw['checkpoint_report_m4_06.md'].decode('utf-8')
    authority = cfg['authority']
    equal('Current authority is retained', authority['system_model'],
        {'id':'system', 'revision':4, 'sha256':'e89e68e192965d8e012cc1213e59c02610f55042ad26d7392ebef0401237ee75'})
    equal('Current authority is retained', authority['work_plan'],
        {'id':'99f7bb629eef45b89fa38d27c803868c', 'revision':1, 'sha256':'e5af8e2f56f7c851b65518b129f39550be73911f56461279cbbb1e85e1cdd5f0'})
    equal('Current authority is retained', authority['interface'],
        {'id':'88561ff8b3ba4e8286cebd95a93e3b08', 'revision':1, 'sha256':'ad6662afab9685585264c86e052c246996d23f4369c6432b56094a42a9187c04'})
    for doc in (installed, purchase, ground, results):
        equal('Output provenance agrees with actual inputs', doc['provenance']['authority'], authority)
        for entry in doc['provenance']['input_files'] + [doc['provenance']['program_file']]:
            name = Path(entry['path']).name
            check('Output provenance agrees with actual inputs', entry['sha256'] == FILES[name], name)
    for name, sha in results['output_file_digests'].items():
        check('Result manifest binds its ledger and CSV files', FILES.get(name) == sha, name)
    check('Result manifest binds its ledger and CSV files', set(results['output_file_digests']) == {
        'installed_component_ledger_m4_06.json','whole_purchase_ledger_m4_06.json',
        'ground_purchase_ledger_m4_06.json','paired_sensitivity_m4_06.csv'})
    p = cfg['proposed_analysis_parameters']
    g = p['standard_gravity_m_s2']
    tables = {t['id']: t for t in cfg['isolated_tables']}
    vendor_tables = reg['motor_candidates'][0]['isolated_tables']
    for table, vendor in zip(cfg['isolated_tables'], vendor_tables):
        equal('Isolated tables preserve the inspected supplier observations', table['rows'], vendor['rows'])
        equal('Isolated tables preserve the inspected supplier observations', table['voltage_V'], vendor['test_voltage_V'])
        check('Isolated tables preserve the inspected supplier observations', table['source_propeller_label'] == vendor['source_propeller_label'])
        check('Isolated table knots and units are consistent', all(b[1] > a[1] for a,b in zip(table['rows'], table['rows'][1:])))
        for current, gf, watts in table['rows']:
            equal('Isolated table knots and units are consistent', watts, current * table['voltage_V'])
            equal('Isolated table knots and units are consistent', interp(table, gf * g / 1000, g), None) if False else None
        lo, hi = [table['rows'][i][1] * g / 1000 for i in (0,-1)]
        check('Independent oracle excludes out-of-table demands', interp(table, lo - 1e-6, g) is None and interp(table, hi + 1e-6, g) is None)
    branches = {b['id']: b for b in cfg['propulsion_branches']}
    options = {r['id']: r for r in cfg['component_options']}
    expected_designs = set()
    expected_cases = {}
    configuration_by_id = {c['design_id']: c for c in installed['configurations']}
    for branch, servo_id, controller_id in itertools.product(cfg['propulsion_branches'],
            ['SERVO_HITEC_35245S','SERVO_EMAX_0102003010'], ['CONTROLLER_WING_MINI','CONTROLLER_H743_WLITE']):
        design = branch['id'] + '__' + servo_id + '__' + controller_id
        expected_designs.add(design)
        c = configuration_by_id[design]
        servo, controller = options[servo_id], options[controller_id]
        expected_instances = {'motor_assembly_' + str(i+1): branch['motor_claimed_mass_g_each'] for i in range(branch['motor_quantity'])}
        expected_instances['installed_battery'] = branch['battery_claimed_mass_g_each']
        for i in (1,2):
            expected_instances['ESC_' + str(i)] = options['ESC_80060442']['claimed_mass_g_each']
            expected_instances['gimbal_servo_' + str(i)] = servo['claimed_mass_g_each']
        if 'installed_subassemblies' in controller:
            for sub in controller['installed_subassemblies']:
                expected_instances['controller_' + sub['id']] = sub['claimed_mass_g'] * sub['quantity']
        else:
            expected_instances['controller_package'] = controller['claimed_mass_g_each']
        for key in ('RECEIVER_RP1_V2','GNSS_M10Q_5883','RANGE_TFMINI_S'):
            expected_instances[key] = options[key]['claimed_mass_g_each']
        rows = c['vendor_claim_instances']
        actual_instances = {r['instance_id']:r['claimed_mass_g'] for r in rows}
        check('Installed instance quantities and masses match branch inputs', len(rows) == len(actual_instances) and set(actual_instances) == set(expected_instances), design)
        equal('Installed instance quantities and masses match branch inputs', actual_instances, expected_instances, design)
        check('Installed ledger preserves unselected and incomplete status', c['selected'] is False and c['unknown_unallocated_mass_kg'] is None, design)
        subtotal = math.fsum(expected_instances.values()) / 1000
        check('Installed mass scenarios match enumerated allowances', len(c['study_mass_cases']) == 3, design)
        for i, case in enumerate(c['study_mass_cases']):
            expected_rows = [{'category':r['id'],'assumed_mass_g':r['study_mass_g'][i],'actual_mass_g':None} for r in cfg['installed_remainder_ledger']['rows']]
            equal('Installed mass scenarios match enumerated allowances', case['allowance_rows'], expected_rows, case['case_id'])
            mass = subtotal + math.fsum(r['assumed_mass_g'] for r in expected_rows) / 1000
            equal('Installed mass scenarios match enumerated allowances', case['vendor_claim_subtotal_kg'], subtotal)
            equal('Installed mass scenarios match enumerated allowances', case['study_installed_mass_kg'], mass)
            check('Installed ledger preserves unselected and incomplete status', case['supported_complete_installed_mass_kg'] is None)
            equal('REQ-ZERO-PAYLOAD: study inputs contain zero payload', case['payload_mass_kg'], 0)
            expected_cases[case['case_id']] = (mass, branch)
    check('Design and mass-scenario coverage is complete for this checkpoint', set(configuration_by_id) == expected_designs and len(installed['configurations']) == 12 and len(expected_cases) == 36)
    check('Whole-purchase alternative coverage matches installed alternatives', {c['design_id'] for c in purchase['configurations']} == expected_designs and len(purchase['configurations']) == 12)
    for c in purchase['configurations']:
        design = c['design_id']
        branch_id, servo_id, controller_id = design.split('__')
        branch = branches[branch_id]
        rows = c['rows']
        bypart = {r['part_or_category']:r for r in rows}
        check('Whole-purchase rows are unique', len(bypart) == len(rows), design)
        battery = bypart[branch['battery_candidate']]
        check('Two batteries purchased while one flies', battery['whole_purchase_packages'] == 1 and battery['units_per_package'] == 2, design)
        for part, count in ((branch['motor'],branch['motor_quantity']),('ESC_80060442',2),(servo_id,2),(controller_id,1),('RECEIVER_RP1_V2',1),('GNSS_M10Q_5883',1),('RANGE_TFMINI_S',1)):
            check('Whole listed component quantities are retained', bypart[part]['whole_purchase_packages'] == count and bypart[part]['units_per_package'] == 1, design + '/' + part)
        for remainder in cfg['installed_remainder_ledger']['rows']:
            if remainder['id'] != 'propellers_pair':
                check('Unspecified pack and spool quantities remain unknown', bypart[remainder['id']]['whole_purchase_packages'] is None, remainder['id'])
        known, unresolved = Decimal('0'), []
        for row in rows:
            nets = []
            for obs in row['observations']:
                net = None
                if obs.get('currency') == 'AUD' and obs.get('tax_included') is True and obs.get('tax_fraction') is not None and obs.get('amount') is not None:
                    net = Decimal(str(obs['amount'])) / (Decimal('1') + Decimal(str(obs['tax_fraction'])))
                recorded = obs['calculated_unrounded_net_AUD_per_listing']
                check('Tax-exclusive calculations require explicit AUD and tax basis', recorded is None if net is None else recorded is not None and Decimal(recorded) == net, row['part_or_category'])
                nets.append(net)
            index = row['accounting_observation_index']
            packages = row['whole_purchase_packages']
            contribution = None if index is None or packages is None or nets[index] is None else nets[index] * Decimal(packages)
            recorded = row['unrounded_net_AUD_contribution']
            check('Whole-purchase contributions and decimal subtotal reproduce', recorded is None if contribution is None else recorded is not None and Decimal(recorded) == contribution, row['part_or_category'])
            if contribution is not None:
                known += contribution
            elif packages != 0:
                unresolved.append(row['part_or_category'])
            check('Procurement alternatives remain unselected', row['supplier_or_component_selected'] is False)
        check('Whole-purchase contributions and decimal subtotal reproduce', Decimal(c['known_unrounded_net_AUD_subtotal']) == known and c['known_net_AUD_subtotal_rounded'] == money(known), design)
        check('Unknown costs do not become complete-budget compliance', c['unresolved_cost_rows'] == unresolved and len(unresolved) > 0 and c['purchased_vehicle_hardware_materials_cost'] is None and c['budget_compliance'] is None and c['procurement_readiness'] is None, design)
        check('Report partial-cost figures match ledger', 'known ex-tax subtotal AUD ' + money(known) + '; ' + str(len(unresolved)) + ' unresolved cost rows' in report, design)
    check('Unknown costs do not become complete-budget compliance', purchase['complete_budget_compliance'] is None)
    equal('Ground ledger remains separate and explicitly unpriced', ground['items'], cfg['ground_purchase_ledger'])
    check('Ground ledger remains separate and explicitly unpriced', ground['complete_ground_total_AUD'] is None)
    result_by_id = {r['case_id']:r for r in results['results']}
    check('Numerical results cover every mass scenario once', len(results['results']) == len(expected_cases) and set(result_by_id) == set(expected_cases))
    grid_names = ['thrust_interference_upper','thrust_interference_lower','torque_interference_upper','torque_interference_lower','synthetic_isolated_Q_over_T_m','synthetic_isolated_Q_over_T_m']
    grids = [p[key] for key in grid_names]
    combinations = set(itertools.product(*grids))
    central = tuple(v[len(v)//2] for v in grids)
    parameter_keys = ['kT_upper','kT_lower','kQ_upper','kQ_lower','ell_upper_m','ell_lower_m']
    sweep_values = {cid: {'keys':set(),'maximum':[],'power':[],'energy':[],'yaw':[]} for cid,(mass,b) in expected_cases.items() if b['table_id'] is not None}
    max_collective = max_torque = 0.0
    csv_count = 0
    for row in csv.DictReader(raw['paired_sensitivity_m4_06.csv'].decode('utf-8').splitlines()):
        csv_count += 1
        cid = row['case_id']
        mass, branch = expected_cases[cid]
        table = tables[branch['table_id']]
        pars = tuple(float(row[k]) for k in parameter_keys)
        stats = sweep_values[cid]
        check('CSV Cartesian sweep coverage has no duplicates or foreign parameters', pars in combinations and pars not in stats['keys'], cid)
        stats['keys'].add(pars)
        T = mass * g
        d, pt = domain(pars, table, g), point(T, 0, pars, table, g)
        stats['maximum'].append(d['torque_balanced_collective_max_N'])
        expected = {'mass_kg':mass,'target_N':T,'balanced_min_N':d['torque_balanced_collective_min_N'],
            'balanced_max_N':d['torque_balanced_collective_max_N'], 'balanced_max_to_weight':d['torque_balanced_collective_max_N']/T}
        check('CSV unsupported trim rows are explicitly distinguished', row['trim_in_table_domain'] == str(pt is not None), cid)
        optional_columns = [k for k in row if k not in ['case_id','trim_in_table_domain'] + parameter_keys + list(expected)]
        if pt is not None:
            power = pt['test_voltage_power_proxy_W']
            m, _, _ = mission(mass, power, p['auxiliary_bus_power_W'][1], cfg)
            y = yaw(T, pars, table, g)
            yr = yaw(1.20*T, pars, table, g)
            expected.update(upper_isolated_equivalent_N=pt['isolated_equivalent_thrust_upper_N'],lower_isolated_equivalent_N=pt['isolated_equivalent_thrust_lower_N'],
                upper_drag_Nm=pt['synthetic_aero_drag_upper_Nm'],lower_drag_Nm=pt['synthetic_aero_drag_lower_Nm'],
                upper_vendor_current_A=pt['upper_vendor_test_current_A'],lower_vendor_current_A=pt['lower_vendor_test_current_A'],
                paired_power_proxy_W=power,central_aux_bus_W=p['auxiliary_bus_power_W'][1],central_aux_mission_proxy_Wh=m['total_energy_Wh'],
                collective_residual_N=pt['collective_residual_N'],couple_residual_Nm=pt['couple_residual_Nm'],
                margin_Wh_at_0p70_usable_0p10_withheld=branch['nominal_voltage_V']*branch['capacity_Ah']*p['terminal_usable_energy_fraction'][1]*(1-p['proposed_reserve_fractions'][1])-m['total_energy_Wh'])
            stats['power'].append(power)
            stats['energy'].append(m['total_energy_Wh'])
            if y is not None:
                expected.update(yaw_min_Nm=y['minimum_delta_Q_Nm'],yaw_max_Nm=y['maximum_delta_Q_Nm'],yaw_symmetric_Nm=y['symmetric_about_trim_Nm'])
                if y['symmetric_about_trim_Nm'] is not None:
                    stats['yaw'].append(y['symmetric_about_trim_Nm'])
                for prefix, endpoint in [('yaw_negative',y['negative_endpoint']),('yaw_positive',y['positive_endpoint'])]:
                    if endpoint is not None:
                        expected[prefix+'_upper_vendor_current_A'] = endpoint['upper_vendor_test_current_A']
                        expected[prefix+'_lower_vendor_current_A'] = endpoint['lower_vendor_test_current_A']
                        expected[prefix+'_power_proxy_W'] = endpoint['test_voltage_power_proxy_W']
            if yr is not None:
                expected['yaw_symmetric_at_1p20_weight_Nm'] = yr['symmetric_about_trim_Nm']
            xu, xl = float(row['upper_isolated_equivalent_N']), float(row['lower_isolated_equivalent_N'])
            max_collective = max(max_collective,abs(pars[0]*xu+pars[1]*xl-T))
            max_torque = max(max_torque,abs(pars[3]*pars[5]*xl-pars[2]*pars[4]*xu))
        for key in set(optional_columns) | set(expected):
            value = expected.get(key)
            if value is None:
                check('CSV unsupported values remain empty rather than zero', row[key] == '', cid + '/' + key)
            else:
                equal('CSV allocation, interpolation, yaw and mission arithmetic reproduce', float(row[key]) if row[key] else None, value, cid + '/' + key)
    for cid, stats in sweep_values.items():
        check('CSV Cartesian sweep coverage has no duplicates or foreign parameters', stats['keys'] == combinations, cid)
        r = result_by_id[cid]
        expected_sweep = {'evaluated_parameter_combinations':len(combinations),
            'in_isolated_table_domain':len(stats['power']), 'outside_isolated_table_domain':len(combinations)-len(stats['power'])}
        for field,key in [('torque_balanced_collective_max_N_span','maximum'),('in_domain_hover_power_W_span','power'),('in_domain_central_aux_mission_proxy_Wh_span','energy'),('synthetic_symmetric_yaw_Nm_span','yaw')]:
            expected_sweep[field] = [min(stats[key]),max(stats[key])] if stats[key] else None
        equal('JSON sweep summaries reproduce the full CSV population', r['sweep'], expected_sweep, cid)
    for cid, (mass, branch) in expected_cases.items():
        r = result_by_id[cid]
        T, nominal = mass*g, branch['nominal_voltage_V']*branch['capacity_Ah']
        equal('Numerical result identities and basic units match inputs', r, {'branch_id':branch['id'],'study_installed_mass_kg':mass,'required_neutral_hover_thrust_N':T,'nominal_label_battery_energy_Wh':nominal}, cid)
        equal('Energy-envelope arithmetic retains all auxiliary and reserve cases', r['energy_allowable_hover_power'], energy_rows(mass,0,nominal,cfg,True), cid)
        if branch['table_id'] is None:
            check('Integrated alternative receives no transplanted performance map', r['central_grid_case'] is None and r['sweep'] is None, cid)
            continue
        table = tables[branch['table_id']]
        pt = point(T,0,central,table,g)
        c = r['central_grid_case']
        equal('Central paired operating points reproduce independently', c['parameters'],dict(zip(parameter_keys,central)),cid)
        equal('Central paired operating points reproduce independently', c['domain'],domain(central,table,g),cid)
        equal('Central paired operating points reproduce independently', c['trim'],pt,cid)
        equal('Central paired operating points reproduce independently', c['table_voltage_V'],table['voltage_V'],cid)
        y = yaw(T,central,table,g) if pt else None
        equal('Simultaneous yaw endpoint currents reproduce at fixed collective', c['simultaneous_yaw_at_hover'],y,cid)
        equal('Simultaneous yaw endpoint currents reproduce at fixed collective', c['simultaneous_yaw_at_1p20_weight'],yaw(1.20*T,central,table,g) if pt else None,cid)
        if pt is None:
            check('Unsupported central trim receives no energy or voltage result', all(c[k] is None for k in ['central_auxiliary_mission_proxy','energy_reserve_sensitivity','constant_power_voltage_sensitivity']),cid)
        else:
            power = pt['test_voltage_power_proxy_W']
            m,_,_ = mission(mass,power,p['auxiliary_bus_power_W'][1],cfg)
            equal('Mission stage integrals count auxiliary energy once',c['central_auxiliary_mission_proxy'],m,cid)
            equal('Energy-envelope arithmetic retains all auxiliary and reserve cases',c['energy_reserve_sensitivity'],energy_rows(mass,power,nominal,cfg),cid)
            equal('Thevenin constant-power sensitivity reproduces independently',c['constant_power_voltage_sensitivity'],voltage_rows(power+p['auxiliary_bus_power_W'][1],3 if branch['nominal_voltage_V']==11.1 else 4,p),cid)
            if cid.endswith('__central_allowance'):
                expected_line = f"| {cid} | {mass:.4f} | {T:.4f} | {power:.3f} | {m['total_energy_Wh']:.3f} | {y['symmetric_about_trim_Nm']:.6f} |"
                check('Report numerical central rows match underlying artifacts',expected_line in report,cid)
    equal('REQ-HOVER-DURATION: proxy includes a separate 300 s hover segment',p['mission_energy_proxy']['hover_duration_s'],300)
    equal('REQ-HOVER-HEIGHT: sizing proxy uses the 5 m climb target',p['mission_energy_proxy']['climb_height_m'],5)
    check('Unverified engineering conclusions remain unavailable',all(results[k] is None for k in ['selected_configuration','physical_qualification','complete_procurement_compliance','CAD_mass_reconciliation','independent_verification']))
    check('Report retains every declared evidence limitation',all('- '+s in report for s in results['limitations']))
    check('CSV row count agrees with the configured Cartesian product',csv_count==len(sweep_values)*len(combinations))
    MEASUREMENTS.update({
        'checked_mass_scenarios':{'value':len(expected_cases),'unit':''},
        'checked_paired_parameter_rows':{'value':csv_count,'unit':''},
        'maximum_reconstructed_collective_residual':{'value':max_collective,'unit':'N'},
        'maximum_reconstructed_torque_balance_residual':{'value':max_torque,'unit':'N m'},
        'arithmetic_comparison_relative_tolerance':{'value':RTOL,'unit':''}
    })


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        check('Checker completed its intended arithmetic scope',False,type(exc).__name__+': '+str(exc))
        traceback.print_exc(file=sys.stderr)
    else:
        check('Checker completed its intended arithmetic scope',True)
    CHECKS.update({
        'REQ-HARDWARE-BUDGET: complete purchased vehicle cost compliance':None,
        'REQ-PROPULSION-BUDGET: complete CAD-reconciled installed mass':None,
        'REQ-PROPULSION-BUDGET: physical coupled thrust torque current calibration':None,
        'REQ-PROPULSION-BUDGET: mission-duration thermal and loaded-voltage qualification':None,
        'REQ-PROPULSION-BUDGET: measured usable battery energy and transient demand':None,
        'Realizable motor ESC and loaded gimbal response calibration':None,
        'REQ-HOVER-DURATION: demonstrated uninterrupted hover':None,
        'Full takeoff acquisition hover landing simulation acceptance':None,
        'Complete separately priced reusable ground equipment':None,
        'Physical geometry structural and flight validation':None
    })
    outcome = 'failed' if any(v is False for v in CHECKS.values()) else 'passed'
    print('Checker failure observations: '+str(len(FAILURES)),file=sys.stderr)
    print(json.dumps({'outcome':outcome,
        'explanation':'Independent digest-bound arithmetic and accounting audit of checkpoint M4-06 only. Passing performed checks does not qualify assumed coaxial/torque parameters, source specifications, complete procurement, CAD mass closure, actuator realization or mission performance. Null checks were not performed. Historical sourcing headers are not current authority. Arithmetic tolerances are not approved plant solver tolerances.',
        'checks':CHECKS,'measurements':MEASUREMENTS},allow_nan=False))
