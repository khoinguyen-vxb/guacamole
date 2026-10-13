'''PDR-r12 candidate generator revision 03: diagnostic drawing recovery.

Run through freecad_run(headless=True), not the repository interpreter.
Original generators and configuration remain unchanged. This wrapper applies
revision-02's alias repair to the hash-pinned revision-01 source, exports native
CAD and STEP before drawing, and replaces only the arrangement renderer.
Geometry, physical/reference ownership, candidate set and measurements remain
unchanged. No collision is waived and no vehicle selection is made.

Observed failure: request ed7929bfa3d7422b8089971cb3759cec failed inside
arrangement_svg at edge.discretize(Number=20). The failed edge was not identified.
Do not label it a degenerate sphere edge without subsequent evidence.

Declared outputs for the NEXT freecad_run action, under
cad/pdr_r12_chief/braced_candidates_03/:
  for each {G_INTERMEDIATE_D279,G_WIDE_D330}_{TRIPOD,QUADPOD}_{S1,S4}:
    <id>.FCStd
    <id>_tubes.step
    <id>_arrangement.svg
    <id>_drawing_diagnostics_03.json
  cad_measurements_01.json
  output_manifest_01.json
Total: 34 outputs. Include this source, the original generator and configuration
Refs in execution inputs. Preserve any partial outputs; existing OUT is rejected.

Projection uses actual CAD edges. Failed discretization may fall back to actual
edge valueAt samples, with no claimed chord-error bound. Unresolved edges remain
recorded omissions and make the drawing visibly incomplete. These illustrations
are not silhouette, manufacturing, clearance or acceptance drawings.

API research accessed 2026-10-13:
[FreeCAD edge wrapper](https://raw.githubusercontent.com/FreeCAD/FreeCAD/main/src/Mod/Part/App/TopoShapeEdgePyImp.cpp)
The inspected upstream source provides Number-based discretization, Length,
ParameterRange and valueAt. It does not identify this project's failed edge.
Upstream main is not proof of compatibility with the installed snap revision.
No upstream implementation code is copied. Currency: not applicable; CAD units: mm.
'''

