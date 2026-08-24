"""Build the sample dump kit under test-dump/. Safe to re-run; wipes the folder first."""

from __future__ import annotations

import json
import shutil
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from apps.engine.tests.dump_paths import (
    ACME,
    BANKS,
    BANKS_MESSY,
    BOOKS,
    DUMP,
    LANDING_ZIP,
    GSTR_1,
    GSTR_2B,
    GSTR_3B,
    GST,
    HDFC,
    ICICI,
    INVOICE_PHOTO,
    INVOICES,
    JUNK,
    MEETING_NOTES,
    MIXED,
    RANDOM_JPG,
    SBI,
    TALLY_XML,
    TALLY_ZIP,
    ZOHO_CSV,
)
from apps.engine.tests.fixtures_stage5 import invoice_lines, write_invoice_pdf
from make_test_dump import JPEG, PNG, pdf_with_text

GSTIN = "27AAPFU0939F1ZV"
CLIENT_GSTIN = "29ABCDE1234F1Z5"


def _write_readme(folder: Path, title: str, intro: str, rows: list[tuple[str, str, str, str]]) -> None:
    lines = [
        f"# {title}",
        "",
        intro,
        "",
        "Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.",
        "",
        "| File | Kind the app should detect | What should happen | Pack / review |",
        "|---|---|---|---|",
    ]
    for name, kind, happens, pack in rows:
        lines.append(f"| `{name}` | {kind} | {happens} | {pack} |")
    lines.append("")
    (folder / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _bank_lines(bank: str, account: str, ifsc: str, opening: Decimal, events: list[tuple[str, str, str, Decimal]]) -> list[str]:
    lines = [
        f"{bank} Account Statement",
        f"Account Number {account}",
        f"IFSC {ifsc}",
        f"Opening Balance {opening:.2f}",
    ]
    balance = opening
    for date, narr, word, amount in events:
        debit_word = word.lower() in {"withdrawal", "debit"}
        if debit_word:
            balance -= amount
        else:
            balance += amount
        lines.append(f"{date} {narr} {word} {amount:.2f} {balance:.2f}")
    lines.append(f"Closing Balance {balance:.2f}")
    return lines


def _write_pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_with_text(lines))


def _pdf_pages(pages: list[list[str]]) -> bytes:
    writer = PdfWriter()
    for lines in pages:
        reader = PdfReader(BytesIO(pdf_with_text(lines)))
        writer.add_page(reader.pages[0])
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _simple_tally_xml() -> str:
    return """<?xml version="1.0"?>
<ENVELOPE>
 <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
 <BODY>
  <TALLYMESSAGE>
   <VOUCHER VCHTYPE="Purchase">
    <DATE>20260712</DATE>
    <VOUCHERNUMBER>PUR-88</VOUCHERNUMBER>
    <PARTYLEDGERNAME>Acme Traders</PARTYLEDGERNAME>
    <AMOUNT>-11800.00</AMOUNT>
   </VOUCHER>
  </TALLYMESSAGE>
 </BODY>
</ENVELOPE>
"""


def _hdfc_simple() -> list[tuple[str, str, str, Decimal]]:
    return [
        ("01/07/2026", "UPI merchant Zomato", "Withdrawal", Decimal("2500.00")),
        ("03/07/2026", "NEFT INWARD Mehta Exports", "Deposit", Decimal("18000.00")),
        ("05/07/2026", "Cheque 112233 Lakshmi Printers", "Withdrawal", Decimal("1000.00")),
        ("09/07/2026", "UPI Swiggy", "Withdrawal", Decimal("640.00")),
        ("14/07/2026", "IMPS from Kiran Agencies", "Deposit", Decimal("9200.00")),
        ("21/07/2026", "ACH EMI Bajaj Finance", "Withdrawal", Decimal("4800.00")),
        ("28/07/2026", "Interest credit", "Deposit", Decimal("112.50")),
    ]


