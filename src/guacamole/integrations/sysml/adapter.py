"""Read SysML v2 text through the OpenMBEE SysML Toolkit (the `sysml` SDK).

Every reading is a deterministic function of the model text and the standard library
carried by the installed wheel. Judgement over these readings lives in validator.py.
"""

import os
import sys
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

import sysml
from sysml.base import SdkError, UnresolvedReference

# The Toolkit's standard-library cache and its stderr diagnostics are process-wide.
LOCK = threading.RLock()

COMPARISONS = frozenset({"<", "<=", ">", ">=", "=="})
FLIPPED = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "=="}
REQUIREMENTS = frozenset({"RequirementUsage", "RequirementDefinition"})
type Value = tuple[float, str]  # Number and unit symbol; "" is dimensionless


class ModelLoadError(ValueError):
    """The SysML Toolkit could not load the files; its own reason is the message."""


class Unchecked(ValueError):
    """A constraint whose form cannot be evaluated deterministically."""


@dataclass(frozen=True)
class Bound:
    """metric <op> value, read from one required constraint."""

    metric: str
    name: str
    op: str
    value: float
    unit: str


@dataclass
class RequirementInfo:
    element: str
    id: str | None
    declared: bool  # The ID is this element's own short name, not its definition's
    text: str
    parent: str | None  # Enclosing requirement element of a derived requirement
    bounds: list[Bound] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)


@dataclass
class SatisfyInfo:
    requirement: RequirementInfo | None  # None when the Toolkit cannot name it
    element: str | None
    readings: list[tuple[Bound, Value | None]] = field(default_factory=list)


def _read(element: Any, name: str, default: Any = None) -> Any:
    """A property the Toolkit may not answer, or this metaclass may not have."""
    try:
        value = getattr(element, name)
    except (SdkError, AttributeError):
        return default
    return default if value is None else value


def _qualified(element: Any) -> str:
    return str(_read(element, "qualifiedName", ""))


def _label(element: Any) -> str:
    return _qualified(element) or f"<{element.metaclass_name} {element.element_id}>"


def _relationships(element: Any, metaclass: str) -> list[Any]:
    return [
        r
        for r in _read(element, "ownedRelationship", [])
        if r.metaclass_name == metaclass
    ]


def _owned(relationship: Any) -> Any:
    related = _read(relationship, "ownedRelatedElement", [])
    return related[0] if related else None


def _value(feature: Any) -> Any:
    """The expression bound to a feature by `= ...` or `:= ...`."""
    for membership in _relationships(feature, "FeatureValue"):
        return _owned(membership)
    return None


def _arguments(expression: Any) -> list[Any]:
    return [
        _value(_owned(m)) for m in _relationships(expression, "ParameterMembership")
    ]


def _operator(expression: Any) -> str | None:
    if expression is None or expression.metaclass_name != "OperatorExpression":
        return None
    return str(_read(expression, "operator", ""))


def _unit(expression: Any, top: bool = True) -> str | None:
    """Unit symbol as written: [kg], [m/s^2], [kg/(m*s)]."""
    if expression is None:
        return None
    if expression.metaclass_name == "LiteralInteger":
        return str(_read(expression, "value"))
    if expression.metaclass_name == "FeatureReferenceExpression":
        unit = _read(expression, "referent")
        symbol = _read(unit, "declaredShortName") or _read(unit, "name")
        return str(symbol) if symbol else None
    operator, arguments = _operator(expression), _arguments(expression)
    if operator not in {"*", "/", "^", "**"} or len(arguments) != 2:
        return None
    left, right = (_unit(a, top=False) for a in arguments)
    if left is None or right is None:
        return None
    if operator in {"^", "**"}:
        return f"{left}^{right}"
    return f"{left}{operator}{right}" if top else f"({left}{operator}{right})"


