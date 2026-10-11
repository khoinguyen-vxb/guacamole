# PDR r12 fresh static affected-caller index

Status: static evidence only; manual caller review remains required.

Observed preservation during this audit: {"historical_r9": true, "original_hopper": true, "pendulum_reference": true}

Full imports, definitions and symbol references are in source_inventory_r12_01.json.
Read the original files at the locations below before accepting a repair.

## original_hopper/PyThrust/examples/calibrate_system_resistance.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/examples/calibrate_system_resistance.py`
SHA-256: `bbbda8dfd8841a59c7b05bb0a0dbbe55357c21fbe4956fb68fb196b098b16ea9`


## original_hopper/PyThrust/examples/openmdao_hover_optimization.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/examples/openmdao_hover_optimization.py`
SHA-256: `dbd10e0958bae8555a9687ea08c91911eb3d2563ca78e1601365809333f48992`


## original_hopper/PyThrust/examples/rate_map_battery_mission.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/examples/rate_map_battery_mission.py`
SHA-256: `f50afad15ba3ab830ec97149fb81593cc39c1feb5789f3657bab45f8ede1c842`


## original_hopper/PyThrust/examples/rate_map_battery_point_states.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/examples/rate_map_battery_point_states.py`
SHA-256: `001af20c1efcc0e5f08bfc5a9881b2db627d411ac4c0906a2e067a5aaa6b1005`


## original_hopper/PyThrust/examples/select_motor_from_database.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/examples/select_motor_from_database.py`
SHA-256: `ac206cf26bed8a0c7b5dd36c1a865b10b895d17bfb7313bc720c859ecb920d58`


## original_hopper/PyThrust/pythrust/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/__init__.py`
SHA-256: `4142193748ce5aa470e6e7c9e5aae3ad97d8bbb13259f464609455fe24dfe0b7`


## original_hopper/PyThrust/pythrust/battery/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/battery/__init__.py`
SHA-256: `de66bd81737502fc7020ea5be3f523b330ae75e20a8c3d7b21587f2e8835ee8e`


## original_hopper/PyThrust/pythrust/battery/fixed.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/battery/fixed.py`
SHA-256: `295be468c829359addcbec5c8c12a768e44c49bf27b0321c2d74ed7bad15df75`


## original_hopper/PyThrust/pythrust/battery/rate_map.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/battery/rate_map.py`
SHA-256: `b022873a21892005fbc4333584fc5d5a45fd808f467f92031a5084c11051090c`

- Lines 667-675: `RateMapBattery._integrate_with_point_function` calls `solve_ivp`.
- Lines 758-766: `RateMapBattery._integrate_to_dod` calls `solve_ivp`.
- Symbol-reference locations: 667 RateMapBattery._integrate_with_point_function -> solve_ivp; 758 RateMapBattery._integrate_to_dod -> solve_ivp

## original_hopper/PyThrust/pythrust/battery/state.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/battery/state.py`
SHA-256: `cc8e66287d1d5fe937772567599f5f678421a5047ebf69f058c9d7199674603b`


## original_hopper/PyThrust/pythrust/motors/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/motors/__init__.py`
SHA-256: `c2b6c75ea068e4686e10a3d52cdf1258ceefb641e84e0e25e60e4cd0256a48ad`


## original_hopper/PyThrust/pythrust/motors/database.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/motors/database.py`
SHA-256: `4cbd82fe126591ab368307942fb4fd5d134f0c364526ed65d47fee40cf8ad327`


## original_hopper/PyThrust/pythrust/openmdao/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/openmdao/__init__.py`
SHA-256: `d382c68c2478e7c4e4ec149c314cd0603fa7b34833ed649b04cafc4bbd08500c`


## original_hopper/PyThrust/pythrust/openmdao/components.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/openmdao/components.py`
SHA-256: `f8f15cc69aebe1a4c3ba6cde6aba7d6473b6a2c1724a035729042c9602cf25fb`


## original_hopper/PyThrust/pythrust/propellers/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propellers/__init__.py`
SHA-256: `a063d129ab7dd6c4c2526e2ed0db810bcb551b114646c9c4fbdd958b3eb8a8d1`


