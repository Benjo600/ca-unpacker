"""Local image preprocessing for OCR.

Financial scans are rarely clean: faint photocopies, skewed phone photos,
grey shadows, noise from flatbeds.  Every operation here is *conservative*
and reversible — the original page image is always preserved for evidence;
preprocessing happens on a copy that only feeds the OCR engine.

Design rules (from the scanning upgrade plan):

* never apply an aggressive transform blindly — build a small set of
  candidate variants and let measured OCR quality pick the winner;
* never upscale when upscaling cannot recover information (cap at 2x);
* preserve small decimal points and punctuation (median denoise radius 1,
  threshold with a local mean, no morphological erosion);
* everything is Pillow + numpy — no OpenCV dependency for this path.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageFilter, ImageOps

# Angles below this are noise; rotating by them costs accuracy for nothing.
_MIN_DESKEW_ANGLE = 0.25
_MAX_DESKEW_ANGLE = 8.0
# Effective pixels per inch band that OCR engines read reliably.
_MIN_OCR_PPI = 150
_TARGET_OCR_PPI = 220


def to_grayscale(image: Image.Image) -> Image.Image:
    if image.mode == "L":
        return image
    return image.convert("L")


def assess(image: Image.Image) -> dict:
    """Cheap, measurable quality indicators for an OCR input image."""
    gray = np.asarray(to_grayscale(image), dtype=np.float32)
    if gray.size == 0:
        return {"contrast": 0.0, "ink_ratio": 0.0, "dpi_risk": True}
    p_low, p_high = np.percentile(gray, [5, 95])
    contrast = float(p_high - p_low)
    ink = float((gray < 128).mean())
    # Very low ink with very low contrast usually means a faint photocopy.
    faint = contrast < 40.0 and ink < 0.01
    return {
        "contrast": round(contrast, 2),
        "ink_ratio": round(ink, 5),
        "faint": faint,
    }


def estimate_skew(image: Image.Image) -> float:
    """Estimate the skew angle in degrees using a projection-profile search.

    Downsamples the image, then scores candidate angles by the variance of
    row ink sums (text lines produce sharp peaks when the image is level).
    Returns a positive angle when text ascends left-to-right (i.e. the page
    must be rotated by ``-angle`` to level it).
    """
    gray = to_grayscale(image)
    scale = min(1.0, 1000.0 / max(gray.size))
    if scale < 1.0:
        gray = gray.resize(
            (max(1, int(gray.width * scale)), max(1, int(gray.height * scale))),
            Image.Resampling.BILINEAR,
        )
    arr = np.asarray(gray, dtype=np.float32)
    ink = arr < 160  # text-ish pixels
    if ink.sum() < 40:
        return 0.0
    best_angle = 0.0
    best_score = -1.0
    coarse = [a / 4.0 for a in range(-24, 25)]  # -6..6 in 0.25° steps
    for angle in coarse:
        score = _profile_score(ink, angle)
        if score > best_score:
            best_score = score
            best_angle = angle
    # Refine around the coarse winner.
    fine = [best_angle + step / 10.0 for step in range(-4, 5)]
    for angle in fine:
        if abs(angle) > _MAX_DESKEW_ANGLE:
            continue
        score = _profile_score(ink, angle)
        if score > best_score:
            best_score = score
            best_angle = angle
    if abs(best_angle) < _MIN_DESKEW_ANGLE:
        return 0.0
    return float(max(-_MAX_DESKEW_ANGLE, min(_MAX_DESKEW_ANGLE, best_angle)))


def _profile_score(ink: np.ndarray, angle_deg: float) -> float:
    if angle_deg == 0.0:
        rows = ink.sum(axis=1)
        return float(rows.var())
    rotated = _rotate_binary(ink, angle_deg)
    rows = rotated.sum(axis=1)
    return float(rows.var())


def _rotate_binary(ink: np.ndarray, angle_deg: float) -> np.ndarray:
    h, w = ink.shape
    angle = math.radians(angle_deg)
    cos, sin = math.cos(angle), math.sin(angle)
    # Rotate around the centre; output keeps the original frame size.
    cx, cy = w / 2.0, h / 2.0
    ys, xs = np.mgrid[0:h, 0:w]
    src_x = cos * (xs - cx) + sin * (ys - cy) + cx
    src_y = -sin * (xs - cx) + cos * (ys - cy) + cy
    ix = np.floor(src_x).astype(np.int64)
    iy = np.floor(src_y).astype(np.int64)
    inside = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    out = np.zeros_like(ink, dtype=bool)
    out[inside] = ink[iy[inside], ix[inside]]
    return out


def deskew(image: Image.Image, angle_deg: float | None = None) -> tuple[Image.Image, float]:
    """Rotate the image to level the text.  Returns (image, applied angle)."""
    angle = estimate_skew(image) if angle_deg is None else angle_deg
    if abs(angle) < _MIN_DESKEW_ANGLE:
        return image, 0.0
    rotated = image.rotate(
        -angle,
        resample=Image.Resampling.BICUBIC,
        fillcolor=255 if image.mode == "L" else (255, 255, 255),
        expand=False,
    )
    return rotated, -angle


def enhance_contrast(image: Image.Image) -> Image.Image:
    gray = to_grayscale(image)
    return ImageOps.autocontrast(gray, cutoff=1)


def denoise(image: Image.Image) -> Image.Image:
    """Median denoise (radius 1) — removes speckle, keeps decimal points."""
    return to_grayscale(image).filter(ImageFilter.MedianFilter(size=3))


def adaptive_threshold(image: Image.Image, block: int = 25, offset: int = 12) -> Image.Image:
    """Local-mean thresholding (pure numpy integral image).

    Handles shadows and uneven illumination that global thresholding destroys.
    ``offset`` keeps faint-but-real strokes while dropping background noise.
    """
    arr = np.asarray(to_grayscale(image), dtype=np.int32)
    integral = _integral_image(arr)
    pad = block // 2
    h, w = arr.shape
    # Mean over a (2*pad+1) window at every pixel.
    y0 = np.clip(np.arange(h) - pad, 0, h)
    y1 = np.clip(np.arange(h) + pad + 1, 0, h)
    x0 = np.clip(np.arange(w) - pad, 0, w)
    x1 = np.clip(np.arange(w) + pad + 1, 0, w)
    area = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    s = (
        integral[np.ix_(y1, x1)].reshape(h, w)
        - integral[np.ix_(y0, x1)].reshape(h, w)
        - integral[np.ix_(y1, x0)].reshape(h, w)
        + integral[np.ix_(y0, x0)].reshape(h, w)
    )
    mean = s / np.maximum(area, 1)
    out = np.where(arr < (mean - offset), 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="L")


def _integral_image(arr: np.ndarray) -> np.ndarray:
    rows, cols = arr.shape
    integral = np.zeros((rows + 1, cols + 1), dtype=np.int64)
    integral[1:, 1:] = arr.cumsum(axis=0).cumsum(axis=1)
    return integral


def resolution_scale(image: Image.Image, ppi: float | None) -> float:
    """Recommended OCR scale so the effective resolution lands in the good band.

    ``ppi`` is the *effective* resolution (for PDF pages: 72 * render_scale).
    Never upscales beyond 2x — upscaling cannot recover lost detail, it only
    smooths the engine's input.
    """
    if ppi is None or ppi <= 0:
        return 1.0
    if ppi < _MIN_OCR_PPI:
        return min(2.0, _TARGET_OCR_PPI / ppi)
    if ppi > 400:
        return max(0.5, 300.0 / ppi)
    return 1.0


def variant_sequence(image: Image.Image, faint: bool | None = None) -> list[tuple[str, Image.Image]]:
    """Candidate preprocessing variants, cheapest first.

    The caller OCRs them in order and may stop early when quality is already
    acceptable.  ``faint`` comes from :func:`assess` and promotes the threshold
    variant for faint photocopies.
    """
    if faint is None:
        faint = assess(image).get("faint", False)
    variants: list[tuple[str, Image.Image]] = [("original", image)]
    enhanced = enhance_contrast(image)
    variants.append(("contrast", enhanced))
    variants.append(("denoise+contrast", denoise(enhanced)))
    if faint:
        # Faint copies benefit most from local thresholding; offer it earlier.
        variants.insert(2, ("threshold", adaptive_threshold(enhanced)))
    else:
        variants.append(("threshold", adaptive_threshold(enhanced)))
    return variants
