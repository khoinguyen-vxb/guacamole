import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_support import TestReasoning

from examples.bracket import bracket
from guacamole import (
    AgentTurn,
    AskHuman,
    Candidate,
    Constraint,
    DecisionRequest,
    DeliverableSpec,
    Project,
    Requirement,
    ToolRegistry,
    WorkPlan,
)
from guacamole.contracts import Deliverable, Evidence, Rationale, Ref, Wait

SOURCE = Ref(kind="source", id="brief", revision=1, sha256="0" * 64)


def requirement(id, metric, unit, *, minimum=None, maximum=None, source=SOURCE):
    return Requirement(
        id=id,
        wording=f"TEST FIXTURE {id}",
        source=source,
        source_quote="fixture",
        constraint=Constraint(
            metric=metric, unit=unit, minimum=minimum, maximum=maximum
        )
        if metric
        else None,
    )


def part(name, material, density, volume, size=(10.0, 10.0, 10.0)):
    return {
        "name": name,
        "part_number": name.rstrip("12"),
        "material": material,
        "density": density,
        "valid": True,
        "solids": 1,
        "volume": volume,
        "size": list(size),
    }


# Shaped like freecad_bracket.inspect's report for a 60 x 100 x 180 x 8 mm
# aluminium bracket on two M6 screws, as FreeCAD measured it.
MEASURED = {
    "errors": [],
    "parameters": {
        "width": 60.0,
        "thickness": 8.0,
        "wall_leg": 100.0,
        "shelf_leg": 180.0,
        "edge": 13.2,
        "screw_d": 6.0,
    },
    "holes": 2,
    "components": [
        part("Bracket", "aluminium-6061-t6", 2700.0, 129465.2, (60.0, 180.0, 100.0)),
        part("Screw1", "steel", 7850.0, 1373.2),
        part("Screw2", "steel", 7850.0, 1373.2),
        part("Washer1", "steel", 7850.0, 129.48),
        part("Washer2", "steel", 7850.0, 129.48),
    ],
    "bom": [["item", "part_number"], ["1", "Bracket"]],
    "interferences": [],
    "step_volumes": [129.48, 129.48, 1373.2, 1373.2, 129465.2],
    "thickened": {"errors": [], "volume_before": 129465.2, "volume_after": 145108.4},
}


class BracketTests(unittest.IsolatedAsyncioTestCase):
    def test_each_constraint_becomes_a_traced_check(self):
        result = bracket.assess(
            MEASURED,
            MEASURED["bom"],
            250,
            (
                requirement("R1", "mass", "kg", maximum=0.5),
                requirement("R2", "safety_factor", "1", minimum=2),
                requirement("R3", "deflection", "mm", maximum=3),
                requirement("R4", "mass", "g", maximum=300),
                requirement("R5", "colour", "RAL", maximum=1),
                requirement("R6", None, ""),
            ),
        )
        checks = result.checks
        self.assertTrue(checks["R1: mass <= 0.5 kg"])
        self.assertTrue(checks["R2: safety_factor >= 2"])
        self.assertTrue(checks["R3: deflection <= 3 mm"])
        self.assertFalse(checks["R4: mass <= 300 g"])
        self.assertIsNone(checks["R5: colour <= 1 RAL"])  # Not measurable here.
        self.assertFalse([name for name in checks if name.startswith("R6")])
        self.assertEqual(result.outcome, "failed")
        # Cantilever plate: 6 F L / (W t^2) and 4 F L^3 / (E W t^3).
        self.assertAlmostEqual(result.measurements["max_stress"].value, 70.3125)
        self.assertAlmostEqual(result.measurements["deflection"].value, 2.7554, 3)
        self.assertAlmostEqual(result.measurements["R4"].value, 373.148, 2)
        self.assertEqual(result.measurements["R4"].unit, "g")
        geometry = [v for k, v in checks.items() if not k.startswith("R")]
        self.assertTrue(all(geometry))
        stale = bracket.assess(MEASURED, [["item"]], 250, ())
        self.assertFalse(stale.checks["BOM matches the assembly"])

    async def test_benchmark_answers_blocking_questions_then_reports(self):
        class Asking(TestReasoning):
            calls = 0

            async def respond(self, packet):
                self.calls += 1
                return AgentTurn(
                    rationale=Rationale(objective="fixture", explanation="Fixture"),
                    action=AskHuman(question="Which wall material?")
                    if self.calls == 1
                    else Wait(reason="Answered"),
                )

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bracket, "reasoning", Asking),
        ):
            brief = Path(directory) / "fixture.md"
            brief.write_text("TEST FIXTURE: hold 10 N")
            result = await bracket.run_brief(brief, Path(directory) / "runs")
        self.assertEqual(result["scripted_replies"], 1)
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["passed"])
        self.assertGreater(result["estimated_input_tokens"], 0)


