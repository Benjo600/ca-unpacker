from __future__ import annotations

import math
import tempfile
from pathlib import Path


def page_size_pts(path: Path, page: int, password: str | None = None) -> tuple[float, float]:
    """Return (width, height) in PDF points. page is 1-based."""
    pdf = _open_pdf(path, password)
    try:
        pdf_page = _get_page(pdf, page)
        try:
            width, height = pdf_page.get_size()
        finally:
            pdf_page.close()
    finally:
        pdf.close()
    return float(width), float(height)


def render_page_png(
    path: Path,
    page: int,
    dest: Path,
    password: str | None = None,
    scale: float = 2.0,
) -> Path:
    """Render one page to dest PNG. Create parent dirs. Never upload. Local only."""
    image, _size = _render_page(path, page, password, scale)
    return _save_png(image, dest)


def crop_png(
    path: Path,
    page: int,
    bbox: str,
    dest: Path,
    password: str | None = None,
    scale: float = 2.0,
    pad: float = 8.0,
) -> Path:
    """Crop the bbox (PDF space) from the rendered page. Add pad points. Clamp to page.

    If bbox is empty/invalid, render a wider strip of that page (top third)
    so the UI still shows something.
    """
    image, page_size = _render_page(path, page, password, scale)
    box = _pixel_box(bbox, page_size, image.size, scale, pad)
    return _save_png(image.crop(box), dest)


def crop_png_bytes(
    path: Path,
    page: int,
    bbox: str,
    password: str | None = None,
    scale: float = 2.0,
    pad: float = 8.0,
) -> bytes:
    """Same as crop_png but return PNG bytes (for data URLs). May use a temp file."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "crop.png"
        crop_png(path, page, bbox, dest, password=password, scale=scale, pad=pad)
        return dest.read_bytes()


def crop_image_png(path: Path, bbox: str, dest: Path, pad: float = 8.0) -> Path:
    """Crop a raster using the PDF bbox contract. Image points == pixels (scale 1).

    Origin is bottom-left; pixel_top = height - (y + h). Invalid bbox → top third.
    """
    image = _open_raster(path)
    page_size = (float(image.width), float(image.height))
    box = _pixel_box(bbox, page_size, image.size, 1.0, pad)
    return _save_png(image.crop(box), dest)


def crop_image_png_bytes(path: Path, bbox: str, pad: float = 8.0) -> bytes:
    """Same as crop_image_png but return PNG bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "crop.png"
        crop_image_png(path, bbox, dest, pad=pad)
        return dest.read_bytes()


def _open_raster(path: Path):
    from PIL import Image

    with Image.open(path) as src:
        return src.convert("RGB")


def _open_pdf(path: Path, password: str | None = None):
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(str(path), password=password or None)
    except Exception as exc:
        if _is_password_failure(path, exc):
            if password:
                raise ValueError("That password did not open the PDF.") from None
            raise ValueError("This PDF needs a password.") from None
        raise


def _is_password_failure(path: Path, exc: BaseException) -> bool:
    err_code = getattr(exc, "err_code", None)
    try:
        import pypdfium2.raw as pdfium_c

        if err_code in {pdfium_c.FPDF_ERR_PASSWORD, pdfium_c.FPDF_ERR_SECURITY}:
            return True
    except Exception:
        pass
    text = str(exc).lower()
    if "password" in text or "encrypt" in text:
        return True
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
    except Exception:
        return False
    return bool(getattr(reader, "is_encrypted", False))


def _get_page(pdf, page: int):
    if page < 1 or page > len(pdf):
        raise ValueError("This PDF has no page %s." % page)
    return pdf[page - 1]


def _render_page(path: Path, page: int, password: str | None, scale: float):
    if scale <= 0:
        raise ValueError("scale must be greater than 0.")
    pdf = _open_pdf(path, password)
    try:
        pdf_page = _get_page(pdf, page)
        try:
            size = tuple(float(v) for v in pdf_page.get_size())
            bitmap = pdf_page.render(scale=scale)
            try:
                # Detach from the pdfium buffer before the bitmap/page is closed.
                image = bitmap.to_pil().convert("RGB").copy()
            finally:
                close = getattr(bitmap, "close", None)
                if callable(close):
                    close()
        finally:
            pdf_page.close()
    finally:
        pdf.close()
    return image, size


def _parse_bbox(bbox: str) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    text = str(bbox).strip()
    if not text:
        return None
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 4:
        return None
    try:
        x, y, width, height = (float(part) for part in parts)
    except ValueError:
        return None
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _pixel_box(
    bbox: str,
    page_size: tuple[float, float],
    image_size: tuple[int, int],
    scale: float,
    pad: float,
) -> tuple[int, int, int, int]:
    parsed = _parse_bbox(bbox)
    page_w, page_h = page_size
    img_w, img_h = image_size
    if parsed is None:
        return _top_third_box(img_w, img_h)
    x, y, width, height = parsed
    pad = max(0.0, float(pad))
    # PDF user space is bottom-left; the rendered bitmap is top-left.
    x0 = max(0.0, x - pad)
    y0 = max(0.0, y - pad)
    x1 = min(page_w, x + width + pad)
    y1 = min(page_h, y + height + pad)
    if x1 <= x0 or y1 <= y0:
        return _top_third_box(img_w, img_h)
    left = max(0, min(img_w, int(math.floor(x0 * scale))))
    right = max(0, min(img_w, int(math.ceil(x1 * scale))))
    top = max(0, min(img_h, int(math.floor((page_h - y1) * scale))))
    bottom = max(0, min(img_h, int(math.ceil((page_h - y0) * scale))))
    if right - left < 1 or bottom - top < 1:
        return _top_third_box(img_w, img_h)
    return left, top, right, bottom


def _top_third_box(img_w: int, img_h: int) -> tuple[int, int, int, int]:
    height = max(1, int(math.ceil(img_h / 3.0)))
    return 0, 0, max(1, img_w), min(img_h, height)


def _save_png(image, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG")
    return dest
