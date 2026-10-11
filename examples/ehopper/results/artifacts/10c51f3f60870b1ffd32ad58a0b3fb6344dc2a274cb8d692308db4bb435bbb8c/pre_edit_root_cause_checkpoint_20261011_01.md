# PDR r12 preliminary plant — pre-edit checkpoint

Date: 2026-10-11.
Task: pdr_r12_preliminary_plant.
Authorization: decision 66c7448f443f44ac9a016a1b384593a2 revision 1.

## Status and evidence boundary

This is an editable, incomplete audit checkpoint, not a repaired-code release or verification result. It consolidates actual source text already returned by current readers. No supplied checkout or historical output is changed by this document.

The findings below are SOURCE-INSPECTION findings. No r12 failure reproduction, dependency/import capability, numerical execution or analytical test pass is established by the evidence cited here. Historical repaired code is reusable evidence, not current authorization or proof that it runs. No vehicle configuration, PID gains, PDR/CDR acceptance or physical validity is established.

The retained contracts are:

- Frame decision f046cc4fe5294a6f9a61027529056f61 r1: NED local coordinates, FRD structure-fixed axes, scalar-first Hamilton q_LB, R_LB mapping body vectors into local coordinates, and instantaneous complete-vehicle CG translation.
- Gimbal decision 28e10be57d6548a3aa5be06c96f6d0d0 r1: R_BM=Rx(alpha)Ry(beta), explicit outer/inner joint-origin translations, stable upper/lower rotor identities, and external aerodynamic rotor-torque signs.
- REQ-SIMULATION-ACCEPTANCE r1: mission tracking uses fixed airframe datum O_B0, not instantaneous CG. Agreed targets are future acceptance criteria, not achieved results.
- REQ-PROPULSION-PLACEMENT r1: bottom-mounted propulsion and retained common two-axis gimbal. Historical numerical geometry is not transferable without current evidence.

## 1. Confirmed original-source findings

Locators below identify functions within current read_text results; no unavailable line numbers are invented.

| ID | Source finding | Consequence and affected interface |
|---|---|---|
| R12-RC01 | simulation/simulation.py imports State using `from state import State`, whereas the inspected state implementation resides under simulation. | Import/package integration defect. Repair package imports together with entry points; reproduce in the selected backend before claiming an observed import failure. |
| R12-RC02 | Simulation.__init__ receives `state` but assigns `self.state = None`. | Supplied initial-state ownership is lost. Preserve a copied/immutable authoritative initial state and test nonzero initialization. |
| R12-RC03 | trajectory_ode reads `self.time`, which is not initialized in the inspected class. | Use the solver's time argument. An execution exception has not yet been reproduced here. |
| R12-RC04 | trajectory_ode calls `self.state.update_state(state)`, but State.update_state requires thirteen scalar arguments. | Caller/callee signature mismatch. Explicit numeric-vector decoding is needed; changing only the call would not repair the other RHS defects. |
| R12-RC05 | trajectory_ode accesses `state.x`, `state.u`, quaternion attributes and rates, although solve_ivp supplies a numeric state array. | Decode the ODE vector consistently. Do not interchange numeric vectors and mutable State instances. |
| R12-RC06 | helpers/math.py declares parameter `quarternion`, then reads and assigns the distinct local name `quaternions` before initialization. | Definite local-variable defect in quarternion_to_dcm. Its expected exception remains a source prediction until reproduced. |
| R12-RC07 | solve_ode passes three positional Euler arguments; euler_to_quaternion accepts an angle vector and optional degrees flag. | Definite signature mismatch. Migrate the caller and helper together. |
| R12-RC08 | euler_to_quaternion comments identify roll/pitch/yaw input, but unpacking assigns psi/theta/phi. Degrees are enabled by default. | Documented ordering contradicts implementation. Replace ambiguity with named roll_rad, pitch_rad and yaw_rad; use isolated-axis and noncommuting-angle fixtures. |
| R12-RC09 | solve_ode replaces initialization with zero position, velocity and rates, retaining only its newly constructed attitude. | Nonzero constructor state is not used by this integration entry point. Preserve all rigid-body and actuator initial components explicitly. |
| R12-RC10 | solve_ode assigns the solve_ivp result to a local `solution` and returns nothing. | Caller cannot obtain the actual result. Return solver status, samples, events and dense output without concealing failures. |
| R12-RC11 | State.update_state appends history; trajectory_ode attempts to call it during RHS evaluation. | Adaptive trial stages would become misleading trajectory history if the call were merely repaired. Keep RHS pure; report accepted output samples separately. |
| R12-RC12 | Propellor implements none of Propulsion's abstract methods, and its constructor discards the supplied electrical parameters after super().__init__. | Incomplete propulsion implementation. An instance is not a working propulsion backend; retain an explicit coupled performance-map and actuator-response interface. |

