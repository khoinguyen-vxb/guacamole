# PDR plant: current pre-edit root causes and caller reconciliation

Task: pdr_plant_repair. Checkpoint M4-03.

## 1. Authority and evidence boundary

Current authority is system_model:system revision 4, work-plan decision 99f7bb629eef45b89fa38d27c803868c revision 1, and interface decision 88561ff8b3ba4e8286cebd95a93e3b08 revision 1, selecting INTERFACE-NED-CG-FIXED-PLATE. Earlier model/plan numbers in task descriptions, source headers and archived reports are historical, not current authority. The recovery notification 0d3d9cf96bf24187a6541d90d5a82b27 revision 1 confirms this reconciliation.

The brief and context/previous_run/README.md were reviewed. Archived audits and repaired_hopper_r12 are reuse leads, not proof of execution, calibration or acceptance. Their former CDR gating does not govern this run: current PDR includes dependent PID integration and mission simulation, after this foundational plant task.

This document records reviewed source findings BEFORE creating the new repaired implementation. It changes no original or recovered implementation. No current dependency import, original exception reproduction, repaired trajectory or analytical VerificationResult is claimed here. The source-auditor execution is a separate capability observation: it ran a standard-library inventory program, not the plant or NumPy/SciPy numerical path.

## 2. Inspected scope and source preservation

Current reader results expose the original Simulation, State, math helpers, Hopper, Propulsion ABC and Propellor. The generated remaining-source excerpts additionally expose the complete original main.py, aero/aero.py, helpers/constants.py, empty scripts/ehopper.py, test/__init__.py and test/test_pythrust.py. All eight recovered core modules have been returned and reviewed, including continuation excerpts for simulation.py, propulsion.py, propeller.py and actuators.py.

PDR-PLANT-CALLER-INDEX-M4-02 revision 1 records the discovered call spellings and locations. Its relevant concrete callers are reconciled below. It is a bounded static index, not a universal runtime call graph. Aliases, rebinding, dynamic dispatch, generated code, excluded directories and callers outside the scanned roots remain discovery limitations.

Execution 99ca6249bcb947b9899dc8ee0237f101 revision 1 inventoried 8,873 regular files. PDR-PLANT-PRESERVATION-DELTA-M4-02 revision 1 reports no changed, added or missing files relative to source_inventory_01.json within that inventory scope. This is a content-comparison diagnostic, not registered source-preservation verification or proof of original checkout cleanliness. Excluded environments, caches, Git metadata and un-followed symlinks are outside that comparison. The auditor ran with python -B and did not import target modules.

The inspected recovered root contains the eight core Python implementations. Historical documentation names fixture configurations, builders, checkers and logs that have not been recovered in that root by the current scan. Their historical results cannot be reused as current executable evidence. New fixture providers and retained checkers are required unless those missing files are separately supplied and inspected.

## 3. Original root causes: source findings, not reproduced exceptions

Line locators below refer to original files as indexed by PDR-PLANT-CALLER-INDEX-M4-02.

