from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent / "test-dump" / "complex-statements"


def inr(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    n = abs(value).quantize(Decimal("0.01"))
    whole, frac = f"{n:.2f}".split(".")
    if len(whole) <= 3:
        grouped = whole
    else:
        grouped = whole[-3:]
        rest = whole[:-3]
        while rest:
            grouped = rest[-2:] + "," + grouped
            rest = rest[:-2]
    return f"{sign}{grouped}.{frac}"


def apply(opening: Decimal, events: list[dict]) -> list[dict]:
    balance = opening
    rows = []
    for event in events:
        debit = Decimal(str(event.get("debit") or 0))
        credit = Decimal(str(event.get("credit") or 0))
        balance = balance - debit + credit
        rows.append({**event, "debit": debit, "credit": credit, "balance": balance})
    return rows


def styles_for(accent):
    base = getSampleStyleSheet()
    return {
        "bank": ParagraphStyle("bank", parent=base["Heading1"], fontName="Times-Bold", fontSize=16, textColor=accent, spaceAfter=1, leading=18),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#444444"), leading=10),
        "h": ParagraphStyle("h", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10),
        "tiny": ParagraphStyle("tiny", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#333333")),
        "tinyR": ParagraphStyle("tinyR", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9, alignment=TA_RIGHT),
        "narr": ParagraphStyle("narr", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9),
        "th": ParagraphStyle("th", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=colors.white),
        "foot": ParagraphStyle("foot", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=7, textColor=colors.HexColor("#666666")),
        "box": ParagraphStyle("box", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, leading=10, alignment=TA_LEFT),
    }


def cell(text, style):
    return Paragraph(str(text).replace("\n", "<br/>"), style)


def statement(path: Path, spec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    accent = colors.HexColor(spec["accent"])
    s = styles_for(accent)
    opening = Decimal(str(spec["opening"]))
    rows = apply(opening, spec["events"])
    closing = rows[-1]["balance"] if rows else opening

    def draw_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(accent)
        canvas.rect(0, A4[1] - 18, A4[0], 18, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(16 * mm, A4[1] - 12, spec["banner"])
        canvas.drawRightString(A4[0] - 16 * mm, A4[1] - 12, f"Page {doc.page}")
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(16 * mm, 10 * mm, "Computer generated fictional statement for parser testing. Not a real bank document.")
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, spec["footer_id"])
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=spec["title"],
    )

    story = []
    story.append(Paragraph(spec["bank_name"], s["bank"]))
    story.append(Paragraph(spec["tagline"], s["sub"]))
    story.append(Spacer(1, 6))

    left = (
        f"<b>Customer</b><br/>{spec['customer']}<br/>{spec['address']}<br/><br/>"
        f"<b>Customer ID</b> {spec['cust_id']}<br/>"
        f"<b>Account No.</b> {spec['account']}<br/>"
        f"<b>IFSC</b> {spec['ifsc']}<br/>"
        f"<b>MICR</b> {spec['micr']}<br/>"
        f"<b>Branch</b> {spec['branch']}"
    )
    right = (
        f"<b>Statement of Account</b><br/>{spec['period']}<br/><br/>"
        f"<b>Account type</b> {spec['ac_type']}<br/>"
        f"<b>Nomination</b> Registered<br/>"
        f"<b>Opening balance</b> {inr(opening)}<br/>"
        f"<b>Closing balance</b> {inr(closing)}<br/>"
        f"<b>Currency</b> INR"
    )
    info = Table(
        [[cell(left, s["box"]), cell(right, s["box"])]],
        colWidths=[95 * mm, 80 * mm],
    )
    info.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, accent),
                ("LINEAFTER", (0, 0), (0, 0), 0.3, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f6f3ea")),
            ]
        )
    )
    story.append(info)
    story.append(Spacer(1, 8))
    story.append(Paragraph(spec["disclaimer"], s["tiny"]))
    story.append(Spacer(1, 6))

    headers = spec["headers"]
    data = [[cell(h, s["th"]) for h in headers]]

    data.append(
        [
            cell("", s["tiny"]),
            cell("<b>B/F Opening Balance</b>", s["narr"]),
            cell("", s["tiny"]),
            cell("", s["tinyR"]),
            cell("", s["tinyR"]),
            cell(f"<b>{inr(opening)}</b>", s["tinyR"]),
        ]
    )

    page_rows = int(spec.get("page_rows") or 22)
    for index, row in enumerate(rows):
        debit = inr(row["debit"]) if row["debit"] else ""
        credit = inr(row["credit"]) if row["credit"] else ""
        data.append(
            [
                cell(f"{row['date']}<br/><font color='#777777'>{row['value_date']}</font>", s["tiny"]),
                cell(row["narration"], s["narr"]),
                cell(row.get("ref") or "", s["tiny"]),
                cell(debit, s["tinyR"]),
                cell(credit, s["tinyR"]),
                cell(inr(row["balance"]), s["tinyR"]),
            ]
        )
        if (index + 1) % page_rows == 0 and index + 1 < len(rows):
            story.append(_grid(data, accent))
            story.append(Paragraph("Continued on next page…", s["foot"]))
            story.append(PageBreak())
            story.append(Paragraph(f"{spec['bank_name']} — {spec['period']} (contd.)", s["h"]))
            story.append(Spacer(1, 4))
            data = [[cell(h, s["th"]) for h in headers]]

    data.append(
        [
            cell("", s["tiny"]),
            cell("<b>C/F Closing Balance</b>", s["narr"]),
            cell("", s["tiny"]),
            cell("", s["tinyR"]),
            cell("", s["tinyR"]),
            cell(f"<b>{inr(closing)}</b>", s["tinyR"]),
        ]
    )
    story.append(_grid(data, accent))
    story.append(Spacer(1, 8))

    summary = Table(
        [
            [
                cell(
                    f"<b>Summary</b><br/>Debits {spec['debit_count']} &nbsp;&nbsp; Credits {spec['credit_count']}<br/>"
                    f"Opening {inr(opening)} &nbsp; Closing {inr(closing)}",
                    s["box"],
                )
            ]
        ],
        colWidths=[175 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, accent),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f3ea")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(KeepTogether([summary, Spacer(1, 4), Paragraph(spec["end_note"], s["foot"])]))
    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)


