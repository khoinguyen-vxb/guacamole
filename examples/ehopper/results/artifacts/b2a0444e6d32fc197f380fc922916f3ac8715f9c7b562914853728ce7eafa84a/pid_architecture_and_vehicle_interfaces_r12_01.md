# PDR r12: proposed PID architecture and vehicle interfaces

Date: 2026-10-13. Task: `pdr_r12_preliminary_plant`.

**Status: preliminary proposal, not an engineering selection or implemented controller.** Work-plan decision `66c7448f443f44ac9a016a1b384593a2` revision 1 authorizes this document. No gains are selected or tuned. No vehicle closed-loop mission is run. Controller implementation, tuning and mission acceptance remain gated on accepted current PDR and a subsequent validated CDR plan. The Chief owns vehicle, propulsion, structural and procurement selections. This document makes no installation changes and does not modify the repaired plant, supplied checkouts or historical outputs.

## 1. Governing records and evidence boundary

- Frame decision `f046cc4fe5294a6f9a61027529056f61`, revision 1: NED/FRD, scalar-first Hamilton quaternions, instantaneous complete-vehicle CG translation and fixed structural datum.
- Gimbal convention decision `28e10be57d6548a3aa5be06c96f6d0d0`, revision 1: retained common two-axis gimbal, separated joint origins and differential external aerodynamic rotor torque. This selects mathematical conventions, not numerical vehicle geometry.
- `REQ-SIMULATOR-PID`, revision 1: repaired plant, explicit actuator dynamics, fixed-cadence PID, anti-windup and filtered derivative.
- `REQ-SIMULATION-ACCEPTANCE`, revision 1: agreed fixed-datum tracking, attitude-recovery and first-foot-contact targets. These are targets, not achieved results or review acceptance.
- `REQ-PROPULSION-PLACEMENT`, revision 1: both rotors below the structure; preserve the common gimbal.
- `REQ-VEHICLE-CONFIGURATION`, revision 3: current exposed-structure and CFRP-leg requirements. Neither a structure nor its numerical mass properties is selected here.

Existing registered evidence, each revision 1 and each with outcome **inconclusive**:

| Evidence ID | Observed boolean checks | Scope |
|---|---:|---|
| PDR-R12-PLANT-STATE-FRAME-MASS-VERIFICATION-02 | 83 true, 0 false; 4 null | State ownership, frame/quaternion identities, mass/momentum algebra and fixed-datum kinematics |
| PDR-R12-PLANT-PROPULSION-INTERFACE-VERIFICATION-01 | 151 true, 0 false; 4 null | Bottom-pivot signs, external wrench, separated origins, domain and actuator interfaces |
| PDR-R12-PLANT-SOLVER-OPEN-LOOP-VERIFICATION-01 | 146 true, 0 false; 4 null | Analytical trajectories, synthetic trim, actual solver returns, events and injected failures |
| PDR-R12-PLANT-ACTUATOR-RESPONSE-VERIFICATION-01 | 116 true, 0 false; 4 null | Synthetic lag, saturation, command switching and endpoint carry-forward |

The retained raw logs and digest are `PDR-R12-PLANT-RAW-CHECKER-LOGS-01` and `PDR-R12-PLANT-MEASURED-ERROR-DIGEST-MD-01`, revision 1. Their re-executions retain diagnostics; they do not replace or upgrade registered verification. The digest parser tabulates no individual measured rows for the state/frame checker; its raw diagnostics remain in the raw log. Do not interpret an empty table as zero measured error.

All these tests use labelled synthetic fixtures. Numerical tolerances are regression thresholds, not agreed vehicle acceptance limits. No test establishes loaded actuator capability, complete articulated dynamics, battery/thermal endurance, vehicle closed-loop recovery, physical validity or PDR/CDR acceptance. The earlier state/frame checker registration failed because it reported passed with null checks; reporting correction 02 preserves that history and retains the null checks as unperformed.

## 2. Coordinates, states and scoring

Local frame L is North-East-Down. Structure-fixed B is Forward-Right-Down. `R_LB` maps B components into L. `q_LB=[w,x,y,z]` is scalar-first Hamilton, with

