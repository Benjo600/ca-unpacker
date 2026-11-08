from __future__ import annotations

import copy
import re
from decimal import Decimal
from pathlib import Path

from apps.engine.currency import detect_currency
from apps.engine.kinds import IMAGE_SUFFIXES
from apps.engine.parsers.bank.docling_tables import rows_from_docling
from apps.engine.parsers.bank.layout import _debit_credit, rows_from_words
from apps.engine.parsers.bank.money import (
    DATE_RE,
    amounts_in,
    decimal_convention,
    detect_decimal_separator,
    is_plausible_iso_date,
    normalize_date,
    parse_amount,
    strip_amount_tokens,
)
from apps.engine.parsers.bank.patterns import (
    ACCOUNT_RE,
    CLOSING_RE,
    IFSC_RE,
    OPENING_RE,
    clean_text,
    is_amount_line,
    is_boilerplate,
    is_continuation,
    looks_like_txn,
)
from apps.engine.parsers.bank.plumber import rows_from_pdfplumber
from apps.engine.parsers.bank.profiles import BankProfile, detect_profile
from apps.engine.parsers.bank.tables import rows_from_cell_tables, rows_from_markdown
from apps.engine.pdf_extract import ExtractedPdf, LineBox, WordBox, extract_pdf

# Safeguards.  These are deliberately far above ordinary statements but keep
# a corrupt or hostile input from exhausting memory or producing a workbook
# that Excel cannot open.  Excel's hard worksheet limit is 1,048,576 rows.
MAX_BANK_PDF_PAGES = 500
MAX_BANK_TRANSACTIONS = 1_048_575
MAX_BANK_IMAGE_PIXELS = 80_000_000
MAX_BANK_SOURCE_BYTES = 100 * 1024 * 1024


def parse_bank_pdf(
    path: Path,
    filename: str | None = None,
    extracted: ExtractedPdf | None = None,
) -> dict:
    """Backward-compatible alias for the bank statement parser."""
    return parse_bank_statement(path, filename, extracted=extracted)


