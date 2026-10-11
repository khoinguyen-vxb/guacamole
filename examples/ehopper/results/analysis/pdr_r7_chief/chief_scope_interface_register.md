# r7 Chief scope and interface register

Status: preliminary PDR integration reference; not a selected component baseline, fabrication release, verification result or flight authorization.
Prepared: 2026-10-11.

## 1. Governing records

The following current records govern this document; their full Ref objects accompany the producing tool request.

| Record | Revision | Purpose |
|---|---:|---|
| b92477571f0f44019eb0c8a61817d627 | 1 | Validated parallel r7 PDR work plan |
| 0d7c37748d54451eac7d660e80a13cb9 | 1 | Scope disposition |
| f046cc4fe5294a6f9a61027529056f61 | 1 | NED/FRD Hamilton and CAD mass-property contract |
| 72ef86f229ea461f8f31f8a231a70fca | 1 | Preliminary common-coaxial-gimbal architecture |
| REQ-HARDWARE-BUDGET | 4 | Complete purchase accounting |
| REQ-VEHICLE-CONFIGURATION | 1 | Minimum exposed structure; no cosmetic shell |
| REQ-CAD-ASSEMBLY | 1 | Editable assembly, exports and interfaces |
| REQ-SIMULATOR-PID | 1 | Audited repairs and simulated PID integration |

Historical calculations and superseded worker proposals are not adopted merely because their files or messages remain available.

## 2. Scope and accounting boundary

Included: propulsion selection; complete purchased-vehicle BOM; installed mass and electrical demand; minimum exposed structural CAD; preliminary electronics, power/signal and harness interfaces; corrected simulator and simulated PID integration within the review-stage gates.

Excluded development: custom PCB, embedded flight firmware/builds, operational ground-station software and fluid-propulsion systems. Gazebo, ROS, MPC, machine learning, Raspberry Pi and ODrive development are not imported from the pendulum reference.

These exclusions do not remove purchased controller/sensors, command link, regulation/distribution, wiring/connectors, mounting or retention from the vehicle ledger. Candidate hardware/firmware compatibility with coaxial gimbal control and autonomous landing remains to be established; a runnable simulator is not flight firmware.

The complete vehicle purchase cost must be strictly less than AUD 500, excluding tax and shipping. Charge whole minimum purchasable packs, spools and stock lengths, including the mandatory two-battery purchase pack although only one battery flies. Distinguish purchased quantities from installed quantities. Price required reusable ground equipment separately and assume nothing is already owned. Unknown prices, FX or tax basis must remain visible; an incomplete estimate is not a budget pass.

Retain only justified load-carrying, mounting, alignment, retention, clearance and landing parts. Exclude fins, nosecone and cosmetic/aerodynamic enclosing shells. Vehicle-mounted guards, if subsequently required, must enter both purchase and installed-mass ledgers. Guarding remains unresolved, not silently waived.

## 3. Selected coordinate contract

Local frame L is North-East-Down with fixed origin at the launch-ground datum. Body axes B are fixed to the central structure: +x forward, +y right, +z toward the feet when upright.

R_LB maps body components into local components; R_BL = transpose(R_LB). The scalar-first Hamilton quaternion q_LB = [w,x,y,z] represents this orientation. Upright and forward north is [1,0,0,0]. For body-resolved angular velocity omega_B in rad/s:

qdot_LB = 0.5 * q_LB Hamilton-product [0,omega_B].

Explicit Euler interfaces use roll, pitch, yaw in rad and R_LB = Rz(yaw) Ry(pitch) Rx(roll); attitude integration remains quaternion-based. Gravity is [0,0,+g] in L, in m/s^2. Neutral propulsion force is [0,0,-T] in B, in N.

CAD axes C are +X forward, +Y left, +Z upward. CAD Z=0 is the nominal feet-contact plane; the horizontal datum must be documented by the CAD branch. FreeCAD lengths are mm. The proper CAD-to-body rotation is R_BC = diag(1,-1,-1), with determinant +1.

O_B0 is a fixed structural reference coincident with the complete vehicle neutral CG once computed. Its numerical CAD position CG_C0 is unknown, not assumed zero. For an articulated configuration a:

- Point coordinates about O_B0: r_B0(P,a) = 0.001 R_BC [p_C(P,a) - CG_C0], in m.
- Instantaneous complete-vehicle CG offset: r_B0G(a) = 0.001 R_BC [CG_C(a) - CG_C0], in m.
- Plant translation uses instantaneous complete-vehicle CG position p_G,L and velocity v_G,L in SI.
- Moment arms are relative to instantaneous G. Converting CG motion to fixed-datum motion must include configuration-dependent offsets and their time derivatives.

Report full inertia about instantaneous G. Density-weight raw geometric properties before unit conversion. Inertia already in kg mm^2 requires multiplication by 1e-6; then I_B,G = R_BC I_C,G transpose(R_BC). Apply the parallel-axis theorem when changing reference points. Do not silently use geometric inertia as mass inertia or replace the tensor with its diagonal.

## 4. Selected preliminary actuator architecture

A bearing-supported nested two-axis gimbal carries both coaxial rotors as one module. Two independent servos operate linkages; bearings and structural frames, not servo output shafts alone, carry primary propulsion loads. Collective operation supplies thrust; gimbal deflection and the actual CG-relative thrust line supply pitch/roll moments; differential signed rotor aerodynamic reaction torque supplies axial authority.

