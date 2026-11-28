from __future__ import annotations

import copy
import os
import re
import shutil
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from apps.engine.imageprep import (
    assess as _assess_image,
    deskew as _deskew_image,
    resolution_scale as _resolution_scale,
    variant_sequence as _variant_sequence,
)
from apps.engine.pdf_extract import ExtractedPdf, LineBox, PageText, WordBox

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIN_WORD_CONF = 40.0
_MIN_RAPID_SCORE = 0.35
_RENDER_SCALE = 2.0
_RETRY_SCALE = 3.0
_MAX_OCR_IMAGE_SIDE = 4500
_MIN_OCR_IMAGE_SIDE = 1200
# OCR result quality targets used to decide whether a better variant or a
# higher-resolution retry is worth trying (Phase 3/4 quality selection).
_GOOD_ENOUGH_MEAN_CONF = 0.86
_rapidocr_singleton = None
_rapidocr_lock = threading.Lock()

# --- Image extraction cache -------------------------------------------------
# The classifier OCRs a raster to decide what it is, then the bank/invoice
# parser OCRs the very same file moments later.  Running the engine twice
# doubles the wall time of a scanned dump, so the last few image extractions
# are kept in memory, keyed on the file's identity (resolved path + mtime +
# size).  A replaced or re-imported file gets a different key, so cached text
# can never leak into a new file's parse.
_EXTRACTION_CACHE_LOCK = threading.Lock()
_EXTRACTION_CACHE: "OrderedDict[tuple[str, int, int], tuple[int, ExtractedPdf]]" = OrderedDict()
_EXTRACTION_CACHE_MAX_ENTRIES = 16
_EXTRACTION_CACHE_MAX_BYTES = 32 * 1024 * 1024
_extraction_cache_bytes = 0
# Rough per-object cost of a LineBox/WordBox dataclass (fields + __dict__).
_BOX_BYTES_ESTIMATE = 200


def _rapidocr_engine():
    global _rapidocr_singleton
    if _rapidocr_singleton is False:
        return None
    if _rapidocr_singleton is not None:
        return _rapidocr_singleton
    with _rapidocr_lock:
        # Re-check inside the lock: two threads can pass the fast path.
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
    """OCR one page image with preprocessing-variant selection.

    A small set of candidate preprocessing variants (original, contrast,
    denoise, local threshold) is OCR'd and the variant whose result carries
    the best *measured* recognition quality wins.  This is the controlled
    fallback from the scanning plan: no aggressive transform is applied
    blindly, and the winner is recorded.
    """
    from apps.engine.evidence import summarise_word_confidence

    best_words: list[tuple[float, float, float, float, str, float | None]] = []
    best_engine = "none"
    best_quality = -1.0
    best_variant = "original"

    def score(words: list[tuple[float, float, float, float, str, float | None]]) -> float:
        scores = [c for c in (item[5] for item in words) if c is not None]
        if not scores:
            return 0.0
        mean = sum(scores) / len(scores)
        # Too few recognised words means the variant destroyed content even if
        # the survivors look confident.  Scale quality down towards zero.
        if len(words) < 5:
            mean *= len(words) / 5.0
        # A digit run broken by a non-standard separator ("00·00086" for
        # "98,000.00") is a recognition failure the engine is confident about;
        # penalise it so another preprocessing variant gets a chance.
        if _has_suspicious_amount_token(item[4] for item in words):
            mean *= 0.5
        return mean

    variants = _variant_sequence_for(image_path)
    for variant_name, variant_path in variants:
        words: list[tuple[float, float, float, float, str, float | None]] = []
        engine = "none"
        words, engine = _rapidocr_words(variant_path, page_width_pts, page_height_pts, scale)
        if not words:
            words, engine = _tesseract_words(variant_path, page_width_pts, page_height_pts, scale)
        if not words:
            continue
        quality = score(words)
        if quality > best_quality:
            best_words = words
            best_engine = engine
            best_quality = quality
            best_variant = variant_name
        if quality >= _GOOD_ENOUGH_MEAN_CONF and not _has_suspicious_amount_token(
            item[4] for item in words
        ):
            break

    page_no = page + 1 if page <= 0 else page
    lines = _lines_from_words(best_words, page_no)
    boxes = [
        WordBox(
            page=page_no,
            text=item[4],
            x=item[0],
            y=item[1],
            width=item[2],
            height=item[3],
            confidence=item[5],
        )
        for item in best_words
    ]
    engine_label = best_engine if best_words else "none"
    if best_variant != "original" and best_words:
        engine_label = f"{best_engine}:{best_variant}"
    return lines, boxes, engine_label


_SUSPICIOUS_AMOUNT_RE = re.compile(r"\d\s*[·•▪◦‣·]\s*\d")