`qdot_LB = 0.5 * q_LB ⊗ [0, omega_B]`.

Identity attitude is upright and forward north. Euler initialization, if used, takes named radians with `R_LB=Rz(yaw) Ry(pitch) Rx(roll)`. Gravity is `[0,0,+g]` in L; neutral rotor force is `[0,0,-T]` in B. CAD lengths are mm; plant lengths are m. `R_BC=diag(1,-1,-1)` and `r_B0=0.001 R_BC (p_C-CG_C0)`. The actual neutral complete-vehicle CAD CG_C0 must be supplied.

The current plant vector has 19 SI components:

| Slice | Quantity | Unit |
|---|---|---|
| 0:3 | Position of instantaneous complete-vehicle CG G in L | m |
| 3:6 | Velocity of G in L | m/s |
| 6:10 | q_LB, wxyz | 1 |
| 10:13 | Airframe angular velocity in B | rad/s |
| 13:15 | Upper/lower rotor speed magnitudes | rad/s |
| 15:17 | Alpha/beta demand-filter states | rad |
| 17:19 | Actual alpha/beta gimbal angles | rad |

Use the module's explicit `PLANT_STATE_SCHEMA` and `PLANT_UNITS`; do not reinterpret legacy body velocities as local velocities. Preserve raw quaternion norm error in integration outputs.

The controller and mission scorer must use the fixed airframe datum O_B0, not G. For `r=r_B0G` and its component derivative `rdot` in B:

`p_O,L = p_G,L - R_LB r`

`v_O,L = v_G,L - R_LB (omega_B × r + rdot)`.

Height rise is `h(t)=p_O,L,z(t_initial)-p_O,L,z(t)`. Horizontal displacement is relative to the same datum's stationary pre-takeoff position. Current `fixed_datum_kinematics` supplies position and velocity conversion.

An exact acceleration conversion additionally needs a consistent `rddot`:

`a_O,L = a_G,L - R_LB [omegadot × r + omega × (omega × r) + 2 omega × rdot + rddot]`.

The present mass interface supplies r and rdot, not a complete vehicle rddot provider. Do not assume that fixed-datum acceleration equals CG acceleration during articulation. A future implementation must either extend this interface consistently or document and bound a reduced approximation.

## 3. Proposed scheduling and ownership

A discrete outer runner owns controller memory, reference generation, mode transitions, logging and scoring. The ODE RHS owns none of these.

1. Define sample instants by integer indices, `t_k=t_start+k*T_c`, rather than accumulated floating-point additions.
2. At t_k, obtain one accepted plant/estimated state and compute fixed-datum feedback. Initially any feedback would be ideal state feedback; no sensor or estimator implementation is implied.
3. Evaluate each scheduled control loop exactly once. An outer position loop may run at an integer multiple of T_c. Keep explicit timestamps for references and measurements.
4. Allocate the requested force/moment objective and create one immutable `HeldCommand` containing rotor speed magnitudes and gimbal angles.
5. Hold that command over `[t_k,t_(k+1)]`; call `Simulation.solve_ode` with explicit numerical settings and the interval endpoint included in requested output times.
6. Inspect the actual solver result. For an event-free completed interval, decode its endpoint with `unpack_state(..., schema=PLANT_STATE_SCHEMA)` and construct the next Simulation with both initial snapshots replaced. Carry all 19 states, including both gimbal filters and motor states. Repeated solves of the same instance otherwise restart from its original state.
7. Log requested, allocated, bounded and achieved quantities at accepted times. Never treat adaptive trial evaluations as accepted trajectory history.

A terminal event ends the interval: inspect event time and `y_events`, or validated dense output, rather than assuming the last requested output sample is the event endpoint. A solver/provider failure must stop that scenario and retain diagnostics; it must not generate an accepted endpoint.

Tentative cadence candidates for later study are T_c=0.01 s and a position-loop period of 0.05 s. These are **unselected proposals**, not validated hardware rates, gains or proof of stability. Loaded actuator bandwidth, sensing delay and computation latency must determine the eventual choice. Numerical `max_step_s` and output spacing are separate from controller cadence. Reducing T_c changes the discrete controller and requires a distinct study; reducing the ODE step alone must not add controller updates.

