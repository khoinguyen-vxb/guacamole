# Backlog

Checked against the code at `86d1f45` and the live ehopper workspace on 2026-10-14.
IDs follow the external GUA-001..021 review; items it got wrong are rescoped here.

## Done

| ID | Change |
|---|---|
| GUA-001 | Run outputs that bloat the repository are ignored and untracked: FreeCAD/STEP files, `logs/`, `artifacts/`, `stdout`/`stderr`/FreeCAD logs and `timeline.jsonl`. Summaries, manifests and generator scripts stay tracked. |
| GUA-002 | `.github/workflows/ci.yml` runs the README checks on ubuntu-24.04: unittest, ruff, ruff format, ty. The test broken since `4e15e5e` is fixed. SysML tests skip where sysml has no standard library (linux-aarch64). |
| GUA-004 | Rescoped: kind and same-run checks on `supersede()` add nothing, since only tool requests can fail and the parent pins the run. Fixed instead: a retry refused by its plan no longer strands the request in `queued`. A human correction releases failed or interrupted work that no agent is left to settle, so the run can complete. |
| GUA-005 | Partial: review readiness ignores evidence that covers none of the deliverable's artifacts. |
| GUA-007 | Partial: `Budget.max_run_input_tokens` caps a run's estimated prompt tokens. Failed calls and earlier sessions of a resumed run count toward it. |
| GUA-009 | (c) A turn whose plan changed while its call was out is dropped, not acted on. A plan decision no longer reverts a budget raise or compaction made earlier in the same turn. (b) was already done: each dispatch records provider, model, tier and effort. |
| GUA-010 | Partial: `max_agents` counts running workers; completed and superseded ones free their slot. |
| GUA-021 | `pytest` moved to the dev group and pytest scoped to `tests/`. The garbled launcher text in `ehopper.py` and the ehopper install line are fixed. Supported platforms are documented. |
| GUA-012 | A failed Codex or Claude CLI is reported by a fixed label (usage limit, rate limit, authentication, context overflow, unrecognised error) read from its JSON error events; the text itself is still never stored. |
| Delivery | From the ehopper run's history (no `deliver` or `review` in 2,003 turns; the Chief 61% of turns): `passed` means every performed check passed, with unperformed checks listed for the reviewer; the Chief sees `review_blockers`; plans give the Chief reader tools only, so execution runs in parallel workers; replies carry their question (one Chief spent 247 turns searching for it); empty searches say what search covers. |
| GUA-016 | Image input: reading a PNG/JPEG/WebP record sends its pixels through Codex `--image`, Claude CLI stream-json image blocks and LiteLLM data URLs, with hash checks, budgeting and stated omissions. ehopper ingests its reference photos and keeps FreeCAD screenshots as files; MCP results carry produced images. The live check (`GUACAMOLE_LIVE_VISION`) is opt-in. |

## Milestone B: brief to review package

Done, on one product family ([examples/bracket](examples/bracket/README.md)):

- **CAD tools, not core modules.** A parametric FreeCAD bracket model produces native CAD, STEP, a third-angle drawing and a BOM derived from the assembly tree. Deterministic checks cover recompute, solid validity, recompute after a parameter change, STEP correspondence, interference, BOM against model, and every measurable requirement constraint. Unmeasurable constraints stay "not performed".
- **Measured evidence.** `VerificationResult.measurements` carries quantities; one keyed by a requirement id traces into the report.
- **Package document.** `review.md` is generated from records only: requirements traceability with measured values, decisions with candidate metrics, deliverables with figures and CSV tables inline, every check and measurement, and open items including unperformed checks.
- **Benchmark harness.** One fresh project per brief and a scripted reply to blocking questions. A run passes when it reaches a ready PDR review within `max_run_input_tokens`.

Next:

