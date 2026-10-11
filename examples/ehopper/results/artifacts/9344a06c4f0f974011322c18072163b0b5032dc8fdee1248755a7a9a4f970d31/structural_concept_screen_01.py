"""PDR-only structural material/stock sensitivity study; NOT verification.

Authorization: decision 98d7c43a499d4584a77132cd5ac96874 r1.
Common-gimbal architecture: decision 84ef41fdd3fd4266ada43df2ace64a48 r1.
No structural concept, vehicle dimensions or material is selected here.

Future execution: execute with command ['python', 'structural_concept_screen_01.py']
and workdir analysis/pdr_r9_chief. Declare BOTH outputs:
  analysis/pdr_r9_chief/structural_concept_screen_01_results.json
  analysis/pdr_r9_chief/structural_concept_screen_01_report.md

Standard-library analysis only. No CAD, supplied checkout or original document
is modified. A separate retained verify_command checker remains required.
"""
import hashlib
import itertools
import json
import math
from pathlib import Path

ACCESS_DATE = '2026-10-11'
OUT = Path(__file__).resolve().parent
RESULT = OUT / 'structural_concept_screen_01_results.json'
REPORT = OUT / 'structural_concept_screen_01_report.md'

SOURCES = [
    {
        'id': 'STR-S01',
        'citation': '[Bunnings Metal Mate tube](https://www.bunnings.com.au/metal-mate-12-x-1mm-1m-aluminium-rcr-round-tube_p1067750)',
        'url': 'https://www.bunnings.com.au/metal-mate-12-x-1mm-1m-aluminium-rcr-round-tube_p1067750',
        'access_date': ACCESS_DATE,
        'method': 'Provider-side HTML text retrieval; images not inspected',
        'locator': 'Product title, I/N and price, retrieved lines 430-441; availability 446-464; alloy claim 467-473',
        'product_id': '1067750',
        'nominal_outer_diameter_mm': 12.0,
        'nominal_wall_mm': 1.0,
        'nominal_stock_length_mm': 1000.0,
        'alloy_temper_supplier_claim': '6063-T5',
        'displayed_price': 5.23,
        'currency': 'AUD',
        'tax_basis': 'GST-inclusive according to STR-S02',
        'purchase_unit': 'one 1000 mm stock length',
        'availability': 'Requires store/postcode selection; not established',
        'limitations': 'Retrieved page was marked crawled last year. Access date is not a supplier quote date. Historical AUD 5.94 is not reused as this retrieval. Dimensions/tolerances and properties are not independently measured.'
    },
    {
        'id': 'STR-S02',
        'citation': '[Bunnings terms of sale](https://www.bunnings.com.au/terms-conditions/online-and-special-order)',
        'url': 'https://www.bunnings.com.au/terms-conditions/online-and-special-order',
        'access_date': ACCESS_DATE,
        'method': 'Provider-side indexed supplier-page text',
        'locator': 'Section 3, Pricing and payment, clause c; page states updated 13 March 2026',
        'finding': 'Displayed product prices are in Australian dollars and include GST.'
    },
    {
        'id': 'STR-S03',
        'citation': '[Jaycar TL6452 PETG](https://www.jaycar.com.au/slic3d-petg-filament-grey-1-75mm-1kg/p/TL6452)',
        'url': 'https://www.jaycar.com.au/slic3d-petg-filament-grey-1-75mm-1kg/p/TL6452',
        'access_date': ACCESS_DATE,
        'method': 'Provider-side indexed product-page text; direct open and alternate storefront open returned Internal Error',
        'locator': 'Product title, CAT.NO TL6452, MPN 50.203.0391, displayed price and specifications',
        'displayed_price': 17.95,
        'displayed_currency_symbol': '$',
        'currency_for_sensitivity': 'AUD',
        'currency_status': 'Inferred from Jaycar Australia storefront; explicit currency-code statement not retrieved',
        'tax_basis': 'GST-inclusive according to STR-S04',
        'purchase_unit': 'one nominal 1 kg filament spool',
        'filament_diameter_mm': 1.75,
        'nominal_filament_mass_kg': 1.0,
        'availability': 'Not established; add-to-cart text is not stock confirmation',
        'limitations': 'Indexed page marked crawled last month. No density, mechanical-property or print-process certification retrieved. Spool/package dimensions are not printed-part geometry.'
    },
    {
        'id': 'STR-S04',
        'citation': '[Jaycar terms and conditions](https://help.jaycar.com.au/hc/en-us/articles/22466779698713-Terms-conditions)',
        'url': 'https://help.jaycar.com.au/hc/en-us/articles/22466779698713-Terms-conditions',
        'access_date': ACCESS_DATE,
        'method': 'Provider-side indexed supplier-page text',
        'locator': 'Prices section; page states updated 13 March 2025',
        'finding': 'Australian site prices include GST; supplier reserves the right to change prices.'
    }
]