def parse_bank_statement(
    path: Path,
    filename: str | None = None,
    *,
    extracted: ExtractedPdf | None = None,
) -> dict:
    path = Path(path)
    name = filename or path.name
    is_image = path.suffix.lower() in IMAGE_SUFFIXES

    if extracted is None:
        extracted = _extract_source(path, is_image)
    _guard_extracted(extracted)

    header = "\n".join(page.text for page in extracted.pages[:2])
    profile = detect_profile(header, name)
    account = _search(header, ACCOUNT_RE)
    ifsc = _search(header.upper(), IFSC_RE)
    currency_text = "\n".join(page.text or "" for page in extracted.pages[:3])
    decision = detect_currency(
        currency_text,
        metadata={
            "filename": name,
            "profile_key": profile.key,
            "profile_label": profile.label,
            "ifsc": ifsc,
            "account_number": account,
        },
    )
    period_ym = _detect_period_ym(header)

    separator = detect_decimal_separator(currency_text)
    with decimal_convention(separator):
        opening = _balance_near(extracted, OPENING_RE)
        closing = _balance_near(extracted, CLOSING_RE)
        line_rows, line_candidates = _rows_from_lines(
            extracted.lines,
            profile,
            name,
            period_ym,
            getattr(extracted, "words", []),
        )
        word_rows, word_candidates = _rows_from_extracted_words(extracted, profile, name)
        table_rows = _rows_from_extracted_tables(
            getattr(extracted, "tables", []), profile, name
        )
        plumber_rows = table_rows
        if (
            not plumber_rows
            and not is_image
            and extracted.pdf_type not in {"scanned", "image_based", "encrypted"}
        ):
            # The inspector already produced text/positions.  pdfplumber is a
            # second pass only for text PDFs where table columns may be exact.
            plumber_rows = rows_from_pdfplumber(path, profile, name)

        markdown_rows = rows_from_markdown(
            "\n".join(page.text or "" for page in extracted.pages),
            profile,
            name,
        )

        docling_rows: list[dict] = []
        if (
            not is_image
            and extracted.pdf_type in {"scanned", "image_based", "mixed"}
            and not (line_rows or word_rows or markdown_rows or plumber_rows)
            and len(extracted.lines) < 5
            and len(extracted.words or []) < 10
        ):
            # Avoid an expensive Docling pass when OCR/line extraction already
            # found transaction rows.
            docling_rows = rows_from_docling(path, profile, name)

        finished_lines = _finish_rows(line_rows, opening, account, ifsc, profile)
        finished_words = _finish_rows(word_rows, opening, account, ifsc, profile)
        finished_plumber = _finish_rows(plumber_rows, opening, account, ifsc, profile)
        finished_markdown = _finish_rows(markdown_rows, opening, account, ifsc, profile)
        finished_docling = _finish_rows(docling_rows, opening, account, ifsc, profile)
        rows, candidate_count, strategy = _choose_rows(
            opening,
            closing,
            ("docling", finished_docling, len(docling_rows)),
            ("pdfplumber", finished_plumber, len(plumber_rows)),
            ("markdown", finished_markdown, len(markdown_rows)),
            ("columns", finished_words, word_candidates),
            ("lines", finished_lines, line_candidates),
        )

    if len(rows) > MAX_BANK_TRANSACTIONS:
        raise ValueError(
            f"This statement produced {len(rows):,} transaction rows. "
            f"Excel supports at most {MAX_BANK_TRANSACTIONS:,} data rows per sheet. "
            "Split the statement into smaller date ranges and re-import it."
        )

    attach_currency(rows, decision)
    duplicate_count = _flag_duplicate_source_rows(rows)
    inferred_count = sum(
        1 for row in rows if "inferred_from_balance" in (row.get("flags") or [])
    )
    error = None
    if is_image and extracted.engine == "none" and not rows:
        error = (
            "No local OCR engine could read this image. Install the bundled "
            "Tesseract or enable RapidOCR, then re-import the image."
        )

    return {
        "profile": profile.key,
        "profile_label": profile.label,
        "engine": extracted.engine,
        "pdf_type": extracted.pdf_type,
        "input_type": "image" if is_image else "pdf",
        "parse_strategy": strategy,
        "page_count": extracted.page_count,
        "opening_balance": _dec(opening),
        "stated_closing": _dec(closing),
        "account_number": account,
        "ifsc": ifsc,
        "candidate_count": candidate_count,
        "dropped_count": max(candidate_count - len(rows), 0),
        "inferred_count": inferred_count,
        "duplicate_count": duplicate_count,
        "rows": rows,
        "currency": decision,
        "error": error,
    }


def _extract_source(path: Path, is_image: bool) -> ExtractedPdf:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size > MAX_BANK_SOURCE_BYTES:
        raise ValueError(
            f"This file is {size / (1024 * 1024):.1f} MB. "
            "Bank statements larger than 100 MB are not imported; split the PDF "
            "or export a smaller date range."
        )
    if is_image:
        _guard_image(path)
        from apps.engine.ocr import extract_image

        return extract_image(path)
    _guard_pdf_pages(path)
    return extract_pdf(path)


def _guard_pdf_pages(path: Path) -> None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    try:
        reader = PdfReader(str(path), strict=False)
        page_count = len(reader.pages)
    except Exception:
        return
    if page_count > MAX_BANK_PDF_PAGES:
        raise ValueError(
            f"This PDF has {page_count:,} pages. The safe bank-statement limit "
            f"is {MAX_BANK_PDF_PAGES:,} pages; split the PDF and re-import it."
        )


def _guard_image(path: Path) -> None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return
    pixels = int(width) * int(height)
    if pixels > MAX_BANK_IMAGE_PIXELS:
        raise ValueError(
            f"This image is {width:,} x {height:,} pixels, above the safe "
            f"limit of {MAX_BANK_IMAGE_PIXELS:,} pixels. Resize it and re-import."
        )


def _guard_extracted(extracted: ExtractedPdf) -> None:
    if extracted.page_count > MAX_BANK_PDF_PAGES:
        raise ValueError(
            f"This document has {extracted.page_count:,} pages. The safe "
            f"bank-statement limit is {MAX_BANK_PDF_PAGES:,} pages; split it "
            "and re-import."
        )