1. **Run the benchmark live** on the three briefs (up to 6M estimated tokens each). Fix whatever stops a run before review. *Done when* all three reach a ready review on two consecutive runs.
2. **Let agents see tool failures.** A tool's exception text reaches agents only if it is registered with `show_errors=True`. The bracket tools are not, so a FreeCAD failure inside `bracket_generate` is still opaque to them. Layout problems already come back as data. *Done when* an agent can correct a failed generation without help.
3. **A second product family**, such as a sheet-metal enclosure, before generalising the CAD representation into a shared assembly contract.
4. **SysML in the loop.** Allow a SysML `library_dir` override so the model loads on linux-aarch64, then trace requirement constraints through the model.
5. **Drawing checks and PDF.** Drawing dimensions are generated from the model but not checked. Export `review.md` to PDF if reviewers need it.

## Next

Each item lists what "done" means.

1. **Engineering review interface.** The smallest page another engineer can use without reading logs: submit a brief, confirm assumptions, inspect the package and its change summary, request a change, accept or reject. It drives the existing WebSocket human commands. *Done when* an engineer other than the author completes a review and one change cycle without help.
2. **GUA-008 Context waste.**
   - (a) Context clearing edits only a per-call copy (`middleware.py`), so about 87 of the Chief's sources are cleared again every turn, and the prompt never says they were dropped.
   - (b) `state.records` gives the Chief every run's tool results, about 13% of its prompt.
   - (c) `search()` ranks by raw substring count.
   - (d) A decision's evidence is shown again as its dependencies.
   - *Done when* the Chief's prompt shrinks measurably on the next ehopper run, with no rise in rejected reads.
3. **GUA-005 Shared CAD checks.**
   - One module in `examples/ehopper/tooling` covering reopen, `isValid`, solid count, volume/mass and STEP solid correspondence. 34 of the agents' result scripts are one-off checks, and 6 of them re-implement reopen + `isValid` + volume.
   - `publish` should refuse a run whose result reports failure. ehopper's tools return failures as data, so such runs complete.
   - *Done when* agents call the shared check instead of writing new inspect or diagnose scripts.
4. **GUA-003 Cancellation that reaches the tool (rescoped).** ehopper's `execute` and FreeCAD calls are already killable subprocesses. The gaps:
   - `Job.cancel()` only records a status.
   - A turn timeout stops the wait, not the work.
   - A tool's own `TimeoutError` is mistaken for a turn timeout (`Job.collect`).
   - *Done when* cancelling a running `execute` job kills its process group.
5. **GUA-018** `read_text` takes several paths: 17% of ehopper turns are a read straight after a read.
6. **GUA-017** `execute` results also record the argv and environment the tool already builds.
7. **GUA-010** Ask the Chief for task ids that stay stable across replans, so plan adoption keeps running workers.
8. **GUA-011** Route on a qualification only after at least 3 trials, and count crashed trials as failures. One pass in one trial currently qualifies.
9. **GUA-006** Engineering decisions supply a metric for each cited requirement's constraint (`_eligible`). Do this once a demo uses constraints or SysML; neither does today.
10. **GUA-001 history.** Old outputs still take about 260 MB of history; the largest blob is 31 MB. Purging them rewrites history, so coordinate before running `git filter-repo`. The `tooling/` gitlinks have no `.gitmodules`, so a clone gets empty folders: add one or drop them.

## Not now

- **GUA-013 migrations:** write the first migration when a column changes. Back up with `sqlite3 project.sqlite3 ".backup ..."` while no run is going.
- **GUA-014 storage:** the database is about 1% of turn time. The one cheap win: `Activity.included()` writes an inbox revision every time a packet includes a message, about 315 MB in the current run.
- **GUA-009a** clamping input budgets to a tier's capacity: no example uses tiers.
- **Repair budget** capping retries of a failing tool: in ehopper's 815 tool calls the longest failure streak was 2. Add one if runs show agents grinding on a tool.
- **GUA-015** capability registry, **GUA-019** fault injection beyond the existing restart, timeout and stale-input tests, **GUA-020** CLI: wait for a concrete need.
