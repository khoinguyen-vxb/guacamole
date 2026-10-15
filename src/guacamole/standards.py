"""Deterministic standards logic: edition ordering and applicability rules.

A catalogue entry's rule is an expression over the project's facts in a small, safe
subset of Python: names, numbers, strings, booleans, arithmetic, comparisons, `in`,
and `and`, `or` and `not`. A missing fact makes the answer unknown, never false:
`and` is false only when a part is false, `or` true only when a part is true.
"""

import ast
import operator
import re
from collections.abc import Callable, Mapping
from typing import Any, Literal, NamedTuple

from .contracts import Catalogue, Fact, Requirement, Standard

type Answer = bool | None  # None: unknown
type Status = Literal["applies", "does not apply", "unknown", "by selection"]

_ALLOWED = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Tuple,
    ast.List,
)
_ARITHMETIC: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_COMPARE: dict[type, Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}
_UNKNOWN = object()


def edition_key(edition: str) -> tuple[int, ...]:
    """A sortable key for an edition: its year, then any amendment numbers.

    "2010" < "2010 Amdt 1" < "2010+A2:2018" < "2021". An edition without a year sorts
    by its numbers alone, and one without numbers before all others.
    """
    numbers = [int(n) for n in re.findall(r"\d+", edition)]
    year = next((n for n in numbers if 1900 <= n <= 2999), None)
    if year is None:
        return (0, *numbers)
    numbers.remove(year)
    return (year, *numbers)


def parse(rule: str) -> ast.Expression:
    """The rule's syntax tree; ValueError for anything outside the subset."""
    try:
        tree = ast.parse(rule, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Rule {rule!r} is not an expression: {exc.msg}") from None
    outside = next(
        (
            node
            for node in ast.walk(tree)
            if not isinstance(node, _ALLOWED)
            or (
                isinstance(node, ast.Constant)
                and not isinstance(node.value, (int, float, str, bool))
            )
        ),
        None,
    )
    if outside is not None:
        raise ValueError(f"Rule {rule!r} uses {type(outside).__name__}, not allowed")
    return tree


def evaluate(rule: str, facts: Mapping[str, Any]) -> tuple[Answer, tuple[str, ...]]:
    """The rule's answer over the facts, and the names it needed but lacked."""
    missing: list[str] = []

    def value(node: ast.AST) -> Any:
        match node:
            case ast.Expression(body=body):
                return value(body)
            case ast.Constant(value=v):
                return v
            case ast.Name(id=name):
                if name in facts:
                    return facts[name]
                missing.append(name)
                return _UNKNOWN
            case ast.Tuple(elts=items) | ast.List(elts=items):
                values = tuple(value(i) for i in items)
                return _UNKNOWN if _UNKNOWN in values else values
            case ast.UnaryOp(op=op, operand=operand):
                v = value(operand)
                if v is _UNKNOWN:
                    return v
                return (
                    not v
                    if isinstance(op, ast.Not)
                    else -v
                    if isinstance(op, ast.USub)
                    else v
                )
            case ast.BinOp(left=left, op=op, right=right):
                a, b = value(left), value(right)
                return _UNKNOWN if _UNKNOWN in (a, b) else _ARITHMETIC[type(op)](a, b)
            case ast.BoolOp(op=op, values=parts):
                answers = [value(p) for p in parts]
                decisive = not isinstance(op, ast.And)  # False decides and; True, or
                if any(a is not _UNKNOWN and bool(a) == decisive for a in answers):
                    return decisive
                return _UNKNOWN if _UNKNOWN in answers else not decisive
            case ast.Compare(left=left, ops=ops, comparators=rights):
                operands = [value(left), *(value(r) for r in rights)]
                answers = [
                    _UNKNOWN if _UNKNOWN in (a, b) else _COMPARE[type(op)](a, b)
                    for op, a, b in zip(ops, operands, operands[1:])
                ]
                if False in answers:
                    return False
                return _UNKNOWN if _UNKNOWN in answers else True
        raise ValueError(f"Rule {rule!r} uses {type(node).__name__}, not allowed")

    try:
        answer = value(parse(rule))
    except (TypeError, ArithmeticError) as exc:  # A word against a number, 1 / 0
        raise ValueError(f"Rule {rule!r} cannot use its facts: {exc}") from None
    return (None if answer is _UNKNOWN else bool(answer)), tuple(dict.fromkeys(missing))


class Applicability(NamedTuple):
    """One catalogue standard's status for the project. See assess()."""

    standard: str
    status: Status
    mandatory: bool
    missing: tuple[str, ...]  # Facts the rule lacked, with why
    selected: str | None  # The selecting requirement's id
    edition: str | None  # The selected edition
    latest: str  # The catalogue's latest edition

    @property
    def superseded(self) -> bool:
        """Whether the selected edition is older than the catalogue's latest."""
        return self.edition is not None and edition_key(self.edition) < edition_key(
            self.latest
        )


def facts(requirements: list[Requirement]) -> dict[str, Fact | str]:
    """Facts by name from current requirements; a name stated twice differently is
    a conflict, given as its explanation instead of a fact."""
    found: dict[str, Fact | str] = {}
    for r in requirements:
        if r.fact is None or r.withdrawn:
            continue
        name = r.fact.name
        if name in found and found[name] != r.fact:
            found[name] = f"{name} (stated differently by more than one requirement)"
        else:
            found.setdefault(name, r.fact)
    return found


def assess(
    catalogue: Catalogue, requirements: list[Requirement]
) -> list[Applicability]:
    """Each catalogue standard's applicability from the current requirements' facts.

    A fact stated in a unit other than the one the rule reads counts as missing: the
    systems engineer restates it, as every comparison in the runtime is in the unit
    its bound names. An entry without a rule applies by human selection only.
    """
    stated = facts(requirements)
    selections: dict[str, tuple[str, Standard]] = {
        squash(r.standard.id): (r.id, r.standard)
        for r in requirements
        if r.standard and not r.withdrawn
    }
    out = []
    for entry in catalogue.entries:
        values: dict[str, Any] = {}
        notes: list[str] = []
        for name, fact in stated.items():
            if isinstance(fact, str):
                notes.append(fact)
            elif name in entry.units and fact.unit != entry.units[name]:
                notes.append(
                    f"{name} (stated in {fact.unit or 'no unit'}; the rule reads "
                    f"{entry.units[name] or 'no unit'})"
                )
            else:
                values[name] = fact.value
        status: Status = "by selection"
        reasons: tuple[str, ...] = ()
        if entry.applies_when:
            try:
                answer, missing = evaluate(entry.applies_when, values)
            except ValueError as exc:  # Unknown, with why, rather than no review
                answer, missing = None, (str(exc),)
            status = (
                "unknown"
                if answer is None
                else "applies"
                if answer
                else "does not apply"
            )
            reasons = tuple(
                next((n for n in notes if n.startswith(f"{m} ")), m) for m in missing
            )
        selection = selections.get(squash(entry.id))
        latest = max(entry.editions, key=edition_key)
        out.append(
            Applicability(
                entry.id,
                status,
                entry.mandatory,
                reasons,
                selection[0] if selection else None,
                selection[1].edition if selection else None,
                latest,
            )
        )
    return out


def squash(text: str) -> str:
    return "".join(text.split()).casefold()
