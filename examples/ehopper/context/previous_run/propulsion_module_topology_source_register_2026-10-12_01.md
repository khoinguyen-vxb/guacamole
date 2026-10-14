# PDR r12 — propulsion-module topology source register 01

Access date for every web observation: **2026-10-12**. Prepared by the Chief under validated plan 66c7448f443f44ac9a016a1b384593a2 r1 (deliverables PDR-R12-PROPULSION-BUDGET and PDR-R12-STRUCTURE-CAD).

**Status:** provider-side web research recorded as preliminary supplier and precedent evidence. It selects no motor, propeller, ESC, battery or module topology. It does not establish thrust, endurance, budget, geometry or flight compliance. Prices and stock are catalogue observations, not quotations. Only page text was inspected (no images, drawings or datasheet PDFs). No Guacamole engineering tool computed anything in this note.

## 1. Question addressed

REQ-PROPULSION-PLACEMENT r1 puts both rotors below the structure. The retained common two-axis gimbal (84ef41fdd3fd4266ada43df2ace64a48; convention 28e10be57d6548a3aa5be06c96f6d0d0 r1) sits above them. A non-rotating load path must therefore run from the gimbal to both motors. With two separate conventional outrunners, one propeller disc always lies between the gimbal and a motor, so a member must bypass that disc. PDR-R12-STRUCTURAL-TRADE-CONFIG-01 uses a moving outboard yoke for this. The Chief's unverified hand check (summary 598b769493da4beba1b081eb4827f7a9, item C4) predicts interference through +/-15 deg travel between the yoke's pivot-plane crossmember and both the B45 leg braces and the leg ring. An integrated contra-rotating unit removes the bypass: two independently driven rotors share one stationary axle and a single rear mounting face. context/reference_designs.md describes Vehicle A's motor as an integrated contra-rotating unit and the other vehicles' propulsion as one coaxial motor unit (qualitative evidence only). This register asks whether purchasable integrated units match the current thrust, endurance and budget scale.

## 2. Integrated contra-rotating units: product pages retrieved directly

- **HMX-CR2816-1100-COMBO**: Himax CR2816 1100KV Contra Rotating Motor and Propeller Combo, BuddyRC (MPI Hobby SKU CR28161100).
  - Price and stock: displayed sale price 153.99, page text USD; tax basis not stated; no stock status shown, though an add-to-cart button is present.
  - Electrical: 1100 Kv; 3S LiPo; 20 A maximum for 15 s per rotor, efficient operation at 6–16 A per rotor; maximum power 350 W; maximum 20,000 rpm; maximum case temperature 65 °C. Rm and Io are printed as 'tba'.
  - Mechanical: 164 g including prop attachments; Ø27.8 mm × 65 mm; shafts 4.0 mm front and 9.5 mm rear; four 3.5 mm through holes on a 43 mm bolt circle.
  - Props: APC 10x5E front. The rear prop is MX9x7R in the specification but MPI 9X7R in the description.
  - Requirements: two 25 A ESCs and a Y-harness ('will not run with one ESC'). No thrust data.
  - https://buddyrc.com/products/himax-cr28161100-contra-rotating-motor-and-propeller-combo
- **HMX-CR3516-1030-COMBO**: Himax CR3516 1030KV Contra Rotating Motor and Propeller Combo, BuddyRC (SKU CR35161030).
  - Price and stock: displayed sale price 199.99; USD inferred (US retailer, no currency code); tax basis not stated; **sold out**.
  - Electrical: 1030 Kv; Rm printed '.0.035'; Io 4.8 A front and 2.3 A rear at 10 V; maximum power 800 W; maximum 12,000 rpm; efficient 30–36 A per rotor, 40 A maximum for 15 s per rotor.
  - Mechanical: 275 g with prop adapter; Ø35.3 mm × 64.3 mm; shafts 4.73 mm front and 9.48 mm rear; four 3.17 mm through holes on a 43 mm bolt circle.
  - Battery and props: 3S battery able to sustain 70–80 A continuous; suggested props APC 12x6P front (header '12X6EP') and APC 11x8E rear.
  - Requirements: two 35 A ESCs and a Y-harness. No thrust data.
  - https://www.buddyrc.com/products/copy-of-himax-cr28161100-contra-rotating-motor-and-propeller-combo
