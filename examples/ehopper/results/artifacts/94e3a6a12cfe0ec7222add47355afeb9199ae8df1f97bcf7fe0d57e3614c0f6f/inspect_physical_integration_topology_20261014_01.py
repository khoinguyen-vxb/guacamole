"""Reopen the unselected physical-integration prototype without repairing it.

Run subsequently through freecad_run(headless=True). Declare these outputs:
 cad/pdr_r12_chief/physical_integration_topology_20261014_01/observations.json
 cad/pdr_r12_chief/physical_integration_topology_20261014_01/summary.json

Include this source and every inspected artifact Ref in that tool action.
This is an observation collector, not a VerificationResult program. A separate
artifact-bound verify_command checker must interpret the retained observations.
No source generation, healing, shape replacement, parameter changes, geometry
selection or native-document saves occur. Forced recomputation is in memory.
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

SELF = 'cad/pdr_r12_chief/inspect_physical_integration_topology_20261014_01.py'
BASE = 'cad/pdr_r12_chief/physical_integration_prototype_20261014_01/'
OUT = 'cad/pdr_r12_chief/physical_integration_topology_20261014_01'
FILES = {
    'native': (BASE + 'physical_integration_prototype_01.FCStd',
               '45010bcd928d38cd580f8ded06273e561d290a671d7ecfb771943825fee2fa16'),
    'STEP': (BASE + 'physical_integration_prototype_01_physical.step',
             '74c69347eed6498e280398daee8ab77da3ac7f5afa822be7bf1b3384e0ddf1a3'),
    'configuration': ('cad/pdr_r12_chief/physical_integration_prototype_config_20261014_01.json',
                      'be78fc14b24b01cd824e1bf90625c415176b27ecae2dca26dff8ac790de1e9b0'),
    'generation_observations': (BASE + 'generation_observations_01.json',
                                'cf37a3e262eb9e0031a7b0c5a29a1f471098113937b8479d5b12b90a2400ecd5')
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite geometric observation')
    return result


def xyz(value):
    return [number(value.x), number(value.y), number(value.z)]


def bounds(shape):
    bb = shape.BoundBox
    return [[number(getattr(bb, axis + 'Min')), number(getattr(bb, axis + 'Max'))]
            for axis in ('X', 'Y', 'Z')]


def error(exc):
    return type(exc).__name__ + ': ' + str(exc)


def shape_observation(shape):
    row = {'is_null': None, 'is_valid': None, 'solid_count': None,
           'volume_mm3': None, 'bounds_CAD_mm': None, 'solids': [], 'errors': []}
    try:
        row['is_null'] = bool(shape.isNull())
        if row['is_null']:
            row['solid_count'] = 0
            return row
        row['shape_type'] = str(shape.ShapeType)
    except Exception as exc:
        row['errors'].append(error(exc))
        return row
    try:
        row['is_valid'] = bool(shape.isValid())
    except Exception as exc:
        row['errors'].append(error(exc))
    try:
        row['volume_mm3'] = number(shape.Volume)
        row['bounds_CAD_mm'] = bounds(shape)
    except Exception as exc:
        row['errors'].append(error(exc))
    try:
        solids = list(shape.Solids)
        row['solid_count'] = len(solids)
        for index, solid in enumerate(solids, 1):
            observed = {'index': index, 'errors': []}
            try:
                observed.update({'valid': bool(solid.isValid()),
                                 'volume_mm3': number(solid.Volume),
                                 'centroid_CAD_mm': xyz(solid.CenterOfMass),
                                 'bounds_CAD_mm': bounds(solid)})
            except Exception as exc:
                observed['errors'].append(error(exc))
            row['solids'].append(observed)
    except Exception as exc:
        row['errors'].append(error(exc))
    return row


def world_shape(obj):
    shape = obj.Shape.copy()
    ancestors = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    shape.Placement = ancestors.multiply(shape.Placement)
    return shape


def object_observation(obj):
    row = {'name': obj.Name, 'type': obj.TypeId,
           'state': [str(x) for x in getattr(obj, 'State', [])],
           'dependencies': sorted(x.Name for x in obj.OutList),
           'errors': []}
    for key in ('MaterialHypothesis', 'MovingGroup', 'PhysicalRole'):
        row[key] = str(getattr(obj, key)) if key in obj.PropertiesList else None
    row['primitive_parameters'] = {}
    for key in ('Radius', 'Height', 'Length', 'Width', 'Angle', 'Refine'):
        if key in obj.PropertiesList:
            row['primitive_parameters'][key] = str(getattr(obj, key))
    try:
        row['expressions'] = [[str(a), str(b)] for a, b in obj.ExpressionEngine]
    except Exception as exc:
        row['expression_observation_error'] = error(exc)
    try:
        row['shape'] = shape_observation(world_shape(obj))
    except Exception as exc:
        row['shape'] = None
        row['errors'].append(error(exc))
    return row


def snapshot(doc, names):
    rows = []
    for name in names:
        obj = doc.getObject(name)
        rows.append(object_observation(obj) if obj is not None else
                    {'name': name, 'missing': True, 'shape': None, 'errors': ['Object missing']})
    return rows


def dependency_names(doc, roots):
    pending = [doc.getObject(name) for name in roots]
    seen = set()
    while pending:
        obj = pending.pop()
        if obj is None or obj.Name in seen:
            continue
        seen.add(obj.Name)
        pending.extend(obj.OutList)
    return sorted(seen)


def issues(rows):
    result = []
    for row in rows:
        shape = row.get('shape')
        reasons = list(row.get('errors', []))
        if shape is None:
            reasons.append('No shape observation')
        else:
            reasons.extend(shape['errors'])
            if shape['is_null'] is not False:
                reasons.append('Null or unobserved shape')
            if shape['is_valid'] is not True:
                reasons.append('Validity false or unobserved')
            if shape['solid_count'] != 1:
                reasons.append('Expected one connected physical solid; observed ' + str(shape['solid_count']))
            for solid in shape['solids']:
                if solid.get('valid') is not True or solid.get('volume_mm3', 0) <= 0 or solid['errors']:
                    reasons.append('Invalid, nonpositive or unobserved solid ' + str(solid['index']))
        if reasons:
            result.append({'name': row['name'], 'reasons': reasons})
    return result


def expected_physical_names(cfg):
    names = ['Spine_01', 'PrintedRootRingSpider', 'FixedGimbalSupport_PositiveX',
             'FixedGimbalSupport_NegativeX', 'SpinePedestal', 'Bond_SpinePedestal']
    for i in range(1, len(cfg['immutable_reference_geometry']['leg_azimuths_deg']) + 1):
        names.extend(pattern % i for pattern in (
            'MainLeg_%02d', 'Bond_MainRoot_%02d', 'BraceJunctionFitting_%02d',
            'Bond_JunctionMain_%02d', 'PrintedFoot_%02d', 'FootPad_%02d', 'Bond_Foot_%02d'))
        for suffix in ('Plus', 'Minus'):
            names.extend(pattern % (i, suffix) for pattern in (
                'Brace_%02d_%s', 'Bond_BraceRoot_%02d_%s', 'Bond_JunctionBrace_%02d_%s'))
    return sorted(names)


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    root = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
    paths = {key: (root / item[0]).resolve() for key, item in FILES.items()}
    source = (root / SELF).resolve()
    out = (root / OUT).resolve()
    for path in [*paths.values(), source, out]:
        if not path.is_relative_to(root):
            raise ValueError('Path escaped sandbox')
    for key, path in paths.items():
        if sha(path) != FILES[key][1]:
            raise ValueError('Pinned input bytes differ: ' + key)
    before = {key: {'path': FILES[key][0], 'sha256': sha(path)} for key, path in paths.items()}
    before['inspection_source'] = {'path': SELF, 'sha256': sha(source)}
    if out.exists():
        raise FileExistsError('Preserve earlier or partial diagnostic output: ' + str(out))
    cfg = json.loads(paths['configuration'].read_text(encoding='utf-8'))
    generation = json.loads(paths['generation_observations'].read_text(encoding='utf-8'))
    expected = expected_physical_names(cfg)
    fitting_names = [name for name in expected if name.startswith('BraceJunctionFitting_')]
    report = {
        'schema': 'hopper_physical_integration_topology_reopen/1',
        'timestamp_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'FreeCAD_version': list(App.Version()), 'authority': cfg['authority'],
        'inputs_before': before, 'expected_physical_names': expected,
        'units': {'length': 'mm', 'volume': 'mm^3'},
        'errors': [], 'native_saved': False, 'geometry_repaired': False,
        'evidence_boundary': 'Topology observations only; no geometry or physical acceptance. Invalid or omitted parts must not be treated as zero mass.'
    }
    doc = None
    try:
        doc = App.openDocument(str(paths['native']))
        group = doc.getObject('PhysicalComponents')
        actual_names = sorted(obj.Name for obj in group.Group) if group is not None else []
        report['native_group_names'] = actual_names
        report['missing_expected_names'] = sorted(set(expected) - set(actual_names))
        report['unexpected_group_names'] = sorted(set(actual_names) - set(expected))
        inspect_names = sorted(set(expected) | set(actual_names))
        dependencies = dependency_names(doc, fitting_names)
        shape_dependencies = [name for name in dependencies if hasattr(doc.getObject(name), 'Shape')]
        report['junction_dependency_names'] = dependencies
        report['cached_physical'] = snapshot(doc, inspect_names)
        report['cached_junction_features'] = snapshot(doc, shape_dependencies)
        try:
            report['ordinary_recompute_return'] = str(doc.recompute())
        except Exception as exc:
            report['errors'].append('Ordinary recompute: ' + error(exc))
        report['ordinary_recomputed_physical'] = snapshot(doc, inspect_names)
        report['ordinary_recomputed_junction_features'] = snapshot(doc, shape_dependencies)
        # Dirty only the existing junction shape dependency tree. No property,
        # placement, dimensional or topology edits are made by this program.
        touched = []
        for name in shape_dependencies:
            try:
                doc.getObject(name).touch()
                touched.append(name)
            except Exception as exc:
                report['errors'].append('Touch ' + name + ': ' + error(exc))
        report['forced_recompute_touched_names'] = touched
        try:
            report['forced_recompute_return'] = str(doc.recompute())
        except Exception as exc:
            report['errors'].append('Forced recompute: ' + error(exc))
        report['forced_recomputed_physical'] = snapshot(doc, inspect_names)
        report['forced_recomputed_junction_features'] = snapshot(doc, shape_dependencies)
    except Exception as exc:
        report['errors'].append('Native inspection: ' + error(exc))
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
    try:
        report['STEP_shape'] = shape_observation(Part.read(str(paths['STEP'])))
    except Exception as exc:
        report['STEP_shape'] = None
        report['errors'].append('STEP inspection: ' + error(exc))
    after = {key: {'path': FILES[key][0], 'sha256': sha(path)} for key, path in paths.items()}
    after['inspection_source'] = {'path': SELF, 'sha256': sha(source)}
    report['inputs_after'] = after
    report['input_bytes_unchanged'] = before == after
    report['STEP_component_material_correspondence'] = None
    report['complete_vehicle_mass_kg'] = None
    report['geometry_acceptance'] = None
    report['unperformed'] = [
        'STEP-to-native component/material correspondence; solid order is not correspondence',
        'All physical pair intersections and intended contact verification',
        'Parameter perturbation/restoration and assembly insertion/access',
        'Mass, CG and inertia reconciliation',
        'Motion, ground, continuous and loaded clearance',
        'Material, joint, actuator and structural qualification',
        'Complete mass, energy, procurement and review acceptance'
    ]
    summary = {
        'schema': 'hopper_physical_integration_topology_summary/1',
        'inputs': before, 'expected_component_count': len(expected),
        'native_group_count': len(report.get('native_group_names', [])),
        'missing_expected_names': report.get('missing_expected_names'),
        'unexpected_group_names': report.get('unexpected_group_names'),
        'generation_reported_issues': [
            {'name': row['name'], 'is_null': row.get('shape_is_null'),
             'valid': row.get('shape_valid'), 'solid_count': row.get('solid_count'),
             'error': row.get('inspection_error')}
            for row in generation['physical_inventory']
            if row.get('inspection_error') or row.get('shape_is_null') is not False
            or row.get('shape_valid') is not True or row.get('solid_count') != 1
        ],
        'cached_physical_issues': issues(report.get('cached_physical', [])),
        'ordinary_recomputed_physical_issues': issues(report.get('ordinary_recomputed_physical', [])),
        'forced_recomputed_physical_issues': issues(report.get('forced_recomputed_physical', [])),
        'junction_feature_failures': [],
        'STEP_solid_count': (report.get('STEP_shape') or {}).get('solid_count'),
        'STEP_shape_valid': (report.get('STEP_shape') or {}).get('is_valid'),
        'STEP_component_material_correspondence': None,
        'input_bytes_unchanged': before == after,
        'errors': report['errors'], 'root_cause_confirmed': False,
        'geometry_acceptance': None, 'unperformed': report['unperformed'],
        'interpretation': 'Use dependency observations to locate failures; orientation differences alone do not establish their cause. No repair or acceptance is asserted.'
    }
    # Construction tools may intentionally contain multiple disconnected solids;
    # diagnose null/invalid shapes here without imposing a one-solid criterion.
    for row in report.get('forced_recomputed_junction_features', []):
        shape = row.get('shape')
        if shape is None or shape['is_null'] is not False or shape['is_valid'] is not True or shape['errors']:
            summary['junction_feature_failures'].append({
                'name': row['name'], 'type': row.get('type'), 'state': row.get('state'),
                'dependencies': row.get('dependencies'),
                'is_null': (shape or {}).get('is_null'),
                'valid': (shape or {}).get('is_valid'),
                'errors': row.get('errors', []) + (shape or {}).get('errors', [])})
    out.mkdir(parents=True)
    dump(out / 'observations.json', report)
    dump(out / 'summary.json', summary)
    print('Retained topology observations; no acceptance established: ' + OUT, file=sys.stderr)


if __name__ == '__main__':
    main()