@unittest.skipUnless(bracket.FREECAD, "needs FreeCAD (freecadcmd or freecad.cmd)")
class FreeCADBracketTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_bracket_reaches_an_accepted_review_with_its_report(self):
        # Snap and Flatpak FreeCAD builds see $HOME but not /tmp.
        cache = Path.home() / ".cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            root = Path(directory)
            with Project(
                root / "state", sandbox=root / "results", tools=ToolRegistry()
            ) as project:
                bracket.register_tools(project)
                generate = project.tools.get("bracket_generate@1")
                check = project.tools.get("bracket_check@1")
                brief = root / "brief.txt"
                brief.write_text(
                    "TEST FIXTURE: mass at most 0.5 kg, safety factor at least 2, "
                    "deflection at most 3 mm, at least 180 mm deep."
                )
                source = project.ingest(brief, source_id="brief")
                requirements = tuple(
                    project.record_requirement(
                        r.model_copy(update={"source": source, "source_quote": quote})
                    )
                    for r, quote in (
                        (requirement("R1", "mass", "kg", maximum=0.5), "0.5 kg"),
                        (
                            requirement("R2", "safety_factor", "1", minimum=2),
                            "at least 2",
                        ),
                        (requirement("R3", "deflection", "mm", maximum=3), "3 mm"),
                        (requirement("R4", "depth", "mm", minimum=180), "180 mm deep"),
                    )
                )
                kinds = ("native-cad", "step", "drawing", "bom")
                plan = DeliverableSpec(
                    id="PDR-bracket",
                    title="Shelf bracket",
                    stage="PDR",
                    requirements=requirements,
                    artifact_kinds=kinds,
                    evidence_kinds=("cad-verification",),
                    acceptance_criteria=("Every bracket_check check passes",),
                )
                decision = await project.decisions.choose(
                    DecisionRequest(
                        question="Select the fixture bracket plan",
                        kind="work_plan",
                        criteria=("Fixture coverage",),
                        candidates=(
                            Candidate(
                                id="fixture",
                                description="TEST ONLY",
                                plan=WorkPlan(
                                    stage="PDR",
                                    inputs=requirements,
                                    deliverables=(plan,),
                                ),
                            ),
                        ),
                    ),
                    selected="fixture",
                    explanation="Test fixture selection",
                )
                design = {
                    "material": "aluminium-6061-t6",
                    "width_mm": 60,
                    "thickness_mm": 8,
                    "wall_leg_mm": 100,
                    "shelf_leg_mm": 180,
                    "fastener": "M6",
                    "holes_per_leg": 2,
                }
                # A layout the parametric model cannot hold comes back as problems.
                cramped = await project.call(
                    generate,
                    {"design": {**design, "width_mm": 30}, "name": "cramped"},
                )
                self.assertIsNone(cramped.files)
                self.assertIn("width", cramped.problems[0])
                job = project.executor.submit(
                    generate,
                    {"design": design, "name": "shelf"},
                    decision_id=decision,
                    inputs=requirements,
                )
                built = (await job.collect()).files
                assert built is not None
                artifacts = {
                    kind: project.publish(
                        path=getattr(built, field).path,
                        artifact_id=kind,
                        kind=kind,
                        request_id=job.id,
                        decision_id=decision,
                        inputs=requirements,
                        requirements=requirements,
                    )
                    for kind, field in zip(kinds, ("native", "step", "drawing", "bom"))
                }
                checked = (artifacts["native-cad"], artifacts["step"], artifacts["bom"])
                check_job = project.executor.submit(
                    check,
                    {
                        "native_artifact": "native-cad",
                        "step_artifact": "step",
                        "bom_artifact": "bom",
                        "load_n": 250,
                    },
                    decision_id=decision,
                    inputs=checked,
                )
                result = await check_job.collect()
                self.assertEqual(result.outcome, "passed", result.checks)
                evidence = project.evidence(
                    Evidence(
                        id="bracket-check",
                        kind="cad-verification",
                        outcome=result.outcome,
                        explanation=result.explanation,
                        artifacts=checked,
                        requirements=requirements,
                        request_id=check_job.id,
                        decision_id=decision,
                    )
                )
                project.store.put(
                    "rationale",
                    "fixture-rationale",
                    Rationale(objective="Test", explanation="Fixture delivery"),
                    actor="script",
                )
                project.deliver(
                    Deliverable(
                        spec_id="PDR-bracket",
                        artifacts=tuple(artifacts.values()),
                        evidence=(evidence,),
                        rationale_id="fixture-rationale",
                    ),
                    decision_id=decision,
                )
                review = await project.reviews.generate(decision)
                self.assertEqual(project.store.resolve(review).data["status"], "ready")
                accepted = project.reviews.accept(
                    review, reviewer="test human", disposition="Accept the fixture"
                )
                self.assertTrue(project.reviews.accepted("PDR"))
                report = (
                    project.sandbox
                    / "reviews"
                    / accepted.id
                    / f"v{accepted.revision}"
                    / "review.md"
                ).read_text()
        rows: dict[str, str] = {}  # First occurrence: the requirements table.
        for line in report.splitlines():
            rows.setdefault(line.split(" | ")[0], line)
        self.assertIn("passed", rows["| R1"])
        self.assertIn(" kg ", rows["| R1"])
        self.assertIn("cad-verification (passed)", rows["| R4"])
        self.assertIn("ISO4017-M6x35-8.8", report)  # The BOM, as a table.
        self.assertIn("![drawing: BRK-shelf.svg]", report)
        self.assertIn("### cad-verification — passed", report)
        self.assertIn("Disposition by test human: Accept the fixture", report)


if __name__ == "__main__":
    unittest.main()
