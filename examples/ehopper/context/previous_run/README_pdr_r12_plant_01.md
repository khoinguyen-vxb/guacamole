# PDR r12 preliminary hopper plant

Date: 2026-10-13. Task: `pdr_r12_preliminary_plant`.
Authorization: work-plan decision `66c7448f443f44ac9a016a1b384593a2`, revision 1.

## Status and scope

This directory contains a separate, runnable **analytical-fixture implementation** of the audited hopper plant, editable configurations and checkers, retained logs, and a proposed PID architecture. It is not a calibrated vehicle simulator, flight controller or accepted PDR/CDR baseline. Supplied checkouts and historical r9 outputs are not the repair destination.

The runnable preliminary path repairs imports, initialization ownership, numeric state decoding, frame interfaces, solver-result handling and propulsion integration. It retains explicit motor/gimbal dynamics and saturation interfaces. No PID gains are selected or tuned, and no vehicle closed-loop mission acceptance is performed. Controller implementation, tuning and mission acceptance remain gated on accepted current PDR and a subsequent validated CDR plan.

Chief-owned structural, CAD, propulsion, procurement and vehicle selections are outside this worker's authority. Fixture mass, inertia, geometry, travel, spin signs and response parameters must never be promoted to selected vehicle inputs merely because their tests execute.

## 1. Directory and module map

Paths below are relative to `software/pdr_r12_plant/`.

| Path | Purpose |
|---|---|
| `pre_edit_root_cause_checkpoint_20261011_01.md` | Preserved source-inspection findings and initial audit gaps |
| `pre_edit_caller_reconciliation_r12_20261011_02.md` | Additional caller inspection, capability distinction and separated-origin migration |
| `read_only_source_audit_01.py` | Editable static source/caller inventory program |
| `source_inventory_r12_01.json` | Bounded source inventory and file hashes |
| `affected_caller_index_r12_01.md` | Candidate caller locations; not a globally complete runtime call graph |
| `capability_probe_r12_01.py` | Editable dependency/import diagnostic |
| `capability_report_r12_01.json` | Recorded interpreter, import and preservation observations |
| `repaired_hopper_r12/helpers/math.py` | Hamilton quaternion, explicit rotation, CAD/SI and fixed-datum helpers |
| `repaired_hopper_r12/simulation/state.py` | Immutable instantaneous-CG rigid-body state and explicit serialization |
| `repaired_hopper_r12/chassis/hopper.py` | Complete mass-property snapshot and full-inertia angular-momentum interface |
| `repaired_hopper_r12/propulsion/propulsion.py` | External point loads/free couples, paired performance and domain contracts |
| `repaired_hopper_r12/propulsion/propeller.py` | Common-gimbal geometry, separated origins, hub kinematics and rotor-load adapter |
| `repaired_hopper_r12/propulsion/actuators.py` | Held commands, six actuator states, synthetic lag and explicit limits |
| `repaired_hopper_r12/simulation/environment.py` | Explicit ambient conditions, hub-location sampling and auxiliary bus loads |
| `repaired_hopper_r12/simulation/simulation.py` | Pure numerical RHS and one-held-command integration boundary |
| `analytical_fixture_config_r12_01.json` | Labelled synthetic inputs, test vectors and numerical regression thresholds |
| `analytical_fixture_models_r12_01.py` | Fixture loading, initial snapshots, mass/map/environment providers and construction |
| `verify_state_frames_mass_r12_02.py` | Current state/frame checker entry point; depends on retained checker 01 |
| `verify_propulsion_interfaces_r12_01.py` | Wrench, separated-origin, bottom-pivot and interface fixtures |
| `verify_solver_open_loop_r12_01.py` | Analytical trajectories, synthetic trim, events and solver-failure fixtures |
| `verify_actuator_response_r12_01.py` | Analytical actuator response, saturation and endpoint carry-forward fixtures |
| `collect_verification_logs_r12_01.py` | Log collector, not a new verification authority |
| `test_logs_r12_01/` | Raw checker output and JSON/Markdown measured-error digests |
| `pid_architecture_and_vehicle_interfaces_r12_01.md` | Untuned control proposal, reduced-model limitations and VI-01 through VI-12 interface register |

