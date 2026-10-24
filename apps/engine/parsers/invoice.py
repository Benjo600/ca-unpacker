"""General-purpose GST / non-GST invoice extraction.

The parser is deliberately layout-led rather than vendor-led:

* A document is split into one record per distinct invoice number (or per
  fresh invoice header when a number is missing).  Every record is parsed
  independently, so a PDF containing several invoices produces several rows.
* Inside a record the column model is learnt from the printed header.  Header
  labels may wrap over several lines, appear in any order and omit optional
  columns.  When the extractor gives no x coordinates, the header order is
  used instead.
* Item rows may wrap over several lines.  Description fragments and HSN/SAC
  codes found on continuation lines are attached to the row above them.
* Totals, tax summaries and line items are reconciled against each other;
  anything uncertain is flagged instead of being silently dropped or
  invented.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from apps.engine.ocr import extract_image
from apps.engine.parsers.bank.money import DATE_RE, normalize_date, parse_amount
from apps.engine.pdf_extract import ExtractedPdf, LineBox, extract_pdf
from apps.engine.validators.gstin import find_gstins, gstin_flags, hsn_flags

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

INV_RE = re.compile(
    r"(?:(?:tax\s+)?invoice|inv\.?|bill)\s*(?:no\.?|number|num\.?|#)\s*[:#.\-]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9/_\-]{1,40})",
    re.I,
)
CREDIT_NOTE_RE = re.compile(
    r"credit\s+note\s*(?:no\.?|number|num\.?|#)\s*[:#.\-]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9/_\-]{1,40})",
    re.I,
)

_DATE_BODY = (
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{1,2}[\s\-./]+[A-Za-z]{3,9}\.?\s*[\s\-./,]*\d{2,4})"
)
INVOICE_DATE_RE = re.compile(
    r"(?:tax\s+invoice|invoice|bill)\s*(?:date|dt)\s*[:.\-]?\s*" + _DATE_BODY,
    re.I,
)
DATED_RE = re.compile(r"\bdated\s*[:.\-]?\s*" + _DATE_BODY, re.I)

HSN_RE = re.compile(r"\b(?:HSN(?:/SAC)?|SAC)\b\s*(?:code)?\s*[:.\-]?\s*(\d{4,8})\b", re.I)
GSTIN_LOOSE_RE = re.compile(r"\b[0-9]{2}[A-Z0-9]{13}\b", re.I)
_HSN_TOKEN_RE = re.compile(r"^\d{4,8}$")
_NUMBER_TOKEN_RE = re.compile(r"^\d{1,4}$")

TOTAL_LABELS = (
    r"grand\s+total|invoice\s+total|invoice\s+value|total\s+invoice\s+value|"
    r"total\s+amount|total\s+price|bill\s+amount|net\s+payable|total\s+payable|amount\s+payable"
)
TAXABLE_LABELS = (
    r"total\s+taxable\s+value|taxable\s+value|taxable\s+amount|taxable\s+amt|"
    r"net\s+taxable\s+value|total\s+taxable\s+amount"
)
TAX_LABELS = r"total\s+tax|tax\s+amount|total\s+gst"

SUPPLIER_LABELS = re.compile(
    r"(?:sold\s+by|supplier|seller|vendor|billed\s+by|invoice\s+from|m/s\.?|trade\s+name)"
    r"\s*(?:name)?\s*[:.\-]\s*",
    re.I,
)
CUSTOMER_LABELS = re.compile(
    r"(?:bill\s+to|customer\s+name|buyer\s+name|billed\s+to|buyer|customer)\s*[:.\-]\s*",
    re.I,
)
CUSTOMER_GSTIN_LABELS = re.compile(
    r"(?:buyer|customer|recipient|billed\s+to|bill\s+to)\s*(?:'s)?\s*gstin\s*[:.\-]?\s*", re.I
)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
_OCR_ENGINES = {"rapidocr", "tesseract"}
_METADATA_PREFIXES = (
    "warranty",
    "imei",
    "serial",
    "model",
    "batch",
    "terms",
    "declaration",
    "bank",
    "ifsc",
    "pan",
    "cin",
    "phone",
    "email",
    "www",
    "page",
    "e. & o.e",
    "e.&o.e",
    "authorised",
    "authorized",
    "signature",
    "for ",
    "returns",
    "contact",
    "regd",
    "registered",
)
_ADDRESS_HINTS = (
    "road",
    "street",
    "division",
    "nagar",
    "layout",
    "sector",
    "floor",
    "pin",
    "phone",
    "karnataka",
    "maharashtra",
    "gujarat",
    "delhi",
    "mumbai",
    "bangalore",
    "bengaluru",
    "address",
    "india",
)

# Header synonyms.  Longest phrase wins; generic words are only used when no
# more specific label occupies the same column.
_HEADER_SYNONYMS: dict[str, set[str]] = {
    "description": {
        "description",
        "desc",
        "product",
        "product title",
        "title",
        "particulars",
        "item",
        "items",
        "goods",
        "service",
        "services",
        "nature of service",
        "name of product",
        "name of item",
        "item description",
        "product description",
    },
    "hsn": {"hsn", "sac", "hsn/sac", "hsn code", "sac code", "hsn sac"},
    "qty": {"qty", "qty.", "quantity", "qnty", "nos", "nos.", "units", "pcs", "qty nos"},
    "rate": {"rate", "unit rate", "unit price", "price", "rate per unit", "per unit", "unit cost"},
    "gross": {"gross", "gross amount", "gross amt", "gross value", "mrp", "list price"},
    "discount": {
        "discount",
        "discounts",
        "disc",
        "disc.",
        "coupon",
        "coupons",
        "rebate",
        "less discount",
        "discount amount",
    },
    "taxable": {
        "taxable",
        "taxable value",
        "net amount",
        "net value",
        "basic value",
        "basic amount",
        "value",
    },
    "sgst": {"sgst", "utgst", "sgst/utgst", "state gst", "state tax"},
    "cgst": {"cgst", "central gst", "central tax"},
    "igst": {"igst", "integrated gst", "integrated tax"},
    "cess": {"cess"},
    "tax": {"tax", "gst", "tax amount"},
    "total": {"total", "total amount", "total value", "invoice total", "line total", "net total"},
    "amount": {"amount", "amt", "amount rs", "value rs"},
}
_HEADER_INDEX: dict[str, str] = {
    phrase: field_name
    for field_name, phrases in _HEADER_SYNONYMS.items()
    for phrase in phrases
}
_HEADER_WORDS = {word for phrase in _HEADER_INDEX for word in phrase.split()}
_IGNORED_HEADER_WORDS = {
    "sr",
    "s.no",
    "sno",
    "sl",
    "no",
    "#",
    "code",
    "unit",
    "uom",
    "inr",
    "rs",
    "₹",
    "percentage",
    "percent",
    "%",
}

# Specific labels beat generic ones when two labels land on the same column.
_FIELD_PRIORITY = {
    "description": 100,
    "hsn": 95,
    "qty": 90,
    "rate": 85,
    "gross": 80,
    "discount": 75,
    "taxable": 70,
    "sgst": 65,
    "cgst": 64,
    "igst": 63,
    "cess": 62,
    "tax": 55,
    "total": 50,
    "amount": 40,
}
_NUMERIC_FIELDS = {
    "qty",
    "rate",
    "gross",
    "discount",
    "taxable",
    "sgst",
    "cgst",
    "igst",
    "cess",
    "tax",
    "total",
    "amount",
}
_OPTIONAL_FIELDS = ("discount", "cess", "igst", "cgst", "sgst", "rate", "qty", "tax")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class _Token:
    text: str
    x0: float = 0.0
    x1: float = 0.0

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2.0


@dataclass
class _Column:
    field: str
    x0: float
    x1: float
    sequence: int = 0

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2.0


@dataclass
class _Header:
    fields: list[str]
    columns: list[_Column]
    start: int
    end: int
    positioned: bool


@dataclass
class _Record:
    number: str | None
    lines: list[LineBox] = field(default_factory=list)
    start_page: int = 1
    split_reason: str | None = None
    document_type: str = "invoice"


@dataclass
class _Values:
    values: dict[str, Decimal] = field(default_factory=dict)
    description: str = ""
    hsn: str | None = None
    uncertain: bool = False
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_invoice_file(path: Path, filename: str | None = None) -> dict:
    path = Path(path)
    extracted = _extract(path)
    source = filename or path.name
    records = _split_records(extracted.lines)
    rows: list[dict] = []
    line_items: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    ignored: list[dict] = []
    document_flags: list[str] = []

    if extracted.engine in _OCR_ENGINES:
        document_flags.append("ocr_source")

    for index, record in enumerate(records):
        if record.document_type != "invoice":
            ignored.append(
                {
                    "record": index + 1,
                    "document_type": record.document_type,
                    "number": record.number,
                    "page": record.start_page,
                }
            )
            document_flags.append(f"{record.document_type}_ignored")
            continue
        try:
            row, items, record_skipped = _parse_record(record, extracted, source, index)
        except Exception as error:  # a single bad layout must not sink the document
            failed.append(
                {
                    "record": index + 1,
                    "invoice_number": record.number,
                    "page": record.start_page,
                    "reason": f"parser error: {type(error).__name__}",
                }
            )
            continue
        skipped.extend(record_skipped)
        if row is None or not items:
            failed.append(
                {
                    "record": index + 1,
                    "invoice_number": record.number,
                    "page": record.start_page,
                    "reason": "no line items",
                }
            )
            continue
        row["record_index"] = index + 1
        for item in items:
            item["invoice_number"] = row.get("invoice_number")
            item["record_index"] = index + 1
        rows.append(row)
        line_items.extend(items)

    return {
        "rows": rows,
        "line_items": line_items,
        "engine": extracted.engine,
        "unreadable": not rows,
        "record_count": len(records),
        "invoice_record_count": sum(
            1 for record in records if record.document_type == "invoice"
        ),
        "skipped_rows": skipped,
        "failed_records": failed,
        "ignored_documents": ignored,
        "warnings": document_flags,
    }


def _extract(path: Path) -> ExtractedPdf:
    if path.suffix.lower() in _IMAGE_SUFFIXES:
        return extract_image(path)
    return extract_pdf(path)


# ---------------------------------------------------------------------------
# Document segmentation
# ---------------------------------------------------------------------------


def _clean(text: str | None) -> str:
    value = html.unescape(text or "")
    value = value.replace("\u00a0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", value).strip()


def _invoice_anchor(text: str) -> str | None:
    cleaned = _clean(text)
    match = INV_RE.search(cleaned)
    if not match:
        return None
    prefix = cleaned[: match.start()].lower().rstrip()
    if prefix.endswith("original") or "original invoice" in prefix:
        # \"Original Invoice Number\" is a reference to an earlier document,
        # not the identity of this one.
        return None
    value = match.group(1).strip(" .,:;#-")
    if not value or value.lower() in {"number", "date", "no", "num"}:
        return None
    if not any(character.isdigit() for character in value):
        return None
    return value


def _ordered_lines(lines: list[LineBox]) -> list[LineBox]:
    """Reading order, keeping extractor order for coordinate-less sources."""
    indexed = list(enumerate(lines))
    indexed.sort(key=lambda pair: (pair[1].page, -pair[1].y, pair[0]))
    return [line for _, line in indexed]


def _group_pages(lines: list[LineBox]) -> list[tuple[int, list[LineBox]]]:
    pages: list[tuple[int, list[LineBox]]] = []
    current: list[LineBox] = []
    current_page: int | None = None
    for line in _ordered_lines(lines):
        page = int(line.page or 1)
        if current_page is None:
            current_page = page
        if page != current_page:
            pages.append((current_page, current))
            current = []
            current_page = page
        current.append(line)
    if current:
        pages.append((current_page or 1, current))
    return pages


def _record_has_items(record: _Record) -> bool:
    return any(_money_line(line.text) for line in record.lines)


def _money_line(text: str) -> bool:
    return any(_money(token) is not None for token in _clean(text).split())


def _starts_fresh_invoice(page_lines: list[LineBox]) -> bool:
    head = " ".join(_clean(line.text) for line in page_lines[:8]).lower()
    if "continued" in head or "contd" in head:
        return False
    if re.search(r"\bcredit\s+note\b|\bdebit\s+note\b", head):
        return False
    if not re.search(r"\b(tax\s+)?invoice\b", head):
        return False
    return any(
        token in head
        for token in ("sold by", "supplier", "bill to", "invoice date", "invoice no", "invoice number")
    )


def _page_document_type(page_lines: list[LineBox]) -> str:
    head = " ".join(_clean(line.text) for line in page_lines[:6]).lower()
    if re.search(r"\bcredit\s+note\b", head):
        return "credit_note"
    if re.search(r"\bdebit\s+note\b", head):
        return "debit_note"
    return "invoice"


def _credit_note_number(page_lines: list[LineBox]) -> str | None:
    for line in page_lines:
        match = CREDIT_NOTE_RE.search(_clean(line.text))
        if match:
            value = match.group(1).strip(" .,:;#-")
            if value and any(character.isdigit() for character in value):
                return value
    return None


def _credit_note_anchor(text: str) -> str | None:
    match = CREDIT_NOTE_RE.search(_clean(text))
    if not match:
        return None
    value = match.group(1).strip(" .,:;#-")
    if not value or not any(character.isdigit() for character in value):
        return None
    return value


def _split_records(lines: list[LineBox]) -> list[_Record]:
    records: list[_Record] = []
    current: _Record | None = None

    for page, page_lines in _group_pages(lines):
        document_type = _page_document_type(page_lines)

        if document_type != "invoice":
            # Credit/debit notes are separate documents.  Keep them out of the
            # tax-invoice records so their lines and totals cannot contaminate
            # a real invoice.
            note_anchors = [
                (index, number)
                for index, line in enumerate(page_lines)
                if (number := _credit_note_anchor(line.text))
            ]
            first_note = note_anchors[0][1] if note_anchors else None
            if (
                current is None
                or current.document_type != document_type
                or (
                    first_note
                    and current.number
                    and first_note.upper() != current.number.upper()
                )
                or (
                    first_note
                    and current.number is None
                    and current.lines
                )
            ):
                current = _Record(
                    first_note,
                    start_page=page,
                    split_reason=document_type,
                    document_type=document_type,
                )
                records.append(current)
            elif current.number is None and first_note:
                current.number = first_note
            current.lines.extend(page_lines)
            continue

        anchors = [
            (index, number)
            for index, line in enumerate(page_lines)
            if (number := _invoice_anchor(line.text))
        ]

        if not anchors:
            if current is None or current.document_type != "invoice":
                current = _Record(None, start_page=page, split_reason="document_start")
                records.append(current)
            elif _starts_fresh_invoice(page_lines) and _record_has_items(current):
                current = _Record(None, start_page=page, split_reason="page_header")
                records.append(current)
            current.lines.extend(page_lines)
            continue

        first_number = anchors[0][1]
        if current is None or current.document_type != "invoice":
            current = _Record(None, start_page=page, split_reason="document_start")
            records.append(current)
        elif current.number and first_number.upper() != current.number.upper():
            current = _Record(None, start_page=page, split_reason="invoice_number")
            records.append(current)
        elif current.number is None and current.lines and _starts_fresh_invoice(page_lines):
            current = _Record(None, start_page=page, split_reason="page_header")
            records.append(current)

        # Page preamble (supplier block, address) belongs to the record whose
        # invoice number appears on this page.
        current.lines.extend(page_lines[: anchors[0][0]])
        if current.number is None:
            current.number = first_number

        for line in page_lines[anchors[0][0] :]:
            number = _invoice_anchor(line.text)
            if number and current.number and number.upper() != current.number.upper():
                current = _Record(number, start_page=page, split_reason="invoice_number")
                records.append(current)
            elif number and current.number is None:
                current.number = number
            current.lines.append(line)

    return records


# ---------------------------------------------------------------------------
# Tokens and money
# ---------------------------------------------------------------------------


def _words_for_line(line: LineBox, line_words: dict[int, list]) -> list:
    return line_words.get(id(line), [])


def _assign_words(lines: list[LineBox], words: list) -> dict[int, list]:
    """Assign every extracted word to exactly one line.

    PDF extractors sometimes emit overlapping line boxes for the same visual
    row (for example a description line and its numeric cells).  A naive
    y-band lookup then pulls the numeric cells into the description line and
    duplicates the row.  Scoring by vertical distance plus text containment
    keeps each word with the line it was printed on.
    """
    result: dict[int, list] = {id(line): [] for line in lines}
    by_page: dict[int, list] = {}
    for word in words:
        by_page.setdefault(int(word.page or 1), []).append(word)
    for page, page_words in by_page.items():
        page_lines = [line for line in lines if int(line.page or 1) == page]
        if not page_lines:
            continue
        for word in page_words:
            center = word.y + word.height / 2.0
            text = _clean(word.text)
            best: LineBox | None = None
            best_score: float | None = None
            for line in page_lines:
                line_center = line.y + line.height / 2.0
                contains = bool(text) and text in _clean(line.text)
                score = abs(center - line_center) + (0.0 if contains else 10.0)
                if best_score is None or score < best_score:
                    best = line
                    best_score = score
            if best is not None:
                result[id(best)].append(word)
    for items in result.values():
        items.sort(key=lambda word: (word.x, word.y))
    return result


def _tokens_for_line(line: LineBox, line_words: dict[int, list]) -> tuple[list[_Token], bool]:
    band = _words_for_line(line, line_words)
    raw = _clean(line.text)
    if len(band) >= 2 and not (len(band) == 1 and _clean(band[0].text) == raw):
        tokens = [
            _Token(
                text=_clean(word.text),
                x0=float(word.x),
                x1=float(word.x + word.width),
            )
            for word in band
            if _clean(word.text)
        ]
        if tokens and any(token.x1 > token.x0 for token in tokens):
            return tokens, True
    return [_Token(text=token) for token in raw.split()], False


def _money(raw: str) -> Decimal | None:
    text = (raw or "").strip()
    if not text or "%" in text:
        return None
    text = re.sub(r"^(?:₹|Rs\.?|INR|USD|EUR|GBP|\$|€|£)\s*", "", text, flags=re.I)
    text = re.sub(r"\s*(?:₹|Rs\.?|INR|USD|EUR|GBP|\$|€|£)$", "", text, flags=re.I)
    if not text:
        return None
    if not re.fullmatch(r"[0-9.,'+\-()]+", text):
        return None
    return parse_amount(text)


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _f(value) -> float | None:
    number = _decimal(value)
    return float(number) if number is not None else None


def _norm_word(text: str) -> str:
    value = (text or "").lower()
    value = value.replace("₹", " ").replace(":", " ").replace("(", " ").replace(")", " ")
    value = value.replace(".", "").replace(",", " ")
    value = re.sub(r"\s+", " ", value).strip(" -/#")
    return value


# ---------------------------------------------------------------------------
# Header detection
# ---------------------------------------------------------------------------


def _header_spans(tokens: list[_Token]) -> list[tuple[int, int, str, _Token, _Token]]:
    norms = [_norm_word(token.text) for token in tokens]
    spans: list[tuple[int, int, str, _Token, _Token]] = []
    index = 0
    while index < len(norms):
        matched: tuple[int, str] | None = None
        for size in (3, 2, 1):
            if index + size > len(norms):
                continue
            phrase = " ".join(norms[index : index + size]).strip()
            if phrase in _HEADER_INDEX:
                matched = (size, _HEADER_INDEX[phrase])
                break
        if matched is None:
            index += 1
            continue
        size, field_name = matched
        first = tokens[index]
        last = tokens[index + size - 1]
        spans.append((index, index + size - 1, field_name, first, last))
        index += size
    return spans


def _window_header(
    record: _Record, start: int, end: int, line_words: dict[int, list]
) -> _Header | None:
    all_tokens: list[_Token] = []
    positioned = False
    sequence = 0
    anchors: list[tuple[str, _Token, _Token, int]] = []
    for line_index in range(start, end + 1):
        tokens, line_positioned = _tokens_for_line(record.lines[line_index], line_words)
        positioned = positioned or line_positioned
        all_tokens.extend(tokens)
        for _i, _j, field_name, first, last in _header_spans(tokens):
            anchors.append((field_name, first, last, sequence))
        sequence += len(tokens)

    if not anchors:
        return None

    if not positioned:
        fields: list[str] = []
        for field_name, _first, _last, _seq in anchors:
            if not fields or fields[-1] != field_name:
                fields.append(field_name)
        # A repeated description label ("Product Title") is one column.
        deduped: list[str] = []
        for field_name in fields:
            if field_name == "description" and "description" in deduped:
                continue
            deduped.append(field_name)
        if len(set(deduped)) < 2:
            return None
        return _Header(
            fields=deduped,
            columns=[],
            start=start,
            end=end,
            positioned=False,
        )

    columns = _columns_from_anchors(anchors)
    fields = [column.field for column in columns]
    if len(set(fields)) < 2:
        return None
    return _Header(fields=fields, columns=columns, start=start, end=end, positioned=True)


def _columns_from_anchors(anchors: list[tuple[str, _Token, _Token, int]]) -> list[_Column]:
    groups: list[dict] = []
    for field_name, first, last, sequence in anchors:
        x0 = min(first.x0, last.x0)
        x1 = max(first.x1, last.x1)
        center = (x0 + x1) / 2.0
        target = None
        for group in groups:
            tolerance = max(18.0, 0.45 * min(group["x1"] - group["x0"] + 1.0, x1 - x0 + 1.0))
            if abs(center - group["center"]) <= tolerance:
                target = group
                break
        if target is None:
            groups.append(
                {
                    "x0": x0,
                    "x1": x1,
                    "center": center,
                    "fields": [field_name],
                    "sequence": sequence,
                }
            )
        else:
            target["x0"] = min(target["x0"], x0)
            target["x1"] = max(target["x1"], x1)
            target["center"] = (target["x0"] + target["x1"]) / 2.0
            target["fields"].append(field_name)
            target["sequence"] = min(target["sequence"], sequence)

    columns: list[_Column] = []
    for group in groups:
        field_names = set(group["fields"])
        if "description" in field_names:
            chosen = "description"
        elif "hsn" in field_names:
            chosen = "hsn"
        else:
            chosen = max(field_names, key=lambda name: _FIELD_PRIORITY.get(name, 0))
        columns.append(_Column(chosen, group["x0"], group["x1"], group["sequence"]))

    # Merge split description anchors into one broad description column.
    descriptions = [column for column in columns if column.field == "description"]
    if len(descriptions) > 1:
        merged = _Column(
            "description",
            min(column.x0 for column in descriptions),
            max(column.x1 for column in descriptions),
            min(column.sequence for column in descriptions),
        )
        columns = [column for column in columns if column.field != "description"]
        columns.append(merged)

    # Merge remaining duplicate fields (e.g. "SGST" and "UTGST" on two lines).
    by_field: dict[str, list[_Column]] = {}
    for column in columns:
        by_field.setdefault(column.field, []).append(column)
    merged_columns: list[_Column] = []
    for field_name, items in by_field.items():
        if len(items) == 1:
            merged_columns.append(items[0])
            continue
        merged_columns.append(
            _Column(
                field_name,
                min(item.x0 for item in items),
                max(item.x1 for item in items),
                min(item.sequence for item in items),
            )
        )
    merged_columns.sort(key=lambda column: (column.center, column.sequence))
    return merged_columns


def _valid_header(header: _Header) -> bool:
    fields = set(header.fields)
    numeric = fields & _NUMERIC_FIELDS
    if not numeric:
        return False
    if "description" in fields or "hsn" in fields:
        return True
    return len(numeric) >= 3


def _header_like_line(tokens: list[_Token]) -> bool:
    if not tokens:
        return False
    for token in tokens:
        normalized = _norm_word(token.text)
        if not normalized:
            continue
        if normalized in {"₹", "%", "rs", "inr"}:
            continue
        if normalized in _HEADER_WORDS or normalized in _IGNORED_HEADER_WORDS:
            continue
        return False
    return True


def _header_followed_by_row(
    record: _Record, end: int, line_words: dict[int, list]
) -> bool:
    for index in range(end + 1, min(end + 8, len(record.lines))):
        line = record.lines[index]
        text = _clean(line.text)
        if not text:
            continue
        if _looks_like_summary(text):
            continue
        tokens, _positioned = _tokens_for_line(line, line_words)
        if any(_money(token.text) is not None for token in tokens):
            return True
    return False


def _find_header(
    record: _Record, start: int, line_words: dict[int, list]
) -> _Header | None:
    index = start
    while index < len(record.lines):
        for span in (1, 2, 3):
            end = index + span - 1
            if end >= len(record.lines):
                break
            if span > 1 and not _contiguous(record.lines[end - 1], record.lines[end]):
                break
            if span > 1:
                # Every physical line in a wrapped header must itself look
                # like header labels, otherwise we would swallow the supplier
                # block above the table.
                window_ok = True
                for line_index in range(index, end + 1):
                    window_tokens, _window_positioned = _tokens_for_line(
                        record.lines[line_index], line_words
                    )
                    if window_tokens and not _header_like_line(window_tokens):
                        window_ok = False
                        break
                if not window_ok:
                    continue
            header = _window_header(record, index, end, line_words)
            if header is None or not _valid_header(header):
                continue
            header = _extend_header(header, record, line_words)
            if not _header_followed_by_row(record, header.end, line_words):
                continue
            return header
        index += 1
    return None


def _contiguous(previous: LineBox, current: LineBox) -> bool:
    if previous.page != current.page:
        return False
    gap = previous.y - (current.y + current.height)
    return -2.0 <= gap <= 32.0


def _extend_header(
    header: _Header, record: _Record, line_words: dict[int, list]
) -> _Header:
    end = header.end
    while end + 1 < len(record.lines):
        candidate = record.lines[end + 1]
        if candidate.page != record.lines[end].page:
            break
        if not _contiguous(record.lines[end], candidate):
            break
        tokens, _positioned = _tokens_for_line(candidate, line_words)
        if not tokens or any(_money(token.text) is not None for token in tokens):
            break
        if not _header_like_line(tokens):
            break
        extended = _window_header(record, header.start, end + 1, line_words)
        if extended is None or not _valid_header(extended):
            break
        header = extended
        end += 1
    return header


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------


def _column_for(token: _Token, columns: list[_Column]) -> _Column | None:
    centers = [column.center for column in columns]
    if not centers:
        return None
    best = min(columns, key=lambda column: abs(token.center - column.center))
    if not columns:
        return None
    # Boundaries are midpoints between adjacent column centres.
    ordered = sorted(columns, key=lambda column: column.center)
    position = ordered.index(best)
    left = float("-inf") if position == 0 else (ordered[position - 1].center + best.center) / 2.0
    right = float("inf") if position == len(ordered) - 1 else (best.center + ordered[position + 1].center) / 2.0
    if left <= token.center < right:
        return best
    return None


def _positional_values(tokens: list[_Token], header: _Header, text: str) -> _Values:
    result = _Values()
    numeric_columns = [column for column in header.columns if column.field in _NUMERIC_FIELDS]
    if not numeric_columns:
        return result
    first_numeric = min(column.center for column in numeric_columns)
    last_numeric = max(column.center for column in numeric_columns)
    span = max(40.0, (last_numeric - first_numeric) / max(1, len(numeric_columns)))
    description_parts: list[str] = []

    for token in tokens:
        target = _column_for(token, header.columns)
        is_hsn = bool(_HSN_TOKEN_RE.match(token.text))
        if is_hsn and target is not None and target.field == "hsn":
            result.hsn = token.text
            continue
        if token.center < first_numeric - 5.0:
            description_parts.append(token.text)
            continue
        money = _money(token.text)
        if money is None:
            if target is not None and target.field == "description":
                description_parts.append(token.text)
            elif token.center <= last_numeric + span and any(
                character.isalpha() for character in token.text
            ):
                description_parts.append(token.text)
            continue
        if token.center > last_numeric + max(40.0, span * 0.75):
            result.uncertain = True
            result.notes.append("amount outside table")
            continue
        if target is None or target.field not in _NUMERIC_FIELDS:
            result.uncertain = True
            result.notes.append("unmapped amount")
            continue
        if target.field in result.values and result.values[target.field] != money:
            result.uncertain = True
            result.notes.append("duplicate column value")
            continue
        result.values[target.field] = money

    result.description = _strip_hsn(_join_description(description_parts))
    inline_hsn = _hsn_from_text(text)
    if inline_hsn:
        result.hsn = inline_hsn
    return result


def _sequential_values(tokens: list[_Token], header: _Header, text: str) -> _Values:
    result = _Values()
    texts = [token.text for token in tokens]
    fields = list(header.fields)

    hsn_indexes: set[int] = set()
    hsn = _hsn_from_text(text)
    if "hsn" in fields:
        for index, token_text in enumerate(texts):
            if _HSN_TOKEN_RE.match(token_text):
                hsn = token_text
                hsn_indexes.add(index)
                break
    result.hsn = hsn

    numeric_fields = [name for name in fields if name in _NUMERIC_FIELDS]
    numeric_positions: list[tuple[int, Decimal]] = []
    for index, token_text in enumerate(texts):
        if index in hsn_indexes:
            continue
        value = _money(token_text)
        if value is not None:
            numeric_positions.append((index, value))

    if not numeric_fields:
        result.description = _strip_hsn(_join_description(texts))
        return result

    values = [value for _index, value in numeric_positions]
    # Row-level optional columns may be blank; drop optional fields from the
    # mapping until the counts line up.  If they still do not line up we do
    # not guess financial values - the row is flagged and reported instead.
    while len(values) < len(numeric_fields):
        removed = False
        for optional in _OPTIONAL_FIELDS:
            if optional in numeric_fields:
                numeric_fields.remove(optional)
                removed = True
                break
        if not removed:
            break
    if len(values) != len(numeric_fields):
        result.uncertain = True
        result.notes.append("column count mismatch")
        return result
    if len(values) > len(numeric_fields):
        surplus = len(values) - len(numeric_fields)
        values = values[surplus:]
        consumed = len(numeric_positions) - len(values)
    else:
        consumed = len(numeric_positions) - len(values)

    for field_name, value in zip(numeric_fields, values):
        result.values[field_name] = value

    start_index = numeric_positions[consumed][0] if consumed < len(numeric_positions) else len(texts)
    description_tokens = [
        token
        for index, token in enumerate(texts)
        if index < start_index and index not in hsn_indexes
    ]
    result.description = _strip_hsn(_join_description(description_tokens))
    return result


_INLINE_METADATA_RE = re.compile(
    r"(?:(?:\s*\|\s*|\s+)(?:imei|sr\s*no|serial\s*(?:no|number))\s*[:#]?\s*.*$"
    r"|(?:\s*\|\s*|\s+)(?:warranty|fsn|sku|asin)\s*[:#]\s*.*$)",
    re.I,
)


def _strip_inline_metadata(text: str) -> str:
    return _INLINE_METADATA_RE.sub("", text or "").strip(" ,;:-|")


def _join_description(parts: list[str]) -> str:
    cleaned: list[str] = []
    for part in parts:
        value = _strip_inline_metadata(_clean(part))
        if not value or value in {"₹", "%", "|", "-"}:
            continue
        cleaned.append(value)
    return re.sub(r"\s+", " ", " ".join(cleaned)).strip(" ,;:-|")


def _strip_rate_labels(text: str) -> str:
    return re.sub(
        r"\b(?:SGST|CGST|IGST|UTGST|CESS|GST)\b\s*(?:@|:)?\s*\d{1,2}(?:\.\d+)?\s*%",
        " ",
        text or "",
        flags=re.I,
    )


def _strip_hsn(text: str) -> str:
    value = HSN_RE.sub(" ", text or "")
    value = re.sub(r"\b(?:HSN(?:/SAC)?|SAC)\b\s*(?:code)?\s*[:.\-]?\s*", " ", value, flags=re.I)
    value = _strip_rate_labels(value)
    return _join_description([value])


def _hsn_from_text(text: str) -> str | None:
    match = HSN_RE.search(text or "")
    return match.group(1) if match else None


def _is_item_row(values: _Values) -> bool:
    return any(
        values.values.get(name) is not None
        for name in ("amount", "total", "taxable", "gross", "rate")
    )


def _line_items(
    record: _Record, header: _Header, line_words: dict[int, list]
) -> tuple[list[dict], list[dict], dict[str, Decimal], list[str]]:
    items: list[dict] = []
    skipped: list[dict] = []
    totals: dict[str, Decimal] = {}
    summary_flags: list[str] = []
    current: dict | None = None
    pending_description: list[str] = []
    index = header.end + 1
    footer_seen = False
    footer_page: int | None = None

    while index < len(record.lines):
        line = record.lines[index]
        text = _clean(line.text)
        if not text:
            index += 1
            continue
        tokens, _positioned = _tokens_for_line(line, line_words)

        if _looks_like_summary(text):
            pending_description.clear()
            if _looks_like_totals_row(text, tokens) and header.positioned:
                values = _positional_values(tokens, header, text)
                _absorb_totals(totals, values.values)
            footer_seen = True
            if footer_page is None:
                footer_page = int(line.page or 1)
            index += 1
            continue

        if footer_seen:
            # Summary lines on the footer page belong to this invoice.  A
            # later page may continue the table (repeated header) - only then
            # do we resume item extraction.
            if int(line.page or 1) <= (footer_page or 0):
                index += 1
                continue
            next_header = _find_header(record, index, line_words)
            if next_header is not None:
                header = next_header
                footer_seen = False
                footer_page = None
                current = None
                index = header.end + 1
                continue
            break

        if _is_item_header_repeat(text, tokens, header):
            replacement = _find_header(record, index, line_words)
            if replacement is not None and replacement.start == index:
                header = replacement
                current = None
                pending_description.clear()
                index = header.end + 1
                continue

        if not any(_money(token.text) is not None for token in tokens):
            if _is_special_line(text):
                _continuation(current, text)
            elif current is None or _numeric_row_soon(record, index, line_words):
                fragment = _strip_hsn(text)
                if fragment:
                    pending_description.append(fragment)
            else:
                _continuation(current, text)
            index += 1
            continue

        if re.match(r"^(?:fsn|sku|asin)\b", text, re.I):
            _continuation(current, text)
            index += 1
            continue

        if _metadata_only_line(text, tokens):
            _continuation(current, text)
            index += 1
            continue

        values = (
            _positional_values(tokens, header, text)
            if header.positioned
            else _sequential_values(tokens, header, text)
        )
        if not _is_item_row(values):
            if _is_special_line(text):
                _continuation(current, text)
                index += 1
                continue
            if header.positioned and values.description and not values.values:
                if current is None or _numeric_row_soon(record, index, line_words):
                    pending_description.append(_strip_hsn(values.description))
                else:
                    _append_description(current, _strip_hsn(values.description))
                index += 1
                continue
            skipped.append(
                {"page": int(line.page), "text": text[:240], "reason": "no amount columns"}
            )
            index += 1
            continue

        if pending_description:
            combined = pending_description + ([values.description] if values.description else [])
            values.description = _join_description(combined)
            pending_description.clear()
        item = _item_from_values(values, line, text, header)
        if item is None:
            skipped.append(
                {"page": int(line.page), "text": text[:240], "reason": "could not map row"}
            )
            index += 1
            continue
        items.append(item)
        current = item
        index += 1

    return items, skipped, totals, summary_flags


def _is_item_header_repeat(text: str, tokens: list[_Token], header: _Header) -> bool:
    if not _header_like_line(tokens):
        return False
    spans = _header_spans(tokens)
    fields = {field_name for _i, _j, field_name, _first, _last in spans}
    return len(fields & set(header.fields)) >= 2


def _looks_like_summary(text: str) -> bool:
    lowered = text.lower().strip()
    if re.match(r"^(grand\s+total|sub\s*total|subtotal)\b", lowered):
        return True
    # A totals row may be "Total", "Total: 1180.00", "Total 1 36560.00" or
    # "Total amount".  A line item may also start with the word "Total"
    # ("Total Protection Plan 1 500.00"), so only treat it as a summary when
    # the next word is a known summary word or a number/currency.
    if re.match(
        r"^total\b\s*[:.\-]?\s*(?:"
        r"\(|₹|rs\.?|inr\b|usd\b|eur\b|gbp\b|\d|$|"
        r"amount\b|value\b|price\b|tax\b|gst\b|invoice\b|payable\b|items?\b|qty\b|"
        r"quantity\b|of\b|taxable\s+(?:value|amount|amt)\b|cgst\b|sgst\b|"
        r"igst\b|utgst\b|cess\b|discount\b"
        r")",
        lowered,
    ):
        return True
    if re.match(
        r"^(taxable\s+value|taxable\s+amount|taxable\s+amt|net\s+taxable\s+value|"
        r"invoice\s+value|invoice\s+total|amount\s+payable|net\s+payable|"
        r"total\s+payable|amount\s+in\s+words|tax\s+amount|tax\s+summary|"
        r"gst\s+summary|tax\s+details|summary)\b",
        lowered,
    ):
        return True
    if re.match(
        r"^(?:cgst|sgst|igst|utgst|cess)\b\s*(?:amount|amt|@|:)?\s*"
        r"(?:\d|₹|rs\.?|inr\b)",
        lowered,
    ):
        # "CGST: 9.0 %" is a rate continuation for the item above, while
        # "CGST 9000.00" or "IGST 18% 9000.00" is a tax summary.  A number
        # immediately followed by "%" is a rate, not an amount.
        if "%" not in lowered:
            return True
        parts = text.split()
        for position, token in enumerate(parts):
            if _money(token) is None:
                continue
            if position + 1 < len(parts) and parts[position + 1] == "%":
                continue
            return True
    return False


def _looks_like_totals_row(text: str, tokens: list[_Token]) -> bool:
    if not re.match(r"^(grand\s+)?(sub\s*)?total\b", text.lower()):
        return False
    if re.search(r"\b(total\s+tax|taxable|invoice\s+value|invoice\s+total)\b", text.lower()):
        return False
    return sum(1 for token in tokens if _money(token.text) is not None) >= 2


def _absorb_totals(totals: dict[str, Decimal], values: dict[str, Decimal]) -> None:
    for name in ("taxable", "sgst", "cgst", "igst", "cess", "total", "amount", "discount", "gross"):
        if name in values:
            totals[name] = values[name]


def _item_from_values(
    values: _Values, line: LineBox, text: str, header: _Header | None
) -> dict | None:
    data = values.values
    qty = data.get("qty")
    rate = data.get("rate")
    gross = data.get("gross")
    discount = data.get("discount")
    taxable = data.get("taxable")
    sgst = data.get("sgst")
    cgst = data.get("cgst")
    igst = data.get("igst")
    cess = data.get("cess")
    generic_tax = data.get("tax")
    amount = data.get("total")
    if amount is None:
        amount = data.get("amount")

    tax_parts = [value for value in (sgst, cgst, igst, cess) if value is not None]
    tax = sum(tax_parts, Decimal("0")) if tax_parts else generic_tax
    if tax is None and amount is not None and taxable is not None:
        derived = amount - taxable
        if derived >= 0:
            tax = derived
    if amount is None and taxable is not None and tax is not None:
        amount = taxable + tax
    if taxable is None and amount is not None and tax is not None:
        derived = amount - tax
        if derived >= 0:
            taxable = derived
    if taxable is None and gross is not None and discount is not None:
        if discount < 0 and gross + discount >= 0:
            taxable = gross + discount
        elif discount > 0 and gross - discount >= 0:
            taxable = gross - discount

    flags = []
    if values.uncertain:
        flags.append("item_layout_uncertain")
    if not values.description:
        flags.append("description_missing")
    if not tax_parts and generic_tax is not None:
        flags.append("tax_untagged")

    sgst_rate = None
    cgst_rate = None
    igst_rate = None
    combined_rate = None

    description = values.description or _strip_hsn(_clean(text))
    if not description:
        return None
    notes = list(values.notes)
    return {
        "invoice_number": None,
        "description": description[:500],
        "hsn": values.hsn,
        "qty": _f(qty),
        "rate": _f(rate),
        "gross": _f(gross),
        "discount": _f(discount),
        "taxable": _f(taxable),
        "sgst": _f(sgst),
        "cgst": _f(cgst),
        "igst": _f(igst),
        "cess": _f(cess),
        "tax": _f(tax),
        "amount": _f(amount),
        "sgst_rate": _f(sgst_rate),
        "cgst_rate": _f(cgst_rate),
        "igst_rate": _f(igst_rate),
        "tax_rate": _f(combined_rate),
        "currency": None,
        "source": None,
        "source_page": int(line.page),
        "source_bbox": _bbox(line),
        "flags": flags,
        "notes": notes,
    }


def _starts_metadata(text: str) -> bool:
    lowered = text.lower().strip()
    if any(lowered.startswith(prefix) for prefix in _METADATA_PREFIXES):
        return True
    if re.match(r"^\d+\.\s*\[?(?:imei|serial)", lowered):
        return True
    return bool(
        re.match(
            r"^(?:imei\b|sr\s*no\b|serial\s*(?:no|number)\b|in\s+the\s+box\b)",
            lowered,
        )
    )


def _metadata_phrase(text: str) -> bool:
    if _starts_metadata(text):
        return True
    return bool(
        re.search(
            r"\b(?:imei|sr\s*no|serial\s*(?:no|number)|warranty\s*:|"
            r"\d+\s*(?:months?|years?)\s+(?:manufacturer\s+)?warranty|in\s+the\s+box)\b",
            text.lower(),
        )
    )


def _continuation(current: dict | None, text: str) -> bool:
    if current is None:
        return False
    lowered = text.lower().strip()
    is_metadata = _starts_metadata(text)
    is_rate_line = bool(re.match(r"^(sgst|cgst|igst|utgst|gst)\b", lowered)) and (
        "%" in text or _money_line(text)
    )

    hsn = _hsn_from_text(text)
    if hsn and not current.get("hsn"):
        current["hsn"] = hsn
    rates = _tax_rates(text)
    for name, value in rates.items():
        key = f"{name}_rate"
        if name in {"sgst", "cgst", "igst"} and current.get(key) is None:
            current[key] = _f(value)
    if rates:
        rate_values = [
            current.get(key)
            for key in ("sgst_rate", "cgst_rate", "igst_rate")
            if current.get(key) is not None
        ]
        if rate_values:
            current["tax_rate"] = float(sum(rate_values))

    if is_metadata or is_rate_line:
        return True
    if not text or text.strip("₹ %|-") == "":
        return True
    # Never fold a numeric row into the previous description: if it could not
    # be mapped, report it instead of corrupting the item above.  A stray
    # number inside prose (e.g. "Ryzen 5") is not a numeric row.
    if _looks_numeric_row(text):
        return False

    fragment = _strip_hsn(text)
    fragment = re.sub(r"^(?:fsn|sku|asin)\s*[:#.\-]?\s*", "", fragment, flags=re.I)
    if not fragment:
        return True
    if re.fullmatch(r"[A-Z0-9][A-Z0-9/_\-]{7,}", fragment):
        # A standalone seller/model code is metadata, not a description.
        return True
    if re.search(r"\b(?:warranty|fsn|sku|asin)\s*:", text, re.I) and re.fullmatch(
        r"[A-Z0-9][A-Z0-9/_\-]{5,}", fragment
    ):
        # A bare seller code followed by warranty metadata, not a description.
        return True
    if re.search(
        r"\b(?:\d+\s*(?:months?|years?)\s+(?:manufacturer\s+)?warranty|in\s+the\s+box)\b",
        fragment,
        re.I,
    ):
        return True
    _append_description(current, fragment)
    return True


def _append_description(current: dict | None, fragment: str) -> None:
    if current is None:
        return
    description = current.get("description") or ""
    if fragment and fragment.lower() not in description.lower():
        current["description"] = f"{description} {fragment}".strip()[:1000]


def _looks_numeric_row(text: str) -> bool:
    """True when a line looks like a financial row, not prose with a number."""
    money_tokens: list[str] = []
    for token in (text or "").split():
        if _HSN_TOKEN_RE.match(token):
            continue
        if _money(token) is None:
            continue
        money_tokens.append(token)
    if not money_tokens:
        return False
    if len(money_tokens) >= 2:
        return True
    return any("." in token or "," in token for token in money_tokens)


def _metadata_only_line(text: str, tokens: list[_Token]) -> bool:
    """A metadata line that happens to contain a bare number (e.g. "1 Year")."""
    if not _metadata_phrase(text):
        return False
    money_tokens = [
        token
        for token in tokens
        if _money(token.text) is not None and not _HSN_TOKEN_RE.match(token.text)
    ]
    if len(money_tokens) >= 2:
        return False
    if any("." in token.text or "," in token.text for token in money_tokens):
        return False
    return True


def _is_special_line(text: str) -> bool:
    """Metadata, tax-rate or HSN-only lines never belong to a description."""
    lowered = text.lower().strip()
    if _metadata_phrase(text):
        return True
    if re.match(r"^(sgst|cgst|igst|utgst|gst|cess)\b", lowered) and (
        "%" in text or _money_line(text)
    ):
        return True
    return not _strip_hsn(text)


def _numeric_row_soon(
    record: _Record, index: int, line_words: dict[int, list], limit: int = 1
) -> bool:
    """True when a wrapped description is printed immediately above a row."""
    for follow in range(index + 1, min(index + 1 + limit, len(record.lines))):
        text = _clean(record.lines[follow].text)
        if not text:
            continue
        if _is_special_line(text) or _looks_like_summary(text):
            return False
        if not _looks_numeric_row(text):
            continue
        # If the numeric row carries its own description (e.g. "Service Fee 1
        # 100.00"), text above it is a continuation of the previous row, not a
        # wrapped description for this one.
        tokens, _positioned = _tokens_for_line(record.lines[follow], line_words)
        first_amount: float | None = None
        for token in tokens:
            if _HSN_TOKEN_RE.match(token.text):
                continue
            if _money(token.text) is not None:
                first_amount = token.center
                break
        if first_amount is not None and any(
            token.center < first_amount and any(character.isalpha() for character in token.text)
            for token in tokens
        ):
            return False
        return True
    return False


def _tax_rates(text: str) -> dict[str, Decimal]:
    rates: dict[str, Decimal] = {}
    for name, pattern in (
        ("sgst", r"(?:\bSGST\b|\bUTGST\b|\bSGST\s*/\s*UTGST\b)"),
        ("cgst", r"\bCGST\b"),
        ("igst", r"\bIGST\b"),
    ):
        match = re.search(pattern + r"\s*(?:@|:)?\s*(\d{1,2}(?:\.\d+)?)\s*%", text, re.I)
        if match:
            rates[name] = Decimal(match.group(1))
    if not rates:
        match = re.search(r"\bGST\b\s*(?:@|:)?\s*(\d{1,2}(?:\.\d+)?)\s*%", text, re.I)
        if match:
            rates["igst"] = Decimal(match.group(1))
    return rates


def _bbox(line: LineBox) -> str:
    return f"{line.x:.1f},{line.y:.1f},{line.width:.1f},{line.height:.1f}"


# ---------------------------------------------------------------------------
# Record-level fields
# ---------------------------------------------------------------------------


def _parse_record(
    record: _Record, extracted: ExtractedPdf, source: str, index: int
) -> tuple[dict | None, list[dict], list[dict]]:
    line_words = _assign_words(record.lines, extracted.words)

    text = "\n".join(_clean(line.text) for line in record.lines if _clean(line.text))
    if not text:
        return None, [], []

    header = _find_header(record, 0, line_words)
    items, skipped, totals, _summary_flags = (
        _line_items(record, header, line_words) if header is not None else ([], [], {}, [])
    )
    summary = _parse_summary(record, header, text)
    row = _build_row(record, text, source, items, totals, summary, header, line_words)
    if row is None or not items:
        return None, items, skipped

    if skipped:
        row["flags"].append("unparsed_rows")
        row["skipped_rows"] = skipped
    for item in items:
        item["currency"] = row.get("currency")
        item["source"] = source
    return row, items, skipped


def _parse_summary(record: _Record, header: _Header | None, text: str) -> dict:
    summary: dict[str, str | Decimal | None] = {
        "invoice_value": None,
        "taxable_value": None,
        "cgst": None,
        "sgst": None,
        "igst": None,
        "cess": None,
        "tax": None,
        "invoice_value_source": None,
        "taxable_value_source": None,
    }
    for line in record.lines:
        value_text = _clean(line.text)
        lowered = value_text.lower()
        if not value_text:
            continue
        total = _last_amount_after(value_text, TOTAL_LABELS)
        if total is not None and summary["invoice_value"] is None:
            summary["invoice_value"] = total
            summary["invoice_value_source"] = "label"
        taxable = _last_amount_after(value_text, TAXABLE_LABELS)
        if taxable is not None and summary["taxable_value"] is None:
            summary["taxable_value"] = taxable
            summary["taxable_value_source"] = "label"
        for name in ("cgst", "sgst", "igst"):
            if summary[name] is not None:
                continue
            amount = _first_amount_after_label(value_text, name.upper())
            if amount is not None:
                summary[name] = amount
        if summary["tax"] is None:
            tax = _last_amount_after(value_text, TAX_LABELS)
            if tax is not None and not re.search(r"cgst|sgst|igst", lowered):
                summary["tax"] = tax
        if summary["cess"] is None:
            cess = _first_amount_after_label(value_text, "CESS")
            if cess is not None:
                summary["cess"] = cess
    return summary


def _last_amount_after(text: str, labels: str) -> Decimal | None:
    match = re.search(r"(?:^|\b)(?:" + labels + r")\b", text, re.I)
    if not match:
        return None
    tail = text[match.end() :]
    amounts = [
        value
        for value in (_money(token) for token in tail.split())
        if value is not None
    ]
    return amounts[-1] if amounts else None


def _first_amount_after_label(text: str, label: str) -> Decimal | None:
    match = re.search(r"(?<![\w/])" + re.escape(label) + r"\b(?!\s*/)", text, re.I)
    if not match:
        return None
    tail = text[match.end() :]
    # "CGST 9 %" carries a rate but no amount; "CGST 9 % 1,800.00" carries both.
    rate = re.match(r"\s*(?:@|:|\-)?\s*\d{1,2}(?:\.\d+)?\s*%", tail)
    if rate:
        tail = tail[rate.end() :]
    amounts = [value for value in (_money(token) for token in tail.split()) if value is not None]
    if rate is not None and not amounts:
        return None
    return amounts[0] if amounts else None


def _build_row(
    record: _Record,
    text: str,
    source: str,
    items: list[dict],
    totals: dict[str, Decimal],
    summary: dict,
    header: _Header | None,
    line_words: dict[int, list],
) -> dict | None:
    gstin = _supplier_gstin(record.lines)
    invoice_number = record.number or _fallback_invoice_number(text)
    invoice_date, date_flag = _invoice_date(text)
    supplier_name = _supplier_name(record.lines)
    customer_name, customer_address, customer_gstin = _customer_details(
        record.lines, line_words, gstin
    )

    if not gstin and not invoice_number and not items:
        return None

    flags: list[str] = []
    flags.extend(gstin_flags(gstin))
    if invoice_number is None:
        flags.append("invoice_number_missing")
    if invoice_date is None:
        flags.append("date_missing")
    elif date_flag:
        flags.append(date_flag)
    if customer_gstin:
        flags.extend(gstin_flags(customer_gstin))

    taxable = summary.get("taxable_value")
    if taxable is None:
        taxable = totals.get("taxable")
    if taxable is None:
        item_taxable = [item.get("taxable") for item in items if item.get("taxable") is not None]
        if item_taxable:
            taxable = sum((_decimal(value) for value in item_taxable), Decimal("0"))
            flags.append("taxable_derived")

    total = summary.get("invoice_value")
    if total is None:
        total = totals.get("total", totals.get("amount"))
    if total is None:
        item_amounts = [item.get("amount") for item in items if item.get("amount") is not None]
        if item_amounts:
            total = sum((_decimal(value) for value in item_amounts), Decimal("0"))
            flags.append("invoice_value_derived")

    cgst = _pick(summary.get("cgst"), totals.get("cgst"), _sum_items(items, "cgst"))
    sgst = _pick(summary.get("sgst"), totals.get("sgst"), _sum_items(items, "sgst"))
    igst = _pick(summary.get("igst"), totals.get("igst"), _sum_items(items, "igst"))
    cess = _pick(summary.get("cess"), totals.get("cess"), _sum_items(items, "cess"))
    tax = summary.get("tax")
    if tax is None:
        tax_parts = [value for value in (cgst, sgst, igst, cess) if value is not None]
        if tax_parts:
            tax = sum(tax_parts, Decimal("0"))
        else:
            item_tax = [item.get("tax") for item in items if item.get("tax") is not None]
            if item_tax:
                tax = sum((_decimal(value) for value in item_tax), Decimal("0"))
                flags.append("tax_derived")

    discount = totals.get("discount")
    gross = totals.get("gross")
    adjustments = _non_taxable_adjustments(items)
    tax_rate = _common_tax_rate(items)

    checks = _checks(
        taxable=taxable,
        tax=tax,
        total=total,
        items=items,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        cess=cess,
        adjustments=adjustments,
        flags=flags,
    )

    match = HSN_RE.search(text)
    if match:
        hsn = match.group(1)
    else:
        hsn = next((item.get("hsn") for item in items if item.get("hsn")), None)
    flags.extend(hsn_flags(hsn))

    currency = _detect_currency(text)
    if currency is None:
        flags.append("currency_unknown")

    fields, located = _locate_fields(
        record.lines,
        gstin=gstin,
        invoice_number=invoice_number,
        taxable=taxable,
        invoice_value=total,
        customer_name=customer_name,
    )
    source_line = located.get("invoice_number") or located.get("supplier_gstin")
    if source_line is None and record.lines:
        source_line = record.lines[0]
    source_bbox = _union_bbox(list(located.values())) or (
        _bbox(source_line) if source_line is not None else None
    )
    source_page = int(source_line.page) if source_line is not None else record.start_page

    if not items:
        flags.append("unreadable")

    return {
        "supplier_name": supplier_name,
        "supplier_gstin": gstin,
        "customer_name": customer_name,
        "customer_gstin": customer_gstin,
        "customer_address": customer_address,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "taxable_value": _f(taxable),
        "tax": _f(tax),
        "cgst": _f(cgst),
        "sgst": _f(sgst),
        "igst": _f(igst),
        "cess": _f(cess),
        "gross_value": _f(gross),
        "discount": _f(discount),
        "adjustments": _f(adjustments),
        "invoice_value": _f(total),
        "tax_rate": _f(tax_rate),
        "currency": currency,
        "hsn": hsn,
        "source": source,
        "source_page": source_page,
        "source_bbox": source_bbox,
        "fields": fields,
        "flags": flags,
        "checks": checks,
        "raw_excerpt": " ".join(text.split())[:240],
    }


def _pick(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _sum_items(items: list[dict], key: str) -> Decimal | None:
    present = [item.get(key) for item in items]
    if not present or any(value is None for value in present):
        return None
    return sum((_decimal(value) for value in present), Decimal("0"))


def _non_taxable_adjustments(items: list[dict]) -> Decimal:
    """Amounts that change the invoice total without changing taxable value.

    Examples: product-exchange deductions, freight adjustments, round-offs.
    They are real rows with zero taxable value and zero tax.
    """
    total = Decimal("0")
    for item in items:
        amount = _decimal(item.get("amount"))
        taxable = _decimal(item.get("taxable"))
        tax = _decimal(item.get("tax"))
        if amount is None or amount == 0:
            continue
        if taxable == 0 and (tax is None or tax == 0):
            total += amount
    return total


def _common_tax_rate(items: list[dict]) -> Decimal | None:
    """A single printed tax rate shared by every taxable line item.

    Mixed-rate invoices return ``None`` rather than a misleading one-rate
    summary.  Rates are only taken from printed rate lines, never inferred
    from amounts.
    """
    rates: list[Decimal] = []
    for item in items:
        taxable = _decimal(item.get("taxable"))
        if taxable is None or taxable <= 0:
            continue
        rate = _decimal(item.get("tax_rate"))
        if rate is None:
            return None
        rates.append(rate)
    if not rates:
        return None
    first = rates[0]
    if all(abs(rate - first) <= Decimal("0.01") for rate in rates):
        return first
    return None


def _checks(
    *,
    taxable: Decimal | None,
    tax: Decimal | None,
    total: Decimal | None,
    items: list[dict],
    cgst: Decimal | None,
    sgst: Decimal | None,
    igst: Decimal | None,
    cess: Decimal | None,
    adjustments: Decimal,
    flags: list[str],
) -> list[dict]:
    checks: list[dict] = []

    def compare(name: str, left: Decimal | None, right: Decimal | None) -> None:
        if left is None or right is None:
            return
        difference = abs(left - right)
        ok = difference <= Decimal("1.00")
        checks.append(
            {
                "check": name,
                "status": "ok" if ok else "mismatch",
                "expected": float(left),
                "actual": float(right),
                "difference": float(difference),
            }
        )
        if not ok:
            if "invoice_math" not in flags:
                flags.append("invoice_math")
            detail = {
                "taxable_plus_tax": "taxable_mismatch",
                "line_items_total": "line_total_mismatch",
                "line_items_taxable": "taxable_mismatch",
                "line_items_tax": "tax_mismatch",
            }.get(name)
            if detail and detail not in flags:
                flags.append(detail)

    compare(
        "taxable_plus_tax",
        (taxable + tax + adjustments)
        if taxable is not None and tax is not None
        else None,
        total,
    )
    if adjustments:
        checks.append(
            {
                "check": "non_taxable_adjustments",
                "status": "ok",
                "expected": float(adjustments),
                "actual": float(adjustments),
                "difference": 0.0,
            }
        )

    item_amounts = [item.get("amount") for item in items]
    if item_amounts and all(value is not None for value in item_amounts):
        compare("line_items_total", sum((_decimal(value) for value in item_amounts), Decimal("0")), total)

    item_taxable = [item.get("taxable") for item in items]
    if item_taxable and all(value is not None for value in item_taxable):
        compare("line_items_taxable", sum((_decimal(value) for value in item_taxable), Decimal("0")), taxable)

    item_tax = [item.get("tax") for item in items]
    if item_tax and all(value is not None for value in item_tax):
        compare("line_items_tax", sum((_decimal(value) for value in item_tax), Decimal("0")), tax)

    tax_parts = [value for value in (cgst, sgst, igst, cess) if value is not None]
    if tax_parts and tax is not None:
        compare("tax_components", sum(tax_parts, Decimal("0")), tax)

    return checks


def _detect_currency(text: str) -> str | None:
    scores = {
        "INR": len(re.findall(r"₹|\bINR\b|\bRs\.?\b", text, re.I)),
        "USD": len(re.findall(r"\$|\bUSD\b", text)),
        "EUR": len(re.findall(r"€|\bEUR\b", text)),
        "GBP": len(re.findall(r"£|\bGBP\b", text)),
    }
    best = max(scores, key=lambda code: scores[code])
    return best if scores[best] else None


def _fallback_invoice_number(text: str) -> str | None:
    for line in text.splitlines():
        value = _invoice_anchor(line)
        if value:
            return value
    return None


def _invoice_date(text: str) -> tuple[str | None, str | None]:
    match = INVOICE_DATE_RE.search(text)
    if match:
        return _normalise_date(match.group(1)), None
    match = DATED_RE.search(text)
    if match:
        return _normalise_date(match.group(1)), None
    match = re.search(_DATE_BODY, text, re.I)
    if match:
        return _normalise_date(match.group(1)), "date_unlabelled"
    match = DATE_RE.search(text)
    if match:
        return _normalise_date(match.group(1)), "date_unlabelled"
    return None, None


def _normalise_date(raw: str) -> str | None:
    value_text = _clean(raw)
    named = re.fullmatch(
        r"(\d{1,2})[\s\-./]+([A-Za-z]{3,9})\.?[\s\-./,]*(\d{2,4})", value_text
    )
    if named:
        value_text = f"{named.group(1)} {named.group(2)} {named.group(3)}"
    value = normalize_date(value_text)
    parts = value.split("-")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
    except ValueError:
        return None
    if not (1990 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    return value


# ---------------------------------------------------------------------------
# Metadata fields
# ---------------------------------------------------------------------------


def _supplier_gstin(lines: list[LineBox]) -> str | None:
    gstins = find_gstins("\n".join(_clean(line.text) for line in lines))
    if not gstins:
        return None
    supplier: str | None = None
    saw_buyer = False
    for index, line in enumerate(lines):
        text = _clean(line.text)
        if "gstin" not in text.lower():
            continue
        found = find_gstins(text)
        if not found:
            continue
        block = " ".join(_clean(lines[j].text).lower() for j in range(max(0, index - 2), index + 1))
        buyer = bool(re.search(r"buyer|customer|recipient|billed\s+to", block))
        seller = bool(re.search(r"supplier|seller|sold\s+by|vendor", block))
        if buyer and not seller:
            saw_buyer = True
            continue
        supplier = found[0]
        break
    if supplier:
        return supplier
    if saw_buyer:
        # The only printed GSTIN belongs to the buyer; do not mislabel it.
        return None
    return gstins[0]


def _supplier_name(lines: list[LineBox]) -> str | None:
    for line in lines:
        text = _clean(line.text)
        match = SUPPLIER_LABELS.search(text)
        if not match:
            continue
        name = _first_name_fragment(text[match.end() :])
        if name:
            return name
    # Many invoices print "Supplier <name>" without a colon.
    loose = re.compile(
        r"^(?:supplier|seller|vendor|sold\s+by|billed\s+by|invoice\s+from|m/s\.?|trade\s+name)\s+(.+)$",
        re.I,
    )
    for line in lines:
        match = loose.match(_clean(line.text))
        if not match:
            continue
        name = _first_name_fragment(match.group(1))
        if name:
            return name
    # Fallback: a company-looking line near the top, before the GSTIN.
    for line in lines[:15]:
        text = _clean(line.text)
        if not re.search(
            r"\b(pvt|private|ltd|limited|llp|inc|corp|enterprises?|traders?|industries)\b",
            text,
            re.I,
        ):
            continue
        if find_gstins(text) or "address" in text.lower():
            continue
        name = _first_name_fragment(text)
        if name:
            return name
    return None


def _first_name_fragment(text: str) -> str | None:
    value = re.split(r",|\||\bGSTIN\b|\bGST\b|\bPhone\b|\bPAN\b", text, maxsplit=1, flags=re.I)[0]
    value = _clean(value).strip(" ,;:-")
    if not value or len(value) > 120:
        return None
    if find_gstins(value) or GSTIN_LOOSE_RE.search(value):
        return None
    if re.match(
        r"^(gstin|hsn|sac|invoice|tax|total|cgst|sgst|igst|billing|shipping|ship\s+to|"
        r"bill\s+to|address|registered|sold\s+by|supplier|seller|vendor)\b",
        value,
        re.I,
    ):
        return None
    return value


def _customer_details(
    lines: list[LineBox], line_words: dict[int, list], supplier_gstin: str | None
) -> tuple[str | None, str | None, str | None]:
    customer_gstin: str | None = None
    for line in lines:
        text = _clean(line.text)
        match = CUSTOMER_GSTIN_LABELS.search(text)
        if match:
            found = find_gstins(text[match.end() :])
            if found:
                customer_gstin = found[0]
                break
    if customer_gstin and supplier_gstin and customer_gstin == supplier_gstin:
        customer_gstin = None

    # Inline "Bill To: Name".
    for line in lines:
        text = _clean(line.text)
        match = CUSTOMER_LABELS.search(text)
        if match:
            name = _first_name_fragment(text[match.end() :])
            if name and not _looks_like_address(name):
                address = _address_block(lines, line, line_words)
                return name, address, customer_gstin

    # Header cell "Bill To" with the value underneath, in the same x band.
    for index, line in enumerate(lines):
        text = _clean(line.text)
        if not re.search(r"\b(bill\s+to|billing\s+address|buyer|customer)\b", text, re.I):
            continue
        header_words = [
            word
            for word in _words_for_line(line, line_words)
            if re.search(r"bill\s+to|billing\s+address|buyer|customer", _clean(word.text), re.I)
        ]
        if not header_words:
            continue
        x0 = min(word.x for word in header_words)
        name: str | None = None
        address_parts: list[str] = []
        for follow in lines[index + 1 : index + 7]:
            if follow.page != line.page:
                break
            words = [
                word
                for word in _words_for_line(follow, line_words)
                if x0 - 18.0 <= word.x <= x0 + 130.0
            ]
            value = _clean(" ".join(word.text for word in words))
            if not value or re.search(r"bill\s+to|ship\s+to|order\s+id", value, re.I):
                continue
            if name is None:
                if not _looks_like_address(value) and not any(ch.isdigit() for ch in value):
                    name = value
                continue
            if not _looks_like_phone(value):
                address_parts.append(value)
        if name:
            return name, _join_address(address_parts), customer_gstin
    return None, None, customer_gstin


def _looks_like_address(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in _ADDRESS_HINTS)


def _looks_like_phone(value: str) -> bool:
    return bool(re.search(r"\b(phone|mobile|tel|contact)\b", value, re.I))


def _address_block(
    lines: list[LineBox], line: LineBox, line_words: dict[int, list]
) -> str | None:
    words = _words_for_line(line, line_words)
    if not words:
        return None
    x0 = min(word.x for word in words)
    parts: list[str] = []
    seen = False
    for follow in lines:
        if follow is line:
            seen = True
            continue
        if not seen or follow.page != line.page:
            continue
        if len(parts) >= 3:
            break
        text = _clean(follow.text)
        if text and len(text) > len(_clean(line.text)) and _looks_like_address(text):
            parts.append(text)
    return _join_address(parts)


def _join_address(parts: list[str]) -> str | None:
    cleaned = []
    for part in parts:
        value = _clean(part).strip(" ,;")
        if value and value not in cleaned:
            cleaned.append(value)
    return ", ".join(cleaned)[:300] or None


def _locate_fields(
    lines: list[LineBox],
    *,
    gstin: str | None,
    invoice_number: str | None,
    taxable: Decimal | None,
    invoice_value: Decimal | None,
    customer_name: str | None,
) -> tuple[dict[str, dict], dict[str, LineBox]]:
    fields: dict[str, dict] = {}
    located: dict[str, LineBox] = {}

    def locate(name: str, line: LineBox | None) -> None:
        if line is not None:
            located[name] = line
            fields[name] = {"page": int(line.page), "bbox": _bbox(line)}

    if gstin:
        locate("supplier_gstin", _line_containing(lines, gstin))
    if invoice_number:
        locate("invoice_number", _line_containing(lines, invoice_number))
    if customer_name:
        locate("customer_name", _line_containing(lines, customer_name))
    if taxable is not None:
        locate("taxable_value", _line_with_amount(lines, taxable))
    if invoice_value is not None:
        locate("invoice_value", _line_with_amount(lines, invoice_value))
    return fields, located


def _line_containing(lines: list[LineBox], needle: str) -> LineBox | None:
    target = _clean(needle).upper()
    for line in lines:
        if target and target in _clean(line.text).upper():
            return line
    return None


def _line_with_amount(lines: list[LineBox], value: Decimal) -> LineBox | None:
    for line in lines:
        for token in _clean(line.text).split():
            parsed = _money(token)
            if parsed is not None and parsed == value:
                return line
    return None


def _union_bbox(lines: list[LineBox]) -> str | None:
    if not lines:
        return None
    x0 = min(line.x for line in lines)
    y0 = min(line.y for line in lines)
    x1 = max(line.x + line.width for line in lines)
    y1 = max(line.y + line.height for line in lines)
    return f"{x0:.1f},{y0:.1f},{x1 - x0:.1f},{y1 - y0:.1f}"
