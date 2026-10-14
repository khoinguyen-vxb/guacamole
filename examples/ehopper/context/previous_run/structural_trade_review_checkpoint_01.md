# PDR r12 — structural trade review checkpoint

Prepared: 2026-10-11.

**Status: preliminary evidence synthesis and proposed CAD handoff. No vehicle configuration, commercial component, procurement release, structural qualification or review baseline is selected by this report.**

## 1. Authority and evidence boundary

Retain validated plan `66c7448f443f44ac9a016a1b384593a2` r1, REQ-VEHICLE-CONFIGURATION r3, REQ-HARDWARE-BUDGET r5 and REQ-PROPULSION-PLACEMENT r1. Compare one through four spines, CFRP versus aluminium spines, and CFRP tripod versus quadpod legs. Keep exposed minimum structure, bottom propulsion and the common two-axis gimbal. PETG filament cost is exempt; its installed mass and structural effects are not. No fins, nosecone or enclosing cosmetic shell.

Reviewed evidence:

- `PDR-R12-STRUCTURAL-TRADE-CORE-RESULTS-01` r1, file `analysis/pdr_r12_chief/structural_trade_core_results_01.json`; file SHA-256 `c0b7337c5726d379fd13a7ff0a79f48f691796a5cd3b41ac740da0e9a5b8d2b2`.
- `PDR-R12-STRUCTURAL-TRADE-CORE-VERIFICATION-01` r1: executed arithmetic, integrity and analytical-fixture checks passed within their scope; overall engineering outcome remains inconclusive.
- `PDR-R12-STRUCTURAL-CLEARANCE-RESULTS-OFFSET20-01` r1, file `analysis/pdr_r12_chief/structural_clearance_screen_results_offset20_01.json`; file SHA-256 `8b9aa30187fa501a5d8f01b31b938759b02bac987bde453074b1d942ae20cb79`.
- Read-only support projection: request `e952f43bd4cd4804ac03dfac6f9b5781`; member/procurement projection: `be1389a4babf4d26930bf15fc166649b`; intermediate clearance detail: `802e85df368a4998bfae627ff32d1386`; twelve-case clearance comparison: `124671f0cf4b496ebdf1d17dd2a83c4b`.

These projections inspected stored calculations; their process success is not fresh independent verification. This report performs no new engineering computation. Source result files remain unchanged. Unreviewed detailed witnesses, material-response values and verification records are not implicitly endorsed.

## 2. Clearance findings that affect the next CAD pass

The table below reproduces stored reductions for a **15 deg resultant gimbal cone**, **10 mm rotor-slab half-thickness**, and neutral outer-to-inner joint displacement **[0, 0, -20] mm in CAD coordinates**. These are study hypotheses, not selected hardware travel or blade envelopes. Twelve cases were inspected from 48 stored cases; this is not a claim that these settings govern every other case.

Distances are mm, rounded to 0.001 mm for display. T/Q means tripod/quadpod. Moving-to-fixed reductions include the stored alternative spine envelopes, not one selected assembled vehicle. Different bound minima can have different governing pairs and poses.

| Layout / rotor diameter | Moving-to-fixed continuous lower bound, T / Q | Moving-to-fixed sampled upper bound, T / Q | Rotor-ground continuous lower bound, either arrangement, before additional consumption debit |
|---|---:|---:|---:|
| Compact / 279.4 mm | -5.505 / -3.262 | 2.444 / 4.687 | 23.397 |
| Compact / 330.2 mm | -11.753 / -11.753 | -5.000 / -5.000 | 15.976 |
| Intermediate / 279.4 mm | 10.345 / 10.345 | 18.086 / 18.086 | 41.351 |
| Intermediate / 330.2 mm | -6.679 / -4.360 | 2.399 / 4.718 | 33.982 |
| Wide / 279.4 mm | 10.044 / 10.177 | 18.086 / 18.086 | 39.001 |
| Wide / 330.2 mm | 10.646 / 10.646 | 18.086 / 18.086 | 31.721 |

Interpretation within the stated model:

- The compact 330.2 mm cases have stored sampled outer-envelope overlap/touch findings involving the upper rotor and legs. Do not advance them unchanged as clearance-compliant hypotheses.
- Compact 279.4 mm and intermediate 330.2 mm cases have sampled upper distance bounds below the 10 mm study discriminator. Subject to the bound implementation, that establishes a **modeled threshold shortfall**, not merely failure to prove adequate clearance. It does not establish a physical collision. Retain the original stored classification strings for traceability rather than silently rewriting them.
- A negative continuous lower bound alone does not establish collision. Likewise, positive sampled separation alone does not certify continuous separation.
- Intermediate 279.4 mm and both wide cases have stored continuous lower bounds above the study discriminator for the represented pairs. These are useful candidates for actual-solid CAD comparison, not complete geometry passes. Several lower bounds are close to 10 mm; omitted hardware and deformation cannot be assumed to fit within the remainder.
- Stored rotor-to-yoke invariant minima are approximately 23 mm. Rotor-slab axial gaps are 100 mm for compact/intermediate and 120 mm for wide layouts. These apply only to the modeled slabs and yoke envelopes, not qualified blade flexibility, mounting interfaces or coaxial performance.
- Ground clearance must retain the stated body-attitude and foot-contact construction. Additional compression/terrain/tolerance debits are exploratory. For example, intermediate/tripod/330.2 mm lower-rotor ground clearance decreases from the stored 33.982 mm lower bound to 18.982 mm with the separate 15 mm sensitivity debit; this does not cure its rotor-leg threshold shortfall.