- **DW-CRM-SYSTEMS**: 'Contra-Rotating Dual Brushless Motor Systems (1300-1600KV)', Redwing RC.
  - Price and stock: one displayed price, 83.99, not broken out by variant; '$' with USD inferred; tax not stated. '2 in stock' is shown for SKU DW-CRM2208 1600KV.
  - Variants: CRM2204 1400KV, CRM2208 1600KV, CRM2405 1500KV, CRM2409 1300KV and CRM2413 1300KV. Optional ESC add-ons cost +20.00 to +23.00.
  - Numerical specifications are only in images, which were not inspected.
  - https://www.redwingrc.com/product.php?productid=2219

## 3. Search-result summaries only (pages not retrieved; unverified)

- CRM2413A 1300KV, from copied reseller specifications on Amazon, desertcart and ubuy:
  - 170 g; rated 12 V.
  - Thrust with GWS 8040: 1082 g at 10 V, 1188 g at 12 V, 1385 g at 12.6 V. With GWS 9050: 1582 g at 12 V, 1696 g at 12.6 V.
  - Two 30 A ESCs recommended; two 9-inch props and an adapter included.
  - Unverified: whether the thrust is combined across both rotors, and the test conditions. 4S use is anecdotal only.
  - The desertcart fetch returned HTTP 403, and the retrieved Amazon text was truncated before the specifications. https://www.amazon.com/Brushless-Contra-rotating-CRM2413-Airplane-propellers/dp/B07D7SYPMK
- DZP30 1500KV contra motor: 32 g; about 280 g per rotor at 11.1 V and 5.1 A per rotor (formatting ambiguous); GWS 7035 three-blade prop pair. Snippets show about US$49.46 at Banggood and US$73.75 at AliExpress. Far too small for this vehicle. https://www.banggood.com/DZP30-Contra-rotating-1500KV-Dual-Brushless-Motor-with-Dual-3-Blade-Propellers-32g-for-Fixed-Wing-Plane-RC-Airplane-Aircraft-p-1599932.html
- HobbyKing 'Co Axial Contra Rotating Brushless motors 375w' and 'Contra Rotating CR50L' (snippet: 80 A per motor): both pages returned HTTP 403, so no price or specification is recorded. A relayed hobbyist review reports about 100 W real output from the 375 W unit; this is anecdotal.

## 4. Coaxial products outside this vehicle's scale (noted, not candidates)

- MAD 6X12 PRO L 170KV coaxial arm set (12S, 24-inch props), listed by rcdrone.top: https://rcdrone.top/products/mad-6x12-pro-l-170kv-coaxial-contra-rotating-drone-arm-set
- Eaglepower EA110X2 coaxial agricultural motors (12–14S): https://www.arrishobby.com/products/eaglepower-ea110x2-coaxial-contra-rotating-big-thrust-brushless-motors-for-uav-agriculture-drones-1064

## 5. Precedents (comparative evidence, not project data)

- **E-Rocket TVC testbed, arXiv 2512.06535 (HTML retrieved).** https://arxiv.org/html/2512.06535
  - Propulsion: a pair of contra-rotating T-Motor F60 PRO V 2020KV motors with 5-inch Hurricane MCK 51466 V2 props; T-Motor AT55A ESCs. The paper does not say whether the motors are an integrated unit or mounted back-to-back.
  - Gimbal: Power HD 30KG servos with a +/-30 deg command range.
  - Battery: Tattu R-Line 1800 mAh LiPo. The cell count is rendered ambiguously; the table reads '6SP'.
  - Vehicle: total mass 1.6 kg; combined thrust '3 kgf', hovering at about 60% throttle; about 3 minutes of continuous hover. Four CFRP tube legs total 0.033 kg. Gimbal-to-CG distance L = 0.26 m; j_perp = 0.375 kg m^2.
  - Models: static-test thrust map T = 26.45*Mbar - 0.3821 N. Differential-yaw map tau_delta_bar = 23.99*dM + 0.4031*Mbar + 0.02432 rad/s^2, identified below hover and extrapolated above it. Aerodynamics and actuator dynamics are neglected.
  - Gains (not transferable): position PID Kp = diag(3,3,8.5), Kd = diag(2.5,2.5,3), Ki = diag(0.2,0.2,1); attitude Kp = diag(5,5,5), Kd = diag(2,2,2), Ki = diag(0,0,0.5).
