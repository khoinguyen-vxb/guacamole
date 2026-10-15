# PDR propulsion source register M2-03: batteries, actuators and auxiliary power

## Authority and scope

Task: pdr_propulsion_trade. Authority: system model system@2, SHA256 4c93f9bb676b0e59572034a4c2f51438a8d94cd2aa7d9af7830964ee72219b21; validated work-plan decision a37ef3716fce4eb2b2b35919d6cb0b97@1. Deliverable: PDR-PROPULSION-BUDGET.

The current brief and previous-run index were reviewed in the supplied context. Compacted history supplied targeted search leads; no archival decision, stale result or historical restriction is adopted. This register supports the Chief's early numerical-checkpoint request, message 240a40641e134622a4522585384fe2ef. That request remains outstanding: this file is sourcing evidence, not its completed numerical response.

**Every web observation below was accessed 2026-10-15 through provider-side live search/retrieval.** Search services can return cached material. Access date is neither a supplier quotation date nor proof of live warehouse stock. No purchase, supplier contact, hardware test or component selection occurred. Prices are catalogue observations. Shipping is excluded from project cost calculations; unknown tax or currency is not silently resolved.

## Battery candidates

### B01 — Zeee Premium 3S 5200 mAh 100C, Deans T, two-pack

Exact observed variant: 11.1 V, 5200 mAh, 100C-labelled soft case, Deans T; product handle `zeee-3s-lipo-battery-5200mah-11-1v-100c-deans-t-2pack`. Numeric manufacturer SKU was not exposed. Minimum listed purchase: one package containing two batteries and a manual; one battery would fly.

