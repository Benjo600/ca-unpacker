"""Stress-test dump builder: harder, larger, nastier dummy files than build_test_dump.py.

Writes to stress-dump/ (gitignored). Safe to re-run; wipes the folder first.
Run: .venv\\Scripts\\python.exe build_stress_dump.py
"""

from __future__ import annotations

import json
import shutil
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from make_test_dump import JPEG, PNG, pdf_with_text

ROOT = Path(__file__).resolve().parent
DUMP = ROOT / "stress-dump"

BANKS = DUMP / "01-banks-stress"
INVOICES = DUMP / "02-invoices-stress"
GST = DUMP / "03-gst-stress"
BOOKS = DUMP / "04-books-stress"
JUNK = DUMP / "05-junk-stress"
MIXED = DUMP / "06-mixed-stress"

GSTIN = "27AAPFU0939F1ZV"
CLIENT_GSTIN = "29ABCDE1234F1Z5"


def indian(value: Decimal | float | int) -> str:
    """Format 1234567.89 -> 12,34,567.89 (Indian comma grouping)."""
    value = Decimal(value).quantize(Decimal("0.01"))
    neg = value < 0
    value = -value if neg else value
    whole, _, frac = str(value).partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups + [tail])
    return ("-" if neg else "") + whole + "." + frac


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


def _multi_page(
    path: Path,
    header: list[str],
    events: list[tuple[str, str, str, Decimal]],
    opening: Decimal,
    page_size: int,
    footer: str = "",
) -> None:
    balance = opening
    body: list[str] = []
    for date, narr, word, amount in events:
        debit_word = word.lower() in {"withdrawal", "debit", "dr", "atm withdrawal"}
        balance = balance - amount if debit_word else balance + amount
        body.append(f"{date} {narr} {word} {indian(amount)} {indian(balance)}")
    if page_size <= 0:
        _write_pdf(path, list(header) + body + [f"Closing Balance {indian(balance)}"])
        return
    pages_no = (len(body) + page_size - 1) // page_size
    pages: list[list[str]] = []
    for page_no, start in enumerate(range(0, len(body), page_size), 1):
        lines = list(header) if page_no == 1 else [header[0] + " (continued)"]
        lines.extend(body[start : start + page_size])
        if page_no < pages_no and footer:
            lines.append(footer.format(page=page_no, total=pages_no))
        else:
            lines.append(f"Closing Balance {indian(balance)}")
        pages.append(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pdf_pages(pages))


def _events(count: int, *, day_step: int, vendors: tuple[str, ...], seed_amt: int) -> list[tuple[str, str, str, Decimal]]:
    """Deterministic debit-heavy event stream."""
    events: list[tuple[str, str, str, Decimal]] = []
    day = 1
    for i in range(count):
        day = 1 + ((i * day_step) % 30)
        vendor = vendors[i % len(vendors)]
        if i % 3 == 0:
            word, amount = "Deposit", Decimal(f"{seed_amt + i * 37}.00")
            narr = f"NEFT CR {vendor} INV/{seed_amt + i}"
        else:
            word, amount = "Withdrawal", Decimal(f"{seed_amt // 2 + i * 19}.00")
            narr = f"UPI {vendor} ref {400000000000 + i * 7}"
        events.append((f"{day:02d}/07/2026", narr, word, amount))
    return events


