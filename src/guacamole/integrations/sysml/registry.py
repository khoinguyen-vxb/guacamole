"""The authoritative SysML model: revisions, amendments and the decision gate.

Only validated revisions are recorded. The gate is active once a systems engineer is
configured or a model exists: decisions then need a current model of every recorded
requirement, candidates must respect its bounds, and each new revision invalidates
decisions it contradicts. Amendment status is derived from records, never stored.
"""

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ...contracts import (
    JSON,
    Amendment,
    AmendmentRecord,
    Assessment,
    Candidate,
    DecisionRecord,
    Evidence,
    ModelChanges,
    ModelReport,
    Ref,
    Requirement,
    SystemModel,
    VerificationResult,
)
from ...decision import DecisionBlocked
from ...storage import Snapshot
from ...tools.registry import encode
from . import validator

if TYPE_CHECKING:
    from ...project import Project

MODEL_ID = "system"
EXPORT = Path("sysml")
CITABLE = frozenset(
    {
        "source",
        "requirement",
        "open_item",
        "decision",
        "evidence",
        "artifact",
        "deliverable",
        "review",
        "summary",
        "tool_result",
    }
)
# Records whose arrival can change what the model must say.
CHANGES = {
    "requirement.recorded": "requirement",
    "open_item.recorded": "open_item",
    "decision.recorded": "decision",
    "evidence.recorded": "evidence",
    "human.input_recorded": "source",
    "review.accepted": "review",
    "review.rejected": "review",
}
PENDING = frozenset({"proposed", "accepted"})


def _system(snapshot: Snapshot) -> SystemModel:
    return SystemModel.model_validate_json(encode(snapshot.data))


def _proposal(snapshot: Snapshot) -> AmendmentRecord:
    return AmendmentRecord.model_validate_json(encode(snapshot.data))


class ModelRejected(ValueError):
    """An invalid model; the full deterministic report travels with it."""

    def __init__(self, report: ModelReport) -> None:
        errors = [i for i in report.issues if i.severity == "error"]
        super().__init__(
            f"SysML model rejected with {len(errors)} error(s): "
            + "; ".join(f"[{i.code}] {i.element}: {i.detail}" for i in errors)
        )
        self.report = report


