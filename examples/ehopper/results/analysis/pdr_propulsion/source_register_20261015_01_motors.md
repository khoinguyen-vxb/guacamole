# PDR propulsion source register 01 — motors and module alternatives

## Authority and evidence status

Task: pdr_propulsion_trade. Current authority: system model revision 1, SHA256 555c3753f99fdc172ff087527158537f0264eb7ffe12861692c2db71f3dde57b; work-plan decision b8988137b7274bddb05c87f7884c81fd revision 1. This is comparative research, not hardware selection, procurement approval or verification.

The current brief and context/previous_run/README.md were reviewed first. Archived propulsion registers supplied search leads only. Their decisions, restrictions and numerical claims are not current authority.

Access date for EVERY web observation below: **2026-10-15**. Method: provider-side live search and HTML retrieval. Search infrastructure may serve cached content; access date is not a quotation or supplier confirmation date. Page-section names and retrieval line numbers identify observations, not stable pagination. No drawings, product images or binary manuals were inspected. No supplier contact, checkout, purchase, installation, engineering execution or physical test occurred.

Classification: SOURCED = retrieved vendor claim; SEARCH-ONLY = indexed lead not corroborated by an opened page; ASSUMED = study hypothesis; COMPUTED = retained-program result; CALIBRATED = measurement-supported fit. This note contains no COMPUTED or CALIBRATED performance.

## M01 — separate-motor candidate, original SunnySky X2814 KV900

Candidate ID: MOTOR-SS-X2814-900-ORIGINAL; exclude X2814 V3/III substitutions.

