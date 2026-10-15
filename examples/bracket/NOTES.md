# Benchmark run notes

Running notes taken while the benchmark runs. Times are AEDT.

## Direction: agent roles

The user's view (2026-10-15):

- **The project starts with the SE.** The SE owns the system requirements and formalises them in SysML.
- **The Chief is the main actor.** It structures sub-agents to carry out the vision.
- **The SE runs on demand, not all the time.** It is called only to:
  1. review requirement changes proposed by the human or the Chief;
  2. update the project SysML model when the Chief asks;
  3. assess the design outcomes the Chief presents and verify that they comply with the system requirements.

How the runtime behaves today, as seen in run `20261015-005600`:

- The Chief and the SE are spawned together and both run from the first turn.
- The Chief records the requirements (R1 to R6). The SE only models what the Chief has recorded.
- The SE has the same tools as the Chief (`bracket_generate`, `bracket_check`).
- Compliance is judged by `bracket_check` and `assess()`, not by the SE.

## Run 20261015-005600 (enclosure brief, Claude Opus 5.5 at max effort, 17M cap)

- **00:56** Chief and SE start in parallel. The SE's first turn sees no requirements.
- **00:57 to 01:03** The Chief records R1 to R5, one per turn, at 30 s to 2 min and $0.08 to $0.37 per turn: 150 N tip load, S275 steel (paint system unknown), safety factor at least 2.5, mass at most 0.35 kg, width at most 50 mm.
- **01:03:37** SE turn 1 returns after 7.5 min (52k output tokens, $1.19). The model is **rejected** for 5 `unmodeled_requirement` errors: R1 to R5 were recorded while it was thinking. Validation uses the requirements recorded at submit time, not those in the SE's prompt.
- **01:03:39** SE turn 2 is sent with the rejection. In the same second the Chief records R6 (depth at least 120 mm), which turn 2's prompt does not contain, so turn 2 will probably be rejected for R6.
- **01:06, 01:11** While waiting for the model, the Chief records open items `OI-wall-fixing` and `OI-physical-test`. Its 01:06 turn took 4.5 min.
- **01:12:31** SE turn 2 returns after 9 min (60k output tokens, $1.25). It is **rejected** again, with two errors:
  - `unmodeled_requirement` R6, as predicted.
  - `constraint_mismatch` R3: the model has `2.5 <= safety_factor` (dimensionless), while the recorded constraint has unit `"1"`.
- **01:12:32** SE turn 3 is sent.
- **01:13 to 01:19** The Chief, still blocked from deciding, does the following:
  - reads its open items;
  - at 01:16, messages the SE with the full requirement set, the metric names and units (`safety_factor >= 2.5 [1]`) and the design parameter ranges;
  - at 01:19, sends the human a non-blocking `ask_human` about the wall type, to close `OI-wall-fixing` before CDR.
- **01:19:32** SE turn 3 returns after 7 min (48k output tokens, $1.02) and commits **model revision 1, valid**. It covers R1 to R6 with 4 bounds and no satisfy claims yet. R3 is written as `>= 2.5 [1]`. The SE worked this out from the turn 2 rejection; it was mid-turn when the Chief's 01:16 message arrived. The model was rejected twice before this, so a valid model took 23 min and $3.46.
- **01:19:32** SE turn 4 is sent with the Chief's 01:16 message. The model already covers that message, so this turn is probably redundant. The Chief now holds a valid model and can plan.
- **01:20:36** The Chief's turn, sent at 01:19:05 just before the commit, still saw the model as "missing" and chose `wait` ($0.26).
- **01:21:52** SE turn 4 replies to the Chief with the bounds, metric names and `load_n = 150`, then acknowledges the Chief's message ($0.40). The reply wakes the Chief, whose next turn is sent at once. As of 01:28 it has run 6.5 min, probably drafting the PDR work plan.
- **01:23 and 01:24** SE turns 5 and 6 read the two open items, conclude that nothing changes, and wait ($0.59). These are the on-demand role's "SE runs all the time" cost: three SE turns ($1) after the model was valid, with no model change.
- **01:28** 32 min into the run: about $8.07 and 955k estimated input tokens of the 17M cap. Still no plan, CAD or check. The run's `max_seconds` is 5400 (90 min), and at this pace the wall-clock limit may end the run before review.
- **01:31:25** The Chief records the **PDR work plan** after a 9.5 min turn (50k output tokens, $1.09).
  - It selected `pdr-plan-single-cad-worker`: one worker task, `bracket_cad_pdr`, holding `bracket_generate` and `bracket_check`, and no chief tools.
  - It rejected `pdr-plan-split-design-verify`, which split design and verification into two workers.
  - Next it plans to run a small design search, decide the design from the `bracket_check` metrics, notify the SE and deliver.
