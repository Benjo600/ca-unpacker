from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from make_complex_statements import apply, statement

OUT = Path(__file__).resolve().parent / "test-dump" / "long-statements"

UPI = (
    "ZOMATO LIMITED",
    "SWIGGY",
    "BIGBASKET",
    "IRCTC RAIL",
    "INDIAN OIL",
    "AIRTEL THANKS",
    "JIO PREPAID",
    "BMTC SMART",
    "NETFLIX.COM",
    "PHONEPE STORE",
)
VENDORS = (
    "LAKSHMI PRINTERS",
    "BHARAT PACKAGING",
    "SHREE STEELS",
    "SOUTH INDIA SPICES",
    "MEHTA EXPORTS",
    "KIRAN AGENCIES",
    "ORIX LEASING",
    "PRISM ANALYTICS",
)
TEMPLATES = (
    ("upi", "UPI-{who}<br/>UPI/{ref}/Payment from Phone", True, "48.00", "3200.00"),
    ("neft_in", "NEFT CR-{who}<br/>INV/{ref} AGAINST SUPPLY", False, "8000.00", "95000.00"),
    ("neft_out", "NEFT DR-{who}<br/>JOBWORK / {ref}", True, "3500.00", "48000.00"),
    ("imps", "IMPS-P2A-{ref}-{who}<br/>ADVANCE / PART PAY", False, "5000.00", "28000.00"),
    ("pos", "POS XXXX8812 {who}<br/>TID {ref}", True, "220.00", "8900.00"),
    ("atm", "ATW CASH WITHDRAWAL<br/>{who} ATM {ref}", True, "2000.00", "10000.00"),
    ("ach", "ACH D-{who}<br/>EMI / NACH {ref}", True, "1800.00", "22000.00"),
    ("int", "CREDIT INTEREST<br/>SB INT SLAB {ref}", False, "12.00", "480.00"),
)


def _amt(seed: int, low: str, high: str) -> Decimal:
    lo = Decimal(low)
    hi = Decimal(high)
    span = int((hi - lo) * 100)
    return (lo + Decimal((seed % max(span, 1)) / 100)).quantize(Decimal("0.01"))


def build_events(count: int, date_style: str, seed: int = 17) -> list[dict]:
    events: list[dict] = []
    n = 0
    day = 1
    while len(events) < count:
        kind, template, is_debit, low, high = TEMPLATES[n % len(TEMPLATES)]
        if kind == "int" and day not in {10, 20, 30}:
            n += 1
            continue
        who = (UPI if kind == "upi" else VENDORS)[(n + seed) % len(UPI if kind == "upi" else VENDORS)]
        ref = f"{800000 + n * 17 + seed}"
        amount = _amt(n * 31 + seed, low, high)
        if date_style == "hyphen":
            date = f"{day:02d}-07-2026"
        elif date_style == "short":
            date = f"{day:02d}/07/26"
        else:
            date = f"{day:02d}/07/2026"
        wrap = n % 3 == 0
        narration = template.format(who=who, ref=ref)
        if wrap:
            narration += f"<br/>{who.lower().replace(' ', '')}@okaxis"
        events.append(
            {
                "date": date,
                "value_date": date,
                "ref": ref[:12],
                "debit": str(amount) if is_debit else "",
                "credit": "" if is_debit else str(amount),
                "narration": narration,
            }
        )
        n += 1
        if n % 5 == 0:
            day = min(31, day + 1)
    return events


def bank_spec(name: str, file: str, accent: str, customer: str, account: str, ifsc: str, opening: str, style: str, count: int, extra: dict) -> dict:
    events = build_events(count, style, seed=extra.get("seed", 11))
    rows = apply(Decimal(opening), events)
    return {
        "file": file,
        "bank_name": name,
        "tagline": extra["tagline"],
        "banner": extra["banner"],
        "footer_id": extra["footer"],
        "accent": accent,
        "title": file,
        "customer": customer,
        "address": extra["address"],
        "cust_id": extra["cust_id"],
        "account": account,
        "ifsc": ifsc,
        "micr": extra["micr"],
        "branch": extra["branch"],
        "period": "01 Jul 2026 to 31 Jul 2026",
        "ac_type": extra["ac_type"],
        "disclaimer": "Fictional long statement for prototype load testing. Not a real bank document.",
        "headers": extra["headers"],
        "opening": opening,
        "events": events,
        "debit_count": sum(1 for row in rows if row["debit"]),
        "credit_count": sum(1 for row in rows if row["credit"]),
        "end_note": f"**** END OF STATEMENT ****  {len(rows)} fictional lines. Closing {rows[-1]['balance']}.",
        "page_rows": 20,
    }


