"""Synthetic headless capability probe under system model revision 2.
Not vehicle geometry acceptance or physical verification.
Run with freecad_run@1, headless=True, declaring these outputs:
  cad/pdr_trade/capability_probe_m2_02.FCStd
  cad/pdr_trade/capability_probe_m2_02.step
  analysis/pdr_cad_trade/capability_probe_m2_02.json
Preserves capability_probe_01.py and any earlier outputs.
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
    'fcstd': 'cad/pdr_trade/capability_probe_m2_02.FCStd',
    'step': 'cad/pdr_trade/capability_probe_m2_02.step',
    'report': 'analysis/pdr_cad_trade/capability_probe_m2_02.json',
}
AUTHORITY = {
    'system_model': {
        'kind': 'system_model', 'id': 'system', 'revision': 2,
        'sha256': '4c93f9bb676b0e59572034a4c2f51438a8d94cd2aa7d9af7830964ee72219b21',
    },
    'work_plan': {
        'kind': 'decision', 'id': 'a37ef3716fce4eb2b2b35919d6cb0b97', 'revision': 1,
        'sha256': '8e7cf79a28ee431b8be3dfece7bf4fca94e60e40a2fa62a0e416e3e4e171772d',
    },
}
for relative in FILES.values():
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('Preserve prior outputs; use a new revision: ' + str(path))

checks = {}
observations = {}

def close(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-7, abs_tol=1e-12)

def matrix_rows(matrix):
    return [[float(getattr(matrix, 'A%d%d' % (i, j)))
             for j in (1, 2, 3)] for i in (1, 2, 3)]

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
        result['centroid_mm'] = [float(c.x), float(c.y), float(c.z)]
        result['unit_density_inertia_about_centroid_mm5'] = matrix_rows(solid.MatrixOfInertia)
    return result

def valid_single_solid(measurement, expected_volume):
    return (measurement['shape_valid']
            and measurement['solid_count'] == 1
            and all(measurement['solids_valid'])
            and close(measurement['volume_mm3'], expected_volume))

# Native CSG and expressions remain editable without a custom Python Proxy.
doc = App.newDocument('PDR_CAD_Capability_M2_02')
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
checks['native_boolean_valid_single_solid_and_analytical_volume'] = valid_single_solid(
    observations['initial'], expected_volume)

outer.Height = 120.0
doc.recompute()
observations['edited'] = measure(tube.Shape)
checks['parameter_edit_propagates_and_recomputes'] = (
    close(inner.Height.Value, 120.0)
    and valid_single_solid(observations['edited'], expected_volume * 1.2))
outer.Height = 100.0
doc.recompute()
checks['restored_parameter_volume'] = close(tube.Shape.Solids[0].Volume, expected_volume)

# Save once: subsequent edit tests are in memory, avoiding undeclared backup files.
doc.saveAs(str(ROOT / FILES['fcstd']))
Part.export([tube], str(ROOT / FILES['step']))
App.closeDocument(doc.Name)

reopened = App.openDocument(str(ROOT / FILES['fcstd']))
reopened.recompute()
actual = reopened.getObject('Tube').Shape
observations['reopened_fcstd'] = measure(actual)
checks['fcstd_reopens_valid_single_solid'] = valid_single_solid(
    observations['reopened_fcstd'], expected_volume)
reopened.getObject('Outer').Height = 110.0
reopened.recompute()
observations['reopened_edited'] = measure(reopened.getObject('Tube').Shape)
checks['reopened_parameter_edit_propagates'] = (
    close(reopened.getObject('Inner').Height.Value, 110.0)
    and valid_single_solid(observations['reopened_edited'], expected_volume * 1.1))
reopened.getObject('Outer').Height = 100.0
reopened.recompute()
actual = reopened.getObject('Tube').Shape
checks['reopened_parameter_restored'] = close(actual.Solids[0].Volume, expected_volume)

step_shape = Part.Shape()
step_shape.read(str(ROOT / FILES['step']))
observations['reopened_step'] = measure(step_shape)
checks['step_reopens_valid_single_solid'] = valid_single_solid(
    observations['reopened_step'], expected_volume)

# Synthetic witness: tube reaches x=5 mm and box starts at x=15 mm.
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

# Synthetic uniform density, deliberately not represented as a sourced material.
# OCCT solid volume is mm^3; unit-density centroidal inertia is mm^5.
rho_kg_m3 = 2700.0
solid = actual.Solids[0]
mass_kg = float(solid.Volume) * rho_kg_m3 * 1e-9
raw_inertia = matrix_rows(solid.MatrixOfInertia)
inertia_kg_m2 = [[v * rho_kg_m3 * 1e-15 for v in row] for row in raw_inertia]
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
observations['analytical_inertia_about_centroid_kg_m2'] = expected_inertia
observations['inertia_error_kg_m2'] = [
    [inertia_kg_m2[i][j] - expected_inertia[i][j] for j in range(3)]
    for i in range(3)]

report = {
    'schema': 'pdr_cad_capability_probe/2',
    'authority': AUTHORITY,
    'scope': 'Synthetic headless FreeCAD capability only; not vehicle geometry or physical acceptance.',
    'freecad_version': list(App.Version()),
    'python_version': sys.version,
    'occt_version': str(getattr(Part, 'OCC_VERSION', 'not exposed')),
    'files': FILES,
    'comparison_tolerances': {'relative': 1e-7, 'absolute_in_compared_units': 1e-12},
    'checks': checks,
    'capability_checks_all_true': all(checks.values()),
    'observations': observations,
    'not_performed': [
        'GUI addon connectivity and screenshots',
        'Vehicle geometry, mounting interfaces and articulated clearance',
        'Commercial component compatibility and complete installed-mass accounting',
        'Material qualification, structural loads and physical tests',
    ],
}
App.closeDocument(reopened.Name)
(ROOT / FILES['report']).write_text(
    json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
print(json.dumps({'scope': report['scope'], 'checks': checks}, allow_nan=False))
if not report['capability_checks_all_true']:
    raise RuntimeError('Synthetic capability check failed; inspect retained report and exports.')
