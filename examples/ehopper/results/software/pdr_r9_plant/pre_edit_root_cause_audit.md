# PDR-R9 plant: current pre-edit root-cause audit

Date: 2026-10-11. Status: static diagnostic evidence, before plant repairs. No controller tuning, numerical plant acceptance, mission acceptance or physical validation is claimed.

## Authorization and current decisions

- Work plan: decision `98d7c43a499d4584a77132cd5ac96874` r1; bounded task `pdr_r9_plant` only.
- Frame contract: decision `f046cc4fe5294a6f9a61027529056f61` r1.
- Current provisional actuator architecture: decision `84ef41fdd3fd4266ada43df2ace64a48` r1, received from Chief in message `725b2f41ad89443cb1d5201a50a39b38`.
- Applicable requirements: `REQ-SIMULATOR-PID` r1 and `REQ-VEHICLE-CONFIGURATION` r1. The exposed structure supersedes the original rocket-shaped description.

The Chief decision selects a common bearing-supported two-axis gimbal carrying both independently driven counter-rotating rotors. It selects an architecture, not numerical travel, lever arms, component hardware or feasibility. Historical 12-degree travel and 0.25 m arm values are NOT selected vehicle inputs. Preliminary repair and independent analytical fixtures are authorized; PID tuning and closed-loop mission acceptance require an accepted current PDR and validated CDR plan.

## Inspected setup, implementation and callers

Inventory `inventory` r3 identifies the supplied repositories. The 6DOF setup source `b9013a7e55694253808f17532838c85e` r1 declares Python >=3.13 and dependencies including NumPy, SciPy, pytest, matplotlib and OpenMDAO. These declarations do not establish installed versions or successful imports. The top-level README is empty. `main.py:1-6` prints a greeting; `scripts/ehopper.py` is empty. Neither constructs or runs the plant.

The editable read-only audit program is `software/pdr_r9_plant/audit_sources.py`, created by request `fe88df4d80bc40bd9f8e466f22cd3582`. Execution request `75789ca9ed8b4f3f9320b5bb7b173ce8` produced:

- `software/pdr_r9_plant/source_inventory.json`, SHA-256 `f6b9881a35c7c0382c3e148dd483eb4c082311220a374ad9cb218479082e0cec`.
- `software/pdr_r9_plant/source_callers.md`, SHA-256 `7a0777cb751a871de70bdced8c66bc19cd25a2bdefa8d7f715b08d468941cc40`.

The inventory covers 57 files: 52 in 6dof_hopper including nested PyThrust, and five in PendulumControlProject. Its scope is Python source plus named setup/documentation files. It excludes binary/data files, version-control metadata, environments and caches. No excluded symlinks were reported. Both repositories' in-scope contents compared unchanged during that audit. This is an observed baseline, not proof of historical cleanliness or preservation of unmeasured files.

Current implementation/caller review evidence:

- `9522ea1694604e6eaa0156a22a2cde35` r1: current inventory and line-numbered core source; its displayed stdout was truncated.
- `bda071d187504809ac8e93752894897b` r1: continuation of the saved stdout, including Simulation through line 153, State through line 75 and quaternion helpers through line 68.
- `046ef7e762724dadb9ce9bd8b0ce326f` r1: relevant imports across both inventories and complete Hopper, Propulsion, Propellor, constants and entry-point source.
- `b913670059ca4776ab422b0c47a70b87` r1: complete cylindrical Aerodynamics implementation.
- `0389bcc64b1547ec8238faea6c8b5f07` r1: complete standalone PyThrust example in `test/test_pythrust.py`.
- `30be8dc35a3141f1b30fd56de2e4b0b5` r1: PendulumControlProject README; PID is roadmap/reference material, not an integrated hopper controller.

The initial broad diagnostic output was also truncated. Conclusions below rely on the bounded continuation and focused caller output, not an assumption that unseen stdout was reviewed.

### Affected caller map

| Affected implementation | Reviewed callers and dependencies |
|---|---|
| State constructor and update/serialization | `Simulation.solve_ode:142`; `Simulation.trajectory_ode:17`. No other direct plant caller identified. |
| Quaternion DCM helper | `Simulation.trajectory_ode:37`, with transpose at line 38. |
| Euler conversion | `Simulation.solve_ode:134`. |
| Simulation RHS | Passed to SciPy `solve_ivp` by `Simulation.solve_ode:144-153`. SciPy itself is not being modified. |
| Hopper mass, CG, inertia and propulsion wrench | `Simulation.trajectory_ode:91-104`. |
| Propulsion mass and wrench methods | `Hopper.mass:45-46`; `Hopper.get_thrust_and_moment:54-58`; inherited contract in `Propellor:4-15`. |
| Aerodynamics.determine_at_point | `Simulation.trajectory_ode:98-105`. |
| Entry points and examples | Greeting-only `main.py`; empty `scripts/ehopper.py`; `test/test_pythrust.py` calls PyThrust directly, not Simulation or Propellor. |