INPUTS = {
    'status': 'Exploratory sensitivity inputs, not selected dimensions or measured properties',
    'tube': {
        'outer_diameter_mm': 12.0, 'wall_mm': 1.0, 'stock_length_mm': 1000.0,
        'dimension_source': 'STR-S01',
        'assumed_density_kg_m3': 2700.0,
        'assumed_elastic_modulus_pa': 69e9,
        'property_status': 'Uncertified generic analysis assumptions, not product test evidence',
        'assumed_kerf_per_finished_part_mm': 3.0,
        'assumed_end_trim_each_end_per_stock_mm': 5.0
    },
    'printed_material': {
        'assumed_density_kg_m3': 1270.0,
        'nominal_spool_mass_kg': 1.0,
        'spool_source': 'STR-S03',
        'assumed_purchase_consumption_multiplier': 1.25,
        'accounting': 'Full-density net solid volume; no infill discount. Extra 25 percent for supports/waste is consumed material, not installed flight mass.'
    },
    'main_member_lengths_mm': [350.0, 450.0, 550.0],
    'fork_upright_lengths_mm': [150.0, 180.0, 220.0],
    'hybrid_printed_net_volume_cm3': [200.0, 260.0, 320.0],
    'all_printed_net_volume_cm3': [260.0, 320.0, 380.0],
    'volume_scope': 'Assumed total custom printed load-carrying structure, gimbal frames, equipment retention features and landing legs; commercial bearings, fasteners, straps, servos and linkages excluded and unresolved.',
    'comparison_warning': 'Shared lengths and volume sweeps do not imply equal stiffness, strength, mounting capacity or rotor clearance. Volumes are NOT measured CAD volumes.',
    'price_basis': 'Whole stock/spools at retrieved displayed prices. No tax deduction or shipping added. Jaycar AUD inference is explicit. Complete ex-tax vehicle budget remains unknown.'
}

CONCEPTS = {
    'A_SINGLE_SPINE': {
        'main_member_count': 1,
        'description': 'One load-carrying tube spine below the lower rotor; two outboard fork uprights route loads around the swept rotor to the common gimbal.',
        'issues': ['Spine clamp torsion/slip', 'Printed fork bending and creep', 'Positive axial/rotation retention', 'Full-motion lower-rotor bypass']
    },
    'B_THREE_RAILS': {
        'main_member_count': 3,
        'description': 'Three longitudinal tube rails with printed connecting nodes/plates and two outboard fork uprights.',
        'issues': ['Additional joints and assembly alignment', 'Separated rails provide composite stiffness only with adequate shear transfer', 'Full-motion lower-rotor bypass']
    },
    'C_PRINTED_TRUSS': {
        'main_member_count': 0,
        'description': 'Open printed truss with integrated mounting nodes, outboard fork and landing structure; no enclosing shell.',
        'issues': ['Layer-direction strength', 'Joint/segmentation stiffness', 'Creep and temperature sensitivity', 'Print-bed and process dependence', 'Full-motion lower-rotor bypass']
    }
}

EXCLUSIONS = [
    'Installed propulsion, battery, ESCs, controller/sensors, receiver and wiring',
    'Commercial servos, bearings, linkage hardware, hubs/adapters and fasteners',
    'Additional retention straps/pads, connectors and power distribution',
    'Reusable printer, cutting/drilling tools, assembly and measurement equipment, priced separately',
    'No assumed ownership, free components or zero-valued missing BOM rows'
]