def build_banks() -> None:
    BANKS.mkdir(parents=True, exist_ok=True)

    # 1: Indian comma grouping, lakh/crore scale (Axis)
    opening = Decimal("1254300.50")
    events = _events(40, day_step=1, vendors=("SHREE STEELS", "KIRAN AGENCIES", "IRCTC RAIL"), seed_amt=5000)
    _multi_page(
        BANKS / "Axis_Bank_CommaLakhs_Jul2026.pdf",
        ["Axis Bank Statement", "Account Number 917020045678901", "IFSC UTIB0000123", f"Opening Balance {indian(opening)}"],
        events, opening, page_size=25, footer="Page {page} of {total}",
    )

    # 2: lowercase dr/cr words (Kotak)
    opening = Decimal("45000.00")
    events = [
        ("01/07/2026", "upi inward kiran agencies", "cr", Decimal("8000.00")),
        ("03/07/2026", "upi merchant zomato", "dr", Decimal("1250.00")),
        ("08/07/2026", "neft bharat packaging", "dr", Decimal("9200.00")),
        ("15/07/2026", "salary jul", "cr", Decimal("35000.00")),
        ("22/07/2026", "ixigo rail", "dr", Decimal("1471.50")),
        ("29/07/2026", "interest", "cr", Decimal("62.35")),
    ]
    _write_pdf(
        BANKS / "Kotak_LowerCase_DrCr_Jul2026.pdf",
        ["Kotak Mahindra Bank Ltd", "CRN 4711082 IFSC KKBK0000958", f"opening balance {opening:.2f}"]
        + [
            f"{d} {n} {w} {a:.2f}"
            for d, n, w, a in _running(opening, events)
        ]
        + [f"closing balance {_closing(opening, events):.2f}"],
    )

    # 3: month boundary dates incl. 31st (SBI)
    opening = Decimal("88000.00")
    events = [
        ("01/07/2026", "IMPS from client", "Credit", Decimal("15000.00")),
        ("14/07/2026", "ATM WDL MG Road", "Debit", Decimal("3000.00")),
        ("31/07/2026", "To transfer Kiran Agencies", "Debit", Decimal("12000.00")),
        ("31/07/2026", "Cheque deposit self", "Credit", Decimal("1000.00")),
        ("31/07/2026", "SMS alert chg", "Debit", Decimal("15.00")),
    ]
    _multi_page(
        BANKS / "SBI_MonthBoundary_Jul2026.pdf",
        ["State Bank of India", "Statement of Account 01/07/2026 - 31/07/2026", "Account Number 389100112233", f"Opening Balance {opening:.2f}"],
        events, opening, page_size=0,
    )

    # 4: 300-row multi-page with big UPI references (HDFC)
    opening = Decimal("1000000.00")
    vendors = ("ZOMATO LIMITED", "LAKSHMI PRINTERS", "BHARAT PACKAGING", "MEHTA EXPORTS", "KIRAN AGENCIES", "IRCTC RAIL", "AIRTEL THANKS", "SHREE STEELS")
    events = []
    for i in range(300):
        vendor = vendors[i % len(vendors)]
        if i % 3 == 0:
            events.append((f"{1 + (i % 28):02d}/07/2026", f"NEFT CR {vendor} INV/{9000 + i} RRN {200000000000 + i * 13}", "Deposit", Decimal(f"{2000 + i * 17}.50")))
        else:
            events.append((f"{1 + (i % 28):02d}/07/2026", f"UPI/{vendor}/ref{618000000000 + i * 29}/PhonePe", "Withdrawal", Decimal(f"{180 + i * 11}.25")))
    _multi_page(
        BANKS / "HDFC_Long300_Jul2026.pdf",
        ["HDFC Bank Account Statement", "Account Number 502000111222", "IFSC HDFC0001888", f"Opening Balance {opening:.2f}"],
        events, opening, page_size=30, footer="Page {page} of {total} | This is a system generated statement and does not require a signature",
    )

    # 5: crore-scale comma amounts (ICICI)
    opening = Decimal("12345678.90")
    events = [
        ("02/07/2026", "RTGS INWARD MEHTA EXPORTS", "Credit", Decimal("4500000.00")),
        ("08/07/2026", "NEFT OUTWARD BHARAT PACKAGING", "Debit", Decimal("1275000.00")),
        ("16/07/2026", "FD BOOKING", "Debit", Decimal("5000000.00")),
        ("21/07/2026", "RTGS INWARD NORTH RETAIL", "Credit", Decimal("875000.25")),
        ("28/07/2026", "PAYMENT SHREE STEELS", "Debit", Decimal("234567.89")),
    ]
    _multi_page(
        BANKS / "ICICI_CroreScale_Jul2026.pdf",
        ["ICICI Bank Ltd Statement", "Account Number 000405998877", "IFSC ICIC0002211", f"Opening Balance {indian(opening)}"],
        events, opening, page_size=0,
    )

    # 6: Dr / Cr suffix instead of deposit/withdrawal words (Axis)
    opening = Decimal("60000.00")
    events = [
        ("02/07/2026", "UPI Kiran Agencies", "", Decimal("4000.00")),  # credit suffix below
        ("05/07/2026", "UPI Zomato", "", Decimal("780.00")),
        ("11/07/2026", "NEFT Mehta Exports", "", Decimal("15000.00")),
        ("19/07/2026", "Charges SMS chg", "", Decimal("23.60")),
    ]
    balance = opening
    lines = ["Axis Bank Statement of Account", "Account Number 917023411223344", "IFSC UTIB0004567", f"Opening Balance {opening:.2f}"]
    for (date, narr, _, amount), suffix in zip(events, ("Cr", "Dr", "Cr", "Dr")):
        balance = balance + amount if suffix == "Cr" else balance - amount
        lines.append(f"{date} {narr} {indian(amount)} {suffix} {indian(balance)}")
    lines.append(f"Closing Balance {indian(balance)}")
    _write_pdf(BANKS / "Axis_DrSuffix_Jul2026.pdf", lines)

    # 7: generic regional bank, no known hints
    opening = Decimal("32100.00")
    events = [
        ("03/07/2026", "NEFT customer Anand Stores", "Deposit", Decimal("7800.00")),
        ("12/07/2026", "ATM withdrawal Dadar", "Withdrawal", Decimal("2000.00")),
        ("20/07/2026", "UPI merchant Hibiscus Cafe", "Withdrawal", Decimal("640.00")),
        ("30/07/2026", "Interest capitalised", "Deposit", Decimal("41.27")),
    ]
    balance = opening
    lines = ["Janakalyan Sahakari Bank Ltd Statement of Account", "Account Number 00320104567", "IFSC JSBL0000123", f"Opening Balance {opening:.2f}"]
    for date, narr, word, amount in events:
        balance = balance + amount if word == "Deposit" else balance - amount
        lines.append(f"{date} {narr} {word} {amount:.2f} {balance:.2f}")
    lines.append(f"Closing Balance {balance:.2f}")
    _write_pdf(BANKS / "Generic_Regional_Jul2026.pdf", lines)

    # 8: narration packed with distracting numbers (HDFC)
    opening = Decimal("50000.00")
    events = [
        ("02/07/2026", "UPI BSS VODAFONE bill subsidy scheme 799.00 ref 432198765432", "Withdrawal", Decimal("2500.00")),
        ("06/07/2026", "NEFT INWARD Mehta Exports inv 9012 amt 18000.00", "Deposit", Decimal("18000.00")),
        ("09/07/2026", "ACH EMI Bajaj Finance loan 1099.00 instalment", "Withdrawal", Decimal("3200.00")),
        ("17/07/2026", "IMPS Kiran Agencies hall ticket 4401 seat 21", "Deposit", Decimal("9200.00")),
    ]
    balance = opening
    lines = ["HDFC Bank Account Statement", "Account Number 50100123456789", "IFSC HDFC0001234", f"Opening Balance {opening:.2f}"]
    for date, narr, word, amount in events:
        balance = balance - amount if word == "Withdrawal" else balance + amount
        lines.append(f"{date} {narr} {word} {amount:.2f} {balance:.2f}")
    lines.append(f"Closing Balance {balance:.2f}")
    _write_pdf(BANKS / "HDFC_NarrationNumbers_Jul2026.pdf", lines)

    # 9: Kotak month-name dates, 150 rows, comma amounts
    opening = Decimal("250000.00")
    events: list[tuple[str, str, str, Decimal]] = []
    for i in range(150):
        day = 1 + (i * 3) % 30
        vendor = vendors[i % len(vendors)]
        if i % 4 == 0:
            events.append((f"{day:02d} Jul2026", f"UPI inward {vendor} id {510000000000 + i}", "Deposit", Decimal(f"{1400 + i * 23}.00")))
        else:
            events.append((f"{day:02d} Jul2026", f"UPI merchant {vendor} id {610000000000 + i}", "Withdrawal", Decimal(f"{210 + i * 13}.50")))
    _multi_page(
        BANKS / "Kotak_MonthName150_Jul2026.pdf",
        ["Kotak Mahindra Bank Ltd", "CRN 9012882 IFSC KKBK0000958", "Statement 01 Jul 2026 - 31 Jul 2026", f"Opening Balance {indian(opening)}"],
        events, opening, page_size=25, footer="Page {page} of {total}",
    )

    # 10: dense boilerplate between rows (SBI)
    opening = Decimal("150000.00")
    events = _events(60, day_step=2, vendors=("MEHTA EXPORTS", "LAKSHMI PRINTERS", "NORTH RETAIL"), seed_amt=3000)
    balance = opening
    body = [
        "State Bank of India",
        "Account Number 12345678901 IFSC SBIN0000456",
        f"Opening Balance {opening:.2f}",
        "Legends: NEFT=National Electronic Funds Transfer IMPS=Immediate Payment Service",
    ]
    n = 0
    for date, narr, word, amount in events:
        n += 1
        balance = balance - amount if word.lower() in {"withdrawal", "debit"} else balance + amount
        body.append(f"{date} {narr} {word} {amount:.2f} {balance:.2f}")
        if n % 6 == 0:
            body.append("This is a computer generated statement and does not require physical signature.")
        if n % 9 == 0:
            body.append("SBIN | Mumbai Main Branch | 11 Vidhan Bhavan Marg Nariman Point Mumbai 400021 022-22023333")
        if n % 12 == 0:
            body.append("Debits 24 Credits 36 Closing Balance as per statement summary reconciled")
    body.append(f"Closing Balance {balance:.2f}")
    _write_pdf(BANKS / "SBI_BoilerplateNoise_Jul2026.pdf", body)

    # 11: odd paisa rounding everywhere (HDFC)
    opening = Decimal("100000.03")
    events = [
        ("01/07/2026", "UPI Chai Point", "Withdrawal", Decimal("47.97")),
        ("04/07/2026", "IMPS client advance", "Deposit", Decimal("25600.01")),
        ("08/07/2026", "Cheque 334455 printer", "Withdrawal", Decimal("1280.49")),
        ("19/07/2026", "Interest quarterly", "Deposit", Decimal("233.43")),
        ("27/07/2026", "UPI Stationery Mart", "Withdrawal", Decimal("99.99")),
    ]
    balance = opening
    lines = ["HDFC Bank Account Statement", "Account Number 50100123456789", "IFSC HDFC0001234", f"Opening Balance {opening:.2f}"]
    for date, narr, word, amount in events:
        balance = balance - amount if word == "Withdrawal" else balance + amount
        lines.append(f"{date} narr {word} {amount:.2f} {balance:.2f}")
    lines.append(f"Closing Balance {balance:.2f}")
    _write_pdf(BANKS / "HDFC_PaisaRounding_Jul2026.pdf", lines)

    # 12: ALL CAPS + mixed case deposit/debit words (Axis)
    opening = Decimal("77000.00")
    events = [
        ("03/07/2026", "UPI SHREE STEELS", "DEPOSIT", Decimal("12000.00")),
        ("07/07/2026", "UPI zomato", "Withdrawal", Decimal("640.00")),
        ("15/07/2026", "NEFT Production House", "Deposit", Decimal("8900.50")),
        ("23/07/2026", "ATM WDL", "Withdrawal", Decimal("3000.00")),
    ]
    balance = opening
    lines = ["Axis Bank Statement", "Account Number 917020055667788", "IFSC UTIB0000123", f"Opening Balance {opening:.2f}"]
    for date, narr, word, amount in events:
        balance = balance - amount if word.lower() in {"withdrawal", "debit"} else balance + amount
        lines.append(f"{date} {narr} {word} {amount:.2f} {balance:.2f}")
    lines.append(f"Closing Balance {balance:.2f}")
    _write_pdf(BANKS / "Axis_MixedCase_Jul2026.pdf", lines)


