"""Export the unselected PDR-r12 physical-integration prototype.

Run only through freecad_run(headless=True), with this driver and the
published geometry/configuration artifact Refs included in tool inputs.
Declare these seven outputs, all under OUT_REL below:
  physical_integration_prototype_01.FCStd
  physical_integration_prototype_01_physical.step
  physical_integration_prototype_01_arrangement.svg
  component_interface_ledger_01.json
  generation_observations_01.json
  drawing_diagnostics_01.json
  output_manifest_01.json

This driver generates and exports geometry. Initial topology observations
are NOT a VerificationResult. It does not independently reopen the exports,
compute accepted mass properties, inspect assembly insertion, or certify
clearance/strength. Those remain subsequent artifact-bound inspection work.
No supplied checkout, existing source or previous output is modified.
"""

import datetime
import hashlib
import json
import math
import os
from pathlib import Path
from xml.sax.saxutils import escape

import FreeCAD as App
import Part

DRIVER_REL = 'cad/pdr_r12_chief/build_physical_integration_prototype_20261014_01.py'
GEOMETRY_REL = 'cad/pdr_r12_chief/physical_integration_geometry_20261014_01.py'
GEOMETRY_SHA = 'c8e74b814c41899236df91d885abc876c5e0f950a514f19d4719a61a0aeee7e6'
CONFIG_REL = 'cad/pdr_r12_chief/physical_integration_prototype_config_20261014_01.json'
CONFIG_SHA = 'be78fc14b24b01cd824e1bf90625c415176b27ecae2dca26dff8ac790de1e9b0'
OUT_REL = 'cad/pdr_r12_chief/physical_integration_prototype_20261014_01'
OUTPUT_NAMES = [
    'physical_integration_prototype_01.FCStd',
    'physical_integration_prototype_01_physical.step',
    'physical_integration_prototype_01_arrangement.svg',
    'component_interface_ledger_01.json',
    'generation_observations_01.json',
    'drawing_diagnostics_01.json',
    'output_manifest_01.json'
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(root, path):
    return {'path': str(path.relative_to(root)), 'sha256': sha(path)}


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def xyz(point):
    values = [float(point.x), float(point.y), float(point.z)]
    if not all(math.isfinite(x) for x in values):
        raise ValueError('Nonfinite CAD coordinate')
    return values


def world_shape(obj):
    # Leaf Shape already contains its own Placement; apply ancestors only.
    shape = obj.Shape.copy()
    ancestors = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    shape.Placement = ancestors.multiply(shape.Placement)
    return shape


def bounds(shape):
    bb = shape.BoundBox
    return [[float(getattr(bb, axis + 'Min')), float(getattr(bb, axis + 'Max'))]
            for axis in ('X', 'Y', 'Z')]


def initial_inventory(objects):
    rows = []
    for obj in objects:
        row = {'name': obj.Name, 'native_type': obj.TypeId,
               'material_hypothesis': str(obj.MaterialHypothesis),
               'density_hypothesis_kg_m3': float(obj.AssumedDensityKgM3),
               'moving_group': str(obj.MovingGroup),
               'role': str(obj.PhysicalRole), 'inspection_error': None}
        try:
            shape = world_shape(obj)
            row['shape_is_null'] = bool(shape.isNull())
            row['shape_valid'] = bool(shape.isValid())
            row['solid_count'] = len(shape.Solids)
            row['solid_observations'] = [
                {'index_within_component': index,
                 'valid': bool(solid.isValid()),
                 'volume_mm3': float(solid.Volume),
                 'cg_CAD_mm': xyz(solid.CenterOfMass),
                 'bounding_box_CAD_mm': bounds(solid)}
                for index, solid in enumerate(shape.Solids, 1)
            ]
            row['bounding_box_CAD_mm'] = None if shape.isNull() else bounds(shape)
        except Exception as exc:
            row['inspection_error'] = type(exc).__name__ + ': ' + str(exc)
        rows.append(row)
    return rows


def draw_arrangement(path, physical, references):
    """Approximate neutral projections from actual shape edges, with omissions."""
    colors = {
        'CFRP': '#172a3a',
        'PETG_assumed_full_density': '#286bba',
        'unspecified_adhesive_density_hypothesis': '#a83882',
        'unspecified_compliant_pad_density_hypothesis': '#555555',
        'non_mass_reference': '#bc6800'
    }
    polylines, omissions, object_rows = [], [], []
    for obj in physical + references:
        reference = obj in references
        material = 'non_mass_reference' if reference else str(obj.MaterialHypothesis)
        row = {'name': obj.Name, 'category': material, 'edge_count': None,
               'rendered_edges': 0, 'omitted_edges': 0}
        object_rows.append(row)
        try:
            shape = world_shape(obj)
            if shape.isNull():
                raise ValueError('Null shape has no drawable edges')
            edges = list(shape.Edges)
            row['edge_count'] = len(edges)
        except Exception as exc:
            omissions.append({'object': obj.Name, 'edge': None,
                              'reason': type(exc).__name__ + ': ' + str(exc)})
            continue
        for index, edge in enumerate(edges, 1):
            try:
                points = [xyz(p) for p in edge.discretize(Number=24)]
                if len(points) < 2:
                    raise ValueError('Fewer than two discretized points')
                polylines.append({'name': obj.Name, 'edge': index,
                                  'points': points, 'reference': reference,
                                  'color': colors.get(material, '#111111')})
                row['rendered_edges'] += 1
            except Exception as exc:
                row['omitted_edges'] += 1
                omissions.append({'object': obj.Name, 'edge': index,
                                  'reason': type(exc).__name__ + ': ' + str(exc)})
    points = [p for line in polylines for p in line['points']]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1000" viewBox="0 0 1400 1000">',
        '<rect width="1400" height="1000" fill="white"/>',
        '<g font-family="sans-serif" fill="#111">',
        '<text x="25" y="30" font-size="20">PDR-r12 physical-integration prototype 01 — UNSELECTED</text>',
        '<text x="25" y="54" font-size="13">Neutral arrangement; CAD coordinates in mm. Not a manufacturing drawing or geometry acceptance.</text>',
        '<text x="25" y="76" font-size="13">CFRP: dark; PETG: blue; adhesive: magenta; pads: grey; non-mass rotor/yoke references: dashed orange.</text>',
        '<text x="25" y="98" font-size="13">Actual edges sampled at 24 points; no hidden-line removal. Geometry and materials remain hypotheses.</text>',
        '<text x="25" y="120" font-size="13">Drawing omissions: %d. Consult drawing_diagnostics_01.json; omitted edges are not repaired or concealed.</text>' % len(omissions)
    ]
    view_rows = []
    if points:
        for axes, box, title in [
            ((0, 2), (25, 165, 650, 730), 'CAD X-Z projection'),
            ((0, 1), (725, 165, 650, 730), 'CAD X-Y projection')
        ]:
            i, j = axes
            lo_i, hi_i = min(p[i] for p in points), max(p[i] for p in points)
            lo_j, hi_j = min(p[j] for p in points), max(p[j] for p in points)
            x, y, width, height = box
            factor = min((width-30)/max(hi_i-lo_i, 1),
                         (height-65)/max(hi_j-lo_j, 1))
            svg.append('<text x="%g" y="%g" font-size="15">%s</text>' % (x, y-15, title))
            for line in polylines:
                coordinates = ' '.join('%.4f,%.4f' %
                    (x+15+(p[i]-lo_i)*factor, y+10+(hi_j-p[j])*factor)
                    for p in line['points'])
                dash = ' stroke-dasharray="4 3"' if line['reference'] else ''
                svg.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="0.65"%s><title>%s edge %d</title></polyline>' %
                           (coordinates, line['color'], dash, escape(line['name']), line['edge']))
            svg.append('<path d="M %g %g h %g" stroke="black"/><text x="%g" y="%g" font-size="12">100 mm scale bar</text>' %
                       (x+15, y+height-22, 100*factor, x+15, y+height-4))
            view_rows.append({'axes': list(axes), 'SVG_units_per_CAD_mm': factor,
                              'sampled_projected_extents_mm': [[lo_i, hi_i], [lo_j, hi_j]]})
    else:
        svg.append('<text x="25" y="190" font-size="18">No drawable edges recovered; inspect diagnostics.</text>')
    svg.extend([
        '<text x="25" y="945" font-size="13">Rotor diameter hypothesis 279.4 mm; foot socket radius 400 mm; ring attachment Z=430 mm.</text>',
        '<text x="25" y="968" font-size="13">Missing: moving carriers, bearings, actuators, equipment, fasteners and qualified retention. No complete-vehicle mass claim.</text>',
        '</g></svg>'
    ])
    with path.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(svg) + '\n')
    return {
        'schema': 'hopper_preliminary_drawing_diagnostics/1',
        'scope': 'Neutral sampled-edge projections; not visual inspection or dimensional acceptance',
        'objects': object_rows, 'views': view_rows, 'omissions': omissions,
        'rendered_polyline_count': len(polylines),
        'drawing_complete': bool(points) and not omissions,
        'hidden_line_removal': False, 'visual_review_performed': False,
        'manufacturing_drawing': False
    }


