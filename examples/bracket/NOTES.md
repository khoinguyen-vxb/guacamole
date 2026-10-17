# Benchmark run notes

Running notes taken while the benchmark runs. Times are AEDT.

## Run 20261017-093301

First run with the terminal notifications, the control bridge (ws://127.0.0.1:8767)
and the hold at each ready review. Run 20261017-092749 was stopped at 09:29, in the
systems engineer's second turn.

### enclosure

- 09:33 Started. The control bridge is listening on 8767.
- 09:33 Systems engineer recorded R1–R7 (R4 safety factor ≥ 2.5, R5 mass ≤ 0.35 kg,
  R6 width ≤ 50 mm, R7 depth ≥ 120 mm) and two open items: no paint system for the
  S275 bracket (R3), and no wall substrate or anchor pull-out capacity (R1).
- 09:35 System model revision 1 recorded. The systems engineer handed off to the Chief
  and is waiting to assess R4–R7 against the CAD verification evidence.
- 09:36 The Chief's first turn read the full system model. Its prompt only carries a
  1.6k-character summary under `state.system_model`, so the read is reasonable. Its
  prompt grew from 55.6k to 66.9k estimated tokens.
- 09:39 **The plan was rejected and the Chief has to re-plan.** The planning turn took
  2m43s, and both tasks named `systems_engineer` as a peer. `validate_plan`
  (`src/guacamole/decision.py:38`) only allows plan task IDs plus `"chief"`, so the
  plan failed with "names unknown dependencies or peers: ['systems_engineer']". The
  grant isn't needed anyway: `allow_peer` (`src/guacamole/activity.py:345`) already lets
  every worker message the root agents, which are the Chief and the systems engineer.
  Suggested fix: exempt the systems engineer's task ID the same way as `"chief"`. Also
  say in the Chief prompt that neither needs a peer grant.
- 09:41 The second plan was accepted after another 2m10s turn. It has one task,
  `bracket_cad` (tools `bracket_generate` and `bracket_check`, 40 steps, no peers), and
  one deliverable, `pdr-enclosure-bracket`. Dropping the separate verify task merged
  design and verification into one worker. The rejection cost about 2.7 min and one
  Chief turn of about 67k estimated input tokens.
- 09:41 The `bracket_cad` worker was spawned, and its first action is `bracket_generate`
  (S275, M6, 8 mm thick, 25 mm wide, 50 mm wall leg, 125 mm shelf leg). The Chief then
  wasted a turn: it tried to supersede the rejected plan's decision request (b125505)
  and got "Only a failed request can be superseded". The plan was rejected at
  validation, but its request was left `blocked` (`required: False`) rather than
  `failed`. It still shows in the Chief's `state.requests` and looks like something to
  clean up, yet `Activity.supersede` (`src/guacamole/activity.py:147`) refuses it.
  Suggested fix: mark a decision request whose plan fails validation as `failed`, so
  supersede works and the state reads correctly.
- 09:43 Watchdog at 10 min: 976k input tokens dispatched, $3.15, no interventions.
  Chief 6 steps / 450k tokens / $1.57, systems engineer 3 / 172k / $0.53, `bracket_cad`
  4 / 354k / $1.05 and still active. In the previous run the Chief had used 11 steps
  and $3.52 by the time the PDR was ready. This run's two rejected Chief turns were
  about a third of its spend so far.
- 09:44 `bracket_cad` completed in 3 min and 4 steps, and its first design passed. The
  cad-verification evidence `EV-enc_bracket_pdr-cad-verification` reads: 0.267 kg (R5
  ≤ 0.35), safety factor 3.91 (R4 ≥ 2.5), root stress 70.3 MPa, tip deflection 0.44 mm,
  481 N per wall screw, 23/23 checks passed. As expected, the evidence states that
  screw shear, prying and wall anchorage are not assessed, which matches the
  OI-WALL-ANCHOR open item. The `request.retry_requested` on the Chief's request was
  the normal wake-up from waiting, not a fault.
- 09:46 The systems engineer recorded the assessment `AS-enc_bracket_pdr-R4-R7` rev 1,
  which marks R4–R7 as satisfied. It said R1–R3 can't be assessed because they have no
  bounds, and it carried the evidence's limitation verbatim. Its hand-off note to the
  Chief was then rejected: "4 validation errors for Note". The payload added
  `assessment`, `open_items` and `system_model` ref fields, and passed `evidence` as a
  single ref instead of a list. `Note@1` is only `{text, evidence: [Ref]}`
  (`src/guacamole/contracts.py:593`). Agents never see that shape, because
  `Send.payload` is typed as free `JsonValue` (`contracts.py:755`) and the prompt
  doesn't include message schemas. Suggested fix: describe the `Note@1` and
  `AskHuman@1` payload shapes on `Send.payload` (one `Field(description=...)`), or put
  the message schemas in the prompt.
- 09:47 The systems engineer's retry (54 s later) delivered a valid note, which woke the
  Chief. The bad payload cost one systems engineer turn.
- 09:45 The Chief delivered `pdr-enclosure-bracket` rev 1 (seven artifacts plus the
  cad-verification evidence), 14 s before the systems engineer's assessment landed.
- 09:47 **The Chief delivered again and was rejected:** "already delivered with these
  artifacts and evidence (revision 1)". Its rationale assumed the deliverable record
  "is the approved spec, not a prior delivery". It can't tell from its state whether a
  delivery happened. The Chief prompt (`src/guacamole/agents/chief.py:116`) also says
  "deliver and request the review once [review_blockers] is empty", which invites a
  second delivery when the blockers clear after delivering. Suggested fix: when the
  current deliverables are already delivered, have `state.review_blockers` (or the
  deliverable entry) say so ("delivered; request the review"). Cost: one Chief turn.
- 09:47 **PDR ready:** review `c948a98e80f643b394e87c93c7d04f75` rev 2, plus a blocking
  human request. Watchdog at 15 min: 2.07M input tokens, $6.73 (Chief 11 steps / $2.78,
  systems engineer 5 / $1.88, `bracket_cad` 6 / $2.07). That's about the same as the
  previous run ($7.39, 2.18M) despite four wasted turns.
- 09:48 The runner is holding at the review as intended: the process is alive, no shelf
  brief has started, and no new events since 09:47:50.
- 09:53 Review accepted through `review.py` (control `script:review-827f05b488c2`). It
  is review rev 3, `status: accepted`. The Chief and systems engineer requests woke up
  to close out the run.
- 09:54 After the acceptance, the Chief tried again to supersede the blocked plan
  request b125505 and was rejected again. The 09:41 issue recurs whenever the Chief
  tidies up, so each run will keep paying for it until the request is marked `failed`.
- 09:54 **Enclosure complete.** Run status is `complete` and the PDR is accepted. Wrap-up
  after acceptance took 1 min and about $0.79 (Chief $0.58, systems engineer $0.21).
  Totals for the brief: about $7.52, 2.35M estimated input tokens, 21 min wall time
  including about 6 min waiting for the review, and 5 rejected actions. The
  post-review watchdog report restarts its elapsed time and per-agent counters from
  the resume ("after 1 min"), so add the pre-review report to get brief totals.

### shelf

- 09:54 Started straight after the enclosure finished, with the systems engineer and
  Chief spawned.
- 09:55 Systems engineer recorded R1–R8: 250 N at the shelf front edge, aluminium for
  a damp garage, safety factor ≥ 2, tip deflection ≤ 3 mm, ≤ 0.5 kg with fasteners,
  ≤ 60 mm wide, ≥ 180 mm deep, M6 screws into masonry. Open items: OI1, alloy and
  temper not given (assumes 6061-T6, the family's only aluminium); OI2, the failure
  criterion behind the safety factor (assumes yield); OI3, masonry type and anchor
  pull-out unknown, so screw tension can't be bounded. It flagged the R3 criterion
  ambiguity unprompted.
- 09:57 System model rev 1 recorded.
- 09:59 **Same plan rejection as the enclosure:** task `bracket_pdr_cad` named
  `systems_engineer` as a peer. That's 2 of 2 briefs, so it's systematic: the Chief
  treats the systems engineer as a peer it has to grant. The 09:39 fix applies. The
  second candidate was also rejected ("lacks a typed plan"); it was an alternative
  candidate with no plan attached.
- 10:01 The second plan was accepted after a 1m51s re-plan. Same shape as the
  enclosure's: one task, `bracket_pdr_cad` (generate and check, 40 steps, no peers),
  and one deliverable, `bracket_pdr_package`.
- 10:01 The worker spawned, then the Chief tried to supersede the blocked plan request
  and was rejected. It's the same sequence as the enclosure's, and the third time this
  run.
- 10:03 `bracket_pdr_cad` completed in about 2.3 min and 5 steps, with a first-pass
  design. Evidence `shelf_bracket_pdr_cad_verification` passed: 0.431 kg (R5 ≤ 0.5),
  safety factor 7.16 (R3 ≥ 2), tip deflection 1.06 mm (R4 ≤ 3), root stress 38.5 MPa,
  346 N per wall screw, 24/24 checks. A safety factor of 7.16 against a minimum of 2
  suggests the design is heavier than it needs to be.
- 10:04 **Paused on a provider failure.** The Chief's call failed with "Claude exited
  with status 1 (unrecognised error)". It happened at the same time as the claude.ai
  usage limit, so this was most likely the limit. The run stopped correctly
  (`paused`, and the benchmark broke out of the brief loop). Totals: 575 s, 1.04M
  input tokens, about $3.12 (Chief 6 steps / $1.06, systems engineer 3 / $0.51,
  worker 5 / $1.55). Two gaps:
  - **The error label missed the usage limit.** The `usage limit` entry in
    `_FAILURES` (`src/guacamole/context.py:81`) matches "usage limit", "quota" and
    "credit". The CLI's subscription message is likely worded "hit your limit" or
    "limit reached" instead. That wording is unverified, because the provider
    deliberately doesn't keep CLI output. Suggested fix: add `"limit reached"` and
    `"hit your limit"` to that entry.
  - **The benchmark can't resume.** `main()` prints "resume run eba93dec… in
    runs/20261017-093301/shelf", but `bracket.py` has no resume path:
    `run_brief` always calls `project.run` with a fresh request in a new timestamped
    directory. The README promises a resume too. Suggested fix: take an optional
    `runs/<stamp>` argument, resume the paused brief's saved run with
    `project.run(resume=…)`, and skip briefs that are already in `benchmark.json`.

### Fixes built after this run (2026-10-17)

- Peer grants: `validate_plan` accepts `systems_engineer` like `"chief"`, and the
  Chief prompt says neither needs a grant.
- Rejected decisions are `failed`, not `blocked`. The next completed decision by the
  same requester supersedes them, so nothing is left in `state.requests` to clean up.
- `Send.payload` describes `Note@1` exactly: `{text, evidence: [Ref]}`, no other
  fields.
- The Chief prompt says a deliverable record is a delivery, and to deliver again
  only when its artifacts or evidence change.
- The Claude provider classifies stderr as well as the result event. stderr was
  discarded before, which probably hid the limit message. "limit reached" and "hit
  your limit" count as a usage limit, and rate limits are matched first.
- Resume: `python -m examples.bracket.bracket runs/<timestamp>` keeps finished briefs
  and continues the paused one. `benchmark.json` is written after every brief.
