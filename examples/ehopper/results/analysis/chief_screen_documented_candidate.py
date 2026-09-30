"""Preliminary candidate sensitivity analysis; not verification or selection.
Run with the 6dof_hopper backend using python -B from results/analysis.
Retains existing screening inputs unchanged. All costs remain assumptions.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust')
sys.path.insert(0, str(ROOT))
from pythrust.motors import MotorDatabase
from pythrust.propellers import PropellerDatabase
from chief_coaxial_model import CoaxialModel, OutsideEnvelope, evaluate_candidate

HERE = Path(__file__).resolve().parent
MOTOR_ID = 'SunnySky_X2814_KV900_3-4S'
PROP_ID = 'APC_13x6.5E'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config_path = HERE / 'chief_propulsion_screening_config.json'
    cfg = copy.deepcopy(json.loads(config_path.read_text()))
    for item in cfg['vehicle_allowances']:
        if item['item'] == 'Matched CW/CCW propellers':
            item['unit_mass_kg'] = 1.06 * 28.349523125 / 1000
    motors = MotorDatabase()
    motors.load(ROOT / 'data/motors')
    matches = [m for m in motors.search(min_kv=899, max_kv=901) if m.id == MOTOR_ID]
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one non-V3 X2814-900 catalogue entry')
    motor = matches[0]
    prop_path = ROOT / 'data/propellers/apc_202602' / (PROP_ID + '.json')
    db = PropellerDatabase()
    prop = db.load_entry(prop_path, strict=False)
    if prop is None:
        raise RuntimeError('Propeller data failed to load')
    battery_template = copy.deepcopy(next(b for b in cfg['battery_alternatives'] if b['id'] == 'assumed_4S_4000'))
    battery_template.update(id='Graphene_9067000412_0_provisional', mass_kg=0.419,
                            cells_series=4, capacity_ah=4.0)
    # Keep assumed 60 A screening ceiling, not the advertised 100C rating.
    # Keep old AUD allowance visibly hypothetical; no currency conversion invented.
    rows = []
    rpm_limit = 150000.0 / 13.0
    for resistance in (0.012, 0.035, 0.060):
        battery = dict(battery_template, pack_resistance_ohm=resistance)
        for tf in cfg['coaxial']['per_rotor_thrust_factors']:
            for qf in cfg['coaxial']['per_rotor_torque_factors']:
                for extra_mass in (0.0, 0.15, 0.30):
                    identity = dict(pack_resistance_ohm=resistance, thrust_factors=tf,
                                    torque_factors=qf, additional_mass_kg=extra_mass)
                    try:
                        model = CoaxialModel(motor, prop, cfg, tf, qf)
                        model.rpm_hi = min(model.rpm_hi, rpm_limit)
                        if model.rpm_hi <= model.rpm_lo:
                            raise OutsideEnvelope('No domain below supplier RPM limit')
                        model.qhi = min(model.rotor(model.rpm_hi, k)['torque_nm'] for k in range(2))
                        if model.qhi <= model.qlo:
                            raise OutsideEnvelope('No common torque domain below RPM limit')
                        row = evaluate_candidate(model, battery, extra_mass)
                        row['conditional_screening_feasible'] = row.pop('screening_feasible')
                        row['cost_status'] = 'Hypothetical allowances only; budget compliance unresolved'
                        row['thermal_acceptance'] = 'unperformed'
                        row['yaw_authority_acceptance'] = 'unperformed; equal-torque trim only'
                        row.update(identity)
                    except OutsideEnvelope as error:
                        row = dict(identity, conditional_screening_feasible=False,
                                   rejection=str(error), procurement_ready=False)
                    rows.append(row)
    motor_path = ROOT / 'data/motors' / (MOTOR_ID + '.json')
    csv_path = prop_path.parent / json.loads(prop_path.read_text())['data_csv']
    result = dict(
        status='Preliminary conditional screening; not Chief selection or VerificationResult',
        motor_id=MOTOR_ID, propeller_pair=['LP13065E', 'LP13065EP'],
        battery_id='9067000412-0', supplier_access_date='2026-10-01',
        supplier_sources=[
            'https://www.buddyrc.com/products/sunnysky-x2814-brushless-motors',
            'https://www.apcprop.com/product/13x6-5e/',
            'https://www.apcprop.com/product/13x6-5ep/',
            'https://www.apcprop.com/technical-information/rpm-limits/',
            'https://hobbyking.com/en_us/turnigy-graphene-4000mah-4s-100c-lipo-pack-w-xt90.html'],
        battery_listed_price=dict(value=46.99, currency='USD', tax_treatment='unknown'),
        enforced_propeller_limit_rpm=rpm_limit,
        effective_configuration=cfg, battery_template=battery_template,
        source_sha256={str(p): sha(p) for p in [config_path, motor_path, prop_path, csv_path, HERE/'chief_coaxial_model.py', Path(__file__)]},
        cases=rows,
        limitations=[
            'Reverse propeller uses normal-rotation coefficient table provisionally; equivalence unmeasured.',
            'Supplier motor 40 A rating is 30-second limited, not proven for 300-second hover.',
            'ESC envelope, structure, servos, electronics and AUD prices remain hypothetical.',
            'Resistance and coaxial sweeps are not validated uncertainty bounds.',
            'Static mission energy envelope is not a flight trajectory simulation.',
            'Differential yaw authority and installed thermal endurance remain unverified.'])
    output = HERE / 'chief_documented_candidate_screening.json'
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(cases=len(rows), conditional_passes=sum(r['conditional_screening_feasible'] for r in rows), output=str(output), physical_acceptance='unperformed')))


if __name__ == '__main__':
    main()
