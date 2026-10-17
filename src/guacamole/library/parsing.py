"""Layout parsers: a PDF as ordered text blocks, each with its page and position.

Docling reads layout (headings, tables, reading order); pypdf reads the text layer
alone, line by line. Both import on first use.
"""

import importlib.metadata
from pathlib import Path
from typing import Literal, NamedTuple, Protocol

type BlockKind = Literal["heading", "text", "table", "formula", "list_item", "caption"]


class Block(NamedTuple):
    kind: BlockKind
    text: str
    page: int
    # Left, top, right, bottom in PDF points from the page's top-left; None: text only.
    bbox: tuple[float, float, float, float] | None = None


class LayoutParser(Protocol):
    name: str  # name@version, recorded on each snapshot

    def parse(self, path: Path) -> tuple[Block, ...]: ...


class PypdfParser:
    """The PDF's text layer, one block per line; no layout, tables or positions."""

    def __init__(self) -> None:
        self.name = f"pypdf@{importlib.metadata.version('pypdf')}"

    def parse(self, path: Path) -> tuple[Block, ...]:
        import pypdf

        blocks = []
        for number, page in enumerate(pypdf.PdfReader(path).pages, start=1):
            for line in (page.extract_text() or "").splitlines():
                if line.strip():
                    blocks.append(Block("text", line.strip(), number))
        return tuple(blocks)


# Docling labels kept, as block kinds; headers, footers, pictures and the
# table of contents are dropped so they never become elements.
_DOCLING_KINDS: dict[str, BlockKind] = {
    "title": "heading",
    "section_header": "heading",
    "text": "text",
    "paragraph": "text",
    "footnote": "text",
    "code": "text",
    "list_item": "list_item",
    "caption": "caption",
    "table": "table",
    "formula": "formula",
}


class DoclingParser:
    """Docling's layout model: reading order, headings, table structure and positions."""

    def __init__(self, *, ocr: bool = False, formulas: bool = False) -> None:
        self.name = f"docling@{importlib.metadata.version('docling')}"
        self.ocr = ocr  # For scanned pages; born-digital PDFs have a text layer
        self.formulas = formulas  # LaTeX for equations; slower

    def parse(self, path: Path) -> tuple[Block, ...]:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling_core.types.doc.document import TableItem

        options = PdfPipelineOptions(
            do_ocr=self.ocr, do_formula_enrichment=self.formulas
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        document = converter.convert(path).document
        blocks = []
        for item, _ in document.iterate_items():
            label = getattr(item, "label", "")
            kind = _DOCLING_KINDS.get(getattr(label, "value", label))
            prov = getattr(item, "prov", None)
            if kind is None or not prov:
                continue
            text = (
                item.export_to_markdown(document)
                if isinstance(item, TableItem)
                else getattr(item, "text", "")
            )
            # Docling lifts a numbered line's number into the list marker; a clause
            # number is part of the clause.
            marker = getattr(item, "marker", "") or ""
            if kind == "list_item" and any(c.isalnum() for c in marker):
                text = f"{marker} {text}"
            if not text.strip():
                continue
            height = document.pages[prov[0].page_no].size.height
            box = prov[0].bbox.to_top_left_origin(height)
            blocks.append(
                Block(
                    kind,
                    text.strip(),
                    prov[0].page_no,
                    (box.l, box.t, box.r, box.b),
                )
            )
        return tuple(blocks)


def default_parser() -> LayoutParser:
    """Docling when the library extra is installed, else the pypdf text layer."""
    try:
        importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        return PypdfParser()
    return DoclingParser()
