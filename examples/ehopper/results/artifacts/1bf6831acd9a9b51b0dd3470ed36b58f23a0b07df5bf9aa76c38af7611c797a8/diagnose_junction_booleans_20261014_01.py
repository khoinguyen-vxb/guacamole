"""Bounded junction Boolean diagnosis; no prototype repair or selection.

Run through freecad_run(headless=True), declaring:
 cad/pdr_r12_chief/junction_boolean_diagnostics_20261014_01/observations.json
 cad/pdr_r12_chief/junction_boolean_diagnostics_20261014_01/summary.json
Include this source and every inspected/dependent artifact Ref in inputs.

For each of the four existing junctions, inspect the actual saved operands,
then compare four fixed experiments: original global union, sequential global
union, branch-grouped global union, and original union in a joint-centred
rotated frame. Dimensions, material domains and source artifacts are unchanged.
The same saved cutting-tool shape is used in each applicable experiment.
No healing, fuzzy tolerance, dimension search, component omission, native save,
or automatic selection occurs. This is an observation collector, not a
VerificationResult program. Its output requires subsequent interpretation.
"""

import datetime
import hashlib
import json
import math
import os
import sys
from itertools import combinations
from pathlib import Path

import FreeCAD as App
import Part

SELF = 'cad/pdr_r12_chief/diagnose_junction_booleans_20261014_01.py'
OUT = 'cad/pdr_r12_chief/junction_boolean_diagnostics_20261014_01'
FILES = {
    'native': (
        'cad/pdr_r12_chief/physical_integration_prototype_20261014_01/physical_integration_prototype_01.FCStd',
        '45010bcd928d38cd580f8ded06273e561d290a671d7ecfb771943825fee2fa16'),
    'configuration': (
        'cad/pdr_r12_chief/physical_integration_prototype_config_20261014_01.json',
        'be78fc14b24b01cd824e1bf90625c415176b27ecae2dca26dff8ac790de1e9b0'),
    'geometry_source': (
        'cad/pdr_r12_chief/physical_integration_geometry_20261014_01.py',
        'c8e74b814c41899236df91d885abc876c5e0f950a514f19d4719a61a0aeee7e6'),
    'inspection_helpers': (
        'cad/pdr_r12_chief/inspect_physical_integration_topology_20261014_01.py',
        '94e3a6a12cfe0ec7222add47355afeb9199ae8df1f97bcf7fe0d57e3614c0f6f'),
    'prior_observations': (
        'cad/pdr_r12_chief/physical_integration_topology_20261014_01/observations.json',
        'c412ea15d3d371114c1f4a7745b9d7f973d07740f41081763579c5bc2674831e')
}
VARIANTS = ('global_original', 'global_sequential', 'global_branch_grouped',
            'joint_centred_original')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def err(exc):
    return type(exc).__name__ + ': ' + str(exc)


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def transformed(shape, placement):
    result = shape.copy()
    result.Placement = placement.multiply(result.Placement)
    return result


def inspect_node(obj, helpers):
    return helpers['object_observation'](obj)


def usable(shape):
    return (not shape.isNull() and shape.isValid()
            and len(shape.Solids) == 1 and shape.Volume > 0)


def joint_transform(g, index):
    phi = float(g['leg_azimuths_deg'][index - 1])
    angle = math.radians(phi)
    radial = [math.cos(angle), math.sin(angle)]
    a = [g['ring_attachment_radius_mm'] * radial[0],
         g['ring_attachment_radius_mm'] * radial[1], g['ring_attachment_z_mm']]
    f = [g['foot_socket_radius_mm'] * radial[0],
         g['foot_socket_radius_mm'] * radial[1], g['foot_socket_z_mm']]
    fraction = g['junction_fraction_A_to_F']
    j = [a[k] + fraction * (f[k] - a[k]) for k in range(3)]
    rotation = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), -phi))
    translation = App.Placement(App.Vector(*[-v for v in j]), App.Rotation())
    return rotation.multiply(translation), {'joint_CAD_mm': j, 'azimuth_deg': phi,
        'coordinate_operation': 'p_local = Rz(-azimuth) * (p_CAD - joint)',
        'physical_geometry_changed': False}


def pair_observations(operands, helpers):
    rows = []
    for (aname, a), (bname, b) in combinations(operands.items(), 2):
        row = {'a': aname, 'b': bname, 'distance_mm': None,
               'common_shape': None, 'errors': []}
        try:
            if not usable(a) or not usable(b):
                row['not_evaluated_reason'] = 'An operand is not one valid positive-volume solid'
            else:
                row['distance_mm'] = helpers['number'](a.distToShape(b)[0])
                row['common_shape'] = helpers['shape_observation'](a.common(b))
        except Exception as exc:
            row['errors'].append(err(exc))
        rows.append(row)
    return rows


