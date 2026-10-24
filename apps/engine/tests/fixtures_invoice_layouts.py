"""Synthetic invoice layouts for the general invoice regression tests.

The real-world sample in ``fixtures/invoices/flpk.pdf`` covers a positioned
marketplace invoice.  These fixtures cover layouts that are structurally
different: multiple invoices, credit notes, a table split over pages, wrapped
rows, missing optional columns, non-GST/USD invoices, scanned pages and
ambiguous rows.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

A4 = (595.0, 842.0)


def lines_at(
    lines: list[str], *, x: float = 40.0, top: float = 800.0, step: float = 14.0
) -> list[tuple[float, float, str]]:
    return [(x, top - index * step, line) for index, line in enumerate(lines)]


def write_pdf(
    path: Path,
    pages: list[list[tuple[float, float, str]]],
    *,
    font_size: float = 9.0,
) -> Path:
    from reportlab.pdfgen import canvas

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book = canvas.Canvas(str(path), pagesize=A4)
    for page in pages:
        book.setFont("Helvetica", font_size)
        for x, y, text in page:
            book.drawString(float(x), float(y), text)
        book.showPage()
    book.save()
    return path


def write_scanned_pdf(source: Path, dest: Path, *, scale: float = 3.0) -> Path:
    """Render the first page of ``source`` and embed it as an image-only PDF."""
    from PIL import Image

    from apps.engine.pdf_render import render_page_png

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="caunpacker_scan_") as tmp:
        png = render_page_png(Path(source), 1, Path(tmp) / "page.png", scale=scale)
        with Image.open(png) as image:
            image.convert("RGB").save(dest, "PDF", resolution=150.0)
    return dest


def multi_invoice_pages() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No INV/AA/001",
                "Invoice Date 01/04/2026",
                "Supplier Alpha Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "HSN Qty Rate Taxable Amount",
                "Widget A 998314 2 100.00 200.00 236.00",
                "Taxable value 200.00",
                "CGST 18.00  SGST 18.00",
                "Invoice value 236.00",
            ]
        ),
        lines_at(
            [
                "CREDIT NOTE",
                "Credit Note Number CR/001",
                "Credit Note Date 01/04/2026",
                "Supplier Alpha Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "HSN Qty Rate Taxable Amount",
                "Returned Widget A 998314 1 100.00 100.00 118.00",
                "Taxable value 100.00",
                "CGST 9.00  SGST 9.00",
                "Credit Note value 118.00",
            ]
        ),
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No INV/BB/002",
                "Invoice Date 02/04/2026",
                "Supplier Beta Supplies",
                "Supplier GSTIN 29AADCH8449J1Z0",
                "Description Qty Rate Amount",
                "Service B 1 500.00 500.00",
                "Total Amount 500.00",
            ]
        ),
    ]


def same_page_invoice_pages() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No SAME/001",
                "Invoice Date 08/04/2026",
                "Supplier Same Page Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "HSN Qty Rate Amount",
                "Item A 998314 1 100.00 118.00",
                "Invoice value 118.00",
                "TAX INVOICE",
                "Invoice No SAME/002",
                "Invoice Date 08/04/2026",
                "Supplier Same Page Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "HSN Qty Rate Amount",
                "Item B 998314 1 200.00 236.00",
                "Invoice value 236.00",
            ]
        )
    ]


def multipage_invoice_pages() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No MULTI/001",
                "Invoice Date 07/04/2026",
                "Supplier Multi Page Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description Qty Rate Amount",
                "Item A 1 100.00 118.00",
            ]
        ),
        lines_at(
            [
                "Description Qty Rate Amount",
                "Item B 1 200.00 236.00",
                "Taxable value 300.00",
                "CGST 27.00  SGST 27.00",
                "Invoice value 354.00",
            ]
        ),
    ]


def wrapped_table_page() -> list[list[tuple[float, float, str]]]:
    return [
        [
            (40.0, 790.0, "TAX INVOICE"),
            (40.0, 770.0, "Invoice No WRAP/001"),
            (40.0, 755.0, "Invoice Date 03/04/2026"),
            (40.0, 740.0, "Supplier Wrap Industries Pvt Ltd"),
            (40.0, 725.0, "Supplier GSTIN 27AAPFU0939F1ZV"),
            (30.0, 690.0, "Description"),
            (230.0, 690.0, "Qty"),
            (270.0, 690.0, "Gross"),
            (330.0, 690.0, "Discount"),
            (400.0, 690.0, "Taxable"),
            (470.0, 690.0, "SGST"),
            (510.0, 690.0, "CGST"),
            (555.0, 690.0, "Total"),
            (270.0, 678.0, "Amount"),
            (330.0, 678.0, "/Coupons"),
            (400.0, 678.0, "Value"),
            (470.0, 678.0, "/UTGST"),
            (30.0, 650.0, "Widget with a very"),
            (230.0, 650.0, "1"),
            (270.0, 650.0, "1180.00"),
            (330.0, 650.0, "0.00"),
            (400.0, 650.0, "1000.00"),
            (470.0, 650.0, "90.00"),
            (510.0, 650.0, "90.00"),
            (555.0, 650.0, "1180.00"),
            (30.0, 638.0, "long description that wraps"),
            (30.0, 626.0, "HSN/SAC: 998314"),
            (30.0, 614.0, "across three lines"),
            (30.0, 585.0, "Service Fee"),
            (230.0, 585.0, "1"),
            (270.0, 585.0, "236.00"),
            (330.0, 585.0, "0.00"),
            (400.0, 585.0, "200.00"),
            (470.0, 585.0, "18.00"),
            (510.0, 585.0, "18.00"),
            (555.0, 585.0, "236.00"),
            (30.0, 555.0, "Total"),
            (230.0, 555.0, "2"),
            (270.0, 555.0, "1416.00"),
            (330.0, 555.0, "0.00"),
            (400.0, 555.0, "1200.00"),
            (470.0, 555.0, "108.00"),
            (510.0, 555.0, "108.00"),
            (555.0, 555.0, "1416.00"),
            (400.0, 530.0, "Grand Total"),
            (555.0, 530.0, "1416.00"),
        ]
    ]


def missing_column_page() -> list[list[tuple[float, float, str]]]:
    return [
        [
            (40.0, 790.0, "TAX INVOICE"),
            (40.0, 770.0, "Invoice No MISS/001"),
            (40.0, 755.0, "Invoice Date 04/04/2026"),
            (40.0, 740.0, "Supplier Missing Column Traders"),
            (40.0, 725.0, "Supplier GSTIN 27AAPFU0939F1ZV"),
            (40.0, 700.0, "Description"),
            (250.0, 700.0, "Qty"),
            (310.0, 700.0, "Rate"),
            (370.0, 700.0, "Discount"),
            (440.0, 700.0, "Taxable"),
            (530.0, 700.0, "Amount"),
            (40.0, 670.0, "Item A"),
            (250.0, 670.0, "2"),
            (310.0, 670.0, "100.00"),
            (440.0, 670.0, "200.00"),
            (530.0, 670.0, "200.00"),
            (40.0, 640.0, "Item B"),
            (250.0, 640.0, "1"),
            (310.0, 640.0, "50.00"),
            (370.0, 640.0, "5.00"),
            (440.0, 640.0, "45.00"),
            (530.0, 640.0, "45.00"),
            (40.0, 610.0, "Total"),
            (250.0, 610.0, "3"),
            (440.0, 610.0, "245.00"),
            (530.0, 610.0, "245.00"),
        ]
    ]


def non_gst_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "INVOICE",
                "Bill No: NGP-2026-77",
                "Dated 03/04/2026",
                "Supplier: Northwind Traders",
                "Description Qty Rate Amount",
                "Consulting 2 250.00 500.00",
                "Implementation 1 750.00 750.00",
                "Total Amount USD 1,250.00",
            ]
        )
    ]


def header_name_trap_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No HDR/001",
                "Invoice Date 10/04/2026",
                "Sold By Billing Address Shipping ADDRESS",
                "Acme Trading Private Limited, Buyer Name, Buyer Name,",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description Qty Rate Amount",
                "Item 1 100.00 118.00",
                "Invoice value 118.00",
            ]
        )
    ]


def formatted_numbers_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No FMT/001",
                "Invoice Date 12-Jul-2026",
                "Supplier Format Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description Qty Rate Taxable Amount",
                "Item A 1 1,00,000.00 1,00,000.00 1,18,000.00",
                "Taxable value 1,00,000.00",
                "CGST 9000.00  SGST 9000.00",
                "Invoice value INR 1,18,000.00",
            ]
        )
    ]


def scanned_source_page() -> list[list[tuple[float, float, str]]]:
    return [
        [
            (50.0, 760.0, "TAX INVOICE"),
            (50.0, 720.0, "Invoice No SCAN/001"),
            (50.0, 690.0, "Invoice Date 05/04/2026"),
            (50.0, 660.0, "Supplier Scan Traders"),
            (50.0, 630.0, "Supplier GSTIN 27AAPFU0939F1ZV"),
            (50.0, 590.0, "Description Qty Rate Taxable Amount"),
            (50.0, 560.0, "Widget 1 1000.00 1000.00 1180.00"),
            (50.0, 520.0, "Taxable value 1000.00"),
            (50.0, 490.0, "IGST 180.00"),
            (50.0, 460.0, "Invoice value 1180.00"),
        ]
    ]


def unsupported_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No PROSE/001",
                "Invoice Date 06/04/2026",
                "Supplier Prose Consulting LLP",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "This document describes consulting services.",
                "No table, quantities, rates or amounts are printed.",
            ]
        )
    ]


def adjustment_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No ADJ/001",
                "Invoice Date 14/04/2026",
                "Supplier Adjustment Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description Qty Rate Taxable Amount",
                "Handset 1 1000.00 1000.00 1180.00",
                "Exchange 0.00 -250.00",
                "Taxable value 1000.00",
                "CGST 90.00  SGST 90.00",
                "Invoice value 930.00",
            ]
        )
    ]


def total_named_item_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No TOT/001",
                "Invoice Date 11/04/2026",
                "Supplier Total Care Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description Qty Rate Taxable Amount",
                "Total Protection Plan 1 500.00 500.00 590.00",
                "Taxable value 500.00",
                "CGST 45.00  SGST 45.00",
                "Invoice value 590.00",
            ]
        )
    ]


def metadata_continuation_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No META/001",
                "Invoice Date 13/04/2026",
                "Supplier Metadata Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description Qty Rate Amount",
                "Portable Table 1 100.00 118.00",
                "YellowWood | IMEI/SrNo: [[]]",
                "FSN: Black, 128 GB)",
                "MOBGW9FEZKAV8QCZ Warranty: 1 Year Manufacturer Warranty for",
                "HSN/SAC: 44219090 Phone and 6 Months Warranty for In the Box",
                "Accessories",
                "Invoice value 118.00",
            ]
        )
    ]


def tax_summary_before_total_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No TAXSUM/001",
                "Invoice Date 12/04/2026",
                "Supplier Tax Summary Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description Qty Rate Amount",
                "Item 1 100.00 118.00",
                "CGST 9.00",
                "SGST 9.00",
                "Invoice value 118.00",
            ]
        )
    ]


def ambiguous_rows_page() -> list[list[tuple[float, float, str]]]:
    return [
        lines_at(
            [
                "TAX INVOICE",
                "Invoice No AMB/001",
                "Invoice Date 09/04/2026",
                "Supplier Ambiguous Traders",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Description HSN Taxable Amount",
                "Good Item 998314 100.00 118.00",
                "Mystery 50.00",
                "Invoice value 118.00",
            ]
        )
    ]
