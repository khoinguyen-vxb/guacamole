"""Isolated FreeCAD capability/units fixture; NOT vehicle hardware.
Run this saved script exclusively through freecad_run(headless=True).
Declare all three generated outputs:
  cad/pdr_r8_cad/r8_solid_fixture_01.FCStd
  cad/pdr_r8_cad/r8_solid_fixture_01.step
  cad/pdr_r8_cad/r8_solid_fixture_01_measurements.json

Correction provenance:
  Human diagnostics: source 6461e706a0c84ff394997606ff098cdb revision 1.
  Complete r7 script: tool_result 2ab7e366ee2f49279f631b8a46bb94e6 revision 1.
  Existing r7 directory: tool_result 08ee4447f30041ac8b39b507519947a3 revision 1.
  Authorization: decision d7ce8230da9d4545b5a79427bd75a7de revision 1.
Generic Part.Shape may lack CenterOfMass and MatrixOfInertia. Require exactly
one solid and read ALL geometric mass properties from that Part.Solid.
Existing r7 files are neither opened for writing nor removed.
Independent artifact-bound verification must follow publication of outputs.
"""
import hashlib
import json
import math
import os
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
OUT = ROOT / 'cad' / 'pdr_r8_cad'
OUT.mkdir(parents=True, exist_ok=True)
SCRIPT = OUT / 'r8_solid_fixture_01.py'
NATIVE = OUT / 'r8_solid_fixture_01.FCStd'
STEP = OUT / 'r8_solid_fixture_01.step'
REPORT = OUT / 'r8_solid_fixture_01_measurements.json'

# Guard every generated output before creating any document or export.
# A failed run may leave partial outputs: preserve them and use a fresh stem.
for path in (NATIVE, STEP, REPORT):
    if path.exists() or path.is_symlink():
        raise FileExistsError('Preserve existing fixture output: ' + str(path))
if not SCRIPT.is_file():
    raise FileNotFoundError('The saved generator must exist: ' + str(SCRIPT))


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Non-finite geometric measurement')
    return number


def measure_single_solid(shape):
    if shape.isNull():
        raise ValueError('Fixture shape is null')
    solids = list(shape.Solids)
    if len(solids) != 1:
        raise ValueError('Fixture requires exactly one solid; got %d' % len(solids))
    solid = solids[0]
    if solid.ShapeType != 'Solid':
        raise TypeError('Expected Part.Solid, got ' + str(solid.ShapeType))
    # Never read CenterOfMass or MatrixOfInertia from the generic input shape.
    bb = solid.BoundBox
    cm = solid.CenterOfMass
    matrix = solid.MatrixOfInertia
    raw = [[finite(getattr(matrix, 'A%d%d' % (i, j)))
            for j in range(1, 4)] for i in range(1, 4)]
    volume = finite(solid.Volume)
    rho = 2700.0  # Assumption for this numerical units fixture ONLY.
    return {
        'input_shape_type': str(shape.ShapeType),
        'input_shape_is_valid': bool(shape.isValid()),
        'measured_shape_type': str(solid.ShapeType),
        'solid_count': len(solids),
        'is_valid': bool(solid.isValid()),
        'volume_mm3': volume,
        'bounding_box_mm': {
            'min': [finite(bb.XMin), finite(bb.YMin), finite(bb.ZMin)],
            'max': [finite(bb.XMax), finite(bb.YMax), finite(bb.ZMax)],
            'size': [finite(bb.XLength), finite(bb.YLength), finite(bb.ZLength)]
        },
        'center_of_mass_mm': [finite(cm.x), finite(cm.y), finite(cm.z)],
        'geometric_inertia_matrix_mm5': raw,
        'inertia_reference': 'sole solid center of mass; CAD axes',
        'assumed_uniform_density_kg_m3': rho,
        'density_assumption_scope': 'units fixture only; not a vehicle material selection',
        'mass_kg': volume * rho * 1e-9,
        'inertia_kg_m2': [[entry * rho * 1e-15 for entry in row] for row in raw]
    }


script_hash_before = sha256_file(SCRIPT)
doc = App.newDocument('R8SolidCapabilityFixture01')
try:
    box = doc.addObject('Part::Box', 'UnitsFixtureBox')
    box.Label = 'CAPABILITY FIXTURE ONLY - NOT VEHICLE HARDWARE'
    box.Length = 10.0
    box.Width = 20.0
    box.Height = 30.0
    box.Placement.Base = App.Vector(11.0, 17.0, 23.0)
    doc.recompute()
    # Fail explicitly before export if the generator does not produce one solid.
    measure_single_solid(box.Shape)
    doc.saveAs(str(NATIVE))
    Part.export([box], str(STEP))
finally:
    App.closeDocument(doc.Name)

