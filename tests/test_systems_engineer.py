import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import sysml
from runtime_support import TestReasoning, passed_evidence, plan_request
from sysml.library import LibraryUnavailable

from guacamole import (
    AgentSpec,
    AgentTurn,
    Amendment,
    Budget,
    Candidate,
    Constraint,
    ContextSpec,
    DecisionRequest,
    Note,
    Project,
    ProjectRequest,
    Quantity,
    Ref,
    Requirement,
    SystemsEngineer,
    TaskAuthorization,
    TaskReport,
)
from guacamole.agents.systems_engineer import OBJECTIVE
from guacamole.contracts import (
    Acknowledge,
    AgentState,
    Assessment,
    Compliance,
    Decide,
    Finish,
    Rationale,
    Record,
    Send,
    Spawn,
    UpdateModel,
    Wait,
)
from guacamole.decision import DecisionBlocked
from guacamole.integrations.sysml import validator
from guacamole.integrations.sysml.registry import ModelRejected

try:
    sysml.standard_library()
    LIBRARY = True
except LibraryUnavailable:
    LIBRARY = False
# Only sysml's platform wheels carry its standard library; linux-aarch64 has none.
needs_library = unittest.skipUnless(LIBRARY, "sysml has no standard library here")

WORDING = "Liftoff mass shall not exceed 50 kg"
# Validator-only checks never resolve requirement sources.
SOURCE = Ref(kind="source", id="fixture", revision=1, sha256="0" * 64)


def rocket(limit=50, mass=42, extra=""):
    """TEST FIXTURE: a minimal SysML v2 model, not an engineering design."""
    return {
        "rocket.sysml": f"""package Rocket {{
  private import ISQ::*;
  private import SI::*;
  part def Vehicle {{ attribute mass :> ISQ::mass; attribute speed :> ISQ::speed; }}
  part vehicle : Vehicle {{ attribute redefines mass = {mass} [kg]; }}
  requirement <'R1'> liftoffMass {{
    doc /* Liftoff mass shall not exceed {limit} kg */
    subject v : Vehicle;
    require constraint {{ v.mass <= {limit} [kg] }}
  }}
  satisfy liftoffMass by vehicle;{extra}
}}
"""
    }


def requirement(source, limit=50.0, id="R1"):
    return Requirement(
        id=id,
        wording=f"Liftoff mass shall not exceed {limit:g} kg",
        source=source,
        source_quote=f"Liftoff mass shall not exceed {limit:g} kg",
        constraint=Constraint(metric="mass", unit="kg", maximum=limit),
    )


def choice(*candidates, question="Select a fixture motor"):
    return DecisionRequest(
        question=question,
        kind="engineering",
        criteria=("Fixture criterion",),
        candidates=candidates,
    )