## 4. Proposed cascade and force/moment coupling

Proposed blocks:

- Fixed-datum position/velocity loops generate desired acceleration in L, with limited reference velocity and acceleration.
- Gravity and model-based feedforward convert this objective into a desired thrust direction and magnitude, accounting for nonpropulsive loads and the datum-to-CG distinction.
- An attitude-reference generator combines desired force direction, heading and predicted gimbal deflection. It applies airframe tilt and rate limits.
- Quaternion attitude error generates a body-rate request.
- A body-rate PID generates an external moment objective, with any momentum feedforward explicitly matched to the selected dynamics model.
- A constrained allocator produces the four available command coordinates: two rotor speeds and two common-gimbal angles.

For attitude error, a candidate convention is `q_err=conjugate(q_LB) ⊗ q_LB_ref`, selecting the equivalent quaternion with nonnegative scalar part for shortest-rotation feedback. Desired rates must be expressed in the same current B frame as measured rates. The sign convention needs independent fixtures before implementation is accepted.

**There are not six independently controllable wrench components.** Changing alpha/beta creates both lateral force and roll/pitch moment; differential rotor torque at nonzero gimbal angles also has non-axial body components. A controller must not demand arbitrary independent three-axis force and three-axis moment. One candidate allocator prioritizes vertical force and three moments while reporting the unavoidable lateral force; the outer attitude/position loops compensate using the coupled plant. Alternatively, a constrained weighted wrench allocator can report all six residuals. Either approach needs a current-geometry control-effectiveness/rank and stability assessment. No allocator is selected or implemented here.

The current speed-command abstraction is not an ESC PWM or voltage command. A future vehicle interface must provide a calibrated mapping or a realizable speed-regulation mechanism rather than assuming hobby ESCs internally regulate the requested speed.

## 5. Retained gimbal and aerodynamic torque allocation

Use `R_BM=Rx(alpha) Ry(beta)`: outer rotation about body x, inner rotation about carried y. Generalized rates are not components of a single angular velocity.

For upper/lower rotor i:

`r_B0,i = r_B0,Ox + Rx(alpha) d_OxOy + R_BM r_Oy,i,M`

`F_i,B = R_BM [0,0,-T_i]`

`tau_air,i,B = R_BM [0,0,-sigma_i Q_i]`

`M_ext,G = sum[(r_B0,i-r_B0,G) × F_i,B + tau_air,i,B] + other external moments`.

Here T_i and Q_i are nonnegative magnitudes and sigma_U=-sigma_L refers to the same module +z axis. Physical spin assignments and supplier viewing directions remain unresolved. Equal rotor speed does not establish equal thrust or cancelling torque.

For the labelled ideal fixture with coincident origins, collinear hubs, pivot `[0,0,h]` relative to G, h>0, and equal cancelling rotor drag:

`F_B=[-T sin(beta), T sin(alpha) cos(beta), -T cos(alpha) cos(beta)]`

`M_G=[-hT sin(alpha) cos(beta), -hT sin(beta), 0]`.

Near neutral, `dMx/dalpha=dMy/dbeta=-hT`. Positive roll/pitch moments therefore require negative small-angle gimbal deflections in this fixture. These signs were analytically checked; the historical top-pivot lever arm is not a vehicle input. Actual separated origins, off-axis CG and aerodynamic couples require evaluation of the full wrench, not reuse of the scalar approximation.

The module-axis aerodynamic torque is `-(sigma_U Q_U + sigma_L Q_L)`. For fixture signs `[+1,-1]`, increasing Q_L relative to Q_U gives positive module-z torque. Actual allocation must solve the simultaneous paired map for collective thrust and differential torque. Do not double isolated-rotor thrust or independently clip thrust/current/torque into an apparently feasible point.