import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
THIS = ROOT / 'cad/pdr_r12_chief/build_braced_candidates_03.py'
BASE = ROOT / 'cad/pdr_r12_chief/build_braced_candidates_01.py'
BASE_SHA256 = 'dd275ef7747ca385671ad870169cb038921ead8357ec0d486612e55d40c054b7'
RUN_TAG = 'braced_candidates_03'
OUT = ROOT / 'cad/pdr_r12_chief' / RUN_TAG
DRAWINGS = {}
POINT_COUNT = 81
PLOT_SPAN_TOLERANCE_MM = 1e-9
API_RESEARCH = {
    'url': 'https://raw.githubusercontent.com/FreeCAD/FreeCAD/main/src/Mod/Part/App/TopoShapeEdgePyImp.cpp',
    'access_date': '2026-10-13',
    'sections': 'discretize; valueAt; getLength; getParameterRange',
    'currency': None,
    'units': 'CAD coordinates and lengths in mm; curve parameters use the edge parameterization',
    'finding': 'Upstream wrapper exposes these interfaces. Installed-version compatibility must be observed during execution.',
    'limitation': 'Mutable upstream main was inspected; no claim that it is the installed implementation or diagnoses the failed edge.',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    path = Path(path)
    return {'path': str(path.relative_to(ROOT)), 'sha256': digest(path.read_bytes())}


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def error_text(exc):
    return type(exc).__name__ + ': ' + str(exc)


def finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Nonfinite drawing coordinate or parameter')
    return value


def xyz(point):
    return [finite(point.x), finite(point.y), finite(point.z)]


def usable_points(points):
    coords = [xyz(p) for p in points]
    if len(coords) < 2:
        raise ValueError('Fewer than two drawing samples')
    span = max(max(p[i] for p in coords) - min(p[i] for p in coords) for i in range(3))
    if span <= PLOT_SPAN_TOLERANCE_MM:
        raise ValueError('Point-like sampled edge; degeneracy is not established by samples')
    return coords


def inspect_edge(edge, row):
    getters = {
        'length_mm': lambda: finite(edge.Length),
        'parameter_range': lambda: [finite(x) for x in edge.ParameterRange],
        'vertex_points_CAD_mm': lambda: [xyz(vertex.Point) for vertex in edge.Vertexes],
        'curve_type': lambda: type(edge.Curve).__name__,
    }
    row['inspection_errors'] = {}
    for key, getter in getters.items():
        try:
            row[key] = getter()
        except Exception as exc:
            row[key] = None
            row['inspection_errors'][key] = error_text(exc)


def sample_edge(edge, row):
    inspect_edge(edge, row)
    try:
        coords = usable_points(edge.discretize(Number=20))
        row.update(status='rendered_number_samples', sample_count=len(coords))
        return coords
    except Exception as exc:
        row['discretize_error'] = error_text(exc)
    try:
        bounds = row['parameter_range']
        if bounds is None or len(bounds) != 2 or bounds[0] == bounds[1]:
            raise ValueError('No usable finite nonzero parameter interval')
        first, last = bounds
        coords = usable_points([
            edge.valueAt(first + (last-first)*i/(POINT_COUNT-1))
            for i in range(POINT_COUNT)
        ])
        row.update(status='rendered_uniform_parameter_fallback', sample_count=len(coords))
        row['approximation'] = 'Actual-edge samples, not equal arc-length spacing; no chord-error guarantee.'
        return coords
    except Exception as exc:
        row['fallback_error'] = error_text(exc)
        row['status'] = 'unresolved_edge_omitted'
        row['sample_count'] = 0
        return None


def make_svg(path, candidate_id, lines, bounds, diag, geom):
    incomplete = not diag['all_enumerated_edges_represented']
    banner = 'INCOMPLETE EDGE PROJECTION - see diagnostics' if incomplete else 'SAMPLED EDGE PROJECTION - accuracy unverified'
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="850" viewBox="0 0 1200 850">',
        '<rect width="1200" height="850" fill="white"/>',
        '<g font-family="sans-serif" fill="#111">',
        '<text x="25" y="25" font-size="16">' + escape(candidate_id) + '</text>',
        '<text x="25" y="47" font-size="14" fill="#b00020">' + banner + '</text>',
        '<text x="25" y="67" font-size="12">Preliminary, mm. Dark: tubes; orange: non-mass references. Not a manufacturing drawing.</text>',
        '<text x="25" y="86" font-size="12">No hidden-line removal or silhouettes; use native solids for geometry evaluation.</text>',
    ]
    if not bounds or not lines:
        parts.append('<text x="25" y="140" font-size="18" fill="#b00020">No usable edge projection. Inspect native CAD and diagnostics.</text>')
    else:
        for axes, box, title in [((0,2),(25,125,550,615),'CAD X-Z projection'),
                                  ((0,1),(625,125,550,615),'CAD X-Y projection')]:
            i, j = axes
            xmin = min(b[i][0] for b in bounds)
            xmax = max(b[i][1] for b in bounds)
            ymin = min(b[j][0] for b in bounds)
            ymax = max(b[j][1] for b in bounds)
            x, y, w, h = box
            factor = min((w-20)/max(xmax-xmin,1.0), (h-50)/max(ymax-ymin,1.0))
            parts.append('<text x="%g" y="%g" font-size="13">%s</text>' % (x,y-12,title))
            for style, coords in lines:
                points = ' '.join('%.3f,%.3f' % (x+10+(p[i]-xmin)*factor,y+10+(ymax-p[j])*factor) for p in coords)
                color = '#172a3a' if style == 'physical' else '#bc6800'
                dash = '' if style == 'physical' else ' stroke-dasharray="4 3"'
                parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="0.8"%s/>' % (points,color,dash))
            parts.append('<path d="M %g %g h %g" stroke="black"/><text x="%g" y="%g" font-size="12">100 mm</text>' % (x+10,y+h-15,100*factor,x+10,y+h+2))
    parts.append('<text x="25" y="782" font-size="12">Omitted edges: %d; fallback edges: %d; object errors: %d. No geometry acceptance.</text>' % (diag['omitted_edge_count'],diag['fallback_edge_count'],len(diag['object_errors'])))
    parts.append('<text x="25" y="806" font-size="12">Nominal rotor diameter %.1f mm; foot radius %.1f mm; attachment Z %.1f mm. Unselected hypotheses.</text>' % (geom['rotor_diameter_mm'],geom['foot_socket_radius_mm'],geom['ring_attachment_z_mm']))
    parts.append('</g></svg>')
    Path(path).write_text('\n'.join(parts) + '\n', encoding='utf-8')