@needs_library
class ValidatorTests(unittest.TestCase):
    def test_valid_model_traces_requirements_bounds_and_satisfactions(self):
        report = validator.validate(rocket(), [requirement(SOURCE)])
        self.assertTrue(report.valid, report.issues)
        self.assertEqual([r.id for r in report.requirements], ["R1"])
        [bound] = report.bounds
        self.assertEqual(
            (bound.metric, bound.name, bound.unit, bound.maximum),
            ("Rocket::Vehicle::mass", "mass", "kg", 50.0),
        )
        [claim] = report.satisfactions
        self.assertEqual(
            (claim.status, claim.element), ("satisfied", "Rocket::vehicle")
        )

    def test_reports_every_truth_defect(self):
        unparsed = validator.validate({"a.sysml": "package P { part x : ; }"}, [])
        self.assertFalse(unparsed.valid)
        self.assertEqual(
            [(i.code, i.element) for i in unparsed.issues], [("syntax", "a.sysml")]
        )
        extra = """
  part spare : Undefined;
  requirement <'R9'> invented { doc /* not recorded */ }
  requirement <'R1.1'> cruise {
    doc /* derived */
    subject v : Vehicle;
    require constraint { v.speed >= 1 [m/s] and v.speed <= 5 [m/s] }
  }"""
        report = validator.validate(
            rocket(limit=55, mass=60, extra=extra),
            [
                requirement(SOURCE),
                requirement(SOURCE, limit=10, id="R2"),
            ],
        )
        self.assertFalse(report.valid)
        codes = {(i.code, i.element) for i in report.issues if i.severity == "error"}
        self.assertEqual(
            codes,
            {
                ("unresolved", "Rocket::spare"),
                ("unrecorded_requirement", "R9"),
                ("unrecorded_requirement", "R1.1"),  # Derived only when nested.
                ("unmodeled_requirement", "R2"),
                ("constraint_mismatch", "R1"),
                ("satisfaction_violated", "R1 by Rocket::vehicle"),
            },
        )
        derived = next(b for b in report.bounds if b.requirement == "R1.1")
        self.assertEqual(validator.describe(derived), "1 m/s <= speed <= 5 m/s")

    def test_candidate_metrics_must_respect_model_bounds(self):
        bounds = validator.validate(rocket(), [requirement(SOURCE)]).bounds
        kg = Quantity(value=45.0, unit="kg")
        self.assertEqual(validator.violations(bounds, {"mass": kg}), [])
        self.assertEqual(
            validator.violations(bounds, {"mass": Quantity(value=55.0, unit="kg")}),
            ["mass = 55 kg violates R1: mass <= 50 kg"],
        )
        self.assertIn(
            "must be reported in 'kg'",
            validator.violations(bounds, {"mass": Quantity(value=4.5e4, unit="g")})[0],
        )
        self.assertEqual(
            validator.violations(bounds, {"Rocket::Vehicle::mass": kg, "cost": kg}), []
        )
        shared = (*bounds, bounds[0].model_copy(update={"metric": "Payload::mass"}))
        self.assertIn("ambiguous", validator.violations(shared, {"mass": kg})[0])

    def test_one_and_no_unit_are_both_dimensionless(self):
        recorded = Requirement(
            id="R1",
            wording="Safety factor at least 2.5",
            source=SOURCE,
            source_quote="Safety factor at least 2.5",
            constraint=Constraint(metric="sf", unit="1", minimum=2.5),
        )
        for written in ("2.5 [1]", "2.5"):
            report = validator.validate(
                {
                    "s.sysml": "package S { part def P { attribute sf; }\n"
                    "requirement <'R1'> r { doc /* Safety factor at least 2.5 */ "
                    f"subject p : P; require constraint {{ p.sf >= {written} }} }} }}"
                },
                [recorded],
            )
            self.assertTrue(report.valid, report.issues)
        sf = Quantity(value=3.0, unit="1")
        self.assertEqual(validator.violations(report.bounds, {"sf": sf}), [])


class TruthGateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.project = Project(
            root / "state", sandbox=root / "out", systems_engineer=SystemsEngineer()
        )
        (root / "brief.txt").write_text(
            f"{WORDING}. Liftoff mass shall not exceed 40 kg."
        )
        self.brief = self.project.ingest(root / "brief.txt", source_id="brief")
        self.r1 = self.project.record_requirement(requirement(self.brief))

    async def asyncTearDown(self):
        self.project.close()
        self.directory.cleanup()

    @needs_library
    async def test_decisions_need_a_current_model_of_every_requirement(self):
        project = self.project
        motors = choice(
            Candidate(
                id="A",
                description="Fixture",
                metrics={"mass": Quantity(value=45.0, unit="kg")},
            ),
            Candidate(
                id="B",
                description="Fixture",
                metrics={"mass": Quantity(value=55.0, unit="kg")},
            ),
        )
        with self.assertRaisesRegex(DecisionBlocked, "No SysML model yet"):
            await project.decisions.choose(motors, selected="A", explanation="Fixture")
        with self.assertRaises(ModelRejected) as rejected:
            await project.sysml.commit(
                summary="Fixture", files=rocket(limit=55), derived_from=(self.r1,)
            )
        self.assertEqual(
            [i.code for i in rejected.exception.report.issues if i.severity == "error"],
            ["constraint_mismatch"],
        )
        with self.assertRaisesRegex(ValueError, "derived_from"):
            await project.sysml.commit(summary="Fixture", files=rocket())
        unclaimed = rocket()["rocket.sysml"].replace(
            "  satisfy liftoffMass by vehicle;", ""
        )
        await project.sysml.commit(
            summary="Fixture",
            files={"rocket.sysml": unclaimed},
            derived_from=(self.brief, self.r1),
        )
        model, invalidated = await project.sysml.commit(
            summary="Fixture", files=rocket(), derived_from=(self.brief, self.r1)
        )
        self.assertEqual((model.revision, invalidated), (2, {}))
        # A satisfy claim is model content; only an assessment unblocks the review.
        self.assertEqual(
            project.sysml.review_issues(),
            (
                (
                    "R1: no compliance assessment against SysML model revision 2; "
                    "send the passed evidence to the systems engineer to assess"
                ),
            ),
        )

        def assess(measurements, requirements=(self.r1,), measurement=""):
            evidence = passed_evidence(
                project, requirements, measurements, id=f"ev-{len(project.events())}"
            )
            claim = Compliance(requirement="R1", measurement=measurement)
            return evidence, project.sysml.assess(
                Assessment(
                    id="assessment",
                    evidence=evidence,
                    satisfied=(claim,),
                    explanation="x",
                )
            )

        kg = Quantity(value=42.0, unit="kg")
        for measurements, requirements, error in (
            ({"R1": Quantity(value=60.0, unit="kg")}, (self.r1,), "violates R1"),
            ({"R1": Quantity(value=42e3, unit="g")}, (self.r1,), "reported in 'kg'"),
            ({"R1": kg}, (), "does not cover it"),
            ({"mass": kg}, (self.r1,), "no measurement 'R1'"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                assess(measurements, requirements)
        evidence, assessment = assess({"mass": kg}, measurement="mass")
        self.assertEqual(project.sysml.review_issues(), ())
        # Assessing stales nothing it assessed, unlike a model revision would.
        self.assertFalse(project.store.resolve(evidence).stale)
        self.assertEqual(project.sysml.current().ref, model)
        exported = project.sandbox / "sysml"
        self.assertEqual(
            (exported / "rocket.sysml").read_text(), rocket()["rocket.sysml"]
        )
        self.assertEqual(
            json.loads((exported / "report.json").read_text())["ref"]["revision"], 2
        )

        with self.assertRaisesRegex(DecisionBlocked, "Contradicts the SysML model"):
            await project.decisions.choose(motors, selected="B", explanation="Fixture")
        decision = await project.decisions.choose(
            motors, selected="A", explanation="Fixture"
        )
        record = project.decisions.record(decision)
        self.assertEqual(record.model, model)
        self.assertEqual([c.id for c in record.request.candidates], ["A"])

        r2 = requirement(self.brief, limit=40, id="R2")
        project.record_requirement(r2)
        with self.assertRaisesRegex(DecisionBlocked, "does not model requirements R2"):
            await project.decisions.choose(motors, selected="A", explanation="Fixture")
        self.assertEqual(project.sysml.state(engineer=False)["status"], "incomplete")
        project.record_requirement(requirement(self.brief, limit=40))  # Revises R1.
        self.assertTrue(project.sysml.current().stale)
        self.assertTrue(project.store.resolve(assessment).stale)
        with self.assertRaisesRegex(DecisionBlocked, "stale"):
            await project.decisions.choose(motors, selected="A", explanation="Fixture")
        self.assertTrue(project.sysml.review_issues())

    @needs_library
    async def test_model_revision_rolls_back_when_its_inputs_depend_on_prior_model(
        self,
    ):
        project = self.project
        base, _ = await project.sysml.commit(
            summary="Fixture", files=rocket(), derived_from=(self.r1,)
        )
        decision = await project.decisions.choose(
            choice(Candidate(id="A", description="Fixture", evidence=(base,))),
            selected="A",
            explanation="Fixture",
        )
        decision_ref = project.store.get("decision", decision).ref
        output = project.store.put(
            "tool_result",
            "fixture-output",
            {"result": "Fixture"},
            actor="fixture",
            dependencies=(decision_ref,),
        )
        for dependency in (decision_ref, output):
            with self.subTest(kind=dependency.kind):
                before = len(project.events())
                with self.assertRaisesRegex(ValueError, "invalidate its own inputs"):
                    await project.sysml.commit(
                        summary="Fixture circular provenance",
                        derived_from=(dependency,),
                    )
                self.assertEqual(project.sysml.current().ref, base)
                self.assertFalse(project.store.resolve(base).stale)
                self.assertFalse(project.store.resolve(dependency).stale)
                self.assertEqual(len(project.events()), before)
                self.assertEqual(
                    (project.sandbox / "sysml/rocket.sysml").read_text(),
                    rocket()["rocket.sysml"],
                )
        updated, _ = await project.sysml.commit(
            summary="Fixture independent provenance", derived_from=(self.r1,)
        )
        self.assertEqual(updated.revision, 2)
        self.assertFalse(project.store.resolve(updated).stale)
        self.assertTrue(project.store.resolve(decision_ref).stale)

    @needs_library
    async def test_a_new_revision_invalidates_decisions_it_contradicts(self):
        project = self.project
        await project.sysml.commit(
            summary="Fixture", files=rocket(), derived_from=(self.r1,)
        )
        motor = Candidate(
            id="A",
            description="Fixture",
            metrics={"mass": Quantity(value=45.0, unit="kg")},
        )
        decision = await project.decisions.choose(
            choice(motor), selected="A", explanation="Fixture"
        )
        r1 = project.record_requirement(requirement(self.brief, limit=40))
        self.assertFalse(project.store.get("decision", decision).stale)
        ref, invalidated = await project.sysml.commit(
            summary="Fixture", files=rocket(limit=40, mass=38), derived_from=(r1,)
        )
        self.assertEqual(ref.revision, 2)
        self.assertEqual(list(invalidated), [decision])
        self.assertIn("mass = 45 kg violates R1", invalidated[decision])
        self.assertTrue(project.store.get("decision", decision).stale)

    @needs_library
    async def test_amendments_are_adopted_by_decision_then_implemented(self):
        project = self.project
        base, _ = await project.sysml.commit(
            summary="Fixture", files=rocket(), derived_from=(self.r1,)
        )
        bay = Amendment(
            id="A1",
            title="Add a payload bay",
            rationale="TEST FIXTURE",
            files={"payload.sysml": "package Payload { part def Bay; }"},
        )
        ref = await project.sysml.amend(bay, actor="fixture")
        record = project.store.resolve(ref).data
        self.assertEqual(record["base"], base.model_dump(mode="json"))
        self.assertEqual(record["changes"]["files"], ["payload.sysml"])
        self.assertEqual(
            record["changes"]["elements_added"], ["Payload", "Payload::Bay"]
        )
        self.assertEqual(project.sysml.status("A1"), ("proposed", None))
        self.assertEqual(
            amendment_issues(project),
            ("Amendment A1 is proposed: Add a payload bay",),
        )
        with self.assertRaisesRegex(ValueError, "A1 is proposed"):
            await project.sysml.commit(summary="Fixture", implements="A1")

        adopt = Candidate(id="adopt", description="Fixture", evidence=(ref,))
        keep = Candidate(id="keep", description="Fixture")
        await project.decisions.choose(
            choice(adopt, keep), selected="keep", explanation="Fixture"
        )
        self.assertEqual(project.sysml.status("A1")[0], "rejected")
        decision = await project.decisions.choose(
            choice(adopt, keep), selected="adopt", explanation="Fixture"
        )
        self.assertEqual(project.sysml.status("A1"), ("accepted", decision))
        with self.assertRaisesRegex(ValueError, "exactly"):
            await project.sysml.commit(
                summary="Fixture", implements="A1", files=rocket()
            )
        implemented, _ = await project.sysml.commit(summary="Fixture", implements="A1")
        self.assertEqual(implemented.revision, 2)
        self.assertEqual(project.sysml.status("A1"), ("implemented", None))
        self.assertIn(
            project.store.get("decision", decision).ref,
            project.store.get("system_model", "system").dependencies,
        )
        self.assertEqual(amendment_issues(project), ())

        relax = Amendment(
            id="A2",
            title="Relax mass",
            rationale="TEST FIXTURE",
            files=rocket(limit=55),
        )
        relaxed = await project.sysml.amend(relax, actor="fixture")
        proposal = project.store.resolve(relaxed).data
        self.assertFalse(proposal["report"]["valid"])
        self.assertEqual(
            proposal["changes"]["requirements"], ["R1: mass <= 50 kg -> mass <= 55 kg"]
        )
        adopt = Candidate(id="adopt", description="Fixture", evidence=(relaxed,))
        with self.assertRaisesRegex(DecisionBlocked, "requirement records first"):
            await project.decisions.choose(
                choice(adopt), selected="adopt", explanation="Fixture"
            )
        with self.assertRaises(ModelRejected):
            await project.sysml.amend(
                Amendment(
                    id="A3",
                    title="Broken",
                    rationale="TEST FIXTURE",
                    files={"x.sysml": "package X { part y : ; }"},
                )
            )
        await project.sysml.amend(
            Amendment(
                id="A4",
                title="Withdraw A2",
                rationale="TEST FIXTURE",
                supersedes=("A2",),
            )
        )
        self.assertEqual(project.sysml.status("A2")[0], "superseded")
        self.assertEqual(project.sysml.status("A4")[0], "withdrawal")
        self.assertEqual(
            sorted(a["id"] for a in project.sysml.amendments()), ["A1", "A2"]
        )

    async def test_sysml_sources_are_ingested_as_text(self):
        path = Path(self.directory.name) / "existing.sysml"
        path.write_text(rocket()["rocket.sysml"])
        source = self.project.ingest(path)
        self.assertEqual(
            self.project.store.resolve(source).data["text"], rocket()["rocket.sysml"]
        )


@needs_library
class SystemsEngineerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_project_runs_a_systems_engineer(self):
        class Idle(TestReasoning):
            async def respond(self, packet):
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=Wait(reason="Fixture idle"),
                )

        # No systems_engineer argument: every project gets the default one.
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=Idle()) as project,
        ):
            self.assertIsInstance(project.systems_engineer, SystemsEngineer)
            result = await project.run(ProjectRequest(description="fixture"))
            run = project.store.get("run", result.run_id).data
            engineer = project.store.model("agent", run["engineer_id"], AgentSpec)
            self.assertEqual(engineer.task_id, "systems_engineer")
            self.assertEqual(engineer.objective, OBJECTIVE)

    async def test_engineer_records_requirements_in_one_turn_or_none(self):
        class Engineer(TestReasoning):
            def __init__(self):
                self.observations = []

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                if data["agent"]["task_id"] == "systems_engineer":
                    action = self.systems_engineer(data)
                else:
                    action = Wait(reason="Fixture idle")
                return AgentTurn(
                    rationale=Rationale(objective="Fixture", explanation="Fixture"),
                    action=action,
                )

            def systems_engineer(self, data):
                self.observations.append(data["state"]["last_observation"])
                if len(self.observations) > 2:
                    return Wait(reason="Fixture idle")
                brief = project.store.get("source", "brief").ref
                r2 = Requirement(
                    id="R2",
                    wording="fixture",
                    source=brief,
                    source_quote="TEST FIXTURE" if self.observations[1:] else "absent",
                )
                return Record(records=(requirement(brief), r2))

        engineer = Engineer()
        with (
            tempfile.TemporaryDirectory() as directory,
            Project(Path(directory), reasoning=engineer) as project,
        ):
            await project.run(
                ProjectRequest(
                    description=f"TEST FIXTURE. {WORDING}.",
                    context=ContextSpec(max_input_tokens=200_000),
                    budget=Budget(max_seconds=60),
                )
            )
            # A bad quote rejects the whole batch, naming the failing record.
            self.assertIn("R2", engineer.observations[1]["detail"])
            self.assertEqual(len(engineer.observations[2]["refs"]), 2)
            self.assertEqual(
                {s.ref.id: s.ref.revision for s in project.store.list("requirement")},
                {"R1": 1, "R2": 1},
            )

    async def test_systems_engineer_maintains_truth_beside_the_chief(self):
        rationale = Rationale(objective="Fixture", explanation="Fixture")

        class Team(TestReasoning):
            def __init__(self):
                self.steps = {}
                self.packets = {}
                self.rejected_draft = self.tried_finish = False

            async def respond(self, packet):
                data = json.loads(packet.prompt)
                task = data["agent"]["task_id"]
                count = self.steps.get(task, 0)
                self.steps[task] = count + 1
                self.packets.setdefault(task, []).append(data)
                action = getattr(self, task.lower())(data, count)
                if asyncio.iscoroutine(action):
                    action = await action
                return AgentTurn(rationale=rationale, action=action)

            def chief(self, data, count):
                store = project.store
                r1 = store.get("requirement", "R1").ref
                worker = TaskAuthorization(
                    id="W",
                    objective="Ask the systems engineer",
                    budget=Budget(max_seconds=60),
                )
                if count == 0:
                    return Record(record=requirement(store.get("source", "brief").ref))
                if count == 1:
                    return Decide(
                        selected="fixture", request=plan_request(r1, tasks=(worker,))
                    )
                if count == 2:
                    return Spawn(decision_id=data["agent"]["decision_id"], task_id="W")
                if count == 3:
                    return UpdateModel(
                        summary="Not mine", files=rocket(), derived_from=(r1,)
                    )
                return Wait(reason="Fixture finished")

            def systems_engineer(self, data, count):
                store = project.store
                r1 = store.maybe("requirement", "R1")
                if r1 is None:  # The engineer starts the project.
                    return Record(record=requirement(store.get("source", "brief").ref))
                if not self.rejected_draft:
                    self.rejected_draft = True
                    return UpdateModel(
                        summary="Draft",
                        files={"rocket.sysml": "package Rocket { part x : ; }"},
                        derived_from=(r1.ref,),
                    )
                if project.sysml.current() is None:
                    return UpdateModel(
                        summary="Initial model", files=rocket(), derived_from=(r1.ref,)
                    )
                if not self.tried_finish:
                    self.tried_finish = True
                    return Finish(
                        result=TaskReport(summary="Done").model_dump(mode="json")
                    )
                if data["messages"]:
                    return Acknowledge(message_ids=(data["messages"][0]["id"],))
                return Wait(reason="Model is current")

            def w(self, data, count):
                if count == 0:
                    engineer = next(
                        a
                        for a in data["state"]["agents"]
                        if a["task_id"] == "systems_engineer"
                    )
                    note = Note(text="Which mass bound applies?")
                    return Send(
                        recipient=engineer["id"], payload=note.model_dump(mode="json")
                    )
                return Finish(
                    result=TaskReport(summary="Asked").model_dump(mode="json")
                )

        team = Team()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Project(
                root / "state",
                sandbox=root / "out",
                reasoning=team,
                systems_engineer=SystemsEngineer(),
            ) as project:
                result = await project.run(
                    ProjectRequest(
                        description=f"TEST FIXTURE. {WORDING}.",
                        context=ContextSpec(max_input_tokens=200_000),
                        budget=Budget(max_seconds=120),
                    )
                )
                engineer = next(
                    s
                    for s in project.store.list("agent")
                    if s.data["task_id"] == "systems_engineer"
                )
                engineer_state = project.store.model(
                    "agent_state", engineer.ref.id, AgentState
                )
                self.assertFalse(
                    project.activity.get(engineer_state.request_id).required
                )
                [plan] = [
                    project.decisions.record(s.ref.id)
                    for s in project.store.list("decision")
                ]
                [question] = [
                    e
                    for e in project.inbox(engineer.ref.id)
                    if e.message.kind == "finding"
                ]
                project.human.interject(
                    "TEST FIXTURE correction", author="Fixture", run_id=result.run_id
                )
                redirected = project.store.model(
                    "agent_state", engineer.ref.id, AgentState
                )
                self.assertNotEqual(redirected.request_id, engineer_state.request_id)
                self.assertFalse(project.activity.get(redirected.request_id).required)

        engineer_packets, chief_packets = (
            team.packets["systems_engineer"],
            team.packets["chief"],
        )
        self.assertIn(
            "You are the Systems Engineer", engineer_packets[0]["instructions"]
        )
        self.assertIn("You are the Chief Engineer", chief_packets[0]["instructions"])
        observations = [p["state"]["last_observation"] for p in engineer_packets]
        # The draft was rejected with its full report; the valid model was recorded.
        rejection = next(o for o in observations if "report" in o)
        self.assertEqual(rejection["report"]["issues"][0]["code"], "syntax")
        # The chief starts once the engineer's model is valid, and cannot record
        # requirements itself.
        self.assertEqual(chief_packets[0]["state"]["system_model"]["status"], "valid")
        self.assertNotIn("files", chief_packets[0]["state"]["system_model"])
        self.assertIn(
            "Only the systems engineer records requirements",
            chief_packets[1]["state"]["last_observation"]["detail"],
        )
        self.assertEqual(
            engineer_packets[-1]["state"]["system_model"]["files"], rocket()
        )
        self.assertTrue(
            any("serves the whole run" in o.get("detail", "") for o in observations)
        )
        self.assertIn(
            "Only the systems engineer",
            chief_packets[4]["state"]["last_observation"]["detail"],
        )
        self.assertEqual(plan.model.revision, 1)
        # A worker reached the systems engineer directly, which acknowledged it.
        self.assertEqual(question.message.payload["text"], "Which mass bound applies?")
        self.assertIsNotNone(question.acknowledged_at)
        self.assertFalse(any("systems_engineer" in item for item in result.open_items))


def amendment_issues(project):
    """Review issues from amendments, apart from the unassessed requirements."""
    return tuple(i for i in project.sysml.review_issues() if i.startswith("Amendment"))


if __name__ == "__main__":
    unittest.main()
