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
class WordBox:
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
    words: list[WordBox] = field(default_factory=list)
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


def current_pdf_password() -> str | None:
    return _resolve_password(None)


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
        if extracted is None or _almost_no_lines(extracted):
            plumber = _extract_with_pdfplumber(work)
            if plumber is not None and (
                extracted is None or len(plumber.words) > len(extracted.words)
            ):
                extracted = plumber
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
    for word in extracted.words:
        if word.page <= 0:
            word.page += 1
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
        words=_words_from_items(items),
        engine="pdf-inspector",
    )


def _words_from_items(items) -> list[WordBox]:
    words: list[WordBox] = []
    if not items:
        return words
    for item in items:
        text = (item.text or "").strip()
        if not text:
            continue
        try:
            words.append(
                WordBox(
                    page=int(item.page),
                    text=text,
                    x=float(item.x),
                    y=float(item.y),
                    width=float(item.width),
                    height=float(item.height),
                )
            )
        except (TypeError, ValueError):
            continue
    return words


def _extract_with_pdfplumber(path: Path) -> ExtractedPdf | None:
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(str(path)) as pdf:
            pages: list[PageText] = []
            words: list[WordBox] = []
            for index, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                pages.append(PageText(page=index, text=text))
                height = float(page.height or 0)
                try:
                    raw_words = page.extract_words() or []
                except Exception:
                    raw_words = []
                for raw in raw_words:
                    token = (raw.get("text") or "").strip()
                    if not token:
                        continue
                    x0 = float(raw.get("x0") or 0)
                    x1 = float(raw.get("x1") or x0)
                    top = float(raw.get("top") or 0)
                    bottom = float(raw.get("bottom") or top)
                    word_height = max(bottom - top, 0.0)
                    y = height - bottom if height else top
                    words.append(
                        WordBox(
                            page=index,
                            text=token,
                            x=x0,
                            y=y,
                            width=max(x1 - x0, 0.0),
                            height=word_height,
                        )
                    )
    except Exception:
        return None
    if not pages:
        return None
    lines = _lines_from_words(words)
    has_text = any((page.text or "").strip() for page in pages) or bool(words)
    return ExtractedPdf(
        pdf_type="text_based" if has_text else "image_based",
        page_count=len(pages),
        pages=pages,
        lines=lines,
        words=words,
        engine="pdfplumber",
    )


def _lines_from_words(words: list[WordBox]) -> list[LineBox]:
    if not words:
        return []
    by_page: dict[int, list[WordBox]] = {}
    for word in words:
        by_page.setdefault(word.page, []).append(word)
    lines: list[LineBox] = []
    for page, page_words in by_page.items():
        ordered = sorted(page_words, key=lambda item: (-(item.y + item.height / 2.0), item.x))
        bands: list[list[WordBox]] = []
        for word in ordered:
            placed = False
            for band in bands:
                if abs(word.y - band[0].y) <= max(3.0, max(word.height, band[0].height) * 0.5):
                    band.append(word)
                    placed = True
                    break
            if not placed:
                bands.append([word])
        for band in bands:
            band.sort(key=lambda item: item.x)
            text = " ".join(item.text for item in band if item.text.strip())
            xs = [item.x for item in band]
            ys = [item.y for item in band]
            rights = [item.x + item.width for item in band]
            tops = [item.y + item.height for item in band]
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
    words = [
        WordBox(page=line.page, text=line.text, x=line.x, y=line.y, width=line.width, height=line.height)
        for line in lines
    ]
    return ExtractedPdf(
        pdf_type="text_based" if has_text else "image_based",
        page_count=len(reader.pages),
        pages=pages,
        lines=lines,
        words=words,
        engine="pypdf",
    )