## original_hopper/PyThrust/pythrust/propellers/database.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propellers/database.py`
SHA-256: `0023cea3d22f8f68e77742ab59f51fec6c745c920ee0d38ac47a6ba7d4a5d495`


## original_hopper/PyThrust/pythrust/propulsion/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/__init__.py`
SHA-256: `dcea13fc967933551ba327adedb276e7fd5ec0ae763590c6da0f4043d9f58878`


## original_hopper/PyThrust/pythrust/propulsion/autotune.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/autotune.py`
SHA-256: `9842a77c083007c7263e2031d3bb5218b5a5d4975ae70f01df0df37fd3ccb8ef`


## original_hopper/PyThrust/pythrust/propulsion/models/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/models/__init__.py`
SHA-256: `b6f7c6c27fc75acfa4a2b385ab12acd31503a2b56f414da3ca48ed0088060160`


## original_hopper/PyThrust/pythrust/propulsion/models/battery.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/models/battery.py`
SHA-256: `fc019ccf294f92c981b36e3f45afba0a17bb3c791865b5dde10aaf14d615840f`


## original_hopper/PyThrust/pythrust/propulsion/models/motor.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/models/motor.py`
SHA-256: `4d9f0b5ca53b0f2689e29d07b7c96cdf710b60f28f74d0fba7c46f4bc9c082e8`


## original_hopper/PyThrust/pythrust/propulsion/models/operating_point.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/models/operating_point.py`
SHA-256: `f0f307cb6fe2f6f35a36b69cff73a11f429dcc5347afb7b962cf741989cd2812`


## original_hopper/PyThrust/pythrust/propulsion/models/propeller.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/models/propeller.py`
SHA-256: `75ada146f733da0a18034214ceaf40b2d12e7dfdfe85e54b060ba9d291b06569`


## original_hopper/PyThrust/pythrust/propulsion/models/system.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/models/system.py`
SHA-256: `a945a9295f3e89f03ece21055fef7426fb8a15a3d9262bc97b218a0c473175b4`


## original_hopper/PyThrust/pythrust/propulsion/solver.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/pythrust/propulsion/solver.py`
SHA-256: `f8e12261294e0e3e787ca69714aa45f523574b9189b645a3f290196527c17a3f`

- Dynamic-site review: line 391, `getattr`.
- Dynamic-site review: line 401, `getattr`.

## original_hopper/PyThrust/scripts/convert_apc_dat.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/scripts/convert_apc_dat.py`
SHA-256: `14a27e3e51f165c6e431090ef074540e44b821bc42c146231918a9bdc7b63d3b`


## original_hopper/PyThrust/scripts/generate_readme_plots.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/scripts/generate_readme_plots.py`
SHA-256: `71320bca98c2356650f53957e27ba2691a72bdaed9637f5d8f58311dfed2367c`


## original_hopper/PyThrust/tests/test_autotune.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/tests/test_autotune.py`
SHA-256: `f011064031bb78ee71373f81e822a98164c5d2296526c66daeecb42fe810cbce`


## original_hopper/PyThrust/tests/test_battery.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/tests/test_battery.py`
SHA-256: `02b7d10105c621a182e4aa4c541f398968edc8446f9909c6aa520848b7ce37d0`

- Dynamic-site review: line 492, `getattr`.

## original_hopper/PyThrust/tests/test_models.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/tests/test_models.py`
SHA-256: `469ea6b0fcd9c79bd29557cb6e26b450b819a881b3f2fded9a8879cf0a774786`


## original_hopper/PyThrust/tests/test_motors.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/tests/test_motors.py`
SHA-256: `b702785653608de62a57872bc8803838d78b7cda6340e715fdfaf63ecb5f8de4`


## original_hopper/PyThrust/tests/test_openmdao.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/tests/test_openmdao.py`
SHA-256: `3bafafb878552fdd90b567c03945223d1ac4d1c3a91d108804404dc6136d8f8d`


## original_hopper/PyThrust/tests/test_propellers.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/tests/test_propellers.py`
SHA-256: `ecb31f2eb600bcc23b6b4a03a2ae6b51beef107034e99a3d3a796ba41fe35c54`