def _has_suspicious_amount_token(tokens) -> bool:
    """True when any token looks like a broken amount (digits split by a
    bullet/separator glyph instead of a decimal point or comma)."""
    for token in tokens:
        text = str(token or "")
        if _SUSPICIOUS_AMOUNT_RE.search(text):
            return True
    return False


def _variant_sequence_for(image_path: Path) -> list[tuple[str, Path]]:
    """Build preprocessing variants next to the source image (best effort)."""
    try:
        from PIL import Image

        with Image.open(image_path) as source:
            image = source.convert("RGB")
        faint = bool(_assess_image(image).get("faint", False))
        variants = _variant_sequence(image, faint=faint)
    except Exception:
        return [("original", image_path)]
    out: list[tuple[str, Path]] = []
    for name, variant in variants:
        if name == "original":
            out.append((name, image_path))
            continue
        path = image_path.with_name(f"{image_path.stem}-{name}.png")
        try:
            variant.save(path, "PNG")
        except Exception:
            continue
        out.append((name, path))
    return out


def _rapidocr_words(
    image_path: Path, page_width_pts: float, page_height_pts: float, scale: float
) -> tuple[list[tuple[float, float, float, float, str, float | None]], str]:
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
    words: list[tuple[float, float, float, float, str, float | None]] = []
    for index, text in enumerate(txts):
        token = (text or "").strip()
        if not token:
            continue
        confidence: float | None = None
        if scores is not None:
            try:
                score = float(scores[index])
            except (TypeError, ValueError, IndexError):
                score = None
            if score is not None:
                if score < _MIN_RAPID_SCORE:
                    continue
                confidence = score
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
        words.append((x, y, width, height, token, confidence))
    words.sort(key=lambda item: (-(item[1] + item[3] / 2.0), item[0]))
    return words, "rapidocr"


def _tesseract_words(
    image_path: Path, page_width_pts: float, page_height_pts: float, scale: float
) -> tuple[list[tuple[float, float, float, float, str, float | None]], str]:
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

    words: list[tuple[float, float, float, float, str, float | None]] = []
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
        words.append((x, y, width, height, text, conf / 100.0))
    words.sort(key=lambda item: (-(item[1] + item[3] / 2.0), item[0]))
    return words, "tesseract"


def _lines_from_words(
    words: list[tuple[float, float, float, float, str, float | None]], page_no: int
) -> list[LineBox]:
    bands: list[list[tuple[float, float, float, float, str, float | None]]] = []
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
    """OCR a raster statement or invoice.

    The image is normalised (EXIF orientation, colour mode) and scaled for a
    reliable OCR pass.  The page coordinate system remains the *original*
    oriented pixel grid, so source boxes still open the right crop in the UI.
    If no local OCR engine is present, return empty lines, engine='none'.

    Results are memoised per file identity for the life of the process, so a
    classifier pass and the parser pass over the same image share one engine
    run.  Every caller gets its own deep copy.
    """
    path = Path(path)
    key = _extraction_cache_key(path)
    cached = _extraction_cache_get(key)
    if cached is not None:
        return cached
    extracted = _extract_image_uncached(path)
    _extraction_cache_put(key, extracted)
    return extracted


def _extract_image_uncached(path: Path) -> ExtractedPdf:
    if not ocr_available():
        return ExtractedPdf(pdf_type="image_based", page_count=1, engine="none")

    with tempfile.TemporaryDirectory(prefix="caunpacker_image_ocr_") as tmp:
        prepared = _prepare_image(path, Path(tmp))
        if prepared is None:
            return ExtractedPdf(pdf_type="image_based", page_count=1, engine="none")
        ocr_path, width_pts, height_pts, scale = prepared
        lines, words, engine = ocr_image_page(
            ocr_path, 1, width_pts, height_pts, scale
        )

    text = "\n".join(line.text for line in lines)
    return ExtractedPdf(
        pdf_type="image_based",
        page_count=1,
        pages=[PageText(page=1, text=text, needs_ocr=False)],
        lines=lines,
        words=words,
        engine=engine if lines else "none",
        page_methods={1: engine} if lines else {},
    )


def _extraction_cache_key(path: Path) -> tuple[str, int, int] | None:
    """Identity of the file's current bytes. ``None`` bypasses the cache."""
    try:
        resolved = path.resolve()
        stat = resolved.stat()
    except OSError:
        return None
    if stat.st_size <= 0:
        return None
    return (str(resolved).lower(), stat.st_mtime_ns, stat.st_size)


def _extracted_size_estimate(extracted: ExtractedPdf) -> int:
    total = _BOX_BYTES_ESTIMATE
    for line in extracted.lines:
        total += _BOX_BYTES_ESTIMATE + len(line.text or "")
    for word in extracted.words:
        total += _BOX_BYTES_ESTIMATE + len(word.text or "")
    for page in extracted.pages:
        total += _BOX_BYTES_ESTIMATE + len(page.text or "")
    return total


