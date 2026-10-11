"""Recover existing fixture exports without overwriting any prior artifact.
Run through freecad_run(headless=True), declaring these generated outputs:
  cad/pdr_r9_chief/r9_recovered_fixture_01.FCStd
  cad/pdr_r9_chief/r9_recovered_fixture_01.step
  cad/pdr_r9_chief/r9_recovered_fixture_01_measurements.json

This program records measurements, NOT a VerificationResult.
A separate editable analytical verifier must check the published artifacts.
Authorization: decision 98d7c43a499d4584a77132cd5ac96874 r1.
Original export hashes: reader result ebf8b645175c401899d4d54a961d9076 r1.
"""
import hashlib
import json
import math
import os
import shutil
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
OUT = ROOT / 'cad/pdr_r9_chief'
SCRIPT = OUT / 'r9_fixture_recovery_01.py'
NATIVE = OUT / 'r9_recovered_fixture_01.FCStd'
STEP = OUT / 'r9_recovered_fixture_01.step'
REPORT = OUT / 'r9_recovered_fixture_01_measurements.json'
SOURCES = {
    'native': ROOT / 'cad/pdr_r8_cad/r8_solid_fixture_01.FCStd',
    'step': ROOT / 'cad/pdr_r8_cad/r8_solid_fixture_01.step',
}
EXPECTED_SOURCE_HASHES = {
    'native': 'ca4d55acb1b40ae8fc33cba740ee34374d3a4d300b9ff7f4b0c064868b5a90d9',
    'step': '0a3dc72fb44cd901427a4ad9186287991bd592d7aaf19d4104d0775486635bf4',
}
RHO = 2700.0  # Assumed numerical units-fixture value, not a vehicle material.


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def relative(path):
    return str(path.relative_to(ROOT))


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite measurement')
    return result


def measure(shape):
    if shape.isNull():
        raise ValueError('Null fixture shape')
    solids = list(shape.Solids)
    if len(solids) != 1:
        raise ValueError('Expected exactly one fixture solid, found %d' % len(solids))
    solid = solids[0]
    bb = solid.BoundBox
    cg = solid.CenterOfMass
    tensor = solid.MatrixOfInertia
    inertia = [[number(getattr(tensor, 'A%d%d' % (i, j)))
                for j in range(1, 4)] for i in range(1, 4)]
    volume = number(solid.Volume)
    return {
        'input_shape_type': str(shape.ShapeType),
        'input_shape_valid': bool(shape.isValid()),
        'solid_count': len(solids),
        'measured_shape_type': str(solid.ShapeType),
        'solid_valid': bool(solid.isValid()),
        'volume_mm3': volume,
        'bbox_min_mm': [number(bb.XMin), number(bb.YMin), number(bb.ZMin)],
        'bbox_max_mm': [number(bb.XMax), number(bb.YMax), number(bb.ZMax)],
        'bbox_size_mm': [number(bb.XLength), number(bb.YLength), number(bb.ZLength)],
        'cg_mm': [number(cg.x), number(cg.y), number(cg.z)],
        'geometric_inertia_about_solid_cg_mm5': inertia,
        'assumed_density_kg_m3': RHO,
        'mass_kg': volume * RHO * 1e-9,
        'inertia_about_solid_cg_kg_m2': [[v * RHO * 1e-15 for v in row]
                                        for row in inertia],
    }


OUT.mkdir(parents=True, exist_ok=True)
for path in (NATIVE, STEP, REPORT):
    if path.exists() or path.is_symlink():
        raise FileExistsError('Preserve existing output; use a fresh stem: ' + str(path))
for path in (SCRIPT, *SOURCES.values()):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular non-symlink input: ' + str(path))
    path.resolve().relative_to(ROOT)

script_hash = digest(SCRIPT)
source_hashes_before = {key: digest(path) for key, path in SOURCES.items()}
if source_hashes_before != EXPECTED_SOURCE_HASHES:
    raise RuntimeError('Existing exports differ from reviewed provenance; inspect before recovery')

# Exclusive, byte-preserving copies. Never write or save to the original r8 files.
for source, destination in ((SOURCES['native'], NATIVE), (SOURCES['step'], STEP)):
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst, length=1048576)

copy_hashes_before = {'native': digest(NATIVE), 'step': digest(STEP)}
if copy_hashes_before != source_hashes_before:
    raise RuntimeError('Recovered copy differs from its source')