def _grid(data, accent):
    table = Table(data, colWidths=[22 * mm, 78 * mm, 28 * mm, 16 * mm, 16 * mm, 18 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8c2b4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbf8f1")]),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    return table


HDFC_EVENTS = [
    {"date": "01/07/2026", "value_date": "01/07/2026", "ref": "UPI-3921847301", "debit": "2480.00", "credit": "", "narration": "UPI-ZOMATO LIMITED<br/>UPI/322184739201/Payment from Phone<br/>zomato@okicici"},
    {"date": "01/07/2026", "value_date": "01/07/2026", "ref": "UPI-3921848012", "debit": "186.50", "credit": "", "narration": "UPI-SWIGGY INSTAMART<br/>UPI/322190118833/instamart order"},
    {"date": "02/07/2026", "value_date": "02/07/2026", "ref": "NEFT N192260702", "debit": "", "credit": "185000.00", "narration": "NEFT CR-HDFC0000123-MEHTA EXPORTS PVT LTD<br/>INV/26-27/0144 EXPORT PROCEEDS"},
    {"date": "03/07/2026", "value_date": "03/07/2026", "ref": "CHQ 884421", "debit": "12500.00", "credit": "", "narration": "CHQ PAID 884421<br/>BHARAT PACKAGING WORKS<br/>Towards corrugated boxes"},
    {"date": "04/07/2026", "value_date": "04/07/2026", "ref": "POS 441029", "debit": "7340.00", "credit": "", "narration": "POS 441029XXXX8812 RELIANCE TRENDS INDIRANAGAR<br/>TID 88291033"},
    {"date": "06/07/2026", "value_date": "06/07/2026", "ref": "IMPS 6071844", "debit": "", "credit": "25000.00", "narration": "IMPS-P2A-607184492211-RAVI SHANKAR<br/>ADVANCE AGAINST PO 441"},
    {"date": "07/07/2026", "value_date": "07/07/2026", "ref": "ACH 229100", "debit": "18420.75", "credit": "", "narration": "ACH D-BAJAJ FINANCE EMI<br/>LAN XJ229100883 Loan EMI Jul-26"},
    {"date": "08/07/2026", "value_date": "08/07/2026", "ref": "GST 290726", "debit": "3120.00", "credit": "", "narration": "GST @18% ON CHARGES<br/>CGST/SGST recovered by bank"},
    {"date": "09/07/2026", "value_date": "09/07/2026", "ref": "UPI-4011882", "debit": "540.00", "credit": "", "narration": "UPI-INDIAN OIL PETROL<br/>UPI/4011882291/fuel"},
    {"date": "11/07/2026", "value_date": "11/07/2026", "ref": "RTGS UTIBH261", "debit": "", "credit": "96000.00", "narration": "RTGS CR-UTIB0000234-SOUTH INDIA SPICES<br/>PART PYMT AGAINST PI 88"},
    {"date": "12/07/2026", "value_date": "13/07/2026", "ref": "E-COLL 712", "debit": "", "credit": "14800.00", "narration": "E-COLL RAZORPAY<br/>SETTLEMENT RZP_BATCH_712339"},
    {"date": "14/07/2026", "value_date": "14/07/2026", "ref": "ATM 5521", "debit": "10000.00", "credit": "", "narration": "ATW-552189-HDFC INDIRANAGAR<br/>CASH WITHDRAWAL"},
    {"date": "16/07/2026", "value_date": "16/07/2026", "ref": "SAL JUL26", "debit": "86400.00", "credit": "", "narration": "SALARY BULK UPLOAD JUL26<br/>STAFF SALARY / TDS SEPARATE"},
    {"date": "18/07/2026", "value_date": "18/07/2026", "ref": "UPI-4182001", "debit": "2199.00", "credit": "", "narration": "UPI-AIRTEL THANKS<br/>UPI/4182001882/postpaid"},
    {"date": "21/07/2026", "value_date": "21/07/2026", "ref": "NEFT N192260721", "debit": "47500.00", "credit": "", "narration": "NEFT DR-ICIC0000456-LAKSHMI PRINTERS<br/>INV LP/452 COLOUR JOBWORK"},
    {"date": "24/07/2026", "value_date": "24/07/2026", "ref": "INT 0726", "debit": "", "credit": "412.88", "narration": "CREDIT INTEREST<br/>SB INT FOR 01-04-2026 TO 30-06-2026"},
    {"date": "28/07/2026", "value_date": "28/07/2026", "ref": "CHQ 884422", "debit": "32000.00", "credit": "", "narration": "CHQ PAID 884422<br/>MUNICIPAL PROPERTY TAX BBMP"},
    {"date": "30/07/2026", "value_date": "30/07/2026", "ref": "UPI-4309912", "debit": "75.00", "credit": "", "narration": "UPI-BMTC SMART CARD<br/>UPI/4309912881/topup"},
]

ICICI_EVENTS = [
    {"date": "01/07/26", "value_date": "01/07/26", "ref": "INF/NEFT/0031", "debit": "", "credit": "72000.00", "narration": "NEFT-ORIX LEASING-RENT REFUND<br/>UTR ICICN202607011188"},
    {"date": "02/07/26", "value_date": "02/07/26", "ref": "BIL/001821", "debit": "899.00", "credit": "", "narration": "BIL/ONL/ICICI PRUDENTIAL<br/>SIP FOLIO 2291883"},
    {"date": "03/07/26", "value_date": "03/07/26", "ref": "UPI/329100", "debit": "1560.00", "credit": "", "narration": "UPI/yespay@ybl/BIGBASKET<br/>Order BB77821 / 2 shipments"},
    {"date": "05/07/26", "value_date": "05/07/26", "ref": "ACH/LIC", "debit": "6248.00", "credit": "", "narration": "ACH-DR LIC OF INDIA<br/>POLICY 442198833 PREMIUM"},
    {"date": "06/07/26", "value_date": "06/07/26", "ref": "MMT/IMPS", "debit": "", "credit": "18500.00", "narration": "MMT/IMPS/6182001992/ANITA MEHTA<br/>TRANSFER FROM MOTHER"},
    {"date": "08/07/26", "value_date": "08/07/26", "ref": "ATM/WDL", "debit": "8000.00", "credit": "", "narration": "ATM/CASH WDL/ICICI KORAMANGALA 4TH BLOCK<br/>ATM ID IKM044"},
    {"date": "10/07/26", "value_date": "10/07/26", "ref": "VIN/001192", "debit": "21450.00", "credit": "", "narration": "VIN/DEBIT CARD INTL<br/>AMAZON.COM SEATTLE USD 248.10"},
    {"date": "12/07/26", "value_date": "13/07/26", "ref": "ECOL/RZP", "debit": "", "credit": "33640.20", "narration": "ECOLLECT RAZORPAY<br/>MID IZXY2291 / 14 txns"},
    {"date": "15/07/26", "value_date": "15/07/26", "ref": "SAL/JUL", "debit": "", "credit": "92000.00", "narration": "NEFT-PRISM ANALYTICS PVT LTD<br/>JUL SALARY / EMP 24MIFB03"},
    {"date": "17/07/26", "value_date": "17/07/26", "ref": "UPI/441002", "debit": "349.00", "credit": "", "narration": "UPI/paytm-netflix@paytm<br/>NETFLIX.COM"},
    {"date": "19/07/26", "value_date": "19/07/26", "ref": "CHQ/229188", "debit": "15000.00", "credit": "", "narration": "CHQ DEP RET - 229188<br/>FUNDS INSUFFICIENT / RETURN CHG NEXT"},
    {"date": "19/07/26", "value_date": "19/07/26", "ref": "CHG/RET", "debit": "177.00", "credit": "", "narration": "CHQ RETURN CHARGES + GST<br/>CGST 13.50 SGST 13.50"},
    {"date": "22/07/26", "value_date": "22/07/26", "ref": "RTGS/SBIN", "debit": "50000.00", "credit": "", "narration": "RTGS DR SBIN0000456<br/>LAKSHMI TRADERS / ADVANCE"},
    {"date": "25/07/26", "value_date": "25/07/26", "ref": "INT/Q1", "debit": "", "credit": "208.40", "narration": "INTEREST CREDIT Q1<br/>TDS NOT DEDUCTED"},
    {"date": "29/07/26", "value_date": "29/07/26", "ref": "UPI/452991", "debit": "420.00", "credit": "", "narration": "UPI/bharatpe.kanti@fbl<br/>KANTI SWEETS INDIRANAGAR"},
]

SBI_EVENTS = [
    {"date": "01-07-2026", "value_date": "01-07-2026", "ref": "000000", "debit": "", "credit": "", "narration": "BY TRANSFER<br/>OPENING BROUGHT FORWARD DETAIL"},
    {"date": "02-07-2026", "value_date": "02-07-2026", "ref": "CTRANSFER", "debit": "", "credit": "54000.00", "narration": "BY TRANSFER-INB<br/>NEFT*SBIN326183*KIRAN AGENCIES*INV 19"},
    {"date": "03-07-2026", "value_date": "03-07-2026", "ref": "ATM WDL", "debit": "5000.00", "credit": "", "narration": "ATM WDL-ATM S1DX1234<br/>SBI INDIRANAGAR 12TH MAIN"},
    {"date": "04-07-2026", "value_date": "04-07-2026", "ref": "UPI", "debit": "799.00", "credit": "", "narration": "DEBIT-UPI/DR/4321882991<br/>/JIO PREPAID / jio@paytm"},
    {"date": "06-07-2026", "value_date": "06-07-2026", "ref": "ACH", "debit": "2210.00", "credit": "", "narration": "TO TRANSFER<br/>ACH DR NACH HDFC BANK CREDIT CARD"},
    {"date": "08-07-2026", "value_date": "08-07-2026", "ref": "CASH DEP", "debit": "", "credit": "15000.00", "narration": "CASH DEPOSIT-CDM<br/>SBI CDM 2291 / DENOM MIXED"},
    {"date": "10-07-2026", "value_date": "10-07-2026", "ref": "CHQ 001192", "debit": "8750.00", "credit": "", "narration": "CHEQUE WDL-001192<br/>SELF / BEARER"},
    {"date": "13-07-2026", "value_date": "13-07-2026", "ref": "INB", "debit": "32000.00", "credit": "", "narration": "TO TRANSFER-INB<br/>RTGS*ICIC0000781*SHREE STEELS*ADV"},
    {"date": "15-07-2026", "value_date": "15-07-2026", "ref": "SAL", "debit": "", "credit": "41000.00", "narration": "BY TRANSFER<br/>NEFT*HDFC0001234*MEHTA TRADING*CONSULT"},
    {"date": "18-07-2026", "value_date": "18-07-2026", "ref": "UPI", "debit": "145.00", "credit": "", "narration": "DEBIT-UPI/DR/4412001882<br/>/BMTC TICKET"},
    {"date": "21-07-2026", "value_date": "21-07-2026", "ref": "POS", "debit": "2680.00", "credit": "", "narration": "DEBIT-POS/429188XXXX0012<br/>MORE SUPERMARKET HAL 2ND STAGE"},
    {"date": "24-07-2026", "value_date": "24-07-2026", "ref": "INT", "debit": "", "credit": "156.25", "narration": "CREDIT INTEREST<br/>FOR THE PERIOD 01.04.2026 TO 30.06.2026"},
    {"date": "27-07-2026", "value_date": "27-07-2026", "ref": "GST", "debit": "118.00", "credit": "", "narration": "SMS ALERT CHG + GST<br/>APR-JUN 2026"},
    {"date": "30-07-2026", "value_date": "30-07-2026", "ref": "UPI", "debit": "60.00", "credit": "", "narration": "DEBIT-UPI/DR/4521001993<br/>/DARSHINI COFFEE"},
]


def specs() -> list[dict]:
    hdfc_rows = apply(Decimal("248320.55"), [e for e in HDFC_EVENTS])
    icici_rows = apply(Decimal("61240.10"), ICICI_EVENTS)
    sbi_open = Decimal("38750.00")
    sbi_events = [e for e in SBI_EVENTS if e["debit"] or e["credit"]]
    sbi_rows = apply(sbi_open, sbi_events)
    return [
        {
            "file": "HDFC_MehtaTrading_Jul2026_complex.pdf",
            "bank_name": "HDFC Bank Limited",
            "tagline": "Retail Assets · Bengaluru Metro · Statement of Account",
            "banner": "HDFC BANK  |  Confidential  |  For the account holder only",
            "footer_id": "CIF 229184403 · Statement  ST/SA/072026/8812",
            "accent": "#004C8F",
            "title": "HDFC fictional statement Jul 2026",
            "customer": "MEHTA TRADING CO",
            "address": "14, 12th Main, HAL 2nd Stage<br/>Indiranagar, Bengaluru 560038",
            "cust_id": "229184403",
            "account": "50100291844762",
            "ifsc": "HDFC0001234",
            "micr": "560240029",
            "branch": "Indiranagar, Bengaluru",
            "period": "01 Jul 2026 to 31 Jul 2026",
            "ac_type": "Current Account — Regular",
            "disclaimer": "This is a computer generated fictional statement built to stress-test table extraction. Names, IFSC and amounts are invented. Do not treat as a real HDFC document.",
            "headers": ["Txn Date / Value", "Narration", "Chq / Ref No.", "Withdrawal (Dr)", "Deposit (Cr)", "Closing Balance"],
            "opening": "248320.55",
            "events": HDFC_EVENTS,
            "debit_count": sum(1 for r in hdfc_rows if r["debit"]),
            "credit_count": sum(1 for r in hdfc_rows if r["credit"]),
            "end_note": "End of statement. Please verify closing balance  within 30 days. For queries quote CIF 229184403.",
        },
        {
            "file": "ICICI_AnitaMehta_Jul2026_complex.pdf",
            "bank_name": "ICICI Bank",
            "tagline": "Digital Savings · Relationship ID 884219",
            "banner": "ICICI Bank  |  e-Statement  |  Password was not applied (test file)",
            "footer_id": "Rel ID 884219 · ESTMT/SAV/072026",
            "accent": "#B85C38",
            "title": "ICICI fictional statement Jul 2026",
            "customer": "ANITA R MEHTA",
            "address": "Apt 4B, Palm Grove<br/>Koramangala 4th Block, Bengaluru 560034",
            "cust_id": "8842193301",
            "account": "00040500991823",
            "ifsc": "ICIC0000456",
            "micr": "560229003",
            "branch": "Koramangala, Bengaluru",
            "period": "01/07/2026 — 31/07/2026",
            "ac_type": "Salary Savings Account",
            "disclaimer": "Fictional ICICI-style e-statement. Two date formats, SIP, international POS and a returned cheque are intentional layout traps.",
            "headers": ["Date / Val Dt", "Transaction Remarks", "Reference", "Debit", "Credit", "Balance"],
            "opening": "61240.10",
            "events": ICICI_EVENTS,
            "debit_count": sum(1 for r in icici_rows if r["debit"]),
            "credit_count": sum(1 for r in icici_rows if r["credit"]),
            "end_note": "This statement is system generated. No signature is required.",
        },
        {
            "file": "SBI_KiranAgencies_Jul2026_complex.pdf",
            "bank_name": "State Bank of India",
            "tagline": "खाता विवरण / Account Statement  ·  Branch Code 00456",
            "banner": "STATE BANK OF INDIA  |  CIN L65110MH1955GOI000038  |  Test specimen",
            "footer_id": "A/c 00000041299852314 · BR 00456",
            "accent": "#1B4F72",
            "title": "SBI fictional statement Jul 2026",
            "customer": "M/S KIRAN AGENCIES",
            "address": "Shop 7, Russell Market Road<br/>Shivajinagar, Bengaluru 560051",
            "cust_id": "SBI-7721844",
            "account": "41299852314",
            "ifsc": "SBIN0000456",
            "micr": "560002056",
            "branch": "Shivajinagar, Bengaluru",
            "period": "01-07-2026 to 31-07-2026",
            "ac_type": "CA — Current Account",
            "disclaimer": "SBI-style layout with hyphen dates, BY TRANSFER / TO TRANSFER wording, and a dummy opening row with no amount. All figures invented.",
            "headers": ["Txn Date / Val", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"],
            "opening": "38750.00",
            "events": sbi_events,
            "debit_count": sum(1 for r in sbi_rows if r["debit"]),
            "credit_count": sum(1 for r in sbi_rows if r["credit"]),
            "end_note": "**** END OF STATEMENT ****   Please contact branch 00456 for discrepancy.",
        },
    ]


def main() -> None:
    if OUT.exists():
        for child in OUT.glob("*.pdf"):
            child.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    for spec in specs():
        statement(OUT / spec["file"], spec)
        print("wrote", spec["file"])


if __name__ == "__main__":
    main()
