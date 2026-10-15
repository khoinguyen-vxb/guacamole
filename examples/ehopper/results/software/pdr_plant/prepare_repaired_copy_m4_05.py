"""Prepare an audited, separate fixed-D analytical plant copy.

Authority: system_model:system@4; work-plan
99f7bb629eef45b89fa38d27c803868c@1; interface
88561ff8b3ba4e8286cebd95a93e3b08@1.
Pre-edit audit: PDR-PLANT-PRE-EDIT-AUDIT-M4-03@1.
Capability: PDR-PLANT-CAPABILITY-REPORT-M4-04@1.

Run with python -B from the results sandbox. Declare every OUTPUT_PATHS
entry in the execute action. No source import, installation, original edit,
vehicle-scope extension or numerical verification is performed by this script.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parents[1]
RECOVERED = SANDBOX / 'previous_run/repaired_hopper_r12'
PACKAGE_REL = 'software/pdr_plant/repaired_hopper_m4'
MANIFEST_REL = 'software/pdr_plant/migration_manifest_m4_05.json'
PATCH_REL = 'software/pdr_plant/recovered_to_m4_05.patch'
README_REL = 'software/pdr_plant/README_repaired_m4_05.md'

AUTHORITY = {
    'system_model': {'kind':'system_model','id':'system','revision':4,
        'sha256':'e89e68e192965d8e012cc1213e59c02610f55042ad26d7392ebef0401237ee75'},
    'work_plan': {'kind':'decision','id':'99f7bb629eef45b89fa38d27c803868c','revision':1,
        'sha256':'e5af8e2f56f7c851b65518b129f39550be73911f56461279cbbb1e85e1cdd5f0'},
    'interface': {'kind':'decision','id':'88561ff8b3ba4e8286cebd95a93e3b08','revision':1,
        'sha256':'ad6662afab9685585264c86e052c246996d23f4369c6432b56094a42a9187c04'},
}
AUDIT_REF = {'kind':'artifact','id':'PDR-PLANT-PRE-EDIT-AUDIT-M4-03','revision':1,
             'sha256':'e6ee2af73b7e5af2f2f475166a4ae66be2c7f92b3cdae37360107798fedfeb18'}
CAPABILITY_REF = {'kind':'artifact','id':'PDR-PLANT-CAPABILITY-REPORT-M4-04','revision':1,
                  'sha256':'e4ea0097e9ae4c8830261874f173a5abe2cd82cbb351ea810d715cd0e1ea4618'}
# These are observed FILE hashes, not manufactured runtime Ref hashes.
SOURCE_PINS = {
    'helpers/math.py':'281a5578b6d33c45578350429cb30ead28ba6a378c571c2c6929c60819ceecfb',
    'simulation/state.py':'b62a1a4fcc70a4a88e07f77996e955a64184891ce614957c85ccb7d63e90f294',
    'chassis/hopper.py':'f2b6e4b54634220105655e994e3ff5c78e84c60084879696a25ef39fdc29ff05',
    'propulsion/propulsion.py':'d860528b277893bbfe59527b7fcc2017955cc66681d3994fb66744a8006271de',
    'propulsion/propeller.py':'ce7be67ceae3866ecf402ee03b7812c3ea1e39c216ca5d412322af53d586ae3b',
    'propulsion/actuators.py':'bacfd1457ea3d24ae82d4868f3418b46c967fc2442d83d36e96973467645be78',
    'simulation/environment.py':'ba795b5d1d5344a1ecf5b2b5cc122255234d5ff394fb0dc41ee3366196aac03c',
    'simulation/simulation.py':'a186c50ab7c5500e7da14bb5c98a5c2772ff97d63645558be3cfdc3b6e5ca1a8',
}
INIT_PATHS = ('__init__.py', 'helpers/__init__.py', 'simulation/__init__.py',
              'chassis/__init__.py', 'propulsion/__init__.py')
OUTPUT_PATHS = tuple(PACKAGE_REL + '/' + p for p in SOURCE_PINS) + tuple(
    PACKAGE_REL + '/' + p for p in INIT_PATHS
) + (MANIFEST_REL, PATCH_REL, README_REL)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def replace_once(text, old, new, description):
    count = text.count(old)
    if count != 1:
        raise ValueError(f'{description}: expected one exact match, found {count}')
    return text.replace(old, new, 1)


def checked_source(relative, expected):
    path = RECOVERED / relative
    if (path.is_symlink() or not path.is_file()
            or not path.resolve().is_relative_to(RECOVERED.resolve())):
        raise ValueError('Invalid recovered source path: ' + str(path))
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError('Recovered file differs from inspected pin: ' + relative)
    return raw.decode('utf-8').replace('\r\n', '\n')


def current_header(relative, original_hash):
    return f'''"""PDR M4 fixed-D analytical plant: {relative}.

