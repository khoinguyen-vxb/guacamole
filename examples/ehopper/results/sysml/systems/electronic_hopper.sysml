package ElectronicHopper {
    private import ScalarValues::*;
    private import SI::*;

    doc /*
    Requirements and selected interface-convention model for the Electronic Hopper PDR scope.
    Requirements authority: context/brief.md, source 79626f8bf0b5472c8ba568b4311c0d68 r1,
    human budget clarification 49b30062efe1476d9a2faa01ee276653 r1,
    and human scoring-definition approval ea4eeff069b645a2bddfacac56bade5e r1.
    Selected interface conventions: Chief decision 17534e6b12854073a06a0471fec47a84 r1,
    candidate INTERFACE-NED-CG-FIXED-PLATE. Its supporting checkpoint is
    artifact PDR-PLANT-INTERFACE-CHECKPOINT-M2-01 r1; only the selected decision,
    not every checkpoint proposal, establishes the design contract recorded here.
    Work-plan decision a37ef3716fce4eb2b2b35919d6cb0b97 r1 defines the PDR work scope.
    Requirement documentation below reproduces the current recorded wording.
    All numerical assessment features are unassigned: requirements are not measured results.
    Selected conventions are not new requirements, verified interfaces or physical results.
    No component selection, verified design value or satisfy claim is established.
    Archived notes are unverified starting points, as stated by
    context/previous_run/README.md, source cedca4b22feb4a23b667cc67049eb339 r1.
    Their former decisions, verification claims and PDR/CDR gates are not current authority.
    Current scope includes simulator repair, PID integration and tuning, and repeatable
    mission simulation as PDR deliverables; CDR is outside this run.
    Neither the scoring-definition approval nor the interface decision is hardware
    validation or PDR acceptance.
    */

    attribute def AustralianDollarValue :> Quantities::ScalarQuantityValue {
        attribute :>> num : Real;
        attribute :>> mRef : AustralianDollarUnit;
    }
    attribute monetaryAmount : AustralianDollarValue :> Quantities::scalarQuantities;
    attribute def AustralianDollarUnit :> MeasurementReferences::SimpleUnit {
        private attribute monetaryPowerFactor : Quantities::QuantityPowerFactor {
            attribute :>> quantity = monetaryAmount;
            attribute :>> exponent = 1;
        }
        attribute :>> quantityDimension {
            attribute :>> quantityPowerFactors = monetaryPowerFactor;
        }
    }
    attribute <AUD> australianDollar : AustralianDollarUnit;
    attribute <'°/s'> degreePerSecond : ISQ::AngularVelocityUnit = '°' / s;

    part def HopperVehicle {
        doc /*
        Brief-established architecture, not a selected physical assembly.
        Exposed structure, battery and electronics are above the bottom coaxial
        propulsion and both rotors. Landing feet extend below the rotor plane.
        Integrated versus separate-motor topology, support load path, component
        quantities beyond the two propellers, dimensions and connections remain open.
        Mathematical frame, datum and gimbal conventions are selected separately
        in SelectedIntegrationContract; their implementation is not verified.
        No propeller diameter limit is specified by the brief.
        */
        attribute payload_mass :> ISQ::mass;
        attribute spine_count : Integer;
        attribute landing_leg_count : Integer;
        attribute gimbal_axis_count : Integer;
        attribute installed_mass :> ISQ::mass;
        part airframe {
            doc /* Exposed minimum structure; compare one through four spines and CFRP versus aluminium. No fins, nose cone or fairing. */
        }
        part coaxialPropulsion {
            doc /* Counter-rotating electric propulsion. Motor, propeller, ESC and module-topology selections remain open. Joint evaluation and external aerodynamic torque semantics are selected, but performance maps and physical spin assignments are not. */
            part propellers[2];
        }
        part commonGimbal {
            doc /* Common two-axis motor-unit thrust vectoring. Selected convention: outer alpha about body x, inner beta about carried y, R_BM=Rx(alpha)Ry(beta), with explicit separate origins. Numerical origin locations and separation, linkage, travel and loaded actuator capability remain undefined. No implementation satisfaction is claimed. */
        }
        part installedBattery {
            doc /* One battery flies; the complete required two-battery purchase pack is charged to procurement. Battery specification remains open. */
        }
        part electronics {
            doc /* Controller hardware remains open. Hardware protocols, sensors, supplies and mounting interfaces are not selected. */
        }
        part landingGear {
            doc /* Compare splayed thin-CFRP-tube tripod and quadpod legs attached just above the gimbal. Geometry and compliance remain open. The fixed attachment plate/ring provides the selected scoring-datum reference plane; its numerical geometry is not selected. */
        }
        port propulsionPowerInterface {
            doc /* Shared-bus and auxiliary-energy ownership must prevent double counting. Voltage, current, protection, regulation, connector and thermal ratings remain to be established. Battery-branch and motor-winding currents are distinct quantities. */
        }
        port propulsionCommandInterface {
            doc /* Selected semantics require realizable commands with explicit units, actual dynamic states, loaded mapping, response and limits. Protocol and calibration remain open. Recovered speed-demand lag alone is an analytical abstraction, not evidence of a realizable vehicle command interface. */
        }
        port gimbalCommandInterface {
            doc /* Selected semantics distinguish commanded and actual joint states, loaded response and saturation. Protocol, cadence, linkage, travel, loaded torque/speed capability and supply limits remain to be established. */
        }
    }

    part def ProcurementAssessment {
        attribute purchased_vehicle_hardware_materials_cost : AustralianDollarValue;
        doc /*
        Cost is expressed in AUD and quantized to 0.01 AUD under the human correction.
        Exclude tax and shipping. Assume nothing is owned; charge whole minimum
        purchase packs and spools. Buy the two-battery pack although one battery flies.
        Exclude PETG printed-part cost, not installed mass. Reusable ground equipment
        has a separate priced ledger. Unknown prices and quantities are not zero.
        Exact part numbers, dated vendor sources, currency, stock, tax treatment,
        shipping exclusions and any currency conversions require provenance.
        */
    }

    part def SimulationAssessment {
        attribute hover_target_rise :> ISQ::length;
        attribute hover_duration :> ISQ::duration;
        attribute altitude_rms_error :> ISQ::length;
        attribute altitude_max_absolute_error :> ISQ::length;
        attribute horizontal_radial_rms_error :> ISQ::length;
        attribute horizontal_radial_max_error :> ISQ::length;
        attribute attitude_recovery_total_error :> ISQ::angularMeasure;
        attribute attitude_recovery_body_rate_norm :> ISQ::angularVelocity;
        attribute attitude_recovery_time :> ISQ::duration;
        attribute attitude_recovery_hold_duration :> ISQ::duration;
        attribute contacting_foot_downward_speed :> ISQ::speed;
        attribute contacting_foot_horizontal_speed :> ISQ::speed;
        attribute landing_airframe_tilt :> ISQ::angularMeasure;
        doc /*
        These are unassigned simulation assessment quantities, not achieved values.
        Hover scoring uses a fixed airframe datum's rise and horizontal displacement
        from its stationary pre-takeoff position, not instantaneous CG translation.
        The selected design definition of datum D is recorded in
        SelectedIntegrationContract::fixedScoringDatum; its numerical CAD location
        and implementation remain outstanding. This selection changes no scoring limit.
        Acquisition completes at the end of the first continuous 2 s interval with
        absolute altitude error no greater than 0.25 m relative to the 5.00 m target
        rise and horizontal radial error no greater than 0.50 m simultaneously.
        Immediately thereafter, score one uninterrupted 300 s hover interval,
        without restarting it or excluding transients. Acquisition, climb and
        controlled landing are additional battery loads.
        Total attitude error is the shortest three-dimensional rotation angle between
        actual and reference attitudes, independent of quaternion sign, not the norm
        of Euler-angle errors. Attitude metrics cover every specified isolated and
        combined perturbation. The combined initialization is R = Ry(10 deg)Rx(10 deg),
        using active right-handed rotations relative to the hover reference: apply x
        first, then y, with zero initial body rates. The attitude and rate limits hold
        simultaneously for the same continuous two-second interval beginning within
        five seconds of initialization.
        Touchdown quantities are evaluated immediately before first foot contact on
        level ground, using the contacting foot rather than CG velocity.
        Simulation alone establishes neither hardware validity nor review acceptance.
        */
    }

    part def SelectedIntegrationContract {
        doc /*
        Selected design conventions and interface semantics authorized by Chief
        decision 17534e6b12854073a06a0471fec47a84 r1. These are not new requirement
        records, implemented interfaces, verified results or satisfaction claims.
        No hardware, numerical geometry, dynamics reduction, gains or additional
        acceptance thresholds are selected by this contract.
        */
        attribute local_frame : String = "North-East-Down";
        attribute airframe_frame : String = "Forward-Right-Down";
        attribute cad_frame : String = "Forward-Left-Up";
        attribute quaternion_convention : String = "scalar-first Hamilton q_LB=[w,x,y,z]";
        attribute rotation_mapping : String = "R_LB maps B components into local L";
        attribute translation_reference : String = "instantaneous complete-vehicle CG G";
        attribute gimbal_rotation_order : String = "R_BM=Rx(alpha)Ry(beta)";

        part stateAndFrameSemantics {
            doc /*
            Local L is the fixed launch NED frame. B is airframe-fixed FRD.
            Integrate instantaneous complete-vehicle CG position p_G,L [m] and
            velocity v_G,L [m/s], and airframe angular velocity omega_B [rad/s].
            Use scalar-first Hamilton q_LB and qdot_LB=0.5*q_LB tensor-product
            [0,omega_B]. R_LB maps body vectors into L. Named Euler initialization
            is in radians with R_LB=Rz(yaw)Ry(pitch)Rx(roll).
            Identity attitude is upright, forward north. Gravity is along local
            positive z and neutral rotor thrust is along module negative z.
            Preserve raw integrated quaternion samples; rotation-helper processing
            must not conceal their norm drift or replace the stored trajectory.
            Version state schemas and retain every initial and carried state.
            The recovered 19-state layout is a reuse candidate, not a mandatory
            vehicle state count or proof that its actuator realization is adequate.
            Controller memory updates occur outside adaptive RHS evaluations at
            fixed sample times, with commands held between samples. Integration
            steps and output sampling are not controller cadence. Actual endpoint,
            event and failure handling require implementation and independent tests.
            */
        }

        part fixedScoringDatum {
            doc /*
            Define fixed datum D as the intersection of the neutral propulsion
            centreline with the upper reference plane of the FIXED leg-attachment
            plate/ring. Store D as a named airframe-fixed CAD feature. It does not
            follow articulation or instantaneous CG. Its numerical CAD location
            D_C remains a design output; no coordinates are assigned here.
            CAD C is forward-left-up with a physically marked forward direction.
            For a CAD point p_C and datum D_C in mm, convert to body coordinates
            relative to D by r_B[m]=0.001*diag(1,-1,-1)*(p_C[mm]-D_C[mm]).
            Let r_DG be the vector from D to instantaneous G in B components,
            and rdot_DG its derivative in B components due to internal motion.
            Score p_D,L=p_G,L-R_LB*r_DG and
            v_D,L=v_G,L-R_LB*(omega_B cross r_DG+rdot_DG).
            Height rise and horizontal displacement retain the stationary
            pre-takeoff position of D as their reference.
            Acceleration conversion requires consistent rddot_DG:
            a_D,L=a_G,L-R_LB*(omegadot_B cross r_DG
            +omega_B cross (omega_B cross r_DG)
            +2*omega_B cross rdot_DG+rddot_DG),
            or a separately justified approximation. No such reduction is selected.
            The datum definition and transform convention are resolved, but numerical
            registration, derivative providers and implementation checks are not.
            */
        }

        part gimbalKinematics {
            doc /*
            Outer rotation alpha is about body x. Inner rotation beta is about
            carried y, with R_BM=Rx(alpha)Ry(beta). Angles use rad in the simulator.
            Represent outer origin r_DOx in B relative to D, outer-to-inner
            displacement d_OxOy in the outer frame, and module hub offsets
            r_Oyi,M in M relative to the inner origin. All translated lengths use m.
            For rotor i, r_Di=r_DOx+Rx(alpha)*d_OxOy+R_BM*r_Oyi,M.
            Differentiate the outer-to-inner offset using outer-axis motion only:
            alpha_dot*e_x cross (Rx(alpha)*d_OxOy).
            The module-offset derivative uses
            omega_MB,B=[alpha_dot,cos(alpha)*beta_dot,sin(alpha)*beta_dot].
            Do not apply inner-axis motion to the outer-to-inner offset.
            Coincident origins are a special geometry, not an implicit assumption.
            Stable upper/lower rotor identities follow their physical components.
            Spin signs refer to the same module positive-z axis; purchased CW/CCW
            labels require an explicit viewing convention. Physical spin and
            propeller assignments remain unselected.
            Selected mathematical axes do not establish numerical origin positions,
            pivot separation, bearing arrangement, linkage, travel or actuator sizing.
            */
        }

        part massMomentumOwnership {
            doc /*
            Use one consistent complete-vehicle mass/momentum interface about
            instantaneous G. Transfer fixed, outer-gimbal, inner/module and supported
            spinning-group ownership, neutral transforms, mass, centroid and full
            centroidal inertia. Each installed mass is counted once. Commercial
            mass overrides replace envelope-density mass rather than adding to it.
            Unknown component subdivisions, properties and membership remain unknown.
            All inertia tensors, angular velocity and relative angular momentum in
            the angular balance use B components and a consistent reference at G:
            I_G*omegadot_B=M_external,G-omega_B cross (I_G*omega_B+h_rel)
            -I_dot*omega_B-h_rel_dot.
            I_dot and h_rel_dot are derivatives of B components due to internal
            motion. CG offsets and their derivatives must match the same assembly
            kinematics used by thrust and fixed-datum conversions.
            Resolve each external point force and free couple once about G.
            Internal motor and servo reactions are not additional external
            whole-vehicle moments. If momentum terms depend on unknown accelerations,
            solve the coupling rather than treating them as independent inputs.
            Counter-rotation does not establish cancellation of spin momentum or
            gyroscopic effects. No rigid, prescribed-motion or reduced-articulated
            vehicle approximation is selected or verified by this convention.
            */
        }

        part propulsionAndActuation {
            doc /*
            Evaluate both actual rotors jointly, retaining density, hub-relative
            airflow, spacing and relevant electrical/thermal conditions and map domains.
            Distinguish thrust, external aerodynamic torque, motor-winding current,
            battery-branch current and transient electrical power. Keep separate
            thrust/torque interference and motor/ESC-response calibration parameters,
            provenance, uncertainty and unsupported quantities explicit.
            With nonnegative thrust T_i and aerodynamic drag magnitude Q_i and signed
            spin sigma_i about common module positive z:
            F_i,B=R_BM*[0,0,-T_i],
            tau_air,i,B=R_BM*[0,0,-sigma_i*Q_i],
            M_external,G=sum((r_Di-r_DG) cross F_i,B+tau_air,i,B)
            plus other external loads resolved once about G.
            Equal RPM or opposite spin alone establishes neither torque balance
            nor equal thrust. Do not double isolated-rotor thrust to claim coupled
            performance. Actual physical spin assignments and maps remain open.
            Motor/ESC and gimbal interfaces identify realizable commands, units,
            actual states, loaded response and saturation, and electrical/thermal
            operating limits. The recovered speed-demand lag remains an analytical
            abstraction until a realizable command model is supplied and tested.
            Shared-bus and auxiliary-energy ownership must prevent double counting;
            aerodynamic shaft power alone does not establish transient electrical
            energy. Hardware protocols, calibration, usable energy and loaded
            actuator capabilities remain unresolved.
            */
        }

        part implementationVerificationBoundary {
            doc /*
            Before interface acceptance, execute independent frame, noncommuting
            rotation, separated-origin, inertia/unit-conversion, wrench-shift and
            fixed-datum fixtures against actual artifacts. Implementation and
            independent verification remain outstanding; archived implementations,
            synthetic fixtures and CAD/backend capability observations are not
            verified vehicle interfaces or physical validity evidence.
            This contract adds no satisfy claims, including for gimbal_axis_count.
            It selects no dynamics reduction, gains, hardware, numerical mass
            properties, reserve, disturbance, contact/settling or solver threshold.
            Every existing requirement, bound, unit and approved scoring definition
            remains unchanged. Review acceptance is a separate human disposition.
            */
        }
    }

    port def CADSimulatorData {
        doc /*
        Selected transfer semantics under decision 17534e6b12854073a06a0471fec47a84 r1.
        Transfer complete installed mass, CG and full inertia from editable CAD,
        including fixed, outer-gimbal, inner/module and supported spinning-group
        ownership, neutral transforms and property provenance/uncertainty.
        Numerical geometry, group membership and mass properties remain outstanding.
        CAD C is forward-left-up; body B is forward-right-down. D is the named
        airframe-fixed feature defined by SelectedIntegrationContract::fixedScoringDatum.
        FreeCAD point lengths are mm; r_B[m]=0.001*diag(1,-1,-1)*(p_C[mm]-D_C[mm]).
        Export separate outer origin, outer-to-inner displacement and module offsets
        consistent with R_BM=Rx(alpha)Ry(beta); do not silently merge joint origins.
        Count installed components once. Commercial mass overrides replace rather
        than duplicate envelope-density mass, with unresolved subdivisions explicit.
        State the density, original units and reference point for each inertia.
        Raw uniform-density OCCT volume inertia in mm^5 converts to kg m^2 by
        multiplication by rho[kg/m^3]*1e-15. An inertia already expressed in
        kg mm^2 instead converts by 1e-6; these conversion stages are distinct.
        Rotate tensors with the declared rotation and apply reference-point shifts
        separately using the parallel-axis relation. Rotation alone is not a
        reference-point shift. These are selected data semantics, not computed
        masses/inertias or evidence that exported geometry implements them.
        */
    }

    part def EngineeringDeliverables {
        part vehicleCAD {
            doc /* Editable parametric FCStd, STEP and mounting/assembly drawings; actual-solid, interface, clearance and mass-property evidence required. */
        }
        part correctedSimulator {
            doc /* Preserve originals; deliver runnable repaired copy or patch, fixed-cadence PID, gains, limits, verification scripts and repeatable mission results. Implement and independently test the selected interface contract; do not replace verification with a convention declaration. */
        }
        port cadToSimulator : CADSimulatorData;
    }

    part projectContext {
        part vehicle : HopperVehicle;
        part procurement : ProcurementAssessment;
        part simulationAssessment : SimulationAssessment;
        part selectedIntegrationContract : SelectedIntegrationContract;
        part deliverables : EngineeringDeliverables;
        part operatingEnvironment {
            doc /* Calm air near sea level is qualitative. Numerical atmosphere, wind and disturbance envelopes remain unspecified. */
        }
        part reusableGroundEquipment {
            doc /* Priced separately from the vehicle cap; no equipment is assumed owned. This model does not select ground equipment. */
        }
    }

    requirement <'REQ-COAXIAL-PROPULSION'> coaxialPropulsionRequirement {
        doc /* The hopper shall take off, hold position and land using electric propulsion with counter-rotating coaxial propellers. This architecture does not select an integrated contra-rotating motor unit or a separate-motor implementation. */
        subject vehicle : HopperVehicle;
    }

    requirement <'REQ-COMMON-GIMBAL'> commonGimbalRequirement {
        doc /* Thrust vectoring shall use a common motor-unit gimbal with exactly two controlled rotational axes. The gimbal_axis_count shall equal 2. Changing this architecture requires human agreement. */
        subject vehicle : HopperVehicle;
        require constraint { vehicle.gimbal_axis_count == 2 }
    }

    requirement <'REQ-EXPOSED-STRUCTURE'> exposedStructureRequirement {
        doc /* The vehicle shall use exposed minimum structure only, with no fins, nose cone or fairing. A rocket-like appearance is not required. This is a hard vehicle-configuration constraint; changes require human agreement. */
        subject vehicle : HopperVehicle;
    }

    requirement <'REQ-HARDWARE-BUDGET'> hardwareBudgetRequirement {
        doc /* Total purchased vehicle hardware and materials cost, quantized to 0.01 AUD, shall not exceed 499.99 AUD, excluding tax and shipping. This is the human-authorized representation of the original strictly-below-500-AUD cap. All other accounting rules remain unchanged: assume everything is bought and nothing is already owned; charge whole minimum purchase packs and spools, including a two-battery pack although only one battery flies; price reusable ground equipment, including transmitter, charger or power supply, test and ground safety equipment, separately from the vehicle cap; exclude 3D-printed PETG parts from cost but include their installed mass. */
        subject procurement : ProcurementAssessment;
        require constraint { procurement.purchased_vehicle_hardware_materials_cost <= 499.99 [AUD] }
    }

    requirement <'REQ-HOVER-HEIGHT'> hoverHeightRequirement {
        doc /* For simulation acceptance only, hover_target_rise shall equal 5.00 m. Height shall be measured as the rise of a fixed airframe datum from its stationary pre-takeoff position, not the instantaneous CG. Horizontal position shall be relative to that datum's initial location. This equality constrains the target reference; achieved tracking errors are governed by the separate hover-error requirements. Simulation acceptance does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.hover_target_rise == 5.00 [m] }
    }

    requirement <'REQ-HOVER-DURATION'> hoverDurationRequirement {
        doc /* For simulation acceptance only, the hopper shall sustain hover after acquisition for an uninterrupted interval of at least 300 s. Acquisition is completed at the end of the first continuous 2 s interval during which the fixed airframe datum's absolute altitude error relative to its 5.00 m target rise is no greater than 0.25 m and its horizontal radial error relative to its stationary pre-takeoff location is no greater than 0.50 m simultaneously. Immediately after acquisition, score one uninterrupted 300 s hover interval without restarting it or excluding transients. Acquisition, climb and controlled landing are additional battery loads, not portions of the required hover interval. Simulation acceptance does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.hover_duration >= 300 [s] }
    }

    requirement <'REQ-HOVER-ALTITUDE-RMS'> hoverAltitudeRMSRequirement {
        doc /* For simulation acceptance only, altitude RMS error relative to the 5.00 m target rise of the fixed airframe datum from its stationary pre-takeoff position shall not exceed 0.10 m over the uninterrupted 300 s hover interval after acquisition, with no transient exclusions. Acquisition is completed at the end of the first continuous 2 s interval during which the datum's absolute altitude error is no greater than 0.25 m and its horizontal radial error relative to its stationary pre-takeoff location is no greater than 0.50 m simultaneously. The scored 300 s interval shall begin immediately after acquisition, without restarting it or excluding transients, as defined in REQ-HOVER-DURATION. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.altitude_rms_error <= 0.10 [m] }
    }

    requirement <'REQ-HOVER-ALTITUDE-MAX'> hoverAltitudeMaximumRequirement {
        doc /* For simulation acceptance only, maximum absolute altitude error relative to the 5.00 m target rise of the fixed airframe datum from its stationary pre-takeoff position shall not exceed 0.25 m over the uninterrupted 300 s hover interval after acquisition, with no transient exclusions. Acquisition is completed at the end of the first continuous 2 s interval during which the datum's absolute altitude error is no greater than 0.25 m and its horizontal radial error relative to its stationary pre-takeoff location is no greater than 0.50 m simultaneously. The scored 300 s interval shall begin immediately after acquisition, without restarting it or excluding transients, as defined in REQ-HOVER-DURATION. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.altitude_max_absolute_error <= 0.25 [m] }
    }

    requirement <'REQ-HOVER-HORIZONTAL-RMS'> hoverHorizontalRMSRequirement {
        doc /* For simulation acceptance only, horizontal radial RMS position error of the fixed airframe datum relative to its stationary pre-takeoff horizontal location shall not exceed 0.25 m over the uninterrupted 300 s hover interval after acquisition, with no transient exclusions. Acquisition is completed at the end of the first continuous 2 s interval during which the datum's absolute altitude error relative to its 5.00 m target rise is no greater than 0.25 m and its horizontal radial error relative to its stationary pre-takeoff location is no greater than 0.50 m simultaneously. The scored 300 s interval shall begin immediately after acquisition, without restarting it or excluding transients, as defined in REQ-HOVER-DURATION. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.horizontal_radial_rms_error <= 0.25 [m] }
    }

    requirement <'REQ-HOVER-HORIZONTAL-MAX'> hoverHorizontalMaximumRequirement {
        doc /* For simulation acceptance only, maximum horizontal radial position error of the fixed airframe datum relative to its stationary pre-takeoff horizontal location shall not exceed 0.50 m over the uninterrupted 300 s hover interval after acquisition, with no transient exclusions. Acquisition is completed at the end of the first continuous 2 s interval during which the datum's absolute altitude error relative to its 5.00 m target rise is no greater than 0.25 m and its horizontal radial error relative to its stationary pre-takeoff location is no greater than 0.50 m simultaneously. The scored 300 s interval shall begin immediately after acquisition, without restarting it or excluding transients, as defined in REQ-HOVER-DURATION. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.horizontal_radial_max_error <= 0.50 [m] }
    }

    requirement <'REQ-ATTITUDE-RECOVERY-ERROR'> attitudeRecoveryErrorRequirement {
        doc /* For simulation acceptance only, each isolated 10 deg roll, pitch and yaw perturbation and the combined 10 deg roll plus 10 deg pitch perturbation, starting at zero body rates, shall recover to total attitude error no greater than 2 deg within 5 s and remain within that limit for 2 s, concurrently with the required body-rate limit. Total attitude error is the shortest three-dimensional rotation angle between actual and reference attitudes, independent of quaternion sign, not the norm of Euler-angle errors. The combined perturbation is R = Ry(10 deg)Rx(10 deg), using active right-handed rotations relative to the hover reference: apply the x rotation first, then y, with zero initial body rates. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.attitude_recovery_total_error <= 2 ['°'] }
    }

    requirement <'REQ-ATTITUDE-RECOVERY-RATE'> attitudeRecoveryRateRequirement {
        doc /* For simulation acceptance only, each isolated 10 deg roll, pitch and yaw perturbation and the combined 10 deg roll plus 10 deg pitch perturbation, starting at zero body rates, shall recover to body-rate norm no greater than 2 deg/s within 5 s and remain within that limit for 2 s, concurrently with the required total attitude-error limit. Total attitude error is the shortest three-dimensional rotation angle between actual and reference attitudes, independent of quaternion sign, not the norm of Euler-angle errors. The combined perturbation is R = Ry(10 deg)Rx(10 deg), using active right-handed rotations relative to the hover reference: apply the x rotation first, then y, with zero initial body rates. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.attitude_recovery_body_rate_norm <= 2 ['°/s'] }
    }

    requirement <'REQ-ATTITUDE-RECOVERY-TIME'> attitudeRecoveryTimeRequirement {
        doc /* For simulation acceptance only, each isolated 10 deg roll, pitch and yaw perturbation and the combined 10 deg roll plus 10 deg pitch perturbation, starting at zero body rates, shall have an attitude_recovery_time no greater than 5 s. Recovery time is measured from perturbation initialization to the start of a continuous 2 s interval during which total attitude error remains no greater than 2 deg and body-rate norm remains no greater than 2 deg/s simultaneously. Total attitude error is the shortest three-dimensional rotation angle between actual and reference attitudes, independent of quaternion sign, not the norm of Euler-angle errors. The combined perturbation is R = Ry(10 deg)Rx(10 deg), using active right-handed rotations relative to the hover reference: apply the x rotation first, then y, with zero initial body rates. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.attitude_recovery_time <= 5 [s] }
    }

    requirement <'REQ-ATTITUDE-RECOVERY-HOLD'> attitudeRecoveryHoldRequirement {
        doc /* For simulation acceptance only, each isolated 10 deg roll, pitch and yaw perturbation and the combined 10 deg roll plus 10 deg pitch perturbation, starting at zero initial body rates, shall achieve a continuous attitude_recovery_hold_duration of at least 2 s during which total attitude error remains no greater than 2 deg and body-rate norm remains no greater than 2 deg/s simultaneously. This interval shall begin within 5 s of perturbation initialization. Total attitude error is the shortest three-dimensional rotation angle between actual and reference attitudes, independent of quaternion sign, not the norm of Euler-angle errors. The combined perturbation is R = Ry(10 deg)Rx(10 deg), using active right-handed rotations relative to the hover reference: apply the x rotation first, then y, with zero initial body rates. This does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.attitude_recovery_hold_duration >= 2 [s] }
    }

    requirement <'REQ-LANDING-DOWNWARD-SPEED'> landingDownwardSpeedRequirement {
        doc /* For simulation acceptance only, during landing on level ground, the contacting foot's downward speed immediately before first foot contact shall not exceed 0.30 m/s. This is a foot-point velocity criterion, not a CG velocity criterion, and does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.contacting_foot_downward_speed <= 0.30 ['m/s'] }
    }

    requirement <'REQ-LANDING-HORIZONTAL-SPEED'> landingHorizontalSpeedRequirement {
        doc /* For simulation acceptance only, during landing on level ground, the contacting foot's horizontal speed immediately before first foot contact shall not exceed 0.20 m/s. This is a foot-point velocity criterion, not a CG velocity criterion, and does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.contacting_foot_horizontal_speed <= 0.20 ['m/s'] }
    }

    requirement <'REQ-LANDING-TILT'> landingTiltRequirement {
        doc /* For simulation acceptance only, during landing on level ground, airframe tilt immediately before first foot contact shall not exceed 5 deg. This criterion concerns airframe tilt, not gimbal deflection, and does not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
        require constraint { assessment.landing_airframe_tilt <= 5 ['°'] }
    }

    requirement <'REQ-LANDING-CONTACT-CLEARANCE'> landingContactClearanceRequirement {
        doc /* For simulation acceptance only, both rotor envelopes shall remain clear throughout landing approach and settling. The simulation shall explicitly model contact stiffness and leg compression and evaluate uneven-ground sensitivity. The separately recorded touchdown speed and airframe-tilt limits apply to landing on level ground. Simulation results do not establish hardware validation or review acceptance. */
        subject assessment : SimulationAssessment;
    }

    requirement <'REQ-LANDING-GEAR-ARRANGEMENT'> landingGearArrangementRequirement {
        doc /* The landing legs shall be splayed thin CFRP tubes attached at a ring or plate just above the common gimbal. The feet shall sit below the propeller plane, the stance shall be wider than the propeller disc, and both rotor envelopes shall remain clear of the ground at full gimbal tilt. Compare tripod and quadpod arrangements and recommend one using CAD-derived mass, CG and clearance results. These are hard vehicle-configuration constraints; changes require human agreement. */
        subject vehicle : HopperVehicle;
    }

    requirement <'REQ-LANDING-LEG-COUNT'> landingLegCountRequirement {
        doc /* The vehicle shall have an integer landing_leg_count of three or four, forming a tripod or quadpod respectively. Compare both configurations and recommend one using CAD-derived mass, CG and clearance results. Changing these permitted configurations requires human agreement. */
        subject vehicle : HopperVehicle;
        require constraint { vehicle.landing_leg_count >= 3 and vehicle.landing_leg_count <= 4 }
    }

    requirement <'REQ-SPINE-COUNT'> spineCountRequirement {
        doc /* The vehicle shall have an integer spine_count from one through four inclusive. Select and justify the count based on mounting the battery, avionics, gimbal and legs and on structural need. Compare CFRP tube with aluminium, retaining the stated preference for CFRP. Changing the permitted configuration requires human agreement. */
        subject vehicle : HopperVehicle;
        require constraint { vehicle.spine_count >= 1 and vehicle.spine_count <= 4 }
    }

    requirement <'REQ-ZERO-PAYLOAD'> zeroPayloadRequirement {
        doc /* The hopper shall be a zero-payload demonstrator, with payload_mass equal to 0 kg. */
        subject vehicle : HopperVehicle;
        require constraint { vehicle.payload_mass == 0 [kg] }
    }

    requirement <'REQ-OPERATING-ENVIRONMENT'> operatingEnvironmentRequirement {
        doc /* The hopper demonstrator shall be designed and assessed for operation in calm air near sea level. Numerical atmospheric conditions and wind limits are not established by this qualitative operating condition; simulation disturbance cases shall not silently redefine the operating envelope. */
        subject vehicle : HopperVehicle;
    }

    requirement <'REQ-PROPULSION-PLACEMENT'> propulsionPlacementRequirement {
        doc /* The coaxial propulsion module and both propellers shall sit at the bottom, below the structure. The structure, battery and electronics shall sit above the rotors. This placement is a hard vehicle-configuration constraint; changes require human agreement. It shall be implemented together with the brief's landing-leg arrangement, whose feet extend below the propeller plane. */
        subject vehicle : HopperVehicle;
    }

    requirement <'REQ-PROPULSION-BUDGET'> propulsionBudgetRequirement {
        doc /* Select the motors, counter-rotating coaxial propellers, ESCs and battery using a traceable integrated thrust, torque, current, energy, installed-mass and purchased-cost budget. Include the installed battery and acquisition, climb and landing energy in addition to the uninterrupted 300 s hover. Keep coaxial interference and calibration uncertainty explicit, and record current vendor sources and access dates. Assess cost under REQ-HARDWARE-BUDGET; do not treat isolated-rotor data as demonstrated combined coaxial performance. */
        subject vehicle : HopperVehicle;
    }

    requirement <'REQ-VEHICLE-CAD'> vehicleCADRequirement {
        doc /* Design the vehicle using the supplied freecad-mcp and deliver an editable parametric FCStd assembly, STEP exports and mounting/assembly drawings. Include propulsion support, battery and electronics mounts, the common gimbal and landing legs. Transfer vehicle mass, CG and inertia to the simulator with documented units and coordinate conventions. Archived geometry and successful CAD execution alone do not establish geometry acceptance. */
        subject deliverables : EngineeringDeliverables;
    }

    requirement <'REQ-SIMULATOR-PID'> simulatorPIDRequirement {
        doc /* Diagnose and repair the supplied tooling/6dof_hopper simulator before integrating and tuning PID control. The integrated controller shall include actuator limits, lag, anti-windup and fixed control sampling. Deliver a runnable modified copy or patch, gain configuration, verification scripts and repeatable takeoff, hover and landing results. Evaluate simulation performance against the separately recorded acceptance requirements; software execution alone does not establish hardware performance or review acceptance. */
        subject deliverables : EngineeringDeliverables;
    }

    requirement <'REQ-PDR-DELIVERY-PRESERVATION'> pdrDeliveryPreservationRequirement {
        doc /* This run shall deliver the PDR package for the propulsion-selection, vehicle-CAD and repaired simulator with integrated and tuned PID scope specified in the brief. Supplied checkouts shall remain unchanged. Runnable corrected copies, CAD, analyses and logs shall be placed in results/, and generated outputs and actual verification evidence shall be registered in project history. CDR shall follow only after PDR acceptance and is not a deliverable of this run. */
        subject deliverables : EngineeringDeliverables;
    }

    comment /*
    Unresolved inputs retained from the current requirement records, partitioned
    from convention portions resolved by Chief decision 17534e6b12854073a06a0471fec47a84 r1:
    - Complete component selection, installed-mass accounting, minimum purchase
      quantities, current tax-exclusive AUD prices and supported exchange rates.
    - Integrated/separate motor topology, stationary support load path, mounting
      drawings, physical rotor spin/viewing assignments and propeller retention.
      The common-axis sign convention is selected, not the physical assignments.
    - Coupled coaxial thrust/torque/current maps and domains, interference calibration,
      loaded motor/ESC response, thermal capability, voltage sag and usable energy.
      Joint-evaluation and ownership semantics do not establish these data.
    - Thrust and energy reserves: no numerical thresholds are authorized.
    - Numerical gimbal origin positions and separation, linkage geometry, travel,
      actuator selection, loaded torque/speed/response, saturation and supply limits.
      Outer-body-x/inner-carried-y axes and Rx(alpha)Ry(beta) are selected conventions;
      they do not resolve the remaining compound geometry and capability unknowns.
    - Structural dimensions, joints, densities and material properties; selected
      spine and leg counts; actual-solid CAD, clearance and mass-property evidence.
    - Full rotor envelopes, deformation/tolerances and ground-clearance allowances;
      stance-width definition, leg compliance and asymmetric contact behaviour.
    - Numerical definition of calm air/near sea level and atmospheric uncertainty.
    - Numerical location and CAD realization of fixed datum D, marked-forward
      registration, actual group membership and neutral/articulated mass properties,
      CG derivatives, full inertia and internal momentum providers.
      Datum definition, coordinate directions, transformation and ownership semantics
      are selected; numerical exports and their verification remain outstanding.
    - Contact stiffness, damping, friction, leg compression, uneven-ground cases,
      settling interval and completion criteria.
    - Control hardware, realizable command protocols, sample cadence, gains,
      disturbances, saturation-recovery criteria and numerical solver tolerances.
    - Implementation and independent verification of the selected interfaces,
      including acceleration-dependent coupling; no vehicle dynamics reduction
      is selected by the interface decision.
    The acquisition rule, combined-perturbation rotation order and total-attitude-error
    definition are resolved by human approval ea4eeff069b645a2bddfacac56bade5e r1
    and the corresponding current requirement records; they are no longer unknowns.
    SelectedIntegrationContract and CADSimulatorData record only the convention
    portions resolved by the Chief. They do not close entire compound unknowns
    in the originating requirement records or establish any satisfaction claim.
    Other archived numerical proposals remain proposals, not requirements or selected
    values. No missing input is represented by an invented zero or test pass.
    */
}