## original_hopper/PyThrust/tests/test_solver.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/PyThrust/tests/test_solver.py`
SHA-256: `fb86891911b4a7b9e758ef5762d6b5320682568d8eab04cc878fb797bb884b09`


## original_hopper/aero/aero.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/aero/aero.py`
SHA-256: `9008c26ea2c2c26e1e26441ee17f27872e1d34bf1c0d9cb7179ce285d6e2b53f`


## original_hopper/chassis/hopper.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/chassis/hopper.py`
SHA-256: `6e2b2f93e98b844ce04f68d26b704c65270e9329e1abff76caa45cbcd5dcf0bd`

- Lines 46-46: `Hopper.mass` calls `self.propulsion.get_mass`.
- Lines 58-58: `Hopper.get_thrust_and_moment` calls `self.propulsion.get_thrust_and_moment`.
- Symbol-reference locations: 13 Hopper -> Propulsion; 46 Hopper.mass -> self.propulsion.get_mass; 58 Hopper.get_thrust_and_moment -> self.propulsion.get_thrust_and_moment
- Dynamic-site review: line 39, `getattr`.

## original_hopper/helpers/constants.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/helpers/constants.py`
SHA-256: `4853ae63f4d7df5254af6fbab9b46dd31ca60aa722dd3580643064bfce9523a4`


## original_hopper/helpers/math.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/helpers/math.py`
SHA-256: `5e6420ade1c4d642762ba4d6b0812a80f2f693a58151bbf16a4274efb521239a`


## original_hopper/main.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/main.py`
SHA-256: `67ebbf79c219721eb1f0cc6e4817b8fb218488b6dec4bbd25a1f0faee6527dbc`


## original_hopper/propulsion/propeller.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/propulsion/propeller.py`
SHA-256: `caa5ee91e46d102b8ebe0c02e1dfec0ecdca18e2c423791fca6f2c19100ae7b6`

- Symbol-reference locations: 4 Propellor -> Propulsion

## original_hopper/propulsion/propulsion.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/propulsion/propulsion.py`
SHA-256: `e07b895d8399016a3b0511afb195d7ebf992050cef04ab3015600347f01750ce`


## original_hopper/scripts/ehopper.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/scripts/ehopper.py`
SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`


## original_hopper/simulation/simulation.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/simulation/simulation.py`
SHA-256: `087767eef40f728775d5bd8ee597a6e0a8c0769fe4d2d6ab2a060d06692f86ca`

- Lines 17-17: `Simulation.trajectory_ode` calls `self.state.update_state`.
- Lines 37-37: `Simulation.trajectory_ode` calls `quarternion_to_dcm`.
- Lines 91-91: `Simulation.trajectory_ode` calls `self.hopper.mass`.
- Lines 92-92: `Simulation.trajectory_ode` calls `self.hopper.CG`.
- Lines 93-93: `Simulation.trajectory_ode` calls `self.hopper.inertia`.
- Lines 96-96: `Simulation.trajectory_ode` calls `self.hopper.get_thrust_and_moment`.
- Lines 98-105: `Simulation.trajectory_ode` calls `self.aero.determine_at_point`.
- Lines 134-134: `Simulation.solve_ode` calls `euler_to_quaternion`.
- Lines 142-142: `Simulation.solve_ode` calls `State`.
- Lines 144-153: `Simulation.solve_ode` calls `solve_ivp`.
- Symbol-reference locations: 9 Simulation.__init__ -> State; 17 Simulation.trajectory_ode -> self.state.update_state; 37 Simulation.trajectory_ode -> quarternion_to_dcm; 91 Simulation.trajectory_ode -> self.hopper.mass; 92 Simulation.trajectory_ode -> self.hopper.CG; 93 Simulation.trajectory_ode -> self.hopper.inertia; 96 Simulation.trajectory_ode -> self.hopper.get_thrust_and_moment; 98 Simulation.trajectory_ode -> self.aero.determine_at_point; 118 Simulation.trajectory_ode -> mass; 125 Simulation.trajectory_ode -> inertia; 126 Simulation.trajectory_ode -> inertia; 134 Simulation.solve_ode -> euler_to_quaternion; 142 Simulation.solve_ode -> State; 144 Simulation.solve_ode -> solve_ivp; 145 Simulation.solve_ode -> self.trajectory_ode

