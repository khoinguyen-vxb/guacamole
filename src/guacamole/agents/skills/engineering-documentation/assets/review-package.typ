// PDR/CDR review package template. Prepared by the Systems Engineer only,
// from the current ReviewManifest, the SysML model's satisfactions, and
// every worker's delivered artifacts and evidence. See
// references/document-types.md.

// --- Document metadata: fill these in ---
#let title = "Preliminary design review package" // or "Critical design review package"
#let doc_id = "doc-id-here"
#let revision = "A"
#let date = "2026-01-01"
#let status = "In review"
#let owner = "Project / system name"
#let author = "systems_engineer"
#let stage = "PDR" // "PDR" or "CDR"

// --- Page setup ---
#set page(
  paper: "a4",
  margin: (top: 3cm, bottom: 2.5cm, x: 2.5cm),
  header: context [
    #if counter(page).get().first() > 1 [
      #grid(
        columns: (1fr, 1fr),
        align(left)[#text(size: 9pt, fill: gray)[#doc_id]],
        align(right)[#text(size: 9pt, fill: gray)[#title]],
      )
      #line(length: 100%, stroke: 0.4pt + gray)
    ]
  ],
  footer: context [
    #line(length: 100%, stroke: 0.4pt + gray)
    #grid(
      columns: (1fr, 1fr),
      align(left)[#text(size: 9pt, fill: gray)[#revision · #status]],
      align(right)[#text(size: 9pt, fill: gray)[
        #counter(page).display() / #counter(page).final().first()
      ]],
    )
  ],
)
#set text(size: 11pt)
#set par(justify: true, leading: 0.65em)
#set heading(numbering: "1.1")

#let cite(r) = raw(r.kind + ":" + r.id + "#" + str(r.revision))
#let status_word(word) = {
  let c = if word in ("passed", "satisfied", "accepted") { rgb("#1a7f37") }
    else if word in ("failed", "violated", "rejected") { rgb("#cf222e") }
    else { rgb("#6e7781") }
  text(fill: c, weight: "bold")[#word]
}

#block(width: 100%, stroke: 0.6pt, inset: 14pt)[
  #text(size: 20pt, weight: "bold")[#title]
  #v(2pt)
  #text(size: 12pt, fill: gray)[#doc_id · #stage]
  #v(10pt)
  #grid(
    columns: (1fr, 1fr),
    gutter: 8pt,
    [*Revision*#h(6pt)#revision], [*Status*#h(6pt)#status],
    [*Date*#h(6pt)#date], [*Owner*#h(6pt)#owner],
    [*Author*#h(6pt)#author], [*Disposition*#h(6pt)_pending human review_],
  )
]
#v(20pt)

= Baseline
// The plan decide'd for this stage, the SysML model revision it was
// validated against, and the ReviewManifest's baseline refs.
This package reviews the #stage baseline under
#cite((kind: "decision", id: "PLAN-DECISION-ID", revision: 1)), validated against
#cite((kind: "system_model", id: "MODEL-ID", revision: 1)).

= Deliverables
#table(
  columns: (auto, auto, auto, 1fr),
  table.header([*Spec*], [*Artifacts*], [*Evidence*], [*Acceptance*]),
  [DELIVERABLE-SPEC-ID],
  [#cite((kind: "artifact", id: "ARTIFACT-ID", revision: 1))],
  [#cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))],
  [#status_word("passed")],
)

= Compliance
// Every bounded requirement's Satisfaction status from the current model,
// and every mandatory standard's applicability and assessment.
#table(
  columns: (auto, auto, auto, 1fr),
  table.header([*Requirement*], [*Bound*], [*Status*], [*Evidence*]),
  [#cite((kind: "requirement", id: "REQ-ID", revision: 1))], [metric <= value],
  [#status_word("satisfied")], [#cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))],
)

= Open items
// Every open item blocking this stage, and who/what owns resolving it.
- #cite((kind: "open_item", id: "OPEN-ITEM-ID", revision: 1)): description, owned by TASK-ID.

= Disposition
// Left blank for the human reviewer.
#block(stroke: 0.6pt, inset: 10pt, width: 100%)[
  *Human reviewer*: #h(2fr) \
  #v(8pt)
  *Disposition* (accepted / rejected): #h(2fr) \
  #v(8pt)
  *Comments*: #h(2fr)
]

= Traceability
#table(
  columns: (auto, auto, 1fr),
  table.header([*\#*], [*Citation*], [*What it supports*]),
  [1], [#cite((kind: "decision", id: "PLAN-DECISION-ID", revision: 1))], [Baseline, §1],
  [2], [#cite((kind: "system_model", id: "MODEL-ID", revision: 1))], [Baseline, §1],
)
