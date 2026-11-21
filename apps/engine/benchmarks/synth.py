"""Synthetic ground-truth financial documents.

Every document is generated from explicit values, so the expected extraction
result is known by construction — never reverse-engineered from the parser's
own output.  Generators use pymupdf (already a dependency) and PIL; nothing
is downloaded and nothing is fabricated at benchmark time.
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

PAGE_W, PAGE_H = 595, 842


def _doc_from_lines(pages: list[list[str]]) -> pymupdf.Document:
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        y = 56.0
        for line in lines:
            page.insert_text((40, y), line, fontsize=9, fontname="cour")
            y += 15
    return doc


def _rasterize(doc: pymupdf.Document, dpi: float = 96.0, jpeg_quality: int | None = None):
    """Render the document to PIL images (grayscale, optionally JPEG-softened)."""
    images: list[Image.Image] = []
    for page in doc:
        pix = page.get_pixmap(dpi=int(round(dpi)), colorspace=pymupdf.csGRAY)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        if jpeg_quality is not None:
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=jpeg_quality)
            buffer.seek(0)
            image = Image.open(buffer).convert("L")
        images.append(image)
    return images


def save_pdf(doc: pymupdf.Document, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(doc.tobytes())
    return path


def save_image(image: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")
    return path


# ---------------------------------------------------------------------------
# 1. Clean searchable GST invoice
# ---------------------------------------------------------------------------

INVOICE_LINES = [
    "SERENE ELECTRONICS PRIVATE LIMITED",
    "GSTIN: 29AABCS1429B1ZP        State: Karnataka",
    "TAX INVOICE",
    "Customer: MARATHAHALLA TRADERS LLP",
    "Customer GSTIN: 29AAFMT7601K1Z6",
    "Invoice No: SE/2026/0417        Invoice Date: 14-Feb-2026",
    "Place of supply: Karnataka (29)",
    "PO Number: PO-88213",
    "Description            HSN     Qty   Rate      Taxable   CGST    SGST    Total",
    "LED Panel 18W          9405    40    320.00    12,800.00 384.00  384.00  13,568.00",
    "LED Panel 24W          9405    25    480.00    12,000.00 360.00  360.00  12,720.00",
    "Driver Unit            8504    10    900.00     9,000.00 270.00  270.00   9,540.00",
    "Taxable Value: 33,800.00",
    "CGST: 1,014.00",
    "SGST: 1,014.00",
    "Round Off: 0.00",
    "Invoice Total: 35,828.00",
    "Amount in words: Thirty Five Thousand Eight Hundred Twenty Eight Only",
    "Payment terms: 30 days from invoice date",
]

INVOICE_TRUTH = {
    "kind": "invoice",
    "invoice_number": "SE/2026/0417",
    "invoice_date": "2026-02-14",
    "supplier_gstin": "29AABCS1429B1ZP",
    "customer_gstin": "29AAFMT7601K1Z6",
    "taxable_value": Decimal("33800.00"),
    "cgst": Decimal("1014.00"),
    "sgst": Decimal("1014.00"),
    "invoice_value": Decimal("35828.00"),
    "line_items": 3,
    "full_text": "\n".join(INVOICE_LINES),
}


def make_searchable_invoice(path: Path) -> Path:
    return save_pdf(_doc_from_lines([INVOICE_LINES]), path)


# ---------------------------------------------------------------------------
# 2. Scanned / low-resolution invoice (OCR path)
# ---------------------------------------------------------------------------


def make_scanned_invoice(path: Path, dpi: float = 96.0, quality: int | None = 55) -> Path:
    doc = _doc_from_lines([INVOICE_LINES])
    images = _rasterize(doc, dpi=dpi, jpeg_quality=quality)
    return save_image(images[0], path)


# ---------------------------------------------------------------------------
# 3. Bank statement (searchable, then rotated/low-res variants)
# ---------------------------------------------------------------------------

STATEMENT_HEAD = [
    "HDFC BANK LIMITED - STATEMENT OF ACCOUNT",
    "Account Number 501001234567    IFSC HDFC0000123",
    "Statement Period: 01-04-2026 to 30-04-2026",
    "Opening Balance 25,000.00 Dr",
    "Date        Narration                        Chq/Ref   Withdrawal   Deposit    Balance",
]

_STATEMENT_TXNS = [
    ("2026-04-02", "UPI/MR GROCERY STORE", "UPI-1101", "1,250.50", "", "23,749.50"),
    ("2026-04-04", "NEFT CR ACME INDUSTRIES", "NEFT-7788", "", "48,000.00", "71,749.50"),
    ("2026-04-09", "ATM WDL MG ROAD", "ATM-2231", "10,000.00", "", "61,749.50"),
    ("2026-04-15", "CHQ PAID 000221 TELECOM", "000221", "3,499.99", "", "58,249.51"),
    ("2026-04-21", "UPI/MR CANTEEN SERVICES", "UPI-1188", "180.00", "", "58,069.51"),
    ("2026-04-27", "NEFT CR ACME INDUSTRIES", "NEFT-7901", "", "21,500.00", "79,569.51"),
]

STATEMENT_LINES = STATEMENT_HEAD + [
    f"{date}   {narration}   {ref}   {debit}   {credit}   {balance}"
    for date, narration, ref, debit, credit, balance in _STATEMENT_TXNS
] + ["Closing Balance 79,569.51"]

STATEMENT_TRUTH_ROWS = [
    {
        "date": date,
        "debit": Decimal(debit.replace(",", "")) if debit else None,
        "credit": Decimal(credit.replace(",", "")) if credit else None,
        "balance": Decimal(balance.replace(",", "")),
    }
    for date, _n, _r, debit, credit, balance in _STATEMENT_TXNS
]


def _statement_doc() -> pymupdf.Document:
    return _doc_from_lines([STATEMENT_LINES])


def make_searchable_statement(path: Path) -> Path:
    return save_pdf(_statement_doc(), path)


def make_lowres_statement(path: Path, dpi: float = 100.0) -> Path:
    doc = _statement_doc()
    images = _rasterize(doc, dpi=dpi)
    image = images[0].filter(ImageFilter.GaussianBlur(radius=0.6))
    return save_image(image, path)


def make_rotated_statement(path: Path, angle: float = 2.5) -> Path:
    doc = _statement_doc()
    images = _rasterize(doc, dpi=120.0)
    rotated = images[0].rotate(angle, expand=True, fillcolor=255, resample=Image.Resampling.BICUBIC)
    return save_image(rotated, path)


def make_multipage_statement(path: Path) -> Path:
    """2 pages: repeated header rows and a narration that wraps mid-page."""
    page1 = STATEMENT_HEAD + [
        f"{date}  {narr}  {ref}  {debit}  {credit}  {balance}"
        for date, narr, ref, debit, credit, balance in _STATEMENT_TXNS[:3]
    ]
    page2 = [
        "HDFC BANK LIMITED - STATEMENT OF ACCOUNT (continued)",
        "Date        Narration                        Chq/Ref   Withdrawal   Deposit    Balance",
        "2026-04-15  CHQ PAID 000221 TELECOM LIMITED  000221  3,499.99    58,249.51",
        "            BILLING FEE INCLUDED IN THE ABOVE INVOICE",
        "2026-04-21  UPI/MR CANTEEN SERVICES PVT LTD  UPI-1188  180.00    58,069.51",
        "2026-04-27  NEFT CR ACME INDUSTRIES PVT LTD  NEFT-7901   21,500.00  79,569.51",
        "Closing Balance 79,569.51",
    ]
    doc = _doc_from_lines([page1, page2])
    return save_pdf(doc, path)


# ---------------------------------------------------------------------------
# 4. Mixed searchable + scanned PDF
# ---------------------------------------------------------------------------


def make_mixed_pdf(path: Path) -> Path:
    """Page 1 searchable invoice, page 2 a scanned (raster) continuation."""
    doc = _doc_from_lines([INVOICE_LINES])
    second = doc.new_page(width=PAGE_W, height=PAGE_H)
    raster_doc = _doc_from_lines(
        [[
            "Continuation sheet - SCANNED",
            "Description            HSN     Qty   Rate      Taxable   CGST   SGST   Total",
            "Cable Tray 2m          8547    15    250.00     3,750.00 112.50 112.50  3,975.00",
            "Taxable Value: 3,750.00",
            "Invoice Total (sheet 2): 3,975.00",
        ]]
    )
    pix = raster_doc[0].get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
    png = pix.tobytes("png")
    raster_doc.close()
    rect = pymupdf.Rect(30, 40, PAGE_W - 30, PAGE_H - 40)
    second.insert_image(rect, stream=png)
    return save_pdf(doc, path)


# ---------------------------------------------------------------------------
# 5. Complex multi-column financial table (SAP-style ledger)
# ---------------------------------------------------------------------------

LEDGER_COLUMNS = (
    ("Document No", 40),
    ("Type", 130),
    ("Posting Dt", 190),
    ("Reference", 280),
    ("Debit", 370),
    ("Credit", 450),
    ("Balance", 520),
)

LEDGER_DATA_ROWS = (
    ("5100000012", "KR", "02.04.2026", "INV-9001", "18,540.00", "", "18,540.00"),
    ("5100000013", "KZ", "09.04.2026", "PAY-1101", "", "18,540.00", "0.00"),
    ("5100000014", "KR", "17.04.2026", "INV-9077", "7,210.25", "", "7,210.25"),
    ("5100000015", "KZ", "25.04.2026", "PAY-1188", "", "7,210.25", "0.00"),
)


def make_ledger_pdf(path: Path) -> Path:
    """Columnar SAP-style ledger: values placed at real x positions."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = 56.0
    page.insert_text((40, y), "LEDGER: TELECOM VENDORS", fontsize=10, fontname="cour")
    page.insert_text((380, y), "Company Code 1000", fontsize=9, fontname="cour")
    page.insert_text((40, y + 14), "Period 04.2026 - 04.2026   Currency INR", fontsize=9, fontname="cour")
    y += 34
    for _label, x in LEDGER_COLUMNS:
        page.insert_text((x, y), _label, fontsize=9, fontname="cour")
    y += 16
    for row in LEDGER_DATA_ROWS:
        for (_label, x), value in zip(LEDGER_COLUMNS, row):
            if value:
                page.insert_text((x, y), value, fontsize=9, fontname="cour")
        y += 15
    page.insert_text((40, y + 6), "Closing Balance: 0.00", fontsize=9, fontname="cour")
    return save_pdf(doc, path)

LEDGER_TRUTH_ROWS = [
    {"document": "5100000012", "debit": Decimal("18540.00"), "credit": None},
    {"document": "5100000013", "debit": None, "credit": Decimal("18540.00")},
    {"document": "5100000014", "debit": Decimal("7210.25"), "credit": None},
    {"document": "5100000015", "debit": None, "credit": Decimal("7210.25")},
]

REFERENCE_BY_DOCUMENT = {
    "5100000012": "INV-9001",
    "5100000013": "PAY-1101",
    "5100000014": "INV-9077",
    "5100000015": "PAY-1188",
}