Relevant imports across the inventory are in `chassis/hopper.py`, `propulsion/propeller.py` and `simulation/simulation.py`; their complete contents were reviewed. Other detected solve_ivp users belong to PyThrust battery models and pendulum models. They are not callers of the hopper implementations and will not be modified. The pendulum source inventory identifies no direct hopper import or affected plant call.

This is a static caller audit: attribute names are not resolved to runtime types, and dynamic/generated callers or callers outside these supplied roots cannot be ruled out. New sandbox callers must be reviewed together with each repair.

## Root causes and planned dispositions

The historical audit was recovered using read_text, request `69160da2a4984e95a9c390ca2f1378c6`, from `software/chief_6dof_root_cause_audit.md`. Its source-defect findings are confirmed below against current implementation. Its historical mechanism references and numerical assumptions do not govern this work.

| ID | Current source evidence and root cause | Affected caller / preliminary repair |
|---|---|---|
| RC01 | `simulation/simulation.py:4` imports `from state import State`, although the implementation is `simulation/state.py`. Import behavior depends on an inappropriate top-level module path. | Simulation import and all future runners. Establish explicit package-relative imports in the sandbox copy; test the actual published package rather than accidentally importing the checkout. |
| RC02 | `Simulation.__init__:9-13` discards the supplied initial state by assigning None. `solve_ode:133-142` separately forces initial position, velocity and rates to zero. | Constructor, solve_ode and its future runner. Use one authoritative validated initial vector and preserve nonzero position, velocity, attitude and rates. |
| RC03 | `trajectory_ode:16` reads undefined `self.time`. | solve_ivp -> trajectory_ode. Use the supplied time argument; no evaluation-history dependency. |
| RC04 | `trajectory_ode:22-27` treats the solve_ivp ndarray as an object with x/u/q0/p attributes. | solve_ivp -> trajectory_ode. Explicitly unpack a validated numeric vector with a documented versioned ordering. |
| RC05 | `trajectory_ode:17` passes one vector to `State.update_state`, which requires thirteen scalars (`state.py:31`). That method also appends history on every invocation (`32-44`). | trajectory_ode -> State. Separate state conversion from trajectory logging. Do not append histories or mutate controller states in adaptive RHS evaluations, which can include trial/rejected or repeated times. |
| RC06 | `helpers/math.py:5,13` accepts `quarternion` but reads local `quaternions` before assignment. | trajectory_ode -> DCM helper. Repair the variable error and expose an unambiguous rotation-direction API; document any retained compatibility alias. |
| RC07 | `solve_ode:134` supplies three positional scalars to `euler_to_quaternion(euler_angles, degrees=True)`. Helper comments describe roll/pitch/yaw while line 46 unpacks psi/theta/phi, reversing the documented first/last axes. | solve_ode -> Euler helper. Require explicitly named roll, pitch and yaw in radians; verify isolated axes and compound rotations independently. |
| RC08 | The original velocity state is body-resolved (`simulation.py:23,55,111,117-120`), whereas the current Chief contract requires local-frame instantaneous-CG velocity. DCM direction and axes are insufficiently explicit at interfaces. | State, Simulation, force providers and new runners. Deliberately migrate to local CG position/velocity with a named conversion boundary; never silently reinterpret existing body u/v/w values as local values. |
| RC09 | Quaternion normalization in `simulation.py:35` and `helpers/math.py:13,66` lacks explicit zero/nonfinite guards. | Initialization, DCM conversion and RHS. Validate dimensions, finiteness and quaternion norm; distinguish initialization normalization policy from measured integration drift. |
| RC10 | `Simulation.solve_ode:144-153` assigns a local solution and returns nothing. | Future runner and verification programs. Return the actual integration result, including solver status/message, samples, dense output and events where requested; handle integration failure explicitly. |
| RC11 | `propulsion/propeller.py:4-15` does not implement abstract propulsion methods and discards all electrical arguments. Base methods at `propulsion.py:15,19,23` omit self and have inconsistent signatures. | Propellor inheritance, Hopper.mass and Hopper.get_thrust_and_moment. Replace the unusable contract in the sandbox with explicit commands, actuator state, external wrench and electrical/map interfaces. Do not present a fixture map as calibrated propulsion. |
| RC12 | `Hopper.mass:45-46` adds propulsion mass to ambiguously named mass_wo_propellant. `CG:48-49` is fixed; `inertia:51-52` is diagonal. Stored moment_arm is unused and propulsion wrench reference is unspecified. | trajectory_ode -> Hopper -> Propulsion. Define complete installed-mass ownership, instantaneous CG and full inertia about that CG. Compute each application-point moment exactly once. Battery discharge does not imply appreciable vehicle mass loss. |
| RC13 | Required environment/atmosphere methods are called at `simulation.py:40-52`, but no implementation is identified in the current core inventory. Entry points do not build a simulation. | Simulation construction and future runnable entry point. Supply an explicit environment interface and a clearly labelled analytical fixture environment; do not invent operating-condition acceptance. |
| RC14 | `Aerodynamics.determine_at_point` returns zero force AND moment when translational air speed is near zero, before evaluating its later rotational damping term. The later term can be nonzero for nonzero transverse angular rate. | trajectory_ode -> Aerodynamics. Report the limiting-case defect; do not reuse this tube model as the exposed-structure model. Use an explicit external aerodynamic-wrench interface and separately labelled no-aerodynamics fixtures. Any retained legacy tube repair must remain isolated and tested. |
| RC15 | Existing test/test_pythrust.py is a standalone propulsion example with no hopper assertion-based verification. Main and scripts provide no mission/PID integration; the pendulum README is not an implemented hopper controller. | Entry points, tests and future control integration. Add actual artifact-driven plant checks and a runnable analytical entry point. Produce a sampled-PID architecture proposal only at PDR; no tuning or mission pass claims. |