The checkers are reproducible analytical entry points, not a general vehicle mission launcher. Preserve the directory hierarchy when copying the repaired package and fixtures. Do not substitute the original checkout's similarly named modules.

## 2. Reproducible execution

The project output root is:

`/home/ngvnngkhoi/guacamole/examples/ehopper/results`

For Guacamole calls select `repository="6dof_hopper"`, `workdir="."`, and an argv list beginning with `python`. The repository option selects the backend interpreter/import root; it does not make the original plant the repaired implementation. `-B` prevents bytecode writes.

Run each current checker through `verify_command@1`:

```text
python -B software/pdr_r12_plant/verify_state_frames_mass_r12_02.py
python -B software/pdr_r12_plant/verify_propulsion_interfaces_r12_01.py
python -B software/pdr_r12_plant/verify_solver_open_loop_r12_01.py
python -B software/pdr_r12_plant/verify_actuator_response_r12_01.py
```

These lines describe argv, not shell scripts. For each tool action include the exact current artifact Refs for the checker, fixture configuration, fixture models and all eight repaired modules. The state/frame entry point additionally requires retained checker 01. Use runtime records for Ref hashes; file hashes in checker `PINNED` dictionaries are different identifiers.

Checkers read the actual files and retain file-hash binding. Stdout contains only a VerificationResult JSON object; diagnostics and measurements go to stderr. An exit code of zero is not a physical or verification pass. Inspect the returned outcome and checks. Unknown/unperformed checks remain null and must not be counted as passing.

The four registered runs already exist; documentation does not require repeating them. If a future authorized change alters a pinned artifact, audit affected callers, publish a new version and update the checker binding deliberately. Do not bypass a hash mismatch or overwrite the historical results.

The existing collector command is:

```text
python -B software/pdr_r12_plant/collect_verification_logs_r12_01.py
```

It has already executed through `execute@1`, with these declared outputs:

- `software/pdr_r12_plant/test_logs_r12_01/checker_raw_logs_r12_01.txt`
- `software/pdr_r12_plant/test_logs_r12_01/measured_error_digest_r12_01.json`
- `software/pdr_r12_plant/test_logs_r12_01/measured_error_digest_r12_01.md`

**Do not rerun that collector unchanged:** it refuses existing output files. A future collection needs reviewed, fresh task-specific output paths and declared outputs. Its re-executions retain diagnostics; they neither replace nor upgrade registered verification.

No installation command is required or authorized here. Request any newly observed missing installation through the Chief rather than changing the source environment.

## 3. Audit and migration map

Authoritative audit records are `PDR-R12-PLANT-PRE-EDIT-AUDIT-01` and `PDR-R12-PLANT-CALLER-RECONCILIATION-02`, each revision 1. Read them together: the addendum supplements the original checkpoint rather than erasing its earlier gaps.

Only the original `simulation.simulation` import failure was reproduced by the capability probe: `ModuleNotFoundError: No module named 'state'`, without an import workaround. The remaining original defects below are source-inspection findings, not claims of reproduced exceptions.

| Original finding/interface | Preliminary replacement |
|---|---|
| `Simulation.__init__` assigns `self.state=None`, losing its input | Explicit immutable initial rigid-body and actuator snapshots |
| `trajectory_ode` reads undefined `self.time` | Supplied solver time used explicitly |
| Numeric ODE array treated as a State object | Versioned numeric-vector decoding |
| `update_state` called with one vector despite a thirteen-scalar signature; it also appends history | Pure RHS; accepted trajectory output remains separate from trial evaluations |
| Incorrect top-level State import | Repaired package-relative imports |
| `quarternion_to_dcm` reads an uninitialized local variable | Explicit quaternion helper with input validation |
| Euler caller passes three positional values to a vector/degrees API; documented ordering is inconsistent | Named `roll_rad`, `pitch_rad`, `yaw_rad` initialization |
| `solve_ode` resets position, velocity and rates | All initial rigid-body and actuator components preserved |
| `solve_ode` discards its integration result | Actual solver result returned, with events and failure semantics retained |
| `Propellor` leaves abstract methods unimplemented and discards electrical arguments | Concrete load adapter requiring explicit geometry and a coupled performance provider |
| Separate time-only mass/CG/inertia and ambiguous forwarded wrench | One complete-vehicle snapshot and explicit external loads resolved about its instantaneous CG |
| Recovered r9 geometry assumes coincident gimbal origins | Explicit outer origin, outer-to-inner displacement and module hub offsets, with distinct velocity derivatives |