# Inspect actual recovered exports. No prior JSON pass flags are reused.
doc = App.openDocument(str(NATIVE))
try:
    doc.recompute()
    obj = doc.getObject('UnitsFixtureBox')
    if obj is None:
        raise RuntimeError('UnitsFixtureBox missing from recovered native document')
    geometry_objects = [item for item in doc.Objects
                        if hasattr(item, 'Shape') and not item.Shape.isNull()]
    native = measure(obj.Shape)
    native['geometry_object_count'] = len(geometry_objects)
    native['object_type'] = str(obj.TypeId)
    native['object_name'] = str(obj.Name)
    native['editable_dimensions_mm'] = {
        name: number(getattr(obj, name).Value) for name in ('Length', 'Width', 'Height')
    }
    native['placement_base_mm'] = [number(v) for v in
                                   (obj.Placement.Base.x, obj.Placement.Base.y,
                                    obj.Placement.Base.z)]
    native['placement_quaternion_xyzw'] = [number(v) for v in obj.Placement.Rotation.Q]
    probes = []
    for name in ('Length', 'Width', 'Height'):
        original = number(getattr(obj, name).Value)
        try:
            setattr(obj, name, original + 1.0)
            doc.recompute()
            probes.append({
                'parameter': name,
                'original_mm': original,
                'requested_mm': original + 1.0,
                'readback_mm': number(getattr(obj, name).Value),
                'geometry': measure(obj.Shape),
            })
        finally:
            setattr(obj, name, original)
            doc.recompute()
    native['in_memory_edit_probes_not_saved'] = probes
    native['restored_geometry'] = measure(obj.Shape)
finally:
    # All parameter changes are in-memory only. Do not save the reopened file.
    App.closeDocument(doc.Name)

step = measure(Part.read(str(STEP)))
source_hashes_after = {key: digest(path) for key, path in SOURCES.items()}
copy_hashes_after = {'native': digest(NATIVE), 'step': digest(STEP)}
if source_hashes_after != source_hashes_before:
    raise RuntimeError('An original export changed during recovery')
if copy_hashes_after != copy_hashes_before:
    raise RuntimeError('A recovered export changed during readback')
if digest(SCRIPT) != script_hash:
    raise RuntimeError('Recovery program changed during execution')

report = {
    'schema': 'r9_recovered_fixture_measurements_v1',
    'status': 'measurements_only_independent_verification_pending',
    'vehicle_baseline': False,
    'physical_acceptance': 'not_assessed',
    'freecad_version': list(App.Version()),
    'recovery_program': {'path': relative(SCRIPT), 'sha256': script_hash},
    'source_paths': {key: relative(path) for key, path in SOURCES.items()},
    'source_sha256_before': source_hashes_before,
    'source_sha256_after': source_hashes_after,
    'recovered_paths': {'native': relative(NATIVE), 'step': relative(STEP)},
    'recovered_sha256_before_readback': copy_hashes_before,
    'recovered_sha256_after_readback': copy_hashes_after,
    'fixture_contract': {
        'dimensions_mm': [10.0, 20.0, 30.0],
        'translation_mm': [11.0, 17.0, 23.0],
        'rotation_quaternion_xyzw': [0.0, 0.0, 0.0, 1.0],
        'assumed_density_kg_m3': RHO,
        'density_scope': 'numerical units fixture only',
    },
    'units': {
        'geometry_length': 'mm', 'geometry_volume': 'mm^3',
        'geometric_inertia': 'mm^5', 'density': 'kg/m^3',
        'mass': 'kg', 'density_weighted_inertia': 'kg m^2',
        'volume_to_m3': 1e-9, 'geometric_inertia_to_m5': 1e-15,
        'inertia_reference': 'individual solid center of mass, CAD axes',
    },
    'native_reopened': native,
    'step_reimported': step,
    'limitations': [
        'Original export-producing request is unavailable in current records; these are recovered sandbox artifacts.',
        'This execution creates byte-identical recovery copies and new actual readback measurements.',
        'An independent artifact-bound analytical VerificationResult remains required.',
        'No GUI-addon availability, vehicle layout, mount fit, rotor clearance, structural strength or flight acceptance is established.',
        'Parameter probes were restored in memory and were not saved.',
    ],
}
with REPORT.open('x', encoding='utf-8') as stream:
    stream.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
print(json.dumps({'status': report['status'], 'report': relative(REPORT)}, allow_nan=False))