def main():
    root = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
    driver = root / DRIVER_REL
    geometry = root / GEOMETRY_REL
    config = root / CONFIG_REL
    out = (root / OUT_REL).resolve()
    for path in (driver, geometry, config, out):
        if not path.resolve().is_relative_to(root):
            raise ValueError('Path escaped sandbox')
    if sha(geometry) != GEOMETRY_SHA or sha(config) != CONFIG_SHA:
        raise ValueError('Published geometry/configuration bytes do not match')
    before = [identity(root, path) for path in (driver, geometry, config)]
    cfg = json.loads(config.read_text(encoding='utf-8'))
    if cfg['execution_contract']['future_output_directory'] != OUT_REL:
        raise ValueError('Output directory differs from published configuration')
    if out.exists():
        raise FileExistsError('Preserve previous or partial output directory: ' + str(out))
    out.mkdir(parents=True)

    # Execute only the inspected, hash-pinned module definition. No source
    # rewriting, generated wrapper copies or Python bytecode files are needed.
    namespace = {'__name__': 'pdr_r12_physical_integration_geometry',
                 '__file__': str(geometry)}
    exec(compile(geometry.read_bytes(), str(geometry), 'exec'), namespace)
    built = namespace['build_document'](root)
    doc = built['document']
    try:
        physical = built['physical_objects']
        references = built['moving_reference_objects']
        physical_names = [o.Name for o in physical]
        reference_names = [o.Name for o in references]
        if len(physical_names) != len(set(physical_names)):
            raise ValueError('Duplicate physical ownership')
        if set(physical_names).intersection(reference_names):
            raise ValueError('Non-mass reference included as physical material')
        if {o.Name for o in doc.getObject('PhysicalComponents').Group} != set(physical_names):
            raise ValueError('Physical export inventory differs from native group')
        if any(not o.CountsInStructuralSubtotal for o in physical):
            raise ValueError('Non-mass object in physical export list')
        if any(o.CountsInStructuralSubtotal for o in references):
            raise ValueError('Moving reference incorrectly marked for mass')
        doc.recompute()
        inventory = initial_inventory(physical)

        # Preserve the editable native artifact and export EVERY separately
        # owned physical component. No pair exclusions, component fusion,
        # collider removal or geometry repairs occur in this driver.
        native = out / OUTPUT_NAMES[0]
        step = out / OUTPUT_NAMES[1]
        doc.saveAs(str(native))
        Part.export(physical, str(step))

        ledger = {
            'schema': 'hopper_preliminary_component_interface_ledger/1',
            'configuration_sha256': CONFIG_SHA,
            'geometry_source_sha256': GEOMETRY_SHA,
            'candidate_status': 'unselected_partial_physical_integration_prototype',
            'component_ledger': built['component_ledger'],
            'physical_native_names': physical_names,
            'STEP_export_names': physical_names,
            'intended_interfaces': built['intended_interfaces'],
            'tube_cut_hypotheses': built['tube_cut_hypotheses'],
            'joint_geometry_index': built['joint_geometry_index'],
            'through_cutting_tool_index': built['through_cutting_tool_index'],
            'excluded_non_mass_references': reference_names,
            'excluded_diagnostics': [o.Name for o in built['diagnostic_objects']],
            'units_and_frames': cfg['units_and_frames'],
            'material_and_mass_ownership': cfg['material_and_mass_ownership'],
            'scope': 'Construction and ownership ledger; intended contacts are not observed contacts or qualified retention',
            'assembly_access_demonstrated': None,
            'positive_retention_qualified': None,
            'complete_vehicle_mass_kg': None,
            'complete_vehicle_CG_CAD_mm': None,
            'complete_vehicle_inertia_kg_m2': None
        }
        dump(out / OUTPUT_NAMES[3], ledger)
        drawing = draw_arrangement(out / OUTPUT_NAMES[2], physical, references)
        dump(out / OUTPUT_NAMES[5], drawing)
        after = [identity(root, path) for path in (driver, geometry, config)]
        if before != after:
            raise RuntimeError('An input changed during generation')
        observations = {
            'schema': 'hopper_physical_integration_generation_observations/1',
            'generated_at_UTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'authority': cfg['authority'],
            'inputs_before': before, 'inputs_after': after,
            'input_bytes_unchanged': before == after,
            'FreeCAD_version': list(App.Version()),
            'physical_component_count': len(physical),
            'physical_inventory': inventory,
            'native_file': identity(root, native),
            'physical_STEP_file': identity(root, step),
            'drawing_omission_count': len(drawing['omissions']),
            'evidence_boundary': 'Initial in-memory solid observations and exported files only; not independent reopened inspection or a VerificationResult',
            'geometry_changed_by_driver': False,
            'unperformed': [
                'Independent native/STEP reopen and heterogeneous-material correspondence',
                'Unsaved parameter perturbation and restoration after reopen',
                'All physical pair distances, common volumes and intended contacts',
                'Bore separation, residual webs, insertion and assembly sequence',
                'Material-based partial mass, CG and full inertia reconciliation',
                'Retained 97-pose rotor/yoke sampling and finite-pad ground observations',
                'Continuous, deformed and tolerance-aware clearance',
                'Structural, joint, actuator, electrical and hardware qualification',
                'Complete installed mass, propulsion energy and purchased cost closure',
                'PDR/CDR and flight acceptance'
            ],
            'geometry_acceptance': None,
            'structural_selection': None,
            'physical_validation': None
        }
        dump(out / OUTPUT_NAMES[4], observations)
        files = [identity(root, out / name) for name in OUTPUT_NAMES[:-1]]
        dump(out / OUTPUT_NAMES[6], {
            'schema': 'hopper_preliminary_output_manifest/1',
            'inputs': before, 'files': files,
            'manifest_path': str((out / OUTPUT_NAMES[6]).relative_to(root)),
            'manifest_self_hash_omitted': True,
            'evidence_boundary': 'Produced artifacts do not imply geometry, structural or review acceptance'
        })
        print(json.dumps({'output_directory': OUT_REL,
                          'physical_component_count': len(physical),
                          'declared_output_count': len(OUTPUT_NAMES),
                          'drawing_omission_count': len(drawing['omissions']),
                          'acceptance': 'not established'}))
    finally:
        # Never save an inspection edit or alter historical native artifacts.
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    main()
