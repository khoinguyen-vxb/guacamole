# PDR-R9 source and caller inventory

Status: static diagnostic evidence only; no imports, numerical verification or repairs.

## Preservation scope

Python sources and named setup/documentation files in both supplied repositories; nested PyThrust included

Observed unchanged during this read: {"6dof_hopper": true, "PendulumControlProject": true}

## Python inventory and candidate callers

### 6dof_hopper/PyThrust/examples/calibrate_system_resistance.py

SHA-256: `bbbda8dfd8841a59c7b05bb0a0dbbe55357c21fbe4956fb68fb196b098b16ea9`


Full source for manual caller review:

```python
1: """Calibrate system resistance from a manufacturer thrust/current table.
2: 
3: This example demonstrates how to use PropulsionCalibrator to identify the
4: system resistance parameter so PyThrust's fixed-voltage propulsion model
5: matches the manufacturer's performance data.
6: 
7: Usage::
8: 
9:     PYTHONPATH=. python examples/calibrate_system_resistance.py
10: """
11: 
12: import math
13: import sys
14: from pathlib import Path
15: 
16: PROJECT_ROOT = Path(__file__).resolve().parents[1]
17: if str(PROJECT_ROOT) not in sys.path:
18:     sys.path.insert(0, str(PROJECT_ROOT))
19: 
20: from pythrust.battery import FixedVoltageBattery
21: from pythrust.propellers import PropellerDatabase
22: from pythrust.propulsion import (
23:     MotorSpec,
24:     PropellerSpec,
25:     SystemSpec,
26: )
27: from pythrust.propulsion.autotune import ManufacturerTestPoint, PropulsionCalibrator
28: 
29: # 1. Motor parameters taken directly from the manufacturer datasheet.
30: motor = MotorSpec(
31:     kv_rpm_per_v=860.0,        # RPM/V
32:     resistance_ohm=0.0258,     # Ohm, terminal resistance
33:     no_load_current_a=1.3,     # A, idle current at rated voltage
34:     current_max_a=65.0,        # A, continuous current limit
35: )
36: 
37: # 2. Fixed-voltage battery, initial system resistance, and propeller geometry.
38: battery = FixedVoltageBattery(voltage_v=14.8)   # 4S LiPo at nominal voltage
39: system = SystemSpec(resistance_ohm=0.05)        # initial guess, fitted below
40: propeller = PropellerSpec(diameter_m=0.3302)    # 13-inch propeller
41: 
42: # 3. Load propeller aerodynamic data.
43: db = PropellerDatabase()
44: db.load(Path("data/propellers/apc_202602"), strict=False)
45: prop_entry = db.get("APC_13x6.5E")
46: if prop_entry is None:
47:     raise SystemExit("Propeller 'APC_13x6.5E' not found in dataset.")
48: 
49: # 4. Manufacturer test table: RPM, thrust in grams, and battery current in amps.
50: RAW_TABLE = [
51:     {"rpm": 3897, "thrust_g": 500, "current_a": 3.9},
52:     {"rpm": 4804, "thrust_g": 750, "current_a": 6.7},
53:     {"rpm": 5421, "thrust_g": 1000, "current_a": 10.2},
54:     {"rpm": 6071, "thrust_g": 1250, "current_a": 13.9},
55:     {"rpm": 6564, "thrust_g": 1500, "current_a": 18.1},
56:     {"rpm": 7077, "thrust_g": 1750, "current_a": 22.6},
57:     {"rpm": 7560, "thrust_g": 2000, "current_a": 27.6},
58:     {"rpm": 8016, "thrust_g": 2250, "current_a": 33.5},
59:     {"rpm": 8346, "thrust_g": 2500, "current_a": 40.1},
60:     {"rpm": 8695, "thrust_g": 2750, "current_a": 47.5},
61:     {"rpm": 9230, "thrust_g": 3350, "current_a": 63.2},
62: ]
63: points = [
64:     ManufacturerTestPoint(
65:         rpm=row["rpm"],
66:         thrust_g=row["thrust_g"],
67:         current_a=row["current_a"],
68:     )
69:     for row in RAW_TABLE
70: ]
71: 
72: # 5. Calibrate the lumped system resistance.
73: calibrator = PropulsionCalibrator()
74: result = calibrator.calibrate(
75:     points, motor, battery, system, propeller, prop_entry, rho=1.225
76: )
77: 
78: print("--- Calibration Result --------------------------------------")
79: print(f"  System resistance : {result.system_resistance_ohm:.5f} ohm")
80: print(f"  Thrust RMSE       : {result.rmse_thrust_g:.1f} g")
81: print(f"  Current RMSE      : {result.rmse_current_a:.2f} A")
82: print(f"  R^2 (thrust)      : {result.r_squared_thrust:.4f}")
83: print(f"  Converged         : {result.converged}")
84: print(f"  Points used       : {result.n_points}")
85: for w in result.warnings:
86:     print(f"  WARNING: {w}")
87: print()
88: 
89: # 6. Validate by comparing predictions against the table at each RPM.
90: system_calibrated = result.to_system_spec()
91: kt = 60.0 / (2.0 * math.pi * motor.kv_rpm_per_v)
92: 
93: header = f"{'RPM':>6}  {'Thrust Pred':>12}  {'Thrust Meas':>12}  {'Thrust Err':>11}  {'Current Pred':>13}  {'Current Meas':>13}  {'Current Err':>11}"
94: print(header)
95: print("-" * len(header))
96: for pt in points:
97:     n = pt.rpm / 60.0
98:     ct, cp = prop_entry.get_coefficients(pt.rpm, 0.0)
99:     torque_nm = cp * 1.225 * (n ** 2) * (propeller.diameter_m ** 5) / (2.0 * math.pi)
100:     i_motor = torque_nm / kt + motor.no_load_current_a
101:     v_back = pt.rpm / motor.kv_rpm_per_v
102:     v_m = v_back + i_motor * motor.resistance_ohm
103:     
104:     thrust_pred_g = ct * 1.225 * (n ** 2) * (propeller.diameter_m ** 4) * 1000.0 / 9.80665
105:     current_pred_a = (v_m * i_motor + (i_motor ** 2) * system_calibrated.resistance_ohm) / battery.voltage_v
106:     
107:     t_err = thrust_pred_g - pt.thrust_g
108:     c_err = current_pred_a - pt.current_a
109:     
110:     print(
111:         f"{pt.rpm:>6.0f}  "
112:         f"{thrust_pred_g:>10.0f} g  "
113:         f"{pt.thrust_g:>10.0f} g  "
114:         f"{t_err:>+9.1f} g  "
115:         f"{current_pred_a:>11.2f} A  "
116:         f"{pt.current_a:>11.2f} A  "
117:         f"{c_err:>+9.2f} A"
118:     )
```

### 6dof_hopper/PyThrust/examples/openmdao_hover_optimization.py

SHA-256: `dbd10e0958bae8555a9687ea08c91911eb3d2563ca78e1601365809333f48992`

- Definition `main` at lines 43-216.

### 6dof_hopper/PyThrust/examples/rate_map_battery_mission.py

SHA-256: `f50afad15ba3ab830ec97149fb81593cc39c1feb5789f3657bab45f8ede1c842`

- Definition `load_propeller` at lines 32-38.
- Definition `main` at lines 41-107.

Full source for manual caller review:

```python
1: """Simulate a simple mission with a rate-map battery.
2: 
3: This example couples RateMapBattery to PropulsionSolver. Each segment solves
4: the propulsion operating point from the current battery state, then integrates
5: state of charge using the solved battery current.
6: 
7: Usage::
8: 
9:     PYTHONPATH=. python examples/rate_map_battery_mission.py
10: """
11: 
12: import sys
13: from pathlib import Path
14: 
15: PROJECT_ROOT = Path(__file__).resolve().parents[1]
16: if str(PROJECT_ROOT) not in sys.path:
17:     sys.path.insert(0, str(PROJECT_ROOT))
18: 
19: from pythrust.battery import BatteryState, RateMapBattery
20: from pythrust.propellers import PropellerDatabase
21: from pythrust.propulsion import MotorSpec, PropellerSpec, PropulsionSolver, SystemSpec
22: 
23: 
24: MISSION_SEGMENTS = [
25:     {"name": "takeoff", "duration_s": 45.0, "throttle": 0.70, "airspeed_mps": 0.0},
26:     {"name": "climb", "duration_s": 90.0, "throttle": 0.65, "airspeed_mps": 5.0},
27:     {"name": "cruise", "duration_s": 180.0, "throttle": 0.50, "airspeed_mps": 10.0},
28:     {"name": "return", "duration_s": 120.0, "throttle": 0.45, "airspeed_mps": 8.0},
29: ]
30: 
31: 
32: def load_propeller():
33:     db = PropellerDatabase()
34:     db.load(Path("data/propellers/apc_202602"), strict=False)
35:     prop_entry = db.get("APC_13x6.5E")
36:     if prop_entry is None:
37:         raise SystemExit("Propeller 'APC_13x6.5E' not found in dataset.")
38:     return prop_entry
39: 
40: 
41: def main():
42:     battery_dataset = Path("data/batteries/example_liion_cell.json")
43:     battery = RateMapBattery.from_json(battery_dataset, series=4, parallel=2)
44:     state = BatteryState(soc=0.95)
45: 
46:     motor = MotorSpec(
47:         kv_rpm_per_v=860.0,
48:         resistance_ohm=0.0258,
49:         no_load_current_a=1.3,
50:         current_max_a=65.0,
51:     )
52:     system = SystemSpec(resistance_ohm=0.095)
53:     propeller = PropellerSpec(diameter_m=0.3302)
54:     prop_entry = load_propeller()
55:     solver = PropulsionSolver()
56: 
57:     total_energy_wh = 0.0
58:     total_time_s = 0.0
59: 
60:     print("Rate-map battery mission")
61:     print(f"Pack: {battery.name}, {battery.series}S{battery.parallel}P")
62:     print(f"Initial SoC: {state.soc * 100.0:.1f}%")
63:     print()
64: 
65:     header = f"{'Segment':<10}{'min':>6}{'thr':>7}{'SoC':>17}{'I [A]':>9}{'V [V]':>9}"
66:     print(header)
67:     print("-" * len(header))
68: 
69:     for segment in MISSION_SEGMENTS:
70:         op = solver.solve_operating_point(
71:             motor=motor,
72:             battery=battery,
73:             battery_state=state,
74:             system=system,
75:             propeller=propeller,
76:             prop_entry=prop_entry,
77:             rho=1.225,
78:             airspeed_mps=segment["airspeed_mps"],
79:             throttle=segment["throttle"],
80:         )
81: 
82:         if not op.is_feasible:
83:             reason = op.infeasible_reason or "unknown"
84:             raise SystemExit(f"Mission segment '{segment['name']}' is infeasible: {reason}")
85: 
86:         battery_result = battery.integrate_current(
87:             state=state,
88:             current_a=op.battery_current_a,
89:             dt_s=segment["duration_s"],
90:         )
91:         next_state = battery_result.final_state
92: 
93:         total_energy_wh += battery_result.delivered_energy_wh
94:         total_time_s += segment["duration_s"]
95: 
96:         print(
97:             f"{segment['name']:<10}"
98:             f"{segment['duration_s'] / 60.0:>6.1f}"
99:             f"{segment['throttle'] * 100.0:>6.0f}%"
100:             f"{state.soc * 100.0:>7.1f}% -> {next_state.soc * 100.0:>5.1f}%"
101:             f"{op.battery_current_a:>9.2f}"
102:             f"{op.battery_voltage_v:>9.2f}"
103:         )
104:         state = next_state
105: 
106:     print()
107:     print(f"Summary: {total_time_s / 60.0:.1f} min, {total_energy_wh:.1f} Wh, final SoC {state.soc * 100.0:.1f}%")
108: 
109: 
110: if __name__ == "__main__":
111:     main()
```

### 6dof_hopper/PyThrust/examples/rate_map_battery_point_states.py

SHA-256: `001af20c1efcc0e5f08bfc5a9881b2db627d411ac4c0906a2e067a5aaa6b1005`

- Definition `print_point` at lines 22-33.
- Definition `main` at lines 36-59.

### 6dof_hopper/PyThrust/examples/select_motor_from_database.py

SHA-256: `ac206cf26bed8a0c7b5dd36c1a865b10b895d17bfb7313bc720c859ecb920d58`

- Definition `main` at lines 25-125.

### 6dof_hopper/PyThrust/pythrust/__init__.py

SHA-256: `4142193748ce5aa470e6e7c9e5aae3ad97d8bbb13259f464609455fe24dfe0b7`


### 6dof_hopper/PyThrust/pythrust/battery/__init__.py

SHA-256: `de66bd81737502fc7020ea5be3f523b330ae75e20a8c3d7b21587f2e8835ee8e`


Full source for manual caller review:

```python
1: """Battery models for propulsion and mission analysis."""
2: 
3: from .fixed import FixedVoltageBattery
4: from .rate_map import RateMapBattery
5: from .state import BatteryIntegrationResult, BatteryPoint, BatteryState
6: 
7: __all__ = [
8:     "BatteryIntegrationResult",
9:     "BatteryPoint",
10:     "BatteryState",
11:     "FixedVoltageBattery",
12:     "RateMapBattery",
13: ]
```

### 6dof_hopper/PyThrust/pythrust/battery/fixed.py

SHA-256: `295be468c829359addcbec5c8c12a768e44c49bf27b0321c2d74ed7bad15df75`

- Definition `FixedVoltageBattery` at lines 11-34.
- Definition `FixedVoltageBattery.terminal_voltage` at lines 20-26.
- Definition `FixedVoltageBattery.terminal_power` at lines 28-34.

Full source for manual caller review:

```python
1: """Fixed-voltage battery model."""
2: 
3: from __future__ import annotations
4: 
5: from dataclasses import dataclass
6: 
7: from .state import BatteryState
8: 
9: 
10: @dataclass(frozen=True)
11: class FixedVoltageBattery:
12:     """Battery model with constant pack voltage.
13: 
14:     This is the historical PyThrust battery model under a more explicit name.
15:     """
16: 
17:     voltage_v: float
18:     discharge_efficiency: float = 1.0
19: 
20:     def terminal_voltage(
21:         self,
22:         current_a: float = 0.0,
23:         state: BatteryState | None = None,
24:     ) -> float:
25:         """Return pack voltage for the requested current and state."""
26:         return self.voltage_v
27: 
28:     def terminal_power(
29:         self,
30:         current_a: float,
31:         state: BatteryState | None = None,
32:     ) -> float:
33:         """Return battery-side power draw using the fixed-voltage efficiency."""
34:         return self.voltage_v * current_a / max(1e-12, self.discharge_efficiency)
```

### 6dof_hopper/PyThrust/pythrust/battery/rate_map.py

SHA-256: `b022873a21892005fbc4333584fc5d5a45fd808f467f92031a5084c11051090c`

- Definition `RateMapBattery` at lines 18-968.
- Definition `RateMapBattery.__post_init__` at lines 33-57.
- Definition `RateMapBattery.from_json` at lines 60-85.
- Definition `RateMapBattery.capacity_as` at lines 88-90.
- Definition `RateMapBattery.rated_current_a` at lines 93-95.
- Definition `RateMapBattery.ocv` at lines 97-99.
- Definition `RateMapBattery.resistance` at lines 101-103.
- Definition `RateMapBattery.terminal_voltage` at lines 105-107.
- Definition `RateMapBattery.terminal_power` at lines 109-111.
- Definition `RateMapBattery.state_at_current` at lines 113-126.
- Definition `RateMapBattery.state_at_c_rate` at lines 128-133.
- Definition `RateMapBattery.state_at_voltage` at lines 135-148.
- Definition `RateMapBattery.state_at_power` at lines 150-181.
- Definition `RateMapBattery.state_at_load_resistance` at lines 183-200.
- Definition `RateMapBattery.state_at_power_loss` at lines 202-211.
- Definition `RateMapBattery.step_current` at lines 213-219.
- Definition `RateMapBattery.step_power` at lines 221-226.
- Definition `RateMapBattery.integrate_current` at lines 228-243.
- Definition `RateMapBattery.integrate_c_rate` at lines 245-261.
- Definition `RateMapBattery.integrate_power` at lines 263-278.
- Definition `RateMapBattery.integrate_voltage` at lines 280-295.
- Definition `RateMapBattery.integrate_load_resistance` at lines 297-314.
- Definition `RateMapBattery.integrate_power_loss` at lines 316-331.
- Definition `RateMapBattery.integrate_current_to_dod` at lines 333-348.
- Definition `RateMapBattery.integrate_c_rate_to_dod` at lines 350-366.
- Definition `RateMapBattery.integrate_power_to_dod` at lines 368-383.
- Definition `RateMapBattery.integrate_voltage_to_dod` at lines 385-400.
- Definition `RateMapBattery.integrate_load_resistance_to_dod` at lines 402-419.
- Definition `RateMapBattery.integrate_power_loss_to_dod` at lines 421-436.
- Definition `RateMapBattery.dod_at_voltage_power` at lines 438-444.
- Definition `RateMapBattery.dod_at_power_voltage` at lines 446-452.
- Definition `RateMapBattery.integrate_power_profile` at lines 454-519.
- Definition `RateMapBattery.energy_knockdown_dod` at lines 521-535.
- Definition `RateMapBattery.energy_knockdown_c_rate` at lines 537-553.
- Definition `RateMapBattery._point_from_cell_state` at lines 555-590.
- Definition `RateMapBattery._clip_dod` at lines 593-599.
- Definition `RateMapBattery._reversible_energy_wh` at lines 601-605.
- Definition `RateMapBattery._usable_energy_at_c_rate` at lines 607-616.
- Definition `RateMapBattery._integrate_with_point_function` at lines 618-708.
- Definition `RateMapBattery._integrate_with_point_function.rhs` at lines 657-664.
- Definition `RateMapBattery._integrate_to_dod` at lines 710-799.
- Definition `RateMapBattery._integrate_to_dod.rhs` at lines 746-755.
- Definition `RateMapBattery._solve_dod` at lines 801-826.
- Definition `RateMapBattery._time_integration_events` at lines 828-840.
- Definition `RateMapBattery._time_integration_events.event` at lines 832-836.
- Definition `RateMapBattery._dod_integration_events` at lines 842-853.
- Definition `RateMapBattery._dod_integration_events.event` at lines 846-849.
- Definition `RateMapBattery._feasibility_margin` at lines 855-861.
- Definition `RateMapBattery._stop_reason` at lines 863-873.
- Definition `RateMapBattery._validate_integration_inputs` at lines 876-882.
- Definition `RateMapBattery._validate_dod_interval` at lines 885-891.
- Definition `RateMapBattery._initial_integration_histories` at lines 894-903.
- Definition `RateMapBattery._append_integration_sample` at lines 906-918.
- Definition `RateMapBattery._integration_result` at lines 921-942.
- Definition `RateMapBattery._histories_from_result` at lines 945-954.
- Definition `RateMapBattery._extend_profile_histories` at lines 957-968.
- Candidate caller `RateMapBattery._integrate_with_point_function` -> `solve_ivp` at line 667.
- Candidate caller `RateMapBattery._integrate_to_dod` -> `solve_ivp` at line 758.

Full source for manual caller review:

