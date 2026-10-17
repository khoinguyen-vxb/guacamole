"""The part-instance tree a SysML revision implies, read through the SysML Toolkit.

A pure function of the model text, so one revision always yields one tree. Each
part usage owned by a package roots a tree. A usage's parts are its own nested
parts, plus those declared by its definitions (and their supertypes) and by the
features it redefines or subsets, less the ones it redefines. The Toolkit does not
compute inherited features, so this walks those relationships itself.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pxr import Tf

from ..sysml.adapter import (
    LOCK,
    SysMLAdapter,
    _owned,
    _qualified,
    _read,
    _relationships,
)

ROOT = "Twin"
MAX_PARTS = 20_000
# Relationships through which an element inherits parts, and the end that gives them.
SOURCES = (
    ("FeatureTyping", "type"),
    ("Subclassification", "general"),
    ("Redefinition", "redefinedFeature"),
    ("Subsetting", "subsettedFeature"),
)


@dataclass(frozen=True)
class Node:
    prim: str  # USD path, e.g. /Twin/Hopper/vehicle/engine
    kind: str  # "package" or "part"
    element: str  # Qualified name of the declaring SysML element
    element_id: str
    feature_path: str  # The instance in SysML terms, e.g. Hopper::vehicle.engine
    definitions: tuple[str, ...] = ()
    multiplicity: str = ""
    recursive: bool = False  # Recursive composition; its parts are not expanded


def _name(element: Any) -> str:
    return str(_read(element, "name", "")) or f"part_{element.element_id[:8]}"


def _sysml(name: str) -> str:
    """name as SysML writes it: unrestricted names are quoted."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else f"'{name}'"


def _parts(owner: Any) -> list[Any]:
    return [
        f
        for m in _relationships(owner, "FeatureMembership")
        if (f := _owned(m)) is not None and f.metaclass_name == "PartUsage"
    ]


def _sources(element: Any) -> list[Any]:
    return [
        target
        for kind, end in SOURCES
        for r in _relationships(element, kind)
        if (target := _read(r, end)) is not None
        and not _read(target, "isLibraryElement", False)
    ]


def _effective(element: Any, chain: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Name -> declaring PartUsage, for every part an instance of element has."""
    if element.element_id in chain:
        return {}
    chain |= {element.element_id}
    found: dict[str, Any] = {}
    for source in _sources(element):
        for name, part in _effective(source, chain).items():
            found.setdefault(name, part)
    for part in _parts(element):
        redefined = {
            target.element_id
            for r in _relationships(part, "Redefinition")
            if (target := _read(r, "redefinedFeature")) is not None
        }
        found = {n: p for n, p in found.items() if p.element_id not in redefined}
        found[_name(part)] = part
    return found


def _bound(literal: Any) -> str | None:
    if literal is None:
        return None
    if literal.metaclass_name == "LiteralInfinity":
        return "*"
    value = _read(literal, "value")
    return "?" if value is None else str(value)


def _multiplicity(part: Any) -> str:
    multiplicity = _read(part, "multiplicity")
    if multiplicity is None:
        return ""
    low = _bound(_read(multiplicity, "lowerBound"))
    high = _bound(_read(multiplicity, "upperBound"))
    if high is None:
        return ""
    return high if low is None else f"{low}..{high}"


def _definitions(part: Any) -> tuple[str, ...]:
    return tuple(
        sorted(
            _qualified(d)
            for d in _read(part, "definition", [])
            if not _read(d, "isLibraryElement", False)
        )
    )


def _prim_names(elements: Mapping[str, Any]) -> dict[str, str]:
    """Valid, unique USD names for sibling elements, keyed by SysML name."""
    names: dict[str, str] = {}
    taken: set[str] = set()
    for name, element in sorted(elements.items()):
        prim = Tf.MakeValidIdentifier(name)
        if prim in taken:
            prim = f"{prim}_{element.element_id[:8]}"
        taken.add(prim)
        names[name] = prim
    return names


def _packages(element: Any) -> list[Any]:
    """The named packages enclosing element, outermost first."""
    packages = []
    owner = _read(element, "owningNamespace")
    while owner is not None and _read(owner, "name"):
        packages.append(owner)
        owner = _read(owner, "owningNamespace")
    return packages[::-1]


def derive(files: Mapping[str, str]) -> tuple[Node, ...]:
    """Every package scope and part instance, parents before children."""
    with LOCK, SysMLAdapter.load(files) as adapter:
        roots = [
            e
            for e in adapter.model.all()
            if e.metaclass_name == "PartUsage"
            and not _read(e, "isLibraryElement", False)
            and _read(_read(e, "owningNamespace"), "metaclass_name")
            in {"Package", None}
            and _read(e, "owningType") is None
        ]
        nodes: dict[str, Node] = {}
        tops: dict[str, dict[str, Any]] = {}
        for root in roots:
            path = f"/{ROOT}"
            for package in _packages(root):
                path += "/" + Tf.MakeValidIdentifier(_name(package))
                nodes.setdefault(
                    path,
                    Node(
                        prim=path,
                        kind="package",
                        element=_qualified(package),
                        element_id=package.element_id,
                        feature_path=_qualified(package),
                    ),
                )
            tops.setdefault(path, {})[_name(root)] = root

        def expand(prim: str, part: Any, feature: str, ancestors: frozenset[str]):
            if len(nodes) >= MAX_PARTS:
                raise ValueError(
                    f"The twin would exceed {MAX_PARTS} parts; check for unbounded "
                    "composition in the SysML model"
                )
            recursive = part.element_id in ancestors
            nodes[prim] = Node(
                prim=prim,
                kind="part",
                element=_qualified(part),
                element_id=part.element_id,
                feature_path=feature,
                definitions=_definitions(part),
                multiplicity=_multiplicity(part),
                recursive=recursive,
            )
            if recursive:
                return
            children = _effective(part)
            for name, prim_name in _prim_names(children).items():
                expand(
                    f"{prim}/{prim_name}",
                    children[name],
                    f"{feature}.{_sysml(name)}",
                    ancestors | {part.element_id},
                )

        for scope, parts in sorted(tops.items()):
            for name, prim_name in _prim_names(parts).items():
                expand(
                    f"{scope}/{prim_name}",
                    parts[name],
                    _qualified(parts[name]),
                    frozenset(),
                )
    return tuple(nodes[p] for p in sorted(nodes))
