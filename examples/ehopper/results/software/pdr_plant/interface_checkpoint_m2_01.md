# PDR plant: early candidate interface checkpoint

Date: 2026-10-15. Task: pdr_plant_repair.
Authority: system model revision 2; validated work plan a37ef3716fce4eb2b2b35919d6cb0b97 revision 1.

**Status: proposals for Chief disposition, not selected conventions, vehicle parameters, requirements or verification.** This checkpoint precedes completion of the current pre-edit audit. It does not modify implementation code, remove analytical-only guards, adopt archived geometry, or claim physical validity. PID integration and mission simulation belong to this run's PDR scope, but follow this task's audit, repair and analytical regression. Archived CDR gates do not govern.

## 1. Current evidence and remaining inspection

Current references are identified below by kind, ID, revision and record SHA-256; these are record hashes, not file hashes.

- System authority: system_model:system r2, 4c93f9bb676b0e59572034a4c2f51438a8d94cd2aa7d9af7830964ee72219b21.
- Work plan: decision:a37ef3716fce4eb2b2b35919d6cb0b97 r1, 8e7cf79a28ee431b8be3dfece7bf4fca94e60e40a2fa62a0e416e3e4e171772d.
- Actual original Simulation text: tool_result:a6183d153c3e40afa9dd736a087de35f r1, 818320759a30e60fcc2fbf2d296ec6d468626047fefcffbbbd0feb9471efa9f4.
- Actual recovered Simulation, first excerpt: tool_result:1af88f1ce8904313aad614cd362ae0ab r1, f701bc2638e81864989715654729ec224c4358d695476c1e388756bac64aa2e3.
- Recovered Simulation continuation: tool_result:e387022758704935b4fa58a1e55df093 r1, 2e9d204038c731695a20cfb086efd733ab073aae75e1e258a92a2a8a78db0863.
- Current static candidate caller index: tool_result:fd2da8c9acc943619b26d92756955429 r1, d1e61669b990cfb8cc25f455b54a4483838854412cf8b90dfb0593af7e8739b3.
- Actual setup declaration: tool_result:fbb27f22399941b5a2e6990981ee6f26 r1, deba66b3b1d60b7bc173fa6d6142f69f890b68c9e68805542663ca731da97e38.
- Archived proposal used only as a lead: source:a1f744d95b264a00a05d72ebfe307168 r1, 164a1ee41106deec898d9da985eec2e9bd03477cfbfa211f069ddf4f81763f7f.

The current inventory execution reported 8,873 inventoried files and 55 candidate calls. It imported no target module and performed no analytical verification. Its embedded revision-1 authority identifies its creation context, not present authorization. It remains a bounded static discovery aid, not proof of complete dynamic caller coverage. Existing bytecode directories were explicitly excluded; their presence does not establish writes by this task.

The original Simulation text corroborates discarded constructor state, undefined self.time, array/object and update_state call mismatches, an inconsistent Euler call, reset initial components and a discarded solver result. These are source observations, not newly reproduced failures. The recovered Simulation exposes immutable initialization, explicit vector decoding, held-command evaluation, provider interfaces and actual solver-return handling, with an explicit analytical-fixture guard. Supporting modules and every discovered affected caller still require current inspection before modification. Setup declarations and successful inventory execution do not establish NumPy/SciPy imports or repaired-plant execution.

**No current plant regression VerificationResult or vehicle-validity evidence is available for this checkpoint.** Archived test counts and measured errors are not substituted. Subsequent publication and tests must supply exact current artifact and evidence Refs.

## 2. Candidate mathematical contracts

### Preferred candidate for review: explicit NED/FRD, instantaneous-CG translation

