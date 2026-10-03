# FreeCAD capability evidence — Chief PDR revision 4

Recorded: 2026-10-03. Scope: backend capability only, not vehicle acceptance or manufacturing release.

## Authorization and execution

Current preliminary work-plan decision: 50896eb541aa4c0892237325fae91185. Detailed design remains gated by human acceptance of the current PDR; no such acceptance is recorded.

The GUI-status request 78e71f4dc83d437db33b7af9a6134ff1 failed with RuntimeError. Its diagnostic text was withheld by the runtime. GUI-addon availability therefore remains unconfirmed; this does not establish that headless execution is unavailable.

Headless FreeCAD MCP request db644cdf888844f29d4cf16da97dc3b3 completed using cad/chief_r4_capability_probe.py. The declared FCStd, STEP and measurement outputs were returned with no missing outputs. The captured environment reported FreeCAD 1.1.1 and Python 3.12.3. Process completion is recorded separately from the artifact checks below.

## Retained artifacts

- Generator: cad/chief_r4_capability_probe.py
- Native model: cad/chief_r4_capability/probe.FCStd
- STEP export: cad/chief_r4_capability/probe.step
- Captured measurements: cad/chief_r4_capability/measurements.json
- Original checker: cad/chief_r4_verify_capability.py
- Revised checker: cad/chief_r4_verify_capability_v2.py

These are synthetic capability artifacts, not the hopper assembly. Exact artifact revisions and record hashes are retained in this report's producing-tool inputs.

## Captured geometry and verification

The probe created a parametric Part::Box with dimensions 10 × 20 × 30 mm. It saved and reopened the native model, changed Length to 11 mm and recomputed, restored Length to 10 mm, and independently read the STEP export through the geometry kernel. The edit/restore exercise was not saved over the native output.

Captured volumes were 6000 mm³ for the created, reopened, restored and STEP-imported shapes, and 6600 mm³ for the edited shape. Each captured stage reported one valid, non-null solid. Bounds and native dimension parameters were checked against the intended dimensions.

Revised verify_command request d10c4855887f45639a1fc896b99493ba returned VerificationResult outcome passed, with all reported checks true. The checks included file existence, recorded paths, sizes and SHA-256 correspondence; measurement schema, scope and units; solid validity/count; dimensions, bounds and volumes; and the 600 mm³ edit response. Numerical tolerances were absolute 1e-8 mm for dimensions, absolute 1e-6 mm³ for volumes and relative 1e-9.

The revised checker validates the saved files' correspondence to the captured geometry measurements. It does not itself rerun the FreeCAD geometry kernel. A changed artifact requires regeneration and fresh geometry inspection, not reuse of these measurements.

## Correction and failure history

Original verify_command request 4cd730818d4144628aa234ea9c5df745 failed runtime validation. Diagnostic execute request 95e943473d92480eb74662c4872490fe subsequently exposed the original checker's stdout, including two null out-of-scope checks. That execute result is diagnostic evidence, not a substitute verification result. The runtime did not disclose a definitive validation-failure cause.

The retained v2 checker removes those unassessed checks from the boolean check set and describes the exclusions in its explanation. Geometry tolerances were not relaxed. Only the completed revised verify_command result supports the scoped verification outcome above. A subsequent action rejection does not disclose its cause or establish additional acceptance.

## Limits and remaining work

This report does not close REQ-CAD-ASSEMBLY. Vehicle solids, mounting interfaces, rotor/structure swept clearances, actuator travel, component fit, structural strength, material-density assignments, total mass, CG, inertia and CAD-to-body transforms remain outside this probe. No physical hardware validation was performed.

The vehicle CAD branch still requires a current Chief-recorded preliminary component/mechanism choice, sourced dimensions, editable assembly and drawings, artifact-derived geometry checks, and reconciliation with propulsion and purchasing budgets. Successful box export is not evidence that those deliverables satisfy their acceptance criteria.