All stored complete-geometry acceptance values remain null. No actual FCStd/STEP acceptance follows from this table.

## 3. Spine and purchasing comparison

The following is the inspected **intermediate-layout, 300 mm spine** subset, with roll-wrapped 8 mm OD / 6 mm ID CFRP legs of stored finished length 462.040722 mm. Costs are whole-stock tube subtotals only. They exclude required non-tube vehicle items and cannot establish the AUD 500 requirement.

| Spine arrangement / section | Tripod tube subtotal, assumed AUD | Quadpod tube subtotal, assumed AUD |
|---|---:|---:|
| S1: one CFRP 8/6 mm | 81.40 | 122.10 |
| S1: one CFRP 14/12 mm | 123.20 | 123.20 |
| S2: two CFRP 8/6 mm | 122.10 | 122.10 |
| S3: three CFRP 8/6 mm | 122.10 | 122.10 |
| S4: four CFRP 8/6 mm | 122.10 | 162.80 |
| S1, S2 or S3: aluminium 12/10 mm | 87.34 | 87.34 |
| S4: aluminium 12/10 mm | 93.28 | 93.28 |

For S4 CFRP 8/6 mm with tripod legs, the stored cutting schedule uses three 1000 mm tubes: two legs in one stock length; one leg and one spine in another; three spines in the third. It includes 5 mm end trim at each stock end and 3 mm kerf per piece. Its three-stock result matches the stored lower bound for the outward-rounded 1 micrometre packing model. Installed tube mass is 0.079621–0.102369 kg across the hypothetical 1400–1800 kg/m³ density cases. This is not complete structural or vehicle mass.

For S1 CFRP 14/12 mm with tripod legs, the stored tube-only mass range is 0.059828–0.076922 kg. S4 aluminium with the same tripod CFRP legs gives 0.154642–0.166835 kg. These comparisons exclude differences in brackets, plates, braces and fasteners; those can change the assembled ranking.

### Price provenance and limitations

All following catalogue observations were originally accessed **2026-10-11**; this report makes no new supplier retrieval:

- [Enhanced Composites roll-wrapped 8/6 mm tube](https://enhancedcomposites.com.au/product/carbon-fibre-roll-wrap-tube-8mm-x-6mm-x-1000mm/): displayed GST-inclusive range $30.80–40.70. The trade uses $40.70 per assumed 1000 mm stock length as a sensitivity allowance, not a confirmed variant quote.
- [Enhanced Composites roll-wrapped 14/12 mm tube](https://enhancedcomposites.com.au/product/carbon-fibre-roll-wrap-tube-14mm-x-12mm-x-1000mm/): displayed GST-inclusive range $35.20–41.80. The trade uses $41.80 with a 1000 mm stock-length assumption, again not a confirmed variant quote.
- [Bunnings Metal Mate item 1067750](https://www.bunnings.com.au/metal-mate-rcr-12-x-1mm-1m-aluminium-round-tube-1m_p1067750): displayed $5.94 per 12 mm OD, 1 mm wall, 1000 mm tube, identified as 6063-T5.

AUD denomination is inferred in these source observations, not explicitly confirmed; Bunnings tax treatment also remains unresolved. No tax deduction was applied to these provisional subtotals. Exact variant price, availability and applicable currency must be resolved before treating them as confirmed budget inputs. The core result's confirmed tax-exclusive subtotal remains null for these candidates. Costs for wide-layout cuts must be obtained from their own schedules, not copied from this intermediate table.

## 4. Structural and mounting interpretation

At the lowest hypothetical CFRP axial modulus, 50 GPa, stored member EI values are 6.872 N m² for a single 8/6 mm tube and 43.393 N m² for a single 14/12 mm tube. Four independent 8/6 mm members sum to 27.489 N m². The aluminium 12/10 mm single-member comparison is 36.363 N m² using assumed E = 69 GPa.

The much larger separated-rail, perfectly shear-coupled section proxies do **not** establish assembled stiffness. Joint slip, plate compliance and bracing remain unresolved; rail separation alone proves neither bending nor torsional adequacy.

Qualitative mounting comparisons, to test in CAD:

- **S1:** fewer longitudinal members and joints, but side-mounted equipment can introduce eccentricity and demands positive anti-rotation retention. A larger single tube deserves comparison with multiple small tubes; a single 8/6 mm tube is not automatically the adequate minimum.
- **S2:** convenient access between two rails, but strongly directional section geometry and unresolved torsional load paths.
- **S3:** distributed support in both lateral directions with fewer rails than S4; rectangular battery/board access and bracket geometry need explicit checking.
- **S4:** rectangular equipment packaging and multiple attachment locations may simplify mounting; extra joints and bracing must earn their mass and cost. The ideal coupled-section calculation is not sufficient justification by itself.

Supplier restrictions on pultruded tubes remain applicable. Favorable beam arithmetic must not override cautions concerning side loads, torsion, crushing or unsuitable applications. Roll-wrapped construction also does not supply missing laminate or joint allowables.

## 5. Tripod versus quadpod

For the intermediate 400 mm foot-radius hypothesis, stored origin-centred edge margins are 0.200 m for all three tripod contacts and 0.282843 m for all four quadpod contacts. Minimum polygon widths are 0.600 m and 0.565685 m respectively. These are different measures; neither should be substituted for the other.

Tripod support is geometrically determinate on a suitable surface but loses positive two-dimensional point-contact support with a foot removed. A centred square quadpod with one foot unloaded has its origin on the remaining triangle's boundary: the stored near-zero signed margins are roundoff-scale, not useful positive reserve. Four-foot force sharing requires compliance information.

A tripod is therefore a useful **CAD comparison lead** for reduced joint count and determinate nominal contact, not an approved landing-gear selection. A quadpod retains greater all-contact edge margin at equal radius but adds a leg and can increase whole-stock purchases. Keep both alternatives until first-contact loads, compliance, actual CG and interfaces are assessed.

The inspected landing-model metadata assigns the complete screening reaction to one leg in first-contact cases and does not assume that a vertical reaction is axial in a splayed leg. Detailed numerical stress/displacement extrema remain to be reviewed before structural down-selection. No strength, stopping-distance or dynamic-landing pass is claimed.

## 6. Proposed bounded CAD handoff — not a down-selection

Begin actual-solid comparison with the promising intermediate/279.4 mm and wide/330.2 mm clearance hypotheses. Highlight S1 14/12 mm CFRP and S4 8/6 mm CFRP for contrasting mounting strategies, each with tripod and quadpod alternatives. Retain S2, S3 and aluminium comparisons; they have not been eliminated by an engineering decision.

Before generating the candidate models, inspect the saved clearance source and its actual input/offset definitions so CAD reproduces the same joint origins and neutral hub coordinates. Do not silently treat noncoincident axes as a single pivot.

The saved FreeCAD generation script and candidate configuration should:

1. Create editable parameter-driven members, feet, attachment plate/ring and explicitly separated fixed, outer-gimbal and module-carried groups. Preserve the common gimbal convention and bottom propulsion.
2. Separate physical solids from non-mass swept envelopes. Label placeholder commercial envelopes and unresolved interfaces; do not invent motor mounting holes, collet retention, servo-ear dimensions or bearing fits. In particular, do not reuse the rejected 19 × 19 mm motor-pattern snippet.
3. Include the actual upper-disc bypass/yoke load path for separate motors rather than passing a structural member through a rotor envelope. Add brackets, pivots, linkages, retention and cable envelopes progressively, recording unknowns rather than treating them as zero mass or zero clearance consumption.
4. Save FCStd, STEP and arrangement drawings with every export declared. Reopen actual exports, enumerate individual solids and test parameter edit/recompute. Apply the documented FreeCAD correction: aggregate mass properties from solids, not unsupported generic Shape/Compound attributes.
5. Compute density-weighted component mass, CG and full inertia with explicit assumed-property provenance, moving-group ownership and supplier-mass overrides. Report incomplete installed mass honestly. Retain the proper CAD-to-body rotation diag(1,-1,-1), mm-to-m conversion and fixed-datum/instantaneous-CG distinction.
6. Check actual-solid clearances across the declared travel and landing-attitude domain. Keep sampled results, continuous bounds, fabrication tolerances and loaded deformation separate. Retain failed configurations and their witnesses.
7. Use a saved artifact-bound verification program through verify_command; process completion must not become geometry or physical acceptance.

Before a final preliminary structural choice, review landing-demand extrema; reconcile CAD mounting practicality, complete mass/CG, whole-purchase BOM, propulsion energy and actuator demand; and obtain missing supplier/interface evidence. Record the subsequent Chief choice through a separate decision action. Independent plant fixtures may continue, but no selected vehicle dimensions or calibrated properties are supplied by this checkpoint.

No PDR/CDR review acceptance, procurement approval, fabrication readiness or flight safety is claimed.
