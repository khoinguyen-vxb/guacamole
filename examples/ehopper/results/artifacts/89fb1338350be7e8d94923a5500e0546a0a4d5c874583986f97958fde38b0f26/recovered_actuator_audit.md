# Recovered actuator calculation: source audit

Review date: 2026-10-11. Status: preliminary source inspection only; no execution, hardware validation or component selection.

## Evidence and scope

Reviewed the complete `chief_actuator_trade.py` text returned by reader request `6587a681207249a5a6d498223c9712c5`, tool_result revision 1, record SHA-256 `3c6bb6336391a91d8087c439388a892447ca047426e4212c342523d943caf451`. This is the runtime record hash, not a claimed hash of the source file.

The script reads `chief_propulsion_search_results.json` and filters for `Team_Hunter_RC_Squid_4008M-KV390`, `APC_20x8E`, and `assumed_4S_3000`. These are historical screening identifiers, not a current Chief-selected baseline. This audit does not validate that input file or its numerical results.

Authorized scope: approved r7 PDR work plan `b92477571f0f44019eb0c8a61817d627`, revision 1. Original files are unchanged.

## Findings

1. **Gyroscopic load classification needs correction.** The script computes each propeller angular-momentum magnitude and sums magnitudes before multiplying by tilt rate. This can serve as a triangle-inequality envelope for the included propeller contributions, but is not signed net momentum or the actual net common-gimbal gyro torque. It must not be passed to the plant as net vehicle torque.
2. **The envelope is incomplete.** Each propeller is assumed to weigh 0.030 kg, with all mass placed at a 0.254 m radius. That distribution bounds axial inertia only for the assumed propeller mass and radius. Motor rotating inertia, adapters and other rotating retention hardware are omitted. Consequently the calculation is not a demonstrated conservative bound for the complete rotating assembly.
3. **Individual loads do not disappear with net cancellation.** Opposing rotor angular momenta can reduce net common-gimbal gyroscopic effects while each motor bearing, mount and intervening frame member still transmits its own load. Structural load cases must retain signed individual rotor vectors and load paths as well as their resultant.
4. **Moving mass and inertia are assumptions.** The script uses 0.35 kg moving mass, 0.03 m moving-CG offset and 0.006 kg m^2 transverse inertia. These have not been reconciled with motors, propellers, mounts, nested gimbal members or retention. The outer axis may move a different assembly from the inner axis. Full tensors, reference points and configuration dependence are needed for coupled-axis loads.
5. **Thrust and gravity moments are scalar bounds.** Total thrust times a 0.005 m offset and m*g*0.03 m are useful preliminary magnitude bounds, not resolved two-axis load vectors. Actual thrust application points, pivot locations and gravity orientation are needed. Pivot-to-vehicle-CG arm is distinct from moving-module-CG offset and thrust-line offset.
6. **The linkage conversion is locally consistent, but not a linkage design.** For r = output angle / servo angle, the script uses servo torque = output torque*r/efficiency and servo speed = output speed/r. These relations are locally consistent for the stated ratio. A real linkage needs configuration-dependent Jacobians, stroke, singularity and efficiency checks. The assumed r=0.5 and efficiency=0.70 are unvalidated.
7. **Stall torque cannot establish duty capability.** A factor-of-two torque allowance does not provide a continuous torque rating. Loaded speed, current, supply voltage, holding and moving duty cycles, temperature limits, backlash and permitted peak durations are absent. No commercial servo is selected.
8. **Operating cases are incomplete.** Only historical hover and reserve points are evaluated. Simultaneous collective thrust and differential reaction torque, combined-axis motion, asymmetric rotor operation, spin acceleration/deceleration and saturation transients need separate cases.
9. **Resultant-cone interpretation is correctly cautioned.** The script explicitly says its 12-degree cone is not simultaneous independent 12-degree axis travel. Its output travel calculation is nevertheless a single-axis screening result, not a combined-axis mechanism-clearance check.
10. **Response values are placeholders.** Servo lag cases of 0.05, 0.10 and 0.20 s are merely stored assumptions; this script does not simulate or validate them. Motor/ESC response is not evaluated here.

## Required signed interface

Use explicit SI quantities and the Chief-reported preliminary convention: FRD body frame, neutral module axes aligned with body axes, R_BG = Rx(alpha) Ry(beta), with thrust along negative module z. This convention is attributed to the current Chief/CAD inbox messages; the associated decision contents still require direct review before baseline consolidation.

Define e_z = [0,0,1] in module coordinates. Define s_i by the right-hand rule about positive module z; positive spin appears counterclockwise to an observer on the positive-z side looking toward the origin. Map vendor CW/CCW labels to this convention explicitly rather than assuming their viewing direction.

For each rotor, retain J_i in kg m^2, nonnegative relative shaft speed omega_i in rad/s, and h_i,G = s_i*J_i*omega_i*e_z. The rotor-spin contribution to net momentum is the signed sum, transformed through R_BG. Equal speeds alone establish neither momentum cancellation nor aerodynamic torque cancellation.

For fixed relative rotor speeds, the idealized precession torque on each rotor includes Omega x h_i; its support reaction has the opposite sign. Sum vectors for the net effect, while preserving individual support reactions for bearing/frame sizing. Variable rotor speeds and moving-frame dynamics require angular-momentum derivatives and consistent multibody bookkeeping. These expressions alone are not a complete gimbal dynamics model.

Report signed air-on-rotor aerodynamic torque separately from motor electromagnetic torque and support reaction. Do not add both an internal motor torque and its equal-and-opposite reaction as external whole-vehicle torque. Each tilted external aerodynamic torque vector is R_BG*[0,0,Q_air_i].

Resolve thrust moments as r_i x F_i using positions relative to the relevant pivot or vehicle CG. State which reference point is used. Do not conflate gimbal drive torque with vehicle attitude-control moment.

## Preserved historical screening parameters — not selections

- Pivot-to-vehicle-CG arm cases: 0.15, 0.25, 0.35 m.
- Resultant tilt-cone half-angle: 12 degrees.
- Moving mass: 0.35 kg; moving-CG offset: 0.03 m.
- Thrust-line offset: 0.005 m.
- Moving transverse inertia: 0.006 kg m^2.
- Tilt acceleration: 8 rad/s^2; tilt rate: 1 rad/s.
- Friction torque allowance: 0.05 N m.
- Each propeller mass: 0.030 kg; radius: 0.254 m.
- Output/servo angular ratio: 0.5; efficiency: 0.70.
- Actuator torque multiplier: 2.0.

## Conditions before numerical reuse

Review the historical propulsion configuration, solver and results provenance; establish current candidate masses and performance domains; retain missing mounting and retention dimensions as unknown; exchange actual geometry and moving-body mass properties with CAD; and obtain continuous actuator/load evidence or explicitly provisional sensitivity cases.

A subsequent editable calculation must report signed net gyro effects separately from individual support loads, include all rotating inertia or expose its uncertainty, and calculate electrical demand and thermal/duty checks without treating stall ratings as continuous capability. Artifact-driven arithmetic/model verification must remain distinct from unperformed physical validation.

This audit establishes no purchase-budget pass, endurance pass, servo suitability, fabrication release or PDR acceptance.
