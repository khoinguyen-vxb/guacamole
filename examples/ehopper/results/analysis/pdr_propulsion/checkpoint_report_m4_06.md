# PDR propulsion numerical checkpoint M4-06

Conditional arithmetic only. No selected vehicle, complete cost, actual CAD mass or physical qualification.

## Central-grid results for each central mass-allowance configuration

| Configuration | Study mass kg | Required neutral thrust N | Propulsion proxy W | Full mission proxy Wh at 10 W auxiliaries | Synthetic symmetric yaw N m |
|---|---:|---:|---:|---:|---:|
| SEPARATE_3S_13__SERVO_HITEC_35245S__CONTROLLER_WING_MINI__central_allowance | 1.3545 | 13.2831 | 220.216 | 23.023 | 0.230783 |
| SEPARATE_3S_13__SERVO_HITEC_35245S__CONTROLLER_H743_WLITE__central_allowance | 1.3622 | 13.3586 | 221.998 | 23.201 | 0.234139 |
| SEPARATE_3S_13__SERVO_EMAX_0102003010__CONTROLLER_WING_MINI__central_allowance | 1.3145 | 12.8908 | 210.959 | 22.098 | 0.213349 |
| SEPARATE_3S_13__SERVO_EMAX_0102003010__CONTROLLER_H743_WLITE__central_allowance | 1.3222 | 12.9664 | 212.741 | 22.276 | 0.216705 |
| SEPARATE_4S_11__SERVO_HITEC_35245S__CONTROLLER_WING_MINI__central_allowance | 1.3595 | 13.3321 | 267.107 | 27.706 | 0.232962 |
| SEPARATE_4S_11__SERVO_HITEC_35245S__CONTROLLER_H743_WLITE__central_allowance | 1.3672 | 13.4077 | 269.206 | 27.915 | 0.236318 |
| SEPARATE_4S_11__SERVO_EMAX_0102003010__CONTROLLER_WING_MINI__central_allowance | 1.3195 | 12.9399 | 256.200 | 26.616 | 0.215528 |
| SEPARATE_4S_11__SERVO_EMAX_0102003010__CONTROLLER_H743_WLITE__central_allowance | 1.3272 | 13.0154 | 258.299 | 26.825 | 0.218884 |
| INTEGRATED_CR2816_3S__SERVO_HITEC_35245S__CONTROLLER_WING_MINI__central_allowance | 1.3025 | 12.7732 | unavailable | unavailable | unavailable |
| INTEGRATED_CR2816_3S__SERVO_HITEC_35245S__CONTROLLER_H743_WLITE__central_allowance | 1.3102 | 12.8487 | unavailable | unavailable | unavailable |
| INTEGRATED_CR2816_3S__SERVO_EMAX_0102003010__CONTROLLER_WING_MINI__central_allowance | 1.2625 | 12.3809 | unavailable | unavailable | unavailable |
| INTEGRATED_CR2816_3S__SERVO_EMAX_0102003010__CONTROLLER_H743_WLITE__central_allowance | 1.2702 | 12.4564 | unavailable | unavailable | unavailable |

## Partial procurement observations