At neutral, module axes G coincide with B. Outer alpha rotates right-handed about +x_B; inner beta rotates about the outer frame's +y axis. R_BG = Rx(alpha) Ry(beta) maps module vectors into B. Angles are rad, rates rad/s and torque N m.

With e_B = R_BG [0,0,1], total propulsion force is F_B = -(T_upper + T_lower) e_B. Each thrust must come from a coaxial-aware model. If the resultant line passes through the pivot, its force moment is (p_pivot,B - p_G,B) cross F_B. Otherwise use actual application points and offsets rather than assuming this simplification.

Define each rotor's spin sign and signed air-on-rotor aerodynamic torque about +z_G explicitly, and transform the torque vector through R_BG. Equal speeds do not establish torque cancellation. Tilted differential torque is not purely body-yaw torque. Report simultaneous collective/differential authority under common electrical and thermal constraints.

Account consistently for rotor acceleration and articulated angular momentum. Internal motor/servo torques must not also be added as external whole-vehicle moments. Any reduced articulated-dynamics approximation must be stated and bounded. Counter-rotation does not establish zero individual bearing, frame or gyroscopic loads.

## 5. Screening values, NOT calibrated vehicle parameters

The actuator decision retains only the following preliminary search assumptions:

| Quantity | Screening values |
|---|---|
| Resultant tilt envelope | 12 degrees |
| Neutral pivot-above-CG target | 0.25 m; sensitivity cases 0.15 and 0.35 m |
| Tilt rate | 1 rad/s |
| Tilt acceleration | 8 rad/s^2 |
| Actuator lag cases | 0.05, 0.10 and 0.20 s |

For the selected rotation order the cone condition is acos(cos(alpha) cos(beta)) <= 12 degrees. Independent simultaneous 12-degree axis limits are not equivalent.

These values are not demonstrated travel, loaded response, duty capability or achieved geometry. No servo is selected by this register. CAD must report achieved three-dimensional pivot-to-CG geometry without undocumented ballast. Historical assumed rotor sizes, moving masses, inertias and servo-torque estimates are not current vehicle inputs.

## 6. Required branch exchanges

| Interface | Responsible branch | Required content | Status in this register |
|---|---|---|---|
| IF-COMPONENTS | Propulsion, reconciled with CAD | Exact variants, purchased/installed quantities, dimensions, mounting/hub/retention interfaces, masses, source URLs and access dates, currencies and units | Unresolved |
| IF-CAD-MASS | CAD | Installed mass ledger, densities and volumes, neutral CG/datum, configuration-dependent CG and full inertia with reference points; moving-assembly and rotating-component properties | Unresolved |
| IF-MECHANISM | CAD with propulsion | Pivot and thrust application points, offsets, linkage ratios/efficiencies, bearings, supported travel, combined-axis swept envelopes and tolerance/deflection allowances | Unresolved |
| IF-PROPULSION | Propulsion | Individual coaxial-aware thrust and signed aerodynamic torque maps, spin convention, operating domains and simultaneous limits | Unresolved |
| IF-ELECTRICAL | Propulsion, Chief integration | Battery usable energy/voltage model; motor/ESC current, voltage and thermal limits; avionics/servo demand; regulation/distribution and harness provisions | Unresolved |
| IF-RESPONSE | Propulsion with plant | Motor/ESC lag and actuator loaded response, rate/acceleration limits, saturation, backlash/duty limitations and calibration status | Unresolved |
| IF-AERO | CAD geometry with plant | Exposed-structure aerodynamic assumptions and uncertainty; no unsupported reuse of the cylindrical rocket-body model | Unresolved |
| IF-PLANT | Plant | Completed source/caller audit, original-to-repaired mapping, explicit state/frame interfaces, analytical fixtures and measured numerical checks | Pending branch evidence |
| IF-ACCEPTANCE | Chief with human | Numerical environment, tracking, attitude recovery, disturbance, saturation, touchdown and reserve criteria | Human agreement outstanding |

Unresolved entries mean this document does not establish the values; they do not claim that another branch has performed no work. Branch submissions must carry current artifact/evidence references before integration.

## 7. Verification and review gates

PDR work permits preliminary sizing/layout and audited minimal open-loop plant repairs. Preserve supplied checkouts. Complete the affected-caller audit and report root causes before edits. Analytical fixture parameters must remain separate from selected vehicle parameters.

The later controller architecture must use fixed-cadence updates with commands held between samples, explicit units/limits, anti-windup and filtered derivative feedback. Do not mutate PID integrals inside adaptive ODE RHS evaluations. PID tuning, detailed CDR work and closed-loop mission acceptance require a human-accepted current PDR and a subsequent validated CDR plan.

Retain editable verification programs, actual tested artifact inputs and numerical results. Use verify_command with tested artifact Refs and JSON-only VerificationResult stdout. Successful imports, process exit, CAD export or this document's creation are not geometry or physical acceptance.

No test pass is asserted here. Coaxial calibration, continuous propulsion/servo thermal capability, battery endurance, structural/joint properties, clearances under deformation, restrained testing and landing tests remain unperformed or unsupported until actual evidence is supplied. Numerical acceptance tolerances and protective-part dispositions require focused human agreement. Such agreement is not PDR/CDR review acceptance.

Next integration gates: receive branch artifacts; record supported Chief structure and propulsion choices; reconcile the common component/mass/energy/interface baseline; obtain outstanding human dispositions; assemble and verify the preliminary review package; then request PDR and await explicit review disposition.
