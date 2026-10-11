# r7 proposed simulation acceptance matrix

Prepared: 2026-10-11.
Status: candidate for plant-branch review and explicit human agreement. NOT an approved requirement, test result, PDR/CDR acceptance, fabrication release or flight authorization. No tests were performed in preparing this document.

## Authority and boundaries

This draft supports PDR-R7-INTEGRATED-REVIEW under work-plan decision b92477571f0f44019eb0c8a61817d627 r1. Governing requirements are REQ-HOVER-HEIGHT r1, REQ-HOVER-DURATION r1, REQ-OPERATING-CONDITIONS r1 and REQ-SIMULATOR-PID r1. The current frame and actuator decisions remain f046cc4fe5294a6f9a61027529056f61 r1 and 72ef86f229ea461f8f31f8a231a70fca r1.

PDR may establish analytical open-loop checks and propose these later tests. Controller tuning and closed-loop mission acceptance remain gated on human-accepted current PDR and a validated CDR plan. This draft does not select gains, control frequency, components, mass properties or calibrated response parameters.

Recommended candidate: use the numerical gates below for simulated-demonstrator evaluation, subject to human changes. Alternative: retain the same measurements as characterization only until numerical gates are agreed; characterization cannot establish mission acceptance.

## Measurement definitions

Use the recorded NED/FRD Hamilton convention. Proposed height reference is the fixed structural datum O_B0, measured relative to its own takeoff position, rather than an articulation-dependent CG altitude. With the existing CG-state contract:

p_O,L = p_G,L - R_LB r_B0G(a)
h = -(p_O,L,z(t) - p_O,L,z(0))

The required offset and its derivatives must come from the articulated interface; do not assume they are zero. Horizontal error is the radial displacement of O_B0 from the takeoff vertical line. Report CG motion separately. Ground contact uses the actual lowest landing-foot/contact geometry, not a test for CG height equal to zero.

Attitude error uses quaternion relative rotation with sign-equivalent quaternions treated identically. Tilt is the angle between structural body +z and local Down. Report heading error separately, wrapped consistently. Body angular rates use rad/s internally; degrees and degrees/s below are reporting units.

Compute RMS by time integration over each specified window, not an unweighted average of irregular solver samples. Evaluate peaks on a documented time grid and solver trajectory; check sensitivity to finer output resolution. Do not choose a favorable window after examining the result.

## Proposed nominal environment

For a reproducible nominal simulation, propose zero ambient wind, air density 1.225 kg/m^3 and gravity 9.80665 m/s^2. These are analysis assumptions for the confirmed calm-air, near-sea-level demonstrator, not a qualified environmental envelope. Temperature-dependent hardware capability remains unresolved. Do not translate force disturbances below into a wind speed without a supported exposed-structure aerodynamic model.

## Proposed numerical and mission gates

| Test | Defined case/window | Candidate acceptance |
|---|---|---|
| Analytical hover trim | Supported trim of the actual configured plant, neutral gimbal, zero motion; no ground force | Translational acceleration norm <= 1e-4 m/s^2 and angular acceleration norm <= 1e-4 rad/s^2; all commands within their documented domains. Failure to find trim is reported, not hidden by arbitrary external moments. |
| Quaternion norm | Every reported integration interval, including nonzero-attitude fixtures | Maximum absolute norm error <= 1e-6. Report raw pre-projection error separately if normalization is used; normalized output alone does not verify integration. |
| Nominal sustained hover | One contiguous 300 s window after an explicitly defined settling event | Height RMS error <= 0.10 m and peak absolute error <= 0.25 m about 5 m; horizontal RMS radial error <= 0.25 m and peak <= 0.50 m; structural tilt <= 5 degrees and absolute heading error <= 5 degrees throughout. |
| Attitude recovery | Separate initial roll +10/-10 degrees, pitch +10/-10 degrees and yaw +20/-20 degrees; one combined roll/pitch/yaw case of 5/5/10 degrees; nominal hover position and zero initial rates | Within 5 s, attitude error <= 2 degrees and rate norm <= 2 degrees/s, then remain within those bounds for 5 s. Peak height deviation <= 0.50 m and horizontal displacement <= 1.0 m; no ground contact. |
| Rate recovery | Separate initial body rates +20/-20 degrees/s about each axis at nominal hover attitude | Same recovery and excursion limits as attitude recovery. |
| Altitude tracking | Smooth 5-to-6 m and 6-to-5 m reference transitions, with explicit reference velocity and acceleration bounds | Within 5 s after each reference transition ends, absolute height error <= 0.10 m for the following 5 s; overshoot beyond endpoint <= 0.25 m; horizontal error <= 0.50 m. Reference profile must be fixed before testing. |
| Lateral disturbance | Apply an external force of 0.05 m g N at instantaneous CG for 1 s, separately in each signed horizontal local direction; m is actual configured total mass | Within 5 s after removal, regain nominal hover bands and remain there for 5 s; peak horizontal error <= 1.0 m and height deviation <= 0.50 m. This is a force-input robustness test, not a wind qualification. |
| Saturation recovery | Separate collective and gimbal command cases deliberately requesting beyond configured limits for 1 s, then returning to hover demand | Actual outputs remain within amplitude/rate limits. Record genuine clipping, integrator state and anti-windup action. Regain nominal hover bands within 5 s after release and remain for 5 s, without ground contact. Excursions: <= 1.0 m horizontally and <= 0.50 m vertically. Abort unsafe modeled trajectories and record failures. |
| Full mission | Takeoff, climb, qualifying hover, descent and contact; launch and terminal profiles fixed before execution | Achieve the complete qualifying 300 s hover window, followed by controlled touchdown. At first foot contact: downward normal speed <= 0.30 m/s, horizontal speed <= 0.20 m/s, structural tilt <= 5 degrees and landing displacement <= 0.50 m. Report post-contact stability only if a supported contact model exists. |
| Solver convergence | Repeat representative tests with finer integration settings while keeping controller cadence and reference/event definitions unchanged | Tighten solver tolerances by a factor of 10 and halve maximum integration step. Proposed differences: peak height <= 0.01 m, attitude <= 0.1 degree, touchdown speed <= 0.01 m/s and mission energy <= 1%. Report event-time shifts. |

