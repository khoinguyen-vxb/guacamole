import FreeCAD as App, Part, json
doc = App.newDocument('SetupCheck')
obj = doc.addObject('Part::Box', 'CheckSolid')
obj.Length, obj.Width, obj.Height = 10, 20, 30
doc.recompute()
assert obj.Shape.isValid() and len(obj.Shape.Solids) == 1
assert abs(obj.Shape.Volume - 6000) < 1e-6
doc.saveAs('setup-test.FCStd')
Part.export([obj], 'setup-test.step')
App.closeDocument(doc.Name)
saved = App.openDocument('setup-test.FCStd')
assert abs(saved.CheckSolid.Shape.Volume - 6000) < 1e-6
shape = Part.Shape()
shape.read('setup-test.step')
assert shape.isValid() and len(shape.Solids) == 1
assert abs(shape.Volume - 6000) < 1e-6
with open('verification.json', 'w') as stream:
    json.dump({'outcome': 'pass', 'volume_mm3': shape.Volume,
               'solid_count': len(shape.Solids),
               'freecad_version': App.Version()}, stream)
