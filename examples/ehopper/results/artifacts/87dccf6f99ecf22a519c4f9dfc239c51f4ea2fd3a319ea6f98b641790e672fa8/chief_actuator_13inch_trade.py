"""Preliminary actuator load sensitivity; not verification or selection.
Run with python -B. Preserves preceding artifacts and original repositories.
"""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    source = HERE / 'chief_40a_esc_candidate_screening.json'
    data = json.loads(source.read_text())
    cfg = data['effective_configuration']
    props = [x for x in cfg['vehicle_allowances'] if x['item'] == 'Matched CW/CCW propellers']
    if len(props) != 1 or props[0]['quantity'] != 2:
        raise ValueError('Expected explicit two-propeller mass ownership')
    prop_mass = props[0]['unit_mass_kg']
    radius = 13 * 0.0254 / 2
    assumptions = dict(
        scope='13-inch comparison candidate only; no accepted hardware baseline',
        motor_mass_each_kg=0.108,
        moving_bracket_bearing_wiring_mass_kg=0.100,
        moving_cg_offset_m=0.030,
        thrust_line_offset_m=0.005,
        moving_transverse_inertia_kg_m2=0.006,
        additional_motor_rotating_inertia_each_kg_m2_cases=[0.0, 0.00002, 0.00005],
        pivot_to_vehicle_cg_m_cases=[0.15, 0.25, 0.35],
        tilt_cone_deg=12.0,
        tilt_rate_rad_s=1.0,
        tilt_acceleration_rad_s2=8.0,
        friction_torque_nm=0.05,
        output_angle_per_servo_angle=0.5,
        linkage_efficiency=0.70,
        torque_margin_factor=2.0)
    a = assumptions
    moving_mass = 2*a['motor_mass_each_kg'] + 2*prop_mass + a['moving_bracket_bearing_wiring_mass_kg']
    angle = math.radians(a['tilt_cone_deg'])
    results = []
    for index, row in enumerate(data['cases']):
        if 'hover' not in row:
            continue
        for phase in ('hover', 'climb', 'reserve'):
            op = row[phase]
            thrust = sum(r['thrust_n'] for r in op['rotors'])
            for motor_j in a['additional_motor_rotating_inertia_each_kg_m2_cases']:
                # Tip-lumped propeller inertia is a conservative geometric envelope.
                # Motor inertia values are sensitivities, NOT validated bounds.
                rotor_j = prop_mass*radius**2 + motor_j
                momenta = [rotor_j*r['rpm']*math.pi/30 for r in op['rotors']]
                terms = dict(
                    thrust_offset=thrust*a['thrust_line_offset_m'],
                    gravity=moving_mass*cfg['gravity_m_s2']*a['moving_cg_offset_m'],
                    acceleration=a['moving_transverse_inertia_kg_m2']*a['tilt_acceleration_rad_s2'],
                    friction=a['friction_torque_nm'],
                    gyro_sum_envelope=sum(abs(h) for h in momenta)*a['tilt_rate_rad_s'])
                pivot_load = sum(terms.values())
                servo_load = pivot_load*a['output_angle_per_servo_angle']/a['linkage_efficiency']*a['torque_margin_factor']
                results.append(dict(
                    source_case=index, phase=phase,
                    conditional_propulsion_screen_pass=row['conditional_screening_feasible'],
                    phase_within_assumed_electrical_envelope=op['within_assumed_envelope'],
                    motor_rotating_inertia_each_kg_m2=motor_j,
                    total_thrust_n=thrust,
                    vertical_thrust_at_tilt_limit_n=thrust*math.cos(angle),
                    transverse_vehicle_moment_nm_by_arm={str(arm):arm*thrust*math.sin(angle) for arm in a['pivot_to_vehicle_cg_m_cases']},
                    pivot_load_terms_nm=terms,
                    required_servo_torque_nm_with_margin=servo_load,
                    required_servo_speed_rad_s=a['tilt_rate_rad_s']/a['output_angle_per_servo_angle'],
                    required_servo_travel_each_side_deg=a['tilt_cone_deg']/a['output_angle_per_servo_angle'],
                    ideal_signed_gyro_magnitude_nm=abs(sum(s*h for s,h in zip(cfg['coaxial']['reaction_torque_signs'], momenta)))*a['tilt_rate_rad_s']))
    if not results:
        raise ValueError('No operating points available')
    output = HERE / 'chief_actuator_13inch_trade_results.json'
    result = dict(status='Preliminary sensitivity only; not VerificationResult',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        assumptions=assumptions, moving_mass_kg=moving_mass,
        propeller_mass_each_kg=prop_mass, rotor_radius_m=radius,
        cases=results,
        limitations=[
            'Old 20-inch actuator results are not transferred to this candidate.',
            'Moving bracket mass is a subset requiring reconciliation with the whole-vehicle BOM, not an additional accepted mass.',
            'Moving transverse inertia and motor rotating inertia require CAD or measurement.',
            'Sum-of-magnitudes gyro estimate deliberately avoids assuming cancellation; aerodynamic tilt moments are omitted.',
            'Full-travel rotor clearance, bearing loads, structural strength and linkage singularities are not evaluated.',
            'Servo torque and speed must be met simultaneously; stall torque is not a continuous rating.',
            'Electrical supply and auxiliary-energy allowances require revision after servo selection.',
            'Differential yaw authority still requires constrained allocation analysis.',
            'No hardware acceptance, procurement approval or physical tests.'])
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(scope=result['status'], calculated_load_cases=len(results),
        moving_mass_kg=moving_mass, output=str(output), physical_validation='unperformed')))


if __name__ == '__main__':
    main()