- Local L: fixed launch frame, North-East-Down. Body B: airframe-fixed Forward-Right-Down.
- Scalar-first Hamilton q_LB=[w,x,y,z]; R_LB maps body components into L. Quaternion rate is qdot=0.5*q_LB tensor-product [0,omega_B]. Identity attitude is upright, forward north.
- Named Euler initialization in radians: R_LB=Rz(yaw) Ry(pitch) Rx(roll). This also permits the approved combined recovery initialization Ry(10 deg)Rx(10 deg), without changing its definition.
- Translate instantaneous complete-vehicle CG G using p_G,L [m] and v_G,L [m/s]. Integrate airframe angular velocity omega_B [rad/s]. Gravity is [0,0,+g] in L; neutral rotor thrust is along module -z.
- Preserve raw integrated quaternion components. A rotation helper may normalize a local copy after rejecting a zero/invalid quaternion; it must not project stored solver samples or conceal norm drift.
- Use an explicit versioned state schema. The recovered 19-component layout is a reuse candidate: p_G,L(3), v_G,L(3), q_LB(4), omega_B(3), two rotor-speed magnitudes, two gimbal-demand filter states and two actual gimbal angles. Its last six components describe a particular analytical actuator realization, not a mandatory vehicle state count.

Alternatives: an up-positive local/body convention, or translation directly at the fixed airframe datum. Either can be valid, but requires coordinated changes to transforms, gravity, thrust, events, velocity definitions and callers. Fixed-datum translation additionally requires consistent moving-CG acceleration terms. Prefer the explicit recovered convention for reuse only after Chief disposition and independent checks; convention consistency is the reason, not archived authority.

### Fixed scoring datum and CAD conversion

Let O_B0 be a physically identified airframe-fixed datum; let r be the vector from O_B0 to instantaneous G, expressed in B, with body-component derivative rdot. Then:

p_O,L = p_G,L - R_LB*r
v_O,L = v_G,L - R_LB*(omega_B cross r + rdot).

Height rise and horizontal displacement use this datum's stationary pre-takeoff position, as required by model revision 2. A CAD feature origin, stationary mounting feature, or neutral-CG-defined material-fixed point are candidates; CAD must identify the chosen point and how it remains fixed during articulation. Do not replace it with the changing CG.

If CAD frame C is forward-left-up, propose R_BC=diag(1,-1,-1) and r_B0=0.001*R_BC*(p_C-D_C), with p_C and fixed datum D_C in mm. Otherwise export the actual proper rotation and translation instead of forcing this convention. Inertia rotation and unit conversion must state the original mass and length units and reference point; kg mm^2 converts to kg m^2 by 1e-6. A reference-point change needs a parallel-axis calculation, not rotation alone.

An exact datum acceleration additionally needs rddot:

a_O,L = a_G,L - R_LB*[omegadot cross r + omega cross (omega cross r) + 2*omega cross rdot + rddot].

The inspected recovered Simulation does not establish a complete provider for these articulated derivatives.

### Separated common-gimbal origins

Candidate: outer rotation alpha about body x and inner rotation beta about carried y, R_BM=Rx(alpha)Ry(beta). Export outer origin r_B0Ox, outer-to-inner offset d_OxOy expressed in the outer frame, and each hub offset r_Oyi,M. All translations are in m after explicit CAD conversion.

r_B0i = r_B0Ox + Rx(alpha)*d_OxOy + R_BM*r_Oyi,M.

The offset derivative is alpha_dot*e_x cross [Rx(alpha)*d_OxOy]; the hub-offset derivative uses omega_MB,B=[alpha_dot, cos(alpha)*beta_dot, sin(alpha)*beta_dot]. Do not apply inner-axis motion to the outer-to-inner offset. Zero separation is a special configuration, not an implicit assumption. An alternative rotation order is permissible only with explicit geometry and caller migration.

Stable upper/lower IDs follow physical components. Define spin signs about the same module +z axis; purchased CW/CCW labels require a viewing direction. No physical spin assignment is selected here.

## 3. Minimum provider interfaces and ownership