def _running(opening: Decimal, events: list[tuple[str, str, str, Decimal]]) -> list[tuple[str, str, Decimal, Decimal]]:
    out = []
    balance = opening
    for date, narr, word, amount in events:
        balance = balance - amount if word in "dr" else balance + amount
        out.append((date, narr, amount, balance))
    return out


def _closing(opening: Decimal, events: list[tuple[str, str, str, Decimal]]) -> Decimal:
    balance = opening
    for _, _, word, amount in events:
        balance = balance - amount if word in "dr" else balance + amount
    return balance


def build_invoices() -> None:
    INVOICES.mkdir(parents=True, exist_ok=True)

    # a: 30 line-item invoice, arithmetic exact to the paisa
    items = [(f"Design sprint block {i}", Decimal(f"{1000 + i * 137}.37")) for i in range(1, 31)]
    taxable = sum(i[1] for i in items)
    cgst = (taxable * Decimal("0.09")).quantize(Decimal("0.01"))
    sgst = (taxable * Decimal("0.09")).quantize(Decimal("0.01"))
    total = taxable + cgst + sgst
    lines = ["TAX INVOICE", "Invoice No BIG/26-27/0030", "Invoice Date 30/07/2026", f"Supplier GSTIN {GSTIN}", "Supplier name Mehta Exports Pvt Ltd", "Place of Supply 27-Maharashtra", "HSN Qty Rate Taxable Amount"]
    for name, amt in items:
        lines.append(f"{name} 998314 1 {amt} {amt} {amt + amt * Decimal('0.18'):.2f}")
    lines += [f"Taxable value {taxable}", f"CGST {cgst}  SGST {sgst}", f"Invoice value {total}"]
    _write_pdf(INVOICES / "Tax_Invoice_Big_30_lines.pdf", lines)

    # b: fully exempt (zero GST)
    _write_pdf(
        INVOICES / "Tax_Invoice_Exempt_zero_gst.pdf",
        [
            "TAX INVOICE",
            "Invoice No EXEMPT/26-27/0017",
            "Invoice Date 09/07/2026",
            f"Supplier GSTIN {GSTIN}",
            "Place of Supply 27-Maharashtra",
            "HSN 999293",
            "HSN Qty Rate Taxable Amount",
            "Charitable services exempt 999293 1 8000.00 8000.00 8000.00",
            "Taxable value 8000.00",
            "CGST 0.00  SGST 0.00",
            "Invoice value 8000.00",
        ],
    )

    # c: one-paisa off total (rounding trap)
    _write_pdf(
        INVOICES / "Tax_Invoice_PaisaOff.pdf",
        [
            "TAX INVOICE",
            "Invoice No PAISA/26-27/0004",
            "Invoice Date 21/07/2026",
            f"Supplier GSTIN {GSTIN}",
            "Place of Supply 27-Maharashtra",
            "HSN 998314",
            "HSN Qty Rate Taxable Amount",
            "Consulting 998314 1 5000.00 5000.00 5900.00",
            "Taxable value 5000.00",
            "CGST 450.00  SGST 450.00",
            "Invoice value 5900.01",
        ],
    )

    # d: high value (trigger warning_high_value on starter profile)
    _write_pdf(
        INVOICES / "Tax_Invoice_HighValue_lakh.pdf",
        invoice_pdf_lines(
            "HIGH/26-27/0001", date="25/07/2026", taxable="2500000.00",
            cgst="225000.00", sgst="225000.00", total="2950000.00",
        ),
    )


