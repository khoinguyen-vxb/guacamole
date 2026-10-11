"""Isolated FreeCAD capability/units fixture; NOT a vehicle assembly.
Run only through freecad_run(headless=True).
Declare these sandbox-relative outputs in that action:
  cad/pdr_r7_cad/r7_headless_fixture.FCStd
  cad/pdr_r7_cad/r7_headless_fixture.step
  cad/pdr_r7_cad/r7_headless_fixture_measurements.json
Execution and measurements alone do not constitute verification acceptance.
"""
import json
import os
from pathlib import Path
import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
OUT = ROOT / 'cad' / 'pdr_r7_cad'
OUT.mkdir(parents=True, exist_ok=True)
NATIVE = OUT / 'r7_headless_fixture.FCStd'
STEP = OUT / 'r7_headless_fixture.step'
REPORT = OUT / 'r7_headless_fixture_measurements.json'
# Preserve earlier artifacts rather than silently overwriting a prior run.
for path in (NATIVE, STEP, REPORT):
    if path.exists():
        raise FileExistsError('Fixture output already exists: ' + str(path))


def measure(shape):
    bb = shape.BoundBox
    cm = shape.CenterOfMass
    matrix = shape.MatrixOfInertia
    raw = [[float(getattr(matrix, 'A%d%d' % (i, j)))
            for j in range(1, 4)] for i in range(1, 4)]
    # Shape geometry uses mm. Density is kg/m^3:
    # volume factor = 1e-9; geometric inertia mm^5 factor = 1e-15.
    rho = 2700.0
    return {
        'is_valid': bool(shape.isValid()),
        'solid_count': len(shape.Solids),
        'volume_mm3': float(shape.Volume),
        'bounding_box_mm': {
            'min': [bb.XMin, bb.YMin, bb.ZMin],
            'max': [bb.XMax, bb.YMax, bb.ZMax],
            'size': [bb.XLength, bb.YLength, bb.ZLength]},
        'center_of_mass_mm': [cm.x, cm.y, cm.z],
        'geometric_inertia_matrix_mm5': raw,
        'inertia_reference': 'shape center of mass; CAD axes',
        'assumed_uniform_density_kg_m3': rho,
        'density_assumption_scope': 'units fixture only; not a selected vehicle material',
        'mass_kg': float(shape.Volume) * rho * 1e-9,
        'inertia_kg_m2': [[v * rho * 1e-15 for v in row] for row in raw]}


doc = App.newDocument('R7HeadlessCapabilityFixture')
box = doc.addObject('Part::Box', 'UnitsFixtureBox')
box.Label = 'CAPABILITY FIXTURE ONLY - NOT VEHICLE HARDWARE'
box.Length = 10.0
box.Width = 20.0
box.Height = 30.0
box.Placement.Base = App.Vector(11.0, 17.0, 23.0)
doc.recompute()
doc.saveAs(str(NATIVE))
Part.export([box], str(STEP))
App.closeDocument(doc.Name)

# Measure reopened exports, not only the in-memory generating shape.
reopened = App.openDocument(str(NATIVE))
reopened.recompute()
obj = reopened.getObject('UnitsFixtureBox')
if obj is None:
    raise RuntimeError('Parametric fixture missing from reopened native export')
native_measurements = measure(obj.Shape)
native_measurements['object_type'] = obj.TypeId
native_measurements['editable_dimensions_mm'] = {
    'length': float(obj.Length.Value),
    'width': float(obj.Width.Value),
    'height': float(obj.Height.Value)}
step_shape = Part.read(str(STEP))
step_measurements = measure(step_shape)

report = {
    'status': 'capability_fixture_measurements_only',
    'physical_acceptance': 'not_assessed',
    'vehicle_baseline': False,
    'freecad_version': list(App.Version()),
    'native_export': str(NATIVE.relative_to(ROOT)),
    'step_export': str(STEP.relative_to(ROOT)),
    'native_reopened': native_measurements,
    'step_reimported': step_measurements,
    'analytical_fixture_expectations_not_test_results': {
        'solid_count': 1,
        'volume_mm3': 6000.0,
        'center_of_mass_mm': [16.0, 27.0, 38.0],
        'mass_kg_at_assumed_density': 0.0162,
        'inertia_about_center_of_mass_kg_m2': [
            [1.755e-6, 0.0, 0.0],
            [0.0, 1.35e-6, 0.0],
            [0.0, 0.0, 6.75e-7]]},
    'limitations': [
        'No GUI capability is inferred from this script.',
        'No vehicle structure, component interface, clearance or load acceptance is inferred.',
        'An independent artifact-driven verifier must compare measurements with expectations.']}
REPORT.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
App.closeDocument(reopened.Name)
print(json.dumps({'status': report['status'], 'report': str(REPORT.relative_to(ROOT))}))