```python
1: """Rate-map battery model."""
2: 
3: from __future__ import annotations
4: 
5: from dataclasses import dataclass
6: import json
7: import math
8: from pathlib import Path
9: from typing import Callable, Sequence
10: 
11: import numpy as np
12: from scipy.integrate import solve_ivp
13: 
14: from .state import BatteryIntegrationResult, BatteryPoint, BatteryState
15: 
16: 
17: @dataclass(frozen=True)
18: class RateMapBattery:
19:     """Equivalent-circuit battery model driven by OCV and resistance curves."""
20: 
21:     name: str
22:     capacity_ah: float
23:     cutoff_voltage_v: float
24:     charge_voltage_v: float
25:     max_current_a: float
26:     series: int
27:     parallel: int
28:     dod: Sequence[float]
29:     ocv_v: Sequence[float]
30:     resistance_ohm: Sequence[float]
31:     source: str | None = None
32: 
33:     def __post_init__(self) -> None:
34:         dod = tuple(float(v) for v in self.dod)
35:         ocv_v = tuple(float(v) for v in self.ocv_v)
36:         resistance_ohm = tuple(float(v) for v in self.resistance_ohm)
37: 
38:         if len(dod) < 2:
39:             raise ValueError("dod must contain at least two points")
40:         if not (len(dod) == len(ocv_v) == len(resistance_ohm)):
41:             raise ValueError("dod, ocv_v, and resistance_ohm must have the same length")
42:         if any(v < 0.0 or v > 1.0 for v in dod):
43:             raise ValueError("dod values must be between 0 and 1")
44:         if any(b <= a for a, b in zip(dod, dod[1:])):
45:             raise ValueError("dod values must be strictly increasing")
46:         if any(v <= 0.0 for v in resistance_ohm):
47:             raise ValueError("resistance_ohm values must be positive")
48:         if self.capacity_ah <= 0.0:
49:             raise ValueError("capacity_ah must be positive")
50:         if self.max_current_a <= 0.0:
51:             raise ValueError("max_current_a must be positive")
52:         if self.series <= 0 or self.parallel <= 0:
53:             raise ValueError("series and parallel counts must be positive")
54: 
55:         object.__setattr__(self, "dod", dod)
56:         object.__setattr__(self, "ocv_v", ocv_v)
57:         object.__setattr__(self, "resistance_ohm", resistance_ohm)
58: 
59:     @classmethod
60:     def from_json(
61:         cls,
62:         path: str | Path,
63:         *,
64:         series: int = 1,
65:         parallel: int = 1,
66:     ) -> "RateMapBattery":
67:         """Load a cell dataset and apply pack series/parallel topology."""
68:         with Path(path).open("r", encoding="utf-8") as f:
69:             data = json.load(f)
70: 
71:         cell = data["cell"]
72:         curves = data["curves"]
73:         return cls(
74:             name=data.get("name", "Rate-map cell"),
75:             source=data.get("source"),
76:             capacity_ah=cell["capacity_ah"],
77:             cutoff_voltage_v=cell["cutoff_voltage_v"],
78:             charge_voltage_v=cell["charge_voltage_v"],
79:             max_current_a=cell["max_current_a"],
80:             series=series,
81:             parallel=parallel,
82:             dod=curves["dod"],
83:             ocv_v=curves["ocv_v"],
84:             resistance_ohm=curves["resistance_ohm"],
85:         )
86: 
87:     @property
88:     def capacity_as(self) -> float:
89:         """Cell capacity in ampere-seconds."""
90:         return self.capacity_ah * 3600.0
91: 
92:     @property
93:     def rated_current_a(self) -> float:
94:         """Cell 1C current in amps."""
95:         return self.capacity_ah
96: 
97:     def ocv(self, dod: float) -> float:
98:         """Interpolate open-circuit cell voltage at depth of discharge."""
99:         return float(np.interp(self._clip_dod(dod), self.dod, self.ocv_v))
100: 
101:     def resistance(self, dod: float) -> float:
102:         """Interpolate cell resistance at depth of discharge."""
103:         return float(np.interp(self._clip_dod(dod), self.dod, self.resistance_ohm))
104: 
105:     def terminal_voltage(self, current_a: float, state: BatteryState) -> float:
106:         """Return pack terminal voltage at pack current and battery state."""
107:         return self.state_at_current(state=state, current_a=current_a).terminal_voltage_v
108: 
109:     def terminal_power(self, current_a: float, state: BatteryState) -> float:
110:         """Return pack terminal power at pack current and battery state."""
111:         return self.state_at_current(state=state, current_a=current_a).power_w
112: 
113:     def state_at_current(self, state: BatteryState, current_a: float) -> BatteryPoint:
114:         """Evaluate battery point state for a specified pack current."""
115:         cell_current_a = current_a / self.parallel
116:         dod = state.dod
117:         ocv_v = self.ocv(dod)
118:         resistance_ohm = self.resistance(dod)
119:         cell_voltage_v = ocv_v - resistance_ohm * cell_current_a
120:         return self._point_from_cell_state(
121:             state=state,
122:             cell_current_a=cell_current_a,
123:             cell_voltage_v=cell_voltage_v,
124:             ocv_v=ocv_v,
125:             resistance_ohm=resistance_ohm,
126:         )
127: 
128:     def state_at_c_rate(self, state: BatteryState, c_rate: float) -> BatteryPoint:
129:         """Evaluate battery point state for a specified cell C-rate."""
130:         return self.state_at_current(
131:             state=state,
132:             current_a=c_rate * self.rated_current_a * self.parallel,
133:         )
134: 
135:     def state_at_voltage(self, state: BatteryState, voltage_v: float) -> BatteryPoint:
136:         """Evaluate battery point state for a specified pack voltage."""
137:         cell_voltage_v = voltage_v / self.series
138:         dod = state.dod
139:         ocv_v = self.ocv(dod)
140:         resistance_ohm = self.resistance(dod)
141:         cell_current_a = (ocv_v - cell_voltage_v) / resistance_ohm
142:         return self._point_from_cell_state(
143:             state=state,
144:             cell_current_a=cell_current_a,
145:             cell_voltage_v=cell_voltage_v,
146:             ocv_v=ocv_v,
147:             resistance_ohm=resistance_ohm,
148:         )
149: 
150:     def state_at_power(self, state: BatteryState, power_w: float) -> BatteryPoint:
151:         """Evaluate battery point state for a specified pack power draw."""
152:         dod = state.dod
153:         ocv_v = self.ocv(dod)
154:         resistance_ohm = self.resistance(dod)
155:         cell_power_w = power_w / (self.series * self.parallel)
156:         discriminant = ocv_v**2 - 4.0 * resistance_ohm * cell_power_w
157: 
158:         if discriminant < 0.0:
159:             return BatteryPoint(
160:                 terminal_voltage_v=0.0,
161:                 current_a=0.0,
162:                 power_w=0.0,
163:                 cell_voltage_v=0.0,
164:                 cell_current_a=0.0,
165:                 c_rate=0.0,
166:                 efficiency=0.0,
167:                 ocv_v=ocv_v,
168:                 resistance_ohm=resistance_ohm,
169:                 is_feasible=False,
170:                 infeasible_reason="power_limit",
171:             )
172: 
173:         cell_current_a = (ocv_v - math.sqrt(discriminant)) / (2.0 * resistance_ohm)
174:         cell_voltage_v = ocv_v - resistance_ohm * cell_current_a
175:         return self._point_from_cell_state(
176:             state=state,
177:             cell_current_a=cell_current_a,
178:             cell_voltage_v=cell_voltage_v,
179:             ocv_v=ocv_v,
180:             resistance_ohm=resistance_ohm,
181:         )
182: 
183:     def state_at_load_resistance(self, state: BatteryState, resistance_ohm: float) -> BatteryPoint:
184:         """Evaluate battery point state for a specified pack load resistance."""
185:         if resistance_ohm <= 0.0:
186:             raise ValueError("load resistance must be positive")
187: 
188:         dod = state.dod
189:         ocv_v = self.ocv(dod)
190:         cell_internal_ohm = self.resistance(dod)
191:         cell_load_ohm = resistance_ohm * self.parallel / self.series
192:         cell_current_a = ocv_v / (cell_internal_ohm + cell_load_ohm)
193:         cell_voltage_v = ocv_v - cell_internal_ohm * cell_current_a
194:         return self._point_from_cell_state(
195:             state=state,
196:             cell_current_a=cell_current_a,
197:             cell_voltage_v=cell_voltage_v,
198:             ocv_v=ocv_v,
199:             resistance_ohm=cell_internal_ohm,
200:         )
201: 
202:     def state_at_power_loss(self, state: BatteryState, power_loss_w: float) -> BatteryPoint:
203:         """Evaluate battery point state for a specified pack internal power loss."""
204:         if not math.isfinite(power_loss_w) or power_loss_w < 0.0:
205:             raise ValueError("power_loss_w must be finite and non-negative")
206: 
207:         dod = state.dod
208:         resistance_ohm = self.resistance(dod)
209:         cell_power_loss_w = power_loss_w / (self.series * self.parallel)
210:         cell_current_a = math.sqrt(cell_power_loss_w / resistance_ohm) if cell_power_loss_w > 0.0 else 0.0
211:         return self.state_at_current(state=state, current_a=cell_current_a * self.parallel)
212: 
213:     def step_current(self, state: BatteryState, current_a: float, dt_s: float) -> BatteryState:
214:         """Advance state using constant pack current over a time step."""
215:         if dt_s < 0.0:
216:             raise ValueError("dt_s must be non-negative")
217:         cell_current_a = current_a / self.parallel
218:         dod_next = state.dod + cell_current_a * dt_s / self.capacity_as
219:         return BatteryState.from_dod(min(1.0, max(0.0, dod_next)))
220: 
221:     def step_power(self, state: BatteryState, power_w: float, dt_s: float) -> BatteryState:
222:         """Advance state using constant pack power over a time step."""
223:         point = self.state_at_power(state=state, power_w=power_w)
224:         if not point.is_feasible:
225:             raise ValueError(point.infeasible_reason or "infeasible battery power")
226:         return self.step_current(state=state, current_a=point.current_a, dt_s=dt_s)
227: 
228:     def integrate_current(
229:         self,
230:         state: BatteryState,
231:         current_a: float,
232:         dt_s: float,
233:         *,
234:         max_step_s: float = 1.0,
235:     ) -> BatteryIntegrationResult:
236:         """Integrate battery state under constant pack current."""
237:         self._validate_integration_inputs(current_a, dt_s, max_step_s, "current_a")
238:         return self._integrate_with_point_function(
239:             state=state,
240:             dt_s=dt_s,
241:             max_step_s=max_step_s,
242:             point_function=lambda current_state: self.state_at_current(current_state, current_a),
243:         )
244: 
245:     def integrate_c_rate(
246:         self,
247:         state: BatteryState,
248:         c_rate: float,
249:         dt_s: float,
250:         *,
251:         max_step_s: float = 1.0,
252:     ) -> BatteryIntegrationResult:
253:         """Integrate battery state under constant cell C-rate."""
254:         if not math.isfinite(c_rate) or c_rate < 0.0:
255:             raise ValueError("c_rate must be finite and non-negative")
256:         return self.integrate_current(
257:             state=state,
258:             current_a=c_rate * self.rated_current_a * self.parallel,
259:             dt_s=dt_s,
260:             max_step_s=max_step_s,
261:         )
262: 
263:     def integrate_power(
264:         self,
265:         state: BatteryState,
266:         power_w: float,
267:         dt_s: float,
268:         *,
269:         max_step_s: float = 1.0,
270:     ) -> BatteryIntegrationResult:
271:         """Integrate battery state under constant pack power draw."""
272:         self._validate_integration_inputs(power_w, dt_s, max_step_s, "power_w")
273:         return self._integrate_with_point_function(
274:             state=state,
275:             dt_s=dt_s,
276:             max_step_s=max_step_s,
277:             point_function=lambda current_state: self.state_at_power(current_state, power_w),
278:         )
279: 
280:     def integrate_voltage(
281:         self,
282:         state: BatteryState,
283:         voltage_v: float,
284:         dt_s: float,
285:         *,
286:         max_step_s: float = 1.0,
287:     ) -> BatteryIntegrationResult:
288:         """Integrate battery state under constant pack terminal voltage."""
289:         self._validate_integration_inputs(voltage_v, dt_s, max_step_s, "voltage_v")
290:         return self._integrate_with_point_function(
291:             state=state,
292:             dt_s=dt_s,
293:             max_step_s=max_step_s,
294:             point_function=lambda current_state: self.state_at_voltage(current_state, voltage_v),
295:         )
296: 
297:     def integrate_load_resistance(
298:         self,
299:         state: BatteryState,
300:         resistance_ohm: float,
301:         dt_s: float,
302:         *,
303:         max_step_s: float = 1.0,
304:     ) -> BatteryIntegrationResult:
305:         """Integrate battery state under constant pack load resistance."""
306:         if not math.isfinite(resistance_ohm) or resistance_ohm <= 0.0:
307:             raise ValueError("resistance_ohm must be finite and positive")
308:         self._validate_integration_inputs(0.0, dt_s, max_step_s, "load")
309:         return self._integrate_with_point_function(
310:             state=state,
311:             dt_s=dt_s,
312:             max_step_s=max_step_s,
313:             point_function=lambda current_state: self.state_at_load_resistance(current_state, resistance_ohm),
314:         )
315: 
316:     def integrate_power_loss(
317:         self,
318:         state: BatteryState,
319:         power_loss_w: float,
320:         dt_s: float,
321:         *,
322:         max_step_s: float = 1.0,
323:     ) -> BatteryIntegrationResult:
324:         """Integrate battery state under constant pack internal power loss."""
325:         self._validate_integration_inputs(power_loss_w, dt_s, max_step_s, "power_loss_w")
326:         return self._integrate_with_point_function(
327:             state=state,
328:             dt_s=dt_s,
329:             max_step_s=max_step_s,
330:             point_function=lambda current_state: self.state_at_power_loss(current_state, power_loss_w),
331:         )
332: 
333:     def integrate_current_to_dod(
334:         self,
335:         state: BatteryState,
336:         current_a: float,
337:         dod_final: float,
338:         *,
339:         max_step_s: float = 1.0,
340:     ) -> BatteryIntegrationResult:
341:         """Integrate constant current until a target DOD is reached."""
342:         self._validate_integration_inputs(current_a, 0.0, max_step_s, "current_a")
343:         return self._integrate_to_dod(
344:             state=state,
345:             dod_final=dod_final,
346:             max_step_s=max_step_s,
347:             point_function=lambda current_state: self.state_at_current(current_state, current_a),
348:         )
349: 
350:     def integrate_c_rate_to_dod(
351:         self,
352:         state: BatteryState,
353:         c_rate: float,
354:         dod_final: float,
355:         *,
356:         max_step_s: float = 1.0,
357:     ) -> BatteryIntegrationResult:
358:         """Integrate constant cell C-rate until a target DOD is reached."""
359:         if not math.isfinite(c_rate) or c_rate < 0.0:
360:             raise ValueError("c_rate must be finite and non-negative")
361:         return self.integrate_current_to_dod(
362:             state=state,
363:             current_a=c_rate * self.rated_current_a * self.parallel,
364:             dod_final=dod_final,
365:             max_step_s=max_step_s,
366:         )
367: 
368:     def integrate_power_to_dod(
369:         self,
370:         state: BatteryState,
371:         power_w: float,
372:         dod_final: float,
373:         *,
374:         max_step_s: float = 1.0,
375:     ) -> BatteryIntegrationResult:
376:         """Integrate constant pack power until a target DOD is reached."""
377:         self._validate_integration_inputs(power_w, 0.0, max_step_s, "power_w")
378:         return self._integrate_to_dod(
379:             state=state,
380:             dod_final=dod_final,
381:             max_step_s=max_step_s,
382:             point_function=lambda current_state: self.state_at_power(current_state, power_w),
383:         )
384: 
385:     def integrate_voltage_to_dod(
386:         self,
387:         state: BatteryState,
388:         voltage_v: float,
389:         dod_final: float,
390:         *,
391:         max_step_s: float = 1.0,
392:     ) -> BatteryIntegrationResult:
393:         """Integrate constant pack terminal voltage until a target DOD is reached."""
394:         self._validate_integration_inputs(voltage_v, 0.0, max_step_s, "voltage_v")
395:         return self._integrate_to_dod(
396:             state=state,
397:             dod_final=dod_final,
398:             max_step_s=max_step_s,
399:             point_function=lambda current_state: self.state_at_voltage(current_state, voltage_v),
400:         )
401: 
402:     def integrate_load_resistance_to_dod(
403:         self,
404:         state: BatteryState,
405:         resistance_ohm: float,
406:         dod_final: float,
407:         *,
408:         max_step_s: float = 1.0,
409:     ) -> BatteryIntegrationResult:
410:         """Integrate constant pack load resistance until a target DOD is reached."""
411:         if not math.isfinite(resistance_ohm) or resistance_ohm <= 0.0:
412:             raise ValueError("resistance_ohm must be finite and positive")
413:         self._validate_integration_inputs(0.0, 0.0, max_step_s, "load")
414:         return self._integrate_to_dod(
415:             state=state,
416:             dod_final=dod_final,
417:             max_step_s=max_step_s,
418:             point_function=lambda current_state: self.state_at_load_resistance(current_state, resistance_ohm),
419:         )
420: 
421:     def integrate_power_loss_to_dod(
422:         self,
423:         state: BatteryState,
424:         power_loss_w: float,
425:         dod_final: float,
426:         *,
427:         max_step_s: float = 1.0,
428:     ) -> BatteryIntegrationResult:
429:         """Integrate constant pack internal power loss until a target DOD is reached."""
430:         self._validate_integration_inputs(power_loss_w, 0.0, max_step_s, "power_loss_w")
431:         return self._integrate_to_dod(
432:             state=state,
433:             dod_final=dod_final,
434:             max_step_s=max_step_s,
435:             point_function=lambda current_state: self.state_at_power_loss(current_state, power_loss_w),
436:         )
437: 
438:     def dod_at_voltage_power(self, voltage_v: float, power_w: float) -> float:
439:         """Solve DOD where constant-voltage and requested-power states coincide."""
440:         self._validate_integration_inputs(voltage_v, 0.0, 1.0, "voltage_v")
441:         self._validate_integration_inputs(power_w, 0.0, 1.0, "power_w")
442:         return self._solve_dod(
443:             lambda dod: self.state_at_voltage(BatteryState.from_dod(dod), voltage_v).power_w - power_w
444:         )
445: 
446:     def dod_at_power_voltage(self, power_w: float, voltage_v: float) -> float:
447:         """Solve DOD where constant-power and requested-voltage states coincide."""
448:         self._validate_integration_inputs(power_w, 0.0, 1.0, "power_w")
449:         self._validate_integration_inputs(voltage_v, 0.0, 1.0, "voltage_v")
450:         return self._solve_dod(
451:             lambda dod: self.state_at_power(BatteryState.from_dod(dod), power_w).terminal_voltage_v - voltage_v
452:         )
453: 
454:     def integrate_power_profile(
455:         self,
456:         state: BatteryState,
457:         power_w: Sequence[float],
458:         durations_s: Sequence[float],
459:         *,
460:         max_step_s: float = 1.0,
461:     ) -> BatteryIntegrationResult:
462:         """Integrate consecutive constant-power segments into one time history."""
463:         if len(power_w) != len(durations_s):
464:             raise ValueError("power_w and durations_s must have the same length")
465:         if len(power_w) == 0:
466:             point = self.state_at_power(state=state, power_w=0.0)
467:             return self._integration_result(
468:                 final_state=state,
469:                 histories=self._initial_integration_histories(state, point),
470:                 delivered_energy_wh=0.0,
471:                 consumed_charge_ah=0.0,
472:                 is_feasible=True,
473:                 stop_reason="duration_complete",
474:             )
475:         if not math.isfinite(max_step_s) or max_step_s <= 0.0:
476:             raise ValueError("max_step_s must be finite and positive")
477: 
478:         histories: dict[str, list[float]] | None = None
479:         current_state = state
480:         elapsed_s = 0.0
481:         delivered_energy_wh = 0.0
482:         consumed_charge_ah = 0.0
483: 
484:         for power, duration_s in zip(power_w, durations_s):
485:             result = self.integrate_power(
486:                 state=current_state,
487:                 power_w=power,
488:                 dt_s=duration_s,
489:                 max_step_s=max_step_s,
490:             )
491:             if histories is None:
492:                 histories = {name: list(values) for name, values in self._histories_from_result(result).items()}
493:             else:
494:                 self._extend_profile_histories(histories, result, elapsed_s)
495: 
496:             elapsed_s = histories["time_s"][-1]
497:             delivered_energy_wh += result.delivered_energy_wh
498:             consumed_charge_ah += result.consumed_charge_ah
499:             current_state = result.final_state
500:             if not result.is_feasible:
501:                 return self._integration_result(
502:                     final_state=current_state,
503:                     histories=histories,
504:                     delivered_energy_wh=delivered_energy_wh,
505:                     consumed_charge_ah=consumed_charge_ah,
506:                     is_feasible=False,
507:                     stop_reason=result.stop_reason,
508:                 )
509: 
510:         if histories is None:
511:             raise RuntimeError("integration profile did not produce histories")
512:         return self._integration_result(
513:             final_state=current_state,
514:             histories=histories,
515:             delivered_energy_wh=delivered_energy_wh,
516:             consumed_charge_ah=consumed_charge_ah,
517:             is_feasible=True,
518:             stop_reason="duration_complete",
519:         )
520: 
521:     def energy_knockdown_dod(
522:         self,
523:         dod_initial: float,
524:         dod_final: float,
525:         *,
526:         samples: int = 1001,
527:     ) -> float:
528:         """Return reversible energy fraction available over a DOD interval."""
529:         self._validate_dod_interval(dod_initial, dod_final)
530:         if samples < 2:
531:             raise ValueError("samples must be at least 2")
532: 
533:         total_energy_wh = self._reversible_energy_wh(0.0, 1.0, samples=samples)
534:         interval_energy_wh = self._reversible_energy_wh(dod_initial, dod_final, samples=samples)
535:         return interval_energy_wh / total_energy_wh
536: 
537:     def energy_knockdown_c_rate(
538:         self,
539:         c_rate: float,
540:         *,
541:         max_step_s: float = 1.0,
542:     ) -> float:
543:         """Return usable-energy fraction at C-rate relative to reversible energy."""
544:         if not math.isfinite(c_rate) or c_rate < 0.0:
545:             raise ValueError("c_rate must be finite and non-negative")
546:         if not math.isfinite(max_step_s) or max_step_s <= 0.0:
547:             raise ValueError("max_step_s must be finite and positive")
548:         if c_rate == 0.0:
549:             return 1.0
550: 
551:         energy_wh = self._usable_energy_at_c_rate(c_rate, max_step_s=max_step_s)
552:         reversible_energy_wh = self._reversible_energy_wh(0.0, 1.0, samples=1001)
553:         return energy_wh / reversible_energy_wh
554: 
555:     def _point_from_cell_state(
556:         self,
557:         state: BatteryState,
558:         cell_current_a: float,
559:         cell_voltage_v: float,
560:         ocv_v: float,
561:         resistance_ohm: float,
562:     ) -> BatteryPoint:
563:         pack_current_a = cell_current_a * self.parallel
564:         pack_voltage_v = cell_voltage_v * self.series
565:         c_rate = cell_current_a / self.rated_current_a
566:         efficiency = cell_voltage_v / ocv_v if ocv_v > 0.0 else 0.0
567:         reason = None
568: 
569:         if cell_current_a > self.max_current_a:
570:             reason = "current_limit"
571:         if reason is None and cell_voltage_v < self.cutoff_voltage_v:
572:             reason = "voltage_cutoff"
573:         if reason is None and cell_voltage_v > self.charge_voltage_v:
574:             reason = "voltage_limit"
575:         if reason is None and (state.dod < 0.0 or state.dod > 1.0):
576:             reason = "state_limit"
577: 
578:         return BatteryPoint(
579:             terminal_voltage_v=float(pack_voltage_v),
580:             current_a=float(pack_current_a),
581:             power_w=float(pack_voltage_v * pack_current_a),
582:             cell_voltage_v=float(cell_voltage_v),
583:             cell_current_a=float(cell_current_a),
584:             c_rate=float(c_rate),
585:             efficiency=float(efficiency),
586:             ocv_v=float(ocv_v),
587:             resistance_ohm=float(resistance_ohm),
588:             is_feasible=reason is None,
589:             infeasible_reason=reason,
590:         )
591: 
592:     @staticmethod
593:     def _clip_dod(dod: float) -> float:
594:         clipped = min(1.0, max(0.0, float(dod)))
595:         if math.isclose(clipped, 0.0, rel_tol=0.0, abs_tol=1e-12):
596:             return 0.0
597:         if math.isclose(clipped, 1.0, rel_tol=0.0, abs_tol=1e-12):
598:             return 1.0
599:         return clipped
600: 
601:     def _reversible_energy_wh(self, dod_initial: float, dod_final: float, *, samples: int) -> float:
602:         dod_values = np.linspace(dod_initial, dod_final, samples)
603:         ocv_values = np.array([self.ocv(float(dod)) for dod in dod_values])
604:         cell_energy_wh = float(np.trapezoid(ocv_values, dod_values)) * self.capacity_ah
605:         return cell_energy_wh * self.series * self.parallel
606: 
607:     def _usable_energy_at_c_rate(self, c_rate: float, *, max_step_s: float) -> float:
608:         current_a = c_rate * self.rated_current_a * self.parallel
609:         duration_s = self.capacity_as / (self.rated_current_a * c_rate) if c_rate > 0.0 else 0.0
610:         result = self.integrate_current(
611:             state=BatteryState(soc=1.0),
612:             current_a=current_a,
613:             dt_s=duration_s,
614:             max_step_s=max_step_s,
615:         )
616:         return result.delivered_energy_wh
617: 
618:     def _integrate_with_point_function(
619:         self,
620:         state: BatteryState,
621:         dt_s: float,
622:         max_step_s: float,
623:         point_function: Callable[[BatteryState], BatteryPoint],
624:     ) -> BatteryIntegrationResult:
625:         initial_point = point_function(state)
626:         histories = self._initial_integration_histories(state, initial_point)
627: 
628:         if not initial_point.is_feasible:
629:             return self._integration_result(
630:                 final_state=state,
631:                 histories=histories,
632:                 delivered_energy_wh=0.0,
633:                 consumed_charge_ah=0.0,
634:                 is_feasible=False,
635:                 stop_reason=initial_point.infeasible_reason or "infeasible_state",
636:             )
637:         if dt_s == 0.0:
638:             return self._integration_result(
639:                 final_state=state,
640:                 histories=histories,
641:                 delivered_energy_wh=0.0,
642:                 consumed_charge_ah=0.0,
643:                 is_feasible=True,
644:                 stop_reason="duration_complete",
645:             )
646:         if initial_point.current_a == 0.0:
647:             self._append_integration_sample(histories, dt_s, state, initial_point)
648:             return self._integration_result(
649:                 final_state=state,
650:                 histories=histories,
651:                 delivered_energy_wh=0.0,
652:                 consumed_charge_ah=0.0,
653:                 is_feasible=True,
654:                 stop_reason="duration_complete",
655:             )
656: 
657:         def rhs(_time_s: float, values: np.ndarray) -> list[float]:
658:             state_at_t = BatteryState.from_dod(self._clip_dod(float(values[0])))
659:             point = point_function(state_at_t)
660:             return [
661:                 point.cell_current_a / self.capacity_as,
662:                 point.power_w / 3600.0,
663:                 point.current_a / 3600.0,
664:             ]
665: 
666:         events = self._time_integration_events(point_function)
667:         solution = solve_ivp(
668:             rhs,
669:             (0.0, dt_s),
670:             [state.dod, 0.0, 0.0],
671:             events=events,
672:             max_step=max_step_s,
673:             rtol=1e-9,
674:             atol=1e-11,
675:         )
676:         if not solution.success:
677:             raise RuntimeError(solution.message)
678: 
679:         histories = {
680:             "time_s": [],
681:             "dod": [],
682:             "voltage_v": [],
683:             "current_a": [],
684:             "c_rate": [],
685:             "power_w": [],
686:             "efficiency": [],
687:         }
688:         for time_s, dod in zip(solution.t, solution.y[0]):
689:             sample_state = BatteryState.from_dod(self._clip_dod(float(dod)))
690:             sample_point = point_function(sample_state)
691:             self._append_integration_sample(histories, float(time_s), sample_state, sample_point)
692: 
693:         final_state = BatteryState.from_dod(self._clip_dod(float(solution.y[0, -1])))
694:         final_point = point_function(final_state)
695:         stop_reason = "duration_complete"
696:         is_feasible = True
697:         if solution.t[-1] < dt_s - 1e-9:
698:             stop_reason = self._stop_reason(final_state, final_point)
699:             is_feasible = False
700: 
701:         return self._integration_result(
702:             final_state=final_state,
703:             histories=histories,
704:             delivered_energy_wh=float(solution.y[1, -1]),
705:             consumed_charge_ah=float(solution.y[2, -1]),
706:             is_feasible=is_feasible,
707:             stop_reason=stop_reason,
708:         )
709: 
710:     def _integrate_to_dod(
711:         self,
712:         state: BatteryState,
713:         dod_final: float,
714:         max_step_s: float,
715:         point_function: Callable[[BatteryState], BatteryPoint],
716:     ) -> BatteryIntegrationResult:
717:         if not math.isfinite(dod_final) or dod_final < 0.0 or dod_final > 1.0:
718:             raise ValueError("dod_final must be finite and between 0 and 1")
719:         if dod_final <= state.dod:
720:             raise ValueError("dod_final must be greater than the initial DOD")
721: 
722:         initial_point = point_function(state)
723:         histories = self._initial_integration_histories(state, initial_point)
724: 
725:         if not initial_point.is_feasible:
726:             return self._integration_result(
727:                 final_state=state,
728:                 histories=histories,
729:                 delivered_energy_wh=0.0,
730:                 consumed_charge_ah=0.0,
731:                 is_feasible=False,
732:                 stop_reason=initial_point.infeasible_reason or "infeasible_state",
733:             )
734:         if initial_point.current_a <= 0.0:
735:             return self._integration_result(
736:                 final_state=state,
737:                 histories=histories,
738:                 delivered_energy_wh=0.0,
739:                 consumed_charge_ah=0.0,
740:                 is_feasible=False,
741:                 stop_reason="zero_discharge_current",
742:             )
743: 
744:         max_dod_step = max_step_s * initial_point.cell_current_a / self.capacity_as
745: 
746:         def rhs(dod: float, _values: np.ndarray) -> list[float]:
747:             state_at_dod = BatteryState.from_dod(self._clip_dod(dod))
748:             point = point_function(state_at_dod)
749:             if point.cell_current_a <= 0.0:
750:                 return [0.0, 0.0, 0.0]
751:             return [
752:                 self.capacity_as / point.cell_current_a,
753:                 point.terminal_voltage_v * self.capacity_ah * self.parallel,
754:                 self.capacity_ah * self.parallel,
755:             ]
756: 
757:         events = self._dod_integration_events(point_function)
758:         solution = solve_ivp(
759:             rhs,
760:             (state.dod, dod_final),
761:             [0.0, 0.0, 0.0],
762:             events=events,
763:             max_step=min(max_dod_step, dod_final - state.dod),
764:             rtol=1e-9,
765:             atol=1e-11,
766:         )
767:         if not solution.success:
768:             raise RuntimeError(solution.message)
769: 
770:         histories = {
771:             "time_s": [],
772:             "dod": [],
773:             "voltage_v": [],
774:             "current_a": [],
775:             "c_rate": [],
776:             "power_w": [],
777:             "efficiency": [],
778:         }
779:         for dod, time_s in zip(solution.t, solution.y[0]):
780:             sample_state = BatteryState.from_dod(self._clip_dod(float(dod)))
781:             sample_point = point_function(sample_state)
782:             self._append_integration_sample(histories, float(time_s), sample_state, sample_point)
783: 
784:         final_state = BatteryState.from_dod(self._clip_dod(float(solution.t[-1])))
785:         final_point = point_function(final_state)
786:         stop_reason = "dod_target"
787:         is_feasible = True
788:         if solution.t[-1] < dod_final - 1e-10:
789:             stop_reason = self._stop_reason(final_state, final_point)
790:             is_feasible = False
791: 
792:         return self._integration_result(
793:             final_state=final_state,
794:             histories=histories,
795:             delivered_energy_wh=float(solution.y[1, -1]),
796:             consumed_charge_ah=float(solution.y[2, -1]),
797:             is_feasible=is_feasible,
798:             stop_reason=stop_reason,
799:         )
800: 
801:     def _solve_dod(self, residual: Callable[[float], float]) -> float:
802:         low = 0.0
803:         high = 1.0
804:         low_value = residual(low)
805:         high_value = residual(high)
806:         if not math.isfinite(low_value) or not math.isfinite(high_value):
807:             raise ValueError("DOD solve residual must be finite at interval bounds")
808:         if low_value == 0.0:
809:             return low
810:         if high_value == 0.0:
811:             return high
812:         if low_value * high_value > 0.0:
813:             raise ValueError("voltage and power do not bracket a DOD solution")
814: 
815:         for _ in range(80):
816:             mid = 0.5 * (low + high)
817:             mid_value = residual(mid)
818:             if mid_value == 0.0:
819:                 return mid
820:             if low_value * mid_value <= 0.0:
821:                 high = mid
822:             else:
823:                 low = mid
824:                 low_value = mid_value
825: 
826:         return 0.5 * (low + high)
827: 
828:     def _time_integration_events(
829:         self,
830:         point_function: Callable[[BatteryState], BatteryPoint],
831:     ) -> list[Callable[[float, np.ndarray], float]]:
832:         def event(_time_s: float, values: np.ndarray) -> float:
833:             dod = float(values[0])
834:             state = BatteryState.from_dod(self._clip_dod(dod))
835:             point = point_function(state)
836:             return self._feasibility_margin(dod, point)
837: 
838:         event.terminal = True  # type: ignore[attr-defined]
839:         event.direction = -1  # type: ignore[attr-defined]
840:         return [event]
841: 
842:     def _dod_integration_events(
843:         self,
844:         point_function: Callable[[BatteryState], BatteryPoint],
845:     ) -> list[Callable[[float, np.ndarray], float]]:
846:         def event(dod: float, _values: np.ndarray) -> float:
847:             state = BatteryState.from_dod(self._clip_dod(dod))
848:             point = point_function(state)
849:             return self._feasibility_margin(dod, point)
850: 
851:         event.terminal = True  # type: ignore[attr-defined]
852:         event.direction = -1  # type: ignore[attr-defined]
853:         return [event]
854: 
855:     def _feasibility_margin(self, dod: float, point: BatteryPoint) -> float:
856:         return min(
857:             self.max_current_a - point.cell_current_a,
858:             point.cell_voltage_v - self.cutoff_voltage_v,
859:             self.charge_voltage_v - point.cell_voltage_v,
860:             1.0 - dod,
861:         )
862: 
863:     def _stop_reason(self, state: BatteryState, point: BatteryPoint) -> str:
864:         if not point.is_feasible:
865:             return point.infeasible_reason or "infeasible_state"
866: 
867:         margins = {
868:             "current_limit": self.max_current_a - point.cell_current_a,
869:             "voltage_cutoff": point.cell_voltage_v - self.cutoff_voltage_v,
870:             "voltage_limit": self.charge_voltage_v - point.cell_voltage_v,
871:             "dod_limit": 1.0 - state.dod,
872:         }
873:         return min(margins, key=lambda name: margins[name])
874: 
875:     @staticmethod
876:     def _validate_integration_inputs(load: float, dt_s: float, max_step_s: float, load_name: str) -> None:
877:         if not math.isfinite(load) or load < 0.0:
878:             raise ValueError(f"{load_name} must be finite and non-negative")
879:         if not math.isfinite(dt_s) or dt_s < 0.0:
880:             raise ValueError("dt_s must be finite and non-negative")
881:         if not math.isfinite(max_step_s) or max_step_s <= 0.0:
882:             raise ValueError("max_step_s must be finite and positive")
883: 
884:     @staticmethod
885:     def _validate_dod_interval(dod_initial: float, dod_final: float) -> None:
886:         if not math.isfinite(dod_initial) or not math.isfinite(dod_final):
887:             raise ValueError("dod values must be finite")
888:         if dod_initial < 0.0 or dod_initial > 1.0 or dod_final < 0.0 or dod_final > 1.0:
889:             raise ValueError("dod values must be between 0 and 1")
890:         if dod_final <= dod_initial:
891:             raise ValueError("dod_final must be greater than dod_initial")
892: 
893:     @staticmethod
894:     def _initial_integration_histories(state: BatteryState, point: BatteryPoint) -> dict[str, list[float]]:
895:         return {
896:             "time_s": [0.0],
897:             "dod": [state.dod],
898:             "voltage_v": [point.terminal_voltage_v],
899:             "current_a": [point.current_a],
900:             "c_rate": [point.c_rate],
901:             "power_w": [point.power_w],
902:             "efficiency": [point.efficiency],
903:         }
904: 
905:     @staticmethod
906:     def _append_integration_sample(
907:         histories: dict[str, list[float]],
908:         time_s: float,
909:         state: BatteryState,
910:         point: BatteryPoint,
911:     ) -> None:
912:         histories["time_s"].append(time_s)
913:         histories["dod"].append(state.dod)
914:         histories["voltage_v"].append(point.terminal_voltage_v)
915:         histories["current_a"].append(point.current_a)
916:         histories["c_rate"].append(point.c_rate)
917:         histories["power_w"].append(point.power_w)
918:         histories["efficiency"].append(point.efficiency)
919: 
920:     @staticmethod
921:     def _integration_result(
922:         final_state: BatteryState,
923:         histories: dict[str, list[float]],
924:         delivered_energy_wh: float,
925:         consumed_charge_ah: float,
926:         is_feasible: bool,
927:         stop_reason: str,
928:     ) -> BatteryIntegrationResult:
929:         return BatteryIntegrationResult(
930:             final_state=final_state,
931:             time_s=histories["time_s"],
932:             dod=histories["dod"],
933:             voltage_v=histories["voltage_v"],
934:             current_a=histories["current_a"],
935:             c_rate=histories["c_rate"],
936:             power_w=histories["power_w"],
937:             efficiency=histories["efficiency"],
938:             delivered_energy_wh=delivered_energy_wh,
939:             consumed_charge_ah=consumed_charge_ah,
940:             is_feasible=is_feasible,
941:             stop_reason=stop_reason,
942:         )
943: 
944:     @staticmethod
945:     def _histories_from_result(result: BatteryIntegrationResult) -> dict[str, Sequence[float]]:
946:         return {
947:             "time_s": result.time_s,
948:             "dod": result.dod,
949:             "voltage_v": result.voltage_v,
950:             "current_a": result.current_a,
951:             "c_rate": result.c_rate,
952:             "power_w": result.power_w,
953:             "efficiency": result.efficiency,
954:         }
955: 
956:     @staticmethod
957:     def _extend_profile_histories(
958:         histories: dict[str, list[float]],
959:         result: BatteryIntegrationResult,
960:         time_offset_s: float,
961:     ) -> None:
962:         histories["time_s"].extend(time_offset_s + value for value in result.time_s[1:])
963:         histories["dod"].extend(result.dod[1:])
964:         histories["voltage_v"].extend(result.voltage_v[1:])
965:         histories["current_a"].extend(result.current_a[1:])
966:         histories["c_rate"].extend(result.c_rate[1:])
967:         histories["power_w"].extend(result.power_w[1:])
968:         histories["efficiency"].extend(result.efficiency[1:])
```

