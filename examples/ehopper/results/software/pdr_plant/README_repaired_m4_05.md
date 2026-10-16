# PDR M4 fixed-D analytical plant copy

## Authority and status

System model revision 4, work-plan decision 99f7bb629eef45b89fa38d27c803868c r1,
and interface decision 88561ff8b3ba4e8286cebd95a93e3b08 r1 govern this copy.
PDR-PLANT-PRE-EDIT-AUDIT-M4-03 r1 records the pre-edit findings and affected callers.
PDR-PLANT-CAPABILITY-REPORT-M4-04 r1 separately records dependency imports,
standalone SciPy execution, original failure reproductions and recovered imports.

This is a migrated source package, not a verified release. The generation
manifest and patch show exactly what changed. Syntax compilation during
preparation does not import this copy or execute its dynamics. Analytical
regressions and a runnable synthetic scenario entry point are still required.
Historical checker files/results were not recovered with the eight modules.

## Preserved and changed behavior

Retained mechanisms: immutable initialization, owned serialization, explicit
local-CG velocity, Hamilton quaternion evolution, package-relative imports,
separated-origin gimbal geometry, complete mass/momentum snapshots, paired
propulsion evaluation, external point-load resolution, pure held-command RHS,
synthetic actuator lag/limits, and actual solve_ivp result/failure handling.

The inspected source's fixed reference was defined at neutral CG. The selected
contract instead defines D at the fixed leg-attachment plate/ring upper plane.
The copy updates that definition and coordinates all datum-related identifiers.
It changes neither the selected frame directions nor the underlying force,
kinematic, lag or momentum equations. No original body-velocity vector is
silently imported into the new local-velocity schema.

| Recovered name | M4 name/meaning |
|---|---|
| neutral_cg_C_mm | datum_D_C_mm; explicit keyword-only CAD datum argument |
| cg_B0_m | cg_D_m; vector D to G, expressed in B, metres |
| cg_rate_B0_m_s | cg_rate_D_m_s; derivative of B components due to internal motion |
| outer_origin_B0_m | outer_origin_D_m; D to outer origin, expressed in B |
| joint_origins_B0_m | joint_origins_D_m |
| application_points_B0_m | application_points_D_m |
| application_point_rates_B0_m_s | application_point_rates_D_m_s |
| application_point_B0_m | application_point_D_m |
| offset_B0G_B_m | offset_DG_B_m |
| offset_rate_B0G_B_m_s | offset_rate_DG_B_m_s |
| pdr_r12_* schemas | hopper_m4_fixed_D_* schemas; old strings rejected |

The inverse CAD helper uses point_D_m. Every datum-relative vector above uses
FRD body components even where the compact field name contains only D.
The numerical D_C is an explicit geometry input, not zero by default and not
necessarily the neutral CG. A shifted datum requires coherent changes to all
point and CG offsets; it is not a change to local CG position or velocity.

## Package and execution boundary

The package directory is software/pdr_plant/repaired_hopper_m4/ and contains:
helpers/math.py; simulation/state.py; chassis/hopper.py;
propulsion/propulsion.py; propulsion/propeller.py; propulsion/actuators.py;
simulation/environment.py; simulation/simulation.py; and package markers.
All numerical module imports are package-relative. NumPy and SciPy are required;
no dependency installation is performed or authorized by this copy.

For subsequent Guacamole execution use repository='6dof_hopper', sandbox
workdir='.', and python -B. New runners located in software/pdr_plant/ can import
repaired_hopper_m4 directly. Do not invoke the original greeting main.py or the
PyThrust example as though they launched this plant. Missing installations must
be reported through the Chief, not silently installed.

State order remains 13 CG/attitude components plus six analytical actuator
components: p_G,L [m], v_G,L [m/s], q_LB wxyz [1], omega_B [rad/s], upper/lower
rotor speed magnitudes [rad/s], alpha/beta demand-filter states [rad], and actual
alpha/beta angles [rad]. Use module schema constants and units, never length
alone. Preserve every initial/carried state and raw quaternion sample.

solve_ode integrates one immutable HeldCommand. Repeated calls restart at its
initial snapshots. A scheduler must explicitly carry accepted endpoints,
including all actuator states. Output sampling is not controller cadence.
For terminal events inspect actual t_events/y_events or validated dense output;
the final requested output sample need not be the event endpoint. Preserve
IntegrationFailure.solution and do not convert provider exceptions into a
completed trajectory. These behaviors remain subject to independent checks.

## Fixed datum and scope limits

Local L is NED, body B is FRD, CAD C is forward-left-up. q_LB is scalar-first
Hamilton and R_LB maps B into L. Convert CAD points using
r_B=0.001*diag(1,-1,-1)*(p_C-D_C), with CAD mm and simulator m.
The fixed datum converter retains
p_D=p_G-R_LB*r_DG and
v_D=v_G-R_LB*(omega_B cross r_DG+rdot_DG).
There is no new acceleration converter in this migration; consistent rddot_DG
and independent checks remain necessary before such an interface is used.

Simulation, LagParameters and ActuatorEvaluation remain analytical-fixture only.
Some data records can describe provisional_vehicle, but that does not make the
runnable analytical path a vehicle model. Do not relabel vehicle numbers as
fixtures. A vehicle extension requires implemented dynamics, an applicability
assessment, explicit Chief disposition and tests, not removal of a label guard.

The speed-demand lag is not a realizable hobby-ESC command interface. Gimbal
motion is prescribed rather than solved from joint loads. Mass/momentum terms
are supplied, not a derived coupled multibody solution. Prescribed electrical
conditions do not close sag, transient energy or thermal evolution. The original
cylinder aerodynamics is not silently imported. Contact and PID are not added.

Next: publish generated sources and migration records, create independently
specified synthetic providers/configurations/checkers, and execute artifact-bound
regressions. Unperformed physical checks remain null. No hardware selection,
mission acceptance, requirement satisfaction or PDR acceptance is claimed.