Proposed hover-window entry: remain inside the nominal peak position/attitude bands for 2 s, then start the 300 s clock. Climb, this entry dwell and landing are additional mission time and energy. Entry timeout and complete reference profiles require plant-branch proposal before a test protocol is finalized. A failed case is retained; do not reset state or restart the clock to conceal a violation.

## Proposed resource margins

- Propose available vertical thrust at least 1.5 m g at the limiting supported battery/electrical/thermal condition and required tilt, while retaining the differential-torque authority demanded by the agreed tests. Evaluate simultaneous allocation, not separate incompatible maxima. This is a candidate design margin, not an existing requirement or a demonstrated capability.
- Propose touchdown remaining energy at least 20% of usable mission-start battery energy. Define usable energy from the documented battery model, discharge conditions and cutoff before applying this reserve; do not silently use nominal nameplate energy or apply the same derating twice.
- Include climb, entry dwell, all 300 s of hover, landing, avionics, regulation losses and actuator demand. Report actual voltage, current, power, energy and thermal-model assumptions. Absence of a thermal model or continuous rating prevents a thermal pass.
- No numerical margin overrides manufacturer voltage, current, speed, temperature or duty limits. Unknown limits remain unresolved. Report how often each actuator saturates, how long it remains saturated and the simultaneous available authority.

## Evidence and physical-test limitations

Each eventual verifier must read the actual published code, configuration, mass-property, propulsion and trajectory artifacts; identify their exact revisions/hashes; compute its checks; and emit only the runtime VerificationResult JSON to stdout. Diagnostics belong on stderr. Retain the editable verifier and detailed measurements. A successful process, generated trajectory or fixture pass is not a vehicle or physical pass.

Keep analytical fixtures separate from selected vehicle cases. Describe sensor/estimator assumptions; perfect-state feedback results do not establish sensing or autonomous-flight capability. Motor lag, actuator response, coaxial interference, signed torque and battery uncertainty require separately documented sensitivity cases. Their tested ranges must come from branch evidence or explicit assumptions, not this draft.

Physical coaxial calibration, propulsion endurance/thermal tests, battery characterization, loaded servo/linkage tests, structural/joint tests, clearance under deformation, restrained tests and landing tests remain due. Touchdown speed alone does not define landing impact force; stopping distance, contact stiffness, first-foot loading and structural allowables require separate substantiation.

The exposed-rotor/guard disposition remains unresolved. No physical powered test or free flight is authorized by these simulation criteria. Test containment, isolation, emergency shutdown and operating procedures require a separate safety disposition, including the applicable vehicle/GSE accounting.

## Next disposition

Obtain the plant branch's practicality review and missing profile/sensitivity definitions, then ask the human to accept or amend the proposed simulation criteria and height datum. Preserve the reply as source evidence and update affected requirements and the validated plan before implementing an altered baseline. Agreement on these criteria is not PDR/CDR acceptance.
