"""Versioned deliverables, deterministic readiness, Jev, then human disposition."""

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from .contracts import (
    ArtifactRecord,
    Candidate,
    DecisionRequest,
    Deliverable,
    Evidence,
    OpenItem,
    Ref,
    Requirement,
    ReviewManifest,
    ReviewStage,
)
from .tools.registry import encode

if TYPE_CHECKING:
    from .project import Project


class Reviews:
    def __init__(self, project: "Project") -> None:
        self.project = project

    def accepted(self, stage: ReviewStage) -> tuple[Ref, ...]:
        store = self.project.store
        accepted = []
        for snapshot in store.list("review"):
            if (
                snapshot.stale
                or snapshot.data["stage"] != stage
                or snapshot.data["status"] != "accepted"
            ):
                continue
            manifest = ReviewManifest.model_validate_json(encode(snapshot.data))
            try:
                for ref in manifest.baseline:
                    store.resolve(ref, current=True)
                _, current, issues = self.checks(manifest.plan_decision)
                if not issues and current == manifest.baseline:
                    accepted.append(snapshot.ref)
            except (ValueError, KeyError, RuntimeError):
                continue
        return tuple(accepted)

    def checks(
        self, plan_decision: str
    ) -> tuple[tuple[Deliverable, ...], tuple[Ref, ...], tuple[str, ...]]:
        store = self.project.store
        plan = self.project.decisions.plan(plan_decision)
        issues: list[str] = []
        baseline: list[Ref] = [store.get("decision", plan_decision).ref]
        baseline.extend(s.ref for s in store.list("requirement"))
        for requirement in store.list("requirement"):
            record = Requirement.model_validate_json(encode(requirement.data))
            issues.extend(
                f"{requirement.ref.id}: unresolved input {unknown}"
                for unknown in record.unknowns
            )
        deliverables: list[Deliverable] = []
        for spec in plan.deliverables:
            for grant in spec.required_tools:
                try:
                    self.project.tools.get(grant)
                except KeyError:
                    issues.append(f"{spec.id}: missing tool {grant.key}")
            snapshot = store.maybe("deliverable", spec.id)
            if snapshot is None:
                issues.append(f"{spec.id}: missing deliverable")
                continue
            deliverable = Deliverable.model_validate_json(encode(snapshot.data))
            deliverables.append(deliverable)
            refs = (snapshot.ref, *deliverable.artifacts, *deliverable.evidence)
            kinds: set[str] = set()
            evidence_kinds: set[str] = set()
            covered: set[str] = set()
            for ref in refs:
                try:
                    store.resolve(ref, current=True)
                    if ref.kind == "artifact":
                        artifact = store.model("artifact", ref.id, ArtifactRecord)
                        self.project.verify_file(artifact.file)
                        kinds.add(artifact.kind)
                        covered.update(r.id for r in artifact.requirements)
                    elif ref.kind == "evidence":
                        evidence = store.model("evidence", ref.id, Evidence)
                        if evidence.outcome == "passed":
                            evidence_kinds.add(evidence.kind)
                        else:
                            issues.append(
                                f"{spec.id}: {evidence.kind} is {evidence.outcome}"
                            )
                except (ValueError, KeyError, OSError):
                    issues.append(
                        f"{spec.id}: missing, changed, or stale {ref.kind}:{ref.id}"
                    )
            if not set(spec.artifact_kinds) <= kinds:
                issues.append(
                    f"{spec.id}: missing artifact kinds {sorted(set(spec.artifact_kinds) - kinds)}"
                )
            if not set(spec.evidence_kinds) <= evidence_kinds:
                issues.append(
                    f"{spec.id}: missing verification {sorted(set(spec.evidence_kinds) - evidence_kinds)}"
                )
            if not {r.id for r in spec.requirements} <= covered:
                issues.append(f"{spec.id}: incomplete requirement traceability")
            baseline.extend(refs)
        for snapshot in store.list("open_item"):
            item = OpenItem.model_validate_json(encode(snapshot.data))
            baseline.append(snapshot.ref)
            if plan.stage in item.blocking_stages and (
                not item.resolved_by or snapshot.stale
            ):
                issues.append(f"{item.id}: {item.description}")
        for request in self.project.activity.requests(decision=plan_decision):
            if request.required and request.status not in {"completed", "cancelled"}:
                issues.append(f"Request {request.id}: {request.status}")
        unique = tuple({(r.kind, r.id, r.revision): r for r in baseline}.values())
        return tuple(deliverables), unique, tuple(issues)

    async def generate(
        self,
        plan_decision: str,
        *,
        actor: str = "script",
        run_id: str = "script",
        parent_id: str | None = None,
        rationale_id: str | None = None,
        packet_id: str | None = None,
    ) -> Ref:
        store = self.project.store
        plan = self.project.decisions.plan(plan_decision)
        deliverables, baseline, issues = self.checks(plan_decision)
        manifest = ReviewManifest(
            stage=plan.stage,
            plan_decision=plan_decision,
            baseline=baseline,
            deliverables=deliverables,
            open_items=issues,
            test_only=self.project.decisions.record(plan_decision).is_test_double,
        )
        ref = store.put(
            "review",
            manifest.id,
            manifest,
            actor=actor,
            dependencies=tuple(r for r in baseline if not store.resolve(r).stale),
            event="review.generated",
        )
        self._export(manifest)
        if issues:
            return ref
        decision_id = await self.project.decisions.choose(
            DecisionRequest(
                question=f"Is this exact {plan.stage} baseline ready for human review?",
                kind="review",
                candidates=(
                    Candidate(
                        id="ready",
                        description="Recommend the recorded baseline for human review",
                        evidence=baseline,
                    ),
                ),
                evidence=baseline,
                criteria=tuple(
                    c for d in plan.deliverables for c in d.acceptance_criteria
                ),
            ),
            actor=actor,
            run_id=run_id,
            parent_id=parent_id,
            rationale_id=rationale_id,
            packet_id=packet_id,
        )
        # Recheck after provider latency; a decision cannot legitimize stale evidence.
        _, current, issues = self.checks(plan_decision)
        if issues or current != baseline:
            raise ValueError("Baseline changed during readiness evaluation")
        manifest = manifest.model_copy(
            update={"status": "ready", "readiness_decision": decision_id}
        )
        ref = store.put(
            "review",
            manifest.id,
            manifest,
            actor="runtime",
            dependencies=(*baseline, store.get("decision", decision_id).ref),
            event="review.ready",
        )
        self._export(manifest)
        return ref

    def accept(
        self, ref: Ref, *, reviewer: str, disposition: str, accepted: bool = True
    ) -> Ref:
        if ref.kind != "review" or not reviewer.strip() or not disposition.strip():
            raise ValueError(
                "An exact review revision, reviewer, and disposition are required"
            )
        store = self.project.store
        snapshot = store.resolve(ref, current=True)
        manifest = ReviewManifest.model_validate_json(encode(snapshot.data))
        if manifest.status != "ready" or manifest.readiness_decision is None:
            raise ValueError("Only a ready baseline can receive human disposition")
        self.project.decisions.record(manifest.readiness_decision)
        _, baseline, issues = self.checks(manifest.plan_decision)
        if issues or baseline != manifest.baseline:
            raise ValueError("Review baseline is no longer current or complete")
        changed = manifest.model_copy(
            update={
                "status": "accepted" if accepted else "rejected",
                "human": reviewer,
                "disposition": disposition,
            }
        )
        ref = store.put(
            "review",
            manifest.id,
            changed,
            actor=f"human:{reviewer}",
            dependencies=snapshot.dependencies,
            event=f"review.{changed.status}",
        )
        self._export(changed)
        return ref

    def _export(self, manifest: ReviewManifest) -> Path:
        output = self.project.output_path
        directory = output(Path("reviews") / manifest.id)
        directory.mkdir(parents=True, exist_ok=True)
        revision = self.project.store.get("review", manifest.id).ref.revision
        path = output(directory / f"manifest-v{revision}.json")
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        package = output(directory / f"v{revision}")
        package.mkdir(exist_ok=True)
        records = [
            self.project.store.resolve(ref).model_dump(mode="json")
            for ref in manifest.baseline
        ]
        output(package / "records.json").write_text(encode(records), encoding="utf-8")
        artifacts = []
        for deliverable in manifest.deliverables:
            for ref in deliverable.artifacts:
                artifact = ArtifactRecord.model_validate_json(
                    encode(self.project.store.resolve(ref).data)
                )
                try:
                    source = self.project.verify_file(artifact.file)
                except (OSError, ValueError):
                    continue  # The generated manifest already reports the missing/stale input.
                target = output(
                    package / "files" / artifact.file.sha256 / artifact.file.name
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                artifacts.append(
                    f"- {artifact.kind}: [{artifact.file.name}]({target.relative_to(package).as_posix()})"
                )
        plan = self.project.decisions.plan(manifest.plan_decision)
        criteria = [
            f"- {spec.title}: {'; '.join(spec.acceptance_criteria)}"
            for spec in plan.deliverables
        ]
        text = (
            f"# {manifest.stage} — {manifest.status}\n\nBaseline: {manifest.id}, revision {revision}.\n\n## Artifacts\n\n"
            + "\n".join(artifacts)
            + "\n\n## Acceptance criteria\n\n"
            + "\n".join(criteria)
            + "\n\n## Open items\n\n"
            + "\n".join(f"- {item}" for item in manifest.open_items)
            + "\n"
        )
        output(package / "review.md").write_text(text, encoding="utf-8")
        traces = {
            r.id: self.project.trace(r.id)
            for r in self.project.requests(decision=manifest.plan_decision)
        }
        traces[manifest.plan_decision] = self.project.trace(manifest.plan_decision)
        if manifest.readiness_decision:
            traces[manifest.readiness_decision] = self.project.trace(
                manifest.readiness_decision
            )
        output(package / "traces.json").write_text(encode(traces), encoding="utf-8")
        return path
