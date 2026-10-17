"""Profiles: how a family of documents divides into elements and links them.

A profile scores how well it fits a parsed document and builds its element tree;
the best fit is used unless one is named. The fallback fits anything, as pages and
paragraphs without links, so no PDF is refused.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from ..contracts import Element, Link, LinkType, Provenance
from .parsing import Block


class Profile(Protocol):
    name: str  # name@version, recorded on each snapshot

    def fit(self, blocks: tuple[Block, ...]) -> float: ...

    def structure(self, blocks: tuple[Block, ...]) -> tuple[Element, ...]: ...

    def link(self, elements: tuple[Element, ...]) -> tuple[Element, ...]:
        """The elements with their links found again, after an amendment."""
        ...


@dataclass
class _Draft:
    id: str
    parent: str | None
    kind: str
    heading: str = ""
    lines: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    def add(self, block: Block, text: str | None = None) -> None:
        self.lines.append(block.text if text is None else text)
        self.blocks.append(block)


def _provenance(blocks: list[Block]) -> tuple[Provenance, ...]:
    """Each block's page and box; text-only blocks collapse to one entry a page."""
    seen = {}
    for b in blocks:
        key = (b.page, b.bbox)
        seen.setdefault(key, Provenance(page=b.page, bbox=b.bbox))
    return tuple(seen.values())


def _paragraphs(blocks: list[Block]) -> list[list[Block]]:
    """Laid-out blocks are paragraphs already; text-layer lines join until a sentence ends."""
    paragraphs: list[list[Block]] = []
    open_ = False
    for block in blocks:
        if block.bbox is not None or not open_:
            paragraphs.append([block])
        else:
            paragraphs[-1].append(block)
        open_ = block.bbox is None and not block.text.endswith(
            (".", ":", ";", "?", "!")
        )
    return paragraphs


class FallbackProfile:
    """Any PDF: an element per page and per paragraph, with no links."""

    name = "fallback@1"

    def fit(self, blocks: tuple[Block, ...]) -> float:
        return 0.05  # Every other profile that recognises the document beats it

    def structure(self, blocks: tuple[Block, ...]) -> tuple[Element, ...]:
        pages: dict[int, list[Block]] = {}
        for block in blocks:
            pages.setdefault(block.page, []).append(block)
        elements = []
        for number, page in pages.items():
            paragraphs = _paragraphs(page)
            texts = ["\n".join(b.text for b in p) for p in paragraphs]
            elements.append(
                Element(
                    id=f"p{number}",
                    kind="page",
                    text="\n\n".join(texts),
                    provenance=(Provenance(page=number),),
                )
            )
            elements += [
                Element(
                    id=f"p{number}.{i}",
                    parent=f"p{number}",
                    kind="paragraph",
                    text=text,
                    provenance=_provenance(paragraph),
                )
                for i, (text, paragraph) in enumerate(
                    zip(texts, paragraphs, strict=True), start=1
                )
            ]
        return tuple(elements)

    def link(self, elements: tuple[Element, ...]) -> tuple[Element, ...]:
        return elements  # Pages and paragraphs have no links