def _extraction_cache_get(key: tuple[str, int, int] | None) -> ExtractedPdf | None:
    if key is None:
        return None
    with _EXTRACTION_CACHE_LOCK:
        stored = _EXTRACTION_CACHE.get(key)
        if stored is None:
            return None
        _EXTRACTION_CACHE.move_to_end(key)
        value = stored[1]
    # Parsers merge and reorder box lists, so hand out a private copy.
    return copy.deepcopy(value)


def _extraction_cache_put(
    key: tuple[str, int, int] | None, extracted: ExtractedPdf
) -> None:
    global _extraction_cache_bytes
    if key is None:
        return
    # An empty pass is a failure (no engine yet, driver crash, unreadable
    # image), not a result.  Pinning it would make the file unreadable for
    # the rest of the session after a driver fix, so failures are never kept.
    if not extracted.lines and not extracted.words:
        return
    size = _extracted_size_estimate(extracted)
    if size > _EXTRACTION_CACHE_MAX_BYTES:
        return
    stored = copy.deepcopy(extracted)
    with _EXTRACTION_CACHE_LOCK:
        previous = _EXTRACTION_CACHE.pop(key, None)
        if previous is not None:
            _extraction_cache_bytes -= previous[0]
        _EXTRACTION_CACHE[key] = (size, stored)
        _extraction_cache_bytes += size
        while _EXTRACTION_CACHE and (
            len(_EXTRACTION_CACHE) > _EXTRACTION_CACHE_MAX_ENTRIES
            or _extraction_cache_bytes > _EXTRACTION_CACHE_MAX_BYTES
        ):
            _evicted_key, (evicted_size, _value) = _EXTRACTION_CACHE.popitem(last=False)
            _extraction_cache_bytes -= evicted_size


def clear_extraction_cache() -> None:
    """Drop every cached image OCR result (used when the library is wiped)."""
    global _extraction_cache_bytes
    with _EXTRACTION_CACHE_LOCK:
        _EXTRACTION_CACHE.clear()
        _extraction_cache_bytes = 0


def extraction_cache_info() -> dict:
    """{entries, bytes, max_entries, max_bytes} — diagnostics and tests."""
    with _EXTRACTION_CACHE_LOCK:
        return {
            "entries": len(_EXTRACTION_CACHE),
            "bytes": _extraction_cache_bytes,
            "max_entries": _EXTRACTION_CACHE_MAX_ENTRIES,
            "max_bytes": _EXTRACTION_CACHE_MAX_BYTES,
        }


def _prepare_image(path: Path, tmp_dir: Path) -> tuple[Path, float, float, float] | None:
    """Return (ocr copy, display width, display height, ocr scale).

    Display dimensions are the original oriented pixel dimensions.  ``scale``
    converts OCR pixels back to that grid; a 2x upscale therefore has scale 2.
    """
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
            width, height = image.size
            if width <= 0 or height <= 0:
                return None
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            if image.mode == "L":
                image = ImageOps.autocontrast(image, cutoff=1).convert("RGB")
            else:
                image = ImageOps.autocontrast(image.convert("L"), cutoff=1).convert("RGB")

            longest = max(width, height)
            scale = 1.0
            if longest > _MAX_OCR_IMAGE_SIDE:
                scale = _MAX_OCR_IMAGE_SIDE / float(longest)
            elif longest < _MIN_OCR_IMAGE_SIDE:
                scale = min(2.0, _MIN_OCR_IMAGE_SIDE / float(longest))
            if abs(scale - 1.0) > 0.01:
                target = (
                    max(1, int(round(width * scale))),
                    max(1, int(round(height * scale))),
                )
                image = image.resize(target, Image.Resampling.LANCZOS)
            # Skewed phone photos band into wrong OCR lines; level the page
            # when the measured skew is meaningful.  The display grid is the
            # original orientation, so crops keep working either way.
            angle = _estimate_skew_safe(image)
            if angle:
                image, _applied = _deskew_image(image, angle)
            dest = tmp_dir / "page.png"
            image.save(dest, "PNG")
    except Exception:
        return None
    return dest, float(width), float(height), float(scale)


