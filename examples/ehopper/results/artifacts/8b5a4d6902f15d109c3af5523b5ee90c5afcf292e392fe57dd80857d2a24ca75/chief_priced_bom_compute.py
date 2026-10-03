'''Priced-BOM cost computation and indicative mass reconciliation (preliminary).

Status: reproducible arithmetic over recorded supplier evidence and explicit
allowances for the Electronic Hopper PDR. NOT a Chief selection, procurement
approval, assured quotation, budget-compliance acceptance or physical
acceptance. A total below the ceiling does not establish compliance while
unresearched allowances, search-snippet prices or availability conflicts
remain.

Script revision 1, written 2026-10-03; Python standard library only. Input
artifacts and original repositories are read, never modified.

Compute mode (execute; repository=6dof_hopper; workdir=analysis):
    python -B chief_priced_bom_compute.py
        --base chief_priced_bom_inputs_2026-10-02.json
        --supplement chief_priced_bom_supplement_2026-10-02.json
        --screening chief_40a_esc_candidate_screening.json
        --output chief_priced_bom_results.json
        --markdown chief_priced_bom_tables.md
Verify mode (verify_command): the same --base and --supplement arguments plus
--verify CONFIG_ID. Stdout then carries exactly one VerificationResult JSON
object, diagnostics go to stderr and no files are written. Outcome rule:
failed if even the tax-exclusive estimate reaches the ceiling; passed only if
every check holds; otherwise inconclusive.

Conventions
- Money is AUD. USD prices use the minimum recorded RBA USD-per-AUD value,
  giving the largest AUD amount (base currency_conversion.policy).
- Tax and FX cases follow the base tax_policy.cases definitions.
- Every line total is rounded up to the next cent before summation for the
  strict ceiling comparison; unrounded sums are reported alongside.
- Line mass = quantity x (unit_mass_kg + mass_tolerance_kg); unit_mass_kg is
  the carried mass per purchased quantity unit. Reconciliation against the
  screening allowances is indicative and retains an allowance wherever a
  group is only partly replaced or lacks listed masses.
'''
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_CEILING, getcontext
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
getcontext().prec = 34

SCRIPT_REVISION = 1
NEWLINE = chr(10)
BASE_SCHEMA = 'hopper_priced_bom_inputs_v1'
SUPPLEMENT_SCHEMA = 'hopper_priced_bom_supplement_v1'
ADDITIVE_LISTS = ('open_items', 'evidence_updates', 'rejected_or_unusable_evidence')
CASES = ('conservative', 'tax_exclusive_estimate', 'conservative_fx_margin')
CURRENCIES = ('AUD', 'USD')
GST_DEDUCTIBLE_BASES = ('au_displayed_gst_status_unstated', 'au_displayed_incl_gst')
PRINTED_BASIS = 'au_printed_inc_and_ex_gst'
REQUIRED_OPTION_KEYS = ('id', 'role', 'description', 'quantity', 'unit_price',
                        'currency', 'price_basis', 'evidence_grade')
# Screening-allowance group keys used by the BOM inputs for non-itemised groups.
MOTOR_GROUP = 'motor_allowance'
BATTERY_GROUP = 'battery_alternatives assumed_4S_4000'
COST_ONLY_GROUPS = ('uncertainty.additional_cost_aud',)
PARTIAL_MARKERS = (' (part)', ' (servo share)')
NON_CANDIDATE_PREFIXES = ('diagnostic only', 'comparison only')
CENT = Decimal('0.01')
MICRO = Decimal('0.000001')
SOLD_OUT = re.compile('sold[ -]out|discontinued', re.I)
CONFLICT = re.compile('in stock|conflict|add[ -]to[ -]cart', re.I)
CAVEAT = re.compile('not stated|unknown|unconfirmed|unresolved|not re-verified|not re-fetched|'
                    'http 403|store-dependent|lead time|caveat|quantity|listed stock|'
                    'not confirmed', re.I)
AVAILABLE = re.compile('in stock|available|included|local stock|dispatch', re.I)
LIMITATIONS = [
    'Arithmetic over recorded supplier evidence and allowances; prices, stock and exchange rates '
    'change, and assured quotations are required before procurement.',
    'The conservative case deducts no GST where a retailer did not print an ex-GST price; the '
    'tax-exclusive estimate assumes Australian displayed prices include 10 percent GST.',
    'USD amounts exclude card, bank and marketplace FX margins except in the 3 percent '
    'sensitivity case; Temu, Taobao and AliExpress quotes were not retrievable.',
    'Whole purchase units (filament spool, tube length, multi-packs) count in full and listed GSE '
    'is excluded; both policies await human confirmation.',
    'Availability classes are text-match review aids that can misclassify; read the recorded '
    'availability text for each line.',
    'Mass reconciliation is indicative: screening allowances are retained for partly replaced or '
    'unlisted groups, and listed masses include recorded tolerances; CAD-derived and measured '
    'masses must replace them.',
    'Screening coverage counts reuse the 40 A ESC static propulsion screening at the smallest '
    'covering added-mass case; they are not a rerun at the reconciled mass, revised servo supply '
    'or auxiliary power.',
    'No Chief selection, procurement approval, budget-compliance acceptance, mission or physical '
    'validation.']


