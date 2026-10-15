import json
import tempfile
import unittest
from pathlib import Path

from runtime_support import commit_fixture_model, plan_request

from guacamole import (
    Clause,
    DecisionBlocked,
    Fact,
    HumanInput,
    Project,
    Requirement,
    Standard,
    Withdrawal,
)
from guacamole.standards import edition_key, evaluate


class StandardsTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_standard_is_human_selected_pinned_and_reassessed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(root) as project:

                def source(name, text):
                    (root / name).write_text(text)
                    return project.ingest(root / name, source_id=name)

                def human(id, text, question):
                    note = HumanInput(
                        run_id="fixture",
                        author="fixture human",
                        text=text,
                        question=question,
                    )
                    return project.store.put("source", id, note, actor="human:fixture")

                def stale(id):
                    return project.store.get("requirement", id).stale

                brief = source(
                    "brief.txt", "A 200 L vessel installed in NSW, designed to AS 1210."
                )
                licensed = source(
                    "as1210.txt", "TEST FIXTURE AS 1210-2010\n3.3.1 Minimum thickness"
                )
                site = project.record_requirement(
                    Requirement(
                        id="site",
                        wording="NSW",
                        source=brief,
                        source_quote="installed in NSW",
                    )
                )
                code = Requirement(
                    id="code",
                    wording="Designed to AS 1210-2010",
                    source=brief,
                    source_quote="designed to AS 1210",
                    standard=Standard(id="AS 1210", edition="2010", basis=(site,)),
                )
                # The brief names no edition: pinning one is the human's decision.
                with self.assertRaisesRegex(ValueError, "ask the human"):
                    project.record_requirement(code)
                code = code.model_copy(
                    update={
                        "source": human("yes", "Yes.", "Design to AS 1210-2010?"),
                        "source_quote": "Yes.",
                    }
                )
                selected = project.record_requirement(code)
                with self.assertRaisesRegex(ValueError, "code already selects AS 1210"):
                    project.record_requirement(code.model_copy(update={"id": "again"}))
                clause = Requirement(
                    id="thickness",
                    wording="Minimum thickness",
                    source=licensed,
                    source_quote="3.3.1 Minimum thickness",
                    clause=Clause(standard=selected, reference="3.3.1"),
                )
                with self.assertRaisesRegex(
                    ValueError, "with the standard's licensed text"
                ):
                    project.record_requirement(clause)

                # Without its licensed text, nothing can be verified against it.
                await commit_fixture_model(project)
                plan = await project.decisions.choose(
                    plan_request(site, selected),
                    selected="fixture",
                    explanation="TEST FIXTURE",
                )
                self.assertIn(
                    "code: no licensed text of AS 1210:2010 in the project to verify against",
                    project.reviews.checks(plan)[2],
                )

                pin = code.standard.model_copy(update={"text": licensed})
                selected = project.record_requirement(
                    code.model_copy(update={"standard": pin})
                )
                clause = clause.model_copy(
                    update={"clause": Clause(standard=selected, reference="3.3.1")}
                )
                with self.assertRaisesRegex(
                    ValueError, "from the licensed text of AS 1210"
                ):
                    project.record_requirement(
                        clause.model_copy(
                            update={"source": brief, "source_quote": "AS 1210"}
                        )
                    )
                thickness = project.record_requirement(clause)
                await commit_fixture_model(project)
                plan = await project.decisions.choose(
                    plan_request(site, selected, thickness),
                    selected="fixture",
                    explanation="TEST FIXTURE",
                )
                review = await project.reviews.generate(plan)
                self.assertFalse(
                    [
                        i
                        for i in project.store.resolve(review).data["open_items"]
                        if "licensed" in i
                    ]
                )
                package = root / "reviews" / review.id / "v1"
                self.assertIn(
                    "| AS 1210:2010 | none | code | as1210.txt (",
                    (package / "review.md").read_text(),
                )
                lock = json.loads((package / "standards.lock.json").read_text())
                self.assertEqual(
                    (lock[0]["id"], lock[0]["edition"], lock[0]["clauses"]),
                    ("AS 1210", "2010", {"thickness": "3.3.1"}),
                )

                # A changed edition or jurisdiction reopens everything resting on it.
                edition = human(
                    "2021", "Use the 2021 edition.", "Which edition of AS 1210?"
                )
                project.record_requirement(
                    code.model_copy(
                        update={
                            "source": edition,
                            "source_quote": "Use the 2021 edition.",
                            "standard": pin.model_copy(update={"edition": "2021"}),
                        }
                    )
                )
                self.assertTrue(stale("thickness"))
                project.record_requirement(
                    Requirement(
                        id="site", wording="NSW site", source=brief, source_quote="NSW"
                    )
                )
                self.assertTrue(stale("code"))


