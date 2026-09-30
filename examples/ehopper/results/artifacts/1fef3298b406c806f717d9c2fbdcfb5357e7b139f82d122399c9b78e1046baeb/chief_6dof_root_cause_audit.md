# Electronic Hopper — preliminary 6DOF source audit

Status: PDR diagnostic work only. Original checkouts remain unchanged. No repaired plant, tuned controller, mission success or physical acceptance is claimed.

## Inspected scope and provenance

Source root: supplied tooling/6dof_hopper. Static AST inventory and caller report: tool_result c9192d21709946c8bf5655f2eff02eaa revision 1. It enumerates aero/aero.py, chassis/hopper.py, helpers/constants.py, helpers/math.py, main.py, propulsion/propeller.py, propulsion/propulsion.py, scripts/ehopper.py, simulation/simulation.py, simulation/state.py and test files. No parse errors were reported; dynamic dispatch is not excluded.

Full source readers: simulation/simulation.py — eda44d599b3c472ba985c4f579cbd909 r1; helpers/math.py — 9b109a76a3d24595898446d01abe6eda r1; simulation/state.py — 7990c07cefb34a87954bee8947a7bbbb r1; chassis/hopper.py — 14e30e1ebe2d4de4b1803248e2bfa0e3 r1; aero/aero.py — b913670059ca4776ab422b0c47a70b87 r1; propulsion/propeller.py — 5dc6e2c512ba41d6aac9eb2df685da89 r1; propulsion/propulsion.py — a5a521c6952b43ffb1e4e62e31425e91 r1; main.py — ed76246a4e164496ab349ba3dedb6b64 r1; scripts/ehopper.py — c70dadfd36a84f4298a96d51d885d175 r1; test/test_pythrust.py — 0389bcc64b1547ec8238faea6c8b5f07 r1. References below identify functions; these are Python sources, not paginated documents.

## Root causes and required repair sequence

1. **Import failure:** simulation/simulation.py imports `from state import State`, although State is in simulation/state.py. Establish an explicit package/import layout and test import from the published runnable copy.
2. **Discarded initial condition:** Simulation.__init__ assigns self.state=None instead of retaining its state argument. solve_ode independently replaces initial position, velocity and rates with zeros. Define one authoritative initial-state interface and test nonzero initial conditions.
3. **Undefined time:** trajectory_ode reads self.time, which the inspected constructor never defines. Use its time argument; the RHS must not rely on mutable evaluation history.
4. **ODE vector/object mismatch:** solve_ivp passes an ndarray, but trajectory_ode accesses state.x, state.u, state.q0 and other object fields. Explicitly unpack a validated 13-element vector, with documented ordering and units.
5. **State update signature and history misuse:** trajectory_ode calls self.state.update_state(state), while update_state requires thirteen scalar arguments. That method also appends history on every call. Adaptive RHS evaluations include trial/rejected steps, so logging and controller state updates must occur outside the RHS at accepted/sample times.
6. **Quaternion variable typo:** quarternion_to_dcm accepts `quarternion` but reads local `quaternions` before assignment. Correct the implementation in the modified copy; retain an alias only if compatibility requires it.
7. **Euler signature/order ambiguity:** solve_ode passes three positional scalars to euler_to_quaternion(euler_angles, degrees=True). The helper's comment says roll/pitch/yaw, but unpacking is psi/theta/phi. Specify the convention and explicit radians at the interface. Test each isolated axis and compound rotations against an independent rotation implementation.
8. **Frame convention requires explicit confirmation:** the plant uses height=-local_z and gravity=[0,0,+g], indicating a down-positive local frame. It uses TBL for local-to-body and its transpose for body-to-local. The displayed scalar-first quaternion DCM and rate matrix should be checked together; do not claim a sign defect without a basis-vector/kinematic test. Aerodynamics defaults to body +x as the longitudinal axis. CAD, propulsion and control must use a single documented right-handed mapping; identity attitude is not automatically upright for a +x-longitudinal vehicle.
9. **Quaternion robustness:** normalization divides by the quaternion norm without rejecting a zero or nonfinite quaternion. Validate initial state and monitor norm drift. The existing norm-feedback term is not evidence of correct orientation integration.
10. **Lost integration result:** solve_ode assigns the solve_ivp return to local `solution` but does not return it. Return a structured result, inspect solver success/message, and retain accepted trajectory samples and event information.
11. **Incomplete propulsion:** Propellor only invokes the base constructor, discards its supplied electrical parameters and does not implement abstract mass, CG, or thrust/moment methods. It cannot serve as an integrated electric propulsion plant. Base abstract methods also omit self and have inconsistent time arguments. Define explicit command, state, force, moment, mass and electrical interfaces before implementation.
12. **Mass/moment interface ambiguity:** Hopper.mass adds propulsion.get_mass to mass_wo_propellant; an electric battery does not appreciably lose mass during discharge. Define component ownership to prevent double counting. Hopper.CG is fixed, inertia is diagonal, and moment_arm is stored but unused. Specify whether propulsion returns a moment about the vehicle CG; apply r cross F exactly once and support a full inertia tensor.
13. **Missing executable mission integration:** main.py prints a greeting; scripts/ehopper.py is empty. No environment implementation appears in the audited top-level plant inventory, although the RHS requires elevation and atmosphere methods. Supply an explicit environment, vehicle construction, command interface and mission runner in the later runnable copy.
14. **Aerodynamic zero-speed discontinuity:** Aerodynamics.determine_at_point returns zero force and moment when translational air speed is near zero, before calculating rotational damping. Its later rotational-damping expression can be nonzero at zero translation. Separate translational and rotational contributions and test this limiting case. The tube-only model does not establish rotor-wake, gimbal or landing-contact loads.
15. **No hopper PID integration:** test/test_pythrust.py is a standalone propulsion example, not an integrated controller or assertion-based mission test. PendulumControlProject/README.md describes planned PID work; its roadmap is not evidence of a working hopper controller and does not expand project scope.

