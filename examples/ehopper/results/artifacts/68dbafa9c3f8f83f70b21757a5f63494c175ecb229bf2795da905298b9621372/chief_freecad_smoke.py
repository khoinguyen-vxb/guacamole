"""Headless capability probe only; not vehicle CAD or geometry acceptance.
FreeCAD dimensions are mm. Run through freecad_run with all exports declared.
"""
import os
from pathlib import Path
import json
import FreeCAD as App
import Part

out = Path(os.environ['GUACAMOLE_SANDBOX']) / 'cad'
out.mkdir(parents=True, exist_ok=True)
doc = App.newDocument('ChiefCapabilityProbe')
box = doc.addObject('Part::Box', 'ParametricProbe')
box.Label = 'Capability probe — NOT vehicle geometry'
box.Length = 20
box.Width = 30
box.Height = 40
doc.recompute()
doc.saveAs(str(out / 'chief_freecad_smoke.FCStd'))
Part.export([box], str(out / 'chief_freecad_smoke.step'))
report = {
    'purpose': 'FreeCAD capability probe only',
    'freecad_version': list(App.Version()),
    'length_unit': 'mm',
    'observed_solid_count': len(box.Shape.Solids),
    'observed_volume_mm3': box.Shape.Volume,
    'observed_shape_valid': box.Shape.isValid(),
    'vehicle_geometry_acceptance': 'not assessed',
    'physical_validation': 'unperformed'
}
(out / 'chief_freecad_smoke_observations.json').write_text(
    json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
App.closeDocument(doc.Name)
