"""Agent readers over the snapshots a project has pinned.

They return SourceExcerpts citing the pin, so an extracted excerpt is quotable
wherever the pinned standard's licensed text is required.
"""

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, JsonValue

from ..contracts import Element, LibraryPin, Model, Ref, SourceExcerpt
from ..tools.registry import encode

if TYPE_CHECKING:
    from ..project import Project
    from .store import Library

LIMIT = 16_000  # Characters an excerpt carries, as read_text and read_document do
ATTACHED = {"note", "example", "table"}  # Read with the element they qualify

type Offset = Annotated[int, Field(ge=0)]
type Depth = Annotated[int, Field(ge=0, le=3)]
type Query = Annotated[str, Field(min_length=2)]
type Limit = Annotated[int, Field(ge=1, le=50)]


class LibraryHit(Model):
    source: Ref  # The pin to read the element from with get_element
    element: str
    kind: str
    snippet: str


def _header(element: Element, why: str = "") -> str:
    return f"[{element.id}] ({element.kind}{', ' + why if why else ''})\n"


def _shown(element: Element, why: str = "") -> str:
    return _header(element, why) + element.text


def _subtree(root: str, children: dict[str | None, list[str]]) -> list[str]:
    """root and its descendants in document order."""
    ids, pending = [], [root]
    while pending:
        id = pending.pop(0)
        ids.append(id)
        pending[:0] = children.get(id, [])
    return ids


