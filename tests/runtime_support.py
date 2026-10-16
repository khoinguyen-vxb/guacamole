"""Labelled reasoning fixtures; they provide no engineering performance evidence."""

import asyncio
import functools
import json

from guacamole import (
    Candidate,
    DecisionRequest,
    DeliverableSpec,
    Requirement,
    WorkPlan,
)
from guacamole.contracts import (
    AgentTurn,
    Decide,
    Evidence,
    Note,
    Rationale,
    Record,
    RequestRecord,
    Send,
    UpdateModel,
    VerificationResult,
    Wait,
)

FIXTURE = Rationale(objective="TEST FIXTURE", explanation="Scripted fixture turn")


class TestReasoning:
    """Every project starts with a Systems Engineer. Unless a fixture scripts one itself
    (a systems_engineer attribute), it records what the fixture's requirements() lists,
    commits fixture_model of them, then replies to each agent's message; the chief's
    decisions wait until the engineer has seen that model validated."""

    name = "test-double-reasoning"
    model = "scripted-fixture"
    context_capacity_tokens = 500_000

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        respond = cls.__dict__.get("respond")
        if respond is None or hasattr(cls, "systems_engineer"):
            return

        @functools.wraps(respond)
        async def wrapped(self, packet):
            data = json.loads(packet.prompt)
            if data["agent"]["task_id"] == "systems_engineer":
                return _engineer_turn(self, data)
            turn = await respond(self, packet)
            if data["agent"]["task_id"] == "chief" and isinstance(turn.action, Decide):
                await _model_validated(self, data["state"]["system_model"])
            return turn

        cls.respond = wrapped

    def requirements(self):
        """Requirements the fixture's engineer records; read again on every turn."""
        return ()

    async def count_tokens(self, prompt):
        # Exact count for this fake provider's one-byte token alphabet.
        return len(prompt.encode())


def _revision(model):
    return model["ref"]["revision"] if "ref" in model else 0


def _engineer_turn(provider, data):
    records = [
        s
        for s in data["sources"]
        if s["ref"]["kind"] == "requirement" and not s["stale"]
    ]
    recorded = {s["ref"]["id"] for s in records}
    if wanted := [r for r in provider.requirements() if r.id not in recorded]:
        return AgentTurn(rationale=FIXTURE, action=Record(records=tuple(wanted)))
    model = data["state"]["system_model"]
    if model["status"] != "valid":
        brief = next(
            s["ref"]
            for s in data["sources"]
            if s["ref"]["kind"] == "source" and s["ref"]["id"] == "brief"
        )
        return AgentTurn(
            rationale=FIXTURE,
            action=UpdateModel(
                summary="TEST FIXTURE model of every recorded requirement",
                files=fixture_model(
                    Requirement.model_validate_json(json.dumps(s["data"]))
                    for s in records
                ),
                derived_from=tuple(s["ref"] for s in records) or (brief,),
            ),
        )
    provider._validated = max(getattr(provider, "_validated", 0), _revision(model))
    _validation_event(provider).set()
    agents = {a["id"] for a in data["state"]["agents"]}
    # A reply wakes its asker even mid-turn, which a model commit alone does not.
    if asked := [m for m in data["messages"] if m["sender"] in agents]:
        return AgentTurn(
            rationale=FIXTURE,
            action=Send(
                recipient=asked[0]["sender"],
                payload=Note(text="TEST FIXTURE: the model is current").model_dump(
                    mode="json"
                ),
                reply_to=asked[0]["id"],
            ),
        )
    return AgentTurn(rationale=FIXTURE, action=Wait(reason="Model is current"))


def fixture_requirement(project, id="r"):
    """TEST FIXTURE: one requirement on the brief, for TestReasoning.requirements."""
    source = project.store.list("source")[0].ref
    return (
        Requirement(id=id, wording="fixture", source=source, source_quote="fixture"),
    )


def to_engineer(data, text="TEST FIXTURE request"):
    """A message that wakes the fixture's systems engineer."""
    engineer = next(
        a for a in data["state"]["agents"] if a["task_id"] == "systems_engineer"
    )
    return Send(
        recipient=engineer["id"], payload=Note(text=text).model_dump(mode="json")
    )