def _rows_from_extracted_tables(
    tables: list, profile: BankProfile, filename: str
) -> list[dict]:
    rows: list[dict] = []
    for table in tables:
        grid = getattr(table, "grid", None)
        if grid and len(grid) >= 2:
            page_no = getattr(table, "page", 1)
            bbox = getattr(table, "bbox", None)
            rows.extend(rows_from_cell_tables([grid], profile, filename, page_no, bbox))
    return rows


def _rows_from_extracted_words(
    extracted: ExtractedPdf, profile: BankProfile, filename: str
) -> tuple[list[dict], int]:
    words = list(extracted.words or [])
    rows = rows_from_words(words, profile, filename)
    return rows, len(rows)


MONTHS_PAT = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
DAY_MON_RE = re.compile(rf"\b(\d{{1,2}})\s*({MONTHS_PAT})\b", re.I)
SERIAL_DAY_RE = re.compile(r"^\s*(?:\d{1,3}|[a-zA-Z]{1,2})\s+(\d{1,2})\b")


def _detect_period_ym(header: str) -> str | None:
    match = re.search(
        r"(\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4})\s*(?:-|to)\s*(\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4})",
        header,
        re.I,
    )
    if match:
        norm = normalize_date(match.group(1))
        if norm:
            return norm[:7]
    match_slash = re.search(
        r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})\s*(?:-|to)\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})",
        header,
    )
    if match_slash:
        norm = normalize_date(match_slash.group(1))
        if norm:
            return norm[:7]
    return None


def _is_txn_start(text: str) -> bool:
    if is_boilerplate(text):
        return False
    if DATE_RE.search(text):
        return True
    if DAY_MON_RE.search(text):
        return True
    if SERIAL_DAY_RE.search(text) and amounts_in(text):
        return True
    return False


def _extract_line_date(
    text: str, default_ym: str | None, last_date: str | None
) -> tuple[str | None, str]:
    m = DATE_RE.search(text)
    if m:
        d = normalize_date(m.group(1))
        if d and is_plausible_iso_date(d):
            return d, DATE_RE.sub("", text, count=1)
    m = DAY_MON_RE.search(text)
    if m:
        day = int(m.group(1))
        mon = m.group(2).capitalize()
        year = default_ym.split("-")[0] if default_ym else "2026"
        d = normalize_date(f"{day:02d} {mon} {year}")
        if d and is_plausible_iso_date(d):
            return d, DAY_MON_RE.sub("", text, count=1)
    m = SERIAL_DAY_RE.search(text)
    if m and default_ym:
        day = int(m.group(1))
        if 1 <= day <= 31:
            d = f"{default_ym}-{day:02d}"
            return d, SERIAL_DAY_RE.sub("", text, count=1)
    if last_date and amounts_in(text):
        return last_date, text
    return None, text


