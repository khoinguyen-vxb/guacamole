# Citing Guacamole records in a document

A document's only authority is the records it cites. This is the one format
for citing them, used in every template so a reader (human or agent) can find
the same short form in the body and in the closing Traceability table.

## Short-form citation

In body text, tables and figure captions, cite a record as:

```
kind:id#revision
```

e.g. `requirement:TH-12#1`, `evidence:7f3a9c…#3`, `decision:9b1e02…#1`,
`system_model:…#5`. Use the `Ref`'s actual `kind`, `id` and `revision` fields
- never shorten or guess an id. When a `Ref`'s id is long, it is fine to
truncate it in running text (`evidence:7f3a9c…#3`) as long as the closing
Traceability table carries the exact, untruncated value.

Typst helper (already in every template):

```typ
#let cite(ref) = raw(ref.kind + ":" + ref.id + "#" + str(ref.revision))
```

Call `cite(the-ref)` rather than typing the string by hand, so a copy-paste
error in a doc id can't silently miscite a record.

## What to cite, and how to phrase it

- **Requirement** - cite it wherever its wording, bound, or id is stated.
  Quote `wording` and `source_quote` verbatim; never paraphrase a
  requirement's text.
- **Evidence** - cite it wherever a measured value, test outcome or
  verification result appears. State the `outcome` using the exact word
  (`passed`/`failed`/`unperformed`/`inconclusive`) and copy `explanation`
  word for word, as the project's own evidence rules require (see
  `agents/chief.py`'s `COMMON` prompt) - a report may not reword what
  evidence says.
- **DecisionRecord** - cite the decision id when stating what was chosen and
  why; quote `DecisionResult.explanation` rather than summarizing it.
- **ArtifactRecord / Deliverable** - cite the artifact when showing a
  produced file, drawing, model or dataset; a figure reproducing it in the
  document is illustrative, the citation is what's authoritative.
- **SystemModel** - cite the exact revision (`system_model:…#n`) a
  compliance or satisfaction claim rests on; a claim against a stale
  revision is wrong even if the words haven't changed.
- **Standard / Clause / Fact** - cite the requirement record that selected
  the standard or stated the fact (standards and facts are not independently
  `Ref`-able; they live inside a `Requirement`), and give the standard's
  `id` and `edition` in text, e.g. "AS 1210:2010 clause 3.3.1
  (requirement:STD-4#2)".
- **AmendmentRecord** - cite it when describing a model change; state
  whether it was adopted (cited by a decision's evidence) or is still
  proposed/withdrawn.
- **OpenItem** - cite it in an Open Items section with its `kind` and which
  review stages it blocks; do not cite open items elsewhere as if they were
  settled.
- **ReviewManifest** - cite it in a review package's own header (the
  manifest a package renders) and in any later document that references a
  past review's disposition.

Never cite a `tool_result`, `job_inputs` or `job_file` directly in a document
meant for a human - those are the run's internal working records. If a tool
run needs to be shown, cite the `ArtifactRecord` or `Evidence` it produced
instead; those are the records meant to outlive the run.

## The Traceability table

Every template ends with a table, one row per citation in the order it first
appears in the body, with these columns:

| # | Citation | Kind | What it supports |
| - | -------- | ---- | ----------------- |
| 1 | `requirement:TH-12#1` | requirement | Thermal bound in §3 |
| 2 | `evidence:7f3a9c…#3` | evidence | Measured result in §4, Table 2 |

"What it supports" is a short phrase pointing back at the section/table/figure
that used it - enough for a reviewer to jump straight to where a record was
relied on. Add one row every time you call `cite(..)` for a `Ref` not already
in the table; keep the table in first-cited order so it doubles as a map of
"what did this document rely on, in the order it came up".