## Affected callers reviewed

- Simulation.trajectory_ode calls the quaternion DCM helper, Hopper.mass/CG/inertia/get_thrust_and_moment and Aerodynamics.determine_at_point.
- Simulation.solve_ode calls the Euler helper, State constructor and solve_ivp with trajectory_ode.
- Hopper.mass and Hopper.get_thrust_and_moment delegate to Propulsion.
- Propellor inherits Propulsion; the abstract contract must be reconciled with Hopper.
- State.update_state is called by trajectory_ode with the incompatible signature above.
- main.py and scripts/ehopper.py provide no further plant construction or mission caller.
- test/test_pythrust.py calls PyThrust directly, not Simulation or Propellor.

Before each detailed-stage change, repeat the caller audit against the actual modified copy and inspect any newly introduced callers. The current AST result is not proof that external or dynamic callers cannot exist.

## Controller/plant boundary for detailed work

The preliminary mechanism decision 47859c3918d741fd93606cd0ddd0c9e6 r1 selects a common two-axis coaxial gimbal and differential reaction torque. A fixed coaxial pair alone cannot supply arbitrary transverse moments. Preserve the provisional 12-degree total tilt cone and 0.25 m pivot-to-CG target as assumptions, not measured interfaces. Differential-torque authority under shared battery sag remains to be calculated.

After human acceptance of the current PDR: repair and verify the plant first; then implement sampled PID with commands held between fixed controller samples. Never mutate PID integrals in solve_ivp RHS calls. Include anti-windup using achieved allocation/saturation feedback, filtered derivative feedback, explicit units, configurable gains/limits, motor and servo lag, rate/travel/current limits, and coupled thrust/reaction-torque allocation. Account for rotor acceleration reaction torque and gyroscopic effects consistently with the chosen rotor-state model; do not double-count internal torques.

## Required evidence before declaring success

Retain editable checks for imports, nonzero initial-state preservation, state-vector round trips, quaternion basis rotations and norm, gravity/free fall, torque-free motion, applied-force/moment response, propulsion trim and electrical balance, zero-speed aerodynamic limits, and integrator return/event behavior. Then test attitude recovery, altitude/position tracking, disturbances, saturation recovery and takeoff/300-second hover/landing. Propose numeric tolerances for human agreement before mission acceptance. Report actual errors, touchdown rates, thrust/current/energy and margins from artifact inputs using verify_command. Physical calibration and flight tests remain unperformed.