- SEPARATE_3S_13__SERVO_HITEC_35245S__CONTROLLER_WING_MINI: known ex-tax subtotal AUD 245.42; 23 unresolved cost rows. This is not the total vehicle cost.
- SEPARATE_3S_13__SERVO_HITEC_35245S__CONTROLLER_H743_WLITE: known ex-tax subtotal AUD 245.42; 23 unresolved cost rows. This is not the total vehicle cost.
- SEPARATE_3S_13__SERVO_EMAX_0102003010__CONTROLLER_WING_MINI: known ex-tax subtotal AUD 99.98; 24 unresolved cost rows. This is not the total vehicle cost.
- SEPARATE_3S_13__SERVO_EMAX_0102003010__CONTROLLER_H743_WLITE: known ex-tax subtotal AUD 99.98; 24 unresolved cost rows. This is not the total vehicle cost.
- SEPARATE_4S_11__SERVO_HITEC_35245S__CONTROLLER_WING_MINI: known ex-tax subtotal AUD 245.42; 23 unresolved cost rows. This is not the total vehicle cost.
- SEPARATE_4S_11__SERVO_HITEC_35245S__CONTROLLER_H743_WLITE: known ex-tax subtotal AUD 245.42; 23 unresolved cost rows. This is not the total vehicle cost.
- SEPARATE_4S_11__SERVO_EMAX_0102003010__CONTROLLER_WING_MINI: known ex-tax subtotal AUD 99.98; 24 unresolved cost rows. This is not the total vehicle cost.
- SEPARATE_4S_11__SERVO_EMAX_0102003010__CONTROLLER_H743_WLITE: known ex-tax subtotal AUD 99.98; 24 unresolved cost rows. This is not the total vehicle cost.
- INTEGRATED_CR2816_3S__SERVO_HITEC_35245S__CONTROLLER_WING_MINI: known ex-tax subtotal AUD 245.42; 21 unresolved cost rows. This is not the total vehicle cost.
- INTEGRATED_CR2816_3S__SERVO_HITEC_35245S__CONTROLLER_H743_WLITE: known ex-tax subtotal AUD 245.42; 21 unresolved cost rows. This is not the total vehicle cost.
- INTEGRATED_CR2816_3S__SERVO_EMAX_0102003010__CONTROLLER_WING_MINI: known ex-tax subtotal AUD 99.98; 22 unresolved cost rows. This is not the total vehicle cost.
- INTEGRATED_CR2816_3S__SERVO_EMAX_0102003010__CONTROLLER_H743_WLITE: known ex-tax subtotal AUD 99.98; 22 unresolved cost rows. This is not the total vehicle cost.

## Evidence boundaries and remaining work

- No hardware, supplier, topology or controller is selected. Central grid values are not recommended or calibrated values.
- Masses combine commercial claims with enumerated allowances, not actual complete CAD mass. Unknown omissions and accessory overlap remain.
- Paired T_i=kT_i*Tiso_i and Q_i=kQ_i*ell_i*Tiso_i are independent exploratory corrections. Torque coefficients are not measured or inferred from KV/current.
- The paired model is neutral-axis, static and at each isolated test voltage. Rotor spacing, inflow, density correction, articulation, gyroscopic coupling and blade deformation are not resolved.
- Yaw results preserve collective thrust while changing both rotor loads. They are constrained by table range, not a qualified electrical/thermal or command envelope.
- Vendor test-current boundaries are unknown. Treating summed test input power as propulsion bus demand is an explicit study assumption; it is not motor phase-current evidence.
- Thevenin solutions assume constant terminal power and the high-voltage root. Off-test-voltage thrust is unsupported. Algebraic voltage existence is not vehicle feasibility.
- The energy proxy includes all named mission stages and auxiliary bus power once. Usable fraction is terminal energy inclusive of battery losses; I-squared-R energy is not subtracted again.
- Rotor transient electrical energy, actuator load histories and SOC-dependent battery response remain unresolved. Proxy margins cannot establish endurance compliance.
- SunnySky 40 A/30 s and Himax 20 A/15 s are not 300-second thermal qualifications. ESC catalogue ratings do not qualify installed cooling or duty.
- The 1.20-weight collective diagnostic and energy reserve grids are unapproved sensitivities, not acceptance limits.
- Motor/ESC lag and command-delay parameters are retained but not dynamically simulated here. No realizable command mapping is established.
- GNSS/range/receiver alternatives do not establish position accuracy, safety-rated abort, compatible regulated rails or runnable hopper firmware.
- Ground equipment remains separately enumerated but unpriced. Whole minimum purchase quantities and many vehicle quotations remain unresolved.
- No PyThrust execution, dependency installation, physical calibration, flight test, geometry acceptance or independent verification is performed by this program.

Next: publish actual outputs, execute an independent artifact-bound checker, send the numerical checkpoint to the Chief, reconcile actual CAD mass/ownership, complete procurement and ground pricing, and obtain missing supplier/calibration data.