## original_hopper/simulation/state.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/simulation/state.py`
SHA-256: `7b8713aecd017a7ff1f0b3ad4e14e1c63c716d1181a6df516d25b7a7d1973b2a`


## original_hopper/test/__init__.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/test/__init__.py`
SHA-256: `d72bcd69d0ed6d706e690574d1dbdedf15ab740d5ce705aad834bd1b91b3d76e`


## original_hopper/test/test_pythrust.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/6dof_hopper/test/test_pythrust.py`
SHA-256: `a3590eef1c8b2d922a54464d7254205ca046c4af4e42f4bde815a67cec690a0d`


## pendulum_reference/src/gui.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/PendulumControlProject/src/gui.py`
SHA-256: `e53b845c05025f4039b1c34f02766fc58fb96afd6bb117867467c5e4fc51cecc`

- Symbol-reference locations: 329 PendulumSimulator.run_simulation -> mass; 331 PendulumSimulator.run_simulation -> mass

## pendulum_reference/src/main.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/PendulumControlProject/src/main.py`
SHA-256: `016c59131bf7f5d0360616a0b8dbb19033d0524bd610694e116faf968b1d8b30`

- Symbol-reference locations: 35 main -> mass; 37 main -> mass; 52 main -> pendulum.mass; 55 main -> pendulum.mass

## pendulum_reference/src/pendulum_model.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/tooling/PendulumControlProject/src/pendulum_model.py`
SHA-256: `b2aca9be8e608d8cb701407998ee26a7e6e62a51ed41be93660e3cf4caf39d50`

- Lines 21-21: `NonlinearPendulum.integrate_step` calls `solve_ivp`.
- Lines 25-25: `NonlinearPendulum.simulate` calls `solve_ivp`.
- Lines 43-43: `LinearizedPendulum.integrate_step` calls `solve_ivp`.
- Lines 47-47: `LinearizedPendulum.simulate` calls `solve_ivp`.
- Lines 92-92: `NonlinearDoublePendulum.integrate_step` calls `solve_ivp`.
- Lines 96-96: `NonlinearDoublePendulum.simulate` calls `solve_ivp`.
- Lines 128-128: `LinearizedDoublePendulum.integrate_step` calls `solve_ivp`.
- Lines 132-132: `LinearizedDoublePendulum.simulate` calls `solve_ivp`.
- Symbol-reference locations: 9 NonlinearPendulum.__init__ -> mass; 17 NonlinearPendulum.equations_of_motion -> self.mass; 21 NonlinearPendulum.integrate_step -> solve_ivp; 25 NonlinearPendulum.simulate -> solve_ivp; 31 LinearizedPendulum.__init__ -> mass; 39 LinearizedPendulum.equations_of_motion -> self.mass; 43 LinearizedPendulum.integrate_step -> solve_ivp; 47 LinearizedPendulum.simulate -> solve_ivp; 92 NonlinearDoublePendulum.integrate_step -> solve_ivp; 96 NonlinearDoublePendulum.simulate -> solve_ivp; 128 LinearizedDoublePendulum.integrate_step -> solve_ivp; 132 LinearizedDoublePendulum.simulate -> solve_ivp

## historical_r9/analytical_fixture_models_01.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/analytical_fixture_models_01.py`
SHA-256: `6921f11f48f66abebe55943436662b6df3746c886641efd0a8b9e77369373524`