def diagnostic_drawing(ns, path, candidate_id, physical, references, geom):
    diag_path = OUT / (candidate_id + '_drawing_diagnostics_03.json')
    diag = {
        'schema': 'hopper_edge_projection_diagnostics/1',
        'candidate_id': candidate_id,
        'generated_at_UTC': datetime.now(timezone.utc).isoformat(),
        'units': 'mm',
        'geometry_modified_by_renderer': False,
        'accuracy_verified': False,
        'degeneracy_diagnosis': 'None. Failed or point-like edges are unresolved, not automatically classified as degenerate.',
        'fallback_point_count': POINT_COUNT,
        'plot_span_tolerance_mm': PLOT_SPAN_TOLERANCE_MM,
        'tolerance_scope': 'Rendering diagnostic only; not a geometry or clearance acceptance tolerance.',
        'edge_records': [], 'object_errors': [], 'object_records': [],
        'omitted_edge_count': 0, 'fallback_edge_count': 0,
        'all_enumerated_edges_represented': False,
        'api_research': API_RESEARCH,
    }
    lines, bounds = [], []
    try:
        for style, objects in [('physical',physical),('reference',references)]:
            for obj in objects:
                try:
                    shape = ns['world_shape'](obj)
                    bb = shape.BoundBox
                    bound = [[finite(getattr(bb,a+'Min')),finite(getattr(bb,a+'Max'))] for a in ('X','Y','Z')]
                    edges = list(shape.Edges)
                    bounds.append(bound)
                    diag['object_records'].append({'name':obj.Name,'label':str(obj.Label),'category':style,'edge_count':len(edges),'bounding_box_CAD_mm':bound})
                    for index, edge in enumerate(edges,1):
                        row = {'object_name':obj.Name,'object_label':str(obj.Label),'category':style,'edge_index_1_based':index}
                        coords = sample_edge(edge,row)
                        diag['edge_records'].append(row)
                        if coords is not None:
                            lines.append((style,coords))
                except Exception as exc:
                    diag['object_errors'].append({'object_name':obj.Name,'category':style,'error':error_text(exc)})
        diag['omitted_edge_count'] = sum(r['status']=='unresolved_edge_omitted' for r in diag['edge_records'])
        diag['fallback_edge_count'] = sum(r['status']=='rendered_uniform_parameter_fallback' for r in diag['edge_records'])
        diag['all_enumerated_edges_represented'] = bool(lines) and not diag['object_errors'] and diag['omitted_edge_count']==0
        make_svg(path,candidate_id,lines,bounds,diag,geom)
    except Exception as exc:
        # Presentation failure is retained, not converted into a geometry pass.
        # Filesystem failures writing the placeholder or diagnostics remain fatal.
        diag['renderer_error'] = error_text(exc)
        diag['all_enumerated_edges_represented'] = False
        Path(path).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="200"><rect width="1200" height="200" fill="white"/><text x="25" y="40" fill="red">INCOMPLETE: arrangement rendering failed; inspect drawing diagnostics and native CAD.</text><text x="25" y="80">' + escape(candidate_id) + '</text></svg>\n',encoding='utf-8')
    diag['svg'] = identity(path)
    diag['generator'] = identity(THIS)
    dump(diag_path,diag)
    DRAWINGS[candidate_id] = {
        'diagnostics': identity(diag_path),
        'all_enumerated_edges_represented': diag['all_enumerated_edges_represented'],
        'omitted_edge_count': diag['omitted_edge_count'],
        'fallback_edge_count': diag['fallback_edge_count'],
        'object_error_count': len(diag['object_errors']),
        'renderer_error': diag.get('renderer_error'),
        'accuracy_verified': False,
        'scope': 'Edge-projection diagnostic only; no solid, clearance, interface or structural acceptance.',
    }
    print(json.dumps({'candidate':candidate_id,'drawing':DRAWINGS[candidate_id]}),file=sys.stderr)