Source references: original Simulation reader eda44d599b3c472ba985c4f579cbd909 r1; math reader 9b109a76a3d24595898446d01abe6eda r1; State reader 7990c07cefb34a87954bee8947a7bbbb r1; propulsion ABC reader a5a521c6952b43ffb1e4e62e31425e91 r1; Propellor reader 5dc6e2c512ba41d6aac9eb2df685da89 r1.

### Additional interface/model limitations, not automatically numerical bugs

- Hopper.inertia returns a diagonal tensor. That can represent a rigid principal-axis model, but it cannot generally represent the current articulated assembly's full tensor in fixed FRD axes. Hopper.CG returns a fixed value and does not use its propulsion local-CG interface. Current integration requires a consistent complete-vehicle snapshot, not an inherited mass-accounting assumption.
- Hopper.get_thrust_and_moment forwards a time-only wrench. Its moment_arm field is not applied there. The supplied implementations do not establish the wrench reference point; do not infer that an absent cross product proves a missing moment without checking the provider contract. The r12 interface must explicitly resolve each force application point about instantaneous G exactly once.
- The abstract propulsion signatures omit explicit self parameters. This is an interface-definition weakness; Python ABC machinery does not itself validate overriding method signatures.
- The original main.py prints a greeting and does not demonstrate an integrated simulation entry point. This statement is limited to that inspected file, not an assertion that an exhaustive repository caller search is complete.
- The inspected PyThrust example evaluates prescribed RPM or equilibrium voltage outside the hopper plant. Its existence is not an integrated motor-lag model, calibrated coaxial map or dependency-capability result.
- The inspected cylindrical Aerodynamics model defaults to a longitudinal +x tube and returns zero loads immediately at zero translational airspeed, before its rotational damping calculation. That behavior needs an explicit fixture if the model is retained. Its cylinder assumptions are not a validated aerodynamic description of the required exposed multi-member structure. Do not silently import it into r12 as vehicle aerodynamics.

References: Hopper 14e30e1ebe2d4de4b1803248e2bfa0e3 r1; Aerodynamics b913670059ca4776ab422b0c47a70b87 r1; main ed76246a4e164496ab349ba3dedb6b64 r1; PyThrust example 0389bcc64b1547ec8238faea6c8b5f07 r1.

## 2. Convention migrations distinguished from defects

The original DCM algebra, after correcting its variable-name defect, returns the body-from-local direction. That direction is not intrinsically incorrect. The original quaternion-rate matrix is consistent with the scalar-first Hamilton right-product form; it must not be labelled defective merely because the replacement expresses the same operation differently.

The original body-resolved velocity equation includes `-omega cross velocity`, appropriate to that velocity representation. The selected r12 state instead carries local NED velocity of instantaneous complete-vehicle G. Its derivative therefore uses `R_LB F_B/m + [0,0,g]` without that body-coordinate transport term. This is a coordinated schema migration, not a one-line sign fix.

Required explicit migrations are:

