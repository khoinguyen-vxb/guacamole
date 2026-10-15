"""Synthetic headless capability probe; not hopper geometry acceptance.
Run through freecad_run@1 with headless=True.
Declare all three generated files:
  cad/pdr_trade/capability_probe_01.FCStd
  cad/pdr_trade/capability_probe_01.step
  analysis/pdr_cad_trade/capability_probe_01.json
The editable source is separately produced by write_text@1.
"""
import sys
sys.dont_write_bytecode = True
import json
import math
import os
from pathlib import Path
import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
FILES = {
    'fcstd': 'cad/pdr_trade/capability_probe_01.FCStd',
    'step': 'cad/pdr_trade/capability_probe_01.step',
    'report': 'analysis/pdr_cad_trade/capability_probe_01.json',
}
for relative in FILES.values():
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('Preserve previous outputs; use a new probe revision: ' + str(path))

checks = {}
observations = {}
def close(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-7, abs_tol=1e-9)

def measure(shape):
    solids = list(shape.Solids)
    result = {
        'shape_valid': bool(shape.isValid()),
        'solid_count': len(solids),
        'solids_valid': [bool(s.isValid()) for s in solids],
        'volume_mm3': sum(float(s.Volume) for s in solids),
    }
    if len(solids) == 1:
        solid = solids[0]
        c = solid.CenterOfMass
        matrix = solid.MatrixOfInertia
        result['centroid_mm'] = [float(c.x), float(c.y), float(c.z)]
        result['unit_density_inertia_about_centroid_mm5'] = [
            [float(getattr(matrix, 'A%d%d' % (i, j))) for j in (1, 2, 3)]
            for i in (1, 2, 3)
        ]
    return result

# Native CSG objects avoid dependence on a custom Python Proxy when reopened.
doc = App.newDocument('PDR_CAD_Capability_01')
outer = doc.addObject('Part::Cylinder', 'Outer')
outer.Radius = 5.0
outer.Height = 100.0
inner = doc.addObject('Part::Cylinder', 'Inner')
inner.setExpression('Radius', 'Outer.Radius - 1 mm')
inner.setExpression('Height', 'Outer.Height')
tube = doc.addObject('Part::Cut', 'Tube')
tube.Base = outer
tube.Tool = inner
doc.recompute()
expected_volume = math.pi * (5.0**2 - 4.0**2) * 100.0
observations['initial'] = measure(tube.Shape)
checks['native_boolean_single_valid_solid'] = (
    observations['initial']['shape_valid']
    and observations['initial']['solid_count'] == 1
    and all(observations['initial']['solids_valid'])
)
checks['initial_volume_matches_analytical_tube'] = close(
    observations['initial']['volume_mm3'], expected_volume)

outer.Height = 120.0
doc.recompute()
observations['edited'] = measure(tube.Shape)
checks['parameter_edit_propagates_and_recomputes'] = (
    close(inner.Height.Value, 120.0)
    and close(observations['edited']['volume_mm3'], expected_volume * 1.2)
)
outer.Height = 100.0
doc.recompute()
checks['restored_parameter_volume'] = close(tube.Shape.Solids[0].Volume, expected_volume)

doc.saveAs(str(ROOT / FILES['fcstd']))
Part.export([tube], str(ROOT / FILES['step']))
App.closeDocument(doc.Name)

reopened = App.openDocument(str(ROOT / FILES['fcstd']))
reopened.recompute()
actual = reopened.getObject('Tube').Shape
observations['reopened_fcstd'] = measure(actual)
checks['fcstd_reopens_valid_single_solid'] = (
    observations['reopened_fcstd']['shape_valid']
    and observations['reopened_fcstd']['solid_count'] == 1
    and all(observations['reopened_fcstd']['solids_valid'])
    and close(observations['reopened_fcstd']['volume_mm3'], expected_volume)
)
# Exercise editable native expressions after reopening, without saving a backup.
reopened.getObject('Outer').Height = 110.0
reopened.recompute()
checks['reopened_parameter_edit_propagates'] = close(
    reopened.getObject('Tube').Shape.Solids[0].Volume, expected_volume * 1.1)
