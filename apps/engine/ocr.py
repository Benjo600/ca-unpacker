from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from apps.engine.pdf_extract import ExtractedPdf, LineBox, PageText

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIN_WORD_CONF = 40.0
_RENDER_SCALE = 2.0


def _frozen_roots() -> list[Path]:
    import sys

    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
    return roots


def find_tesseract() -> Path | None:
    """Search local tesseract.exe locations. First existing hit wins."""
    env = os.environ.get("CAUNPACKER_TESSERACT")
    if env:
        env_path = Path(env)
        if env_path.is_file():
            return env_path
        nested = env_path / "tesseract.exe"
        if nested.is_file():
            return nested

    local = os.environ.get("LOCALAPPDATA")
    candidates = []
    for root in _frozen_roots():
        candidates.append(root / "tesseract" / "tesseract.exe")
        candidates.append(root / "tesseract.exe")
    if local:
        candidates.append(Path(local) / "CAUnpacker" / "tesseract" / "tesseract.exe")
    # Tests override LOCALAPPDATA; still look at the real user library.
    candidates.append(Path.home() / "AppData" / "Local" / "CAUnpacker" / "tesseract" / "tesseract.exe")
    candidates.extend(
        [
            _REPO_ROOT / "third_party" / "tesseract" / "tesseract.exe",
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    which = shutil.which("tesseract")
    if which:
        found = Path(which)
        if found.is_file():
            return found
    return None


def tesseract_status() -> dict:
    """{found: bool, path: str|None, note: str} — never raises, never downloads."""
    exe = find_tesseract()
    if exe is None:
        return {
            "found": False,
            "path": None,
            "note": (
                "Tesseract not found. Set CAUNPACKER_TESSERACT, or place tesseract.exe "
                "under %LOCALAPPDATA%\\CAUnpacker\\tesseract\\ or "
                "third_party\\tesseract\\. No cloud OCR is used."
            ),
        }
    return {
        "found": True,
        "path": str(exe),
        "note": f"Local Tesseract at {exe}. Images stay on this PC; no cloud OCR.",
    }


def ocr_image_lines(
    image_path: Path,
    page: int,
    page_width_pts: float,
    page_height_pts: float,
    scale: float,
) -> list[LineBox]:
    """OCR a page image. Pixel boxes (top-left) become PDF user-space LineBoxes."""
    exe = find_tesseract()
    if exe is None:
        return []
    try:
        import pytesseract
    except ImportError:
        return []

    pytesseract.pytesseract.tesseract_cmd = str(exe)
    tessdata = exe.parent / "tessdata"
    if tessdata.is_dir():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
    try:
        data = pytesseract.image_to_data(str(image_path), output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    words: list[tuple[float, float, float, float, str]] = []
    n = len(data.get("text") or [])
    for index in range(n):
        if data.get("level") is not None:
            try:
                if int(data["level"][index]) != 5:
                    continue
            except (TypeError, ValueError):
                pass
        text = (data["text"][index] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][index])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < _MIN_WORD_CONF:
            continue
        left = float(data["left"][index])
        top = float(data["top"][index])
        width_px = float(data["width"][index])
        height_px = float(data["height"][index])
        if width_px <= 0 or height_px <= 0 or scale <= 0:
            continue
        x = left / scale
        width = width_px / scale
        height = height_px / scale
        y = page_height_pts - (top + height_px) / scale
        words.append((x, y, width, height, text))

    words.sort(key=lambda item: (-(item[1] + item[3] / 2.0), item[0]))
    bands: list[list[tuple[float, float, float, float, str]]] = []
    for word in words:
        placed = False
        for band in bands:
            if abs(word[1] - band[0][1]) <= max(3.0, word[3] * 0.6):
                band.append(word)
                placed = True
                break
        if not placed:
            bands.append([word])

    page_no = page + 1 if page <= 0 else page
    lines: list[LineBox] = []
    for band in bands:
        band.sort(key=lambda item: item[0])
        text = " ".join(item[4] for item in band)
        xs = [item[0] for item in band]
        ys = [item[1] for item in band]
        rights = [item[0] + item[2] for item in band]
        tops = [item[1] + item[3] for item in band]
        lines.append(
            LineBox(
                page=page_no,
                text=text,
                x=min(xs),
                y=min(ys),
                width=max(rights) - min(xs),
                height=max(tops) - min(ys),
            )
        )
    return lines


def extract_image(path: Path) -> ExtractedPdf:
    """OCR a raster invoice. page size in points = pixel size, scale=1.
    LineBoxes must use the same bottom-left PDF space as ocr_image_lines.
    If tesseract missing, return empty lines, engine='none'.
    """
    path = Path(path)
    if find_tesseract() is None:
        return ExtractedPdf(pdf_type="image_based", page_count=1, engine="none")

    width_pts, height_pts = _image_size_pts(path)
    if width_pts <= 0 or height_pts <= 0:
        return ExtractedPdf(pdf_type="image_based", page_count=1, engine="tesseract")

    lines = ocr_image_lines(path, 1, width_pts, height_pts, 1.0)
    text = "\n".join(line.text for line in lines)
    return ExtractedPdf(
        pdf_type="image_based",
        page_count=1,
        pages=[PageText(page=1, text=text, needs_ocr=False)],
        lines=lines,
        engine="tesseract",
    )


def _image_size_pts(path: Path) -> tuple[float, float]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.load()
            return float(image.width), float(image.height)
    except Exception:
        return 0.0, 0.0


def ocr_pdf(path: Path, password: str | None = None) -> ExtractedPdf:
    """Render each page locally and OCR with Tesseract. Never uploads."""
    page_count = _pdf_page_count(path, password)
    empty = ExtractedPdf(pdf_type="scanned", page_count=page_count, engine="none")
    if find_tesseract() is None:
        return empty
    try:
        import pypdfium2
    except ImportError:
        return empty

    try:
        document = pypdfium2.PdfDocument(str(path), password=password or None)
    except Exception:
        return empty

    lines: list[LineBox] = []
    pages: list[PageText] = []
    try:
        with tempfile.TemporaryDirectory(prefix="caunpacker_ocr_") as tmp:
            tmp_dir = Path(tmp)
            for index in range(len(document)):
                page = document[index]
                page_no = index + 1
                try:
                    width = float(page.get_width())
                    height = float(page.get_height())
                    bitmap = page.render(scale=_RENDER_SCALE)
                    try:
                        image = bitmap.to_pil()
                        if image.mode not in {"RGB", "L"}:
                            image = image.convert("RGB")
                        png_path = tmp_dir / f"page-{page_no}.png"
                        image.save(png_path, "PNG")
                    finally:
                        bitmap.close()
                    page_lines = ocr_image_lines(
                        png_path, page_no, width, height, _RENDER_SCALE
                    )
                except Exception:
                    page_lines = []
                finally:
                    page.close()
                lines.extend(page_lines)
                pages.append(
                    PageText(
                        page=page_no,
                        text="\n".join(line.text for line in page_lines),
                        needs_ocr=False,
                    )
                )
    finally:
        document.close()

    return ExtractedPdf(
        pdf_type="scanned",
        page_count=len(pages) or page_count,
        pages=pages,
        lines=lines,
        engine="tesseract",
    )


def _pdf_page_count(path: Path, password: str | None) -> int:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and password:
            reader.decrypt(password)
        return len(reader.pages)
    except Exception:
        pass
    try:
        import pypdfium2

        document = pypdfium2.PdfDocument(str(path), password=password or None)
        try:
            return len(document)
        finally:
            document.close()
    except Exception:
        return 0