- Lines 189-189: `PrescribedFixtureEnvironment.from_config` calls `AppliedLoad`.
- Lines 193-196: `PrescribedFixtureEnvironment.from_config` calls `EnvironmentSample`.
- Lines 335-345: `SyntheticPairedMap.evaluate` calls `CoaxialPerformance`.
- Lines 352-357: `initial_snapshots` calls `State.from_euler`.
- Lines 358-362: `initial_snapshots` calls `ActuatorState`.
- Lines 374-374: `build_fixture` calls `MassProperties`.
- Lines 375-380: `build_fixture` calls `Hopper`.
- Lines 377-377: `build_fixture` calls `FrozenFixtureMass`.
- Lines 381-384: `build_fixture` calls `Propellor`.
- Lines 382-382: `build_fixture` calls `CoaxialGeometry`.
- Lines 385-394: `build_fixture` calls `Simulation`.
- Lines 388-388: `build_fixture` calls `LaggedActuators`.
- Lines 388-388: `build_fixture` calls `LagParameters`.
- Symbol-reference locations: 144 FrozenFixtureMass -> MassProperties; 147 FrozenFixtureMass.__post_init__ -> MassProperties; 155 FrozenFixtureMass.snapshot -> AssemblyKinematics; 175 PrescribedFixtureEnvironment -> EnvironmentSample; 178 PrescribedFixtureEnvironment.__post_init__ -> EnvironmentSample; 189 PrescribedFixtureEnvironment.from_config -> AppliedLoad; 193 PrescribedFixtureEnvironment.from_config -> EnvironmentSample; 202 PrescribedFixtureEnvironment.sample -> State; 204 PrescribedFixtureEnvironment.sample -> MassProperties; 204 PrescribedFixtureEnvironment.sample -> mass_properties; 206 PrescribedFixtureEnvironment.sample -> mass_properties; 208 PrescribedFixtureEnvironment.sample -> AssemblyKinematics; 311 SyntheticPairedMap.evaluate -> AssemblyKinematics; 313 SyntheticPairedMap.evaluate -> CoaxialConditions; 335 SyntheticPairedMap.evaluate -> CoaxialPerformance; 352 initial_snapshots -> State; 352 initial_snapshots -> State.from_euler; 358 initial_snapshots -> ActuatorState; 374 build_fixture -> MassProperties; 375 build_fixture -> Hopper; 377 build_fixture -> FrozenFixtureMass; 381 build_fixture -> Propellor; 382 build_fixture -> CoaxialGeometry; 383 build_fixture -> SyntheticPairedMap; 385 build_fixture -> Simulation; 388 build_fixture -> LagParameters; 388 build_fixture -> LaggedActuators; 389 build_fixture -> PrescribedFixtureEnvironment
- Dynamic-site review: line 257, `getattr`.
- Dynamic-site review: line 261, `getattr`.

## historical_r9/audit_sources.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/audit_sources.py`
SHA-256: `52a344e7f53cf56737bd2a0a6c50b9b3df583d1453397344fe0b10eb91826524`


## historical_r9/capability_probe_01.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/capability_probe_01.py`
SHA-256: `acd213cb5dc214ef1069a29439d15de201605649a7e30ac2d29084348d72209d`

- Lines 44-44: `<module>` calls `snapshot`.
- Lines 93-93: `<module>` calls `snapshot`.
- Symbol-reference locations: 44 <module> -> snapshot; 93 <module> -> snapshot
- Dynamic-site review: line 60, `importlib.import_module`.
- Dynamic-site review: line 61, `getattr`.

## historical_r9/repaired_hopper/chassis/hopper.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/chassis/hopper.py`
SHA-256: `2c2b09a5993ccedea61cf543fe2f342f079a646d877bf65cba19dc302ae39432`

- Lines 271-271: `Hopper.mass_properties` calls `self.mass_property_provider.snapshot`.
- Symbol-reference locations: 223 MassProperties.angular_acceleration_B_rad_s2 -> inertia; 236 MassPropertyProvider.snapshot -> AssemblyKinematics; 236 MassPropertyProvider.snapshot -> MassProperties; 269 Hopper.mass_properties -> AssemblyKinematics; 271 Hopper.mass_properties -> self.mass_property_provider.snapshot; 272 Hopper.mass_properties -> MassProperties
- Dynamic-site review: line 111, `getattr`.
- Dynamic-site review: line 161, `getattr`.
- Dynamic-site review: line 186, `getattr`.
- Dynamic-site review: line 190, `getattr`.
- Dynamic-site review: line 262, `getattr`.

## historical_r9/repaired_hopper/helpers/math.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/helpers/math.py`
SHA-256: `7941782e298900bdbbe35383aaa376a9679e225b6e85247c191b3a53486755a6`