def invoice_pdf_lines(no: str, *, date: str, taxable: str, cgst: str, sgst: str, total: str) -> list[str]:
    return [
        "TAX INVOICE",
        f"Invoice No {no}",
        f"Invoice Date {date}",
        f"Supplier GSTIN {GSTIN}",
        "Place of Supply 27-Maharashtra",
        "HSN 998314",
        "HSN Qty Rate Taxable Amount",
        f"Enterprise retainer 998314 1 {taxable} {taxable} {total}",
        f"Taxable value {taxable}",
        f"CGST {cgst}  SGST {sgst}",
        f"Invoice value {total}",
    ]


def build_gst() -> None:
    GST.mkdir(parents=True, exist_ok=True)

    # busy 2B: 3 parties, 25 invoices, 4 credit notes
    invoices_2b = []
    parties = [("27AAPFU0939F1ZV", "Acme Traders"), ("29AABCU9603R1ZX", "Lakshmi Printers"), ("27AAACN1234A1Z5", "North Retail")]
    i = 0
    for ctin, name in parties:
        group = []
        for k in range(8 if name == "Acme Traders" else 8 if name == "Lakshmi Printers" else 6):
            i += 1
            group.append({
                "inum": f"INV/{26 - 27 if False else '26-27'}/{i:04d}",
                "dt": f"{2 + k}-07-2026",
                "val": 1180 * (k + 1),
                "txval": 1000 * (k + 1),
                "camt": 90 * (k + 1),
                "samt": 90 * (k + 1),
            })
        invoices_2b.append({"ctin": ctin, "trdnm": name, "inv": group})
    busy_2b = {
        "gstin": CLIENT_GSTIN,
        "rtnprd": "072026",
        "data": {"docdata": {"b2b": invoices_2b, "cdnr": [
            {"ctin": parties[0][0], "trdnm": parties[0][1], "nt": [{"ntnum": f"CN/{n:03d}", "dt": f"{20 + n}-07-2026", "val": 1180, "txval": 1000, "camt": 90, "samt": 90} for n in range(1, 5)]},
        ]}},
    }
    (GST / "GSTR-2B_July_three_parties.json").write_text(json.dumps(busy_2b, indent=2), encoding="utf-8")

    (GST / "GSTR-2B_empty_data.json").write_text(
        json.dumps({"gstin": CLIENT_GSTIN, "rtnprd": "072026", "data": {"docdata": {}}}, indent=2),
        encoding="utf-8",
    )

    g1_invoices = []
    for n in range(1, 9):
        g1_invoices.append({"ctin": f"27AAACP{1000 + n}Q1Z{n}", "inv": [{"inum": f"OUT/{n:03d}", "val": 5900 * n, "itms": [{"itm_det": {"txval": 5000 * n, "camt": 450 * n, "samt": 450 * n}}]}]})
    (GST / "GSTR-1_July_outward8.json").write_text(
        json.dumps({"gstin": CLIENT_GSTIN, "fp": "072026", "b2b": g1_invoices, "hsn": {"data": [
            {"hsn_sc": "9983", "txval": 45000}, {"hsn_sc": "9973", "txval": 12000}, {"hsn_sc": "6109", "txval": 8000},
        ]}}, indent=2),
        encoding="utf-8",
    )

    (GST / "GSTR-3B_July.json").write_text(
        json.dumps({"gstin": CLIENT_GSTIN, "ret_period": "072026", "sup_details": {"osup_det": {"txval": 65000, "iamt": 0, "camt": 5850, "samt": 5850}}, "inward_sup": {}}, indent=2),
        encoding="utf-8",
    )

    (GST / "GSTR-2B_broken.json").write_text("{ \"gstin\": \"29ABCDE1234F1Z5\", \"data\": ", encoding="utf-8")


