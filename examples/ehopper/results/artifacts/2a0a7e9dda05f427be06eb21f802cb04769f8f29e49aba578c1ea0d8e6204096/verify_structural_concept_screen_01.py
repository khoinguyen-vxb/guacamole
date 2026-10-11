"""Independent numerical checker for the PDR r9 structural sensitivity study.

Run through verify_command, not execute:
  command=['python', 'verify_structural_concept_screen_01.py']
  workdir='analysis/pdr_r9_chief'
Include current artifact Refs for this checker, analysis source, results JSON
and Markdown report in tool inputs. This program creates/modifies no files.
Stdout is exactly one VerificationResult JSON object; diagnostics use stderr.

Authorization: decision 98d7c43a499d4584a77132cd5ac96874 r1.
Digests below are file-content digests returned by tools, not Ref hashes.
Production code is parsed for literal inputs but never imported or executed.
Independent subset-partition optimization checks minimum whole-stock counts.
All acceptance here is numerical/accounting consistency ONLY, not hardware,
geometry, structural strength, supplier validation or whole-vehicle compliance.
"""
import ast
from collections import Counter
from decimal import Decimal, ROUND_CEILING
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
FILES = {
    'source': ('structural_concept_screen_01.py', '9344a06c4f0f974011322c18072163b0b5032dc8fdee1248755a7a9a4f970d31'),
    'results': ('structural_concept_screen_01_results.json', 'a76d5180f443acfb3539b29bd7b01dbe0513d5afba9373f5655622e6eaba6389'),
    'report': ('structural_concept_screen_01_report.md', 'd7fca34f2b23571c3ed8d927fd490b73df94a3f4368e25f3fed758f929db33ca'),
}
CHECKS = {}
DIAG = {'maximum_absolute_errors_by_unit': {}, 'numerical_mismatches': []}
REL_TOL = 1e-10
ABS_TOL = {'mm': 1e-8, 'kg': 1e-12, 'm2': 1e-15, 'm4': 1e-20,
           'N m2': 1e-10, 'kg/m': 1e-12, 'm/N': 1e-12}


def check(name, condition):
    if name in CHECKS:
        raise ValueError('Duplicate check name')
    CHECKS[name] = bool(condition)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def near(actual, expected, unit, label):
    valid = number(actual)
    if valid:
        error = abs(actual - expected)
        previous = DIAG['maximum_absolute_errors_by_unit'].get(unit, 0.0)
        DIAG['maximum_absolute_errors_by_unit'][unit] = max(previous, error)
        valid = math.isclose(actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL[unit])
    if not valid and len(DIAG['numerical_mismatches']) < 30:
        DIAG['numerical_mismatches'].append({'field': label, 'actual': actual,
                                           'expected': expected, 'unit': unit})
    return valid


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Nonfinite JSON constant')


