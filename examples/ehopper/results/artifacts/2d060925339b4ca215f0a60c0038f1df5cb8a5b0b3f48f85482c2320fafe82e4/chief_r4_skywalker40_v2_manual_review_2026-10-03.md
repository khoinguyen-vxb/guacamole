# Chief PDR research: Skywalker 40A V2

Access date for every linked source: 2026-10-03. Provider-side web research; manufacturer claims, not measured performance. This supplements the active propulsion and plant/control branches without modifying their files. No component selection, procurement authorization or review acceptance is recorded.

## Identity and commercial evidence

HOBBYWING North America's model page identifies Skywalker 40A V2 as part 80060022. Its series table independently associates that part with 3–4S input. Do not substitute original-generation Skywalker data or infer voltage compatibility from a supplier URL. [Exact-model page](https://www.hobbywingdirect.com/products/skywalker-esc-40a), heading/product identifier; [series table](https://www.hobbywingdirect.com/products/skywalker-esc), P/N 80060022 row.

The accessed store text displayed USD currency but did not expose a numeric price. This lookup therefore establishes no fresh price, stock quantity, tax treatment, shipping eligibility or AUD conversion. Existing dated price evidence must remain separately qualified; no BOM arithmetic is changed here.

## Published model envelope

The manufacturer-linked brochure's page 2 specification table lists 40 A continuous, 60 A peak, 3–4S LiPo, switching BEC 5 V/5 A, mass 36 g and dimensions 60 × 25 × 8 mm. Peak duration and rating test conditions are not specified there. Its filename mentions Mini, but the table explicitly includes the regular 40A V2. [Manufacturer-linked brochure, page 2](https://cdn.shopify.com/s/files/1/0109/9702/files/SKYWALKER_V2_mini_Leaflet_EN.pdf?v=1758654074).

## Manual findings and critical limitations

Manual HW-SMA202DUL02-A0, dated 2025-08-14, page 1:
- §04: factory throttle endpoints 1100–1940 µs; calibration required. White carries throttle; red/black carry BEC output.
- §06: Normal/Soft/Very Soft startup ramps approximately 200/500/800 ms from zero to full command.
- §07: signal absence exceeding 0.25 s cuts output; valid signals restore output.
- §06: selectable low-voltage thresholds approximately 2.8/3.0/3.4 V per cell; soft cutoff reduces output to 60% over 3 s; hard cutoff stops output.
- §07: thermal protection activates above 120 °C. Reduction wording is ambiguous, and troubleshooting reports 50% output rather than the 60% description elsewhere. Keep the discrepancy unresolved.
- §06: reverse mode stops before reversing; loss of its additional signal can also trigger shutdown.

Inference: startup ramp is not a calibrated motor time constant; protection is not a flight-safe landing strategy. Do not use 120 °C as an allowable design temperature. [Manufacturer manual, page 1, §§04/06/07](https://www.hobbywing.com/en/uploads/file/20250930/64b726be7a56c9f415385f77683cdc46.pdf).

## Follow-on evidence needed

Confirm purchased hardware/firmware identity, command repetition-rate limits, 3.3 V logic compatibility, BEC transient capability, cooling-dependent continuous limits and loaded acceleration/deceleration. Retain configurable response parameters and explicit uncertainty pending guarded tests. Do not parallel independent BEC positive outputs without a substantiated power-sharing design.

For subsequent verification planning, distinguish loss of radio link from loss of ESC pulses: a failed controller can continue transmitting a stale command. Include controller-stall and unintended-restart hazards in the arming/inhibit review. No failsafe acceptance follows from this research.

Method limitation: text and tables were reviewed through provider-side web retrieval. Figures, connector geometry and mounting drawings were not visually interpreted. No Guacamole SourceExcerpt, saved manufacturer PDF or physical-test evidence is claimed. Relay this supplement to both active workers after its ProducedFile is available.