1. Version numeric state ordering, velocity frame, origin and SI units.
2. Make Euler initialization keyword-only in radians; integrate attitude with quaternions.
3. Name the DCM direction explicitly and test transpose/inverse identities.
4. Preserve raw quaternion samples for norm-error measurement. Local normalization for constructing a rotation must not silently rewrite stored solver state.
5. Replace separate mass/CG/inertia calls with a consistent full mass-property snapshot, with complete installed mass counted once.
6. Replace time-only propulsion forwarding with actual rotor/gimbal-state evaluation and explicit external point loads/free couples.
7. Convert CG translation to fixed-datum scoring using both configuration offsets and their derivatives.

## 3. Historical repair recovery and caller reconciliation

Current readers have exposed the historical r9 implementations of helpers/math.py, simulation/state.py, simulation/simulation.py, chassis/hopper.py, propulsion/propulsion.py, propulsion/propeller.py and propulsion/actuators.py. Their headers cite historical decisions; those citations do not reinstate old authorization.

Inspected implementation features include immutable state snapshots, owned numeric serialization, package-relative imports, explicit full inertia and angular-momentum terms, a pure numerical RHS, actual solver-result return, held commands, explicit actuator states, motor lag, gimbal lag and command/state limits. These are inspected features, NOT verified outcomes.

The historical geometry has a material restriction: CoaxialGeometry assumes intersecting axes and computes hub points from a single fixed pivot plus R_BM times a module offset. The current r12 contract requires separate outer and inner joint origins. This is a documented historical limitation, not a reproduced arithmetic failure.

For a module-carried hub, the required position is:

`r_B0i = r_B0Ox + Rx(alpha) d_OxOy + Rx(alpha) Ry(beta) r_Oyi_M`.

The body-component derivative of the joint-offset term is `alpha_dot e_x cross (Rx(alpha) d_OxOy)`. The module-offset derivative additionally contains carried inner-axis motion. A single module angular-velocity cross product applied to both offsets is generally incorrect for separated origins.

Affected inspected callers for this reconciliation:

- CoaxialGeometry.application_points_B0_m.
- Propellor.hub_velocities_relative_air_M_m_s.
- Propellor.evaluate, which places forces and transforms aerodynamic couples.
- Simulation.evaluate, which samples environment at actual hub positions and supplies hub-relative flow to the paired map.
- Mass-property providers, which must use the same configuration and derivatives; their concrete implementations still need complete review.

Historical reader references: Simulation 1554320f8ece4ffb94555dec39b57b8b r1 and dd4f0efafe0241de9a7f131d530b9c6b r1; State 84f5e9300c4d469f8031fbf6d0c2f2f1 r1; math 1e6f6589619d4c48ad76b8b7deb0864e r1; Hopper 180358e2665649fbbcd3739defd50dbe r1; propulsion contract ce29e2f2be974024a02cda38b57a7029 r1; Propellor 19244a324ca6484fb23d689d4ee1b877 r1; actuators 08a1b4f57fff44eaa0864efbb8afdc00 r1 and 7ca431a9f23946b59b9051f8cbf9fda4 r1.

## 4. Analytical expectations to test, not test results

For a labelled coincident-axis fixture with pivot relative to G equal to [0,0,h], h>0, and collinear thrust lines:

- Neutral thrust is [0,0,-T] N; gravity is [0,0,+g] m/s² in L.
- With R_BM=Rx(alpha)Ry(beta), thrust is [-T sin(beta), T sin(alpha) cos(beta), -T cos(alpha) cos(beta)].
- Thrust moments are M_x=-h T sin(alpha) cos(beta), M_y=-h T sin(beta). Thus both small-angle control-effectiveness signs are negative for a bottom pivot.
- External aerodynamic rotor torque is R_BM[0,0,-sigma_i Q_i]. Opposite spin signs alone do not guarantee cancellation: the torque magnitudes must also match.
- Offset hubs, separated joint origins and configuration-dependent CG must use the general cross-product calculation, not the simplified fixture lever arm.