| Interface | Required information | Unavailable values must remain explicit |
|---|---|---|
| Assembly kinematics | Actual angles, rates and needed accelerations; signed rotor speeds/accelerations; joint origins and hub offsets; units, ordering and schema | Loaded joint dynamics and physical spin assignments |
| Complete mass snapshot | Installed mass once; CG and its body-component derivatives; symmetric physical full inertia about G; I_dot; relative angular momentum h_rel and its body-component derivative; moving-group ownership and provenance | CAD values, rotor inertias and omitted-term error bounds |
| Paired propulsion map | Evaluate both actual rotors together using density, hub-relative airflow, spacing and relevant electrical/thermal state; return per-rotor thrust, external aerodynamic torque and supported current/power quantities | Coupled performance, calibration, RPM/torque data and continuous thermal capability |
| Motor/ESC realization | Command type/units/protocol, actual dynamic states, mapping to voltage/torque/speed, delay, acceleration/braking and saturation; loaded voltage/current/thermal domains | Calibrated command mapping and response |
| Common gimbal realization | Command convention, actual states, linkage ratio, travel/cone/rate/acceleration limits, load-dependent torque/speed, supply and mechanical losses | Continuous loaded actuator capability; stall ratings are insufficient |
| Environment/electrical | Gravity, density and wind at actual hubs; explicit external point loads/couples; shared-bus voltage, auxiliary demand and energy ownership | Sag, SOC/temperature evolution, usable energy, wake/ground effects |

Whole-vehicle angular balance candidate:

I_G*omegadot = M_external,G - omega cross (I_G*omega + h_rel) - I_dot*omega - h_rel_dot.

All terms must arise from one consistent assembly model about instantaneous G. If any provider term depends on unknown accelerations, solve that coupling rather than treating it as an independent prescribed input. Internal motor and servo reactions are not additional external whole-vehicle torques. A frozen rigid fixture, prescribed internal motion, and a reduced articulated approximation are distinct model modes requiring explicit assumptions and tests.

For rotor i, with nonnegative thrust T_i and aerodynamic drag magnitude Q_i:

F_i,B=R_BM*[0,0,-T_i]
tau_air,i,B=R_BM*[0,0,-sigma_i*Q_i]
M_external,G=sum[(r_B0i-r_B0G) cross F_i,B + tau_air,i,B] plus other external loads.

Resolve each load once about G. Opposite spin does not establish equal torque or cancelled gyroscopic momentum. No doubling of isolated thrust is authorized. Require coupled-map domain/provenance flags, separate thrust/torque interference parameters, uncertainty and explicit unsupported quantities. Battery-branch current is not motor winding current; aerodynamic shaft power alone does not close transient electrical energy.

The recovered speed-demand lag model is suitable only as a labelled analytical abstraction until a realizable speed-control mechanism or motor/ESC command model is supplied. Alternatives are calibrated throttle/pulse-to-dynamics mapping or an explicitly modelled speed loop. Changing a scope label does not implement either.

A future controller owns its memory outside adaptive RHS evaluations, samples at explicit fixed times, holds immutable commands between samples and carries every accepted endpoint state. Events and failed solves require explicit disposition. Output sampling and solver steps are not controller cadence.

## 4. Focused additional-criteria proposals — not requirements

Existing model-r2 mission and attitude definitions remain unchanged. The following are starting points for Chief review and, where acceptance is intended, human agreement followed by requirements/model reconciliation.

### Numerical convergence: can be discussed before hardware selection

- Candidate raw quaternion norm criterion: max(abs(norm(q)-1)) <= 1e-8, assessed on unprojected accepted samples, event states and refined dense-output grids.
- Compare a baseline with at least two refinements of integration step/tolerances and independently refined scoring grids. Hold controller cadence and reference definitions fixed during solver convergence tests.
- Candidate adjacent-refinement differences: tracking RMS/max <= 0.01 m; attitude metrics <= 0.1 deg; touchdown foot speeds <= 0.01 m/s; acquisition, first-contact and recovery times <= 0.01 s; complete-mission energy <= 1% of the refined value, with an absolute criterion for near-zero comparison quantities.
- Report all differences and raw errors; passing difference thresholds alone is not proof of mathematical convergence. Include discontinuity/event handling and extrema resolution. Specific solver settings remain a study configuration, separate from acceptance thresholds and physical calibration.

