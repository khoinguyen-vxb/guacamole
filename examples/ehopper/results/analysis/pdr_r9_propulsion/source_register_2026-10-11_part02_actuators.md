# PDR r9 source register — part 02: actuator and supply alternatives

Access date: **2026-10-11** for every URL below. Method: provider-side web search and HTML text retrieval. Retrieval may use cached pages; access date is not a supplier quotation date. Page sections and retrieval-specific line ranges are locators, not permanent document pagination. No product images, dimension drawings or binary manuals were visually inspected. No purchase, supplier contact, installation, engineering execution or physical test occurred during this research.

Authorization: decision 98d7c43a499d4584a77132cd5ac96874 r1, task pdr_r9_propulsion. Supplements PDR-R9-PROPULSION-SOURCE-REGISTER-01 r1. These are unselected alternatives for the Chief's common two-axis gimbal architecture, not accepted component interfaces.

Classification: SOURCED = retrieved supplier/manufacturer claim; ASSUMED = study input; DERIVED = arithmetic; CALIBRATED = supported by measurements and fitting. No value here is calibrated. MISSING remains unknown, never zero. Prices below are displayed prices, not established tax-exclusive costs. No exchange rate has been applied.

## S12 — digital mini-servo candidate

Candidate ID: ACT-HITEC-HS5245MG-35245S.

