---
name: engineering-documentation
description: Produce polished, traceable engineering documents - formal reports, subsystem design-update decks, decision/trade-study briefs, PDR/CDR review packages, and traceability or regulatory record-keeping submissions - as Typst source compiled to PDF. Use whenever an agent must present its own work, an engineering decision, verification evidence, or a review package to a human in a document someone outside the run can read, file, or sign.
compatibility: Requires a `typst` CLI on PATH, run through Guacamole's execute tool. Templates use only typst's built-in paper presets and fonts; no network access and no external Typst packages.
metadata:
  domain: systems-engineering
  runtime: guacamole
---

# Engineering documentation

Guacamole's traceability is only as good as its documents. Every requirement,
decision, piece of evidence and review already exists as a record with an exact
`Ref` (kind, id, revision) - this skill is about turning those records into a
document a human can actually read, file, or sign, without losing that
traceability on the way.

## Who writes what

Documents are work products, not a separate role. Any agent that already has
the material writes its own document; only cross-cutting documents go through
the systems engineer.

| Document | Prepared by | When |
| --- | --- | --- |
| Formal report (analysis, test, subsystem report) | The worker that produced the evidence/artifacts | Reporting its own completed work |
| Subsystem design-update deck | The worker owning that subsystem's task | Presenting current state/decisions at a design review |
| Decision / trade-study brief | The agent that formed the candidates (usually the Chief) | Before or alongside a `decide` action, to lay out alternatives for review |
| Review package (PDR/CDR) | The Systems Engineer, from every worker's delivered artifacts and evidence | Assembling `state.review_blockers` material once a plan's deliverables are complete |
| Traceability / compliance / regulatory record | The Systems Engineer | Whenever a standard, clause or requirement's verification status needs to be shown to a human or submitted externally |

A worker never assembles a cross-subsystem review package or a compliance
submission itself: it hands the Systems Engineer its artifact and evidence
`Ref`s (by finishing its task, or by `send`), and the Systems Engineer composes
the document from the current model and assessments.

## The one rule that matters: every claim cites a Ref

A document produced here is read by a human who was not in the run. Nothing in
it may be asserted from memory or "what the agent saw" - only from the records
it cites.

- Every number, test result, requirement wording, or decision outcome in the
  body is traceable to an exact `Ref` (`kind`, `id`, `revision`) already in
  `state.records`, `state.system_model`, or a message/result you received.
- Never invent a value, approval, or test pass. If something is not yet
  measured, verified or decided, say so in the Open Items section - do not
  round it off or omit it.
- Assumptions and unknowns carried from `OpenItem` records are stated, not
  silently resolved.
- The document ends with a **Traceability** table: one row per `Ref` cited in
  the body, in the order first cited. See
  [references/traceability.md](references/traceability.md) for exactly how to
  format citations and that table, including how to cite requirements,
  evidence, decisions, the SysML model, and standards/clauses.

## Document layout and style

Read [references/typst-style.md](references/typst-style.md) before writing a
new document - it covers page setup, the title block, headings, tables,
figures and footers so every document in a project looks like it came from the
same program, not from whichever agent happened to write it.

Start from the template closest to what you're writing rather than from a
blank file:

- [assets/report.typ](assets/report.typ) - formal reports (analysis, test, subsystem reports)
- [assets/slides.typ](assets/slides.typ) - design-update decks
- [assets/decision-brief.typ](assets/decision-brief.typ) - decision/trade-study briefs
- [assets/review-package.typ](assets/review-package.typ) - PDR/CDR review packages (Systems Engineer)
- [assets/traceability-record.typ](assets/traceability-record.typ) - compliance/traceability/regulatory records (Systems Engineer)

Read a template, copy it to your working file, and replace the placeholder
variables and example sections - do not change the page/header/footer
machinery at the top unless a document genuinely needs a different layout.
[references/document-types.md](references/document-types.md) explains what
each template's sections mean and when to add or drop one.

## Writing the file and compiling it

1. Pick a doc ID: `<deliverable-or-decision-or-review-id>-<kind>`, e.g.
   `prop-feed-analysis-report`, `pdr-review-package`, `amend-14-decision-brief`.
2. `write_text` the Typst source to
   `docs/<doc-id>/main.typ` (sandbox-relative - `write_text` creates the
   directory). Keep one document per directory; add any figures it embeds
   alongside it in the same directory and reference them by that relative
   path.
3. Compile with the `execute` tool, no shell, one argv:
   ```json
   {
     "command": ["typst", "compile", "main.typ", "main.pdf"],
     "workdir": "docs/<doc-id>",
     "outputs": ["docs/<doc-id>/main.pdf"]
   }
   ```
4. Read `stdout`/`stderr` from the result before trusting the PDF exists -
   Typst reports every layout and syntax error there, and a non-zero
   `returncode` or an entry in `missing_outputs` means it did not compile.
   Fix the `.typ` source and recompile; never hand-edit or fabricate a PDF.
5. `write_text` the `.typ` source is itself a declared tool output, so it is
   snapshotted; the compiled PDF is the `ProducedFile` from `execute`'s
   `files`.

## Publishing

Publish both the Typst source (the editable artifact) and the compiled PDF
through `publish`, citing the requirements and inputs the document is actually
about:

- `artifact_kind`: `"report"`, `"slides"`, `"decision_brief"`,
  `"review_package"`, or `"traceability_record"` - pick the one matching the
  template used, so later agents and humans can filter by kind.
- `requirements`: the `Requirement` refs the document addresses or reports
  against.
- `inputs`: every `Ref` (evidence, decisions, artifacts, the system model
  revision) the document cites in its Traceability table.

A `Deliverable` for the document's `DeliverableSpec` cites the same artifact
and evidence refs so a review package can find it.

## Before publishing, check

- [ ] Every figure, table value and claim in the body has a citation, and
      every citation appears in the closing Traceability table.
- [ ] Every open item, assumption or unknown the work actually carries is
      listed, not smoothed over.
- [ ] The title block (see
      [references/typst-style.md](references/typst-style.md)) has the real
      doc id, revision, date, author (your `task_id`), and status
      `"In review"` - never `"Released"`; only a human-accepted review
      releases a document.
- [ ] `typst compile` returned 0 and the PDF exists among `files`, not
      `missing_outputs`.
