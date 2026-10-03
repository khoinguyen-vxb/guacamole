"""Revision-4 purchasing audit; preliminary PDR analysis, not component selection.

Original inputs and chief_priced_bom_compute.py remain unchanged. Only the
inspected legacy loader and configuration resolver are reused. Legacy pricing,
line_mass, verification and report functions are NOT used.

Run with repository=6dof_hopper and python -B. Supply --base, repeated
--supplement arguments in dependency order (including the r4 policy),
--accounting, --configuration and --output. Declare --output in execute.outputs.
For verification use --verify --result SAVED_REPORT with the same inputs through
verify_command; include every input artifact, this script, the legacy loader
and the saved report in tool inputs. Verification recomputes the saved ledger.
Stdout in verification mode contains exactly one VerificationResult object.

The separately prepared accounting JSON must have schema
hopper_purchase_accounting_r4_v1, requirement_ref equal to REQUIREMENT below,
vehicle_lines keyed by selected option ID, gse_lines (a list), and
unpriced_vehicle_items/unpriced_gse_items (lists, possibly empty).

Each vehicle accounting record requires:
  category: hardware | material | consumable | included | contingency
  purchase_units: integer count of whole supplier purchase units
  minimum_purchase_units: positive integer minimum order
  stock_per_purchase_unit: positive number
  stock_unit: piece, m, kg, etc.
  required_stock_quantity: number or null, including fabrication consumption
  installed_quantity: number or null, in stock_unit (not purchase units)
  mass_per_installed_unit_kg: number or null
  mass_tolerance_per_unit_kg: nonnegative number, optional
  mass_basis: explanation distinguishing supplier/CAD/measured/assumed values
  purchase_basis: explanation and source section for pack/minimum quantities
  accounting_status: provisional | reviewed
  availability_status: listed_available | caveated | unknown | unavailable
  unresolved: list of outstanding issues

For the two-battery purchase pack use purchase_units=1,
stock_per_purchase_unit=2 and installed_quantity=1; mass is per battery.
For stock material use installed quantities in m/kg, not full stock mass.
For included/contingency records stock and mass fields may be omitted;
contingency remains charged but is not claimed as a purchased component.
GSE records contain id, price (same price fields as a legacy option), and
accounting (same accounting format, category must be reusable_gse).

No ownership credits or apportioned purchase costs are supported. Unknown
installation quantities/masses remain unknown. Unknown stock never becomes
confirmed availability. All retained prices remain dated historical evidence.
Completeness, physical fit, thermal endurance and mission feasibility are not
verified by this ledger. In particular a budget flag is not procurement approval.
"""
import argparse
from datetime import date
from decimal import Decimal, ROUND_CEILING, getcontext
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
getcontext().prec = 34
REVISION = 1
CENT = Decimal('0.01')
REQUIREMENT = {
    'kind': 'requirement', 'id': 'REQ-HARDWARE-BUDGET', 'revision': 4,
    'sha256': '0a1e886cb48d7e054b9d88177a9e78a9a125d007f88948aaae5a3d8af22be2c6'
}
POLICY_SOURCE = {
    'kind': 'source', 'id': 'b985cd4b473d49f5b74e889cc8f454f9', 'revision': 1,
    'sha256': '5ef30df7ed9f7b87c042a1d7fdc7c8e1427e435fadde08ee00181e377da43c75'
}
CASES = ('conservative', 'documented_tax_exclusive', 'conservative_fx_margin')
VEHICLE_CATEGORIES = {'hardware', 'material', 'consumable', 'included', 'contingency'}
AVAILABILITY = {'listed_available', 'caveated', 'unknown', 'unavailable'}


class InputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def number(value, label, positive=False):
    require(not isinstance(value, bool) and isinstance(value, (int, float)),
            label + ' must be numeric')
    require(math.isfinite(value) and (value > 0 if positive else value >= 0),
            label + ' must be finite and ' + ('positive' if positive else 'nonnegative'))
    return Decimal(str(value))


def integer(value, label):
    require(type(value) is int and value > 0, label + ' must be a positive integer')
    return value


def text_field(record, key, label):
    value = record.get(key)
    require(isinstance(value, str) and bool(value.strip()), label + '.' + key + ' is required')
    return value


