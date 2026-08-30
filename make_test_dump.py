from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "test-dump"

# 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

# tiny JPEG
JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043000101010101010101"
    "010101010101010101010101010101010101010101010101010101010101010101"
    "01010101010101010101010101010101010101010101ffc0000b08000100010101"
    "1100ffc40014100100000000000000000000000000000000ffda00080001000100"
    "00023f10ffd9"
)


def pdf_with_text(lines: list[str]) -> bytes:
    content = "BT /F1 11 Tf 40 760 Td 14 TL\n"
    for i, line in enumerate(lines):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if i == 0:
            content += f"({safe}) Tj T*\n"
        else:
            content += f"({safe}) '\n"
    content += "ET\n"
    stream = content.encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n",
        f"4 0 obj<</Length {len(stream)}>>stream\n".encode("ascii") + stream + b"endstream\nendobj\n",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]
    body = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(body))
        body += obj
    xref_pos = len(body)
    xref = f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n"
    trailer = (
        f"trailer<</Size {len(objects)+1}/Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF\n"
    )
    return body + xref.encode("ascii") + trailer.encode("ascii")


def main() -> None:
    if ROOT.exists():
        for child in ROOT.iterdir():
            if child.is_file():
                child.unlink()
    ROOT.mkdir(exist_ok=True)

    (ROOT / "HDFC_Statement_Jul2026.pdf").write_bytes(
        pdf_with_text(
            [
                "HDFC Bank Account Statement",
                "Account Number 50100123456789",
                "IFSC HDFC0001234",
                "Opening Balance 150000.00",
                "01/07/2026 UPI merchant Withdrawal 2500.00 147500.00",
                "03/07/2026 NEFT INWARD Deposit 18000.00 165500.00",
                "05/07/2026 Cheque 112233 Withdrawal 1000.00 164500.00",
                "Closing Balance 164500.00",
            ]
        )
    )
    (ROOT / "ICICI_Statement_Jul2026.pdf").write_bytes(
        pdf_with_text(
            [
                "ICICI Bank Account Statement",
                "Account Number 000405001234",
                "IFSC ICIC0000004",
                "Opening Balance 80000.00",
                "02/07/2026 UPI Amazon Debit 1200.00 78800.00",
                "08/07/2026 Salary Credit 45000.00 123800.00",
                "Closing Balance 123800.00",
            ]
        )
    )
    (ROOT / "SBI_Statement_Jul2026.pdf").write_bytes(
        pdf_with_text(
            [
                "State Bank of India Account Statement",
                "Account Number 12345678901",
                "IFSC SBIN0000456",
                "Opening Balance 25000.00",
                "04/07/2026 ATM Withdrawal Debit 2000.00 23000.00",
                "11/07/2026 IMPS from client Credit 9000.00 32000.00",
                "Closing Balance 32000.00",
            ]
        )
    )

    (ROOT / "Tax_Invoice_Acme.pdf").write_bytes(
        pdf_with_text(
            [
                "TAX INVOICE",
                "Invoice No ACME/26-27/0142",
                "Invoice Date 12/07/2026",
                "Supplier GSTIN 27AAPFU0939F1ZV",
                "Place of Supply 29-Karnataka",
                "HSN 998314",
                "Taxable value 10000.00",
                "CGST 900.00  SGST 900.00",
                "Invoice value 11800.00",
            ]
        )
    )

    (ROOT / "GSTR-2B_July.json").write_text(
        json.dumps(
            {
                "gstin": "29ABCDE1234F1Z5",
                "rtnprd": "072026",
                "data": {
                    "docdata": {
                        "b2b": [
                            {
                                "ctin": "27AAPFU0939F1ZV",
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

    (ROOT / "GSTR1_July.json").write_text(
        json.dumps(
            {
                "gstin": "29ABCDE1234F1Z5",
                "fp": "072026",
                "b2b": [{"ctin": "27AAPFU0939F1ZV", "inv": [{"inum": "BN/101", "val": 5000}]}],
                "hsn": {"data": [{"hsn_sc": "9983", "txval": 5000}]},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (ROOT / "GSTR3B_July.json").write_text(
        json.dumps(
            {
                "gstin": "29ABCDE1234F1Z5",
                "ret_period": "072026",
                "sup_details": {"osup_det": {"txval": 50000, "iamt": 0, "camt": 4500, "samt": 4500}},
                "inward_sup": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    tally_xml = """<?xml version="1.0"?>
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
    (ROOT / "Tally_Daybook.xml").write_text(tally_xml, encoding="utf-8")
    with zipfile.ZipFile(ROOT / "Tally_Backup.zip", "w") as archive:
        archive.writestr("DAYBOOK.xml", tally_xml)

    (ROOT / "Zoho_Books_Invoices.csv").write_text(
        "Invoice Number,Invoice Date,GST Treatment,GST Identification Number (GSTIN),Item Tax %,Total\n"
        "INV-204,2026-07-08,taxable,27AAPFU0939F1ZV,18,5900\n",
        encoding="utf-8",
    )

    (ROOT / "invoice_photo.png").write_bytes(PNG)
    (ROOT / "random_scan.jpg").write_bytes(JPEG)
    (ROOT / "meeting_notes.docx").write_bytes(b"PK dummy office file, not a real invoice")

    print(f"Wrote {len(list(ROOT.iterdir()))} files in {ROOT}")


if __name__ == "__main__":
    main()