def _rows_from_lines(
    lines: list[LineBox],
    profile: BankProfile,
    filename: str,
    default_ym: str | None = None,
    words: list[WordBox] | None = None,
) -> tuple[list[dict], int]:
    rows: list[dict] = []
    candidate_count = 0
    last_date = f"{default_ym}-01" if default_ym else None
    words_by_page: dict[int, list[WordBox]] = {}
    if words:
        for w in words:
            words_by_page.setdefault(w.page, []).append(w)

    index = 0
    while index < len(lines):
        line = lines[index]
        text = clean_text(line.text)
        if not _is_txn_start(text):
            if rows and is_continuation(text) and not amounts_in(text) and not SERIAL_DAY_RE.search(text):
                extra = text.strip()
                if extra:
                    rows[-1]["description"] = f"{rows[-1]['description']} {extra}".strip()
                    rows[-1]["raw_text"] = f"{rows[-1]['raw_text']} | {extra}"
            index += 1
            continue

        block, index = _expand_txn_lines(lines, index)
        merged = _merge_line_boxes(block)
        merged_text = clean_text(merged.text)

        # Prefer the layout-led row when the printed line is complete.  The
        # word-position path below is for scanned/column-only statements whose
        # line text does not carry a full date and all three money columns.
        layout_row = _line_to_row(merged, profile, filename)
        if layout_row is not None:
            candidate_count += 1
            last_date = layout_row["date"]
            rows.append(layout_row)
            continue

        date, desc = _extract_line_date(merged_text, default_ym, last_date)
        amts = amounts_in(merged_text)
        if not date or not amts:
            continue

        candidate_count += 1
        last_date = date

        # Map amounts with word boxes if available
        p_words = [
            w for w in words_by_page.get(line.page, [])
            if abs(w.y - line.y) < 8
        ]
        debit, credit, balance = None, None, None
        if p_words:
            for w in sorted(p_words, key=lambda item: item.x):
                w_text = w.text.replace(",", ".") if re.fullmatch(r"\d{1,4},\d{2}", w.text) else w.text
                v = parse_amount(w_text)
                if v is not None:
                    if 340 <= w.x < 415 and debit is None and balance is None:
                        debit = v
                    elif 415 <= w.x < 488 and credit is None and balance is None:
                        credit = v
                    elif w.x >= 488 and balance is None:
                        balance = v

        if debit is None and credit is None and balance is None:
            balance = amts[-1] if len(amts) >= 2 else None
            d_amt, c_amt = _debit_credit(amts, merged_text, profile)
            debit = d_amt
            credit = c_amt

        for amount in amts[-3:]:
            desc = desc.replace(f"{amount:,}", "").replace(str(amount), "")
        desc = re.sub(r"\s{2,}", " ", desc).strip(" -|")

        cheque = None
        chq = re.search(r"\b(?:chq|cheque|ref)[^\d]{0,6}(\d{4,})\b", merged_text, re.I)
        if chq:
            cheque = chq.group(1)

        bbox = None
        if merged.width or merged.height:
            bbox = f"{merged.x:.1f},{merged.y:.1f},{merged.width:.1f},{merged.height:.1f}"

        rows.append({
            "date": date,
            "description": desc or merged_text,
            "cheque_ref": cheque,
            "debit": _dec(debit),
            "credit": _dec(credit),
            "balance": _dec(balance),
            "source_page": merged.page,
            "source_bbox": bbox,
            "source": f"{filename}#p{merged.page}" + (f"@{bbox}" if bbox else ""),
            "raw_text": merged_text,
            "flags": [],
        })

    return rows, candidate_count


def _expand_txn_lines(lines: list[LineBox], start: int) -> tuple[list[LineBox], int]:
    block = [lines[start]]
    cursor = start + 1
    while cursor < len(lines) and cursor - start < 8:
        nxt = clean_text(lines[cursor].text)
        if not nxt:
            cursor += 1
            continue
        if _is_txn_start(nxt) or is_boilerplate(nxt):
            break
        combined = clean_text(" ".join(item.text for item in block))
        if looks_like_txn(combined) and is_amount_line(nxt):
            break
        if looks_like_txn(combined) and not amounts_in(nxt) and not is_continuation(nxt):
            break
        if looks_like_txn(combined) and is_continuation(nxt):
            block.append(lines[cursor])
            cursor += 1
            continue
        if not looks_like_txn(combined):
            block.append(lines[cursor])
            cursor += 1
            continue
        break
    return block, cursor


def _merge_line_boxes(lines: list[LineBox]) -> LineBox:
    first = lines[0]
    text = clean_text(" ".join(line.text for line in lines))
    xs = [line.x for line in lines]
    ys = [line.y for line in lines]
    rights = [line.x + line.width for line in lines]
    tops = [line.y + line.height for line in lines]
    return LineBox(
        page=first.page,
        text=text,
        x=min(xs),
        y=min(ys),
        width=max(rights) - min(xs),
        height=max(tops) - min(ys),
    )


def _finish_rows(
    raw_rows: list[dict],
    opening: Decimal | None,
    account: str | None,
    ifsc: str | None,
    profile: BankProfile,
) -> list[dict]:
    rows: list[dict] = []
    running = opening
    for raw in raw_rows:
        row = dict(raw)
        gap = _implied_gap_row(row, running)
        if gap is not None:
            gap["account_number"] = account
            gap["ifsc"] = ifsc
            gap["account_name"] = profile.label
            rows.append(gap)
            running = Decimal(str(gap["balance"]))
        row = _align_to_running(row, running)
        row["account_number"] = account
        row["ifsc"] = ifsc
        row["account_name"] = profile.label
        rows.append(row)
        if row.get("balance") is not None:
            running = Decimal(str(row["balance"]))
    return rows


