"""Artifact-bound PDR-R12 propulsion and plant-interface checks.

Authorization: 66c7448f443f44ac9a016a1b384593a2 r1.
Audits: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 r1 and
PDR-R12-PLANT-CALLER-RECONCILIATION-02 r1.
Frames: f046cc4fe5294a6f9a61027529056f61 r1.
Gimbal: 28e10be57d6548a3aa5be06c96f6d0d0 r1.

New caller audit: uses the inspected r12 constructors, actual AssemblyKinematics,
Propellor geometry/evaluate/hub-velocity interfaces, resolve_applied_loads,
LaggedActuators.evaluate and Simulation.evaluate. No existing source changes.
Independent expectations use elementary matrices, scalar paired-map equations,
component cross products, finite differences and angular-momentum residuals.
All geometry/performance numbers are explicitly synthetic fixture inputs.

After publication, run through verify_command, repository='6dof_hopper',
workdir='.', command=['python','-B',
 'software/pdr_r12_plant/verify_propulsion_interfaces_r12_01.py'].
Include this checker, configuration, fixture provider and all eight plant-module
artifact Refs. PINNED contains FILE hashes, not Guacamole Ref hashes.
Stdout contains only VerificationResult JSON; measurements go to stderr.
No files, controller memory, trajectory or energy integrals are written.
Passing individual checks cannot establish physical or mission acceptance.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
PINNED = {
    'analytical_fixture_config_r12_01.json': '397133a2ab342cf35a29c4758adcb0e3f52682cc96dc85dfd0710323247b54c5',
    'analytical_fixture_models_r12_01.py': '25ae16b4a9fbfe42a1e083f952316a8d26cc69559fbef11f62c871f997d0e517',
    'repaired_hopper_r12/helpers/math.py': '281a5578b6d33c45578350429cb30ead28ba6a378c571c2c6929c60819ceecfb',
    'repaired_hopper_r12/simulation/state.py': 'b62a1a4fcc70a4a88e07f77996e955a64184891ce614957c85ccb7d63e90f294',
    'repaired_hopper_r12/chassis/hopper.py': 'f2b6e4b54634220105655e994e3ff5c78e84c60084879696a25ef39fdc29ff05',
    'repaired_hopper_r12/propulsion/propulsion.py': 'd860528b277893bbfe59527b7fcc2017955cc66681d3994fb66744a8006271de',
    'repaired_hopper_r12/propulsion/propeller.py': 'ce7be67ceae3866ecf402ee03b7812c3ea1e39c216ca5d412322af53d586ae3b',
    'repaired_hopper_r12/propulsion/actuators.py': 'bacfd1457ea3d24ae82d4868f3418b46c967fc2442d83d36e96973467645be78',
    'repaired_hopper_r12/simulation/environment.py': 'ba795b5d1d5344a1ecf5b2b5cc122255234d5ff394fb0dc41ee3366196aac03c',
    'repaired_hopper_r12/simulation/simulation.py': 'a186c50ab7c5500e7da14bb5c98a5c2772ff97d63645558be3cfdc3b6e5ca1a8',
}
CHECKS = {}


def diagnostic(value):
    print(json.dumps(value, allow_nan=False, sort_keys=True), file=sys.stderr)


def check(name, condition, details=None):
    if name in CHECKS:
        raise ValueError('Duplicate check: '+name)
    CHECKS[name] = bool(condition)
    if details is not None:
        diagnostic({'check': name, 'details': details})


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def near(name, actual, expected, tolerance, unit):
    import numpy as np
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    tolerance = float(tolerance)
    require(np.isfinite(tolerance) and tolerance >= 0, 'Invalid tolerance')
    valid = a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all()
    if not valid:
        check(name, False, {'shape_or_finiteness_failure': True, 'unit': unit})
        return
    error = float(np.max(np.abs(a-b))) if a.size else 0.0
    check(name, error <= tolerance, {'max_absolute_error': error,
          'tolerance': tolerance, 'unit': unit,
          'actual': a.tolist(), 'expected': b.tolist()})


def rejects(name, operation, expected=ValueError):
    try:
        operation()
    except expected as error:
        check(name, True, {'deliberate_negative_fixture': True,
              'exception': type(error).__name__, 'message': str(error)})
    except Exception:
        check(name, False, {'unexpected_exception': True})
        raise
    else:
        check(name, False, {'expected_exception_not_raised': True})


def group(name, operation):
    try:
        operation()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        check(name+'.completed', False)
    else:
        check(name+'.completed', True)


def hashes():
    result = {}
    for relative in list(PINNED)+[Path(__file__).name]:
        path = ROOT/relative
        require(ROOT in path.resolve().parents and not path.is_symlink(),
                'Unexpected artifact path: '+relative)
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def run():
    import numpy as np
    import analytical_fixture_models_r12_01 as fixtures
    from repaired_hopper_r12.chassis.hopper import AssemblyKinematics, MassProperties
    from repaired_hopper_r12.propulsion.actuators import ActuatorState, HeldCommand
    from repaired_hopper_r12.propulsion.propeller import CoaxialGeometry
    from repaired_hopper_r12.propulsion.propulsion import AppliedLoad, resolve_applied_loads
    from repaired_hopper_r12.simulation.simulation import ModelDomainError
    from repaired_hopper_r12.simulation.state import State

    cfg = fixtures.load_fixture_config(ROOT/'analytical_fixture_config_r12_01.json')
    saved_cfg = deepcopy(cfg)
    tv, tol = cfg['test_vectors'], cfg['analytical_test_tolerances']
    initial, initial_actuator = fixtures.initial_snapshots(cfg)
    base = fixtures.build_fixture(cfg, initial_state=initial,
                                  initial_actuator_state=initial_actuator)
    time = tv['nonzero_initialization']['time_start_s']
    saturated = HeldCommand(
        tv['saturated_command']['rotor_speed_magnitude_rad_s'],
        tv['saturated_command']['gimbal_rad'])

    def cross(a, b):
        return np.array([a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
                         a[0]*b[1]-a[1]*b[0]])

    def axis(j, angle):
        c, s = np.cos(angle), np.sin(angle)
        if j == 0:
            return np.array([[1,0,0],[0,c,-s],[0,s,c]], dtype=float)
        if j == 1:
            return np.array([[c,0,s],[0,1,0],[-s,0,c]], dtype=float)
        return np.array([[c,-s,0],[s,c,0],[0,0,1]], dtype=float)

    init = tv['nonzero_initialization']
    R = axis(2,init['yaw_rad']) @ axis(1,init['pitch_rad']) @ axis(0,init['roll_rad'])

    def positions(geometry, angles):
        a, b = angles
        A, M = axis(0,a), axis(0,a) @ axis(1,b)
        outer = np.array(geometry['outer_origin_B0_m'])
        inner = outer+A @ np.array(geometry['outer_to_inner_outer_m'])
        points = np.array([inner+M @ np.array(v)
                          for v in geometry['hub_offsets_from_inner_M_m']])
        return points, inner, M

    def oracle(config, speeds, angles):
        p = config['synthetic_paired_map']
        voltage = config['environment']['bus_voltage_V']
        thrust, drag, winding, branch = [], [], [], []
        for i in range(2):
            denominator = 1+p['cross_interference_coefficient'][i]*(speeds[1-i]/p['reference_speed_rad_s'])**2
            t = p['thrust_coefficient_N_s2_rad2'][i]*speeds[i]**2/denominator
            q = p['drag_torque_coefficient_N_m_s2_rad2'][i]*speeds[i]**2/denominator
            thrust.append(t)
            drag.append(q)
            winding.append(p['idle_current_A'][i]+q/p['motor_torque_constant_N_m_A'][i])
            branch.append(p['idle_current_A'][i]+q*speeds[i]/(p['synthetic_efficiency'][i]*voltage))
        points, unused, M = positions(config['geometry'], angles)
        forces = np.array([-t*M[:,2] for t in thrust])
        couples = np.array([-s*q*M[:,2] for s,q in zip(config['geometry']['spin_signs'],drag)])
        cg = np.array(config['mass_properties']['cg_B0_m'])
        moment = sum((cross(point-cg,force)+couple
                      for point,force,couple in zip(points,forces,couples)), np.zeros(3))
        return dict(points=points, forces=forces, couples=couples,
                    force=forces.sum(axis=0), moment=moment, thrust=thrust,
                    drag=drag, winding=winding, branch=branch)

    rest = State(position_G_L_m=tv['trim']['position_G_L_m'],
                 velocity_G_L_m_s=[0,0,0], q_LB=[1,0,0,0], omega_B_rad_s=[0,0,0])

    def evaluated(config, speeds, angles):
        states = ActuatorState(speeds, angles, angles)
        model = fixtures.build_fixture(config, initial_state=rest, initial_actuator_state=states)
        return model.evaluate(time_s=time, vector=model.initial_vector(),
                              command=HeldCommand(speeds,angles))

    def compare_load_case(name, config, speeds, angles):
        e, o = evaluated(config,speeds,angles), oracle(config,speeds,angles)
        loads, performance = e.propulsion.rotor_loads, e.propulsion.performance
        near(name+'.points', [x.application_point_B0_m for x in loads], o['points'],
             tol['kinematic_position_error_m'], 'm')
        near(name+'.rotor_forces', [x.force_B_N for x in loads], o['forces'], tol['force_error_N'], 'N')
        near(name+'.external_aerodynamic_couples', [x.free_moment_B_N_m for x in loads],
             o['couples'], tol['moment_error_N_m'], 'N m')
        near(name+'.resolved_force', e.external_wrench.force_B_N, o['force'], tol['force_error_N'], 'N')
        near(name+'.resolved_moment', e.external_wrench.moment_B_G_N_m, o['moment'], tol['moment_error_N_m'], 'N m')
        near(name+'.paired_thrust', performance.thrust_N, o['thrust'], tol['force_error_N'], 'N')
        near(name+'.paired_drag', performance.aerodynamic_drag_torque_N_m, o['drag'], tol['moment_error_N_m'], 'N m')
        near(name+'.winding_current', performance.motor_current_A, o['winding'], tol['bus_current_error_A'], 'A')
        near(name+'.branch_current', performance.rotor_bus_current_A, o['branch'], tol['bus_current_error_A'], 'A')
        current = sum(o['branch'])+config['environment']['auxiliary_bus_current_A']
        near(name+'.auxiliary_counted_once', e.total_bus_current_A, current, tol['bus_current_error_A'], 'A')
        near(name+'.shared_bus_power', e.total_bus_power_W,
             current*config['environment']['bus_voltage_V'], tol['bus_power_error_W'], 'W')
        return e, o

    def bottom_signs():
        geometry = cfg['geometry']
        h = geometry['outer_origin_B0_m'][2]-cfg['mass_properties']['cg_B0_m'][2]
        require(h > 0 and np.array_equal(geometry['outer_to_inner_outer_m'],[0,0,0]),
                'Simplified sign fixture requires positive-down coincident pivot')
        require(np.array_equal(np.array(geometry['hub_offsets_from_inner_M_m'])[:,:2],np.zeros((2,2)))
                and np.array_equal(np.array(geometry['outer_origin_B0_m'])[:2],np.zeros(2))
                and np.array_equal(cfg['mass_properties']['cg_B0_m'],[0,0,0]),
                'Simplified sign fixture requires centred collinear geometry')
        v = tv['bottom_pivot_effectiveness']
        speeds = v['rotor_speed_magnitude_rad_s']
        total = sum(oracle(cfg,speeds,[0,0])['thrust'])
        for i, angles in enumerate([[0,0]]+v['finite_angle_pairs_rad']):
            a,b = angles
            e, unused = compare_load_case('bottom.'+str(i),cfg,speeds,angles)
            expected_force = [-total*np.sin(b),total*np.sin(a)*np.cos(b),-total*np.cos(a)*np.cos(b)]
            expected_moment = [-h*total*np.sin(a)*np.cos(b),-h*total*np.sin(b),0]
            near('bottom.closed_force_'+str(i),e.external_wrench.force_B_N,expected_force,tol['force_error_N'],'N')
            near('bottom.closed_moment_'+str(i),e.external_wrench.moment_B_G_N_m,expected_moment,tol['moment_error_N_m'],'N m')
        step = v['finite_difference_angle_step_rad']
        require(step > 0, 'Positive angular difference step required')
        for j in range(2):
            angles = np.zeros(2)
            angles[j] = step
            plus = np.array(evaluated(cfg,speeds,angles).external_wrench.moment_B_G_N_m)
            minus = np.array(evaluated(cfg,speeds,-angles).external_wrench.moment_B_G_N_m)
            derivative = (plus-minus)/(2*step)
            expected = np.zeros(3)
            expected[j] = -h*total
            near('bottom.effectiveness_'+str(j),derivative,expected,tol['moment_derivative_error_N_m_rad'],'N m/rad')
            check('bottom.negative_effectiveness_'+str(j),derivative[j] < 0)

    def torque_cases():
        v = tv['differential_aerodynamic_torque']
        for i,speeds in enumerate(v['rotor_speed_cases_rad_s']):
            e,o = compare_load_case('torque.'+str(i),cfg,speeds,v['gimbal_rad'])
            axial = -sum(s*q for s,q in zip(cfg['geometry']['spin_signs'],o['drag']))
            if i == 0:
                near('torque.equal_Q_cancel',sum((np.array(x.free_moment_B_N_m) for x in e.propulsion.rotor_loads),np.zeros(3)),
                     np.zeros(3),tol['moment_error_N_m'],'N m')
            diagnostic({'case':'torque.'+str(i),'module_axial_aerodynamic_couple_N_m':axial})
        changed = deepcopy(cfg)
        changed['synthetic_paired_map']['drag_torque_coefficient_N_m_s2_rad2'][1] *= v['lower_drag_coefficient_multiplier_for_unequal_map_case']
        e,o = compare_load_case('torque.unequal_Q_equal_speed',changed,v['rotor_speed_cases_rad_s'][0],v['gimbal_rad'])
        check('torque.opposite_spin_does_not_force_cancellation',np.linalg.norm(o['couples'].sum(axis=0)) > tol['moment_error_N_m'])
        diagnostic({'explicit_fixture_override':{'lower_drag_coefficient_multiplier':v['lower_drag_coefficient_multiplier_for_unequal_map_case']}})

    def kinematics():
        v, geometry = tv['offset_kinematics'], tv['separated_origin_geometry']
        geo = CoaxialGeometry(**geometry)
        kin = AssemblyKinematics(gimbal_rad=v['gimbal_rad'],gimbal_rate_rad_s=v['gimbal_rate_rad_s'],
              gimbal_acceleration_rad_s2=v['gimbal_acceleration_rad_s2'],
              rotor_signed_speed_rad_s=np.array(geometry['spin_signs'])*np.array(init['rotor_speed_magnitude_rad_s']),
              rotor_signed_acceleration_rad_s2=[0,0])
        mass = replace(MassProperties(**cfg['mass_properties']),cg_B0_m=v['cg_B0_m'],
                       cg_rate_B0_m_s=v['cg_rate_B0_m_s'],dynamics_mode=v['dynamics_mode'])
        adapter = replace(base.propulsion,geometry=geo)
        p0, inner, M = positions(geometry,v['gimbal_rad'])
        near('geometry.separated_origins',geo.joint_origins_B0_m(kin),
             [geometry['outer_origin_B0_m'],inner],tol['kinematic_position_error_m'],'m')
        near('geometry.actual_hubs',geo.application_points_B0_m(kin),p0,tol['kinematic_position_error_m'],'m')
        rates = geo.application_point_rates_B0_m_s(kin)
        air_velocity = adapter.hub_velocities_relative_air_M_m_s(state=initial,mass_properties=mass,
                       kinematics=kin,wind_at_hubs_L_m_s=v['wind_at_hubs_L_m_s'])
        omega = initial.omega_B_rad_s
        magnitude = np.linalg.norm(omega)
        def point_at(dt, local):
            angles = np.array(v['gimbal_rad'])+dt*np.array(v['gimbal_rate_rad_s'])+0.5*dt*dt*np.array(v['gimbal_acceleration_rad_s2'])
            points = positions(geometry,angles)[0]
            if not local:
                return points
            if magnitude == 0:
                increment = np.eye(3)
            else:
                u = omega/magnitude
                K = np.array([[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]])
                increment = np.eye(3)+np.sin(magnitude*dt)*K+(1-np.cos(magnitude*dt))*(K@K)
            cg = np.array(v['cg_B0_m'])+dt*np.array(v['cg_rate_B0_m_s'])
            return initial.position_G_L_m+dt*initial.velocity_G_L_m_s+(R@increment@(points-cg).T).T
        for i,dt in enumerate([v['finite_difference_time_step_s'],v['finite_difference_time_step_s']/2]):
            require(dt > 0,'Positive difference step required')
            near('geometry.component_rates_'+str(i),rates,(point_at(dt,False)-point_at(-dt,False))/(2*dt),
                 tol['kinematic_velocity_error_m_s'],'m/s')
            velocity = (point_at(dt,True)-point_at(-dt,True))/(2*dt)
            expected = (M.T@R.T@(velocity-np.array(v['wind_at_hubs_L_m_s'])).T).T
            near('geometry.air_relative_hub_velocity_'+str(i),air_velocity,expected,tol['kinematic_velocity_error_m_s'],'m/s')

    def load_accounting():
        load = AppliedLoad(**tv['external_point_load'])
        mass = replace(MassProperties(**cfg['mass_properties']),cg_B0_m=tv['offset_kinematics']['cg_B0_m'])
        actual = resolve_applied_loads(loads=[load],mass_properties=mass,provenance='Instantaneous algebraic shift fixture')
        force = np.array(load.force_B_N)
        expected = cross(np.array(load.application_point_B0_m)-np.array(mass.cg_B0_m),force)+load.free_moment_B_N_m
        near('wrench.single_CG_shift',actual.moment_B_G_N_m,expected,tol['moment_error_N_m'],'N m')
        original = resolve_applied_loads(loads=[load],mass_properties=MassProperties(**cfg['mass_properties']),provenance='Reference shift fixture')
        near('wrench.reference_change',np.array(actual.moment_B_G_N_m)-np.array(original.moment_B_G_N_m),
             -cross(np.array(mass.cg_B0_m),force),tol['moment_error_N_m'],'N m')
        changed = deepcopy(cfg)
        changed['geometry'] = deepcopy(tv['separated_origin_geometry'])
        changed['environment']['additional_external_loads'] = [deepcopy(tv['external_point_load'])]
        model = fixtures.build_fixture(changed,initial_state=initial,initial_actuator_state=initial_actuator)
        e = model.evaluate(time_s=time,vector=model.initial_vector(),command=saturated)
        o = oracle(changed,init['rotor_speed_magnitude_rad_s'],init['actual_gimbal_rad'])
        total_force = o['force']+force
        total_moment = o['moment']+cross(np.array(load.application_point_B0_m),force)+load.free_moment_B_N_m
        near('plant.actual_not_commanded_rotor_force',e.external_wrench.force_B_N,total_force,tol['force_error_N'],'N')
        near('plant.external_moments_once',e.external_wrench.moment_B_G_N_m,total_moment,tol['moment_error_N_m'],'N m')
        acceleration = R@total_force/changed['mass_properties']['mass_kg']+[0,0,changed['environment']['gravity_m_s2']]
        near('plant.NED_acceleration_no_body_transport',e.derivative[3:6],acceleration,tol['algebraic_acceleration_error_m_s2'],'m/s^2')
        near('plant.position_derivative',e.derivative[:3],initial.velocity_G_L_m_s,tol['kinematic_velocity_error_m_s'],'m/s')
        I, omega = np.array(changed['mass_properties']['inertia_B_G_kg_m2']),initial.omega_B_rad_s
        near('plant.full_inertia_residual',I@np.array(e.derivative[10:13])+cross(omega,I@omega)-total_moment,
             np.zeros(3),tol['angular_momentum_residual_N_m'],'N m')
        zero = evaluated(cfg,[0,0],[0,0])
        near('plant.gravity_positive_down',zero.derivative[3:6],[0,0,cfg['environment']['gravity_m_s2']],tol['algebraic_acceleration_error_m_s2'],'m/s^2')

    def limiter():
        params = base.actuator_model.parameters
        e = base.actuator_model.evaluate(time_s=time,state=initial_actuator,command=saturated)
        bounded = e.bounded_command
        expected_speed = np.minimum(np.maximum(saturated.rotor_speed_magnitude_rad_s,0),params.rotor_speed_limit_rad_s)
        near('actuator.speed_command_limits',bounded.rotor_speed_magnitude_rad_s,expected_speed,0,'rad/s')
        expected_rate = (expected_speed-np.array(initial_actuator.rotor_speed_magnitude_rad_s))/params.motor_time_constant_s
        expected_rate = np.minimum(np.maximum(expected_rate,-np.array(params.rotor_acceleration_limit_rad_s2)),params.rotor_acceleration_limit_rad_s2)
        near('actuator.instantaneous_motor_lag_and_acceleration_cap',e.derivative[:2],expected_rate,tol['motor_speed_error_rad_s'],'rad/s^2')
        angles = np.array(bounded.gimbal_rad)
        clipped = np.minimum(np.maximum(saturated.gimbal_rad,params.joint_lower_rad),params.joint_upper_rad)
        epsilon = tol['limit_roundoff_allowance']
        check('actuator.joint_domain',np.all(angles >= np.array(params.joint_lower_rad)-epsilon) and np.all(angles <= np.array(params.joint_upper_rad)+epsilon))
        cosine = np.cos(angles[0])*np.cos(angles[1])
        check('actuator.resultant_cone_domain',cosine >= np.cos(params.resultant_cone_limit_rad)-epsilon)
        if np.cos(clipped[0])*np.cos(clipped[1]) < np.cos(params.resultant_cone_limit_rad):
            near('actuator.active_cone_boundary',cosine,np.cos(params.resultant_cone_limit_rad),epsilon,'1')
            near('actuator.common_radial_reduction',angles[0]*clipped[1]-angles[1]*clipped[0],0,epsilon,'rad^2')
            check('actuator.no_radial_expansion',np.linalg.norm(angles) <= np.linalg.norm(clipped)+epsilon)
        else:
            near('actuator.inactive_cone_preserves_joint_clip',angles,clipped,epsilon,'rad')
        requested = saturated.rotor_speed_magnitude_rad_s+saturated.gimbal_rad
        limited = bounded.rotor_speed_magnitude_rad_s+bounded.gimbal_rad
        check('actuator.limiting_flags',e.command_limited == tuple(a != b for a,b in zip(requested,limited)))
        near('actuator.actual_angles_not_commands',e.kinematics.gimbal_rad,initial_actuator.actual_gimbal_rad,0,'rad')

    def policies():
        vector = base.initial_vector()
        evaluate = lambda model: model.evaluate(time_s=time,vector=vector,command=saturated)
        e = evaluate(base)
        rejects('policy.unknown_domains_strict',lambda:evaluate(replace(base,domain_policy='require_reported_admissible')),ModelDomainError)
        checks = base.propulsion.performance_map.domain_checks
        bad_map = replace(base.propulsion.performance_map,domain_checks=tuple((n,False if n=='motor_current' else f) for n,f in checks))
        rejects('policy.known_violation_even_fixture',lambda:evaluate(replace(base,propulsion=replace(base.propulsion,performance_map=bad_map))),ModelDomainError)
        good_map = replace(base.propulsion.performance_map,domain_checks=tuple((n,True) for n,f in checks))
        good = evaluate(replace(base,propulsion=replace(base.propulsion,performance_map=good_map),domain_policy='require_reported_admissible'))
        check('policy.injected_true_flags_only',good.propulsion.performance.reported_admissibility is True,
              {'scope':'Deliberately injected policy fixture; not calibrated domain evidence'})
        rejects('interface.inconsistent_spin_signs',lambda:replace(base,propulsion=replace(base.propulsion,geometry=replace(base.propulsion.geometry,spin_signs=(-1,1)))))
        conditions = e.propulsion.performance.conditions
        rejects('interface.spacing_mismatch',lambda:base.propulsion.evaluate(time_s=time,kinematics=e.actuator.kinematics,
                conditions=replace(conditions,rotor_axial_spacing_m=conditions.rotor_axial_spacing_m*1.1)))
        old = dict(cfg['geometry'])
        old['pivot_B0_m'] = old.pop('outer_origin_B0_m')
        rejects('interface.old_geometry_keyword',lambda:CoaxialGeometry(**old),TypeError)
        class CommandSubstitution:
            def evaluate(self, **kwargs):
                result = base.actuator_model.evaluate(**kwargs)
                return replace(result,kinematics=replace(result.kinematics,gimbal_rad=kwargs['command'].gimbal_rad))
        rejects('interface.command_substitution_rejected',lambda:evaluate(replace(base,actuator_model=CommandSubstitution())))
        class WrongConditions:
            def evaluate(self, **kwargs):
                result = base.propulsion.performance_map.evaluate(**kwargs)
                return replace(result,conditions=replace(result.conditions,bus_voltage_V=result.conditions.bus_voltage_V*1.01))
        rejects('interface.map_condition_echo_mismatch',lambda:evaluate(replace(base,propulsion=replace(base.propulsion,performance_map=WrongConditions()))))

    def time_and_purity():
        v = tv['time_argument_and_purity']
        parent = base.environment_provider
        def load_at(t):
            return AppliedLoad(force_B_N=np.array(v['external_force_at_reference_B_N'])+(t-v['reference_time_s'])*np.array(v['external_force_slope_B_N_s']),
                   application_point_B0_m=tv['external_point_load']['application_point_B0_m'],free_moment_B_N_m=[0,0,0],
                   model_scope='analytical_fixture',provenance='Pure explicitly time-dependent analytical load')
        class TimeEnvironment:
            def sample(self, **kwargs):
                return replace(parent.sample(**kwargs),additional_external_loads=(load_at(kwargs['time_s']),))
        model = replace(base,environment_provider=TimeEnvironment())
        vector, command_before = model.initial_vector(), saturated
        before = vector.copy()
        o = oracle(cfg,init['rotor_speed_magnitude_rad_s'],init['actual_gimbal_rad'])
        derivatives = []
        for i,t in enumerate(v['evaluation_times_s']):
            e = model.evaluate(time_s=t,vector=vector,command=saturated)
            force = o['force']+np.array(load_at(t).force_B_N)
            expected = R@force/cfg['mass_properties']['mass_kg']+[0,0,cfg['environment']['gravity_m_s2']]
            near('time.supplied_argument_'+str(i),e.derivative[3:6],expected,tol['algebraic_acceleration_error_m_s2'],'m/s^2')
            derivatives.append(e.derivative)
        require(v['evaluation_times_s'][0] == v['evaluation_times_s'][-1],'Repeatability fixture endpoints must repeat')
        near('purity.out_of_order_repeatability',derivatives[0],derivatives[-1],0,'mixed SI derivatives')
        near('purity.input_vector_unchanged',vector,before,0,'mixed SI state')
        check('purity.command_unchanged',saturated == command_before)
        check('purity.configuration_unchanged',cfg == saved_cfg)

    for name,operation in [('bottom',bottom_signs),('torque',torque_cases),('geometry',kinematics),
                           ('wrench_and_plant',load_accounting),('limiter',limiter),
                           ('policies',policies),('time_and_purity',time_and_purity)]:
        group(name,operation)


def main():
    before = None
    try:
        with redirect_stdout(sys.stderr):
            before = hashes()
            require(all(before[p] == digest for p,digest in PINNED.items()),'Pinned input file mismatch; review before running')
            check('artifacts.pinned_input_hashes',True)
            sys.path.insert(0,str(ROOT))
            for relative in PINNED:
                if relative.endswith('.py'):
                    name = relative[:-3].replace('/','.')
                    module = importlib.import_module(name)
                    require(Path(module.__file__).resolve() == (ROOT/relative).resolve(),'Unexpected import origin: '+name)
            check('capability.actual_repaired_module_imports',True)
            run()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        check('checker.setup_or_dispatch',False)
    try:
        after = hashes()
        check('artifacts.unchanged_during_checks',before is not None and before == after)
        diagnostic({'file_sha256_before':before,'file_sha256_after':after,
                    'interpreter':sys.executable,'controller_executed':False,
                    'preservation_scope':'Listed r12 files only, not whole source checkouts'})
    except Exception:
        traceback.print_exc(file=sys.stderr)
        check('artifacts.final_hashes',False)
    tested = dict(CHECKS)
    CHECKS.update({'integrated_motor_gimbal_response':None,'solver_returns_events_and_failure_tests':None,
                   'vehicle_closed_loop_mission_acceptance':None,'physical_validation':None})
    failed = any(value is False for value in tested.values())
    print(json.dumps({'outcome':'failed' if failed else 'inconclusive',
          'explanation':str(sum(tested.values()))+'/'+str(len(tested))+
          ' recorded boolean analytical/interface checks satisfied. Measurements and exact file hashes are on stderr. '
          'Overall vehicle validity remains inconclusive; null checks are unperformed here. Synthetic current/power '
          'arithmetic is not electrical closure or mission energy. No PID, physical, PDR or CDR acceptance is inferred.',
          'checks':CHECKS},allow_nan=False,sort_keys=True))


if __name__ == '__main__':
    main()
