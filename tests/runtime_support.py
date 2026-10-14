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
from guacamole.contracts import AgentTurn, Decide, Rationale, UpdateModel, Wait

FIXTURE = Rationale(objective="TEST FIXTURE", explanation="Scripted fixture turn")


class TestReasoning:
    """Every project runs a Systems Engineer. Unless a fixture scripts one itself (a
    systems_engineer attribute), its packets get fixture_model turns, and the chief's
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

    async def count_tokens(self, prompt):
        # Exact count for this fake provider's one-byte token alphabet.
        return len(prompt.encode())


def _revision(model):
    return model["ref"]["revision"] if "ref" in model else 0


def _engineer_turn(provider, data):
    model = data["state"]["system_model"]
    if model["status"] == "valid":
        provider._validated = max(getattr(provider, "_validated", 0), _revision(model))
        _validation_event(provider).set()
        return AgentTurn(rationale=FIXTURE, action=Wait(reason="Model is current"))
    records = [
        s
        for s in data["sources"]
        if s["ref"]["kind"] == "requirement" and not s["stale"]
    ]
    # Idle until a requirement exists: a first model would wake a waiting chief.
    if not records:
        return AgentTurn(rationale=FIXTURE, action=Wait(reason="Await requirements"))
    return AgentTurn(
        rationale=FIXTURE,
        action=UpdateModel(
            summary="TEST FIXTURE model of every recorded requirement",
            files=fixture_model(
                Requirement.model_validate_json(json.dumps(s["data"])) for s in records
            ),
            derived_from=tuple(s["ref"] for s in records),
        ),
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
                f"s.'{c.metric}' {op} {value:g} [{c.unit}]"
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
    records = [s for s in project.store.list("requirement") if not s.stale]
    await project.sysml.commit(
        summary="TEST FIXTURE model of every recorded requirement",
        files=fixture_model(
            project.store.model("requirement", s.ref.id, Requirement) for s in records
        ),
        derived_from=tuple(s.ref for s in records)
        or (project.store.list("source")[0].ref,),
    )