_NUMBER = r"\d{1,2}(?:\.\d{1,3}){1,5}"
_CLAUSE = re.compile(rf"^({_NUMBER})\s+(?=[A-Z(“\"])(.*)$")
# "SECTION 3 DESIGN", "Section 3" with its title on the next line, or "3 DESIGN".
_SECTION = re.compile(
    r"^(?:(?:SECTION|Section)\s+(\d{1,2})\b[\s:.—–-]*(.*)|(\d{1,2})\s+([A-Z][A-Z ,&-]{2,}))$"
)
# "APPENDIX B", "MANDATORY APPENDIX I", "NONMANDATORY APPENDIX A": a nonmandatory
# appendix and everything in it is informative.
_APPENDIX = re.compile(r"^(?:(NON)?MANDATORY\s+)?APPENDIX\s+([A-Z]|[IVX]+)\b\s*(.*)$")
_APPENDIX_CLAUSE = re.compile(
    r"^((?:[A-Z]|[IVX]+)-\d{1,2}(?:\.\d{1,3}){0,4})\s+(?=[A-Z(“\"])(.*)$"
)
# 3.3.1(B), 4-12, B-2; a cited "10-" may wrap before its "11".
_CAPTION_NUMBER = r"[A-Z]?\d+(?:\.\d+|[\-–]\s?\d+)*(?:\([A-Z]\))?"
_CAPTION = re.compile(rf"^(TABLE|FIGURE)\s+({_CAPTION_NUMBER})\s*(.*)$")
_CAPTION_ANY = re.compile(_CAPTION.pattern, re.IGNORECASE)
_NOTE = re.compile(r"^(NOTES?|EXAMPLES?)\b")
# A contents or list-of-figures entry: "3.3.1 Title .... 41", "Title . . . 41".
_LEADERS = re.compile(r"(?:\.\s?){3,}\s*\d*\s*$|\s\.\s\d{1,4}\s*$")
_DEFINITIONS = re.compile(r"\bdefinitions?\b", re.IGNORECASE)
_TERM = re.compile(r"^(.{3,60}?)\s*(?:—|–|:| - )")
# A clause number after a word that cites one; "Clause" and "para." cite even
# when unresolved, the others only when the number is an element (not a value).
_CITE = re.compile(
    r"\b(?:(?P<strong>[Cc]lauses?|[Ss]ubclauses?|[Ss]ubsections?|[Ss]ections?"
    r"|[Pp]aragraphs?|[Pp]aras?\.?)"
    rf"|(?P<weak>see|in|with|under|per|to|and|or|of))\s+(?P<id>{_NUMBER})\b"
)
# Further numbers in a cited list: "paras. 1.4.1, 1.4.2 through 1.4.10".
_CITE_MORE = re.compile(rf"(?:,\s*|\s+(?:and|or|through|to)\s+)({_NUMBER})\b")
_CITE_CAPTION = re.compile(rf"\b(Table|Figure)\s+({_CAPTION_NUMBER})")
_CITE_APPENDIX = re.compile(r"\bAppendix\s+([A-Z])\b")
# Words that make a citation an exception: read the two together. ("Other than"
# mostly narrows scope, so it is not one.)
_EXCEPTION = re.compile(
    r"\b(?:except|exceptions?|unless|notwithstanding|in lieu of|overrides?"
    r"|(?:does|do) not apply|not applicable|need not|(?:is|are) not required"
    r"|may be omitted)\b",
    re.IGNORECASE,
)
# A provision cited by name: "Rule #1: The Envelope Principle".
_NAMED = re.compile(r"^([A-Z][A-Za-z]+\s+#?\d+[A-Za-z]?)\s*:")
# Where a laid-out paragraph runs a note or caption on after a sentence.
_RUN_ON = re.compile(
    r"(?<=[.:])\s+(?=(?:NOTES?|EXAMPLES?)\b|(?:TABLE|FIGURE)\s+[A-Z]?\d)"
)


def _split(blocks: tuple[Block, ...]) -> list[Block]:
    """Blocks without contents pages, split where a note or caption begins mid-block.

    A page where at least a quarter of the lines end in leaders is a contents or
    list of figures, whose wrapped entries would otherwise read as clauses.
    """
    pages: dict[int, list[Block]] = {}
    for block in blocks:
        pages.setdefault(block.page, []).append(block)
    contents = {
        page
        for page, on in pages.items()
        if len(on) >= 4
        and sum(bool(_LEADERS.search(b.text)) for b in on) >= len(on) / 4
    }
    split = []
    for block in blocks:
        if block.page in contents:
            continue
        if block.kind != "text" or block.bbox is None:
            split.append(block)
            continue
        split += [block._replace(text=part) for part in _RUN_ON.split(block.text)]
    return split