def build_books() -> None:
    BOOKS.mkdir(parents=True, exist_ok=True)

    # 40-voucher Tally daybook (30 purchases + 10 sales), then a zip backup
    vouchers = []
    for n in range(1, 41):
        if n <= 30:
            vouchers.append(
                "   <VOUCHER VCHTYPE=\"Purchase\">\n"
                f"    <DATE>202607{2 + n % 27:02d}</DATE>\n"
                f"    <VOUCHERNUMBER>PUR-{n}</VOUCHERNUMBER>\n"
                f"    <PARTYLEDGERNAME>{'Acme Traders' if n % 2 else 'Lakshmi Printers'}</PARTYLEDGERNAME>\n"
                f"    <PARTYGSTIN>{'27AAPFU0939F1ZV' if n % 2 else '29AABCU9603R1ZX'}</PARTYGSTIN>\n"
                f"    <AMOUNT>-{1180 * n}.00</AMOUNT>\n"
                f"    <TAXABLEVALUE>{1000 * n}.00</TAXABLEVALUE>\n"
                "    <HSNCODE>998314</HSNCODE>\n"
                "   </VOUCHER>"
            )
        else:
            vouchers.append(
                "   <VOUCHER VCHTYPE=\"Sales\">\n"
                f"    <DATE>202607{2 + n % 27:02d}</DATE>\n"
                f"    <VOUCHERNUMBER>SAL-{n - 30}</VOUCHERNUMBER>\n"
                "    <PARTYLEDGERNAME>North Retail</PARTYLEDGERNAME>\n"
                "    <PARTYGSTIN>27AAACN1234A1Z5</PARTYGSTIN>\n"
                f"    <AMOUNT>{2360 * (n - 30)}.00</AMOUNT>\n"
                f"    <TAXABLEVALUE>{2000 * (n - 30)}.00</TAXABLEVALUE>\n"
                "    <HSNCODE>997331</HSNCODE>\n"
                "   </VOUCHER>"
            )
    xml = (
        "<?xml version=\"1.0\"?>\n<ENVELOPE>\n <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>\n"
        " <BODY>\n  <TALLYMESSAGE>\n" + "\n".join(vouchers) + "\n  </TALLYMESSAGE>\n </BODY>\n</ENVELOPE>\n"
    )
    (BOOKS / "Tally_Daybook_40vouchers.xml").write_text(xml, encoding="utf-8")
    with zipfile.ZipFile(BOOKS / "Tally_Backup_40vouchers.zip", "w") as archive:
        archive.writestr("DAYBOOK.xml", xml)

    # Zoho CSV with quoted names containing commas, 40 rows
    rows = ["Invoice Number,Invoice Date,GST Treatment,GST Identification Number (GSTIN),Item Tax %,Total,Customer Name"]
    for n in range(1, 41):
        rows.append(
            f"INV-{200 + n},2026-07-{1 + n % 28:02d},taxable,27AAPFU0939F1ZV,18,{590 + n * 17},\"{('North Retail, Andheri' if n % 2 else 'South Spices, Warje')}\""
        )
    (BOOKS / "Zoho_Books_40rows.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def build_junk() -> None:
    JUNK.mkdir(parents=True, exist_ok=True)
    JUNK.joinpath("team_meeting_notes.pdf").write_bytes(pdf_with_text(["Meeting notes 20 July", "Follow up with Rajesh on TDS lookup", "No GSTIN and no invoice table here"]))
    JUNK.joinpath("tiny.png").write_bytes(PNG)
    JUNK.joinpath("tiny.jpg").write_bytes(JPEG)
    JUNK.joinpath("fake_office_file.docx").write_bytes(b"PK dummy office file, not a real pack source")


def build_mixed() -> None:
    MIXED.mkdir(parents=True, exist_ok=True)
    picks = [
        BANKS / "Axis_Bank_CommaLakhs_Jul2026.pdf",
        BANKS / "HDFC_NarrationNumbers_Jul2026.pdf",
        INVOICES / "Tax_Invoice_Big_30_lines.pdf",
        INVOICES / "Tax_Invoice_PaisaOff.pdf",
        GST / "GSTR-2B_July_three_parties.json",
        GST / "GSTR-2B_broken.json",
        BOOKS / "Tally_Daybook_40vouchers.xml",
        BOOKS / "Zoho_Books_40rows.csv",
        JUNK / "team_meeting_notes.pdf",
    ]
    for src in picks:
        shutil.copy2(src, MIXED / src.name)


def build() -> None:
    if DUMP.exists():
        shutil.rmtree(DUMP)
    for folder in (BANKS, INVOICES, GST, BOOKS, JUNK, MIXED):
        folder.mkdir(parents=True, exist_ok=True)

    build_banks()
    build_invoices()
    build_gst()
    build_books()
    build_junk()
    build_mixed()

    DUMP.joinpath("README.md").write_text(
        """# Stress dump kit (dummy data, machine generated)

Every bank PDF computes its own running balance, so a correct parser must land on a
**match**. Intended stress angles:

| Folder | Files | Stress angle |
|---|---|---|
| `01-banks-stress` | 12 PDFs | Indian comma lakhs, lowercase dr/cr, 31st-of-month rows, 300-row multi-page with 12-digit UPI refs in narrations, crore scale, amount + Dr/Cr suffix, unknown regional bank, narrations stuffed with numbers that look like amounts, 150 Kotak month-name rows, boilerplate every few rows, odd-paisa rounding, ALL-CAPS words |
| `02-invoices-stress` | 4 PDFs | 30-line item invoice, zero-GST exempt, total that is 1 paisa off, 25-lakh high-value |
| `03-gst-stress` | 5 JSONs | 3-party 25-invoice 2B with credit notes, empty 2B data, 8-invoice GSTR-1 with 3-row HSN summary, 3B, deliberately broken JSON |
| `04-books-stress` | 4 files | 40-voucher Tally daybook (+ zip backup), 40-row Zoho CSV with quoted comma customer names |
| `05-junk-stress` | 4 files | notes PDF, tiny PNG, tiny JPEG, fake .docx |
| `06-mixed-stress` | 9 files | one file from every folder above, dump whole folder at once |
""",
        encoding="utf-8",
    )
    print(f"Wrote stress dump kit at {DUMP}")


if __name__ == "__main__":
    build()