reopened.getObject('Outer').Height = 100.0
reopened.recompute()
actual = reopened.getObject('Tube').Shape

step_shape = Part.Shape()
step_shape.read(str(ROOT / FILES['step']))
observations['reopened_step'] = measure(step_shape)
checks['step_reopens_valid_single_solid'] = (
    observations['reopened_step']['shape_valid']
    and observations['reopened_step']['solid_count'] == 1
    and all(observations['reopened_step']['solids_valid'])
    and close(observations['reopened_step']['volume_mm3'], expected_volume)
)

# Synthetic noncontact witness: tube reaches x=5; box starts at x=15.
witness = Part.makeBox(10.0, 10.0, 100.0, App.Vector(15.0, -5.0, 0.0))
distance, point_pairs, _ = actual.distToShape(witness)
common = actual.common(witness)
observations['distance_mm'] = float(distance)
observations['common_volume_mm3'] = sum(float(s.Volume) for s in common.Solids)
observations['nearest_point_pairs_mm'] = [
    [[float(p.x), float(p.y), float(p.z)] for p in pair] for pair in point_pairs
]
checks['distance_matches_analytical_gap'] = close(distance, 10.0)
checks['separated_solids_have_zero_overlap_volume'] = close(
    observations['common_volume_mm3'], 0.0)

# Explicit synthetic uniform-density calculation; not a sourced material value.
rho_kg_m3 = 2700.0
solid = actual.Solids[0]
mass_kg = float(solid.Volume) * rho_kg_m3 * 1e-9
matrix = solid.MatrixOfInertia
inertia_kg_m2 = [
    [float(getattr(matrix, 'A%d%d' % (i, j))) * rho_kg_m3 * 1e-15
     for j in (1, 2, 3)] for i in (1, 2, 3)
]
expected_mass = expected_volume * rho_kg_m3 * 1e-9
ix = expected_mass * (3.0 * (5.0**2 + 4.0**2) + 100.0**2) / 12.0 * 1e-6
iz = expected_mass * (5.0**2 + 4.0**2) / 2.0 * 1e-6
expected_inertia = [[ix, 0.0, 0.0], [0.0, ix, 0.0], [0.0, 0.0, iz]]
checks['solid_mass_matches_analytical_fixture'] = close(mass_kg, expected_mass)
checks['solid_centroid_matches_analytical_fixture'] = all(
    close(v, e) for v, e in zip(observations['reopened_fcstd']['centroid_mm'], [0.0, 0.0, 50.0]))
checks['solid_full_inertia_matches_analytical_fixture'] = all(
    close(inertia_kg_m2[i][j], expected_inertia[i][j])
    for i in range(3) for j in range(3))
observations['synthetic_uniform_density_kg_m3'] = rho_kg_m3
observations['synthetic_mass_kg'] = mass_kg
observations['synthetic_inertia_about_centroid_kg_m2'] = inertia_kg_m2

report = {
    'schema': 'pdr_cad_capability_probe/1',
    'system_model_revision': 1,
    'scope': 'Synthetic headless FreeCAD capability only; not vehicle geometry or physical acceptance.',
    'freecad_version': list(App.Version()),
    'python_version': sys.version,
    'occt_version': str(getattr(Part, 'OCC_VERSION', 'not exposed')),
    'files': FILES,
    'checks': checks,
    'capability_checks_all_true': all(checks.values()),
    'observations': observations,
    'not_performed': [
        'GUI addon connectivity and screenshots',
        'Vehicle geometry, mounting interfaces and articulated clearance',
        'Material qualification, structural loads and physical tests',
    ],
}
App.closeDocument(reopened.Name)
(ROOT / FILES['report']).write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
print(json.dumps({'scope': report['scope'], 'checks': checks}, allow_nan=False))
if not report['capability_checks_all_true']:
    raise RuntimeError('Synthetic capability check failed; inspect retained report and exports.')
