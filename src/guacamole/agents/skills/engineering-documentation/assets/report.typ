// Formal report template. Copy this file, fill in the metadata and sections
// below, and leave the page/title-block/helper machinery alone.
// See references/typst-style.md and references/document-types.md.

// --- Document metadata: fill these in ---
#let title = "Subsystem analysis report"
#let doc_id = "doc-id-here"
#let revision = "A"
#let date = "2026-01-01"
#let status = "In review" // In preparation | In review | Released | Withdrawn
#let owner = "Project / system name"
#let author = "task_id of the authoring agent"
#let approver = "" // leave blank; a human fills this in on acceptance
#let stage = "" // "PDR", "CDR", or "" if not tied to a review stage

// --- Page setup: shared across every report ---
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

// --- Helpers: shared across every template ---

// A short-form citation, e.g. cite((kind: "evidence", id: "7f3a9c", revision: 3))
// -> raw text "evidence:7f3a9c#3". Pass the Ref object as returned by a tool.
#let cite(r) = raw(r.kind + ":" + r.id + "#" + str(r.revision))

// Colors a known outcome/status word; anything else is left plain.
#let status_word(word) = {
  let c = if word in ("passed", "satisfied") { rgb("#1a7f37") }
    else if word in ("failed", "violated") { rgb("#cf222e") }
    else { rgb("#6e7781") } // unperformed, inconclusive, unverified
  text(fill: c, weight: "bold")[#word]
}

// --- Title page ---
#block(
  width: 100%,
  stroke: 0.6pt,
  inset: 14pt,
)[
  #text(size: 20pt, weight: "bold")[#title]
  #v(2pt)
  #text(size: 12pt, fill: gray)[#doc_id#if stage != "" [ · #stage ]]
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

= Executive summary
// One paragraph: what was done, what it shows, what (if anything) is open.
Replace this paragraph.

= Scope
// The task objective, and the requirement(s) this report addresses.
This report addresses #cite((kind: "requirement", id: "REQ-ID", revision: 1)):
_quote the requirement's wording here, verbatim_.

= Method
// What was built/run/analyzed, and with which tools. Name tool grants used,
// not internal reasoning.

= Results
// Every number here cites the evidence it came from.
#figure(
  table(
    columns: (auto, auto, auto, 1fr),
    table.header([*Metric*], [*Value*], [*Outcome*], [*Evidence*]),
    [Example metric], [0.0], [#status_word("passed")],
    [#cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))],
  ),
  caption: [Measured results against the requirement's bound.],
)

= Discussion
// What the results mean against the requirement's bound. Call out partial
// satisfaction explicitly - never round it off.

= Open items
// Unresolved OpenItems this work carries forward, and which review stage
// each blocks.
- #cite((kind: "open_item", id: "OPEN-ITEM-ID", revision: 1)): description,
  blocks #text(style: "italic")[PDR/CDR].

= Traceability
#table(
  columns: (auto, auto, 1fr),
  table.header([*\#*], [*Citation*], [*What it supports*]),
  [1], [#cite((kind: "requirement", id: "REQ-ID", revision: 1))], [Scope, §2],
  [2], [#cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))], [Results, §4, Table 1],
)
