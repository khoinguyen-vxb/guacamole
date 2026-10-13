# PDR r12 plant checker logs and measured errors (digest 01)

Generated (UTC): 2026-10-13T02:08:32.548796+00:00

Collector: `software/pdr_r12_plant/collect_verification_logs_r12_01.py`. Raw stdout/stderr: `software/pdr_r12_plant/test_logs_r12_01/checker_raw_logs_r12_01.txt`. Structured digest: `software/pdr_r12_plant/test_logs_r12_01/measured_error_digest_r12_01.json`.

**Scope.** Test-log capture and measured-error tabulation only. Registered verification outcomes are the verify_command evidence records named per checker; these re-executions of the same hash-pinned files retain the stdout/stderr and measured errors that the registered runs did not retain as artifacts. All fixtures are synthetic analytical fixtures. Tolerances are proposed numerical regression thresholds from analytical_fixture_config_r12_01.json, not human-agreed vehicle acceptance limits. Process exit status is not a verification pass. No PID tuning, vehicle closed-loop mission, electrical/thermal endurance, physical validation or PDR/CDR acceptance is tested or implied.

## Execution environment

- Interpreter: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/.venv/bin/python`, CPython 3.13.11
- numpy 2.5.2, scipy 1.18.0 (distribution metadata)
- Platform: Linux-6.6.87.2-microsoft-standard-WSL2-aarch64-with-glibc2.39
- Checker working directory: `/home/ngvnngkhoi/guacamole/examples/ehopper/results`; PYTHONDONTWRITEBYTECODE=1; one subprocess per checker

## Artifact binding

File SHA-256 values, not Guacamole Ref hashes; 12-character prefixes shown, full values in the JSON digest. All equal: true.

| file | published | before runs | after runs | all equal |
|---|---|---|---|---|
| software/pdr_r12_plant/analytical_fixture_config_r12_01.json | 397133a2ab34 | 397133a2ab34 | 397133a2ab34 | true |
| software/pdr_r12_plant/analytical_fixture_models_r12_01.py | 25ae16b4a9fb | 25ae16b4a9fb | 25ae16b4a9fb | true |
| software/pdr_r12_plant/repaired_hopper_r12/helpers/math.py | 281a5578b6d3 | 281a5578b6d3 | 281a5578b6d3 | true |
| software/pdr_r12_plant/repaired_hopper_r12/simulation/state.py | b62a1a4fcc70 | b62a1a4fcc70 | b62a1a4fcc70 | true |
| software/pdr_r12_plant/repaired_hopper_r12/chassis/hopper.py | f2b6e4b54634 | f2b6e4b54634 | f2b6e4b54634 | true |
| software/pdr_r12_plant/repaired_hopper_r12/propulsion/propulsion.py | d860528b2778 | d860528b2778 | d860528b2778 | true |
| software/pdr_r12_plant/repaired_hopper_r12/propulsion/propeller.py | ce7be67ceae3 | ce7be67ceae3 | ce7be67ceae3 | true |
| software/pdr_r12_plant/repaired_hopper_r12/propulsion/actuators.py | bacfd1457ea3 | bacfd1457ea3 | bacfd1457ea3 | true |
| software/pdr_r12_plant/repaired_hopper_r12/simulation/environment.py | ba795b5d1d53 | ba795b5d1d53 | ba795b5d1d53 | true |
| software/pdr_r12_plant/repaired_hopper_r12/simulation/simulation.py | a186c50ab7c5 | a186c50ab7c5 | a186c50ab7c5 | true |
| software/pdr_r12_plant/verify_state_frames_mass_r12_01.py | 2d078567740c | 2d078567740c | 2d078567740c | true |
| software/pdr_r12_plant/verify_state_frames_mass_r12_02.py | 040db6b78e88 | 040db6b78e88 | 040db6b78e88 | true |
| software/pdr_r12_plant/verify_propulsion_interfaces_r12_01.py | 99e8ff520f11 | 99e8ff520f11 | 99e8ff520f11 | true |
| software/pdr_r12_plant/verify_solver_open_loop_r12_01.py | e18851bfbec6 | e18851bfbec6 | e18851bfbec6 | true |
| software/pdr_r12_plant/verify_actuator_response_r12_01.py | b23611266cdb | b23611266cdb | b23611266cdb | true |

## Checker re-runs

Outcomes and counts are copied from each re-run VerificationResult and are not reinterpreted. Registered evidence is unchanged.

| checker | registered evidence (request) | registered outcome | re-run outcome | true/false/null | return code | timed out | duration (s) | measured rows | outside tolerance | worst error/tolerance | worst check |
|---|---|---|---|---|---|---|---|---|---|---|---|
| state_frames_mass_02 | PDR-R12-PLANT-STATE-FRAME-MASS-VERIFICATION-02 (21ca2850ef224d3bbb276822db3dd2ff) | inconclusive | inconclusive | 83/0/4 | 0 | false | 1.2 | 0 | 0 | n/a | n/a |
| propulsion_interfaces_01 | PDR-R12-PLANT-PROPULSION-INTERFACE-VERIFICATION-01 (9de4362ce7284d998d70953f1d4599fa) | inconclusive | inconclusive | 151/0/4 | 0 | false | 0.8 | 124 | 0 | 2.711e-02 | geometry.air_relative_hub_velocity_1 |
| solver_open_loop_01 | PDR-R12-PLANT-SOLVER-OPEN-LOOP-VERIFICATION-01 (a0229a233f1947cea5f61cd143ae5ffc) | inconclusive | inconclusive | 146/0/4 | 0 | false | 8.6 | 88 | 0 | 3.553e-05 | trim.force_balances_weight |
| actuator_response_01 | PDR-R12-PLANT-ACTUATOR-RESPONSE-VERIFICATION-01 (477c2f40ce7242cb9a9a8810e17993e3) | inconclusive | inconclusive | 116/0/4 | 0 | false | 8.1 | 64 | 0 | 1.196e-01 | release.refinement.filter_angles |

## Unperformed (null) and false checks

- state_frames_mass_02: null = numerical_trajectory_checks_in_this_program, propulsion_and_actuator_analytical_checks_in_this_program, vehicle_closed_loop_mission_acceptance, vehicle_physical_validation; false = none
- propulsion_interfaces_01: null = integrated_motor_gimbal_response, physical_validation, solver_returns_events_and_failure_tests, vehicle_closed_loop_mission_acceptance; false = none
- solver_open_loop_01: null = integrated_actuator_response_analytical_verification, vehicle_closed_loop_mission_acceptance, vehicle_electrical_thermal_endurance, vehicle_physical_validation; false = none
- actuator_response_01: null = complete_articulated_vehicle_accuracy, loaded_hardware_actuator_calibration, vehicle_closed_loop_saturation_recovery_and_mission, vehicle_electrical_thermal_and_physical_validation; false = none

## Largest error-to-tolerance ratios

Ratios use the proposed regression tolerance. Zero-tolerance rows are exact comparisons, reported with ratio 0 when exactly equal.

### state_frames_mass_02

Rows 0; within 0; outside 0; undetermined 0; exact comparisons 0; rows by unit {}.

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|

### propulsion_interfaces_01

Rows 124; within 124; outside 0; undetermined 0; exact comparisons 4; rows by unit {"1": 1, "A": 24, "N": 29, "N m": 33, "N m/rad": 2, "W": 8, "m": 10, "m/s": 5, "m/s^2": 6, "mixed SI derivatives": 1, "mixed SI state": 1, "rad": 1, "rad/s": 1, "rad/s^2": 1, "rad^2": 1}.

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|
| geometry.air_relative_hub_velocity_1 | 2.711e-11 | 1.000e-09 | m/s | 2.711e-02 | true |
| geometry.air_relative_hub_velocity_0 | 1.738e-11 | 1.000e-09 | m/s | 1.738e-02 | true |
| geometry.component_rates_1 | 3.675e-12 | 1.000e-09 | m/s | 3.675e-03 | true |
| geometry.component_rates_0 | 8.993e-13 | 1.000e-09 | m/s | 8.993e-04 | true |
| bottom.effectiveness_0 | 8.100e-13 | 1.000e-07 | N m/rad | 8.100e-06 | true |
| bottom.effectiveness_1 | 8.100e-13 | 1.000e-07 | N m/rad | 8.100e-06 | true |
| bottom.closed_moment_2 | 5.551e-17 | 1.000e-10 | N m | 5.551e-07 | true |
| bottom.closed_moment_3 | 5.551e-17 | 1.000e-10 | N m | 5.551e-07 | true |
| plant.external_moments_once | 2.776e-17 | 1.000e-10 | N m | 2.776e-07 | true |
| plant.full_inertia_residual | 2.776e-17 | 1.000e-10 | N m | 2.776e-07 | true |
| wrench.reference_change | 2.429e-17 | 1.000e-10 | N m | 2.429e-07 | true |
| time.supplied_argument_2 | 1.110e-16 | 1.000e-09 | m/s^2 | 1.110e-07 | true |

### solver_open_loop_01

Rows 88; within 88; outside 0; undetermined 0; exact comparisons 5; rows by unit {"1": 14, "N": 1, "N m": 1, "m": 11, "m/s": 11, "mixed SI state": 4, "rad": 22, "rad/s": 22, "s": 2}.

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|
| trim.force_balances_weight | 3.553e-15 | 1.000e-10 | N | 3.553e-05 | true |
| coupled.RK45_DOP853_agreement.actual_gimbal | 3.440e-14 | 1.000e-08 | rad | 3.440e-06 | true |
| coupled.RK45_DOP853_agreement.quaternion | 8.021e-15 | 1.000e-08 | 1 | 8.021e-07 | true |
| coupled.RK45_DOP853_agreement.body_rate | 7.544e-14 | 1.000e-07 | rad/s | 7.544e-07 | true |
| coupled.raw_quaternion_norm | 2.220e-16 | 1.000e-09 | 1 | 2.220e-07 | true |
| free.raw_quaternion_norm | 2.220e-16 | 1.000e-09 | 1 | 2.220e-07 | true |
| free.refinement_agreement.position | 1.332e-14 | 1.000e-07 | m | 1.332e-07 | true |
| coupled.refinement_agreement.quaternion | 7.216e-16 | 1.000e-08 | 1 | 7.216e-08 | true |
| free.analytic_dense_output.velocity | 5.329e-15 | 1.000e-07 | m/s | 5.329e-08 | true |
| free.analytic_samples.velocity | 5.329e-15 | 1.000e-07 | m/s | 5.329e-08 | true |
| coupled.RK45_DOP853_agreement.velocity | 4.968e-15 | 1.000e-07 | m/s | 4.968e-08 | true |
| free.refinement_agreement.quaternion | 4.441e-16 | 1.000e-08 | 1 | 4.441e-08 | true |

### actuator_response_01

Rows 64; within 64; outside 0; undetermined 0; exact comparisons 21; rows by unit {"1": 6, "mixed SI state": 14, "rad": 11, "rad/s": 14, "rad/s^2": 19}.

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|
| release.refinement.filter_angles | 1.196e-09 | 1.000e-08 | rad | 1.196e-01 | true |
| release.refinement.actual_angles | 4.534e-10 | 1.000e-08 | rad | 4.534e-02 | true |
| saturated.refinement.filter_angles | 2.517e-10 | 1.000e-08 | rad | 2.517e-02 | true |
| release.refinement.motor_speed | 9.741e-08 | 1.000e-05 | rad/s | 9.741e-03 | true |
| saturated.refinement.actual_angles | 9.733e-11 | 1.000e-08 | rad | 9.733e-03 | true |
| release.piecewise_motor | 8.160e-08 | 1.000e-05 | rad/s | 8.160e-03 | true |
| saturated.rate_derivative_0_0 | 2.269e-09 | 2.000e-06 | rad/s^2 | 1.135e-03 | true |
| release.rate_derivative_0_0 | 2.264e-09 | 2.000e-06 | rad/s^2 | 1.132e-03 | true |
| saturated.rate_derivative_0_1 | 5.566e-10 | 2.000e-06 | rad/s^2 | 2.783e-04 | true |
| release.rate_derivative_0_1 | 5.429e-10 | 2.000e-06 | rad/s^2 | 2.714e-04 | true |
| release.rate_derivative_1_0 | 4.761e-10 | 2.000e-06 | rad/s^2 | 2.380e-04 | true |
| saturated.rate_derivative_1_0 | 4.736e-10 | 2.000e-06 | rad/s^2 | 2.368e-04 | true |

## Other diagnostics

- state_frames_mass_02: stderr JSON lines 2; check diagnostics 0; deliberate negative fixtures 0; shape/finiteness failures 0; error fields without a paired tolerance 0; unparsed stderr lines 0.
- propulsion_interfaces_01: stderr JSON lines 137; check diagnostics 132; deliberate negative fixtures 7; shape/finiteness failures 0; error fields without a paired tolerance 0; unparsed stderr lines 0.
- solver_open_loop_01: stderr JSON lines 116; check diagnostics 102; deliberate negative fixtures 14; shape/finiteness failures 0; error fields without a paired tolerance 0; unparsed stderr lines 0.
- actuator_response_01: stderr JSON lines 80; check diagnostics 69; deliberate negative fixtures 5; shape/finiteness failures 0; error fields without a paired tolerance 0; unparsed stderr lines 0.

## Complete measured-error tables

### state_frames_mass_02 (sorted by check name)

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|

### propulsion_interfaces_01 (sorted by check name)

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|
| actuator.active_cone_boundary | 0 | 1.000e-10 | 1 | 0 | true |
| actuator.actual_angles_not_commands | 0 | 0 | rad | 0 | true |
| actuator.common_radial_reduction | 0 | 1.000e-10 | rad^2 | 0 | true |
| actuator.instantaneous_motor_lag_and_acceleration_cap | 0 | 1.000e-05 | rad/s^2 | 0 | true |
| actuator.speed_command_limits | 0 | 0 | rad/s | 0 | true |
| bottom.0.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| bottom.0.branch_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.0.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| bottom.0.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| bottom.0.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| bottom.0.points | 0 | 1.000e-12 | m | 0 | true |
| bottom.0.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| bottom.0.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| bottom.0.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| bottom.0.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| bottom.0.winding_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.1.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| bottom.1.branch_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.1.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| bottom.1.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| bottom.1.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| bottom.1.points | 0 | 1.000e-12 | m | 0 | true |
| bottom.1.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| bottom.1.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| bottom.1.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| bottom.1.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| bottom.1.winding_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.2.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| bottom.2.branch_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.2.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| bottom.2.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| bottom.2.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| bottom.2.points | 0 | 1.000e-12 | m | 0 | true |
| bottom.2.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| bottom.2.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| bottom.2.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| bottom.2.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| bottom.2.winding_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.3.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| bottom.3.branch_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.3.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| bottom.3.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| bottom.3.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| bottom.3.points | 0 | 1.000e-12 | m | 0 | true |
| bottom.3.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| bottom.3.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| bottom.3.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| bottom.3.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| bottom.3.winding_current | 0 | 1.000e-10 | A | 0 | true |
| bottom.closed_force_0 | 0 | 1.000e-10 | N | 0 | true |
| bottom.closed_force_1 | 0 | 1.000e-10 | N | 0 | true |
| bottom.closed_force_2 | 0 | 1.000e-10 | N | 0 | true |
| bottom.closed_force_3 | 0 | 1.000e-10 | N | 0 | true |
| bottom.closed_moment_0 | 0 | 1.000e-10 | N m | 0 | true |
| bottom.closed_moment_1 | 0 | 1.000e-10 | N m | 0 | true |
| bottom.closed_moment_2 | 5.551e-17 | 1.000e-10 | N m | 5.551e-07 | true |
| bottom.closed_moment_3 | 5.551e-17 | 1.000e-10 | N m | 5.551e-07 | true |
| bottom.effectiveness_0 | 8.100e-13 | 1.000e-07 | N m/rad | 8.100e-06 | true |
| bottom.effectiveness_1 | 8.100e-13 | 1.000e-07 | N m/rad | 8.100e-06 | true |
| geometry.actual_hubs | 0 | 1.000e-12 | m | 0 | true |
| geometry.air_relative_hub_velocity_0 | 1.738e-11 | 1.000e-09 | m/s | 1.738e-02 | true |
| geometry.air_relative_hub_velocity_1 | 2.711e-11 | 1.000e-09 | m/s | 2.711e-02 | true |
| geometry.component_rates_0 | 8.993e-13 | 1.000e-09 | m/s | 8.993e-04 | true |
| geometry.component_rates_1 | 3.675e-12 | 1.000e-09 | m/s | 3.675e-03 | true |
| geometry.separated_origins | 0 | 1.000e-12 | m | 0 | true |
| plant.NED_acceleration_no_body_transport | 5.551e-17 | 1.000e-09 | m/s^2 | 5.551e-08 | true |
| plant.actual_not_commanded_rotor_force | 0 | 1.000e-10 | N | 0 | true |
| plant.external_moments_once | 2.776e-17 | 1.000e-10 | N m | 2.776e-07 | true |
| plant.full_inertia_residual | 2.776e-17 | 1.000e-10 | N m | 2.776e-07 | true |
| plant.gravity_positive_down | 0 | 1.000e-09 | m/s^2 | 0 | true |
| plant.position_derivative | 0 | 1.000e-09 | m/s | 0 | true |
| purity.input_vector_unchanged | 0 | 0 | mixed SI state | 0 | true |
| purity.out_of_order_repeatability | 0 | 0 | mixed SI derivatives | 0 | true |
| time.supplied_argument_0 | 5.551e-17 | 1.000e-09 | m/s^2 | 5.551e-08 | true |
| time.supplied_argument_1 | 5.551e-17 | 1.000e-09 | m/s^2 | 5.551e-08 | true |
| time.supplied_argument_2 | 1.110e-16 | 1.000e-09 | m/s^2 | 1.110e-07 | true |
| time.supplied_argument_3 | 5.551e-17 | 1.000e-09 | m/s^2 | 5.551e-08 | true |
| torque.0.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| torque.0.branch_current | 0 | 1.000e-10 | A | 0 | true |
| torque.0.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| torque.0.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| torque.0.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| torque.0.points | 0 | 1.000e-12 | m | 0 | true |
| torque.0.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| torque.0.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| torque.0.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| torque.0.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| torque.0.winding_current | 0 | 1.000e-10 | A | 0 | true |
| torque.1.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| torque.1.branch_current | 0 | 1.000e-10 | A | 0 | true |
| torque.1.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| torque.1.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| torque.1.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| torque.1.points | 0 | 1.000e-12 | m | 0 | true |
| torque.1.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| torque.1.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| torque.1.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| torque.1.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| torque.1.winding_current | 0 | 1.000e-10 | A | 0 | true |
| torque.2.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| torque.2.branch_current | 0 | 1.000e-10 | A | 0 | true |
| torque.2.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| torque.2.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| torque.2.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| torque.2.points | 0 | 1.000e-12 | m | 0 | true |
| torque.2.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| torque.2.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| torque.2.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| torque.2.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| torque.2.winding_current | 0 | 1.000e-10 | A | 0 | true |
| torque.equal_Q_cancel | 0 | 1.000e-10 | N m | 0 | true |
| torque.unequal_Q_equal_speed.auxiliary_counted_once | 0 | 1.000e-10 | A | 0 | true |
| torque.unequal_Q_equal_speed.branch_current | 0 | 1.000e-10 | A | 0 | true |
| torque.unequal_Q_equal_speed.external_aerodynamic_couples | 0 | 1.000e-10 | N m | 0 | true |
| torque.unequal_Q_equal_speed.paired_drag | 0 | 1.000e-10 | N m | 0 | true |
| torque.unequal_Q_equal_speed.paired_thrust | 0 | 1.000e-10 | N | 0 | true |
| torque.unequal_Q_equal_speed.points | 0 | 1.000e-12 | m | 0 | true |
| torque.unequal_Q_equal_speed.resolved_force | 0 | 1.000e-10 | N | 0 | true |
| torque.unequal_Q_equal_speed.resolved_moment | 0 | 1.000e-10 | N m | 0 | true |
| torque.unequal_Q_equal_speed.rotor_forces | 0 | 1.000e-10 | N | 0 | true |
| torque.unequal_Q_equal_speed.shared_bus_power | 0 | 1.000e-08 | W | 0 | true |
| torque.unequal_Q_equal_speed.winding_current | 0 | 1.000e-10 | A | 0 | true |
| wrench.reference_change | 2.429e-17 | 1.000e-10 | N m | 2.429e-07 | true |
| wrench.single_CG_shift | 0 | 1.000e-10 | N m | 0 | true |

### solver_open_loop_01 (sorted by check name)

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|
| coupled.RK45_DOP853_agreement.actual_gimbal | 3.440e-14 | 1.000e-08 | rad | 3.440e-06 | true |
| coupled.RK45_DOP853_agreement.body_rate | 7.544e-14 | 1.000e-07 | rad/s | 7.544e-07 | true |
| coupled.RK45_DOP853_agreement.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| coupled.RK45_DOP853_agreement.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| coupled.RK45_DOP853_agreement.position | 1.110e-15 | 1.000e-07 | m | 1.110e-08 | true |
| coupled.RK45_DOP853_agreement.quaternion | 8.021e-15 | 1.000e-08 | 1 | 8.021e-07 | true |
| coupled.RK45_DOP853_agreement.velocity | 4.968e-15 | 1.000e-07 | m/s | 4.968e-08 | true |
| coupled.all_nineteen_initial_components | 0 | 0 | mixed SI state | 0 | true |
| coupled.initial_snapshot_unchanged | 0 | 0 | mixed SI state | 0 | true |
| coupled.raw_quaternion_norm | 2.220e-16 | 1.000e-09 | 1 | 2.220e-07 | true |
| coupled.refinement_agreement.actual_gimbal | 1.041e-17 | 1.000e-08 | rad | 1.041e-09 | true |
| coupled.refinement_agreement.body_rate | 2.220e-16 | 1.000e-07 | rad/s | 2.220e-09 | true |
| coupled.refinement_agreement.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| coupled.refinement_agreement.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| coupled.refinement_agreement.position | 6.661e-16 | 1.000e-07 | m | 6.661e-09 | true |
| coupled.refinement_agreement.quaternion | 7.216e-16 | 1.000e-08 | 1 | 7.216e-08 | true |
| coupled.refinement_agreement.velocity | 1.776e-15 | 1.000e-07 | m/s | 1.776e-08 | true |
| event.analytic_event_state.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| event.analytic_event_state.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| event.analytic_event_state.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| event.analytic_event_state.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| event.analytic_event_state.position | 3.331e-16 | 1.000e-07 | m | 3.331e-09 | true |
| event.analytic_event_state.quaternion | 0 | 1.000e-08 | 1 | 0 | true |
| event.analytic_event_state.velocity | 8.882e-16 | 1.000e-07 | m/s | 8.882e-09 | true |
| event.dense_endpoint.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| event.dense_endpoint.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| event.dense_endpoint.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| event.dense_endpoint.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| event.dense_endpoint.position | 3.331e-16 | 1.000e-07 | m | 3.331e-09 | true |
| event.dense_endpoint.quaternion | 0 | 1.000e-08 | 1 | 0 | true |
| event.dense_endpoint.velocity | 8.882e-16 | 1.000e-07 | m/s | 8.882e-09 | true |
| event.pre_event_output.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| event.pre_event_output.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| event.pre_event_output.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| event.pre_event_output.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| event.pre_event_output.position | 1.110e-16 | 1.000e-07 | m | 1.110e-09 | true |
| event.pre_event_output.quaternion | 0 | 1.000e-08 | 1 | 0 | true |
| event.pre_event_output.velocity | 0 | 1.000e-07 | m/s | 0 | true |
| event.quadratic_time | 0 | 1.000e-08 | s | 0 | true |
| event.requested_samples_retained | 0 | 0 | s | 0 | true |
| free.analytic_dense_output.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| free.analytic_dense_output.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| free.analytic_dense_output.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| free.analytic_dense_output.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| free.analytic_dense_output.position | 2.665e-15 | 1.000e-07 | m | 2.665e-08 | true |
| free.analytic_dense_output.quaternion | 2.220e-16 | 1.000e-08 | 1 | 2.220e-08 | true |
| free.analytic_dense_output.velocity | 5.329e-15 | 1.000e-07 | m/s | 5.329e-08 | true |
| free.analytic_samples.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| free.analytic_samples.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| free.analytic_samples.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| free.analytic_samples.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| free.analytic_samples.position | 2.665e-15 | 1.000e-07 | m | 2.665e-08 | true |
| free.analytic_samples.quaternion | 3.331e-16 | 1.000e-08 | 1 | 3.331e-08 | true |
| free.analytic_samples.velocity | 5.329e-15 | 1.000e-07 | m/s | 5.329e-08 | true |
| free.initial_ownership_after_solve | 0 | 0 | mixed SI state | 0 | true |
| free.initial_state_exact | 0 | 0 | mixed SI state | 0 | true |
| free.raw_quaternion_norm | 2.220e-16 | 1.000e-09 | 1 | 2.220e-07 | true |
| free.refinement_agreement.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| free.refinement_agreement.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| free.refinement_agreement.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| free.refinement_agreement.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| free.refinement_agreement.position | 1.332e-14 | 1.000e-07 | m | 1.332e-07 | true |
| free.refinement_agreement.quaternion | 4.441e-16 | 1.000e-08 | 1 | 4.441e-08 | true |
| free.refinement_agreement.velocity | 1.776e-15 | 1.000e-07 | m/s | 1.776e-08 | true |
| free.repeat_restarts_initial_state.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| free.repeat_restarts_initial_state.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| free.repeat_restarts_initial_state.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| free.repeat_restarts_initial_state.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| free.repeat_restarts_initial_state.position | 0 | 1.000e-07 | m | 0 | true |
| free.repeat_restarts_initial_state.quaternion | 0 | 1.000e-08 | 1 | 0 | true |
| free.repeat_restarts_initial_state.velocity | 0 | 1.000e-07 | m/s | 0 | true |
| trim.external_moment_zero | 0 | 1.000e-10 | N m | 0 | true |
| trim.force_balances_weight | 3.553e-15 | 1.000e-10 | N | 3.553e-05 | true |
| trim.raw_quaternion_norm | 0 | 1.000e-09 | 1 | 0 | true |
| trim.refinement_agreement.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| trim.refinement_agreement.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| trim.refinement_agreement.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| trim.refinement_agreement.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| trim.refinement_agreement.position | 0 | 1.000e-07 | m | 0 | true |
| trim.refinement_agreement.quaternion | 0 | 1.000e-08 | 1 | 0 | true |
| trim.refinement_agreement.velocity | 4.930e-32 | 1.000e-07 | m/s | 4.930e-25 | true |
| trim.stationary_state.actual_gimbal | 0 | 1.000e-08 | rad | 0 | true |
| trim.stationary_state.body_rate | 0 | 1.000e-07 | rad/s | 0 | true |
| trim.stationary_state.demand_filter | 0 | 1.000e-08 | rad | 0 | true |
| trim.stationary_state.motor_speed | 0 | 1.000e-05 | rad/s | 0 | true |
| trim.stationary_state.position | 0 | 1.000e-07 | m | 0 | true |
| trim.stationary_state.quaternion | 0 | 1.000e-08 | 1 | 0 | true |
| trim.stationary_state.velocity | 1.776e-15 | 1.000e-07 | m/s | 1.776e-08 | true |

### actuator_response_01 (sorted by check name)

| check | measured error | tolerance | unit | error/tolerance | within |
|---|---|---|---|---|---|
| release.actual_signed_rotor_speeds | 0 | 0 | rad/s | 0 | true |
| release.all_endpoint_states_carried | 0 | 0 | mixed SI state | 0 | true |
| release.gimbal_rate_continuity | 0 | 0 | rad/s | 0 | true |
| release.held_bounded_angles | 0 | 1.000e-08 | rad | 0 | true |
| release.held_bounded_speed | 0 | 0 | rad/s | 0 | true |
| release.initial_components | 0 | 0 | mixed SI state | 0 | true |
| release.initial_snapshot_unchanged | 0 | 0 | mixed SI state | 0 | true |
| release.piecewise_motor | 8.160e-08 | 1.000e-05 | rad/s | 8.160e-03 | true |
| release.predecessor_initial_not_replaced | 0 | 0 | mixed SI state | 0 | true |
| release.quaternion_norm | 2.046e-13 | 1.000e-09 | 1 | 2.046e-04 | true |
| release.rate_derivative_0_0 | 2.264e-09 | 2.000e-06 | rad/s^2 | 1.132e-03 | true |
| release.rate_derivative_0_1 | 5.429e-10 | 2.000e-06 | rad/s^2 | 2.714e-04 | true |
| release.rate_derivative_1_0 | 4.761e-10 | 2.000e-06 | rad/s^2 | 2.380e-04 | true |
| release.rate_derivative_1_1 | 1.402e-10 | 2.000e-06 | rad/s^2 | 7.011e-05 | true |
| release.rate_derivative_2_0 | 4.694e-11 | 2.000e-06 | rad/s^2 | 2.347e-05 | true |
| release.rate_derivative_2_1 | 2.920e-11 | 2.000e-06 | rad/s^2 | 1.460e-05 | true |
| release.refinement.actual_angles | 4.534e-10 | 1.000e-08 | rad | 4.534e-02 | true |
| release.refinement.filter_angles | 1.196e-09 | 1.000e-08 | rad | 1.196e-01 | true |
| release.refinement.motor_speed | 9.741e-08 | 1.000e-05 | rad/s | 9.741e-03 | true |
| release_refined.initial_components | 0 | 0 | mixed SI state | 0 | true |
| release_refined.initial_snapshot_unchanged | 0 | 0 | mixed SI state | 0 | true |
| release_refined.quaternion_norm | 3.120e-14 | 1.000e-09 | 1 | 3.120e-05 | true |
| saturated.actual_signed_rotor_speeds | 0 | 0 | rad/s | 0 | true |
| saturated.held_bounded_angles | 0 | 1.000e-08 | rad | 0 | true |
| saturated.held_bounded_speed | 0 | 0 | rad/s | 0 | true |
| saturated.initial_components | 0 | 0 | mixed SI state | 0 | true |
| saturated.initial_snapshot_unchanged | 0 | 0 | mixed SI state | 0 | true |
| saturated.piecewise_motor | 2.274e-13 | 1.000e-05 | rad/s | 2.274e-08 | true |
| saturated.quaternion_norm | 3.098e-14 | 1.000e-09 | 1 | 3.098e-05 | true |
| saturated.rate_derivative_0_0 | 2.269e-09 | 2.000e-06 | rad/s^2 | 1.135e-03 | true |
| saturated.rate_derivative_0_1 | 5.566e-10 | 2.000e-06 | rad/s^2 | 2.783e-04 | true |
| saturated.rate_derivative_1_0 | 4.736e-10 | 2.000e-06 | rad/s^2 | 2.368e-04 | true |
| saturated.rate_derivative_1_1 | 1.406e-10 | 2.000e-06 | rad/s^2 | 7.028e-05 | true |
| saturated.rate_derivative_2_0 | 4.177e-11 | 2.000e-06 | rad/s^2 | 2.088e-05 | true |
| saturated.rate_derivative_2_1 | 3.806e-11 | 2.000e-06 | rad/s^2 | 1.903e-05 | true |
| saturated.refinement.actual_angles | 9.733e-11 | 1.000e-08 | rad | 9.733e-03 | true |
| saturated.refinement.filter_angles | 2.517e-10 | 1.000e-08 | rad | 2.517e-02 | true |
| saturated.refinement.motor_speed | 4.547e-13 | 1.000e-05 | rad/s | 4.547e-08 | true |
| saturated_refined.initial_components | 0 | 0 | mixed SI state | 0 | true |
| saturated_refined.initial_snapshot_unchanged | 0 | 0 | mixed SI state | 0 | true |
| saturated_refined.quaternion_norm | 6.661e-16 | 1.000e-09 | 1 | 6.661e-07 | true |
| unlimited.actual_signed_rotor_speeds | 0 | 0 | rad/s | 0 | true |
| unlimited.analytic_gimbal_acceleration | 5.898e-16 | 2.000e-06 | rad/s^2 | 2.949e-10 | true |
| unlimited.analytic_gimbal_rate | 8.674e-17 | 5.000e-08 | rad/s | 1.735e-09 | true |
| unlimited.cascaded_actual_angle | 2.082e-17 | 1.000e-08 | rad | 2.082e-09 | true |
| unlimited.exponential_filter | 1.388e-17 | 1.000e-08 | rad | 1.388e-09 | true |
| unlimited.exponential_motor | 5.684e-14 | 1.000e-05 | rad/s | 5.684e-09 | true |
| unlimited.held_bounded_angles | 0 | 1.000e-08 | rad | 0 | true |
| unlimited.held_bounded_speed | 0 | 0 | rad/s | 0 | true |
| unlimited.initial_components | 0 | 0 | mixed SI state | 0 | true |
| unlimited.initial_snapshot_unchanged | 0 | 0 | mixed SI state | 0 | true |
| unlimited.quaternion_norm | 2.220e-16 | 1.000e-09 | 1 | 2.220e-07 | true |
| unlimited.rate_derivative_0_0 | 3.067e-10 | 2.000e-06 | rad/s^2 | 1.533e-04 | true |
| unlimited.rate_derivative_0_1 | 7.633e-11 | 2.000e-06 | rad/s^2 | 3.816e-05 | true |
| unlimited.rate_derivative_1_0 | 6.310e-11 | 2.000e-06 | rad/s^2 | 3.155e-05 | true |
| unlimited.rate_derivative_1_1 | 2.043e-11 | 2.000e-06 | rad/s^2 | 1.021e-05 | true |
| unlimited.rate_derivative_2_0 | 3.437e-12 | 2.000e-06 | rad/s^2 | 1.719e-06 | true |
| unlimited.rate_derivative_2_1 | 4.582e-12 | 2.000e-06 | rad/s^2 | 2.291e-06 | true |
| unlimited.refinement.actual_angles | 2.082e-17 | 1.000e-08 | rad | 2.082e-09 | true |
| unlimited.refinement.filter_angles | 1.388e-17 | 1.000e-08 | rad | 1.388e-09 | true |
| unlimited.refinement.motor_speed | 8.527e-14 | 1.000e-05 | rad/s | 8.527e-09 | true |
| unlimited_refined.initial_components | 0 | 0 | mixed SI state | 0 | true |
| unlimited_refined.initial_snapshot_unchanged | 0 | 0 | mixed SI state | 0 | true |
| unlimited_refined.quaternion_norm | 3.331e-16 | 1.000e-09 | 1 | 3.331e-07 | true |

## Interpretation limits

- Oracles are those labelled by each checker: closed-form analytical expectations, finite differences, refinement or alternate-method agreement. Numerical agreement is not independent physical validation.
- Limits observed at output samples and dense midpoints are not continuous certification.
- Fixture masses, geometry, paired-map coefficients, actuator parameters and tolerances are synthetic; none is a selected vehicle input.
- Re-run outcomes neither replace nor upgrade the registered inconclusive evidence; null checks remain unperformed.
- No PID tuning, vehicle mission, electrical/thermal, structural, physical or PDR/CDR acceptance follows from these logs.
