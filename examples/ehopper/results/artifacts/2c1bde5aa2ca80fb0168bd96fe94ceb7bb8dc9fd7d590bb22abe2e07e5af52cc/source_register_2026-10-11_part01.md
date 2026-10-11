# PDR r9 propulsion source register — part 01

Status: preliminary candidate evidence, NOT hardware selection, a complete BOM, numerical screening or physical acceptance.
Access date for EVERY web source below: **2026-10-11**. Method: provider-side web search and HTML text retrieval. Locators identify page sections and extraction line ranges; line numbering is retrieval-specific. Product images, mounting drawings and linked binary manuals were not inspected. Search snippets alone are not treated as a reviewed manual.

Authorization: decision 98d7c43a499d4584a77132cd5ac96874 r1. Architecture: decision 84ef41fdd3fd4266ada43df2ace64a48 r1; frame contract: f046cc4fe5294a6f9a61027529056f61 r1. Procurement rule: REQ-HARDWARE-BUDGET r4, strictly below AUD 500 excluding tax/shipping; whole packs/stock; two batteries purchased, one installed; reusable ground equipment separate, none assumed owned.

## Evidence classification

- SOURCED means a manufacturer/supplier claim was retrieved, not independently measured.
- DERIVED means arithmetic or unit conversion, not a test result.
- ASSUMED means an explicitly proposed study input, not a selected vehicle parameter.
- CALIBRATED requires traceable measurements and fitting evidence. Nothing in this register is calibrated.
- MISSING values remain unknown and must not enter a ledger as zero.
- Displayed price, tax-exclusive price, currency conversion and stock availability are separate fields. No FX conversion has been applied here. An add-to-cart control does not establish stock.

## S01 — original SunnySky X2814-900 supplier data

