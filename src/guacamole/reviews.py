"""Versioned deliverables, deterministic readiness, then human disposition."""

import csv
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from .contracts import (
    JSON,
    ArtifactRecord,
    AskHuman,
    Catalogue,
    DecisionRecord,
    Deliverable,
    Evidence,
    OpenItem,
    Quantity,
    Ref,
    Requirement,
    ReviewManifest,
    ReviewStage,
    Standard,
    SystemModel,
    VerificationResult,
)
from .standards import assess
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
        catalogue = store.maybe("catalogue", "standards")
        if catalogue is not None:
            baseline.append(catalogue.ref)
        current: list[Requirement] = []
        # Unknowns an open item tracks block only the stages that item blocks.
        tracked = {
            id
            for s in store.list("open_item")
            if not s.stale
            for id in OpenItem.model_validate_json(encode(s.data)).requirements
        }
        for requirement in store.list("requirement"):
            record = Requirement.model_validate_json(encode(requirement.data))
            if record.withdrawn:
                continue
            if not requirement.stale:
                current.append(record)
            if requirement.ref.id not in tracked:
                issues.extend(
                    f"{requirement.ref.id}: unresolved input {unknown}; record an "
                    "open item for it with requirements and the stages it blocks"
                    for unknown in record.unknowns
                )
            if (pin := record.standard) and not pin.text and not requirement.stale:
                issues.append(
                    f"{requirement.ref.id}: no licensed text of {pin.id}:{pin.edition} "
                    "in the project to verify against"
                )
        if catalogue is not None and catalogue.stale:
            issues.append("standards catalogue: its source changed; record it again")
        elif catalogue is not None:
            # An unresolved mandatory standard cannot pass: it applies and nothing
            # selects it, or the facts its rule needs are missing.
            for a in assess(
                Catalogue.model_validate_json(encode(catalogue.data)), current
            ):
                if a.mandatory and a.status == "applies" and a.selected is None:
                    issues.append(
                        f"{a.standard}: the catalogue's rule says it applies, and no "
                        "requirement selects it"
                    )
                elif a.mandatory and a.status == "unknown":
                    issues.append(
                        f"{a.standard}: whether it applies is unknown without "
                        + ", ".join(a.missing)
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
                        if not {a.id for a in evidence.artifacts} & {
                            a.id for a in deliverable.artifacts
                        }:
                            issues.append(
                                f"{spec.id}: {evidence.kind} evidence covers none of its artifacts"
                            )
                        elif evidence.outcome == "passed":
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
            if (
                request.required
                and request.status not in {"completed", "cancelled"}
                and not (request.kind == "human" and "review" in request.arguments)
            ):
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
        # The model revision is reviewed but kept out of the baseline, so refining
        # the model after acceptance does not withdraw an accepted review.
        model = self.project.sysml.current()
        manifest = ReviewManifest(
            stage=plan.stage,
            plan_decision=plan_decision,
            baseline=baseline,
            deliverables=deliverables,
            open_items=(*issues, *self.project.sysml.review_issues()),
            model=model.ref if model is not None else None,
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
        if manifest.open_items:
            return ref
        manifest = manifest.model_copy(update={"status": "ready"})
        ref = store.put(
            "review",
            manifest.id,
            manifest,
            actor="runtime",
            dependencies=baseline,
            event="review.ready",
        )
        self.project.human.ask(
            AskHuman(
                question=f"Review the {plan.stage} package and accept it or request changes.",
                choices=("Accept", "Request changes"),
                references=(ref,),
            ),
            run_id=run_id,
            sender=actor,
            parent_id=parent_id,
            decision_id=plan_decision,
            packet_id=packet_id,
            rationale_id=rationale_id,
            review=ref,
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
        if manifest.status != "ready":
            raise ValueError("Only a ready baseline can receive human disposition")
        _, baseline, issues = self.checks(manifest.plan_decision)
        if issues or baseline != manifest.baseline:
            raise ValueError("Review baseline is no longer current or complete")
        model = self.project.sysml.current() if manifest.model else None
        if self.project.sysml.review_issues() or (
            model is not None and model.ref != manifest.model
        ):
            raise ValueError("The SysML model changed or is unusable since this review")
        changed = manifest.model_copy(
            update={
                "status": "accepted" if accepted else "rejected",
                "human": reviewer,
                "disposition": disposition,
            }
        )
        original = ref
        ref = store.put(
            "review",
            manifest.id,
            changed,
            actor=f"human:{reviewer}",
            dependencies=snapshot.dependencies,
            event=f"review.{changed.status}",
        )
        self.project.human.review_answered(
            original, author=reviewer, disposition=disposition
        )
        self._export(changed)
        if not accepted:
            run_id = self.project.activity.get(manifest.plan_decision).run_id
            self.project.human.interject(
                disposition, author=reviewer, run_id=run_id, references=(ref,)
            )
        return ref

    def _export(self, manifest: ReviewManifest) -> Path:
        output, store = self.project.output_path, self.project.store
        directory = output(Path("reviews") / manifest.id)
        directory.mkdir(parents=True, exist_ok=True)
        revision = store.get("review", manifest.id).ref.revision
        path = output(directory / f"manifest-v{revision}.json")
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        package = output(directory / f"v{revision}")
        package.mkdir(exist_ok=True)
        records = [
            store.resolve(ref).model_dump(mode="json") for ref in manifest.baseline
        ]
        output(package / "records.json").write_text(encode(records), encoding="utf-8")
        lock = [
            {"requirement": ref.model_dump(mode="json")}
            | pin.model_dump(mode="json")
            | self._library(pin)
            | {"clauses": clauses}
            for ref, pin, clauses in self._standards(manifest.baseline)
        ]
        if lock:
            output(package / "standards.lock.json").write_text(
                encode(lock), encoding="utf-8"
            )
        files: dict[str, Path] = {}
        for deliverable in manifest.deliverables:
            for ref in deliverable.artifacts:
                artifact = ArtifactRecord.model_validate_json(
                    encode(store.resolve(ref).data)
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
                files[ref.id] = target.relative_to(package)
        model = []
        if manifest.model is not None:
            system = SystemModel.model_validate_json(
                encode(store.resolve(manifest.model).data)
            )
            for name, content in sorted(system.files.items()):
                target = output(package / "sysml" / name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                model.append(f"- [{name}]({target.relative_to(package).as_posix()})")
            model.insert(0, f"Revision {manifest.model.revision}: {system.summary}\n")
        text = self._report(manifest, revision, package, files, model)
        output(package / "review.md").write_text(text, encoding="utf-8")
        traces = {
            r.id: self.project.trace(r.id)
            for r in self.project.requests(decision=manifest.plan_decision)
        }
        traces[manifest.plan_decision] = self.project.trace(manifest.plan_decision)
        output(package / "traces.json").write_text(encode(traces), encoding="utf-8")
        return path

    def _report(
        self,
        manifest: ReviewManifest,
        revision: int,
        package: Path,
        files: dict[str, Path],
        model: list[str],
    ) -> str:
        """The review document, rendered only from the records under review."""
        store, activity = self.project.store, self.project.activity
        plan = self.project.decisions.plan(manifest.plan_decision)
        verified: dict[str, tuple[Evidence, VerificationResult]] = {}
        for deliverable in manifest.deliverables:
            for ref in deliverable.evidence:
                evidence = Evidence.model_validate_json(encode(store.resolve(ref).data))
                result = activity.get(evidence.request_id).result
                verified[ref.id] = (
                    evidence,
                    VerificationResult.model_validate_json(encode(result)),
                )
        lines = [
            f"# {manifest.stage} design review — {manifest.status}",
            "",
            f"Baseline {manifest.id}, revision {revision}; plan {manifest.plan_decision}.",
        ]
        if manifest.human:
            lines += ["", f"Disposition by {manifest.human}: {manifest.disposition}"]
        lines += self._changes(manifest)

        assessed = self.project.sysml.assessed()
        lines += [
            "",
            "## Requirements and traceability",
            "",
            "| Requirement | Statement | Limit | Measured | Verified by |",
            "|---|---|---|---|---|",
        ]
        for ref in manifest.baseline:
            if ref.kind != "requirement":
                continue
            requirement = Requirement.model_validate_json(
                encode(store.resolve(ref).data)
            )
            if (withdrawn := requirement.withdrawn) is not None:
                cells = (
                    requirement.id,
                    requirement.wording,
                    "—",
                    "withdrawn",
                    f'{withdrawn.source.id}: "{withdrawn.quote}"',
                )
                lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
                continue
            limit = "—"
            if requirement.constraint is not None:
                c = requirement.constraint
                bounds = [
                    f"{op} {value:g}"
                    for op, value in ((">=", c.minimum), ("<=", c.maximum))
                    if value is not None
                ]
                limit = f"{c.metric} {' and '.join(bounds)}{_unit(c.unit)}"
            measured, by = [], []
            for evidence, result in verified.values():
                if requirement.id not in {r.id for r in evidence.requirements}:
                    continue
                by.append(f"{evidence.kind} ({evidence.outcome})")
                checks = [
                    ok
                    for name, ok in result.checks.items()
                    if name.startswith(f"{requirement.id}:")
                ]
                quantity = result.measurements.get(requirement.id)
                if quantity is not None or checks:
                    status = (
                        "not performed"
                        if not checks or None in checks
                        else "FAILED"
                        if False in checks
                        else "passed"
                    )
                    value = f"{_amount(quantity)} " if quantity is not None else ""
                    measured.append(f"{value}{status}")
            if by and not measured:
                # Passing evidence that never checks this requirement is no pass for it.
                measured.append("not checked")
            if requirement.id in assessed:
                by.append("systems engineer assessment")
            lines.append(
                "| "
                + " | ".join(
                    _cell(text)
                    for text in (
                        requirement.id,
                        requirement.wording,
                        limit,
                        "; ".join(measured) or "—",
                        "; ".join(by) or "not verified",
                    )
                )
                + " |"
            )

        if standards := self._standards(manifest.baseline):
            lines += [
                "",
                "## Standards",
                "",
                "| Standard | Amendments | Selected by | Licensed text | Clauses |",
                "|---|---|---|---|---|",
            ]
            for ref, pin, clauses in standards:
                text = "none"
                if pin.text is not None:
                    data = store.resolve(pin.text).data
                    digest = str(data.get("sha256") or pin.text.sha256)[:12]
                    text = f"{data.get('name') or pin.text.id} ({digest})"
                cells = (
                    f"{pin.id}:{pin.edition}",
                    ", ".join(pin.amendments) or "none",
                    ref.id,
                    text,
                    "; ".join(f"{c} ({id})" for id, c in clauses.items()) or "none",
                )
                lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")

        catalogue = next((r for r in manifest.baseline if r.kind == "catalogue"), None)
        if catalogue is not None:
            current = [
                record
                for ref in manifest.baseline
                if ref.kind == "requirement"
                and not (
                    record := Requirement.model_validate_json(
                        encode(store.resolve(ref).data)
                    )
                ).withdrawn
            ]
            entries = Catalogue.model_validate_json(
                encode(store.resolve(catalogue).data)
            )
            lines += [
                "",
                "## Applicability",
                "",
                f"From catalogue revision {catalogue.revision}.",
                "",
                "| Standard | Rule | Applicability | Selected by | Edition |",
                "|---|---|---|---|---|",
            ]
            for entry, a in zip(entries.entries, assess(entries, current)):
                status = a.status + (" (mandatory)" if a.mandatory else "")
                if a.missing:
                    status += f"; missing {', '.join(a.missing)}"
                edition = a.edition or "—"
                if a.superseded:
                    edition += f" (catalogue lists {a.latest})"
                cells = (
                    a.standard,
                    entry.applies_when or "by selection",
                    status,
                    a.selected or "none",
                    edition,
                )
                lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")

        lines += ["", "## Decisions"]
        run_id = activity.get(manifest.plan_decision).run_id
        decisions = sorted(
            (
                s
                for s in store.list("decision")
                if not s.stale and activity.get(s.ref.id).run_id == run_id
            ),
            key=lambda s: activity.get(s.ref.id).created_at,
        )
        for snapshot in decisions:
            decision = DecisionRecord.model_validate_json(encode(snapshot.data))
            chosen = decision.result.selected
            candidates = decision.request.candidates
            lines += [
                "",
                f"### {decision.request.question}",
                "",
                f"Selected **{chosen}**: "
                + next(c.description for c in candidates if c.id == chosen),
                "",
                decision.result.explanation,
            ]
            metrics = sorted({name for c in candidates for name in c.metrics})
            if len(candidates) > 1 or metrics:
                lines += [
                    "",
                    "| Candidate | " + " | ".join(_cell(m) for m in metrics) + " |",
                    "|---|" + "---|" * len(metrics),
                ]
                lines += [
                    f"| {_cell(c.id)} | "
                    + " | ".join(
                        _amount(q) if (q := c.metrics.get(m)) else "—" for m in metrics
                    )
                    + " |"
                    for c in candidates
                ]

        lines += ["", "## Deliverables"]
        titles = {spec.id: spec.title for spec in plan.deliverables}
        for deliverable in manifest.deliverables:
            lines += [
                "",
                f"### {titles.get(deliverable.spec_id, deliverable.spec_id)}",
                "",
                "| Kind | File | SHA-256 |",
                "|---|---|---|",
            ]
            figures, tables = [], []
            for ref in deliverable.artifacts:
                artifact = ArtifactRecord.model_validate_json(
                    encode(store.resolve(ref).data)
                )
                name, link = artifact.file.name, files.get(ref.id)
                lines.append(
                    f"| {_cell(artifact.kind)} | "
                    + (f"[{name}]({link.as_posix()})" if link else f"{name} (missing)")
                    + f" | {artifact.file.sha256[:12]} |"
                )
                if link and link.suffix.lower() in {".svg", ".png", ".jpg"}:
                    figures.append(f"![{artifact.kind}: {name}]({link.as_posix()})")
                elif link and link.suffix.lower() == ".csv":
                    with (package / link).open(newline="", encoding="utf-8") as f:
                        tables.append((artifact.kind, name, list(csv.reader(f))))
            for figure in figures:
                lines += ["", figure]
            for kind, name, rows in tables:
                if rows:
                    lines += ["", f"**{kind}** ({name})", ""]
                    lines += [
                        "| " + " | ".join(_cell(v) for v in row) + " |"
                        for row in (rows[0], ["---"] * len(rows[0]), *rows[1:])
                    ]

        lines += ["", "## Verification"]
        for evidence, result in verified.values():
            lines += [
                "",
                f"### {evidence.kind} — {evidence.outcome}",
                "",
                evidence.explanation,
                "",
                "| Check | Result |",
                "|---|---|",
            ]
            lines += [
                f"| {_cell(name)} | "
                + ("passed" if ok else "FAILED" if ok is False else "not performed")
                + " |"
                for name, ok in result.checks.items()
            ]
            if result.measurements:
                lines += ["", "| Quantity | Value |", "|---|---|"]
                lines += [
                    f"| {_cell(name)} | {_amount(q)} |"
                    for name, q in result.measurements.items()
                ]

        unperformed = [
            f"{evidence.kind}: {name} — not performed"
            for evidence, result in verified.values()
            for name, ok in result.checks.items()
            if ok is None
        ]
        lines += ["", "## Open items and limitations", ""]
        lines += [f"- {item}" for item in (*manifest.open_items, *unperformed)] or [
            "None recorded."
        ]
        lines += ["", "## Acceptance criteria", ""]
        lines += [
            f"- {spec.title}: {'; '.join(spec.acceptance_criteria)}"
            for spec in plan.deliverables
        ]
        if model:
            lines += ["", "## SysML model", "", *model]
        return "\n".join(lines) + "\n"

    def _library(self, pin: Standard) -> JSON:
        """The library snapshot a selection's text is pinned to, when it has one."""
        if pin.text is None:
            return {}
        data = self.project.store.resolve(pin.text).data
        if data.get("kind") != "library_pin":
            return {}
        return {
            "library": {k: data[k] for k in ("snapshot", "scope", "sha256", "name")}
        }

    def _standards(
        self, baseline: tuple[Ref, ...]
    ) -> list[tuple[Ref, Standard, dict[str, str]]]:
        """The standards lock: each selection, its pin and clause requirements by ID."""
        records = [
            (
                ref,
                Requirement.model_validate_json(
                    encode(self.project.store.resolve(ref).data)
                ),
            )
            for ref in baseline
            if ref.kind == "requirement"
        ]
        return [
            (
                ref,
                pin,
                {
                    r.id: r.clause.reference
                    for _, r in records
                    if r.clause and r.clause.standard == ref
                },
            )
            for ref, record in records
            if (pin := record.standard) and not record.withdrawn
        ]

    def _changes(self, manifest: ReviewManifest) -> list[str]:
        """What changed since the last baseline of this stage a human dispositioned."""
        store, activity = self.project.store, self.project.activity
        reviewed = [
            ReviewManifest.model_validate_json(encode(s.data))
            for s in store.list("review")
            if s.ref.id != manifest.id
            and s.data["stage"] == manifest.stage
            and s.data["status"] in {"accepted", "rejected"}
        ]
        if not reviewed:
            return []
        # ponytail: latest by plan decision; two dispositions of one plan tie.
        previous = max(reviewed, key=lambda m: activity.get(m.plan_decision).created_at)
        before = {(r.kind, r.id): r for r in previous.baseline}
        after = {(r.kind, r.id): r for r in manifest.baseline}
        rows, kept = [], 0
        for key in sorted(before.keys() | after.keys()):
            old, new = before.get(key), after.get(key)
            if new is not None and store.resolve(new).stale:
                change = "stale"
            elif old is None:
                change = "added"
            elif new is None:
                change = "dropped"
            elif old.revision != new.revision:
                change = f"revision {old.revision} → {new.revision}"
            else:
                kept += 1
                continue
            wording = (
                str(store.resolve(old).data["wording"])
                if key[0] == "requirement" and old is not None
                else ""
            )
            rows.append(f"| {_cell(':'.join(key))} | {change} | {_cell(wording)} |")
        return [
            "",
            f"## Changes since review {previous.id} ({previous.status})",
            "",
            (
                f"{kept} records carry over unchanged and current. Dropped records stay "
                "in history and are not evidence for this baseline; anything still owed "
                "is listed under open items."
            ),
            "",
            "| Record | Change | Earlier requirement wording |",
            "|---|---|---|",
            *rows,
        ]


def _unit(unit: str) -> str:
    """ " kg", or nothing for a dimensionless unit."""
    return "" if unit.strip() in {"", "1", "-"} else f" {unit}"


def _amount(quantity: Quantity) -> str:
    return f"{quantity.value:.4g}{_unit(quantity.unit)}"


def _cell(text: str) -> str:
    """One Markdown table cell: pipes escaped, newlines folded."""
    return " ".join(str(text).split()).replace("|", "\\|")