### 6dof_hopper/PyThrust/pythrust/battery/state.py

SHA-256: `cc8e66287d1d5fe937772567599f5f678421a5047ebf69f058c9d7199674603b`

- Definition `BatteryState` at lines 11-30.
- Definition `BatteryState.__post_init__` at lines 16-18.
- Definition `BatteryState.from_dod` at lines 21-25.
- Definition `BatteryState.dod` at lines 28-30.
- Definition `BatteryPoint` at lines 34-47.
- Definition `BatteryIntegrationResult` at lines 51-90.
- Definition `BatteryIntegrationResult.__post_init__` at lines 67-90.
- Definition `_as_float_tuple` at lines 93-97.

### 6dof_hopper/PyThrust/pythrust/motors/__init__.py

SHA-256: `c2b6c75ea068e4686e10a3d52cdf1258ceefb641e84e0e25e60e4cd0256a48ad`


### 6dof_hopper/PyThrust/pythrust/motors/database.py

SHA-256: `4cbd82fe126591ab368307942fb4fd5d134f0c364526ed65d47fee40cf8ad327`

- Definition `MotorEntry` at lines 13-34.
- Definition `MotorEntry.to_spec` at lines 26-34.
- Definition `MotorDatabase` at lines 37-130.
- Definition `MotorDatabase.__init__` at lines 40-43.
- Definition `MotorDatabase.is_loaded` at lines 46-48.
- Definition `MotorDatabase.motor_count` at lines 51-53.
- Definition `MotorDatabase.list_motors` at lines 55-57.
- Definition `MotorDatabase.get` at lines 59-61.
- Definition `MotorDatabase.load` at lines 63-77.
- Definition `MotorDatabase.load_entry` at lines 79-106.
- Definition `MotorDatabase.search` at lines 108-130.

Full source for manual caller review:

```python
1: """Brushless motor database loader and query interface."""
2: 
3: from __future__ import annotations
4: 
5: from dataclasses import dataclass
6: from pathlib import Path
7: import json
8: from typing import Dict, List, Optional
9: from pythrust.propulsion.models import MotorSpec
10: 
11: 
12: @dataclass(frozen=True)
13: class MotorEntry:
14:     """A database entry for a single brushless motor."""
15:     id: str
16:     name: str
17:     manufacturer: str
18:     kv: float
19:     resistance: float
20:     io: float
21:     max_current: float
22:     weight_g: float
23:     max_power: float
24:     io_voltage: float
25: 
26:     def to_spec(self) -> MotorSpec:
27:         """Convert the database entry to a PyThrust MotorSpec object."""
28:         return MotorSpec(
29:             kv_rpm_per_v=self.kv,
30:             resistance_ohm=self.resistance,
31:             no_load_current_a=self.io,
32:             current_max_a=self.max_current,
33:             no_load_voltage_v=self.io_voltage,
34:         )
35: 
36: 
37: class MotorDatabase:
38:     """Load and query brushless motor database from JSON files."""
39: 
40:     def __init__(self) -> None:
41:         """Create an empty motor database."""
42:         self._entries: Dict[str, MotorEntry] = {}
43:         self._loaded = False
44: 
45:     @property
46:     def is_loaded(self) -> bool:
47:         """Return True if a database has been successfully loaded."""
48:         return self._loaded
49: 
50:     @property
51:     def motor_count(self) -> int:
52:         """Return the number of motors in the database."""
53:         return len(self._entries)
54: 
55:     def list_motors(self) -> List[str]:
56:         """Return sorted unique motor IDs in the database."""
57:         return sorted(self._entries.keys())
58: 
59:     def get(self, motor_id: str) -> Optional[MotorEntry]:
60:         """Get a motor entry by its unique ID."""
61:         return self._entries.get(motor_id)
62: 
63:     def load(self, data_dir: Path) -> bool:
64:         """Load all motor JSON entries from a dataset directory."""
65:         data_dir = Path(data_dir)
66:         if not data_dir.exists():
67:             self._loaded = False
68:             return False
69: 
70:         self._entries.clear()
71:         
72:         # Recursively search for and load all .json files under the directory
73:         for json_path in sorted(data_dir.glob("**/*.json")):
74:             self.load_entry(json_path)
75: 
76:         self._loaded = bool(self._entries)
77:         return self._loaded
78: 
79:     def load_entry(self, json_path: Path) -> Optional[MotorEntry]:
80:         """Load a single motor JSON file and store its entry."""
81:         json_path = Path(json_path)
82:         if not json_path.exists():
83:             return None
84:         try:
85:             with open(json_path, "r", encoding="utf-8") as f:
86:                 m = json.load(f)
87:             
88:             entry = MotorEntry(
89:                 id=m.get("id", ""),
90:                 name=m.get("name", "Unknown"),
91:                 manufacturer=m.get("manufacturer", "Unknown"),
92:                 kv=float(m.get("kv", 0.0)),
93:                 resistance=float(m.get("resistance", 0.0)),
94:                 io=float(m.get("io", 0.0)),
95:                 max_current=float(m.get("max_current", 0.0)),
96:                 weight_g=float(m.get("weight_g", 0.0)),
97:                 max_power=float(m.get("max_power", 0.0)),
98:                 io_voltage=float(m.get("io_voltage", 10.0)),
99:             )
100:             if entry.id:
101:                 self._entries[entry.id] = entry
102:                 self._loaded = True
103:                 return entry
104:         except Exception:
105:             pass
106:         return None
107: 
108:     def search(
109:         self,
110:         min_kv: Optional[float] = None,
111:         max_kv: Optional[float] = None,
112:         min_max_current: Optional[float] = None,
113:         min_weight: Optional[float] = None,
114:         max_weight: Optional[float] = None,
115:     ) -> List[MotorEntry]:
116:         """Search and filter motors in the database matching specified criteria."""
117:         results = []
118:         for entry in self._entries.values():
119:             if min_kv is not None and entry.kv < min_kv:
120:                 continue
121:             if max_kv is not None and entry.kv > max_kv:
122:                 continue
123:             if min_max_current is not None and entry.max_current < min_max_current:
124:                 continue
125:             if min_weight is not None and entry.weight_g < min_weight:
126:                 continue
127:             if max_weight is not None and entry.weight_g > max_weight:
128:                 continue
129:             results.append(entry)
130:         return results
```

### 6dof_hopper/PyThrust/pythrust/openmdao/__init__.py

SHA-256: `d382c68c2478e7c4e4ec149c314cd0603fa7b34833ed649b04cafc4bbd08500c`


### 6dof_hopper/PyThrust/pythrust/openmdao/components.py

SHA-256: `f8f15cc69aebe1a4c3ba6cde6aba7d6473b6a2c1724a035729042c9602cf25fb`

- Definition `PropulsionComponent` at lines 18-103.
- Definition `PropulsionComponent.initialize` at lines 21-26.
- Definition `PropulsionComponent.setup` at lines 28-56.
- Definition `PropulsionComponent._get_specs` at lines 58-75.
- Definition `PropulsionComponent.compute` at lines 77-103.

Full source for manual caller review:

```python
1: """OpenMDAO wrapper component for PyThrust propulsion solver."""
2: 
3: from __future__ import annotations
4: 
5: import math
6: import openmdao.api as om
7: 
8: from pythrust.propellers.database import PropellerEntry
9: from pythrust.propulsion import (
10:     BatterySpec,
11:     MotorSpec,
12:     PropellerSpec,
13:     PropulsionSolver,
14:     SystemSpec,
15: )
16: 
17: 
18: class PropulsionComponent(om.ExplicitComponent):
19:     """OpenMDAO ExplicitComponent wrapping the PyThrust propulsion solver."""
20: 
21:     def initialize(self) -> None:
22:         self.options.declare(
23:             'prop_entry',
24:             types=PropellerEntry,
25:             desc='PropellerEntry database object',
26:         )
27: 
28:     def setup(self) -> None:
29:         # Inputs
30:         self.add_input('kv_rpm_per_v', val=860.0, desc='Motor Kv [RPM/V]')
31:         self.add_input('resistance_ohm', val=0.0258, desc='Motor winding resistance [ohm]')
32:         self.add_input('no_load_current_a', val=1.3, desc='Motor no-load current [A]')
33:         self.add_input('current_max_a', val=65.0, desc='Motor maximum current [A]')
34: 
35:         self.add_input('voltage_v', val=14.8, desc='Battery pack voltage [V]')
36:         self.add_input('discharge_efficiency', val=1.0, desc='Battery discharge efficiency')
37: 
38:         self.add_input('resistance_system_ohm', val=0.095, desc='Lumped system transmission resistance [ohm]')
39:         self.add_input('diameter_m', val=0.3302, desc='Propeller diameter [m]')
40:         self.add_input('throttle', val=0.7, desc='Throttle fraction [0, 1]')
41: 
42:         self.add_input('rho', val=1.225, desc='Air density [kg/m^3]')
43:         self.add_input('airspeed_mps', val=0.0, desc='Flight airspeed [m/s]')
44: 
45:         # Outputs
46:         self.add_output('rpm', val=5000.0, desc='Equilibrium shaft speed [RPM]')
47:         self.add_output('thrust_n', val=10.0, desc='Generated static/dynamic thrust [N]')
48:         self.add_output('torque_nm', val=0.2, desc='Propeller shaft torque [N-m]')
49:         self.add_output('battery_current_a', val=15.0, desc='Battery DC current draw [A]')
50:         self.add_output('battery_power_w', val=220.0, desc='Battery power consumption [W]')
51:         self.add_output('motor_current_a', val=15.0, desc='Motor winding current [A]')
52:         self.add_output('motor_voltage_v', val=12.0, desc='Motor terminal voltage [V]')
53:         self.add_output('is_feasible', val=1.0, desc='1.0 if feasible, 0.0 otherwise')
54: 
55:         # Declare derivatives using finite-difference
56:         self.declare_partials(of='*', wrt='*', method='fd')
57: 
58:     def _get_specs(self, inputs: om.Vector) -> tuple[MotorSpec, BatterySpec, SystemSpec, PropellerSpec]:
59:         motor = MotorSpec(
60:             kv_rpm_per_v=float(inputs['kv_rpm_per_v'][0]),
61:             resistance_ohm=float(inputs['resistance_ohm'][0]),
62:             no_load_current_a=float(inputs['no_load_current_a'][0]),
63:             current_max_a=float(inputs['current_max_a'][0]),
64:         )
65:         battery = BatterySpec(
66:             voltage_v=float(inputs['voltage_v'][0]),
67:             discharge_efficiency=float(inputs['discharge_efficiency'][0]),
68:         )
69:         system = SystemSpec(
70:             resistance_ohm=float(inputs['resistance_system_ohm'][0]),
71:         )
72:         propeller = PropellerSpec(
73:             diameter_m=float(inputs['diameter_m'][0]),
74:         )
75:         return motor, battery, system, propeller
76: 
77:     def compute(self, inputs: om.Vector, outputs: om.Vector) -> None:
78:         motor, battery, system, propeller = self._get_specs(inputs)
79:         prop_entry = self.options['prop_entry']
80:         throttle = float(inputs['throttle'][0])
81:         rho = float(inputs['rho'][0])
82:         airspeed_mps = float(inputs['airspeed_mps'][0])
83: 
84:         solver = PropulsionSolver()
85:         op = solver.solve_operating_point(
86:             motor=motor,
87:             battery=battery,
88:             system=system,
89:             propeller=propeller,
90:             prop_entry=prop_entry,
91:             rho=rho,
92:             airspeed_mps=airspeed_mps,
93:             throttle=throttle,
94:         )
95: 
96:         outputs['rpm'] = op.rpm
97:         outputs['thrust_n'] = op.thrust_n
98:         outputs['torque_nm'] = op.torque_nm
99:         outputs['battery_current_a'] = op.battery_current_a
100:         outputs['battery_power_w'] = op.battery_power_w
101:         outputs['motor_current_a'] = op.motor_current_a
102:         outputs['motor_voltage_v'] = op.motor_voltage_v
103:         outputs['is_feasible'] = 1.0 if op.is_feasible else 0.0
```

### 6dof_hopper/PyThrust/pythrust/propellers/__init__.py

SHA-256: `a063d129ab7dd6c4c2526e2ed0db810bcb551b114646c9c4fbdd958b3eb8a8d1`


### 6dof_hopper/PyThrust/pythrust/propellers/database.py

SHA-256: `0023cea3d22f8f68e77742ab59f51fec6c745c920ee0d38ac47a6ba7d4a5d495`

- Definition `PropellerMetadata` at lines 14-22.
- Definition `PropellerDataPoint` at lines 26-30.
- Definition `PropellerEntry` at lines 34-105.
- Definition `PropellerEntry.diameter_m` at lines 40-41.
- Definition `PropellerEntry.pitch_m` at lines 44-45.
- Definition `PropellerEntry.rpm_levels` at lines 48-49.
- Definition `PropellerEntry.get_coefficients` at lines 51-73.
- Definition `PropellerEntry._interp_at_rpm` at lines 75-105.
- Definition `PropellerDatabase` at lines 108-205.
- Definition `PropellerDatabase.__init__` at lines 110-113.
- Definition `PropellerDatabase.is_loaded` at lines 116-117.
- Definition `PropellerDatabase.propeller_count` at lines 120-121.
- Definition `PropellerDatabase.list_propellers` at lines 123-125.
- Definition `PropellerDatabase.get` at lines 127-129.
- Definition `PropellerDatabase.load` at lines 131-146.
- Definition `PropellerDatabase.load_entry` at lines 148-163.
- Definition `PropellerDatabase.find_by_size` at lines 165-188.
- Definition `PropellerDatabase.get_interpolated_coefficients` at lines 190-205.
- Definition `_normalize_rpm` at lines 208-214.
- Definition `_find_bracketing_indices` at lines 217-225.
- Definition `_find_insert_index` at lines 228-238.
- Definition `_load_entry` at lines 241-316.

### 6dof_hopper/PyThrust/pythrust/propulsion/__init__.py

SHA-256: `dcea13fc967933551ba327adedb276e7fd5ec0ae763590c6da0f4043d9f58878`


### 6dof_hopper/PyThrust/pythrust/propulsion/autotune.py

SHA-256: `9842a77c083007c7263e2031d3bb5218b5a5d4975ae70f01df0df37fd3ccb8ef`

- Definition `ManufacturerTestPoint` at lines 24-39.
- Definition `CalibrationResult` at lines 43-74.
- Definition `CalibrationResult.to_system_spec` at lines 72-74.
- Definition `PropulsionCalibrator` at lines 77-275.
- Definition `PropulsionCalibrator.__init__` at lines 84-85.
- Definition `PropulsionCalibrator.calibrate` at lines 87-236.
- Definition `PropulsionCalibrator.calibrate._motor_state` at lines 148-156.
- Definition `PropulsionCalibrator.calibrate._residuals` at lines 158-169.
- Definition `PropulsionCalibrator.load_csv` at lines 239-275.

### 6dof_hopper/PyThrust/pythrust/propulsion/models/__init__.py

SHA-256: `b6f7c6c27fc75acfa4a2b385ab12acd31503a2b56f414da3ca48ed0088060160`


### 6dof_hopper/PyThrust/pythrust/propulsion/models/battery.py

SHA-256: `fc019ccf294f92c981b36e3f45afba0a17bb3c791865b5dde10aaf14d615840f`


### 6dof_hopper/PyThrust/pythrust/propulsion/models/motor.py

SHA-256: `4d9f0b5ca53b0f2689e29d07b7c96cdf710b60f28f74d0fba7c46f4bc9c082e8`

- Definition `MotorSpec` at lines 10-59.
- Definition `MotorSpec.get_no_load_current` at lines 38-53.
- Definition `MotorSpec.get_winding_resistance` at lines 55-59.

### 6dof_hopper/PyThrust/pythrust/propulsion/models/operating_point.py

SHA-256: `f0f307cb6fe2f6f35a36b69cff73a11f429dcc5347afb7b962cf741989cd2812`

- Definition `OperatingPoint` at lines 10-32.

### 6dof_hopper/PyThrust/pythrust/propulsion/models/propeller.py

SHA-256: `75ada146f733da0a18034214ceaf40b2d12e7dfdfe85e54b060ba9d291b06569`

- Definition `PropellerSpec` at lines 10-20.

### 6dof_hopper/PyThrust/pythrust/propulsion/models/system.py

SHA-256: `a945a9295f3e89f03ece21055fef7426fb8a15a3d9262bc97b218a0c473175b4`

- Definition `SystemSpec` at lines 9-16.

### 6dof_hopper/PyThrust/pythrust/propulsion/solver.py

SHA-256: `f8e12261294e0e3e787ca69714aa45f523574b9189b645a3f290196527c17a3f`

- Definition `SolverConfig` at lines 18-25.
- Definition `evaluate_propulsion_state` at lines 28-48.
- Definition `PropulsionSolver` at lines 51-418.
- Definition `PropulsionSolver.__init__` at lines 54-55.
- Definition `PropulsionSolver.solve_operating_point` at lines 57-170.
- Definition `PropulsionSolver.solve_operating_point.g` at lines 92-107.
- Definition `PropulsionSolver._evaluate_state` at lines 172-181.
- Definition `PropulsionSolver._build_point` at lines 183-283.
- Definition `PropulsionSolver._build_infeasible_point` at lines 285-332.
- Definition `PropulsionSolver._validate_battery_state` at lines 335-337.
- Definition `PropulsionSolver._battery_voltage` at lines 339-348.
- Definition `PropulsionSolver._battery_voltage_from_point` at lines 350-359.
- Definition `PropulsionSolver._battery_current_from_point_or_power` at lines 362-369.
- Definition `PropulsionSolver._battery_point` at lines 372-381.
- Definition `PropulsionSolver._battery_power` at lines 384-392.
- Definition `PropulsionSolver._battery_efficiency` at lines 395-401.
- Definition `PropulsionSolver._estimate_j_max` at lines 404-418.

### 6dof_hopper/PyThrust/scripts/convert_apc_dat.py

SHA-256: `14a27e3e51f165c6e431090ef074540e44b821bc42c146231918a9bdc7b63d3b`

- Definition `_normalize_id` at lines 53-59.
- Definition `_parse_model` at lines 62-69.
- Definition `_iter_data_rows` at lines 72-106.
- Definition `_convert_file` at lines 109-165.
- Definition `main` at lines 168-208.

### 6dof_hopper/PyThrust/scripts/generate_readme_plots.py

SHA-256: `71320bca98c2356650f53957e27ba2691a72bdaed9637f5d8f58311dfed2367c`

- Definition `configure_style` at lines 37-55.
- Definition `save_figure` at lines 58-61.
- Definition `apply_two_panel_layout` at lines 64-71.
- Definition `build_baseline_specs` at lines 74-83.
- Definition `generate_calibration_plot` at lines 86-186.
- Definition `generate_propeller_plot` at lines 189-226.
- Definition `generate_battery_mission_plot` at lines 229-320.
- Definition `generate_heatmap_plot` at lines 323-407.
- Definition `generate_heatmap_plot.find_hover_throttle` at lines 334-367.
- Definition `main` at lines 410-428.

Full source for manual caller review:

```python
1: import sys
2: from pathlib import Path
3: 
4: import matplotlib
5: 
6: matplotlib.use("Agg")
7: 
8: import matplotlib.pyplot as plt
9: import numpy as np
10: 
11: sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
12: 
13: from pythrust.battery import BatteryState, FixedVoltageBattery, RateMapBattery
14: from pythrust.propellers import PropellerDatabase
15: from pythrust.propulsion import MotorSpec, PropellerSpec, PropulsionSolver, SystemSpec
16: from pythrust.propulsion.autotune import ManufacturerTestPoint, PropulsionCalibrator
17: 
18: 
19: IMAGE_DIR = Path("docs/images")
20: FIGSIZE = (9.6, 5.4)
21: DPI = 170
22: 
23: COLORS = {
24:     "blue": "#2563eb",
25:     "green": "#059669",
26:     "orange": "#d97706",
27:     "red": "#dc2626",
28:     "purple": "#7c3aed",
29:     "teal": "#0891b2",
30:     "ink": "#111827",
31:     "muted": "#6b7280",
32:     "grid": "#d1d5db",
33:     "panel": "#f8fafc",
34: }
35: 
36: 
37: def configure_style():
38:     plt.rcParams.update(
39:         {
40:             "figure.facecolor": "white",
41:             "axes.facecolor": "white",
42:             "axes.edgecolor": "#374151",
43:             "axes.labelcolor": COLORS["ink"],
44:             "axes.titlecolor": COLORS["ink"],
45:             "xtick.color": COLORS["ink"],
46:             "ytick.color": COLORS["ink"],
47:             "grid.color": COLORS["grid"],
48:             "grid.linewidth": 0.8,
49:             "font.size": 10,
50:             "axes.titlesize": 12,
51:             "axes.labelsize": 10,
52:             "legend.fontsize": 9,
53:             "figure.titlesize": 15,
54:         }
55:     )
56: 
57: 
58: def save_figure(fig, path):
59:     fig.savefig(path, dpi=DPI)
60:     plt.close(fig)
61:     print(f"Saved: {path}")
62: 
63: 
64: def apply_two_panel_layout(fig):
65:     fig.subplots_adjust(
66:         left=0.09,
67:         right=0.90,
68:         bottom=0.17,
69:         top=0.78,
70:         wspace=0.48,
71:     )
72: 
73: 
74: def build_baseline_specs():
75:     motor = MotorSpec(
76:         kv_rpm_per_v=860.0,
77:         resistance_ohm=0.0258,
78:         no_load_current_a=1.3,
79:         current_max_a=65.0,
80:     )
81:     system = SystemSpec(resistance_ohm=0.095)
82:     propeller = PropellerSpec(diameter_m=0.3302)
83:     return motor, system, propeller
84: 
85: 
86: def generate_calibration_plot(prop_entry):
87:     print("Generating Calibration Plot...")
88:     motor = MotorSpec(
89:         kv_rpm_per_v=860.0,
90:         resistance_ohm=0.0258,
91:         no_load_current_a=1.3,
92:         current_max_a=65.0,
93:     )
94:     battery = FixedVoltageBattery(voltage_v=14.8)
95:     system = SystemSpec(resistance_ohm=0.05)
96:     propeller = PropellerSpec(diameter_m=0.3302)
97: 
98:     raw_table = [
99:         {"rpm": 3897, "thrust_g": 500, "current_a": 3.9},
100:         {"rpm": 4804, "thrust_g": 750, "current_a": 6.7},
101:         {"rpm": 5421, "thrust_g": 1000, "current_a": 10.2},
102:         {"rpm": 6071, "thrust_g": 1250, "current_a": 13.9},
103:         {"rpm": 6564, "thrust_g": 1500, "current_a": 18.1},
104:         {"rpm": 7077, "thrust_g": 1750, "current_a": 22.6},
105:         {"rpm": 7560, "thrust_g": 2000, "current_a": 27.6},
106:         {"rpm": 8016, "thrust_g": 2250, "current_a": 33.5},
107:         {"rpm": 8346, "thrust_g": 2500, "current_a": 40.1},
108:         {"rpm": 8695, "thrust_g": 2750, "current_a": 47.5},
109:         {"rpm": 9230, "thrust_g": 3350, "current_a": 63.2},
110:     ]
111:     points = [
112:         ManufacturerTestPoint(rpm=r["rpm"], thrust_g=r["thrust_g"], current_a=r["current_a"])
113:         for r in raw_table
114:     ]
115: 
116:     result = PropulsionCalibrator().calibrate(
117:         test_points=points,
118:         motor=motor,
119:         battery=battery,
120:         system=system,
121:         propeller=propeller,
122:         prop_entry=prop_entry,
123:     )
124:     fitted_system = result.to_system_spec()
125:     solver = PropulsionSolver()
126: 
127:     model_rpms = np.linspace(3500, 9500, 100)
128:     model_thrusts_g = []
129:     model_currents_a = []
130:     for rpm in model_rpms:
131:         point = solver._build_point(
132:             motor=motor,
133:             battery=battery,
134:             system=fitted_system,
135:             propeller=propeller,
136:             prop_entry=prop_entry,
137:             rho=1.225,
138:             airspeed_mps=0.0,
139:             rpm=rpm,
140:         )
141:         model_thrusts_g.append(point.thrust_n * 1000.0 / 9.80665)
142:         model_currents_a.append(point.battery_current_a)
143: 
144:     fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
145:     fig.suptitle("System Resistance Calibration", weight="bold")
146:     fig.text(
147:         0.5,
148:         0.91,
149:         f"Fitted wiring/ESC loss term: {result.system_resistance_ohm:.3f} ohm",
150:         ha="center",
151:         color=COLORS["muted"],
152:         fontsize=10,
153:     )
154: 
155:     ax1.plot(model_rpms, model_thrusts_g, color=COLORS["blue"], linewidth=2.2, label="PyThrust fit")
156:     ax1.scatter(
157:         [p.rpm for p in points],
158:         [p.thrust_g for p in points],
159:         color=COLORS["red"],
160:         s=32,
161:         label="test data",
162:         zorder=3,
163:     )
164:     ax1.set_title("Thrust match")
165:     ax1.set_xlabel("Shaft speed [RPM]")
166:     ax1.set_ylabel("Thrust [g]")
167:     ax1.grid(True)
168:     ax1.legend(frameon=False)
169: 
170:     ax2.plot(model_rpms, model_currents_a, color=COLORS["orange"], linewidth=2.2, label="PyThrust fit")
171:     ax2.scatter(
172:         [p.rpm for p in points],
173:         [p.current_a for p in points],
174:         color=COLORS["red"],
175:         s=32,
176:         label="test data",
177:         zorder=3,
178:     )
179:     ax2.set_title("Battery current match")
180:     ax2.set_xlabel("Shaft speed [RPM]")
181:     ax2.set_ylabel("Battery current [A]")
182:     ax2.grid(True)
183:     ax2.legend(frameon=False)
184: 
185:     apply_two_panel_layout(fig)
186:     save_figure(fig, IMAGE_DIR / "calibration_results.png")
187: 
188: 
189: def generate_propeller_plot(prop_entry):
190:     print("Generating Propeller Database Plot...")
191:     fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
192:     fig.suptitle("Empirical Propeller Database", weight="bold")
193:     fig.text(
194:         0.5,
195:         0.91,
196:         "APC 13x6.5E coefficient maps used by the operating-point solver",
197:         ha="center",
198:         color=COLORS["muted"],
199:         fontsize=10,
200:     )
201: 
202:     rpms = prop_entry.rpm_levels
203:     selected = [rpms[i] for i in [0, len(rpms) // 3, 2 * len(rpms) // 3, len(rpms) - 1] if i < len(rpms)]
204:     selected = sorted(set(selected))
205:     palette = [COLORS["blue"], COLORS["green"], COLORS["orange"], COLORS["purple"]]
206: 
207:     for color, rpm in zip(palette, selected):
208:         points = prop_entry.data_by_rpm[rpm]
209:         j_vals = [p.j for p in points]
210:         ax1.plot(j_vals, [p.ct for p in points], color=color, linewidth=2.0, label=f"{int(rpm)} RPM")
211:         ax2.plot(j_vals, [p.cp for p in points], color=color, linewidth=2.0, label=f"{int(rpm)} RPM")
212: 
213:     ax1.set_title("Thrust coefficient")
214:     ax1.set_xlabel("Advance ratio J")
215:     ax1.set_ylabel("Ct")
216:     ax1.grid(True)
217:     ax1.legend(frameon=False)
218: 
219:     ax2.set_title("Power coefficient")
220:     ax2.set_xlabel("Advance ratio J")
221:     ax2.set_ylabel("Cp")
222:     ax2.grid(True)
223:     ax2.legend(frameon=False)
224: 
225:     apply_two_panel_layout(fig)
226:     save_figure(fig, IMAGE_DIR / "propeller_coefficients.png")
227: 
228: 
229: def generate_battery_mission_plot(prop_entry):
230:     print("Generating Rate-Map Battery Mission Plot...")
231:     battery = RateMapBattery.from_json("data/batteries/example_liion_cell.json", series=4, parallel=2)
232:     motor, system, propeller = build_baseline_specs()
233:     solver = PropulsionSolver()
234:     state = BatteryState(soc=0.95)
235: 
236:     segments = [
237:         {"name": "takeoff", "duration_s": 45.0, "throttle": 0.70, "airspeed_mps": 0.0},
238:         {"name": "climb", "duration_s": 90.0, "throttle": 0.65, "airspeed_mps": 5.0},
239:         {"name": "cruise", "duration_s": 180.0, "throttle": 0.50, "airspeed_mps": 10.0},
240:         {"name": "return", "duration_s": 120.0, "throttle": 0.45, "airspeed_mps": 8.0},
241:     ]
242: 
243:     times_min = [0.0]
244:     soc = [state.soc]
245:     voltages = []
246:     currents = []
247:     c_rates = []
248:     labels = []
249:     elapsed_s = 0.0
250: 
251:     for segment in segments:
252:         point = solver.solve_operating_point(
253:             motor=motor,
254:             battery=battery,
255:             battery_state=state,
256:             system=system,
257:             propeller=propeller,
258:             prop_entry=prop_entry,
259:             rho=1.225,
260:             airspeed_mps=segment["airspeed_mps"],
261:             throttle=segment["throttle"],
262:         )
263:         elapsed_s += segment["duration_s"]
264:         state = battery.step_current(state=state, current_a=point.battery_current_a, dt_s=segment["duration_s"])
265:         times_min.append(elapsed_s / 60.0)
266:         soc.append(state.soc)
267:         voltages.append(point.battery_voltage_v)
268:         currents.append(point.battery_current_a)
269:         c_rates.append(point.battery_c_rate)
270:         labels.append(segment["name"])
271: 
272:     centers = [(times_min[i] + times_min[i + 1]) / 2 for i in range(len(segments))]
273:     widths = [times_min[i + 1] - times_min[i] for i in range(len(segments))]
274: 
275:     fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
276:     fig.suptitle("Rate-Map Battery Mission Example", weight="bold")
277:     fig.text(
278:         0.5,
279:         0.91,
280:         "A short segment schedule updates battery state from solved pack current",
281:         ha="center",
282:         color=COLORS["muted"],
283:         fontsize=10,
284:     )
285: 
286:     ax1.plot(times_min, soc, color=COLORS["green"], marker="o", linewidth=2.3, label="SoC")
287:     ax1.set_title("State of charge")
288:     ax1.set_xlabel("Elapsed time [min]")
289:     ax1.set_ylabel("SoC")
290:     ax1.set_ylim(0.75, 0.98)
291:     ax1.grid(True)
292: 
293:     ax2.plot(
294:         centers,
295:         currents,
296:         color=COLORS["orange"],
297:         marker="o",
298:         linewidth=2.4,
299:         label="current",
300:     )
301:     ax2.set_title("Solved pack current")
302:     ax2.set_xlabel("Mission segment")
303:     ax2.set_ylabel("Battery current [A]")
304:     ax2.set_xticks(centers)
305:     ax2.set_xticklabels(labels, rotation=20, ha="right")
306:     ax2.grid(True)
307:     ax2.set_ylim(0.0, max(currents) * 1.18)
308:     for x, current, segment in zip(centers, currents, segments):
309:         ax2.text(
310:             x,
311:             current + max(currents) * 0.035,
312:             f"{segment['throttle'] * 100:.0f}%",
313:             ha="center",
314:             va="bottom",
315:             color=COLORS["muted"],
316:             fontsize=9,
317:         )
318: 
319:     apply_two_panel_layout(fig)
320:     save_figure(fig, IMAGE_DIR / "rate_map_battery_mission.png")
321: 
322: 
323: def generate_heatmap_plot(db):
324:     print("Generating Efficiency Heatmap...")
325:     kv_grid = np.linspace(400, 1200, 25)
326:     dia_grid = np.linspace(10, 18, 25)
327:     efficiency = np.zeros((len(dia_grid), len(kv_grid)))
328: 
329:     battery = FixedVoltageBattery(voltage_v=14.8)
330:     system = SystemSpec(resistance_ohm=0.05)
331:     solver = PropulsionSolver()
332:     target_thrust_n = 4.903
333: 
334:     def find_hover_throttle(motor, propeller, prop_entry):
335:         low, high = 0.1, 0.99
336:         mid = 0.5
337:         for _ in range(15):
338:             mid = (low + high) / 2.0
339:             point = solver.solve_operating_point(
340:                 motor=motor,
341:                 battery=battery,
342:                 system=system,
343:                 propeller=propeller,
344:                 prop_entry=prop_entry,
345:                 rho=1.225,
346:                 airspeed_mps=0.0,
347:                 throttle=mid,
348:             )
349:             residual = point.thrust_n - target_thrust_n
350:             if abs(residual) < 1e-3:
351:                 break
352:             if residual < 0:
353:                 low = mid
354:             else:
355:                 high = mid
356: 
357:         point = solver.solve_operating_point(
358:             motor=motor,
359:             battery=battery,
360:             system=system,
361:             propeller=propeller,
362:             prop_entry=prop_entry,
363:             rho=1.225,
364:             airspeed_mps=0.0,
365:             throttle=mid,
366:         )
367:         return point if point.is_feasible and abs(point.thrust_n - target_thrust_n) < 0.1 else None
368: 
369:     for i, dia_in in enumerate(dia_grid):
370:         prop_entry = db.find_by_size(dia_in, pitch_in=dia_in * 0.5, blade_count=2, tolerance=2.0)
371:         if prop_entry is None:
372:             prop_entry = db.get("APC_13x6.5E")
373:         propeller = PropellerSpec(diameter_m=dia_in * 0.0254)
374: 
375:         for j, kv in enumerate(kv_grid):
376:             motor = MotorSpec(
377:                 kv_rpm_per_v=kv,
378:                 resistance_ohm=0.0258,
379:                 no_load_current_a=1.3,
380:                 current_max_a=65.0,
381:             )
382:             point = find_hover_throttle(motor, propeller, prop_entry)
383:             if point is not None and point.battery_power_w > 0:
384:                 thrust_g = point.thrust_n * 1000.0 / 9.80665
385:                 efficiency[i, j] = thrust_g / point.battery_power_w
386:             else:
387:                 efficiency[i, j] = np.nan
388: 
389:     fig = plt.figure(figsize=FIGSIZE)
390:     ax = fig.add_axes([0.08, 0.13, 0.76, 0.70])
391:     contour = ax.contourf(kv_grid, dia_grid, efficiency, levels=16, cmap="viridis")
392:     cax = fig.add_axes([0.87, 0.13, 0.025, 0.70])
393:     cbar = fig.colorbar(contour, cax=cax)
394:     cbar.set_label("Hover efficiency [g/W]", rotation=270, labelpad=15)
395:     ax.set_xlabel("Motor Kv [RPM/V]")
396:     ax.set_ylabel("Propeller diameter [in]")
397:     fig.suptitle("Hover Efficiency Design Map", fontweight="bold")
398:     fig.text(
399:         0.5,
400:         0.91,
401:         "Target thrust: 500 g",
402:         ha="center",
403:         color=COLORS["muted"],
404:         fontsize=10,
405:     )
406:     ax.grid(True, linestyle=":", alpha=0.6)
407:     save_figure(fig, IMAGE_DIR / "efficiency_heatmap.png")
408: 
409: 
410: def main():
411:     configure_style()
412: 
413:     db_prop = PropellerDatabase()
414:     if not db_prop.load(Path("data/propellers/apc_202602"), strict=False):
415:         print("Error: Could not load propeller database.")
416:         sys.exit(1)
417: 
418:     prop_entry = db_prop.get("APC_13x6.5E")
419:     if prop_entry is None:
420:         print("Error: Propeller APC_13x6.5E not found.")
421:         sys.exit(1)
422: 
423:     IMAGE_DIR.mkdir(parents=True, exist_ok=True)
424: 
425:     generate_battery_mission_plot(prop_entry)
426:     generate_calibration_plot(prop_entry)
427:     generate_propeller_plot(prop_entry)
428:     generate_heatmap_plot(db_prop)
429: 
430: 
431: if __name__ == "__main__":
432:     main()
```

### 6dof_hopper/PyThrust/tests/test_autotune.py

SHA-256: `f011064031bb78ee71373f81e822a98164c5d2296526c66daeecb42fe810cbce`

- Definition `prop_entry` at lines 38-45.
- Definition `base_motor` at lines 49-55.
- Definition `base_battery` at lines 59-60.
- Definition `base_propeller` at lines 64-65.
- Definition `_make_synthetic_table` at lines 73-106.
- Definition `TestRoundTrip` at lines 114-142.
- Definition `TestRoundTrip.test_recover_system_resistance` at lines 118-142.
- Definition `TestDataQuality` at lines 145-196.
- Definition `TestDataQuality.test_warns_on_few_points` at lines 148-161.
- Definition `TestDataQuality.test_empty_table` at lines 163-173.
- Definition `TestDataQuality.test_invalid_rows_are_dropped` at lines 175-196.
- Definition `TestCSVLoader` at lines 199-234.
- Definition `TestCSVLoader.test_load_valid_csv` at lines 202-214.
- Definition `TestCSVLoader.test_load_missing_required_column` at lines 216-223.
- Definition `TestCSVLoader.test_load_skips_bad_rows` at lines 225-234.
- Definition `TestToSystemSpec` at lines 237-250.
- Definition `TestToSystemSpec.test_to_system_spec` at lines 238-250.
- Definition `TestSecondOrderMotor` at lines 253-320.
- Definition `TestSecondOrderMotor.test_no_load_current_exponent` at lines 254-265.
- Definition `TestSecondOrderMotor.test_no_load_current_quadratic` at lines 267-278.
- Definition `TestSecondOrderMotor.test_winding_resistance_quadratic` at lines 280-289.
- Definition `TestSecondOrderMotor.test_solver_with_second_order_parameters` at lines 291-320.

Full source for manual caller review:

```python
1: """Unit and integration tests for PropulsionCalibrator.
2: 
3: Run from the project root::
4: 
5:     pytest tests/test_autotune.py -v
6: """
7: 
8: from __future__ import annotations
9: 
10: import math
11: from pathlib import Path
12: 
13: import pytest
14: 
15: from pythrust.propellers.database import PropellerDatabase
16: from pythrust.propulsion import (
17:     BatterySpec,
18:     MotorSpec,
19:     PropellerSpec,
20:     SystemSpec,
21:     PropulsionSolver,
22: )
23: from pythrust.propulsion.autotune import (
24:     CalibrationResult,
25:     ManufacturerTestPoint,
26:     PropulsionCalibrator,
27: )
28: 
29: # ---------------------------------------------------------------------------
30: # Fixtures
31: # ---------------------------------------------------------------------------
32: 
33: _DATASET_DIR = Path(__file__).parent.parent / "data" / "propellers" / "apc_202602"
34: _PROP_ID = "APC_13x6.5E"
35: 
36: 
37: @pytest.fixture(scope="module")
38: def prop_entry():
39:     db = PropellerDatabase()
40:     if not db.load(_DATASET_DIR, strict=False):
41:         pytest.skip(f"Propeller dataset not found at {_DATASET_DIR}")
42:     entry = db.get(_PROP_ID)
43:     if entry is None:
44:         pytest.skip(f"{_PROP_ID} not found in dataset")
45:     return entry
46: 
47: 
48: @pytest.fixture(scope="module")
49: def base_motor():
50:     return MotorSpec(
51:         kv_rpm_per_v=860.0,
52:         resistance_ohm=0.0258,
53:         no_load_current_a=1.3,
54:         current_max_a=65.0,
55:     )
56: 
57: 
58: @pytest.fixture(scope="module")
59: def base_battery():
60:     return BatterySpec(voltage_v=14.8)
61: 
62: 
63: @pytest.fixture(scope="module")
64: def base_propeller():
65:     return PropellerSpec(diameter_m=0.3302)  # 13-inch
66: 
67: 
68: # ---------------------------------------------------------------------------
69: # Helpers
70: # ---------------------------------------------------------------------------
71: 
72: 
73: def _make_synthetic_table(
74:     motor: MotorSpec,
75:     battery: BatterySpec,
76:     system: SystemSpec,
77:     propeller: PropellerSpec,
78:     prop_entry,
79:     throttles=(0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
80:     rho: float = 1.225,
81: ) -> list[ManufacturerTestPoint]:
82:     """Generate a synthetic table from the forward model."""
83:     solver = PropulsionSolver()
84:     points = []
85:     for t in throttles:
86:         op = solver.solve_operating_point(
87:             motor=motor,
88:             battery=battery,
89:             system=system,
90:             propeller=propeller,
91:             prop_entry=prop_entry,
92:             rho=rho,
93:             airspeed_mps=0.0,
94:             throttle=t,
95:         )
96:         if op.is_feasible:
97:             # battery DC current = battery power / battery voltage
98:             current_a = op.battery_power_w / battery.voltage_v
99:             points.append(
100:                 ManufacturerTestPoint(
101:                     rpm=op.rpm,
102:                     thrust_g=op.thrust_n * 1000.0 / 9.80665,
103:                     current_a=current_a,
104:                 )
105:             )
106:     return points
107: 
108: 
109: # ---------------------------------------------------------------------------
110: # Tests
111: # ---------------------------------------------------------------------------
112: 
113: 
114: class TestRoundTrip:
115:     """Calibrator must recover the true system resistance from synthetic data."""
116: 
117:     @pytest.mark.parametrize("true_r_sys", [0.01, 0.03, 0.05, 0.08])
118:     def test_recover_system_resistance(
119:         self, true_r_sys, base_motor, base_battery, base_propeller, prop_entry
120:     ):
121:         system_true = SystemSpec(resistance_ohm=true_r_sys)
122:         table = _make_synthetic_table(
123:             base_motor, base_battery, system_true, base_propeller, prop_entry
124:         )
125:         assert len(table) >= 3, "Need >= 3 feasible points"
126: 
127:         cal = PropulsionCalibrator()
128:         result = cal.calibrate(
129:             table,
130:             base_motor,
131:             base_battery,
132:             SystemSpec(resistance_ohm=0.04),  # starting guess
133:             base_propeller,
134:             prop_entry,
135:         )
136: 
137:         assert result.converged, "Optimizer did not converge"
138:         assert abs(result.system_resistance_ohm - true_r_sys) < 0.001, (
139:             f"true R={true_r_sys}, recovered R={result.system_resistance_ohm:.5f}"
140:         )
141:         assert result.r_squared_thrust > 0.99
142:         assert result.rmse_thrust_g < 2.0
143: 
144: 
145: class TestDataQuality:
146:     """Edge cases and data quality handling."""
147: 
148:     def test_warns_on_few_points(
149:         self, base_motor, base_battery, base_propeller, prop_entry
150:     ):
151:         table = [ManufacturerTestPoint(rpm=4000.0, thrust_g=500.0, current_a=4.0)]
152: 
153:         cal = PropulsionCalibrator()
154:         result = cal.calibrate(
155:             table, base_motor, base_battery, SystemSpec(resistance_ohm=0.05),
156:             base_propeller, prop_entry,
157:         )
158:         assert any("valid point" in w.lower() or "fewer" in w.lower()
159:                    for w in result.warnings), (
160:             f"Expected a 'few points' warning; got: {result.warnings}"
161:         )
162: 
163:     def test_empty_table(
164:         self, base_motor, base_battery, base_propeller, prop_entry
165:     ):
166:         cal = PropulsionCalibrator()
167:         result = cal.calibrate(
168:             [], base_motor, base_battery, SystemSpec(resistance_ohm=0.05),
169:             base_propeller, prop_entry,
170:         )
171:         assert not result.converged
172:         assert result.n_points == 0
173:         assert math.isnan(result.rmse_thrust_g)
174: 
175:     def test_invalid_rows_are_dropped(
176:         self, base_motor, base_battery, base_propeller, prop_entry
177:     ):
178:         system_true = SystemSpec(resistance_ohm=0.05)
179:         good = _make_synthetic_table(
180:             base_motor, base_battery, system_true, base_propeller, prop_entry
181:         )
182:         bad = [
183:             ManufacturerTestPoint(rpm=-100.0, thrust_g=500.0, current_a=4.0),  # negative rpm
184:             ManufacturerTestPoint(rpm=4000.0, thrust_g=-10.0, current_a=4.0),  # negative thrust
185:             ManufacturerTestPoint(rpm=4000.0, thrust_g=500.0, current_a=-1.0),  # negative current
186:         ]
187:         table = bad + good
188: 
189:         cal = PropulsionCalibrator()
190:         result = cal.calibrate(
191:             table, base_motor, base_battery, SystemSpec(resistance_ohm=0.05),
192:             base_propeller, prop_entry,
193:         )
194:         assert result.n_points == len(good)
195:         assert result.converged
196:         assert any("dropped" in w.lower() for w in result.warnings)
197: 
198: 
199: class TestCSVLoader:
200:     """CSV loading."""
201: 
202:     def test_load_valid_csv(self, tmp_path):
203:         csv_file = tmp_path / "table.csv"
204:         csv_file.write_text(
205:             "rpm,thrust_g,current_a\n"
206:             "3000,182.0,3.2\n"
207:             "6000,680.0,13.1\n"
208:             "9000,1720.0,44.5\n"
209:         )
210:         points = PropulsionCalibrator.load_csv(csv_file)
211:         assert len(points) == 3
212:         assert points[0].rpm == pytest.approx(3000.0)
213:         assert points[0].thrust_g == pytest.approx(182.0)
214:         assert points[0].current_a == pytest.approx(3.2)
215: 
216:     def test_load_missing_required_column(self, tmp_path):
217:         csv_file = tmp_path / "table_missing.csv"
218:         csv_file.write_text(
219:             "rpm,thrust_g\n"
220:             "3000,182.0\n"
221:         )
222:         points = PropulsionCalibrator.load_csv(csv_file)
223:         assert len(points) == 0
224: 
225:     def test_load_skips_bad_rows(self, tmp_path):
226:         csv_file = tmp_path / "table_bad.csv"
227:         csv_file.write_text(
228:             "rpm,thrust_g,current_a\n"
229:             "3000,182.0,3.2\n"
230:             "bad,row,here\n"
231:             "9000,1720.0,44.5\n"
232:         )
233:         points = PropulsionCalibrator.load_csv(csv_file)
234:         assert len(points) == 2
235: 
236: 
237: class TestToSystemSpec:
238:     def test_to_system_spec(self):
239:         result = CalibrationResult(
240:             system_resistance_ohm=0.052,
241:             rmse_thrust_g=4.2,
242:             rmse_current_a=0.18,
243:             r_squared_thrust=0.998,
244:             n_points=8,
245:             converged=True,
246:             warnings=[],
247:         )
248:         spec = result.to_system_spec()
249:         assert isinstance(spec, SystemSpec)
250:         assert spec.resistance_ohm == pytest.approx(0.052)
251: 
252: 
253: class TestSecondOrderMotor:
254:     def test_no_load_current_exponent(self):
255:         motor = MotorSpec(
256:             kv_rpm_per_v=860.0,
257:             resistance_ohm=0.025,
258:             no_load_current_a=1.3,
259:             current_max_a=65.0,
260:             no_load_voltage_v=10.0,
261:             iron_loss_exponent=1.5,
262:         )
263:         assert motor.get_no_load_current(8600.0) == pytest.approx(1.3)
264:         assert motor.get_no_load_current(17200.0) == pytest.approx(1.3 * (2.0 ** 1.5))
265:         assert motor.get_no_load_current(0.0) == pytest.approx(1.3)
266: 
267:     def test_no_load_current_quadratic(self):
268:         motor = MotorSpec(
269:             kv_rpm_per_v=800.0,
270:             resistance_ohm=0.03,
271:             no_load_current_a=1.0,
272:             current_max_a=50.0,
273:             no_load_current_linear=0.02,
274:             no_load_current_quadratic=0.005,
275:         )
276:         omega = 1000.0 * math.pi / 30.0
277:         expected = 1.0 + 0.02 * omega + 0.005 * (omega ** 2)
278:         assert motor.get_no_load_current(1000.0) == pytest.approx(expected)
279: 
280:     def test_winding_resistance_quadratic(self):
281:         motor = MotorSpec(
282:             kv_rpm_per_v=800.0,
283:             resistance_ohm=0.03,
284:             no_load_current_a=1.0,
285:             current_max_a=50.0,
286:             resistance_quadratic=0.001,
287:         )
288:         assert motor.get_winding_resistance(10.0) == pytest.approx(0.13)
289:         assert motor.get_winding_resistance(0.0) == pytest.approx(0.03)
290: 
291:     def test_solver_with_second_order_parameters(self, prop_entry):
292:         motor = MotorSpec(
293:             kv_rpm_per_v=860.0,
294:             resistance_ohm=0.0258,
295:             no_load_current_a=1.3,
296:             current_max_a=65.0,
297:             torque_constant_kv_ratio=1.02,
298:             magnetic_lag_tau=1e-5,
299:             no_load_current_linear=0.001,
300:             resistance_quadratic=1e-5,
301:         )
302:         battery = BatterySpec(voltage_v=14.8)
303:         system = SystemSpec(resistance_ohm=0.05)
304:         propeller = PropellerSpec(diameter_m=0.3302)
305:         solver = PropulsionSolver()
306: 
307:         op = solver.solve_operating_point(
308:             motor=motor,
309:             battery=battery,
310:             system=system,
311:             propeller=propeller,
312:             prop_entry=prop_entry,
313:             rho=1.225,
314:             airspeed_mps=0.0,
315:             throttle=0.7,
316:         )
317:         assert op.is_feasible
318:         assert op.rpm > 3000.0
319:         assert op.motor_current_a > 1.0
320:         assert op.motor_voltage_v > 0.0
```