def _choose_rows(
    opening: Decimal | None,
    closing: Decimal | None,
    *options: tuple[str, list[dict], int],
) -> tuple[list[dict], int, str]:
    best_name = "lines"
    best_rows: list[dict] = []
    best_candidates = 0
    best_key = (-2, 0, -1, 0, 0)
    for name, rows, candidates in options:
        quality = _quality(rows, opening, closing)
        prefer = {"docling": 3, "pdfplumber": 2, "markdown": 1}.get(name, 0) if rows else 0
        # Prefer a strategy that extracted more real transactions before falling
        # back to source preference.  A parser that silently loses half the rows
        # can still balance via inferred gap rows, so raw length is not enough.
        key = (quality[0], quality[1], quality[2], quality[3], prefer)
        if key > best_key:
            best_key = key
            best_name = name
            best_rows = rows
            best_candidates = candidates
    return best_rows, max(best_candidates, len(best_rows)), best_name


def _quality(rows: list[dict], opening: Decimal | None, closing: Decimal | None) -> tuple:
    if not rows:
        return (-1, 0, 0, 0)
    from apps.engine.validators.balance import check_balance

    probe = copy.deepcopy(rows)
    check = check_balance(
        probe,
        float(opening) if opening is not None else None,
        float(closing) if closing is not None else None,
    )
    rank = {"match": 3, "unverified": 1, "mismatch": 0}.get(check.get("status"), 0)
    breaks = sum(
        1
        for row in rows
        if "running_balance_break" in (row.get("flags") or [])
        or "balance_mismatch" in (row.get("flags") or [])
    )
    inferred = sum(
        1 for row in rows if "inferred_from_balance" in (row.get("flags") or [])
    )
    real_rows = len(rows) - inferred
    return (rank, real_rows - breaks, real_rows, len(rows))


def _search(text: str, pattern: re.Pattern) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _balance_near(extracted: ExtractedPdf, pattern: re.Pattern) -> Decimal | None:
    for line in extracted.lines:
        if pattern.search(line.text):
            amounts = amounts_in(line.text)
            if amounts:
                return amounts[-1]
    for page in extracted.pages:
        for raw in page.text.splitlines():
            if pattern.search(raw):
                amounts = amounts_in(raw)
                if amounts:
                    return amounts[-1]
    return None


def _implied_gap_row(row: dict, running: Decimal | None) -> dict | None:
    if running is None or row.get("balance") is None:
        return None
    stated = Decimal(str(row["balance"]))
    debit = Decimal(str(row["debit"])) if row.get("debit") else Decimal("0")
    credit = Decimal(str(row["credit"])) if row.get("credit") else Decimal("0")
    expected = running - debit + credit
    gap = expected - stated
    if gap.copy_abs() <= Decimal("1.00"):
        return None
    txn = debit if debit else credit
    if txn:
        if (running - txn - stated).copy_abs() <= Decimal("1.00"):
            return None
        if (running + txn - stated).copy_abs() <= Decimal("1.00"):
            return None
        if gap.copy_abs() > running.copy_abs() + txn.copy_abs() + Decimal("1.00"):
            return None
    if debit and credit:
        return None
    inferred_balance = running - gap
    flags = ["inferred_from_balance"]
    return {
        "date": row.get("date"),
        "description": "Inferred missing row (statement wrap)",
        "cheque_ref": None,
        "debit": float(gap) if gap > 0 else None,
        "credit": float(-gap) if gap < 0 else None,
        "balance": float(inferred_balance),
        "source_page": row.get("source_page"),
        "source_bbox": row.get("source_bbox"),
        "source": row.get("source"),
        "raw_text": "",
        "flags": flags,
        "validation_flags": flags,
    }