def _estimate_skew_safe(image) -> float:
    try:
        from apps.engine.imageprep import estimate_skew

        angle = estimate_skew(image)
        # Only rotate on meaningful skews — sub-degree estimates are noise,
        # and rotating for nothing costs accuracy on clean pages.
        return angle if abs(angle) >= 1.0 else 0.0
    except Exception:
        return 0.0


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
    page_methods: dict[int, str] = {}
    warnings: list[str] = []
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
                    page_lines, page_words, used = _ocr_rendered_page(
                        page, page_no, width, height, tmp_dir
                    )
                    if used != "none":
                        engine_name = used.split(":", 1)[0]
                        page_methods[page_no] = used
                    elif not page_lines:
                        warnings.append(f"page {page_no} could not be OCR read")
                except Exception:
                    page_lines = []
                    page_words = []
                    warnings.append(f"page {page_no} could not be OCR read")
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
        page_methods=page_methods,
        warnings=warnings,
    )


def _ocr_rendered_page(
    page,
    page_no: int,
    width: float,
    height: float,
    tmp_dir: Path,
) -> tuple[list[LineBox], list[WordBox], str]:
    """OCR one rendered PDF page, with a measured quality-based retry.

    First pass renders at the standard scale.  When recognition quality is
    poor (few words or low mean confidence) the page is retried at a higher
    render scale with preprocessing variants and the better result wins.
    """
    from apps.engine.evidence import summarise_word_confidence

    def render(scale: float) -> Path | None:
        bitmap = page.render(scale=scale)
        try:
            image = bitmap.to_pil()
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            png_path = tmp_dir / f"page-{page_no}-{int(scale * 100)}.png"
            image.save(png_path, "PNG")
            return png_path
        finally:
            bitmap.close()

    first_path = render(_RENDER_SCALE)
    if first_path is None:
        return [], [], "none"
    lines, words, engine = ocr_image_page(first_path, page_no, width, height, _RENDER_SCALE)

    summary = summarise_word_confidence(words)
    weak = not words or (
        summary is not None and summary["mean_confidence"] < _GOOD_ENOUGH_MEAN_CONF
    ) or len(words) < 12
    if weak:
        try:
            retry_path = render(_RETRY_SCALE)
        except Exception:
            retry_path = None
        if retry_path is not None:
            retry_lines, retry_words, retry_engine = ocr_image_page(
                retry_path, page_no, width, height, _RETRY_SCALE
            )
            retry_summary = summarise_word_confidence(retry_words)
            if _better_result(retry_summary, summary, retry_lines, lines):
                lines, words, engine = retry_lines, retry_words, retry_engine

    if not (lines or words):
        return [], [], "none"
    return lines, words, engine


def _better_result(
    candidate, current, candidate_lines: list[LineBox], current_lines: list[LineBox]
) -> bool:
    """Quality comparison between two OCR passes over the same page.

    A retry must beat the current result on mean confidence *and* recognise a
    comparable number of words — a confident-but-empty pass is not better.
    """
    if candidate is None:
        return False
    if current is None:
        current = {"mean_confidence": 0.0, "word_count": 0}
    cand_words = candidate.get("word_count", 0) or 0
    cur_words = current.get("word_count", 0) or 0
    cand_conf = candidate.get("mean_confidence", 0.0) or 0.0
    cur_conf = current.get("mean_confidence", 0.0) or 0.0
    if cand_words * 4 < cur_words:
        return False
    if not current_lines:
        return bool(candidate_lines)
    return cand_conf > cur_conf


def ocr_pdf_pages(
    path: Path,
    page_numbers: list[int],
    password: str | None = None,
) -> ExtractedPdf:
    """OCR only the requested pages of a PDF (used by hybrid per-page routing).

    Returns an ExtractedPdf whose page numbering matches ``page_numbers``
    (1-based).  Never uploads anything.
    """
    wanted = sorted({int(n) for n in page_numbers if int(n) >= 1})
    empty = ExtractedPdf(pdf_type="scanned", page_count=0, engine="none")
    if not wanted or not ocr_available():
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
    page_methods: dict[int, str] = {}
    warnings: list[str] = []
    engine_name = "none"
    total_pages = 0
    try:
        total_pages = len(document)
        with tempfile.TemporaryDirectory(prefix="caunpacker_ocr_") as tmp:
            tmp_dir = Path(tmp)
            for index in wanted:
                if index > len(document):
                    warnings.append(f"page {index} does not exist in this document")
                    continue
                page = document[index - 1]
                page_no = index
                try:
                    width = float(page.get_width())
                    height = float(page.get_height())
                    page_lines, page_words, used = _ocr_rendered_page(
                        page, page_no, width, height, tmp_dir
                    )
                    if used != "none":
                        engine_name = used.split(":", 1)[0]
                        page_methods[page_no] = used
                    elif not page_lines:
                        warnings.append(f"page {page_no} could not be OCR read")
                except Exception:
                    page_lines = []
                    page_words = []
                    warnings.append(f"page {page_no} could not be OCR read")
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
        page_count=total_pages,
        pages=pages,
        lines=lines,
        words=words,
        engine=engine_name if lines else "none",
        page_methods=page_methods,
        warnings=warnings,
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