### 6dof_hopper/PyThrust/tests/test_battery.py

SHA-256: `02b7d10105c621a182e4aa4c541f398968edc8446f9909c6aa520848b7ce37d0`

- Definition `rate_map_battery` at lines 20-32.
- Definition `test_fixed_voltage_battery_replaces_battery_spec` at lines 35-40.
- Definition `test_battery_state_dod_round_trip` at lines 43-47.
- Definition `test_battery_state_rejects_non_finite_soc` at lines 51-53.
- Definition `test_battery_state_rejects_non_finite_dod` at lines 57-59.
- Definition `test_battery_integration_result_normalizes_histories` at lines 62-82.
- Definition `test_battery_integration_result_rejects_mismatched_histories` at lines 85-100.
- Definition `test_rate_map_state_at_current` at lines 103-112.
- Definition `test_rate_map_state_at_power` at lines 115-128.
- Definition `test_rate_map_state_at_power_loss` at lines 131-143.
- Definition `test_rate_map_state_at_power_loss_rejects_invalid_inputs` at lines 147-149.
- Definition `test_rate_map_reports_infeasible_power` at lines 152-157.
- Definition `test_rate_map_preserves_first_infeasible_reason` at lines 160-167.
- Definition `test_rate_map_step_current` at lines 170-175.
- Definition `test_rate_map_integrates_constant_current` at lines 178-195.
- Definition `test_rate_map_integrates_constant_c_rate_like_current` at lines 198-214.
- Definition `test_rate_map_integrates_zero_current_without_changing_state` at lines 217-229.
- Definition `test_rate_map_integrates_zero_duration_without_extra_sample` at lines 232-242.
- Definition `test_rate_map_integrates_current_until_voltage_cutoff` at lines 245-257.
- Definition `test_rate_map_integrates_current_until_dod_limit` at lines 260-272.
- Definition `test_rate_map_integrates_current_reports_initial_infeasible_state` at lines 275-286.
- Definition `test_rate_map_integrate_current_rejects_invalid_inputs` at lines 300-310.
- Definition `test_rate_map_integrates_constant_power` at lines 313-329.
- Definition `test_rate_map_integrates_zero_power_without_changing_state` at lines 332-344.
- Definition `test_rate_map_integrates_zero_power_duration_without_extra_sample` at lines 347-357.
- Definition `test_rate_map_integrates_power_until_voltage_cutoff` at lines 360-372.
- Definition `test_rate_map_integrates_power_until_dod_limit` at lines 375-387.
- Definition `test_rate_map_integrates_power_reports_initial_power_limit` at lines 390-401.
- Definition `test_rate_map_integrate_power_rejects_invalid_inputs` at lines 415-425.
- Definition `test_rate_map_integrates_constant_voltage` at lines 428-439.
- Definition `test_rate_map_integrates_constant_load_resistance` at lines 442-454.
- Definition `test_rate_map_integrates_constant_power_loss` at lines 457-475.
- Definition `test_rate_map_extended_integrators_reject_invalid_inputs` at lines 486-495.
- Definition `test_rate_map_integrates_current_to_target_dod` at lines 498-510.
- Definition `test_rate_map_integrates_power_to_target_dod` at lines 513-524.
- Definition `test_rate_map_integrate_to_dod_rejects_invalid_target` at lines 528-534.
- Definition `test_rate_map_solves_dod_at_voltage_power` at lines 537-551.
- Definition `test_rate_map_integrates_power_profile` at lines 554-579.
- Definition `test_rate_map_integrate_power_profile_rejects_mismatched_segments` at lines 582-588.
- Definition `test_rate_map_dod_energy_knockdown` at lines 591-596.
- Definition `test_rate_map_dod_energy_knockdown_rejects_invalid_inputs` at lines 609-615.
- Definition `test_rate_map_c_rate_energy_knockdown` at lines 618-624.
- Definition `test_rate_map_c_rate_energy_knockdown_rejects_invalid_inputs` at lines 636-645.
- Definition `test_rate_map_loads_from_json` at lines 648-676.
- Definition `test_rate_map_loads_example_cell_dataset` at lines 679-690.

Full source for manual caller review:

```python
1: import json
2: import math
3: from pathlib import Path
4: 
5: import pytest
6: 
7: from pythrust.battery import (
8:     BatteryIntegrationResult,
9:     BatteryState,
10:     FixedVoltageBattery,
11:     RateMapBattery,
12: )
13: from pythrust.propulsion.models import BatterySpec
14: 
15: 
16: PROJECT_ROOT = Path(__file__).resolve().parents[1]
17: 
18: 
19: @pytest.fixture
20: def rate_map_battery():
21:     return RateMapBattery(
22:         name="Example pack",
23:         capacity_ah=4.2,
24:         cutoff_voltage_v=2.5,
25:         charge_voltage_v=4.2,
26:         max_current_a=20.0,
27:         series=4,
28:         parallel=2,
29:         dod=[0.0, 0.5, 1.0],
30:         ocv_v=[4.2, 3.8, 3.2],
31:         resistance_ohm=[0.02, 0.03, 0.05],
32:     )
33: 
34: 
35: def test_fixed_voltage_battery_replaces_battery_spec():
36:     battery = FixedVoltageBattery(voltage_v=14.8, discharge_efficiency=0.95)
37: 
38:     assert BatterySpec is FixedVoltageBattery
39:     assert battery.terminal_voltage(current_a=10.0) == 14.8
40:     assert math.isclose(battery.terminal_power(current_a=10.0), 14.8 * 10.0 / 0.95)
41: 
42: 
43: def test_battery_state_dod_round_trip():
44:     state = BatteryState.from_dod(0.25)
45: 
46:     assert state.soc == 0.75
47:     assert state.dod == 0.25
48: 
49: 
50: @pytest.mark.parametrize("soc", [math.nan, math.inf, -math.inf])
51: def test_battery_state_rejects_non_finite_soc(soc):
52:     with pytest.raises(ValueError, match="soc"):
53:         BatteryState(soc=soc)
54: 
55: 
56: @pytest.mark.parametrize("dod", [math.nan, math.inf, -math.inf])
57: def test_battery_state_rejects_non_finite_dod(dod):
58:     with pytest.raises(ValueError, match="dod"):
59:         BatteryState.from_dod(dod)
60: 
61: 
62: def test_battery_integration_result_normalizes_histories():
63:     final_state = BatteryState(soc=0.9)
64:     result = BatteryIntegrationResult(
65:         final_state=final_state,
66:         time_s=[0, 10],
67:         dod=[0.0, 0.1],
68:         voltage_v=[16.0, 15.8],
69:         current_a=[8.0, 8.0],
70:         c_rate=[1.0, 1.0],
71:         power_w=[128.0, 126.4],
72:         efficiency=[0.95, 0.94],
73:         delivered_energy_wh=0.35,
74:         consumed_charge_ah=0.022,
75:         is_feasible=True,
76:         stop_reason="duration_complete",
77:     )
78: 
79:     assert result.final_state is final_state
80:     assert result.time_s == (0.0, 10.0)
81:     assert result.dod == (0.0, 0.1)
82:     assert result.stop_reason == "duration_complete"
83: 
84: 
85: def test_battery_integration_result_rejects_mismatched_histories():
86:     with pytest.raises(ValueError, match="same length"):
87:         BatteryIntegrationResult(
88:             final_state=BatteryState(soc=0.9),
89:             time_s=[0.0, 10.0],
90:             dod=[0.0],
91:             voltage_v=[16.0, 15.8],
92:             current_a=[8.0, 8.0],
93:             c_rate=[1.0, 1.0],
94:             power_w=[128.0, 126.4],
95:             efficiency=[0.95, 0.94],
96:             delivered_energy_wh=0.35,
97:             consumed_charge_ah=0.022,
98:             is_feasible=True,
99:             stop_reason="duration_complete",
100:         )
101: 
102: 
103: def test_rate_map_state_at_current(rate_map_battery):
104:     state = BatteryState(soc=0.5)
105:     point = rate_map_battery.state_at_current(state=state, current_a=8.0)
106: 
107:     assert point.is_feasible is True
108:     assert math.isclose(point.cell_current_a, 4.0)
109:     assert math.isclose(point.cell_voltage_v, 3.8 - 0.03 * 4.0)
110:     assert math.isclose(point.terminal_voltage_v, (3.8 - 0.03 * 4.0) * 4)
111:     assert math.isclose(point.power_w, point.terminal_voltage_v * 8.0)
112:     assert math.isclose(point.c_rate, 4.0 / 4.2)
113: 
114: 
115: def test_rate_map_state_at_power(rate_map_battery):
116:     state = BatteryState(soc=0.5)
117:     point = rate_map_battery.state_at_power(state=state, power_w=100.0)
118: 
119:     ocv = 3.8
120:     resistance = 0.03
121:     cell_power = 100.0 / (4 * 2)
122:     expected_cell_current = (ocv - math.sqrt(ocv**2 - 4.0 * resistance * cell_power)) / (
123:         2.0 * resistance
124:     )
125: 
126:     assert point.is_feasible is True
127:     assert math.isclose(point.cell_current_a, expected_cell_current)
128:     assert math.isclose(point.power_w, 100.0, rel_tol=1e-12)
129: 
130: 
131: def test_rate_map_state_at_power_loss(rate_map_battery):
132:     state = BatteryState(soc=0.5)
133:     point = rate_map_battery.state_at_power_loss(state=state, power_loss_w=7.68)
134: 
135:     internal_loss_w = (
136:         point.cell_current_a**2
137:         * point.resistance_ohm
138:         * rate_map_battery.series
139:         * rate_map_battery.parallel
140:     )
141: 
142:     assert point.is_feasible is True
143:     assert math.isclose(internal_loss_w, 7.68)
144: 
145: 
146: @pytest.mark.parametrize("power_loss_w", [-1.0, math.nan])
147: def test_rate_map_state_at_power_loss_rejects_invalid_inputs(rate_map_battery, power_loss_w):
148:     with pytest.raises(ValueError, match="power_loss_w"):
149:         rate_map_battery.state_at_power_loss(state=BatteryState(soc=0.5), power_loss_w=power_loss_w)
150: 
151: 
152: def test_rate_map_reports_infeasible_power(rate_map_battery):
153:     state = BatteryState(soc=0.5)
154:     point = rate_map_battery.state_at_power(state=state, power_w=2000.0)
155: 
156:     assert point.is_feasible is False
157:     assert point.infeasible_reason == "power_limit"
158: 
159: 
160: def test_rate_map_preserves_first_infeasible_reason(rate_map_battery):
161:     state = BatteryState(soc=0.5)
162:     point = rate_map_battery.state_at_current(state=state, current_a=1000.0)
163: 
164:     assert point.is_feasible is False
165:     assert point.cell_current_a > rate_map_battery.max_current_a
166:     assert point.cell_voltage_v < rate_map_battery.cutoff_voltage_v
167:     assert point.infeasible_reason == "current_limit"
168: 
169: 
170: def test_rate_map_step_current(rate_map_battery):
171:     state = BatteryState(soc=1.0)
172:     next_state = rate_map_battery.step_current(state=state, current_a=8.4, dt_s=1800.0)
173: 
174:     assert math.isclose(next_state.dod, 0.5)
175:     assert math.isclose(next_state.soc, 0.5)
176: 
177: 
178: def test_rate_map_integrates_constant_current(rate_map_battery):
179:     result = rate_map_battery.integrate_current(
180:         state=BatteryState(soc=1.0),
181:         current_a=8.4,
182:         dt_s=1800.0,
183:         max_step_s=60.0,
184:     )
185: 
186:     expected_energy_wh = ((16.464 + 14.696) / 2.0) * 8.4 * 0.5
187: 
188:     assert result.is_feasible is True
189:     assert result.stop_reason == "duration_complete"
190:     assert math.isclose(result.final_state.dod, 0.5)
191:     assert math.isclose(result.consumed_charge_ah, 4.2)
192:     assert math.isclose(result.delivered_energy_wh, expected_energy_wh)
193:     assert result.time_s[0] == 0.0
194:     assert result.time_s[-1] == 1800.0
195:     assert result.dod[-1] == result.final_state.dod
196: 
197: 
198: def test_rate_map_integrates_constant_c_rate_like_current(rate_map_battery):
199:     c_rate = rate_map_battery.integrate_c_rate(
200:         state=BatteryState(soc=1.0),
201:         c_rate=1.0,
202:         dt_s=600.0,
203:         max_step_s=60.0,
204:     )
205:     current = rate_map_battery.integrate_current(
206:         state=BatteryState(soc=1.0),
207:         current_a=rate_map_battery.rated_current_a * rate_map_battery.parallel,
208:         dt_s=600.0,
209:         max_step_s=60.0,
210:     )
211: 
212:     assert c_rate.final_state == current.final_state
213:     assert c_rate.delivered_energy_wh == current.delivered_energy_wh
214:     assert c_rate.consumed_charge_ah == current.consumed_charge_ah
215: 
216: 
217: def test_rate_map_integrates_zero_current_without_changing_state(rate_map_battery):
218:     result = rate_map_battery.integrate_current(
219:         state=BatteryState(soc=0.8),
220:         current_a=0.0,
221:         dt_s=120.0,
222:     )
223: 
224:     assert result.is_feasible is True
225:     assert result.stop_reason == "duration_complete"
226:     assert result.time_s == (0.0, 120.0)
227:     assert all(math.isclose(dod, 0.2) for dod in result.dod)
228:     assert result.consumed_charge_ah == 0.0
229:     assert result.delivered_energy_wh == 0.0
230: 
231: 
232: def test_rate_map_integrates_zero_duration_without_extra_sample(rate_map_battery):
233:     result = rate_map_battery.integrate_current(
234:         state=BatteryState(soc=0.8),
235:         current_a=8.0,
236:         dt_s=0.0,
237:     )
238: 
239:     assert result.is_feasible is True
240:     assert result.stop_reason == "duration_complete"
241:     assert result.time_s == (0.0,)
242:     assert math.isclose(result.dod[0], 0.2)
243: 
244: 
245: def test_rate_map_integrates_current_until_voltage_cutoff(rate_map_battery):
246:     result = rate_map_battery.integrate_current(
247:         state=BatteryState(soc=1.0),
248:         current_a=36.0,
249:         dt_s=1200.0,
250:         max_step_s=60.0,
251:     )
252: 
253:     assert result.is_feasible is False
254:     assert result.stop_reason == "voltage_cutoff"
255:     assert result.time_s[-1] < 1200.0
256:     assert math.isclose(result.voltage_v[-1] / rate_map_battery.series, rate_map_battery.cutoff_voltage_v)
257:     assert result.final_state.dod < 1.0
258: 
259: 
260: def test_rate_map_integrates_current_until_dod_limit(rate_map_battery):
261:     result = rate_map_battery.integrate_current(
262:         state=BatteryState(soc=1.0),
263:         current_a=1.0,
264:         dt_s=40000.0,
265:         max_step_s=5000.0,
266:     )
267: 
268:     assert result.is_feasible is False
269:     assert result.stop_reason == "dod_limit"
270:     assert result.final_state.dod == 1.0
271:     assert math.isclose(result.time_s[-1], 30240.0)
272:     assert math.isclose(result.consumed_charge_ah, 8.4)
273: 
274: 
275: def test_rate_map_integrates_current_reports_initial_infeasible_state(rate_map_battery):
276:     result = rate_map_battery.integrate_current(
277:         state=BatteryState(soc=0.5),
278:         current_a=1000.0,
279:         dt_s=60.0,
280:     )
281: 
282:     assert result.is_feasible is False
283:     assert result.stop_reason == "current_limit"
284:     assert result.time_s == (0.0,)
285:     assert result.consumed_charge_ah == 0.0
286:     assert result.delivered_energy_wh == 0.0
287: 
288: 
289: @pytest.mark.parametrize(
290:     ("kwargs", "message"),
291:     [
292:         ({"current_a": -1.0}, "current_a"),
293:         ({"current_a": math.nan}, "current_a"),
294:         ({"dt_s": -1.0}, "dt_s"),
295:         ({"dt_s": math.inf}, "dt_s"),
296:         ({"max_step_s": 0.0}, "max_step_s"),
297:         ({"max_step_s": math.nan}, "max_step_s"),
298:     ],
299: )
300: def test_rate_map_integrate_current_rejects_invalid_inputs(rate_map_battery, kwargs, message):
301:     params = {
302:         "state": BatteryState(soc=1.0),
303:         "current_a": 1.0,
304:         "dt_s": 10.0,
305:         "max_step_s": 1.0,
306:     }
307:     params.update(kwargs)
308: 
309:     with pytest.raises(ValueError, match=message):
310:         rate_map_battery.integrate_current(**params)
311: 
312: 
313: def test_rate_map_integrates_constant_power(rate_map_battery):
314:     result = rate_map_battery.integrate_power(
315:         state=BatteryState(soc=1.0),
316:         power_w=100.0,
317:         dt_s=600.0,
318:         max_step_s=10.0,
319:     )
320: 
321:     assert result.is_feasible is True
322:     assert result.stop_reason == "duration_complete"
323:     assert result.final_state.dod > 0.0
324:     assert result.time_s[0] == 0.0
325:     assert result.time_s[-1] == 600.0
326:     assert math.isclose(result.delivered_energy_wh, 100.0 * 600.0 / 3600.0)
327:     assert result.consumed_charge_ah > 0.0
328:     assert result.current_a[-1] > result.current_a[0]
329:     assert result.voltage_v[-1] < result.voltage_v[0]
330: 
331: 
332: def test_rate_map_integrates_zero_power_without_changing_state(rate_map_battery):
333:     result = rate_map_battery.integrate_power(
334:         state=BatteryState(soc=0.8),
335:         power_w=0.0,
336:         dt_s=120.0,
337:     )
338: 
339:     assert result.is_feasible is True
340:     assert result.stop_reason == "duration_complete"
341:     assert result.time_s == (0.0, 120.0)
342:     assert all(math.isclose(dod, 0.2) for dod in result.dod)
343:     assert result.consumed_charge_ah == 0.0
344:     assert result.delivered_energy_wh == 0.0
345: 
346: 
347: def test_rate_map_integrates_zero_power_duration_without_extra_sample(rate_map_battery):
348:     result = rate_map_battery.integrate_power(
349:         state=BatteryState(soc=0.8),
350:         power_w=100.0,
351:         dt_s=0.0,
352:     )
353: 
354:     assert result.is_feasible is True
355:     assert result.stop_reason == "duration_complete"
356:     assert result.time_s == (0.0,)
357:     assert math.isclose(result.dod[0], 0.2)
358: 
359: 
360: def test_rate_map_integrates_power_until_voltage_cutoff(rate_map_battery):
361:     result = rate_map_battery.integrate_power(
362:         state=BatteryState(soc=1.0),
363:         power_w=300.0,
364:         dt_s=20000.0,
365:         max_step_s=20.0,
366:     )
367: 
368:     assert result.is_feasible is False
369:     assert result.stop_reason == "voltage_cutoff"
370:     assert result.time_s[-1] < 20000.0
371:     assert math.isclose(result.voltage_v[-1] / rate_map_battery.series, rate_map_battery.cutoff_voltage_v)
372:     assert math.isclose(result.delivered_energy_wh, 300.0 * result.time_s[-1] / 3600.0)
373: 
374: 
375: def test_rate_map_integrates_power_until_dod_limit(rate_map_battery):
376:     result = rate_map_battery.integrate_power(
377:         state=BatteryState(soc=1.0),
378:         power_w=120.0,
379:         dt_s=20000.0,
380:         max_step_s=20.0,
381:     )
382: 
383:     assert result.is_feasible is False
384:     assert result.stop_reason == "dod_limit"
385:     assert result.final_state.dod == 1.0
386:     assert result.voltage_v[-1] / rate_map_battery.series > rate_map_battery.cutoff_voltage_v
387:     assert math.isclose(result.delivered_energy_wh, 120.0 * result.time_s[-1] / 3600.0)
388: 
389: 
390: def test_rate_map_integrates_power_reports_initial_power_limit(rate_map_battery):
391:     result = rate_map_battery.integrate_power(
392:         state=BatteryState(soc=0.5),
393:         power_w=2000.0,
394:         dt_s=60.0,
395:     )
396: 
397:     assert result.is_feasible is False
398:     assert result.stop_reason == "power_limit"
399:     assert result.time_s == (0.0,)
400:     assert result.consumed_charge_ah == 0.0
401:     assert result.delivered_energy_wh == 0.0
402: 
403: 
404: @pytest.mark.parametrize(
405:     ("kwargs", "message"),
406:     [
407:         ({"power_w": -1.0}, "power_w"),
408:         ({"power_w": math.nan}, "power_w"),
409:         ({"dt_s": -1.0}, "dt_s"),
410:         ({"dt_s": math.inf}, "dt_s"),
411:         ({"max_step_s": 0.0}, "max_step_s"),
412:         ({"max_step_s": math.nan}, "max_step_s"),
413:     ],
414: )
415: def test_rate_map_integrate_power_rejects_invalid_inputs(rate_map_battery, kwargs, message):
416:     params = {
417:         "state": BatteryState(soc=1.0),
418:         "power_w": 100.0,
419:         "dt_s": 10.0,
420:         "max_step_s": 1.0,
421:     }
422:     params.update(kwargs)
423: 
424:     with pytest.raises(ValueError, match=message):
425:         rate_map_battery.integrate_power(**params)
426: 
427: 
428: def test_rate_map_integrates_constant_voltage(rate_map_battery):
429:     result = rate_map_battery.integrate_voltage(
430:         state=BatteryState(soc=0.5),
431:         voltage_v=14.8,
432:         dt_s=120.0,
433:         max_step_s=10.0,
434:     )
435: 
436:     assert result.is_feasible is True
437:     assert result.stop_reason == "duration_complete"
438:     assert result.final_state.dod > 0.5
439:     assert all(math.isclose(voltage, 14.8) for voltage in result.voltage_v)
440: 
441: 
442: def test_rate_map_integrates_constant_load_resistance(rate_map_battery):
443:     result = rate_map_battery.integrate_load_resistance(
444:         state=BatteryState(soc=1.0),
445:         resistance_ohm=1.5,
446:         dt_s=120.0,
447:         max_step_s=10.0,
448:     )
449: 
450:     assert result.is_feasible is True
451:     assert result.stop_reason == "duration_complete"
452:     assert result.final_state.dod > 0.0
453:     assert result.current_a[-1] > 0.0
454:     assert math.isclose(result.power_w[-1], result.voltage_v[-1] * result.current_a[-1])
455: 
456: 
457: def test_rate_map_integrates_constant_power_loss(rate_map_battery):
458:     result = rate_map_battery.integrate_power_loss(
459:         state=BatteryState(soc=1.0),
460:         power_loss_w=4.0,
461:         dt_s=120.0,
462:         max_step_s=10.0,
463:     )
464: 
465:     point_loss_w = (
466:         (result.current_a[-1] / rate_map_battery.parallel) ** 2
467:         * rate_map_battery.resistance(result.final_state.dod)
468:         * rate_map_battery.series
469:         * rate_map_battery.parallel
470:     )
471: 
472:     assert result.is_feasible is True
473:     assert result.stop_reason == "duration_complete"
474:     assert result.final_state.dod > 0.0
475:     assert math.isclose(point_loss_w, 4.0)
476: 
477: 
478: @pytest.mark.parametrize(
479:     ("method_name", "kwargs", "message"),
480:     [
481:         ("integrate_voltage", {"voltage_v": -1.0, "dt_s": 10.0}, "voltage_v"),
482:         ("integrate_load_resistance", {"resistance_ohm": 0.0, "dt_s": 10.0}, "resistance_ohm"),
483:         ("integrate_power_loss", {"power_loss_w": math.nan, "dt_s": 10.0}, "power_loss_w"),
484:     ],
485: )
486: def test_rate_map_extended_integrators_reject_invalid_inputs(
487:     rate_map_battery,
488:     method_name,
489:     kwargs,
490:     message,
491: ):
492:     method = getattr(rate_map_battery, method_name)
493: 
494:     with pytest.raises(ValueError, match=message):
495:         method(state=BatteryState(soc=1.0), **kwargs)
496: 
497: 
498: def test_rate_map_integrates_current_to_target_dod(rate_map_battery):
499:     result = rate_map_battery.integrate_current_to_dod(
500:         state=BatteryState(soc=1.0),
501:         current_a=8.4,
502:         dod_final=0.5,
503:         max_step_s=60.0,
504:     )
505: 
506:     assert result.is_feasible is True
507:     assert result.stop_reason == "dod_target"
508:     assert math.isclose(result.final_state.dod, 0.5)
509:     assert math.isclose(result.time_s[-1], 1800.0)
510:     assert math.isclose(result.consumed_charge_ah, 4.2)
511: 
512: 
513: def test_rate_map_integrates_power_to_target_dod(rate_map_battery):
514:     result = rate_map_battery.integrate_power_to_dod(
515:         state=BatteryState(soc=1.0),
516:         power_w=100.0,
517:         dod_final=0.3,
518:         max_step_s=10.0,
519:     )
520: 
521:     assert result.is_feasible is True
522:     assert result.stop_reason == "dod_target"
523:     assert math.isclose(result.final_state.dod, 0.3, abs_tol=1e-10)
524:     assert math.isclose(result.delivered_energy_wh, 100.0 * result.time_s[-1] / 3600.0)
525: 
526: 
527: @pytest.mark.parametrize("dod_final", [0.0, -0.1, 1.1, math.nan])
528: def test_rate_map_integrate_to_dod_rejects_invalid_target(rate_map_battery, dod_final):
529:     with pytest.raises(ValueError, match="dod_final"):
530:         rate_map_battery.integrate_current_to_dod(
531:             state=BatteryState(soc=1.0),
532:             current_a=8.4,
533:             dod_final=dod_final,
534:         )
535: 
536: 
537: def test_rate_map_solves_dod_at_voltage_power(rate_map_battery):
538:     state = BatteryState.from_dod(0.5)
539:     point = rate_map_battery.state_at_power(state=state, power_w=100.0)
540: 
541:     dod_from_voltage = rate_map_battery.dod_at_voltage_power(
542:         voltage_v=point.terminal_voltage_v,
543:         power_w=point.power_w,
544:     )
545:     dod_from_power = rate_map_battery.dod_at_power_voltage(
546:         power_w=point.power_w,
547:         voltage_v=point.terminal_voltage_v,
548:     )
549: 
550:     assert math.isclose(dod_from_voltage, 0.5, abs_tol=1e-10)
551:     assert math.isclose(dod_from_power, 0.5, abs_tol=1e-10)
552: 
553: 
554: def test_rate_map_integrates_power_profile(rate_map_battery):
555:     result = rate_map_battery.integrate_power_profile(
556:         state=BatteryState(soc=1.0),
557:         power_w=[100.0, 60.0],
558:         durations_s=[120.0, 180.0],
559:         max_step_s=10.0,
560:     )
561:     first = rate_map_battery.integrate_power(
562:         state=BatteryState(soc=1.0),
563:         power_w=100.0,
564:         dt_s=120.0,
565:         max_step_s=10.0,
566:     )
567:     second = rate_map_battery.integrate_power(
568:         state=first.final_state,
569:         power_w=60.0,
570:         dt_s=180.0,
571:         max_step_s=10.0,
572:     )
573: 
574:     assert result.is_feasible is True
575:     assert result.stop_reason == "duration_complete"
576:     assert math.isclose(result.time_s[-1], 300.0)
577:     assert result.final_state == second.final_state
578:     assert math.isclose(result.delivered_energy_wh, first.delivered_energy_wh + second.delivered_energy_wh)
579:     assert math.isclose(result.consumed_charge_ah, first.consumed_charge_ah + second.consumed_charge_ah)
580: 
581: 
582: def test_rate_map_integrate_power_profile_rejects_mismatched_segments(rate_map_battery):
583:     with pytest.raises(ValueError, match="same length"):
584:         rate_map_battery.integrate_power_profile(
585:             state=BatteryState(soc=1.0),
586:             power_w=[100.0, 60.0],
587:             durations_s=[120.0],
588:         )
589: 
590: 
591: def test_rate_map_dod_energy_knockdown(rate_map_battery):
592:     full = rate_map_battery.energy_knockdown_dod(0.0, 1.0)
593:     first_half = rate_map_battery.energy_knockdown_dod(0.0, 0.5)
594: 
595:     assert math.isclose(full, 1.0)
596:     assert math.isclose(first_half, 2.0 / 3.75)
597: 
598: 
599: @pytest.mark.parametrize(
600:     ("dod_initial", "dod_final"),
601:     [
602:         (-0.1, 0.5),
603:         (0.5, 1.1),
604:         (0.5, 0.5),
605:         (0.8, 0.2),
606:         (math.nan, 0.5),
607:     ],
608: )
609: def test_rate_map_dod_energy_knockdown_rejects_invalid_inputs(
610:     rate_map_battery,
611:     dod_initial,
612:     dod_final,
613: ):
614:     with pytest.raises(ValueError, match="dod"):
615:         rate_map_battery.energy_knockdown_dod(dod_initial, dod_final)
616: 
617: 
618: def test_rate_map_c_rate_energy_knockdown(rate_map_battery):
619:     zero_c = rate_map_battery.energy_knockdown_c_rate(0.0)
620:     half_c = rate_map_battery.energy_knockdown_c_rate(0.5, max_step_s=60.0)
621:     one_c = rate_map_battery.energy_knockdown_c_rate(1.0, max_step_s=60.0)
622: 
623:     assert zero_c == 1.0
624:     assert 0.0 < one_c < half_c < zero_c
625: 
626: 
627: @pytest.mark.parametrize(
628:     ("kwargs", "message"),
629:     [
630:         ({"c_rate": -1.0}, "c_rate"),
631:         ({"c_rate": math.nan}, "c_rate"),
632:         ({"max_step_s": 0.0}, "max_step_s"),
633:         ({"max_step_s": math.inf}, "max_step_s"),
634:     ],
635: )
636: def test_rate_map_c_rate_energy_knockdown_rejects_invalid_inputs(
637:     rate_map_battery,
638:     kwargs,
639:     message,
640: ):
641:     params = {"c_rate": 1.0, "max_step_s": 60.0}
642:     params.update(kwargs)
643: 
644:     with pytest.raises(ValueError, match=message):
645:         rate_map_battery.energy_knockdown_c_rate(**params)
646: 
647: 
648: def test_rate_map_loads_from_json(tmp_path):
649:     path = tmp_path / "battery.json"
650:     path.write_text(
651:         json.dumps(
652:             {
653:                 "name": "JSON pack",
654:                 "source": "test",
655:                 "cell": {
656:                     "capacity_ah": 4.2,
657:                     "cutoff_voltage_v": 2.5,
658:                     "charge_voltage_v": 4.2,
659:                     "max_current_a": 20.0,
660:                 },
661:                 "curves": {
662:                     "dod": [0.0, 0.5, 1.0],
663:                     "ocv_v": [4.2, 3.8, 3.2],
664:                     "resistance_ohm": [0.02, 0.03, 0.05],
665:                 },
666:             }
667:         ),
668:         encoding="utf-8",
669:     )
670: 
671:     battery = RateMapBattery.from_json(path, series=4, parallel=2)
672: 
673:     assert battery.name == "JSON pack"
674:     assert battery.source == "test"
675:     assert battery.series == 4
676:     assert battery.parallel == 2
677: 
678: 
679: def test_rate_map_loads_example_cell_dataset():
680:     path = PROJECT_ROOT / "data" / "batteries" / "example_liion_cell.json"
681: 
682:     battery = RateMapBattery.from_json(path, series=4, parallel=2)
683:     point = battery.state_at_current(state=BatteryState(soc=0.5), current_a=8.4)
684: 
685:     assert battery.name == "Example Li-ion Cell"
686:     assert battery.series == 4
687:     assert battery.parallel == 2
688:     assert battery.capacity_ah == 4.2
689:     assert point.is_feasible is True
690:     assert math.isclose(point.cell_current_a, 4.2)
```

