# Recovered actuator-model source audit

Review date: 2026-10-11 (Australia/Sydney).
Scope: preliminary PDR source inspection only; no execution, hardware validation, component selection or acceptance is claimed.

## Inspected evidence

Original file: `results/analysis/chief_actuator_trade.py`.
The complete source was supplied in current read result `0fe7a17ecf394f7d9410bdf81fa795f5`, revision 1, record SHA-256 `3c6bb6336391a91d8087c439388a892447ca047426e4212c342523d943caf451`. This is the runtime record hash, not a claimed file-content hash.
Relevant source locations: `main()`, reference-row filtering, `assumptions`, the hover/reserve loop, `momenta`, `gyro_bound`, `load_terms`, and `servo_torque`.

## Findings and required treatment

1. **Historical candidate is hard-coded, not currently selected.** The script filters `chief_propulsion_search_results.json` for Team_Hunter_RC_Squid_4008M-KV390, APC_20x8E and assumed_4S_3000, requiring exactly one row. Neither this filter nor the historical `ranked_nominal_feasible` label establishes current feasibility, provenance or Chief selection. Inspect the actual propulsion model, configuration and results before reusing numbers.

2. **Signed net momentum is absent.** The script computes positive propeller momentum magnitudes and sums them. For a common rotor axis, define signed spin speed by the right-hand rule about positive module z: positive spin appears counterclockwise to an observer on the positive-z side looking toward the origin. Use `H_i = J_spin_i * omega_i * e_zG` and `H_net = sum(H_i)`, transformed to the frame in which dynamics are evaluated. Opposite rotation alone does not ensure cancellation: both inertia and speed matter. Product CW/CCW labels require their own verified viewing convention.

3. **Net gyroscopic effects and individual loads must remain separate.** `sum(abs(H_i))*tilt_rate` can bound the magnitude of gyroscopic torque when all relevant angular rates and inertias are included. It is not the actual signed pair torque. Individual motor bearings, mounts and intervening frame members can experience substantial loads even if net momentum cancels. Report each rotor's vector moment and the combined moment, with load paths and reference points. Include module motion relative to the body and body motion relative to the inertial frame; the historical scalar tilt-rate allowance does not cover arbitrary combined motion.

4. **Rotating and moving inertia are incomplete.** The script uses `m_prop*R^2`, placing assumed blade mass at the tip. This is an upper-bound construction for that assumed propeller mass and radius, not measured inertia. It omits motor bell/rotor, hub and rotating retention inertia. Moving transverse inertia is separately assumed as 0.006 kg m^2, without a mass-property derivation. Obtain configuration-dependent moving masses, CGs and inertia from CAD, avoiding omission or double counting of rotating components and parallel-axis terms.

5. **Scalar loads are screening bounds, not simultaneous multibody loads.** Thrust-offset load is `T*0.005 m`; gravity load is `0.35 kg*g*0.03 m`; acceleration load is `0.006 kg m^2*8 rad/s^2`; friction is 0.05 N m. These are assumptions. Gravity uses a maximum moment-arm magnitude rather than a configuration-specific vector cross product. Sum-of-magnitudes loading may be conservative, but is not proof that the assumed inputs bound the real mechanism. Include actual thrust application points, moving CGs, axis offsets, nested-gimbal coupling, aerodynamic tilt moments, cable forces and bearing friction. Separate holding, transient and repeated-duty cases.

6. **Linkage conversion is conditionally consistent.** For `r = d(theta_output)/d(theta_servo)`, the idealized conversion `tau_servo = tau_output*r/eta` and `omega_servo = omega_output/r` is consistent with power balance. The historical values r=0.5 and eta=0.70 are assumptions. Actual linkage ratio, efficiency, backlash, travel, force and singularity margins must be evaluated throughout travel. A single constant ratio does not establish packaging or joint-load feasibility.

7. **Stall torque cannot establish continuous operation.** The factor-of-two torque allowance is not a thermal or duty-cycle model. Required evidence includes servo supply voltage, torque-speed behavior, current under load, holding and transient duty, thermal limits, loaded response, and regulator peak/continuous capacity. Servo energy must enter the mission budget, including regulator losses. No commercial servo is selected by this audit.

8. **Travel and lever arm remain screening inputs.** Historical 12-degree travel represents a resultant thrust-vector cone, not simultaneous independent 12-degree axis limits. For the communicated `R_BG=Rx(alpha)Ry(beta)` convention, the cone condition is `cos(alpha)*cos(beta) >= cos(theta_cone)` within the intended small-angle domain. The historical 0.15/0.25/0.35 m pivot-to-CG cases are sensitivities, not achieved geometry. Use CAD-reported geometry before consolidating vehicle moments.

9. **Propulsion and yaw allocation remain upstream dependencies.** The two historical operating points do not establish simultaneous collective-thrust and differential-torque authority. Evaluate feasible rotor operating-point pairs subject to shared battery sag, per-rotor current, voltage, speed and thermal constraints. Keep signed air-on-rotor aerodynamic torque distinct from spin-acceleration reaction loads and use a consistent angular-momentum formulation to avoid double counting.

## Disposition

Retain the source as historical analytical evidence; do not modify the original. Reuse the linkage identities and explicitly labelled conservative bounds, not the historical candidate selection or unsupported numerical loads. A revised editable calculation must expose signed rotor inertia/speed, individual bearing loads, actual moving mass properties, thrust offsets, linkage behavior, duty limits and simultaneous thrust/yaw operating cases. Its arithmetic checks must remain separate from unperformed physical validation.

This audit contains no new supplier prices, dimensions, availability claims, computed performance results or verification passes.
