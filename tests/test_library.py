import json
import os
import tempfile
import unittest
from pathlib import Path

from runtime_support import commit_fixture_model, plan_request

from guacamole import (
    Clause,
    HumanInput,
    Label,
    Library,
    Project,
    Requirement,
    Standard,
)
from guacamole.library import DoclingParser, PypdfParser


def write_pdf(path: Path, pages: list[list[str]]) -> Path:
    """A born-digital PDF: each page's lines top to bottom, laid out as a document.

    "# " starts a bold heading, set off from what precedes it; "" ends a paragraph.
    """

    def escape(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        "/Encoding /WinAnsiEncoding >>",
        4: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        "/Encoding /WinAnsiEncoding >>",
    }
    kids = []
    for lines in pages:
        n = max(objects) + 1
        y, shown = 790, []
        for line in lines:
            if not line:
                y -= 10
                continue
            heading = line.startswith("# ")
            if heading:
                y -= 12
            font, size = ("F2", 12) if heading else ("F1", 10)
            text = escape(line.removeprefix("# "))
            shown.append(f"/{font} {size} Tf 1 0 0 1 50 {y} Tm ({text}) Tj")
            y -= 16 if heading else 13
        stream = f"BT {' '.join(shown)} ET"
        objects[n] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
        objects[n + 1] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {n} 0 R >>"
        )
        kids.append(n + 1)
    objects[2] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] "
        f"/Count {len(kids)} >>"
    )
    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for i in sorted(objects):
        offsets[i] = len(out)
        out += f"{i} 0 obj\n{objects[i]}\nendobj\n".encode("cp1252")  # WinAnsiEncoding
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offsets[i]:010d} 00000 n \n" for i in sorted(objects)).encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    path.write_bytes(out)
    return path


def fixture_standard(path: Path, edition: str = "2010", minimum: str = "3") -> Path:
    return write_pdf(
        path,
        [
            [
                f"# TEST FIXTURE STANDARD TF 1210-{edition}",
                "Pressure vessels",
                "# CONTENTS",
                "1 SCOPE AND GENERAL .......... 2",
                "3.3.1 Minimum thickness .......... 3",
            ],
            [
                "# SECTION 1 SCOPE AND GENERAL",
                "# 1.1 Scope",
                "This Standard specifies requirements for pressure vessels.",
                "# 1.4 Definitions",
                "1.4.1 Design pressure: the maximum pressure the vessel is designed for.",
                "",
                "1.4.2 Hydrostatic test: a pressure test using water.",
                "# SECTION 3 DESIGN",
            ],
            [
                "# 3.2 Corrosion allowance",
                "# 3.2.4 Exemption for clad vessels",
                "Clad vessels need no corrosion allowance where cladding is 3 mm thick.",
                "# 3.3 Thickness",
                "# 3.3.1 Minimum thickness",
                "The thickness of shells shall be not less than that given in Table",
                "3.3.1(B), except as permitted in 3.2.4. The design pressure shall be",
                "used.",
                "",
                "NOTE: Thicker shells may be needed for external loads.",
                "",
                "TABLE 3.3.1(B) MINIMUM SHELL THICKNESS",
                f"Diameter up to 1000 mm: {minimum} mm",
                "Diameter over 1000 mm: 5 mm",
                "# 3.4 Hydrostatic test",
                "The vessel shall pass a hydrostatic test at 1.25 times the design",
                "pressure.",
            ],
        ],
    )


