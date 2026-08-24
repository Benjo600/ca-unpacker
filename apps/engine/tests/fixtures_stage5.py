from __future__ import annotations

from pathlib import Path

GOOD_GSTIN = "27AAPFU0939F1ZV"
# Valid shape, last character flipped. Prefer 27AAPFU0939F1ZZ when that checksum fails.
BAD_GSTIN = "27AAPFU0939F1ZZ"
BAD_HSN = "12345"
GOOD_INVOICE_NO = "GEN/26-27/0101"
BAD_GSTIN_INVOICE_NO = "BADGST/26-27/0001"
BAD_HSN_INVOICE_NO = "BADHSN/26-27/0002"


def _pdf_with_text(lines: list[str]) -> bytes:
    from make_test_dump import pdf_with_text

    return pdf_with_text(lines)


def _tiny_png() -> bytes:
    from make_test_dump import PNG

    return PNG


def invoice_lines(
    *,
    invoice_no: str,
    gstin: str = GOOD_GSTIN,
    hsn: str = "998314",
    date: str = "15/07/2026",
    taxable: str = "20000.00",
    cgst: str = "1800.00",
    sgst: str = "1800.00",
    total: str = "23600.00",
) -> list[str]:
    return [
        "TAX INVOICE",
        f"Invoice No {invoice_no}",
        f"Invoice Date {date}",
        f"Supplier GSTIN {gstin}",
        "Place of Supply 27-Maharashtra",
        f"HSN {hsn}",
        "HSN Qty Rate Taxable Amount",
        f"Professional fees {hsn} 1 {taxable} {taxable} {total}",
        f"Taxable value {taxable}",
        f"CGST {cgst}  SGST {sgst}",
        f"Invoice value {total}",
    ]


def write_invoice_pdf(dest: Path, lines: list[str]) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_pdf_with_text(lines))
    return dest


def copy_acme_invoice(folder: Path) -> Path:
    dest = Path(folder) / "Tax_Invoice_Acme.pdf"
    return write_invoice_pdf(
        dest,
        invoice_lines(
            invoice_no="ACME/26-27/0142",
            date="12/07/2026",
            taxable="10000.00",
            cgst="900.00",
            sgst="900.00",
            total="11800.00",
        ),
    )


def write_generated_invoice(folder: Path) -> Path:
    return write_invoice_pdf(Path(folder) / "Tax_Invoice_Generated.pdf", invoice_lines(invoice_no=GOOD_INVOICE_NO))


def write_bad_gstin_invoice(folder: Path) -> Path:
    return write_invoice_pdf(
        Path(folder) / "Tax_Invoice_BadGSTIN.pdf",
        invoice_lines(invoice_no=BAD_GSTIN_INVOICE_NO, gstin=BAD_GSTIN),
    )


def write_bad_hsn_invoice(folder: Path) -> Path:
    return write_invoice_pdf(
        Path(folder) / "Tax_Invoice_BadHSN.pdf",
        invoice_lines(invoice_no=BAD_HSN_INVOICE_NO, hsn=BAD_HSN),
    )


def write_tiny_png(folder: Path, name: str = "tiny.png") -> Path:
    dest = Path(folder) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_tiny_png())
    return dest


def write_bills_folder(folder: Path) -> dict[str, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return {
        "acme": copy_acme_invoice(folder),
        "generated": write_generated_invoice(folder),
        "bad_gstin": write_bad_gstin_invoice(folder),
        "bad_hsn": write_bad_hsn_invoice(folder),
        "tiny_png": write_tiny_png(folder, "invoice_photo.png"),
        "tiny_unknown": write_tiny_png(folder, "tiny.png"),
    }
