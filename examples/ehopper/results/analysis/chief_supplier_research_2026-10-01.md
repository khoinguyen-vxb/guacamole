# Supplier research — 2026-10-01

Status: preliminary evidence, not component selection or procurement approval. Access date for every source below: 2026-10-01. Web extraction inspected text, not performance-chart images or mounting drawings.

## SunnySky X2814-900 comparison candidate

Source: [Buddy RC product page](https://www.buddyrc.com/products/sunnysky-x2814-brushless-motors), SKU/price section and KV900 specification/performance tables.

Displayed SKU SS-X2814-900; price $29.99 per motor. Currency is not explicit in the extracted price; no AUD conversion applied. Specifications: 900 rpm/V, resistance 52 mΩ, no-load current 0.7 A at 10 V, mass 108 g, rotor diameter 35 mm, body length excluding shaft 36 mm, overall length 54 mm, shaft diameter 4 mm, 3–4S LiPo. Listed current limit is 40 A/30 s despite its continuous-current heading; it does NOT establish a 300-second thermal rating. Listed maximum power 570 W.

Isolated APC13x6.5 table at 11.1 V lists (current A, thrust gf, electrical power W): (5,500,55.5), (8.7,750,96.57), (13,1000,144.3), (18.3,1250,203.13), (24.2,1500,268.62). These are supplier data, not our measurements or coaxial results. Mounting-hole geometry and reverse-rotation propeller compatibility remain unverified.

## RCDrone Hobbywing Skywalker listing

Source: [RCDrone Skywalker series](https://rcdrone.top/products/hobbywing-skywalker-series), price/variant section and individual current-rating descriptions.

Page displays USD 22.18, taxes included, and Sold out; selectable variants include 20/30/40/50/60/80 A. The extracted price is not reliably associated with a selected variant: do not use it as a 50 A quote.

The 40 A description specifies 2–3S, 39 g and 68 × 25 × 8 mm. It is unsuitable for the assumed 4S bus on that evidence, regardless of the broad 2–6S title. The 50 A description specifies 2–4S, 50 A continuous, 65 A short-duration, 5 V/5 A BEC, 43 g, 65 × 25 × 12 mm and 50–432 Hz command range. These are unverified listing claims; exact model generation, thermal conditions and variant-specific availability/price require confirmation.

Manufacturer follow-up: [Hobbywing Skywalker support](https://support.hobbywingdirect.com/hc/en-us/articles/19617280940435-Skywalker-series) separately lists original and V2 variants and links their manuals. Manuals have not yet been inspected; do not interchange their ratings.

## Jaycar battery search

Source: [Jaycar GT4264](https://www.jaycar.com.au/spare-li-po-battery-to-suit-gt-4261-4wd/p/GT4264), overview and specifications returned in search.

Search located a 7.4 V, 1800 mAh, 13.32 Wh pack, displayed $20.97 on Jaycar Australia. AUD is inferred from the Australian storefront, not explicitly printed beside this extracted price; tax treatment unverified. This is not the requested 4S propulsion candidate. Continuous discharge capability and mass were not supplied. A listed 999 mm height is suspicious and must not enter CAD. Search did not establish that Jaycar has no suitable alternative.

## Propeller search limitations

Attempts to open https://www.apcprop.com/product/14x4-7mr/ and https://www.apcprop.com/product/14x4-7mrp/ returned internal errors. Those attempted URLs establish neither product existence nor dimensions, price, handedness or availability. Continue with verified catalogue links and matched rotation variants before adopting any propeller.

## Implications for the next trade update

1. Recover and inspect the existing screening implementation and PyThrust solver interfaces before rerunning or changing them.
2. Keep all previous hypothetical battery, ESC, propeller and motor-price allowances labelled as assumptions; do not promote numerical feasibility to procurement feasibility.
3. Obtain matched CW/CCW product evidence and variant-specific ESC/battery quotes, dimensions, masses and limits. Check original versus V2 motor/ESC identities against catalogue entries.
4. Apply dated currency conversion only after currency is established; keep tax-inclusive displayed prices separate from the confirmed tax/shipping-exclusive AUD 500 ceiling.
5. Retain whole-vehicle mass, mission energy, coaxial loss/torque calibration, voltage sag and continuous thermal uncertainty in subsequent comparisons.