- Lines 83-83: `quaternion_derivative` calls `hamilton_product`.
- Lines 91-96: `euler_to_quaternion` calls `normalize_quaternion`.
- Lines 105-105: `quaternion_to_dcm` calls `normalize_quaternion`.
- Lines 126-126: `quarternion_to_dcm` calls `quaternion_to_dcm`.
- Lines 224-224: `fixed_datum_kinematics` calls `quaternion_to_dcm`.
- Symbol-reference locations: 83 quaternion_derivative -> hamilton_product; 91 euler_to_quaternion -> normalize_quaternion; 105 quaternion_to_dcm -> normalize_quaternion; 126 quarternion_to_dcm -> quaternion_to_dcm; 185 cad_inertia_to_body_kg_m2 -> inertia; 188 cad_inertia_to_body_kg_m2 -> inertia; 204 cad_inertia_to_body_kg_m2 -> inertia; 224 fixed_datum_kinematics -> quaternion_to_dcm

## historical_r9/repaired_hopper/propulsion/actuators.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/propulsion/actuators.py`
SHA-256: `04854da079bf83f5cdd15f06c03d76e2f451a86344fdbdd3fea7e2cb250d1ed1`

- Lines 422-430: `LaggedActuators.evaluate` calls `AssemblyKinematics`.
- Symbol-reference locations: 262 LagParameters.validate_state -> ActuatorState; 318 ActuatorEvaluation -> AssemblyKinematics; 326 ActuatorEvaluation.__post_init__ -> AssemblyKinematics; 345 ActuatorModel.evaluate -> ActuatorState; 378 LaggedActuators -> LagParameters; 381 LaggedActuators.__post_init__ -> LagParameters; 422 LaggedActuators.evaluate -> AssemblyKinematics
- Dynamic-site review: line 92, `getattr`.
- Dynamic-site review: line 108, `getattr`.
- Dynamic-site review: line 180, `getattr`.
- Dynamic-site review: line 184, `getattr`.
- Dynamic-site review: line 186, `getattr`.

## historical_r9/repaired_hopper/propulsion/propeller.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/propulsion/propeller.py`
SHA-256: `0d5eec44099bf6f34b0875893b37556ece5cd5bc43e845b55f06510c9c0ec7b5`

- Lines 105-105: `CoaxialGeometry.rotation_BM` calls `gimbal_to_body`.
- Lines 187-187: `Propellor.hub_velocities_relative_air_M_m_s` calls `quaternion_to_dcm`.
- Lines 188-188: `Propellor.hub_velocities_relative_air_M_m_s` calls `self.geometry.application_points_B0_m`.
- Lines 220-222: `Propellor.evaluate` calls `self.performance_map.evaluate`.
- Lines 228-228: `Propellor.evaluate` calls `self.geometry.application_points_B0_m`.
- Lines 233-241: `Propellor.evaluate` calls `AppliedLoad`.
- Symbol-reference locations: 102 CoaxialGeometry.rotation_BM -> AssemblyKinematics; 105 CoaxialGeometry.rotation_BM -> gimbal_to_body; 120 CoaxialGeometry.validate_spin_kinematics -> AssemblyKinematics; 132 Propellor -> Propulsion; 148 Propellor -> CoaxialGeometry; 152 Propellor.__post_init__ -> CoaxialGeometry; 178 Propellor.hub_velocities_relative_air_M_m_s -> State; 180 Propellor.hub_velocities_relative_air_M_m_s -> MassProperties; 180 Propellor.hub_velocities_relative_air_M_m_s -> mass_properties; 182 Propellor.hub_velocities_relative_air_M_m_s -> mass_properties; 187 Propellor.hub_velocities_relative_air_M_m_s -> quaternion_to_dcm; 188 Propellor.hub_velocities_relative_air_M_m_s -> self.geometry.application_points_B0_m; 197 Propellor.hub_velocities_relative_air_M_m_s -> mass_properties; 203 Propellor.hub_velocities_relative_air_M_m_s -> mass_properties; 213 Propellor.evaluate -> CoaxialConditions; 220 Propellor.evaluate -> self.performance_map.evaluate; 223 Propellor.evaluate -> CoaxialPerformance; 228 Propellor.evaluate -> self.geometry.application_points_B0_m; 233 Propellor.evaluate -> AppliedLoad
- Dynamic-site review: line 154, `getattr`.

