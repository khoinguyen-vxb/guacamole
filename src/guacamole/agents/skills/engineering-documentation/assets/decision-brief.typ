// Decision / trade-study brief template. Presents a DecisionRequest's
// candidates before (or to record) a decide action. See
// references/document-types.md for when to include the Recommendation
// section.

// --- Document metadata: fill these in ---
#let title = "Decision brief"
#let doc_id = "doc-id-here"
#let revision = "A"
#let date = "2026-01-01"
#let status = "In review"
#let author = "task_id of the authoring agent"
#let decided = false // true once a decide action has selected a candidate

// --- Page setup (report-style; a brief is read, not presented) ---
#set page(
  paper: "a4",
  margin: (top: 3cm, bottom: 2.5cm, x: 2.5cm),
  footer: context [
    #line(length: 100%, stroke: 0.4pt + gray)
    #grid(
      columns: (1fr, 1fr),
      align(left)[#text(size: 9pt, fill: gray)[#doc_id · #revision · #status]],
      align(right)[#text(size: 9pt, fill: gray)[
        #counter(page).display() / #counter(page).final().first()
      ]],
    )
  ],
)
#set text(size: 11pt)
#set par(justify: true, leading: 0.65em)

#let cite(r) = raw(r.kind + ":" + r.id + "#" + str(r.revision))

#text(size: 20pt, weight: "bold")[#title]
#v(2pt)
#text(size: 12pt, fill: gray)[#doc_id]
#v(16pt)

= Question
// The DecisionRequest.question, verbatim.
Replace with the exact question text.

= Candidates
// One subsection per candidate: description, metrics, constraints, then a
// comparison table.

== Candidate A
Description of candidate A.

#table(
  columns: (auto, auto, auto),
  table.header([*Criterion*], [*Candidate A*], [*Candidate B*]),
  [Metric one], [0.0], [0.0],
  [Metric two], [0.0], [0.0],
)

= Evidence
// The refs each candidate's metrics rest on.
- #cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1)): what it measured.

#if decided [
  = Recommendation
  // Fill in only once a decide action has run. Quote DecisionResult.explanation
  // verbatim; do not summarize it.
  Selected: *Candidate A* (#cite((kind: "decision", id: "DECISION-ID", revision: 1))).

  _"Quote the decision's explanation verbatim here."_
]

= Traceability
#table(
  columns: (auto, auto, 1fr),
  table.header([*\#*], [*Citation*], [*What it supports*]),
  [1], [#cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))], [Candidate A metrics],
)
