from __future__ import annotations

import contextvars
import os
import re
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
class ExtractedTable:
    page: int
    grid: list[list[str | None]]
    bbox: str | None = None
    engine: str = "pdfplumber"


@dataclass
class ExtractedPdf:
    pdf_type: str
    page_count: int
    pages: list[PageText] = field(default_factory=list)
    lines: list[LineBox] = field(default_factory=list)
    words: list[WordBox] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
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

        mupdf = _extract_with_pymupdf(work)
        inspector = _extract_with_inspector(work)
        plumber = _extract_with_pdfplumber(work)

        extracted = mupdf if (mupdf is not None and not _almost_no_lines(mupdf)) else inspector
        if extracted is None or _almost_no_lines(extracted):
            if plumber is not None:
                extracted = plumber
            elif mupdf is not None:
                extracted = mupdf

        for candidate in (mupdf, plumber):
            if candidate is not None and extracted is not None:
                if not extracted.tables and candidate.tables:
                    extracted.tables = candidate.tables
                if len(candidate.words) > len(extracted.words):
                    extracted.words = candidate.words
                    if not extracted.lines or len(candidate.lines) > len(extracted.lines):
                        extracted.lines = candidate.lines

        if extracted is None:
            extracted = _extract_with_pypdf(work)
        extracted = _normalize_extracted(extracted)

        if _should_ocr(extracted):
            from apps.engine.ocr import ocr_pdf

            ocr = ocr_pdf(work, password=secret)
            if ocr.lines:
                ocr_norm = _normalize_extracted(ocr)
                if not extracted.tables and ocr_norm.tables:
                    extracted.tables = ocr_norm.tables
                extracted.pages = ocr_norm.pages
                extracted.lines = ocr_norm.lines
                extracted.words = ocr_norm.words
                extracted.pdf_type = ocr_norm.pdf_type
                extracted.engine = f"{extracted.engine}+ocr"
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
    if extracted.pages and any(page.needs_ocr for page in extracted.pages):
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
    for table in extracted.tables:
        if table.page <= 0:
            table.page += 1
    return extracted


def _parse_markdown_tables(page: int, text: str) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    if not text or "|" not in text:
        return tables
    lines = text.splitlines()
    current_grid: list[list[str | None]] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            inner = stripped[1:-1]
            cells = [c.strip() for c in inner.split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                continue
            row = [(c if c else None) for c in cells]
            current_grid.append(row)
        else:
            if len(current_grid) >= 2:
                tables.append(ExtractedTable(page=page, grid=current_grid, engine="pdf-inspector"))
            current_grid = []
    if len(current_grid) >= 2:
        tables.append(ExtractedTable(page=page, grid=current_grid, engine="pdf-inspector"))
    return tables


def _extract_with_pymupdf(path: Path) -> ExtractedPdf | None:
    try:
        import pymupdf
    except ImportError:
        return None
    try:
        doc = pymupdf.open(str(path))
    except Exception:
        return None

    pages: list[PageText] = []
    words: list[WordBox] = []
    tables: list[ExtractedTable] = []
    try:
        for index, page in enumerate(doc, start=1):
            text = page.get_text() or ""
            height = float(page.rect.height)
            width = float(page.rect.width)
            bbox_str = f"0.0,0.0,{width:.1f},{height:.1f}" if (width and height) else None
            pages.append(PageText(page=index, text=text, needs_ocr=len(text.strip()) < 10))
            try:
                raw_words = page.get_text("words") or []
            except Exception:
                raw_words = []
            for item in raw_words:
                token = str(item[4] or "").strip()
                if not token:
                    continue
                x0 = float(item[0])
                y0 = float(item[1])
                x1 = float(item[2])
                y1 = float(item[3])
                y = height - y1 if height else y0
                words.append(
                    WordBox(
                        page=index,
                        text=token,
                        x=x0,
                        y=y,
                        width=max(x1 - x0, 0.0),
                        height=max(y1 - y0, 0.0),
                    )
                )
            try:
                found_tabs = page.find_tables()
                for tab in found_tabs:
                    grid = tab.extract()
                    if grid and len(grid) >= 2:
                        cleaned_grid = [
                            [(str(cell).strip() if cell is not None and str(cell).strip() else None) for cell in row]
                            for row in grid
                        ]
                        if any(any(c for c in row if c) for row in cleaned_grid):
                            tables.append(ExtractedTable(page=index, grid=cleaned_grid, bbox=bbox_str, engine="pymupdf"))
            except Exception:
                pass
    finally:
        try:
            doc.close()
        except Exception:
            pass

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
        tables=tables,
        engine="pymupdf",
    )


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
    tables: list[ExtractedTable] = []
    for page in pages_md.pages:
        page_no = int(page.page) + 1
        md_text = page.markdown or ""
        pages.append(
            PageText(
                page=page_no,
                text=md_text,
                needs_ocr=bool(page.needs_ocr),
            )
        )
        tables.extend(_parse_markdown_tables(page_no, md_text))
    if not pages and result.markdown:
        pages.append(PageText(page=1, text=result.markdown))
        tables.extend(_parse_markdown_tables(1, result.markdown))

    return ExtractedPdf(
        pdf_type=getattr(result, "pdf_type", "text_based") or "text_based",
        page_count=int(getattr(result, "page_count", len(pages)) or len(pages)),
        pages=pages,
        lines=_group_items(items),
        words=_words_from_items(items),
        tables=tables,
        engine="pdf-inspector",
    )


