"""Bounded preliminary catalogue search; not physical verification.
Run with the 6dof_hopper backend, Python -B, from results/analysis.
All output paths are beside this script. Original catalogues remain unchanged.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from collections import Counter

sys.dont_write_bytecode = True
ROOT = Path('/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust')
sys.path.insert(0, str(ROOT))
from pythrust.motors import MotorDatabase
from pythrust.propellers import PropellerDatabase
from chief_coaxial_model import CoaxialModel, OutsideEnvelope, evaluate_candidate

HERE = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    config_path = HERE / 'chief_propulsion_screening_config.json'
    cfg = json.loads(config_path.read_text())
    motors = MotorDatabase()
    motors.load(ROOT / 'data/motors')
    policy = cfg['catalogue_policy']
    candidates = motors.search(
        min_kv=policy['motor_kv_range_rpm_per_v'][0],
        max_kv=policy['motor_kv_range_rpm_per_v'][1],
        min_weight=policy['motor_mass_range_g'][0],
        max_weight=policy['motor_mass_range_g'][1])
    valid = [m for m in candidates if all(math.isfinite(x) and x > 0 for x in
             (m.kv, m.resistance, m.max_current, m.max_power, m.weight_g))
             and math.isfinite(m.io) and m.io >= 0]
    # Six KV bands, two mass bands, two representatives per cell.
    # Prefer lower winding resistance within each cell, then lower mass.
    # This is reproducible exploration, not a proof of optimal selection.
    selected = {}
    for klo, khi in [(300,450),(450,600),(600,750),(750,900),(900,1050),(1050,1201)]:
        for mlo, mhi in [(50,120),(120,251)]:
            pool = [m for m in valid if klo <= m.kv < khi and mlo <= m.weight_g < mhi]
            for m in sorted(pool, key=lambda m: (m.resistance,m.weight_g,m.id))[:2]:
                selected[m.id] = m
    db = PropellerDatabase()
    propdir = ROOT / 'data/propellers/apc_202602'
    props, audits, provenance = [], [], {}
    for path in sorted(propdir.glob('*.json')):
        meta = json.loads(path.read_text())
        if not (10 <= meta['diameter_in'] <= 20 and meta['blade_count'] == 2
                and meta['model'].endswith('E')):
            continue
        table = propdir / meta['data_csv']
        rejected, seen, bad_static = [], set(), False
        with table.open(newline='') as stream:
            for line, row in enumerate(csv.DictReader(stream), 2):
                reason = None
                try:
                    rpm,j,ct,cp = [float(row[k]) for k in
                                  ('rpm','advance_ratio','thrust_coeff','power_coeff')]
                    if not all(math.isfinite(v) for v in (rpm,j,ct,cp)):
                        reason = 'nonfinite'
                    elif rpm <= 0 or j < 0 or ct < 0 or cp < 0:
                        reason = 'out_of_range'
                    elif (rpm,j) in seen:
                        reason = 'duplicate'
                    if reason is None:
                        seen.add((rpm,j))
                except (KeyError,ValueError):
                    reason = 'invalid_numeric'
                if reason:
                    rejected.append({'csv_line':line,'reason':reason,'row':row})
                    try:
                        bad_static |= float(row['advance_ratio']) == 0
                    except (KeyError,ValueError):
                        bad_static = True
        prop = db.load_entry(path, strict=False)
        usable = prop is not None and bool(prop.data_by_rpm) and not bad_static
        usable = usable and all(any(p.j == 0 and p.ct > 0 and p.cp > 0 for p in band)
                                for band in prop.data_by_rpm.values())
        audits.append({'id':meta['id'],'usable_static':usable,'rejected_rows':rejected})
        provenance[str(path)] = digest(path)
        provenance[str(table)] = digest(table)
        if usable:
            props.append(prop)
    for path in sorted((ROOT/'data/motors').rglob('*.json')):
        if json.loads(path.read_text()).get('id') in selected:
            provenance[str(path)] = digest(path)
    records, failures = [], Counter()
    def evaluate(motor, prop, battery, tf, qf, added):
        identity = dict(motor_id=motor.id,propeller_id=prop.metadata.id,
                        battery_id=battery['id'],thrust_factors=tf,torque_factors=qf,
                        added_mass_kg=added)
        try:
            return evaluate_candidate(CoaxialModel(motor,prop,cfg,tf,qf),battery,added)
        except OutsideEnvelope as error:
            failures[str(error)] += 1
            return dict(identity,screening_feasible=False,rejection=str(error),
                        procurement_ready=False)
    for index,motor in enumerate(selected.values()):
        print(f'Screening motor {index+1}/{len(selected)}: {motor.id}',file=sys.stderr,flush=True)
        for prop in props:
            for battery in cfg['battery_alternatives']:
                records.append(evaluate(motor,prop,battery,[0.90,0.75],[1.05,1.15],0))
    feasible = sorted((r for r in records if r['screening_feasible']),
                      key=lambda r:(r['mission_energy_with_allowance_wh'],r['mass_kg'],r['motor_id']))
    sensitivity = []
    for row in feasible[:10]:
        motor = selected[row['motor_id']]
        prop = db.get(row['propeller_id'])
        battery = next(b for b in cfg['battery_alternatives'] if b['id']==row['battery_id'])
        for tf in cfg['coaxial']['per_rotor_thrust_factors']:
            for qf in cfg['coaxial']['per_rotor_torque_factors']:
                for added in cfg['uncertainty']['additional_structure_mass_kg_cases']:
                    sensitivity.append(evaluate(motor,prop,battery,tf,qf,added))
    result = dict(status='Preliminary numerical screening only; no Chief selection yet',
        search_policy='24 maximum motors: two lowest-resistance representatives per KV/mass cell; all eligible 10-20 inch two-blade E propellers; three hypothetical batteries',
        catalogue_motor_count=motors.motor_count,eligible_motor_count=len(valid),
        screened_motor_ids=list(selected),screened_propeller_ids=[p.metadata.id for p in props],
        attempted=len(records),nominal_feasible_count=len(feasible),
        rejection_counts_including_sensitivity=dict(failures),
        ranked_nominal_feasible=feasible,all_nominal_results=records,sensitivity_results=sensitivity,
        source_sha256=provenance,
        configuration_sha256=digest(config_path),model_sha256=digest(HERE/'chief_coaxial_model.py'),
        driver_sha256=digest(Path(__file__)),
        limitations=['Prices and battery/ESC envelopes are assumptions, not quotations.',
                     'Matched CW/CCW availability and performance are unverified.',
                     'Catalogue maximum ratings and derating do not establish continuous thermal capability.',
                     'Static energy envelope is not a mission simulation.',
                     'Coaxial sensitivity factors are not measured bounds.',
                     'Search is bounded; no global optimum or hardware acceptance claimed.'])
    (HERE/'chief_propulsion_search_results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    (HERE/'chief_propeller_row_audit.json').write_text(json.dumps(audits,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'attempted':len(records),'nominal_feasible':len(feasible),
                      'top_candidates':feasible[:3],'physical_validation':'unperformed'},indent=2))

if __name__ == '__main__':
    main()