Convention migrations must not be misreported as original defects:

- The original DCM algebra, after its variable-name defect is corrected, has the body-from-local direction. That direction is not intrinsically wrong. New code names the opposite mapping explicitly; the deprecated spelling retains its documented legacy direction.
- The original quaternion-rate matrix is consistent with scalar-first Hamilton right multiplication.
- The original `-omega cross velocity` transport term is appropriate for body-resolved velocity. It does not belong in the new local-NED CG velocity equation.
- Diagonal inertia and fixed CG can describe a limited rigid model, but are not sufficient descriptions of the articulated assembly. Adding propulsion mass is not inherently wrong; adding it again to a complete installed-mass ledger would double-count it.

The inspected original callers include `Simulation.trajectory_ode`, `Simulation.solve_ode` and Hopper's propulsion forwarding. Original `main.py` prints a greeting, `scripts/ehopper.py` is empty, and `test/test_pythrust.py` is a separate prescribed-RPM/equilibrium-voltage example. It is not a calibrated integrated hopper propulsion path.

The static inventory covers specified roots and candidate symbols. Dynamic dispatch, rebinding, generated code and callers outside those roots are not globally excluded. New checkers are additional callers and remain editable for review.

## 4. Frames, units and state ownership

Retained frame decision: `f046cc4fe5294a6f9a61027529056f61`, revision 1.
Retained gimbal convention: `28e10be57d6548a3aa5be06c96f6d0d0`, revision 1.

- L: North-East-Down, with a fixed launch-ground origin.
- B: structure-fixed Forward-Right-Down.
- `q_LB=[w,x,y,z]`: scalar-first Hamilton; `R_LB` maps B components into L.
- Identity attitude is upright, forward north; `qdot=0.5*q_LB ⊗ [0,omega_B]`.
- Euler initialization uses radians and `R_LB=Rz(yaw)Ry(pitch)Rx(roll)`.
- Gravity in L is `[0,0,+g]`; neutral propulsion force in B is `[0,0,-T]`.
- CAD C: forward, left, up. `R_BC=diag(1,-1,-1)` and `r_B0=0.001*R_BC*(p_C-CG_C0)` convert CAD mm to body m. Numerical neutral complete-vehicle `CG_C0` is a required input, not zero by assumption.
- Mass is kg; inertia is kg m^2; angular quantities use rad and seconds; force is N and moment N m.

The current plant has 19 components:

| Slice | Quantity | Unit |
|---|---|---|
| 0:3 | Instantaneous complete-vehicle CG position in L | m |
| 3:6 | CG velocity in L | m/s |
| 6:10 | q_LB, scalar first | 1 |
| 10:13 | Airframe angular velocity in B | rad/s |
| 13:15 | Upper/lower rotor speed magnitudes | rad/s |
| 15:17 | Alpha/beta demand-filter states | rad |
| 17:19 | Actual alpha/beta angles | rad |

Use `PLANT_STATE_SCHEMA`, `PLANT_UNITS`, `pack_state` and `unpack_state`. Shape alone does not identify the velocity frame or reference point. Preserve raw quaternion samples for norm-error measurement; local normalization to construct a rotation does not authorize projection of the reported trajectory.

`Simulation.solve_ode` integrates one immutable HeldCommand. Repeated solves of one instance restart from its original state. Continuing an event-free interval requires explicit endpoint decoding and replacement of both initial snapshots, including all actuator components. For a terminal event, inspect `t_events` and `y_events` or validated dense output; the last requested sample is not necessarily the event endpoint. Solver and provider failures must not be converted into accepted endpoints.

Translation is at instantaneous G, while mission scoring is at fixed airframe datum O_B0. For CG offset r and its body-component derivative rdot:

`p_O=p_G-R_LB*r`

`v_O=v_G-R_LB*(omega_B cross r+rdot)`.

An acceleration conversion additionally requires consistent CG-offset acceleration. The current interface is not a complete articulated acceleration provider.