def _words_from_items(items) -> list[WordBox]:
    words: list[WordBox] = []
    if not items:
        return words
    for item in items:
        raw_text = (getattr(item, "text", "") or "").strip()
        if not raw_text:
            continue
        try:
            page = int(item.page)
            base_x = float(item.x)
            base_y = float(item.y)
            total_w = float(item.width)
            h = float(item.height)
        except (TypeError, ValueError):
            continue

        parts = raw_text.split()
        if len(parts) <= 1:
            words.append(
                WordBox(
                    page=page,
                    text=raw_text,
                    x=base_x,
                    y=base_y,
                    width=total_w,
                    height=h,
                )
            )
        else:
            total_chars = max(len(raw_text), 1)
            char_w = total_w / total_chars if total_chars > 0 else 0.0
            idx = 0
            for token in parts:
                token_start = raw_text.find(token, idx)
                if token_start == -1:
                    token_start = idx
                token_x = base_x + (token_start * char_w)
                token_w = max(len(token) * char_w, 1.0)
                words.append(
                    WordBox(
                        page=page,
                        text=token,
                        x=token_x,
                        y=base_y,
                        width=token_w,
                        height=h,
                    )
                )
                idx = token_start + len(token)
    return words


_PLUMBER_TABLE_SETTINGS = (
    {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
    },
    {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 4,
        "join_tolerance": 4,
        "text_x_tolerance": 3,
        "text_y_tolerance": 3,
    },
)


def _extract_with_pdfplumber(path: Path) -> ExtractedPdf | None:
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(str(path)) as pdf:
            pages: list[PageText] = []
            words: list[WordBox] = []
            tables: list[ExtractedTable] = []
            for index, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                pages.append(PageText(page=index, text=text))
                height = float(page.height or 0)
                width = float(page.width or 0)
                bbox_str = f"0.0,0.0,{width:.1f},{height:.1f}" if (width and height) else None
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
                found_page_tables = []
                for settings in _PLUMBER_TABLE_SETTINGS:
                    try:
                        raw_t = page.extract_tables(table_settings=settings) or []
                    except Exception:
                        raw_t = []
                    usable = [t for t in raw_t if t and len(t) >= 2]
                    if usable:
                        found_page_tables = usable
                        break
                if not found_page_tables:
                    try:
                        raw_t = page.extract_tables() or []
                        usable = [t for t in raw_t if t and len(t) >= 2]
                        if usable:
                            found_page_tables = usable
                    except Exception:
                        pass
                for t in found_page_tables:
                    cleaned_grid = [
                        [(str(cell).strip() if cell is not None and str(cell).strip() else None) for cell in row]
                        for row in t
                    ]
                    if any(any(c for c in row if c) for row in cleaned_grid):
                        tables.append(ExtractedTable(page=index, grid=cleaned_grid, bbox=bbox_str, engine="pdfplumber"))
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
        tables=tables,
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
