# PDR propulsion sourcing — propeller and ESC evidence, M2 register 02

## Authority and evidence status

Task: pdr_propulsion_trade. Authority: system model revision 2, SHA256 4c93f9bb676b0e59572034a4c2f51438a8d94cd2aa7d9af7830964ee72219b21; work-plan decision a37ef3716fce4eb2b2b35919d6cb0b97 revision 1. Applicable deliverable: PDR-PROPULSION-BUDGET.

The current brief and previous-run index have been reviewed. Compacted supplier leads were reused for targeted questions, not reread wholesale. This new file preserves live observations without overwriting or revalidating stale files. Historical motor sourcing remains distinct; this register does not establish motor selection or compatibility.

**Access date for every URL below: 2026-10-15.** Method: provider-side live web search and retrieval. Cached/indexed content can be returned by the search service. These are dated catalogue observations, not quotations, purchases, physical measurements, calibration or verification results. HTML text does not establish that product images or mounting drawings were inspected. Unknown quantities and prices are not zero.

## P01–P04: exact APC candidate variants

Source sections: product code, price, description and specifications, approximately HTML lines 75–95 on each page.

| ID | Exact manufacturer part | Type | Diameter × pitch, source units | Listed price per propeller | Product weight, source units | Direct source |
|---|---|---|---|---|---|---|
| P01 | LP13065E | Thin Electric | 13 × 6.5 in | $5.73 | 1.06 oz | [APC 13x6.5E](https://www.apcprop.com/product/13x6-5e/) |
| P02 | LP13065EP | Thin Electric Pusher; reverse rotation | 13 × 6.5 in | $5.73 | 1.06 oz | [APC 13x6.5EP](https://www.apcprop.com/product/13x6-5ep/) |
| P03 | LP11055E | Thin Electric | 11 × 5.5 in | $4.17 | 0.81 oz | [APC 11x5.5E](https://www.apcprop.com/product/11x5-5e/) |
| P04 | LP11055EP | Thin Electric Pusher; reverse rotation | 11 × 5.5 in | $4.17 | 0.81 oz | [APC 11x5.5EP](https://www.apcprop.com/product/11x5-5ep/) |

Each product page specifies a 0.80 in hub diameter, 0.41 in hub thickness and 1/4 in shaft/bore diameter; each includes one set of LPAR06E adapter rings. Ring sizes, installed ring mass and suitability for the actual motor adapter remain unresolved here. No additional ring purchase is automatically added when already included.

For all four rows: retail presentation is one propeller, with an add-to-cart control and no larger minimum pack stated. Checkout minimum quantity and dispatchable stock were not independently confirmed; there is no inspected numerical stock count. Proposed matched-pair scenarios install/purchase one of each handed variant, not two identical propellers. No order was placed.

Currency: pages display '$' without an inspected explicit ISO currency declaration. USD is plausible from the US supplier location, but remains an inference, not an established ledger currency. No AUD conversion is authorized by this observation.

Tax/shipping: APC's [General FAQ, Pricing and Billing](https://www.apcprop.com/general-faq/?v=84de8e2b14bb) states that its sales tax applies to California customers. This is a supplier statement, not confirmation of Australian import tax treatment or a destination-specific invoice. Its [Shipping FAQ](https://www.apcprop.com/shipping-faq/) separates destination/weight-dependent shipping and calculates it at checkout. Shipping and tax are excluded from the project cap; no shipping credit or invented tax deduction is taken. Tax-exclusive AUD ledger values remain unresolved pending currency and purchase-basis confirmation.

Unit conversions for interface discussion only, not measured geometry: 13 in = 330.2 mm; 11 in = 279.4 mm; hub diameter 20.32 mm; hub thickness 10.414 mm; nominal bore 6.35 mm, using 25.4 mm/in. Product mass inclusion and tolerance remain unknown. A bore/adapter-ring match does not establish thread engagement, clamping, washer coverage or reverse-rotation retention.

## P05: handed pairing and coaxial qualification

The manufacturer's [Propeller FAQ, matched-pair and coaxial questions](https://www.apcprop.com/faq/?v=84de8e2b14bb) identifies standard/reverse pairs by otherwise identical part numbers differing only by final P. It also recommends a larger leading rotor and higher-pitch trailing rotor for coaxial applications, illustrating an 11x4.5MR / 10x5.5MRP combination. This is qualitative manufacturer guidance, not a coupled performance map or a selected hopper pairing.

Consequences for this trade: retain the equal-size E/EP pairs as comparison candidates, but also assess unequal-diameter/pitch alternatives when supported by motor data. Neither matched handedness nor the FAQ demonstrates equal torque, current or thrust. Physical viewing direction, blade orientation and retention must be explicitly reconciled with CAD and the plant. Do not double isolated thrust. Keep upper/lower thrust interference and upper/lower torque interference as separate calibration parameters, with spacing and operating-domain dependence.

## P06: propeller RPM domain

The current [APC RPM Limits page](https://www.apcprop.com/technical-information/rpm-limits/?v=84de8e2b14bb) specifies maximum recommended speed for Thin Electric as 150000 divided by diameter in inches, in rpm. The [manufacturer Rev 5 document, dated 2022-03-23, page 1](https://www.apcprop.com/wp-content/uploads/2022/03/APC-Propeller-RPM-Limits-rev5.pdf) corroborates that category formula. It is not the different Multi-Rotor-series formula.

Use 150000/13 and 150000/11 rpm as candidate limit expressions in subsequent executable calculations. Actual loaded RPM is still needed; motor KV times nominal voltage is not a measured operating speed. These limits establish neither coaxial blade clearance nor endurance qualification.

## E01–E02: manufacturer ESC variants

The [Hobbywing Skywalker V2 manufacturer specification matrix](https://www.hobbywing.com/en/index.php/products/skywalker-v2-series274) distinguishes:

| ID | Exact part number | Variant | LiPo input | Continuous / peak current | BEC | Body dimensions | Listed mass |
|---|---|---|---|---|---|---|---|
| E01 | 80060442 | Skywalker 50A V2 | 3–4S | 50 / 70 A | 5 V, 5 A switching | 60 × 25 × 8 mm | 36 g |
| E02 | 30216400 | Skywalker 50A-6S V2 | 3–6S | 50 / 70 A | 5 V, 6 A switching | 73 × 30 × 12 mm | 68 g |

These are advertised ratings, not installed cooling verification. Peak duration and mission thermal derating are unresolved. E01 lists 14 AWG, 100 mm input leads; 16 AWG, 75 mm motor leads; no input connector; 3.5 mm female motor bullets. Harness/mass inclusions require reconciliation before adding separate wiring allowances.

The [Hobbywing North America series page](https://www.hobbywingdirect.com/products/skywalker-esc?variant=41312598589555) calls part 30216400 '50A V2 Plus' and confirms its 3–6S input, distinguishing it from 80060442. Neither manufacturer page establishes an inspected current price, currency, stock count or purchase minimum in this register. Do not substitute E02 mass or BEC specifications into E01.

Documentation conflict: the search-indexed table from [Hobbywing's Chinese-language manual URL](https://www.hobbywing.com/uploads/file/20240717/003cfdbd5f9fad6ac356f2396c8103b3.pdf) lists 5 V/5 A for the 50A-6S variant, versus 5 V/6 A on the manufacturer matrix. A subsequent full-text retrieval timed out. Preserve this as a documentation discrepancy requiring exact supplied-revision confirmation; do not silently take the higher rating.

## E03: Australian supplier price and availability limitation

[The Joy Box product page](https://thejoybox.com.au/products/hobbywing-skywalker-v2-60a-esc-6a-bec), product/pricing/specification/package sections, displays AUD 45.95 including taxes for a Skywalker V2 50A, 5 A BEC. Listed package: one ESC and manual. Body specifications match E01, but no inspected manufacturer part number establishes the exact SKU. The URL instead describes 60A/6A: retain that mismatch.

The extracted page contains both a sold-out label and an add-to-cart control. Treat dispatchable availability as unconfirmed, not in stock. Retail package quantity is one; no larger minimum is stated. Proposed dual-motor scenarios need two independently commanded ESCs.

Shipping is excluded from the budget. The page advertises free shipping above AUD 29 but also describes checkout-dependent eligibility; no delivery charge or credit is assumed. Tax is included, but the inspected page does not identify its rate or component. Do not automatically divide by 1.1. The tax-exclusive price is unresolved. This listing cannot yet establish procurement readiness or an exact ex-tax AUD ledger amount.

## E04: command, response and protection evidence

The official [Skywalker support index](https://support.hobbywingdirect.com/hc/en-us/articles/19617280940435-Skywalker-series) links the [V2 manual attachment](https://support.hobbywingdirect.com/hc/en-us/article_attachments/29009714926611). Page 1 body identifies Skywalker V2, dated 20221221, despite inconsistent PDF metadata naming a Platinum unit. Text reviewed; wiring figures were not visually accepted.

Page 1, sections 04/06/07: default throttle endpoints 1100–1940 microseconds; calibration required. White wire carries throttle, red/black are BEC supply. Normal/soft/very-soft 0–100% acceleration settings are approximately 200/500/800 ms. Signal loss exceeding 0.25 s cuts output, with resumption when signals return. Thermal protection begins above 120 °C. Low-voltage choices are approximately 2.8/3.0/3.4 V per cell. Soft cutoff describes reduction to 60% over 3 s; troubleshooting instead mentions 50%, so retain that inconsistency. Hard cutoff removes output immediately. These are documentation claims, not measured installed dynamics.

Engineering interpretation, not vendor qualification: the acceleration figures are not measured first-order motor time constants. Retain separate configurable command slew/startup, motor lag, transport delay, deadband and asymmetric acceleration/deceleration uncertainty. Input repetition-rate limits, loaded response and precise supplied firmware behavior remain unknown. Protection thresholds are not normal operating targets. Do not choose cutoff/brake settings without Chief disposition and a safety assessment.

## Integration and accounting consequences

- Use independent motor commands for simultaneous collective thrust and differential reaction torque. A common throttle signal cannot establish independent yaw authority. Torque-balanced trim must allow unequal commands.
- Do not parallel ESC BEC outputs without an explicitly supported power architecture. Compare one active BEC plus isolated second positive lead against a separately sourced regulator; preserve common signal-reference and fault-path requirements.
- Include both ESCs, their actual included leads, required input connectors, mating motor bullets, distribution, protection, insulation and retention exactly once. Add remaining ancillary hardware explicitly; this is not a complete mass ledger.
- Keep battery loaded voltage, total current and auxiliary regulator loads coupled to propulsion. Ratings alone do not establish usable energy for spool-up, climb, acquisition, uninterrupted 300 s hover and landing.
- CAD handoff needs body dimensions plus lead bends, connector access, cooling clearance and attachment hardware. Listed dimensions are envelopes, not mounting drawings or accepted interfaces.
- The 499.99 AUD cap remains unchanged. No subtotal, unconfirmed currency conversion or missing hardware price constitutes compliance.

## Retrieval limitations and follow-up

Retained failures: direct rereads of the Chinese manual and APC RPM/general-FAQ pages timed out; the General FAQ was subsequently retrieved successfully through its canonical query URL, and RPM data through indexed manufacturer material. The attempted guessed adapter-ring URL https://www.apcprop.com/product/adapter-rings-electric/ was inaccessible; no ring dimensions were inferred from it. A support-index inline manual link failed, while its attachment link yielded the text documented above.

Next evidence needs: exact adapter/retention drawings; supplier confirmation of ESC SKU, availability and tax basis; command-frequency specification and supplied manual revision; battery sourcing and load data; control/sensing/abort alternatives; CAD-derived complete mass; and executable coupled propulsion/mission calculations. PyThrust entry points, loaders, raw data and current import capability still require inspection before execution. No hardware or topology has been selected, and no physical test has been performed.