## 5. Propulsion and reduced dynamics

The retained common two-axis gimbal uses `R_BM=Rx(alpha)Ry(beta)`: outer body-fixed x and inner carried y. Its point geometry is

`r_B0,i=r_B0,Ox+Rx(alpha)*d_OxOy+R_BM*r_Oy,i,M`.

Upper/lower identifiers stay attached to their components. Rotor spin signs are defined about the same module +z axis; purchased CW/CCW labels require a viewing direction. With nonnegative thrust and aerodynamic drag magnitudes:

`F_i,B=R_BM*[0,0,-T_i]`

`tau_air,i,B=R_BM*[0,0,-sigma_i*Q_i]`.

Resolve each external moment exactly once as `(r_B0,i-r_B0,G) cross F_i + tau_air,i`. Opposite spin signs alone do not establish equal torque, equal thrust or cancelled gyroscopic effects. The map evaluates both actual rotor states together. Synthetic paired-map arithmetic is not vendor performance or measured coaxial calibration.

The labelled bottom-pivot fixture verifies negative near-neutral effectiveness, `dMx/dalpha=dMy/dbeta=-h*T` for h>0. Actual separated origins, off-axis CG and transformed aerodynamic couples require the full wrench calculation, not an inherited scalar lever arm.

The mass interface uses

`I*omega_dot=M_ext-omega cross (I*omega+h_rel)-I_dot*omega-h_rel_dot`.

Internal motor and servo reactions are not additional external whole-vehicle moments. `rigid_body_fixture` deliberately freezes properties and omits internal relative momentum. `prescribed_internal_momentum` accepts explicitly supplied consistent terms but does not derive or validate a multibody provider. `reduced_articulated` omits relative-momentum terms; configuration-dependent inertia alone does not restore them.

The lag model is a synthetic speed-response abstraction, not an ESC PWM/voltage interface or evidence of actual speed regulation. Prescribed gimbal motion does not solve joint loads, servo torque, backlash, friction, bearing compliance or structural deflection. Limits observed at samples and dense midpoints are not continuous certification; invalid explicit-integration trial states can be rejected.

Prescribed voltage, SOC and temperatures do not close battery sag, usable energy or thermal evolution. Motor winding and battery-branch currents are distinct; auxiliary consumers are counted once. Exposed-structure aerodynamics, wakes, ground effect, foot contact and settling are not validated by these fixtures.

## 6. Evidence layers and recorded outcomes

`PDR-R12-PLANT-CAPABILITY-REPORT-01`, revision 1, records CPython 3.13.11 and successful imports of NumPy 2.5.2, SciPy 1.18.0, scipy.integrate and pytest 9.1.1. Other distribution versions in that report are metadata observations only. The capability diagnostic reproduced the original import defect; its exit code zero meant observations were recorded, not that the original plant worked.

Preservation measurements covered 68 inventoried files. They do not establish historical checkout cleanliness or cover all unlisted files, environments and data.

The following registered verification evidence is current, each revision 1:

| Evidence ID | Outcome | True / false / null | Tested scope |
|---|---|---:|---|
| PDR-R12-PLANT-STATE-FRAME-MASS-VERIFICATION-02 | inconclusive | 83 / 0 / 4 | Initialization ownership, quaternion/frame/CAD identities, mass-momentum algebra and fixed-datum kinematics |
| PDR-R12-PLANT-PROPULSION-INTERFACE-VERIFICATION-01 | inconclusive | 151 / 0 / 4 | Bottom-pivot signs, separated-origin kinematics, external loads, domain policies and interfaces |
| PDR-R12-PLANT-SOLVER-OPEN-LOOP-VERIFICATION-01 | inconclusive | 146 / 0 / 4 | Ballistic rotation, synthetic trim, solver returns, dense output, events and deliberately injected failures |
| PDR-R12-PLANT-ACTUATOR-RESPONSE-VERIFICATION-01 | inconclusive | 116 / 0 / 4 | Synthetic motor/gimbal response, saturation, switching and explicit state carry-forward |

These are scoped software observations, not a complete-vehicle pass. Null checks remain unperformed by their respective programs. Some scopes are addressed by a separate checker; that does not change the original record's outcome.

