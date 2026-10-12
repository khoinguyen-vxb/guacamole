"""Deterministic truth checks: SysML text against requirement records and decisions.

validate() and propose() parse with the SysML Toolkit (adapter.py). The bound checks
used by decision gates read stored reports and never invoke the Toolkit.
"""

import difflib
import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ...contracts import (
    Constraint,
    ModelBound,
    ModelChanges,
    ModeledRequirement,
    ModelIssue,
    ModelReport,
    Quantity,
    Requirement,
    Satisfaction,
)
from ...tools.registry import encode

if TYPE_CHECKING:
    from .adapter import Bound, SysMLAdapter

SUFFIXES = frozenset({".sysml", ".kerml"})
# Proposals with these errors cannot be read at all; other errors are reported.
STRUCTURAL = frozenset(
    {"syntax", "unresolved", "duplicate", "duplicate_requirement_id"}
)
MAX_DIFF = 40_000
MAX_NAMES = 200


def digest(files: Mapping[str, str]) -> str:
    return hashlib.sha256(encode(dict(files)).encode()).hexdigest()


def check_paths(paths: Iterable[str]) -> None:
    for path in paths:
        pure = PurePosixPath(path)
        if (
            str(pure) != path
            or pure.is_absolute()
            or ".." in pure.parts
            or "\\" in path
            or pure.suffix not in SUFFIXES
        ):
            raise ValueError(
                f"Model files need relative .sysml or .kerml paths without '..': {path!r}"
            )


def _number(value: float) -> str:
    return f"{value:.12g}"


def describe(bound: ModelBound) -> str:
    unit = f" {bound.unit}" if bound.unit else ""
    if (
        bound.minimum is not None
        and bound.minimum == bound.maximum
        and not bound.exclusive_minimum | bound.exclusive_maximum
    ):
        return f"{bound.name} == {_number(bound.minimum)}{unit}"
    text = bound.name
    if bound.minimum is not None:
        sign = "<" if bound.exclusive_minimum else "<="
        text = f"{_number(bound.minimum)}{unit} {sign} {text}"
    if bound.maximum is not None:
        sign = "<" if bound.exclusive_maximum else "<="
        text = f"{text} {sign} {_number(bound.maximum)}{unit}"
    return text


def _recorded(constraint: Constraint) -> str:
    return describe(
        ModelBound(
            requirement="",
            metric=constraint.metric,
            name=constraint.metric,
            unit=constraint.unit,
            minimum=constraint.minimum,
            maximum=constraint.maximum,
        )
    )


def within(bound: ModelBound, value: float) -> bool:
    low, high = bound.minimum, bound.maximum
    return not (
        low is not None and (value < low or bound.exclusive_minimum and value == low)
    ) and not (
        high is not None and (value > high or bound.exclusive_maximum and value == high)
    )


def shared_names(bounds: Iterable[ModelBound]) -> set[str]:
    """Names of more than one bounded feature; only qualified keys select those."""
    metrics: defaultdict[str, set[str]] = defaultdict(set)
    for bound in bounds:
        metrics[bound.name].add(bound.metric)
    return {name for name, found in metrics.items() if len(found) > 1}


def matches(key: str, bound: ModelBound, shared: set[str]) -> bool:
    return key == bound.metric or key == bound.name and key not in shared


def violations(
    bounds: Sequence[ModelBound], metrics: Mapping[str, Quantity]
) -> list[str]:
    """Why reported metrics contradict the model's bounds; empty when they agree."""
    shared = shared_names(bounds)
    problems = []
    for key, quantity in sorted(metrics.items()):
        if key in shared:
            options = sorted({b.metric for b in bounds if b.name == key})
            problems.append(
                f"metric {key!r} is ambiguous in the SysML model; use one of {options}"
            )
            continue
        for bound in bounds:
            if not matches(key, bound, shared):
                continue
            if quantity.unit != bound.unit:
                problems.append(
                    f"{key} must be reported in {bound.unit!r}, the unit the SysML "
                    f"model bounds it in, not {quantity.unit!r}"
                )
            elif not within(bound, quantity.value):
                problems.append(
                    f"{key} = {_number(quantity.value)} {quantity.unit} violates "
                    f"{bound.requirement}: {describe(bound)}"
                )
    return list(dict.fromkeys(problems))  # Several requirements may bound one feature.


