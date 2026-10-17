"""Verification: each element checked against an independent reading of its pages.

The layout parser reads the PDF's text layer; the checker renders each page to
pixels and reads them with OCR, so a fault in one (a dropped hyphen, words run
together, a misread digit) shows as disagreement. Every number in an element must
appear in the OCR of its pages between the same neighbours, so a value
misread in a table is not excused by the same digit elsewhere; most of its words
must appear. Disagreements are
disputes for a person to resolve (Library.resolve), never silently corrected.
"""

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple, Protocol

from ..contracts import Element, Verification
from .store import Library

WORD_SHARE = 0.9  # Words of an element the OCR must also read
_DASHES = str.maketrans("‐‑‒–—−", "------", "­")
_QUOTES = str.maketrans("“”‘’", "\"\"''")
# A number keeps its dots and dashes ("4-15", "2.0-2.5"); a word is letters.
_TOKEN = re.compile(r"\d+(?:[.,-]\d+)*|[^\W\d_]+")
_WORD = re.compile(r"[^\W\d_]{3,}")
# A number hyphenated across a line ("4-" then "15") is printed as "4-15".
_WRAPPED = re.compile(r"(\d)-\s*\n\s*(\d)")


class PageReader(Protocol):
    name: str  # name@version, recorded on each verification

    def read(self, image: Path) -> str: ...


class TesseractReader:
    """The tesseract command on a rendered page; needs tesseract installed."""

    def __init__(self, command: str = "tesseract") -> None:
        path = shutil.which(command)
        if path is None:
            raise RuntimeError(f"{command} is not installed; install tesseract-ocr")
        self.command = path
        version = subprocess.run(
            [path, "--version"], capture_output=True, text=True, check=True
        ).stdout.split()[1]
        self.name = f"tesseract@{version}"

    def read(self, image: Path) -> str:
        return subprocess.run(
            [self.command, str(image), "stdout"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout


class Report(NamedTuple):
    passed: int
    disputed: int
    skipped: int  # Elements with no page to check against


def _normal(text: str) -> str:
    return text.translate(_DASHES).translate(_QUOTES).casefold()


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(_WRAPPED.sub(r"\1-\2", _normal(text)))


def _numbers(tokens: list[str]) -> set[tuple[str, str, str]]:
    """Each number with the tokens either side of it."""
    padded = ["", *tokens, ""]
    return {
        (padded[i - 1], token, padded[i + 1])
        for i, token in enumerate(padded)
        if token[:1].isdigit()
    }


def _words(text: str) -> set[str]:
    return set(_WORD.findall(_normal(text)))


def compare(element: Element, reading: str) -> Verification:
    """The element against the independent reading of its pages."""
    numbers = _numbers(_tokens(element.text))
    read = _numbers(_tokens(reading))
    # At an element's edge a neighbour is unknown: match on the side it has.
    missing_numbers = sorted(
        {
            number
            for before, number, after in numbers
            if (before, number, after) not in read
            and not (
                (not before or not after)
                and any(
                    n == number
                    and (not before or b == before)
                    and (not after or a == after)
                    for b, n, a in read
                )
            )
        }
    )
    words = _words(element.text)
    read_words = _words(reading)
    missing_words = sorted(words - read_words)
    problems = []
    if missing_numbers:
        problems.append(f"numbers not on the page: {', '.join(missing_numbers[:10])}")
    if words and len(missing_words) > (1 - WORD_SHARE) * len(words):
        problems.append(
            f"{len(missing_words)} of {len(words)} words not read: "
            f"{', '.join(missing_words[:10])}"
        )
    return Verification(
        element=element.id,
        status="disputed" if problems else "passed",
        method="",
        detail="; ".join(problems),
    )


def render(
    pdf: Path, pages: Iterable[int], out: Path, dpi: int = 300
) -> dict[int, Path]:
    """Pages of a PDF as PNG images, sharp enough for OCR."""
    import pypdfium2

    document = pypdfium2.PdfDocument(pdf)
    try:
        images = {}
        for page in sorted(set(pages)):
            target = out / f"page-{page}.png"
            document[page - 1].render(scale=dpi / 72).to_pil().save(target)
            images[page] = target
        return images
    finally:
        document.close()


def verify(
    library: Library,
    snapshot: str,
    reader: PageReader | None = None,
    *,
    elements: Iterable[str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Report:
    """Check a snapshot's elements, or the ones named, and record each result."""
    reader = reader or TesseractReader()
    frozen = library.snapshot(snapshot)
    chosen = set(elements) if elements is not None else None
    targets = [
        e
        for e in library.elements(snapshot)
        if (chosen is None or e.id in chosen) and e.provenance
    ]
    skipped = (len(chosen) if chosen is not None else frozen.elements) - len(targets)
    pages = {p.page for e in targets for p in e.provenance}
    readings: dict[int, str] = {}
    with tempfile.TemporaryDirectory() as directory:
        images = render(library.original(frozen), pages, Path(directory))
        for done, (page, image) in enumerate(images.items(), start=1):
            readings[page] = reader.read(image)
            if progress:
                progress(done, len(images))
    passed = disputed = 0
    results = []
    for element in targets:
        reading = "\n".join(
            readings[p] for p in sorted({p.page for p in element.provenance})
        )
        result = compare(element, reading).model_copy(
            update={"method": f"ocr:{reader.name}"}
        )
        results.append(result)
        passed += result.status == "passed"
        disputed += result.status == "disputed"
    library.record(snapshot, results)
    return Report(passed, disputed, skipped)