| ID | Finding and root cause | Required coordinated repair |
|---|---|---|
| RC-01 | simulation/simulation.py L4 imports State from top-level state, while the implementation is simulation/state.py. | Establish explicit package imports and test import resolution without an undocumented sys.modules workaround. |
| RC-02 | Simulation.__init__ accepts state but assigns self.state=None. | Preserve owned authoritative initialization; test nonzero position, velocity, attitude and rates. |
| RC-03 | Simulation.trajectory_ode accesses undefined self.time before using the solver's time argument. | Use supplied time explicitly; no previous-call time or implicit state progression. |
| RC-04 | trajectory_ode L17 passes one vector to State.update_state, whose signature requires thirteen scalar arguments. | Decode the numerical vector through a versioned schema rather than repairing only the call signature. |
| RC-05 | trajectory_ode L22-L27 accesses State-like attributes on the numeric array passed by solve_ivp. | Separate immutable snapshots from numerical RHS vectors and return a correctly ordered numeric derivative. |
| RC-06 | helpers/math.py L13 reads local quaternions before assignment; the actual parameter is named quarternion. | Correct the variable defect and retain explicit validation and matrix-direction tests. |
| RC-07 | Simulation.solve_ode L134 supplies three positional Euler arguments, but the original helper accepts an angle vector and optional degrees flag. | Migrate helper and callers together to named radian arguments. |
| RC-08 | Original Euler documentation says roll/pitch/yaw, but unpacking assigns psi/theta/phi; degrees default to true. | Remove ordering/unit ambiguity and test isolated axes plus noncommuting rotations. |
| RC-09 | solve_ode L135-L142 constructs zero position, velocity and rates rather than using the constructor state. | Carry all initialization and actuator states explicitly, without hidden resets. |
| RC-10 | solve_ode L144-L153 obtains solution but does not return it. | Return the actual OdeResult, including unsuccessful status, events, raw samples and dense output. |
| RC-11 | State.update_state L32-L44 appends history, and trajectory_ode attempts to invoke it during adaptive RHS evaluation. | Remove trial-call history mutation. Accepted trajectory logging and controller memory belong outside the RHS. |
| RC-12 | Propellor implements none of the Propulsion abstract methods; its constructor retains only type and discards supplied electrical parameters. | Supply a concrete adapter with explicit paired performance and actual actuator states. Do not claim that source availability establishes an instantiable propulsion implementation. |
| RC-13 | Original Hopper.__post_init__ uses np.asarray without owning copies for caller-supplied floating arrays. | The replacement snapshot contract must prevent later caller mutation from silently changing mass/geometry data. Reproduce alias behavior separately before claiming an executed failure. |
| RC-14 | Aerodynamics.determine_at_point L98-L104 normalizes np.asarray(tube_axis_body) in place. A compatible caller-owned floating array can therefore be changed. | If this model is ever reused, use an owned input and add a purity fixture. It is not imported into the analytical replacement by default. |

Additional original interface limitations:

- Propulsion abstract method signatures omit explicit self parameters. ABC abstractness does not validate implementation signatures. Redesign the interface and test concrete calls rather than treating ABC membership as compatibility.
- Hopper.mass L46 adds mass_wo_propellant and propulsion.get_mass. The meaning of the first term is not a complete installed ledger. Adding propulsion mass is not inherently wrong, but adding it to an already complete vehicle total would double-count it.
- Hopper.CG and inertia return fixed CG and diagonal inertia. These can describe a restricted rigid/principal-axis model; they do not establish the articulated vehicle's full inertia or internal momentum.
- Hopper.get_thrust_and_moment L58 forwards a time-only wrench without documenting its reference point. Its unused moment_arm does not alone prove a missing cross product: the provider could already return a shifted moment. The replacement must remove this ambiguity and resolve each load once.
- Original Aerodynamics explicitly returns a moment about CG. A future adapter must not shift that moment a second time. The cylinder model's +x longitudinal assumptions do not establish suitability for the exposed hopper structure.
- Aerodynamics L108-L109 returns zero loads at zero translational airspeed before its rotational damping calculation. This suppresses the later damping contribution for pure rotation. It is a source-observed model limitation requiring a dedicated test if retained, not a validated physical model for this project.
- helpers/constants.py supplies GRAVITY=9.8065 m/s^2. This is a source value, not a selected atmosphere/gravity requirement or calibration result.

## 4. Convention migrations are not defects

The original DCM algebra, after correcting RC-06, maps local components into body components. That direction is not intrinsically wrong. The current contract instead names R_LB as body into local, with its transpose used explicitly when required.

The original scalar-first quaternion-rate matrix is consistent with Hamilton right multiplication by [0,omega_B]. Re-expression using a Hamilton helper is not evidence that the original rate algebra was wrong.

The original -omega cross velocity term is appropriate for body-resolved velocity. The current state carries instantaneous complete-vehicle CG velocity in local NED, so its acceleration is R_LB F_B/m+[0,0,g] without that transport term. This requires a schema migration, not an isolated sign change.

