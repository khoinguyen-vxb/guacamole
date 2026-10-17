# Typst style: one house style for every document

All five templates share this skeleton so a reviewer flipping between a
subsystem report and a review package sees one program, not five habits.
Copy it; do not redesign it per document.

## Page and type

- `#set page(paper: "a4", margin: (top: 3cm, bottom: 2.5cm, x: 2.5cm))` for
  reports and records. Slides and briefs use a presentation preset instead
  (see `assets/slides.typ`) - do not put slide content on A4 or vice versa.
- Leave the font unset. Typst's default (New Computer Modern) is always
  available in the compile environment; naming an installed font that isn't
  there fails the whole compile with no PDF produced.
- `#set par(justify: true, leading: 0.65em)`, body text at the default 11pt.
- `#set heading(numbering: "1.1")` for reports and records (headings are
  cited by number in review comments); slides and briefs leave headings
  unnumbered since each slide is already addressed by title.
- `#set table(inset: 6pt, align: horizon)` and draw every table with a
  horizontal rule under its header row only - no vertical rules, no shading.
  Dense grids (traceability tables, compliance matrices) may add a light
  horizontal rule every 5 rows for readability, nothing more.

## Title block

Every document opens with a title block carrying the same fields as a
drawing's ISO 7200 block (`integrations/drafting.py`'s `Sheet`), so a
document and a drawing for the same deliverable read as one family:

| Field | Source |
| --- | --- |
| `title` | What the document is about, not its kind - "Feed system CDR analysis", not "Report" |
| `doc_id` | The id you chose in SKILL.md step 1 |
| `revision` | `"A"` for a first issue; letter per re-issue after review comments |
| `date` | The compile date, ISO 8601 |
| `status` | `"In preparation"`, `"In review"`, `"Released"`, or `"Withdrawn"` - set by the agent until a human disposition changes it |
| `owner` | The project/system this belongs to |
| `author` | Your `task_id` |
| `approver` | Blank (`""`) until a human review accepts it - never fill this in yourself |
| `stage` | `"PDR"`, `"CDR"`, or `""` when the document isn't tied to a review stage |

Render it as a bordered block at the top of page one: title and doc id large,
the rest as a compact two-column key/value table underneath. All five
templates already implement this as a `title_block(..)` function - call it,
don't rebuild it.

## Headers, footers, page numbers

Every page after the title page carries:

- Header: `doc_id` left, `title` right, a thin rule beneath.
- Footer: `revision` and `status` left, page `n / total` right.

This is also already wired into each template via `#set page(header: .., footer: ..)`
reading the same variables as the title block - change the variables, not the
header/footer code.

## Figures and tables

- Number figures and tables independently (`#figure(.., kind: "table")` vs
  the default), and always give a caption - a figure with no caption cannot
  be cited from the body text.
- A plotted or measured figure is evidence: caption it with the artifact or
  evidence `Ref` it came from (short form, e.g. `evidence:a1b2…#4`), not just
  a description. See `references/traceability.md` for the short-form
  citation syntax used in captions and body text.
- Prefer a table over prose whenever you are listing more than three
  comparable values (metrics across candidates, requirements across a
  compliance matrix, open items) - reviewers scan tables, not paragraphs.

## Color

Use color only to carry meaning, consistently across every document:

- Headings and rules: black/default text color, no accent.
- Status/outcome words inline (`passed`, `failed`, `unperformed`,
  `inconclusive`, satisfied/violated/unverified) are the only colored text:
  green for passed/satisfied, red for failed/violated, gray for
  unperformed/unverified/inconclusive. Implement this once as a `status(..)`
  helper (each template already has one) and reuse it; never hand-color text
  elsewhere.
- Never use color as the only signal (always pair it with the word) - a
  document may be printed in black and white.

## Length and tone

Write for a reader deciding whether to accept a review or sign a submission,
not for the record alone:

- Lead each section with the conclusion, then the evidence for it - not the
  chronology of how the work happened.
- State uncertainty and open items plainly in their own section; do not bury
  a caveat in a subordinate clause inside a results paragraph.
- Keep a formal report or review package to what a human will actually read
  in one sitting; move raw data, long derivations, or full tool output to an
  appendix (its own numbered section at the end) rather than inline.
