# PDR r5 — 6DOF plant root-cause audit

## Status and scope

Pre-repair audit under work-plan decision af32106a18c540cb8586a4adf40ca04c r1, deliverable D-PDR5-SIMULATOR-PLANT. This revision records defects and intended checks before modifying the initial copy. **Repairs and plant verification are pending.** No PID tuning, mission simulation, procurement acceptance or hardware validation is claimed.

Supplied checkout: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper` (read-only, including PyThrust). Modification destination: `software/r5/6dof_hopper_r5`. All worker-authored outputs belong beneath `software/r5/`; every Python process must use `-B`.

The original brief's rocket-shaped description is superseded by REQ-VEHICLE-CONFIGURATION r1: only the exposed functional central structure, equipment and landing legs are in scope. The pendulum reference does not supply an integrated hopper controller and adds no ROS, Gazebo, MPC or machine-learning work.

## Evidence already obtained

- Starting audit: `software/chief_6dof_root_cause_audit.md`, read through tool_result aabba078954d47b6882b715fe889696b r1. Its references to the old actuator decision and repair timing are superseded by the current r5 decisions.
- Baseline: `software/r5/supplied_hashes_before.json`, SHA-256 `ab5d979836a7bd447c213d3c60f38d5475d674c9a5cbcfdfa862de677a3dc317`; execute ac2289dc3c114b50ab7c0938abf8c0d6 r1 reported 8,847 files, eight excluded entries, no symlinks, return code 0 and empty stderr. This proves the hashing process ran, not that the plant works.
- Copy: `software/r5/copy_manifest_initial.json`, SHA-256 `1f240a4627c8208e6cd0b4dc6b69a8974e8f8d4cc78fdd5bf761afc58ee828f9`; execute 6fd8cfcba46444ea9c997f4bc8873926 r1 reported 17 copied files matching the baseline, return code 0 and empty stderr. PyThrust, caches and dot-directories were excluded from copying. Dot-files such as `.gitmodules` and `.python-version` were retained.
- Editable scanner: `software/r5/tools/ast_scan.py`, SHA-256 `d3a0c576366587c7ab9d401737ed1e0e924125a35a125aeeaeba451376e1eaea`.
- Initial caller inventory: `software/r5/caller_scan_before.json`, SHA-256 `fb75d04a072dd2d75806a3de12fe9196e42f0da1136031c2ba747e12ee6842f2`; execute 4b5a176131ce41c680744f7c4c005cd8 r1 scanned 46 supplied Python files including PyThrust and 12 copied Python files, with no reported parse/coverage errors.
- Caller-summary execute e64bd1ba35ff41de96628f6a001b618b r1 reported matching initial-copy/supplied plant Python hashes and matching caller candidates. Its stdout is a review aid, not VerificationResult evidence.

The baseline starts after backend interpreter initialization. It cannot establish that initialization made no earlier changes. Excluded-directory metadata is recorded, but excluded contents are not hashed. Final comparison must report added/removed/changed source files, lock files, symlinks and excluded-entry metadata rather than silently broadening exclusions. No final preservation comparison exists yet.

Repository presence, availability of this Python interpreter, importability of dependencies, successful plant integration and physical validity are separate claims. The completed standard-library scripts establish neither NumPy/SciPy availability nor plant correctness.

## Source review and caller coverage

The following full source excerpts were reviewed in the supplied context; locations below use Python file/function names rather than document page numbers:

| Source | Read tool_result r1 |
|---|---|
| `simulation/simulation.py` | eda44d599b3c472ba985c4f579cbd909 |
| `simulation/state.py` | 7990c07cefb34a87954bee8947a7bbbb |
| `helpers/math.py` | 9b109a76a3d24595898446d01abe6eda |
| `helpers/constants.py` | cd0d4ce8705644998226fd674dfcabe8 |
| `chassis/hopper.py` | 14e30e1ebe2d4de4b1803248e2bfa0e3 |
| `aero/aero.py` | b913670059ca4776ab422b0c47a70b87 |
| `propulsion/propulsion.py` | a5a521c6952b43ffb1e4e62e31425e91 |
| `propulsion/propeller.py` | 5dc6e2c512ba41d6aac9eb2df685da89 |
| `main.py` | ed76246a4e164496ab349ba3dedb6b64 |
| `scripts/ehopper.py` | c70dadfd36a84f4298a96d51d885d175 |
| `test/test_pythrust.py` | 0389bcc64b1547ec8238faea6c8b5f07 |

Backend declaration: supplied `pyproject.toml`, source b9013a7e55694253808f17532838c85e r1, declares Python >=3.13 and dependencies including NumPy and SciPy. A dependency declaration is not an import test.

### Complete affected-symbol caller list reported by the initial scan

Line numbers are from the supplied source and its byte-identical initial copy.

| Affected symbol | Reviewed callers/references |
|---|---|
| `Simulation` / constructor | No construction call identified in scanned trees. |
| `Simulation.trajectory_ode` | `Simulation.solve_ode`, callback reference at `simulation/simulation.py:145`. |
| `Simulation.solve_ode` | No call identified. |
| `State` | `Simulation.__init__` annotation at line 9; `Simulation.solve_ode` construction at line 142. |
| `State.update_state` | `Simulation.trajectory_ode` at line 17. |
| `State.unpack_state` | No call identified. |
| `quarternion_to_dcm` | `Simulation.trajectory_ode` at line 37. |
| `quaternion_to_dcm` | No supplied definition/call identified under this corrected spelling. |
| `euler_to_quaternion` | `Simulation.solve_ode` at line 134. |
| `Hopper` / constructor | No construction call identified. |
| `Hopper.mass` | `Simulation.trajectory_ode` at line 91. |
| `Hopper.CG` | `Simulation.trajectory_ode` at line 92. |
| `Hopper.inertia` | `Simulation.trajectory_ode` at line 93. Other matches at lines 125–126 are local-variable uses, not function calls. |
| `Hopper.get_thrust_and_moment` | `Simulation.trajectory_ode` at line 96. |
| `Propulsion` | `Hopper.propulsion` annotation at `chassis/hopper.py:13`; superclass reference at `propulsion/propeller.py:4`. |
| `Propulsion.get_mass` | Delegation from `Hopper.mass` at `chassis/hopper.py:46`. |
| `Propulsion.get_local_cg` | No call identified. |
| `Propulsion.get_thrust_and_moment` | Delegation from `Hopper.get_thrust_and_moment` at `chassis/hopper.py:58`. |
| `Propellor` | No construction call identified. |
| `Aerodynamics` / constructor | No construction call identified. |
| `Aerodynamics.determine_at_point` | `Simulation.trajectory_ode` at lines 98–105. |

All identified plant caller bodies above are present in the reviewed excerpts. `main.py` only prints a greeting, `scripts/ehopper.py` is empty, and the PyThrust example does not call the hopper plant. Terminal-name matching, conservative import-alias expansion and callback references are not a complete resolved call graph. Assignment aliases, reflection, dynamic dispatch and external callers remain limitations. Rerun the scanner after modifications, include new symbols where needed, and read every newly identified caller before claiming coverage. Check scripts outside the copied tree also require explicit caller review.

## Root causes, planned repairs and coverage

Every repair and check below is **planned, not yet implemented or passed**. Check labels are intended names for the retained verifier, not existing results.

### RC-01 — package import failure and ambiguous module provenance

- **File/function:** `simulation/simulation.py`, module import `from state import State`; cross-package imports in the plant; copied `test/test_pythrust.py` dependency setup.
- **Reviewed callers:** `Simulation.solve_ode` constructs `State`; `Simulation.trajectory_ode` uses its methods. Hopper imports Propulsion; Propellor inherits it. No external plant construction caller was found.
- **Root cause:** `State` lives in `simulation/state.py`, not a top-level `state.py`. The source lacks an explicit complete package layout. The copied PyThrust example still derives a dependency path beneath the copy, although PyThrust is deliberately excluded. The backend also puts the ORIGINAL source root on PYTHONPATH.
- **Repair:** establish explicit package boundaries and correct imports; make entry-point and data paths independent of cwd. Put the absolute read-only PyThrust location in configuration. Do not install into or mutate the supplied checkout. Prepend the modified root during checks and inspect module provenance.
- **Checks:** `imports_from_modified_copy`, `cwd_independent_imports`, `pythrust_path_configuration`. Assert each imported project module's resolved `__file__` is beneath the modified root; separately identify approved third-party/PyThrust dependency paths.

### RC-02 — supplied initial state discarded

- **File/function:** `Simulation.__init__`, `Simulation.solve_ode`.
- **Reviewed callers:** no constructor or solve call found; solve calls `State` and registers `trajectory_ode`.
- **Root cause:** constructor assigns `self.state = None`; solve constructs an unrelated zero-position, zero-velocity and zero-rate state.
- **Repair:** retain a defensive copy of the supplied 13-element initial vector, validate shape/finiteness/nonzero quaternion, and integrate that vector without silently replacing or normalizing its recorded initial values. Define explicit continuation/restart behavior.
- **Checks:** `nonzero_initial_state_preserved`, `invalid_state_rejected`, `initial_state_not_aliased`.

### RC-03 — undefined time and ndarray/object mismatch

- **File/function:** `Simulation.trajectory_ode`.
- **Reviewed callers:** `Simulation.solve_ode` supplies it to solve_ivp at line 145.
- **Root cause:** RHS reads undefined `self.time` and accesses object fields on the ndarray supplied by solve_ivp.
- **Repair:** use the time argument and explicitly unpack `[x_L,y_L,z_L,u_B,v_B,w_B,q0,q1,q2,q3,p_B,q_B,r_B]`. Do not confuse pitch-rate `q_B` with the quaternion.
- **Checks:** `rhs_vector_contract`, `rhs_uses_supplied_time`, free-fall and torque-free checks.

### RC-04 — history and state mutation inside adaptive RHS

- **File/function:** `Simulation.trajectory_ode`; `State.update_state`.
- **Reviewed callers:** RHS calls `update_state` at line 17; no other caller was found. `State.unpack_state` has no identified caller.
- **Root cause:** RHS passes one vector to a thirteen-scalar method; the method appends history. Trial and rejected adaptive solver evaluations are not accepted physical samples.
- **Repair:** remove state/history/controller mutation from RHS. Separate validated state conversion from explicit accepted-sample recording. Record integration results or controller sample endpoints outside RHS, with explicit timestamps.
- **Checks:** `rhs_repeatable_without_mutation`, `state_roundtrip`, `history_only_outside_rhs`; later CDR checks cover controller sample timing.

### RC-05 — quaternion DCM variable typo and missing input validation

- **File/function:** `helpers/math.py:quarternion_to_dcm`.
- **Reviewed callers:** `Simulation.trajectory_ode`, line 37.
- **Root cause:** parameter `quarternion` is ignored while unassigned local `quaternions` is read. Normalization has no finite/nonzero validation.
- **Repair:** implement a validated, direction-documented quaternion DCM function; preserve the misspelled name only as a documented compatibility wrapper if retained. Explicitly distinguish body-to-local R_LB from local-to-body C_BL=R_LB.T.
- **Checks:** `isolated_axis_rotations`, `compound_rotations`, `dcm_direction_basis_vectors`, `invalid_quaternion_rejected`, tolerance 1e-9 against an independent implementation. A conversion round trip alone is insufficient.

### RC-06 — Euler signature, ordering and units disagree

- **File/function:** `helpers/math.py:euler_to_quaternion`; `Simulation.solve_ode`.
- **Reviewed callers:** solve at line 134 is the sole identified caller.
- **Root cause:** helper accepts an angle collection and a degrees flag, but caller supplies three scalars. Commented roll/pitch/yaw order conflicts with psi/theta/phi unpacking.
- **Repair:** explicit `euler_to_quaternion(roll, pitch, yaw)` in radians, scalar-first Hamilton output, R_LB=Rz(yaw)Ry(pitch)Rx(roll). Initial attitude comes from the authoritative state, not a hidden reset in solve.
- **Checks:** isolated-axis and compound rotations against independent matrices/rotation implementation within 1e-9; invalid input rejection.

### RC-07 — undocumented frame alignment and hover Euler singularity

- **File/function:** quaternion helpers; `Simulation.trajectory_ode`; `Aerodynamics.determine_at_point`; propulsion/CG interfaces.
- **Reviewed callers:** RHS calls DCM, mass/CG/inertia, propulsion and aerodynamics; Hopper delegates propulsion. Caller locations are listed above.
- **Root cause:** gravity and height imply down-positive local z, while the aerodynamic default uses longitudinal body +x. Identity attitude is not upright if +x is required to point upward.
- **Repair authority:** Chief decision eadb9fb2606b47c18adf61537afece9c r1 selects local NED and structure-fixed forward/right/down body axes. Upright forward-north attitude is q_LB=[1,0,0,0]; neutral thrust is -z_B. Quaternion integration uses qdot=0.5*q Hamilton-product [0,omega_B]. Existing rate-matrix signs must be tested, not labelled wrong merely from appearance.
- **Alternative explicitly rejected for this baseline:** longitudinal +x upward with NED gives upright pitch +pi/2 and q=[sqrt(0.5),0,sqrt(0.5),0] at zero roll/yaw. This places hover at the 3-2-1 Euler singularity, although quaternion dynamics themselves remain nonsingular.
- **Checks:** `upright_frame_basis`, `quaternion_kinematics`, independent compound rotations and torque-free inertial angular-momentum checks.

### RC-08 — integration result and solver status lost

- **File/function:** `Simulation.solve_ode`.
- **Reviewed callers:** no supplied call found; solve registers RHS and constructs State.
- **Root cause:** solve_ivp result remains a local variable and is not returned.
- **Repair:** return a structured result containing times, state samples, success, message, status and relevant event/evaluation information. Do not relabel early termination or failure as completion of the requested duration.
- **Checks:** `structured_solver_result`, `solver_success_and_duration`, `solver_failure_reported`; inspect status as well as measured numerical errors.

### RC-09 — required environment is absent from the supplied plant

- **File/function:** `Simulation.trajectory_ode`, environment access.
- **Reviewed callers:** solve's RHS callback; no environment construction entry point found in the reviewed plant.
- **Root cause:** RHS requires elevation plus atmosphere density, viscosity, sound speed and wind methods, but no implementation is supplied in the audited plant inventory.
- **Repair:** add explicit calm-air near-sea-level ISA environment with SI units and a documented altitude domain; distinguish ground-datum elevation, CG height and rise from initial CG. Preserve configurable gravity and deterministic atmosphere evaluations.
- **Checks:** `calm_isa_environment`, `altitude_sign`, free-fall regression with aerodynamics disabled.

### RC-10 — incomplete and inconsistent propulsion abstract contract

- **File/function:** `propulsion/propulsion.py:Propulsion`; `propulsion/propeller.py:Propellor`; `Hopper.get_thrust_and_moment`.
- **Reviewed callers:** Hopper's mass/force delegation, Propellor superclass reference, and RHS's Hopper force call. No Propellor construction was found.
- **Root cause:** abstract methods omit self and have inconsistent arguments; Propellor discards electrical parameters and implements none of the abstract methods.
- **Repair:** define a coherent explicit time/command/state contract and executable electric implementation. Return forces in body axes and moments about the current specified vehicle CG. Define actuator and electrical states separately from the 13 rigid-body states, and use pure evaluations rather than hidden RHS updates. Read PyThrust modules, including `pythrust/propulsion/solver.py`, before relying on their interfaces.
- **Checks:** `propulsion_contract`, `propellor_instantiable`, `propulsion_zero_command`, `propulsion_force_and_torque_signs`, explicit electrical feasibility reporting.

### RC-11 — ambiguous mass ownership, moment origin and diagonal-only inertia

- **File/function:** `Hopper.mass`, `Hopper.CG`, `Hopper.inertia`, `Hopper.get_thrust_and_moment`.
- **Reviewed callers:** RHS lines 91–96; Hopper delegates `Propulsion.get_mass` and force/moment.
- **Root cause:** mass_wo_propellant plus propulsion mass has unclear ownership for electric equipment; battery discharge must not imply mass loss. Moment arm is stored but unused. Inertia is forced diagonal, and the CG reference for returned propulsion moments is unspecified.
- **Repair:** use complete constant electric vehicle mass, with component ownership preventing double counting. Accept a finite symmetric positive-definite full 3x3 inertia about the stated CG. Compute (r_application-r_CG) cross F exactly once; Hopper must not repeat a moment already included by propulsion.
- **Checks:** `battery_mass_constant`, `full_inertia_tensor`, `mass_properties_validation`, `moment_arm_applied_once`, torque-free checks with nonzero products of inertia.
- **Limitation:** neutral locked-gimbal mass properties are acceptable for isolated PDR rigid-body checks only. Moving-module inertia, CG and angular momentum require a consistent articulated model or quantified approximation before CDR performance claims.

### RC-12 — missing realizable actuator dynamics and coupled allocation

- **File/function:** incomplete propulsion implementation; no integrated control/actuator plant exists in the reviewed source.
- **Reviewed callers:** RHS/Hopper/Propulsion chain; greeting and empty entry points provide no further implementation.
- **Root cause:** no model connects realizable actuator commands to transverse moments, signed reaction torque, response lag or limits.
- **Repair authority:** Chief decision 5e982749fd82487180d94f35416d647f r1 selects a provisional common two-axis coaxial gimbal plus differential rotor reaction torque. Maximum resultant deflection is 12 degrees in any azimuth, not independent simultaneous 12-degree axis limits. Pivot target is 0.25 m above CG; actual signed offset must come from CAD.
- **Repair:** configurable first-order motor/ESC and servo lag, gimbal rate/travel/cone limits, rotor limits and differential reaction torque. Preserve uncalibrated motor-lag cases 0.05/0.10/0.20 s and explicit coaxial thrust/torque factors. Reaction torque follows the tilted rotor axis. Do not assume equal RPM gives equal opposing torque. Separate steady aerodynamic torque from rotor-acceleration/gyroscopic contributions and avoid double counting internal torques.
- **Checks:** `motor_lag_response`, `gimbal_lag_rate_cone_limits`, `differential_reaction_torque`, `saturation_reported`; static authority calculation is separate evidence, not a closed-loop mission.
- **Evidence limitation:** MG996R 0.17 s/60 deg at 4.8 V, 0.14 s/60 deg at 6 V and 9.4–11 kgf cm are search-snippet-grade stall/no-load specifications, not loaded gimbal response or continuous torque ratings. Treat the retailer's 50–432 Hz Skywalker V2 40A PWM range as a command-rate bound, not achieved actuator bandwidth.

### RC-13 — cylindrical aerodynamics do not represent the exposed vehicle

- **File/function:** `aero/aero.py:Aerodynamics.determine_at_point`; Hopper tube parameters.
- **Reviewed callers:** RHS lines 98–105; no other caller identified.
- **Root cause:** the model assumes an axisymmetric cylindrical tube, normally longitudinal +x. REQ-VEHICLE-CONFIGURATION r1 excludes an enclosing body skin; battery, plates, electronics and landing legs are exposed.
- **Planned PDR treatment:** use an explicitly disabled aerodynamic model for analytical plant checks and the idealized calm-air hover reference. At stationary calm-air hover, translational freestream dynamic pressure is zero; disabling unknown drag isolates rigid-body equations without inventing tube geometry or coefficients. This is NOT evidence that rotor-wake loading or rotational aerodynamic loads vanish, and is not adequate justification for arbitrary moving-flight accuracy.
- **Proposed detailed re-parameterisation:** component locations and directional projected areas from CAD, with traceable drag coefficients. Evaluate each component's local relative velocity including omega cross r, sum component forces and moments about the same CG, and assess rotor wake separately. Drag coefficients, wake forces and validity bounds remain open.
- **Checks:** `aerodynamics_explicitly_disabled`, no implicit tube fallback; later component-drag dissipation/zero-speed checks and sensitivity bounds.

### RC-14 — zero-airspeed rotational-damping discontinuity

- **File/function:** `Aerodynamics.determine_at_point` near-zero-speed early return and later damping calculation.
- **Reviewed callers:** RHS lines 98–105.
- **Root cause:** the function returns zero force AND moment when translational speed is below epsilon, before computing a rotational damping term that can remain nonzero at zero translational speed for fixed nonzero angular rates.
- **Repair:** keep translational and rotational contributions separate in any retained model. Explicitly disabling aerodynamics avoids this branch during rigid-body checks but does not repair or validate the legacy cylinder model. Mark that legacy model unsupported for the exposed-vehicle configuration unless deliberately repaired and re-parameterised.
- **Checks:** `zero_airspeed_rotational_limit` if a damping model is enabled; otherwise report the legacy defect as excluded/unresolved, not passed.

### RC-15 — inconsistent gravity constants

- **File/function:** `helpers/constants.py:GRAVITY`; `Simulation.trajectory_ode` gravity vector.
- **Reviewed callers:** RHS imports and uses GRAVITY; analysis configuration separately supplies gravity.
- **Root cause:** supplied constant is 9.8065 m/s^2, while `analysis/chief_propulsion_screening_config.json` uses 9.80665 m/s^2. Difference is 0.00015 m/s^2, producing 0.000075 m position difference after 1 s of rest free fall, larger than the required 1e-6 m tolerance.
- **Repair:** use explicitly documented standard gravity 9.80665 m/s^2 consistently, with any alternative value configurable and reported.
- **Checks:** `standard_gravity_consistent`, analytical free-fall check using an independently specified reference value.

### RC-16 — no executable hopper controller or mission integration

- **File/function:** `main.py:main`; empty `scripts/ehopper.py`; `test/test_pythrust.py`.
- **Reviewed callers:** main's `__main__` guard; the PyThrust example calls its own RPM/voltage helper functions, not Simulation or Propellor. No hopper PID caller found.
- **Root cause:** entry points do not construct the plant, and the propulsion example prints operating points rather than asserting integrated hopper behavior.
- **PDR repair boundary:** provide runnable plant/check entry points and preliminary altitude/attitude/rate-loop and allocation documentation. Defer gains, tuned PID and takeoff/300-second-hover/landing runs to CDR after explicit human PDR acceptance.
- **Control interface requirement:** update PID integrals and measurement-derivative filters only at fixed samples; hold allocated commands during each control interval; integrate one interval per solve_ivp call; record accepted endpoints outside RHS. Include conditional integration or back-calculation using achieved saturated allocation. A documented architecture is not an implemented or tested controller.
- **Checks:** plant entry-point/import checks at PDR. Fixed-rate timing, anti-windup, disturbance/saturation recovery and mission checks remain CDR items.

## Frame and CAD interface constraints

Apply Chief frame decision eadb9fb2606b47c18adf61537afece9c r1, not an unrecorded worker selection:

- L: right-handed North-East-Down, fixed launch-ground datum.
- B: non-gimballed structure-fixed +x forward, +y right, +z toward landing feet upright.
- O: structural reference origin at neutral complete-vehicle reference CG. G: instantaneous CG, distinguished if articulated geometry changes.
- Integrated translation describes G: local position in m and body-resolved CG velocity in m/s. Angular rates are structure rates in rad/s.
- q_LB: scalar-first Hamilton body-to-local quaternion. R_LB maps body components into local components; C_BL=R_LB.T maps local to body.
- Upright forward north: q_LB=[1,0,0,0]; gravity_L=[0,0,+g]; neutral thrust_B=[0,0,-T].
- CAD mapping remains numerical-configuration pending: x_B,m=0.001 R_BC(x_C,mm-CG_C0,mm). Require orthogonality and determinant +1, not a reflection.
- Rotate CG-referenced mass inertia as I_B=R_BC I_C R_BC.T after unit conversion. For kg mm^2, multiply by 1e-6; apply parallel-axis translation if reference points differ. Geometric volume moments are not mass inertia.
- Ground clearance, -z_G and rise z_G(0)-z_G(t) are distinct. This decision does not settle the human mission-height reference.

## Required retained verification evidence

Write editable `software/r5/checks/plant_checks.py`. The verify_command invocation must list the tested artifact Refs, insert the modified root first, assert imported project module provenance and print only `{outcome, explanation, checks}` to stdout, with every checks value boolean or null. Send diagnostics to stderr. A separate execute run must save numeric measurements and provenance in JSON. Do not turn an exception or missing measurement into a true check.

Required PDR checks:

1. Imports resolve to the modified copy.
2. A nonzero 13-element initial state is preserved.
3. Isolated-axis and compound rotations agree with an independent implementation within 1e-9.
4. Aerodynamics-disabled free-fall position error is below 1e-6 m over 1 s.
5. Torque-free angular-momentum magnitude relative error is below 1e-5 and quaternion norm error below 1e-6 over 10 s, with norm feedback BOTH disabled and enabled. Use nontrivial angular rates and a full inertia tensor; report solver success, actual duration and sampled maxima. Additional inertial-direction/energy checks strengthen coverage.
6. Supplied source/data hashes match the preserved baseline; separately disclose exclusion metadata and initialization limitations.

After implementation, rerun the caller scan, review changed/new callers, record actual check results without replacing failures, and update this audit with implementation status. Retain the editable diff-generation script, patch against the supplied source, final modified-copy manifest and after-hash comparison.

## Open dependencies and CDR items

- Current CAD mass, neutral CG, full inertia tensor, actual pivot offsets and numerical CAD transform are not yet available here.
- Updated per-rotor thrust/torque/current, shared-voltage feasible allocation and calibrated actuator data are not yet available here. Do not invent yaw authority from motor constants alone.
- Static pitch/roll/yaw authority must be computed by a retained script from identifiable input artifacts; provisional values must retain their evidence grade.
- Moving-module inertia/CG, rotor acceleration reaction torque, gyroscopic coupling, wake loading, thermal behavior and electrical transients need modelling or quantified approximation limits.
- Numerical mission tolerances and height reference require human agreement; ground/flight calibration and acceptance remain unperformed.
- No current PDR review disposition is recorded. PID tuning and mission verification are not authorized by completion of software checks.