def same_ref(actual, expected):
    return isinstance(actual, dict) and all(actual.get(k) == v for k, v in expected.items())


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sandbox_path(value):
    root = Path(os.environ.get('GUACAMOLE_SANDBOX', Path(__file__).resolve().parent.parent)).resolve()
    path = Path(value).resolve()
    require(path.is_relative_to(root), 'Path is outside the sandbox: ' + str(path))
    return path


def price_policy(merged):
    budget = merged['budget']
    require(budget.get('comparison') == 'strictly_less_than', 'Strict comparison is required')
    require(number(budget.get('ceiling_aud'), 'ceiling') == Decimal(500), 'Expected AUD 500 ceiling')
    latest = {r['policy']: r for r in merged.get('policy_confirmations', [])}
    for key in ('purchase_unit_policy', 'gse_policy'):
        row = latest.get(key, {})
        require(row.get('decision') == 'confirmed' and same_ref(row.get('source'), POLICY_SOURCE),
                'Missing current human policy confirmation: ' + key)
    conversion = merged['currency_conversion']
    rates = conversion.get('usd_per_aud', {})
    require(bool(rates), 'No dated USD-per-AUD rates')
    checked = {}
    for day, value in rates.items():
        date.fromisoformat(day)
        checked[day] = number(value, 'USD-per-AUD rate', positive=True)
    rate_day = min(checked, key=lambda d: (checked[d], d))
    return {
        'rate': checked[rate_day], 'rate_date': rate_day,
        'fx_margin': number(conversion['fx_margin_sensitivity_fraction'], 'FX margin'),
        'gst': number(merged['tax_policy']['au_gst_rate'], 'GST rate'),
        'provenance': conversion
    }


def unit_prices(option, policy):
    unit = number(option['unit_price'], 'unit_price')
    currency, basis = option['currency'], option['price_basis']
    require(currency in ('AUD', 'USD'), 'Unsupported currency: ' + str(currency))
    printed = option.get('printed_ex_tax_unit_price')
    conservative = number(option.get('conservative_unit_price', option['unit_price']),
                          'conservative_unit_price')
    require(conservative >= unit, 'Conservative price must not undercut listed price')
    if printed is not None:
        require(currency == 'AUD' and basis in ('au_printed_inc_and_ex_gst', 'au_printed_ex_gst_only'),
                'Printed ex-tax price has incompatible basis')
        exclusive = number(printed, 'printed_ex_tax_unit_price')
        require(exclusive <= unit, 'Printed ex-tax price exceeds listed price')
        if basis == 'au_printed_ex_gst_only':
            require(exclusive == unit, 'Exclusive-only prices disagree')
        conservative = exclusive
    elif basis == 'au_displayed_incl_gst':
        exclusive = unit / (1 + policy['gst'])
    else:
        # No inferred GST deduction for an unstated Australian tax basis.
        exclusive = conservative
    if currency == 'USD':
        conservative /= policy['rate']
        exclusive /= policy['rate']
    fx = conservative * (1 + policy['fx_margin']) if currency == 'USD' else conservative
    return dict(zip(CASES, (conservative, exclusive, fx)))


