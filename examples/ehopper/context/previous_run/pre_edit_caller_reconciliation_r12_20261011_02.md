# PDR r12 plant: pre-edit caller reconciliation addendum

Date: 2026-10-11.
Task: pdr_r12_preliminary_plant.
Validated authorization: 66c7448f443f44ac9a016a1b384593a2 revision 1.

This addendum preserves and supplements PDR-R12-PLANT-PRE-EDIT-AUDIT-01 revision 1; it does not replace that checkpoint or erase its evidence limitations. It records additional source inspection before creating the separate r12 implementation. Supplied checkouts and historical outputs remain unchanged by this documentation action.

## 1. Evidence levels

- Source availability: original plant implementations and the recovered r9 implementations described below have been returned by current readers.
- Static caller discovery: affected_caller_index_r12_01.md covers the inventoried original_hopper, pendulum_reference and historical_r9 roots. It is a candidate index, not a complete runtime call graph.
- Actual dependency capability: execution ea20703027944ce9879c37648f332163 used repository-selected CPython 3.13.11 and imported NumPy 2.5.2, SciPy 1.18.0, scipy.integrate and pytest 9.1.1. Other reported distribution versions are metadata observations only.
- Reproduced original failure: importing simulation.simulation raised ModuleNotFoundError: No module named 'state', without an import workaround. This corroborates R12-RC01; it is not a missing NumPy/SciPy installation.
- Other original defects: the checkpoint's remaining findings are source-inspection findings, not reproduced exceptions or integration results.
- Repaired execution and analytical verification: not yet established. Neither the historical code nor the source index constitutes a test pass.
- Vehicle physical validity, mission acceptance and PDR/CDR acceptance: not established.

The capability diagnostic returned exit code zero because it wrote observations, including the failed import. It observed no changes in the 68 inventoried files before/after imports. That preservation statement excludes unlisted files, new files, environments and binary/data files.

Capability references: PDR-R12-PLANT-CAPABILITY-REPORT-01 r1; execution ea20703027944ce9879c37648f332163 r1. Logs: logs/5fd6bdc9d4c448cbaa3d0b78a9743caa/stdout.txt and stderr.txt.

## 2. Original-source caller map retained

The original implementations are preserved, not patched in place.

| Affected interface | Inspected caller and consequence |
|---|---|
| State construction, numeric decoding and update_state | Simulation.solve_ode constructs State; Simulation.trajectory_ode incorrectly treats its numerical argument as an object and calls update_state with the wrong signature. Replace this path coherently, retaining all initial components and removing RHS history mutation. |
| Euler conversion | Simulation.solve_ode calls euler_to_quaternion with three positional arguments although the helper accepts a vector and optional degrees flag. Migrate helper and caller together to named radian arguments. |
| DCM conversion | Simulation.trajectory_ode calls the misspelled helper. Its uninitialized local variable is a defect; the original matrix direction is a convention, not itself a defect. |
| Mass, CG and inertia | Simulation.trajectory_ode calls Hopper.mass, CG and inertia separately. Hopper.mass calls propulsion.get_mass. Replace with one complete-vehicle snapshot, avoiding propulsion mass double-counting. |
| Propulsion wrench | Simulation.trajectory_ode calls Hopper.get_thrust_and_moment, which forwards to the propulsion provider. Replace the ambiguous time-only forwarding with actual actuator-state loads and explicit application points. |
| Aerodynamics | Simulation.trajectory_ode calls Aerodynamics.determine_at_point. The inspected cylinder model is not adopted as the exposed-structure model; any replacement nonpropulsive loads require explicit provenance and reference points. |
| Solver boundary | Simulation.solve_ode passes trajectory_ode to solve_ivp but discards the result. Preserve the actual result and failure/event semantics in the replacement. |

The inspected main.py only prints a greeting; scripts/ehopper.py is empty. The inspected test/test_pythrust.py supplies separate prescribed-RPM/equilibrium-voltage examples, not an integrated hopper entry point or calibrated dynamic coaxial model.

Original source references are retained in PDR-R12-PLANT-PRE-EDIT-AUDIT-01 r1. Source line locations in the fresh index include Simulation.trajectory_ode calls at lines 17, 37, 91–105; Simulation.solve_ode calls at lines 134, 142 and 144–153; Hopper forwarding at lines 46 and 58.

## 3. Recovered implementation and concrete caller inspection

The recovered r9 core modules inspected are helpers/math.py, simulation/state.py, chassis/hopper.py, propulsion/propulsion.py, propulsion/propeller.py, propulsion/actuators.py and simulation/simulation.py, including the latter two files' continuation excerpts. The additional environment and fixture-provider inspections close the corresponding content gaps identified in checkpoint section 6.

