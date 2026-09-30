"""Preliminary static coaxial screening; SI throughout except RPM.

Uses PyThrust PropellerEntry coefficient interpolation without modifying its
source. Loss factors are sensitivity assumptions, not validated coaxial data.
Battery/ESC envelopes are hypothetical until supported by supplier evidence.
No mission dynamics, thermal model, or hardware acceptance is implied.
"""
import math
from scipy.optimize import brentq


class OutsideEnvelope(ValueError):
    pass


class CoaxialModel:
    def __init__(self, motor, prop, config, thrust_factors, torque_factors):
        self.motor = motor
        self.prop = prop
        self.config = config
        self.tf = tuple(thrust_factors)
        self.qf = tuple(torque_factors)
        self.rpm_lo = min(prop.rpm_levels)
        self.rpm_hi = max(prop.rpm_levels)
        if min(self.tf + self.qf) <= 0:
            raise ValueError('Loss factors must be positive')
        if not all(any(p.j == 0 for p in band)
                   for band in prop.data_by_rpm.values()):
            raise OutsideEnvelope('Static data missing from an RPM band')
        for k in range(2):
            values = [self.rotor(rpm, k)['torque_nm'] for rpm in prop.rpm_levels]
            if any(b <= a for a, b in zip(values, values[1:])):
                raise OutsideEnvelope('Nonmonotonic static torque; requires separate solver')
        self.qlo = max(self.rotor(self.rpm_lo, k)['torque_nm'] for k in range(2))
        self.qhi = min(self.rotor(self.rpm_hi, k)['torque_nm'] for k in range(2))
        if self.qhi <= self.qlo:
            raise OutsideEnvelope('No common torque domain')

    def rotor(self, rpm, index):
        if not self.rpm_lo <= rpm <= self.rpm_hi:
            raise OutsideEnvelope('RPM extrapolation prohibited')
        ct, cp = self.prop.get_coefficients(rpm, 0.0)
        if ct <= 0 or cp <= 0:
            raise OutsideEnvelope('Nonpositive static coefficient')
        n = rpm / 60.0
        d = self.prop.diameter_m
        rho = self.config['density_kg_m3']
        thrust = self.tf[index] * ct * rho * n*n * d**4
        torque = self.qf[index] * cp * rho * n*n * d**5 / (2*math.pi)
        spec = self.motor.to_spec()
        kt = 30 / (math.pi * spec.kv_rpm_per_v * spec.torque_constant_kv_ratio)
        current = torque / kt + spec.get_no_load_current(rpm)
        back_emf = rpm / spec.kv_rpm_per_v * (1 + spec.magnetic_lag_tau*rpm*math.pi/30)
        voltage = back_emf + current * spec.get_winding_resistance(current)
        branch_voltage = voltage + current*self.config['electrical']['per_branch_esc_wire_resistance_ohm']
        return dict(rpm=rpm, thrust_n=thrust, torque_nm=torque,
                    shaft_power_w=torque*rpm*math.pi/30,
                    motor_current_a=current, motor_voltage_v=voltage,
                    motor_power_w=voltage*current,
                    branch_voltage_v=branch_voltage,
                    branch_input_power_w=branch_voltage*current/self.config['electrical']['esc_efficiency'])

    def at_torque(self, torque):
        result = []
        for k in range(2):
            rpm = brentq(lambda r: self.rotor(r, k)['torque_nm']-torque,
                         self.rpm_lo, self.rpm_hi, xtol=1e-7)
            result.append(self.rotor(rpm, k))
        return result

    def operating_point(self, vertical_thrust_n, battery, tilt_deg=0):
        cosine = math.cos(math.radians(tilt_deg))
        if cosine <= 0 or vertical_thrust_n <= 0:
            raise ValueError('Positive upward thrust required')
        target = vertical_thrust_n / cosine
        def residual(q):
            return sum(r['thrust_n'] for r in self.at_torque(q))-target
        if residual(self.qlo) > 0 or residual(self.qhi) < 0:
            raise OutsideEnvelope('Required thrust outside static RPM domain')
        torque = brentq(residual, self.qlo, self.qhi, xtol=1e-10)
        rotors = self.at_torque(torque)
        cfg = self.config
        bc = cfg['battery_common']
        lim = cfg['screening_limits']
        voc = battery['cells_series']*bc['end_of_mission_ocv_cell_v']
        power = sum(r['branch_input_power_w'] for r in rotors)+cfg['mission']['auxiliary_power_w']
        resistance = battery['pack_resistance_ohm']
        discriminant = voc*voc-4*resistance*power
        if discriminant <= 0:
            raise OutsideEnvelope('No stable constant-power battery operating point')
        terminal_v = (voc+math.sqrt(discriminant))/2
        pack_current = power/terminal_v
        for r in rotors:
            r['duty'] = r['branch_voltage_v']/terminal_v
            r['esc_input_current_a'] = r['branch_input_power_w']/terminal_v
        checks = {
            'duty_available': max(r['duty'] for r in rotors) <= 1,
            'motor_current_envelope': max(r['motor_current_a'] for r in rotors) <= self.motor.max_current*lim['motor_catalogue_current_derating'],
            'motor_power_envelope': max(r['motor_power_w'] for r in rotors) <= self.motor.max_power*lim['motor_catalogue_power_derating'],
            'esc_current_envelope': max(r['motor_current_a'] for r in rotors) <= lim['esc_continuous_current_a_assumed']*lim['esc_current_derating'],
            'esc_voltage_envelope': battery['cells_series']*bc['full_cell_voltage_v'] <= lim['esc_maximum_voltage_v_assumed'],
            'battery_current_envelope': pack_current <= battery['continuous_current_a']*lim['battery_current_derating'],
            'battery_loaded_voltage': terminal_v >= battery['cells_series']*bc['minimum_loaded_cell_voltage_v']}
        return dict(rotors=rotors, vertical_thrust_n=sum(r['thrust_n'] for r in rotors)*cosine,
                    tilt_deg=tilt_deg, reaction_torque_nm=sum(s*r['torque_nm'] for s,r in zip(cfg['coaxial']['reaction_torque_signs'],rotors)),
                    battery_voltage_v=terminal_v, battery_current_a=pack_current,
                    delivered_power_w=power, battery_internal_loss_w=pack_current**2*resistance,
                    assumed_envelope_checks=checks, within_assumed_envelope=all(checks.values()))


