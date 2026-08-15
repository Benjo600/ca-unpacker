from __future__ import annotations

import contextvars
import os
import tempfile
from contextlib import contextmanager
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


_active_password: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "caunpacker_pdf_password", default=None
)


@contextmanager
def using_password(password: str | None):
    token = _active_password.set(password)
    try:
        yield
    finally:
        _active_password.reset(token)


def extract_pdf(path: Path, password: str | None = None) -> ExtractedPdf:
    """Local extract only. Uses Firecrawl pdf-inspector on this PC, never uploads."""
    path = Path(path)
    secret = _resolve_password(password)
    unlocked: Path | None = None
    try:
        unlocked, blocked, page_count = _maybe_unlock(path, secret)
        if blocked:
            return ExtractedPdf(pdf_type="encrypted", page_count=page_count, engine="pypdf")
        work = unlocked or path

        extracted = _extract_with_inspector(work)
        if extracted is None:
            extracted = _extract_with_pypdf(work)
        extracted = _normalize_extracted(extracted)

        if _should_ocr(extracted):
            from apps.engine.ocr import ocr_pdf

            ocr = ocr_pdf(work, password=secret)
            if ocr.lines:
                extracted = _normalize_extracted(ocr)
        return extracted
    finally:
        if unlocked is not None:
            _unlink_quiet(unlocked)


def _resolve_password(password: str | None) -> str | None:
    if password is None:
        password = _active_password.get()
    if password is None:
        return None
    text = str(password)
    return text or None


def _maybe_unlock(path: Path, password: str | None) -> tuple[Path | None, bool, int]:
    """If encrypted, decrypt to a temp PDF. Never write the unlocked file into the library."""
    try:
        from pypdf import PasswordType, PdfReader, PdfWriter
    except ImportError:
        return None, False, 0

    try:
        reader = PdfReader(str(path), strict=False)
    except Exception:
        return None, False, 0
    if not reader.is_encrypted:
        return None, False, _reader_page_count(reader)

    page_count = _reader_page_count(reader)
    if not password:
        return None, True, page_count
    try:
        result = reader.decrypt(password)
    except Exception:
        return None, True, page_count
    if result == PasswordType.NOT_DECRYPTED:
        return None, True, page_count

    handle, name = tempfile.mkstemp(prefix="caunpacker_unlock_", suffix=".pdf")
    os.close(handle)
    unlocked = Path(name)
    try:
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with unlocked.open("wb") as handle:
            writer.write(handle)
    except Exception:
        _unlink_quiet(unlocked)
        return None, True, page_count
    return unlocked, False, _reader_page_count(reader) or page_count


def _reader_page_count(reader) -> int:
    try:
        return len(reader.pages)
    except Exception:
        return 0


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _should_ocr(extracted: ExtractedPdf) -> bool:
    if extracted.pdf_type == "encrypted":
        return False
    if extracted.pdf_type in {"scanned", "image_based"}:
        return True
    if extracted.pages and all(page.needs_ocr for page in extracted.pages):
        return True
    if extracted.page_count >= 1 and _almost_no_lines(extracted) and _looks_like_scan(extracted):
        return True
    return False


def _almost_no_lines(extracted: ExtractedPdf) -> bool:
    return sum(1 for line in extracted.lines if line.text.strip()) < 2


def _looks_like_scan(extracted: ExtractedPdf) -> bool:
    if extracted.pdf_type in {"scanned", "image_based", "mixed"}:
        return True
    if extracted.pages and any(page.needs_ocr for page in extracted.pages):
        return True
    text = " ".join((page.text or "") for page in extracted.pages).strip()
    return len(text) < 20


def _normalize_extracted(extracted: ExtractedPdf) -> ExtractedPdf:
    for line in extracted.lines:
        if line.page <= 0:
            line.page += 1
    for page in extracted.pages:
        if page.page <= 0:
            page.page += 1
    return extracted


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
        return ExtractedPdf(pdf_type="encrypted", page_count=_reader_page_count(reader), engine="pypdf")
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
    has_text = any((page.text or "").strip() for page in pages)
    return ExtractedPdf(
        pdf_type="text_based" if has_text else "image_based",
        page_count=len(reader.pages),
        pages=pages,
        lines=lines,
        engine="pypdf",
    )
