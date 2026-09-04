from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from apps.engine.pdf_extract import ExtractedPdf, LineBox, PageText, WordBox

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIN_WORD_CONF = 40.0
_RENDER_SCALE = 2.0
_rapidocr_singleton = None


def _rapidocr_engine():
    global _rapidocr_singleton
    if _rapidocr_singleton is False:
        return None
    if _rapidocr_singleton is not None:
        return _rapidocr_singleton
    try:
        from rapidocr import RapidOCR

        _rapidocr_singleton = RapidOCR()
    except Exception:
        _rapidocr_singleton = False
        return None
    return _rapidocr_singleton


def ocr_available() -> bool:
    return _rapidocr_engine() is not None or find_tesseract() is not None


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
    lines, _, _ = ocr_image_page(image_path, page, page_width_pts, page_height_pts, scale)
    return lines


def ocr_image_page(
    image_path: Path,
    page: int,
    page_width_pts: float,
    page_height_pts: float,
    scale: float,
) -> tuple[list[LineBox], list[WordBox], str]:
    words, engine = _rapidocr_words(image_path, page_width_pts, page_height_pts, scale)
    if not words:
        words, engine = _tesseract_words(image_path, page_width_pts, page_height_pts, scale)
    page_no = page + 1 if page <= 0 else page
    lines = _lines_from_words(words, page_no)
    boxes = [
        WordBox(page=page_no, text=item[4], x=item[0], y=item[1], width=item[2], height=item[3])
        for item in words
    ]
    return lines, boxes, engine


def _rapidocr_words(
    image_path: Path, page_width_pts: float, page_height_pts: float, scale: float
) -> tuple[list[tuple[float, float, float, float, str]], str]:
    engine = _rapidocr_engine()
    if engine is None or scale <= 0:
        return [], "none"
    try:
        result = engine(str(image_path))
    except Exception:
        return [], "none"
    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if boxes is None or txts is None:
        return [], "none"
    words: list[tuple[float, float, float, float, str]] = []
    for index, text in enumerate(txts):
        token = (text or "").strip()
        if not token:
            continue
        if scores is not None:
            try:
                if float(scores[index]) < 0.35:
                    continue
            except (TypeError, ValueError, IndexError):
                pass
        try:
            pts = boxes[index]
            xs = [float(pt[0]) for pt in pts]
            ys = [float(pt[1]) for pt in pts]
        except (TypeError, ValueError, IndexError):
            continue
        if not xs or not ys:
            continue
        left, top = min(xs), min(ys)
        right, bottom = max(xs), max(ys)
        width_px = right - left
        height_px = bottom - top
        if width_px <= 0 or height_px <= 0:
            continue
        x = left / scale
        width = width_px / scale
        height = height_px / scale
        y = page_height_pts - bottom / scale
        words.append((x, y, width, height, token))
    words.sort(key=lambda item: (-(item[1] + item[3] / 2.0), item[0]))
    return words, "rapidocr"


def _tesseract_words(
    image_path: Path, page_width_pts: float, page_height_pts: float, scale: float
) -> tuple[list[tuple[float, float, float, float, str]], str]:
    exe = find_tesseract()
    if exe is None:
        return [], "none"
    try:
        import pytesseract
    except ImportError:
        return [], "none"

    pytesseract.pytesseract.tesseract_cmd = str(exe)
    tessdata = exe.parent / "tessdata"
    if tessdata.is_dir():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
    try:
        data = pytesseract.image_to_data(str(image_path), output_type=pytesseract.Output.DICT)
    except Exception:
        return [], "none"

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
    return words, "tesseract"


def _lines_from_words(
    words: list[tuple[float, float, float, float, str]], page_no: int
) -> list[LineBox]:
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
    If no local OCR engine is present, return empty lines, engine='none'.
    """
    path = Path(path)
    if not ocr_available():
        return ExtractedPdf(pdf_type="image_based", page_count=1, engine="none")

    width_pts, height_pts = _image_size_pts(path)
    if width_pts <= 0 or height_pts <= 0:
        return ExtractedPdf(pdf_type="image_based", page_count=1, engine="none")

    lines, words, engine = ocr_image_page(path, 1, width_pts, height_pts, 1.0)
    text = "\n".join(line.text for line in lines)
    return ExtractedPdf(
        pdf_type="image_based",
        page_count=1,
        pages=[PageText(page=1, text=text, needs_ocr=False)],
        lines=lines,
        words=words,
        engine=engine if lines else "none",
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
    """Render each page locally and OCR. Never uploads. RapidOCR first, Tesseract fallback."""
    page_count = _pdf_page_count(path, password)
    empty = ExtractedPdf(pdf_type="scanned", page_count=page_count, engine="none")
    if not ocr_available():
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
    words: list[WordBox] = []
    pages: list[PageText] = []
    engine_name = "none"
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
                    page_lines, page_words, used = ocr_image_page(
                        png_path, page_no, width, height, _RENDER_SCALE
                    )
                    if used != "none":
                        engine_name = used
                except Exception:
                    page_lines = []
                    page_words = []
                finally:
                    page.close()
                lines.extend(page_lines)
                words.extend(page_words)
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
        words=words,
        engine=engine_name if lines else "none",
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
