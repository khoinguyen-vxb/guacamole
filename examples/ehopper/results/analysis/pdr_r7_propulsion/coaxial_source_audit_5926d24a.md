# Recovered coaxial screening model: source audit

Review date: 2026-10-11, Australia/Sydney.
Scope: source inspection under the approved r7 propulsion PDR task. No execution, numerical verification, procurement readiness or hardware acceptance is claimed.

## Evidence and inspected scope

Inspected the complete `chief_coaxial_model.py` text returned by reader request `5926d24aa7114765bd1312429f2cefe2`, tool_result revision 1, record SHA-256 `8bce6180b21d67acd304d5a8b99fce5a0c9a70cbd5f87a484ecd3133a5f0c206`. This is a runtime record hash, not a claimed file-content hash.

Reviewed `OutsideEnvelope`, `CoaxialModel.__init__`, `rotor`, `at_torque`, `operating_point`, and `evaluate_candidate`. The caller, configuration, coefficient database implementation and motor-spec implementation are not included in this reader result. Their behavior must not be inferred from this audit.

The current frame and mechanism decisions are f046cc4fe5294a6f9a61027529056f61 r1 and 72ef86f229ea461f8f31f8a231a70fca r1: NED/FRD, scalar-first Hamilton q_LB, and a bearing-supported common gimbal with R_BG=Rx(alpha)Ry(beta). These decisions do not select commercial propulsion hardware.

## Useful retained calculation structure

With positive rotational-speed magnitude n in rev/s, diameter D in m and density rho in kg/m^3, the code evaluates:

- T_i = fT_i * Ct_i * rho * n_i^2 * D^4, in N.
- Q_i = fQ_i * Cp_i * rho * n_i^2 * D^5 / (2*pi), in N m.
- Shaft power = Q_i * omega_i, in W, using positive speed magnitude for this power calculation.
- Required collective thrust = required vertical force / cos(resultant tilt).
- Shared constant-power battery equilibrium uses the higher-voltage root of V^2 - Voc*V + R*P = 0.

These are interpretable screening equations, conditional on the backend coefficient definitions and motor parameter conventions. RPM extrapolation is explicitly rejected, and the constructor checks static-data presence and increasing torque at the tabulated RPM levels. Checking the knots alone does not establish monotonicity between them without reviewing interpolation behavior.

## Findings and required treatment

### 1. Torque-balanced trim is present; a simultaneous thrust/yaw envelope is not

`at_torque` independently solves each rotor speed for the same positive torque magnitude. With opposite reaction-torque signs this constructs zero-net-aerodynamic-torque trim, not equal-speed trim. Retain that useful distinction.

`operating_point` exposes only this common-torque solution. It does not search unequal rotor torques, determine positive and negative yaw margins at a requested collective thrust, or establish maximum collective thrust while preserving yaw reserve. The named `reserve` result is a requested operating point, not a computed global maximum.

The revised calculation needs feasible operating-point pairs under the shared battery constraints. Report collective thrust and signed net aerodynamic torque together, plus individual thrust, torque, speed, current and power. Do not combine independently obtained collective and yaw maxima.

### 2. Coaxial factors are uncalibrated constants, without spacing dependence

The source applies separate thrust and torque multipliers to isolated static coefficients. This is preferable to simply doubling isolated thrust, but it is not a calibrated coaxial model. No rotor spacing, speed-ratio dependence, inflow interaction, airspeed or uncertainty domain enters these factors.

Retain explicitly configurable fT_i and fQ_i, candidate spacing in m or spacing/diameter, and calibration status. A spacing sweep cannot claim different performance unless an explicitly assumed or supported spacing-dependent model is supplied. Distinguish geometric spacing studies from aerodynamic evidence.

### 3. A single propeller entry represents both rotors

Both rotors use the same `prop` object. This does not establish that a purchasable matched CW/CCW pair exists, has matching coefficients, or fits the selected hubs. Inspect exact paired product variants, rotation-label viewing conventions, shaft/bore interfaces, hub thickness, fastener pattern and positive retention. Unknown dimensions remain unknown; another product's drawing is not a substitute.

### 4. Signed interfaces need an explicit physical convention

The source returns positive aerodynamic resisting-torque magnitudes and a configurable signed sum named `reaction_torque_nm`. For the current contract, define signed spin omega_i by the right-hand rule about +z_G. Positive spin appears counterclockwise from the +z_G side looking toward the origin. In the modeled powered static regime, air-on-rotor torque is -sign(omega_i)*Q_i.

Use F_i,G=[0,0,-T_i] and tau_air_i,G=[0,0,-sign(omega_i)*Q_i], transformed through R_BG. The transformed differential torque is not purely body yaw when tilted. Product CW/CCW labels must be mapped to this convention from evidence.