Candidate allocation priority is vertical support, then roll/pitch stabilization, then yaw tracking, subject to hard domain constraints. This priority is for Chief review, not a selected failure-management policy. Record allocation residuals and infeasibility explicitly. Near zero thrust or a singular effectiveness matrix, do not divide by hT or conceal loss of authority.

Constraints must include joint travel, resultant cone, rotor speed and acceleration, loaded gimbal rate/acceleration/torque, shared-bus voltage/current, winding and ESC limits, thermal duration, paired-map validity and simultaneous thrust/yaw reserve. Unknown domain flags remain unknown. Static command limiting alone does not enforce dynamic electrical or thermal feasibility.

## 6. PID memory, anti-windup and derivative proposal

For a generic loop with error unit E and output unit U, store the integral contribution I_u in output units. One candidate discrete update is:

`I_u[k+1] = clamp(I_u[k] + dt * (K_i e[k] + (u_feasible[k]-u_requested[k])/T_t))`.

This is back-calculation with positive tracking time T_t in seconds. Compute the requested output using the existing memory, obtain allocation/limiting feedback, then perform one memory update for the next tick. An alternative is conditional integration: suppress only an integral increment that pushes further into the active infeasible direction. Select and test one explicit scheme, including coupled-axis behaviour; do not stack incompatible schemes without analysis.

The residual must have the loop's output units. For a moment loop use a moment residual, not raw differences in motor rad/s or gimbal radians. Propagate allocation and limiter residuals to outer loops through explicit mappings. Use requested-versus-bounded flags together with feasible-wrench information. Lagged achieved output is distinct from static saturation; any achieved-output tracking term needs a justified delay/filter model to avoid opposing normal transients.

Provide integral clamps, initialization, bumpless reference/mode transfer and documented disarm/reset behaviour. Do not reset actuator states at mode switches. Disable or bound integrations when the applicable feedback or allocation is invalid.

Candidate derivative filtering is derivative on measurement rather than reference:

`d_f[k] = a*d_f[k-1] + (1-a)*(y[k]-y[k-1])/dt`, where `a=exp(-dt/tau_f)` and tau_f>0.

Use `-K_d*d_f` in the feedback law, with separately defined reference feedforward. Initialize filter memory explicitly. For attitude damping use body-rate measurements where appropriate rather than differencing wrapped Euler angles. Rate-loop derivative requires filtered angular acceleration and a noise/latency assessment. Do not differentiate arbitrary quaternion component sign flips.

| Loop | Error | Output | Kp | Ki | Kd |
|---|---|---|---|---|---|
| Position/altitude PID | m | m/s^2 | 1/s^2 | 1/s^3 | 1/s |
| Quaternion attitude P | rad | rad/s | 1/s | not proposed | not proposed |
| Body-rate PID | rad/s | N m | N m s/rad | N m/rad | N m s^2/rad |

All gains, filter time constants, tracking times, clamps and selected cadence remain **unset**. A future configuration must refuse operation with missing required parameters; zero gains must not silently substitute for unknown gains. Proposed fields include frame/schema versions, per-loop gains with units, sampling periods, reference limits, allocation priorities, anti-windup mode, derivative filters, sensor delays and traceable actuator/map limits.

## 7. Reduced articulated-dynamics assumptions

The complete-vehicle angular balance used by the interface is

`I_G omegadot = M_ext,G - omega × (I_G omega + h_rel) - I_dot omega - h_rel_dot`.

All components are in B, inertia is about instantaneous G, and derivatives of I and h_rel are derivatives of B components due to internal motion. Mass includes all installed equipment and propulsion exactly once. Internal servo/motor torques are not additional external whole-vehicle moments. External aerodynamic rotor torque is retained; relative rotor acceleration and gyroscopic effects belong in consistent internal momentum terms.

Current limitations:

- The principal runnable fixtures use frozen rigid-body mass properties with synthetic values. They are not the complete articulated vehicle.
- `prescribed_internal_momentum` permits explicit consistent I_dot, h_rel and h_rel_dot, but an interface is not a derived or verified multibody provider.
- `reduced_articulated` explicitly omits h_rel and h_rel_dot. Configuration-dependent inertia alone does not restore omitted rotor/joint momentum or validate the approximation.
- Prescribed lagged gimbal motion is not a coupled joint-load solution. No servo torque capability, bearing compliance, backlash, linkage friction or structural flexibility is established.
- Counter-rotation is not proof of cancellation of spin momentum or gyroscopic loads, especially with unequal inertia/speed or time-varying commands.
- The synthetic paired map supplies analytical interference and current arithmetic, not measured rotor performance. Prescribed bus voltage, SOC and temperatures do not close sag, usable-energy or thermal dynamics.
- Electrical branch currents, winding currents and auxiliary consumers must remain distinct. Auxiliary power is counted once. Rotor acceleration power is not generally just aerodynamic Q times speed.
- Exposed-structure drag, wake interaction, ground effect, landing-leg compliance and ground contact remain unmodelled in the fixture path.
- Limit observations at output samples/dense midpoints are not continuous certification. Current explicit integration can reject inadmissible trial stages; there is no qualified hard-stop/contact solver.

Selecting a vehicle dynamics mode requires the Chief to assess omitted-term errors over the operating envelope. Do not bypass the analytical-only gate by relabelling vehicle numbers as synthetic fixtures.

## 8. Future verification mapping: agreed targets

These procedures are specifications for later authorized work, not completed tests.

**Hover and mission:** initialize a stationary pre-takeoff O_B0 position, climb to its 5.00 m vertical rise, acquire, then score one uninterrupted 300 s interval. Height RMS error <=0.10 m, maximum absolute error <=0.25 m; horizontal radial RMS <=0.25 m, maximum <=0.50 m. Do not remove transients within the scored interval or restart it silently. Record acquisition time separately. A candidate acquisition rule is remaining inside the agreed maximum position-error bounds for 2 s; this additional rule requires agreement.

Use time-weighted RMS over the specified interval and verify scoring resolution for extrema. Retain trajectories, raw quaternion norms, commands, actual rotor/gimbal states, force/moment, domain flags, winding/bus currents, temperatures and energy. Account for spool-up, climb, acquisition, hover, descent and reserve, not just 300 s hover. Integrate power as an explicit energy state or by converged quadrature of accepted trajectory data; never sum RHS evaluations.

**Attitude recovery:** isolated 10 deg roll, pitch and yaw perturbations plus combined 10 deg roll and 10 deg pitch, initially zero body rates. Document whether the combined perturbation is constructed as `Ry(10 deg) Rx(10 deg)` under the retained Euler convention and obtain agreement on that construction. Score total shortest-rotation quaternion error and body-rate norm. Reach <=2 deg and <=2 deg/s within 5 s and remain within both for 2 s. A useful total-error formula is `2 atan2(norm(q_err.vector), abs(q_err.scalar))`. Preserve the equilibrium definition and all actuator initial states; synthetic trim is not vehicle trim.

**Landing:** detect the first descending foot/ground crossing from actual foot locations, not the CG-plane event used by the analytical checker. Immediately before first contact, contacting-foot down speed <=0.30 m/s, horizontal speed <=0.20 m/s and airframe tilt <=5 deg. For simultaneous contacts, report each contacting foot. Body tilt is `acos(clamp(e_down,L dot R_LB e_z,B,-1,1))`; it is not gimbal tilt. Both rotor envelopes must remain clear throughout approach and settling.

For a foot point r_i relative to O_B0, its velocity is `v_G + R_LB[omega × (r_i-r_G) + rdot_i-rdot_G]`. A rigid airframe-mounted foot has rdot_i=0; a compliant leg does not. Contact and settling require ground geometry, stiffness/damping, friction and leg-deflection assumptions. Merely detecting a root is not a validated impact model.

## 9. Additional numeric proposals requiring Chief/human agreement

No entry below is a recorded acceptance requirement or selected vehicle value.

