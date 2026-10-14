"""Export the bounded, unselected PDR-r12 refinement experiment.

Run subsequently through freecad_run(headless=True). Include this driver,
its adapter, the original geometry/configuration/export-helper artifacts,
the historical native artifact and governing decisions in tool inputs.
Declare all eight outputs under OUT_REL:
  physical_integration_unrefined_02.FCStd
  physical_integration_unrefined_02_physical.step
  physical_integration_unrefined_02_arrangement.svg
  component_interface_ledger_02.json
  generation_observations_02.json
  drawing_diagnostics_02.json
  targeted_refinement_observations_02.json
  output_manifest_02.json

The inspected original driver supplies observation and rendering helpers;
its main function is never called. Only the newly generated SVG's title and
diagnostics filename are relabelled. No original source or historical output
is rewritten. The adapter alone applies the selected Refine=False changes.
Generation observations are not independent verification or acceptance.
"""

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

import FreeCAD as App
import Part

SELF = 'cad/pdr_r12_chief/build_physical_integration_unrefined_20261014_02.py'
OUT_REL = 'cad/pdr_r12_chief/physical_integration_unrefined_20261014_02'
DECISION = '32c12da080c74e29afe522cbfc9525c3 revision 1'
FILES = {
    'adapter': (
        'cad/pdr_r12_chief/physical_integration_geometry_unrefined_20261014_02.py',
        'fd13dbc2eeed003678c1aa9fbc93dd11fad85685b4113128ef2170df0352d0be'),
    'export_helpers': (
        'cad/pdr_r12_chief/build_physical_integration_prototype_20261014_01.py',
        'd9a929d840a83343e8b457a916d0d0b0029f2d2286b9b64f74b8987cc5650253'),
    'original_geometry': (
        'cad/pdr_r12_chief/physical_integration_geometry_20261014_01.py',
        'c8e74b814c41899236df91d885abc876c5e0f950a514f19d4719a61a0aeee7e6'),
    'configuration': (
        'cad/pdr_r12_chief/physical_integration_prototype_config_20261014_01.json',
        'be78fc14b24b01cd824e1bf90625c415176b27ecae2dca26dff8ac790de1e9b0'),
    'historical_native': (
        'cad/pdr_r12_chief/physical_integration_prototype_20261014_01/physical_integration_prototype_01.FCStd',
        '45010bcd928d38cd580f8ded06273e561d290a671d7ecfb771943825fee2fa16')
}
OUTPUT_NAMES = [
    'physical_integration_unrefined_02.FCStd',
    'physical_integration_unrefined_02_physical.step',
    'physical_integration_unrefined_02_arrangement.svg',
    'component_interface_ledger_02.json',
    'generation_observations_02.json',
    'drawing_diagnostics_02.json',
    'targeted_refinement_observations_02.json',
    'output_manifest_02.json'
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounded(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path escaped sandbox: ' + relative)
    return path


def identity(root, path):
    return {'path': str(path.relative_to(root)), 'sha256': sha(path)}


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def load_definitions(path, name):
    namespace = {'__name__': name, '__file__': str(path)}
    exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
    return namespace


def relabel_new_drawing(path):
    # This path is a fresh output, never an input or historical drawing.
    replacements = [
        ('PDR-r12 physical-integration prototype 01 — UNSELECTED',
         'PDR-r12 physical-integration unrefined prototype 02 — UNSELECTED'),
        ('drawing_diagnostics_01.json', 'drawing_diagnostics_02.json')
    ]
    text = path.read_text(encoding='utf-8')
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError('Unexpected renderer label: ' + old)
        text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
    return [{'original': old, 'replacement': new} for old, new in replacements]


def main():
    root = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
    paths = {key: bounded(root, value[0]) for key, value in FILES.items()}
    own = bounded(root, SELF)
    out = bounded(root, OUT_REL)
    if out.exists():
        raise FileExistsError('Preserve previous or partial output directory: ' + str(out))
    for key, path in paths.items():
        if sha(path) != FILES[key][1]:
            raise ValueError('Pinned input changed: ' + key)

    def fingerprints():
        rows = {key: identity(root, path) for key, path in paths.items()}
        rows['driver'] = identity(root, own)
        return rows

    before = fingerprints()
    cfg = json.loads(paths['configuration'].read_text(encoding='utf-8'))
    helpers = load_definitions(paths['export_helpers'], 'pdr_r12_export_helpers_only')
    adapter = load_definitions(paths['adapter'], 'pdr_r12_unrefined_adapter_only')
    out.mkdir(parents=True)
    doc = None
    try:
        built = adapter['build_document'](root)
        doc = built['document']
        physical = built['physical_objects']
        references = built['moving_reference_objects']
        names = [obj.Name for obj in physical]
        reference_names = [obj.Name for obj in references]
        if len(names) != 58 or len(set(names)) != 58:
            raise ValueError('Expected 58 separately owned physical components')
        if len(reference_names) != len(set(reference_names)):
            raise ValueError('Duplicate reference ownership')
        if set(names).intersection(reference_names):
            raise ValueError('Reference geometry included in physical ownership')
        group_names = [obj.Name for obj in doc.getObject('PhysicalComponents').Group]
        if len(group_names) != 58 or set(group_names) != set(names):
            raise ValueError('Native physical group differs from export inventory')
        if any(not obj.CountsInStructuralSubtotal for obj in physical):
            raise ValueError('Non-mass object in physical export list')
        if any(obj.CountsInStructuralSubtotal for obj in references):
            raise ValueError('Moving reference incorrectly marked for mass')
        if built['configuration_sha256'] != FILES['configuration'][1]:
            raise ValueError('Adapter returned an unexpected configuration')
        refinement = built['targeted_refinement_observations']
        if refinement['decision'] != DECISION:
            raise ValueError('Unexpected refinement authority')
        if refinement['only_selected_refinement_inputs_changed'] is not True:
            raise ValueError('Adapter did not retain the bounded construction contract')
        if refinement['physical_component_names'] != names:
            raise ValueError('Adapter observation inventory differs')

        # Retain the regeneration observations even if later export fails.
        # This remains construction evidence, not independent verification.
        dump(out / OUTPUT_NAMES[6], refinement)
        doc.recompute()
        inventory = helpers['initial_inventory'](physical)
        native, step = out / OUTPUT_NAMES[0], out / OUTPUT_NAMES[1]
        doc.saveAs(str(native))
        # Request every physical component, including any failed geometry.
        # Reopened inspection must establish what STEP actually retained.
        Part.export(physical, str(step))

        ledger = {
            'schema': 'hopper_preliminary_component_interface_ledger/1',
            'candidate_status': 'unselected_partial_refinement_experiment',
            'refinement_decision': DECISION,
            'configuration_sha256': FILES['configuration'][1],
            'original_geometry_source_sha256': FILES['original_geometry'][1],
            'geometry_adapter_sha256': FILES['adapter'][1],
            'component_ledger': built['component_ledger'],
            'physical_native_names': names,
            'STEP_export_requested_names': names,
            'STEP_component_correspondence_verified': None,
            'intended_interfaces': built['intended_interfaces'],
            'tube_cut_hypotheses': built['tube_cut_hypotheses'],
            'joint_geometry_index': built['joint_geometry_index'],
            'through_cutting_tool_index': built['through_cutting_tool_index'],
            'excluded_non_mass_references': reference_names,
            'excluded_diagnostics': [obj.Name for obj in built['diagnostic_objects']],
            'units_and_frames': cfg['units_and_frames'],
            'material_and_mass_ownership': cfg['material_and_mass_ownership'],
            'refinement_observations_file': identity(root, out / OUTPUT_NAMES[6]),
            'scope': 'Ownership and intended interfaces only; no observed contact, qualified retention or complete mass claim',
            'assembly_access_demonstrated': None,
            'positive_retention_qualified': None,
            'complete_vehicle_mass_kg': None,
            'complete_vehicle_CG_CAD_mm': None,
            'complete_vehicle_inertia_kg_m2': None
        }
        dump(out / OUTPUT_NAMES[3], ledger)
        drawing_path = out / OUTPUT_NAMES[2]
        drawing = helpers['draw_arrangement'](drawing_path, physical, references)
        drawing['fresh_output_label_updates'] = relabel_new_drawing(drawing_path)
        drawing['renderer_source'] = before['export_helpers']
        drawing['refinement_decision'] = DECISION
        dump(out / OUTPUT_NAMES[5], drawing)

        after = fingerprints()
        if after != before:
            raise RuntimeError('An input changed during generation')
        observations = {
            'schema': 'hopper_physical_integration_generation_observations/1',
            'generated_at_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'authority': cfg['authority'],
            'refinement_decision': DECISION,
            'fresh_output_directory': OUT_REL,
            'original_configuration_output_directory_not_used': cfg['execution_contract']['future_output_directory'],
            'inputs_before': before,
            'inputs_after': after,
            'input_bytes_unchanged': before == after,
            'FreeCAD_version': list(App.Version()),
            'physical_component_count': len(physical),
            'physical_inventory': inventory,
            'STEP_export_requested_component_count': len(physical),
            'native_file': identity(root, native),
            'physical_STEP_file': identity(root, step),
            'refinement_observations_file': identity(root, out / OUTPUT_NAMES[6]),
            'drawing_omission_count': len(drawing['omissions']),
            'geometry_changed_by_export_driver': False,
            'evidence_boundary': 'In-memory regeneration observations and generated exports; not independent reopened verification or a VerificationResult',
            'unperformed': [
                'Independent saved native and STEP reopen with forced native recomputation',
                'All 58 physical components reconciled with exported solids independently of solid order',
                'Unsaved parameter perturbation and restoration with downstream topology checks',
                'Physical pair distances, common volumes and intended contact observations',
                'Bore separation, residual webs, insertion access and assembly sequence',
                'Material-based partial mass, CG and full inertia from valid correctly owned solids',
                'Retained 97-pose rotor/yoke clearance sampling and finite-pad ground assessment',
                'Continuous, deformed and manufacturing-tolerance clearance',
                'Joint, structural, actuator, electrical and physical qualification',
                'Complete installed mass, mission energy and purchased budget closure',
                'Vehicle selection and PDR/CDR acceptance'
            ],
            'geometry_acceptance': None,
            'structural_selection': None,
            'physical_validation': None
        }
        dump(out / OUTPUT_NAMES[4], observations)
        dump(out / OUTPUT_NAMES[7], {
            'schema': 'hopper_preliminary_output_manifest/1',
            'refinement_decision': DECISION,
            'inputs': before,
            'files': [identity(root, out / name) for name in OUTPUT_NAMES[:-1]],
            'manifest_path': str((out / OUTPUT_NAMES[7]).relative_to(root)),
            'manifest_self_hash_omitted': True,
            'evidence_boundary': 'Produced artifacts do not imply geometry, structural, vehicle or review acceptance'
        })
        print(json.dumps({
            'output_directory': OUT_REL,
            'requested_physical_component_count': len(physical),
            'declared_output_count': len(OUTPUT_NAMES),
            'drawing_omission_count': len(drawing['omissions']),
            'acceptance': 'not established'
        }), file=sys.stderr)
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)


if __name__ == '__main__':
    main()