The original norm-feedback correction and locally normalized rotation calculation are distinct from raw-state reporting. The replacement must preserve raw integrated quaternion samples; any decision to omit norm feedback is documented numerical policy and checked for drift, not disguised as a correction to an inherently invalid quaternion convention.

## 5. Every discovered concrete affected caller

| Affected interface | Reviewed callers and disposition |
|---|---|
| Original State construction/update | Simulation.solve_ode L142 and trajectory_ode L17. Replace coherently; remove RHS mutation rather than adapting history collection to trial stages. |
| Original Euler/DCM helpers | Simulation.solve_ode L134 and trajectory_ode L37. Migrate their argument units/order and rotation direction together. |
| Original mass and wrench | Simulation.trajectory_ode L91-L98; Hopper.mass L46; Hopper.get_thrust_and_moment L58. Replace separate time-only calls with one consistent mass/momentum snapshot and point-load resolution. |
| Original aerodynamic evaluation | Simulation.trajectory_ode L98-L105. The cylindrical model is not silently retained; future external loads need explicit origins, assumptions and provenance. |
| Recovered State math and serialization | State.from_euler, from_body_velocity, velocity_G_B_m_s, as_vector, unpack_state and with_normalized_orientation; pack_state/unpack_state; Simulation.initial_vector/evaluate. Preserve ownership and raw quaternion values; reject ambiguous old schemas. |
| Recovered CAD and fixed-datum helpers | cad_point_to_body_datum_m, body_datum_point_to_cad_mm and fixed_datum_kinematics. No separate recovered external caller was found in the current index. New fixtures will be explicit additional callers. Migrate neutral-CG semantics to the selected fixed plate datum. |
| Recovered geometry | CoaxialGeometry.joint_origins_B0_m and application_points_B0_m; application_point_rates_B0_m_s; Propellor.evaluate and hub_velocities_relative_air_M_m_s; Simulation.evaluate. Preserve the separate outer-offset and module-offset derivatives. |
| Recovered actuator response | LagParameters.bound_command/validate_state/effective_gimbal_rate_rad_s; LaggedActuators.evaluate; Simulation construction/evaluation. Preserve actual states, derivative consistency, immutable held commands and analytical-only limits. |
| Recovered whole-vehicle mass/momentum | Hopper.mass_properties calls the provider's snapshot; Simulation.evaluate calls it once and uses the returned mass for loads and angular acceleration. MassProperties.angular_acceleration_B_rad_s2 calls angular_momentum_B_kg_m2_s. New providers must implement this contract without hidden mutable state. |
| Recovered external-load resolution | PropulsionEvaluation.wrench_about_cg and Simulation.evaluate call resolve_applied_loads; that function calls mass_properties.moment_arm_m. Moments already resolved about G must not be shifted again. |
| Recovered paired propulsion | Simulation.evaluate calls Propellor.evaluate; Propellor invokes performance_map.evaluate once for both actual rotors and creates the two AppliedLoads. Geometry and conditions must agree on spacing and scope. |
| Recovered environment/electrical arithmetic | Simulation.evaluate requests EnvironmentProvider.sample at actual hub locations; EnvironmentSample.coaxial_conditions builds paired conditions. PlantEvaluation total-current/power accessors use EnvironmentSample arithmetic. Auxiliary current is counted once, but these calls do not close sag or thermal dynamics. |
| Recovered solver | solve_ode captures a held command, calls trajectory_ode through held_rhs and returns solve_ivp's result. No recovered scheduler/checker caller is present in the inspected root. New tests must inspect endpoints/events/failures and explicitly carry every state. |

Original main.py only prints a greeting. scripts/ehopper.py is empty. test/test_pythrust.py is an isolated prescribed-RPM/equilibrium-voltage example, not a caller of the repaired plant. It performs PyThrust imports and database loading at module import; it must not be used as a harmless capability probe without inspecting its PyThrust callees and data handling. Its embedded motor and electrical numbers are example inputs, not selected vehicle data. PyThrust and pendulum calls to a similarly named numerical library are not automatically callers of the changed hopper interfaces. No Gazebo, ROS, MPC or machine-learning work is introduced.

