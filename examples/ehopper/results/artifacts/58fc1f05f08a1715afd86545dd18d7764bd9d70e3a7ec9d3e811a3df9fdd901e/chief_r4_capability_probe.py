"""Run through freecad_run(headless=True), not ordinary Python.

Declare these sandbox-relative outputs when running:
  cad/chief_r4_capability/probe.FCStd
  cad/chief_r4_capability/probe.step
  cad/chief_r4_capability/measurements.json

Writes raw capability measurements, not a VerificationResult or vehicle acceptance.
Use a separate retained verifier and verify_command with actual artifact Refs.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sandbox = Path(os.environ['GUACAMOLE_SANDBOX']).resolve(strict=True)
if not sandbox.is_dir():
    raise RuntimeError('GUACAMOLE_SANDBOX must identify an existing directory')
out = (sandbox / 'cad' / 'chief_r4_capability').resolve()
out.relative_to(sandbox)
out.parent.mkdir(parents=True, exist_ok=True)
out.mkdir(exist_ok=False)  # Never overwrite a previous probe or partial run.
native_path = out / 'probe.FCStd'
step_path = out / 'probe.step'
report_path = out / 'measurements.json'

report = {
    'schema': 'chief_freecad_capability_measurements_v1',
    'scope': 'Synthetic backend probe only; no vehicle acceptance or physical validation.',
    'started_utc': datetime.now(timezone.utc).isoformat(),
    'execution_completed': False,
    'configured_dimensions_mm': [10.0, 20.0, 30.0],
    'edit_test_length_mm': 11.0,
    'units': {'dimensions': 'mm', 'volume': 'mm^3'},
    'observations': {},
    'artifacts': {}
}
opened = []
App = None
stage = 'import_freecad_and_part'


def parameters(obj):
    return {
        'type_id': obj.TypeId,
        'dimensions_mm': [float(obj.Length.Value), float(obj.Width.Value),
                          float(obj.Height.Value)]
    }


def geometry(shape):
    null = bool(shape.isNull())
    result = {
        'is_null': null,
        'is_valid': bool(shape.isValid()),
        'solid_count': len(shape.Solids),
        'volume_mm3': None,
        'bounding_box_mm': None
    }
    if not null:
        box = shape.BoundBox
        result['volume_mm3'] = float(shape.Volume)
        result['bounding_box_mm'] = {
            'minimum': [float(box.XMin), float(box.YMin), float(box.ZMin)],
            'maximum': [float(box.XMax), float(box.YMax), float(box.ZMax)],
            'lengths': [float(box.XLength), float(box.YLength), float(box.ZLength)]
        }
    return result


def close_document(doc):
    name = doc.Name
    App.closeDocument(name)
    opened.remove(name)


def file_record(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {
        'path': path.relative_to(sandbox).as_posix(),
        'size_bytes': path.stat().st_size,
        'sha256': digest.hexdigest()
    }


try:
    import FreeCAD as App
    import Part
    report['freecad_version'] = [str(value) for value in App.Version()]
    report['python_version'] = sys.version

    stage = 'create_parametric_box'
    doc = App.newDocument('ChiefR4CapabilityBox')
    opened.append(doc.Name)
    obj = doc.addObject('Part::Box', 'CalibrationBox')
    obj.Length, obj.Width, obj.Height = report['configured_dimensions_mm']
    doc.recompute()
    report['observations']['created'] = {
        'parameters': parameters(obj), 'geometry': geometry(obj.Shape)
    }

    stage = 'save_native_and_export_step'
    doc.saveAs(str(native_path))
    Part.export([obj], str(step_path))
    close_document(doc)

    stage = 'reopen_native'
    doc = App.openDocument(str(native_path))
    opened.append(doc.Name)
    obj = doc.getObject('CalibrationBox')
    if obj is None:
        raise RuntimeError('Saved native document lacks CalibrationBox')
    report['observations']['native_reopened'] = {
        'parameters': parameters(obj), 'geometry': geometry(obj.Shape)
    }

    stage = 'test_reopened_native_editability'
    original_length = float(obj.Length.Value)
    obj.Length = report['edit_test_length_mm']
    doc.recompute()
    report['observations']['native_edited'] = {
        'parameters': parameters(obj), 'geometry': geometry(obj.Shape)
    }
    obj.Length = original_length
    doc.recompute()
    report['observations']['native_restored'] = {
        'parameters': parameters(obj), 'geometry': geometry(obj.Shape)
    }
    close_document(doc)  # Do not resave or create backup files.

    stage = 'independently_read_step'
    imported = Part.Shape()
    imported.read(str(step_path))
    report['observations']['step_reopened'] = geometry(imported)

    stage = 'hash_saved_artifacts'
    report['artifacts']['native'] = file_record(native_path)
    report['artifacts']['step'] = file_record(step_path)
    report['execution_completed'] = True
    stage = 'completed'
except Exception as exc:
    report['failure'] = {'stage': stage, 'exception_type': type(exc).__name__}
    print('FreeCAD capability probe failed at ' + stage + ': ' + type(exc).__name__,
          file=sys.stderr)
    raise
finally:
    report['last_stage'] = stage
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report['cleanup_errors'] = []
    if App is not None:
        for name in reversed(opened):
            try:
                App.closeDocument(name)
            except Exception as exc:
                report['cleanup_errors'].append(type(exc).__name__)
                print('Document cleanup failed: ' + type(exc).__name__, file=sys.stderr)
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
