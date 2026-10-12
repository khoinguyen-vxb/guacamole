import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from runtime_support import TestReasoning, plan_request

from guacamole import (
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
from guacamole.contracts import (
    Acknowledge,
    AgentState,
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
        model, invalidated = await project.sysml.commit(
            summary="Fixture", files=rocket(), derived_from=(self.brief, self.r1)
        )
        self.assertEqual((model.revision, invalidated), (1, {}))
        exported = project.sandbox / "sysml"
        self.assertEqual(
            (exported / "rocket.sysml").read_text(), rocket()["rocket.sysml"]
        )
        self.assertEqual(
            json.loads((exported / "report.json").read_text())["ref"]["revision"], 1
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
        with self.assertRaisesRegex(DecisionBlocked, "stale"):
            await project.decisions.choose(motors, selected="A", explanation="Fixture")
        self.assertTrue(project.sysml.review_issues())

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
            project.sysml.review_issues(),
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
        self.assertEqual(project.sysml.review_issues(), ())

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


class SystemsEngineerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_systems_engineer_maintains_truth_beside_the_chief(self):
        rationale = Rationale(objective="Fixture", explanation="Fixture")
        chief_blocked = asyncio.Event()

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
                if count == 0:
                    return Record(record=requirement(store.get("source", "brief").ref))
                r1 = store.get("requirement", "R1").ref
                worker = TaskAuthorization(
                    id="W",
                    objective="Ask the systems engineer",
                    budget=Budget(max_seconds=60),
                )
                if count in (1, 3):  # Before and after the model exists.
                    return Decide(
                        selected="fixture", request=plan_request(r1, tasks=(worker,))
                    )
                if count == 2:
                    chief_blocked.set()
                    return Wait(reason="Await the SysML model")
                if count == 4:
                    return Spawn(decision_id=data["agent"]["decision_id"], task_id="W")
                if count == 5:
                    return UpdateModel(
                        summary="Not mine", files=rocket(), derived_from=(r1,)
                    )
                return Wait(reason="Fixture finished")

            async def systems_engineer(self, data, count):
                store = project.store
                r1 = store.maybe("requirement", "R1")
                if r1 is None:
                    return Wait(reason="Await requirements")
                if not self.rejected_draft:
                    self.rejected_draft = True
                    return UpdateModel(
                        summary="Draft",
                        files={"rocket.sysml": "package Rocket { part x : ; }"},
                        derived_from=(r1.ref,),
                    )
                if project.sysml.current() is None:
                    await asyncio.wait_for(chief_blocked.wait(), 10)
                    return UpdateModel(
                        summary="Initial model", files=rocket(), derived_from=(r1.ref,)
                    )
                if not self.tried_finish:
                    self.tried_finish = True
                    return Finish(
                        result=TaskReport(summary="Done").model_dump(mode="json")
                    )
                if data["messages"]:
                    return Acknowledge(message_id=data["messages"][0]["id"])
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
        self.assertIn(
            "No SysML model yet",
            chief_packets[2]["state"]["last_observation"]["detail"],
        )
        self.assertEqual(chief_packets[3]["state"]["system_model"]["status"], "valid")
        self.assertNotIn("files", chief_packets[3]["state"]["system_model"])
        self.assertEqual(
            engineer_packets[-1]["state"]["system_model"]["files"], rocket()
        )
        self.assertTrue(
            any("serves the whole run" in o.get("detail", "") for o in observations)
        )
        self.assertIn(
            "Only the systems engineer",
            chief_packets[6]["state"]["last_observation"]["detail"],
        )
        self.assertEqual(plan.model.revision, 1)
        # A worker reached the systems engineer directly, which acknowledged it.
        self.assertEqual(question.message.payload["text"], "Which mass bound applies?")
        self.assertIsNotNone(question.acknowledged_at)
        self.assertFalse(any("systems_engineer" in item for item in result.open_items))


if __name__ == "__main__":
    unittest.main()
