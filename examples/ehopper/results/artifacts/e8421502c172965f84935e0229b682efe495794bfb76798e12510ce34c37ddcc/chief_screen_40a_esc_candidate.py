"""Conditional preliminary 40 A ESC analysis, not verification or selection.
Run with repository=6dof_hopper and python -B. Original inputs remain unchanged.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust')
sys.path.insert(0, str(ROOT))
from pythrust.motors import MotorDatabase
from pythrust.propellers import PropellerDatabase
from chief_coaxial_model import CoaxialModel, OutsideEnvelope, evaluate_candidate


def main():
    prior_path = HERE / 'chief_documented_candidate_screening.json'
    prior = json.loads(prior_path.read_text())
    cfg = copy.deepcopy(prior['effective_configuration'])
    matches = [x for x in cfg['vehicle_allowances'] if x['item'] == 'ESCs']
    if len(matches) != 1 or matches[0]['quantity'] != 2:
        raise ValueError('Expected one two-ESC BOM entry')
    old_esc = copy.deepcopy(matches[0])
    matches[0].update(unit_mass_kg=0.036, unit_cost_aud=33.77,
        product='Hobbywing Skywalker 40A V2, HW80060022, conditional 3-4S variant',
        price_status='AUD inferred; currency and tax treatment unconfirmed')
    cfg['screening_limits']['esc_continuous_current_a_assumed'] = 40.0
    cfg['screening_limits']['esc_maximum_voltage_v_assumed'] = 16.8
    cfg['status'] = 'Conditional 3-4S ESC alternative; supplier title conflicts with specifications'
    battery_template = copy.deepcopy(prior['battery_template'])
    motors = MotorDatabase()
    motors.load(ROOT / 'data/motors')
    found = [m for m in motors.search(min_kv=899, max_kv=901) if m.id == prior['motor_id']]
    if len(found) != 1:
        raise ValueError('Expected exactly one original-generation motor')
    motor = found[0]
    prop_path = ROOT / 'data/propellers/apc_202602/APC_13x6.5E.json'
    prop = PropellerDatabase().load_entry(prop_path, strict=False)
    if prop is None:
        raise ValueError('Propeller data unavailable')
    rows = []
    for old in prior['cases']:
        identity = {k: old[k] for k in ('pack_resistance_ohm', 'thrust_factors', 'torque_factors', 'additional_mass_kg')}
        battery = dict(battery_template, pack_resistance_ohm=old['pack_resistance_ohm'])
        try:
            model = CoaxialModel(motor, prop, cfg, old['thrust_factors'], old['torque_factors'])
            model.rpm_hi = min(model.rpm_hi, prior['enforced_propeller_limit_rpm'])
            if model.rpm_hi <= model.rpm_lo:
                raise OutsideEnvelope('No RPM domain below propeller limit')
            model.qhi = min(model.rotor(model.rpm_hi, k)['torque_nm'] for k in range(2))
            if model.qhi <= model.qlo:
                raise OutsideEnvelope('No common torque domain')
            row = evaluate_candidate(model, battery, old['additional_mass_kg'])
            row['conditional_screening_feasible'] = row.pop('screening_feasible')
            row['electrical_energy_screening_only'] = all(v for k, v in row['screening_checks'].items() if k != 'cost_estimate_below_ceiling')
            row['failed_checks'] = [k for k, v in row['screening_checks'].items() if not v]
        except OutsideEnvelope as error:
            row = dict(conditional_screening_feasible=False,
                       electrical_energy_screening_only=False, rejection=str(error))
        row.update(identity)
        row.update(procurement_ready=False, physical_validation='unperformed',
                   voltage_compatibility='conditional; supplied 3-4S variant must be confirmed',
                   cost_status='Mixed supplier-informed and hypothetical costs; not verified budget compliance',
                   thermal_acceptance='unperformed',
                   yaw_authority_acceptance='unperformed; equal-torque trim only')
        rows.append(row)
    motor_path = ROOT / 'data/motors' / (motor.id + '.json')
    csv_path = prop_path.parent / json.loads(prop_path.read_text())['data_csv']
    paths = [prior_path, HERE/'chief_coaxial_model.py', motor_path, prop_path, csv_path, Path(__file__)]
    result = dict(
        status='Conditional preliminary analysis, not VerificationResult or Chief selection',
        supplier_access_date='2026-10-01',
        supplier_source='https://ultimatehobbies.com.au/products/skywalker-40amp-v2-econo-air-esc-2-3s',
        supplier_section='Price/stock and Specifications',
        supplier_esc=dict(identifier='HW80060022', price_each=33.77,
            currency='AUD inferred, unconfirmed', tax_treatment='unknown; no deduction applied',
            mass_g=36, dimensions_mm=[60,25,8], continuous_current_a=40,
            cells_series_conditional=[3,4],
            conflict='Title says 2-3S; specification table says 3-4S',
            availability='Listed in stock with warehouse/store caveat; quantity unconfirmed'),
        previous_esc_allowance=old_esc, effective_configuration=cfg,
        battery_template=battery_template, motor_id=motor.id,
        enforced_propeller_limit_rpm=prior['enforced_propeller_limit_rpm'],
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        cases=rows,
        limitations=[
            'Assumed 4S compatibility is not resolved by numerical screening.',
            '0.8 ESC derating is a screening assumption, not installed thermal evidence.',
            'Motor 40 A rating is limited to 30 seconds; continuous endurance unvalidated.',
            'Battery resistance cases are not validated end-of-mission bounds.',
            'Remaining BOM prices and structural masses retain provisional allowances.',
            'No differential-yaw allocation, mission dynamics or physical acceptance evaluated.',
            'Do not parallel BEC outputs without manufacturer authorization.'])
    output = HERE / 'chief_40a_esc_candidate_screening.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(scope=result['status'], cases=len(rows),
        conditional_passes=sum(r['conditional_screening_feasible'] for r in rows),
        electrical_energy_only_passes=sum(r['electrical_energy_screening_only'] for r in rows),
        output=str(output), physical_acceptance='unperformed')))


if __name__ == '__main__':
    main()