- **DIY thrust-vectoring coaxial drone (diydrones, 2016).** Himax CR2805 contra motor, with the 7x5 props replaced by 9x3 for efficiency. Yaw comes from the speed difference between the upper and lower props. Inner and outer loops are P-only; the author reported that integral action caused a pendulum effect. Servos drive the roll and pitch plates. https://diydrones.com/profiles/blogs/thrust-vectoring-coaxial-drone-update
- **Patent US 12545445 / US 2024/0417113 'Rotary wing aircraft'** (search summary only, not retrieved): U8 Lite 190 KV motors, Futaba S3003 servos and a 3D-printed two-axis gimbal; thrust and yaw from differential rpm.

## 6. Retrieval limitations

- HTTP 403: hobbyking.com (two pages) and desertcart.nl.
- HTTP 429: the BuddyRC 'Himax Contra-Rotating Motors ONLY' page.
- DNS failure: maxxprod.com.
- The Amazon text was truncated before the specifications.
- A Chinese-language search found no contra-motor listings, and Taobao and Temu could not be searched with the available tools.

## 7. Engineering interpretation (Chief, preliminary, not a selection)

1. Geometry: an integrated unit removes the disc bypass. A single rear face (a 43 mm bolt circle on both Himax units) mounts to the gimbal inner frame, and both props hang below. Both Himax pages require one ESC per rotor, so independent rotor speed for differential yaw torque is available in principle.
2. Scale: every integrated unit found is an airplane unit for 9–12-inch props.
   - The affordable CRM2413A class reports at most about 1.7 kgf (unverified) on 9-inch props.
   - The CR2816 is limited to 350 W on 3S.
   - The 800 W CR3516 (12-inch front, 11-inch rear props) costs USD 199.99 before ESCs and is sold out at the only seller inspected.
3. Disc loading: momentum theory, P = T^1.5 / sqrt(2*rho*A) with rho = 1.225 kg/m^3, gives these ideal powers for T = 12.75 N (a hypothetical 1.30 kg vehicle, not a project mass): 143.6 W on a 9-inch disc, 117.5 W on 11 inches and 99.4 W on 13 inches. The 9-inch disc needs about 44% more ideal power than the 13-inch disc. This is a Chief hand calculation, not a tool result, and it ignores coaxial interference and profile power. E-Rocket's short hover on 5-inch props is qualitatively consistent.
4. Consequence for the CAD candidates requested in human note 51a1c7e564004f9fbd3db6ae44325332 (279.4 mm and 330.2 mm props): none of the integrated units inspected offers matching 11- or 13-inch capability within the evidence obtained. Keep separate motors with a moving bypass yoke as the CAD baseline until a Chief decision is recorded. Treat an integrated contra unit as an alternative module topology; it needs an exact in-stock product, an AUD price and thrust/current data.
5. With the yoke baseline, CAD revision 02 must resolve the interference through geometry and report actual CAD distances. Options: raise the leg ring above the crossmember's swept volume; phase the braces away from the yoke arms (quadpod gaps align naturally with a two-arm yoke); or use an inverted-V yoke. Collisions must not be waived.
6. Combined coaxial thrust must come from measured coaxial data with stated conditions, or from a calibratable interference model. Never double isolated-rotor thrust.
7. Budget: no USD price here has been converted or tax-adjusted. FX rates and AUD equivalents remain open, and complete-vehicle cost < AUD 500 has not been assessed.

## 8. Open items

- An exact AUD quote and stock confirmation for any integrated unit (other Himax CR3516/CR2816 sellers; an AEO CRM2413 datasheet). Human help may be needed for Taobao/Temu.
- Thrust, torque and current maps for the selected module, retaining parameters for coaxial-interference and motor/ESC-response calibration.
- A Chief decision on module topology, based on numerical evidence (PyThrust and energy screening) and CAD evidence. Inform the human once the topology is chosen.