def _merge(
    requirement: str, bounds: Sequence["Bound"]
) -> tuple[list[ModelBound], list[ModelIssue]]:
    """One tightest interval per bounded feature of a requirement."""
    groups: defaultdict[str, list[Bound]] = defaultdict(list)
    for bound in bounds:
        groups[bound.metric].append(bound)
    merged, issues = [], []
    for metric, group in sorted(groups.items()):
        units = sorted({b.unit for b in group})
        if len(units) > 1:
            issues.append(
                ModelIssue(
                    severity="error",
                    code="inconsistent_units",
                    element=requirement,
                    detail=f"{metric} is bounded in units {units}; use one unit",
                )
            )
            continue
        low = high = None
        open_low = open_high = False
        for b in group:
            if b.op in {">=", ">", "=="} and (
                low is None or b.value > low or b.value == low and b.op == ">"
            ):
                low, open_low = b.value, b.op == ">"
            if b.op in {"<=", "<", "=="} and (
                high is None or b.value < high or b.value == high and b.op == "<"
            ):
                high, open_high = b.value, b.op == "<"
        bound = ModelBound(
            requirement=requirement,
            metric=metric,
            name=group[0].name,
            unit=units[0],
            minimum=low,
            maximum=high,
            exclusive_minimum=open_low,
            exclusive_maximum=open_high,
        )
        merged.append(bound)
        if (
            low is not None
            and high is not None
            and (low > high or low == high and open_low | open_high)
        ):
            issues.append(
                ModelIssue(
                    severity="error",
                    code="contradictory_bounds",
                    element=requirement,
                    detail=f"No value satisfies {describe(bound)}",
                )
            )
    return merged, issues


def _agreement(record: Requirement, bounds: list[ModelBound]) -> list[ModelIssue]:
    """The modeled bound must state exactly the recorded constraint."""
    constraint = record.constraint
    assert constraint is not None
    shared = shared_names(bounds)
    found = [b for b in bounds if matches(constraint.metric, b, shared)]
    if not found:
        detail = (
            f"Recorded constraint {_recorded(constraint)} needs a require constraint "
            f"on a feature named {constraint.metric!r}"
        )
    elif (
        found[0].unit,
        found[0].minimum,
        found[0].maximum,
        found[0].exclusive_minimum or found[0].exclusive_maximum,
    ) != (constraint.unit, constraint.minimum, constraint.maximum, False):
        detail = (
            f"Modeled bound {describe(found[0])} differs from recorded constraint "
            f"{_recorded(constraint)}"
        )
    else:
        return []
    return [
        ModelIssue(
            severity="error",
            code="constraint_mismatch",
            element=record.id,
            detail=detail,
        )
    ]


def _unparsed(files: Mapping[str, str], reason: str) -> ModelReport:
    file = reason.split(" ", 1)[0]
    return ModelReport(
        valid=False,
        digest=digest(files),
        issues=(
            ModelIssue(
                severity="error",
                code="syntax",
                element=file if file in files else "model",
                detail=reason,
            ),
        ),
    )