Current authority: system_model:system revision 4;
work-plan 99f7bb629eef45b89fa38d27c803868c revision 1;
interface 88561ff8b3ba4e8286cebd95a93e3b08 revision 1.
Pre-edit audit: PDR-PLANT-PRE-EDIT-AUDIT-M4-03 revision 1.

Reused from inspected previous_run/repaired_hopper_r12/{relative}.
Recovered file SHA256: {original_hash}
Original checkout and recovered files remain unchanged. The recovered module
header is retained as historical provenance in migration_manifest_m4_05.json.

Migration: explicit fixed plate/ring datum D replaces the recovered neutral-CG
reference semantics; coordinated datum-related identifiers and schema strings
are versioned across all eight modules. L is NED, B is FRD, q_LB is scalar-first
Hamilton, and R_LB maps B components into L. Translation remains at instantaneous
complete-vehicle CG G. D is fixed to the airframe and never follows G.

D is the neutral propulsion centreline intersection with the upper reference
plane of the FIXED leg-attachment plate/ring. Its numerical CAD location is an
explicit input, not a selected coordinate. CAD C is forward-left-up in mm;
r_B[m] = 0.001*diag(1,-1,-1)*(p_C[mm]-D_C[mm]).

This migration does not add vehicle dynamics, a calibrated propulsion map,
realizable ESC commands, loaded servo capability, battery/thermal evolution or
contact. Analytical-only runtime guards are retained. No fixture is vehicle
data merely because it executes. New fixtures/checkers must use these schemas.
Generation, syntax compilation and imports are not analytical verification,
physical validation, requirement satisfaction or review acceptance.
"""
'''


def transform(relative, source):
    tree = ast.parse(source, filename=relative)
    if not tree.body or not isinstance(tree.body[0], ast.Expr):
        raise ValueError('Expected reviewed leading module docstring: ' + relative)
    first = tree.body[0]
    if not isinstance(first.value, ast.Constant) or not isinstance(first.value.value, str):
        raise ValueError('Expected module documentation string: ' + relative)
    if first.lineno != 1:
        raise ValueError('Unexpected preamble; inspect before migration: ' + relative)
    historical_header = first.value.value
    body = ''.join(source.splitlines(keepends=True)[first.end_lineno:])

    # Correct semantic definitions BEFORE mechanical identifier migration.
    if relative == 'helpers/math.py':
        body = replace_once(body,
            '    O_B0 coincides with the complete-vehicle neutral CG once derived from\n'
            '    the actual assembly. That numerical CAD origin is required explicitly;\n'
            '    it is never assumed zero or moved with the instantaneous CG.\n',
            '    D is fixed at the neutral propulsion centreline intersection with the\n'
            '    upper plane of the FIXED leg-attachment plate/ring. Supply its CAD\n'
            '    coordinates explicitly; never substitute a neutral or moving CG.\n',
            'CAD datum definition')
    if relative == 'chassis/hopper.py':
        body = replace_once(body,
            '    locates G relative to fixed O_B0, the neutral complete-vehicle CG datum.\n',
            '    locates G relative to fixed D at the leg-attachment reference plane.\n',
            'Mass-property datum definition')

    counts = {}
    for old, new in (
        ('pdr_r12_', 'hopper_m4_fixed_D_'),
        ('neutral_cg_C_mm', 'datum_D_C_mm'),
        ('O_B0', 'D'),
        ('B0', 'D'),
    ):
        counts[old + ' -> ' + new] = body.count(old)
        body = body.replace(old, new)
    body = re.sub(r'\br12\b', 'M4', body)

    if relative == 'helpers/math.py':
        body = replace_once(body,
            'def cad_point_to_body_datum_m(point_C_mm, datum_D_C_mm):',
            'def cad_point_to_body_datum_m(point_C_mm, *, datum_D_C_mm):',
            'Explicit keyword-only forward CAD datum')
        body = replace_once(body,
            'def body_datum_point_to_cad_mm(point_D_m, datum_D_C_mm):',
            'def body_datum_point_to_cad_mm(point_D_m, *, datum_D_C_mm):',
            'Explicit keyword-only inverse CAD datum')

    output = current_header(relative, SOURCE_PINS[relative]) + body
    if not output.endswith('\n'):
        output += '\n'
    for obsolete in ('pdr_r12_', 'neutral_cg_C_mm', 'O_B0', 'B0'):
        if obsolete in output:
            raise ValueError('Obsolete datum/schema token remains: ' + obsolete)
    parsed = ast.parse(output, filename=PACKAGE_REL + '/' + relative)
    compile(parsed, PACKAGE_REL + '/' + relative, 'exec')
    schemas = {}
    for node in parsed.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith('_SCHEMA'):
                    schemas[target.id] = node.value.value
    return output, historical_header, counts, schemas


README = '''# PDR M4 fixed-D analytical plant copy

## Authority and status

System model revision 4, work-plan decision 99f7bb629eef45b89fa38d27c803868c r1,
and interface decision 88561ff8b3ba4e8286cebd95a93e3b08 r1 govern this copy.
PDR-PLANT-PRE-EDIT-AUDIT-M4-03 r1 records the pre-edit findings and affected callers.
PDR-PLANT-CAPABILITY-REPORT-M4-04 r1 separately records dependency imports,
standalone SciPy execution, original failure reproductions and recovered imports.

This is a migrated source package, not a verified release. The generation
manifest and patch show exactly what changed. Syntax compilation during
preparation does not import this copy or execute its dynamics. Analytical
regressions and a runnable synthetic scenario entry point are still required.
Historical checker files/results were not recovered with the eight modules.

## Preserved and changed behavior

Retained mechanisms: immutable initialization, owned serialization, explicit
local-CG velocity, Hamilton quaternion evolution, package-relative imports,
separated-origin gimbal geometry, complete mass/momentum snapshots, paired
propulsion evaluation, external point-load resolution, pure held-command RHS,
synthetic actuator lag/limits, and actual solve_ivp result/failure handling.

The inspected source's fixed reference was defined at neutral CG. The selected
contract instead defines D at the fixed leg-attachment plate/ring upper plane.
The copy updates that definition and coordinates all datum-related identifiers.
It changes neither the selected frame directions nor the underlying force,
kinematic, lag or momentum equations. No original body-velocity vector is
silently imported into the new local-velocity schema.

| Recovered name | M4 name/meaning |
|---|---|
| neutral_cg_C_mm | datum_D_C_mm; explicit keyword-only CAD datum argument |
| cg_B0_m | cg_D_m; vector D to G, expressed in B, metres |
| cg_rate_B0_m_s | cg_rate_D_m_s; derivative of B components due to internal motion |
| outer_origin_B0_m | outer_origin_D_m; D to outer origin, expressed in B |
| joint_origins_B0_m | joint_origins_D_m |
| application_points_B0_m | application_points_D_m |
| application_point_rates_B0_m_s | application_point_rates_D_m_s |
| application_point_B0_m | application_point_D_m |
| offset_B0G_B_m | offset_DG_B_m |
| offset_rate_B0G_B_m_s | offset_rate_DG_B_m_s |
| pdr_r12_* schemas | hopper_m4_fixed_D_* schemas; old strings rejected |

The inverse CAD helper uses point_D_m. Every datum-relative vector above uses
FRD body components even where the compact field name contains only D.
The numerical D_C is an explicit geometry input, not zero by default and not
necessarily the neutral CG. A shifted datum requires coherent changes to all
point and CG offsets; it is not a change to local CG position or velocity.

## Package and execution boundary

The package directory is software/pdr_plant/repaired_hopper_m4/ and contains:
helpers/math.py; simulation/state.py; chassis/hopper.py;
propulsion/propulsion.py; propulsion/propeller.py; propulsion/actuators.py;
simulation/environment.py; simulation/simulation.py; and package markers.
All numerical module imports are package-relative. NumPy and SciPy are required;
no dependency installation is performed or authorized by this copy.

For subsequent Guacamole execution use repository='6dof_hopper', sandbox
workdir='.', and python -B. New runners located in software/pdr_plant/ can import
repaired_hopper_m4 directly. Do not invoke the original greeting main.py or the
PyThrust example as though they launched this plant. Missing installations must
be reported through the Chief, not silently installed.

State order remains 13 CG/attitude components plus six analytical actuator
components: p_G,L [m], v_G,L [m/s], q_LB wxyz [1], omega_B [rad/s], upper/lower
rotor speed magnitudes [rad/s], alpha/beta demand-filter states [rad], and actual
alpha/beta angles [rad]. Use module schema constants and units, never length
alone. Preserve every initial/carried state and raw quaternion sample.

solve_ode integrates one immutable HeldCommand. Repeated calls restart at its
initial snapshots. A scheduler must explicitly carry accepted endpoints,
including all actuator states. Output sampling is not controller cadence.
For terminal events inspect actual t_events/y_events or validated dense output;
the final requested output sample need not be the event endpoint. Preserve
IntegrationFailure.solution and do not convert provider exceptions into a
completed trajectory. These behaviors remain subject to independent checks.

## Fixed datum and scope limits

Local L is NED, body B is FRD, CAD C is forward-left-up. q_LB is scalar-first
Hamilton and R_LB maps B into L. Convert CAD points using
r_B=0.001*diag(1,-1,-1)*(p_C-D_C), with CAD mm and simulator m.
The fixed datum converter retains
p_D=p_G-R_LB*r_DG and
v_D=v_G-R_LB*(omega_B cross r_DG+rdot_DG).
There is no new acceleration converter in this migration; consistent rddot_DG
and independent checks remain necessary before such an interface is used.

Simulation, LagParameters and ActuatorEvaluation remain analytical-fixture only.
Some data records can describe provisional_vehicle, but that does not make the
runnable analytical path a vehicle model. Do not relabel vehicle numbers as
fixtures. A vehicle extension requires implemented dynamics, an applicability
assessment, explicit Chief disposition and tests, not removal of a label guard.

The speed-demand lag is not a realizable hobby-ESC command interface. Gimbal
motion is prescribed rather than solved from joint loads. Mass/momentum terms
are supplied, not a derived coupled multibody solution. Prescribed electrical
conditions do not close sag, transient energy or thermal evolution. The original
cylinder aerodynamics is not silently imported. Contact and PID are not added.

Next: publish generated sources and migration records, create independently
specified synthetic providers/configurations/checkers, and execute artifact-bound
regressions. Unperformed physical checks remain null. No hardware selection,
mission acceptance, requirement satisfaction or PDR acceptance is claimed.
'''


def main():
    if RECOVERED.is_symlink() or not RECOVERED.is_dir():
        raise ValueError('Recovered source root must be an existing nonsymlink directory')
    if not HERE.resolve().is_relative_to(SANDBOX.resolve()):
        raise ValueError('Preparation script must reside within the sandbox')
    destinations = [SANDBOX / p for p in OUTPUT_PATHS]
    for path in destinations:
        if not path.resolve().is_relative_to(SANDBOX.resolve()):
            raise ValueError('Output escapes sandbox: ' + str(path))
        if path.exists() or path.is_symlink():
            raise FileExistsError('Preserve earlier output: ' + str(path))

    originals, outputs, records, patch_parts = {}, {}, [], []
    for relative, expected in SOURCE_PINS.items():
        source = checked_source(relative, expected)
        originals[relative] = source
        migrated, history, counts, schemas = transform(relative, source)
        destination = PACKAGE_REL + '/' + relative
        outputs[destination] = migrated
        records.append({
            'recovered_path':str(RECOVERED / relative),
            'recovered_file_sha256':expected,
            'output_path':destination,
            'output_file_sha256':text_hash(migrated),
            'recovered_module_header_historical_only':history,
            'replacement_counts':counts,
            'schema_constants':schemas,
            'syntax_compilation':'completed in memory; no target execution',
        })
        patch_parts.extend(difflib.unified_diff(
            source.splitlines(keepends=True), migrated.splitlines(keepends=True),
            fromfile='previous_run/repaired_hopper_r12/' + relative,
            tofile=destination))

    simulation = outputs[PACKAGE_REL + '/simulation/simulation.py']
    actuators = outputs[PACKAGE_REL + '/propulsion/actuators.py']
    required_guards = (
        (simulation, "self.hopper.model_scope != 'analytical_fixture'"),
        (simulation, "self.propulsion.geometry.model_scope != 'analytical_fixture'"),
        (actuators, "raise ValueError('Uncalibrated lag realization is analytical-fixture only')"),
        (actuators, "raise ValueError('Fixture actuator evaluation cannot represent a vehicle baseline')"),
    )
    for body, guard in required_guards:
        if guard not in body:
            raise ValueError('Required analytical-only guard missing: ' + guard)

    for relative in INIT_PATHS:
        output = ('"""M4 fixed-D analytical package; no automatic initialization.\n'
                  'See ../README_repaired_m4_05.md at the plant task directory.\n'
                  'Source presence is not verification or vehicle authorization.\n"""\n')
        compile(output, PACKAGE_REL + '/' + relative, 'exec')
        outputs[PACKAGE_REL + '/' + relative] = output
        patch_parts.extend(difflib.unified_diff(
            [], output.splitlines(keepends=True), fromfile='/dev/null',
            tofile=PACKAGE_REL + '/' + relative))
    outputs[PATCH_REL] = ''.join(patch_parts)
    outputs[README_REL] = README

    # Recheck all pinned inputs before creating any output. No source writes.
    for relative, expected in SOURCE_PINS.items():
        if file_hash(RECOVERED / relative) != expected:
            raise RuntimeError('Source changed during preparation: ' + relative)

    manifest = {
        'schema':'hopper.plant_source_migration/1',
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'authority':AUTHORITY, 'pre_edit_audit':AUDIT_REF,
        'capability_report':CAPABILITY_REF,
        'generator_path':str(Path(__file__).resolve()),
        'generator_file_sha256':file_hash(Path(__file__)),
        'migration':'Recovered analytical implementation to selected fixed-D semantics',
        'modules':records,
        'output_files_except_this_manifest':[
            {'path':path,'file_sha256':text_hash(content)}
            for path,content in outputs.items()],
        'source_preservation_scope':'Eight digest-pinned recovered regular files checked before and after; broader preservation verification remains separate',
        'analytical_only_guards_retained':True,
        'targets_imported':False,
        'numerical_regression_performed':False,
        'physical_acceptance':'not_assessed',
        'limitations':[
            'Syntax compilation and source generation are not verification.',
            'No vehicle dynamics reduction or numerical vehicle data is selected.',
            'All recovered historical authorization and result claims remain historical.',
            'Fixed-datum acceleration, coupled dynamics, electrical/thermal evolution, contact and PID are not added.',
            'Future fixtures and checkers are new callers requiring explicit schema use and review.',
        ],
    }
    outputs[MANIFEST_REL] = json.dumps(manifest, indent=2, allow_nan=False) + '\n'
    if set(outputs) != set(OUTPUT_PATHS):
        raise RuntimeError('Generated outputs differ from declared output list')
    for relative in OUTPUT_PATHS:
        path = SANDBOX / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(outputs[relative].encode('utf-8'))
        if file_hash(path) != text_hash(outputs[relative]):
            raise RuntimeError('Written output digest differs: ' + relative)
    for relative, expected in SOURCE_PINS.items():
        if file_hash(RECOVERED / relative) != expected:
            raise RuntimeError('Recovered source changed: ' + relative)
    print(json.dumps({
        'generated_files':list(OUTPUT_PATHS),
        'recovered_source_files_checked':len(SOURCE_PINS),
        'target_imports_performed':False,
        'numerical_regression_performed':False,
        'physical_acceptance':'not_assessed',
    }))


if __name__ == '__main__':
    main()
