"""Validate and record explicit engineering choices and their input revisions."""

from graphlib import TopologicalSorter
from typing import TYPE_CHECKING

from .agents.systems_engineer import TASK_ID as ENGINEER
from .contracts import (
    Candidate,
    DecisionRecord,
    DecisionRequest,
    DecisionResult,
    Ref,
    RequestRecord,
    WorkPlan,
)

if TYPE_CHECKING:
    from .project import Project
    from .storage import Snapshot


class DecisionBlocked(RuntimeError):
    pass


class Decisions:
    def __init__(self, project: "Project") -> None:
        self.project = project

    def validate_plan(self, plan: WorkPlan) -> None:
        tasks = {t.id: t for t in plan.tasks}
        if len(tasks) != len(plan.tasks):
            raise ValueError("Task IDs must be unique")
        if len({d.id for d in plan.deliverables}) != len(plan.deliverables):
            raise ValueError("Deliverable IDs must be unique")
        for task in plan.tasks:
            # Workers can always message the root agents, so their grants are no-ops.
            unknown = (
                set(task.depends_on) | (set(task.peers) - {"chief", ENGINEER})
            ) - tasks.keys()
            if unknown:
                raise ValueError(
                    f"Task {task.id} names unknown dependencies or peers: {sorted(unknown)}"
                )
            if task.result_schema not in self.project.tools.schemas:
                raise ValueError("Unknown task result schema")
            if task.tier is not None and task.tier not in self.project.tiers:
                raise ValueError(
                    f"Task {task.id} names an unconfigured reasoning tier: {task.tier}"
                )
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
        listed = self.project.store.list("requirement")
        required = {s.ref.id for s in listed if not s.data.get("withdrawn")}
        if not required or not required <= covered:
            raise ValueError("Every current requirement needs a deliverable allocation")
        if withdrawn := covered & {s.ref.id for s in listed if s.data.get("withdrawn")}:
            raise ValueError(
                f"Withdrawn requirements need no work: {sorted(withdrawn)}"
            )
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
        self,
        candidate: Candidate,
        request: DecisionRequest,
        model: "Snapshot | None" = None,
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
        if model is not None:
            self.project.sysml.check(candidate, model)
        return refs

    async def choose(
        self,
        request: DecisionRequest,
        *,
        selected: str,
        explanation: str,
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
                target="runtime",
                arguments={
                    "request": request.model_dump(mode="json"),
                    "selected": selected,
                    "explanation": explanation,
                },
                purpose=request.question,
                parent_id=parent_id,
                rationale_id=rationale_id,
                packet_id=packet_id,
                required=False,
            )
        )
        try:
            # The authoritative SysML model must be usable before any choice.
            model = self.project.sysml.gate()
        except DecisionBlocked as exc:
            activity.transition(record.id, "failed", actor="runtime", reason=str(exc))
            raise
        candidates, references = [], list(self.project.human.references(run_id))
        rejected: dict[str, str] = {}
        for candidate in request.candidates:
            try:
                references.extend(self._eligible(candidate, request, model))
                candidates.append(candidate)
            except (ValueError, KeyError) as exc:
                rejected[candidate.id] = str(exc)
                store.event(
                    "runtime",
                    "decision.candidate_rejected",
                    candidate.id,
                    {"reason": str(exc)},
                    request_id=record.id,
                )
        if selected not in {candidate.id for candidate in candidates}:
            # The Chief can only correct a plan if it sees why the plan was rejected.
            reason = "Selected candidate is unknown or ineligible: " + rejected.get(
                selected, "no candidate has this id"
            )
            activity.transition(record.id, "failed", actor="runtime", reason=reason)
            raise DecisionBlocked(reason)
        try:
            # No external invocation: validation and recording have no async gap.
            with store.atomic():
                context: dict[Ref, None] = {}
                pending = list(references)
                while pending:
                    ref = pending.pop()
                    if ref not in context:
                        context[ref] = None
                        pending.extend(store.resolve(ref, current=True).dependencies)
                result = DecisionResult(
                    request_id=record.id,
                    selected=selected,
                    explanation=explanation,
                    evidence=tuple(dict.fromkeys(references)),
                )
                decision = DecisionRecord(
                    request=request.model_copy(
                        update={
                            "candidates": tuple(candidates),
                            "context": tuple(context),
                        }
                    ),
                    result=result,
                    author=actor,
                    model=model.ref if model is not None else None,
                )
                store.put(
                    "decision",
                    record.id,
                    decision,
                    actor=actor,
                    dependencies=result.evidence,
                    request_id=record.id,
                )
                activity.transition(
                    record.id,
                    "completed",
                    actor="runtime",
                    result=result.model_dump(mode="json"),
                )
                # This choice corrects the requester's rejected ones; the Chief spent
                # turns trying to settle them by hand.
                for failed in activity.requests(status="failed"):
                    if (
                        failed.kind == "decision"
                        and failed.requester == actor
                        and failed.parent_id == parent_id
                    ):
                        activity.supersede(
                            failed.id,
                            by=record.id,
                            actor=actor,
                            reason="A later decision by the same requester completed",
                        )
            return record.id
        except (ValueError, KeyError) as exc:
            activity.transition(
                record.id,
                "failed",
                actor="runtime",
                reason="Invalid choice or stale decision inputs",
            )
            raise DecisionBlocked("Invalid choice or stale decision inputs") from exc

    def record(self, id: str) -> DecisionRecord:
        snapshot = self.project.store.get("decision", id)
        self.project.store.resolve(snapshot.ref, current=True)
        return self.project.store.model("decision", id, DecisionRecord)

    def plan(self, id: str) -> WorkPlan:
        decision = self.record(id)
        candidate = next(
            c for c in decision.request.candidates if c.id == decision.result.selected
        )
        if decision.request.kind != "work_plan" or candidate.plan is None:
            raise DecisionBlocked("A work-plan decision is required")
        self.validate_plan(candidate.plan)
        return candidate.plan
