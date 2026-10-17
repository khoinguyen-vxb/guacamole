// Design-update deck template. One slide per #slide(..) call; copy this file
// and replace the example slides. See references/document-types.md.

// --- Document metadata: fill these in ---
#let title = "Subsystem design update"
#let doc_id = "doc-id-here"
#let revision = "A"
#let date = "2026-01-01"
#let status = "In review"
#let author = "task_id of the authoring agent"
#let stage = "" // "PDR", "CDR", or ""

// --- Page setup ---
#set page(
  paper: "presentation-16-9",
  margin: 1.8cm,
  footer: context [
    #grid(
      columns: (1fr, 1fr),
      align(left)[#text(size: 10pt, fill: gray)[#doc_id · #revision · #status]],
      align(right)[#text(size: 10pt, fill: gray)[#counter(page).display()]],
    )
  ],
)
#set text(size: 18pt)

// --- Helpers (same conventions as assets/report.typ) ---
#let cite(r) = raw(r.kind + ":" + r.id + "#" + str(r.revision))
#let status_word(word) = {
  let c = if word in ("passed", "satisfied") { rgb("#1a7f37") }
    else if word in ("failed", "violated") { rgb("#cf222e") }
    else { rgb("#6e7781") }
  text(fill: c, weight: "bold")[#word]
}

// One slide: a title and body content, laid out on its own page.
#let slide(heading_text, body) = {
  block(height: 100%)[
    #text(size: 28pt, weight: "bold")[#heading_text]
    #v(16pt)
    #body
  ]
  pagebreak(weak: true)
}

// --- Title slide ---
#align(center + horizon)[
  #text(size: 34pt, weight: "bold")[#title]
  #v(8pt)
  #text(size: 16pt, fill: gray)[#doc_id#if stage != "" [ · #stage ]]
  #v(24pt)
  #text(size: 14pt)[#author · #date · #revision]
]
#pagebreak(weak: true)

// --- Status at a glance ---
#slide("Status at a glance", [
  // What changed since the last update, each tied to a ref.
  - Change one, tied to #cite((kind: "decision", id: "DECISION-ID", revision: 1))
  - Change two, tied to #cite((kind: "evidence", id: "EVIDENCE-ID", revision: 1))
])

// --- One slide per subsystem area / requirement group ---
#slide("Requirement area: example", [
  #table(
    columns: (auto, auto, auto),
    table.header([*Requirement*], [*Value*], [*Outcome*]),
    [#cite((kind: "requirement", id: "REQ-ID", revision: 1))], [0.0], [#status_word("passed")],
  )
])

// --- Open items ---
#slide("Open items", [
  - #cite((kind: "open_item", id: "OPEN-ITEM-ID", revision: 1)): description, blocks PDR/CDR
])

// --- Next ---
#slide("Next", [
  - Remaining work and its dependencies.
])

// --- Traceability (small type; this is the audit trail, not read aloud) ---
#set text(size: 12pt)
#slide("Traceability", [
  #table(
    columns: (auto, auto, 1fr),
    table.header([*\#*], [*Citation*], [*What it supports*]),
    [1], [#cite((kind: "decision", id: "DECISION-ID", revision: 1))], [Status at a glance],
    [2], [#cite((kind: "requirement", id: "REQ-ID", revision: 1))], [Requirement area slide],
  )
])
