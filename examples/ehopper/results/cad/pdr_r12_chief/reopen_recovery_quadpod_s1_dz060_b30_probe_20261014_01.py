"""Independent reopened-artifact inspection of one PDR-r12 recovery candidate.

Run subsequently through freecad_run(headless=True), declaring:
 cad/pdr_r12_chief/reopen_recovery_quadpod_s1_dz060_b30_observations_20261014_01.json

Include this source, the retained probe source and BOTH tested native/STEP
artifact Refs in execution inputs. Writing this source does not run FreeCAD.

This adapter reuses the inspected independent probe, NOT the CAD generator.
The retained probe remains unchanged. Four exact source substitutions change
only the expected member inventory, report identity and reporting metadata.
Runtime bindings select the published recovery binaries and fresh output.
The probe checks input hashes before opening them; it never saves the native
file or exports CAD. The radius perturbation is in memory only.

The 97 exploratory poses reproduce the configured sampling domain: neutral,
and 0.5/1.0 fractions of 10/15-degree resultant cones, every 15 degrees of
azimuth. These are finite samples, not selected travel or continuous bounds.
The retained algorithm inspects actual tube solids, native/STEP mass-property
observations, intersections, rotor/yoke primitive distances, articulated
kinematics and edit/recompute response. Joint-envelope and ground checks are
explicitly unperformed by this independent probe.

Output is an observation record, NOT VerificationResult. Publish it and use
a retained artifact-bound checker through verify_command subsequently.
No structural selection, complete vehicle properties, physical validation,
budget compliance or PDR/CDR acceptance follows from this inspection.
"""

import hashlib
import math
import os
from pathlib import Path

import FreeCAD as App
import Part

ROOT = Path(os.environ['GUACAMOLE_SANDBOX']).resolve()
THIS = ROOT / 'cad/pdr_r12_chief/reopen_recovery_quadpod_s1_dz060_b30_probe_20261014_01.py'
TEMPLATE = ROOT / 'cad/pdr_r12_chief/reopen_braced03_tripod_s1_probe_20261014_01.py'
TEMPLATE_SHA256 = '64a732bfa4bdb1725fdcefc3788e91d98ffcf1fc8c0783e45358367a55ca2ccc'
CANDIDATE = 'G_INTERMEDIATE_D279_QUADPOD_S1_DZ060_B30'
DIRECTORY = ROOT / 'cad/pdr_r12_chief/fixed_structure_recovery_20261014_01'
NATIVE = DIRECTORY / (CANDIDATE + '.FCStd')
STEP = DIRECTORY / (CANDIDATE + '_tubes.step')
OUTPUT = ROOT / 'cad/pdr_r12_chief/reopen_recovery_quadpod_s1_dz060_b30_observations_20261014_01.json'
EXPECTED_INPUT_HASHES = {
    NATIVE: '5e6943237c8d740bdd42f6528ddb2751f9e537622961d6cda23c51a2f1eb80db',
    STEP: '0dc0b0cd74199184c01676ca5461f9860c345eddaa909cfb117156c9d2f6d8bf',
}


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': digest(path)}


def configured_pose_samples():
    samples = {(0.0, 0.0)}
    for cone_deg in (10.0, 15.0):
        for fraction in (0.5, 1.0):
            theta = math.radians(cone_deg * fraction)
            for az_deg in range(0, 360, 15):
                az = math.radians(az_deg)
                alpha = math.asin(math.sin(theta) * math.cos(az))
                beta = math.atan2(math.sin(theta) * math.sin(az), math.cos(theta))
                samples.add((round(math.degrees(alpha), 10),
                             round(math.degrees(beta), 10)))
    ensure(len(samples) == 97, 'Unexpected finite pose inventory')
    return sorted(samples)


