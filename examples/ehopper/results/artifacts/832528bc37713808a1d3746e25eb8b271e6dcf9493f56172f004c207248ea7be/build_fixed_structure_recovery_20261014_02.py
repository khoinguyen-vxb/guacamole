"""PDR-r12 bounded CAD recovery: revision 02 preflight correction.

Static finding, not a reproduced execution failure:
Revision 01 compares config.geometry_baselines with parent.geometry_hypotheses
as complete dictionaries. Each parent dictionary additionally has parent_seed,
so the supplied records cannot satisfy that comparison despite matching
geometric values.

This entry point hash-pins the unchanged revision-01 source and substitutes
only that comparison. Every geometric field is compared exactly, in the same
candidate order. The two parent_seed tags are separately checked and retained
in generated provenance; no other extra keys are ignored.

Run subsequently through freecad_run(headless=True). Writing this file does
not run CAD. Importing the retained template uses a non-main namespace.
No supplied repository, historical source, configuration or CAD is rewritten.

Keep the configuration's output directory:
  cad/pdr_r12_chief/fixed_structure_recovery_20261014_01/
The directory suffix identifies the configured experiment, not this generator
revision. The inherited preflight refuses an existing directory; do not bypass
that protection or silently rename/reuse partial outputs.

The subsequent execution action must explicitly enumerate all 99 outputs:
  {G_INTERMEDIATE_D279,G_WIDE_D330}_{TRIPOD,QUADPOD}_{S1,S4}_
  {DZ000_B30,DZ060_B45,DZ060_B30}, each with .FCStd, _tubes.step,
  _arrangement.svg and _drawing_diagnostics_03.json;
  plus cad_measurements_01.json, generation_provenance_01.json and
  output_manifest_01.json. Include this source, the retained template,
  inherited generator/renderer and both configuration Refs in tool inputs.

The original 24-new/eight-retained bound and physical ring/support/joint
integration gate remain unchanged. This is not a verification program,
structural selection, complete vehicle model or review acceptance.
"""

import copy
import hashlib
import os
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
THIS = ROOT / 'cad/pdr_r12_chief/build_fixed_structure_recovery_20261014_02.py'
TEMPLATE = ROOT / 'cad/pdr_r12_chief/build_fixed_structure_recovery_20261014_01.py'
TEMPLATE_SHA256 = '8214c9bb23a2d0dde8c38e459a4b37d68301021aad877855dc79ce949b401871'

GEOMETRY_FIELDS = frozenset({
    'id',
    'ring_attachment_radius_mm',
    'ring_attachment_z_mm',
    'foot_socket_radius_mm',
    'foot_socket_z_mm',
    'foot_contact_z_mm',
    'outer_joint_origin_CAD_mm',
    'neutral_outer_to_inner_origin_CAD_mm',
    'upper_rotor_neutral_hub_CAD_mm',
    'lower_rotor_neutral_hub_CAD_mm',
    'rotor_diameter_mm',
})
EXPECTED_ORDER = ['G_INTERMEDIATE_D279', 'G_WIDE_D330']
EXPECTED_PARENT_SEEDS = {
    'G_INTERMEDIATE_D279': 'G_INTERMEDIATE',
    'G_WIDE_D330': 'G_WIDE',
}
GEOMETRY_COMPARISON = {}


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def validate_geometry_baselines(config, parent):
    """Validate geometry without mistaking provenance metadata for geometry."""
    GEOMETRY_COMPARISON.clear()
    current = config['geometry_baselines']
    inherited = parent['geometry_hypotheses']
    ensure(isinstance(current, list) and isinstance(inherited, list),
           'Geometry baseline collections must be lists')
    ensure(len(current) == len(inherited) == 2,
           'Unexpected geometry baseline count')
    ensure(all(isinstance(g, dict) for g in current + inherited),
           'Geometry baseline entries must be dictionaries')
    ensure([g.get('id') for g in current] == EXPECTED_ORDER,
           'Recovery baseline IDs or order differ')
    ensure([g.get('id') for g in inherited] == EXPECTED_ORDER,
           'Parent baseline IDs or order differ')
    metadata = []
    for child_geometry, parent_geometry in zip(current, inherited):
        cid = child_geometry['id']
        ensure(set(child_geometry) == GEOMETRY_FIELDS,
               'Unexpected recovery geometry fields: ' + cid)
        ensure(set(parent_geometry) == GEOMETRY_FIELDS | {'parent_seed'},
               'Unexpected parent geometry fields: ' + cid)
        ensure(parent_geometry['parent_seed'] == EXPECTED_PARENT_SEEDS[cid],
               'Unexpected parent_seed metadata: ' + cid)
        projected_parent = {key: parent_geometry[key]
                            for key in GEOMETRY_FIELDS}
        ensure(child_geometry == projected_parent,
               'Geometry values differ: ' + cid)
        metadata.append({'geometry_id': cid,
                         'parent_seed': parent_geometry['parent_seed']})
    GEOMETRY_COMPARISON.update({
        'method': 'Exact dictionary equality after removing only separately validated parent_seed metadata from the comparison view; input dictionaries are not modified.',
        'geometry_fields': sorted(GEOMETRY_FIELDS),
        'geometry_order': list(EXPECTED_ORDER),
        'parent_seed_metadata': metadata,
        'all_geometry_fields_equal': True,
        'scope': 'Configuration consistency, not CAD or physical acceptance.',
    })