class NumberedClauseProfile:
    """Standards numbered by clause (AS, ISO, EN): 3.3.1, Table 3.3.1(B), Appendix B.

    Lines before a notes or example heading belong to the clause; the note is its
    own element so it is never quoted as normative. Clauses under a Definitions
    clause are definitions, and every clause using a defined term links to it.
    """

    name = "numbered-clause@1"

    def fit(self, blocks: tuple[Block, ...]) -> float:
        numbered = sum(
            1 for b in blocks if _CLAUSE.match(b.text) and not _LEADERS.search(b.text)
        )
        shall = any(" shall " in f" {b.text} " for b in blocks)
        return min(1.0, numbered / 8) * (1.0 if shall else 0.6)

    def structure(self, blocks: tuple[Block, ...]) -> tuple[Element, ...]:
        drafts: dict[str, _Draft] = {}
        current = clause = None
        counts: dict[str, int] = {}

        def open_(id: str, parent: str | None, kind: str, heading: str) -> _Draft:
            draft = drafts.get(id)
            # A repeated number is a contents entry seen first or a continuation.
            if draft is None or not draft.lines:
                draft = drafts[id] = _Draft(id, parent, kind, heading)
            return draft

        def parent_of(id: str) -> str | None:
            parts = id.split(".")
            while len(parts) > 1:
                parts.pop()
                if (candidate := ".".join(parts)) in drafts:
                    return candidate
            # "A-5" belongs to Appendix A.
            letter = id.split("-")[0] if "-" in id else ""
            return f"Appendix {letter}" if f"Appendix {letter}" in drafts else None

        def child(prefix: str) -> str:
            assert clause is not None
            counts[f"{clause}/{prefix}"] = n = counts.get(f"{clause}/{prefix}", 0) + 1
            return f"{clause}/{prefix}{n}"

        untitled = None  # A section whose title is on the next line
        for block in _split(blocks):
            text = block.text
            if _LEADERS.search(text):
                continue
            if untitled is not None:
                if len(text) <= 80 and not _CLAUSE.match(text):
                    untitled.heading = text
                    untitled.add(block)
                    untitled = None
                    continue
                untitled = None
            # Lettered clauses ("A-5.1") count only once an appendix has begun.
            appendix = clause is not None and (
                clause.startswith("Appendix") or "-" in clause
            )
            if (
                m := _CLAUSE.match(text) or (appendix and _APPENDIX_CLAUSE.match(text))
            ) and block.kind in {"heading", "text", "list_item"}:
                id, rest = m.group(1), m.group(2).strip()
                # A short line without a sentence end is a heading; else body text.
                heading = (
                    rest
                    if block.kind == "heading"
                    or (len(rest) <= 80 and not rest.endswith((".", ":", ";")))
                    else ""
                )
                current = open_(id, parent_of(id), "normative", heading)
                current.add(block)
                clause = id
                continue
            kind = "normative"
            if m := _SECTION.match(text):
                id, heading = m.group(1) or m.group(3), m.group(2) or m.group(4) or ""
            elif m := _APPENDIX.match(text):
                id, heading = f"Appendix {m.group(2)}", m.group(3)
                kind = "informative" if m.group(1) else "normative"
            if m:
                current = open_(id, None, kind, heading.strip())
                current.add(block)
                clause = id
                if not current.heading:
                    untitled = current
                continue
            # Laid-out captions may be in any case; in running text, capitals or
            # a title-case line that is not a sentence ("Figure 3-1 Related ...").
            caption = _CAPTION_ANY.match(text)
            if caption and not (
                block.kind == "caption"
                or _CAPTION.match(text)
                or (_titled(caption.group(3)) and not text.rstrip().endswith("."))
            ):
                caption = None
            if caption:
                kind = caption.group(1).lower()
                id = _caption_id(caption.group(1), caption.group(2))
                draft = open_(id, clause, kind, caption.group(3).strip())
                draft.add(block)
                # A table's rows follow its caption; a figure is its caption alone.
                if kind == "table":
                    current = draft
                continue
            if block.kind == "table":
                if current is None or current.kind != "table":
                    current = open_(
                        child("table") if clause else "table", clause, "table", ""
                    )
                current.add(block)
                continue
            if clause and (m := _NOTE.match(text)):
                kind = "example" if m.group(1).startswith("EXAMPLE") else "note"
                current = open_(child(kind), clause, kind, "")
                current.add(block)
                continue
            if current is None:
                current = open_("front", None, "informative", "")
            current.add(block)

        # Reading order can put a clause before its section's heading (a heading
        # centred over two columns), so numbered parents are settled once all are seen.
        for draft in drafts.values():
            if draft.parent is None:
                draft.parent = parent_of(draft.id)

        def informative(draft: _Draft) -> bool:
            """Whether it sits in a nonmandatory appendix, however deep."""
            while draft.parent in drafts:
                draft = drafts[draft.parent]
                if draft.kind == "informative":
                    return True
            return False

        for draft in drafts.values():
            parent = drafts.get(draft.parent) if draft.parent else None
            if (
                parent
                and draft.kind == "normative"
                and _DEFINITIONS.search(parent.heading)
            ):
                draft.kind = "definition"
            if draft.kind == "normative" and informative(draft):
                draft.kind = "informative"
        return self.link(
            tuple(
                Element(
                    id=d.id,
                    parent=d.parent,
                    kind=d.kind,
                    heading=d.heading,
                    text="\n".join(d.lines),
                    provenance=_provenance(d.blocks),
                )
                for d in drafts.values()
            )
        )

    def link(self, elements: tuple[Element, ...]) -> tuple[Element, ...]:
        ids = {e.id for e in elements}
        names = {m.group(1): e.id for e in elements if (m := _NAMED.match(e.heading))}
        terms = {
            e.id: _forms(term)
            for e in elements
            if e.kind == "definition"
            and (term := e.heading or _first_term(e.text.splitlines()))
        }
        return tuple(
            e.model_copy(update={"links": _links(e, ids, terms, names)})
            for e in elements
        )