def main():
    ensure(not OUTPUT.exists(), 'Preserve existing observation output')
    raw = TEMPLATE.read_bytes()
    ensure(hashlib.sha256(raw).hexdigest() == TEMPLATE_SHA256,
           'Retained independent probe identity mismatch')
    for path, expected in EXPECTED_INPUT_HASHES.items():
        ensure(digest(path) == expected, 'Published CAD identity mismatch: ' + path.name)

    original = raw.decode('utf-8')
    substitutions = [
        (
            '        for i in range(1, 4):\n',
            '        for i in range(1, 5):\n',
            'Expect four main legs and eight braces instead of three main legs and six braces.'
        ),
        (
            "        if {o.Name for o in objects} != expected_names or len(objects) != 10:\n",
            "        if {o.Name for o in objects} != expected_names or len(objects) != 13:\n",
            'Expect thirteen tube components, including the single spine.'
        ),
        (
            "        'candidate_id': 'G_INTERMEDIATE_D279_TRIPOD_S1',\n",
            "        'candidate_id': 'G_INTERMEDIATE_D279_QUADPOD_S1_DZ060_B30',\n",
            'Report the actual inspected recovery candidate.'
        ),
        (
            "        'source': identity(SOURCE), 'inputs_before': before,\n",
            "        'source': identity(SOURCE), 'inspection_adapter': ADAPTER_PROVENANCE, 'inputs_before': before,\n",
            'Retain adapter and template provenance in the generated observation record.'
        ),
        (
            "            'scope': 'Native reference primitives versus actual native tubes at 25 poses. Primitive overlap volumes must not be summed as a unique compound volume.',\n",
            "            'scope': 'Native reference primitives versus actual native tubes at %d finite poses. Primitive overlap volumes must not be summed as a unique compound volume.' % len(samples),\n",
            'Report the actual finite sample count without changing distance mathematics.'
        ),
    ]
    # Five text substitutions; none edits geometry, thresholds or mass formulas.
    revised = original
    changes = []
    for old, new, reason in substitutions:
        ensure(revised.count(old) == 1,
               'Retained probe substitution did not match exactly once: ' + reason)
        revised = revised.replace(old, new, 1)
        changes.append({'old': old.strip(), 'new': new.strip(), 'reason': reason})

    namespace = {
        '__name__': 'recovery_quadpod_independent_probe_template',
        '__file__': str(TEMPLATE),
    }
    exec(compile(revised, str(TEMPLATE) + ' [recovery quadpod inspection adapter]',
                 'exec'), namespace)
    namespace.update({
        'SOURCE': THIS,
        'BASE': DIRECTORY,
        'NATIVE': NATIVE,
        'STEP': STEP,
        'OUTPUT': OUTPUT,
        'EXPECTED_HASHES': dict(EXPECTED_INPUT_HASHES),
        'pose_list': configured_pose_samples,
        'ADAPTER_PROVENANCE': {
            'work_plan': '66c7448f443f44ac9a016a1b384593a2 r1',
            'development_decision': '43d5a1d12e424f9ca9f24ed2e7f1981d r1',
            'retained_probe': identity(TEMPLATE),
            'adapter_source': identity(THIS),
            'executed_template_sha256': hashlib.sha256(revised.encode('utf-8')).hexdigest(),
            'text_substitutions': changes,
            'runtime_bindings': [
                'Published intermediate quadpod S1 DZ060_B30 native and STEP paths and hashes.',
                'Fresh observation output and actual adapter source identity.',
                'Configured 97 finite pose samples, replacing the earlier 25-pose sample.'
            ],
            'sampling': {
                'resultant_cones_deg': [10, 15],
                'cone_fractions': [0.5, 1.0],
                'azimuth_step_deg': 15,
                'neutral_included': True,
                'expected_pose_count': 97,
                'continuous_domain_certified': False
            },
            'unchanged_geometry_expectations': {
                'outer_origin_CAD_mm': [0, 0, 340],
                'outer_to_inner_local_mm': [0, 0, -20],
                'explanation': 'The recovery changes ring elevation and brace-root phasing, not the gimbal origins.'
            },
            'scope': 'Independent of the candidate generator; reuses the retained inspection algorithm. This is not a new independent implementation of all measurement mathematics.',
            'unperformed': [
                'Independent joint-envelope and ground-clearance inspection',
                'Continuous or loaded clearance',
                'Physical ring, supports, fittings and retention integration',
                'Complete installed vehicle mass, CG and inertia',
                'Structural, electrical, propulsion and flight validation',
                'Budget and review acceptance'
            ],
            'selection_status': 'Inspection target only; no vehicle configuration selected.'
        }
    })
    namespace['main']()
    ensure(digest(TEMPLATE) == TEMPLATE_SHA256,
           'Retained inspection source changed during execution')
    for path, expected in EXPECTED_INPUT_HASHES.items():
        ensure(digest(path) == expected,
               'Published CAD changed during read-only inspection: ' + path.name)


if __name__ == '__main__':
    main()