Rotor acceleration reactions and articulated angular momentum are absent from this static model. The plant must account for them consistently without double-counting internal motor torques as external whole-vehicle torques.

### 5. Motor and ESC electrical conventions require backend inspection

`rotor` derives torque constant from Kv and `torque_constant_kv_ratio`, adds a speed-dependent no-load current, applies a magnetic-lag term to back EMF, and adds winding and branch resistance before applying ESC efficiency. Inspect the definitions, units, calibration and validity domains of these backend functions before adopting their outputs.

The model distinguishes battery-side ESC input current from modeled motor current, but its ESC current-envelope check compares modeled motor current with an assumed continuous ESC rating. Establish whether supplier ratings concern input current, phase current or another convention. Also explain the separate resistance-loss and efficiency allowances to avoid unsupported loss accounting.

### 6. Static battery sag is useful but is not a discharge or transient model

All operating points use a configured end-of-mission open-circuit voltage and one pack resistance. The discriminant and loaded-voltage checks are useful necessary screening checks. They do not capture SOC evolution, temperature, aging, transient sag or measured capacity at the mission load.

Usable delivered energy is capacity times usable-capacity fraction times minimum loaded voltage. A further unused-energy fraction is withheld. Keep both factors visible and explain whether they represent distinct restrictions rather than overlapping reserve allowances. Battery internal loss is reported separately; do not add it again to a budget already expressed as terminal-delivered usable energy without changing the energy basis consistently.

### 7. Mission energy contains explicit but unvalidated heuristics

Hover, climb and landing durations are represented. Climb energy combines a static overthrust operating point with an added m*g*h/0.60 term. The 0.60 conversion factor is hard-coded. This is not a demonstrated climb trajectory or validated axial-flight model; overthrust duration alone does not establish the required height.

Landing multiplies the entire hover delivered power by a landing multiplier. Because auxiliary power is already inside hover delivered power, this also scales avionics and actuator demand. Unless independently justified, calculate propulsion, avionics and actuator/regulator energy separately for every mission phase. Retain at least 300 s of hover, climb and landing outside that interval, startup/settling allowances where needed, and explicit reserve.

The static coefficient domain may not include stopped or low-speed operation. Report that limitation rather than extrapolating silently or interpreting it as proof that startup or touchdown is physically impossible.

### 8. Thermal capability and dynamic response are not established

Current and power limits are catalogue limits multiplied by derating factors; ESC and battery limits include assumptions. These checks are not thermal predictions or evidence of continuous endurance. Record rating duration, cooling and ambient conditions, temperature limits and the missing sustained-load tests.

No motor/ESC lag or slew response is implemented here. Retain configurable response parameters for the plant, clearly marked uncalibrated until measured or otherwise supported.

### 9. Purchase accounting is not sufficiently explicit for the current requirement

`evaluate_candidate` multiplies allowance quantities by unit mass and unit cost, adds motor mass/cost and one battery mass/cost, and adds a generic cost allowance. It does not expose separate installed quantities, purchase-pack size, pack count, spare quantities, material consumption or remaining stock. Therefore this function alone cannot establish compliance with whole-minimum-purchase accounting or the mandatory purchase of two batteries while only one flies.

The revised ledger must identify propulsion, flying battery and two-battery purchase, servos, regulation, controller/sensors/receiver, wiring/connectors, retention, bearings/linkages, structural stock, landing parts and fastener packs. Avoid counting bundled accessories twice. Unknown prices and mass allowances must remain explicit. Price required reusable ground equipment separately, assuming nothing is owned.

Enforce complete vehicle purchase cost strictly less than AUD 500 excluding tax/shipping. An allowance-based estimated-cost pass is not a verified budget pass. Retain original currency, dated FX basis, tax treatment, variant, package quantity and supplier URL for each sourced price.

## Disposition and next evidence needed

Preserve the original source unchanged. Reuse its equations only as transparent screening components after inspecting the actual configuration, caller and PyThrust entry points. Do not reuse historical feasibility labels as current selections.

Priority evidence remains: exact paired propulsion products and retention interfaces; traceable current prices and complete purchase quantities; coefficient and motor-model provenance; shared electrical and simultaneous thrust/yaw limits; CAD-derived moving mass properties and thrust offsets; and actuator loaded-duty evidence. The recovered actuator analysis must remain subject to its separate signed-momentum and individual-bearing-load audit.

Retain an editable artifact-driven verifier that recomputes results from actual configuration and catalogue inputs. Arithmetic/model checks, dependency availability, successful execution and physical validation must remain separate outcomes. This audit reports no new numerical results or verification passes.