def _icici_simple() -> list[tuple[str, str, str, Decimal]]:
    return [
        ("02/07/2026", "UPI Amazon", "Debit", Decimal("1200.00")),
        ("08/07/2026", "Salary", "Credit", Decimal("45000.00")),
        ("12/07/2026", "POS Big Bazaar", "Debit", Decimal("3180.00")),
        ("19/07/2026", "NEFT vendor Bharat Packaging", "Debit", Decimal("15000.00")),
        ("25/07/2026", "IMPS customer North Retail", "Credit", Decimal("7200.00")),
    ]


def _sbi_simple() -> list[tuple[str, str, str, Decimal]]:
    return [
        ("04/07/2026", "ATM Withdrawal", "Debit", Decimal("2000.00")),
        ("11/07/2026", "IMPS from client", "Credit", Decimal("9000.00")),
        ("16/07/2026", "UPI PhonePe store", "Debit", Decimal("890.00")),
        ("22/07/2026", "Cheque deposit", "Credit", Decimal("5000.00")),
        ("29/07/2026", "SMS alert charges", "Debit", Decimal("15.00")),
    ]


def _messy_events(seed: int, count: int) -> list[tuple[str, str, str, Decimal]]:
    vendors = (
        "ZOMATO LIMITED",
        "LAKSHMI PRINTERS",
        "BHARAT PACKAGING",
        "MEHTA EXPORTS",
        "KIRAN AGENCIES",
        "IRCTC RAIL",
        "AIRTEL THANKS",
        "SHREE STEELS",
    )
    events = []
    day = 1
    for i in range(count):
        day = 1 + (i * 2) % 28
        vendor = vendors[i % len(vendors)]
        if i % 3 == 0:
            word, amount = "Deposit", Decimal("1500.00") + Decimal(i * 37)
            narr = f"NEFT CR {vendor} INV/{seed + i}"
        else:
            word, amount = "Withdrawal", Decimal("220.00") + Decimal(i * 19)
            narr = f"UPI {vendor} / {seed + i} PhonePe"
        events.append((f"{day:02d}/07/2026", narr, word, amount.quantize(Decimal("0.01"))))
    return events


def _tally_xml() -> str:
    return """<?xml version="1.0"?>
<ENVELOPE>
 <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
 <BODY>
  <TALLYMESSAGE>
   <VOUCHER VCHTYPE="Purchase">
    <DATE>20260712</DATE>
    <VOUCHERNUMBER>PUR-88</VOUCHERNUMBER>
    <PARTYLEDGERNAME>Acme Traders</PARTYLEDGERNAME>
    <PARTYGSTIN>27AAPFU0939F1ZV</PARTYGSTIN>
    <AMOUNT>-11800.00</AMOUNT>
    <TAXABLEVALUE>10000.00</TAXABLEVALUE>
   </VOUCHER>
   <VOUCHER VCHTYPE="Purchase">
    <DATE>20260718</DATE>
    <VOUCHERNUMBER>PUR-91</VOUCHERNUMBER>
    <PARTYLEDGERNAME>Lakshmi Printers</PARTYLEDGERNAME>
    <PARTYGSTIN>29AABCU9603R1ZX</PARTYGSTIN>
    <AMOUNT>-4720.00</AMOUNT>
    <TAXABLEVALUE>4000.00</TAXABLEVALUE>
   </VOUCHER>
   <VOUCHER VCHTYPE="Sales">
    <DATE>20260720</DATE>
    <VOUCHERNUMBER>SAL-10</VOUCHERNUMBER>
    <PARTYLEDGERNAME>North Retail</PARTYLEDGERNAME>
    <PARTYGSTIN>27AAACN1234A1Z5</PARTYGSTIN>
    <AMOUNT>5900.00</AMOUNT>
    <TAXABLEVALUE>5000.00</TAXABLEVALUE>
   </VOUCHER>
  </TALLYMESSAGE>
 </BODY>
</ENVELOPE>
"""