class RulesTests(unittest.TestCase):
    def test_editions_order_by_year_then_amendment(self):
        editions = ["2021", "2010+A2:2018", "2010", "2010 Amdt 1", "Edition"]
        self.assertEqual(
            sorted(editions, key=edition_key),
            ["Edition", "2010", "2010 Amdt 1", "2010+A2:2018", "2021"],
        )

    def test_a_missing_fact_makes_a_rule_unknown_not_false(self):
        rule = "jurisdiction == 'NSW' and pressure * volume > 10000"
        self.assertEqual(
            evaluate(rule, {"jurisdiction": "NSW", "pressure": 1500, "volume": 200}),
            (True, ()),
        )
        self.assertEqual(
            evaluate(rule, {"jurisdiction": "NSW"}), (None, ("pressure", "volume"))
        )
        # One false part decides an and; one true part an or.
        self.assertEqual(evaluate(rule, {"jurisdiction": "QLD"})[0], False)
        self.assertEqual(evaluate("a or b", {"b": True}), (True, ("a",)))
        self.assertEqual(evaluate("level in ('A', 'B')", {"level": "C"})[0], False)
        with self.assertRaisesRegex(ValueError, "cannot use its facts"):
            evaluate("pressure > 10", {"pressure": "high"})
        for unsafe in ("__import__('os')", "a.b", "[x for x in y]", "a if b else c"):
            with self.assertRaisesRegex(ValueError, "not allowed|not an expression"):
                evaluate(unsafe, {})


class CatalogueTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_catalogue_decides_which_standards_a_review_requires(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(root) as project:

                def source(name, text):
                    (root / name).write_text(text)
                    return project.ingest(root / name, source_id=name)

                def human(id, text, question):
                    note = HumanInput(
                        run_id="fixture",
                        author="fixture human",
                        text=text,
                        question=question,
                    )
                    return project.store.put("source", id, note, actor="human:fixture")

                def issues(*requirements):
                    plan = project.decisions.choose(
                        plan_request(*requirements),
                        selected="fixture",
                        explanation="TEST FIXTURE",
                    )
                    return plan

                rules = {
                    "entries": [
                        {
                            "id": "AS 1210",
                            "editions": ["2010", "2021"],
                            "mandatory": True,
                            "applies_when": "jurisdiction == 'NSW' and "
                            "design_pressure * volume > 10000",
                            "units": {"design_pressure": "kPa", "volume": "L"},
                        },
                        {
                            "id": "AS 4343",
                            "editions": ["2014"],
                            "mandatory": True,
                            "applies_when": "hazard_level in ('A', 'B')",
                        },
                    ]
                }
                project.record_catalogue(source("catalogue.json", json.dumps(rules)))
                brief = source(
                    "brief.txt", "A 200 L vessel at 1500 kPa, installed in NSW."
                )

                def stated(id, quote, fact, source=brief):
                    return project.record_requirement(
                        Requirement(
                            id=id,
                            wording=quote,
                            source=source,
                            source_quote=quote,
                            fact=fact,
                        )
                    )

                # A fact's value and unit are what the quote says, nothing else.
                with self.assertRaisesRegex(ValueError, "does not say"):
                    stated(
                        "pressure",
                        "1500 kPa",
                        Fact(name="design_pressure", value=1.5, unit="MPa"),
                    )
                facts = [
                    stated(
                        "site",
                        "installed in NSW",
                        Fact(name="jurisdiction", value="NSW"),
                    ),
                    stated("volume", "200 L", Fact(name="volume", value=200, unit="L")),
                    stated(
                        "pressure",
                        "1500 kPa",
                        Fact(name="design_pressure", value=1500, unit="kPa"),
                    ),
                ]
                await commit_fixture_model(project)
                plan = await issues(*facts)
                found = project.reviews.checks(plan)[2]
                self.assertIn(
                    "AS 1210: the catalogue's rule says it applies, and no requirement "
                    "selects it",
                    found,
                )
                self.assertIn(
                    "AS 4343: whether it applies is unknown without hazard_level", found
                )

                # Selecting AS 1210 and stating the hazard level settle both.
                code = project.record_requirement(
                    Requirement(
                        id="code",
                        wording="Designed to AS 1210-2010",
                        source=human("yes", "Yes, 2010.", "Design to AS 1210-2010?"),
                        source_quote="Yes, 2010.",
                        standard=Standard(id="AS 1210", edition="2010"),
                    )
                )
                level = stated(
                    "hazard",
                    "Hazard level C",
                    Fact(name="hazard_level", value="C"),
                    human("level", "Hazard level C", "Which AS 4343 hazard level?"),
                )
                await commit_fixture_model(project)
                plan = await issues(*facts, code, level)
                found = project.reviews.checks(plan)[2]
                self.assertFalse(
                    [i for i in found if i.startswith(("AS 1210:", "AS 4343:"))], found
                )
                review = await project.reviews.generate(plan)
                text = (root / "reviews" / review.id / "v1" / "review.md").read_text()
                self.assertIn("| AS 1210 | jurisdiction == 'NSW'", text)
                self.assertIn(
                    "applies (mandatory) | code | 2010 (catalogue lists 2021) |", text
                )
                self.assertIn(
                    "| AS 4343 | hazard_level in ('A', 'B') | does not apply (mandatory) | none |",
                    text,
                )

                # A move to Queensland takes AS 1210 out; the human withdraws it.
                moved = human("qld", "It moves to QLD.", "Where is it installed?")
                facts[0] = stated(
                    "site",
                    "It moves to QLD.",
                    Fact(name="jurisdiction", value="QLD"),
                    moved,
                )
                with self.assertRaisesRegex(ValueError, "a human statement quoted"):
                    project.record_requirement(
                        project.store.model(
                            "requirement", "code", Requirement
                        ).model_copy(
                            update={
                                "withdrawn": Withdrawal(source=moved, quote="not said")
                            }
                        )
                    )
                withdrawn = project.record_requirement(
                    project.store.model("requirement", "code", Requirement).model_copy(
                        update={
                            "withdrawn": Withdrawal(
                                source=moved, quote="It moves to QLD."
                            )
                        }
                    )
                )
                self.assertNotIn(
                    "code", [s.ref.id for s in project.sysml.requirements()]
                )
                await commit_fixture_model(project)
                with self.assertRaisesRegex(
                    DecisionBlocked, "Withdrawn requirements need no work"
                ):
                    await issues(*facts, level, withdrawn)
                plan = await issues(*facts, level)
                found = project.reviews.checks(plan)[2]
                self.assertFalse(
                    [i for i in found if i.startswith(("AS 1210:", "AS 4343:"))], found
                )
                review = await project.reviews.generate(plan)
                text = (root / "reviews" / review.id / "v1" / "review.md").read_text()
                self.assertIn(
                    '| code | Designed to AS 1210-2010 | — | withdrawn | qld: "It moves to QLD." |',
                    text,
                )
                self.assertIn("| AS 1210 | jurisdiction == 'NSW'", text)
                self.assertIn("does not apply (mandatory) | none | — |", text)


if __name__ == "__main__":
    unittest.main()
