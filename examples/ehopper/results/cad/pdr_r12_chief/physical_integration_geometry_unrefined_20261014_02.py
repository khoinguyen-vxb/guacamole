"""Bounded refinement adapter for the unselected PDR-r12 prototype.

This file defines build_document(sandbox); importing it builds nothing.
A separately saved driver must run it through freecad_run, declare fresh
exports, and retain targeted_refinement_observations in its output ledger.

Regenerate the inspected original construction first, including its original
through-cutter definitions. Only afterwards set Refine=False on the four
JunctionUnbored features. Do not reconstruct cutters from changed bounds.
No dimensions, operands, operand order, placements, expressions, physical
membership, healing options or fuzzy tolerances are intentionally changed.

This adapter performs construction-consistency observations, not independent
artifact verification. It neither saves nor exports documents. Reopened
native/STEP checks, parameter tests, contacts, mass and clearance assessment
remain required. No vehicle selection or physical acceptance is established.
"""

import hashlib
import math
from pathlib import Path

import FreeCAD as App
import Part

BASE_REL = 'cad/pdr_r12_chief/physical_integration_geometry_20261014_01.py'
BASE_SHA = 'c8e74b814c41899236df91d885abc876c5e0f950a514f19d4719a61a0aeee7e6'
CONFIG_REL = 'cad/pdr_r12_chief/physical_integration_prototype_config_20261014_01.json'
CONFIG_SHA = 'be78fc14b24b01cd824e1bf90625c415176b27ecae2dca26dff8ac790de1e9b0'
NATIVE_REL = 'cad/pdr_r12_chief/physical_integration_prototype_20261014_01/physical_integration_prototype_01.FCStd'
NATIVE_SHA = '45010bcd928d38cd580f8ded06273e561d290a671d7ecfb771943825fee2fa16'
DOCUMENT_NAME = 'PDRR12PhysicalIntegrationUnrefined02'
DECISION = '32c12da080c74e29afe522cbfc9525c3 revision 1'
TARGETS = tuple('JunctionUnbored_%02d' % i for i in range(1, 5))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounded_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path escaped sandbox: ' + relative)
    return path


def number(value):
    value = float(getattr(value, 'Value', value))
    if not math.isfinite(value):
        raise ValueError('Nonfinite construction parameter')
    return value


def refinement_map(doc):
    return {obj.Name: bool(obj.Refine) for obj in doc.Objects
            if 'Refine' in obj.PropertiesList}


def historical_refinements(path):
    """Read original settings without recomputing or saving the old file."""
    for existing in App.listDocuments().values():
        if existing.FileName and Path(existing.FileName).resolve() == path:
            raise ValueError('Preserve already-open historical document')
    doc = None
    try:
        doc = App.openDocument(str(path))
        settings = refinement_map(doc)
        for name in TARGETS:
            obj = doc.getObject(name)
            if obj is None or obj.TypeId != 'Part::MultiFuse':
                raise ValueError('Missing historical junction union: ' + name)
            if settings.get(name) is not True:
                raise ValueError('Historical target is not Refine=True: ' + name)
        return settings
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)


def construction_contract(doc):
    """Record native construction inputs, not derived BREP equivalence."""
    rows = {}
    for obj in doc.Objects:
        row = {'type': obj.TypeId}
        properties = set(obj.PropertiesList)
        if 'Placement' in properties:
            placement = obj.Placement
            row['placement'] = {
                'translation_mm': [number(placement.Base.x),
                                   number(placement.Base.y),
                                   number(placement.Base.z)],
                'rotation_quaternion_FreeCAD_order': [number(x) for x in placement.Rotation.Q]
            }
        row['dimensions'] = {key: number(getattr(obj, key))
                             for key in ('Radius', 'Height', 'Length', 'Width', 'Angle')
                             if key in properties}
        if 'Refine' in properties:
            row['refine'] = bool(obj.Refine)
        if 'ExpressionEngine' in properties:
            row['expressions'] = sorted([[str(key), str(value)]
                                         for key, value in obj.ExpressionEngine])
        if obj.TypeId == 'Part::MultiFuse':
            row['ordered_operands'] = [item.Name for item in obj.Shapes]
        if obj.TypeId == 'Part::Cut':
            row['base'] = None if obj.Base is None else obj.Base.Name
            row['tool'] = None if obj.Tool is None else obj.Tool.Name
        if 'Group' in properties:
            row['group_members'] = [item.Name for item in obj.Group]
        rows[obj.Name] = row
    return rows


def shape_observation(obj):
    row = {'name': obj.Name, 'is_null': None, 'is_valid': None,
           'solid_count': None, 'volume_mm3': None, 'error': None}
    try:
        shape = obj.Shape
        row['is_null'] = bool(shape.isNull())
        if not row['is_null']:
            row['is_valid'] = bool(shape.isValid())
            row['solid_count'] = len(shape.Solids)
            row['volume_mm3'] = number(shape.Volume)
    except Exception as exc:
        row['error'] = type(exc).__name__ + ': ' + str(exc)
    return row


def junction_observations(doc):
    names = [name for i in range(1, 5)
             for name in ('JunctionUnbored_%02d' % i,
                          'BraceJunctionFitting_%02d' % i)]
    return [shape_observation(doc.getObject(name)) for name in names]