## historical_r9/repaired_hopper/propulsion/propulsion.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/propulsion/propulsion.py`
SHA-256: `930f02ef368640a533ced862ff1868b7a11166698c90d57fc2214393207e6a60`

- Symbol-reference locations: 143 resolve_applied_loads -> MassProperties; 143 resolve_applied_loads -> mass_properties; 149 resolve_applied_loads -> AppliedLoad; 151 resolve_applied_loads -> mass_properties; 154 resolve_applied_loads -> mass_properties; 160 resolve_applied_loads -> mass_properties; 252 CoaxialPerformance -> CoaxialConditions; 263 CoaxialPerformance.__post_init__ -> CoaxialConditions; 332 CoaxialPerformanceMap.evaluate -> AssemblyKinematics; 333 CoaxialPerformanceMap.evaluate -> CoaxialConditions; 333 CoaxialPerformanceMap.evaluate -> CoaxialPerformance; 346 PropulsionEvaluation -> CoaxialPerformance; 347 PropulsionEvaluation -> AppliedLoad; 351 PropulsionEvaluation.__post_init__ -> CoaxialPerformance; 354 PropulsionEvaluation.__post_init__ -> AppliedLoad; 364 PropulsionEvaluation.wrench_about_cg -> mass_properties; 384 Propulsion.evaluate -> AssemblyKinematics; 385 Propulsion.evaluate -> CoaxialConditions
- Dynamic-site review: line 110, `getattr`.
- Dynamic-site review: line 131, `getattr`.
- Dynamic-site review: line 203, `getattr`.
- Dynamic-site review: line 217, `getattr`.
- Dynamic-site review: line 270, `getattr`.

## historical_r9/repaired_hopper/simulation/environment.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/simulation/environment.py`
SHA-256: `5bb0bbfbaeae12b59454b4bddbd44a4eefff1fb6abda3f7b8fd098f760edc976`

- Lines 164-175: `EnvironmentSample.coaxial_conditions` calls `CoaxialConditions`.
- Symbol-reference locations: 100 EnvironmentSample -> AppliedLoad; 136 EnvironmentSample.__post_init__ -> AppliedLoad; 164 EnvironmentSample.coaxial_conditions -> CoaxialConditions; 212 EnvironmentProvider.sample -> State; 213 EnvironmentProvider.sample -> MassProperties; 214 EnvironmentProvider.sample -> AssemblyKinematics; 215 EnvironmentProvider.sample -> EnvironmentSample
- Dynamic-site review: line 116, `getattr`.
- Dynamic-site review: line 127, `getattr`.
- Dynamic-site review: line 131, `getattr`.
- Dynamic-site review: line 142, `getattr`.

## historical_r9/repaired_hopper/simulation/simulation.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/simulation/simulation.py`
SHA-256: `4fd06f318503b66fef981277acb1e03de52c29b49c9d1e45147c4b0568b32981`