def main():
    raw = TEMPLATE.read_bytes()
    ensure(hashlib.sha256(raw).hexdigest() == TEMPLATE_SHA256,
           'Retained revision-01 template identity mismatch')
    original = raw.decode('utf-8')
    old = "    require(config['geometry_baselines'] == parent['geometry_hypotheses'], 'Geometry baselines differ')\n"
    new = "    validate_geometry_baselines(config, parent)\n"
    ensure(original.count(old) == 1,
           'Preflight comparison substitution must match exactly once')
    revised = original.replace(old, new, 1)
    executed_template_sha256 = hashlib.sha256(
        revised.encode('utf-8')).hexdigest()

    namespace = {
        '__name__': 'hopper_bounded_recovery_revision02_template',
        '__file__': str(TEMPLATE),
        'validate_geometry_baselines': validate_geometry_baselines,
    }
    exec(compile(revised, str(TEMPLATE) + ' [revision02 metadata comparison correction]',
                 'exec'), namespace)

    # All retained functions resolve their entry-point identity to this source.
    # Also bind the unchanged template into inherited before/after input hashes.
    namespace['THIS'] = THIS
    namespace['EXPECTED_HASHES'][TEMPLATE] = TEMPLATE_SHA256
    inherited_loader = namespace['load_inspected_functions']

    def load_with_correction_provenance(out):
        ensure(GEOMETRY_COMPARISON.get('all_geometry_fields_equal') is True,
               'Geometry comparison was not completed before generator loading')
        functions, renderer, provenance = inherited_loader(out)
        provenance['recovery_generator_revision02_correction'] = {
            'retained_template': namespace['identity'](TEMPLATE),
            'entry_point': namespace['identity'](THIS),
            'executed_recovery_template_sha256': executed_template_sha256,
            'template_text_substitution_count': 1,
            'old_comparison': old.strip(),
            'replacement_call': new.strip(),
            'geometry_comparison': copy.deepcopy(GEOMETRY_COMPARISON),
            'runtime_bindings': [
                'THIS points to revision 02 for source identity.',
                'Unchanged revision-01 template is included in before/after input hashing.',
                'Generator provenance includes this correction and preserved parent_seed tags.',
            ],
            'geometry_changes': [],
            'configuration_file_changes': [],
            'output_directory_change': False,
            'candidate_matrix_change': False,
            'prior_failure_status': 'Identified by static comparison; no revision-01 execution failure is asserted.',
            'scope': 'Preflight implementation correction only. All physical integration gates and evidence limitations remain unchanged.',
        }
        return functions, renderer, provenance

    namespace['load_inspected_functions'] = load_with_correction_provenance
    namespace['main']()


if __name__ == '__main__':
    main()
