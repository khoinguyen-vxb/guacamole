from guacamole.websocket import control

request_id = "6e46c666b10b43f99860727c92f405d3"
reply = f"""
Referring to: {request_id}

**Sourcing Update — SunnySky SS-X2814-900 / Himax CR28161100**

A search for manufacturer drawings, CAD models, technical specifications and performance reports has identified several potentially useful sources. However, **complete manufacturer-issued engineering drawings for the exact motor variants have not been located.**

**1. SunnySky SS-X2814-900 (Original, not III/V3)**

- Original manufacturer/distributor listing: https://sunnyskyusa.com/products/sunnysky-x2814-brushless-motors
- Historical original X2814-900KV listing: https://www.himodel.com/m/electric/SUNNYSKY_X2814_900KV_Outrunner_Brushless_Motor.html
- Downloadable CAD-derived 2D drawings (variant not verified): https://marathon-os.com/library/2d-technical-drawings/sunnysky-x2814-rc-motor-downloadable-680b7ad435a26ccc297a02d7
- GrabCAD X2814-1000KV model (reference geometry only): https://grabcad.com/library/sunnysky-x2814-1000kv-1

Published specifications indicate a 4 mm motor shaft, 6 mm propeller-adapter output shaft and approximately 108 g motor mass. These specifications require confirmation against the exact original revision.

The available third-party CAD appears to reference different variants, including V2 and 1000KV. Consequently, these models may support provisional interface development but cannot be treated as authoritative drawings for the original 900KV motor.

**2. Himax CR28161100**

- Manufacturer product listing: https://himaxmotors.com/products/himax-cr28161100-contra-rotating-motor-and-propeller-combo
- CR2816 operating manual: https://www.scribd.com/document/412969222/CR2816

Published specifications indicate a 43 mm mounting bolt circle, four 3.5 mm mounting holes, 4 mm front shaft, 9.5 mm rear shaft and approximately 164 g mass including propeller attachments.

The operating manual may provide additional mechanical and installation information, but a complete tolerance-controlled engineering drawing for the exact assembly remains unavailable.


**4. Outstanding Evidence**

The following requirements remain unresolved for both candidates:

- Complete mounting-hole, shaft and propeller-retention drawings, including dimensional tolerances and mass inclusions.
- Verified paired coaxial thrust, reaction torque, RPM and battery-current measurements.
- Identification of propellers, supply voltage, rotor spacing and test duration.
- Mission-duration thermal limits and continuous operating ratings.
- Loaded transient response and motor/propeller dynamic characteristics.

No qualifying paired coaxial performance report has been identified. Isolated-rotor performance tables cannot be used to validate combined coaxial operation.

**5. Engineering Disposition**

Status: **PARTIALLY RESOLVED — EVIDENCE HOLD REMAINS ACTIVE.**

Available specifications and third-party CAD can support preliminary geometry development and comparison, provided all unverified dimensions are explicitly identified.

Neither motor can presently be considered mechanically or operationally verified against the outstanding evidence requirements. Independent sourcing, CAD comparison and plant-model development may continue.

No hardware selection, purchasing authorization, evidence waiver or PDR acceptance is implied by this update.

MY ULTIMATE REC IS THAT IF there are other viable alternatives with these questions answered, please prioritise that.

"""

# The token changes on every EHopper start; paste the one it printed.
with control(8766, "EHopper") as send:
    send(
        {"kind": "reply_human", "request_id": request_id, "author": "Khoi", "text": reply},
        # Rerunning is safe: the same ID returns the stored result.
        id=f"reply-{request_id}",
    )
