from propulsion.propulsion import Propulsion


class Propellor(Propulsion):
    def __init__(
        self,
        type,
        motor_kv_rpm_per_v,
        motor_resistance_ohm,
        motor_no_load_current,
        motor_max_current,
        battery_voltage_v,
        system_resistance_ohm,
    ):
        super().__init__(type)