### 6dof_hopper/PyThrust/tests/test_models.py

SHA-256: `469ea6b0fcd9c79bd29557cb6e26b450b819a881b3f2fded9a8879cf0a774786`

- Definition `test_motor_spec_no_load_current` at lines 10-50.
- Definition `test_motor_spec_winding_resistance` at lines 53-73.
- Definition `test_other_specs` at lines 76-87.
- Definition `test_operating_point` at lines 90-144.

Full source for manual caller review:

```python
1: import math
2: import pytest
3: from pythrust.propulsion.models.battery import BatterySpec
4: from pythrust.propulsion.models.motor import MotorSpec
5: from pythrust.propulsion.models.operating_point import OperatingPoint
6: from pythrust.propulsion.models.propeller import PropellerSpec
7: from pythrust.propulsion.models.system import SystemSpec
8: 
9: 
10: def test_motor_spec_no_load_current():
11:     # 1. Base case: rpm <= 0
12:     motor = MotorSpec(
13:         kv_rpm_per_v=980.0,
14:         resistance_ohm=0.06,
15:         no_load_current_a=1.2,
16:         current_max_a=30.0
17:     )
18:     assert motor.get_no_load_current(-10.0) == 1.2
19:     assert motor.get_no_load_current(0.0) == 1.2
20: 
21:     # 2. Power-law iron loss (iron_loss_exponent > 0)
22:     # rpm_0 = kv_rpm_per_v * no_load_voltage_v = 980.0 * 10.0 = 9800.0
23:     # rpm = 4900.0 -> (4900.0 / 9800.0)^1.5 = 0.5^1.5 approx 0.35355
24:     # no_load_current = 1.2 * 0.35355 = 0.42426
25:     motor_iron = MotorSpec(
26:         kv_rpm_per_v=980.0,
27:         resistance_ohm=0.06,
28:         no_load_current_a=1.2,
29:         current_max_a=30.0,
30:         no_load_voltage_v=10.0,
31:         iron_loss_exponent=1.5
32:     )
33:     expected_rpm_0 = 980.0 * 10.0
34:     expected_current = 1.2 * (4900.0 / expected_rpm_0) ** 1.5
35:     assert math.isclose(motor_iron.get_no_load_current(4900.0), expected_current)
36: 
37:     # 3. Drela's quadratic speed model (iron_loss_exponent = 0.0)
38:     # omega = rpm * pi / 30 = 3000 * pi / 30 = 100 * pi
39:     # Io = Io0 + Io1 * omega + Io2 * omega^2
40:     motor_drela = MotorSpec(
41:         kv_rpm_per_v=980.0,
42:         resistance_ohm=0.06,
43:         no_load_current_a=1.2,
44:         current_max_a=30.0,
45:         no_load_current_linear=0.001,
46:         no_load_current_quadratic=0.00002
47:     )
48:     omega = 3000.0 * (math.pi / 30.0)
49:     expected_drela = 1.2 + 0.001 * omega + 0.00002 * (omega ** 2)
50:     assert math.isclose(motor_drela.get_no_load_current(3000.0), expected_drela)
51: 
52: 
53: def test_motor_spec_winding_resistance():
54:     # 1. Base case: resistance_quadratic <= 0
55:     motor = MotorSpec(
56:         kv_rpm_per_v=980.0,
57:         resistance_ohm=0.06,
58:         no_load_current_a=1.2,
59:         current_max_a=30.0
60:     )
61:     assert motor.get_winding_resistance(10.0) == 0.06
62:     assert motor.get_winding_resistance(-5.0) == 0.06
63: 
64:     # 2. Quadratic resistance (resistance_quadratic > 0)
65:     # R = R_base + R_quad * I^2 = 0.06 + 0.002 * 10^2 = 0.06 + 0.2 = 0.26
66:     motor_quad = MotorSpec(
67:         kv_rpm_per_v=980.0,
68:         resistance_ohm=0.06,
69:         no_load_current_a=1.2,
70:         current_max_a=30.0,
71:         resistance_quadratic=0.002
72:     )
73:     assert math.isclose(motor_quad.get_winding_resistance(10.0), 0.26)
74: 
75: 
76: def test_other_specs():
77:     battery = BatterySpec(voltage_v=11.1, discharge_efficiency=0.98)
78:     assert battery.voltage_v == 11.1
79:     assert battery.discharge_efficiency == 0.98
80: 
81:     system = SystemSpec(resistance_ohm=0.015)
82:     assert system.resistance_ohm == 0.015
83: 
84:     propeller = PropellerSpec(diameter_m=0.254, blade_count=3, pitch_m=0.114)
85:     assert propeller.diameter_m == 0.254
86:     assert propeller.blade_count == 3
87:     assert propeller.pitch_m == 0.114
88: 
89: 
90: def test_operating_point():
91:     op = OperatingPoint(
92:         rpm=8000.0,
93:         advance_ratio=0.4,
94:         ct=0.08,
95:         cp=0.04,
96:         thrust_n=15.0,
97:         torque_nm=0.3,
98:         shaft_power_w=250.0,
99:         motor_power_w=300.0,
100:         battery_power_w=310.0,
101:         motor_current_a=25.0,
102:         motor_voltage_v=12.0,
103:         is_feasible=True,
104:         propeller_efficiency=0.65,
105:         motor_efficiency=0.83,
106:         system_efficiency=0.5395,
107:         battery_voltage_v=11.1,
108:         battery_current_a=27.9,
109:         battery_c_rate=6.64,
110:         battery_efficiency=0.98,
111:     )
112:     assert op.rpm == 8000.0
113:     assert op.is_feasible is True
114:     assert op.infeasible_reason is None
115:     assert op.propeller_efficiency == 0.65
116:     assert op.motor_efficiency == 0.83
117:     assert op.system_efficiency == 0.5395
118:     assert op.battery_voltage_v == 11.1
119:     assert op.battery_current_a == 27.9
120:     assert op.battery_c_rate == 6.64
121:     assert op.battery_efficiency == 0.98
122: 
123:     # Test default values
124:     op_default = OperatingPoint(
125:         rpm=8000.0,
126:         advance_ratio=0.4,
127:         ct=0.08,
128:         cp=0.04,
129:         thrust_n=15.0,
130:         torque_nm=0.3,
131:         shaft_power_w=250.0,
132:         motor_power_w=300.0,
133:         battery_power_w=310.0,
134:         motor_current_a=25.0,
135:         motor_voltage_v=12.0,
136:         is_feasible=True
137:     )
138:     assert op_default.propeller_efficiency == 0.0
139:     assert op_default.motor_efficiency == 0.0
140:     assert op_default.system_efficiency == 0.0
141:     assert op_default.battery_voltage_v == 0.0
142:     assert op_default.battery_current_a == 0.0
143:     assert op_default.battery_c_rate == 0.0
144:     assert op_default.battery_efficiency == 1.0
```

### 6dof_hopper/PyThrust/tests/test_motors.py

SHA-256: `b702785653608de62a57872bc8803838d78b7cda6340e715fdfaf63ecb5f8de4`

- Definition `test_motor_database` at lines 6-55.

### 6dof_hopper/PyThrust/tests/test_openmdao.py

SHA-256: `3bafafb878552fdd90b567c03945223d1ac4d1c3a91d108804404dc6136d8f8d`

- Definition `prop_entry` at lines 24-31.
- Definition `test_propulsion_component_runs` at lines 34-97.

Full source for manual caller review:

```python
1: """Unit tests for OpenMDAO PropulsionComponent wrapper."""
2: 
3: from __future__ import annotations
4: 
5: from pathlib import Path
6: import pytest
7: import openmdao.api as om
8: 
9: from pythrust.propellers import PropellerDatabase
10: from pythrust.propulsion import (
11:     BatterySpec,
12:     MotorSpec,
13:     PropellerSpec,
14:     PropulsionSolver,
15:     SystemSpec,
16: )
17: from pythrust.openmdao import PropulsionComponent
18: 
19: _DATASET_DIR = Path(__file__).parent.parent / "data" / "propellers" / "apc_202602"
20: _PROP_ID = "APC_13x6.5E"
21: 
22: 
23: @pytest.fixture(scope="module")
24: def prop_entry():
25:     db = PropellerDatabase()
26:     if not db.load(_DATASET_DIR, strict=False):
27:         pytest.skip(f"Propeller dataset not found at {_DATASET_DIR}")
28:     entry = db.get(_PROP_ID)
29:     if entry is None:
30:         pytest.skip(f"{_PROP_ID} not found in dataset")
31:     return entry
32: 
33: 
34: def test_propulsion_component_runs(prop_entry):
35:     # 1. Run the raw solver as ground truth
36:     motor = MotorSpec(
37:         kv_rpm_per_v=860.0,
38:         resistance_ohm=0.0258,
39:         no_load_current_a=1.3,
40:         current_max_a=65.0,
41:     )
42:     battery = BatterySpec(voltage_v=14.8)
43:     system = SystemSpec(resistance_ohm=0.095)
44:     propeller = PropellerSpec(diameter_m=0.3302)
45:     
46:     solver = PropulsionSolver()
47:     op_ref = solver.solve_operating_point(
48:         motor=motor,
49:         battery=battery,
50:         system=system,
51:         propeller=propeller,
52:         prop_entry=prop_entry,
53:         rho=1.225,
54:         airspeed_mps=0.0,
55:         throttle=0.7,
56:     )
57:     assert op_ref.is_feasible
58: 
59:     # 2. Setup OpenMDAO problem
60:     prob = om.Problem()
61:     model = prob.model
62: 
63:     comp = PropulsionComponent(prop_entry=prop_entry)
64:     model.add_subsystem('prop', comp, promotes=['*'])
65: 
66:     prob.setup()
67: 
68:     # Set inputs
69:     prob.set_val('kv_rpm_per_v', 860.0)
70:     prob.set_val('resistance_ohm', 0.0258)
71:     prob.set_val('no_load_current_a', 1.3)
72:     prob.set_val('current_max_a', 65.0)
73:     prob.set_val('voltage_v', 14.8)
74:     prob.set_val('resistance_system_ohm', 0.095)
75:     prob.set_val('diameter_m', 0.3302)
76:     prob.set_val('throttle', 0.7)
77:     prob.set_val('rho', 1.225)
78:     prob.set_val('airspeed_mps', 0.0)
79: 
80:     # Solve / run
81:     prob.run_model()
82: 
83:     # Get outputs
84:     rpm_val = prob.get_val('rpm')[0]
85:     thrust_val = prob.get_val('thrust_n')[0]
86:     is_feasible_val = prob.get_val('is_feasible')[0]
87: 
88:     # Verify matching values
89:     assert rpm_val == pytest.approx(op_ref.rpm, abs=1e-2)
90:     assert thrust_val == pytest.approx(op_ref.thrust_n, rel=1e-3)
91:     assert is_feasible_val == 1.0
92: 
93:     # 3. Check partial derivatives using finite difference
94:     partials = prob.check_partials(method='fd', out_stream=None)
95:     
96:     # Assert derivatives are successfully calculated and non-empty
97:     assert len(partials) > 0
```

### 6dof_hopper/PyThrust/tests/test_propellers.py

SHA-256: `ecb31f2eb600bcc23b6b4a03a2ae6b51beef107034e99a3d3a796ba41fe35c54`

- Definition `test_find_insert_index` at lines 15-21.
- Definition `test_find_bracketing_indices` at lines 24-29.
- Definition `test_propeller_entry_properties` at lines 32-52.
- Definition `test_propeller_entry_get_coefficients` at lines 55-115.
- Definition `test_propeller_database_load` at lines 118-173.
- Definition `test_propeller_database_strict_validation` at lines 176-200.

### 6dof_hopper/PyThrust/tests/test_solver.py

SHA-256: `fb86891911b4a7b9e758ef5762d6b5320682568d8eab04cc878fb797bb884b09`

- Definition `test_setup` at lines 20-58.
- Definition `test_solver_zero_throttle` at lines 61-82.
- Definition `test_solver_successful_solve` at lines 85-120.
- Definition `test_solver_rate_map_matches_fixed_voltage_when_voltage_is_flat` at lines 123-167.
- Definition `test_solver_rate_map_voltage_changes_with_state_of_charge` at lines 170-218.
- Definition `test_solver_rate_map_requires_battery_state` at lines 221-247.
- Definition `test_solver_current_limit_exceeded` at lines 250-273.
- Definition `test_solver_no_bracket` at lines 276-293.
- Definition `test_estimate_j_max` at lines 296-309.
- Definition `test_solver_efficiencies` at lines 312-358.
- Definition `test_solver_invalid_efficiency` at lines 361-399.
- Definition `test_solver_preserves_first_infeasible_reason` at lines 402-443.

Full source for manual caller review:

```python
1: import math
2: import pytest
3: from pythrust.battery import BatteryState, RateMapBattery
4: from pythrust.propellers.database import (
5:     PropellerMetadata,
6:     PropellerDataPoint,
7:     PropellerEntry
8: )
9: from pythrust.propulsion.models import (
10:     MotorSpec,
11:     BatterySpec,
12:     SystemSpec,
13:     PropellerSpec,
14:     OperatingPoint
15: )
16: from pythrust.propulsion.solver import PropulsionSolver, SolverConfig
17: 
18: 
19: @pytest.fixture
20: def test_setup():
21:     motor = MotorSpec(
22:         kv_rpm_per_v=980.0,
23:         resistance_ohm=0.06,
24:         no_load_current_a=1.2,
25:         current_max_a=30.0,
26:         torque_constant_kv_ratio=1.0,
27:         magnetic_lag_tau=0.0001
28:     )
29:     battery = BatterySpec(voltage_v=11.1, discharge_efficiency=0.98)
30:     system = SystemSpec(resistance_ohm=0.015)
31:     propeller = PropellerSpec(diameter_m=0.254, blade_count=2, pitch_m=0.114)
32:     
33:     meta = PropellerMetadata(
34:         id="apc_10x4.7",
35:         manufacturer="APC",
36:         model="SF",
37:         diameter_in=10.0,
38:         pitch_in=4.7,
39:         blade_count=2,
40:         data_csv="apc_10x4.7.csv"
41:     )
42:     
43:     data = {
44:         1000.0: [
45:             PropellerDataPoint(j=0.0, ct=0.11, cp=0.055),
46:             PropellerDataPoint(j=0.4, ct=0.08, cp=0.04),
47:             PropellerDataPoint(j=0.8, ct=0.02, cp=0.01)
48:         ],
49:         8000.0: [
50:             PropellerDataPoint(j=0.0, ct=0.12, cp=0.06),
51:             PropellerDataPoint(j=0.4, ct=0.09, cp=0.045),
52:             PropellerDataPoint(j=0.8, ct=0.03, cp=0.015)
53:         ]
54:     }
55:     
56:     prop_entry = PropellerEntry(metadata=meta, data_by_rpm=data)
57:     
58:     return motor, battery, system, propeller, prop_entry
59: 
60: 
61: def test_solver_zero_throttle(test_setup):
62:     motor, battery, system, propeller, prop_entry = test_setup
63:     solver = PropulsionSolver()
64:     
65:     op = solver.solve_operating_point(
66:         motor=motor,
67:         battery=battery,
68:         system=system,
69:         propeller=propeller,
70:         prop_entry=prop_entry,
71:         rho=1.225,
72:         airspeed_mps=0.0,
73:         throttle=0.0
74:     )
75:     
76:     assert op.rpm == 0.0
77:     assert op.is_feasible is False
78:     assert op.infeasible_reason == "throttle<=0"
79:     assert op.battery_voltage_v == battery.voltage_v
80:     assert op.battery_current_a == 0.0
81:     assert op.battery_c_rate == 0.0
82:     assert op.battery_efficiency == battery.discharge_efficiency
83: 
84: 
85: def test_solver_successful_solve(test_setup):
86:     motor, battery, system, propeller, prop_entry = test_setup
87:     solver = PropulsionSolver()
88:     
89:     # Use static thrust (airspeed = 0.0) to avoid numeric edge issues on J
90:     op = solver.solve_operating_point(
91:         motor=motor,
92:         battery=battery,
93:         system=system,
94:         propeller=propeller,
95:         prop_entry=prop_entry,
96:         rho=1.225,
97:         airspeed_mps=0.0,
98:         throttle=0.8
99:     )
100:     
101:     # It should successfully converge to a positive RPM and be feasible
102:     assert op.is_feasible is True
103:     assert op.rpm > 0.0
104:     assert op.advance_ratio == 0.0
105:     assert op.ct > 0.0
106:     assert op.cp > 0.0
107:     assert op.thrust_n > 0.0
108:     assert op.torque_nm > 0.0
109:     
110:     # Test backing variables consistency
111:     # V_applied = 0.8 * 11.1 = 8.88V
112:     # V_motor + I * R_sys = V_applied
113:     v_applied = 0.8 * battery.voltage_v
114:     v_motor = op.motor_voltage_v
115:     i_sys = op.motor_current_a
116:     assert math.isclose(v_motor + i_sys * system.resistance_ohm, v_applied, rel_tol=1e-3)
117:     assert math.isclose(op.battery_voltage_v, battery.voltage_v)
118:     assert math.isclose(op.battery_current_a, op.battery_power_w / battery.voltage_v)
119:     assert op.battery_c_rate == 0.0
120:     assert op.battery_efficiency == battery.discharge_efficiency
121: 
122: 
123: def test_solver_rate_map_matches_fixed_voltage_when_voltage_is_flat(test_setup):
124:     motor, battery, system, propeller, prop_entry = test_setup
125:     solver = PropulsionSolver()
126:     state = BatteryState(soc=0.5)
127:     rate_map = RateMapBattery(
128:         name="flat voltage",
129:         capacity_ah=4.2,
130:         cutoff_voltage_v=2.5,
131:         charge_voltage_v=4.2,
132:         max_current_a=1000.0,
133:         series=3,
134:         parallel=1,
135:         dod=[0.0, 1.0],
136:         ocv_v=[battery.voltage_v / 3.0, battery.voltage_v / 3.0],
137:         resistance_ohm=[1e-12, 1e-12],
138:     )
139: 
140:     fixed_op = solver.solve_operating_point(
141:         motor=motor,
142:         battery=battery,
143:         system=system,
144:         propeller=propeller,
145:         prop_entry=prop_entry,
146:         rho=1.225,
147:         airspeed_mps=0.0,
148:         throttle=0.8,
149:     )
150:     rate_map_op = solver.solve_operating_point(
151:         motor=motor,
152:         battery=rate_map,
153:         battery_state=state,
154:         system=system,
155:         propeller=propeller,
156:         prop_entry=prop_entry,
157:         rho=1.225,
158:         airspeed_mps=0.0,
159:         throttle=0.8,
160:     )
161: 
162:     assert rate_map_op.is_feasible is True
163:     assert math.isclose(rate_map_op.rpm, fixed_op.rpm, rel_tol=1e-6)
164:     assert math.isclose(rate_map_op.battery_voltage_v, battery.voltage_v, rel_tol=1e-6)
165:     assert math.isclose(rate_map_op.battery_current_a, 0.8 * rate_map_op.motor_current_a, rel_tol=1e-6)
166:     assert rate_map_op.battery_c_rate > 0.0
167:     assert math.isclose(rate_map_op.battery_efficiency, 1.0, rel_tol=1e-9)
168: 
169: 
170: def test_solver_rate_map_voltage_changes_with_state_of_charge(test_setup):
171:     motor, _, system, propeller, prop_entry = test_setup
172:     solver = PropulsionSolver()
173:     battery = RateMapBattery(
174:         name="soc-sensitive voltage",
175:         capacity_ah=4.2,
176:         cutoff_voltage_v=2.5,
177:         charge_voltage_v=4.2,
178:         max_current_a=1000.0,
179:         series=3,
180:         parallel=2,
181:         dod=[0.0, 1.0],
182:         ocv_v=[4.1, 3.4],
183:         resistance_ohm=[0.01, 0.03],
184:     )
185: 
186:     high_soc = solver.solve_operating_point(
187:         motor=motor,
188:         battery=battery,
189:         battery_state=BatteryState(soc=1.0),
190:         system=system,
191:         propeller=propeller,
192:         prop_entry=prop_entry,
193:         rho=1.225,
194:         airspeed_mps=0.0,
195:         throttle=0.8,
196:     )
197:     low_soc = solver.solve_operating_point(
198:         motor=motor,
199:         battery=battery,
200:         battery_state=BatteryState(soc=0.2),
201:         system=system,
202:         propeller=propeller,
203:         prop_entry=prop_entry,
204:         rho=1.225,
205:         airspeed_mps=0.0,
206:         throttle=0.8,
207:     )
208: 
209:     assert high_soc.is_feasible is True
210:     assert low_soc.is_feasible is True
211:     assert high_soc.rpm > low_soc.rpm
212:     assert high_soc.battery_voltage_v > low_soc.battery_voltage_v
213:     assert high_soc.battery_current_a > 0.0
214:     assert low_soc.battery_current_a > 0.0
215:     assert high_soc.battery_c_rate > 0.0
216:     assert low_soc.battery_c_rate > 0.0
217:     assert 0.0 < high_soc.battery_efficiency <= 1.0
218:     assert 0.0 < low_soc.battery_efficiency <= 1.0
219: 
220: 
221: def test_solver_rate_map_requires_battery_state(test_setup):
222:     motor, _, system, propeller, prop_entry = test_setup
223:     solver = PropulsionSolver()
224:     battery = RateMapBattery(
225:         name="requires state",
226:         capacity_ah=4.2,
227:         cutoff_voltage_v=2.5,
228:         charge_voltage_v=4.2,
229:         max_current_a=1000.0,
230:         series=3,
231:         parallel=1,
232:         dod=[0.0, 1.0],
233:         ocv_v=[4.1, 3.4],
234:         resistance_ohm=[0.01, 0.03],
235:     )
236: 
237:     with pytest.raises(ValueError, match="battery_state"):
238:         solver.solve_operating_point(
239:             motor=motor,
240:             battery=battery,
241:             system=system,
242:             propeller=propeller,
243:             prop_entry=prop_entry,
244:             rho=1.225,
245:             airspeed_mps=0.0,
246:             throttle=0.8,
247:         )
248: 
249: 
250: def test_solver_current_limit_exceeded(test_setup):
251:     motor, battery, system, propeller, prop_entry = test_setup
252:     # Create a motor with a very low current limit to force current_limit infeasibility
253:     low_limit_motor = MotorSpec(
254:         kv_rpm_per_v=motor.kv_rpm_per_v,
255:         resistance_ohm=motor.resistance_ohm,
256:         no_load_current_a=motor.no_load_current_a,
257:         current_max_a=1.0  # Extremely low current limit
258:     )
259:     
260:     solver = PropulsionSolver()
261:     op = solver.solve_operating_point(
262:         motor=low_limit_motor,
263:         battery=battery,
264:         system=system,
265:         propeller=propeller,
266:         prop_entry=prop_entry,
267:         rho=1.225,
268:         airspeed_mps=0.0,
269:         throttle=0.9
270:     )
271:     
272:     assert op.is_feasible is False
273:     assert op.infeasible_reason == "current_limit"
274: 
275: 
276: def test_solver_no_bracket(test_setup):
277:     motor, battery, system, propeller, prop_entry = test_setup
278:     # Set high airspeed, so at low RPM the advance ratio is huge (past J_max)
279:     # causing cp <= 0 and evaluate_state returning inf, or v_motor > v_applied.
280:     solver = PropulsionSolver()
281:     op = solver.solve_operating_point(
282:         motor=motor,
283:         battery=battery,
284:         system=system,
285:         propeller=propeller,
286:         prop_entry=prop_entry,
287:         rho=1.225,
288:         airspeed_mps=100.0,  # Unrealistic high speed
289:         throttle=0.1         # Very low throttle
290:     )
291:     
292:     assert op.is_feasible is False
293:     assert op.infeasible_reason == "no_bracket"
294: 
295: 
296: def test_estimate_j_max(test_setup):
297:     _, _, _, _, prop_entry = test_setup
298:     
299:     # 1. Standard estimation
300:     # j_max values from data: 0.8 at 1000.0 RPM, 0.8 at 8000.0 RPM.
301:     # List of j_maxes is [0.8, 0.8]. Sorted.
302:     # len is 2. start = 2 // 4 = 0.
303:     # Should return j_maxes[0] = 0.8
304:     assert PropulsionSolver._estimate_j_max(prop_entry) == 0.8
305:     
306:     # 2. Empty data_by_rpm
307:     empty_meta = PropellerMetadata("empty", "A", "B", 10.0, 5.0, 2, "csv")
308:     empty_entry = PropellerEntry(metadata=empty_meta, data_by_rpm={})
309:     assert PropulsionSolver._estimate_j_max(empty_entry) == 0.6
310: 
311: 
312: def test_solver_efficiencies(test_setup):
313:     motor, battery, system, propeller, prop_entry = test_setup
314:     # Configure higher rpm_min to prevent rpm_min J from exceeding j_max and returning inf
315:     solver = PropulsionSolver(SolverConfig(rpm_min=2000.0))
316: 
317:     # 1. Static case (airspeed = 0)
318:     op_static = solver.solve_operating_point(
319:         motor=motor,
320:         battery=battery,
321:         system=system,
322:         propeller=propeller,
323:         prop_entry=prop_entry,
324:         rho=1.225,
325:         airspeed_mps=0.0,
326:         throttle=0.8
327:     )
328:     assert op_static.is_feasible is True
329:     assert op_static.propeller_efficiency == 0.0
330:     assert op_static.system_efficiency == 0.0
331:     assert 0.0 < op_static.motor_efficiency <= 1.0
332: 
333:     # 2. Dynamic case (airspeed = 5.0 m/s)
334:     op_dynamic = solver.solve_operating_point(
335:         motor=motor,
336:         battery=battery,
337:         system=system,
338:         propeller=propeller,
339:         prop_entry=prop_entry,
340:         rho=1.225,
341:         airspeed_mps=5.0,
342:         throttle=0.8
343:     )
344:     assert op_dynamic.is_feasible is True
345:     # Efficiencies should be positive and physically reasonable
346:     assert 0.0 < op_dynamic.propeller_efficiency <= 1.0
347:     assert 0.0 < op_dynamic.motor_efficiency <= 1.0
348:     assert 0.0 < op_dynamic.system_efficiency <= 1.0
349:     
350:     # System efficiency should be propeller_eff * motor_eff * battery_discharge_eff approximately
351:     # Since battery discharge efficiency is 0.98 and sys resistance is small:
352:     # eta_sys = (T * V) / P_battery. eta_motor = P_shaft / P_motor. eta_prop = (T * V) / P_shaft.
353:     # P_battery = (P_motor + I^2 * R_sys) / eta_batt_discharge.
354:     # Let's verify mathematically:
355:     expected_sys = op_dynamic.propeller_efficiency * op_dynamic.motor_efficiency
356:     # Since there are small electrical line losses (R_sys = 0.015) and battery efficiency (0.98),
357:     # actual system efficiency will be slightly lower than expected_sys.
358:     assert op_dynamic.system_efficiency <= expected_sys + 1e-5
359: 
360: 
361: def test_solver_invalid_efficiency(test_setup):
362:     motor, battery, system, propeller, _ = test_setup
363:     
364:     # Create custom propeller data where Ct/Cp = 15.0 at J = 0.2
365:     # With J = 0.2, eta_prop = (Ct/Cp) * J = 15.0 * 0.2 = 3.0 (> 1.0)
366:     meta = PropellerMetadata(
367:         id="bad_prop",
368:         manufacturer="APC",
369:         model="SF",
370:         diameter_in=10.0,
371:         pitch_in=4.7,
372:         blade_count=2,
373:         data_csv="bad.csv"
374:     )
375:     data = {
376:         8000.0: [
377:             PropellerDataPoint(j=0.0, ct=0.12, cp=0.06),
378:             PropellerDataPoint(j=0.2, ct=0.15, cp=0.01),
379:             PropellerDataPoint(j=0.8, ct=0.02, cp=0.01)
380:         ]
381:     }
382:     bad_entry = PropellerEntry(metadata=meta, data_by_rpm=data)
383:     
384:     solver = PropulsionSolver(SolverConfig(rpm_min=2000.0))
385:     # Solve at airspeed = 5.0 m/s to land J near 0.2
386:     op = solver.solve_operating_point(
387:         motor=motor,
388:         battery=battery,
389:         system=system,
390:         propeller=propeller,
391:         prop_entry=bad_entry,
392:         rho=1.225,
393:         airspeed_mps=5.0,
394:         throttle=0.8
395:     )
396:     
397:     # The solver should calculate the point but mark it infeasible
398:     assert op.is_feasible is False
399:     assert op.infeasible_reason == "invalid_efficiency"
400: 
401: 
402: def test_solver_preserves_first_infeasible_reason(test_setup):
403:     motor, battery, system, propeller, _ = test_setup
404:     low_limit_motor = MotorSpec(
405:         kv_rpm_per_v=motor.kv_rpm_per_v,
406:         resistance_ohm=motor.resistance_ohm,
407:         no_load_current_a=motor.no_load_current_a,
408:         current_max_a=0.01,
409:     )
410:     meta = PropellerMetadata(
411:         id="bad_prop",
412:         manufacturer="APC",
413:         model="SF",
414:         diameter_in=10.0,
415:         pitch_in=4.7,
416:         blade_count=2,
417:         data_csv="bad.csv",
418:     )
419:     data = {
420:         6000.0: [
421:             PropellerDataPoint(j=0.0, ct=0.12, cp=0.06),
422:             PropellerDataPoint(j=0.2, ct=0.15, cp=0.01),
423:             PropellerDataPoint(j=0.8, ct=0.02, cp=0.01),
424:         ]
425:     }
426:     bad_entry = PropellerEntry(metadata=meta, data_by_rpm=data)
427:     solver = PropulsionSolver()
428:     rpm = 5.0 / (0.2 * propeller.diameter_m) * 60.0
429: 
430:     op = solver._build_point(
431:         motor=low_limit_motor,
432:         battery=battery,
433:         system=system,
434:         propeller=propeller,
435:         prop_entry=bad_entry,
436:         rho=1.225,
437:         airspeed_mps=5.0,
438:         rpm=rpm,
439:         throttle=0.8,
440:     )
441: 
442:     assert op.is_feasible is False
443:     assert op.infeasible_reason == "current_limit"
```

### 6dof_hopper/aero/aero.py

SHA-256: `9008c26ea2c2c26e1e26441ee17f27872e1d34bf1c0d9cb7179ce285d6e2b53f`

- Definition `Aerodynamics` at lines 4-260.
- Definition `Aerodynamics.__init__` at lines 5-6.
- Definition `Aerodynamics.determine_at_point` at lines 8-260.

Full source for manual caller review:

```python
1: import numpy as np
2: 
3: 
4: class Aerodynamics:
5:     def __init__(self, hopper):
6:         self.hopper = hopper
7: 
8:     def determine_at_point(
9:         self,
10:         air_velocity_body,
11:         angular_rates_body,
12:         density,
13:         dynamic_viscosity,
14:         speed_of_sound,
15:         cg,
16:         inner_diameter=0,
17:         tube_axis_body=(1, 0, 0),
18:         closed_front=True,
19:         front_pressure_cd=0.8,
20:     ):
21:         """
22:         Calculate aerodynamic force and moment of a cylindrical tube.
23: 
24:         Uses:
25:             OpenRocket equation 3.26 for cylindrical body lift
26:             OpenRocket equation 3.58 for pitch/yaw damping
27:             OpenRocket equations 3.78, 3.82-3.85 for skin friction
28: 
29:         Assumptions:
30:             - air_velocity_body is vehicle velocity relative to air
31:             - all vectors are expressed in body coordinates
32:             - body +x is normally the tube longitudinal axis
33:             - force and moment are returned in body coordinates
34:             - tube is circular and axisymmetric
35: 
36:         Parameters
37:         ----------
38:         air_velocity_body : array_like, shape (3,)
39:             Vehicle velocity relative to air in body coordinates [m/s].
40: 
41:         angular_rates_body : array_like, shape (3,)
42:             Body angular rates [p, q, r] in body coordinates [rad/s].
43: 
44:         density : float
45:             Air density [kg/m^3].
46: 
47:         dynamic_viscosity : float
48:             Dynamic viscosity [Pa.s].
49: 
50:         speed_of_sound : float
51:             Local speed of sound [m/s].
52: 
53:         tube_length : float
54:             Tube length [m].
55: 
56:         outer_diameter : float
57:             Tube outer diameter [m].
58: 
59:         tube_center_body : array_like, shape (3,)
60:             Tube geometric-centre position relative to the body datum [m].
61: 
62:         cg_body : array_like, shape (3,)
63:             Vehicle CG position relative to the same body datum [m].
64: 
65:         inner_diameter : float
66:             Tube inner diameter [m].
67: 
68:         tube_axis_body : array_like, shape (3,)
69:             Unit vector along the tube longitudinal axis.
70: 
71:         closed_front : bool
72:             If True, use the full circular frontal area.
73:             If False, use the annular tube-wall area.
74: 
75:         front_pressure_cd : float
76:             Pressure-drag coefficient of the front face.
77:             OpenRocket gives approximately 0.8 for a flat blunt face.
78: 
79:         Returns
80:         -------
81:         force_body : ndarray, shape (3,)
82:             Total tube aerodynamic force [N].
83: 
84:         moment_body : ndarray, shape (3,)
85:             Total tube aerodynamic moment about the vehicle CG [N.m].
86:         """
87: 
88:         epsilon = 1e-10
89: 
90:         velocity = np.asarray(air_velocity_body, dtype=float)
91:         omega = np.asarray(angular_rates_body, dtype=float)
92:         tube_center = np.asarray(
93:             self.hopper.tube_center_body,
94:             dtype=float,
95:         )
96:         cg = np.asarray(cg, dtype=float)
97: 
98:         tube_axis = np.asarray(tube_axis_body, dtype=float)
99:         axis_norm = np.linalg.norm(tube_axis)
100: 
101:         if axis_norm < epsilon:
102:             raise ValueError("tube_axis_body cannot be a zero vector")
103: 
104:         tube_axis /= axis_norm
105: 
106:         air_speed = np.linalg.norm(velocity)
107: 
108:         if air_speed < epsilon:
109:             return np.zeros(3), np.zeros(3)
110: 
111:         dynamic_pressure = 0.5 * density * air_speed**2
112: 
113:         # Vector from vehicle CG to the tube centre/CP.
114:         r_cp = tube_center - cg
115: 
116:         # ------------------------------------------------------------------
117:         # Resolve airflow into axial and transverse components
118:         # ------------------------------------------------------------------
119: 
120:         axial_velocity_scalar = np.dot(velocity, tube_axis)
121: 
122:         axial_velocity = axial_velocity_scalar * tube_axis
123: 
124:         crossflow_velocity = velocity - axial_velocity
125:         crossflow_speed = np.linalg.norm(crossflow_velocity)
126: 
127:         # ------------------------------------------------------------------
128:         # Cylindrical body normal force: OpenRocket equation 3.26
129:         #
130:         # CN = K (D L / Aref) sin(alpha)^2
131:         # N  = q Aref CN
132:         #
133:         # K approximately 1.1
134:         # ------------------------------------------------------------------
135: 
136:         normal_force = np.zeros(3)
137: 
138:         if crossflow_speed > epsilon:
139:             sin_alpha = np.clip(crossflow_speed / air_speed, 0, 1)
140: 
141:             normal_force_magnitude = (
142:                 dynamic_pressure
143:                 * 1.1
144:                 * self.hopper.outer_diameter
145:                 * self.hopper.length
146:                 * sin_alpha**2
147:             )
148: 
149:             normal_force = (
150:                 -normal_force_magnitude * crossflow_velocity / crossflow_speed
151:             )
152: 
153:         static_moment = np.cross(r_cp, normal_force)
154: 
155:         # ------------------------------------------------------------------
156:         # Axial skin-friction drag
157:         # OpenRocket equations 3.78 and 3.82-3.85
158:         # ------------------------------------------------------------------
159: 
160:         axial_force = np.zeros(3)
161: 
162:         axial_speed = abs(axial_velocity_scalar)
163: 
164:         if axial_speed > epsilon:
165:             reynolds = density * axial_speed * self.hopper.length / dynamic_viscosity
166: 
167:             if reynolds < 1e4:
168:                 skin_friction_coefficient = 1.48e-2
169:             else:
170:                 skin_friction_coefficient = 1 / (1.5 * np.log(reynolds) - 5.6) ** 2
171: 
172:             mach = axial_speed / speed_of_sound
173: 
174:             # Compressibility correction
175:             if mach < 1:
176:                 corrected_skin_friction = skin_friction_coefficient * (
177:                     1 - 0.1 * mach**2
178:                 )
179:             else:
180:                 corrected_skin_friction = (
181:                     skin_friction_coefficient / (1 + 0.15 * mach**2) ** 0.58
182:                 )
183: 
184:             wetted_area = np.pi * self.hopper.outer_diameter * self.hopper.length
185: 
186:             fineness_ratio = self.hopper.length / self.hopper.outer_diameter
187: 
188:             body_shape_correction = 1 + 1 / (2 * fineness_ratio)
189: 
190:             axial_dynamic_pressure = 0.5 * density * axial_speed**2
191: 
192:             skin_friction_drag = (
193:                 axial_dynamic_pressure
194:                 * corrected_skin_friction
195:                 * body_shape_correction
196:                 * wetted_area
197:             )
198: 
199:             # Frontal pressure drag
200:             if closed_front:
201:                 frontal_area = np.pi * self.hopper.outer_diameter**2 / 4
202:             else:
203:                 frontal_area = (
204:                     np.pi
205:                     * (self.hopper.outer_diameter**2 - self.hopper.inner_diameter**2)
206:                     / 4
207:                 )
208: 
209:             pressure_drag = axial_dynamic_pressure * front_pressure_cd * frontal_area
210: 
211:             total_axial_drag = skin_friction_drag + pressure_drag
212: 
213:             # Oppose the axial component of motion.
214:             axial_direction = np.sign(axial_velocity_scalar) * tube_axis
215: 
216:             axial_force = -total_axial_drag * axial_direction
217: 
218:         axial_moment = np.cross(r_cp, axial_force)
219: 
220:         # ------------------------------------------------------------------
221:         # Pitch/yaw damping: analytical form of OpenRocket equation 3.58
222:         # ------------------------------------------------------------------
223: 
224:         omega_axial = np.dot(omega, tube_axis) * tube_axis
225: 
226:         omega_transverse = omega - omega_axial
227:         omega_transverse_magnitude = np.linalg.norm(omega_transverse)
228: 
229:         damping_moment = np.zeros(3)
230: 
231:         if omega_transverse_magnitude > epsilon:
232:             # Tube-end positions measured longitudinally from the CG.
233:             tube_center_from_cg = np.dot(r_cp, tube_axis)
234: 
235:             first_end = tube_center_from_cg - self.hopper.length / 2
236: 
237:             second_end = tube_center_from_cg + self.hopper.length / 2
238: 
239:             # Integral of |x|^3 dx over the complete tube.
240:             distance_integral = (
241:                 second_end * abs(second_end) ** 3 - first_end * abs(first_end) ** 3
242:             ) / 4
243: 
244:             damping_coefficient = (
245:                 0.5 * density * 1.1 * self.hopper.outer_diameter * distance_integral
246:             )
247: 
248:             damping_moment = (
249:                 -damping_coefficient * omega_transverse_magnitude * omega_transverse
250:             )
251: 
252:         # ------------------------------------------------------------------
253:         # Total force and moment about vehicle CG
254:         # ------------------------------------------------------------------
255: 
256:         force_body = normal_force + axial_force
257: 
258:         moment_body = static_moment + axial_moment + damping_moment
259: 
260:         return force_body, moment_body
```

### 6dof_hopper/chassis/hopper.py

SHA-256: `6e2b2f93e98b844ce04f68d26b704c65270e9329e1abff76caa45cbcd5dcf0bd`

- Definition `Hopper` at lines 10-58.
- Definition `Hopper.__post_init__` at lines 30-43.
- Definition `Hopper.mass` at lines 45-46.
- Definition `Hopper.CG` at lines 48-49.
- Definition `Hopper.inertia` at lines 51-52.
- Definition `Hopper.get_thrust_and_moment` at lines 54-58.
- Candidate caller `Hopper.mass` -> `self.propulsion.get_mass` at line 46.
- Candidate caller `Hopper.get_thrust_and_moment` -> `self.propulsion.get_thrust_and_moment` at line 58.

Full source for manual caller review:

```python
1: from dataclasses import dataclass, field
2: from typing import Optional
3: 
4: import numpy as np
5: 
6: from propulsion.propulsion import Propulsion
7: 
8: 
9: @dataclass
10: class Hopper:
11:     """Mass properties and external geometry of the hopper."""
12: 
13:     propulsion: Propulsion
14:     cg: np.ndarray
15:     mass_wo_propellant: float
16:     moment_arm: np.ndarray
17:     Ixx: float
18:     Iyy: float
19:     Izz: float
20:     cd: float
21:     csa: float
22:     length: float
23:     outer_diameter: float
24:     inner_diameter: float = 0.0
25:     tube_center_body: np.ndarray = field(
26:         default_factory=lambda: np.zeros(3, dtype=float)
27:     )
28:     reference_length: Optional[float] = None
29: 
30:     def __post_init__(self):
31:         self.cg = np.asarray(self.cg, dtype=float)
32:         self.moment_arm = np.asarray(self.moment_arm, dtype=float)
33:         self.tube_center_body = np.asarray(
34:             self.tube_center_body,
35:             dtype=float,
36:         )
37: 
38:         for name in ("cg", "moment_arm", "tube_center_body"):
39:             if getattr(self, name).shape != (3,):
40:                 raise ValueError(f"{name} must be a three-element vector")
41: 
42:         if self.reference_length is None:
43:             self.reference_length = self.length
44: 
45:     def mass(self, time: float) -> float:
46:         return self.mass_wo_propellant + self.propulsion.get_mass(time)
47: 
48:     def CG(self, time: float) -> np.ndarray:
49:         return self.cg.copy()
50: 
51:     def inertia(self, time: float) -> np.ndarray:
52:         return np.diag((self.Ixx, self.Iyy, self.Izz))
53: 
54:     def get_thrust_and_moment(
55:         self,
56:         time: float,
57:     ) -> tuple[np.ndarray, np.ndarray]:
58:         return self.propulsion.get_thrust_and_moment(time)
```

### 6dof_hopper/helpers/constants.py

SHA-256: `4853ae63f4d7df5254af6fbab9b46dd31ca60aa722dd3580643064bfce9523a4`


Full source for manual caller review:

```python
1: GRAVITY = 9.8065
```

### 6dof_hopper/helpers/math.py

SHA-256: `5e6420ade1c4d642762ba4d6b0812a80f2f693a58151bbf16a4274efb521239a`

- Definition `quarternion_to_dcm` at lines 5-37.
- Definition `euler_to_quaternion` at lines 40-68.

Full source for manual caller review:

```python
1: from numpy.typing import NDArray
2: import numpy as np
3: 
4: 
5: def quarternion_to_dcm(quarternion: NDArray, transpose=False):
6:     """
7:     Transformation matrix of body wrt local level coordinates
8:     :param quaternions:
9:     :return:
10:     """
11: 
12:     # Normalise Quaternions
13:     quaternions = np.array(quaternions) / np.linalg.norm(quaternions)
14: 
15:     # Get quaternion components
16:     q0, q1, q2, q3 = quaternions
17: 
18:     # Calculate transformation matrix components
19:     l1 = np.square(q0) + np.square(q1) - np.square(q2) - np.square(q3)
20:     l2 = 2 * (q1 * q2 + q0 * q3)
21:     l3 = 2 * (q1 * q3 - q0 * q2)
22: 
23:     m1 = 2 * (q1 * q2 - q0 * q3)
24:     m2 = np.square(q0) - np.square(q1) + np.square(q2) - np.square(q3)
25:     m3 = 2 * (q2 * q3 + q0 * q1)
26: 
27:     n1 = 2 * (q0 * q2 + q1 * q3)
28:     n2 = 2 * (q2 * q3 - q0 * q1)
29:     n3 = np.square(q0) - np.square(q1) - np.square(q2) + np.square(q3)
30: 
31:     # Calculate transformation matrix
32:     dcm = np.array([[l1, l2, l3], [m1, m2, m3], [n1, n2, n3]])
33: 
34:     if transpose:
35:         return np.transpose(dcm)
36:     else:
37:         return dcm
38: 
39: 
40: def euler_to_quaternion(euler_angles, degrees=True):
41:     # Euler angles are defined as [roll, pitch, yaw], [phi, theta, psi], [z, y, x]
42:     if degrees:
43:         euler_angles = np.deg2rad(euler_angles)
44: 
45:     # Get Euler components
46:     psi, theta, phi = euler_angles
47: 
48:     # Calculate Quaternions
49:     q0 = np.cos(psi / 2) * np.cos(theta / 2) * np.cos(phi / 2) + np.sin(
50:         psi / 2
51:     ) * np.sin(theta / 2) * np.sin(phi / 2)
52:     q1 = np.cos(psi / 2) * np.cos(theta / 2) * np.sin(phi / 2) - np.sin(
53:         psi / 2
54:     ) * np.sin(theta / 2) * np.cos(phi / 2)
55:     q2 = np.cos(psi / 2) * np.sin(theta / 2) * np.cos(phi / 2) + np.sin(
56:         psi / 2
57:     ) * np.cos(theta / 2) * np.sin(phi / 2)
58:     q3 = np.sin(psi / 2) * np.cos(theta / 2) * np.cos(phi / 2) - np.cos(
59:         psi / 2
60:     ) * np.sin(theta / 2) * np.sin(phi / 2)
61: 
62:     # Combine quaternion components into matrix of row vectors
63:     quaternions = np.array([q0, q1, q2, q3])
64: 
65:     # Normalise Quaternions
66:     quaternions = np.array(quaternions) / np.linalg.norm(quaternions)
67: 
68:     return quaternions
```

### 6dof_hopper/main.py

SHA-256: `67ebbf79c219721eb1f0cc6e4817b8fb218488b6dec4bbd25a1f0faee6527dbc`

- Definition `main` at lines 1-2.

Full source for manual caller review:

```python
1: def main():
2:     print("Hello from 6dof-hopper!")
3: 
4: 
5: if __name__ == "__main__":
6:     main()
```

### 6dof_hopper/propulsion/propeller.py

SHA-256: `caa5ee91e46d102b8ebe0c02e1dfec0ecdca18e2c423791fca6f2c19100ae7b6`

- Definition `Propellor` at lines 4-15.
- Definition `Propellor.__init__` at lines 5-15.

Full source for manual caller review:

```python
1: from propulsion.propulsion import Propulsion
2: 
3: 
4: class Propellor(Propulsion):
5:     def __init__(
6:         self,
7:         type,
8:         motor_kv_rpm_per_v,
9:         motor_resistance_ohm,
10:         motor_no_load_current,
11:         motor_max_current,
12:         battery_voltage_v,
13:         system_resistance_ohm,
14:     ):
15:         super().__init__(type)
```

### 6dof_hopper/propulsion/propulsion.py

SHA-256: `e07b895d8399016a3b0511afb195d7ebf992050cef04ab3015600347f01750ce`