| Recovered path | Actual inspected call chain and r12 migration obligation |
|---|---|
| simulation/environment.py | Simulation.evaluate calls EnvironmentProvider.sample with actual hub locations. EnvironmentSample.coaxial_conditions builds paired operating conditions. Preserve location echoes, explicit ambient wind, auxiliary-load accounting and pure evaluation. |
| analytical_fixture_models_01.py: initial_snapshots | Calls State.from_euler and ActuatorState with every configured initial component. Update imports/schema references to the new r12 copy; do not silently reset actuator states. |
| analytical_fixture_models_01.py: build_fixture | Constructs MassProperties, FrozenFixtureMass, Hopper, CoaxialGeometry, SyntheticPairedMap, Propellor, LagParameters, LaggedActuators, PrescribedFixtureEnvironment and Simulation. Geometry constructor and configuration must migrate together. |
| FrozenFixtureMass.snapshot | Called by Hopper.mass_properties. Returns an explicitly rigid analytical snapshot; it must not claim articulated-vehicle dynamics. |
| PrescribedFixtureEnvironment.from_config/sample | Constructs AppliedLoad and EnvironmentSample, then substitutes requested hub positions. Prescribed voltage, SOC and temperatures are not battery/thermal closure. |
| SyntheticPairedMap.evaluate | Called by Propellor.evaluate; evaluates both actual rotor speeds together and returns CoaxialPerformance. Its invented cross-interference functions are fixtures, not vendor data or calibration. |
| solver_options | Returns numerical solve_ode settings; this does not select a PID cadence. |
| CoaxialGeometry.application_points_B0_m | Called by Propellor.evaluate, hub_velocities_relative_air_M_m_s and Simulation.evaluate. All three must use the same separated-origin geometry. |
| Propellor.hub_velocities_relative_air_M_m_s | Called by Simulation.evaluate before constructing paired conditions. Add the outer-to-inner translation derivative consistently; do not substitute commanded angles. |
| Simulation.solve_ode | Captures one held command and calls its pure numerical RHS. The returned OdeResult includes raw samples, event information and failure status. Later checker/runner callers must inspect these rather than infer success from process exit. |

Current reader references: index f16d212c6cc74c81b5332e6dd1081fa2 r1 and bf037bd74a09497ba0bf5313facbc852 r1; fixture providers 51af21da198e41a2a3fd13f4dde8837a r1 and c1f75c35f5814e3a924278437e1861dc r1; environment 2b75af1479394623b11026be2eec2f9a r1; fixture configuration 478a30e6f2c54f1eaaea96c186ea9c46 r1. Core-module reader references remain listed in the published checkpoint.

The recovered directory listing contains source/configuration and audit/capability files but does not establish an existing analytical checker or numerical verification result. New editable checker programs and measured results remain required.

## 4. Specific reconciliation changes before testing

### Separated joint origins

Retain decision 28e10be57d6548a3aa5be06c96f6d0d0 r1:

r_B0i = r_B0Ox + Rx(alpha) d_OxOy + Rx(alpha) Ry(beta) r_Oyi_M.

The derivative in body components is the sum of:

- alpha_dot e_x cross [Rx(alpha) d_OxOy];
- omega_MB,B cross [Rx(alpha) Ry(beta) r_Oyi_M], where omega_MB,B = [alpha_dot, cos(alpha) beta_dot, sin(alpha) beta_dot].

The historical single-pivot implementation explicitly assumes coincident origins. Generalize the geometry interface and its inspected callers; do not reinterpret an old field silently. Test separated origins with nonzero angles and rates using independent finite-difference kinematic expectations.

### Historical configuration is not the bottom-propulsion baseline

The inspected r9 fixture stores pivot_B0_m=[0,0,-0.30] m. With zero fixture CG and FRD axes, that point is above the CG, not a bottom-pivot fixture. This is an unsuitable inherited test geometry for the required bottom-pivot sign check, not evidence of an executed failure.

Create an explicitly labelled positive-down bottom-pivot fixture and a separate noncoincident-origin fixture. Historical mass, inertia, travel, response constants and geometry are never promoted to selected vehicle inputs. Numerical fixture values may be reused only with explicit synthetic provenance and a stated analytical purpose.

### Whole-vehicle momentum and scoring

Preserve full inertia and the interface:

I omega_dot = M_ext - omega cross (I omega + h_rel) - I_dot omega - h_rel_dot.

External rotor free couples are air-on-rotor torques R_BM[0,0,-sigma_i Q_i]. Internal motor/servo reactions are not additional external moments. A frozen rigid fixture deliberately neglects moving-mass and relative-momentum effects; a reduced articulated vehicle model would need a separately documented approximation and error assessment.

Translation remains at instantaneous complete-vehicle CG. Fixed-datum reporting must retain both CG offset and its body-component derivative:

p_O = p_G - R_LB r_B0G;
v_O = v_G - R_LB(omega cross r_B0G + r_dot_B0G).

## 5. Bounded audit scope and next implementation gate

The listed original functions and concrete recovered plant/fixture callers have been inspected. Generic solve_ivp calls elsewhere in PyThrust or the pendulum reference are not, merely by sharing that library name, callers of the replacement hopper interfaces. Neither source environment will be modified or used as an implicit integration layer.

The static index remains scope-limited: dynamic dispatch, wildcard imports, rebinding, symlinks, generated code and callers outside the inventoried roots are not globally excluded. No universal caller-completeness claim is made. Any newly introduced r12 runner/checker is an additional caller and must use the explicit new schemas and be retained for review.

Next: write the separate r12 repaired implementation and labelled fixture configuration under software/pdr_r12_plant, preserving historical files. Record the migration map and reproducible entry point, then perform artifact-bound analytical verification. Required checks include ownership/initialization, quaternion/DCM identities, gravity/thrust/moment signs, full-inertia balance, separated-origin hub kinematics, bottom-pivot effectiveness, differential aerodynamic torque, motor/gimbal response and limits, RHS purity, solver returns/events/failures and fixed-datum conversion. Retain failed/inconclusive outcomes and measured errors.

Vehicle inputs still required from the Chief include complete installed mass and articulated mass-property ownership; outer/inner origins and hub/foot coordinates; actual rotor spin assignments with viewing directions; coupled propulsion maps and calibration domains; loaded motor/ESC/servo response and limits; electrical/thermal closure; and exposed-structure/contact modelling assumptions.

PID remains architecture-only: fixed-time controller updates outside adaptive RHS evaluations, held commands, explicit state carry-forward, constrained allocation, anti-windup and filtered derivative feedback. No gains are tuned and no vehicle closed-loop mission acceptance is performed under this preliminary task.