def build() -> None:
    if DUMP.exists():
        shutil.rmtree(DUMP)
    for folder in (BANKS, BANKS_MESSY, INVOICES, GST, BOOKS, JUNK, MIXED):
        folder.mkdir(parents=True, exist_ok=True)

    _write_pdf(
        HDFC,
        _bank_lines("HDFC Bank", "50100123456789", "HDFC0001234", Decimal("150000.00"), _hdfc_simple()),
    )
    _write_pdf(
        ICICI,
        _bank_lines("ICICI Bank", "000405001234", "ICIC0000004", Decimal("80000.00"), _icici_simple()),
    )
    _write_pdf(
        SBI,
        _bank_lines("State Bank of India", "12345678901", "SBIN0000456", Decimal("25000.00"), _sbi_simple()),
    )
    _write_readme(
        BANKS,
        "01 — Digital bank statements",
        "Clean digital PDFs (text, not scans) for HDFC, ICICI and SBI. This is the path the bank unpacker was built for.",
        [
            (HDFC.name, "Bank statement", "Line-by-line transactions, running balance, debit vs credit from bank wording.", "`Bank_Statement_Cleaned.xlsx` with a match/mismatch cover. Job can still be needs_review if other files are mixed in."),
            (ICICI.name, "Bank statement", "Same as HDFC for an ICICI layout.", "Rows in the same bank Excel (one workbook per period, all bank files)."),
            (SBI.name, "Bank statement", "SBI debit/credit words (ATM Withdrawal, IMPS Credit).", "Same bank pack."),
        ],
    )

    messy_specs = [
        ("HDFC_MehtaTrading_Jul2026_complex.pdf", "HDFC Bank", "502000111222", "HDFC0001888", Decimal("428150.00"), 14, 11),
        ("ICICI_AnitaMehta_Jul2026_complex.pdf", "ICICI Bank", "000405998877", "ICIC0002211", Decimal("91200.00"), 16, 17),
        ("SBI_KiranAgencies_Jul2026_complex.pdf", "State Bank of India", "389100112233", "SBIN0000771", Decimal("64000.00"), 12, 23),
    ]
    for name, bank, acct, ifsc, opening, count, seed in messy_specs:
        _write_pdf(BANKS_MESSY / name, _bank_lines(bank, acct, ifsc, opening, _messy_events(seed, count)))
    long_events = _messy_events(90, 90)
    opening = Decimal("1000000.00")
    header = [
        "HDFC Bank Account Statement",
        "Account Number 502000111222",
        "IFSC HDFC0001888",
        f"Opening Balance {opening:.2f}",
    ]
    balance = opening
    pages: list[list[str]] = []
    chunk = 30
    for start in range(0, len(long_events), chunk):
        group = long_events[start : start + chunk]
        lines = list(header) if start == 0 else ["HDFC Bank Account Statement continued"]
        for date, narr, word, amount in group:
            if word.lower() in {"withdrawal", "debit"}:
                balance -= amount
            else:
                balance += amount
            lines.append(f"{date} {narr} {word} {amount:.2f} {balance:.2f}")
        if start + chunk >= len(long_events):
            lines.append(f"Closing Balance {balance:.2f}")
        pages.append(lines)
    (BANKS_MESSY / "HDFC_MehtaTrading_Jul2026_LONG.pdf").write_bytes(_pdf_pages(pages))
    _write_readme(
        BANKS_MESSY,
        "02 — Messy bank statements",
        "Longer digital PDFs with UPI/NEFT/IMPS narrations. Still text PDFs, not scans. The parser should keep a matching running balance.",
        [
            ("HDFC_MehtaTrading_Jul2026_complex.pdf", "Bank statement", "≥10 transaction lines, continuation-style vendor names.", "Bank Excel; cover status **match** if opening + movements = closing."),
            ("ICICI_AnitaMehta_Jul2026_complex.pdf", "Bank statement", "Same, ICICI debit/credit words.", "Included in the period bank pack."),
            ("SBI_KiranAgencies_Jul2026_complex.pdf", "Bank statement", "Same, SBI wording.", "Included in the period bank pack."),
            ("HDFC_MehtaTrading_Jul2026_LONG.pdf", "Bank statement", "About 90 lines. Unpack should still finish and balance.", "Bank Excel with ~90 rows, status match."),
        ],
    )

    write_invoice_pdf(
        ACME,
        invoice_lines(
            invoice_no="ACME/26-27/0142",
            date="12/07/2026",
            taxable="10000.00",
            cgst="900.00",
            sgst="900.00",
            total="11800.00",
        ),
    )
    two_line = [
        "TAX INVOICE",
        "Invoice No MEHTA/26-27/0881",
        "Invoice Date 18/07/2026",
        f"Supplier GSTIN {GSTIN}",
        "Supplier name Mehta Exports Pvt Ltd",
        "Place of Supply 27-Maharashtra",
        "HSN Qty Rate Taxable Amount",
        "Consulting 998314 1 7000.00 7000.00 8260.00",
        "Software licence 997331 1 3000.00 3000.00 3540.00",
        "Taxable value 10000.00",
        "CGST 900.00  SGST 900.00",
        "Invoice value 11800.00",
    ]
    INVOICES.joinpath("Tax_Invoice_Mehta_two_lines.pdf").write_bytes(pdf_with_text(two_line))
    write_invoice_pdf(
        INVOICES / "Tax_Invoice_BadGSTIN.pdf",
        invoice_lines(invoice_no="BADGST/26-27/0001", gstin="27AAPFU0939F1ZZ"),
    )
    write_invoice_pdf(
        INVOICES / "Tax_Invoice_BadHSN.pdf",
        invoice_lines(invoice_no="BADHSN/26-27/0002", hsn="12345"),
    )
    header_only = [
        "TAX INVOICE",
        "Invoice No THIN/26-27/0009",
        "Invoice Date 04/07/2026",
        f"Supplier GSTIN {GSTIN}",
        "HSN 998314",
        "Taxable value 5000.00",
        "Invoice value 5900.00",
    ]
    INVOICES.joinpath("Tax_Invoice_header_only.pdf").write_bytes(pdf_with_text(header_only))
    _write_readme(
        INVOICES,
        "03 — Tax invoices",
        "Printed GST invoices. The app only writes a purchase workbook when it finds a **header plus an HSN line-item table**. It must not invent a total from the last number on the page.",
        [
            (ACME.name, "Invoice", "One HSN line (Professional fees 998314). GSTIN checksum ok.", "`Purchase_Register_Extracted.xlsx` sheets **Invoices** and **Line items**. Not needs_review."),
            ("Tax_Invoice_Mehta_two_lines.pdf", "Invoice", "Two HSN lines (998314 and 997331) summing to 11800.", "Two line-item rows keyed by MEHTA/26-27/0881."),
            ("Tax_Invoice_BadGSTIN.pdf", "Invoice", "Still unpacks, but GSTIN checksum is wrong on purpose.", "Purchase row exists; Flags include `gstin_checksum`; row tinted. Job can still be done if nothing else is blocked."),
            ("Tax_Invoice_BadHSN.pdf", "Invoice", "HSN 12345 is not 4/6/8 digits.", "Purchase row with `hsn_length` flag. Not rewritten."),
            ("Tax_Invoice_header_only.pdf", "Invoice", "Looks like a bill but **no item table**.", "No purchase row. File stays in **Needs review**. `Needs_Review.xlsx` status unreadable / no line items. Job `needs_review`."),
        ],
    )

    GSTR_2B.write_text(
        json.dumps(
            {
                "gstin": CLIENT_GSTIN,
                "rtnprd": "072026",
                "data": {
                    "docdata": {
                        "b2b": [
                            {
                                "ctin": GSTIN,
                                "trdnm": "Acme Traders",
                                "inv": [
                                    {
                                        "inum": "ACME/26-27/0142",
                                        "dt": "12-07-2026",
                                        "val": 11800,
                                        "txval": 10000,
                                        "iamt": 0,
                                        "camt": 900,
                                        "samt": 900,
                                    }
                                ],
                            }
                        ]
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    GST.joinpath("GSTR-2B_July_busy.json").write_text(
        json.dumps(
            {
                "gstin": CLIENT_GSTIN,
                "rtnprd": "072026",
                "data": {
                    "docdata": {
                        "b2b": [
                            {
                                "ctin": GSTIN,
                                "trdnm": "Acme Traders",
                                "inv": [
                                    {
                                        "inum": "ACME/26-27/0142",
                                        "dt": "12-07-2026",
                                        "val": 11800,
                                        "txval": 10000,
                                        "camt": 900,
                                        "samt": 900,
                                    }
                                ],
                            },
                            {
                                "ctin": "29AABCU9603R1ZX",
                                "trdnm": "Lakshmi Printers",
                                "inv": [
                                    {
                                        "inum": "LP/778",
                                        "dt": "08-07-2026",
                                        "val": 4720,
                                        "txval": 4000,
                                        "iamt": 720,
                                    }
                                ],
                            },
                        ],
                        "cdnr": [
                            {
                                "ctin": GSTIN,
                                "trdnm": "Acme Traders",
                                "nt": [
                                    {
                                        "ntnum": "CN/0142-A",
                                        "dt": "20-07-2026",
                                        "val": 1180,
                                        "txval": 1000,
                                        "camt": 90,
                                        "samt": 90,
                                    }
                                ],
                            }
                        ],
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    GSTR_1.write_text(
        json.dumps(
            {
                "gstin": CLIENT_GSTIN,
                "fp": "072026",
                "b2b": [{"ctin": GSTIN, "inv": [{"inum": "BN/101", "val": 5000, "itms": [{"itm_det": {"txval": 5000, "camt": 450, "samt": 450}}]}]}],
                "hsn": {"data": [{"hsn_sc": "9983", "txval": 5000}]},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    GSTR_3B.write_text(
        json.dumps(
            {
                "gstin": CLIENT_GSTIN,
                "ret_period": "072026",
                "sup_details": {"osup_det": {"txval": 50000, "iamt": 0, "camt": 4500, "samt": 4500}},
                "inward_sup": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    GST.joinpath("GSTR-2B_broken.json").write_text("{", encoding="utf-8")
    _write_readme(
        GST,
        "04 — GST portal JSON",
        "Official JSON downloads only. GST **PDFs** are not unpacked. This is a reshape (JSON → Excel), not OCR.",
        [
            (GSTR_2B.name, "GSTR-2B", "One B2B from Acme Traders, invoice ACME/26-27/0142. Match columns stay empty.", "`GSTR_2B_Formatted.xlsx` B2B sheet. No recon."),
            ("GSTR-2B_July_busy.json", "GSTR-2B", "Two B2B parties plus one credit note.", "B2B sheet plus CDN sheet when present."),
            (GSTR_1.name, "GSTR-1", "Outward B2B BN/101 and an HSN summary.", "`GSTR_1_Formatted.xlsx`."),
            (GSTR_3B.name, "GSTR-3B", "Summary outward taxable 50000.", "`GSTR_3B_Formatted.xlsx`."),
            ("GSTR-2B_broken.json", "GSTR-2B (filename)", "Not valid JSON.", "Zero rows. File in Needs review. Job `needs_review`. `Needs_Review.xlsx` status no rows."),
        ],
    )

    xml = _simple_tally_xml()
    busy = _tally_xml()
    TALLY_XML.write_text(xml, encoding="utf-8")
    BOOKS.joinpath("Tally_Daybook_busy.xml").write_text(busy, encoding="utf-8")
    with zipfile.ZipFile(TALLY_ZIP, "w") as archive:
        archive.writestr("DAYBOOK.xml", xml)
    with zipfile.ZipFile(BOOKS / "Tally_Backup_busy.zip", "w") as archive:
        archive.writestr("DAYBOOK.xml", busy)
    ZOHO_CSV.write_text(
        "Invoice Number,Invoice Date,GST Treatment,GST Identification Number (GSTIN),Item Tax %,Total,Customer Name\n"
        "INV-204,2026-07-08,taxable,27AAPFU0939F1ZV,18,5900,North Retail\n",
        encoding="utf-8",
    )
    BOOKS.joinpath("Zoho_Books_Invoices_busy.csv").write_text(
        "Invoice Number,Invoice Date,GST Treatment,GST Identification Number (GSTIN),Item Tax %,Total,Customer Name\n"
        "INV-204,2026-07-08,taxable,27AAPFU0939F1ZV,18,5900,North Retail\n"
        "INV-218,2026-07-22,taxable,27AAPFU0939F1ZV,18,2360,South Spices\n",
        encoding="utf-8",
    )
    _write_readme(
        BOOKS,
        "05 — Tally and Zoho exports",
        "Only structured exports. A Tally **print PDF** or a screenshot will not unpack. Live Tally ODBC is out of scope.",
        [
            (TALLY_XML.name, "Tally", "Single purchase voucher PUR-88 (Acme Traders, 11800).", "Purchase/books register with PUR-88."),
            ("Tally_Daybook_busy.xml", "Tally", "PUR-88, PUR-91 and sales SAL-10 in one daybook.", "Purchase and sales registers both written."),
            (TALLY_ZIP.name, "Tally", "Zip of the simple PUR-88 daybook.", "Same as Tally_Daybook.xml. Dumping both XML and this zip duplicates PUR-88."),
            ("Tally_Backup_busy.zip", "Tally", "Zip of the busy daybook.", "Same as Tally_Daybook_busy.xml."),
            (ZOHO_CSV.name, "Zoho", "One sales invoice INV-204.", "Sales register INV-204, value 5900."),
            ("Zoho_Books_Invoices_busy.csv", "Zoho", "INV-204 plus INV-218.", "Two sales rows."),
        ],
    )

    INVOICE_PHOTO.write_bytes(PNG)
    RANDOM_JPG.write_bytes(JPEG)
    MEETING_NOTES.write_bytes(b"PK dummy office file, not a real invoice")
    JUNK.joinpath("random_email_print.pdf").write_bytes(
        pdf_with_text(["Meeting notes 12 July", "Call Rajesh about TDS", "No GSTIN and no invoice table here"])
    )
    _write_readme(
        JUNK,
        "06 — Unknown and unreadable",
        "These should stay in the CA’s face. The job must not look finished.",
        [
            (MEETING_NOTES.name, "Unknown", "Word file. No parser.", "Needs review. Set a type only if you really know it. `Needs_Review.xlsx` status unknown."),
            (RANDOM_JPG.name, "Unknown (or invoice if OCR sees GST words)", "Tiny JPEG with no invoice text.", "Needs review. Must **not** invent a purchase row."),
            (INVOICE_PHOTO.name, "Unknown / unreadable invoice", "1×1 PNG. No OCR table.", "No purchase Excel row. Needs review."),
            ("random_email_print.pdf", "Unknown", "PDF with meeting notes, not a bank or invoice.", "Needs review. No bank/purchase pack from this file alone."),
        ],
    )

    shutil.copy2(HDFC, MIXED / HDFC.name)
    shutil.copy2(ACME, MIXED / ACME.name)
    shutil.copy2(INVOICES / "Tax_Invoice_header_only.pdf", MIXED / "Tax_Invoice_header_only.pdf")
    shutil.copy2(GSTR_2B, MIXED / GSTR_2B.name)
    shutil.copy2(TALLY_XML, MIXED / TALLY_XML.name)
    shutil.copy2(MEETING_NOTES, MIXED / MEETING_NOTES.name)
    shutil.copy2(GST / "GSTR-2B_broken.json", MIXED / "GSTR-2B_broken.json")
    _write_readme(
        MIXED,
        "07 — Mixed client month (dump this one to see honesty)",
        "A realistic tray: bank + good invoice + thin invoice + GSTR JSON + Tally + junk + broken JSON. Add **this whole folder** to one period.",
        [
            (HDFC.name, "Bank statement", "Digital HDFC.", "`Bank_Statement_Cleaned.xlsx` written."),
            (ACME.name, "Invoice", "Line-item tax invoice.", "`Purchase_Register_Extracted.xlsx` Invoices + Line items."),
            ("Tax_Invoice_header_only.pdf", "Invoice", "No item table.", "Needs review — not a fake purchase row."),
            (GSTR_2B.name, "GSTR-2B", "Valid JSON.", "`GSTR_2B_Formatted.xlsx`."),
            ("GSTR-2B_broken.json", "GSTR-2B", "Broken JSON.", "Needs review."),
            (TALLY_XML.name, "Tally", "Daybook XML.", "Books / purchase / sales sheets."),
            (MEETING_NOTES.name, "Unknown", "Word notes.", "Needs review."),
        ],
    )
    mixed_note = MIXED / "README.md"
    extra = (
        mixed_note.read_text(encoding="utf-8")
        + "\n**Period job status:** `needs_review` (not done) because of the header-only invoice, broken JSON, and Word file.\n"
        "**Still on disk:** bank Excel, purchase Excel for Acme, GSTR-2B Excel, Tally sheets, and `Needs_Review.xlsx` listing the failures.\n"
    )
    mixed_note.write_text(extra, encoding="utf-8")

    DUMP.joinpath("README.md").write_text(
        """# Sample dump kit

Each numbered folder is one scenario. In CA Unpacker: add a client and a period, then **Add folder** and pick **one** of these folders.

| Folder | What it is | When the job looks finished |
|---|---|---|
| `01-banks-digital` | Clean HDFC / ICICI / SBI PDFs | `done` if you dump only this folder |
| `02-banks-messy` | Longer narrations + a 90-line statement | `done` if only this folder |
| `03-invoices` | Line-item bills plus a header-only bill | `needs_review` because of `Tax_Invoice_header_only.pdf` |
| `04-gst-json` | Portal JSON plus one broken file | `needs_review` because of `GSTR-2B_broken.json` |
| `05-books-tally-zoho` | Tally XML/zip and Zoho CSV | `done` if only this folder |
| `06-unknown-junk` | Word / tiny images / notes PDF | `needs_review` |
| `07-mixed-client-month` | One messy month | `needs_review` — this is the honesty check |

Do not dump `Darshan` or other **output** folders back in. Cleaned Excels belong in the folder you chose at first launch.

Unzip this kit, then in CA Unpacker add a client and a period, then **Add folder** and pick **one** numbered folder.

Rebuild this tree and the landing-page zip:

```bat
.venv\\Scripts\\python.exe build_test_dump.py
```
""",
        encoding="utf-8",
    )
    _write_landing_zip()
    print(f"Wrote sample dump kit at {DUMP}")
    print(f"Wrote {LANDING_ZIP}")


def _write_landing_zip() -> None:
    LANDING_ZIP.parent.mkdir(parents=True, exist_ok=True)
    prefix = "CAUnpacker-Test-Files"
    with zipfile.ZipFile(LANDING_ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in DUMP.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(DUMP).as_posix()
            archive.write(path, f"{prefix}/{rel}")


if __name__ == "__main__":
    build()
