# PDR r11: avionics candidate evidence and integration risks

Access date for all new web observations: **2026-10-11**.

Status: provider-side research, retained for the current PDR trade. This is not a component selection, purchase authorization, complete BOM, verified interface, flight-controller implementation or acceptance result. No engineering backend was executed during this research. Only web text was inspected; product photographs, mechanical drawings and downloadable binary documents were not interpreted.

## 1. Controller candidate: Raspberry Pi Pico 2, non-wireless, without headers

Manufacturer specifications: RP2350; dual Cortex-M33 or dual Hazard3 processors at 150 MHz; 520 KB SRAM; 4 MB flash; two UARTs, two SPI controllers, two I2C controllers and 16 PWM channels. The product page lists supported input voltage of 1.8–5.5 V DC; this is not a GPIO voltage rating or permission to connect the propulsion battery directly. Source: [Raspberry Pi — Specification section](https://www.raspberrypi.com/products/raspberry-pi-pico-2/).

Supplier SKU CE09936: AUD 8.70 including GST; **AUD 7.91 excluding GST per board**. The page displays in-stock status and 404 units of local stock. Listed planform is 21 × 51 mm. Retain one purchased/one installed in a candidate ledger; headers, retention and harness materials are separate unless demonstrated included. Source: [Core Electronics — price, availability, Board Specifications and variant table](https://core-electronics.com.au/raspberry-pi-pico-2.html).

Unknown: installed board mass, full component-height envelope, mounting interfaces, loaded power consumption, chosen pins, electrical protection, scheduling and implementation suitability. Catalogue peripheral counts do not demonstrate a working hopper controller. No flight firmware or new SDK work is authorized by this note.

## 2. IMU candidate: Core Electronics MPU-6050 module

Supplier SKU 018-MPU-6050: **AUD 4.18 excluding GST**, AUD 4.60 including GST, per module. The page displays in-stock status and 128 local units. It lists a three-axis gyroscope and accelerometer, onboard regulator, 3–5 V supply, 3.3 V logic, selectable addresses 0x68/0x69, and 21 × 16 mm planform. Headers are supplied loose and require soldering. Its example uses I2C. Source: [Core Electronics — price, Features, Specifications and soldering note](https://core-electronics.com.au/mpu-6050-module-3-axis-gyroscope-acce-lerometer.html).

Unknown: installed mass, component height, mounting-hole geometry, module schematic/pull-ups, current, noise, bias stability and vibration performance. This evidence does not establish absolute heading or bounded yaw drift over 300 s. Do not adopt the supplier's demonstration code as a flight estimator or as evidence of the required fixed-rate PID implementation.

## 3. Existing range/flow candidate: MicoAir MTF-01

Manufacturer text lists 8 m range at 90% reflectance/600 lux and 5 m at 90% reflectance/60 klux. Other catalogue values: 5 V supply, 0.5 W consumption, 3.3 V LVTTL UART at 115200 baud, 100 Hz output, 42° optical-flow FOV, illumination above 60 lux and flow working distance above 0.08 m. Range accuracy is stated as 0.04 m below 2 m and 2% above 2 m, at 90% reflectance. Physical values: 29.3 × 17 × 14.5 mm; 4.5 g; mounting spacing 24.3 × 12 mm with 2.5 mm diameter holes. These are text specifications, not drawing interpretation. Source: [MicoAir MTF-01 — Specifications and Physical sections](https://micoair.com/optical_range_sensor_mtf-01/).

The direct [MTF-01 store page](https://store.micoair.com/product/mtf-01/) returned a retrieval error. The search-indexed [official store listing](https://store.micoair.com/store/page/2/) displayed 22.90 sale/25.90 regular with a dollar symbol. Currency, applicable variant, tax treatment, stock and Australian supply were not established. Do not convert this into an accepted AUD price or silently carry forward a historical USD assumption.

## 4. Comparison lead: MicoAir MTF-01P

Search-indexed manufacturer text reports 12 m range at 90% reflectance/600 lux and 8 m at 90% reflectance/60 klux; 5 V, 0.5 W; 3.3 V LVTTL UART at 115200 baud and 100 Hz; 42° flow FOV; 33.2 × 20.8 × 16.8 mm; 8 g; mounting spacing 24.3 × 12 mm with 2.5 mm holes. It lists a laser source and 1.5° emitting angle. Source: [MicoAir MTF-01P — Specifications and Physical sections](https://micoair.com/optical_range_sensor_mtf-01p/).

Evidence limitation: direct retrieval initially returned a page record without substantive displayed content; a subsequent find failed. The values above were recovered through the manufacturer's search-indexed text, not a reliably inspected complete page. They require confirmation before interface release.

The [official store listing](https://store.micoair.com/store/page/2/) displayed 28.99 with a dollar symbol for MTF-01P. Direct [product-page](https://store.micoair.com/product/mtf-01p/) inspection remained unreliable. Currency, tax, variant, package contents and availability remain unresolved. This is an alternative to investigate, not a selected replacement. Do not transfer MTF-01 dimensions or mass to it.

## 5. Engineering implications — inferences, not measured results

- The agreed mission is a 5.00 m rise of the fixed airframe datum, not a guarantee of 5.00 m sensor-to-ground distance. For unchanged upright geometry over level ground, sensor height at hover equals its initial ground height plus that rise. Tilt adds slant-range effects. Therefore the MTF-01's stated 5 m bright-light range does not establish adequate mission range.
- The 90% reflectance conditions cannot be assumed for the test surface. Illumination, texture, reflectance, validity/dropout behaviour and actual mounting height need an explicit operating envelope and tests. Longer catalogue range alone does not establish the altitude-error target.
- With electronics above bottom-mounted rotors, a downward-looking sensor must have a demonstrated unobstructed view. CAD must assess its aperture, range beam and flow FOV against both complete rotor swept envelopes, legs, links and wiring throughout gimbal travel. Do not place the sensor below the rotors or change the architecture without the necessary decision.
- Optical flow does not by itself demonstrate bounded absolute horizontal-position error for the uninterrupted 300 s interval. Estimation, calibration, timing and drift remain unresolved; ideal-state simulation must be labelled separately from sensor-realistic performance.
- Add commercial masses once, with brackets, headers, cable and retention accounted separately. Missing mass is unknown, not zero. The quoted controller and IMU prices are only two BOM lines, not evidence of complete-vehicle budget compliance.

## 6. Next integration use

The propulsion/procurement branch should reconcile exact variants, purchased quantities, price basis and ancillary power with its ledger. The CAD branch needs provisional envelopes labelled as such, followed by mounting and optical-clearance checks. The plant branch should retain sensor/datum transforms and distinguish perfect-state control tests from estimation performance.

Before selection: confirm unavailable product information through further supplier evidence or a focused human request; obtain missing drawing interpretation where required; compare the resulting complete cost/mass/energy budget. Preserve current requirements, bottom propulsion and the common two-axis gimbal. This note changes no existing engineering decision and implies no PDR/CDR acceptance.