### Disturbance and saturation: define after preliminary vehicle authority is known

- Candidate applied-load tests: separate positive/negative horizontal force pulses at G of 0.05*m*g N for 1 s; separate body-axis moment pulses of 0.05*m*g*L_ref N m for 0.5 s. These are simulation loads, not a wind-speed claim.
- L_ref must be explicitly defined using current geometry and cannot be inherited from an archived lever arm. CAD/propulsion must assess simultaneous thrust/moment authority, permissible excursions and electrical/thermal domains before the Chief proposes final amplitudes.
- Candidate recovery rule: within 5 s after removal, enter the existing maximum fixed-datum position bounds and 2 deg/2 deg/s attitude/rate bounds simultaneously, then remain for 2 s. This would be an additional disturbance criterion, not a reinterpretation of nominal hover scoring. Report every transient excursion.
- Candidate saturation test: a 0.5 s infeasible request followed by feasible hover, separately exercising each relevant limit and a coupled case. Require bounded controller memory, no concealed state reset and the proposed recovery rule. Request infeasibility must not mean deliberately commanding unmodelled physical overload. Allocation priorities and safe transient bounds need Chief/human disposition.

### Contact and settling: CAD/compliance evidence needed first

- Model explicit normal stiffness/damping, compression travel, friction and per-foot terrain; retain parameter provenance and sensitivity. Detect first contact from actual foot geometry and evaluate each simultaneous contacting foot immediately before contact. A CG-plane event is insufficient.
- Candidate evaluation window: at least 5 s following first contact, extended if not settled. Candidate settled condition: all foot-point speed norms <= 0.02 m/s and compression-rate magnitudes <= 0.002 m/s for 1 continuous second, with defined final motor command, positive rotor clearance and no bottomed-out leg. These numerical values are proposals only.
- Terrain cases should include individual-foot height offsets and slopes in multiple azimuths. Select amplitudes only after CAD supplies support polygon, compression travel, full rotor envelopes and clearance sensitivities; do not choose an arbitrary terrain value that guarantees a pass.
- Clearance must cover both rotors throughout approach and settling, including geometry/tolerance/deformation assumptions. Physical leg and blade qualification remain unperformed.

### Reserve and hardware interfaces

Archived 20% thrust and usable-energy reserves are unselected leads, not current criteria. Ask the human only after propulsion reports coupled thrust/yaw authority at loaded-voltage/thermal limits and complete-mission usable-energy sensitivity. The denominator for energy reserve must be documented usable energy, not an unsupported nominal Wh value.

Controller/ESC/servo protocols, sensing/estimation, abort path, latency, achievable sample rate and supply/brownout limits remain hardware-interface inputs. Ideal simulation feedback must be labelled. This task does not select hardware or authorize firmware deployment.

## 5. Coordination and next disposition

CAD request 957e414803ff436a99ee7116d4f6797b and propulsion request 0915295599664e5a82b3cefbd600c695 are outstanding at writing. Their responses must be reconciled; this document does not imply their agreement.

Requested Chief decisions: mathematical frame/state conventions; fixed-datum selection method; separated-origin rotation convention; mandatory provider schemas and ownership; and the evidence needed before selecting a reduced vehicle model or calibrated command realization. Numerical geometry, gains, actuator parameters and propulsion performance are not part of the proposed convention decision.

Next plant work remains: complete current source/caller inspection, publish the pre-edit root-cause reconciliation and preservation baseline, establish actual dependencies/imports, reproduce original failures where practical, then reconcile a separate runnable copy and execute retained analytical checkers. All outputs stay in software/pdr_plant/; original checkouts and previous_run files remain unchanged, including no bytecode writes. Synthetic fixtures remain visibly distinct from selected vehicle data. Physical checks that programs cannot perform will be null, not inferred passes.
