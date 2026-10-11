"""Isolated capability/units fixture; NOT a vehicle assembly.
Run this saved script only through freecad_run(headless=True).
Declare these sandbox-relative outputs:
  cad/pdr_r8_cad/r8_headless_fixture_v1.FCStd
  cad/pdr_r8_cad/r8_headless_fixture_v1.step
  cad/pdr_r8_cad/r8_headless_fixture_v1_measurements.json

Correction: require exactly one solid and obtain all mass properties from
that Part.Solid, never from the generic shape returned by Part.read().
No r7 files are opened for writing. No GUI dependency is introduced.
Measurements and execution are not independent verification acceptance.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
OUT = ROOT / 'cad' / 'pdr_r8_cad'
SCRIPT = OUT / 'r8_headless_fixture_v1.py'
NATIVE = OUT / 'r8_headless_fixture_v1.FCStd'
STEP = OUT / 'r8_headless_fixture_v1.step'
REPORT = OUT / 'r8_headless_fixture_v1_measurements.json'
OUT.mkdir(parents=True, exist_ok=True)
for path in (NATIVE, STEP, REPORT):
    if path.exists():
        raise FileExistsError('Preserving existing fixture output: ' + str(path))

DENSITY_KG_M3 = 2700.0
DIMENSIONS_MM = [10.0, 20.0, 30.0]
TRANSLATION_MM = [11.0, 17.0, 23.0]


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return {
        'path': str(path.relative_to(ROOT)),
        'sha256': digest.hexdigest(),
        'size_bytes': path.stat().st_size,
    }


def measure(shape):
    if shape.isNull():
        raise RuntimeError('Cannot measure a null shape')
    solids = list(shape.Solids)
    if len(solids) != 1:
        raise RuntimeError('Fixture requires exactly one solid; found %d' % len(solids))
    solid = solids[0]
    if solid.ShapeType != 'Solid':
        raise RuntimeError('Expected a Part.Solid mass-property provider')
    bb = solid.BoundBox
    cm = solid.CenterOfMass
    matrix = solid.MatrixOfInertia
    raw = [[float(getattr(matrix, 'A%d%d' % (i, j)))
            for j in range(1, 4)] for i in range(1, 4)]
    volume = float(solid.Volume)
    return {
        'input_shape_type': shape.ShapeType,
        'mass_property_provider_shape_type': solid.ShapeType,
        'input_shape_is_valid': bool(shape.isValid()),
        'is_valid': bool(solid.isValid()),
        'solid_count': len(solids),
        'volume_mm3': volume,
        'bounding_box_mm': {
            'min': [float(bb.XMin), float(bb.YMin), float(bb.ZMin)],
            'max': [float(bb.XMax), float(bb.YMax), float(bb.ZMax)],
            'size': [float(bb.XLength), float(bb.YLength), float(bb.ZLength)],
        },
        'center_of_mass_mm': [float(cm.x), float(cm.y), float(cm.z)],
        'geometric_inertia_matrix_mm5': raw,
        'inertia_reference': 'measured solid center of mass; CAD axes',
        'assumed_uniform_density_kg_m3': DENSITY_KG_M3,
        'density_assumption_scope': 'units fixture only; not a vehicle material selection',
        'mass_kg': volume * DENSITY_KG_M3 * 1e-9,
        'inertia_kg_m2': [
            [value * DENSITY_KG_M3 * 1e-15 for value in row]
            for row in raw
        ],
    }


script_fingerprint = fingerprint(SCRIPT)
doc = App.newDocument('R8HeadlessCapabilityFixtureV1')
try:
    box = doc.addObject('Part::Box', 'UnitsFixtureBox')
    box.Label = 'CAPABILITY FIXTURE ONLY - NOT VEHICLE HARDWARE'
    box.Length, box.Width, box.Height = DIMENSIONS_MM
    box.Placement.Base = App.Vector(*TRANSLATION_MM)
    doc.recompute()
    doc.saveAs(str(NATIVE))
    Part.export([box], str(STEP))
finally:
    App.closeDocument(doc.Name)

before_reopen = {
    'native': fingerprint(NATIVE),
    'step': fingerprint(STEP),
}

# Reopen the saved native artifact. Do not save any subsequent in-memory edits.
reopened = App.openDocument(str(NATIVE))
try:
    reopened.recompute()
    obj = reopened.getObject('UnitsFixtureBox')
    if obj is None or obj.TypeId != 'Part::Box':
        raise RuntimeError('Reopened native artifact lacks the parametric Part::Box')
    native_objects = []
    for candidate in reopened.Objects:
        if hasattr(candidate, 'Shape') and not candidate.Shape.isNull():
            native_objects.append({
                'name': candidate.Name,
                'object_type': candidate.TypeId,
                'solid_count': len(candidate.Shape.Solids),
            })
    if len(native_objects) != 1 or sum(item['solid_count'] for item in native_objects) != 1:
        raise RuntimeError('Native fixture must contain only one non-null shape object with one solid')
    native_measurements = measure(obj.Shape)
    native_measurements['document_shape_objects'] = native_objects
    native_measurements['object_type'] = obj.TypeId
    native_measurements['editable_dimensions_mm'] = {
        'length': float(obj.Length.Value),
        'width': float(obj.Width.Value),
        'height': float(obj.Height.Value),
    }
    native_measurements['dimension_property_types'] = {
        name: obj.getTypeIdOfProperty(name)
        for name in ('Length', 'Width', 'Height')
    }
    native_measurements['placement_translation_mm'] = [
        float(obj.Placement.Base.x),
        float(obj.Placement.Base.y),
        float(obj.Placement.Base.z),
    ]

    # Exercise native parametric editability in memory and retain actual results.
    original_length = float(obj.Length.Value)
    obj.Length = original_length + 1.0
    reopened.recompute()
    edited_measurements = measure(obj.Shape)
    edited_length = float(obj.Length.Value)
    obj.Length = original_length
    reopened.recompute()
    restored_measurements = measure(obj.Shape)
    edit_probe = {
        'scope': 'reopened native document in memory only; never saved',
        'original_length_mm': original_length,
        'requested_length_mm': original_length + 1.0,
        'observed_length_mm': edited_length,
        'edited': edited_measurements,
        'restored': restored_measurements,
    }
finally:
    App.closeDocument(reopened.Name)

# Part.read returns a generic Shape in this build. measure selects its sole Solid.
step_measurements = measure(Part.read(str(STEP)))
after_reopen = {
    'native': fingerprint(NATIVE),
    'step': fingerprint(STEP),
}
if before_reopen != after_reopen:
    raise RuntimeError('Export bytes changed during readback or in-memory edit probe')
if fingerprint(SCRIPT) != script_fingerprint:
    raise RuntimeError('Generator source changed during execution')

report = {
    'schema': 'pdr_r8_cad.capability_fixture_measurements.v1',
    'status': 'capability_fixture_measurements_only',
    'physical_acceptance': 'not_assessed',
    'vehicle_baseline': False,
    'measured_at_utc': datetime.now(timezone.utc).isoformat(),
    'freecad_version': list(App.Version()),
    'generator': script_fingerprint,
    'exports_before_reopen': before_reopen,
    'exports_after_reopen': after_reopen,
    'fixture_specification': {
        'primitive': 'translated axis-aligned rectangular box',
        'dimensions_mm': DIMENSIONS_MM,
        'placement_translation_mm': TRANSLATION_MM,
        'assumed_uniform_density_kg_m3': DENSITY_KG_M3,
        'scope': 'analytical units fixture; not selected hardware',
    },
    'unit_conversions': {
        'length_mm_to_m': 1e-3,
        'volume_mm3_to_m3': 1e-9,
        'geometric_inertia_mm5_to_m5': 1e-15,
        'mass': 'volume_mm3 * density_kg_m3 * 1e-9',
        'inertia': 'geometric_inertia_mm5 * density_kg_m3 * 1e-15',
    },
    'native_reopened': native_measurements,
    'step_reimported': step_measurements,
    'native_in_memory_edit_probe': edit_probe,
    'limitations': [
        'No independent numerical verification result is asserted here.',
        'The verifier must read the actual exports, generator and measurement file and check their hashes.',
        'Native editability was exercised only in memory; the original exported bytes were preserved.',
        'No GUI capability is inferred.',
        'No vehicle structure, interface, clearance, load or physical acceptance is inferred.',
        'This fixture does not supply vehicle mass, CG, inertia or material selections.',
    ],
}
with REPORT.open('x', encoding='utf-8') as handle:
    json.dump(report, handle, indent=2, allow_nan=False)
    handle.write('\n')
print(json.dumps({
    'status': report['status'],
    'physical_acceptance': report['physical_acceptance'],
    'report': str(REPORT.relative_to(ROOT)),
}))