def _caption_id(word: str, number: str) -> str:
    """ "Figure 10-11" however the number was dashed or wrapped."""
    return f"{word.title()} {''.join(number.split()).replace('–', '-')}"


def _titled(title: str) -> bool:
    """A caption title starts with a capital or a number, maybe after a quote."""
    first = title.lstrip("“\"'(")[:1]
    return first.isupper() or first.isdigit()


def _first_term(lines: list[str]) -> str:
    """The defined term in "1.4.2 Design pressure—the pressure ..."."""
    first = _CLAUSE.sub(r"\2", lines[0]) if lines else ""
    m = _TERM.match(first)
    return m.group(1).strip() if m else ""


def _links(
    element: Element,
    ids: set[str],
    terms: dict[str, tuple[re.Pattern[str], ...]],
    names: dict[str, str],
) -> tuple[Link, ...]:
    text = element.text
    links: dict[tuple[str, str], Link] = {}

    def add(
        target: str,
        at: int,
        explicit: bool,
        type: LinkType = "refers_to",
        confidence: float = 1.0,
    ) -> None:
        resolved = target in ids
        if target == element.id or not (resolved or explicit):
            return
        sentence = text[max(text.rfind(".", 0, at), text.rfind(";", 0, at)) + 1 : at]
        if _EXCEPTION.search(sentence):
            type = "limits"
        links.setdefault(
            (type, target),
            Link(type=type, target=target, resolved=resolved, confidence=confidence),
        )

    for m in _CITE.finditer(text):
        strong = m.group("strong") is not None
        add(m.group("id"), m.start(), strong)
        end = m.end()
        while strong and (more := _CITE_MORE.match(text, end)):
            add(more.group(1), m.start(), True)
            end = more.end()
    for m in _CITE_CAPTION.finditer(text):
        target = _caption_id(m.group(1), m.group(2))
        # A parser that joins "Figure 4-" and "15" across a line break may drop the
        # hyphen; restore it when exactly one figure fits.
        word, _, number = target.partition(" ")
        fits = [
            f"{word} {number[:i]}-{number[i:]}"
            for i in range(1, len(number))
            if number.isdigit() and f"{word} {number[:i]}-{number[i:]}" in ids
        ]
        if target not in ids and len(fits) == 1:
            add(fits[0], m.start(), True, "uses", confidence=0.7)
        else:
            add(target, m.start(), True, "uses")
    for m in _CITE_APPENDIX.finditer(text):
        add(f"Appendix {m.group(1)}", m.start(), True)
    for name, id in names.items():
        for m in re.finditer(rf"\b{re.escape(name)}(?![\w])", text):
            add(id, m.start(), True)
    if element.kind not in {"definition", "front"}:
        for id, forms in terms.items():
            if any(form.search(text) for form in forms):
                links.setdefault(
                    ("uses", id),
                    Link(type="uses", target=id, resolved=True, confidence=0.8),
                )
    return tuple(links.values())


def _forms(term: str) -> tuple[re.Pattern[str], ...]:
    """How a defined term appears in text.

    "BOUNDARY, INNER (IB)" is used as "inner boundary" and, in capitals only, "IB";
    a longer parenthesis is a synonym: "CIRCULARITY (ROUNDNESS)". Words may wrap.
    """
    inside = re.findall(r"\(([^)]*)\)", term)
    words = re.sub(r"\([^)]*\)", "", term).strip()
    head, comma, qualifier = words.partition(",")
    phrases = [f"{qualifier.strip()} {head.strip()}" if comma else words]
    abbreviations = [p for p in inside if re.fullmatch(r"[A-Z]{2,5}", p)]
    phrases += [p for p in inside if p not in abbreviations]

    def pattern(phrase: str, flags: int = 0) -> re.Pattern[str]:
        spaced = r"\s+".join(re.escape(w) for w in phrase.split())
        return re.compile(rf"\b{spaced}\b", flags)

    return tuple(
        [pattern(p, re.IGNORECASE) for p in phrases if len(p.strip()) >= 3]
        + [pattern(a) for a in abbreviations]
    )


PROFILES: dict[str, Profile] = {
    "numbered-clause": NumberedClauseProfile(),
    "fallback": FallbackProfile(),
}


def choose(blocks: tuple[Block, ...], name: str | None = None) -> Profile:
    """The named profile, or the one that best fits these blocks."""
    if name is not None:
        if name not in PROFILES:
            raise ValueError(f"Unknown profile {name}; known: {', '.join(PROFILES)}")
        return PROFILES[name]
    return max(PROFILES.values(), key=lambda p: p.fit(blocks))