Whole-vehicle angular balance is `I omega_dot = M_ext - omega cross (I omega+h_rel) - I_dot omega - h_rel_dot`. Internal motor/servo reactions are not additional external moments. A reduced articulated model must identify every neglected relative-momentum and moving-mass contribution. Full inertia by itself does not establish complete articulated dynamics.

Fixed-datum conversion is `p_O=p_G-R_LB r_B0G` and `v_O=v_G-R_LB(omega cross r_B0G+r_dot_B0G)`. Test nonzero attitude, body rates and configuration-dependent CG offsets.

No fixture mass, inertia, travel, response constant or lever arm is selected as a vehicle input by these expectations.

## 5. Capability and verification ledger at this checkpoint

| Layer | Status established here |
|---|---|
| Repository/source availability | Relevant original and historical source text has been returned by readers. |
| Declared setup | Original pyproject.toml specifies Python >=3.13 and dependencies including NumPy, SciPy and pytest. Declarations are not installation evidence. |
| Interpreter/dependency/import capability | Not established by this checkpoint. Inspect actual backend execution and logs separately. |
| Original failure reproduction | Not established; findings above are source inspection. |
| Repaired numerical execution | Not established by the cited reader outputs. |
| Analytical verification | Not performed by this documentation action. |
| Vehicle/physical validity | Not established; geometry, mass, propulsion and response calibration remain unresolved. |

## 6. Remaining audit gates and next work

Before modifying recovered implementation code:

1. Reconcile the recovered historical audit and complete caller inventory using accessible current reader results; do not repeatedly read stale artifact/decision references.
2. Complete inspection of the historical environment module, concrete fixture/mass/performance providers, entry points, checker programs and any additional affected callers. Resolve the actual call graph, not just import names.
3. Preserve this checkpoint and add a subsequent audit completion/reconciliation artifact rather than erasing gaps or replacing historical evidence.
4. Write all new editable source/configuration under software/pdr_r12_plant using granted write_text. Retain an explicit migration map and reproducible entry point.
5. Run capability checks with command[0]='python', repository='6dof_hopper', sandbox workdir and bytecode writes disabled for supplied checkouts. Request missing installations through the Chief; do not install them.
6. Publish tested artifacts and retain editable artifact-bound verification programs. verify_command stdout must contain only VerificationResult JSON; diagnostics belong on stderr. Preserve actual measurements, logs and failed/inconclusive outcomes.

Required independent fixtures include initialization ownership, serialization, quaternion/DCM identities, nonzero attitudes, solver result/failure/event handling, gravity/thrust signs, full-inertia momentum balance, CG-relative wrench shifts, separated-origin hub kinematics, bottom-pivot signs, differential aerodynamic torque, motor lag, gimbal lag/limits, held-command purity and fixed-datum kinematics.

## 7. Vehicle-interface requests and control boundary

The Chief retains selection authority. Still needed for vehicle-specific integration: complete installed mass ledger; neutral and articulated CG/full inertia with moving-group ownership; actual outer/inner origin offsets and hub coordinates; foot/contact geometry; physical rotor spin assignments with viewing directions; paired thrust/torque/current maps and validity domains; loaded bus voltage and auxiliary-power model; loaded motor/ESC and servo response, rate/acceleration/travel limits; thermal limits; exposed-structure aerodynamics; and the intended reduced-versus-retained articulated-momentum treatment.

The historical actuator model uses a speed-response abstraction, not a demonstrated ESC PWM/voltage interface or evidence of hardware speed regulation. Retain that distinction and calibration boundary.

Proposed PID architecture remains specification-only: update controller memory once at fixed t_k; compute constrained allocation; hold commands over [t_k,t_k+1); carry accepted rigid-body and actuator endpoint states forward. Include anti-windup informed by allocation/saturation, filtered derivative feedback, explicit gain units and independently configurable limits. Do not mutate integrals in adaptive RHS evaluations. Numerical integration steps and output sampling times are not controller cadence.

No PID tuning, selected gains or vehicle closed-loop mission acceptance is authorized by this checkpoint. Those remain gated by accepted current PDR and a validated CDR plan.
