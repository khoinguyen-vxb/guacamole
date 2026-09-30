# Available ESC comparison candidate

Access date: 2026-10-01. Preliminary evidence only; no selection or physical acceptance.

## Supplier listing

[Ultimate Hobbies HW80060442](https://ultimatehobbies.com.au/products/hobbywing-skywalker-v2-50a-3-4s-5a-bec), price/stock and Specifications sections: Hobbywing Skywalker 50A V2, displayed $51.29 each, listed in stock with warehouse/store-location caveat. AUD is inferred from the Australian storefront; currency and tax treatment require confirmation. No tax deduction applied.

Listed specifications: 3–4S LiPo; 50 A continuous, 70 A peak with duration unspecified; switching BEC 5 V/5 A; mass 36 g; dimensions 60 × 25 × 8 mm; input wire 14 AWG/100 mm; output wire 16 AWG/75 mm; female 3.5 mm motor bullets. Text inspected, not drawings. This is the 3–4S variant, not the 50A-6S variant. Checkout quantity and current quotation remain unconfirmed.

## Implications of actual preliminary analysis

Constraint diagnosis tool request 556fbb49d7704f6f9c8fe8b4a4560c4c reports nominal-loss, zero-added-mass vehicle mass 1.565100989025 kg. Reserve maximum motor current is 26.774368097105988 A, exceeding the hypothetical 30 A × 0.8 = 24 A ESC screening ceiling. A 50 A × 0.8 = 40 A candidate ceiling would remove this particular inequality at the old operating point, but is not a recomputed result or thermal qualification.

Replace both ESC masses and prices in a separate candidate configuration before rerunning. Two listed ESCs total 72 g and displayed $102.58, versus old allowances of 70 g and AUD 44. The inferred-AUD cost increase is 58.58; other prices remain provisional. Do not silently raise a limit while retaining the cheaper hypothetical BOM.

The 0.060 ohm battery case also violates loaded-voltage constraints in climb and reserve; a larger ESC does not fix this. Preserve resistance sensitivity, motor limits, usable-energy reserve and differential-yaw checks. Obtain manufacturer instructions, verify command response and failsafe behavior, and perform installed endurance testing before accepting the candidate. Do not parallel BEC outputs without explicit manufacturer authorization.