- Lines 115-115: `unpack_state` calls `State.from_vector`.
- Lines 116-116: `unpack_state` calls `ActuatorState.from_vector`.
- Lines 246-246: `Simulation.evaluate` calls `unpack_state`.
- Lines 247-249: `Simulation.evaluate` calls `self.actuator_model.evaluate`.
- Lines 270-270: `Simulation.evaluate` calls `self.hopper.mass_properties`.
- Lines 271-271: `Simulation.evaluate` calls `quaternion_to_dcm`.
- Lines 272-272: `Simulation.evaluate` calls `self.propulsion.geometry.application_points_B0_m`.
- Lines 278-281: `Simulation.evaluate` calls `self.environment_provider.sample`.
- Lines 288-291: `Simulation.evaluate` calls `self.propulsion.hub_velocities_relative_air_M_m_s`.
- Lines 296-298: `Simulation.evaluate` calls `self.propulsion.evaluate`.
- Lines 326-326: `Simulation.evaluate` calls `quaternion_derivative`.
- Lines 338-340: `Simulation.trajectory_ode` calls `self.evaluate`.
- Lines 416-416: `Simulation.solve_ode` calls `self.evaluate`.
- Lines 419-419: `Simulation.solve_ode.held_rhs` calls `self.trajectory_ode`.
- Lines 421-426: `Simulation.solve_ode` calls `solve_ivp`.
- Symbol-reference locations: 104 pack_state -> ActuatorState; 104 pack_state -> State; 115 unpack_state -> State; 115 unpack_state -> State.from_vector; 116 unpack_state -> ActuatorState; 116 unpack_state -> ActuatorState.from_vector; 131 PlantEvaluation -> State; 132 PlantEvaluation -> ActuatorState; 134 PlantEvaluation -> MassProperties; 135 PlantEvaluation -> EnvironmentSample; 143 PlantEvaluation.__post_init__ -> ActuatorState; 143 PlantEvaluation.__post_init__ -> State; 144 PlantEvaluation.__post_init__ -> MassProperties; 145 PlantEvaluation.__post_init__ -> EnvironmentSample; 189 Simulation -> Hopper; 190 Simulation -> Propellor; 192 Simulation -> EnvironmentProvider; 193 Simulation -> State; 194 Simulation -> ActuatorState; 199 Simulation.__post_init__ -> Hopper; 201 Simulation.__post_init__ -> Propellor; 203 Simulation.__post_init__ -> State; 205 Simulation.__post_init__ -> ActuatorState; 226 Simulation.__post_init__ -> LaggedActuators; 246 Simulation.evaluate -> unpack_state; 247 Simulation.evaluate -> self.actuator_model.evaluate; 270 Simulation.evaluate -> self.hopper.mass_properties; 271 Simulation.evaluate -> quaternion_to_dcm; 272 Simulation.evaluate -> self.propulsion.geometry.application_points_B0_m; 273 Simulation.evaluate -> mass; 278 Simulation.evaluate -> self.environment_provider.sample; 279 Simulation.evaluate -> mass; 282 Simulation.evaluate -> EnvironmentSample; 284 Simulation.evaluate -> mass; 288 Simulation.evaluate -> self.propulsion.hub_velocities_relative_air_M_m_s; 289 Simulation.evaluate -> mass; 296 Simulation.evaluate -> self.propulsion.evaluate; 308 Simulation.evaluate -> mass; 313 Simulation.evaluate -> mass; 319 Simulation.evaluate -> mass; 326 Simulation.evaluate -> quaternion_derivative; 332 Simulation.evaluate -> mass; 338 Simulation.trajectory_ode -> self.evaluate; 416 Simulation.solve_ode -> self.evaluate; 419 Simulation.solve_ode.held_rhs -> self.trajectory_ode; 421 Simulation.solve_ode -> solve_ivp
- Dynamic-site review: line 148, `getattr`.
- Dynamic-site review: line 210, `getattr`.
- Dynamic-site review: line 212, `getattr`.

## historical_r9/repaired_hopper/simulation/state.py

Read path: `/home/ngvnngkhoi/guacamole/examples/ehopper/results/software/pdr_r9_plant/repaired_hopper/simulation/state.py`
SHA-256: `3b5a37931c66e32c2f5bb4b68bd47b8da71417e31dfe11a4b06fddb1c4f62425`

- Lines 104-106: `State.from_euler` calls `euler_to_quaternion`.
- Lines 123-123: `State.from_body_velocity` calls `quaternion_to_dcm`.
- Lines 158-158: `State.velocity_G_B_m_s` calls `quaternion_to_dcm`.
- Lines 169-169: `State.with_normalized_orientation` calls `normalize_quaternion`.
- Symbol-reference locations: 104 State.from_euler -> euler_to_quaternion; 123 State.from_body_velocity -> quaternion_to_dcm; 158 State.velocity_G_B_m_s -> quaternion_to_dcm; 169 State.with_normalized_orientation -> normalize_quaternion

## Limitations

- Static candidate index, not a resolved runtime call graph or completed manual caller review.
- Generic method names may identify unrelated callers; inspect their actual implementations.
- Import-alias expansion is conservative and scope-insensitive; rebinding requires manual review.
- Dynamic calls, wildcard imports, generated code and callers outside the roots are not excluded.
- Symlinks are listed but not followed; relevant targets require separate inspection.
- Only Python and named setup/documentation files are hashed; binary/data files are outside this scope.
- Hash equality describes this audit interval, not historical checkout cleanliness.
- No dependency imports, original failure reproduction, plant execution or physical verification occur.