[Buddy RC X2814 product page](https://www.buddyrc.com/products/sunnysky-x2814-brushless-motors), SKU/price lines 288–322; KV900 specifications/table lines 402–441.

Candidate ID MOTOR-SS-X2814-900-ORIGINAL. SKU SS-X2814-900; displayed price 29.99, symbol $, currency code and tax treatment unconfirmed. Listed singly; comparison requires two motors. Specification claims: 900 rpm/V; 52 mΩ; no-load 0.7 A at 10 V; 108 g; rotor diameter 35 mm; body 36 mm excluding shaft, overall 54 mm; shaft 4 mm; 3–4S LiPo; 570 W. Current entry is 40 A/30 s, NOT a demonstrated 300-second rating.

Isolated performance transcription; tuples are (current A, thrust gf, electrical power W):

- APC13x6.5 at 11.1 V: (5,500,55.5), (8.7,750,96.57), (13,1000,144.3), (18.3,1250,203.13), (24.2,1500,268.62), (27.6,1650,306.36), (29.5,1750,327.45).
- APC11x5.5 at 14.8 V: (4.5,500,66.6), (7.9,750,116.92), (11.7,1000,173.16), (15.8,1250,233.84), (20.6,1500,304.88), (25.7,1750,380.36), (29.3,1950,433.64).

RPM, torque, test duration/conditions and exact propeller suffix are missing. These are not coaxial maps; the E/EP product correspondence needs confirmation.

## S02 — alternative motor supplier and mass basis

[RCDrone original X2814 listing](https://rcdrone.top/products/1pc-original-sunnysky-x2814-90), title/price/variant section, lines 84 onward; parameter and package sections.

Listed price **USD 41.40**, taxes included; variant options include KV900, KV1000, KV1100 and KV1250. The extraction contains both sold-out wording and an add-to-cart control: availability and exact KV900 quote require confirmation. Pack contents: one motor and one accessories bag. Proposed purchase/installation: two single-motor packs/two motors, not a purchase instruction.

Supplier identifies 108 g as motor mass including wire, with 16 AWG, 100 mm motor leads and fitted 3.5 mm bullet connectors. Accessory-bag mass inclusion is unclear. Count supplied leads once; account separately for any additional harness or mounting hardware after reconciliation. This is a listing claim, not weighing evidence.

Do not substitute X2814-III/V3 specifications for this original-model candidate.

## S03–S06 — opposite-rotation propeller candidates

Each source below is a manufacturer product page, accessed 2026-10-11; locator: title/price, description and specifications, approximately lines 76–95.

| Source / candidate ID | Product and source | Displayed each price | Diameter / pitch, in | Product weight, oz | Rotation description |
|---|---|---:|---|---:|---|
| S03 / PROP-APC-13X65E | [APC 13x6.5E](https://www.apcprop.com/product/13x6-5e/) | $5.73 | 13 / 6.5 | 1.06 | Thin Electric |
| S04 / PROP-APC-13X65EP | [APC 13x6.5EP](https://www.apcprop.com/product/13x6-5ep/) | $5.73 | 13 / 6.5 | 1.06 | Pusher, reverse rotation |
| S05 / PROP-APC-11X55E | [APC 11x5.5E](https://www.apcprop.com/product/11x5-5e/) | $4.17 | 11 / 5.5 | 0.81 | Thin Electric |
| S06 / PROP-APC-11X55EP | [APC 11x5.5EP](https://www.apcprop.com/product/11x5-5ep/) | $4.17 | 11 / 5.5 | 0.81 | Pusher, reverse rotation |

Each page specifies hub diameter 0.80 in, hub thickness 0.41 in and shaft-hole diameter 1/4 in; each includes an LPAR06E adapter-ring set. Products are listed individually. Each alternative requires one E and one EP purchased and installed. Currency code, tax treatment and confirmed stock remain missing; preserve the dollar-symbol prices without assuming AUD.

Derived nominal rotor envelopes: 13 in = 330.2 mm; 11 in = 279.4 mm. These are candidate diameters, not CAD clearance envelopes including deformation. For later computation use 25.4 mm/in and 28.349523125 g/oz; retain source units and mass-rounding uncertainty. Determine whether published weight includes rings before separately counting them.

Opposite-rotation catalogue products do not establish equal thrust/torque maps, a coaxial calibration or safe hub retention. Absolute CW/CCW labelling needs a viewing convention. Verify blade orientation so both rotors thrust along -z_M, assign spin signs relative to common +z_M, and verify retention under each rotation. Motor shaft diameter alone does not establish prop-adapter fit or mounting-hole geometry.

## S07 — manufacturer propeller speed constraint

[APC RPM limits](https://www.apcprop.com/technical-information/rpm-limits/), Thin Electric category, lines 108–119, accessed 2026-10-11.

Manufacturer suggested Thin Electric speed ceiling: RPM = 150000 / diameter_in. Derived values: approximately 11538 rpm for 13 in and 13636 rpm for 11 in. Apply category/variant confirmation and any stricter system limit; these are not operating RPM measurements or fatigue validation. Do not apply the separate MR or Slow Flyer category limits interchangeably.

## S08 — exact ESC variant, manufacturer HTML

[Hobbywing SkyWalker V2 low-voltage series](https://www.hobbywing.com/en/products/skywalker-v2-series274), specification table lines 284–433, accessed 2026-10-11.

Candidate ID ESC-HW-80060442: Skywalker 50A V2, product number 80060442. Manufacturer claims 50 A continuous / 70 A peak, 3–4S LiPo, switch-mode BEC 5 V / 5 A, 60 × 25 × 8 mm, 36 g. Listed input leads: red/black 14 AWG, 100 mm; output leads: three 16 AWG, 75 mm; no input connector; 3.5 mm female output connectors.

Distinct comparison ID ESC-HW-30216400: 50A-6S V2, 3–6S, 50/70 A, 5 V / 6 A BEC, 73 × 30 × 12 mm, 68 g. Do not combine its ratings with the smaller 80060442 variant.

Neither retrieved table establishes cooling conditions, peak duration, loaded transient response, command timing or installation-specific continuous capability. Supplied-wire mass inclusion needs confirmation. Price is not provided here. Preserve two independent ESC channels; do not assume BEC outputs may be paralleled or that either BEC can supply both selected tilt actuators.

## S09 — Australian ESC quote, unresolved availability

[The Joy Box Skywalker V2 50A listing](https://thejoybox.com.au/products/hobbywing-skywalker-v2-60a-esc-6a-bec), title/price lines 135–156; specifications/package lines 178–195, accessed 2026-10-11.

Displayed price **AUD 45.95**, taxes included, per package containing one ESC and manual. Proposed comparison quantity: two packages/two installed ESCs. Tax-exclusive unit price remains missing; retain the gross quote separately rather than silently treating it as ex-tax.

Title/specifications say 50A V2, 3–4S, 5 V / 5 A, 36 g, 60 × 25 × 8 mm, agreeing with the smaller manufacturer variant. However, the URL slug says 60A/6A; exact supplied SKU requires confirmation. The extraction contains sold-out wording and an add-to-cart control, so purchasability is unresolved. No order or cart interaction was performed.

## S10 — 3S two-battery purchase pack

[Zeee Premium 3S 5200 mAh 100C, Deans, two-pack](https://zeeebattery.com/products/zeee-3s-lipo-battery-5200mah-11-1v-100c-deans-t-2pack), price/warehouse lines 141–181, specifications/package lines 216–232, accessed 2026-10-11.

Candidate ID BAT-ZEEE-3S5200-100C-DEANS-SOFT. Claims: 11.1 V, 5200 mAh, 330 g ±15 g; dimensions 136 × 43.5 × 26 mm ±2 mm; Deans T connector; marketed 100C continuous. Package contains two batteries. Proposed ledger: purchase one complete two-battery pack; install one battery.

Displayed sale price $76.99 and range $76.99–$92.39, US warehouse selected; AU warehouse option exists. Currency code, AU-variant price, tax treatment and availability are unconfirmed; page says sold out. Do not transfer the US-default quote to AU inventory.

Dimensional conflict: page gives height 26 mm but also 2.02 in. These are inconsistent; no accepted CAD height until clarified. Per-cell resistance, loaded voltage, useful energy, temperature limits and independently established discharge rating are missing. The 100C label is not a measured continuous-current qualification.

## S11 — 4S two-battery purchase pack

[Zeee 4S 3300 mAh 100C, Deans, two-pack](https://zeeebattery.com/products/zeee-4s-lipo-battery-3300mah-14-8v-100c-deans), price/warehouse lines 141–182, specifications/package lines 217–234, accessed 2026-10-11.

Candidate ID BAT-ZEEE-4S3300-100C-DEANS-SOFT. Claims: 4S1P, 14.8 V, 3300 mAh, approximately 355 g; dimensions 132 × 43 × 29 mm ±2 mm; Deans power and JST-XH balance connectors; 100C discharge label. Package contains two batteries. Proposed ledger: purchase one whole two-pack; install one battery.

Displayed sale price $72.99 and range $72.99–$85.99 with US warehouse selected and AU option available. Currency code, Australian variant price, tax treatment and confirmed stock are missing. Add-to-cart text is not stock verification.

Resistance, sag, usable energy versus load/temperature, continuous-current test conditions and flight-duration thermal evidence remain missing. Do not convert the C label directly into an accepted current limit. Both battery candidates require separately priced compatible ground charging equipment and actual connector/interface reconciliation.

## Candidate combinations to investigate — not selected

| Alternative | Motors | Propellers | ESC comparison | Battery comparison |
|---|---|---|---|---|
| ALT-3S-13IN | 2 × MOTOR-SS-X2814-900-ORIGINAL | one PROP-APC-13X65E + one PROP-APC-13X65EP | 2 × ESC-HW-80060442 | BAT-ZEEE-3S5200-100C-DEANS-SOFT; buy 2 batteries, install 1 |
| ALT-4S-11IN | 2 × MOTOR-SS-X2814-900-ORIGINAL | one PROP-APC-11X55E + one PROP-APC-11X55EP | 2 × ESC-HW-80060442 | BAT-ZEEE-4S3300-100C-DEANS-SOFT; buy 2 batteries, install 1 |

These are research combinations, not compatibility or feasibility determinations. Only isolated nominal-voltage table points are available here. Battery voltage range and sag must be included before using either combination. No interpolation, optimization, mission-energy computation or verification program has been executed by this register-writing action.

## Integration and accounting constraints retained from current messages

Chief reply 63c5f7edc9f9411b86763477879d9ef1 reports no current vehicle assembly/mass ledger. Historical mass, rotor spacing, 12-degree travel and 0.25 m arm remain unselected. Chief owns structural concept, custom-part CAD volumes, placement, geometry and aggregate mass properties. This worker owns integrated purchased/installed commercial-component accounting.

Plant reply 73a197ce0d8c461ab4fc4b59957151a3 proposes two independent motor and two tilt channels; IMU plus selected heading, altitude and position aiding; receiver/manual-abort path; battery voltage/current sensing; regulation, distribution, logging and harnesses. No controller or sensor board is selected. Timing proposals are not accepted hardware capabilities.

For the complete ledger, retain stable installed-instance IDs separately from the candidate IDs above. Required unresolved rows include controller, integrated/external sensors, receiver, two tilt actuators, actuator supply, distribution/protection, wiring/connectors, bearings/linkages, fasteners, retention, custom structural stock/material and landing hardware. Ground equipment needs charger/power supply/leads, command transmitter or equivalent, and calibration/test equipment appropriate to the eventual verification plan. This register does not price those rows and does not imply they are free or owned.

Count documented commercial assembly masses once; CAD envelope solids add no duplicate mass. Track purchased stock quantity separately from consumed structural mass. Charge whole packs and spools, and retain unknown quantities/prices rather than a misleading total. Whole-vehicle cost and installed mass remain unresolved.

## Required follow-up before numerical or procurement conclusions

1. Finish bounded inspection of PyThrust propulsion models/solver, propeller loader and actual dataset entries. Reviewed motor loader silently defaults missing numeric fields to zero and suppresses entry exceptions; screen raw records before admitting them. Checkout presence and source readability do not establish imports or execution.
2. Persist machine-readable component, source and mission configurations; retain the two alternatives rather than choosing hardware. Include complete installed battery mass and climb/300-second hover/landing energy with explicit reserve and ancillary power.
3. Obtain dated Australian-usable, variant-specific, tax-exclusive quotations and currency evidence. Request unresolved supplier data from the human if further retrieval cannot resolve it. No FX rate or complete AUD total is established here.
4. Obtain current Chief CAD/component-instance interfaces before vehicle-specific sizing. Any interim mass, spacing or tilt sweeps must be explicitly labelled sensitivity studies.
5. Retain separate coaxial thrust/torque calibration parameters, signed air-on-rotor torque -s_i Q_i about +z_M, simultaneous torque balance/thrust/current constraints, differential authority, motor/ESC lag and thermal uncertainty. Opposite spin does not establish cancellation; isolated thrust must not simply be doubled.
6. Obtain exact mounts, adapters, hub retention, propeller orientation and drawing interpretation. No image or drawing acceptance follows from this text extraction.
7. Develop editable artifact-driven screening and verification programs, execute through authorized tools, inspect logs, publish actual ProducedFiles and bind every tested artifact Ref. This source register is not a VerificationResult, PDR acceptance or permission for CDR work.