class LibraryTests(unittest.IsolatedAsyncioTestCase):
    def test_a_standard_becomes_linked_clauses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = fixture_standard(root / "tf1210.pdf")
            with Library(root / "shared") as library:
                snapshot = library.ingest(
                    pdf,
                    designation="TF 1210",
                    edition="2010",
                    label=Label(level="licensed", compartments=("licence:fixture",)),
                    parser=PypdfParser(),
                )
                self.assertEqual(snapshot.profile, "numbered-clause@1")
                elements = {e.id: e for e in library.elements(snapshot.id)}

                clause = elements["3.3.1"]
                self.assertEqual(
                    (clause.kind, clause.heading, clause.parent),
                    ("normative", "Minimum thickness", "3.3"),
                )
                self.assertEqual({p.page for p in clause.provenance}, {3})
                links = {(l.type, l.target) for l in clause.links}
                # The exception elsewhere, the table and the defined term it uses.
                self.assertLessEqual(
                    {
                        ("limits", "3.2.4"),
                        ("uses", "Table 3.3.1(B)"),
                        ("uses", "1.4.1"),
                    },
                    links,
                )
                self.assertEqual(elements["3.3.1/note1"].kind, "note")
                self.assertEqual(elements["Table 3.3.1(B)"].parent, "3.3.1")
                self.assertIn("1000 mm: 3 mm", elements["Table 3.3.1(B)"].text)
                self.assertEqual(elements["1.4.1"].kind, "definition")
                # Both defined terms, the second wrapped across a line break.
                self.assertEqual(
                    {(l.type, l.target) for l in elements["3.4"].links},
                    {("uses", "1.4.2"), ("uses", "1.4.1")},
                )
                # Contents entries never become elements or duplicate a clause.
                self.assertNotIn(
                    "..........", "".join(e.text for e in elements.values())
                )
                # A value is not a clause citation.
                self.assertNotIn("1.25", {l.target for l in elements["3.4"].links})

                again = library.ingest(
                    pdf,
                    designation="TF 1210",
                    edition="2010",
                    label=Label(level="licensed", compartments=("licence:fixture",)),
                    parser=PypdfParser(),
                )
                self.assertEqual(again, snapshot)
                self.assertEqual(library.snapshots(), (snapshot,))
                self.assertEqual(
                    library.original(snapshot).read_bytes(), pdf.read_bytes()
                )
            # Content-addressed: the same ingestion in another scope is the same snapshot.
            with Library(root / "project", scope="project") as project_scope:
                self.assertEqual(
                    project_scope.ingest(
                        pdf,
                        designation="TF 1210",
                        edition="2010",
                        label=Label(
                            level="licensed", compartments=("licence:fixture",)
                        ),
                        parser=PypdfParser(),
                    ).id,
                    snapshot.id,
                )

    def test_a_paragraph_coded_standard_with_appendices(self):
        # Laid out as ASME Y14.5 is: wrapped contents entries, "Section n" over
        # its title, inverted definitions, para. lists, hyphenated figures that
        # wrap, and mandatory and nonmandatory appendices.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = write_pdf(
                root / "tf145.pdf",
                [
                    [
                        "# Contents",
                        "Section 1 Scope . . . . . . . . . . . . . . . . 2",
                        "Section 3 Definitions . . . . . . . . . . . . . 2",
                        "4.2 Fundamental Rules for Dimensions and",
                        "Tolerances . 3",
                        "Figure 4-1 Datum Features . . . . . . . . . . 3",
                    ],
                    [
                        "# Section 1",
                        "# SCOPE",
                        "# 1.1 General",
                        "This Standard establishes practices; see paras. 4.2.1",
                        "through 4.2.2.",
                        "# Section 3",
                        "# DEFINITIONS",
                        "# 3.1 BOUNDARY, INNER (IB)",
                        "A worst-case boundary generated by the smallest feature.",
                        "# 3.2 CIRCULARITY (ROUNDNESS)",
                        "A condition of a surface of revolution.",
                    ],
                    [
                        "# Section 4",
                        "# FUNDAMENTAL RULES",
                        "# 4.2 Fundamental Rules",
                        "# 4.2.1 “Basic” Dimensions",
                        "Each dimension shall have a tolerance. The inner boundary",
                        "and the IB are shown in Figure 4-",
                        "1. Roundness is checked as in para. 4.2.2.",
                        "Figure 4-1 Datum Features",
                        "# 4.2.2 Measurement",
                        "Dimensions shall be measured at 20°C.",
                        "# 4.3 Rule #1: Envelope Principle",
                        "Form shall be within the size limits.",
                        "# 4.4 Exceptions to Rule #1",
                        "Rule #1 does not apply to stock.",
                    ],
                    [
                        "# MANDATORY APPENDIX I",
                        "# ALTERNATIVE PRACTICES",
                        "# I-1 GENERAL",
                        "Alternative practices shall be stated on the drawing.",
                        "# NONMANDATORY APPENDIX A",
                        "# PRINCIPAL CHANGES",
                        "# A-1 GENERAL",
                        "This Appendix shall be read as guidance only.",
                        "# A-1.1 Edited Definitions",
                        "Definitions were edited.",
                    ],
                ],
            )
            with Library(root / "library") as library:
                snapshot = library.ingest(
                    pdf, designation="TF 14.5", edition="2018", parser=PypdfParser()
                )
                elements = {e.id: e for e in library.elements(snapshot.id)}
            # The wrapped contents entry never becomes clause 4.2.
            self.assertEqual(elements["4.2"].heading, "Fundamental Rules")
            self.assertEqual(
                [(e.id, e.heading) for e in elements.values() if e.parent is None],
                [
                    ("1", "SCOPE"),
                    ("3", "DEFINITIONS"),
                    ("4", "FUNDAMENTAL RULES"),
                    ("Appendix I", "ALTERNATIVE PRACTICES"),
                    ("Appendix A", "PRINCIPAL CHANGES"),
                ],
            )
            self.assertEqual(elements["3.1"].kind, "definition")
            self.assertEqual(
                {(l.type, l.target) for l in elements["1.1"].links},
                {("refers_to", "4.2.1"), ("refers_to", "4.2.2")},
            )
            # The quoted heading is a clause; inverted terms, abbreviations and
            # synonyms link to their definitions, and the wrapped figure resolves.
            self.assertEqual(elements["4.2.1"].heading, "“Basic” Dimensions")
            self.assertLessEqual(
                {
                    ("uses", "3.1"),
                    ("uses", "3.2"),
                    ("uses", "Figure 4-1"),
                    ("refers_to", "4.2.2"),
                },
                {(l.type, l.target) for l in elements["4.2.1"].links},
            )
            self.assertEqual(elements["Figure 4-1"].parent, "4.2.1")
            # A rule cited by name; its exception, written in the citing clause.
            self.assertIn(
                ("limits", "4.3"), {(l.type, l.target) for l in elements["4.4"].links}
            )
            # A figure is its caption; the clause's text does not run into it.
            self.assertEqual(elements["Figure 4-1"].text, "Figure 4-1 Datum Features")
            self.assertEqual(
                [
                    (id, elements[id].parent, elements[id].kind)
                    for id in ("I-1", "A-1", "A-1.1")
                ],
                [
                    ("I-1", "Appendix I", "normative"),
                    ("A-1", "Appendix A", "informative"),
                    ("A-1.1", "A-1", "informative"),
                ],
            )

    def test_any_pdf_falls_back_to_pages_and_paragraphs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = write_pdf(
                root / "notes.pdf",
                [
                    [
                        "Bearing selection notes",
                        "Grease life falls with",
                        "temperature.",
                    ],
                    ["Seals add drag at low speed."],
                ],
            )
            with Library(root / "library") as library:
                snapshot = library.ingest(
                    pdf, designation="Notes", edition="1", parser=PypdfParser()
                )
                self.assertEqual(snapshot.profile, "fallback@1")
                elements = {e.id: e for e in library.elements(snapshot.id)}
                self.assertEqual(elements["p1"].kind, "page")
                self.assertEqual(
                    elements["p1.1"].text,
                    "Bearing selection notes\nGrease life falls with\ntemperature.",
                )
                self.assertEqual(elements["p2.1"].parent, "p2")
                self.assertFalse(any(e.links for e in elements.values()))

    async def test_a_pinned_clause_is_read_quoted_locked_and_reassessed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = Library(root / "shared")
            label = Label(level="licensed", compartments=("licence:fixture",))
            snapshot = shared.ingest(
                fixture_standard(root / "tf1210.pdf"),
                designation="TF 1210",
                edition="2010",
                label=label,
                parser=PypdfParser(),
            )
            with Project(root / "workspace", library=shared) as project:
                pin = project.pin(snapshot.id)
                self.assertEqual(
                    project.pin(snapshot.id), pin
                )  # Unchanged: no revision
                data = project.store.resolve(pin).data
                self.assertEqual(
                    (data["kind"], data["scope"], data["designation"], data["label"]),
                    ("library_pin", "shared", "TF 1210", label.model_dump(mode="json")),
                )

                reader = project.tools.get("get_element@1")
                self.assertFalse(reader.definition.requires_plan)
                job = project.submit(
                    reader,
                    {"source": pin.model_dump(mode="json"), "element": "3.3.1"},
                    inputs=(pin,),
                )
                excerpt = await job.collect()
                self.assertEqual(excerpt.locator, "TF 1210:2010 3.3.1")
                for shown in (
                    "[3.3.1] (normative)",
                    "[3.3.1/note1] (note)",
                    "[Table 3.3.1(B)] (table)",
                    "[3.2.4] (normative, limits from 3.3.1)",
                    "[1.4.1] (definition, uses from 3.3.1)",
                ):
                    self.assertIn(shown, excerpt.text)
                self.assertEqual(excerpt.metadata["kind"], "normative")
                self.assertEqual(excerpt.metadata["deferred"], [])
                self.assertIn(
                    "Extraction not independently verified", excerpt.missing_metadata
                )
                quoted = project.extract(job.id, actor="test")
                # Read the other way, the exception brings the rule it qualifies.
                exempting = await project.call(
                    reader,
                    {"source": pin.model_dump(mode="json"), "element": "3.2.4"},
                )
                self.assertIn("[3.3.1] (normative, limits 3.2.4)", exempting.text)

                outline = await project.call(
                    project.tools.get("library_outline@1"),
                    {"source": pin.model_dump(mode="json"), "under": "3.3"},
                )
                self.assertIn("  3.3.1 (normative) Minimum thickness", outline.text)
                self.assertNotIn("3.4", outline.text)
                hits = await project.call(
                    project.tools.get("search_library@1"),
                    {"query": "hydrostatic test"},
                )
                self.assertEqual({h.element for h in hits}, {"1.4.2", "3.4"})
                self.assertEqual(hits[0].source, pin)

                site_note = root / "brief.txt"
                site_note.write_text("A vessel installed in NSW.")
                brief = project.ingest(site_note, source_id="brief")
                site = project.record_requirement(
                    Requirement(
                        id="site", wording="NSW", source=brief, source_quote="in NSW"
                    )
                )
                yes = project.store.put(
                    "source",
                    "yes",
                    HumanInput(
                        run_id="fixture",
                        author="fixture human",
                        text="Yes.",
                        question="Design to TF 1210-2010?",
                    ),
                    actor="human:fixture",
                )
                selected = project.record_requirement(
                    Requirement(
                        id="code",
                        wording="Designed to TF 1210-2010",
                        source=yes,
                        source_quote="Yes.",
                        standard=Standard(
                            id="TF 1210", edition="2010", text=pin, basis=(site,)
                        ),
                    )
                )
                # The extracted excerpt cites the pin, so its words are a clause quote.
                thickness = project.record_requirement(
                    Requirement(
                        id="thickness",
                        wording="Shell thickness at least Table 3.3.1(B)",
                        source=quoted,
                        source_quote="The thickness of shells shall be not less than",
                        clause=Clause(standard=selected, reference="3.3.1"),
                    )
                )

                await commit_fixture_model(project)
                plan = await project.decisions.choose(
                    plan_request(site, selected, thickness),
                    selected="fixture",
                    explanation="TEST FIXTURE",
                )
                review = await project.reviews.generate(plan)
                package = project.sandbox / "reviews" / review.id / "v1"
                lock = json.loads((package / "standards.lock.json").read_text())
                self.assertEqual(lock[0]["clauses"], {"thickness": "3.3.1"})
                self.assertEqual(
                    lock[0]["library"],
                    {
                        "snapshot": snapshot.id,
                        "scope": "shared",
                        "sha256": snapshot.file_sha256,
                        "name": "tf1210.pdf",
                    },
                )

                # A corrected table is a new snapshot; pinning it revises the pin,
                # so the selection and the clause quoting the old one go stale.
                corrected = shared.ingest(
                    fixture_standard(root / "tf1210-corrected.pdf", minimum="4"),
                    designation="TF 1210",
                    edition="2010",
                    label=label,
                    parser=PypdfParser(),
                )
                self.assertNotEqual(corrected.id, snapshot.id)
                revised = project.pin(corrected.id)
                self.assertEqual((revised.id, revised.revision), (pin.id, 2))
                for id in ("code", "thickness"):
                    self.assertTrue(project.store.get("requirement", id).stale)
                self.assertFalse(project.store.get("requirement", "site").stale)
                with self.assertRaisesRegex(ValueError, "Stale reference"):
                    await project.call(
                        reader,
                        {"source": pin.model_dump(mode="json"), "element": "3.3.1"},
                    )
            shared.close()

    async def test_project_scope_documents_pin_without_a_shared_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = write_pdf(
                root / "client-spec.pdf",
                [["Client spec: paint all shells grey."]],
            )
            with Project(root / "workspace") as project:
                self.assertNotIn("shared", project.libraries)
                snapshot = project.project_library.ingest(
                    spec,
                    designation="ACME-SPEC-7",
                    edition="B",
                    label=Label(level="restricted", compartments=("client:acme",)),
                    parser=PypdfParser(),
                )
                pin = project.pin(snapshot.id)
                self.assertEqual(project.store.resolve(pin).data["scope"], "project")
                excerpt = await project.call(
                    project.tools.get("get_element@1"),
                    {"source": pin.model_dump(mode="json"), "element": "p1"},
                )
                self.assertIn("paint all shells grey", excerpt.text)
                self.assertIn(
                    "Ingested as pages and paragraphs: dependencies are unknown",
                    excerpt.missing_metadata,
                )
            # Reopened, the project scope persists and agents still get the readers.
            with Project(root / "workspace") as project:
                self.assertEqual(project.project_library.snapshots(), (snapshot,))
                project.tools.get("get_element@1")

    @unittest.skipUnless(
        os.environ.get("GUACAMOLE_LIVE_DOCLING"),
        "Set GUACAMOLE_LIVE_DOCLING=1 to parse with Docling (downloads its models)",
    )
    def test_docling_lays_out_the_same_clauses_with_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Library(root / "library") as library:
                snapshot = library.ingest(
                    fixture_standard(root / "tf1210.pdf"),
                    designation="TF 1210",
                    edition="2010",
                    parser=DoclingParser(),
                )
                self.assertTrue(snapshot.parser.startswith("docling@"))
                self.assertEqual(snapshot.profile, "numbered-clause@1")
                clause = library.element(snapshot.id, "3.3.1")
                self.assertTrue(all(p.bbox for p in clause.provenance))
                self.assertIn(
                    ("limits", "3.2.4"), {(l.type, l.target) for l in clause.links}
                )