def register_library_tools(project: "Project") -> None:
    def pinned(source: Ref) -> tuple[LibraryPin, "Library"]:
        saved = project.store.resolve(source, current=True)
        if saved.data.get("kind") != "library_pin":
            raise ValueError("source is not a library pin; read it with read_document")
        pin = LibraryPin.model_validate_json(encode(saved.data))
        library = project.libraries.get(pin.scope)
        if library is None:
            raise ValueError(f"This project has no {pin.scope} library attached")
        return pin, library

    def missing(
        pin: LibraryPin, library: "Library", element: str | None = None
    ) -> tuple[str, ...]:
        snapshot = library.snapshot(pin.snapshot)
        gaps = []
        check = library.verifications(pin.snapshot).get(element or "")
        if check is None:
            gaps.append("Extraction not independently verified")
        elif check.status == "disputed":
            gaps.append(
                f"Extraction disputed ({check.detail}); check the original page "
                "before relying on it"
            )
        if snapshot.profile.startswith("fallback@"):
            gaps.append("Ingested as pages and paragraphs: dependencies are unknown")
        return tuple(gaps)

    async def library_outline(
        source: Ref, under: str = "", offset: Offset = 0
    ) -> SourceExcerpt:
        """Outline of a pinned library source: element IDs, kinds and headings.

        Supply source also in the tool action's inputs. under limits it to one
        element and its descendants; offset paginates the outline text.
        """
        pin, library = pinned(source)
        elements = library.elements(pin.snapshot)
        depth: dict[str, int] = {}
        lines = []
        for e in elements:
            depth[e.id] = depth.get(e.parent, -1) + 1 if e.parent else 0
            label = e.heading or " ".join(e.text.split())[:60]
            lines.append(f"{'  ' * depth[e.id]}{e.id} ({e.kind}) {label}")
        if under:
            children: dict[str | None, list[str]] = {}
            for e in elements:
                children.setdefault(e.parent, []).append(e.id)
            if under not in depth:
                raise ValueError(f"No element {under}; read the outline without under")
            keep = set(_subtree(under, children))
            lines = [l for l, e in zip(lines, elements, strict=True) if e.id in keep]
        text = "\n".join(lines)
        return SourceExcerpt(
            source=source,
            locator=f"{pin.designation}:{pin.edition} outline{' of ' + under if under else ''}; "
            f"characters {offset}-{min(len(text), offset + LIMIT)}",
            text=text[offset : offset + LIMIT],
            metadata={
                "snapshot": pin.snapshot,
                "more_text": offset + LIMIT < len(text),
            },
            missing_metadata=missing(pin, library),
        )

    async def get_element(
        source: Ref,
        element: Annotated[str, Field(min_length=1)],
        depth: Depth = 1,
        offset: Offset = 0,
    ) -> SourceExcerpt:
        """A pinned library element with what it depends on, for quoting.

        Supply source also in the tool action's inputs, then extract the result to
        quote it. Returns the element with its notes, tables and sub-elements, then
        the elements it refers to, uses or is limited by (exceptions), to depth
        links away. What does not fit is listed in metadata.deferred to read next;
        offset paginates an element too long to show whole.
        """
        pin, library = pinned(source)
        elements = {e.id: e for e in library.elements(pin.snapshot)}
        if element not in elements:
            raise ValueError(
                f"No element {element} in {pin.designation}:{pin.edition}; "
                "find IDs with library_outline or search_library"
            )
        children: dict[str | None, list[str]] = {}
        # An exception may be written in either clause, so a limits link is
        # followed both ways: a rule is read with every clause that limits it.
        limited_by: dict[str, list[str]] = {}
        for e in elements.values():
            children.setdefault(e.parent, []).append(e.id)
            for link in e.links:
                if link.type == "limits" and link.resolved:
                    limited_by.setdefault(link.target, []).append(e.id)
        main = _subtree(element, children)
        seen, frontier = set(main), main
        dependencies: list[tuple[str, str]] = []  # (id, why it is shown)
        for _ in range(depth):
            reached = []
            for id in frontier:
                followed = [
                    (link.target, f"{link.type} from {id}")
                    for link in elements[id].links
                    if link.resolved
                ] + [(other, f"limits {id}") for other in limited_by.get(id, [])]
                # Exceptions first, so an element both cited and limiting says so.
                followed.sort(key=lambda f: "limits" not in f[1])
                for target, why in followed:
                    if target in seen:
                        continue
                    # A dependency brings its own notes and tables, not its
                    # sub-clauses and figures: those are read on request.
                    attached = [
                        c
                        for c in children.get(target, [])
                        if elements[c].kind in ATTACHED
                    ]
                    for dependency in (target, *attached):
                        if dependency not in seen:
                            seen.add(dependency)
                            reached.append(dependency)
                            dependencies.append((dependency, why))
            frontier = reached
        root = elements[element]
        checks = library.verifications(pin.snapshot)
        disputed = {id for id, check in checks.items() if check.status == "disputed"}
        shown = [_shown(elements[id]) for id in main]
        included: list[JsonValue]
        deferred: list[JsonValue]
        if offset or sum(len(s) + 2 for s in shown) > LIMIT:
            # Too long whole: the element alone, paginated, its parts deferred.
            text = _header(root) + root.text[offset : offset + LIMIT]
            included = [element]
            deferred = [*main[1:], *(d for d, _ in dependencies)]
            more = offset + LIMIT < len(root.text)
        else:
            text, more = "\n\n".join(shown), False
            included = [*main]
            deferred = []
            for id, why in dependencies:
                addition = "\n\n" + _shown(elements[id], why)
                if len(text) + len(addition) > LIMIT:
                    deferred.append(id)
                else:
                    text += addition
                    included.append(id)
        return SourceExcerpt(
            source=source,
            locator=f"{pin.designation}:{pin.edition} {element}",
            text=text,
            metadata={
                "snapshot": pin.snapshot,
                "element": element,
                "kind": root.kind,
                "verified": checks[element].status
                if element in checks
                else "unverified",
                "disputed": [id for id in included if id in disputed],
                "pages": [*sorted({p.page for p in root.provenance})],
                "links": [l.model_dump(mode="json") for l in root.links],
                "included": included,
                "deferred": deferred,
                "more_text": more,
            },
            missing_metadata=missing(pin, library, element),
        )

    async def search_library(
        query: Query,
        scope: Literal["all", "shared", "project"] = "all",
        limit: Limit = 20,
    ) -> tuple[LibraryHit, ...]:
        """Find elements containing every word of query across the project's pins.

        Hits name the pin and element ID; read them with get_element, never quote
        a snippet. scope narrows the search to the shared or the project library.
        """
        words = query.casefold().split()
        hits: list[tuple[int, LibraryHit]] = []
        for saved in project.store.list("source"):
            if saved.stale or saved.data.get("kind") != "library_pin":
                continue
            pin = LibraryPin.model_validate_json(encode(saved.data))
            library = project.libraries.get(pin.scope)
            if library is None or scope not in {"all", pin.scope}:
                continue
            for e in library.elements(pin.snapshot):
                text = e.text.casefold()
                if not all(w in text for w in words):
                    continue
                at = text.find(words[0])
                flat = " ".join(e.text[max(0, at - 80) : at + 160].split())
                score = sum(text.count(w) for w in words) + 5 * all(
                    w in e.heading.casefold() for w in words
                )
                hit = LibraryHit(
                    source=saved.ref, element=e.id, kind=e.kind, snippet=flat
                )
                hits.append((score, hit))
        hits.sort(key=lambda h: -h[0])
        return tuple(h for _, h in hits[:limit])

    # Library errors name pins and elements, never secrets; agents fix calls with them.
    for function in (library_outline, get_element, search_library):
        project.tools.register(
            function, retry_safe=True, requires_plan=False, show_errors=True
        )