## 6. Recovered implementation applicability and required changes

Reusable inspected mechanisms include immutable rigid-body and actuator snapshots, owned serialization, package-relative imports, named Euler radians, explicit quaternion direction, full-inertia algebra, separated gimbal origins, external aerodynamic torque signs, paired-map contracts, pure held-command RHS structure and actual solver-result return. They remain unverified in this run.

### Required datum migration

Recovered helpers/math.py explicitly defines O_B0 at the neutral complete-vehicle CG and names the CAD-origin argument neutral_cg_C_mm. Recovered chassis/hopper.py repeats that datum definition; other modules use B0 field names and Simulation metadata reports O_B0. Current authority instead defines D at the fixed leg-attachment plate/ring reference plane. This is a genuine contract mismatch, not permission to move the scoring datum with the CG.

The new copy must use an explicit fixed D_C and coherent datum-relative names/schemas throughout mass properties, geometry, applied loads, hub velocity and scoring. Convert r_B=0.001*diag(1,-1,-1)*(p_C-D_C), with CAD lengths in mm and plant lengths in m. An old field named neutral_cg_C_mm must not silently acquire a different meaning. New tests must use a nonzero D_C distinct from neutral and articulated CG positions.

For r_DG and its B-component derivative, preserve p_D=p_G-R_LB*r_DG and v_D=v_G-R_LB*(omega_B cross r_DG+rdot_DG). The recovered helper provides position and velocity only. Any acceleration helper requires explicit consistent rddot_DG and independent tests; no absent derivative is filled with zero for vehicle use.

### Preserve separated-origin and load semantics

The recovered r12 geometry already implements r_Di=r_DOx+Rx(alpha)*d_OxOy+R_BM*r_Oyi,M. Its point-rate method rotates d_OxOy using outer-axis motion only. Do not repeat the archived r9 single-pivot repair as though it were still missing from recovered r12. Test the actual reused implementation with noncoincident origins, noncommuting angles and independent finite differences.

Retain F_i=R_BM*[0,0,-T_i] and aerodynamic couple R_BM*[0,0,-sigma_i*Q_i], resolved once about G. Counter-rotation alone proves neither aerodynamic torque balance nor cancellation of internal spin momentum.

### Keep analytical-only guards and uncertainty

Simulation, LagParameters and ActuatorEvaluation explicitly restrict the runnable path to analytical fixtures. MODEL_SCOPES accepting provisional_vehicle in some data records does not authorize a vehicle Simulation. No guard is removed by this checkpoint.

The recovered lag model is a speed-demand abstraction, not a demonstrated ESC protocol or loaded motor controller. Its gimbal cascade prescribes motion and does not solve servo torque, linkage, friction, backlash or mechanical contact. Its common-progress construction and acceleration bounds require numerical regression, not a claim of real actuator capability.

The mass interface evaluates I*omegadot=M_ext-omega cross(I*omega+h_rel)-I_dot*omega-h_rel_dot for supplied terms. It does not derive a multibody provider or solve acceleration-dependent internal coupling. Current authority selects no rigid or reduced-articulated vehicle approximation. Synthetic rigid and prescribed-momentum fixtures must remain explicitly synthetic.

The paired-map interface distinguishes winding current from battery-branch current and retains tri-state domain flags. Prescribed voltage, SOC and temperatures are not battery/thermal closure. No measured coaxial map, realizable command mapping or calibrated electrical transient is supplied by these interfaces. Known violations must not be clipped into feasibility; unsupported quantities remain explicit.

## 7. Next execution and verification gates