def experiment(doc, prefix, variant, operands, order, tool_shape,
               union_refine, cut_refine, transform, helpers, index):
    row = {'variant': variant, 'operand_order': order,
           'union_refine': union_refine, 'cut_refine': cut_refine,
           'intermediate_operations': [], 'errors': [],
           'final_union': None, 'final_cut': None, 'final_cut_world': None}
    placement = transform if variant == 'joint_centred_original' else App.Placement()
    leaves = {}
    for name in order:
        obj = doc.addObject('Part::Feature', prefix + '_' + name)
        obj.Shape = transformed(operands[name], placement)
        leaves[name] = obj
    cutter = doc.addObject('Part::Feature', prefix + '_SavedCuttingTool')
    cutter.Shape = transformed(tool_shape, placement)
    doc.recompute()
    row['copied_operands'] = [inspect_node(leaves[name], helpers) for name in order]
    row['copied_cutting_tool'] = inspect_node(cutter, helpers)

    def fuse(label, objects):
        obj = doc.addObject('Part::MultiFuse', prefix + '_' + label)
        obj.Shapes = objects
        if union_refine is not None and 'Refine' in obj.PropertiesList:
            obj.Refine = union_refine
        doc.recompute()
        row['intermediate_operations'].append(inspect_node(obj, helpers))
        return obj

    try:
        if variant == 'global_sequential':
            result = leaves[order[0]]
            for step, name in enumerate(order[1:], 1):
                result = fuse('Sequence%02d' % step, [result, leaves[name]])
        elif variant == 'global_branch_grouped':
            groups = []
            for suffix in ('Plus', 'Minus'):
                groups.append(fuse('BranchGroup_' + suffix, [
                    leaves['JunctionBranchBoss_%02d_%s' % (index, suffix)],
                    leaves['JunctionWeb_%02d_%s' % (index, suffix)]]))
            result = fuse('GroupedUnion', [leaves['JunctionMainSleeve_%02d' % index], *groups])
        else:
            result = fuse('OriginalUnion', [leaves[name] for name in order])
        row['final_union'] = inspect_node(result, helpers)
        if not usable(result.Shape):
            row['cut_not_evaluated_reason'] = 'Union is not one valid positive-volume solid'
            return row
        if cutter.Shape.isNull() or not cutter.Shape.isValid():
            row['cut_not_evaluated_reason'] = 'Saved cutting tool is null or invalid'
            return row
        cut = doc.addObject('Part::Cut', prefix + '_FinalCut')
        cut.Base, cut.Tool = result, cutter
        if cut_refine is not None and 'Refine' in cut.PropertiesList:
            cut.Refine = cut_refine
        doc.recompute()
        row['final_cut'] = inspect_node(cut, helpers)
        row['final_cut_world'] = helpers['shape_observation'](
            transformed(helpers['world_shape'](cut), placement.inverse()))
    except Exception as exc:
        row['errors'].append(err(exc))
    return row


def topology(row):
    shape = (row or {}).get('shape') or {}
    return {key: shape.get(key) for key in
            ('is_null', 'is_valid', 'solid_count', 'volume_mm3')}


