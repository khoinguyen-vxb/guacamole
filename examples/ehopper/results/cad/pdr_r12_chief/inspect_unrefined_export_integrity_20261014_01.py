"""Independent saved-export observations for the unselected unrefined prototype.

Run subsequently through freecad_run(headless=True), declaring:
 cad/pdr_r12_chief/physical_integration_unrefined_reopen_20261014_01/observations.json
 cad/pdr_r12_chief/physical_integration_unrefined_reopen_20261014_01/summary.json
Include this source and every FILES artifact Ref in that tool action.

Reuse inspected, hash-pinned observation helpers only; never invoke their main.
Reopen the actual FCStd and STEP. Record native geometry before explicit
recomputation, after ordinary recomputation, and after touching the complete
native feature graph. Do not regenerate, heal, change dimensions/refinement,
save the native document or overwrite historical files.

Descriptor thresholds nominate STEP correspondence candidates only. Record
raw Boolean common/difference observations for those candidates without
turning them into acceptance checks. This is an observation collector, not a
VerificationResult program. A separate editable verify_command checker remains
required. No complete mass, structural, manufacturing or flight claim follows.
"""

import hashlib
import json
import math
import os
import sys
import datetime
from pathlib import Path

import FreeCAD as App
import Part

SELF = 'cad/pdr_r12_chief/inspect_unrefined_export_integrity_20261014_01.py'
OUT = 'cad/pdr_r12_chief/physical_integration_unrefined_reopen_20261014_01'
BASE = 'cad/pdr_r12_chief/physical_integration_unrefined_20261014_02/'
FILES = {
    'native': (BASE + 'physical_integration_unrefined_02.FCStd',
               'a4e6c008821da7e7632efd057fcf63d94b08d345eb51cf8721f59724778fd860'),
    'STEP': (BASE + 'physical_integration_unrefined_02_physical.step',
             '4f3736f7e45e076931839b4801d06059f004cd64f76f83da2037b3d311505f00'),
    'configuration': ('cad/pdr_r12_chief/physical_integration_prototype_config_20261014_01.json',
                      'be78fc14b24b01cd824e1bf90625c415176b27ecae2dca26dff8ac790de1e9b0'),
    'generation_observations': (BASE + 'generation_observations_02.json',
                                'fdc3f4a0c09309e74f7540a1557b01631ce9c388e17fb0e81473f6c048d0ba5d'),
    'helpers': ('cad/pdr_r12_chief/inspect_physical_integration_topology_20261014_01.py',
                '94e3a6a12cfe0ec7222add47355afeb9199ae8df1f97bcf7fe0d57e3614c0f6f')
}
NOMINATION = {
    'centroid_distance_mm': 0.0001,
    'maximum_bbox_coordinate_difference_mm': 0.0001,
    'volume_absolute_allowance_mm3': 0.001,
    'volume_relative_allowance': 0.000001,
    'scope': 'Numerical candidate-search hypotheses only; not physical or Boolean-equivalence acceptance tolerances.'
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def error(exc):
    return type(exc).__name__ + ': ' + str(exc)


def descriptor(solid, h):
    return {
        'valid': bool(solid.isValid()),
        'volume_mm3': h['number'](solid.Volume),
        'centroid_CAD_mm': h['xyz'](solid.CenterOfMass),
        'bounds_CAD_mm': h['bounds'](solid)
    }


def gaps(a, b):
    return {
        'signed_volume_difference_mm3': a['volume_mm3'] - b['volume_mm3'],
        'centroid_distance_mm': math.sqrt(sum((x-y)**2 for x, y in
                                               zip(a['centroid_CAD_mm'], b['centroid_CAD_mm']))),
        'maximum_bbox_coordinate_difference_mm': max(abs(x-y)
            for aa, bb in zip(a['bounds_CAD_mm'], b['bounds_CAD_mm'])
            for x, y in zip(aa, bb))
    }


def nominated(a, b, residual):
    volume_limit = (NOMINATION['volume_absolute_allowance_mm3'] +
                    NOMINATION['volume_relative_allowance'] *
                    max(abs(a['volume_mm3']), abs(b['volume_mm3'])))
    return (a['valid'] and b['valid'] and
            a['volume_mm3'] > 0 and b['volume_mm3'] > 0 and
            abs(residual['signed_volume_difference_mm3']) <= volume_limit and
            residual['centroid_distance_mm'] <= NOMINATION['centroid_distance_mm'] and
            residual['maximum_bbox_coordinate_difference_mm'] <=
            NOMINATION['maximum_bbox_coordinate_difference_mm'])


def boolean_observation(operation, h):
    row = {'is_null': None, 'is_valid': None, 'solid_count': None,
           'volume_mm3': None, 'error': None}
    try:
        shape = operation()
        row['is_null'] = bool(shape.isNull())
        if row['is_null']:
            row['solid_count'] = 0
            row['volume_mm3'] = 0.0
        else:
            row['is_valid'] = bool(shape.isValid())
            row['solid_count'] = len(shape.Solids)
            row['volume_mm3'] = h['number'](shape.Volume)
    except Exception as exc:
        row['error'] = error(exc)
    return row


def snapshot(doc, names, h):
    rows = h['snapshot'](doc, names)
    for row in rows:
        obj = doc.getObject(row['name'])
        if obj is None:
            continue
        for key in ('AssumedDensityKgM3', 'CountsInStructuralSubtotal'):
            row[key] = None
            if key in obj.PropertiesList:
                try:
                    value = getattr(obj, key)
                    row[key] = bool(value) if key == 'CountsInStructuralSubtotal' else h['number'](value)
                except Exception as exc:
                    row['errors'].append(key + ': ' + error(exc))
    return rows


def main():
    root = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
    paths = {key: (root / value[0]).resolve() for key, value in FILES.items()}
    own, out = (root / SELF).resolve(), (root / OUT).resolve()
    for path in [*paths.values(), own, out]:
        if not path.is_relative_to(root):
            raise ValueError('Path escaped sandbox')
    if out.exists():
        raise FileExistsError('Preserve previous or partial observations: ' + str(out))
    for key, path in paths.items():
        if sha(path) != FILES[key][1]:
            raise ValueError('Pinned input bytes differ: ' + key)

    def fingerprints():
        result = {key: {'path': FILES[key][0], 'sha256': sha(path)}
                  for key, path in paths.items()}
        result['inspection_source'] = {'path': SELF, 'sha256': sha(own)}
        return result

    before = fingerprints()
    h = {'__name__': 'pdr_r12_reopen_observation_helpers', '__file__': str(paths['helpers'])}
    exec(compile(paths['helpers'].read_bytes(), str(paths['helpers']), 'exec'), h)
    cfg = json.loads(paths['configuration'].read_text(encoding='utf-8'))
    generation = json.loads(paths['generation_observations'].read_text(encoding='utf-8'))
    expected = h['expected_physical_names'](cfg)
    report = {
        'schema': 'hopper_unrefined_export_integrity_observations/1',
        'timestamp_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'FreeCAD_version': list(App.Version()),
        'authority': cfg['authority'],
        'refinement_decision': '32c12da080c74e29afe522cbfc9525c3 revision 1',
        'inputs_before': before,
        'expected_physical_names': expected,
        'generation_physical_names': sorted(row['name'] for row in generation['physical_inventory']),
        'generation_drawing_omission_count': generation.get('drawing_omission_count'),
        'units': {'length': 'mm', 'volume': 'mm^3', 'density': 'kg/m^3'},
        'errors': [], 'native_snapshots': {},
        'dimension_or_refinement_edits': False,
        'native_saved': False, 'geometry_repaired_by_inspector': False,
        'descriptor_nomination_hypotheses': NOMINATION,
        'correspondence_candidates': [],
        'descriptor_candidate_bijection_only': None,
        'STEP_component_material_correspondence_accepted': None,
        'geometry_acceptance': None, 'complete_vehicle_mass_kg': None,
        'evidence_boundary': 'Reopened artifact observations only. Descriptor nomination and same-kernel Boolean operations do not establish physical acceptance.'
    }
    doc = None
    final_solids = {}
    try:
        for existing in App.listDocuments().values():
            if existing.FileName and Path(existing.FileName).resolve() == paths['native']:
                raise ValueError('Preserve already-open input native document')
        doc = App.openDocument(str(paths['native']))
        group = doc.getObject('PhysicalComponents')
        actual = [obj.Name for obj in group.Group] if group is not None else []
        report['native_group_names'] = actual
        report['missing_expected_names'] = sorted(set(expected) - set(actual))
        report['unexpected_group_names'] = sorted(set(actual) - set(expected))
        names = sorted(set(expected) | set(actual))
        report['native_snapshots']['opened_before_explicit_recompute'] = snapshot(doc, names, h)
        try:
            report['ordinary_recompute_return'] = str(doc.recompute())
        except Exception as exc:
            report['errors'].append('Ordinary recompute: ' + error(exc))
        report['native_snapshots']['ordinary_recomputed'] = snapshot(doc, names, h)
        touched = []
        for obj in doc.Objects:
            try:
                obj.touch()
                touched.append(obj.Name)
            except Exception as exc:
                report['errors'].append('Touch ' + obj.Name + ': ' + error(exc))
        report['forced_recompute_touched_names'] = touched
        try:
            report['forced_recompute_return'] = str(doc.recompute())
        except Exception as exc:
            report['errors'].append('Forced recompute: ' + error(exc))
        report['native_snapshots']['forced_recomputed'] = snapshot(doc, names, h)
        targets = ['JunctionUnbored_%02d' % i for i in range(1, 5)]
        report['reopened_target_refinement_settings'] = {
            name: (bool(doc.getObject(name).Refine) if doc.getObject(name) is not None
                   and 'Refine' in doc.getObject(name).PropertiesList else None)
            for name in targets
        }
        dependencies = h['dependency_names'](doc, ['BraceJunctionFitting_%02d' % i for i in range(1, 5)])
        shape_dependencies = [name for name in dependencies if hasattr(doc.getObject(name), 'Shape')]
        report['forced_junction_dependency_observations'] = h['snapshot'](doc, shape_dependencies)
        for name in expected:
            try:
                obj = doc.getObject(name)
                if obj is None:
                    raise ValueError('Expected object missing')
                shape = h['world_shape'](obj)
                if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
                    raise ValueError('Correspondence requires a valid single native solid')
                solid = shape.Solids[0].copy()
                observed = descriptor(solid, h)
                if not observed['valid'] or observed['volume_mm3'] <= 0:
                    raise ValueError('Invalid or nonpositive native solid')
                final_solids[name] = (solid, observed)
            except Exception as exc:
                report['errors'].append('Native correspondence input ' + name + ': ' + error(exc))
    except Exception as exc:
        report['errors'].append('Native inspection: ' + error(exc))
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)

    try:
        step_shape = Part.read(str(paths['STEP']))
        report['STEP_shape'] = h['shape_observation'](step_shape)
        step_solids = list(step_shape.Solids)
        step_descriptors = []
        for index, solid in enumerate(step_solids, 1):
            try:
                step_descriptors.append({'STEP_index': index, 'descriptor': descriptor(solid, h), 'error': None})
            except Exception as exc:
                step_descriptors.append({'STEP_index': index, 'descriptor': None, 'error': error(exc)})
        report['STEP_solid_descriptors'] = step_descriptors
        claims = {index: [] for index in range(1, len(step_solids) + 1)}
        for name, (native, nd) in sorted(final_solids.items()):
            row = {'native_name': name, 'native_descriptor': nd,
                   'nominated_STEP_indices': [], 'nearest_descriptor_observations': [],
                   'candidate_boolean_observations': []}
            residuals = []
            for entry in step_descriptors:
                sd = entry['descriptor']
                if sd is None:
                    continue
                residual = gaps(nd, sd)
                residuals.append({'STEP_index': entry['STEP_index'], **residual})
                if not nominated(nd, sd, residual):
                    continue
                index = entry['STEP_index']
                row['nominated_STEP_indices'].append(index)
                claims[index].append(name)
                ss = step_solids[index-1]
                row['candidate_boolean_observations'].append({
                    'STEP_index': index, 'descriptor_residuals': residual,
                    'common': boolean_observation(lambda: native.common(ss), h),
                    'native_minus_STEP': boolean_observation(lambda: native.cut(ss), h),
                    'STEP_minus_native': boolean_observation(lambda: ss.cut(native), h),
                    'equivalence_accepted': None
                })
            row['nearest_descriptor_observations'] = sorted(residuals, key=lambda x: (
                x['centroid_distance_mm'], x['maximum_bbox_coordinate_difference_mm'],
                abs(x['signed_volume_difference_mm3'])))[:3]
            report['correspondence_candidates'].append(row)
        report['STEP_candidate_claims'] = [{'STEP_index': index, 'native_names': names}
                                            for index, names in claims.items()]
        report['descriptor_candidate_bijection_only'] = (
            len(final_solids) == len(expected) == len(step_solids) and
            all(len(row['nominated_STEP_indices']) == 1 for row in report['correspondence_candidates']) and
            all(len(names) == 1 for names in claims.values()))
    except Exception as exc:
        report['errors'].append('STEP/correspondence inspection: ' + error(exc))

    report['inputs_after'] = fingerprints()
    report['input_bytes_unchanged'] = before == report['inputs_after']
    report['unperformed'] = [
        'Artifact-bound VerificationResult assessment of these observations',
        'Unsaved parameter perturbation/restoration and downstream topology assessment',
        'All physical pair intersections, contacts, bore separation and residual webs',
        'Assembly insertion/access and positive secondary retention',
        'Partial material-based mass, CG and full inertia reconciliation',
        'Retained 97-pose moving-envelope and finite-pad ground assessment',
        'Continuous, deformed and manufacturing-tolerance clearance',
        'Drawing-omission resolution and visual review',
        'Structural, joint, actuator, electrical and physical qualification',
        'Complete installed mass, mission energy, purchased budget and review acceptance'
    ]
    summary = {
        'schema': 'hopper_unrefined_export_integrity_summary/1',
        'inputs': before,
        'expected_component_count': len(expected),
        'native_group_count': len(report.get('native_group_names', [])),
        'missing_expected_names': report.get('missing_expected_names'),
        'unexpected_group_names': report.get('unexpected_group_names'),
        'native_phase_issues': {phase: h['issues'](rows)
                               for phase, rows in report['native_snapshots'].items()},
        'forced_physical_states': {row['name']: row.get('state') for row in
                                   report['native_snapshots'].get('forced_recomputed', [])},
        'reopened_target_refinement_settings': report.get('reopened_target_refinement_settings'),
        'STEP_solid_count': (report.get('STEP_shape') or {}).get('solid_count'),
        'STEP_shape_valid': (report.get('STEP_shape') or {}).get('is_valid'),
        'descriptor_candidate_bijection_only': report['descriptor_candidate_bijection_only'],
        'candidate_counts': {row['native_name']: len(row['nominated_STEP_indices'])
                             for row in report['correspondence_candidates']},
        'Boolean_observations': [
            {'native_name': row['native_name'], **candidate}
            for row in report['correspondence_candidates']
            for candidate in row['candidate_boolean_observations']
        ],
        'generation_drawing_omission_count': report['generation_drawing_omission_count'],
        'input_bytes_unchanged': report['input_bytes_unchanged'],
        'errors': report['errors'],
        'STEP_component_material_correspondence_accepted': None,
        'geometry_acceptance': None,
        'unperformed': report['unperformed'],
        'interpretation': 'Component nomination is independent of STEP solid order but is not an acceptance result. Preserve all failed or ambiguous observations.'
    }
    out.mkdir(parents=True, exist_ok=False)
    h['dump'](out / 'observations.json', report)
    h['dump'](out / 'summary.json', summary)
    print('Saved independent export observations; no acceptance established: ' + OUT, file=sys.stderr)


if __name__ == '__main__':
    main()
