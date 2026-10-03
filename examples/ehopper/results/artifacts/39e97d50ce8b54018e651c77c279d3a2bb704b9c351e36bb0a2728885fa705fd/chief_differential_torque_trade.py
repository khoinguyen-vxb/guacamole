"""Preliminary steady differential-reaction-torque (yaw) allocation sensitivity.

Scope: NOT a VerificationResult, Chief selection, dynamic or physical acceptance.
Run with execute: repository=6dof_hopper, workdir=analysis, command
[python, -B, chief_differential_torque_trade.py]. Original repositories and
earlier artifacts remain unchanged.

Revision 2, 2026-10-02, replaces the unexecuted first draft (sha256
980ff690c1ceed1259d38b6d1a45d88038751309d0adc59b6dd55fcaa111c58b). A target
formed as (Q + d) - d can differ from Q by one rounding unit, so the draft's
per-rotor brentq brackets could have equal signs at RPM-domain edges and raise
an uncaught ValueError. Rotor inversion now accepts relative 1e-9 rounding at
the edges and reports genuine domain violations as OutsideEnvelope rejections.

Units are SI except rotor speed in rpm. Axis reaction torque
tau_axis = s0*Q0 + s1*Q1 uses configured reaction_torque_signs [+1, -1].
Rotor index 0 carries the larger configured thrust factor (upper-rotor
convention, to be fixed with CAD). tau_axis acts along the common rotor axis,
tilted from body +z by the phase tilt angle with unspecified azimuth. The
physical sign of the body reaction relative to spin direction must be fixed
with the CAD-to-body frame before simulation.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

from scipy.optimize import brentq

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust')
sys.path.insert(0, str(ROOT))
from pythrust.motors import MotorDatabase  # noqa: E402
from pythrust.propellers import PropellerDatabase  # noqa: E402
from chief_coaxial_model import CoaxialModel, OutsideEnvelope  # noqa: E402

PHASES = ('hover', 'climb', 'reserve')
EDGE_REL_TOL = 1e-9
GRID_STEP_NM = 0.01
GRID_HALF_COUNT = 15  # exploration grid -0.15..+0.15 N m; not a requirement
# Placeholder yaw-demand illustration only; CAD mass properties must replace Izz.
ASSUMED_YAW_INERTIA_KG_M2 = (0.005, 0.01, 0.02)
ASSUMED_YAW_ACCELERATION_RAD_S2 = 2.0


def rotor_domain(model, k):
    return (model.rotor(model.rpm_lo, k)['torque_nm'],
            model.rotor(model.rpm_hi, k)['torque_nm'])


def rpm_for_torque(model, k, torque, domain):
    """Invert monotonic static torque for rotor k; tolerate edge rounding."""
    q_lo, q_hi = domain
    tol = EDGE_REL_TOL * max(abs(q_lo), abs(q_hi))
    if torque < q_lo - tol or torque > q_hi + tol:
        raise OutsideEnvelope('Rotor %d torque target outside RPM domain' % k)
    if torque <= q_lo:
        return model.rpm_lo
    if torque >= q_hi:
        return model.rpm_hi
    return brentq(lambda rpm: model.rotor(rpm, k)['torque_nm'] - torque,
                  model.rpm_lo, model.rpm_hi, xtol=1e-7)


def rotors_at(model, domains, q0, requested_nm):
    # Signs [+1, -1]: tau_axis = Q0 - Q1, therefore Q1 = Q0 - tau_axis.
    torques = (q0, q0 - requested_nm)
    return [model.rotor(rpm_for_torque(model, k, q, domains[k]), k)
            for k, q in enumerate(torques)]


def allocate(model, battery, vertical_n, tilt_deg, requested_nm):
    cfg = model.config
    signs = list(cfg['coaxial']['reaction_torque_signs'])
    if signs != [1, -1]:
        raise ValueError('Allocation assumes reaction_torque_signs [+1, -1]')
    cosine = math.cos(math.radians(tilt_deg))
    if cosine <= 0 or vertical_n <= 0:
        raise ValueError('Positive vertical thrust and tilt below 90 degrees required')
    axial_target = vertical_n / cosine
    domains = [rotor_domain(model, k) for k in range(2)]
    low = max(domains[0][0], domains[1][0] + requested_nm)
    high = min(domains[0][1], domains[1][1] + requested_nm)
    if not low < high:
        raise OutsideEnvelope('No common rotor torque domain for requested differential')

    def residual(q0):
        rotors = rotors_at(model, domains, q0, requested_nm)
        return sum(r['thrust_n'] for r in rotors) - axial_target

    if residual(low) > 0:
        raise OutsideEnvelope('Thrust at lowest common torque exceeds requirement')
    if residual(high) < 0:
        raise OutsideEnvelope('Required thrust unavailable with requested differential')
    q0 = brentq(residual, low, high, xtol=1e-12)
    rotors = rotors_at(model, domains, q0, requested_nm)
    bc = cfg['battery_common']
    limits = cfg['screening_limits']
    voc = battery['cells_series'] * bc['end_of_mission_ocv_cell_v']
    power = sum(r['branch_input_power_w'] for r in rotors) + cfg['mission']['auxiliary_power_w']
    resistance = battery['pack_resistance_ohm']
    discriminant = voc * voc - 4 * resistance * power
    if discriminant <= 0:
        raise OutsideEnvelope('No stable constant-power battery operating point')
    voltage = (voc + math.sqrt(discriminant)) / 2
    current = power / voltage
    for r in rotors:
        r['duty'] = r['branch_voltage_v'] / voltage
        r['esc_input_current_a'] = r['branch_input_power_w'] / voltage
    peak_motor_current = max(r['motor_current_a'] for r in rotors)
    checks = {
        'duty_available': max(r['duty'] for r in rotors) <= 1,
        'motor_current_envelope': peak_motor_current <= model.motor.max_current * limits['motor_catalogue_current_derating'],
        'motor_power_envelope': max(r['motor_power_w'] for r in rotors) <= model.motor.max_power * limits['motor_catalogue_power_derating'],
        'esc_current_envelope': peak_motor_current <= limits['esc_continuous_current_a_assumed'] * limits['esc_current_derating'],
        'esc_voltage_envelope': battery['cells_series'] * bc['full_cell_voltage_v'] <= limits['esc_maximum_voltage_v_assumed'],
        'battery_current_envelope': current <= battery['continuous_current_a'] * limits['battery_current_derating'],
        'battery_loaded_voltage': voltage >= battery['cells_series'] * bc['minimum_loaded_cell_voltage_v']}
    achieved = signs[0] * rotors[0]['torque_nm'] + signs[1] * rotors[1]['torque_nm']
    axial_thrust = sum(r['thrust_n'] for r in rotors)
    return dict(
        rotors=rotors,
        achieved_axis_reaction_nm=achieved,
        torque_residual_nm=achieved - requested_nm,
        reaction_body_z_component_nm=achieved * cosine,
        reaction_transverse_component_magnitude_nm=abs(achieved) * math.sin(math.radians(tilt_deg)),
        axial_thrust_n=axial_thrust,
        vertical_thrust_n=axial_thrust * cosine,
        thrust_residual_n=axial_thrust * cosine - vertical_n,
        rpm_difference_rotor0_minus_rotor1=rotors[0]['rpm'] - rotors[1]['rpm'],
        battery_voltage_v=voltage,
        battery_current_a=current,
        delivered_power_w=power,
        battery_internal_loss_w=current * current * resistance,
        assumed_envelope_checks=checks,
        within_assumed_envelope=all(checks.values()))


def contiguous_about_zero(grid, flags):
    """Sampled contiguous feasible interval containing zero, else None."""
    zero = grid.index(0.0)
    if not flags[zero]:
        return None
    lo = hi = zero
    while lo > 0 and flags[lo - 1]:
        lo -= 1
    while hi < len(grid) - 1 and flags[hi + 1]:
        hi += 1
    return [grid[lo], grid[hi]]


def summarize(index, old, phase, grid, subset):
    flags = [row['within_assumed_envelope'] for row in subset]
    interval = contiguous_about_zero(grid, flags)
    zero_row = subset[grid.index(0.0)]
    trim = mismatch = None
    if 'rotors' in zero_row:
        trim = [r['rpm'] for r in zero_row['rotors']]
        mismatch = max(abs(a - b['rpm']) for a, b in zip(trim, old[phase]['rotors']))
    reasons = {}
    for row in subset:
        labels = list(row.get('failed_checks', []))
        if 'rejection' in row:
            labels.append(row['rejection'])
        for label in labels:
            reasons[label] = reasons.get(label, 0) + 1
    return dict(
        source_case=index, phase=phase,
        baseline_conditional_pass=old['conditional_screening_feasible'],
        pack_resistance_ohm=old['pack_resistance_ohm'],
        thrust_factors=old['thrust_factors'],
        torque_factors=old['torque_factors'],
        additional_mass_kg=old['additional_mass_kg'],
        feasible_sampled_axis_torques_nm=[g for g, f in zip(grid, flags) if f],
        contiguous_feasible_interval_nm=interval,
        symmetric_sampled_authority_nm=None if interval is None else min(abs(interval[0]), abs(interval[1])),
        interval_reaches_grid_edge=None if interval is None else (interval[0] == grid[0] or interval[1] == grid[-1]),
        zero_request_trim_rpm=trim,
        zero_request_rpm_mismatch_vs_source=mismatch,
        limiting_reason_counts=reasons)


def aggregate(summaries):
    result = {}
    subsets = (('all_cases', lambda s: True),
               ('baseline_conditional_pass', lambda s: s['baseline_conditional_pass']))
    for phase in PHASES:
        result[phase] = {}
        for name, keep in subsets:
            items = [s for s in summaries if s['phase'] == phase and keep(s)]
            numeric = [s for s in items if s['symmetric_sampled_authority_nm'] is not None]
            worst = min(numeric, key=lambda s: s['symmetric_sampled_authority_nm']) if numeric else None
            result[phase][name] = dict(
                case_count=len(items),
                zero_request_infeasible_count=len(items) - len(numeric),
                minimum_symmetric_sampled_authority_nm=None if worst is None else worst['symmetric_sampled_authority_nm'],
                worst_source_case=None if worst is None else worst['source_case'],
                worst_contiguous_interval_nm=None if worst is None else worst['contiguous_feasible_interval_nm'])
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source = HERE / 'chief_40a_esc_candidate_screening.json'
    prior = json.loads(source.read_text())
    cfg = prior['effective_configuration']
    motors = MotorDatabase()
    motors.load(ROOT / 'data/motors')
    matches = [m for m in motors.search(min_kv=899, max_kv=901) if m.id == prior['motor_id']]
    if len(matches) != 1:
        raise ValueError('Expected exactly one matching motor catalogue entry')
    motor = matches[0]
    prop_path = ROOT / 'data/propellers/apc_202602/APC_13x6.5E.json'
    prop = PropellerDatabase().load_entry(prop_path, strict=False)
    if prop is None:
        raise ValueError('Propeller data could not be loaded')
    grid = [round(i * GRID_STEP_NM, 10) for i in range(-GRID_HALF_COUNT, GRID_HALF_COUNT + 1)]
    hover_duty_limit = cfg['screening_limits']['maximum_hover_duty']
    rows, summaries = [], []
    for index, old in enumerate(prior['cases']):
        if 'hover' not in old:
            continue
        model = CoaxialModel(motor, prop, cfg, old['thrust_factors'], old['torque_factors'])
        model.rpm_hi = min(model.rpm_hi, prior['enforced_propeller_limit_rpm'])
        battery = dict(prior['battery_template'], pack_resistance_ohm=old['pack_resistance_ohm'])
        for phase in PHASES:
            point = old[phase]
            subset = []
            for requested in grid:
                row = dict(source_case=index, phase=phase,
                           requested_axis_reaction_nm=requested,
                           baseline_conditional_pass=old['conditional_screening_feasible'])
                try:
                    row.update(allocate(model, battery, point['vertical_thrust_n'],
                                        point['tilt_deg'], requested))
                    if phase == 'hover':
                        checks = row['assumed_envelope_checks']
                        checks['hover_duty'] = max(r['duty'] for r in row['rotors']) <= hover_duty_limit
                        row['within_assumed_envelope'] = all(checks.values())
                    row['failed_checks'] = [k for k, v in row['assumed_envelope_checks'].items() if not v]
                except OutsideEnvelope as error:
                    row.update(within_assumed_envelope=False, rejection=str(error))
                subset.append(row)
                rows.append(row)
            summaries.append(summarize(index, old, phase, grid, subset))
        print('Completed source case %d' % index, file=sys.stderr, flush=True)
    aggregates = aggregate(summaries)
    mismatches = [s['zero_request_rpm_mismatch_vs_source'] for s in summaries
                  if s['zero_request_rpm_mismatch_vs_source'] is not None]
    demand = {str(j): j * ASSUMED_YAW_ACCELERATION_RAD_S2 for j in ASSUMED_YAW_INERTIA_KG_M2}
    motor_path = ROOT / 'data/motors' / (motor.id + '.json')
    csv_path = prop_path.parent / json.loads(prop_path.read_text())['data_csv']
    paths = [source, HERE / 'chief_coaxial_model.py', Path(__file__).resolve(),
             motor_path, prop_path, csv_path]
    output = HERE / 'chief_differential_torque_trade_results.json'
    result = dict(
        status='Preliminary steady allocation sensitivity; not VerificationResult or Chief selection',
        script_revision=2,
        date='2026-10-02',
        source_sha256={str(p): digest(p) for p in paths},
        units=dict(torque='N m', thrust='N', rotor_speed='rpm', voltage='V',
                   current='A', power='W', inertia='kg m2'),
        sign_convention='tau_axis = Q0 - Q1 from reaction_torque_signs [+1, -1]; rotor 0 has the larger configured thrust factor',
        frame='Common rotor axis tilted from body +z by the phase tilt angle; azimuth unspecified',
        requested_axis_reaction_grid_nm=grid,
        illustrative_yaw_demand=dict(
            assumption='tau = Izz * yaw acceleration; Izz values are placeholders pending CAD mass properties',
            yaw_acceleration_rad_s2=ASSUMED_YAW_ACCELERATION_RAD_S2,
            torque_nm_by_assumed_izz_kg_m2=demand),
        maximum_zero_request_rpm_mismatch_vs_source=max(mismatches) if mismatches else None,
        aggregates=aggregates,
        limitations=[
            'Grid extent and spacing are exploration choices, not agreed yaw-authority requirements.',
            'Sampled intervals are not continuous bounds; true limits lie between grid points.',
            'Constant coaxial thrust and torque factors are assumed across RPM splits; interference depends on rotor loading ratio and spacing, so authority far from trim requires calibration.',
            'Steady allocation only: rotor acceleration reaction torque, motor/ESC lag, gyroscopic coupling, gimbal dynamics and attitude response are excluded.',
            'Reaction torque along a tilted rotor axis has a transverse body component; tilt azimuth and gimbal load paths remain unspecified.',
            'Yaw demand uses placeholder inertias and acceleration; replace with CAD-derived Izz and agreed response requirements.',
            'Battery terminal model uses end-of-mission open-circuit voltage and swept resistance, not a validated discharge curve.',
            'Reverse-propeller coefficient equivalence, motor thermal endurance and installed ESC behaviour remain unmeasured.',
            'Auxiliary power and BOM allowances are unchanged from the 40 A screening configuration; servo supply revision remains due.',
            'No procurement, geometry, mission or physical acceptance.'],
        summaries=summaries,
        cases=rows)
    output.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n')
    print(json.dumps(dict(
        scope=result['status'], operating_points=len(rows),
        maximum_zero_request_rpm_mismatch_vs_source=result['maximum_zero_request_rpm_mismatch_vs_source'],
        aggregates=aggregates, illustrative_yaw_demand_nm=demand,
        output=str(output), physical_validation='unperformed')))


if __name__ == '__main__':
    main()
