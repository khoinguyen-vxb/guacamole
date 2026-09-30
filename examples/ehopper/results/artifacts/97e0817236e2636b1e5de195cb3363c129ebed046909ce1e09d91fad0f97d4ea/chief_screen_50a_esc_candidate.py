"""Preliminary ESC alternative analysis, not verification or selection.
Preserves prior artifacts. Run with the 6dof_hopper backend and python -B.
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
    matches = [item for item in cfg['vehicle_allowances'] if item['item'] == 'ESCs']
    if len(matches) != 1 or matches[0]['quantity'] != 2:
        raise ValueError('Expected one two-ESC BOM entry')
    old_esc = copy.deepcopy(matches[0])
    matches[0].update(unit_mass_kg=0.036, unit_cost_aud=51.29,
                      product='Hobbywing Skywalker 50A V2 3-4S, HW80060442',
                      price_status='AUD inferred from Australian storefront; tax treatment unconfirmed')
    cfg['screening_limits']['esc_continuous_current_a_assumed'] = 50.0
    cfg['screening_limits']['esc_maximum_voltage_v_assumed'] = 16.8
    cfg['status'] = 'Supplier-informed ESC alternative; remaining assumptions retained; not procurement approval'
    battery_template = copy.deepcopy(prior['battery_template'])
    motors = MotorDatabase()
    motors.load(ROOT / 'data/motors')
    found = [m for m in motors.search(min_kv=899, max_kv=901) if m.id == prior['motor_id']]
    if len(found) != 1:
        raise ValueError('Expected exactly one matching original-generation motor')
    motor = found[0]
    prop_path = ROOT / 'data/propellers/apc_202602/APC_13x6.5E.json'
    prop = PropellerDatabase().load_entry(prop_path, strict=False)
    if prop is None:
        raise ValueError('Propeller data could not be loaded')
    rows = []
    for old in prior['cases']:
        battery = dict(battery_template, pack_resistance_ohm=old['pack_resistance_ohm'])
        identity = {k: old[k] for k in ('pack_resistance_ohm', 'thrust_factors', 'torque_factors', 'additional_mass_kg')}
        try:
            model = CoaxialModel(motor, prop, cfg, old['thrust_factors'], old['torque_factors'])
            model.rpm_hi = min(model.rpm_hi, prior['enforced_propeller_limit_rpm'])
            if model.rpm_hi <= model.rpm_lo:
                raise OutsideEnvelope('No domain below propeller RPM limit')
            model.qhi = min(model.rotor(model.rpm_hi, k)['torque_nm'] for k in range(2))
            if model.qhi <= model.qlo:
                raise OutsideEnvelope('No common torque domain below propeller RPM limit')
            row = evaluate_candidate(model, battery, old['additional_mass_kg'])
            row['conditional_screening_feasible'] = row.pop('screening_feasible')
            row['electrical_energy_screening_only'] = all(value for key, value in row['screening_checks'].items() if key != 'cost_estimate_below_ceiling')
            row['failed_checks'] = [key for key, value in row['screening_checks'].items() if not value]
            row['cost_status'] = 'Mixed supplier-informed and hypothetical prices; AUD inference unconfirmed; not verified budget compliance'
            row['thermal_acceptance'] = 'unperformed'
            row['yaw_authority_acceptance'] = 'unperformed; equal-torque trim only'
        except OutsideEnvelope as error:
            row = dict(conditional_screening_feasible=False, electrical_energy_screening_only=False,
                       rejection=str(error), procurement_ready=False, physical_validation='unperformed')
        row.update(identity)
        rows.append(row)
    motor_path = ROOT / 'data/motors' / (motor.id + '.json')
    csv_path = prop_path.parent / json.loads(prop_path.read_text())['data_csv']
    paths = [prior_path, HERE/'chief_coaxial_model.py', motor_path, prop_path, csv_path, Path(__file__)]
    result = dict(
        status='Preliminary alternative analysis; not VerificationResult or Chief selection',
        supplier_access_date='2026-10-01',
        supplier_source='https://ultimatehobbies.com.au/products/hobbywing-skywalker-v2-50a-3-4s-5a-bec',
        supplier_section='Price/stock and Specifications',
        supplier_esc=dict(identifier='HW80060442', price_each=51.29, currency='AUD inferred, unconfirmed',
                          tax_treatment='unknown; no deduction applied', mass_g=36,
                          dimensions_mm=[60,25,8], cells_series=[3,4], continuous_current_a=50,
                          availability='Listed in stock with warehouse/store caveat; quantity not confirmed'),
        previous_esc_allowance=old_esc,
        effective_configuration=cfg, battery_template=battery_template,
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        cases=rows,
        limitations=[
            'The 0.8 ESC derating remains a screening assumption, not installed thermal evidence.',
            'Motor 40 A rating is 30-second limited; continuous hover capability remains unvalidated.',
            'Battery resistance sensitivity does not establish end-of-mission sag bounds.',
            'Remaining BOM costs and structural masses remain allowances.',
            'No differential-yaw allocation, mission dynamics or physical acceptance is evaluated.',
            'Do not parallel ESC BEC outputs without manufacturer authorization.'])
    output = HERE / 'chief_50a_esc_candidate_screening.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(scope=result['status'], cases=len(rows),
        conditional_passes=sum(r['conditional_screening_feasible'] for r in rows),
        electrical_energy_only_passes=sum(r['electrical_energy_screening_only'] for r in rows),
        output=str(output), physical_acceptance='unperformed')))


if __name__ == '__main__':
    main()