def _align_to_running(row: dict, running: Decimal | None) -> dict:
    flags = list(row.get("flags") or row.get("validation_flags") or [])
    if running is None or row.get("balance") is None:
        row["flags"] = flags
        return row
    stated = Decimal(str(row["balance"]))
    debit = Decimal(str(row["debit"])) if row.get("debit") else Decimal("0")
    credit = Decimal(str(row["credit"])) if row.get("credit") else Decimal("0")
    if (running - debit + credit - stated).copy_abs() <= Decimal("1.00"):
        row["flags"] = flags
        return row

    if debit and credit:
        if (running - debit - stated).copy_abs() <= Decimal("1.00"):
            row["debit"] = float(debit)
            row["credit"] = None
            row["flags"] = flags
            return row
        if (running + credit - stated).copy_abs() <= Decimal("1.00"):
            row["credit"] = float(credit)
            row["debit"] = None
            row["flags"] = flags
            return row

    txn = debit if debit else credit
    if txn:
        if (running - txn - stated).copy_abs() <= Decimal("1.00"):
            row["debit"] = float(txn)
            row["credit"] = None
            row["flags"] = flags
            return row
        if (running + txn - stated).copy_abs() <= Decimal("1.00"):
            row["credit"] = float(txn)
            row["debit"] = None
            row["flags"] = flags
            return row
    if "running_balance_break" not in flags:
        flags.append("running_balance_break")
    row["flags"] = flags
    row["validation_flags"] = flags
    return row


def _line_to_row(line: LineBox, profile: BankProfile, filename: str) -> dict | None:
    text = clean_text(line.text)
    if len(text) < 8 or is_boilerplate(text):
        return None
    date_match = DATE_RE.search(text)
    if not date_match:
        return None
    amounts = amounts_in(text)
    if len(amounts) < 2:
        return None

    date = normalize_date(date_match.group(1))
    if not is_plausible_iso_date(date):
        return None
    balance = amounts[-1]
    debit, credit = _debit_credit(amounts, text, profile)

    description = DATE_RE.sub("", text, count=1)
    description = strip_amount_tokens(description)
    description = re.sub(r"\s{2,}", " ", description).strip(" -|")

    cheque = None
    chq = re.search(r"\b(?:chq|cheque|ref)[^\d]{0,6}(\d{4,})\b", text, re.I)
    if chq:
        cheque = chq.group(1)

    bbox = None
    if line.width or line.height:
        bbox = f"{line.x:.1f},{line.y:.1f},{line.width:.1f},{line.height:.1f}"

    return {
        "date": date,
        "description": description or text,
        "cheque_ref": cheque,
        "debit": _dec(debit),
        "credit": _dec(credit),
        "balance": _dec(balance),
        "source_page": line.page,
        "source_bbox": bbox,
        "source": f"{filename}#p{line.page}" + (f"@{bbox}" if bbox else ""),
        "raw_text": text,
        "flags": [],
    }


def attach_currency(rows: list[dict], decision: dict) -> None:
    """Stamp an effective currency decision onto every transaction row."""
    code = decision.get("currency_code")
    status = decision.get("currency_status")
    source = decision.get("currency_source")
    confidence = decision.get("currency_confidence")
    minor = decision.get("currency_minor_units")
    for row in rows:
        row["currency_code"] = code
        row["currency_status"] = status
        row["currency_source"] = source
        row["currency_confidence"] = confidence
        row["currency_minor_units"] = minor


def _flag_duplicate_source_rows(rows: list[dict]) -> int:
    """Flag exact repeated source rows without deleting either transaction.

    Legitimate identical transactions normally come from different source
    coordinates.  An exact match on date, description, amounts, balance and
    source reference is strong evidence of a duplicated extraction, but we
    still keep both rows so a human can decide.
    """
    seen: set[tuple] = set()
    duplicates = 0
    for row in rows:
        key = (
            row.get("date"),
            clean_text(row.get("description") or ""),
            row.get("debit"),
            row.get("credit"),
            row.get("balance"),
            row.get("source"),
            row.get("source_page"),
            row.get("source_bbox"),
        )
        if key in seen:
            flags = list(row.get("flags") or [])
            if "duplicate_source_row" not in flags:
                flags.append("duplicate_source_row")
            row["flags"] = flags
            row["validation_flags"] = flags
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def _dec(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
