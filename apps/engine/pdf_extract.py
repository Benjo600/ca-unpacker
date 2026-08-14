from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PageText:
    page: int
    text: str
    needs_ocr: bool = False


@dataclass
class LineBox:
    page: int
    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class ExtractedPdf:
    pdf_type: str
    page_count: int
    pages: list[PageText] = field(default_factory=list)
    lines: list[LineBox] = field(default_factory=list)
    engine: str = "none"


def extract_pdf(path: Path) -> ExtractedPdf:
    """Local extract only. Uses Firecrawl pdf-inspector on this PC, never uploads."""
    extracted = _extract_with_inspector(path)
    if extracted is not None:
        return extracted
    return _extract_with_pypdf(path)


def _extract_with_inspector(path: Path) -> ExtractedPdf | None:
    try:
        import pdf_inspector
    except ImportError:
        return None
    try:
        result = pdf_inspector.process_pdf(str(path))
        pages_md = pdf_inspector.extract_pages_markdown(str(path))
        items = pdf_inspector.extract_text_with_positions(str(path))
    except Exception:
        return None

    pages: list[PageText] = []
    for page in pages_md.pages:
        page_no = int(page.page) + 1
        pages.append(
            PageText(
                page=page_no,
                text=page.markdown or "",
                needs_ocr=bool(page.needs_ocr),
            )
        )
    if not pages and result.markdown:
        pages.append(PageText(page=1, text=result.markdown))

    return ExtractedPdf(
        pdf_type=getattr(result, "pdf_type", "text_based") or "text_based",
        page_count=int(getattr(result, "page_count", len(pages)) or len(pages)),
        pages=pages,
        lines=_group_items(items),
        engine="pdf-inspector",
    )


def _group_items(items) -> list[LineBox]:
    if not items:
        return []
    by_page: dict[int, list] = {}
    for item in items:
        text = (item.text or "").strip()
        if not text:
            continue
        by_page.setdefault(int(item.page), []).append(item)

    lines: list[LineBox] = []
    for page, page_items in by_page.items():
        page_items.sort(key=lambda item: (-float(item.y), float(item.x)))
        bands: list[list] = []
        for item in page_items:
            placed = False
            for band in bands:
                if abs(float(item.y) - float(band[0].y)) <= max(3.0, float(item.font_size) * 0.45):
                    band.append(item)
                    placed = True
                    break
            if not placed:
                bands.append([item])
        for band in bands:
            band.sort(key=lambda item: float(item.x))
            text = " ".join((item.text or "").strip() for item in band if (item.text or "").strip())
            xs = [float(item.x) for item in band]
            ys = [float(item.y) for item in band]
            rights = [float(item.x) + float(item.width) for item in band]
            tops = [float(item.y) + float(item.height) for item in band]
            lines.append(
                LineBox(
                    page=page,
                    text=text,
                    x=min(xs),
                    y=min(ys),
                    width=max(rights) - min(xs),
                    height=max(tops) - min(ys),
                )
            )
    return lines


def _extract_with_pypdf(path: Path) -> ExtractedPdf:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ExtractedPdf(pdf_type="unknown", page_count=0, engine="none")
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception:
        return ExtractedPdf(pdf_type="unknown", page_count=0, engine="none")
    if reader.is_encrypted:
        return ExtractedPdf(pdf_type="encrypted", page_count=len(reader.pages), engine="pypdf")
    pages: list[PageText] = []
    lines: list[LineBox] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(PageText(page=index, text=text))
        for row in text.splitlines():
            if row.strip():
                lines.append(LineBox(page=index, text=row.strip(), x=0, y=0, width=0, height=0))
    return ExtractedPdf(
        pdf_type="text_based",
        page_count=len(reader.pages),
        pages=pages,
        lines=lines,
        engine="pypdf",
    )