### Important distinctions from a blanket frame-sign diagnosis

The original down-positive gravity and height=-z are compatible with NED. The original displayed DCM is a local-to-body form for the usual scalar-first Hamilton orientation, and the displayed quaternion rate matrix is consistent with right multiplication by body angular velocity. Neither is declared a mathematical sign defect solely from variable names. The confirmed defects are the variable typo, Euler signature/order ambiguity and incomplete interface contract. Basis-vector and kinematic tests must establish the repaired implementation's direction and signs.

The current FRD body uses +x forward, +y right and +z toward the feet when upright. The original cylindrical model's default longitudinal +x axis is therefore not automatically the new upright vehicle axis and is not evidence for exposed-structure aerodynamic applicability.

## Mandatory repair/interface contract

### State, frames and mass properties

The rigid-body state will explicitly represent `[p_G,L (m), v_G,L (m/s), q_LB (dimensionless, wxyz), omega_B (rad/s)]`. Actuator states, if integrated, must have separately documented names, dimensions and units. The local frame is NED with a fixed launch-ground origin. R_LB maps body vectors to local; R_BL is its transpose. Quaternion kinematics are qdot=0.5*q_LB Hamilton-product [0,omega_B]. Euler diagnostics use Rz(yaw)Ry(pitch)Rx(roll), radians.

Gravity is [0,0,+g] in L and neutral thrust [0,0,-T] in B. For constant complete-vehicle mass, local CG translation uses pdot=v and vdot=R_LB*F_B/m+[0,0,g]. A body-velocity Coriolis term must not be retained after migration to local velocity.

CAD axes are +X forward, +Y left, +Z up. R_BC=diag(1,-1,-1) is a proper rotation, determinant +1. With neutral CAD CG_C0 unresolved, r_B0=0.001*R_BC*(p_C-CG_C0), in m. Report instantaneous r_B0G(configuration) and full I_B,G in kg m^2. Transform inertia with R_BC*I_C,G*R_BC^T after correct density weighting and SI conversion. Raw geometric mm^5 needs density in kg/m^3 and factor 1e-15; already mass-weighted kg mm^2 needs factor 1e-6. Apply parallel-axis shifts only when changing reference points.

The fixed structural datum must not move with the articulated CG. Converting CG state to a fixed-datum state requires both the rotated CG offset and its time derivative, including body rotation and configuration motion.

### Propulsion and selected gimbal

Use R_BM=Rx(alpha)Ry(beta), outer body-fixed x and carried inner y. Ideal axes intersect at P; actual offsets remain explicit. For rotor i:

- F_Bi=R_BM*[0,0,-T_i], T_i>=0 N.
- r_B0i=r_B0P+R_BM*r_MPi, with all points in m and datums identified.
- r_Gi=r_B0i-r_B0G(alpha,beta).
- External moment contribution is r_Gi cross F_Bi plus R_BM*[0,0,-s_i*Q_i], where Q_i>=0 N m and s_i is spin sign about common +z_M.

