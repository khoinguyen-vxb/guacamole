"""Validate and record explicit engineering choices and their input revisions."""

from graphlib import TopologicalSorter
from typing import TYPE_CHECKING

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
        candidates, references = [], list(self.project.human.references(run_id))
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
        if selected not in {candidate.id for candidate in candidates}:
            activity.transition(
                record.id,
                "blocked",
                actor="runtime",
                reason="Selected candidate is unknown or ineligible",
            )
            raise DecisionBlocked("Selected candidate is unknown or ineligible")
        try:
            # No external invocation: validation and recording have no async gap.
            with store.atomic():
                snapshots: dict[Ref, ReferencedData] = {}
                pending = list(references)
                while pending:
                    ref = pending.pop()
                    if ref not in snapshots:
                        snapshot = store.resolve(ref, current=True)
                        snapshots[ref] = ReferencedData(ref=ref, content=snapshot.data)
                        pending.extend(snapshot.dependencies)
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
                            "context": tuple(snapshots.values()),
                        }
                    ),
                    result=result,
                    author=actor,
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
            return record.id
        except (ValueError, KeyError) as exc:
            activity.transition(
                record.id,
                "blocked",
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
