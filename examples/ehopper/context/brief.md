# Electronic Hopper brief

Build a hopper that takes off, holds position and lands using electric propulsion
with counter-rotating coaxial propellers.

User requirements, recorded 2026-09-30 and confirmed or amended up to 2026-10-11:

- Hover height: approximately 5 m above takeoff level.
- Sustain hover for 5 minutes (300 s), then land under control. Climb and landing
  add to the required battery endurance.
- No specified propeller diameter limit.
- Zero-payload demonstrator, flown in calm air near sea level.
- Budget: strictly less than AUD 500 for all purchased vehicle hardware and
  materials, excluding tax and shipping. Assume everything is bought; nothing is
  already owned. Charge whole minimum purchase packs and spools to the vehicle,
  including a two-battery pack even though only one battery flies. Price reusable
  ground equipment (transmitter, charger or power supply, test and ground safety
  equipment) separately from the vehicle cap. 3D-printed PETG parts are not costed,
  but their mass counts.
- Suppliers: research current prices online, for example rcdrone.top,
  jaycar.com.au, Temu and Taobao. The PyThrust library includes commercial motors
  and propellers.

Vehicle configuration (hard constraints; ask before changing any of them):

- Exposed minimum structure only, with no fins, nose cone or fairing. The vehicle
  need not look like a rocket.
- The coaxial propulsion module and both propellers sit at the bottom, below the
  structure. The structure, battery and electronics sit above the rotors.
- Thrust vectoring by a common two-axis gimbal of the motor unit.
- One to four spines (longerons). Choose the count for ease of mounting the
  battery, avionics, gimbal and legs and for structural need, and record why.
  Prefer CFRP tube over aluminium, with a comparison.
- Splayed landing legs of thin CFRP tube, tripod or quadpod: compare both and
  recommend one. Attach them at a ring or plate just above the gimbal. The feet sit
  below the propeller plane, the stance is wider than the propeller disc, and both
  rotor envelopes stay clear of the ground at full gimbal tilt.
- Use CAD-derived mass, CG and clearance results for the structural down-selection.

The photos in `context/reference_images/`, described in
`context/reference_designs.md`, show flown vehicles of this kind. They are design
precedent, not requirements.

Simulation acceptance targets, agreed 2026-10-11. They apply to simulation only:
they are not hardware validation or review acceptance.

1. Height reference: a fixed airframe datum, measured as its rise from its
   stationary pre-takeoff position, not the instantaneous CG. The target rise is
   5.00 m; horizontal position is relative to the datum's initial location.
2. Hover: after acquisition, one uninterrupted 300 s interval with altitude RMS
   error ≤ 0.10 m and maximum absolute error ≤ 0.25 m, and horizontal radial error
   RMS ≤ 0.25 m and maximum ≤ 0.50 m, with no transient exclusions. Acquisition,
   climb and landing are additional battery loads.
3. Attitude recovery: from isolated 10° roll, pitch and yaw perturbations, and a
   combined 10° roll plus 10° pitch, at zero initial body rates, recover to total
   attitude error ≤ 2° and body-rate norm ≤ 2°/s within 5 s, then stay within both
   limits for 2 s.
4. Landing on level ground: immediately before first foot contact, the contacting
   foot's downward speed is ≤ 0.30 m/s, horizontal speed ≤ 0.20 m/s and airframe
   tilt ≤ 5°. Both rotor envelopes stay clear during approach and settling. Contact
   stiffness, leg compression and uneven-ground sensitivity need explicit modelling.

Still open: disturbance amplitudes, thrust and energy reserves, numerical solver
tolerances, and control hardware. Hardware flight performance requires testing;
simulation alone does not establish it.

Scope and deliverables:

1. Select motors, coaxial propellers, ESCs and battery with a traceable thrust,
   torque, current, energy, mass and cost budget. Keep coaxial interference and
   calibration uncertainty explicit. Record current vendor sources and dates.
2. Design the vehicle using the supplied `freecad-mcp`, preserving an editable
   parametric FCStd assembly, STEP exports and mounting/assembly drawings.
   Include propulsion support, battery/electronics mounts, the gimbal and the
   landing legs. Transfer mass, CG and inertia to the sim with documented units and
   coordinates.
3. Diagnose and repair the supplied `tooling/6dof_hopper`, then integrate and
   tune PID control with actuator limits, lag, anti-windup and fixed control
   sampling. Deliver a runnable modified copy/patch, gains, verification scripts
   and repeatable takeoff, hover and landing results.

Initial source inspection found that `Simulation` discards its initial state,
references undefined `self.time`, treats an ODE array as a `State`, imports
`state` from the wrong package location, calls `euler_to_quaternion` with a
mismatched signature and does not return its integration result. `Propellor`
does not implement its abstract propulsion methods. These are plant/integration
defects to diagnose before PID tuning. The pendulum project describes planned
PID work; it does not supply an integrated hopper controller.

Prior work: `context/previous_run/README.md` indexes unverified notes from an
earlier run (supplier research, a structural trade review, the simulator root-cause
audit and a proposed PID architecture). Start from them rather than repeating that
research, and re-check them before relying on them.

Keep the supplied checkouts unchanged. Put runnable corrected copies, CAD,
analyses and logs in `results/`; register generated outputs and actual
verification evidence in the project history. This run delivers the PDR package
for this scope; CDR follows only after the PDR is accepted.