def build_document(sandbox):
    root = Path(sandbox).resolve()
    paths = {
        'original_geometry': bounded_path(root, BASE_REL),
        'configuration': bounded_path(root, CONFIG_REL),
        'historical_native': bounded_path(root, NATIVE_REL)
    }
    expected = {'original_geometry': BASE_SHA, 'configuration': CONFIG_SHA,
                'historical_native': NATIVE_SHA}
    before_hashes = {key: sha(path) for key, path in paths.items()}
    if before_hashes != expected:
        raise ValueError('Pinned source/configuration/native bytes changed')
    if DOCUMENT_NAME in App.listDocuments():
        raise ValueError('Preserve existing target document')

    old_settings = historical_refinements(paths['historical_native'])
    if sha(paths['historical_native']) != NATIVE_SHA:
        raise RuntimeError('Historical native bytes changed while reading settings')

    namespace = {'__name__': 'pdr_r12_original_geometry_for_refinement_adapter',
                 '__file__': str(paths['original_geometry'])}
    exec(compile(paths['original_geometry'].read_bytes(),
                 str(paths['original_geometry']), 'exec'), namespace)
    # Change the new document identifier only; original source stays unchanged.
    namespace['DOCUMENT_NAME'] = DOCUMENT_NAME
    doc = None
    try:
        # Complete the original construction before changing refinement.
        # Consequently through-cutter parameters are fixed exactly as generated
        # by the original algorithm, not recalculated after the workaround.
        built = namespace['build_document'](root)
        doc = built['document']
        original_settings = refinement_map(doc)
        if original_settings != old_settings:
            raise ValueError('Fresh original refinement settings differ from historical native')
        original_contract = construction_contract(doc)
        shapes_before = junction_observations(doc)
        physical_names = [obj.Name for obj in built['physical_objects']]
        reference_names = [obj.Name for obj in built['moving_reference_objects']]
        if len(physical_names) != 58 or len(set(physical_names)) != 58:
            raise ValueError('Expected 58 separately owned physical components')

        for name in TARGETS:
            obj = doc.getObject(name)
            if obj is None or obj.TypeId != 'Part::MultiFuse':
                raise ValueError('Missing target native union: ' + name)
            obj.Refine = False

        # Force evaluation of the actual native feature graph. No Shape
        # replacement, cutter reconstruction, healing or fusion of parts.
        for obj in doc.Objects:
            obj.touch()
        doc.recompute()

        updated_settings = refinement_map(doc)
        expected_settings = dict(original_settings)
        expected_settings.update({name: False for name in TARGETS})
        if updated_settings != expected_settings:
            raise ValueError('Unexpected refinement changes')
        updated_contract = construction_contract(doc)
        expected_contract = {name: dict(row) for name, row in original_contract.items()}
        for name in TARGETS:
            expected_contract[name]['refine'] = False
        if updated_contract != expected_contract:
            changed = sorted(name for name in set(updated_contract) | set(expected_contract)
                             if updated_contract.get(name) != expected_contract.get(name))
            raise ValueError('Construction changed beyond selected refinement: ' + repr(changed))
        if [obj.Name for obj in built['physical_objects']] != physical_names:
            raise ValueError('Physical membership changed')
        if [obj.Name for obj in built['moving_reference_objects']] != reference_names:
            raise ValueError('Reference membership changed')

        after_hashes = {key: sha(path) for key, path in paths.items()}
        if after_hashes != before_hashes:
            raise RuntimeError('An input file changed during regeneration')

        # Evidence metadata is added only after construction comparison.
        contract = doc.getObject('EvidenceContract')
        set_property = namespace['property_value']
        set_property(contract, 'App::PropertyString', 'RefinementExperimentDecision', DECISION)
        set_property(contract, 'App::PropertyString', 'OriginalGeometrySHA256', BASE_SHA)
        set_property(contract, 'App::PropertyString', 'RefinementExperimentScope',
                     'Only four JunctionUnbored unions set Refine=False; independent export and geometry acceptance outstanding')

        built['targeted_refinement_observations'] = {
            'schema': 'hopper_targeted_refinement_regeneration/1',
            'decision': DECISION,
            'scope': 'In-memory regeneration and construction consistency; not independent artifact verification',
            'input_paths': {key: str(path.relative_to(root)) for key, path in paths.items()},
            'inputs_before_sha256': before_hashes,
            'inputs_after_sha256': after_hashes,
            'input_bytes_unchanged': before_hashes == after_hashes,
            'historical_refinement_settings': old_settings,
            'regenerated_original_refinement_settings': original_settings,
            'modified_refinement_settings': updated_settings,
            'target_union_names': list(TARGETS),
            'construction_before': original_contract,
            'construction_after': updated_contract,
            'only_selected_refinement_inputs_changed': updated_contract == expected_contract,
            'junction_shapes_before': shapes_before,
            'junction_shapes_after': junction_observations(doc),
            'physical_component_names': physical_names,
            'non_mass_reference_names': reference_names,
            'document_identifier_changed_for_fresh_output': True,
            'through_cutters_reconstructed_after_refinement_change': False,
            'geometry_acceptance': None,
            'limitations': [
                'Construction-input equality does not establish BREP set equivalence.',
                'In-memory topology does not establish saved/reopened native or STEP integrity.',
                'All 58 physical components still require individual-solid and export-correspondence checks.',
                'Parameter perturbation/restoration, contacts, insertion access and residual webs remain untested.',
                'Material-based partial mass and full inertia require valid correctly owned solids.',
                'Sampled, continuous, deformed and tolerance-aware clearances remain unaccepted.',
                'No complete vehicle mass, budget, structural qualification or review acceptance is established.'
            ]
        }
        return built
    except Exception:
        # Do not leave an ambiguously modified document open after an error.
        # Never save the historical document or partially repaired construction.
        if doc is not None:
            App.closeDocument(doc.Name)
        elif DOCUMENT_NAME in App.listDocuments():
            App.closeDocument(DOCUMENT_NAME)
        raise


if __name__ == '__main__':
    raise RuntimeError('Module only: use a separately saved freecad_run export driver with fresh declared outputs.')