Observed sale display: $76.99, with $76.99–$92.39 variant range; currency code and AU-specific price UNKNOWN. Default warehouse US; AU is an option. Product retrieval says sold out. Claims: 330 ±15 g per battery; dimensions 136 ×43.5 ×26 mm ±2 mm, but accompanying inch dimensions end in 2.02 in, an unresolved height conflict. Charge limit stated as 1C. The 100C label is not a measured continuous-current qualification. [Manufacturer product, price/warehouse/specification/package sections](https://zeeebattery.com/products/zeee-3s-lipo-battery-5200mah-11-1v-100c-deans-t-2pack).

Do not treat this as the XT60 variant or resolve the dimensional conflict by averaging. Loaded energy, resistance, thermal limits, lead/connector envelope and mass inclusions remain unavailable.

### B02 — Zeee 3S 5200 mAh 50C, Deans T, two-pack

Exact observed variant: 3S1P, 11.1 V, 5200 mAh, 50C-labelled soft case, Deans connector; handle `zeee-3s-lipo-battery-5200mah-11-1v-50c-deans-t`. Numeric manufacturer SKU UNKNOWN. One listed package contains two batteries and a manual.

Observed sale display $68.99, range $68.99–$82.79; currency code and AU-specific price UNKNOWN. Default US warehouse; AU selectable. Add-to-cart shown, but stock quantity and AU availability not established. Claims: approximately 343 g each; 132 ×43 ×29 mm. [Manufacturer product, specifications and package](https://zeeebattery.com/products/zeee-3s-lipo-battery-5200mah-11-1v-50c-deans-t).

This is a separate alternative, not a corrected value for B01. No measured discharge map, sag, usable-energy fraction, connector current qualification or continuous thermal duration was obtained. Do not import specifications from similarly named XT60 or hardcase listings.

### B03 — Zeee 4S 3300 mAh 50C, XT60, two-pack

Exact observed variant: 4S1P, 14.8 V, 3300 mAh, 50C-labelled soft case, XT60 main connector and JST-XH balance connector; handle `zeee-4s-lipo-battery-3300mah-14-8v-50c-xt60`. Numeric manufacturer SKU UNKNOWN. Minimum listed package: two batteries plus manual.

Claims: approximately 348 g each; 131 ×43.5 ×29 mm ±2 mm. Sale display $68.99, range $68.99–$82.79; currency and AU-specific amount UNKNOWN. Default US warehouse. A collection-path retrieval showed add-to-cart, whereas canonical product retrieval showed sold out. Preserve both observations; availability is unresolved, not confirmed. [Canonical manufacturer product](https://zeeebattery.com/products/zeee-4s-lipo-battery-3300mah-14-8v-50c-xt60), [collection-path observation](https://zeeebattery.com/collections/zeee-lipo-car-discount/products/zeee-4s-lipo-battery-3300mah-14-8v-50c-xt60).

The historical approximately 355 g figure is not adopted for this identified variant. Lead envelope, usable energy, resistance and continuous thermal/current qualification remain unknown.

### B04 — Shared Zeee commercial qualifications

Manufacturer FAQ describes destination duties/taxes as the customer's responsibility and shipments as duty unpaid. This does not establish whether a particular AU warehouse checkout price includes Australian GST. Keep tax-exclusive AUD battery cost unresolved until exact warehouse/currency/tax evidence is available. [Manufacturer FAQ, payment/sales-tax section](https://zeeebattery.com/pages/faqs).

Shipping policy lists Australian and other regional warehouses, and conditional free-shipping thresholds. Do not assume a free-shipping claim establishes delivery of these exact variants to the project address. Shipping remains excluded from the vehicle cap regardless. [Manufacturer shipping policy](https://zeeebattery.com/pages/shipping-policy).

## Actuator alternatives

### A01 — Hitec HS-5245MG, manufacturer part 35245S

The retail manufacturer page claims 4.8–6.0 V operation, 32 g mass, 32.4 ×16.8 ×30.8 mm body, 24-tooth output, 4.4/5.5 kgf·cm maximum torque and 0.15/0.12 s per 60 degrees at the two voltages. It lists idle/no-load/stall currents of 3/300/1200 mA and 4 microsecond deadband. Display price $49.99; explicit currency code, tax and stock quantity were not established. [Hitec retail specifications, part 35245S](https://hitecrcd.com/hs-5245mg/?setCurrencyId=1).

A separately retrieved manufacturer datasheet conflicts materially with that page; do not merge favourable values from the two sources.

### A02 — Hitec HS-5245MG manufacturer datasheet conflict

Document: `HCS_HS-5245MG_Specsheet(v2.2)_103023`, page 1. It reports PWM, voltage range 3.5–8.4 V with a short-duration warning at maximum voltage; test columns 4.8/6.0 V. At those voltages: no-load speed 0.15/0.12 s per 60 degrees; stall torque 4.4/5.5 kgf·cm; peak-efficiency torque 0.9/1.1 kgf·cm; no-load current 260/360 mA; stall current 1600/2000 mA; standing current 3 mA; deadband 2 microseconds. Travel defaults ±60 degrees, programmable maximum 175 degrees; pulses 900–2100 microseconds centred at 1500. Dimensions 32.2 ×16.8 ×31.0 mm, general tolerance ±0.1 mm; mass 32 g excluding horn; 24T diameter-6-mm spline; 300-mm, 22-AWG lead; operating temperature −20 to +60 degrees C. [Manufacturer datasheet, p.1](https://www.hiteccs.com/public/uploads/data_sheet/HCS_HS-5245MG_Specsheetv2.2_-1729884691.pdf).

Only extracted text was reviewed successfully; no drawing dimensions were measured. The conflicting range is NOT permission to operate above 6 V. Neither peak-efficiency nor stall torque establishes continuous gimbal capability.

### A03 — Hitec commercial page and CAD lead

Commercial manufacturer identifies part 35245S and PWM; page claims 4.8–6.0 V, 32.4 ×16.8 ×30.8 mm, 32 g and 24-segment diameter-5.76-mm spline. Those dimensions/spline differ from A02. Page display $49.99 lacks an explicit retrieved currency code; stock quantity and tax basis UNKNOWN. International customers are directed to sales. [Commercial product and download links](https://www.hiteccs.com/actuators/product-details/HS-5245MG).

A manufacturer STEP link was discovered and responded as STEP text; it has not been imported, measured, snapshotted or verified in Guacamole: [HS-5245MG STEP lead](https://www.hiteccs.com/public/uploads/cad_files/HS-5245MG-1642816979.stp). CAD peer should obtain it through an authorized, declared-output workflow before relying on its geometry. No accepted mounting pattern is established here.

### A04 — Australian Hitec procurement observation

XC-RC retailer model HT-HS-5245MG: AUD 79.99 each, page reports three units in stock. Listing is per servo; no larger minimum pack stated. Candidate two-axis arrangement would provision two servos, subject to mechanism design. [Supplier product](https://www.xc-rc.com.au/index.php?main_page=product_info&products_id=2717).

Supplier terms section 19 explicitly states AUD prices for Australian delivery include 10% GST. Use exact decimal calculation `quantity * 79.99 / 1.10` for GST removal before the declared final rounding policy; exclude shipping. This is a reproducible pricing input, not an executed ledger total. Other embedded mandatory charges are not separately itemized. [Supplier conditions, section 19](https://www.xc-rc.com.au/index.php?main_page=conditions).

Stock is a page observation, not reservation. Horns, mounting screws, complete accessories, installation mass and required linkage purchases must be reconciled separately.

### A05 — EMAX ES08MA II standard-voltage analog alternative

Manufacturer store identifies product code 0102003010, ES08MA II metal-gear analog PWM, normal-servo option; reverse option also exists. Store displays $11.94 and in stock. Explicit currency code, AU delivery eligibility, tax, package accessories and stock count UNKNOWN. Listing unit is one servo; no larger minimum stated. Exclude ES08MA II HV and ES08MD II substitutions. [Manufacturer store, exact code and option](https://shop.emaxmodel.com/collections/all/products/emax-es08ma-ii-12g-mini-metal-gear-analog-servo-for-rc-model-robot-pwm-servo).

EMAX USA lists retailer code EMX-SV-0275, same stated standard analog model, $7.75 and in stock. Search/page title also mentions a plastic-gear ES08A model, so retain the title conflict; do not assume this resolves SKU equivalence, currency, shipping or tax. [EMAX USA listing](https://shop.emax-usa.com/collections/metal-servos/products/emx-sv-0275-es08ma-ii-metal-analog-servo).

### A06 — EMAX manufacturer-authored specification, supplier-hosted copy

Document identifies EMAX ES08MA II analog-metal servo, dated 2020-06-03; hosted by Flymod. Page 2 specifies, at 4.8/6.0 V: no-load speed 0.14/0.12 s per 60 degrees ±10%; no-load current maximum 200/250 mA; stall torque maximum 1.6/2.0 kg·cm as printed; maximum current 0.9/1.1 A; idle current 6.5 mA. Mass 12 ±1 g; lead 250 ±8 mm excluding connector; 15T spline; no bearing. PWM travel 95 ±10 degrees for 1000–2000 microseconds, centre 1500; maximum 170 ±10 degrees for 600–2400 microseconds. Operating temperature −10 to +60 degrees C. Overall dimensions refer to a drawing, which was not visually inspected. [Manufacturer-authored specification, pp.1–2; uninspected drawing p.3](https://flymod.net/download/emax_12g_metal_gear_steering_servo_2kg_es08ma_specifications).

Applicability to the presently sold lot is unconfirmed. Torque units require interpretation as kgf·cm before SI conversion, explicitly labelled. No continuous-duty joint rating, PWM repetition-rate limit or loaded response map was obtained.

## Auxiliary-power alternative

### P01 — Hobbywing UBEC 5A AIR, part 30607000

Manufacturer regional page: input 2–8S LiPo; selectable outputs 5.0/6.0/7.4 V; 5 A continuous and 15 A instantaneous; 50 ×17 ×10 mm; 21 g. It claims conversion efficiency above 90% and overcurrent/short-circuit/overtemperature protection. Retrieved page did not establish price, stock or peak-current duration. [Manufacturer specifications](https://www.hobbywingdirect.com/products/ubec-5a-air).

The efficiency statement is not a load-dependent efficiency map or brownout verification. Do not use the 7.4-V setting for a provisional 6-V-limited servo branch. Do not parallel this regulator with ESC BEC outputs without an explicitly supported power architecture. Connector, wiring and mounting mass inclusions remain to be reconciled.

### P02 — Australian UBEC procurement observation

Hobbies Direct lists exact MPN 30607000 at AUD 29.94, sold out. It reports an order placed with its supplier on 2026-10-05, not a delivery promise. Footer explicitly identifies advertised prices as AUD including GST unless otherwise specified. Listing is one unit; no larger minimum stated. Shipping is destination-dependent and excluded from the project cap. [Supplier listing and currency/GST footer](https://hobbiesdirect.com.au/products/hobbywing-ubec-5a-2-8s-30607000-42712).

Ex-tax conversion requires the applicable GST rate to be documented in the calculation basis; retain the original inclusive observation. Availability prevents treating this particular listing as an immediately procurable selection.

## Consequences for the forthcoming editable studies

These are engineering interpretations and proposed study methods, not vendor claims or approved thresholds:

1. Keep B01, B02 and B03 as different components. Exactly one installed battery contributes mass and energy; one whole two-battery package contributes procurement cost. The spare supplies no airborne energy.
2. Calculate nominal energy as V_nominal * capacity_Ah, then distinguish nominal label energy from measured usable terminal energy. Explicit uncertain inputs must include SOC-dependent open-circuit voltage, internal resistance, temperature, cutoff, discharge-dependent capacity and usable fraction. Avoid counting resistive losses twice when using terminal-energy data.
3. Source-backed battery discharge and thermal maps are absent. C labels cannot establish connector, wire, ESC or motor limits. Model peak and mission-duration current separately, with loaded voltage coupled to both propulsion channels and auxiliary consumption.
4. Auxiliary consumption must cover both loaded servos, control/IMU/position sensors, receiver/abort equipment and conversion/distribution losses. A01's lower stall-current figure must not be silently substituted for A02's higher figure. For a conservative exploratory 6-V Hitec transient, expose 2 A per servo as an unconfirmed datasheet case, not a measured load or continuous duty.
5. For either actuator branch, obtain CAD-derived moving-group mass/inertia, gravity and thrust offsets, rotor gyroscopic contribution, linkage ratio, friction, cable torque and commanded acceleration. Check simultaneous torque, speed, travel and current. Stall torque and no-load speed are mutually different operating points; they do not define a rectangular usable envelope.
6. Keep motor/ESC response and servo loaded response as independent calibration parameters. No PWM-to-thrust equivalence, motor time constant, servo time constant or calibrated actuator authority is established by this register.
7. Full mission energy must include spool-up, climb to the fixed datum's 5.00-m rise, acquisition including its approved continuous two-second condition, uninterrupted 300-second hover, descent, touchdown and settling. Sensitivity ranges are proposals, not reserve acceptance thresholds.
8. The installed ledger must still include propulsion/supports, all retention, gimbal bearings/linkages/horns, control/sensing/abort options, power distribution, wiring/connectors, battery retention, structure/legs, feet, adhesives and fasteners. Unknown entries remain unknown, not zero. Ground equipment is separately purchased and priced; none is presumed owned.
9. The present document contains no executed mass, procurement or mission results. It does not establish purchased_vehicle_hardware_materials_cost compliance with 499.99 AUD. Component selections require a separate Chief disposition and final reconciliation with actual CAD ownership and mass.

## Prioritized supplier questions for the Chief's later focused human request

- Battery suppliers: for exact B01/B02/B03 variants, request numeric SKU, deliverable AU warehouse stock, currency and tax-separated two-pack quotation, dimensional/lead drawing, mass inclusions and discharge/temperature data. Resolve B01's incompatible height units. If unavailable, identify an alternative exact two-pack rather than silently substitute it.
- Hitec: for part 35245S presently supplied, resolve retail versus v2.2 voltage, current, dimensions, spline and deadband discrepancies; confirm mounting/CAD revision, horn mass/accessories, safe PWM repetition rate and continuous loaded torque/thermal capability. Do not request a broad hardware approval in place of these facts.
- EMAX: confirm 0102003010 normal standard-voltage variant, current drawing/spec revision, complete accessory contents and AU-delivered currency/tax-separated quotation. The 2020 supplier-hosted sheet is a lead requiring lot applicability, not a calibration.
- Regulator supplier: establish in-stock exact 30607000 source, tax basis, allowable peak duration and load/voltage/temperature efficiency and brownout behaviour.

Motor paired-map, mounting, retention and continuous-duty gaps remain as previously identified; this sourcing action does not resolve them. No supplied repository or previous output was changed.
