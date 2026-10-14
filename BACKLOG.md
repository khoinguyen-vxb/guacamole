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

## Next

Each item lists what "done" means.

1. **GUA-012 Name CLI provider failures.** Codex and Claude CLI exits all read "exited with status N", because stderr is rightly never stored. Map its tail to a fixed label (usage limit, auth, context overflow, other). *Done when* a Codex usage-limit exit says so in the blocked agent's observation.
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
- **GUA-015** capability registry, **GUA-016** image input, **GUA-019** fault injection beyond the existing restart, timeout and stale-input tests, **GUA-020** CLI: wait for a concrete need.