def literal_inputs(source_text):
    tree = ast.parse(source_text)
    wanted = {'ACCESS_DATE', 'SOURCES', 'INPUTS', 'CONCEPTS', 'EXCLUSIONS'}
    found = {}

    class ResolveAccessDate(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == 'ACCESS_DATE' and 'ACCESS_DATE' in found:
                return ast.copy_location(ast.Constant(found['ACCESS_DATE']), node)
            return node

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in wanted:
                if target.id in found:
                    raise ValueError('Repeated input definition')
                value_node = ResolveAccessDate().visit(node.value)
                found[target.id] = ast.literal_eval(value_node)
    if set(found) != wanted:
        raise ValueError('Missing literal input definitions')
    return found


def minimum_stocks(cuts, stock, kerf, trim):
    """Independent exhaustive subset-partition dynamic programming.

    Decimal arithmetic prevents floating-point tolerance from admitting cuts
    exceeding capacity. A stock loses two end trims; every part consumes a kerf.
    This is intentionally different from the production recursive bin search.
    """
    if not cuts:
        return 0
    capacity = Decimal(str(stock)) - 2 * Decimal(str(trim))
    weights = [Decimal(str(x)) + Decimal(str(kerf)) for x in cuts]
    if capacity <= 0 or any(w <= 0 or w > capacity for w in weights):
        raise ValueError('Infeasible individual cut')
    n = len(weights)
    if n > 12:
        raise ValueError('Checker subset bound exceeded')
    size = 1 << n
    loads = [Decimal(0)] * size
    for mask in range(1, size):
        bit = mask & -mask
        loads[mask] = loads[mask ^ bit] + weights[bit.bit_length() - 1]
    dp = [n + 1] * size
    dp[0] = 0
    for mask in range(1, size):
        anchor = mask & -mask
        subset = mask
        while subset:
            if subset & anchor and loads[subset] <= capacity:
                dp[mask] = min(dp[mask], 1 + dp[mask ^ subset])
            subset = (subset - 1) & mask
    return dp[-1]


def verify():
    paths = {}
    initial_hashes = {}
    for key, (name, expected_hash) in FILES.items():
        path = ROOT / name
        regular = path.is_file() and not path.is_symlink()
        check('binding.' + key + '.regular_file', regular)
        if not regular:
            raise FileNotFoundError('Required published input unavailable')
        paths[key] = path
        initial_hashes[key] = digest(path)
        check('binding.' + key + '.content_digest', initial_hashes[key] == expected_hash)
    DIAG['actual_content_digests'] = initial_hashes
    if any(initial_hashes[k] != FILES[k][1] for k in FILES):
        return False  # Reject altered inputs without interpreting their contents.

    source = literal_inputs(paths['source'].read_text(encoding='utf-8'))
    data = json.loads(paths['results'].read_text(encoding='utf-8'),
                      object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)
    report = paths['report'].read_text(encoding='utf-8')
    check('schema', data.get('schema') == 'pdr_r9_structural_concept_sensitivity_v1')
    status = 'Analysis only; independent verification and Chief selection pending'
    check('analysis_status_preserved', data.get('status') == status and status in report)
    check('source_digest_recorded', data.get('analysis_program_sha256') == initial_hashes['source'])
    for field, literal_name in (('inputs', 'INPUTS'), ('sources', 'SOURCES'),
                                ('concepts', 'CONCEPTS'), ('excluded_unresolved_items', 'EXCLUSIONS')):
        check('source_output.' + field, data.get(field) == source[literal_name])
    check('source_dates', source['ACCESS_DATE'] == '2026-10-11'
          and all(s.get('access_date') == source['ACCESS_DATE'] for s in data['sources']))
    check('report_source_links', all(s['citation'] in report and s['url'] in report
                                     for s in source['SOURCES']))
    check('report_exclusions', all('- ' + s in report for s in source['EXCLUSIONS']))
    check('report_limitations', isinstance(data.get('limitations'), list)
          and len(data['limitations']) >= 8
          and all('- ' + s in report for s in data['limitations']))

    check('checker.partition_fixtures',
          minimum_stocks([], 10, 0, 0) == 0
          and minimum_stocks([6, 6, 4, 4], 10, 0, 0) == 2
          and minimum_stocks([5, 5], 10, 0.1, 0) == 2
          and minimum_stocks([5, 5], 10, 0, 0.1) == 2
          and minimum_stocks([550, 220, 220], 1000, 3, 5) == 2
          and minimum_stocks([550, 550, 550, 150, 150], 1000, 3, 5) == 3)

    inputs = source['INPUTS']
    t = inputs['tube']
    p = inputs['printed_material']
    # Independent mm-based section calculation, converted explicitly to SI.
    radius = t['outer_diameter_mm'] / 2
    inner_radius = radius - t['wall_mm']
    check('tube_section.physical_dimensions', 0 < inner_radius < radius)
    area_mm2 = math.pi * (radius**2 - inner_radius**2)
    moment_mm4 = math.pi * (radius**4 - inner_radius**4) / 4
    modulus_n_mm2 = t['assumed_elastic_modulus_pa'] / 1e6
    section = data['tube_section_derived']
    section_expectations = [
        ('cross_section_area_m2', area_mm2 / 1e6, 'm2'),
        ('area_second_moment_m4', moment_mm4 / 1e12, 'm4'),
        ('assumed_material_EI_n_m2', modulus_n_mm2 * moment_mm4 / 1e6, 'N m2'),
        ('mass_per_length_kg_m', area_mm2 * t['assumed_density_kg_m3'] / 1e6, 'kg/m'),
    ]
    for field, expected, unit in section_expectations:
        check('section.' + field, near(section.get(field), expected, unit, field))

    sources = {s['id']: s for s in source['SOURCES']}
    tube_price = Decimal(str(sources['STR-S01']['displayed_price']))
    spool_price = Decimal(str(sources['STR-S03']['displayed_price']))
    check('price_basis_explicit', sources['STR-S01']['currency'] == 'AUD'
          and sources['STR-S03']['currency_for_sensitivity'] == 'AUD'
          and 'Inferred' in sources['STR-S03']['currency_status']
          and 'No tax deduction' in inputs['price_basis']
          and 'Tax is not deducted' in report)

    expected_cases = []
    for cid in ('A_SINGLE_SPINE', 'B_THREE_RAILS'):
        for main, fork, volume in itertools.product(inputs['main_member_lengths_mm'],
                inputs['fork_upright_lengths_mm'], inputs['hybrid_printed_net_volume_cm3']):
            expected_cases.append((cid, main, fork, volume))
    expected_cases += [('C_PRINTED_TRUSS', None, None, v)
                       for v in inputs['all_printed_net_volume_cm3']]
    rows = data['cases']
    check('case_count', isinstance(rows, list) and len(rows) == len(expected_cases) == 57)
    observed_cases = [(r['concept_id'], r['main_member_length_mm'],
                       r['fork_upright_length_mm'], r['assumed_printed_net_volume_cm3']) for r in rows]
    check('case_coverage_and_order', observed_cases == expected_cases)
    check('case_identity_unique', len({r['case_id'] for r in rows}) == len(rows))
    if len(rows) != len(expected_cases) or observed_cases != expected_cases:
        return False

    expected_table = []
    for index, (row, definition) in enumerate(zip(rows, expected_cases), 1):
        cid, main, fork, volume = definition
        name = '%s_%02d' % (cid, index)
        check(name + '.identity', row['case_id'] == name)
        count = source['CONCEPTS'][cid]['main_member_count']
        cuts = [main] * count + [fork] * 2 if count else []
        total_length = sum(cuts)
        tube_mass = area_mm2 * total_length * t['assumed_density_kg_m3'] / 1e9
        print_mass = volume * p['assumed_density_kg_m3'] / 1e6
        partial_mass = tube_mass + print_mass
        consumed = print_mass * p['assumed_purchase_consumption_multiplier']
        consumed_decimal = (Decimal(str(volume)) * Decimal(str(p['assumed_density_kg_m3']))
                            / Decimal('1000000') * Decimal(str(p['assumed_purchase_consumption_multiplier'])))
        spools = int((consumed_decimal / Decimal(str(p['nominal_spool_mass_kg']))).to_integral_value(rounding=ROUND_CEILING))
        optimum = minimum_stocks(cuts, t['stock_length_mm'],
                                 t['assumed_kerf_per_finished_part_mm'],
                                 t['assumed_end_trim_each_end_per_stock_mm'])
        check(name + '.whole_purchase_counts',
              type(row['whole_tube_lengths_purchased']) is int
              and row['whole_tube_lengths_purchased'] == optimum
              and type(row['whole_filament_spools_purchased']) is int
              and row['whole_filament_spools_purchased'] == spools)
        expected_cost = (optimum * tube_price + spools * spool_price).quantize(Decimal('0.01'))
        actual_cost = row['displayed_price_material_subtotal_assuming_AUD']
        check(name + '.displayed_material_subtotal', number(actual_cost)
              and Decimal(str(actual_cost)) == expected_cost)
        numerical = []
        for field, expected, unit in [
            ('tube_finished_length_mm', total_length, 'mm'),
            ('estimated_installed_tube_mass_kg', tube_mass, 'kg'),
            ('estimated_installed_print_mass_kg', print_mass, 'kg'),
            ('partial_structural_mass_kg', partial_mass, 'kg'),
            ('estimated_consumed_filament_including_waste_kg', consumed, 'kg'),
        ]:
            numerical.append(near(row.get(field), expected, unit, name + '.' + field))
        compliance_field = 'single_bare_main_tube_cantilever_tip_compliance_m_per_n'
        if count:
            compliance = main**3 / (3 * modulus_n_mm2 * moment_mm4) / 1000
            numerical.append(near(row.get(compliance_field), compliance, 'm/N', name + '.compliance'))
        else:
            numerical.append(row.get(compliance_field) is None)
        check(name + '.mass_length_and_bare_tube_arithmetic', all(numerical))

        packing = row['tube_stock_packing']
        flat = [cut for stock in packing for cut in stock['finished_cuts_mm']]
        check(name + '.cut_conservation',
              all(number(v) and v > 0 for v in flat) and Counter(flat) == Counter(cuts))
        check(name + '.optimal_stock_partition', len(packing) == optimum)
        packing_valid = []
        for stock in packing:
            pieces = stock['finished_cuts_mm']
            kerf = len(pieces) * t['assumed_kerf_per_finished_part_mm']
            trims = 2 * t['assumed_end_trim_each_end_per_stock_mm']
            remainder = t['stock_length_mm'] - sum(pieces) - kerf - trims
            packing_valid.append(bool(pieces) and remainder >= 0)
            for field, expected in [('kerf_allowance_mm', kerf),
                                    ('end_trim_allowance_mm', trims),
                                    ('remaining_offcut_mm', remainder)]:
                packing_valid.append(near(stock.get(field), expected, 'mm', name + '.' + field))
        check(name + '.stock_capacity_and_allowances', all(packing_valid))
        check(name + '.unresolved_vehicle_and_physical_results_preserved',
              all(field in row and row[field] is None for field in
                  ('assembly_stiffness', 'complete_vehicle_mass_kg', 'complete_vehicle_ex_tax_cost_aud'))
              and row.get('geometry_acceptance') == 'unperformed'
              and row.get('structural_load_acceptance') == 'unperformed')
        expected_table.append('| %s | %s / %s | %.1f | %d | %d | %.6f | %.2f |' %
                              (name, main, fork, volume, optimum, spools, partial_mass, float(expected_cost)))

    observed_table = [line for line in report.splitlines()
                      if line.startswith(('| A_SINGLE_SPINE_', '| B_THREE_RAILS_', '| C_PRINTED_TRUSS_'))]
    check('report_table_independent_recalculation', observed_table == expected_table)
    for key, path in paths.items():
        check('binding.' + key + '.unchanged', digest(path) == initial_hashes[key])
    DIAG['case_count_checked'] = len(rows)
    DIAG['relative_tolerance'] = REL_TOL
    DIAG['absolute_tolerances_by_unit'] = ABS_TOL
    DIAG['scope'] = 'Published numerical study only; no independent supplier or physical validation.'
    return True


def main():
    exception = None
    try:
        completed = verify()
    except Exception as exc:
        completed = False
        exception = type(exc).__name__
        print('Structural study verification incomplete: ' + exception, file=sys.stderr)
    CHECKS['verification_completed'] = completed
    failed = [key for key, value in CHECKS.items() if not value]
    outcome = 'inconclusive' if exception else ('passed' if not failed else 'failed')
    explanation = (
        'Scope: numerical consistency of the hash-bound structural sensitivity source, '
        '57-case results and Markdown report only. Checks independently recompute section '
        'properties, partial installed mass, consumed filament, whole purchases, displayed-price '
        'subtotals and bare-tube compliance. Exhaustive subset partitions independently check '
        'minimum tube-stock counts including kerf and end trims. Supplier provenance is checked '
        'for faithful retention, not external truth or freshness. Printed volumes and properties '
        'remain assumptions. No concept selection, equivalent structural performance, CAD clearance, '
        'strength, complete vehicle cost/mass, fabrication or flight acceptance is established. '
        'Failed/incomplete checks: ' + (', '.join(failed) if failed else 'none')
        + ('. Incomplete due to ' + exception if exception else '')
    )
    print(json.dumps(DIAG, sort_keys=True, allow_nan=False), file=sys.stderr)
    print(json.dumps({'outcome': outcome, 'explanation': explanation, 'checks': CHECKS},
                     sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
