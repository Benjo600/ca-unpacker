"""Evidence helpers: extraction confidence and method for parsed rows.

Every extracted financial row should be able to say where it came from and how
sure the extraction is.  Confidence here is *derived from recognition
evidence* (OCR word scores, presence of a native text layer) — it is never
invented, and a high confidence never overrides source validation flags.
"""

from __future__ import annotations

from apps.engine.pdf_extract import WordBox


def word_confidence(word: WordBox) -> float | None:
    value = getattr(word, "confidence", None)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    # Tesseract reports 0..100; RapidOCR reports 0..1.
    if value > 1.0:
        value = value / 100.0
    if value < 0.0:
        return None
    return min(value, 1.0)


def words_in_bbox(
    words: list[WordBox],
    page: int,
    bbox: str | None,
    *,
    slack: float = 6.0,
) -> list[WordBox]:
    """Words whose boxes overlap ``bbox`` (an ``x,y,w,h`` string in page units)."""
    if not bbox or not words:
        return []
    try:
        x_s, y_s, w_s, h_s = (float(part) for part in str(bbox).split(",")[:4])
    except (TypeError, ValueError):
        return []
    right, top = x_s + w_s + slack, y_s + h_s + slack
    return [
        word
        for word in words
        if word.page == page
        and word.x + word.width >= x_s - slack
        and word.x <= right
        and word.y + word.height >= y_s - slack
        and word.y <= top
    ]


def confidence_for_bbox(
    words: list[WordBox], page: int, bbox: str | None
) -> float | None:
    """Mean OCR word confidence for the words inside ``bbox``, or ``None``.

    ``None`` means "no recognition evidence available" (native text layer),
    which is different from a low score and must not be read as zero.
    """
    picked = [word for word in words_in_bbox(words, page, bbox) if word.text.strip()]
    scores = [score for score in (word_confidence(word) for word in picked) if score is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def attach_extraction_evidence(
    row: dict,
    *,
    method: str | None = None,
    confidence: float | None = None,
    words: list[WordBox] | None = None,
    page: int | None = None,
    bbox: str | None = None,
) -> dict:
    """Stamp ``extraction_method``/``extraction_confidence`` onto a row dict.

    Additive keys only; existing consumers ignore unknown payload keys.  When
    ``words`` is provided the confidence is recomputed from the words inside
    the row's own bounding box instead of a page-wide average.
    """
    if method:
        row["extraction_method"] = str(method)[:40]
    if confidence is None and words:
        confidence = confidence_for_bbox(words, page or 1, bbox or row.get("source_bbox"))
    if confidence is not None:
        try:
            row["extraction_confidence"] = round(min(max(float(confidence), 0.0), 1.0), 4)
        except (TypeError, ValueError):
            pass
    return row


def summarise_word_confidence(words: list[WordBox]) -> dict | None:
    """Page-level recognition summary used for warnings and quality gates."""
    scores = [score for score in (word_confidence(word) for word in words) if score is not None]
    if not scores:
        return None
    low = sum(1 for score in scores if score < 0.6)
    return {
        "mean_confidence": round(sum(scores) / len(scores), 4),
        "min_confidence": round(min(scores), 4),
        "word_count": len(scores),
        "low_confidence_words": low,
    }