def _report(
    adapter: "SysMLAdapter",
    files: Mapping[str, str],
    requirements: Sequence[Requirement],
) -> ModelReport:
    issues = [
        ModelIssue(severity="error", code=code, element=element, detail=detail)
        for code, element, detail in adapter.problems()
    ]
    infos = adapter.get_requirements()
    ids = {info.element: info.id for info in infos}
    declared = {}
    unchecked = set()
    for info in infos:
        unchecked.update((info.id or info.element, text) for text in info.unchecked)
        if info.id is None:
            issues.append(
                ModelIssue(
                    severity="warning",
                    code="untraced_requirement",
                    element=info.element,
                    detail="Give it a short-name ID: requirement <'ID'> name { ... }",
                )
            )
        elif not info.declared:
            continue
        elif info.id in declared:
            issues.append(
                ModelIssue(
                    severity="error",
                    code="duplicate_requirement_id",
                    element=info.element,
                    detail=f"{declared[info.id].element} already has ID {info.id}",
                )
            )
        else:
            declared[info.id] = info
    issues.extend(
        ModelIssue(severity="warning", code="unchecked_constraint", element=e, detail=d)
        for e, d in sorted(unchecked)
    )
    records = {r.id: r for r in requirements}
    modeled, bounds = [], []
    for id, info in sorted(declared.items()):
        parent = ids.get(info.parent) if info.parent else None
        modeled.append(
            ModeledRequirement(
                id=id, element=info.element, text=info.text, parent=parent
            )
        )
        if parent is None and id not in records:
            issues.append(
                ModelIssue(
                    severity="error",
                    code="unrecorded_requirement",
                    element=id,
                    detail="Top-level requirements must be recorded requirements; "
                    "nest a derived requirement inside the requirement it refines",
                )
            )
        merged, problems = _merge(id, info.bounds)
        bounds.extend(merged)
        issues.extend(problems)
    for record in requirements:
        info = declared.get(record.id)
        if info is None:
            issues.append(
                ModelIssue(
                    severity="error",
                    code="unmodeled_requirement",
                    element=record.id,
                    detail=f"Model it as requirement <'{record.id}'> with its recorded "
                    "wording",
                )
            )
            continue
        if " ".join(record.wording.split()) not in " ".join(info.text.split()):
            issues.append(
                ModelIssue(
                    severity="warning",
                    code="wording_mismatch",
                    element=record.id,
                    detail="The requirement's doc text omits its recorded wording",
                )
            )
        if record.constraint is not None:
            issues.extend(
                _agreement(record, [b for b in bounds if b.requirement == record.id])
            )
    satisfactions = []
    for claim in adapter.get_satisfactions():
        if claim.requirement is None:
            issues.append(
                ModelIssue(
                    severity="warning",
                    code="unknown_satisfaction",
                    element=claim.element or "model",
                    detail="The SysML Toolkit cannot name the satisfied requirement",
                )
            )
            continue
        label = claim.requirement.id or claim.requirement.element
        merged, _ = _merge(label, claim.requirement.bounds)
        readings = {b.metric: value for b, value in claim.readings}
        problems, unknown = [], []
        for bound in merged:
            value = readings.get(bound.metric)
            if value is None:
                unknown.append(f"{bound.name} has no value")
            elif value[1] != bound.unit:
                unknown.append(
                    f"{bound.name} is in {value[1]!r}, not {bound.unit!r} as bounded"
                )
            elif not within(bound, value[0]):
                problems.append(
                    f"{bound.name} = {_number(value[0])} {value[1]} violates "
                    f"{describe(bound)}"
                )
        if claim.element is None:
            status, detail = "unverified", "No satisfying element"
        elif not merged:
            status, detail = "unverified", "The requirement has no checkable bound"
        elif problems:
            status, detail = "violated", "; ".join(problems)
            issues.append(
                ModelIssue(
                    severity="error",
                    code="satisfaction_violated",
                    element=f"{label} by {claim.element}",
                    detail=detail,
                )
            )
        elif unknown:
            status, detail = "unverified", "; ".join(unknown)
        else:
            status, detail = "satisfied", "; ".join(describe(b) for b in merged)
        satisfactions.append(
            Satisfaction(
                requirement=label,
                element=claim.element or "",
                status=status,
                detail=detail,
            )
        )
    return ModelReport(
        valid=not any(i.severity == "error" for i in issues),
        digest=digest(files),
        elements=len(adapter.model.all()),
        requirements=tuple(modeled),
        bounds=tuple(sorted(bounds, key=lambda b: (b.requirement, b.metric))),
        satisfactions=tuple(
            sorted(satisfactions, key=lambda s: (s.requirement, s.element))
        ),
        issues=tuple(
            sorted(
                issues,
                key=lambda i: (i.severity != "error", i.code, i.element, i.detail),
            )
        ),
    )