def exact_stock_packing(cuts_mm, stock_mm, kerf_mm, end_trim_mm):
    """Minimum stock count under this conservative one-dimensional cut model.

    Each part consumes its finished length plus one kerf, including the last
    part. Every used stock loses two end trims. Exhaustive bin-count search
    with symmetry pruning; no claim about manufacturing tolerances or defects.
    """
    if not cuts_mm:
        return []
    capacity = stock_mm - 2.0 * end_trim_mm
    parts = sorted(cuts_mm, reverse=True)
    if capacity <= 0 or any(x <= 0 or x + kerf_mm > capacity for x in parts):
        raise ValueError('Cut cannot fit the assumed usable stock')
    lower = max(1, math.ceil(sum(x + kerf_mm for x in parts) / capacity))
    for count in range(lower, len(parts) + 1):
        bins = [[] for _ in range(count)]
        used = [0.0] * count

        def place(index):
            if index == len(parts):
                return True
            part = parts[index]
            footprint = part + kerf_mm
            seen = set()
            for j in range(count):
                if used[j] in seen:
                    continue
                seen.add(used[j])
                if used[j] + footprint <= capacity + 1e-9:
                    used[j] += footprint
                    bins[j].append(part)
                    if place(index + 1):
                        return True
                    bins[j].pop()
                    used[j] -= footprint
            return False

        if place(0):
            return [
                {'finished_cuts_mm': row,
                 'kerf_allowance_mm': len(row) * kerf_mm,
                 'end_trim_allowance_mm': 2.0 * end_trim_mm,
                 'remaining_offcut_mm': stock_mm - sum(row) - len(row) * kerf_mm - 2.0 * end_trim_mm}
                for row in bins if row
            ]
    raise RuntimeError('No packing found')


def compute():
    t = INPUTS['tube']
    p = INPUTS['printed_material']
    od = t['outer_diameter_mm'] * 1e-3
    inner = od - 2.0 * t['wall_mm'] * 1e-3
    if not 0 < inner < od:
        raise ValueError('Invalid hollow tube section')
    area = math.pi * (od**2 - inner**2) / 4.0
    second_moment = math.pi * (od**4 - inner**4) / 64.0
    ei = t['assumed_elastic_modulus_pa'] * second_moment
    rows = []
    for cid in ('A_SINGLE_SPINE', 'B_THREE_RAILS', 'C_PRINTED_TRUSS'):
        count = CONCEPTS[cid]['main_member_count']
        cases = (itertools.product(INPUTS['main_member_lengths_mm'], INPUTS['fork_upright_lengths_mm'], INPUTS['hybrid_printed_net_volume_cm3'])
                 if count else [(None, None, v) for v in INPUTS['all_printed_net_volume_cm3']])
        for main_length, fork_length, volume_cm3 in cases:
            cuts = [main_length] * count + [fork_length] * 2 if count else []
            packing = exact_stock_packing(cuts, t['stock_length_mm'], t['assumed_kerf_per_finished_part_mm'], t['assumed_end_trim_each_end_per_stock_mm'])
            installed_tube_mass = area * sum(cuts) * 1e-3 * t['assumed_density_kg_m3']
            installed_print_mass = volume_cm3 * 1e-6 * p['assumed_density_kg_m3']
            consumed_filament = installed_print_mass * p['assumed_purchase_consumption_multiplier']
            spools = math.ceil(consumed_filament / p['nominal_spool_mass_kg'])
            rows.append({
                'case_id': '%s_%02d' % (cid, len(rows) + 1),
                'concept_id': cid,
                'main_member_length_mm': main_length,
                'fork_upright_length_mm': fork_length,
                'assumed_printed_net_volume_cm3': volume_cm3,
                'tube_finished_length_mm': sum(cuts),
                'tube_stock_packing': packing,
                'whole_tube_lengths_purchased': len(packing),
                'whole_filament_spools_purchased': spools,
                'estimated_consumed_filament_including_waste_kg': consumed_filament,
                'estimated_installed_tube_mass_kg': installed_tube_mass,
                'estimated_installed_print_mass_kg': installed_print_mass,
                'partial_structural_mass_kg': installed_tube_mass + installed_print_mass,
                'displayed_price_material_subtotal_assuming_AUD': round(len(packing) * SOURCES[0]['displayed_price'] + spools * SOURCES[2]['displayed_price'], 2),
                'single_bare_main_tube_cantilever_tip_compliance_m_per_n': (main_length * 1e-3)**3 / (3.0 * ei) if count else None,
                'assembly_stiffness': None,
                'complete_vehicle_mass_kg': None,
                'complete_vehicle_ex_tax_cost_aud': None,
                'geometry_acceptance': 'unperformed',
                'structural_load_acceptance': 'unperformed'
            })
    return {
        'schema': 'pdr_r9_structural_concept_sensitivity_v1',
        'status': 'Analysis only; independent verification and Chief selection pending',
        'sources': SOURCES,
        'inputs': INPUTS,
        'concepts': CONCEPTS,
        'excluded_unresolved_items': EXCLUSIONS,
        'tube_section_derived': {
            'cross_section_area_m2': area,
            'area_second_moment_m4': second_moment,
            'assumed_material_EI_n_m2': ei,
            'mass_per_length_kg_m': area * t['assumed_density_kg_m3'],
            'scope': 'Ideal unperforated tube only, not joined structure or gimbal stiffness'
        },
        'cases': rows,
        'limitations': [
            'No automatic ranking: assumed printed volumes do not prove comparable structural function.',
            'No historical travel, lever arm, mass or rotor spacing is adopted.',
            'The spine/rails must end below the complete lower-rotor swept envelope. Forks, cross-members, fasteners and wiring require actual CAD clearance checks over selected motion.',
            'Servo stall rating is not continuous torque; actual gimbal loads, rotor momentum and response remain unresolved.',
            'No yield, buckling, fatigue, joint, landing-impact or printed-material qualification is computed.',
            'Partial structural masses and material costs must not be reported as whole-vehicle compliance.',
            'No current product drawing or image was interpreted. Stock and property confirmation remain necessary.',
            'No PDR/CDR acceptance, fabrication permission or flight validation is implied.'
        ]
    }