def main():
    root = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
    paths = {key: (root / value[0]).resolve() for key, value in FILES.items()}
    own = (root / SELF).resolve()
    out = (root / OUT).resolve()
    for path in [*paths.values(), own, out]:
        if not path.is_relative_to(root):
            raise ValueError('Path escaped sandbox')
    if out.exists():
        raise FileExistsError('Preserve earlier or partial diagnostics: ' + str(out))
    for key, path in paths.items():
        if sha(path) != FILES[key][1]:
            raise ValueError('Pinned input changed: ' + key)
    before = {key: {'path': FILES[key][0], 'sha256': sha(path)}
              for key, path in paths.items()}
    before['diagnostic_source'] = {'path': SELF, 'sha256': sha(own)}
    cfg = json.loads(paths['configuration'].read_text(encoding='utf-8'))
    prior = json.loads(paths['prior_observations'].read_text(encoding='utf-8'))
    if len(cfg['immutable_reference_geometry']['leg_azimuths_deg']) != 4:
        raise ValueError('This bounded diagnosis supports exactly four existing junctions')

    # Reuse only the already-inspected, hash-pinned observation helpers.
    # Their guarded main is not invoked; no import cache or source edit is made.
    helpers = {'__name__': 'pdr_r12_topology_observation_helpers',
               '__file__': str(paths['inspection_helpers'])}
    exec(compile(paths['inspection_helpers'].read_bytes(),
                 str(paths['inspection_helpers']), 'exec'), helpers)
    report = {'schema': 'hopper_junction_boolean_diagnostics/1',
              'timestamp_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'FreeCAD_version': list(App.Version()), 'authority': cfg['authority'],
              'inputs_before': before, 'units': {'length': 'mm', 'volume': 'mm^3'},
              'experiment_variants': list(VARIANTS), 'junctions': [], 'errors': [],
              'source_document_saved': False, 'prototype_repaired': False,
              'root_cause_confirmed': False, 'geometry_acceptance': None,
              'scope': 'Boolean grouping and rigid-coordinate diagnostic only; no changed physical dimensions or acceptance thresholds'}
    source = scratch = None
    scratch_name = 'PDRR12JunctionBooleanDiagnosis20261014_01'
    if scratch_name in App.listDocuments():
        raise ValueError('Preserve existing diagnostic document')
    try:
        source = App.openDocument(str(paths['native']))
        scratch = App.newDocument(scratch_name)
        prior_rows = {r['name']: r for r in prior['forced_recomputed_junction_features']}
        for index in range(1, 5):
            name = 'JunctionUnbored_%02d' % index
            final_name = 'BraceJunctionFitting_%02d' % index
            row = {'junction_index': index, 'source_union_name': name,
                   'source_fitting_name': final_name, 'experiments': [], 'errors': []}
            report['junctions'].append(row)
            try:
                union, fitting = source.getObject(name), source.getObject(final_name)
                if union is None or fitting is None:
                    raise ValueError('Required source feature missing')
                order = [obj.Name for obj in union.Shapes]
                expected = ['JunctionMainSleeve_%02d' % index]
                for suffix in ('Plus', 'Minus'):
                    expected.extend(['JunctionBranchBoss_%02d_%s' % (index, suffix),
                                     'JunctionWeb_%02d_%s' % (index, suffix)])
                if order != expected:
                    raise ValueError('Saved operand order differs from inspected generator')
                operands = {obj.Name: helpers['world_shape'](obj) for obj in union.Shapes}
                tool_shape = helpers['world_shape'](fitting.Tool)
                transform, transform_description = joint_transform(cfg['immutable_reference_geometry'], index)
                row.update({'source_union': inspect_node(union, helpers),
                            'source_fitting': inspect_node(fitting, helpers),
                            'source_operands': [inspect_node(obj, helpers) for obj in union.Shapes],
                            'source_cutting_tool': inspect_node(fitting.Tool, helpers),
                            'prior_forced_union': prior_rows.get(name),
                            'prior_forced_fitting': prior_rows.get(final_name),
                            'coordinate_transform': transform_description,
                            'primitive_pair_observations': pair_observations(operands, helpers)})
                union_refine = bool(union.Refine) if 'Refine' in union.PropertiesList else None
                cut_refine = bool(fitting.Refine) if 'Refine' in fitting.PropertiesList else None
                for variant in VARIANTS:
                    row['experiments'].append(experiment(
                        scratch, 'J%02d_%s' % (index, variant), variant,
                        operands, order, tool_shape, union_refine, cut_refine,
                        transform, helpers, index))
            except Exception as exc:
                row['errors'].append(err(exc))
    except Exception as exc:
        report['errors'].append(err(exc))
    finally:
        if scratch is not None:
            App.closeDocument(scratch.Name)
        if source is not None:
            App.closeDocument(source.Name)

    after = {key: {'path': FILES[key][0], 'sha256': sha(path)}
             for key, path in paths.items()}
    after['diagnostic_source'] = {'path': SELF, 'sha256': sha(own)}
    report['inputs_after'] = after
    report['input_bytes_unchanged'] = before == after
    report['unperformed'] = [
        'Independent verification and interpretation of these observations',
        'Geometric set-equivalence between valid Boolean variants',
        'Prototype repair, parameter regeneration and export acceptance',
        'Component intersections, intended contacts and assembly insertion',
        'Mass/CG/inertia, motion/ground clearance and material qualification',
        'Vehicle selection, complete budgets, PDR/CDR and physical acceptance']
    summary = {'schema': 'hopper_junction_boolean_diagnostic_summary/1',
               'inputs': before, 'input_bytes_unchanged': before == after,
               'junctions': [], 'errors': report['errors'],
               'root_cause_confirmed': False, 'prototype_repaired': False,
               'geometry_acceptance': None,
               'interpretation': 'Differences can support a failure hypothesis, but validity alone does not prove material equivalence or establish a root cause.'}
    for row in report['junctions']:
        summary['junctions'].append({
            'junction_index': row['junction_index'],
            'source_union': topology(row.get('source_union')),
            'source_fitting': topology(row.get('source_fitting')),
            'errors': row['errors'],
            'experiments': [{
                'variant': trial['variant'],
                'union': topology(trial.get('final_union')),
                'cut': topology(trial.get('final_cut')),
                'cut_not_evaluated_reason': trial.get('cut_not_evaluated_reason'),
                'errors': trial['errors']}
                for trial in row['experiments']]})
    out.mkdir(parents=True)
    dump(out / 'observations.json', report)
    dump(out / 'summary.json', summary)
    print('Retained bounded junction diagnostics; no repair or acceptance: ' + OUT,
          file=sys.stderr)


if __name__ == '__main__':
    main()
