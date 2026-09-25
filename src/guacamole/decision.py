"""Mandatory Jev boundary with deterministic eligibility and freshness gates."""

import asyncio
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, Protocol

from .contracts import (
    Candidate,
    DecisionRecord,
    DecisionRequest,
    DecisionResult,
    Ref,
    ReferencedData,
    RequestRecord,
    WorkPlan,
)

if TYPE_CHECKING:
    from .project import Project


class JevProvider(Protocol):
    name: str
    version: str
    is_test_double: bool

    async def decide(
        self, request_id: str, request: DecisionRequest
    ) -> DecisionResult: ...


class DecisionBlocked(RuntimeError):
    pass


class Decisions:
    def __init__(self, project: "Project", provider: JevProvider | None) -> None:
        self.project, self.provider = project, provider

    def validate_plan(self, plan: WorkPlan) -> None:
        tasks = {t.id: t for t in plan.tasks}
        if len(tasks) != len(plan.tasks):
            raise ValueError("Task IDs must be unique")
        if len({d.id for d in plan.deliverables}) != len(plan.deliverables):
            raise ValueError("Deliverable IDs must be unique")
        for task in plan.tasks:
            if not set(task.depends_on + task.peers) <= tasks.keys():
                raise ValueError("Unknown task dependency or peer grant")
            if task.result_schema not in self.project.tools.schemas:
                raise ValueError("Unknown task result schema")
        tuple(
            TopologicalSorter({t.id: t.depends_on for t in plan.tasks}).static_order()
        )
        for grant in (
            *plan.chief_tools,
            *(g for t in plan.tasks for g in t.tools),
            *(g for d in plan.deliverables for g in d.required_tools),
        ):
            self.project.tools.get(grant)
        if any(d.stage != plan.stage for d in plan.deliverables):
            raise ValueError("Deliverable review stage differs from work plan")
        covered = {r.id for d in plan.deliverables for r in d.requirements}
        required = {s.ref.id for s in self.project.store.list("requirement")}
        if not required or not required <= covered:
            raise ValueError("Every current requirement needs a deliverable allocation")
        for ref in (
            *plan.inputs,
            *(r for d in plan.deliverables for r in d.requirements),
        ):
            self.project.store.resolve(ref, current=True)
        if plan.stage == "CDR" and not self.project.reviews.accepted("PDR"):
            raise ValueError(
                "Detailed design requires a current human-accepted PDR baseline"
            )

    def _eligible(
        self, candidate: Candidate, request: DecisionRequest
    ) -> tuple[Ref, ...]:
        if request.kind == "work_plan":
            if candidate.plan is None:
                raise ValueError("Work-plan candidate lacks a typed plan")
            self.validate_plan(candidate.plan)
        elif candidate.plan is not None:
            raise ValueError("Plans must be selected as work-plan decisions")
        for constraint in request.constraints:
            metric = candidate.metrics.get(constraint.metric)
            if metric is None or metric.unit != constraint.unit:
                raise ValueError("Missing metric or incompatible units")
            if constraint.minimum is not None and metric.value < constraint.minimum:
                raise ValueError("Candidate violates lower constraint")
            if constraint.maximum is not None and metric.value > constraint.maximum:
                raise ValueError("Candidate violates upper constraint")
        refs = (*request.evidence, *candidate.evidence)
        if candidate.plan:
            refs += (
                *candidate.plan.inputs,
                *(r for d in candidate.plan.deliverables for r in d.requirements),
            )
            if candidate.plan.stage == "CDR":
                refs += self.project.reviews.accepted("PDR")
        for ref in refs:
            self.project.store.resolve(ref, current=True)
        return refs

    async def choose(
        self,
        request: DecisionRequest,
        *,
        actor: str = "script",
        run_id: str = "script",
        parent_id: str | None = None,
        rationale_id: str | None = None,
        packet_id: str | None = None,
    ) -> str:
        request = DecisionRequest.model_validate(request)
        if len({c.id for c in request.candidates}) != len(request.candidates):
            raise ValueError("Candidate IDs must be unique")
        activity, store = self.project.activity, self.project.store
        record = activity.request(
            RequestRecord(
                kind="decision",
                run_id=run_id,
                requester=actor,
                target="Jev",
                arguments=request.model_dump(mode="json"),
                purpose=request.question,
                parent_id=parent_id,
                rationale_id=rationale_id,
                packet_id=packet_id,
                required=False,
            )
        )
        if self.provider is None:
            activity.transition(
                record.id,
                "blocked",
                actor="runtime",
                reason="A configured Jev provider is mandatory",
            )
            raise DecisionBlocked("A configured Jev provider is mandatory")
        candidates, references = [], []
        for candidate in request.candidates:
            try:
                references.extend(self._eligible(candidate, request))
                candidates.append(candidate)
            except (ValueError, KeyError) as exc:
                store.event(
                    "runtime",
                    "decision.candidate_rejected",
                    candidate.id,
                    {"reason": str(exc)},
                    request_id=record.id,
                )
        if not candidates:
            activity.transition(
                record.id,
                "blocked",
                actor="runtime",
                reason="No deterministically eligible candidates",
            )
            raise DecisionBlocked("No deterministically eligible candidates")
        snapshots: dict[Ref, ReferencedData] = {}
        pending = list(references)
        while pending:
            ref = pending.pop()
            if ref not in snapshots:
                snapshot = store.resolve(ref, current=True)
                snapshots[ref] = ReferencedData(ref=ref, content=snapshot.data)
                pending.extend(snapshot.dependencies)
        eligible = request.model_copy(
            update={
                "candidates": tuple(candidates),
                "context": tuple(snapshots.values()),
            }
        )
        store.put(
            "decision_input",
            record.id,
            eligible,
            actor=actor,
            dependencies=tuple(references),
            request_id=record.id,
        )
        activity.transition(record.id, "dispatched", actor="runtime")
        activity.transition(record.id, "running", actor="runtime")
        try:
            result = DecisionResult.model_validate(
                await self.provider.decide(
                    record.id,
                    DecisionRequest.model_validate_json(eligible.model_dump_json()),
                )
            )
            store.put(
                "decision_response",
                record.id,
                result,
                actor="Jev",
                request_id=record.id,
                event="decision.responded",
            )
            valid = result.request_id == record.id and result.selected in {
                c.id for c in candidates
            }
            for ref in (*references, *result.evidence):
                store.resolve(ref, current=True)
            decision = DecisionRecord(
                request=eligible,
                result=result,
                provider=self.provider.name,
                version=self.provider.version,
                is_test_double=self.provider.is_test_double,
                accepted=valid,
            )
            with store.atomic():
                store.put(
                    "decision",
                    record.id,
                    decision,
                    actor="Jev",
                    dependencies=(*references, *result.evidence),
                    request_id=record.id,
                )
                activity.transition(
                    record.id,
                    "completed" if valid else "blocked",
                    actor="runtime",
                    result=result.model_dump(mode="json"),
                    reason=None
                    if valid
                    else "Jev abstained or returned an invalid selection",
                )
            if not valid:
                raise DecisionBlocked("Jev abstained or returned an invalid selection")
            return record.id
        except DecisionBlocked:
            raise
        except asyncio.CancelledError:
            activity.transition(
                record.id,
                "uncertain",
                actor="runtime",
                reason="Jev invocation interrupted before a recorded outcome",
            )
            raise
        except Exception as exc:
            activity.transition(
                record.id,
                "failed",
                actor="runtime",
                reason=f"{type(exc).__name__}; Jev result unavailable or invalid; error detail omitted",
            )
            raise DecisionBlocked("Jev failed; dependent work is blocked") from exc

    def record(self, id: str) -> DecisionRecord:
        snapshot = self.project.store.get("decision", id)
        self.project.store.resolve(snapshot.ref, current=True)
        decision = self.project.store.model("decision", id, DecisionRecord)
        if not decision.accepted:
            raise DecisionBlocked("Decision does not authorize execution")
        return decision

    def plan(self, id: str) -> WorkPlan:
        decision = self.record(id)
        candidate = next(
            c for c in decision.request.candidates if c.id == decision.result.selected
        )
        if decision.request.kind != "work_plan" or candidate.plan is None:
            raise DecisionBlocked("A work-plan decision is required")
        self.validate_plan(candidate.plan)
        return candidate.plan