- Definition `PropulsionType` at lines 5-7.
- Definition `Propulsion` at lines 10-24.
- Definition `Propulsion.__init__` at lines 11-12.
- Definition `Propulsion.get_mass` at lines 15-16.
- Definition `Propulsion.get_local_cg` at lines 19-20.
- Definition `Propulsion.get_thrust_and_moment` at lines 23-24.

Full source for manual caller review:

```python
1: from enum import Enum, auto, unique
2: from abc import ABC, abstractmethod
3: 
4: 
5: class PropulsionType(Enum):
6:     LIQUID = auto()
7:     PROPELLER = auto()
8: 
9: 
10: class Propulsion(ABC):
11:     def __init__(self, type: PropulsionType):
12:         self.type = type
13: 
14:     @abstractmethod
15:     def get_mass(t):
16:         pass
17: 
18:     @abstractmethod
19:     def get_local_cg():
20:         pass
21: 
22:     @abstractmethod
23:     def get_thrust_and_moment(t):
24:         pass
```

### 6dof_hopper/scripts/ehopper.py

SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`


Full source for manual caller review:

```python
```

### 6dof_hopper/simulation/simulation.py

SHA-256: `087767eef40f728775d5bd8ee597a6e0a8c0769fe4d2d6ab2a060d06692f86ca`

- Definition `Simulation` at lines 8-153.
- Definition `Simulation.__init__` at lines 9-13.
- Definition `Simulation.trajectory_ode` at lines 15-131.
- Definition `Simulation.solve_ode` at lines 133-153.
- Candidate caller `Simulation.trajectory_ode` -> `self.state.update_state` at line 17.
- Candidate caller `Simulation.trajectory_ode` -> `quarternion_to_dcm` at line 37.
- Candidate caller `Simulation.trajectory_ode` -> `self.hopper.mass` at line 91.
- Candidate caller `Simulation.trajectory_ode` -> `self.hopper.CG` at line 92.
- Candidate caller `Simulation.trajectory_ode` -> `self.hopper.inertia` at line 93.
- Candidate caller `Simulation.trajectory_ode` -> `self.hopper.get_thrust_and_moment` at line 96.
- Candidate caller `Simulation.trajectory_ode` -> `self.aero.determine_at_point` at line 98.
- Candidate caller `Simulation.solve_ode` -> `euler_to_quaternion` at line 134.
- Candidate caller `Simulation.solve_ode` -> `State` at line 142.
- Candidate caller `Simulation.solve_ode` -> `solve_ivp` at line 144.

Full source for manual caller review:

```python
1: import numpy as np
2: from helpers.math import quarternion_to_dcm, euler_to_quaternion
3: from helpers.constants import GRAVITY
4: from state import State
5: from scipy.integrate import solve_ivp
6: 
7: 
8: class Simulation:
9:     def __init__(self, state: State, environment, hopper, aero):
10:         self.state = None
11:         self.environment = environment
12:         self.hopper = hopper
13:         self.aero = aero
14: 
15:     def trajectory_ode(self, time, state):
16:         if self.time != 0:
17:             self.state.update_state(state)
18: 
19:         if self.state == None:
20:             print("bricked")
21: 
22:         position = np.array([state.x, state.y, state.z], dtype=float)
23:         velocity_body = np.array([state.u, state.v, state.w], dtype=float)
24: 
25:         quaternion = np.array([state.q0, state.q1, state.q2, state.q3], dtype=float)
26: 
27:         angular_rates = np.array([state.p, state.q, state.r], dtype=float)
28: 
29:         p, q, r = angular_rates
30: 
31:         # Preserve the original norm error for feedback correction.
32:         quaternion_norm_error = 1 - quaternion @ quaternion
33: 
34:         # Use a unit quaternion when generating the DCM.
35:         quaternion_unit = quaternion / np.linalg.norm(quaternion)
36: 
37:         TBL = quarternion_to_dcm(quaternion_unit)
38:         TLB = TBL.T
39: 
40:         # Environment
41:         height = -position[2]
42:         altitude = self.environment.elevation + height
43: 
44:         atmosphere = self.environment.atmosphere
45: 
46:         speed_of_sound = atmosphere.speed_of_sound(altitude)
47:         density = atmosphere.density(altitude)
48:         dynamic_viscosity = atmosphere.dynamic_viscosity(altitude)
49: 
50:         wind_velocity_local = np.asarray(
51:             atmosphere.wind_velocity(altitude), dtype=float
52:         )
53: 
54:         # Relative airflow
55:         rocket_velocity_local = TLB @ velocity_body
56:         air_velocity_local = rocket_velocity_local - wind_velocity_local
57:         air_velocity_body = TBL @ air_velocity_local
58: 
59:         air_speed = np.linalg.norm(air_velocity_body)
60: 
61:         if air_speed < 1e-8:
62:             mach = 0
63:             dynamic_pressure = 0
64:             reynolds = 0
65:             alpha = 0
66:             beta = 0
67:         else:
68:             mach = air_speed / speed_of_sound
69:             dynamic_pressure = 0.5 * density * air_speed**2
70: 
71:             reynolds = (
72:                 density * air_speed * self.hopper.reference_length / dynamic_viscosity
73:             )
74: 
75:             alpha = np.arctan2(air_velocity_body[2], air_velocity_body[0])
76: 
77:             beta = np.arcsin(np.clip(air_velocity_body[1] / air_speed, -1, 1))
78: 
79:         quaternion_rate_matrix = np.array(
80:             [[0, -p, -q, -r], [p, 0, r, -q], [q, -r, 0, p], [r, q, -p, 0]]
81:         )
82: 
83:         correction_gain = 0.5
84: 
85:         quaternion_dot = (
86:             0.5 * quaternion_rate_matrix @ quaternion
87:             + correction_gain * quaternion_norm_error * quaternion
88:         )
89: 
90:         # Mass properties
91:         mass = self.hopper.mass(time)
92:         cg = np.asarray(self.hopper.CG(time))
93:         inertia = np.asarray(self.hopper.inertia(time))
94: 
95:         # Forces and moments must all be in body coordinates
96:         prop_force, prop_moment = self.hopper.get_thrust_and_moment(time)
97: 
98:         aero_force, aero_moment = self.aero.determine_at_point(
99:             air_velocity_body=air_velocity_body,
100:             angular_rates_body=angular_rates,
101:             density=density,
102:             dynamic_viscosity=dynamic_viscosity,
103:             speed_of_sound=speed_of_sound,
104:             cg=cg,
105:         )
106: 
107:         total_force_body = aero_force + prop_force
108:         total_moment_body = aero_moment + prop_moment
109: 
110:         # Translational kinematics
111:         position_dot = TLB @ velocity_body
112: 
113:         # Translational dynamics
114:         gravity_local = np.array([0, 0, GRAVITY])
115:         gravity_body = TBL @ gravity_local
116: 
117:         velocity_dot = (
118:             total_force_body / mass
119:             + gravity_body
120:             - np.cross(angular_rates, velocity_body)
121:         )
122: 
123:         # Rotational dynamics
124:         body_rate_dot = np.linalg.solve(
125:             inertia,
126:             total_moment_body - np.cross(angular_rates, inertia @ angular_rates),
127:         )
128: 
129:         return np.concatenate(
130:             (position_dot, velocity_dot, quaternion_dot, body_rate_dot)
131:         )
132: 
133:     def solve_ode(self, init_roll, init_pitch, init_yaw, t_max):
134:         q = euler_to_quaternion(init_roll, init_pitch, init_yaw)
135:         initial_state = (0, 0, 0, 0, 0, 0, q[0], q[1], q[2], q[3], 0, 0, 0)
136:         absolute_tolerance = np.array(
137:             [1e-6] * 3  # position
138:             + [1e-7] * 3  # velocity
139:             + [1e-9] * 4  # quaternion
140:             + [1e-8] * 3  # angular rates
141:         )
142:         self.state = State(*initial_state)
143: 
144:         solution = solve_ivp(
145:             fun=self.trajectory_ode,
146:             t_span=(0.0, t_max),
147:             y0=initial_state,
148:             method="RK45",
149:             rtol=1e-7,
150:             atol=absolute_tolerance,
151:             max_step=0.01,
152:             dense_output=True,
153:         )
```

### 6dof_hopper/simulation/state.py

SHA-256: `7b8713aecd017a7ff1f0b3ad4e14e1c63c716d1181a6df516d25b7a7d1973b2a`

- Definition `State` at lines 1-75.
- Definition `State.__init__` at lines 2-29.
- Definition `State.update_state` at lines 31-58.
- Definition `State.unpack_state` at lines 60-75.

Full source for manual caller review:

```python
1: class State:
2:     def __init__(self, x, y, z, u, v, w, q0, q1, q2, q3, p, q, r):
3:         self.x = x
4:         self.y = y
5:         self.z = z
6:         self.u = u
7:         self.v = v
8:         self.w = w
9:         self.q0 = q0
10:         self.q1 = q1
11:         self.q2 = q2
12:         self.q3 = q3
13:         self.p = p
14:         self.q = q
15:         self.r = r
16: 
17:         self.x_arr = []
18:         self.y_arr = []
19:         self.z_arr = []
20:         self.u_arr = []
21:         self.v_arr = []
22:         self.w_arr = []
23:         self.q0_arr = []
24:         self.q1_arr = []
25:         self.q2_arr = []
26:         self.q3_arr = []
27:         self.p_arr = []
28:         self.q_arr = []
29:         self.r_arr = []
30: 
31:     def update_state(self, x, y, z, u, v, w, q0, q1, q2, q3, p, q, r):
32:         self.x_arr.append(x)
33:         self.y_arr.append(y)
34:         self.z_arr.append(z)
35:         self.u_arr.append(u)
36:         self.v_arr.append(v)
37:         self.w_arr.append(w)
38:         self.q0_arr.append(q0)
39:         self.q1_arr.append(q1)
40:         self.q2_arr.append(q2)
41:         self.q3_arr.append(q3)
42:         self.p_arr.append(p)
43:         self.q_arr.append(q)
44:         self.r_arr.append(r)
45: 
46:         self.x = x
47:         self.y = y
48:         self.z = z
49:         self.u = u
50:         self.v = v
51:         self.w = w
52:         self.q0 = q0
53:         self.q1 = q1
54:         self.q2 = q2
55:         self.q3 = q3
56:         self.p = p
57:         self.q = q
58:         self.r = r
59: 
60:     def unpack_state(self):
61:         return (
62:             self.x,
63:             self.y,
64:             self.z,
65:             self.u,
66:             self.v,
67:             self.w,
68:             self.q0,
69:             self.q1,
70:             self.q2,
71:             self.q3,
72:             self.p,
73:             self.q,
74:             self.r,
75:         )
```

### 6dof_hopper/test/__init__.py

SHA-256: `d72bcd69d0ed6d706e690574d1dbdedf15ab740d5ce705aad834bd1b91b3d76e`


Full source for manual caller review:

```python
1: """Project test modules."""
```

### 6dof_hopper/test/test_pythrust.py

SHA-256: `a3590eef1c8b2d922a54464d7254205ca046c4af4e42f4bde815a67cec690a0d`

- Definition `results_at_rpm` at lines 71-88.
- Definition `results_at_voltage` at lines 91-122.

Full source for manual caller review:

```python
1: """Minimal PyThrust test: thrust from RPM or commanded voltage.
2: 
3: Run this from the PyThrust repository root after: python -m pip install -e .
4: """
5: 
6: import math
7: from pathlib import Path
8: import sys
9: 
10: PYTHRUST_ROOT = Path(__file__).resolve().parents[1] / "PyThrust"
11: sys.path.insert(0, str(PYTHRUST_ROOT))
12: 
13: from pythrust.battery import FixedVoltageBattery
14: from pythrust.propellers import PropellerDatabase
15: from pythrust.propulsion import MotorSpec, PropellerSpec, PropulsionSolver, SystemSpec
16: 
17: # =============================================================================
18: # EDIT THESE INPUTS
19: # =============================================================================
20: 
21: PROPELLER_ID = "APC_13x6.5E"
22: 
23: MOTOR_KV_RPM_PER_V = 860.0
24: MOTOR_RESISTANCE_OHM = 0.0258
25: MOTOR_NO_LOAD_CURRENT_A = 1.3
26: MOTOR_MAX_CURRENT_A = 65.0
27: 
28: BATTERY_VOLTAGE_V = 14.8
29: SYSTEM_RESISTANCE_OHM = 0.05  # ESC + battery + wires + connectors
30: 
31: AIR_DENSITY_KG_M3 = 1.225
32: AIRSPEED_MPS = 0.0  # 0.0 for a static/hover test
33: 
34: 
35: # =============================================================================
36: # INITIALISE PYTHRUST
37: # =============================================================================
38: 
39: propeller_database = PropellerDatabase()
40: propeller_database.load(
41:     PYTHRUST_ROOT / "data/propellers/apc_202602",
42:     strict=False,
43: )
44: 
45: propeller_data = propeller_database.get(PROPELLER_ID)
46: if propeller_data is None:
47:     raise KeyError(f"Could not find propeller data for {PROPELLER_ID}")
48: 
49: motor = MotorSpec(
50:     kv_rpm_per_v=MOTOR_KV_RPM_PER_V,
51:     resistance_ohm=MOTOR_RESISTANCE_OHM,
52:     no_load_current_a=MOTOR_NO_LOAD_CURRENT_A,
53:     current_max_a=MOTOR_MAX_CURRENT_A,
54: )
55: 
56: battery = FixedVoltageBattery(voltage_v=BATTERY_VOLTAGE_V)
57: electrical_system = SystemSpec(resistance_ohm=SYSTEM_RESISTANCE_OHM)
58: propeller = PropellerSpec(
59:     diameter_m=propeller_data.diameter_m,
60:     pitch_m=propeller_data.pitch_m,
61:     blade_count=propeller_data.metadata.blade_count,
62: )
63: solver = PropulsionSolver()
64: 
65: 
66: # =============================================================================
67: # CALL THESE TWO FUNCTIONS
68: # =============================================================================
69: 
70: 
71: def results_at_rpm(rpm: float) -> dict:
72:     """Return propeller thrust and torque at a prescribed RPM."""
73:     if rpm <= 0.0:
74:         return {"rpm": 0.0, "thrust_n": 0.0, "torque_nm": 0.0}
75: 
76:     n = rpm / 60.0
77:     diameter = propeller.diameter_m
78:     advance_ratio = AIRSPEED_MPS / (n * diameter)
79:     ct, cp = propeller_data.get_coefficients(rpm, advance_ratio)
80: 
81:     thrust_n = ct * AIR_DENSITY_KG_M3 * n**2 * diameter**4
82:     torque_nm = cp * AIR_DENSITY_KG_M3 * n**2 * diameter**5 / (2.0 * math.pi)
83: 
84:     return {
85:         "rpm": rpm,
86:         "thrust_n": thrust_n,
87:         "torque_nm": torque_nm,
88:     }
89: 
90: 
91: def results_at_voltage(commanded_voltage_v: float) -> dict:
92:     """Return equilibrium RPM, thrust and current for an ESC voltage command."""
93:     if not 0.0 <= commanded_voltage_v <= BATTERY_VOLTAGE_V:
94:         raise ValueError(f"Voltage must be between 0 and {BATTERY_VOLTAGE_V} V")
95: 
96:     if commanded_voltage_v == 0.0:
97:         return {
98:             "commanded_voltage_v": 0.0,
99:             "rpm": 0.0,
100:             "thrust_n": 0.0,
101:             "motor_current_a": 0.0,
102:             "feasible": True,
103:         }
104: 
105:     point = solver.solve_operating_point(
106:         motor=motor,
107:         battery=battery,
108:         system=electrical_system,
109:         propeller=propeller,
110:         prop_entry=propeller_data,
111:         rho=AIR_DENSITY_KG_M3,
112:         airspeed_mps=AIRSPEED_MPS,
113:         throttle=commanded_voltage_v / BATTERY_VOLTAGE_V,
114:     )
115: 
116:     return {
117:         "commanded_voltage_v": commanded_voltage_v,
118:         "rpm": point.rpm,
119:         "thrust_n": point.thrust_n,
120:         "motor_current_a": point.motor_current_a,
121:         "feasible": point.is_feasible,
122:     }
123: 
124: 
125: if __name__ == "__main__":
126:     print("At 6000 RPM:", results_at_rpm(6000.0))
127:     print("At 10 V:", results_at_voltage(10.0))
```

### PendulumControlProject/src/gui.py

SHA-256: `e53b845c05025f4039b1c34f02766fc58fb96afd6bb117867467c5e4fc51cecc`

- Definition `TitleBar` at lines 16-107.
- Definition `TitleBar.__init__` at lines 17-20.
- Definition `TitleBar.init_ui` at lines 22-81.
- Definition `TitleBar.minimize` at lines 83-84.
- Definition `TitleBar.maximize` at lines 86-92.
- Definition `TitleBar.close` at lines 94-95.
- Definition `TitleBar.mousePressEvent` at lines 97-100.
- Definition `TitleBar.mouseMoveEvent` at lines 102-104.
- Definition `TitleBar.mouseReleaseEvent` at lines 106-107.
- Definition `PendulumSimulator` at lines 109-669.
- Definition `PendulumSimulator.__init__` at lines 110-114.
- Definition `PendulumSimulator.init_ui` at lines 116-228.
- Definition `PendulumSimulator.apply_stylesheet` at lines 230-266.
- Definition `PendulumSimulator.update_pendulum_type` at lines 268-279.
- Definition `PendulumSimulator.update_time_mode` at lines 281-288.
- Definition `PendulumSimulator.run_simulation` at lines 290-389.
- Definition `PendulumSimulator.stop_simulation` at lines 391-396.
- Definition `PendulumSimulator.prepare_single_pendulum_animation` at lines 398-523.
- Definition `PendulumSimulator.prepare_single_pendulum_animation.init` at lines 454-462.
- Definition `PendulumSimulator.prepare_single_pendulum_animation.update` at lines 464-519.
- Definition `PendulumSimulator.prepare_double_pendulum_animation` at lines 525-662.
- Definition `PendulumSimulator.prepare_double_pendulum_animation.init` at lines 583-592.
- Definition `PendulumSimulator.prepare_double_pendulum_animation.update` at lines 594-658.
- Definition `PendulumSimulator.main` at lines 665-669.

### PendulumControlProject/src/main.py

SHA-256: `016c59131bf7f5d0360616a0b8dbb19033d0524bd610694e116faf968b1d8b30`

- Definition `main` at lines 10-160.

### PendulumControlProject/src/pendulum_model.py

SHA-256: `b2aca9be8e608d8cb701407998ee26a7e6e62a51ed41be93660e3cf4caf39d50`

- Definition `NonlinearPendulum` at lines 6-26.
- Definition `NonlinearPendulum.__init__` at lines 7-11.
- Definition `NonlinearPendulum.equations_of_motion` at lines 13-18.
- Definition `NonlinearPendulum.integrate_step` at lines 20-22.
- Definition `NonlinearPendulum.simulate` at lines 24-26.
- Definition `LinearizedPendulum` at lines 28-48.
- Definition `LinearizedPendulum.__init__` at lines 29-33.
- Definition `LinearizedPendulum.equations_of_motion` at lines 35-40.
- Definition `LinearizedPendulum.integrate_step` at lines 42-44.
- Definition `LinearizedPendulum.simulate` at lines 46-48.
- Definition `NonlinearDoublePendulum` at lines 50-97.
- Definition `NonlinearDoublePendulum.__init__` at lines 51-55.
- Definition `NonlinearDoublePendulum.equations_of_motion` at lines 57-89.
- Definition `NonlinearDoublePendulum.integrate_step` at lines 91-93.
- Definition `NonlinearDoublePendulum.simulate` at lines 95-97.
- Definition `LinearizedDoublePendulum` at lines 99-133.
- Definition `LinearizedDoublePendulum.__init__` at lines 100-104.
- Definition `LinearizedDoublePendulum.equations_of_motion` at lines 106-125.
- Definition `LinearizedDoublePendulum.integrate_step` at lines 127-129.
- Definition `LinearizedDoublePendulum.simulate` at lines 131-133.
- Candidate caller `NonlinearPendulum.integrate_step` -> `solve_ivp` at line 21.
- Candidate caller `NonlinearPendulum.simulate` -> `solve_ivp` at line 25.
- Candidate caller `LinearizedPendulum.integrate_step` -> `solve_ivp` at line 43.
- Candidate caller `LinearizedPendulum.simulate` -> `solve_ivp` at line 47.
- Candidate caller `NonlinearDoublePendulum.integrate_step` -> `solve_ivp` at line 92.
- Candidate caller `NonlinearDoublePendulum.simulate` -> `solve_ivp` at line 96.
- Candidate caller `LinearizedDoublePendulum.integrate_step` -> `solve_ivp` at line 128.
- Candidate caller `LinearizedDoublePendulum.simulate` -> `solve_ivp` at line 132.

Full source for manual caller review:

```python
1: # pendulum_model.py
2: 
3: import numpy as np
4: from scipy.integrate import solve_ivp
5: 
6: class NonlinearPendulum:
7:     def __init__(self, length, mass, gravity=9.81, damping=0.0):
8:         self.length = length
9:         self.mass = mass
10:         self.gravity = gravity
11:         self.damping = damping
12: 
13:     def equations_of_motion(self, t, y):
14:         theta, omega = y
15:         theta_dot = omega
16:         omega_dot = - (self.gravity / self.length) * np.sin(theta) - \
17:                     (self.damping / (self.mass * self.length**2)) * omega
18:         return [theta_dot, omega_dot]
19: 
20:     def integrate_step(self, y_prev, t_span):
21:         sol = solve_ivp(self.equations_of_motion, t_span, y_prev, t_eval=[t_span[1]])
22:         return sol
23: 
24:     def simulate(self, y0, t_span, t_eval):
25:         sol = solve_ivp(self.equations_of_motion, t_span, y0, t_eval=t_eval)
26:         return sol
27: 
28: class LinearizedPendulum:
29:     def __init__(self, length, mass, gravity=9.81, damping=0.0):
30:         self.length = length
31:         self.mass = mass
32:         self.gravity = gravity
33:         self.damping = damping
34: 
35:     def equations_of_motion(self, t, y):
36:         theta, omega = y
37:         theta_dot = omega
38:         omega_dot = - (self.gravity / self.length) * theta - \
39:                     (self.damping / (self.mass * self.length**2)) * omega
40:         return [theta_dot, omega_dot]
41: 
42:     def integrate_step(self, y_prev, t_span):
43:         sol = solve_ivp(self.equations_of_motion, t_span, y_prev, t_eval=[t_span[1]])
44:         return sol
45: 
46:     def simulate(self, y0, t_span, t_eval):
47:         sol = solve_ivp(self.equations_of_motion, t_span, y0, t_eval=t_eval)
48:         return sol
49: 
50: class NonlinearDoublePendulum:
51:     def __init__(self, lengths, masses, gravity=9.81, damping=(0.0, 0.0)):
52:         self.L1, self.L2 = lengths
53:         self.m1, self.m2 = masses
54:         self.gravity = gravity
55:         self.damping1, self.damping2 = damping
56: 
57:     def equations_of_motion(self, t, y):
58:         theta1, omega1, theta2, omega2 = y
59: 
60:         m1 = self.m1
61:         m2 = self.m2
62:         L1 = self.L1
63:         L2 = self.L2
64:         g = self.gravity
65:         b1 = self.damping1
66:         b2 = self.damping2
67: 
68:         delta = theta2 - theta1
69: 
70:         denom1 = (m1 + m2) * L1 - m2 * L1 * np.cos(delta) ** 2
71:         denom2 = (L2 / L1) * denom1
72: 
73:         theta1_dot = omega1
74:         theta2_dot = omega2
75: 
76:         omega1_num = m2 * L1 * omega1 ** 2 * np.sin(delta) * np.cos(delta) + \
77:                      m2 * g * np.sin(theta2) * np.cos(delta) + \
78:                      m2 * L2 * omega2 ** 2 * np.sin(delta) - \
79:                      (m1 + m2) * g * np.sin(theta1) - b1 * omega1
80: 
81:         omega1_dot = omega1_num / denom1
82: 
83:         omega2_num = -m2 * L2 * omega2 ** 2 * np.sin(delta) * np.cos(delta) + \
84:                      (m1 + m2) * (g * np.sin(theta1) * np.cos(delta) - \
85:                      L1 * omega1 ** 2 * np.sin(delta) - g * np.sin(theta2)) - b2 * omega2
86: 
87:         omega2_dot = omega2_num / denom2
88: 
89:         return [theta1_dot, omega1_dot, theta2_dot, omega2_dot]
90: 
91:     def integrate_step(self, y_prev, t_span):
92:         sol = solve_ivp(self.equations_of_motion, t_span, y_prev, t_eval=[t_span[1]], max_step=0.01)
93:         return sol
94: 
95:     def simulate(self, y0, t_span, t_eval):
96:         sol = solve_ivp(self.equations_of_motion, t_span, y0, t_eval=t_eval, max_step=0.01)
97:         return sol
98: 
99: class LinearizedDoublePendulum:
100:     def __init__(self, lengths, masses, gravity=9.81, damping=(0.0, 0.0)):
101:         self.L1, self.L2 = lengths
102:         self.m1, self.m2 = masses
103:         self.gravity = gravity
104:         self.damping1, self.damping2 = damping
105: 
106:     def equations_of_motion(self, t, y):
107:         theta1, omega1, theta2, omega2 = y
108: 
109:         m1 = self.m1
110:         m2 = self.m2
111:         L1 = self.L1
112:         L2 = self.L2
113:         g = self.gravity
114:         b1 = self.damping1
115:         b2 = self.damping2
116: 
117:         theta1_dot = omega1
118:         theta2_dot = omega2
119: 
120:         delta = theta2 - theta1
121: 
122:         omega1_dot = (- (m1 + m2) * g * theta1 + m2 * g * theta2 - b1 * omega1) / ((m1 + m2) * L1)
123:         omega2_dot = (- m2 * g * theta2 + m2 * g * theta1 - b2 * omega2) / (m2 * L2)
124: 
125:         return [theta1_dot, omega1_dot, theta2_dot, omega2_dot]
126: 
127:     def integrate_step(self, y_prev, t_span):
128:         sol = solve_ivp(self.equations_of_motion, t_span, y_prev, t_eval=[t_span[1]])
129:         return sol
130: 
131:     def simulate(self, y0, t_span, t_eval):
132:         sol = solve_ivp(self.equations_of_motion, t_span, y0, t_eval=t_eval)
133:         return sol
```

## Limitations

- Call candidates require manual review; attribute names are not resolved to runtime types.
- Dynamic dispatch, generated code and callers outside these roots are not excluded.
- Symlinks are listed but not followed; any relevant target needs a separate supplied-source review.
- Hash equality measures preservation during this audit only; retain this baseline for post-repair comparison.
- Binary/data files and excluded directories are outside this source-manifest scope.