1. Publish this checkpoint before implementation edits. Preserve all supplied checkouts, previous_run files and earlier generated outputs.
2. Write an editable capability/reproduction probe under software/pdr_plant/. Use repository='6dof_hopper', a sandbox workdir, python -B and no installation. Record interpreter and actual NumPy/SciPy imports separately from distribution metadata. Test original import and practical isolated defects without concealing an import workaround; any instrumented/in-memory isolation must be labelled.
3. Check source contents before/after probing and retain exceptions and diagnostics. Request missing installations through the Chief; do not modify supplied environments.
4. Create a separate runnable package with current authority/migration notes and explicit schemas. Reconcile the fixed-D contract across all reviewed callers. Preserve analytical-only restrictions and do not transplant archived numerical vehicle geometry.
5. Supply clearly labelled synthetic configurations/providers and independent editable checks. Required cases cover nonzero initialization and ownership, serialization, quaternion/DCM and noncommuting rotations, CAD/SI inertia conversions, full momentum balance, fixed-datum position/velocity/acceleration where implemented, separated-origin positions/rates, wrench shifts, differential torque, gravity/thrust signs, motor/gimbal lag and limits, RHS purity, actual solver returns, event endpoints, failure retention and all-state carry-forward.
6. Numerical regression thresholds are test settings, not newly agreed mission tolerances. Verification programs read actual artifacts, emit only VerificationResult JSON on stdout and diagnostics on stderr. Include every tested artifact Ref in tool inputs. Unperformed physical checks are null; passed means every performed check passed, not vehicle or hardware validation.
7. Hand off exact current interfaces, measured errors and remaining limitations to the Chief, CAD, propulsion and later PID worker. Vehicle mass, moving-group properties, physical spin assignments, paired maps, hardware commands, contact parameters, reserve/disturbance criteria and mission solver tolerances remain unresolved unless separately dispositioned.

## 8. Source locators

All references below are revision 1 unless stated otherwise; exact hashes are retained in this write's tool inputs and subsequent publication provenance.

- Current authority: system_model:system r4; decision:99f7bb629eef45b89fa38d27c803868c; decision:88561ff8b3ba4e8286cebd95a93e3b08.
- Original Simulation: tool_result:a6183d153c3e40afa9dd736a087de35f, __init__, trajectory_ode and solve_ode.
- Original math: tool_result:d9430392dbb4497cbafc55490683ccab, both conversion functions.
- Original State: tool_result:11d43b218a1a4e45a97e5ab5b98c732d, constructor/update_state/unpack_state.
- Original Hopper: tool_result:67e6f891708441739ccda5317645c7c4, __post_init__, mass, CG, inertia and wrench forwarding.
- Original propulsion: tool_result:16eb988b4df8449f8ee5378fa4771824 and tool_result:9e9d982de14b4b1d8827be963043af8a, full short modules.
- Additional original files and entry points: artifact:PDR-PLANT-REMAINING-SOURCE-EXCERPTS-M4-02, per-file sections.
- Caller locations: artifact:PDR-PLANT-CALLER-INDEX-M4-02, per-module sections.
- Preservation observations: artifact:PDR-PLANT-PRESERVATION-DELTA-M4-02 and execution tool_result:99ca6249bcb947b9899dc8ee0237f101.
- Recovered math/State/mass: tool_result:3454de3d6a8e4700b26a6c0d8aecab94, ee803fd946d84d7c816823a019162a2d and 99365b17b90a451da677300181a6ccff.
- Recovered propulsion contracts: tool_result:cd3a005342e847059d4fe7e77d2e3724 with continuation 9e6a1de78e094f19b3fc5998e653b42d.
- Recovered geometry: tool_result:cbe5b1328044469b80c68b1b4b65fbd4 with continuation ba4768478977405687a776a5ff33aa07.
- Recovered actuators: tool_result:2fd97b859b034defac40f0d2ef228f08 with continuation a29ca297cf274294932c91cc584486ad.
- Recovered environment: tool_result:700a217ae8824ecfbce400804e5dbbec.
- Recovered Simulation: tool_result:1af88f1ce8904313aad614cd362ae0ab with continuation e387022758704935b4fa58a1e55df093.

No requirement satisfaction, vehicle down-selection, physical verification or PDR acceptance is established by this report.