def main():
    raw = BASE.read_bytes()
    if digest(raw) != BASE_SHA256:
        raise ValueError('Original generator identity mismatch')
    if OUT.exists():
        raise FileExistsError('Preserve existing output directory: ' + str(OUT))
    patched = raw.decode('utf-8')
    changes = []
    for old,new in [('R8','TubeOuterRadiusEight'),('r8','TubeBoreRadiusEight'),
                    ('R14','TubeOuterRadiusFourteen'),('r14','TubeBoreRadiusFourteen')]:
        if patched.count(repr(old)) != 2:
            raise ValueError('Unexpected alias occurrence count: ' + old)
        patched = patched.replace(repr(old),repr(new))
        changes.append({'old':old,'new':new,'count':2})
    drawing_call = '    arrangement_svg(drawing, cid, physical, joints + feet + [ring] + list(rotors.values()) + yoke, geom)\n'
    export_block = '    doc.recompute()\n    doc.saveAs(str(native))\n    Part.export(physical, str(step))\n'
    old_block = drawing_call + export_block
    if patched.count(old_block) != 1:
        raise ValueError('Export-order patch must match exactly once')
    patched = patched.replace(old_block,export_block+drawing_call,1)
    ns = {'__name__':'hopper_braced_candidates_revision03','__file__':str(BASE)}
    exec(compile(patched,str(BASE)+' [revision03 alias and export-order substitutions]','exec'),ns)
    ns.update(SOURCE=THIS,RUN_TAG=RUN_TAG,OUT=OUT)
    ns['arrangement_svg'] = lambda path,cid,physical,refs,geom: diagnostic_drawing(ns,path,cid,physical,refs,geom)
    inherited_candidate = ns['candidate']

    def candidate_with_diagnostics(*args,**kwargs):
        result = inherited_candidate(*args,**kwargs)
        drawing = DRAWINGS[result['candidate_id']]
        result['drawing_projection_revision03'] = drawing
        result['files'].append(drawing['diagnostics'])
        return result

    ns['candidate'] = candidate_with_diagnostics
    provenance = {
        'revision':'03',
        'base_source':identity(BASE),
        'entry_point':identity(THIS),
        'executed_base_source_sha256':digest(patched.encode('utf-8')),
        'alias_changes':changes,
        'other_changes':['Save native and STEP before SVG rendering','Replace edge renderer with diagnostic renderer and explicit fallback/omission reporting','Add drawing diagnostics to candidate files and manifest'],
        'geometry_changes':[], 'configuration_changes':[],
        'failed_request_preserved':'ed7929bfa3d7422b8089971cb3759cec',
        'api_research':API_RESEARCH,
        'evidence_boundary':'Generation and diagnostic observations only; not verification, vehicle selection or review acceptance.',
    }
    inherited_dump = ns['dump']

    def audited_dump(path,value):
        path = Path(path)
        if path == OUT/'cad_measurements_01.json':
            value['prepared_date'] = datetime.now(timezone.utc).date().isoformat()
            value['generated_at_UTC'] = datetime.now(timezone.utc).isoformat()
            value['generator_revision_provenance'] = provenance
            for item in [identity(BASE),identity(THIS)]:
                if item not in value['inputs']:
                    value['inputs'].append(item)
            value['revision03_scope_notes'] = [
                'Original eight geometry hypotheses retained, including predicted yoke/brace conflicts.',
                'Drawing omissions and fallbacks are in each declared diagnostic file; do not infer complete drawings from process success.',
                'Tube sums omit physical ring, joints, fittings, equipment and moving hardware; they are not complete vehicle mass.',
                'Clearances remain sampled and nominal. No loaded or continuous clearance acceptance is established.',
                'A separate editable artifact-bound checker must evaluate actual outputs through verify_command.',
            ]
        elif path == OUT/'output_manifest_01.json':
            value['generator_revision_provenance'] = provenance
        inherited_dump(path,value)

    ns['dump'] = audited_dump
    ns['main']()


if __name__ == '__main__':
    main()