def validate(
    files: Mapping[str, str], requirements: Sequence[Requirement]
) -> ModelReport:
    """Parse with the SysML Toolkit and check the model against requirement records."""
    from .adapter import LOCK, ModelLoadError, SysMLAdapter

    with LOCK:
        try:
            adapter = SysMLAdapter.load(files)
        except ModelLoadError as exc:
            return _unparsed(files, str(exc))
        with adapter:
            return _report(adapter, files, requirements)


def _capped(names: Sequence[str]) -> tuple[str, ...]:
    if len(names) <= MAX_NAMES:
        return tuple(names)
    return (*names[:MAX_NAMES], f"... {len(names) - MAX_NAMES} more")


def _text(text: str) -> list[str]:
    return (text if not text or text.endswith("\n") else text + "\n").splitlines(
        keepends=True
    )


def changes(
    base: Mapping[str, str],
    files: Mapping[str, str],
    base_report: ModelReport,
    report: ModelReport,
    added: Sequence[str] = (),
    removed: Sequence[str] = (),
) -> ModelChanges:
    """What a proposed model changes: files, requirements, bounds and elements."""
    paths = sorted(p for p in base.keys() | files.keys() if base.get(p) != files.get(p))
    diff = "".join(
        line
        for path in paths
        for line in difflib.unified_diff(
            _text(base.get(path, "")),
            _text(files.get(path, "")),
            fromfile=f"a/{path}" if path in base else "/dev/null",
            tofile=f"b/{path}" if path in files else "/dev/null",
        )
    )
    if len(diff) > MAX_DIFF:
        diff = diff[:MAX_DIFF] + "\n... diff truncated; read the amendment files\n"
    old = {r.id for r in base_report.requirements}
    new = {r.id for r in report.requirements}
    lines = [f"Requirement {id} added" for id in sorted(new - old)]
    lines += [f"Requirement {id} removed" for id in sorted(old - new)]
    before = {(b.requirement, b.metric): b for b in base_report.bounds}
    after = {(b.requirement, b.metric): b for b in report.bounds}
    for key in sorted(before.keys() | after.keys()):
        if before.get(key) != after.get(key):
            was, now = before.get(key), after.get(key)
            lines.append(
                f"{key[0]}: {describe(was) if was else 'no bound on ' + key[1]} -> "
                f"{describe(now) if now else 'no bound'}"
            )
    return ModelChanges(
        files=tuple(paths),
        requirements=tuple(lines),
        elements_added=_capped(added),
        elements_removed=_capped(removed),
        diff=diff,
    )


def propose(
    base: Mapping[str, str],
    files: Mapping[str, str],
    base_report: ModelReport,
    requirements: Sequence[Requirement],
) -> tuple[ModelReport, ModelChanges]:
    """Validate a proposed model and describe how it differs from the base model."""
    from .adapter import LOCK, ModelLoadError, SysMLAdapter

    with LOCK:
        try:
            after = SysMLAdapter.load(files)
        except ModelLoadError as exc:
            report = _unparsed(files, str(exc))
            return report, changes(base, files, base_report, report)
        with after:
            report = _report(after, files, requirements)
            with SysMLAdapter.load(base) as before:
                added, removed = before.analyse_change(after)
    return report, changes(base, files, base_report, report, added, removed)