def _evaluate(expression: Any, depth: int = 0) -> Value | None:
    """Literal quantities, unary signs, units and references to valued features."""
    if expression is None or depth > 16:
        return None
    kind = expression.metaclass_name
    if kind in {"LiteralInteger", "LiteralRational"}:
        number = _read(expression, "value")
        return (float(number), "") if isinstance(number, (int, float)) else None
    if kind == "FeatureReferenceExpression":
        return _evaluate(_value(_read(expression, "referent")), depth + 1)
    operator, arguments = _operator(expression), _arguments(expression)
    if operator == "[" and len(arguments) == 2:
        number, unit = _evaluate(arguments[0], depth + 1), _unit(arguments[1])
        if number is None or number[1] or unit is None:
            return None
        return number[0], unit
    if operator in {"-", "+"} and len(arguments) == 1:
        value = _evaluate(arguments[0], depth + 1)
        if value is None:
            return None
        return (-value[0] if operator == "-" else value[0]), value[1]
    return None


def _metric(expression: Any) -> Any:
    """The constrained feature: a subject chain such as v.mass, or an unvalued feature."""
    if expression is None:
        return None
    if expression.metaclass_name == "FeatureChainExpression":
        return _read(expression, "targetFeature")
    if expression.metaclass_name == "FeatureReferenceExpression":
        referent = _read(expression, "referent")
        if referent is not None and _value(referent) is None:
            return referent
    return None


def _comparisons(expression: Any) -> list[Bound]:
    operator = _operator(expression)
    if operator in {"and", "&"}:
        return [b for a in _arguments(expression) for b in _comparisons(a)]
    arguments = _arguments(expression) if operator in COMPARISONS else []
    if len(arguments) == 2:
        left, right = arguments
        assert operator is not None
        for metric, other, op in (
            (_metric(left), right, operator),
            (_metric(right), left, FLIPPED[operator]),
        ):
            value = _evaluate(other)
            if metric is not None and value is not None:
                name = str(_read(metric, "name", "")) or _qualified(metric)
                return [Bound(_qualified(metric) or name, name, op, *value)]
    raise Unchecked(
        "only comparisons of a feature with a literal or valued quantity, "
        "joined by 'and', are machine-checkable"
    )


