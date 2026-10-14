"""Controlled refinement diagnosis of four existing junctions.

Run subsequently through freecad_run(headless=True), declaring:
 cad/pdr_r12_chief/junction_refine_diagnostics_20261014_02/observations.json
 cad/pdr_r12_chief/junction_refine_diagnostics_20261014_02/summary.json

Compare native MultiFuse Refine=False/True using identical saved operands.
For each usable union, compare Cut Refine=False/True with the same saved
cutting tool. No dimensions, placements, tolerances or physical membership
are edited. No source document is saved, no repair is selected, and no
geometry acceptance is inferred. This collector is not a verification
program; subsequent artifact-bound verification remains required.
"""

import datetime
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import FreeCAD as App
import Part

SELF = 'cad/pdr_r12_chief/diagnose_junction_refine_20261014_02.py'
OUT = 'cad/pdr_r12_chief/junction_refine_diagnostics_20261014_02'
FILES = {
    'native': (
        'cad/pdr_r12_chief/physical_integration_prototype_20261014_01/physical_integration_prototype_01.FCStd',
        '45010bcd928d38cd580f8ded06273e561d290a671d7ecfb771943825fee2fa16'),
    'helpers': (
        'cad/pdr_r12_chief/inspect_physical_integration_topology_20261014_01.py',
        '94e3a6a12cfe0ec7222add47355afeb9199ae8df1f97bcf7fe0d57e3614c0f6f'),
    'previous_diagnostics': (
        'cad/pdr_r12_chief/junction_boolean_diagnostics_20261014_01/observations.json',
        '72f175d2b9e6ae7f454c83afde4140aa350712b32362f3d6e71963038d6a3df4')
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def error(exc):
    return type(exc).__name__ + ': ' + str(exc)


def usable(shape):
    return (not shape.isNull() and shape.isValid()
            and len(shape.Solids) == 1 and shape.Volume > 0)


def topology(observation):
    shape = (observation or {}).get('shape') or {}
    return {key: shape.get(key) for key in
            ('is_null', 'is_valid', 'solid_count', 'volume_mm3')}


def difference(a, b):
    """Record directional Boolean difference, not a tolerance-based pass."""
    row = {'is_null': None, 'is_valid': None, 'solid_count': None,
           'volume_mm3': None, 'errors': []}
    try:
        result = a.copy().cut(b.copy())
        row['is_null'] = bool(result.isNull())
        if row['is_null']:
            row['solid_count'] = 0
            return row
        row['is_valid'] = bool(result.isValid())
        row['solid_count'] = len(result.Solids)
        volume = float(result.Volume)
        if not math.isfinite(volume):
            raise ValueError('Nonfinite difference volume')
        row['volume_mm3'] = volume
    except Exception as exc:
        row['errors'].append(error(exc))
    return row


def require_refine(obj, setting):
    if 'Refine' not in obj.PropertiesList:
        raise ValueError('Native feature lacks Refine: ' + obj.Name)
    obj.Refine = setting
    if bool(obj.Refine) != setting:
        raise ValueError('Requested Refine setting was not retained')


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def inspect_junction(source, scratch, index, helpers, previous):
    row = {'junction_index': index, 'errors': [], 'experiments': [],
           'union_directional_differences': None}
    observe = helpers['object_observation']
    world = helpers['world_shape']
    union_name = 'JunctionUnbored_%02d' % index
    fitting_name = 'BraceJunctionFitting_%02d' % index
    original = source.getObject(union_name)
    fitting = source.getObject(fitting_name)
    if original is None or fitting is None:
        raise ValueError('Required saved junction feature missing')
    expected = ['JunctionMainSleeve_%02d' % index]
    for suffix in ('Plus', 'Minus'):
        expected.extend(['JunctionBranchBoss_%02d_%s' % (index, suffix),
                         'JunctionWeb_%02d_%s' % (index, suffix)])
    if [obj.Name for obj in original.Shapes] != expected:
        raise ValueError('Saved operand order differs from inspected generator')
    row['source_union'] = observe(original)
    row['source_fitting'] = observe(fitting)
    row['source_operands'] = [observe(obj) for obj in original.Shapes]
    row['source_cutting_tool'] = observe(fitting.Tool)
    row['previous_experiments'] = [
        {'variant': trial['variant'], 'union_refine': trial['union_refine'],
         'cut_refine': trial['cut_refine'],
         'union': topology(trial.get('final_union')),
         'cut': topology(trial.get('final_cut'))}
        for trial in previous['experiments']]

    leaves = []
    for obj in original.Shapes:
        shape = world(obj)
        if not usable(shape):
            raise ValueError('Saved operand is not one valid positive-volume solid: ' + obj.Name)
        leaf = scratch.addObject('Part::Feature', 'J%02d_%s' % (index, obj.Name))
        leaf.Shape = shape.copy()
        leaves.append(leaf)
    cutter_shape = world(fitting.Tool)
    if cutter_shape.isNull() or not cutter_shape.isValid():
        raise ValueError('Saved cutting-tool shape is null or invalid')
    cutter = scratch.addObject('Part::Feature', 'J%02d_SavedCutter' % index)
    cutter.Shape = cutter_shape.copy()
    scratch.recompute()
    row['copied_operands'] = [observe(obj) for obj in leaves]
    row['copied_cutting_tool'] = observe(cutter)
    valid_unions = {}

    for union_refine in (False, True):
        tag = 'J%02d_UnionRefine%d' % (index, int(union_refine))
        trial = {'requested_union_refine': union_refine, 'union': None,
                 'cuts': [], 'operand_minus_union': [], 'errors': []}
        row['experiments'].append(trial)
        try:
            union = scratch.addObject('Part::MultiFuse', tag)
            union.Shapes = leaves
            require_refine(union, union_refine)
            scratch.recompute()
            trial['observed_union_refine'] = bool(union.Refine)
            trial['union'] = observe(union)
            if not usable(union.Shape):
                trial['cuts_not_evaluated_reason'] = 'Union is not one valid positive-volume solid'
                continue
            valid_unions[union_refine] = world(union)
            for leaf in leaves:
                trial['operand_minus_union'].append({
                    'operand': leaf.Name,
                    'difference': difference(world(leaf), world(union))})
            for cut_refine in (False, True):
                cut_row = {'requested_cut_refine': cut_refine,
                           'cut': None, 'errors': []}
                trial['cuts'].append(cut_row)
                try:
                    cut = scratch.addObject('Part::Cut', tag + '_CutRefine%d' % int(cut_refine))
                    cut.Base, cut.Tool = union, cutter
                    require_refine(cut, cut_refine)
                    scratch.recompute()
                    cut_row['observed_cut_refine'] = bool(cut.Refine)
                    cut_row['cut'] = observe(cut)
                except Exception as exc:
                    cut_row['errors'].append(error(exc))
        except Exception as exc:
            trial['errors'].append(error(exc))

    if False in valid_unions and True in valid_unions:
        row['union_directional_differences'] = {
            'unrefined_minus_refined': difference(valid_unions[False], valid_unions[True]),
            'refined_minus_unrefined': difference(valid_unions[True], valid_unions[False])}
    else:
        row['union_comparison_not_evaluated_reason'] = 'Both unions must be usable before material-difference comparison'
    return row


def main():
    root = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
    paths = {key: (root / value[0]).resolve() for key, value in FILES.items()}
    own, out = (root / SELF).resolve(), (root / OUT).resolve()
    for path in [*paths.values(), own, out]:
        if not path.is_relative_to(root):
            raise ValueError('Path escaped sandbox')
    if out.exists():
        raise FileExistsError('Preserve previous or partial diagnostic output: ' + str(out))
    for key, path in paths.items():
        if sha(path) != FILES[key][1]:
            raise ValueError('Pinned input changed: ' + key)

    def fingerprints():
        result = {key: {'path': FILES[key][0], 'sha256': sha(path)}
                  for key, path in paths.items()}
        result['diagnostic_source'] = {'path': SELF, 'sha256': sha(own)}
        return result

    before = fingerprints()
    previous = json.loads(paths['previous_diagnostics'].read_text(encoding='utf-8'))
    if previous.get('schema') != 'hopper_junction_boolean_diagnostics/1':
        raise ValueError('Unexpected previous diagnostic schema')
    if previous['inputs_before']['native']['sha256'] != FILES['native'][1]:
        raise ValueError('Previous diagnosis used a different native artifact')
    previous_rows = {row['junction_index']: row for row in previous['junctions']}
    if len(previous['junctions']) != 4 or set(previous_rows) != {1, 2, 3, 4}:
        raise ValueError('Expected exactly four previously diagnosed junctions')
    helpers = {'__name__': 'pdr_r12_refine_observation_helpers',
               '__file__': str(paths['helpers'])}
    exec(compile(paths['helpers'].read_bytes(), str(paths['helpers']), 'exec'), helpers)
    report = {
        'schema': 'hopper_junction_refine_diagnostics/1',
        'timestamp_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'FreeCAD_version': list(App.Version()),
        'authority': previous['authority'], 'inputs_before': before,
        'units': {'length': 'mm', 'volume': 'mm^3'},
        'scope': 'Controlled native refinement comparison on identical saved operands; no intended physical geometry edits',
        'junctions': [], 'errors': [], 'source_document_saved': False,
        'prototype_repaired': False, 'root_cause_confirmed': False,
        'geometry_acceptance': None}
    source = scratch = None
    scratch_name = 'PDRR12JunctionRefineDiagnosis20261014_02'
    if scratch_name in App.listDocuments():
        raise ValueError('Preserve existing scratch document')
    for document in App.listDocuments().values():
        if document.FileName and Path(document.FileName).resolve() == paths['native']:
            raise ValueError('Preserve already-open source document')
    try:
        source = App.openDocument(str(paths['native']))
        scratch = App.newDocument(scratch_name)
        for index in range(1, 5):
            try:
                report['junctions'].append(inspect_junction(
                    source, scratch, index, helpers, previous_rows[index]))
            except Exception as exc:
                report['junctions'].append({'junction_index': index,
                    'experiments': [], 'errors': [error(exc)]})
    except Exception as exc:
        report['errors'].append(error(exc))
    finally:
        if scratch is not None:
            App.closeDocument(scratch.Name)
        if source is not None:
            App.closeDocument(source.Name)
    report['inputs_after'] = fingerprints()
    report['input_bytes_unchanged'] = before == report['inputs_after']
    report['limitations'] = [
        'Directional differences use the same geometry kernel and are not independent proof of set equivalence.',
        'No difference-volume acceptance threshold is introduced.',
        'No fitting repair, regenerated prototype, parameter test or export verification is performed.',
        'Joint assembly, material properties, mass, clearances and structural adequacy remain unaccepted.',
        'No vehicle selection, complete budget or review acceptance is established.']
    summary = {key: report[key] for key in (
        'schema', 'inputs_before', 'input_bytes_unchanged', 'errors',
        'prototype_repaired', 'root_cause_confirmed', 'geometry_acceptance', 'limitations')}
    summary['junctions'] = []
    for row in report['junctions']:
        summary['junctions'].append({
            'junction_index': row['junction_index'], 'errors': row['errors'],
            'experiments': [{
                'union_refine': trial['requested_union_refine'],
                'union': topology(trial.get('union')), 'errors': trial['errors'],
                'cuts_not_evaluated_reason': trial.get('cuts_not_evaluated_reason'),
                'cuts': [{'cut_refine': cut['requested_cut_refine'],
                          'cut': topology(cut.get('cut')), 'errors': cut['errors']}
                         for cut in trial['cuts']]}
                for trial in row['experiments']],
            'union_directional_differences': row.get('union_directional_differences')})
    out.mkdir(parents=True)
    dump(out / 'observations.json', report)
    dump(out / 'summary.json', summary)
    print('Retained refinement diagnostics only: ' + OUT, file=sys.stderr)


if __name__ == '__main__':
    main()