class SysMLRegistry:
    def __init__(self, project: "Project") -> None:
        self.project = project

    def current(self) -> Snapshot | None:
        return self.project.store.maybe("system_model", MODEL_ID)

    def model(self) -> SystemModel | None:
        snapshot = self.current()
        return _system(snapshot) if snapshot else None

    def requirements(self) -> tuple[Snapshot, ...]:
        """Current requirements: neither stale nor withdrawn."""
        return tuple(
            s
            for s in self.project.store.list("requirement")
            if not s.stale and not s.data.get("withdrawn")
        )

    def _records(self, snapshots: Sequence[Snapshot]) -> list[Requirement]:
        return [Requirement.model_validate_json(encode(s.data)) for s in snapshots]

    async def validate(self, files: Mapping[str, str]) -> ModelReport:
        """Validate files against current requirements without recording them."""
        records = self._records(self.requirements())
        return await asyncio.to_thread(validator.validate, dict(files), records)

    async def commit(
        self,
        *,
        summary: str,
        files: Mapping[str, str] | None = None,
        remove: Sequence[str] = (),
        derived_from: Sequence[Ref] = (),
        implements: str | None = None,
        actor: str = "script",
    ) -> tuple[Ref, dict[str, str]]:
        """Record a valid revision; return it and why it invalidated decisions."""
        store, files = self.project.store, dict(files or {})
        current = self.current()
        base = dict(_system(current).files) if current else {}
        dependencies = list(derived_from)
        for ref in derived_from:
            if ref.kind not in CITABLE:
                raise ValueError(
                    f"derived_from cites engineering records, not {ref.kind}"
                )
            store.resolve(ref, current=True)
        if implements is not None:
            if files or remove:
                raise ValueError(
                    "An implementing revision applies the adopted amendment exactly; "
                    "send no files"
                )
            status, decision = self.status(implements)
            if status != "accepted" or decision is None:
                raise ValueError(
                    f"Amendment {implements} is {status}; implement only amendments "
                    "a current decision adopted"
                )
            resulting = self._apply(self._amendment(implements), base)
            dependencies.append(store.get("decision", decision).ref)
        else:
            if not derived_from:
                raise ValueError(
                    "Cite the current records this revision derives from in derived_from"
                )
            validator.check_paths((*files, *remove))
            unknown = sorted(set(remove) - base.keys())
            if unknown:
                raise ValueError(f"The model has no files {unknown} to remove")
            resulting = {p: t for p, t in base.items() if p not in remove} | files
        if not resulting:
            raise ValueError("The model needs at least one file")
        requirements = self.requirements()
        report = await asyncio.to_thread(
            validator.validate, resulting, self._records(requirements)
        )
        if not report.valid:
            store.event(
                actor,
                "system_model.rejected",
                MODEL_ID,
                {
                    "digest": report.digest,
                    "issues": [i.model_dump(mode="json") for i in report.issues],
                },
            )
            raise ModelRejected(report)
        model = SystemModel(
            files=resulting,
            summary=summary,
            derived_from=tuple(derived_from),
            implements=implements,
            report=report,
            author=actor,
        )
        with store.atomic():
            # Requirement revisions validated here stale the model when they change.
            ref = store.put(
                "system_model",
                MODEL_ID,
                model,
                actor=actor,
                dependencies=tuple(
                    dict.fromkeys((*dependencies, *(s.ref for s in requirements)))
                ),
            )
            invalidated = self._revalidate(ref, report, actor)
            if store.resolve(ref).stale:
                raise ValueError(
                    "Model revision would invalidate its own inputs. Cite independent "
                    "sources or requirements in derived_from; keep prior-model "
                    "decisions and outputs as historical references in the summary."
                )
        self._export(ref, model, base)
        return ref, invalidated

    def _revalidate(self, ref: Ref, report: ModelReport, actor: str) -> dict[str, str]:
        """Invalidate current decisions whose selected metrics the revision contradicts."""
        store = self.project.store
        invalidated = {}
        for snapshot in store.list("decision"):
            if snapshot.stale:
                continue
            decision = DecisionRecord.model_validate_json(encode(snapshot.data))
            selected = next(
                c
                for c in decision.request.candidates
                if c.id == decision.result.selected
            )
            problems = validator.violations(report.bounds, selected.metrics)
            if problems:
                reason = (
                    f"Contradicts SysML model revision {ref.revision}: "
                    + "; ".join(problems)
                )
                store.invalidate(snapshot.ref, actor=actor, reason=reason)
                invalidated[snapshot.ref.id] = reason
        return invalidated

    async def amend(self, amendment: Amendment, *, actor: str = "script") -> Ref:
        """Record a validated proposal against the current model."""
        store = self.project.store
        current = self.current()
        if current is None or current.stale:
            raise ValueError("Amendments need a current model; commit or revalidate it")
        if store.maybe("amendment", amendment.id) is not None:
            raise ValueError(f"Amendment {amendment.id} exists; propose under a new ID")
        for id in amendment.supersedes:
            if store.maybe("amendment", id) is None:
                raise ValueError(f"Unknown superseded amendment: {id}")
        for ref in amendment.evidence:
            store.resolve(ref, current=True)
        model = _system(current)
        if not amendment.files and not amendment.remove:
            if not amendment.supersedes:
                raise ValueError(
                    "An amendment changes the model or withdraws amendments it supersedes"
                )
            report, changes = model.report, ModelChanges()
        else:
            validator.check_paths((*amendment.files, *amendment.remove))
            unknown = sorted(set(amendment.remove) - model.files.keys())
            if unknown:
                raise ValueError(f"The model has no files {unknown} to remove")
            proposed = {
                p: t for p, t in model.files.items() if p not in amendment.remove
            } | amendment.files
            if proposed == model.files:
                raise ValueError("The amendment changes nothing")
            report, changes = await asyncio.to_thread(
                validator.propose,
                model.files,
                proposed,
                model.report,
                self._records(self.requirements()),
            )
            if any(i.code in validator.STRUCTURAL for i in report.issues):
                raise ModelRejected(report)
        return store.put(
            "amendment",
            amendment.id,
            AmendmentRecord(
                amendment=amendment,
                base=current.ref,
                report=report,
                changes=changes,
                author=actor,
            ),
            actor=actor,
            dependencies=amendment.evidence,
        )

    def _amendment(self, id: str) -> AmendmentRecord:
        return self.project.store.model("amendment", id, AmendmentRecord)

    def _applies(self, record: AmendmentRecord, files: Mapping[str, str]) -> bool:
        """The files it touches are unchanged since the revision it amends."""
        base = _system(self.project.store.resolve(record.base)).files
        changed = (*record.amendment.files, *record.amendment.remove)
        return all(base.get(path) == files.get(path) for path in changed)

    def _apply(
        self, record: AmendmentRecord, files: Mapping[str, str]
    ) -> dict[str, str]:
        if not self._applies(record, files):
            raise ValueError(
                f"Amendment {record.amendment.id} conflicts with the current model; "
                "propose a rebased amendment"
            )
        removed = record.amendment.remove
        return {p: t for p, t in files.items() if p not in removed} | dict(
            record.amendment.files
        )

    def status(
        self, id: str, files: Mapping[str, str] | None = None
    ) -> tuple[str, str | None]:
        """(status, adopting decision): proposed, accepted, rejected, implemented,
        superseded, or withdrawal for an amendment that only withdraws others.

        files defaults to the current model's files."""
        store = self.project.store
        snapshot = store.get("amendment", id)
        record = _proposal(snapshot)
        amendment = record.amendment
        if not amendment.files and not amendment.remove:
            return "withdrawal", None
        if any(
            s.data.get("implements") == id
            for s in store.history("system_model", MODEL_ID)
        ):
            return "implemented", None
        if files is None:
            current = self.current()
            files = _system(current).files if current else {}
        if all(files.get(p) == t for p, t in amendment.files.items()) and not any(
            p in files for p in amendment.remove
        ):
            return "implemented", None
        if (
            snapshot.stale
            or not self._applies(record, files)
            or any(
                id in _proposal(s).amendment.supersedes
                for s in store.list("amendment")
                if s.ref.id != id
            )
        ):
            return "superseded", None
        cited = False
        for snapshot in store.list("decision"):
            # Every eligible candidate's evidence is a dependency of its decision.
            if snapshot.stale or not any(
                r.kind == "amendment" and r.id == id for r in snapshot.dependencies
            ):
                continue
            decision = DecisionRecord.model_validate_json(encode(snapshot.data))
            for candidate in decision.request.candidates:
                if any(
                    r.kind == "amendment" and r.id == id for r in candidate.evidence
                ):
                    if candidate.id == decision.result.selected:
                        return "accepted", snapshot.ref.id
                    cited = True
        return ("rejected" if cited else "proposed"), None

    def amendments(self, files: Mapping[str, str] | None = None) -> list[JSON]:
        listed: list[JSON] = []
        if files is None:
            current = self.current()
            files = _system(current).files if current else {}
        for snapshot in self.project.store.list("amendment"):
            status, decision = self.status(snapshot.ref.id, files)
            if status != "withdrawal":
                listed.append(
                    {
                        "id": snapshot.ref.id,
                        "ref": snapshot.ref.model_dump(mode="json"),
                        "title": _proposal(snapshot).amendment.title,
                        "status": status,
                        "decision": decision,
                    }
                )
        return listed

    def uncovered(self, model: SystemModel) -> list[str]:
        modeled = {r.id for r in model.report.requirements}
        return sorted({s.ref.id for s in self.requirements()} - modeled)

    def gate(self) -> Snapshot:
        """The model a decision must respect."""
        snapshot = self.current()
        if snapshot is None:
            raise DecisionBlocked(
                "No SysML model yet: the systems engineer must commit a valid model "
                "of every recorded requirement before decisions"
            )
        revision = snapshot.ref.revision
        if snapshot.stale:
            raise DecisionBlocked(
                f"SysML model revision {revision} is stale because its inputs "
                "changed; wait for the systems engineer to revalidate it"
            )
        if uncovered := self.uncovered(_system(snapshot)):
            raise DecisionBlocked(
                f"SysML model revision {revision} does not model requirements "
                f"{', '.join(uncovered)}; wait for the systems engineer to add them"
            )
        return snapshot

    def check(self, candidate: Candidate, model: Snapshot) -> None:
        """Reject a candidate that contradicts the model or adopts an unusable amendment."""
        report = ModelReport.model_validate_json(encode(model.data["report"]))
        if problems := validator.violations(report.bounds, candidate.metrics):
            raise ValueError("Contradicts the SysML model: " + "; ".join(problems))
        for ref in candidate.evidence:
            if ref.kind != "amendment":
                continue
            status, _ = self.status(ref.id)
            if status not in {"proposed", "accepted", "rejected"}:
                raise ValueError(f"Amendment {ref.id} is {status}")
            proposal = self._amendment(ref.id).report
            if not proposal.valid:
                errors = [i for i in proposal.issues if i.severity == "error"]
                raise ValueError(
                    f"Amendment {ref.id} would leave the model invalid ("
                    + "; ".join(f"[{i.code}] {i.element}: {i.detail}" for i in errors)
                    + "); requirement changes need updated requirement records first"
                )

    def assess(self, assessment: Assessment, *, actor: str = "script") -> Ref:
        """Record compliance claims the evidence's measurements and the model bear out."""
        store = self.project.store
        snapshot = self.gate()
        model = _system(snapshot)
        if assessment.evidence.kind != "evidence":
            raise ValueError("An assessment cites an evidence record")
        store.resolve(assessment.evidence, current=True)
        evidence = store.model("evidence", assessment.evidence.id, Evidence)
        if evidence.outcome != "passed":
            raise ValueError(
                f"Evidence {evidence.id} is {evidence.outcome}; only passed evidence "
                "shows compliance"
            )
        result = VerificationResult.model_validate_json(
            encode(self.project.activity.get(evidence.request_id).result)
        )
        parents = {r.id: r.parent for r in model.report.requirements}
        covered = {r.id for r in evidence.requirements}
        problems = []
        for claim in assessment.satisfied:
            id, key = claim.requirement, claim.measurement or claim.requirement
            # ponytail: one measurement per requirement; a requirement bounding two
            # metrics is modelled as derived requirements, one bound each.
            bounds = [b for b in model.report.bounds if b.requirement == id]
            lineage, parent = {id}, parents.get(id)
            while parent and parent not in lineage:  # Derived ones trace to records.
                lineage.add(parent)
                parent = parents.get(parent)
            quantity = result.measurements.get(key)
            if not bounds:
                problems.append(
                    f"{id}: no bound in SysML model revision {snapshot.ref.revision}"
                )
            elif not lineage & covered:
                problems.append(f"{id}: evidence {evidence.id} does not cover it")
            elif quantity is None:
                problems.append(
                    f"{id}: evidence {evidence.id} has no measurement {key!r}; it has "
                    f"{sorted(result.measurements)}"
                )
            elif len(metrics := {b.metric for b in bounds}) > 1:
                problems.append(
                    f"{id} bounds {sorted(metrics)}; model one derived requirement "
                    "per metric and assess each"
                )
            else:
                problems.extend(validator.violations(bounds, {metrics.pop(): quantity}))
        if problems:
            raise ValueError("Assessment rejected: " + "; ".join(problems))
        return store.put(
            "assessment",
            assessment.id,
            assessment,
            actor=actor,
            dependencies=(snapshot.ref, assessment.evidence),
        )

    def assessed(self) -> set[str]:
        """Requirement IDs a current assessment shows satisfied by the current model."""
        snapshot = self.current()
        return {
            claim.requirement
            for s in self.project.store.list("assessment")
            if snapshot is not None and not s.stale and snapshot.ref in s.dependencies
            for claim in Assessment.model_validate_json(encode(s.data)).satisfied
        }

    def review_issues(self) -> tuple[str, ...]:
        """Why the model cannot yet be baselined in a review."""
        try:
            snapshot = self.gate()
        except DecisionBlocked as exc:
            return (str(exc),)
        model = _system(snapshot)
        # The systems engineer's compliance gate: each bounded requirement needs a
        # current assessment of passed evidence against this model revision.
        bounded = sorted({b.requirement for b in model.report.bounds} - self.assessed())
        return (
            *(
                f"{id}: no compliance assessment against SysML model revision "
                f"{snapshot.ref.revision}; send the passed evidence to the systems "
                "engineer to assess"
                for id in bounded
            ),
            *(
                f"Amendment {a['id']} is {a['status']}: {a['title']}"
                for a in self.amendments()
                if a["status"] in PENDING
            ),
        )

    def changes(self) -> list[Ref]:
        """Current records that arrived after the latest revision was committed."""
        store = self.project.store
        since = store.db.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM events "
            "WHERE type='system_model.recorded'"
        ).fetchone()[0]
        rows = store.db.execute(
            "SELECT DISTINCT type, entity_id FROM events WHERE sequence > ? "
            f"AND type IN ({','.join('?' * len(CHANGES))})",
            (since, *CHANGES),
        ).fetchall()
        refs = {}
        for type, id in rows:
            snapshot = store.maybe(CHANGES[type], id)
            if snapshot is not None and not snapshot.stale:
                refs[(snapshot.ref.kind, id)] = snapshot.ref
        return [refs[key] for key in sorted(refs)]

    def state(self, *, engineer: bool) -> JSON:
        """The model as every agent sees it; the systems engineer also gets its text."""
        snapshot = self.current()
        view: JSON
        if snapshot is None:
            view = {
                "status": "missing",
                "uncovered_requirements": [
                    *sorted(s.ref.id for s in self.requirements())
                ],
            }
        else:
            model = _system(snapshot)
            uncovered = self.uncovered(model)
            view = {
                "ref": snapshot.ref.model_dump(mode="json"),
                "status": "stale"
                if snapshot.stale
                else "incomplete"
                if uncovered
                else "valid",
                "summary": model.summary,
                "uncovered_requirements": [*uncovered],
                "bounds": [b.model_dump(mode="json") for b in model.report.bounds],
                "unassessed_requirements": [
                    *sorted(
                        {b.requirement for b in model.report.bounds} - self.assessed()
                    )
                ],
                "amendments": [*self.amendments(model.files)],
            }
            if engineer:
                report = model.report
                view |= {
                    "files": {**model.files},
                    "derived_from": [
                        r.model_dump(mode="json") for r in model.derived_from
                    ],
                    "requirements": [
                        r.model_dump(mode="json") for r in report.requirements
                    ],
                    "satisfactions": [
                        s.model_dump(mode="json") for s in report.satisfactions
                    ],
                    "warnings": [i.model_dump(mode="json") for i in report.issues],
                }
        if engineer:
            view["changes"] = [r.model_dump(mode="json") for r in self.changes()]
        return view

    def _export(
        self, ref: Ref, model: SystemModel, previous: Mapping[str, str]
    ) -> None:
        """Mirror the current revision under sandbox/sysml for SysML tools and people."""
        output = self.project.output_path
        for path in previous.keys() - model.files.keys():
            output(EXPORT / path).unlink(missing_ok=True)
        for path, text in model.files.items():
            target = output(EXPORT / path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        output(EXPORT / "report.json").write_text(
            json.dumps(
                {
                    "ref": ref.model_dump(mode="json"),
                    "summary": model.summary,
                    "report": model.report.model_dump(mode="json"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