class SysMLAdapter:
    """One loaded model. Hold LOCK from load() until close()."""

    def __init__(self, model: sysml.Model) -> None:
        self.model = model
        self._requirements: dict[str, RequirementInfo] | None = None

    @classmethod
    def load(cls, files: Mapping[str, str]) -> Self:
        library = sysml.standard_library()
        with tempfile.TemporaryFile() as diagnostics:
            # The Toolkit gives its reason for rejecting a file only on stderr.
            sys.stderr.flush()
            saved = os.dup(2)
            os.dup2(diagnostics.fileno(), 2)
            try:
                model = sysml.Model.from_toolkit(
                    sources=dict(files), library_dir=library
                )
            except SdkError as exc:
                error = str(exc)
            else:
                return cls(model)
            finally:
                os.dup2(saved, 2)
                os.close(saved)
            diagnostics.seek(0)
            reason = diagnostics.read().decode(errors="replace").strip()
        raise ModelLoadError(reason.removeprefix("sysmlv2-abi: load failed: ") or error)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        # Release the Toolkit session now rather than at cyclic garbage collection.
        close = getattr(self.model._backend, "close", None)
        if close is not None:
            close()

    def names(self) -> set[str]:
        return {name for e in self.model.all() if (name := _qualified(e))}

    def problems(self) -> list[tuple[str, str, str]]:
        """(code, element, detail) for unresolved references and duplicate names."""
        problems: list[tuple[str, str, str]] = []
        seen: dict[str, str] = {}
        for element in self.model.all():
            name = _qualified(element)
            if name and seen.setdefault(name, element.element_id) != element.element_id:
                problems.append(("duplicate", name, "Another element has this name"))
            for relationship in _read(element, "ownedRelationship", []):
                try:
                    _ = relationship.target  # Reading a target resolves it.
                except UnresolvedReference as exc:
                    problems.append(("unresolved", _label(element), str(exc)))
                except SdkError:
                    pass  # A target the Toolkit does not compute is not a defect.
        return problems

    def get_requirements(self) -> list[RequirementInfo]:
        if self._requirements is not None:
            return list(self._requirements.values())
        self._requirements = {}
        for element in self.model.all():
            if element.metaclass_name not in REQUIREMENTS:
                continue
            definition = None
            for typing in _relationships(element, "FeatureTyping"):
                typed = _read(typing, "type")
                if typed is not None and typed.metaclass_name in REQUIREMENTS:
                    definition = typed
            own, inherited = _read(element, "reqId"), _read(definition, "reqId")
            texts = _read(element, "text", []) or _read(definition, "text", [])
            owner = _read(element, "owner")
            while owner is not None and owner.metaclass_name not in REQUIREMENTS:
                owner = _read(owner, "owner")
            info = RequirementInfo(
                element=_label(element),
                id=str(own or inherited) if own or inherited else None,
                declared=bool(own),
                text=" ".join(str(t).strip() for t in texts),
                parent=_label(owner) if owner is not None else None,
            )
            for source in (element, definition) if definition else (element,):
                for constraint in _read(source, "requiredConstraint", []):
                    expression = None
                    for membership in _relationships(
                        constraint, "ResultExpressionMembership"
                    ):
                        expression = _owned(membership)
                    try:
                        if expression is None:
                            raise Unchecked("the constraint has no inline expression")
                        info.bounds.extend(
                            b for b in _comparisons(expression) if b not in info.bounds
                        )
                    except Unchecked as exc:
                        info.unchecked.append(f"{_label(constraint)}: {exc}")
            self._requirements[info.element] = info
        return list(self._requirements.values())

    def get_satisfactions(self) -> list[SatisfyInfo]:
        """Each `satisfy R by X`, with X's values for R's bounded features."""
        requirements = {r.element: r for r in self.get_requirements()}
        satisfactions = []
        for satisfy in self.model.all():
            if satisfy.metaclass_name != "SatisfyRequirementUsage" or _read(
                satisfy, "isNegated", False
            ):
                continue
            satisfied = _read(satisfy, "satisfiedRequirement")
            subject = None
            for membership in _relationships(satisfy, "SubjectMembership"):
                subject = _value(_owned(membership))
            element = (
                _read(subject, "referent")
                if subject is not None
                and subject.metaclass_name == "FeatureReferenceExpression"
                else _metric(subject)
            )
            info = SatisfyInfo(
                requirements.get(_label(satisfied)) if satisfied is not None else None,
                _label(element) if element is not None else None,
            )
            if info.requirement is not None and element is not None:
                info.readings = [
                    (b, self._reading(element, b)) for b in info.requirement.bounds
                ]
            satisfactions.append(info)
        return satisfactions

    def _reading(self, element: Any, bound: Bound) -> Value | None:
        """The satisfying element's own or typed value for a bounded feature."""
        features = []
        for owner in (
            element,
            *(_read(t, "type") for t in _relationships(element, "FeatureTyping")),
        ):
            features.extend(
                feature
                for membership in _relationships(owner, "FeatureMembership")
                if (feature := _owned(membership)) is not None
            )
        ranked = []
        for feature in features:
            redefined = {
                _qualified(target)
                for r in _relationships(feature, "Redefinition")
                for target in _read(r, "target", [])
            }
            if _qualified(feature) == bound.metric or bound.metric in redefined:
                ranked.append((0, feature))
            elif _read(feature, "name") == bound.name:
                ranked.append((1, feature))
        for _, feature in sorted(ranked, key=lambda item: item[0]):
            if (value := _evaluate(_value(feature))) is not None:
                return value
        return None

    def analyse_change(self, other: "SysMLAdapter") -> tuple[list[str], list[str]]:
        """Qualified names added and removed going from this model to other."""
        before, after = self.names(), other.names()
        return sorted(after - before), sorted(before - after)