Opposite spins imply neither equal aerodynamic torque nor cancelled angular momentum. Coupled coaxial thrust/torque/electrical maps must report calibration provenance and validity domains, including rotor spacing and simultaneous operating conditions. Shared battery voltage/current and thermal constraints cannot be inferred from isolated rotor maxima.

Provide explicit motor/ESC lag, command bounds and saturation interfaces; tilt travel, resultant cone, loaded rate/acceleration and lag require independent parameters. Missing vehicle values must cause an explicit unresolved-input condition, not silent fixture defaults. Joint limits and a resultant tilt cone are different constraints.

### Reduced articulated-dynamics boundary

Internal motor and servo reactions must not be added as independent external whole-vehicle torques. For total angular momentum about the instantaneous CG, a suitable interface is H_B=I_B,G*omega_B+h_rel,B. Consistent evolution includes I_dot*omega, relative-angular-momentum derivative and omega cross H. Configuration-dependent inertia alone is insufficient.

A reduced rigid-body implementation must label omitted moving-mass, rotor-acceleration and gyroscopic terms, identify the frozen/small-motion assumptions and restrict its evidence to those assumptions. Numerical vehicle error bounds cannot be claimed until moving masses, rotating inertias and loaded gimbal trajectories are supplied. Complete multibody validation remains unperformed. A CG-relative thrust moment is not itself the servo joint load.

Aerodynamic loads on the actual exposed structure and rotor wake remain unresolved. A zero-aerodynamics analytical fixture is allowed only with an explicit label; it is not a calm-air vehicle model, since rotor wake and rotational loads may remain present.

## Controller proposal boundary

Propose fixed controller times t_k=t_0+k*dt_control. Update controller memory once at each sample and hold commands over the subsequent integration interval. Adaptive RHS calls receive immutable held commands and must not mutate PID integrals or derivative-filter state.

The later configuration must expose SI gain units, limits, controller cadence, derivative filtering and anti-windup using achieved allocation/saturation feedback. Account for coupled thrust-vector and signed differential-torque allocation rather than assuming three independent moment actuators. Controller implementation/tuning and closed-loop recovery, tracking and mission acceptance remain gated by accepted PDR and a validated CDR plan.

## Preservation, repeatability and verification status

Only audit support artifacts have been created at this point. No repaired plant has been written or numerically tested. The successful static-audit process establishes that the selected interpreter can run this standard-library audit; it does NOT establish NumPy/SciPy imports, usable plant integration or physical correctness.

Original checkouts are read-only inputs to this task. Retain the source inventory baseline and compare in-scope hashes after repair and execution. Use Python -B to avoid writing bytecode into supplied sources. Hash comparisons must be reported with their exact scope, not as whole-repository preservation evidence.

Recorded audit invocation through Guacamole:

    repository: 6dof_hopper
    workdir: .
    command: [python, -B, software/pdr_r9_plant/audit_sources.py]
    outputs:
      software/pdr_r9_plant/source_inventory.json
      software/pdr_r9_plant/source_callers.md

The audit refuses existing outputs; do not rerun into these evidence files. A repeated audit requires reviewed fresh output names. Subsequent runnable plant and checker instructions must identify the sandbox package/import root and actual tested dependency versions.

Next evidence gates are: dependency/import capability, sandbox-only repairs with explicit migration notes, retained analytical fixture configuration, actual execution, and an artifact-bound verification program. Its stdout must contain only VerificationResult JSON; diagnostics go to stderr; every tested artifact Ref must be included in verify_command inputs.

Required analytical checks include state round trips and rejection of invalid inputs; nonzero initialization; isolated-axis and compound Hamilton/DCM rotations; quaternion norm and integration kinematics; NED gravity/free fall; force and torque signs; full-inertia rotational response; CG-relative thrust and signed rotor torque; solver returns/events; lag and saturation; CAD transform/SI round trips; and analytical trim using explicitly labelled fixture values. These are planned checks, not reported passes.

Vehicle trim, authority, electrical/thermal endurance, actuator feasibility, structural loads, touchdown and takeoff/300-second-hover/landing performance remain unverified. Outstanding inputs include actual pivot/application points, rotor spacing, configuration-dependent CG/full inertia, moving/rotating inertias, loaded actuator properties, calibrated coaxial maps, component limits, exposed-structure loads and human-agreed mission tolerances. Chief owns vehicle selections and CAD; the active propulsion peer owns propulsion evidence. No hardware or mission acceptance follows from this audit.
