# Tilt-servo candidate evidence

Access date: 2026-10-01. Preliminary research only; no hardware selection or acceptance. Website text inspected, not images, drawings or linked CAD.

## RCDrone comparison listing

[RCDrone DS3235 listing](https://rcdrone.top/products/dsservo-ds3235-waterproof-servo), price/status and Specifications sections: USD 24.49 each, taxes included. Sold-out text conflicts with Add to cart and generic ready-stock text; availability is unresolved. Listing mixes DS3235, MG and SG identities. It lists 5–7.4 V, 60 g, 180°/270° options, 50–333 Hz commands, and a 25T arm. At 7.4 V it claims 35 kgf·cm locked-rotor torque and 0.11 s/60° unloaded speed. Dimensions conflict: 40 × 20.5 × 40.5 mm versus 40 × 20 × 38.5 mm. Do not fix mounting geometry from these values. Higher-voltage stall-current text is corrupted in extraction. No assured procurement quote or continuous rating obtained.

## Independent supplier comparison

[PLEX Robotics DS3235SG](https://plexrobotics.com/en/products/dsservo-ds3235sg-35kg-servo), price/currency and Technical Specifications sections: SKU PLX-09-0013-3235, RON 149.90 each including tax, sold-out text alongside Add to cart. Listed 5–7.4 V; at 7.4 V, 35 kgf·cm stall torque, 0.12 s/60° speed and 2.3 A stall current. Mass 60 g; 270° travel; 500–2500 microsecond PWM; 25T spline with M3 thread. This is not proof that the RCDrone variant is identical. Linked STEP was not inspected. Australian delivery and available quantity are unconfirmed.

## Relation to actual preliminary load analysis

Runtime tool_result 23edfb7699a343b0bf9d154fb49e06c2 r1 reports the 13-inch candidate sensitivity. Among conditionally passing propulsion cases, maximum required servo torque with the assumed margin is 2.1950468865 N·m in reserve, with required speed 2 rad/s and travel ±24°. Across all cases, including propulsion failures, the maximum is 2.3543152273 N·m. These are analysis results under assumed inertia, offsets, linkage ratio and friction—not measured loads or verified bounds.

Unit conversion: 35 kgf·cm = 3.4323275 N·m. A stall rating above the calculated moving-load requirement does not establish suitability at 2 rad/s. Do not combine locked-rotor torque with unloaded speed as simultaneous performance. Obtain loaded torque-speed/current data and a 300-second thermal duty assessment, or retain selection as provisional pending guarded testing.

Two 60 g servos would add 10 g relative to the current two 55 g allowances, before horns, wiring or regulator changes. Reconcile mass ownership rather than double-counting accessories. Two RCDrone displayed prices total USD 48.98 including unspecified tax; this cannot replace the AUD 36 allowance without currency conversion and tax treatment. The nominal AUD 16.46 vehicle cost margin is consequently not assured.

The listed 7.4 V performance cannot be assigned to the proposed ESC's 5 V BEC. Evaluate a suitable regulated servo supply, its mass/cost, transient current and efficiency; do not parallel BEC outputs without authorization. The PLEX stall-current figures imply 4.6 A for two simultaneously stalled servos at 7.4 V, not an average mission load. Recompute auxiliary energy and transient bus behavior rather than retaining the 8 W allowance unquestioned.

Next: seek variant-specific available quotations and loaded performance, compare linkage reduction and reduced tilt-rate alternatives, and retain unverified actuator/thermal interfaces in the preliminary review package. No procurement, flight or physical-test acceptance is claimed.