def audit_line(identifier, price, record, policy, gse=False):
    require(isinstance(record, dict), 'Missing accounting record: ' + identifier)
    category = record.get('category')
    require(category == 'reusable_gse' if gse else category in VEHICLE_CATEGORIES,
            'Invalid budget classification: ' + identifier)
    qty = integer(record.get('purchase_units'), identifier + '.purchase_units')
    minimum = integer(record.get('minimum_purchase_units'), identifier + '.minimum_purchase_units')
    require(qty >= minimum, identifier + ' is below minimum order')
    purchase_basis = text_field(record, 'purchase_basis', identifier)
    status = record.get('accounting_status')
    require(status in ('provisional', 'reviewed'), 'Invalid accounting_status: ' + identifier)
    availability = record.get('availability_status')
    require(availability in AVAILABILITY, 'Invalid availability_status: ' + identifier)
    unresolved = record.get('unresolved')
    require(isinstance(unresolved, list) and all(isinstance(s, str) for s in unresolved),
            'unresolved must be a list of strings: ' + identifier)
    historical_qty = price.get('quantity')
    if historical_qty is not None and historical_qty != qty:
        text_field(record, 'quantity_change_reason', identifier)
    unit = unit_prices(price, policy)
    exact = {case: amount * qty for case, amount in unit.items()}
    rounded = {case: amount.quantize(CENT, rounding=ROUND_CEILING) for case, amount in exact.items()}
    accounting_only = category in ('included', 'contingency')
    if category == 'included':
        require(all(amount == 0 for amount in exact.values()), 'Included line must cost zero')
    if category == 'contingency':
        require(price.get('evidence_grade') == 'allowance', 'Contingency must remain labelled allowance')
    purchased_stock = installed = required = mass = None
    coverage = None
    if not accounting_only:
        stock = number(record.get('stock_per_purchase_unit'), identifier + '.stock_per_purchase_unit', True)
        text_field(record, 'stock_unit', identifier)
        purchased_stock = stock * qty
        if record.get('installed_quantity') is not None:
            installed = number(record['installed_quantity'], identifier + '.installed_quantity')
            require(installed <= purchased_stock, identifier + ' installs more stock than purchased')
        if record.get('required_stock_quantity') is not None:
            required = number(record['required_stock_quantity'], identifier + '.required_stock_quantity')
            coverage = purchased_stock >= required
            if installed is not None:
                require(required >= installed, identifier + ' consumption is below installation quantity')
        if installed is not None and record.get('mass_per_installed_unit_kg') is not None:
            mass_unit = number(record['mass_per_installed_unit_kg'], identifier + '.mass_per_installed_unit_kg')
            mass_tol = number(record.get('mass_tolerance_per_unit_kg', 0), identifier + '.mass_tolerance')
            text_field(record, 'mass_basis', identifier)
            mass = installed * (mass_unit + mass_tol)
    else:
        mass = Decimal(0)
        coverage = True
    traceable = accounting_only or bool(price.get('url') and price.get('access_date'))
    if price.get('access_date'):
        date.fromisoformat(price['access_date'])
    values = {
        'id': identifier, 'category': category, 'purchase_units': qty,
        'historical_quantity_field': historical_qty, 'minimum_purchase_units': minimum,
        'purchase_basis': purchase_basis, 'accounting_status': status,
        'stock_unit': record.get('stock_unit'),
        'purchased_stock_quantity': None if purchased_stock is None else float(purchased_stock),
        'required_stock_quantity': None if required is None else float(required),
        'installed_quantity': None if installed is None else float(installed),
        'not_installed_stock_quantity': None if installed is None else float(purchased_stock - installed),
        'installed_mass_upper_kg': None if mass is None else float(mass),
        'mass_basis': record.get('mass_basis'), 'stock_covers_requirement': coverage,
        'aud': {case: float(value) for case, value in rounded.items()},
        'exact_aud_decimal': {case: str(value) for case, value in exact.items()},
        'availability_status': availability, 'unresolved': unresolved,
        'price_traceable': traceable, 'price_record': price,
        'quantity_change_reason': record.get('quantity_change_reason')
    }
    return values


def summarize(lines):
    totals, exact = {}, {}
    for case in CASES:
        # Sum Decimal strings, not binary floating-point values.
        exact[case] = sum((Decimal(r['exact_aud_decimal'][case]) for r in lines), Decimal(0))
        totals[case] = sum((Decimal(r['exact_aud_decimal'][case]).quantize(CENT, rounding=ROUND_CEILING)
                            for r in lines), Decimal(0))
    unknown_mass = [r['id'] for r in lines if r['installed_mass_upper_kg'] is None]
    known_mass = sum((Decimal(str(r['installed_mass_upper_kg'])) for r in lines
                      if r['installed_mass_upper_kg'] is not None), Decimal(0))
    return {
        'totals_aud': {k: float(v) for k, v in totals.items()},
        'exact_totals_aud_decimal': {k: str(v) for k, v in exact.items()},
        'known_installed_mass_upper_subtotal_kg': float(known_mass),
        'installed_mass_upper_kg': None if unknown_mass else float(known_mass),
        'unknown_mass_lines': unknown_mass,
        'unknown_stock_coverage_lines': [r['id'] for r in lines if r['stock_covers_requirement'] is None],
        'insufficient_stock_lines': [r['id'] for r in lines if r['stock_covers_requirement'] is False],
        'provisional_accounting_lines': [r['id'] for r in lines if r['accounting_status'] != 'reviewed'],
        'unresolved_lines': [r['id'] for r in lines if r['unresolved']],
        'unverified_availability_lines': [r['id'] for r in lines
                                        if r['category'] not in ('included', 'contingency')
                                        and r['availability_status'] != 'listed_available'],
        'untraceable_price_lines': [r['id'] for r in lines if not r['price_traceable']]
    }


