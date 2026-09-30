# Electronic Hopper brief

Build a rocket-shaped hopper that takes off, holds position and lands using
electric propulsion with counter-rotating coaxial propellers.

User requirements, recorded 2026-09-30:

- Hover height: approximately 5 m above takeoff level.
- Sustain hover for 5 minutes (300 s), then land under control. Climb and landing
  add to the required battery endurance.
- No specified propeller diameter limit.
- Complete vehicle hardware budget: strictly less than 500. AUD is a provisional
  currency assumption; currency, tax/shipping and any already-owned components
  need confirmation.

Scope and deliverables:

1. Select motors, coaxial propellers, ESCs and battery with a traceable thrust,
   torque, current, energy, mass and cost budget. Keep coaxial interference and
   calibration uncertainty explicit. Record current vendor sources and dates.
2. Design the vehicle using the supplied `freecad-mcp`, preserving an editable
   parametric FCStd assembly, STEP exports and mounting/assembly drawings.
   Include propulsion support, battery/electronics mounts, a realizable attitude
   control mechanism and landing legs. Transfer mass, CG and inertia to the sim
   with documented units and coordinates.
3. Diagnose and repair the supplied `tooling/6dof_hopper`, then integrate and
   tune PID control with actuator limits, lag, anti-windup and fixed control
   sampling. Deliver a runnable modified copy/patch, gains, verification scripts
   and repeatable takeoff, hover and landing results.

Open requirements: total mass/payload, operating wind and conditions, attitude
actuation, control hardware, altitude/position tolerances and touchdown limits.
Propose tolerances before judging simulated mission success. Hardware flight
performance requires testing; simulation alone does not establish it.

Initial source inspection found that `Simulation` discards its initial state,
references undefined `self.time`, treats an ODE array as a `State`, imports
`state` from the wrong package location, calls `euler_to_quaternion` with a
mismatched signature and does not return its integration result. `Propellor`
does not implement its abstract propulsion methods. These are plant/integration
defects to diagnose before PID tuning. The pendulum project describes planned
PID work; it does not supply an integrated hopper controller.

Keep the supplied checkouts unchanged. Put runnable corrected copies, CAD,
analyses and logs in `results/`; register generated outputs and actual
verification evidence in the project history. PDR/CDR packages cover this scope.
