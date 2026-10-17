"""Editions: which element of a new snapshot is which of an old one, and what changed.

Alignment runs in passes, like a rename detector: the same ID with similar text,
then the same heading, then similar text alone; the rest are new or deleted.
Similarity is only for matching. Whether a change matters is decided by fixed
rules over the exact token difference (modal verbs, numbers, comparisons, scope
words, references), never by how similar the texts are: a 97%-similar clause
that turned "shall" into "should" is a significant change.
"""

import difflib
import re
from collections.abc import Sequence

from ..contracts import Element, ElementChange

# "3.3.1 ", "Section 3 ", "TABLE 3.3.1(B) ", "A-5.1 " leading an element's text.
_LABEL = re.compile(
    r"^(?:(?:SECTION|Section|APPENDIX|TABLE|Table|FIGURE|Figure)\s+)?"
    r"(?:[A-Z]-|[IVX]+-)?\d+(?:[.-]\d+)*(?:\([A-Z]\))?\s+"
)
_TOKEN = re.compile(r"\d+(?:[.,-]\d+)*|[^\W\d_]+|[<>≤≥=±]")
MODALS = {"shall", "should", "may", "must", "will", "can", "need", "required"}
SCOPE = {"not", "no", "all", "any", "only", "except", "unless", "each", "every", "none"}
COMPARISONS = {
    "less", "more", "greater", "least", "most", "maximum", "minimum", "exceed",
    "exceeds", "below", "above", "within", "<", ">", "≤", "≥", "±",
}  # fmt: skip


def _tokens(element: Element) -> list[str]:
    """Words and numbers, without the number labelling the element, which a new
    edition may change while the provision stays the same."""
    return _TOKEN.findall(_LABEL.sub("", element.text, count=1).casefold())


def _similarity(a: list[str], b: list[str]) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _shingles(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + 3]) for i in range(max(1, len(tokens) - 2))}


def significance(old: Element, new: Element) -> tuple[str, ...]:
    """Why a change matters, by rule; empty when it is wording alone."""
    a, b = _tokens(old), _tokens(new)
    reasons = []
    for op, i, j, k, m in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if op == "equal":
            continue
        removed, added = a[i:j], b[k:m]
        changed = set(removed) | set(added)
        shown = f"{' '.join(removed) or '∅'} → {' '.join(added) or '∅'}"
        if changed & MODALS:
            reasons.append(f"obligation: {shown}")
        elif any(t[:1].isdigit() for t in changed):
            reasons.append(f"value: {shown}")
        elif changed & COMPARISONS:
            reasons.append(f"limit: {shown}")
        elif changed & SCOPE:
            reasons.append(f"scope: {shown}")
    old_refs = {(l.type, l.target) for l in old.links if l.type != "uses"}
    new_refs = {(l.type, l.target) for l in new.links if l.type != "uses"}
    if old_refs != new_refs:
        gone = sorted(t for _, t in old_refs - new_refs)
        came = sorted(t for _, t in new_refs - old_refs)
        reasons.append(f"references: -{gone} +{came}")
    if old.kind != new.kind:
        reasons.append(f"kind: {old.kind} → {new.kind}")
    # A definition's every word is its meaning.
    if old.kind == "definition" and a != b and not reasons:
        reasons.append("definition reworded")
    return tuple(dict.fromkeys(reasons))


def align(old: Sequence[Element], new: Sequence[Element]) -> tuple[ElementChange, ...]:
    """Every element of either snapshot, matched where it can be, with what changed."""
    tokens = {("old", e.id): _tokens(e) for e in old} | {
        ("new", e.id): _tokens(e) for e in new
    }
    old_by, new_by = {e.id: e for e in old}, {e.id: e for e in new}
    pairs: dict[str, tuple[str, float]] = {}  # old id -> (new id, similarity)
    taken: set[str] = set()

    def pair(o: str, n: str, similarity: float) -> None:
        pairs[o] = (n, similarity)
        taken.add(n)

    # 1. The same ID, still recognisably the same text.
    for o, e in old_by.items():
        if o in new_by:
            similarity = _similarity(tokens["old", o], tokens["new", o])
            if similarity >= 0.5 or e.heading == new_by[o].heading != "":
                pair(o, o, similarity)
    # 2. Renumbered under the same heading.
    headings: dict[tuple[str, str], list[str]] = {}
    for n, e in new_by.items():
        if n not in taken and e.heading:
            headings.setdefault((e.kind, e.heading.casefold()), []).append(n)
    for o, e in old_by.items():
        candidates = [
            n
            for n in headings.get((e.kind, e.heading.casefold()), [])
            if n not in taken
        ]
        if o not in pairs and len(candidates) == 1:
            n = candidates[0]
            pair(o, n, _similarity(tokens["old", o], tokens["new", n]))
    # 3. Similar text alone, best match first.
    shingles = {key: _shingles(t) for key, t in tokens.items()}
    scored = []
    for o, e in old_by.items():
        if o in pairs or not tokens["old", o]:
            continue
        for n, f in new_by.items():
            if n in taken or e.kind != f.kind:
                continue
            a, b = shingles["old", o], shingles["new", n]
            if len(a & b) / len(a | b) >= 0.4:
                scored.append((_similarity(tokens["old", o], tokens["new", n]), o, n))
    for similarity, o, n in sorted(scored, reverse=True):
        if o not in pairs and n not in taken and similarity >= 0.75:
            pair(o, n, similarity)

    changes = []
    for o, e in old_by.items():
        if o not in pairs:
            changes.append(ElementChange(old=o, change="deleted"))
            continue
        n, similarity = pairs[o]
        reasons = significance(e, new_by[n])
        same = tokens["old", o] == tokens["new", n] and not reasons
        change = "unchanged" if same and o == n else "moved" if o != n else "modified"
        changes.append(
            ElementChange(
                old=o,
                new=n,
                change=change,
                similarity=round(similarity, 3),
                reasons=reasons,
            )
        )
    changes += [ElementChange(new=n, change="new") for n in new_by if n not in taken]
    return tuple(changes)
