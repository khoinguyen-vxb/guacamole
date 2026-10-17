# Document types: sections and ownership

Each template's sections map onto Guacamole's own records. Add a section only
if the document has the material for it; never leave an empty section in -
drop it instead and say why in Open Items if its absence is itself notable.

## Formal report (`assets/report.typ`)

A worker's own account of one piece of completed work (an analysis, a test,
a subsystem's current design), written by that worker.

1. **Executive summary** - the conclusion in one paragraph: what was done,
   what it shows, what (if anything) remains open.
2. **Scope** - the task's `objective`, and the `Requirement` refs it
   addresses.
3. **Method** - what was built/run/analyzed and with what tools (name tool
   grants used, not internal reasoning).
4. **Results** - the `Evidence` and `ArtifactRecord`s produced, with their
   outcomes. Numbers come from `measurements` in cited evidence, never
   restated from memory.
5. **Discussion** - what the results mean against the requirement's bound;
   call out any result that only partially satisfies it.
6. **Open items** - unresolved `OpenItem`s this work carries forward (cite
   their refs), with which review stage each blocks.
7. **Traceability** - the closing reference table (see
   `references/traceability.md`).

## Design-update deck (`assets/slides.typ`)

A worker's status update for a design review meeting - the same material as
a report, compressed to slides because it will be presented, not just filed.

- Title slide (title block, abbreviated: title, doc id, revision, date,
  author, stage).
- One "status at a glance" slide: what changed since the last update, in
  bullets, each tied to a decision or evidence ref.
- One slide per subsystem area or requirement group showing current
  values/results against bounds (use the same color convention as reports).
- One "open items" slide - every open item this subsystem owns, who/what it
  blocks.
- One "next" slide - what work remains and its dependencies.

Keep slide bullets to claims, not sentences; the Traceability table still
appears as a final slide (small type is fine - it is the audit trail, not
something read aloud).

## Decision / trade-study brief (`assets/decision-brief.typ`)

Presents a `DecisionRequest`'s candidates before (or as part of) a `decide`
action - written by whichever agent formed the candidates, almost always the
Chief, before deciding, or immediately after deciding to record why.

1. **Question** - the `DecisionRequest.question` verbatim.
2. **Candidates** - one subsection per `Candidate`: its description, its
   `metrics`, and the `Constraint`s it must meet, in a comparison table
   (criteria as rows, candidates as columns).
3. **Evidence** - the `Ref`s each candidate's metrics rest on.
4. **Recommendation** - once decided: the `selected` candidate and the
   `DecisionResult.explanation` verbatim; before deciding, leave this
   section out entirely (a brief presented for a human's input has no
   recommendation yet - that is the human's or the Chief's call, not
   something to presuppose).
5. **Traceability**.

## Review package (`assets/review-package.typ`) - Systems Engineer

Assembles a `ReviewManifest` for human disposition - PDR or CDR. Only the
Systems Engineer composes this: it is the one agent that sees every worker's
delivered artifacts and evidence against the current, authoritative SysML
model.

1. **Baseline** - the plan `decide`d for this stage, the SysML model
   revision it was validated against, and the `baseline` refs.
2. **Deliverables** - one row per `DeliverableSpec`: its id, the
   `Deliverable` that satisfies it (artifacts + evidence refs), and whether
   its acceptance criteria are met.
3. **Compliance** - every bounded requirement's `Satisfaction` status from
   `state.system_model`, and every standard the project's catalogue makes
   mandatory with its applicability and (if selected) its assessment.
4. **Open items** - every open item blocking this stage, by whom it's
   assigned to resolve.
5. **Disposition** - left blank (a `human` field and `disposition` text) for
   the human reviewer; the agent never fills this in.
6. **Traceability**.

## Traceability / compliance / regulatory record (`assets/traceability-record.typ`) - Systems Engineer

A standing record of which requirements and standards are verified by what,
for audit or external submission - not tied to one review's disposition, and
not opinionated like a report (no recommendation, no discussion - a matrix of
fact).

1. **Scope** - which requirements/standards this record covers, and the
   `SystemModel` revision it reflects.
2. **Compliance matrix** - one row per requirement: its wording, its bound,
   the evidence that satisfies it, and its `Satisfaction` status.
3. **Standards register** - one row per selected `Standard`: id, edition,
   each `Clause` requirement derived from it, and its satisfaction.
4. **Amendment history** - every `AmendmentRecord` affecting a requirement or
   standard in scope, adopted or withdrawn, with its rationale.
5. **Traceability** (the full reference table; this document's whole body is
   effectively one, so this section is often the longest).
