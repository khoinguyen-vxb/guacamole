"""Preliminary actuator trade; no hardware or geometry acceptance.
Run Python -B from results/analysis. Original sources remain unchanged.
"""
import json
import math
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main():
    source = HERE / 'chief_propulsion_search_results.json'
    data = json.loads(source.read_text())
    rows = [r for r in data['ranked_nominal_feasible']
            if r['motor_id'] == 'Team_Hunter_RC_Squid_4008M-KV390'
            and r['propeller_id'] == 'APC_20x8E'
            and r['battery_id'] == 'assumed_4S_3000']
    if len(rows) != 1:
        raise ValueError('Expected exactly one selected nominal reference')
    reference = rows[0]
    assumptions = dict(
        pivot_to_vehicle_cg_m_cases=[0.15, 0.25, 0.35],
        total_vector_tilt_limit_deg=12,
        moving_assembly_mass_kg=0.35,
        moving_cg_offset_from_pivot_m=0.03,
        thrust_line_offset_from_pivot_m=0.005,
        moving_transverse_inertia_kg_m2=0.006,
        tilt_acceleration_rad_s2=8.0,
        tilt_rate_rad_s=1.0,
        friction_torque_nm=0.05,
        rotor_radius_m=0.254,
        each_propeller_mass_kg=0.030,
        linkage_output_angle_per_servo_angle=0.5,
        linkage_efficiency=0.70,
        actuator_torque_margin_factor=2.0,
        gravity_m_s2=9.80665,
        servo_lag_s_cases=[0.05, 0.10, 0.20])
    a = assumptions
    angle = math.radians(a['total_vector_tilt_limit_deg'])
    # Deliberately conservative inertia envelope: each propeller mass at tip.
    # Motor rotating inertia is missing and must be added before acceptance.
    rotor_inertia = a['each_propeller_mass_kg'] * a['rotor_radius_m']**2
    cases = []
    for phase in ('hover', 'reserve'):
        op = reference[phase]
        thrust = sum(r['thrust_n'] for r in op['rotors'])
        momenta = [rotor_inertia*r['rpm']*math.pi/30 for r in op['rotors']]
        # Sum magnitudes rather than assuming perfect gyroscopic cancellation.
        gyro_bound = sum(momenta)*a['tilt_rate_rad_s']
        load_terms = dict(
            thrust_offset=thrust*a['thrust_line_offset_from_pivot_m'],
            gravity=a['moving_assembly_mass_kg']*a['gravity_m_s2']*a['moving_cg_offset_from_pivot_m'],
            acceleration=a['moving_transverse_inertia_kg_m2']*a['tilt_acceleration_rad_s2'],
            friction=a['friction_torque_nm'], gyroscopic_envelope=gyro_bound)
        pivot_torque = sum(load_terms.values())
        servo_torque = (pivot_torque*a['linkage_output_angle_per_servo_angle']
                        /a['linkage_efficiency']*a['actuator_torque_margin_factor'])
        cases.append(dict(
            phase=phase, total_thrust_n=thrust,
            transverse_force_n=thrust*math.sin(angle),
            vertical_force_at_limit_n=thrust*math.cos(angle),
            vehicle_moment_nm_by_arm={str(arm):arm*thrust*math.sin(angle)
                for arm in a['pivot_to_vehicle_cg_m']}
            if 'pivot_to_vehicle_cg_m' in a else
            {str(arm):arm*thrust*math.sin(angle)
                for arm in a['pivot_to_vehicle_cg_m_cases']},
            pivot_load_terms_nm=load_terms,
            required_servo_torque_nm_with_margin=servo_torque,
            required_servo_speed_rad_s=a['tilt_rate_rad_s']/a['linkage_output_angle_per_servo_angle'],
            required_servo_travel_each_side_deg=a['total_vector_tilt_limit_deg']/a['linkage_output_angle_per_servo_angle']))
    result = dict(
        status='Preliminary calculation only; Chief mechanism selection pending',
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        assumptions=assumptions, gimbal_cases=cases,
        alternatives=[
            {'mechanism':'Two-axis gimbal carrying both coaxial rotors',
             'assessment':'Direct transverse thrust authority; requires nonzero pivot-to-CG arm, bearings, two servos and full-travel clearance checks.'},
            {'mechanism':'Fixed coaxial rotors with slipstream vanes',
             'assessment':'Potentially lower moving inertia, but vane force, drag, stall and wake distribution lack data; authority cannot presently be quantified.'}],
        limitations=[
            'Loads are conservative preliminary envelopes, not multibody dynamics or structural verification.',
            'Rotor gyroscopic estimate omits motor rotating inertia and aerodynamic tilt moments.',
            'Servo stall torque is not continuous torque; no commercial servo selected.',
            'Total tilt cone is 12 degrees, not independent simultaneous 12-degree axis limits.',
            'Differential reaction torque must supply axial attitude control; its available authority still needs a constrained numerical allocation study.',
            'Mass, power and cost allowances must be reconciled after mechanism selection.',
            'No physical tests performed.'])
    output = HERE / 'chief_actuator_trade_results.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result, indent=2, allow_nan=False))

if __name__ == '__main__':
    main()
