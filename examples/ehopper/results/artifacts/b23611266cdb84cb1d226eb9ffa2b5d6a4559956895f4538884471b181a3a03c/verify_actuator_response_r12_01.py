"""Artifact-bound integrated actuator checks for the preliminary r12 plant.

Authorization: 66c7448f443f44ac9a016a1b384593a2 revision 1.
Audits: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 and
PDR-R12-PLANT-CALLER-RECONCILIATION-02, revision 1.

New caller audit: fixture construction and solver_options; State/ActuatorState;
Simulation.solve_ode/evaluate; unpack_state and explicit endpoint carry-forward;
LagParameters validation. Existing sources and callers remain unchanged.

Publish before verify_command. From sandbox workdir='.', repository='6dof_hopper':
  python -B software/pdr_r12_plant/verify_actuator_response_r12_01.py
Include this checker, fixture configuration/providers and all eight imported
plant-module artifact Refs. PINNED contains file hashes, not Ref hashes.

Independent oracles: exponential motor response, piecewise acceleration-capped
motor response, equal-time-constant cascaded gimbal response, and numerical
central differences of actual gimbal rates along dense trajectories at selected
interior times. Limits are checked at output samples and dense midpoints, not
certified continuously by numerical sampling. Refinement is numerical evidence.

The actual nineteen-state plant is integrated. Response parameters and loads
are synthetic, not calibrated vehicle inputs. A held-command switch is not a
PID update or a closed-loop saturation-recovery test. No files are written.
Only VerificationResult JSON goes to stdout; diagnostics go to stderr.
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


def diagnostic(data):
    print(json.dumps(data, allow_nan=False, sort_keys=True), file=sys.stderr)


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def check(name, condition, details=None):
    require(name not in CHECKS, 'Duplicate check: '+name)
    CHECKS[name] = bool(condition)
    if details is not None:
        diagnostic({'check':name,'details':details})


def near(name, actual, expected, tolerance, unit):
    import numpy as np
    a, b = np.asarray(actual,dtype=float), np.asarray(expected,dtype=float)
    limit = float(tolerance)
    require(np.isfinite(limit) and limit >= 0, 'Invalid tolerance')
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        check(name,False,{'shape_or_finiteness_failure':True,
                         'actual_shape':list(a.shape),'expected_shape':list(b.shape)})
        return
    error = float(np.max(np.abs(a-b))) if a.size else 0.0
    check(name,error <= limit,{'max_absolute_error':error,
                               'tolerance':limit,'unit':unit})


def group(name, operation):
    try:
        operation()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        check(name+'.completed',False)
    else:
        check(name+'.completed',True)


def hashes():
    result = {}
    for name in list(PINNED)+[Path(__file__).name]:
        path = ROOT/name
        require(not path.is_symlink() and ROOT in path.resolve().parents,
                'Unexpected artifact path: '+name)
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def run():
    import numpy as np
    import analytical_fixture_models_r12_01 as fixtures
    import repaired_hopper_r12.simulation.simulation as plant
    from repaired_hopper_r12.propulsion.actuators import ActuatorState, HeldCommand, LagParameters

    cfg = fixtures.load_fixture_config(ROOT/'analytical_fixture_config_r12_01.json')
    original_cfg = deepcopy(cfg)
    tv, tol = cfg['test_vectors'], cfg['analytical_test_tolerances']
    p = cfg['lag_parameters']
    options = fixtures.solver_options(cfg)
    initial, unused_actuator = fixtures.initial_snapshots(cfg)
    t0 = float(tv['nonzero_initialization']['time_start_s'])
    tau_m = np.asarray(p['motor_time_constant_s'])
    cap_m = np.asarray(p['rotor_acceleration_limit_rad_s2'])
    speed_limit = np.asarray(p['rotor_speed_limit_rad_s'])
    rate_limit = np.asarray(p['gimbal_rate_limit_rad_s'])
    acceleration_limit = np.asarray(p['gimbal_acceleration_limit_rad_s2'])
    effective_rate = np.minimum(rate_limit,acceleration_limit*p['gimbal_output_lag_s']/4)
    epsilon = float(tol['limit_roundoff_allowance'])
    sf = float(cfg['solver']['convergence_step_factor'])
    tf = float(cfg['solver']['convergence_tolerance_factor'])
    require(0 < sf < 1 and 0 < tf < 1,'Refinement must tighten settings')
    refined = dict(options,max_step_s=options['max_step_s']*sf,
                   rtol=options['rtol']*tf,
                   atol=(np.asarray(options['atol'])*tf).tolist())

    def times(start,duration):
        spacing = float(cfg['solver']['output_sample_interval_s'])
        require(duration > 0 and spacing > 0,'Positive duration and spacing required')
        return np.linspace(start,start+duration,int(np.ceil(duration/spacing))+1)

    def build(actuator):
        return fixtures.build_fixture(cfg,initial_state=initial,initial_actuator_state=actuator)

    def solve(name,model,command,sampling,numerical):
        before = model.initial_vector()
        result = model.solve_ode(time_span_s=[sampling[0],sampling[-1]],
                 command=command,sample_times_s=sampling,dense_output=True,**numerical)
        require(result.success and result.status == 0,'Incomplete integration: '+name)
        require(result.y.shape == (19,len(sampling)) and np.isfinite(result.y).all(),
                'Invalid output state array: '+name)
        require(np.array_equal(result.t,sampling) and callable(result.sol),
                'Missing requested samples or dense output: '+name)
        near(name+'.initial_components',result.y[:,0],before,0,'mixed SI state')
        near(name+'.initial_snapshot_unchanged',model.initial_vector(),before,0,'mixed SI state')
        check(name+'.no_controller_updates',result.plant_context['controller_updates_performed'] == 0)
        check(name+'.raw_quaternion_retained',result.plant_context['quaternion_samples_renormalized'] is False)
        near(name+'.quaternion_norm',np.linalg.norm(result.y[6:10],axis=0),
             np.ones(len(sampling)),tol['quaternion_norm_error'],'1')
        diagnostic({'integration':name,'start_s':float(sampling[0]),
                    'end_s':float(sampling[-1]),'nfev':int(result.nfev),
                    'status':int(result.status),'message':str(result.message)})
        return result

    def bounded_request(command):
        # Independent reconstruction of the documented static limiter.
        speed = np.maximum(0,np.minimum(command.rotor_speed_magnitude_rad_s,speed_limit))
        angles = np.maximum(p['joint_lower_rad'],np.minimum(command.gimbal_rad,p['joint_upper_rad']))
        if np.cos(angles[0])*np.cos(angles[1]) < np.cos(p['resultant_cone_limit_rad']):
            lo,hi = 0.0,1.0
            for unused in range(80):
                s = (lo+hi)/2
                if np.cos(s*angles[0])*np.cos(s*angles[1]) >= np.cos(p['resultant_cone_limit_rad']):
                    lo = s
                else:
                    hi = s
            angles = lo*angles
        return speed,angles

    def motor_oracle(start_speed,target,elapsed):
        # Solve dOmega/dt=clip((target-Omega)/tau,-A,+A) piecewise.
        elapsed = np.asarray(elapsed)
        values = np.empty((2,len(elapsed)))
        transitions = []
        for i in range(2):
            difference = float(target[i]-start_speed[i])
            sign = float(np.sign(difference))
            magnitude = abs(difference)
            switch = max(0.0,(magnitude-cap_m[i]*tau_m[i])/cap_m[i])
            transitions.append(switch)
            if magnitude <= cap_m[i]*tau_m[i]:
                values[i] = target[i]-difference*np.exp(-elapsed/tau_m[i])
            else:
                values[i] = np.where(elapsed <= switch,
                    start_speed[i]+sign*cap_m[i]*elapsed,
                    target[i]-sign*cap_m[i]*tau_m[i]*np.exp(-(elapsed-switch)/tau_m[i]))
        return values,transitions

    def compare_response(name,a,b):
        near(name+'.motor_speed',a[13:15],b[13:15],tol['motor_speed_error_rad_s'],'rad/s')
        near(name+'.filter_angles',a[15:17],b[15:17],tol['gimbal_angle_error_rad'],'rad')
        near(name+'.actual_angles',a[17:19],b[17:19],tol['gimbal_angle_error_rad'],'rad')

    def sampled_limits(name,model,command,result):
        sampling = np.sort(np.r_[result.t,(result.t[:-1]+result.t[1:])/2])
        y = result.sol(sampling)
        evaluations = [model.evaluate(time_s=float(t),vector=y[:,j],command=command)
                       for j,t in enumerate(sampling)]
        derivatives = np.asarray([v.actuator.derivative for v in evaluations]).T
        accelerations = np.asarray([v.actuator.kinematics.gimbal_acceleration_rad_s2
                                    for v in evaluations]).T
        expected_speed,expected_angles = bounded_request(command)
        check(name+'.sampled_speed_domain',np.all(y[13:15] >= -epsilon)
              and np.all(y[13:15] <= speed_limit[:,None]+epsilon))
        check(name+'.sampled_motor_acceleration',np.all(np.abs(derivatives[:2]) <= cap_m[:,None]+epsilon))
        for label,block in [('filter',y[15:17]),('actual',y[17:19])]:
            check(name+'.'+label+'_joint_domain',
                  np.all(block >= np.asarray(p['joint_lower_rad'])[:,None]-epsilon)
                  and np.all(block <= np.asarray(p['joint_upper_rad'])[:,None]+epsilon))
            check(name+'.'+label+'_cone_domain',
                  np.all(np.cos(block[0])*np.cos(block[1]) >= np.cos(p['resultant_cone_limit_rad'])-epsilon))
        check(name+'.sampled_filter_rate_limit',np.all(np.abs(derivatives[2:4]) <= effective_rate[:,None]+epsilon))
        check(name+'.sampled_actual_rate_limit',np.all(np.abs(derivatives[4:6]) <= effective_rate[:,None]+epsilon))
        check(name+'.sampled_actual_acceleration_limit',np.all(np.abs(accelerations) <= acceleration_limit[:,None]+epsilon))
        near(name+'.held_bounded_speed',np.asarray([v.actuator.bounded_command.rotor_speed_magnitude_rad_s for v in evaluations]),
             np.repeat(expected_speed[None,:],len(sampling),axis=0),0,'rad/s')
        near(name+'.held_bounded_angles',np.asarray([v.actuator.bounded_command.gimbal_rad for v in evaluations]),
             np.repeat(expected_angles[None,:],len(sampling),axis=0),tol['gimbal_angle_error_rad'],'rad')
        signs = np.asarray(p['rotor_spin_signs'])
        near(name+'.actual_signed_rotor_speeds',np.asarray([v.actuator.kinematics.rotor_signed_speed_rad_s for v in evaluations]).T,
             signs[:,None]*y[13:15],0,'rad/s')
        diagnostic({'sampled_limits':name,'sample_count':len(sampling),
                    'max_motor_acceleration_rad_s2':np.max(np.abs(derivatives[:2]),axis=1).tolist(),
                    'max_gimbal_rate_rad_s':np.max(np.abs(derivatives[4:6]),axis=1).tolist(),
                    'max_gimbal_acceleration_rad_s2':np.max(np.abs(accelerations),axis=1).tolist(),
                    'scope':'Output samples and dense midpoints only; not continuous numerical certification'})

    def acceleration_difference(name,model,command,result):
        step = float(tv['offset_kinematics']['finite_difference_time_step_s'])
        require(step > 0,'Positive difference step required')
        for j,fraction in enumerate((0.25,0.5,0.75)):
            instant = float(result.t[0]+fraction*(result.t[-1]-result.t[0]))
            require(result.t[0] < instant-step < instant+step < result.t[-1],
                    'Difference window outside integration interval')
            def evaluation(t):
                return model.evaluate(time_s=t,vector=result.sol(t),command=command).actuator
            exact = evaluation(instant).kinematics.gimbal_acceleration_rad_s2
            for k,h in enumerate((step,step/2)):
                plus = np.asarray(evaluation(instant+h).kinematics.gimbal_rate_rad_s)
                minus = np.asarray(evaluation(instant-h).kinematics.gimbal_rate_rad_s)
                near(name+'.rate_derivative_'+str(j)+'_'+str(k),exact,(plus-minus)/(2*h),
                     tol['directional_derivative_error_rad_s2'],'rad/s^2')

    def unlimited():
        v = tv['unlimited_lag']
        actuator = ActuatorState(v['initial_rotor_speed_rad_s'],v['initial_gimbal_rad'],v['initial_gimbal_rad'])
        command = HeldCommand(v['requested_rotor_speed_rad_s'],v['requested_gimbal_rad'])
        model = build(actuator)
        tau = float(p['gimbal_output_lag_s'])
        require(p['gimbal_demand_lag_s'] == tau,'Equal-time-constant oracle required')
        target_speed,target_angles = bounded_request(command)
        require(np.array_equal(target_speed,command.rotor_speed_magnitude_rad_s)
                and np.array_equal(target_angles,command.gimbal_rad),'Unlimited command is bounded')
        motor_difference = target_speed-np.asarray(v['initial_rotor_speed_rad_s'])
        angle_difference = target_angles-np.asarray(v['initial_gimbal_rad'])
        require(np.all(np.abs(motor_difference)/tau_m < cap_m),'Unlimited motor premise fails')
        require(np.all(np.abs(angle_difference)/tau < effective_rate),'Unlimited filter premise fails')
        sampling = times(t0,float(v['duration_s']))
        result = solve('unlimited',model,command,sampling,options)
        elapsed = sampling-t0
        decay = np.exp(-elapsed/tau)
        expected_motor = target_speed[:,None]-motor_difference[:,None]*np.exp(-elapsed[None,:]/tau_m[:,None])
        expected_filter = target_angles[:,None]-angle_difference[:,None]*decay
        expected_actual = target_angles[:,None]-angle_difference[:,None]*(1+elapsed/tau)*decay
        near('unlimited.exponential_motor',result.y[13:15],expected_motor,tol['motor_speed_error_rad_s'],'rad/s')
        near('unlimited.exponential_filter',result.y[15:17],expected_filter,tol['gimbal_angle_error_rad'],'rad')
        near('unlimited.cascaded_actual_angle',result.y[17:19],expected_actual,tol['gimbal_angle_error_rad'],'rad')
        evaluations = [model.evaluate(time_s=float(t),vector=result.y[:,j],command=command).actuator
                       for j,t in enumerate(sampling)]
        near('unlimited.analytic_gimbal_rate',np.asarray([e.kinematics.gimbal_rate_rad_s for e in evaluations]).T,
             angle_difference[:,None]*(elapsed/tau**2)*decay,tol['gimbal_angle_error_rad']/tau,'rad/s')
        near('unlimited.analytic_gimbal_acceleration',np.asarray([e.kinematics.gimbal_acceleration_rad_s2 for e in evaluations]).T,
             angle_difference[:,None]/tau**2*(1-elapsed/tau)*decay,tol['directional_derivative_error_rad_s2'],'rad/s^2')
        tight = solve('unlimited_refined',model,command,sampling,refined)
        compare_response('unlimited.refinement',result.y,tight.y)
        sampled_limits('unlimited',model,command,result)
        acceleration_difference('unlimited',model,command,result)

    def saturation_and_release():
        v = tv['saturated_command']
        initial_values = tv['unlimited_lag']
        actuator = ActuatorState(initial_values['initial_rotor_speed_rad_s'],
                  initial_values['initial_gimbal_rad'],initial_values['initial_gimbal_rad'])
        command = HeldCommand(v['rotor_speed_magnitude_rad_s'],v['gimbal_rad'])
        model = build(actuator)
        sampling = times(t0,float(v['duration_s']))
        result = solve('saturated',model,command,sampling,options)
        target,angles = bounded_request(command)
        expected,switches = motor_oracle(np.asarray(actuator.rotor_speed_magnitude_rad_s),target,sampling-t0)
        require(any(0 < value < sampling[-1]-t0 for value in switches),
                'Fixture must exercise an acceleration-cap transition')
        near('saturated.piecewise_motor',result.y[13:15],expected,tol['motor_speed_error_rad_s'],'rad/s')
        sampled_limits('saturated',model,command,result)
        acceleration_difference('saturated',model,command,result)
        tight = solve('saturated_refined',model,command,sampling,refined)
        compare_response('saturated.refinement',result.y,tight.y)
        diagnostic({'saturation_fixture_initial_actuator_state':actuator.as_vector().tolist(),
                    'bounded_rotor_speed_rad_s':target.tolist(),'bounded_gimbal_rad':angles.tolist(),
                    'motor_transition_elapsed_s':switches})

        endpoint = result.y[:,-1].copy()
        state,actuator_endpoint = plant.unpack_state(endpoint,schema=plant.PLANT_STATE_SCHEMA)
        continued = replace(model,initial_state=state,initial_actuator_state=actuator_endpoint)
        near('release.all_endpoint_states_carried',continued.initial_vector(),endpoint,0,'mixed SI state')
        release = HeldCommand(v['release_command_rotor_speed_rad_s'],v['release_command_gimbal_rad'])
        release_times = times(float(sampling[-1]),float(v['release_duration_s']))
        before = model.evaluate(time_s=float(sampling[-1]),vector=endpoint,command=command).actuator
        after = continued.evaluate(time_s=float(sampling[-1]),vector=endpoint,command=release).actuator
        near('release.gimbal_rate_continuity',after.kinematics.gimbal_rate_rad_s,
             before.kinematics.gimbal_rate_rad_s,0,'rad/s')
        check('release.motor_derivative_changes',not np.array_equal(after.derivative[:2],before.derivative[:2]))
        released = solve('release',continued,release,release_times,options)
        release_target,unused_angles = bounded_request(release)
        expected,unused_switches = motor_oracle(endpoint[13:15],release_target,release_times-release_times[0])
        near('release.piecewise_motor',released.y[13:15],expected,tol['motor_speed_error_rad_s'],'rad/s')
        sampled_limits('release',continued,release,released)
        acceleration_difference('release',continued,release,released)
        tight_release = solve('release_refined',continued,release,release_times,refined)
        compare_response('release.refinement',released.y,tight_release.y)
        near('release.predecessor_initial_not_replaced',model.initial_vector(),
             plant.pack_state(initial,actuator),0,'mixed SI state')

    def negative_inputs():
        parameters = LagParameters(**p)
        operations = {
            'zero_motor_tau':lambda:replace(parameters,motor_time_constant_s=[0,tau_m[1]]),
            'zero_output_tau':lambda:replace(parameters,gimbal_output_lag_s=0),
            'negative_actual_speed':lambda:ActuatorState([-1,0],[0,0],[0,0]),
            'actual_speed_above_limit':lambda:parameters.validate_state(ActuatorState(speed_limit+1,[0,0],[0,0])),
            'actual_joint_outside_limit':lambda:parameters.validate_state(ActuatorState([0,0],[0,0],np.asarray(p['joint_upper_rad'])+1)),
        }
        for name,operation in operations.items():
            try:
                operation()
            except ValueError as error:
                check('invalid.'+name,True,{'deliberate_negative_fixture':True,'message':str(error)})
            else:
                check('invalid.'+name,False)

    for name,operation in [('unlimited',unlimited),('saturation_release',saturation_and_release),
                           ('invalid',negative_inputs)]:
        group(name,operation)
    check('configuration.unchanged',cfg == original_cfg)


def main():
    before = None
    try:
        with redirect_stdout(sys.stderr):
            before = hashes()
            require(all(before[name] == value for name,value in PINNED.items()),
                    'Pinned artifact mismatch; review before execution')
            check('artifacts.pinned_inputs',True)
            sys.path.insert(0,str(ROOT))
            for relative in PINNED:
                if relative.endswith('.py'):
                    module = importlib.import_module(relative[:-3].replace('/','.'))
                    require(Path(module.__file__).resolve() == (ROOT/relative).resolve(),
                            'Unexpected module origin: '+relative)
            check('capability.repaired_imports',True)
            run()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        check('checker.setup_or_dispatch',False)
    try:
        after = hashes()
        check('artifacts.unchanged_during_checks',before is not None and before == after)
        diagnostic({'file_sha256_before':before,'file_sha256_after':after,
                    'interpreter':sys.executable,'controller_executed':False,
                    'preservation_scope':'Listed r12 files only, not whole-checkout cleanliness'})
    except Exception:
        traceback.print_exc(file=sys.stderr)
        check('artifacts.final_hashes',False)
    tested = dict(CHECKS)
    CHECKS.update({'loaded_hardware_actuator_calibration':None,
                   'complete_articulated_vehicle_accuracy':None,
                   'vehicle_closed_loop_saturation_recovery_and_mission':None,
                   'vehicle_electrical_thermal_and_physical_validation':None})
    failed = any(value is False for value in tested.values())
    print(json.dumps({
        'outcome':'failed' if failed else 'inconclusive',
        'explanation':str(sum(tested.values()))+'/'+str(len(tested))+
            ' recorded boolean integrated-actuator checks satisfied. Measurements, fixture initialization and file hashes are on stderr. '
            'Analytical motor and cascaded-gimbal responses use synthetic parameters; command switching tests explicit endpoint carry-forward, not PID recovery. '
            'Limit observations are sampled, not continuous numerical certification. Null checks are unperformed. '
            'No loaded hardware capability, complete articulated accuracy, vehicle mission or PDR/CDR acceptance is inferred.',
        'checks':CHECKS},allow_nan=False,sort_keys=True))


if __name__ == '__main__':
    main()