The initial state/frame registration, request `b7d6f20b863f491c9545257a292c241a`, failed validation because its passed outcome included null checks. Human diagnostic source `49ab555137c7475890307e8e5f93f7d3`, revision 1, clarified the contract. Entry point 02 preserves checker 01 and its analytical calculations while correcting reporting to inconclusive. Do not erase the failed registration or present it as a physical failure.

Measured diagnostics are retained in `PDR-R12-PLANT-RAW-CHECKER-LOGS-01`, `PDR-R12-PLANT-MEASURED-ERROR-DIGEST-JSON-01` and `PDR-R12-PLANT-MEASURED-ERROR-DIGEST-MD-01`, each revision 1. Collection execution `fbe241125f2f4824a6872d6785b39f9e` observed matching before/after file pins and matching registered outcomes/counts. It is log retention, not new acceptance evidence.

Examples tabulated by digest 01 include:

- Separated-origin air-relative hub-velocity maximum error: 2.711e-11 m/s against a 1e-9 m/s regression tolerance.
- Bottom-pivot effectiveness error: 8.100e-13 N m/rad against 1e-7 N m/rad.
- Synthetic trim force residual: 3.553e-15 N against 1e-10 N.
- Coupled-run raw quaternion norm error: 2.220e-16 against 1e-9.
- Saturation-release filter-angle refinement difference: 1.196e-9 rad against 1e-8 rad.

These thresholds are synthetic numerical regression criteria, not human-agreed vehicle limits. The digest parser tabulated zero individual measurement rows for the state/frame checker; its raw diagnostics remain retained. An empty table is not a zero-error result.

## 7. PID proposal and future acceptance

See `pid_architecture_and_vehicle_interfaces_r12_01.md`, published as `PDR-R12-PLANT-PID-ARCHITECTURE-01`, revision 1. It specifies proposed fixed-cadence scheduling, held commands, all-state carry-forward, coupled force/moment allocation, unit-consistent anti-windup and filtered derivative on measurement. Controller memory must be updated outside adaptive RHS evaluations. Gains and selected cadence remain unset.

REQ-SIMULATION-ACCEPTANCE revision 1 provides future targets, not achieved results: a 5.00 m fixed-datum rise; uninterrupted 300 s hover with altitude RMS/max <=0.10/0.25 m and horizontal radial RMS/max <=0.25/0.50 m; specified 10 deg attitude perturbations recovering to <=2 deg and <=2 deg/s within 5 s and held for 2 s; first-foot-contact downward/horizontal speed <=0.30/0.20 m/s and airframe tilt <=5 deg, with both rotor envelopes clear.

The architecture document maps these targets to future procedures and separately labels proposed acquisition, disturbance, saturation, numerical and reserve criteria requiring agreement. The analytical CG-plane event is not a foot-contact or landing validation. Climb, acquisition and landing energy are additional to the 300-second hover.

## 8. Unresolved interfaces and handoff boundary

The architecture's VI-01 through VI-12 register identifies the required Chief inputs:

1. Complete installed mass, neutral CAD CG, full inertia and component ownership.
2. Articulation-dependent CG and derivatives, inertia and relative angular momentum; justified dynamics mode.
3. Joint origins, hub offsets/spacing, thrust application assumptions, feet and ground geometry.
4. Physical rotor spin assignments and purchased-propeller mapping with viewing direction.
5. Coupled propulsion map, interference calibration and operating domains.
6. Loaded motor/ESC command mapping, response, braking and electrical/thermal limits.
7. Servo/linkage geometry, travel, cone, loaded rate/acceleration/torque and supply limits.
8. Shared-bus sag, usable energy, SOC/temperature evolution and auxiliary power.
9. Exposed-structure aerodynamic, wake, ground-effect and disturbance assumptions.
10. Leg/contact compliance, friction, terrain, settling and clearance allowances.
11. Sensor/estimator, latency and achievable controller cadence.
12. Chief disposition and human agreement on the remaining proposed criteria.

Independent analytical fixtures do not require inventing these vehicle values. Their absence prevents vehicle-validity and mission-acceptance claims. No review notification, conversational agreement, successful process or analytical fixture result substitutes for human PDR/CDR review disposition.
