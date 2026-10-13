'''PDR-r12 candidate CAD generator entry point, revision 02.

Execute through freecad_run, headless=True. Preserve revision 01 unchanged.
This editable wrapper hash-pins that generator and changes only spreadsheet
aliases, output-directory identity and provenance reporting. The original
configuration and eight geometric hypotheses remain unchanged. In particular,
predicted yoke/brace conflicts are NOT silently removed or accepted.

This is generation/measurement, not a VerificationResult or vehicle selection.
The inherited model contains nominal tubes and non-mass reference envelopes;
it does not contain a complete physical ring, fittings, gimbal or equipment.
Distances are sampled, and tube mass is not complete vehicle mass.

Declare these outputs in the subsequent freecad_run action:
For each Cartesian-product candidate ID
  {G_INTERMEDIATE_D279,G_WIDE_D330}_{TRIPOD,QUADPOD}_{S1,S4}
under cad/pdr_r12_chief/braced_candidates_02/:
  <candidate>.FCStd
  <candidate>_tubes.step
  <candidate>_arrangement.svg
and:
  cad_measurements_01.json
  output_manifest_01.json
The report suffixes are inherited; the fresh directory prevents overwriting.
Include this wrapper, its original generator and configuration in tool inputs.
'''

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
THIS = ROOT / 'cad/pdr_r12_chief/build_braced_candidates_02.py'
BASE = ROOT / 'cad/pdr_r12_chief/build_braced_candidates_01.py'
BASE_SHA256 = 'dd275ef7747ca385671ad870169cb038921ead8357ec0d486612e55d40c054b7'
RUN_TAG = 'braced_candidates_02'
OUT = ROOT / 'cad/pdr_r12_chief' / RUN_TAG

# Letter-only aliases avoid cell-address ambiguity, including case variants.
# Each old literal occurs once in parameters() and once in tube().
ALIAS_CHANGES = (
    ('R8', 'TubeOuterRadiusEight', 2),
    ('r8', 'TubeBoreRadiusEight', 2),
    ('R14', 'TubeOuterRadiusFourteen', 2),
    ('r14', 'TubeBoreRadiusFourteen', 2),
)


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def file_identity(path):
    return {
        'path': str(path.relative_to(ROOT)),
        'sha256': digest_bytes(path.read_bytes()),
    }


def main():
    raw = BASE.read_bytes()
    observed_hash = digest_bytes(raw)
    if observed_hash != BASE_SHA256:
        raise ValueError('Revision-01 generator differs from the inspected source')
    if OUT.exists():
        raise FileExistsError('Preserve existing/partial outputs; choose a fresh run tag: ' + str(OUT))

    patched = raw.decode('utf-8')
    patch_log = []
    for old, new, expected_count in ALIAS_CHANGES:
        old_literal, new_literal = repr(old), repr(new)
        actual_count = patched.count(old_literal)
        if actual_count != expected_count:
            raise ValueError('Unexpected alias occurrence count for ' + old)
        patched = patched.replace(old_literal, new_literal)
        patch_log.append({
            'old_alias': old,
            'new_alias': new,
            'literal_replacement_count': actual_count,
        })

    # Execute definitions only. The original __main__ guard does not run.
    # All inherited functions share this dictionary, so the explicit overrides
    # below govern their global path/provenance references consistently.
    namespace = {
        '__name__': 'hopper_braced_candidates_r12_revision02',
        '__file__': str(BASE),
    }
    exec(compile(patched, str(BASE) + ' [revision02 alias substitutions]', 'exec'), namespace)
    namespace['SOURCE'] = THIS
    namespace['RUN_TAG'] = RUN_TAG
    namespace['OUT'] = OUT

    source_chain = [file_identity(BASE), file_identity(THIS)]
    provenance = {
        'revision': '02',
        'base_source': source_chain[0],
        'entry_point': source_chain[1],
        'in_memory_executed_base_source_sha256': digest_bytes(patched.encode('utf-8')),
        'alias_changes': patch_log,
        'output_directory': str(OUT.relative_to(ROOT)),
        'geometry_changes': [],
        'configuration_changes': [],
        'execution_method': 'Hash-checked original source; exact alias-literal substitutions in memory; explicit namespace overrides; inherited main invoked once.',
        'preservation': 'Original generator and configuration are read only. Existing output directory is rejected.',
        'evidence_boundary': 'Source preparation and CAD execution do not establish geometry, structural, complete-mass, budget or flight acceptance.',
    }

    inherited_dump = namespace['dump']

    def audited_dump(path, value):
        path = Path(path)
        if path == OUT / 'cad_measurements_01.json':
            value['prepared_date'] = datetime.now(timezone.utc).date().isoformat()
            value['generated_at_UTC'] = datetime.now(timezone.utc).isoformat()
            value['generator_revision_provenance'] = provenance
            identities = value.setdefault('inputs', [])
            for identity in source_chain:
                if identity not in identities:
                    identities.append(identity)
            value['revision02_scope_notes'] = [
                'Eight original B45_F080 tube candidates retained; no topology or dimension selected.',
                'Predicted yoke/brace interference remains a hypothesis until the stored CAD measurements are reviewed.',
                'The attachment-ring guide is not a physical ring and does not establish ring clearance or a load path.',
                'Joint spheres and yoke capsules are assumed packaging envelopes, not qualified hardware.',
                'Nominal tube intersections remain reported; they are not accepted joints or an assembled-mass correction.',
                'Use a separate editable artifact-bound checker through verify_command after reviewing execution results.',
            ]
        elif path == OUT / 'output_manifest_01.json':
            value['generator_revision_provenance'] = provenance
        inherited_dump(path, value)

    namespace['dump'] = audited_dump
    namespace['main']()


if __name__ == '__main__':
    main()