def recompute(args):
    paths = [sandbox_path(args.loader), sandbox_path(args.base)]
    supplements = [sandbox_path(p) for p in args.supplement]
    manifest_path = sandbox_path(args.accounting)
    paths += supplements + [manifest_path, sandbox_path(__file__)]
    require(len(paths) == len(set(paths)), 'Repeated input paths')
    spec = importlib.util.spec_from_file_location('hopper_legacy_bom_loader', paths[0])
    require(spec is not None and spec.loader is not None, 'Cannot load inspected legacy module')
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    merged, _ = legacy.load_inputs(paths[1], supplements)
    policy = price_policy(merged)
    manifest = load(manifest_path)
    require(manifest.get('schema') == 'hopper_purchase_accounting_r4_v1', 'Wrong accounting schema')
    require(same_ref(manifest.get('requirement_ref'), REQUIREMENT), 'Accounting must reference current budget r4')
    for key in ('unpriced_vehicle_items', 'unpriced_gse_items', 'gse_lines'):
        require(isinstance(manifest.get(key), list), key + ' must be an explicit list')
    records = manifest.get('vehicle_lines')
    require(isinstance(records, dict), 'vehicle_lines must be keyed by option ID')
    selection = legacy.resolve(args.configuration, merged['configurations'], merged['options'])
    require(bool(selection), 'Empty vehicle configuration')
    vehicle = []
    for role, identifier in sorted(selection.items()):
        row = audit_line(identifier, merged['options'][identifier], records.get(identifier), policy)
        row['role'] = role
        vehicle.append(row)
    gse, seen = [], set()
    for item in manifest['gse_lines']:
        identifier = text_field(item, 'id', 'GSE')
        require(identifier not in seen and identifier not in selection.values(), 'Duplicate GSE/vehicle identity')
        seen.add(identifier)
        gse.append(audit_line(identifier, item['price'], item['accounting'], policy, True))
    vsummary, gsummary = summarize(vehicle), summarize(gse)
    report = {
        'schema': 'hopper_purchase_audit_r4_result_v1', 'script_revision': REVISION,
        'scope': 'Preliminary whole-purchase ledger and separately identified installed mass. Not completeness, procurement, mission or physical acceptance.',
        'current_requirement': REQUIREMENT, 'policy_source': POLICY_SOURCE,
        'historical_requirement_metadata': merged.get('requirements', []),
        'configuration': args.configuration, 'configuration_definition': merged['configurations'][args.configuration],
        'input_sha256': {str(p): digest(p) for p in paths},
        'pricing': {
            'currency': 'AUD', 'ceiling_exclusive_aud': 500,
            'usd_per_aud': float(policy['rate']), 'rate_date': policy['rate_date'],
            'source': policy['provenance'], 'fx_margin_fraction': float(policy['fx_margin']),
            'rounding': 'Round each line upward to AUD 0.01, then sum.',
            'tax_rule': 'Use printed ex-tax prices; documented_tax_exclusive additionally deducts recorded GST only where explicitly included. Never deduct tax from an unstated basis.'
        },
        'vehicle_lines': vehicle, 'vehicle': vsummary, 'gse_lines': gse, 'gse': gsummary,
        'vehicle_budget_flags': {
            case: {'total_aud': vsummary['totals_aud'][case],
                   'margin_aud': float(Decimal(500) - Decimal(str(vsummary['totals_aud'][case]))),
                   'strictly_below_500': Decimal(str(vsummary['totals_aud'][case])) < Decimal(500)}
            for case in CASES
        },
        'unpriced_vehicle_items': manifest['unpriced_vehicle_items'],
        'unpriced_gse_items': manifest['unpriced_gse_items'],
        'limitations': [
            'Historical option quantities are not installed quantities; only the explicit accounting manifest supplies installation and consumption.',
            'Full minimum purchase packs/spools/lengths are charged; no equipment ownership is assumed.',
            'Availability labels are review annotations, not independently verified supplier stock.',
            'Supplier URLs, access dates, currencies, units and conflicts are preserved in each price_record; no current re-fetch is implied.',
            'An empty unpriced list or reviewed annotation does not independently prove BOM completeness.',
            'Known mass subtotal excludes unknown lines; a null total must not be used as a complete vehicle mass.',
            'GSE mass is separate and never added to flight mass; contingency is charged to the vehicle without an invented hardware mass.',
            'Above-ceiling gross or uncertain-tax totals do not alone prove the tax-exclusive requirement impossible.',
            'No thermal, propulsion, CAD-clearance, battery-energy or flight-performance check is performed.'
        ]
    }
    return report, paths