[SunnySky USA product specifications](https://sunnyskyusa.com/products/sunnysky-x2814-brushless-motors), KV900 block, retrieval lines 65–103: 900 rpm/V; resistance 52 mOhm; no-load current 0.7 A at 10 V; 108 g; diameter 35 mm; body length 36 mm excluding shaft, overall length 54 mm; shaft diameter 4 mm; 3–4S LiPo. Catalogue power is 570 W; current rating is time-limited, 40 A for 30 s. No 300-second thermal qualification follows.

Isolated performance records below are (current_A, thrust_gf, electrical_power_W), transcribed without interpolation:

- APC13x6.5, 11.1 V: (5,500,55.5); (8.7,750,96.57); (13,1000,144.3); (18.3,1250,203.13); (24.2,1500,268.62); (27.6,1650,306.36); (29.5,1750,327.45).
- APC11x5.5, 14.8 V: (4.5,500,66.6); (7.9,750,116.92); (11.7,1000,173.16); (15.8,1250,233.84); (20.6,1500,304.88); (25.7,1750,380.36); (29.3,1950,433.64).

The corresponding temperature entries are 47° and 48°; scale, duration, ambient conditions and measurement method are not established. RPM, torque, exact propeller suffix and reverse-propeller equivalence remain unknown. These are not combined coaxial data.

[Buddy RC exact candidate listing](https://www.buddyrc.com/products/sunnysky-x2814-brushless-motors), SKU/variant/price section, retrieval lines 288–322: SS-X2814-900, selected KV900, displayed $29.99 per motor listing. Currency code is not explicit; USD is a provisional inference from the US supplier location, not established accounting evidence. Tax basis unknown; shipping excluded from this observation and the vehicle-cap calculation. Listed singly, with no greater minimum shown; proposed trade purchase/install quantity is two, subject to package confirmation. Add-to-cart appears but affirmative stock quantity is absent: availability UNKNOWN. The specification table corroborates the manufacturer values. Accessories, lead inclusion and installed-mass inclusions remain unresolved. No mounting-hole drawing has been inspected.

## M02 — integrated Himax CR2816-1100 combo

Candidate ID: MODULE-HIMAX-CR28161100.

[Himax Motors product page](https://himaxmotors.com/products/himax-cr28161100-contra-rotating-motor-and-propeller-combo), product/specification section, retrieval lines 67–100: CR28161100; displayed $153.99 per combo; currency code/tax unknown, USD provisional only. Add-to-cart is not stock confirmation. Single combo listing; no larger minimum shown. Shipping excluded/unquoted.

Claims: 164 g including prop attachments; diameter 27.8 mm; length 65 mm; front/rear shafts 4.0/9.5 mm; four 3.5 mm through-holes on 43 mm bolt circle. Ratings: 1100 rpm/V, 350 W, 20,000 rpm, 65 °C case maximum; 6–16 A efficient operating range per rotor, 20 A for 15 s per rotor. Resistance and no-load current remain unspecified. Battery recommendation: 3S capable of 35–40 A continuous; two 25 A ESCs. Front prop APC10x5E; rear designation differs between MPI9x7R and MX9x7R. No thrust/current/torque map is provided.

[Buddy RC listing](https://www.buddyrc.com/products/himax-cr28161100-contra-rotating-motor-and-propeller-combo), SKU/price section, retrieval lines 282–302, corroborates SKU CR28161100 and displayed $153.99. Currency/tax unknown; stock unconfirmed; one combo listing, no higher minimum shown; shipping unquoted/excluded. Initial retrieval of the non-www URL failed; the www URL succeeded. This is a research retrieval limitation, not a Guacamole tool failure.

Engineering limitation: a common throttle Y-harness is not an independently commanded differential-yaw interface. Preserve two command channels in any candidate implementation; no motor-response or yaw-authority claim is established here. Textual bolt-circle data are not an inspected mounting drawing, shaft-load rating or verified support design.

## M03 — integrated Himax CR3516-1030 combo

Candidate ID: MODULE-HIMAX-CR35161030.

[Buddy RC product page](https://www.buddyrc.com/products/copy-of-himax-cr28161100-contra-rotating-motor-and-propeller-combo), price and specifications, retrieval lines 282–358: SKU CR35161030; displayed $199.99; SOLD OUT. Currency code/tax unknown; USD provisional inference only. Single combo listing, no higher minimum shown; shipping unquoted/excluded.

Claims: 275 g including adapter; diameter 35.3 mm; length 64.3 mm; front/rear shafts 4.73/9.48 mm; four 3.17 mm through-holes on 43 mm bolt circle; 1030 rpm/V; 800 W; 12,000 rpm; 65 °C case maximum. Resistance is malformed as .0.035; do not silently normalize. Front/rear no-load currents are 4.8/2.3 A at 10 V. Efficient current: 30–36 A per rotor; maximum 40 A for 15 s. Recommended 3S supply: 70–80 A continuous; two 35 A ESCs. Header props: APC12X6EP and APC11X8E; description instead names APC12x6P front. No performance map is provided.

Unresolved internal issue: the upper efficient-current value exceeds the recommended ESC's nominal 35 A label. Exact ESC variant, duty, cooling, propeller suffix and supplied revision need clarification. A linked manual exists but was not inspected.

## M04 — conflicting integrated-module performance leads, SEARCH-ONLY

[Buddy RC contra-motor comparison](https://www.buddyrc.com/products/copy-of-himax-contra-rotating-motors) appeared in current search results, but direct opening failed. Search metadata reported a crawl about 1.3 years old. Indexed CR2816-1100 row: 440 W, static thrust 69 oz, Rm .048, Io 1.8; CR3516-1030 row: 800 W, static thrust 98 oz, Rm .035, Io 2.0. These are not accepted current specifications. The CR2816 power conflicts with M02's 350 W, and its indexed electrical parameters replace values that M02 leaves unspecified. The CR3516 indexed Io differs from M03's separate rotor values.

A second indexed [Ibcinyou RC CR2816 combo listing](https://www.ibcinyourc.com/store.php/carden540/pd10966188/himax_contrarotating_motor_cr28161100_combo_) reports 72 oz static thrust, 440 W and two 20 A ESCs, also differing from the other leads. This page was not directly opened; price, stock, minimum quantity, currency and tax are not admitted from it.

Do not treat any indexed thrust number as a measured combined-module map or pair it with an unrelated current. Test voltage, throttle, duration, RPM, propeller revision, atmosphere, torque split and total-versus-per-rotor interpretation require confirmation. This register explicitly preserves the contradictions rather than selecting favourable values.

## M05 — lower-price CRM integrated-module lead

[Redwing RC product listing](https://www.redwingrc.com/product.php?productid=2219), Options/Details, retrieval lines 146–188: displayed $83.99; SKU DW-CRM2208 1600KV; availability field says two in stock, while a back-in-stock notification control also appears. Variant-specific availability therefore remains provisional. Currency code/tax unknown; USD inference only. Shipping unquoted/excluded. Motor and ESC-combo selectors are present; the extracted price is not established for CRM2413 or any other variant. A quantity control labelled Quantity (2) does not establish a two-module package or minimum purchase quantity. MOQ/package contents UNKNOWN.

The displayed 1.00 lb weight has no established installed-mass basis; do not use it as motor mass. Numerical specifications are embedded in uninspected images. Mounts, dimensions, thrust, current, voltage limits and response remain UNKNOWN in this register. No CRM2413 thrust values from the archive are promoted to current evidence.

## Candidate-study implications and required continuation

1. Retain separate-motor and integrated-module branches. Integrated packaging may simplify support, but complete mounting/load-path evidence is still required. Separate outrunners require a realizable stationary support arrangement coordinated with CAD; no geometry is selected here.
2. Never double the isolated M01 thrust table. Future editable calculations must retain separate upper/lower thrust and torque interference factors, rotor spacing/domain, independent command mapping, motor/ESC lag, current and voltage limits, and calibration status. Equal RPM is not proof of equal reaction torque.
3. Full installed mass must include one battery, both propulsion channels, gimbal actuation and mechanism, avionics/sensors/abort interface, regulation, distribution, harnesses, connectors, retention, fasteners and complete structure. Commercial assembly masses and CAD envelope masses must not be duplicated. Missing rows remain unknown.
4. Purchase accounting must charge complete minimum packs, including two batteries while one flies; PETG mass remains included but printed-part cost excluded. Ground equipment is separately priced. No AUD conversion, total or budget-compliance claim is made. The authoritative cost metric remains purchased_vehicle_hardware_materials_cost, limit 499.99 AUD after 0.01 AUD quantization.
5. Mission sizing must include spool-up, climb to hover_target_rise 5.00 m, acquisition, hover_duration at least 300 s, descent and landing, plus auxiliary conversion losses. Usable battery energy, sag, thermal duration and reserve remain open, not zero.
6. Next inspections: PyThrust directory/entry points/loaders/raw datasets; exact opposite-rotation propellers and retention; ESCs; batteries; actuator and control/power hardware. The supplied PyThrust README and pyproject were reviewed, but repository presence is not import/execution capability. No installation or source modification is authorized.
7. Critical missing supplier data will be escalated with focused choices and exact artifact references. CAD and plant exchanges must use actual peer agent IDs once available. This note establishes neither numerical recommendations nor final component selection.