def main() -> None:
    if OUT.exists():
        for child in OUT.glob("*.pdf"):
            child.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    specs = [
        bank_spec(
            "HDFC Bank Limited",
            "HDFC_MehtaTrading_Jul2026_LONG.pdf",
            "#004C8F",
            "MEHTA TRADING CO",
            "50100291844762",
            "HDFC0001234",
            "248320.55",
            "slash",
            160,
            {
                "seed": 21,
                "tagline": "Current Account · long-form test specimen",
                "banner": "HDFC BANK  |  LONG TEST FILE  |  160 lines",
                "footer": "CIF 229184403 · LONG/072026",
                "address": "14, 12th Main, HAL 2nd Stage<br/>Indiranagar, Bengaluru 560038",
                "cust_id": "229184403",
                "micr": "560240029",
                "branch": "Indiranagar, Bengaluru",
                "ac_type": "Current Account — Regular",
                "headers": ["Txn Date / Value", "Narration", "Chq / Ref No.", "Withdrawal (Dr)", "Deposit (Cr)", "Closing Balance"],
            },
        ),
        bank_spec(
            "ICICI Bank",
            "ICICI_AnitaMehta_Jul2026_LONG.pdf",
            "#B85C38",
            "ANITA R MEHTA",
            "00040500991823",
            "ICIC0000456",
            "61240.10",
            "short",
            140,
            {
                "seed": 44,
                "tagline": "Salary Savings · long e-statement test",
                "banner": "ICICI Bank  |  LONG TEST FILE  |  140 lines",
                "footer": "Rel 884219 · LONG/SAV/072026",
                "address": "Apt 4B, Palm Grove<br/>Koramangala 4th Block, Bengaluru 560034",
                "cust_id": "8842193301",
                "micr": "560229003",
                "branch": "Koramangala, Bengaluru",
                "ac_type": "Salary Savings Account",
                "headers": ["Date / Val Dt", "Transaction Remarks", "Reference", "Debit", "Credit", "Balance"],
            },
        ),
        bank_spec(
            "State Bank of India",
            "SBI_KiranAgencies_Jul2026_LONG.pdf",
            "#1B4F72",
            "M/S KIRAN AGENCIES",
            "41299852314",
            "SBIN0000456",
            "38750.00",
            "hyphen",
            130,
            {
                "seed": 73,
                "tagline": "खाता विवरण / long current-account test",
                "banner": "STATE BANK OF INDIA  |  LONG TEST FILE  |  130 lines",
                "footer": "A/c 41299852314 · BR 00456",
                "address": "Shop 7, Russell Market Road<br/>Shivajinagar, Bengaluru 560051",
                "cust_id": "SBI-7721844",
                "micr": "560002056",
                "branch": "Shivajinagar, Bengaluru",
                "ac_type": "CA — Current Account",
                "headers": ["Txn Date / Val", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"],
            },
        ),
        bank_spec(
            "Axis Bank",
            "AXIS_SouthSpices_Jul2026_LONG.pdf",
            "#8E1B23",
            "SOUTH INDIA SPICES",
            "922010012345678",
            "UTIB0000234",
            "90500.00",
            "slash",
            120,
            {
                "seed": 9,
                "tagline": "Business Advantage · long test specimen",
                "banner": "AXIS BANK  |  LONG TEST FILE  |  120 lines",
                "footer": "Cust 441209 · LONG/CA/072026",
                "address": "42, Commercial Street<br/>Bengaluru 560001",
                "cust_id": "44120988",
                "micr": "560211002",
                "branch": "Commercial Street, Bengaluru",
                "ac_type": "Current Account",
                "headers": ["Tran Date", "Particulars", "Chq No", "Withdrawal", "Deposit", "Balance"],
            },
        ),
    ]
    for spec in specs:
        statement(OUT / spec["file"], spec)
        print("wrote", spec["file"], spec["debit_count"] + spec["credit_count"], "lines")


if __name__ == "__main__":
    main()