def verification(report, result_path):
    saved = load(result_path)
    v, g = report['vehicle'], report['gse']
    all_lines = report['vehicle_lines'] + report['gse_lines']
    checks = {
        'saved_report_matches_recomputed_inputs': saved == report,
        'whole_purchase_stock_sufficient': False if v['insufficient_stock_lines'] or g['insufficient_stock_lines']
            else (None if v['unknown_stock_coverage_lines'] or g['unknown_stock_coverage_lines'] else True),
        'conservative_vehicle_total_strictly_below_500_aud': report['vehicle_budget_flags']['conservative']['strictly_below_500'],
        'fx_sensitivity_vehicle_total_strictly_below_500_aud': report['vehicle_budget_flags']['conservative_fx_margin']['strictly_below_500'],
        'recorded_prices_traceable': not any(not r['price_traceable'] for r in all_lines),
        'accounting_review_recorded': not v['provisional_accounting_lines'] and not g['provisional_accounting_lines'],
        'separate_gse_priced': bool(report['gse_lines']) and not report['unpriced_gse_items'],
        'listed_vehicle_gaps_priced': not report['unpriced_vehicle_items'],
        'supplier_availability_confirmed': None,
        'complete_vehicle_and_gse_coverage_independently_verified': None,
        'physical_acceptance': None
    }
    invalid = not checks['saved_report_matches_recomputed_inputs'] or checks['whole_purchase_stock_sufficient'] is False
    # A complete requirement pass is deliberately unavailable from a ledger alone.
    outcome = 'failed' if invalid else 'inconclusive'
    explanation = {
        'scope': report['scope'], 'configuration': report['configuration'],
        'requirement': REQUIREMENT, 'vehicle_totals_aud': v['totals_aud'],
        'gse_totals_aud': g['totals_aud'], 'budget_flags': report['vehicle_budget_flags'],
        'input_sha256': dict(report['input_sha256'], **{str(result_path): digest(result_path)}),
        'note': 'Report consistency and arithmetic are recomputed. Full budget acceptance remains inconclusive without independent coverage and supplier review; no physical test is inferred.'
    }
    return {'outcome': outcome, 'checks': checks, 'explanation': json.dumps(explanation, sort_keys=True, allow_nan=False)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loader', default=str(Path(__file__).with_name('chief_priced_bom_compute.py')))
    parser.add_argument('--base', required=True)
    parser.add_argument('--supplement', action='append', default=[])
    parser.add_argument('--accounting', required=True)
    parser.add_argument('--configuration', required=True)
    parser.add_argument('--output')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--result')
    args = parser.parse_args()
    try:
        report, inputs = recompute(args)
        if args.verify:
            require(bool(args.result), '--verify requires --result')
            result = verification(report, sandbox_path(args.result))
            print(json.dumps(result, allow_nan=False))
        else:
            require(bool(args.output), 'Compute mode requires --output')
            target = sandbox_path(args.output)
            require(target not in inputs and not target.exists(), 'Use a new output filename; never overwrite inputs or history')
            require(target.parent.is_dir(), 'Output directory must already exist')
            target.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
            print(json.dumps({'output': str(target), 'vehicle_totals_aud': report['vehicle']['totals_aud'],
                              'gse_totals_aud': report['gse']['totals_aud'], 'physical_acceptance': 'unperformed'}, allow_nan=False))
        return 0
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        if args.verify:
            print(json.dumps({'outcome': 'inconclusive', 'checks': {'audit_completed': False},
                              'explanation': 'Audit could not complete: ' + type(error).__name__ + ': ' + str(error)}, allow_nan=False))
            return 0
        return 1


if __name__ == '__main__':
    sys.exit(main())
