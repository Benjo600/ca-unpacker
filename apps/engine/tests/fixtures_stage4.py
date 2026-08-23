from __future__ import annotations

from io import BytesIO
from pathlib import Path


def make_password_pdf(src: Path, dest: Path, password: str) -> Path:
    """Copy *src* into an encrypted PDF at *dest* using pypdf Encryption."""
    from pypdf import PdfReader, PdfWriter
    from pypdf._encryption import Encryption  # noqa: F401 — required Stage 4 helper

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(src), strict=False)
    writer = PdfWriter()
    if getattr(reader, "is_encrypted", False):
        if reader.decrypt(password) == 0:
            raise ValueError("source PDF is encrypted with a different password")
    for page in reader.pages:
        writer.add_page(page)
    try:
        writer.encrypt(user_password=password, algorithm="AES-128")
    except (ValueError, NotImplementedError, TypeError):
        writer.encrypt(user_password=password)
    with dest.open("wb") as handle:
        writer.write(handle)
    return dest


def make_image_only_pdf(src: Path, dest: Path) -> Path:
    """Render page 1 of *src* to a bitmap and wrap it as an image-only PDF."""
    import pypdfium2 as pdfium

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(src))
    try:
        page = pdf[0]
        bitmap = page.render(scale=2)
        image = bitmap.to_pil().convert("RGB")
    finally:
        pdf.close()

    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    dest.write_bytes(_jpeg_only_pdf(buf.getvalue(), image.width, image.height))
    return dest


def _jpeg_only_pdf(jpeg: bytes, width: int, height: int) -> bytes:
    w, h = int(width), int(height)
    contents = f"q {w} 0 0 {h} 0 0 cm /Im0 Do Q\n".encode("ascii")
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        (
            f"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 {w} {h}]"
            f"/Resources<</XObject<</Im0 4 0 R>>>>/Contents 5 0 R>>endobj\n"
        ).encode("ascii"),
        (
            f"4 0 obj<</Type/XObject/Subtype/Image/Width {w}/Height {h}"
            f"/ColorSpace/DeviceRGB/BitsPerComponent 8/Filter/DCTDecode"
            f"/Length {len(jpeg)}>>stream\n"
        ).encode("ascii")
        + jpeg
        + b"\nendstream\nendobj\n",
        f"5 0 obj<</Length {len(contents)}>>stream\n".encode("ascii")
        + contents
        + b"endstream\nendobj\n",
    ]
    body = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(body))
        body += obj
    xref_pos = len(body)
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n"
    trailer = (
        f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    )
    return body + xref.encode("ascii") + trailer.encode("ascii")