| Proposed criterion | Candidate definition |
|---|---|
| Raw quaternion norm | Maximum abs(norm(q)-1) <=1e-8 over accepted samples, events and a refined scoring grid; no projection before scoring |
| Numerical convergence | Halve max_step and tighten rtol/atol tenfold; changes in tracking RMS/max <=0.01 m, attitude-error metrics <=0.1 deg, contacting-foot speeds <=0.01 m/s and total energy <=1% |
| Disturbance cases | Separate +/-north and +/-east force pulses at G of 0.05*m*g N for 1 s during acquired hover; separately +/-body-axis moment pulses of 0.05*m*g*L_ref N m for 0.5 s, with L_ref explicitly chosen from current geometry |
| Disturbance recovery | Within 5 s of pulse removal, return inside the agreed maximum tracking bounds and <=2 deg/2 deg/s attitude/rate bounds, then remain for 2 s; report every peak excursion |
| Saturation recovery | Apply a documented infeasible request for 0.5 s, then restore feasible hover; recover within the same 5 s/2 s bounds, with bounded integrals and no concealed state reset; define each limiting mechanism separately |
| Thrust reserve | At least 20% above weight at the worst accepted loaded-voltage/thermal state while retaining separately specified yaw authority; coupled-map calculation required |
| Usable-energy reserve | At least 20% of conservatively established usable energy remaining after the complete nominal mission; nominal pack Wh is not the denominator without a usable-energy model |

Disturbance cases are applied-load simulation fixtures, not a claim of a particular wind speed or a newly selected operating wind envelope. The moment reference length, permitted transient excursions, altitude safety constraints, yaw reserve and abnormal-mode disposition need explicit agreement. The Chief must reconcile reserve proposals with mass, procurement and budget feasibility. Analytical checker tolerances remain separate from these future vehicle criteria.

## 10. Unresolved vehicle-interface register for Chief handoff

This table records requests to carry into the next Chief communication; writing it does not imply the requests have been answered.

| ID | Required information | Why needed |
|---|---|---|
| VI-01 | Current complete installed-mass ledger; neutral CG_C0 in CAD mm; full density-weighted inertia about G; component ownership and uncertainties | Prevent omitted/double-counted mass and unsupported vehicle inputs |
| VI-02 | CG, CG rate and any required CG acceleration versus articulation; I, I_dot, h_rel and h_rel_dot; moving-group and rotor spin inertias; justified dynamics mode | Consistent datum scoring and whole-vehicle angular momentum |
| VI-03 | Outer origin, outer-to-inner offset, upper/lower hub offsets and spacing, thrust application assumptions, feet and ground coordinates, CAD-to-body provenance | Actual signed moment arms, gimbal kinematics and contact events |
| VI-04 | Physical rotor/motor spin assignments, viewing direction and purchased propeller mapping | External torque signs and differential authority |
| VI-05 | Coupled thrust/torque/current map, interference calibration and spacing/inflow/density domains; transient versus steady electrical assumptions | Feasible collective/yaw allocation rather than isolated-rotor doubling |
| VI-06 | Loaded motor/ESC command mapping, lag, acceleration/braking, delays, speed/current/voltage/thermal-duration limits | Realizable actuation and saturation model |
| VI-07 | Servo/linkage geometry, joint/cone travel, loaded rate/acceleration/torque, supply limits, backlash and friction | Gimbal response and hinge-load feasibility |
| VI-08 | Shared-bus sag, resistance, usable energy, SOC/temperature evolution, auxiliary and actuator power | Mission energy and electrical/thermal closure |
| VI-09 | Exposed-structure aerodynamic/wake/ground-effect assumptions and disturbance definitions | Nonpropulsive loads and operating-envelope assessment |
| VI-10 | Leg/contact compliance, damping, friction, terrain and settling model; rotor flex/clearance allowances | First-foot-contact scoring and rotor clearance |
| VI-11 | Sensor/estimator assumptions, measurement noise/delay, achievable cadence and command latency | Discrete-loop and derivative-filter design |
| VI-12 | Chief disposition and human agreement on Section 9, acquisition and perturbation construction | Avoid inventing acceptance criteria |

Independent analytical fixtures can proceed without filling these fields with invented vehicle numbers. Their absence prevents a vehicle-validity or mission-acceptance claim, but does not erase the recorded preliminary software evidence.
