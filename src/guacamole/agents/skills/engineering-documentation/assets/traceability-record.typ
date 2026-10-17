// Traceability / compliance / regulatory record template. Prepared by the
// Systems Engineer only; a standing matrix of fact, not an opinionated
// report - no discussion, no recommendation. See
// references/document-types.md.

// --- Document metadata: fill these in ---
#let title = "Compliance and traceability record"
#let doc_id = "doc-id-here"
#let revision = "A"
#let date = "2026-01-01"
#let status = "In review"
#let owner = "Project / system name"
#let author = "systems_engineer"
#let approver = ""

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
#set table(inset: 6pt, align: horizon)

#let cite(r) = raw(r.kind + ":" + r.id + "#" + str(r.revision))
#let status_word(word) = {
  let c = if word in ("passed", "satisfied") { rgb("#1a7f37") }
    else if word in ("failed", "violated") { rgb("#cf222e") }
    else { rgb("#6e7781") }
  text(fill: c, weight: "bold")[#word]
}

#block(width: 100%, stroke: 0.6pt, inset: 14pt)[
  #text(size: 20pt, weight: "bold")[#title]
  #v(2pt)
  #text(size: 12pt, fill: gray)[#doc_id]
  #v(10pt)
  #grid(
    columns: (1fr, 1fr),
    gutter: 8pt,
    [*Revision*#h(6pt)#revision], [*Status*#h(6pt)#status],
    [*Date*#h(6pt)#date], [*Owner*#h(6pt)#owner],
    [*Author*#h(6pt)#author], [*Approver*#h(6pt)#if approver == "" [_pending human review_] else [#approver]],
  )
]
#v(20pt)

= Scope
// Which requirements/standards this record covers, and the SystemModel
// revision it reflects.
This record covers the requirements and standards below, against
#cite((kind: "system_model", id: "MODEL-ID", revision: 1)).

= Compliance matrix
#table(
  columns: (auto, 1fr, auto, auto),
  table.header([*Requirement*], [*Wording*], [*Status*], [*Evidence*]),
  [#cite((kind: "requirement", id: "REQ-ID", revision: 1))],
  ["Quote the requirement's wording verbatim."],
  [#status_word("satisfied")],
  [#cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))],
)

= Standards register
#table(
  columns: (auto, auto, auto, auto),
  table.header([*Standard*], [*Edition*], [*Clause requirement*], [*Status*]),
  ["AS 0000"], ["2020"], [#cite((kind: "requirement", id: "CLAUSE-REQ-ID", revision: 1))],
  [#status_word("satisfied")],
)

= Amendment history
#table(
  columns: (auto, auto, 1fr, auto),
  table.header([*Amendment*], [*Affects*], [*Rationale*], [*Status*]),
  [#cite((kind: "amendment", id: "AMENDMENT-ID", revision: 1))],
  [#cite((kind: "requirement", id: "REQ-ID", revision: 1))],
  ["Short rationale, quoted or closely paraphrased from the amendment."],
  ["adopted"],
)

= Traceability
#table(
  columns: (auto, auto, 1fr),
  table.header([*\#*], [*Citation*], [*What it supports*]),
  [1], [#cite((kind: "system_model", id: "MODEL-ID", revision: 1))], [Scope, §1],
  [2], [#cite((kind: "requirement", id: "REQ-ID", revision: 1))], [Compliance matrix, §2],
  [3], [#cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))], [Compliance matrix, §2],
)
