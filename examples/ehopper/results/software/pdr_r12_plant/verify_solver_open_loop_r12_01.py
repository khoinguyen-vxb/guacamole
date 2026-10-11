"""Artifact-bound open-loop and solver checks for the preliminary r12 plant.

Authorization: 66c7448f443f44ac9a016a1b384593a2 revision 1.
Audits: PDR-R12-PLANT-PRE-EDIT-AUDIT-01 and
PDR-R12-PLANT-CALLER-RECONCILIATION-02, both revision 1.
Frames: f046cc4fe5294a6f9a61027529056f61 revision 1.

New caller audit: uses the inspected fixture construction/solver_options,
State and ActuatorState constructors, Simulation.initial_vector/solve_ode,
and the returned samples, dense solution, events and IntegrationFailure.
Existing plant files and their callers are unchanged. Deliberate solver and
provider failures below are labelled API fixtures, not naturally reproduced
numerical failures. Temporary function substitution is restored in finally.

Publish before verify_command. Command, from sandbox workdir='.':
  python -B software/pdr_r12_plant/verify_solver_open_loop_r12_01.py
Select repository='6dof_hopper'. Include artifact Refs for this checker,
configuration, fixture providers and all eight plant modules. PINNED holds
file hashes, not Guacamole Ref hashes.

Independent expectations: ballistic CG translation, scalar-first Hamilton
constant-rate exponential, stationary analytical paired-map trim, and a
quadratic plane-crossing time. Convergence comparisons are numerical evidence,
not independent physical validation. All test values are synthetic.

No PID, vehicle mission, battery endurance or physical landing is tested.
This checker does not verify integrated actuator lag/saturation recovery;
those need a separate analytical-response checker. No files are written.
Stdout contains only VerificationResult JSON; diagnostics use stderr.
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
from types import SimpleNamespace

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


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def check(name, condition, details=None):
    require(name not in CHECKS, 'Duplicate check: ' + name)
    CHECKS[name] = bool(condition)
    if details is not None:
        diagnostic({'check': name, 'details': details})


def near(name, actual, expected, tolerance, unit):
    import numpy as np
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    limit = float(tolerance)
    require(np.isfinite(limit) and limit >= 0, 'Invalid numerical tolerance')
    valid = a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all()
    if not valid:
        check(name, False, {'actual_shape': list(a.shape),
              'expected_shape': list(b.shape), 'shape_or_finiteness_failure': True})
        return
    differences = np.abs(a-b)
    error = float(np.max(differences)) if a.size else 0.0
    details = {'max_absolute_error': error, 'tolerance': limit, 'unit': unit}
    if a.size:
        index = int(np.argmax(differences))
        details.update(actual_at_max_error=float(a.flat[index]),
                       expected_at_max_error=float(b.flat[index]))
    check(name, error <= limit, details)


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
        check(name + '.completed', False)
    else:
        check(name + '.completed', True)


def hashes():
    result = {}
    for relative in list(PINNED) + [Path(__file__).name]:
        path = ROOT / relative
        require(not path.is_symlink() and ROOT in path.resolve().parents,
                'Unexpected artifact path: ' + relative)
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def run():
    import numpy as np
    import analytical_fixture_models_r12_01 as fixtures
    import repaired_hopper_r12.simulation.simulation as plant
    from repaired_hopper_r12.simulation.state import State
    from repaired_hopper_r12.propulsion.actuators import ActuatorState, HeldCommand

    cfg = fixtures.load_fixture_config(ROOT / 'analytical_fixture_config_r12_01.json')
    saved = deepcopy(cfg)
    tv, tol = cfg['test_vectors'], cfg['analytical_test_tolerances']
    options = fixtures.solver_options(cfg)
    start = float(tv['nonzero_initialization']['time_start_s'])
    zero_actuator = ActuatorState([0,0], [0,0], [0,0])
    zero_command = HeldCommand([0,0], [0,0])
    initial, initial_actuator = fixtures.initial_snapshots(cfg)

    def product(a, b):
        w,x,y,z = a
        v,i,j,k = b
        return np.array([w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                         w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v])

    def initial_quaternion():
        v = tv['nonzero_initialization']
        r,p,y = np.array([v['roll_rad'], v['pitch_rad'], v['yaw_rad']])/2
        return product(product([np.cos(y),0,0,np.sin(y)],
                               [np.cos(p),0,np.sin(p),0]),
                               [np.cos(r),np.sin(r),0,0])

    def samples(t0, duration):
        spacing = float(cfg['solver']['output_sample_interval_s'])
        require(spacing > 0 and duration > 0, 'Positive sampling interval/duration required')
        return np.linspace(t0, t0+duration, int(np.ceil(duration/spacing))+1)

    def refined_options():
        sf = float(cfg['solver']['convergence_step_factor'])
        tf = float(cfg['solver']['convergence_tolerance_factor'])
        require(0 < sf < 1 and 0 < tf < 1, 'Convergence factors must tighten settings')
        return dict(options, max_step_s=options['max_step_s']*sf,
                    rtol=options['rtol']*tf,
                    atol=(np.array(options['atol'])*tf).tolist())

    def compare_vectors(name, actual, expected):
        a, b = np.asarray(actual), np.asarray(expected)
        require(a.shape == b.shape and a.ndim == 2 and a.shape[0] == 19,
                'Expected matching (19,N) state arrays')
        blocks = [
            ('position',0,3,'trajectory_position_error_m','m'),
            ('velocity',3,6,'trajectory_velocity_error_m_s','m/s'),
            ('quaternion',6,10,'quaternion_component_error','1'),
            ('body_rate',10,13,'trajectory_angular_rate_error_rad_s','rad/s'),
            ('motor_speed',13,15,'motor_speed_error_rad_s','rad/s'),
            ('demand_filter',15,17,'gimbal_angle_error_rad','rad'),
            ('actual_gimbal',17,19,'gimbal_angle_error_rad','rad'),
        ]
        for label,lo,hi,key,unit in blocks:
            near(name+'.'+label, a[lo:hi], b[lo:hi], tol[key], unit)

    def metadata(name, solution):
        context = solution.plant_context
        check(name+'.state_schema', context['schema'] == plant.PLANT_STATE_SCHEMA)
        check(name+'.units', tuple(context['units']) == plant.PLANT_UNITS)
        check(name+'.no_controller_updates', context['controller_updates_performed'] == 0)
        check(name+'.no_quaternion_projection', context['quaternion_samples_renormalized'] is False)
        check(name+'.CG_translation', context['translation_reference'] == 'instantaneous complete-vehicle CG G')
        check(name+'.physical_status', context['physical_acceptance'] == 'not_assessed')

    def solve(model, command, times, numerical=None, **extra):
        settings = options if numerical is None else numerical
        result = model.solve_ode(time_span_s=[times[0],times[-1]], command=command,
                                 sample_times_s=times, dense_output=True,
                                 **settings, **extra)
        require(result.success and result.status == 0, 'Expected completed event-free integration')
        require(result.y.shape == (19,len(times)), 'Incomplete requested output samples')
        require(np.isfinite(result.y).all(), 'Nonfinite integration output')
        require(np.array_equal(result.t,times), 'Returned sample times differ')
        require(callable(result.sol), 'Dense solution missing')
        diagnostic({'integration': {'time_start_s':float(times[0]),
                    'time_end_s':float(times[-1]), 'output_count':len(times),
                    'method':settings['method'], 'nfev':int(result.nfev),
                    'status':int(result.status), 'message':str(result.message)}})
        return result

    zero_cfg = deepcopy(cfg)
    zero_cfg['synthetic_paired_map']['thrust_coefficient_N_s2_rad2'] = [0,0]
    zero_cfg['synthetic_paired_map']['drag_torque_coefficient_N_m_s2_rad2'] = [0,0]
    zero_cfg['environment']['additional_external_loads'] = []
    spherical = float(tv['spherical_free_rotation']['inertia_kg_m2'])
    require(spherical > 0, 'Positive spherical fixture inertia required')
    zero_cfg['mass_properties']['inertia_B_G_kg_m2'] = (np.eye(3)*spherical).tolist()
    free = fixtures.build_fixture(zero_cfg, initial_state=initial,
                                  initial_actuator_state=zero_actuator)

    def ballistic(state, times, t0, q0, omega):
        dt = np.asarray(times)-t0
        p0 = np.array(state.position_G_L_m)
        v0 = np.array(state.velocity_G_L_m_s)
        acceleration = np.array([0,0,zero_cfg['environment']['gravity_m_s2']])
        expected = np.zeros((19,len(dt)))
        expected[:3] = p0[:,None]+v0[:,None]*dt+0.5*acceleration[:,None]*dt**2
        expected[3:6] = v0[:,None]+acceleration[:,None]*dt
        expected[10:13] = np.asarray(omega)[:,None]
        magnitude = float(np.linalg.norm(omega))
        for j,t in enumerate(dt):
            delta = (np.r_[np.cos(magnitude*t/2),
                     np.asarray(omega)*np.sin(magnitude*t/2)/magnitude]
                     if magnitude else np.array([1,0,0,0]))
            expected[6:10,j] = product(q0,delta)
        return expected

    def free_rotation():
        duration = float(tv['spherical_free_rotation']['duration_s'])
        times = samples(start,duration)
        before = free.initial_vector()
        result = solve(free,zero_command,times)
        expected = ballistic(initial,times,start,initial_quaternion(),initial.omega_B_rad_s)
        compare_vectors('free.analytic_samples',result.y,expected)
        near('free.initial_state_exact',result.y[:,0],before,0,'mixed SI state')
        near('free.initial_ownership_after_solve',free.initial_vector(),before,0,'mixed SI state')
        midpoint_times = (times[:-1]+times[1:])/2
        compare_vectors('free.analytic_dense_output',result.sol(midpoint_times),
                        ballistic(initial,midpoint_times,start,initial_quaternion(),initial.omega_B_rad_s))
        near('free.raw_quaternion_norm',np.linalg.norm(result.y[6:10],axis=0),
             np.ones(len(times)),tol['quaternion_norm_error'],'1')
        refined = solve(free,zero_command,times,refined_options())
        compare_vectors('free.refinement_agreement',result.y,refined.y)
        repeat = solve(free,zero_command,times)
        compare_vectors('free.repeat_restarts_initial_state',result.y,repeat.y)
        metadata('free',result)
        diagnostic({'fixture_overrides': {'thrust_coefficients':[0,0],
                    'drag_coefficients':[0,0], 'additional_external_loads':[],
                    'spherical_inertia_kg_m2':spherical, 'actuator_state':[0]*6},
                    'scope':'Ballistic CG and spherical rigid-body rotation; not rotor-off electrical validation'})

    def analytical_trim():
        p = cfg['synthetic_paired_map']
        require(p['thrust_coefficient_N_s2_rad2'][0] == p['thrust_coefficient_N_s2_rad2'][1],
                'Trim oracle requires equal synthetic thrust coefficients')
        require(p['cross_interference_coefficient'][0] == p['cross_interference_coefficient'][1],
                'Trim oracle requires equal synthetic interference coefficients')
        require(p['drag_torque_coefficient_N_m_s2_rad2'][0] == p['drag_torque_coefficient_N_m_s2_rad2'][1],
                'Trim oracle requires equal aerodynamic torque coefficients')
        geometry = cfg['geometry']
        require(np.array_equal(geometry['outer_to_inner_outer_m'],[0,0,0])
                and np.array_equal(np.array(geometry['outer_origin_B0_m'])[:2],[0,0])
                and np.array_equal(np.array(geometry['hub_offsets_from_inner_M_m'])[:,:2],np.zeros((2,2)))
                and np.array_equal(cfg['mass_properties']['cg_B0_m'],[0,0,0]),
                'Trim oracle requires centred coincident-axis geometry')
        weight = cfg['mass_properties']['mass_kg']*cfg['environment']['gravity_m_s2']
        denominator = 2*p['thrust_coefficient_N_s2_rad2'][0]-weight*p['cross_interference_coefficient'][0]/p['reference_speed_rad_s']**2
        require(weight > 0 and denominator > 0, 'Synthetic trim has no finite positive solution')
        speed = float(np.sqrt(weight/denominator))
        require(np.all(speed <= np.array(cfg['lag_parameters']['rotor_speed_limit_rad_s'])),
                'Synthetic trim exceeds configured response limits')
        state = State(position_G_L_m=tv['trim']['position_G_L_m'],
                      velocity_G_L_m_s=[0,0,0],q_LB=[1,0,0,0],omega_B_rad_s=[0,0,0])
        actuator = ActuatorState([speed,speed],[0,0],[0,0])
        command = HeldCommand([speed,speed],[0,0])
        model = fixtures.build_fixture(cfg,initial_state=state,initial_actuator_state=actuator)
        times = samples(start,float(tv['trim']['duration_s']))
        result = solve(model,command,times)
        compare_vectors('trim.stationary_state',result.y,
                        np.repeat(model.initial_vector()[:,None],len(times),axis=1))
        near('trim.raw_quaternion_norm',np.linalg.norm(result.y[6:10],axis=0),
             np.ones(len(times)),tol['quaternion_norm_error'],'1')
        evaluation = model.evaluate(time_s=start,vector=model.initial_vector(),command=command)
        near('trim.force_balances_weight',evaluation.external_wrench.force_B_N,
             [0,0,-weight],tol['force_error_N'],'N')
        near('trim.external_moment_zero',evaluation.external_wrench.moment_B_G_N_m,
             [0,0,0],tol['moment_error_N_m'],'N m')
        refined = solve(model,command,times,refined_options())
        compare_vectors('trim.refinement_agreement',result.y,refined.y)
        metadata('trim',result)
        diagnostic({'synthetic_trim': {'rotor_speed_magnitude_rad_s':speed,
                    'weight_N':weight,'duration_s':float(times[-1]-times[0]),
                    'bus_current_A':evaluation.total_bus_current_A,
                    'bus_power_W':evaluation.total_bus_power_W},
                    'scope':'Open-loop arithmetic fixture; no calibrated thrust, endurance or hover mission acceptance'})

    def nonzero_coupled_execution():
        model = fixtures.build_fixture(cfg,initial_state=initial,
                                       initial_actuator_state=initial_actuator)
        v = tv['nonzero_initialization']
        command = HeldCommand(v['rotor_speed_magnitude_rad_s'],v['demand_filter_gimbal_rad'])
        times = samples(start,float(v['duration_s']))
        before = model.initial_vector()
        result = solve(model,command,times)
        near('coupled.all_nineteen_initial_components',result.y[:,0],before,0,'mixed SI state')
        near('coupled.initial_snapshot_unchanged',model.initial_vector(),before,0,'mixed SI state')
        refined = solve(model,command,times,refined_options())
        compare_vectors('coupled.refinement_agreement',result.y,refined.y)
        alternate = solve(model,command,times,dict(refined_options(),method='RK45'))
        compare_vectors('coupled.RK45_DOP853_agreement',alternate.y,refined.y)
        near('coupled.raw_quaternion_norm',np.linalg.norm(result.y[6:10],axis=0),
             np.ones(len(times)),tol['quaternion_norm_error'],'1')
        metadata('coupled',result)
        check('coupled.requested_command_metadata',result.plant_context['requested_held_command'] == {
              'rotor_speed_magnitude_rad_s':command.rotor_speed_magnitude_rad_s,
              'gimbal_rad':command.gimbal_rad})

    def terminal_event():
        v = tv['terminal_event']
        state = State(position_G_L_m=v['position_G_L_m'],velocity_G_L_m_s=v['velocity_G_L_m_s'],
                      q_LB=[1,0,0,0],omega_B_rad_s=[0,0,0])
        model = fixtures.build_fixture(zero_cfg,initial_state=state,initial_actuator_state=zero_actuator)
        t0, duration = float(v['time_start_s']),float(v['duration_s'])
        g = float(zero_cfg['environment']['gravity_m_s2'])
        delta = float(v['event_down_coordinate_m']-state.position_G_L_m[2])
        vz = float(state.velocity_G_L_m_s[2])
        require(g > 0 and delta > 0, 'Plane-crossing oracle requires positive gravity and lower plane')
        elapsed = 2*delta/(np.sqrt(vz*vz+2*g*delta)+vz)
        expected_time = float(t0+elapsed)
        times = t0+np.array(v['output_times_relative_s'])
        require(0 < elapsed < duration and times[-1] < expected_time,
                'Event must precede interval end and follow all requested output samples')
        def event(t,y):
            return y[2]-v['event_down_coordinate_m']
        event.terminal = True
        event.direction = v['event_direction']
        require(event.direction == 1, 'Fixture requires positive-down crossing')
        result = model.solve_ode(time_span_s=[t0,t0+duration],command=zero_command,
                 sample_times_s=times,dense_output=True,events=event,**options)
        check('event.successful_terminal_status',result.success and result.status == 1)
        require(len(result.t_events) == 1 and len(result.t_events[0]) == 1,
                'Exactly one terminal event required')
        near('event.quadratic_time',result.t_events[0][0],expected_time,tol['event_time_error_s'],'s')
        expected = ballistic(state,[expected_time],t0,[1,0,0,0],[0,0,0])
        compare_vectors('event.analytic_event_state',result.y_events[0].T,expected)
        compare_vectors('event.dense_endpoint',result.sol([result.t_events[0][0]]),expected)
        check('event.last_requested_sample_is_not_endpoint',result.t[-1] < result.t_events[0][0])
        near('event.requested_samples_retained',result.t,times,0,'s')
        compare_vectors('event.pre_event_output',result.y,
                        ballistic(state,times,t0,[1,0,0,0],[0,0,0]))
        metadata('event',result)
        def opposite(t,y):
            return y[2]-v['event_down_coordinate_m']
        opposite.terminal = True
        opposite.direction = -1
        all_times = samples(t0,duration)
        opposite_result = solve(model,zero_command,all_times,events=opposite)
        check('event.direction_filter_retained',len(opposite_result.t_events[0]) == 0)
        diagnostic({'event_scope':'Synthetic CG plane crossing, not foot contact, impact or controlled landing',
                    'expected_event_time_s':expected_time,
                    'observed_event_time_s':float(result.t_events[0][0])})

    def failure_contract():
        span = [start,start+float(tv['spherical_free_rotation']['duration_s'])]
        original_solver = plant.solve_ivp
        marker = SimpleNamespace(success=False,status=-1,message='INJECTED solver failure API fixture',
                                 t=np.array([start]),y=free.initial_vector()[:,None])
        def injected(*args,**kwargs):
            return marker
        try:
            plant.solve_ivp = injected
            try:
                free.solve_ode(time_span_s=span,command=zero_command,**options)
            except plant.IntegrationFailure as error:
                check('failure.exception_retains_identical_result',error.solution is marker)
                check('failure.exception_retains_message',str(error) == marker.message)
            else:
                check('failure.exception_retains_identical_result',False)
            returned = free.solve_ode(time_span_s=span,command=zero_command,
                                     raise_on_failure=False,**options)
            check('failure.return_policy_preserves_identical_result',returned is marker)
            check('failure.status_not_rewritten',returned.success is False and returned.status == -1)
        finally:
            plant.solve_ivp = original_solver
        check('failure.real_solver_restored',plant.solve_ivp is original_solver)
        class InjectedProviderError(RuntimeError):
            pass
        provider_error = InjectedProviderError('INJECTED provider exception API fixture')
        class FailingEnvironment:
            def sample(self,**kwargs):
                raise provider_error
        changed = replace(free,environment_provider=FailingEnvironment())
        try:
            changed.solve_ode(time_span_s=span,command=zero_command,**options)
        except InjectedProviderError as error:
            check('failure.provider_exception_identity',error is provider_error)
        else:
            check('failure.provider_exception_identity',False)
        diagnostic({'failure_scope':'Deliberately injected API-contract fixtures, not observed natural integration failures'})

    def invalid_solver_inputs():
        base = dict(time_span_s=[start,start+0.1],command=zero_command,**options)
        cases = [
            ('reversed_time',{'time_span_s':[start+0.1,start]}),
            ('zero_interval',{'time_span_s':[start,start]}),
            ('unsupported_method',{'method':'not_a_method'}),
            ('zero_rtol',{'rtol':0}),
            ('unit_rtol',{'rtol':1}),
            ('scalar_atol',{'atol':1e-9}),
            ('wrong_atol_length',{'atol':[1e-9]*18}),
            ('nonpositive_atol',{'atol':[0]+[1e-9]*18}),
            ('zero_max_step',{'max_step_s':0}),
            ('unordered_output',{'sample_times_s':[start+0.05,start]}),
            ('outside_output',{'sample_times_s':[start-0.01]}),
        ]
        for name,override in cases:
            rejects('invalid.'+name,lambda override=override:free.solve_ode(**dict(base,**override)))
        rejects('invalid.nonboolean_dense_output',lambda:free.solve_ode(**dict(base,dense_output=1)),TypeError)
        rejects('invalid.nonboolean_failure_policy',lambda:free.solve_ode(**dict(base,raise_on_failure=1)),TypeError)
        rejects('invalid.noncallable_event',lambda:free.solve_ode(**dict(base,events=[None])),TypeError)

    for name,operation in [
        ('free',free_rotation),('trim',analytical_trim),
        ('coupled',nonzero_coupled_execution),('event',terminal_event),
        ('failure',failure_contract),('invalid',invalid_solver_inputs),
    ]:
        group(name,operation)
    check('configuration.unchanged',cfg == saved)


def main():
    before = None
    try:
        with redirect_stdout(sys.stderr):
            before = hashes()
            require(all(before[p] == digest for p,digest in PINNED.items()),
                    'Pinned artifact mismatch; review inputs before executing')
            check('artifacts.pinned_inputs',True)
            sys.path.insert(0,str(ROOT))
            for relative in PINNED:
                if relative.endswith('.py'):
                    name = relative[:-3].replace('/','.')
                    module = importlib.import_module(name)
                    require(Path(module.__file__).resolve() == (ROOT/relative).resolve(),
                            'Unexpected imported module origin: '+name)
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
                    'preservation_scope':'Listed r12 files only; not whole-checkout cleanliness'})
    except Exception:
        traceback.print_exc(file=sys.stderr)
        check('artifacts.final_hashes',False)
    tested = dict(CHECKS)
    CHECKS.update({
        'integrated_actuator_response_analytical_verification':None,
        'vehicle_closed_loop_mission_acceptance':None,
        'vehicle_electrical_thermal_endurance':None,
        'vehicle_physical_validation':None,
    })
    failed = any(value is False for value in tested.values())
    result = {
        'outcome':'failed' if failed else 'inconclusive',
        'explanation':str(sum(tested.values()))+'/'+str(len(tested))+
            ' recorded boolean open-loop/solver checks satisfied. Measurements, overrides and file hashes are on stderr. '
            'Ballistic rotation, stationary trim and plane crossing are synthetic analytical fixtures; solver failures are deliberately injected API tests. '
            'Numerical agreement does not establish articulated vehicle accuracy. Null checks remain unperformed here. '
            'No PID tuning, vehicle mission, electrical endurance, physical validation or PDR/CDR acceptance is inferred.',
        'checks':CHECKS,
    }
    print(json.dumps(result,allow_nan=False,sort_keys=True))


if __name__ == '__main__':
    main()