export_hashes_before = {
    str(path.relative_to(ROOT)): sha256_file(path)
    for path in (NATIVE, STEP)
}

# Measure the actual reopened exports, not merely the generating object.
reopened = App.openDocument(str(NATIVE))
try:
    reopened.recompute()
    obj = reopened.getObject('UnitsFixtureBox')
    if obj is None:
        raise RuntimeError('Parametric box missing from reopened native export')
    geometry_objects = [item for item in reopened.Objects
                        if hasattr(item, 'Shape') and not item.Shape.isNull()]
    if len(geometry_objects) != 1:
        raise ValueError('Native fixture requires exactly one geometry object')
    native_measurements = measure_single_solid(obj.Shape)
    native_measurements['geometry_object_count'] = len(geometry_objects)
    native_measurements['object_type'] = str(obj.TypeId)
    native_measurements['object_name'] = str(obj.Name)
    native_measurements['editable_dimensions_mm'] = {
        'length': finite(obj.Length.Value),
        'width': finite(obj.Width.Value),
        'height': finite(obj.Height.Value)
    }
    native_measurements['placement_base_mm'] = [
        finite(obj.Placement.Base.x), finite(obj.Placement.Base.y),
        finite(obj.Placement.Base.z)
    ]
    # Demonstrate parameter response on the reopened native document in memory.
    # Never save these probes: artifact hashes must remain unchanged.
    edit_probes = []
    for name in ('Length', 'Width', 'Height'):
        original = finite(getattr(obj, name).Value)
        try:
            setattr(obj, name, original + 1.0)
            reopened.recompute()
            probe = measure_single_solid(obj.Shape)
            edit_probes.append({
                'parameter': name,
                'original_value_mm': original,
                'requested_value_mm': original + 1.0,
                'readback_value_mm': finite(getattr(obj, name).Value),
                'volume_mm3': probe['volume_mm3'],
                'bounding_box_size_mm': probe['bounding_box_mm']['size'],
                'solid_count': probe['solid_count'],
                'is_valid': probe['is_valid']
            })
        finally:
            setattr(obj, name, original)
            reopened.recompute()
    native_measurements['in_memory_parameter_edit_probes_not_saved'] = edit_probes
    native_measurements['restored_after_probes'] = measure_single_solid(obj.Shape)
finally:
    App.closeDocument(reopened.Name)

step_shape = Part.read(str(STEP))
step_measurements = measure_single_solid(step_shape)
export_hashes_after = {
    str(path.relative_to(ROOT)): sha256_file(path)
    for path in (NATIVE, STEP)
}
if export_hashes_before != export_hashes_after:
    raise RuntimeError('An export changed during readback; measurements are not bound')
if sha256_file(SCRIPT) != script_hash_before:
    raise RuntimeError('Generator changed during execution')

report = {
    'schema': 'r8_single_solid_fixture_measurements_v1',
    'status': 'capability_fixture_measurements_only',
    'independent_verification': 'pending',
    'physical_acceptance': 'not_assessed',
    'vehicle_baseline': False,
    'freecad_version': list(App.Version()),
    'generator': {
        'path': str(SCRIPT.relative_to(ROOT)),
        'sha256': script_hash_before
    },
    'native_export': str(NATIVE.relative_to(ROOT)),
    'step_export': str(STEP.relative_to(ROOT)),
    'artifact_sha256_before_readback': export_hashes_before,
    'artifact_sha256_after_readback': export_hashes_after,
    'fixture_definition': {
        'dimensions_mm': [10.0, 20.0, 30.0],
        'translation_mm': [11.0, 17.0, 23.0],
        'uniform_density_kg_m3': 2700.0,
        'density_status': 'assumed numerical fixture value'
    },
    'units': {
        'CAD_length': 'mm',
        'CAD_volume': 'mm^3',
        'raw_solid_inertia': 'mm^5',
        'density': 'kg/m^3',
        'mass': 'kg',
        'density_weighted_inertia': 'kg m^2',
        'volume_to_m3_factor': 1e-9,
        'geometric_inertia_to_m5_factor': 1e-15
    },
    'native_reopened': native_measurements,
    'step_reimported': step_measurements,
    'limitations': [
        'Measurements are not an independent VerificationResult.',
        'No GUI-addon capability is inferred.',
        'No vehicle geometry, interface, clearance, strength or flight acceptance is inferred.',
        'Native edit probes were performed in memory without saving the exports.',
        'The measurement file hash is retained by the runtime ProducedFile record; no self-hash is embedded.'
    ]
}
with REPORT.open('x', encoding='utf-8') as stream:
    stream.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
print(json.dumps({
    'status': report['status'],
    'report': str(REPORT.relative_to(ROOT)),
    'independent_verification': 'pending',
    'physical_acceptance': 'not_assessed'
}, allow_nan=False))