def evaluate_candidate(model, battery, added_mass_kg=0):
    cfg = model.config
    mission = cfg['mission']
    limits = cfg['screening_limits']
    bc = cfg['battery_common']
    mass = sum(x['quantity']*x['unit_mass_kg'] for x in cfg['vehicle_allowances'])
    mass += cfg['motor_allowance']['quantity']*model.motor.weight_g/1000 + battery['mass_kg'] + added_mass_kg + cfg['payload_kg']
    cost = sum(x['quantity']*x['unit_cost_aud'] for x in cfg['vehicle_allowances'])
    cost += cfg['motor_allowance']['quantity']*cfg['motor_allowance']['unit_cost_aud'] + battery['cost_aud'] + cfg['uncertainty']['additional_cost_aud']
    weight = mass*cfg['gravity_m_s2']
    hover = model.operating_point(weight, battery)
    climb = model.operating_point(weight*mission['climb_thrust_weight_ratio'], battery)
    reserve = model.operating_point(weight*limits['minimum_thrust_weight_ratio'], battery, limits['maximum_tilt_deg'])
    energy_hover = hover['delivered_power_w']*mission['hover_s']/3600
    energy_climb = (climb['delivered_power_w']*mission['climb_s']+weight*mission['height_m']/0.60)/3600
    energy_landing = hover['delivered_power_w']*mission['landing_power_hover_multiplier']*mission['landing_s']/3600
    energy = (energy_hover+energy_climb+energy_landing)*(1+mission['additional_energy_allowance_fraction'])
    # Conservative delivered-energy envelope: every usable Ah delivered at
    # the configured minimum permissible loaded voltage. Not a cell curve.
    usable_wh = battery['capacity_ah']*bc['usable_capacity_fraction']*battery['cells_series']*bc['minimum_loaded_cell_voltage_v']
    allowed_wh = usable_wh*(1-bc['required_unused_fraction_of_usable_energy'])
    checks = dict(cost_estimate_below_ceiling=cost < cfg['cost_ceiling_exclusive'],
                  hover_duty=max(r['duty'] for r in hover['rotors']) <= limits['maximum_hover_duty'],
                  hover_envelope=hover['within_assumed_envelope'],
                  climb_envelope=climb['within_assumed_envelope'],
                  simultaneous_tilt_thrust_reserve=reserve['within_assumed_envelope'],
                  energy_with_reserve=energy <= allowed_wh)
    return dict(motor_id=model.motor.id, propeller_id=model.prop.metadata.id,
                battery_id=battery['id'], mass_kg=mass, estimated_cost_aud=cost,
                cost_margin_aud=cfg['cost_ceiling_exclusive']-cost,
                added_mass_kg=added_mass_kg, thrust_factors=model.tf, torque_factors=model.qf,
                hover=hover, climb=climb, reserve=reserve,
                phase_energy_wh=dict(hover=energy_hover, climb=energy_climb, landing=energy_landing),
                mission_energy_with_allowance_wh=energy, usable_energy_envelope_wh=usable_wh,
                permitted_mission_energy_wh=allowed_wh, energy_margin_wh=allowed_wh-energy,
                screening_checks=checks, screening_feasible=all(checks.values()),
                procurement_ready=False, physical_validation='unperformed')
