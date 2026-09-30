"""Verify preliminary actuator arithmetic from actual saved inputs.
Print only VerificationResult JSON; no hardware acceptance is implied.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main():
    checks = {}
    try:
        source = HERE / 'chief_propulsion_search_results.json'
        search = json.loads(source.read_text())
        trade = json.loads((HERE / 'chief_actuator_trade_results.json').read_text())
        checks['propulsion_input_hash_matches'] = (
            hashlib.sha256(source.read_bytes()).hexdigest() == trade['input_sha256'])
        for field, filename in (
            ('configuration_sha256', 'chief_propulsion_screening_config.json'),
            ('model_sha256', 'chief_coaxial_model.py'),
            ('driver_sha256', 'chief_screen_propulsion.py')):
            checks[field] = hashlib.sha256((HERE / filename).read_bytes()).hexdigest() == search[field]
        rows = [r for r in search['ranked_nominal_feasible']
                if r['motor_id'] == 'Team_Hunter_RC_Squid_4008M-KV390'
                and r['propeller_id'] == 'APC_20x8E'
                and r['battery_id'] == 'assumed_4S_3000']
        checks['unique_reference'] = len(rows) == 1
        if len(rows) != 1:
            raise ValueError('Expected exactly one propulsion reference')
        reference = rows[0]
        a = trade['assumptions']
        angle = math.radians(a['total_vector_tilt_limit_deg'])
        rotor_inertia = a['each_propeller_mass_kg'] * a['rotor_radius_m']**2
        def close(actual, expected):
            return math.isfinite(actual) and math.isfinite(expected) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-10)
        cases = trade['gimbal_cases']
        checks['phase_coverage'] = sorted(c['phase'] for c in cases) == ['hover', 'reserve']
        for case in cases:
            phase = case['phase']
            op = reference[phase]
            thrust = sum(r['thrust_n'] for r in op['rotors'])
            transverse = thrust * math.sin(angle)
            expected_terms = {
                'thrust_offset': thrust * a['thrust_line_offset_from_pivot_m'],
                'gravity': a['moving_assembly_mass_kg'] * a['gravity_m_s2'] * a['moving_cg_offset_from_pivot_m'],
                'acceleration': a['moving_transverse_inertia_kg_m2'] * a['tilt_acceleration_rad_s2'],
                'friction': a['friction_torque_nm'],
                'gyroscopic_envelope': sum(rotor_inertia * r['rpm'] * math.pi / 30 for r in op['rotors']) * a['tilt_rate_rad_s']}
            checks[phase + '_forces'] = all((
                close(case['total_thrust_n'], thrust),
                close(case['transverse_force_n'], transverse),
                close(case['vertical_force_at_limit_n'], thrust * math.cos(angle))))
            checks[phase + '_vehicle_moments'] = all(
                close(case['vehicle_moment_nm_by_arm'][str(arm)], arm * transverse)
                for arm in a['pivot_to_vehicle_cg_m_cases'])
            checks[phase + '_pivot_load_terms'] = all(
                close(case['pivot_load_terms_nm'][key], value) for key, value in expected_terms.items())
            torque = sum(expected_terms.values()) * a['linkage_output_angle_per_servo_angle'] / a['linkage_efficiency'] * a['actuator_torque_margin_factor']
            checks[phase + '_servo_requirements'] = all((
                close(case['required_servo_torque_nm_with_margin'], torque),
                close(case['required_servo_speed_rad_s'], a['tilt_rate_rad_s'] / a['linkage_output_angle_per_servo_angle']),
                close(case['required_servo_travel_each_side_deg'], a['total_vector_tilt_limit_deg'] / a['linkage_output_angle_per_servo_angle'])))
        passed = all(checks.values())
        checks['physical_actuator_acceptance'] = None
        result = {'outcome': 'passed' if passed else 'failed', 'checks': checks,
                  'explanation': 'Checks cover saved-input provenance and preliminary actuator arithmetic only. They do not validate the propulsion model, assumed loads, geometry, servo selection, continuous thermal capability or flight performance. Physical actuator acceptance remains unperformed.'}
    except Exception as error:
        print(str(error), file=sys.stderr)
        checks['verification_completed'] = False
        result = {'outcome': 'failed', 'checks': checks,
                  'explanation': 'Could not complete verification against the actual saved inputs; inspect stderr. No physical acceptance.'}
    print(json.dumps(result, allow_nan=False))

if __name__ == '__main__':
    main()