[Hitec HS-5245MG manufacturer page](https://hitecrcd.com/hs-5245mg/?setCurrencyId=1), product identification and Servo Specifications, retrieval lines 160–232.

Manufacturer identifies part 35245S: digital servo, 32.0 g, body dimensions 32.4 × 16.8 × 30.8 mm, Standard 24 output spline. Operating supply 4.8–6.0 V. Catalogue torque endpoints 4.4/5.5 kgf·cm and transit times 0.15/0.12 s per 60 degrees at 4.8/6.0 V. Listed currents: idle 3 mA, no-load operating 300 mA, stall 1200 mA; the table does not assign separate current values to each supply voltage. Deadband 4 microseconds. Displayed price $49.99; explicit currency and tax basis remain unconfirmed and this is not the AUD budget quote.

The page describes configurable endpoints, direction, failsafe, deadband and reduced speed using a programmer. Programming equipment, if required, belongs in the separate ground-equipment ledger. Pulse range, acceptable refresh rate, continuous torque, loaded speed, thermal duty and externally accessible position feedback are not established by the reviewed table.

## S13 — Australian digital-servo price

[XC-RC HS-5245MG listing](https://www.xc-rc.com.au/index.php?main_page=product_info&products_id=2717), model/stock/price and specifications, retrieval lines 59–78.

Supplier model HT-HS-5245MG; displayed **AUD 79.99 each**; page reports three units in stock. Listed individually: comparison purchase two single-servo units, installation two. Tax treatment and an actionable current stock quotation remain missing. Do not divide the price by an assumed GST factor.

Supplier dimensions 32.26 × 16.76 × 30.73 mm and mass 31.75 g differ slightly from manufacturer rounding. Retain both; manufacturer 32.0 g is a sourced candidate value, not a weighing result. Mounting-ear span, hole pattern, output-axis height, horn sweep and cable bend space are not established by these body dimensions. Package contents and inclusion of horns, screws, leads and their mass require reconciliation.

## S14 — analog mini-servo comparison

Candidate ID: ACT-HITEC-HS225MG-32225S.

[Hitec HS-225MG manufacturer page](https://hitecrcd.com/hs-225mg-metal-gear-mighty-mini-servo/), identification and Servo Specifications, retrieval lines 159–220.

Manufacturer identifies part 32225S: analog servo, 31.0 g, 32.4 × 16.8 × 31.0 mm, Standard 24 output spline, operating supply 4.8–6.0 V. Product-page torque endpoints are 3.9/4.8 kgf·cm, with transit times 0.14/0.11 s per 60 degrees. Listed currents are idle 8 mA, no-load operating 300 mA and stall 1200 mA, without separate voltage-specific current values; deadband 8 microseconds. Displayed manufacturer price $35.99 has unconfirmed currency/tax basis here.

These are product-page claims, not selected sizing limits. Continuous loaded torque, response, allowable refresh rate, thermal duty, exact mount and external position feedback remain missing. Accessory and wire mass inclusion is unconfirmed.

## S15 — conflicting manufacturer specification chart

[Hitec servo specification chart](https://hitecrcd.com/servo-specification-chart/), MINI SERVOS rows, retrieval lines 216–221.

At 6.0 V the chart lists HS-225MG stall torque **4.4 kgf·cm** and speed **0.13 s per 60 degrees**, conflicting with the product page's 4.8 kgf·cm and 0.11 s. The chart lists HS-5245MG at 5.5 kgf·cm and 0.12 s, consistent with its product page.

Do not silently select the more favourable HS-225MG values or merge revisions. Exact supplied revision and voltage-specific specifications require manufacturer/supplier clarification. Even the smaller listed stall torque is not a demonstrated continuous operating torque.

Additional unreviewed binary lead: [Hitec Commercial Solutions HS-225MG specification sheet](https://www.hiteccs.com/public/uploads/data_sheet/HCS_HS-225MG_Specsheetv2.2_1-1729889510.pdf). Search indexing suggests further current and dimensional differences. The PDF has NOT been read through the supplied read_document/extract workflow, and its search snippet is not admitted as an accepted specification. Obtain a registered source and bounded excerpt, plus drawing interpretation, before relying on it.

## S16 — Australian analog-servo price and mass conflict

[XC-RC HS-225MG listing](https://www.xc-rc.com.au/index.php?main_page=product_info&products_id=2063), retrieval lines 59–80.

Displayed **AUD 59.99 each**; page reports four units in stock. Listed individually: comparison purchase two units, installation two. Tax treatment and actionable stock confirmation remain missing.

Supplier mass entries are 1.10 oz and 27.94 g; these are internally inconsistent and disagree with the manufacturer's 31.0 g. Do not use the smaller supplier mass to improve the ledger. Retain manufacturer 31.0 g only as a provisional sourced value with accessory inclusion unresolved. Supplier body dimensions are 32.26 × 16.76 × 31.00 mm; they do not constitute a mounting drawing.

## S17 — separate actuator regulator candidate

Candidate ID: PWR-HW-UBEC5A-30607000.

[Hobbywing UBEC 5A manufacturer page](https://www.hobbywing.com/en/products/ubec-5a93.html), Overview and Specifications. HTML/search retrieval reports 2–8S LiPo input, selectable 5.0/6.0/7.4 V output, 5 A continuous and 15 A instantaneous output, 50 × 17 × 10 mm, and 21 g. Manufacturer claims conversion efficiency above 90% and overcurrent, short-circuit and overtemperature protection. A subsequent page lookup failed; preserve this retrieval limitation rather than implying repeated successful access.

[RCMA exact product listing](https://www.rcmodelaircraft.com.au/hobbywing-30607000-ubec-5a-v2-air-2-8s), Description/Technical Specifications and SKU, retrieval lines 365–392, corroborates those nominal ratings and identifies HW30607000. Its separate shipping weight of 0.2500 kg is NOT installed mass.

Comparison purchase one individually listed regulator, installation one. Peak duration, cooling conditions, connector current limits, output transient droop, mass inclusion and input/output behaviour at temperature remain missing. A catalogue 5 A label is not a demonstrated brownout margin. The 7.4 V setting is outside both servo candidates' stated supply range; do not use it with them.

## S18 — regulator quotation limitations

[RCMA Hobbywing catalogue](https://www.rcmodelaircraft.com.au/brand/hobbywing/), HW30607000 product card: retrieved price **$22.99**, with an in-stock label. Currency code and tax treatment were not explicitly established in that excerpt. The direct product-page extraction did not expose the target item's price or stock status, so the catalogue quote is provisional, not independently confirmed by the detail page.

[Hobbytech UBEC 5A V2 listing](https://hobbytechtoys.com.au/products/hobbywing-30607000-ubec-5-amp-v2-2-8s), retrieval lines 494–509: SKU HW30607000, displayed **$29.99**, unavailable wording and an add-to-cart control. Currency code/tax treatment remain unconfirmed. Treat availability as unresolved/unavailable, not as proven by the button. Each listing concerns a single regulator, not a multi-pack. Tax-exclusive AUD cost remains MISSING.

## S19 — discontinued supply lead: do not mix variants

[Hobbywing discontinued-products catalogue](https://a.hobbywing.com/en/discontinued-products?sys=46) marks the older UBEC 10A (2–6S), part 30603000, as stopped. [Its manufacturer product page](https://a.hobbywing.com/en/products/ubec-10a-2-6s152) lists 6–25.2 V input, 5.0/6.0/7.4/8.4 V output, 10/20 A continuous/peak, 43.1 × 32.3 × 12.5 mm and 36 g.

This is a discontinued research lead, not an available selected supply. Do not substitute data from 30603003 UBEC 10A-Car or 30608000 UBEC 10A HV. No price or stock acceptance is established for 30603000; purchase and installed quantities remain undecided.

## Accounting and integration rules for the next ledger

- Compare two HS-225MG units OR two HS-5245MG units; do not install/count both alternatives together. Maintain separate actuator instance IDs for outer and inner axes even when the same model is used.
- A separate UBEC is an alternative to a suitably demonstrated integrated/ESC supply, not an automatically required duplicate. Until Chief selects the topology, keep separate supply branches and do not parallel regulator outputs. Count retained ESC assembly mass once even when its BEC output is unused.
- Catalogue servo mass does not close the actuator assembly: horns, horn screws, ball links, rods, bearings, pivots, fasteners, wiring, strain relief and positive retention need distinct inclusion/ownership records.
- Requested horn ratio and linkage geometry must connect servo torque/travel to joint torque/travel. Published body size and stall torque do not establish this relationship. Retain linkage/bearing cost and mass as unknown, not included in a generic zero-cost mechanism.
- Supply output power, input battery power and mission energy are different quantities. Use measured or explicitly assumed regulator efficiency and simultaneous actuator demand; avoid counting servo demand twice in an ancillary-power allowance.
- Whole purchase quantities apply throughout. Two purchased propulsion batteries and one installed battery remain mandatory. Reusable programming, measuring and charging equipment is separately priced; nothing is assumed owned.

## Chief interface handoff content — not yet a vehicle-specific calculation

Chief message 51bc01472fd04d1c96a7ca2cc9fa4e47 reports the provisional single-spine/outboard-fork concept and a **0.405777 kg partial structural estimate**, comprising approximately 0.075577 kg tube plus 0.330200 kg assumed printed material. The printed volume is not CAD-derived. Treat this as a relayed screening allowance only, never as complete structure or complete vehicle mass. Component-ID custom-part volumes and ownership are needed to replace it without adding both estimates and CAD mass.

Remaining inputs that genuinely block vehicle-specific actuator sizing:

1. Outer/inner moving-group membership, mass, CG and full inertia; rotor spin inertias and operating speeds; joint/pivot positions; thrust-line offsets; actual rotor spacing; proposed travel, loaded rate and acceleration; friction and cable loads. These determine joint load demand. Whole-vehicle thrust moment about its CG is not automatically servo joint torque.
2. Proposed horn/linkage ratio through travel, bearing arrangement, horn sweep and mounting-hole dimensions. These determine whether the candidate servo envelope can be integrated and whether any available torque/speed is adequate.
3. Exact controller/output protocol and rate, actuator supply topology and bus-voltage tolerance, wiring lengths and connector ratings. These determine simultaneous peak demand and brownout exposure.
4. Variant-specific tax-exclusive AUD quotations, minimum packs and inclusion lists for actuators, regulator, horns, bearings and linkages. These block procurement closure, not independent mass sensitivity analysis.
5. Loaded response/current/thermal data and a duty-cycle basis. Neither manufacturer catalogue supplies a validated gimbal map; no servo continuous-torque pass can be claimed.

Other vehicle-envelope blockers retained from source register 01: motor mounting and propeller hub/retention interfaces, contradictory 3S battery height, selected controller/sensors/receiver envelopes, and complete commercial/custom instance reconciliation. Chief selections remain outstanding; historical 12-degree travel and 0.25 m lever arm remain unselected.

Independent propulsion comparisons can continue over explicit complete-mass and ancillary-power scenarios while these interfaces are unresolved. Keep scenario allowances separate from sourced subtotals and missing ledger rows. No mass-support envelope, mission-energy result, budget pass, PyThrust capability result or artifact-bound VerificationResult has been produced by this source-register write. Those require retained input/configuration and analysis/check programs, actual authorized execution and reviewed results.
