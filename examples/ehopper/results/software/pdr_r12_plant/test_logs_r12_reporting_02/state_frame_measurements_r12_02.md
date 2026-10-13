# PDR r12 state/frame measurement reporting reconciliation 02

Generated UTC: 2026-10-13T13:42:17.434609+00:00

Reporting-only extraction from the retained collector-01 re-execution logs. No tests are rerun and no plant, checker, fixture or acceptance threshold is changed. This addendum repairs the missing state/frame measurement table only; other checker tables and all registered verification outcomes remain unchanged. The registered outcome remains inconclusive. Synthetic analytical fixtures and proposed numerical regression tolerances are not calibrated vehicle inputs or human-agreed vehicle acceptance limits. No PID tuning, mission, hardware or PDR/CDR acceptance is implied.

## Confirmed reporting root cause

Collector 01 parse_diagnostics recognizes top-level check/details objects only. The retained state/frame stderr stores observations under a measurements mapping. Its entries therefore never reached measured_row or the old digest tables. Numerical observations were retained, not absent.

The original digest recorded zero state/frame measured rows. This is not evidence of zero error. This addendum reads the existing archived measurements mapping; it does not regenerate measurements.

## Provenance

- Source: `software/pdr_r12_plant/test_logs_r12_01/checker_raw_logs_r12_01.txt`.
- Original digest: `software/pdr_r12_plant/test_logs_r12_01/measured_error_digest_r12_01.json`.
- Raw-log and digest file hashes are pinned and checked before/after extraction.
- Selected archived stream byte lengths and hashes are checked against their headers.
- Exact source lines, JSON keys and unrounded observations are retained in the companion JSON.
- Registered evidence: `PDR-R12-PLANT-STATE-FRAME-MASS-VERIFICATION-02` revision 1.
- Retained result: **inconclusive**; 83 true, 0 false, 4 null checks.

Registered explanation, preserved from retained stdout:

Scoped analytical software checks only: 83/83 recorded boolean checks satisfied. Measurements and actual file hashes are on stderr. Null checks are explicitly unperformed by this program. No propulsion/trajectory pass, vehicle validity, PID tuning, mission acceptance or PDR/CDR acceptance is inferred. Reporting correction 02 preserves all four null checks and all analytical checks; a passed outcome with null checks is reported as inconclusive under the clarified runtime contract.

## Recovered observations

Numerical rows: 61. Deliberate negative-fixture records: 12. Other measurement records: 0.
Recorded numerical errors within their recorded tolerance: 61; outside: 0.

Counts describe existing observations, not new verification. Negative fixtures are expected rejection observations, not measured-error rows. Completion checks need not have numerical observations.

| Check | Recorded maximum absolute error | Recorded tolerance | Unit | Raw-log line |
|---|---:|---:|---|---:|
| cad.inertia_kg m^2 | 0 | 1.0000000000000001e-15 | kg m^2 | 9 |
| cad.inertia_kg mm^2 | 0 | 1.0000000000000001e-15 | kg m^2 | 9 |
| cad.inertia_mm^5 | 2.1175823681357508e-22 | 1.0000000000000001e-15 | kg m^2 | 9 |
| cad.point_roundtrip | 7.1054273576010019e-15 | 1e-10 | mm | 9 |
| cad.point_units_and_datum | 6.9388939039072284e-18 | 9.9999999999999998e-13 | m | 9 |
| cad.proper_rotation | 0 | 9.9999999999999998e-13 | 1 | 9 |
| datum.analytic_velocity | 0 | 1.0000000000000001e-09 | m/s | 9 |
| datum.finite_difference_velocity_0 | 1.6663642687930746e-11 | 1.0000000000000001e-09 | m/s | 9 |
| datum.finite_difference_velocity_1 | 3.9028835718823984e-11 | 1.0000000000000001e-09 | m/s | 9 |
| datum.position | 0 | 9.9999999999999998e-13 | m | 9 |
| frame.carried_gimbal_order | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_0.determinant | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_0.direction | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_0.double_cover | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_0.orthogonality | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_0.quaternion | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_1.determinant | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_1.direction | 1.1102230246251565e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_1.double_cover | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_1.orthogonality | 2.2204460492503131e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_1.quaternion | 2.7755575615628914e-17 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_2.determinant | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_2.direction | 1.1102230246251565e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_2.double_cover | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_2.orthogonality | 6.3173125541858896e-17 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_2.quaternion | 1.1102230246251565e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_3.determinant | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_3.direction | 1.6081226496766364e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_3.double_cover | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_3.orthogonality | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_3.quaternion | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_4.determinant | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_4.direction | 1.6081226496766364e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_4.double_cover | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_4.orthogonality | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_4.quaternion | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_5.determinant | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_5.direction | 1.6081226496766364e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_5.double_cover | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_5.orthogonality | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.case_5.quaternion | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.hamilton_components | 0 | 9.9999999999999998e-13 | 1 | 9 |
| frame.hamilton_composition | 4.4408920985006262e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.legacy_default_direction | 1.1102230246251565e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.legacy_transpose_direction | 1.1102230246251565e-16 | 9.9999999999999998e-13 | 1 | 9 |
| frame.norm_derivative_identity | 1.3877787807814457e-17 | 9.9999999999999998e-13 | 1/s | 9 |
| frame.quaternion_derivative | 2.7755575615628914e-17 | 9.9999999999999998e-13 | 1/s | 9 |
| frame.scaled_normalization_0 | 2.7755575615628914e-17 | 9.9999999999999998e-13 | 1 | 9 |
| frame.scaled_normalization_1 | 2.7755575615628914e-17 | 9.9999999999999998e-13 | 1 | 9 |
| mass.actual_cg_relative_arm | 0 | 9.9999999999999998e-13 | m | 9 |
| mass.full_momentum_residual | 1.3877787807814457e-17 | 1e-10 | N m | 9 |
| mass.total_angular_momentum | 0 | 1e-10 | kg m^2/s | 9 |
| state.actuator_ownership | 0 | 0 | rad/s, rad/s, rad, rad, rad, rad | 9 |
| state.all_initial_components | 0 | 0 | mixed SI; PLANT_UNITS | 9 |
| state.euler_initialization | 2.7755575615628914e-17 | 9.9999999999999998e-13 | 1 | 9 |
| state.explicit_body_velocity_migration | 2.7755575615628914e-17 | 1.0000000000000001e-09 | m/s | 9 |
| state.inverse_velocity_resolution | 1.3877787807814457e-17 | 1.0000000000000001e-09 | m/s | 9 |
| state.owned_input_and_outputs | 0 | 0 | mixed SI; STATE_UNITS | 9 |
| state.plant_roundtrip | 0 | 0 | mixed SI; PLANT_UNITS | 9 |
| state.raw_norm_error_preserved | 0 | 0 | mixed SI; STATE_UNITS | 9 |
| state.simulation_initial_copy | 0 | 0 | mixed SI; PLANT_UNITS | 9 |

## Explicitly unperformed checks

- numerical_trajectory_checks_in_this_program
- propulsion_and_actuator_analytical_checks_in_this_program
- vehicle_closed_loop_mission_acceptance
- vehicle_physical_validation

## Scope and preservation

Original logs, digest, checkers and source remain separate. The README and PID proposal references to the original missing table describe digest 01; use this addendum for the recovered state/frame rows. Neither document nor the original digest is overwritten.

Vehicle mass/articulated momentum, geometry, rotor assignments, calibrated propulsion, loaded actuator limits, electrical/thermal closure, aerodynamic/contact inputs and proposal dispositions remain downstream Chief-owned dependencies.