def main():
    for path in (RESULT, REPORT):
        if path.exists() or path.is_symlink():
            raise FileExistsError('Preserve existing result; use a revised output stem: ' + str(path))
    data = compute()
    data['analysis_program_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    lines = [
        '# PDR r9 structural concept sensitivity', '', data['status'], '',
        'All lengths, volume allowances and material properties used for sizing are explicitly provisional. No concept is selected.', '',
        '## Sources', ''
    ]
    for source in SOURCES:
        lines.extend([source['id'] + ': ' + source['citation'] + ' — accessed ' + source['access_date'] + '.', source['method'] + '. Locator: ' + source['locator'] + '.', ''])
    lines.extend([
        '## Computed cases', '',
        'Material price column uses whole stock/spools and displayed prices; Jaycar AUD is inferred. Tax is not deducted. This is not the complete ex-tax vehicle budget.', '',
        '| Case | Main / fork length, mm | Printed volume, cm3 | Tube stocks | Spools | Partial mass, kg | Displayed-price subtotal, assumed AUD |',
        '|---|---:|---:|---:|---:|---:|---:|'
    ])
    for row in data['cases']:
        lines.append('| %s | %s / %s | %.1f | %d | %d | %.6f | %.2f |' % (
            row['case_id'], row['main_member_length_mm'], row['fork_upright_length_mm'], row['assumed_printed_net_volume_cm3'],
            row['whole_tube_lengths_purchased'], row['whole_filament_spools_purchased'], row['partial_structural_mass_kg'],
            row['displayed_price_material_subtotal_assuming_AUD']))
    lines.extend(['', '## Excluded and unresolved accounting', ''] + ['- ' + x for x in EXCLUSIONS])
    lines.extend(['', '## Limitations and next gates', ''] + ['- ' + x for x in data['limitations']])
    lines.extend(['', 'Next: inspect these actual results, retain an independent artifact-bound checker, then record a provisional structural concept decision. Replace volume allowances with CAD measurements before integrated vehicle sizing.', ''])
    with RESULT.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(data, indent=2, allow_nan=False) + '\n')
    with REPORT.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines))
    print(json.dumps({'status': data['status'], 'case_count': len(data['cases']), 'outputs': [RESULT.name, REPORT.name]}, allow_nan=False))


if __name__ == '__main__':
    main()