def _validation_event(provider):
    if getattr(provider, "_validation", None) is None:
        provider._validation = asyncio.Event()
    return provider._validation


async def _model_validated(provider, model, timeout=30):
    """Wait until the engineer has seen a newer valid revision than the chief saw."""
    if model["status"] == "valid":
        return
    seen, event = _revision(model), _validation_event(provider)
    async with asyncio.timeout(timeout):
        while getattr(provider, "_validated", 0) <= seen:
            event.clear()
            await event.wait()


def _quantity(value, unit):
    return f"{value:g}" + (f" [{unit}]" if unit else "")


def fixture_model(requirements):
    """TEST FIXTURE: a SysML v2 model of each requirement, not an engineering design."""
    subjects, body = [], []
    for n, record in enumerate(requirements):
        body += [
            f"  requirement <'{record.id}'> r{n} {{",
            f"    doc /* {record.wording} */",
        ]
        if (c := record.constraint) is not None:
            subjects.append(f"  part def S{n} {{ attribute '{c.metric}'; }}")
            bounds = [
                f"s.'{c.metric}' {op} {_quantity(value, c.unit)}"
                for op, value in ((">=", c.minimum), ("<=", c.maximum))
                if value is not None
            ]
            body += [
                f"    subject s : S{n};",
                f"    require constraint {{ {' and '.join(bounds)} }}",
            ]
        body.append("  }")
    lines = ["package Fixture {", "  private import ISQ::*;", "  private import SI::*;"]
    return {"fixture.sysml": "\n".join([*lines, *subjects, *body, "}"]) + "\n"}


def plan_request(requirement, *more, stage="PDR", tools=(), tasks=()):
    return DecisionRequest(
        question="Select a fixture work plan",
        kind="work_plan",
        criteria=("Typed fixture coverage",),
        candidates=(
            Candidate(
                id="fixture",
                description="TEST ONLY",
                plan=WorkPlan(
                    stage=stage,
                    inputs=(requirement, *more),
                    chief_tools=tools,
                    tasks=tasks,
                    deliverables=(
                        DeliverableSpec(
                            id=stage + "-design",
                            title="Fixture",
                            stage=stage,
                            requirements=(requirement, *more),
                            artifact_kinds=("editable-design",),
                            evidence_kinds=("verification",),
                            acceptance_criteria=(
                                "Fixture file has the required value",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def engineer_id(project):
    """The Systems Engineer every run starts beside the chief."""
    return next(
        s.ref.id
        for s in project.store.list("agent")
        if s.data["task_id"] == "systems_engineer"
    )


async def commit_fixture_model(project):
    """Commit fixture_model of the current requirements, as scripts deciding need."""
    records = project.sysml.requirements()
    await project.sysml.commit(
        summary="TEST FIXTURE model of every recorded requirement",
        files=fixture_model(
            project.store.model("requirement", s.ref.id, Requirement) for s in records
        ),
        derived_from=tuple(s.ref for s in records)
        or (project.store.list("source")[0].ref,),
    )


def passed_evidence(project, requirements, measurements, id="fixture-evidence"):
    """TEST FIXTURE: passed evidence of a scripted check, for assessments to cite."""
    activity = project.activity
    request = activity.request(
        RequestRecord(
            run_id="script",
            requester="fixture",
            target="fixture-check",
            kind="tool",
            arguments={},
            purpose="TEST FIXTURE check",
        )
    )
    activity.transition(request.id, "dispatched", actor="fixture")
    activity.transition(request.id, "running", actor="fixture")
    result = VerificationResult(
        outcome="passed",
        explanation="TEST FIXTURE",
        checks={"fixture": True},
        measurements=measurements,
    )
    activity.transition(
        request.id, "completed", actor="fixture", result=result.model_dump(mode="json")
    )
    evidence = Evidence(
        id=id,
        kind="verification",
        outcome="passed",
        explanation="TEST FIXTURE",
        artifacts=(),
        requirements=tuple(requirements),
        request_id=request.id,
        decision_id="fixture",
    )
    return project.store.put(
        "evidence", id, evidence, actor="fixture", dependencies=tuple(requirements)
    )