class InputError(ValueError):
    '''Defect in the supplied BOM inputs, as opposed to a script defect.'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise InputError('Cannot read %s: %s' % (path, error)) from error


def check_number(value, label, minimum=None, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError('%s must be numeric, not %r' % (label, value))
    if not math.isfinite(value):
        raise InputError('%s must be finite' % label)
    if minimum is not None and value < minimum:
        raise InputError('%s must be at least %s' % (label, minimum))
    return value


def dec(value):
    '''Exact decimal of the shortest representation of a JSON number.'''
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def valid_date(text):
    try:
        date.fromisoformat(str(text))
    except ValueError:
        return False
    return True


def validate_option(option, merged):
    oid = option.get('id')
    if not isinstance(oid, str) or not oid:
        raise InputError('Option without a string id: %r' % (option,))
    missing = [key for key in REQUIRED_OPTION_KEYS if key not in option]
    if missing:
        raise InputError('Option %s lacks %s' % (oid, ', '.join(missing)))
    currency, basis, grade = option['currency'], option['price_basis'], option['evidence_grade']
    if currency not in CURRENCIES:
        raise InputError('Option %s has unsupported currency %r' % (oid, currency))
    if basis not in merged['tax_policy']['price_basis_codes']:
        raise InputError('Option %s has unknown price_basis %r' % (oid, basis))
    if grade not in merged['evidence_grades']:
        raise InputError('Option %s has unknown evidence_grade %r' % (oid, grade))
    if check_number(option['quantity'], oid + '.quantity') <= 0:
        raise InputError('Option %s quantity must be positive' % oid)
    unit = check_number(option['unit_price'], oid + '.unit_price', minimum=0)
    printed = check_number(option.get('printed_ex_tax_unit_price'),
                           oid + '.printed_ex_tax_unit_price', minimum=0, allow_none=True)
    if (basis == PRINTED_BASIS) != (printed is not None):
        raise InputError('Option %s: a printed ex-tax price and basis %s must occur together'
                         % (oid, PRINTED_BASIS))
    if printed is not None and (currency != 'AUD' or printed > unit):
        raise InputError('Option %s: a printed ex-tax price must be AUD and not exceed unit_price'
                         % oid)
    check_number(option.get('conservative_unit_price'), oid + '.conservative_unit_price',
                 minimum=unit, allow_none=True)
    if (grade == 'allowance') != (basis == 'allowance_aud'):
        raise InputError('Option %s: allowance grade and allowance_aud basis must occur together'
                         % oid)
    if basis == 'allowance_aud' and currency != 'AUD':
        raise InputError('Option %s: allowances must be in AUD' % oid)
    if basis == 'no_purchase' and unit != 0:
        raise InputError('Option %s: a no_purchase line must have zero price' % oid)
    if grade != 'allowance' and not (option.get('url') and valid_date(option.get('access_date'))):
        raise InputError('Option %s lacks a source URL or ISO access date' % oid)
    check_number(option.get('unit_mass_kg'), oid + '.unit_mass_kg', minimum=0, allow_none=True)
    check_number(option.get('mass_tolerance_kg'), oid + '.mass_tolerance_kg', minimum=0,
                 allow_none=True)


def load_inputs(base_path, supplement_paths):
    base_path = Path(base_path)
    base = load_json(base_path)
    if base.get('schema') != BASE_SCHEMA:
        raise InputError('%s is not %s' % (base_path, BASE_SCHEMA))
    for key in ('budget', 'currency_conversion', 'tax_policy', 'evidence_grades'):
        if key not in base:
            raise InputError('Base input lacks %s' % key)
    if 'price_basis_codes' not in base['tax_policy']:
        raise InputError('Base tax_policy lacks price_basis_codes')
    merged = dict(budget=base['budget'], currency_conversion=base['currency_conversion'],
                  tax_policy=base['tax_policy'], evidence_grades=base['evidence_grades'],
                  excluded_gse=list(base.get('excluded_gse', [])), requirements=[],
                  options={}, option_source={}, configurations={}, configuration_source={})
    for key in ADDITIVE_LISTS:
        merged[key] = []
    documents = [(base_path, base)]
    for path in map(Path, supplement_paths):
        document = load_json(path)
        if document.get('schema') != SUPPLEMENT_SCHEMA:
            raise InputError('%s is not %s' % (path, SUPPLEMENT_SCHEMA))
        if Path(str(document.get('extends', ''))).name != base_path.name:
            raise InputError('%s extends %r, not %s' % (path, document.get('extends'),
                                                        base_path.name))
        documents.append((path, document))
    seen = set()
    for path, document in documents:
        for option in document.get('options', []):
            oid = option.get('id')
            if oid in merged['options']:
                raise InputError('Duplicate option id %s in %s' % (oid, path.name))
            validate_option(option, merged)
            merged['options'][oid] = option
            merged['option_source'][oid] = path.name
        for cid, configuration in document.get('configurations', {}).items():
            if cid in merged['configurations']:
                raise InputError('Duplicate configuration id %s in %s' % (cid, path.name))
            merged['configurations'][cid] = configuration
            merged['configuration_source'][cid] = path.name
        for key in ADDITIVE_LISTS:
            merged[key].extend(dict(item, input_file=path.name) for item in document.get(key, []))
        for requirement in document.get('requirements', []):
            ident = (requirement.get('id'), requirement.get('revision'))
            if ident not in seen:
                seen.add(ident)
                merged['requirements'].append(dict(id=ident[0], revision=ident[1]))
    for update in merged['evidence_updates']:
        if update.get('applies_to_option') not in merged['options']:
            raise InputError('Evidence update targets unknown option %r'
                             % (update.get('applies_to_option'),))
    budget = merged['budget']
    if budget.get('comparison') != 'strictly_less_than':
        raise InputError('Only a strictly_less_than budget comparison is supported')
    check_number(budget.get('ceiling_aud'), 'budget.ceiling_aud', minimum=0)
    return merged, documents


def pricing_policy(merged):
    conversion = merged['currency_conversion']
    rates = conversion.get('usd_per_aud') or {}
    if not rates:
        raise InputError('No USD-per-AUD rates are recorded')
    for day, value in rates.items():
        if check_number(value, 'usd_per_aud[%s]' % day) <= 0:
            raise InputError('The exchange rate for %s must be positive' % day)
    rate_date = min(rates, key=lambda day: (rates[day], day))
    gst = check_number(merged['tax_policy'].get('au_gst_rate'), 'tax_policy.au_gst_rate',
                       minimum=0)
    margin = check_number(conversion.get('fx_margin_sensitivity_fraction'),
                          'currency_conversion.fx_margin_sensitivity_fraction', minimum=0)
    return dict(usd_per_aud=dec(rates[rate_date]), rate_date=rate_date, gst=dec(gst),
                fx_margin=dec(margin), ceiling=dec(merged['budget']['ceiling_aud']))


def line_amount(option, case, policy):
    '''AUD amount of one BOM line in one tax/FX case; returns (exact, usd_derived).'''
    printed = option.get('printed_ex_tax_unit_price')
    if printed is not None:
        unit = dec(printed)
    elif case == 'tax_exclusive_estimate':
        unit = dec(option['unit_price'])
        if option['price_basis'] in GST_DEDUCTIBLE_BASES:
            unit = unit / (1 + policy['gst'])
    elif option.get('conservative_unit_price') is not None:
        unit = dec(option['conservative_unit_price'])
    else:
        unit = dec(option['unit_price'])
    usd_derived = option['currency'] == 'USD'
    if usd_derived:
        unit = unit / policy['usd_per_aud']
        if case == 'conservative_fx_margin':
            unit = unit * (1 + policy['fx_margin'])
    return unit * dec(option['quantity']), usd_derived


def resolve(cid, configurations, options, stack=()):
    '''Resolve the base selection, delete remove_roles, then apply this selection.'''
    if cid in stack:
        raise InputError('Configuration cycle: ' + ' -> '.join(stack + (cid,)))
    configuration = configurations.get(cid)
    if configuration is None:
        raise InputError('Unknown configuration %r' % (cid,))
    base = configuration.get('base')
    selection = {} if base is None else resolve(base, configurations, options, stack + (cid,))
    for role in configuration.get('remove_roles', []):
        if role not in selection:
            raise InputError('%s removes absent role %s' % (cid, role))
        del selection[role]
    for role, oid in configuration.get('selection', {}).items():
        option = options.get(oid)
        if option is None:
            raise InputError('%s selects unknown option %s' % (cid, oid))
        if option['role'] != role:
            raise InputError('%s assigns option %s with role %s to role %s'
                             % (cid, oid, option['role'], role))
        selection[role] = oid
    return selection


def availability_class(option):
    '''Text-match review aid only; it can misclassify free-text availability.'''
    if option['evidence_grade'] == 'allowance':
        return 'not_applicable_allowance'
    text = option.get('availability') or ''
    if not text.strip():
        return 'not_recorded'
    if SOLD_OUT.search(text):
        if CONFLICT.search(text):
            return 'conflicting_or_variant_specific'
        return 'sold_out_or_discontinued'
    if CAVEAT.search(text):
        return 'listed_with_caveats'
    if AVAILABLE.search(text):
        return 'listed_available'
    return 'unclassified'


def split_group(text):
    '''Return (screening allowance group, partial replacement flag).'''
    if text is None:
        return None, False
    for marker in PARTIAL_MARKERS:
        if text.endswith(marker):
            return text[:-len(marker)], True
    return text, False


def line_mass(option):
    unit = option.get('unit_mass_kg')
    if unit is None:
        return None
    return option['quantity'] * (unit + (option.get('mass_tolerance_kg') or 0.0))


def is_non_candidate(configuration):
    text = str(configuration.get('description', '')).strip().lower()
    return text.startswith(NON_CANDIDATE_PREFIXES)


def screening_context(path):
    path = Path(path)
    data = load_json(path)
    configuration = data.get('effective_configuration')
    if not isinstance(configuration, dict) or 'cases' not in data or 'battery_template' not in data:
        raise InputError('%s lacks effective_configuration, cases or battery_template' % path)
    allowances = {}
    for item in configuration['vehicle_allowances']:
        if item['item'] in allowances:
            raise InputError('Duplicate screening allowance %s' % item['item'])
        allowances[item['item']] = item['quantity'] * item['unit_mass_kg']
    battery = data['battery_template']['mass_kg']
    zero = [row for row in data['cases']
            if row.get('additional_mass_kg') == 0 and 'mass_kg' in row]
    masses = sorted({round(row['mass_kg'], 9) for row in zero})
    if len(masses) != 1:
        raise InputError('Expected one zero-added-mass screening vehicle mass, found %s' % (masses,))
    baseline = zero[0]['mass_kg']
    payload = configuration.get('payload_kg', 0.0)
    motors = baseline - sum(allowances.values()) - battery - payload
    if motors <= 0:
        raise InputError('The derived screening motor-pair mass is not positive')
    allowances[MOTOR_GROUP] = motors
    allowances[BATTERY_GROUP] = battery
    return dict(path=path.name, allowances=allowances, baseline_mass_kg=baseline,
                payload_kg=payload, derived_motor_pair_mass_kg=motors,
                added_mass_cases_kg=sorted(
                    configuration['uncertainty']['additional_structure_mass_kg_cases']),
                cases=data['cases'])


def coverage(context, delta):
    cases = context['added_mass_cases_kg']
    covering = next((case for case in cases if case >= delta - 1e-12), None)
    result = dict(screened_added_mass_cases_kg=cases, covering_added_mass_case_kg=covering,
                  note='Counts reuse the 40 A ESC static screening at the smallest screened added '
                       'mass covering the indicative increase; they are not a rerun at the '
                       'reconciled mass.')
    if covering is None:
        result['note'] = ('The indicative increase exceeds every screened added-mass case; '
                          'rerun the propulsion screening.')
        return result
    rows = [row for row in context['cases'] if abs(row['additional_mass_kg'] - covering) < 1e-9]
    passes = [row for row in rows if row.get('electrical_energy_screening_only')]
    result.update(case_count_at_covering=len(rows),
                  electrical_energy_passes_at_covering=len(passes),
                  passing_identities=[dict(pack_resistance_ohm=row['pack_resistance_ohm'],
                                           thrust_factors=row['thrust_factors'],
                                           torque_factors=row['torque_factors'])
                                      for row in passes])
    return result


def reconcile_mass(lines, options, context):
    groups = {name: dict(group=name, screening_allowance_kg=mass, option_ids=[], partial=False,
                         unlisted_mass_option_ids=[], listed_kg=0.0)
              for name, mass in context['allowances'].items()}
    additional, unassessed = [], []
    for line in lines:
        option = options[line['option_id']]
        name, partial = split_group(option.get('replaces_screening_allowance'))
        if name in COST_ONLY_GROUPS:
            continue
        mass = line_mass(option)
        if name is None:
            if mass is None:
                unassessed.append(option['id'])
            elif mass > 0:
                additional.append(dict(option_id=option['id'], mass_kg=round(mass, 9)))
            continue
        if name not in groups:
            raise InputError('Option %s replaces unknown screening allowance %r'
                             % (option['id'], name))
        group = groups[name]
        group['option_ids'].append(option['id'])
        group['partial'] = group['partial'] or partial
        if mass is None:
            group['unlisted_mass_option_ids'].append(option['id'])
        else:
            group['listed_kg'] += mass
    rows, total = [], context['payload_kg']
    for group in groups.values():
        allowance = group['screening_allowance_kg']
        if not group['option_ids']:
            basis, estimate = 'allowance_retained_no_selected_line', allowance
        elif group['partial'] or group['unlisted_mass_option_ids']:
            basis, estimate = ('allowance_retained_partial_or_unlisted',
                               max(allowance, group['listed_kg']))
        else:
            basis, estimate = 'listed_masses', group['listed_kg']
        total += estimate
        rows.append(dict(group, basis=basis, estimate_kg=round(estimate, 9),
                         screening_allowance_kg=round(allowance, 9),
                         listed_kg=round(group['listed_kg'], 9),
                         delta_vs_allowance_kg=round(estimate - allowance, 9)))
    total += sum(item['mass_kg'] for item in additional)
    delta = total - context['baseline_mass_kg']
    return dict(indicative_vehicle_mass_kg=round(total, 9),
                screening_baseline_mass_kg=context['baseline_mass_kg'],
                delta_vs_screening_baseline_kg=round(delta, 9),
                groups=rows, additional_listed_lines=additional,
                unassessed_additional_option_ids=unassessed, complete=not unassessed,
                screening_coverage=coverage(context, delta))


def summarize(cid, merged, policy, context=None):
    configuration = merged['configurations'][cid]
    options = merged['options']
    selection = resolve(cid, merged['configurations'], options)
    zero = Decimal(0)
    rounded_totals = dict.fromkeys(CASES, zero)
    exact_totals = dict.fromkeys(CASES, zero)
    by_grade, by_basis = {}, {}
    usd_total = unresearched_total = contingency_total = zero
    lines = []
    for role, oid in selection.items():
        option = options[oid]
        amounts, usd_derived = {}, False
        for case in CASES:
            exact, usd_derived = line_amount(option, case, policy)
            rounded = exact.quantize(CENT, rounding=ROUND_CEILING)
            exact_totals[case] += exact
            rounded_totals[case] += rounded
            amounts[case] = rounded
        conservative = amounts['conservative']
        grade, basis = option['evidence_grade'], option['price_basis']
        by_grade[grade] = by_grade.get(grade, zero) + conservative
        by_basis[basis] = by_basis.get(basis, zero) + conservative
        if usd_derived:
            usd_total += conservative
        if role == 'contingency':
            contingency_total += conservative
        elif grade == 'allowance':
            unresearched_total += conservative
        mass = line_mass(option)
        lines.append(dict(
            role=role, option_id=oid, quantity=option['quantity'],
            aud={case: float(value) for case, value in amounts.items()},
            usd_derived=usd_derived, evidence_grade=grade, price_basis=basis,
            availability_class=availability_class(option),
            line_mass_kg=None if mass is None else round(mass, 9)))
    ceiling = policy['ceiling']
    totals = {case: dict(total_aud=float(rounded_totals[case]),
                         unrounded_total_aud=float(exact_totals[case].quantize(MICRO)),
                         margin_aud=float(ceiling - rounded_totals[case]),
                         below_ceiling=rounded_totals[case] < ceiling)
              for case in CASES}
    classes = {}
    for line in lines:
        classes.setdefault(line['availability_class'], []).append(line['option_id'])
    summary = dict(
        description=configuration.get('description', ''),
        defined_in=merged['configuration_source'][cid],
        base=configuration.get('base'),
        non_candidate=is_non_candidate(configuration),
        line_count=len(lines),
        totals=totals,
        conservative_aud_by_evidence_grade={k: float(v) for k, v in sorted(by_grade.items())},
        conservative_aud_by_price_basis={k: float(v) for k, v in sorted(by_basis.items())},
        conservative_usd_derived_aud=float(usd_total),
        unresearched_allowance_conservative_aud=float(unresearched_total),
        contingency_aud=float(contingency_total),
        unresearched_allowance_option_ids=[line['option_id'] for line in lines
                                           if line['evidence_grade'] == 'allowance'
                                           and line['role'] != 'contingency'],
        search_snippet_option_ids=[line['option_id'] for line in lines
                                   if line['evidence_grade'].startswith('search_snippet')],
        prior_note_option_ids=[line['option_id'] for line in lines
                               if line['evidence_grade'].startswith('prior_note')],
        availability_classes=classes,
        lines=lines)
    if context is not None:
        summary['mass_reconciliation'] = reconcile_mass(lines, options, context)
    return summary


def verification(cid, merged, policy, digests):
    summary = summarize(cid, merged, policy)
    totals, classes, options = summary['totals'], summary['availability_classes'], merged['options']
    traceable = all(options[line['option_id']].get('url')
                    and valid_date(options[line['option_id']].get('access_date'))
                    for line in summary['lines'] if line['evidence_grade'] != 'allowance')
    checks = dict(
        inputs_valid_and_merged=True,
        configuration_resolved=summary['line_count'] > 0,
        selected_priced_lines_traceable=bool(traceable),
        conservative_total_below_ceiling=totals['conservative']['below_ceiling'],
        tax_exclusive_estimate_below_ceiling=totals['tax_exclusive_estimate']['below_ceiling'],
        conservative_fx_margin_total_below_ceiling=totals['conservative_fx_margin']['below_ceiling'],
        no_unresearched_allowances=not summary['unresearched_allowance_option_ids'],
        no_search_snippet_only_prices=not summary['search_snippet_option_ids'],
        no_sold_out_or_discontinued_lines=not classes.get('sold_out_or_discontinued'),
        no_conflicting_or_variant_specific_availability=not classes.get(
            'conflicting_or_variant_specific'),
        availability_recorded_and_classified=not (classes.get('not_recorded')
                                                  or classes.get('unclassified')))
    if not checks['tax_exclusive_estimate_below_ceiling']:
        outcome = 'failed'
    elif all(checks.values()):
        outcome = 'passed'
    else:
        outcome = 'inconclusive'
    explanation = dict(
        scope='Priced-BOM arithmetic against REQ-HARDWARE-BUDGET r3 (strictly below AUD 500, '
              'excluding tax and shipping). Not procurement, mass, mission or physical acceptance.',
        configuration=cid,
        outcome_rule='failed if even the tax-exclusive estimate reaches the ceiling; passed only '
                     'if every check is true; otherwise inconclusive',
        totals_aud={case: dict(total=value['total_aud'], margin=value['margin_aud'])
                    for case, value in totals.items()},
        usd_per_aud=float(policy['usd_per_aud']), rate_date=policy['rate_date'],
        unresearched_allowances=summary['unresearched_allowance_option_ids'],
        unresearched_allowance_aud=summary['unresearched_allowance_conservative_aud'],
        contingency_aud=summary['contingency_aud'],
        search_snippet_prices=summary['search_snippet_option_ids'],
        prior_note_prices=summary['prior_note_option_ids'],
        availability_classes=classes,
        input_sha256=digests)
    return dict(outcome=outcome, checks=checks,
                explanation=json.dumps(explanation, sort_keys=True, allow_nan=False))


def cell(value):
    text = '' if value is None else str(value)
    return ' '.join(text.replace('|', '/').split())


def render_markdown(result):
    pricing, options = result['pricing'], result['options']
    out = [
        '# Electronic Hopper priced-BOM tables (generated)', '',
        'Generated by chief_priced_bom_compute.py revision %d at %s. Preliminary arithmetic only: '
        'not a Chief selection, procurement approval, assured quotation, budget-compliance '
        'acceptance or physical acceptance.' % (result['script_revision'], result['computed_at_utc']),
        '',
        'All amounts AUD. USD converted at %.4f USD per AUD (%s; rate date %s; accessed %s; minimum '
        'recorded value). Ceiling: strictly less than AUD %.2f, excluding tax and shipping. Each '
        'line total is rounded up to the next cent.' % (
            pricing['usd_per_aud_used'], pricing['rate_source'], pricing['rate_date'],
            pricing['rate_access_date'], result['budget']['ceiling_aud']),
        '', 'Input files (sha256):', '']
    out += ['- `%s`: `%s`' % (name, value) for name, value in result['input_sha256'].items()]
    out += ['', '## Configuration summary (sorted by conservative total)', '',
            '| Configuration | Conservative | Margin | Tax-exclusive estimate | Conservative +FX margin '
            '| Unresearched allowances | Contingency | Indicative mass kg | Mass change kg |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in result['ranking_by_conservative_total']:
        cid = row['configuration']
        item = result['configurations'][cid]
        totals, mass = item['totals'], item.get('mass_reconciliation')
        out.append('| %s%s | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %s | %s |' % (
            cid, ' (non-candidate)' if item['non_candidate'] else '',
            totals['conservative']['total_aud'], totals['conservative']['margin_aud'],
            totals['tax_exclusive_estimate']['total_aud'],
            totals['conservative_fx_margin']['total_aud'],
            item['unresearched_allowance_conservative_aud'], item['contingency_aud'],
            '-' if not mass else '%.4f' % mass['indicative_vehicle_mass_kg'],
            '-' if not mass else '%+.4f' % mass['delta_vs_screening_baseline_kg']))
    for cid, item in result['configurations'].items():
        totals = item['totals']
        out += ['', '## ' + cid, '',
                cell(item['description']) + ' Defined in `%s`.' % item['defined_in'], '',
                '| Role | Item | Qty | Unit price | Price basis | Conservative | Tax-exclusive estimate '
                '| Evidence | Source | Accessed | Availability class |',
                '|---|---|---:|---|---|---:|---:|---|---|---|---|']
        for line in item['lines']:
            option = options[line['option_id']]
            if option.get('url'):
                source = '[%s](%s)' % (cell(option.get('supplier') or 'source'), option['url'])
            else:
                source = 'allowance'
            out.append('| %s | %s | %s | %s %s | %s | %.2f | %.2f | %s | %s | %s | %s |' % (
                cell(line['role']), cell(option['description']), cell(option['quantity']),
                cell(option['unit_price']), option['currency'], cell(option['price_basis']),
                line['aud']['conservative'], line['aud']['tax_exclusive_estimate'],
                cell(option['evidence_grade']), source, cell(option.get('access_date')),
                cell(line['availability_class'])))
        out += ['', 'Totals: conservative %.2f (margin %.2f); tax-exclusive estimate %.2f; '
                'conservative with FX margin %.2f.' % (
                    totals['conservative']['total_aud'], totals['conservative']['margin_aud'],
                    totals['tax_exclusive_estimate']['total_aud'],
                    totals['conservative_fx_margin']['total_aud'])]
        mass = item.get('mass_reconciliation')
        if mass:
            cover = mass['screening_coverage']
            out += ['', 'Indicative mass %.4f kg, change %+.4f kg versus screening baseline %.4f kg; '
                    'covering screened added-mass case %s kg with %s electrical/energy passes of %s '
                    'cases.' % (mass['indicative_vehicle_mass_kg'],
                                mass['delta_vs_screening_baseline_kg'],
                                mass['screening_baseline_mass_kg'],
                                cover.get('covering_added_mass_case_kg'),
                                cover.get('electrical_energy_passes_at_covering'),
                                cover.get('case_count_at_covering')),
                    '', '| Allowance group | Basis | Estimate kg | Screening allowance kg | Change kg '
                    '| Lines without listed mass |', '|---|---|---:|---:|---:|---|']
            for group in mass['groups']:
                out.append('| %s | %s | %.4f | %.4f | %+.4f | %s |' % (
                    cell(group['group']), group['basis'], group['estimate_kg'],
                    group['screening_allowance_kg'], group['delta_vs_allowance_kg'],
                    cell(', '.join(group['unlisted_mass_option_ids'])) or '-'))
            if mass['unassessed_additional_option_ids']:
                out += ['', 'Additional lines without listed mass (not included): '
                        + ', '.join(mass['unassessed_additional_option_ids'])]
    out += ['', '## Limitations', ''] + ['- ' + text for text in result['limitations']]
    return NEWLINE.join(out) + NEWLINE


def compute(args):
    merged, documents = load_inputs(args.base, args.supplement)
    policy = pricing_policy(merged)
    context = screening_context(args.screening) if args.screening else None
    paths = [path for path, _ in documents]
    if args.screening:
        paths.append(Path(args.screening))
    paths.append(Path(__file__))
    digests = {path.name: digest(path) for path in paths}
    configurations = {}
    for cid in merged['configurations']:
        print('Computing ' + cid, file=sys.stderr, flush=True)
        configurations[cid] = summarize(cid, merged, policy, context)
    used = {line['option_id'] for item in configurations.values() for line in item['lines']}
    ranking = sorted(configurations, key=lambda cid: (
        configurations[cid]['totals']['conservative']['total_aud'], cid))
    conversion = merged['currency_conversion']
    result = dict(
        status='Preliminary priced-BOM arithmetic and indicative mass reconciliation; not a '
               'Chief selection, VerificationResult, procurement approval or physical acceptance',
        script_revision=SCRIPT_REVISION,
        computed_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        input_sha256=digests,
        requirements=merged['requirements'],
        budget=merged['budget'],
        pricing=dict(
            usd_per_aud_used=float(policy['usd_per_aud']), rate_date=policy['rate_date'],
            rate_source=conversion.get('source'), rate_url=conversion.get('url'),
            rate_access_date=conversion.get('access_date'),
            fx_margin_sensitivity_fraction=float(policy['fx_margin']),
            au_gst_rate=float(policy['gst']), cases=merged['tax_policy'].get('cases'),
            rounding='Each line total is rounded up to the next cent before summation; '
                     'unrounded sums are also reported.'),
        mass_convention='Line mass = quantity x (unit_mass_kg + mass_tolerance_kg). A group keeps '
                        'its screening allowance unless every selected line replacing it has a '
                        'listed mass and none is a partial replacement.',
        screening_context=None if context is None else dict(
            file=context['path'], baseline_mass_kg=context['baseline_mass_kg'],
            derived_motor_pair_mass_kg=round(context['derived_motor_pair_mass_kg'], 9),
            allowances_kg={key: round(value, 9) for key, value in context['allowances'].items()},
            added_mass_cases_kg=context['added_mass_cases_kg']),
        ranking_by_conservative_total=[dict(
            configuration=cid,
            conservative_total_aud=configurations[cid]['totals']['conservative']['total_aud'],
            margin_aud=configurations[cid]['totals']['conservative']['margin_aud'],
            below_ceiling=configurations[cid]['totals']['conservative']['below_ceiling'],
            non_candidate=configurations[cid]['non_candidate']) for cid in ranking],
        configurations=configurations,
        unused_option_ids=sorted(set(merged['options']) - used),
        options={oid: dict(option, defined_in=merged['option_source'][oid])
                 for oid, option in merged['options'].items()},
        open_items=merged['open_items'],
        evidence_updates=merged['evidence_updates'],
        rejected_or_unusable_evidence=merged['rejected_or_unusable_evidence'],
        excluded_gse=merged['excluded_gse'],
        limitations=LIMITATIONS)
    output, markdown = Path(args.output), Path(args.markdown)
    output.write_text(json.dumps(result, indent=1, allow_nan=False) + NEWLINE, encoding='utf-8')
    markdown.write_text(render_markdown(result), encoding='utf-8')
    summary = []
    for cid in ranking:
        item = configurations[cid]
        mass = item.get('mass_reconciliation') or {}
        cover = mass.get('screening_coverage') or {}
        totals = item['totals']
        summary.append(dict(
            configuration=cid, non_candidate=item['non_candidate'],
            conservative_aud=totals['conservative']['total_aud'],
            margin_aud=totals['conservative']['margin_aud'],
            tax_exclusive_estimate_aud=totals['tax_exclusive_estimate']['total_aud'],
            conservative_fx_margin_aud=totals['conservative_fx_margin']['total_aud'],
            unresearched_allowance_aud=item['unresearched_allowance_conservative_aud'],
            indicative_mass_kg=mass.get('indicative_vehicle_mass_kg'),
            mass_delta_kg=mass.get('delta_vs_screening_baseline_kg'),
            covering_added_mass_case_kg=cover.get('covering_added_mass_case_kg'),
            electrical_energy_passes_at_covering=cover.get('electrical_energy_passes_at_covering'),
            availability_flags={key: value for key, value in item['availability_classes'].items()
                                if key in ('sold_out_or_discontinued',
                                           'conflicting_or_variant_specific',
                                           'not_recorded', 'unclassified')}))
    print(json.dumps(dict(scope=result['status'],
                          usd_per_aud_used=result['pricing']['usd_per_aud_used'],
                          output=str(output.resolve()), markdown=str(markdown.resolve()),
                          configurations=summary, physical_validation='unperformed'),
                     allow_nan=False))


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='Preliminary priced-BOM computation; see the module docstring.')
    parser.add_argument('--base', required=True, help='Base hopper_priced_bom_inputs_v1 JSON')
    parser.add_argument('--supplement', action='append', default=[],
                        help='Supplement JSON; repeat to apply several in order')
    parser.add_argument('--screening', help='Propulsion screening JSON for mass reconciliation')
    parser.add_argument('--output', default='chief_priced_bom_results.json')
    parser.add_argument('--markdown', default='chief_priced_bom_tables.md')
    parser.add_argument('--verify', metavar='CONFIG_ID',
                        help='Print only a VerificationResult for one configuration')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.verify is None:
        compute(args)
        return 0
    try:
        merged, documents = load_inputs(args.base, args.supplement)
        policy = pricing_policy(merged)
        if args.verify not in merged['configurations']:
            raise InputError('Unknown configuration %r' % (args.verify,))
        digests = {path.name: digest(path) for path, _ in documents}
        digests[Path(__file__).name] = digest(Path(__file__))
        result = verification(args.verify, merged, policy, digests)
    except InputError as error:
        result = dict(outcome='failed', explanation='Input defect: %s' % (error,),
                      checks=dict(inputs_valid_and_merged=False))
    except Exception as error:  # a script defect must never yield a pass
        print('Verification program error: %r' % (error,), file=sys.stderr)
        result = dict(outcome='inconclusive',
                      explanation='Verification program error: %s: %s'
                                  % (type(error).__name__, error),
                      checks=dict(verification_program_completed=False))
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