- **01:31:25** The decision **auto-wakes the SE** ("Decision recorded"), though nothing in the plan changes the model. This is another on-demand case. The SE spends two turns (01:31 and 01:33) reading and then waits again.
- **01:34:23** The Chief **spawns worker `bracket_cad_pdr`**. This is the first worker, 38 min into the run.
- **01:37:37** The worker's first `bracket_generate` (after a 3 min turn) asks for width 30, t 6.5, M4 ×2 per leg, wall leg 70, shelf leg 125. The tool returns the layout problem "2 M4 holes need width >= 33 mm" as data, with no files. The worker's next turn is sent.
- **01:39:37** The worker's second `bracket_generate` (width 34, t 6, M4 ×2, wall leg 70, shelf leg 125) produces native CAD, STEP, drawing and BOM. This is the **first CAD**, 43.5 min into the run.
- **01:40:39** The worker publishes all four files as artifacts `encl_w34_t6_m4x2`.
- **01:41:21** `bracket_check` at 150 N on `encl_w34_t6_m4x2`: **11 of 11 checks passed**, none unperformed. Mass 0.309 kg (R4 ≤ 0.35), safety factor 2.99 (R3 ≥ 2.5), width 34 mm (R5 ≤ 50), depth 125 mm (R6 ≥ 120). Plate root stress 91.9 MPa, tip deflection 0.76 mm, 154 N per wall screw. The first valid design met every requirement.
- **01:41:23** The worker's next turn, which would have recorded the evidence, fails: "Claude exited with status 1 (unrecognised error)". Most likely the account's Claude usage limit, which also paused the session watching this run, but the CLI's error was not a recognised label. With the worker blocked, the Chief waiting on it and the SE idle, no agent is active, so the run ends **incomplete** after 45 min. Spend was **$13.63**, with 1.99M estimated input tokens.
- **01:41** The `shelf` and `sign` briefs then fail within 3 s each on the same provider error. **Benchmark result: 0 of 3 passed.** None of the three failures reflect the design work.
- **01:37:45** The Chief sends the human a second **non-blocking** question, listing the **19 unknowns** it recorded in R1 to R6 (load case, shock, stiffness, paint, datums, and so on) with proposed defaults. Its reason: `state.review_blockers` lists every requirement unknown as "unresolved input", and these block the PDR review.

Observations:

- **Requirement unknowns can block the benchmark outright.**
  - `reviews.checks()` (`reviews.py:62`) turns every entry in `Requirement.unknowns` into a review issue. The review can only become ready once the requirements are re-recorded without unknowns.
  - Re-recording them stales the SysML model, so the SE must commit again.
  - The harness (`bracket.py:490`) only answers **blocking** questions, and only once the run stops at `awaiting_human`. The Chief asked non-blocking.
  - So unless the Chief later asks a blocking question and then re-records R1 to R6, this run ends `incomplete`.
  - The Chief was diligent in recording unknowns, and the runtime turns that diligence into a PDR blocker. Many of the unknowns are CDR matters (paint, wall fixing), but there is no way to defer an unknown to a later stage, so they all block PDR.

Observations:

- **Requirement race.** A slow SE turn chases a moving requirement set. Each lost race costs about 7 min and $1.20. Having the SE own the requirements (above) removes the race. A smaller fix: reject only for requirements the SE's prompt contained, and flag later ones for its next turn.
- **Two spellings of "dimensionless".** The contracts (`ModelBound.unit`, the adapter's `Value`) say `""` is dimensionless. `bracket.py` tells agents that `safety_factor` has unit `"1"`, so the Chief recorded R3 that way. The validator compares unit strings literally, so a unitless SysML bound never matches. `2.5 [1]` works: the SE found it on its third try, and model revision 1 uses it. No test covers it, though, and the rejection does not suggest it. The evidence check against the model (`validator.py:130`) compares units the same way, but now that the bound says `"1"` it matches what `bracket_check` reports. Fix: treat `"1"` as `""` in one place.
- **Time to first CAD was 43.5 min, and 23 min of that went to the model.** Design was quick once the plan existed: two `bracket_generate` calls and one `bracket_check`, all passing, in 7 min. The overhead was the SE race, the Chief's 9.5 min plan turn and idle SE wakes.
- **A provider failure ends the run instead of pausing it.** A blocked worker, with no other active agent, ends the run as `incomplete`. A usage limit then also burns the remaining briefs in seconds.
- **One action per turn at max effort is slow for bookkeeping.** Six requirements took the Chief about 8 min and $1.60.

## Changes after run 20261015-005600 (2026-10-15, uncommitted)

These implement the agent-roles direction above.

- **The SE owns requirements.** `Record(Requirement)` is SE-only. The Chief is told "Only the systems engineer records requirements; send it the change and its source". The Chief and the SE can both record open items.
- **The SE starts the project.** The Chief starts `waiting`, and the existing "SysML model is usable" wake starts it once the SE's first model is valid.
- **The SE runs on demand.** The wakes on decisions, records, evidence and mid-turn record changes are gone, along with `sysml.changed_since`. The SE now wakes only for messages, human input and watchdog notes.
- **Compliance is a hard gate.** `sysml.review_issues()` lists every bounded requirement the current model does not show `satisfied`. This feeds review readiness and, newly, the Chief's `state.review_blockers`.
- **Dimensionless units.** `Quantity.unit` and `Constraint.unit` store `"1"` as `""`, and the adapter reads `[1]` as `""`. `2.5 [1]` and a bare `2.5` now both match a recorded `"1"`.
- **Prompts and docs.** The Chief, SE and shared prompts, the README and the bracket INSTRUCTIONS now describe the new roles. The SE prompt was kept within the default 32k context.
- **Tests.**
  - The fixture SE records each fixture's `requirements()`, commits, and replies to agents' messages.
  - The Chief fixtures no longer record requirements.
  - New tests cover `[1]` and bare dimensionless bounds, and the compliance gate at registry level.
  - The FreeCAD bracket test now checks blocked → SE assessment → ready → accepted.
  - 99 tests pass, with 2 skipped as before.

Still open from this run, not yet agreed:

- **Requirement unknowns block PDR** with no way to defer them to a later stage.
- **The harness answers only blocking questions.**
- **A provider failure ends the run instead of pausing it.**
