"""Preliminary steady allocation sensitivity, NOT verification or selection.
Run with repository=6dof_hopper, python -B. Original inputs remain unchanged.
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
from pythrust.motors import MotorDatabase
from pythrust.propellers import PropellerDatabase
from chief_coaxial_model import CoaxialModel, OutsideEnvelope


def allocate(model, battery, vertical_n, tilt_deg, requested_nm):
    cfg = model.config
    if cfg['coaxial']['reaction_torque_signs'] != [1, -1]:
        raise ValueError('This allocation requires explicit +1,-1 reaction signs')
    cosine = math.cos(math.radians(tilt_deg))
    target = vertical_n / cosine
    bounds = [(model.rotor(model.rpm_lo, k)['torque_nm'],
               model.rotor(model.rpm_hi, k)['torque_nm']) for k in range(2)]
    # Q1-Q2=requested_nm. Intersect the individual rotor domains.
    low = max(bounds[0][0], bounds[1][0] + requested_nm)
    high = min(bounds[0][1], bounds[1][1] + requested_nm)
    if low >= high:
        raise OutsideEnvelope('No overlapping torque domain')

    def rotors_at(q1):
        rotors = []
        for k, torque in enumerate((q1, q1-requested_nm)):
            rpm = brentq(lambda r: model.rotor(r, k)['torque_nm']-torque,
                         model.rpm_lo, model.rpm_hi, xtol=1e-7)
            rotors.append(model.rotor(rpm, k))
        return rotors

    def residual(q1):
        return sum(r['thrust_n'] for r in rotors_at(q1))-target

    if residual(low) > 0 or residual(high) < 0:
        raise OutsideEnvelope('Required simultaneous thrust/torque outside RPM domain')
    q1 = brentq(residual, low, high, xtol=1e-10)
    rotors = rotors_at(q1)
    bc, limits = cfg['battery_common'], cfg['screening_limits']
    voc = battery['cells_series']*bc['end_of_mission_ocv_cell_v']
    power = sum(r['branch_input_power_w'] for r in rotors)+cfg['mission']['auxiliary_power_w']
    resistance = battery['pack_resistance_ohm']
    discriminant = voc*voc-4*resistance*power
    if discriminant <= 0:
        raise OutsideEnvelope('No stable constant-power battery solution')
    voltage = (voc+math.sqrt(discriminant))/2
    current = power/voltage
    for r in rotors:
        r['duty'] = r['branch_voltage_v']/voltage
        r['esc_input_current_a'] = r['branch_input_power_w']/voltage
    checks = {
        'duty_available': max(r['duty'] for r in rotors) <= 1,
        'motor_current': max(r['motor_current_a'] for r in rotors) <= model.motor.max_current*limits['motor_catalogue_current_derating'],
        'motor_power': max(r['motor_power_w'] for r in rotors) <= model.motor.max_power*limits['motor_catalogue_power_derating'],
        'esc_current': max(r['motor_current_a'] for r in rotors) <= limits['esc_continuous_current_a_assumed']*limits['esc_current_derating'],
        'esc_voltage': battery['cells_series']*bc['full_cell_voltage_v'] <= limits['esc_maximum_voltage_v_assumed'],
        'battery_current': current <= battery['continuous_current_a']*limits['battery_current_derating'],
        'battery_loaded_voltage': voltage >= battery['cells_series']*bc['minimum_loaded_cell_voltage_v']}
    achieved = rotors[0]['torque_nm']-rotors[1]['torque_nm']
    return dict(rotors=rotors, requested_axis_reaction_nm=requested_nm,
                achieved_axis_reaction_nm=achieved,
                reaction_body_z_projection_nm=achieved*cosine,
                reaction_transverse_magnitude_nm=abs(achieved)*math.sin(math.radians(tilt_deg)),
                vertical_thrust_n=sum(r['thrust_n'] for r in rotors)*cosine,
                thrust_residual_n=sum(r['thrust_n'] for r in rotors)*cosine-vertical_n,
                torque_residual_nm=achieved-requested_nm,
                battery_voltage_v=voltage, battery_current_a=current,
                delivered_power_w=power, battery_internal_loss_w=current*current*resistance,
                assumed_envelope_checks=checks, within_assumed_envelope=all(checks.values()))


def main():
    source = HERE/'chief_40a_esc_candidate_screening.json'
    prior = json.loads(source.read_text())
    cfg = prior['effective_configuration']
    motors = MotorDatabase()
    motors.load(ROOT/'data/motors')
    matches = [m for m in motors.search(min_kv=899, max_kv=901) if m.id == prior['motor_id']]
    if len(matches) != 1:
        raise ValueError('Expected one matching motor')
    motor = matches[0]
    prop_path = ROOT/'data/propellers/apc_202602/APC_13x6.5E.json'
    prop = PropellerDatabase().load_entry(prop_path, strict=False)
    if prop is None:
        raise ValueError('Missing propeller data')
    requests = [i*0.01 for i in range(-10, 11)]
    rows, summaries = [], []
    for index, old in enumerate(prior['cases']):
        if 'hover' not in old:
            continue
        model = CoaxialModel(motor, prop, cfg, old['thrust_factors'], old['torque_factors'])
        model.rpm_hi = min(model.rpm_hi, prior['enforced_propeller_limit_rpm'])
        battery = dict(prior['battery_template'], pack_resistance_ohm=old['pack_resistance_ohm'])
        for phase in ('hover', 'climb', 'reserve'):
            point = old[phase]
            subset = []
            for requested in requests:
                row = dict(source_case=index, phase=phase,
                           requested_axis_reaction_nm=requested,
                           baseline_conditional_pass=old['conditional_screening_feasible'])
                try:
                    row.update(allocate(model, battery, point['vertical_thrust_n'], point['tilt_deg'], requested))
                    if phase == 'hover':
                        row['assumed_envelope_checks']['hover_duty'] = max(r['duty'] for r in row['rotors']) <= cfg['screening_limits']['maximum_hover_duty']
                        row['within_assumed_envelope'] = all(row['assumed_envelope_checks'].values())
                except OutsideEnvelope as error:
                    row.update(within_assumed_envelope=False, rejection=str(error))
                subset.append(row)
                rows.append(row)
            feasible = [r['requested_axis_reaction_nm'] for r in subset if r['within_assumed_envelope']]
            summaries.append(dict(source_case=index, phase=phase,
                feasible_sampled_axis_torques_nm=feasible,
                zero_torque_feasible=0.0 in feasible,
                sampled_min_nm=min(feasible) if feasible else None,
                sampled_max_nm=max(feasible) if feasible else None,
                note='Sampled points only; not continuous bounds or dynamic acceptance'))
        print('Completed source case '+str(index), file=sys.stderr, flush=True)
    paths = [source, HERE/'chief_coaxial_model.py', Path(__file__),
             ROOT/'data/motors'/(motor.id+'.json'), prop_path,
             prop_path.parent/json.loads(prop_path.read_text())['data_csv']]
    output = HERE/'chief_differential_torque_trade_results.json'
    result = dict(status='Preliminary steady allocation sensitivity; not VerificationResult',
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        requested_axis_reaction_grid_nm=requests, cases=rows, summaries=summaries,
        frame='Common rotor axis tilted from body +z by the phase tilt angle; azimuth unspecified',
        limitations=[
            'Grid extent and spacing are exploration choices, not agreed yaw requirements.',
            'No dynamic rotor acceleration, gyroscopic, gimbal or attitude response evaluated.',
            'Steady reaction torque along tilted axis also has transverse components.',
            'Original auxiliary-power and component allowances retained; servo supply/BOM revision remains due.',
            'Coaxial factors, reverse-propeller equivalence, battery sag and thermal limits remain provisional.',
            'No procurement, geometry, mission or physical acceptance.'])
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(scope=result['status'], operating_points=len(rows), output=str(output))))


if __name__ == '__main__':
    main()
