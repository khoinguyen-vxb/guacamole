# R4 purchasing-gap supplier research

Access date for all web evidence below: **2026-10-03**. Currency: **AUD**. Evidence type: provider-side supplier/manufacturer web research, not a quotation, purchase, physical measurement or verification result. Sections cited are HTML product price, package contents and specifications unless stated otherwise. No figure-derived dimensions are asserted.

## Accounting boundary

REQ-HARDWARE-BUDGET revision 4 requires whole minimum purchases, including the two-battery vehicle pack, with reusable ground equipment separately priced and nothing assumed owned. Preserve the current accounting baseline and its inconclusive verification (request 341f8caea1544381a306fb308a725f8f). This research does not change the baseline totals or resolve its missing-item checks. Candidate quantities below require reconciliation with the actual harness and assembly schedule; they are not engineering selections.

## Vehicle consumables and connection candidates

- **Jaycar NS3092 solder:** one complete 15 g tube, **AUD5.95** displayed. Wire diameter 1.0 mm; resin core; stated alloy 99.3% tin/0.7% copper. Charge the entire tube to the vehicle, but derive installed solder mass separately. Additional flux need remains process-dependent. Stock requires postcode/store confirmation; GST treatment was not explicit in the extracted product text, so do not silently deduct tax. [Supplier price and specifications](https://www.jaycar.com.au/1-0mm-15g-lead-free-solder-hobby-tube/p/NS3092).

- **Jaycar WH5525 heatshrink:** one complete ten-piece assortment, **AUD9.25** displayed; nominal diameters 1.5–10 mm, mixed 150/300 mm lengths. The specifications include a credible 2:1 shrink-ratio entry and a conflicting malformed duplicate; retain that conflict. Exact size/length distribution and harness coverage remain unverified. Stock and explicit GST treatment unresolved. [Supplier package and specifications](https://www.jaycar.com.au/assorted-heatshrink-pack-1-5-10mm/p/WH5525).

- **Core CE07828 male header:** one 40-position strip, 2.54 mm pitch, **AUD0.45 including GST / AUD0.41 excluding GST**, listed strip mass 2.3 g. Direct page showed 1,360 locally stocked. Determine required strip count from the pin schedule; purchase whole strips and count only installed sections in flight mass. Header availability is not evidence of vibration-resistant connector retention. [Supplier price and specifications](https://core-electronics.com.au/male-pin-header-2-54mm-1x40.html).

- **Conditional extra flux, Jaycar NS3036:** one 12 mL pen, **AUD17.50** displayed. Supplier describes no-clean flux for rework and copper/tinned tracks and identifies flammable dangerous goods. Compatibility with the selected solder/process and need for separate flux remain unconfirmed. If required, charge the whole pen, not the consumed fraction. GST and destination stock unresolved. [Supplier price, overview and handling classification](https://www.jaycar.com.au/solder-flux-pen-12ml/p/NS3036).

- **Small-fastener locking candidate, Loctite 222:** manufacturer describes low-strength locking for threads up to 6.35 mm and hand-tool disassembly. This is not approval for plastic interfaces or every joint. A retailer product-page opening failed and indexed prices conflicted, so no firm price is retained. Locking method, surface preparation, compatibility and complete purchase cost remain open. [Manufacturer application information](https://www.loctite-consumer.com.au/products/central-pdp.html/loctite-222/BP000340.html).

## Separately priced reusable ground-equipment candidates

These are an initial radio/charging subset, not the complete GSE list. No flight mass is assigned to them.

| Candidate and complete purchase quantity | Observed price | Package/specification evidence and limitations |
|---|---:|---|
| RadioMaster Pocket, one ELRS 2.4 GHz transmitter | AUD128.99 including GST | Selected supplier variant showed 20+ stock; batteries excluded. Do not substitute CC2500. [Supplier](https://phaserfpv.com.au/products/radiomaster-pocket-radio-transmitter-cc2500-elrs-24ghz). |
| Panasonic 18650B, two individual cells | AUD16.99 each including GST; displayed ex-GST AUD15.45 each | Page package lists **one** cell despite `2x` in URL. Listed 3.6–3.7 V, 3400 mAh, 18.06 mm diameter × 65 mm, 46 g each. Stock remained loading; confirm terminal style and fit. [Supplier](https://www.fpvfaster.com.au/products/2x-panasonic-18650b-3400mah-3-7v-rechargeable-li-ion-battery). |
| Powertech MP3408, one USB mains adaptor | AUD11.95 displayed; tax treatment unresolved | 100–240 VAC input, two USB-A outlets sharing up to 2.4 A; intended here for transmitter charging only. Destination stock unconfirmed. [Supplier](https://www.jaycar.com.au/12w-dual-2xusb-a-mains-power-adaptor/p/MP3408). |
| SkyRC B6ACneo, one AU-plug charger package | AUD99.50 including GST; displayed ex-GST AUD90.45 | Includes charger and AU plug; integrated 100–240 VAC supply, 60 W AC charging, 1–6S lithium support, balance/storage modes. No separate DC supply needed for AC use. Availability remained loading. [Supplier](https://www.fpvfaster.com.au/products/skyrc-b6ac-neo-1-6s-smart-charger-pd-ac-60w-dc-200w-au-plug). |
| Plexa XT60 extension, one assembled lead | AUD9.95 displayed; tax treatment unresolved | Female-to-male XT60, 30 cm, 14 AWG; page showed three remaining. Confirm connector mating and polarity. [Supplier](https://www.mantisfpv.com.au/plexa-xt60-female-to-xt60-male-30cm-14awg-extension-cable/). |
| One 4S JST-XH balance extension | AUD3.95 including GST | Select five-pin/4S variant: 22 cm, 22 AWG. Current package describes **one** extension despite `set-4pcs` in URL. 4S variant showed 20+ stock. [Supplier](https://phaserfpv.com.au/products/balance-lead-extension-cable-set-4pcs). |

### Compatibility still requiring confirmation

The Pocket requires two 18650 cells and supports onboard USB-C charging; its manufacturer package lists a USB-C cable but the extracted text does not establish the other connector end. Confirm USB-A compatibility with MP3408, or add a separately sourced cable rather than assuming one is owned. [RadioMaster specifications/package](https://radiomasterrc.com/products/pocket-radio-controller-m2).

EP2/transmitter compatibility requires the correct frequency band, compatible firmware major versions, regulatory configuration and binding setup. No radio-link or failsafe test has been performed. [Official ExpressLRS binding guidance](https://www.expresslrs.org/quick-start/binding/).

For charger screening, 16.8 V × 4 A = 67.2 W exceeds the stated 60 W AC rating; 16.8 V × 3 A = 50.4 W is within that power rating. These are elementary screening calculations, not a validated charge procedure: the battery manufacturer's permitted charge current, charger manual, connector alignment and actual setup still govern. Extensions are budgeted as candidates because adequate direct-connection reach has not been established. [SkyRC manufacturer information](https://www.skyrc.com/b6acneo).

## Required follow-through

Reconcile these candidates into a new accounting-input revision and recompute using the retained editable checker. Do not hide additions by silently reducing contingency or reallocating vehicle consumables to GSE. Do not infer flight mass from whole purchase quantities. Keep both display prices and evidenced tax-exclusive prices; unknown tax treatment stays explicit.

Still unpriced/unresolved: gimbal plain-shank pivots and retainers, washers/locking hardware, additional connectors and strain relief, electrical protection/filtering/inhibit components, propeller retention, adhesive/fairing/feet and stock coverage. GSE still needs charging/storage safety provisions, guarded propulsion fixtures, calibrated thrust/torque/RPM/electrical/temperature measurement, weighing/CG apparatus, fabrication and soldering equipment, computer/cables and restraints. Neither a complete cost total nor physical suitability is established by this note. No procurement, PDR acceptance or detailed-stage authorization is implied.
