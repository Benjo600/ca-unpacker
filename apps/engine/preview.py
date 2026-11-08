"""In-app file preview.

The preview pane shows the *source* document, not the extracted rows. It reads
straight from the library copy and never writes to it. Images are returned as
data URLs (the same transport the crop preview already uses) so the window can
show them without a local web server.

Nothing here interprets accounting data. A JSON file that is not valid JSON is
reported as invalid, not repaired.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path

from apps.engine.db import StoredFile, get_session
from apps.engine.kinds import IMAGE_SUFFIXES, KIND_LABELS
from apps.engine.library import init_library, resolve_storage_key
from apps.engine.pdf_passwords import get_file_password, redact_known_passwords

PDF_SUFFIXES = {".pdf"}
JSON_SUFFIXES = {".json"}
CSV_SUFFIXES = {".csv"}
XLSX_SUFFIXES = {".xlsx"}
TEXT_SUFFIXES = {".txt", ".xml"}
ARCHIVE_SUFFIXES = {".zip"}

# Display caps. They exist so one 50 MB portal JSON cannot freeze the window.
TEXT_BYTES = 400_000
TEXT_LIMIT = 200_000
JSON_BYTES = 4_000_000
ROW_LIMIT = 200
COL_LIMIT = 30
ZIP_ENTRY_LIMIT = 200

IMAGE_MAX_EDGE = 2200
JPEG_QUALITY = 88
PNG_KEEP_BYTES = 900_000
PDF_SCALE = 2.0


def preview_file(
    file_id: int,
    page: int = 1,
    password: str = "",
    sheet: str = "",
    formatted: bool = True,
) -> dict:
    """Build one preview payload for a stored file.

    `page` is 1-based and only meaningful for PDFs. `password` is used for this
    call only and is never stored; `sheet`, `formatted` drive XLSX and JSON
    views.
    """
    loaded = _load_records(file_id)
    if loaded is None:
        return _fail("File was not found.", "missing")
    record, path = loaded
    if not path.is_file():
        return _fail("The stored source file is missing.", "missing")

    suffix = path.suffix.lower()
    base = {
        "ok": True,
        "file_id": int(file_id),
        "name": record["name"],
        "kind": record["kind"],
        "kind_label": KIND_LABELS.get(record["kind"], "Unknown"),
        "suffix": suffix,
        "size": path.stat().st_size,
        "preview_type": "unsupported",
        "can_open_external": True,
    }

    try:
        if suffix in PDF_SUFFIXES:
            return _pdf_preview(base, path, int(file_id), int(page or 1), password)
        if suffix in IMAGE_SUFFIXES:
            return _image_preview(base, path, int(file_id))
        if suffix in XLSX_SUFFIXES:
            return _xlsx_preview(base, path, sheet)
        if suffix in CSV_SUFFIXES:
            return _csv_preview(base, path)
        if suffix in JSON_SUFFIXES:
            return _json_preview(base, path, formatted)
        if suffix in TEXT_SUFFIXES:
            return _text_preview(base, path)
        if suffix in ARCHIVE_SUFFIXES:
            return _archive_preview(base, path)
    except Exception as exc:  # noqa: BLE001 - the pane needs a message, not a traceback
        return _fail(_safe_error(exc, int(file_id)), "unreadable")

    return _unsupported(base)


def source_file_path(file_id: int) -> Path | None:
    """Path of the stored original, for "open in its own app"."""
    loaded = _load_records(file_id)
    if loaded is None:
        return None
    _record, path = loaded
    return path if path.is_file() else None


def _load_records(file_id: int) -> tuple[dict, Path] | None:
    session = get_session()
    try:
        row = session.get(StoredFile, int(file_id))
        if row is None or not row.storage_key:
            return None
        record = {
            "name": row.original_name,
            "kind": row.override_kind or row.detected_kind or "unknown",
            "storage_key": row.storage_key,
        }
    finally:
        session.close()
    return record, resolve_storage_key(record["storage_key"])


def _pdf_preview(base: dict, path: Path, file_id: int, page: int, password: str) -> dict:
    from apps.engine import pdf_render

    secret = str(password or "") or get_file_password(file_id)
    try:
        total = pdf_render.page_count(path, secret)
    except Exception as exc:  # noqa: BLE001
        return _pdf_failure(exc, bool(secret), file_id)

    if total < 1:
        return _fail("This PDF has no pages.", "unreadable")
    if page < 1 or page > total:
        return _fail(f"This PDF has no page {page}.", "range")

    try:
        image_path = _render_pdf_page(pdf_render, path, page, secret, file_id)
    except Exception as exc:  # noqa: BLE001
        return _pdf_failure(exc, bool(secret), file_id)

    payload = base | {
        "preview_type": "pdf",
        "page": page,
        "page_count": total,
        "image": _image_payload(image_path),
    }
    if not payload["image"]:
        return _fail("Could not render this page.", "unreadable")
    return payload


def _pdf_failure(exc: BaseException, had_password: bool, file_id: int) -> dict:
    message = _safe_error(exc, file_id)
    if "password" in message.lower() or "encrypted" in message.lower():
        if not had_password:
            return _fail("This PDF needs a password to preview.", "password_required")
        return _fail(message, "password_required")
    return _fail(message or "Could not open this PDF.", "unreadable")


def _render_pdf_page(pdf_render, path: Path, page: int, secret: str | None, file_id: int) -> Path:
    stat = path.stat()
    stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    digest = hashlib.sha1(
        f"{file_id}:{page}:{PDF_SCALE}:{stamp}".encode("utf-8")
    ).hexdigest()[:16]
    folder = _cache_dir()
    png_path = folder / f"{file_id}_p{page}_{digest}.png"
    jpg_path = png_path.with_suffix(".jpg")
    if jpg_path.is_file():
        return jpg_path
    if png_path.is_file():
        return png_path

    # Render to a private temp name so two rapid page clicks cannot write the
    # same PNG at the same time.
    temp_png = png_path.with_name(f".{png_path.stem}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        pdf_render.render_page_png(path, page, temp_png, password=secret, scale=PDF_SCALE)
        if temp_png.stat().st_size > PNG_KEEP_BYTES:
            temp_jpg = jpg_path.with_name(f".{jpg_path.stem}.{uuid.uuid4().hex[:8]}.tmp")
            try:
                _png_to_jpeg(temp_png, temp_jpg)
                temp_jpg.replace(jpg_path)
            finally:
                temp_jpg.unlink(missing_ok=True)
            _prune_cache(folder)
            return jpg_path
        temp_png.replace(png_path)
    finally:
        temp_png.unlink(missing_ok=True)
    _prune_cache(folder)
    return png_path


def _image_preview(base: dict, path: Path, file_id: int) -> dict:
    from PIL import Image, ImageOps

    stat = path.stat()
    stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    digest = hashlib.sha1(f"{file_id}:image:{stamp}".encode("utf-8")).hexdigest()[:16]
    dest = _cache_dir() / f"{file_id}_img_{digest}.jpg"
    if not dest.is_file():
        temp = dest.with_name(f".{dest.stem}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source)
                if image.mode in {"RGBA", "LA", "P"}:
                    rgba = image.convert("RGBA")
                    canvas = Image.new("RGB", rgba.size, (255, 255, 255))
                    canvas.paste(rgba, mask=rgba.split()[-1])
                    image = canvas
                else:
                    image = image.convert("RGB")
                image.thumbnail((IMAGE_MAX_EDGE, IMAGE_MAX_EDGE))
                image.save(temp, "JPEG", quality=90, optimize=True)
            temp.replace(dest)
        finally:
            temp.unlink(missing_ok=True)
        _prune_cache(dest.parent)

    payload = base | {
        "preview_type": "image",
        "page": 1,
        "page_count": 1,
        "image": _image_payload(dest),
    }
    if not payload["image"]:
        return _fail("Could not open this image.", "unreadable")
    return payload


def _json_preview(base: dict, path: Path, formatted: bool) -> dict:
    raw, read_truncated = _read_text(path, JSON_BYTES)
    valid: bool | None = None
    note = ""
    if read_truncated:
        shown = raw
        note = f"Showing the first {_size_label(JSON_BYTES)} of this file. It is too large to format here."
    elif formatted:
        try:
            parsed = json.loads(raw)
        except ValueError:
            valid = False
            shown = raw
            note = "This file is not valid JSON. Showing the raw text."
        else:
            valid = True
            shown = json.dumps(parsed, indent=2, ensure_ascii=False)
            note = "Indented for reading only. The file on disk is unchanged."
    else:
        shown = raw
        note = "Raw file text."

    text, cut = _cap_text(shown)
    if cut:
        note = f"{note} Showing the first {TEXT_LIMIT:,} characters." if note else f"Showing the first {TEXT_LIMIT:,} characters."
    payload = base | {
        "preview_type": "text",
        "text": text,
        "language": "json",
        "is_json": True,
        "valid_json": valid,
        "formatted": bool(formatted),
        "truncated": bool(cut or read_truncated),
        "note": note,
    }
    return payload


def _csv_preview(base: dict, path: Path) -> dict:
    raw, read_truncated = _read_text(path, JSON_BYTES)
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(raw[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","

    rows: list[list[str]] = []
    extra = False
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    for index, row in enumerate(reader):
        if index >= ROW_LIMIT:
            extra = True
            break
        rows.append([_cell_text(cell) for cell in row[:COL_LIMIT]])
        if len(row) > COL_LIMIT:
            extra = True

    note = ""
    if read_truncated:
        note = "This export is larger than the preview limit. Excel has the full file."
    elif extra:
        note = f"Showing the first {ROW_LIMIT} rows and {COL_LIMIT} columns."

    return base | {
        "preview_type": "table",
        "table": {
            "rows": rows,
            "row_count": len(rows),
            "column_count": max((len(row) for row in rows), default=0),
            "has_header": bool(rows),
            "truncated": bool(extra or read_truncated),
            "sheet": path.name,
            "sheets": [],
            "delimiter": delimiter,
        },
        "note": note,
    }


def _xlsx_preview(base: dict, path: Path, sheet: str) -> dict:
    from openpyxl import load_workbook

    workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
    try:
        sheets = list(workbook.sheetnames)
        chosen = sheet if sheet in sheets else (sheets[0] if sheets else "")
        if not chosen:
            return _fail("This workbook has no sheets.", "unreadable")
        worksheet = workbook[chosen]
        rows: list[list[str]] = []
        extra = False
        for index, row in enumerate(
            worksheet.iter_rows(min_row=1, max_row=ROW_LIMIT + 1, max_col=COL_LIMIT, values_only=True)
        ):
            if index >= ROW_LIMIT:
                extra = True
                break
            rows.append([_cell_text(value) for value in row])
        rows = [_trim_cells(row) for row in rows]
        while rows and not any(rows[-1]):
            rows.pop()
        if getattr(worksheet, "max_column", 0) > COL_LIMIT:
            extra = True
    finally:
        workbook.close()

    note = f"Showing the first {ROW_LIMIT} rows." if extra else ""
    return base | {
        "preview_type": "table",
        "table": {
            "rows": rows,
            "row_count": len(rows),
            "column_count": max((len(row) for row in rows), default=0),
            "has_header": bool(rows),
            "truncated": extra,
            "sheet": chosen,
            "sheets": sheets,
            "delimiter": "",
        },
        "note": note,
    }


def _text_preview(base: dict, path: Path) -> dict:
    raw, read_truncated = _read_text(path, TEXT_BYTES)
    text, cut = _cap_text(raw)
    note = ""
    if cut or read_truncated:
        note = f"Showing the first {TEXT_LIMIT:,} characters. The file on disk is unchanged."
    return base | {
        "preview_type": "text",
        "text": text,
        "language": "xml" if path.suffix.lower() == ".xml" else "text",
        "is_json": False,
        "valid_json": None,
        "formatted": False,
        "truncated": bool(cut or read_truncated),
        "note": note,
    }


def _archive_preview(base: dict, path: Path) -> dict:
    entries: list[dict] = []
    extra = False
    try:
        with zipfile.ZipFile(path) as archive:
            for index, info in enumerate(archive.infolist()):
                if index >= ZIP_ENTRY_LIMIT:
                    extra = True
                    break
                entries.append(
                    {
                        "name": info.filename,
                        "size": int(info.file_size),
                        "compressed": int(info.compress_size),
                        "folder": info.is_dir(),
                    }
                )
    except zipfile.BadZipFile:
        return _fail("This zip file cannot be opened.", "unreadable")

    note = ""
    if extra:
        note = f"Showing the first {ZIP_ENTRY_LIMIT} entries."
    return base | {
        "preview_type": "archive",
        "archive": {"entries": entries, "count": len(entries), "truncated": extra},
        "note": note,
    }


def _unsupported(base: dict) -> dict:
    return base | {
        "preview_type": "unsupported",
        "note": (
            f"{base['suffix'] or 'This file type'} cannot be shown in the app. "
            "Open it in its own program to read it."
        ),
    }


def _image_payload(path: Path) -> dict | None:
    from PIL import Image

    try:
        if not path.is_file():
            return None
        with Image.open(path) as image:
            width, height = image.size
        media = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        data = path.read_bytes()
    except Exception:  # noqa: BLE001
        return None
    return {
        "data_url": f"data:{media};base64,{base64.b64encode(data).decode('ascii')}",
        "media": media,
        "width": int(width),
        "height": int(height),
    }


def _png_to_jpeg(source: Path, dest: Path) -> None:
    from PIL import Image

    with Image.open(source) as image:
        image.convert("RGB").save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)


def _cache_dir() -> Path:
    folder = init_library() / "cache" / "previews"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _prune_cache(folder: Path, keep: int = 400) -> None:
    """Keep the preview cache from growing without limit on a busy laptop."""
    try:
        files = sorted(folder.iterdir(), key=lambda item: item.stat().st_mtime)
    except OSError:
        return
    if len(files) <= keep:
        return
    for old in files[: len(files) - keep]:
        try:
            old.unlink()
        except OSError:
            continue


def _read_text(path: Path, limit: int) -> tuple[str, bool]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        data = handle.read(limit)
    return _decode(data), size > limit


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _cap_text(text: str) -> tuple[str, bool]:
    if len(text) <= TEXT_LIMIT:
        return text, False
    return text[:TEXT_LIMIT], True


def _trim_cells(row: list[str]) -> list[str]:
    """Drop the empty padding openpyxl adds up to max_column."""
    while row and not row[-1]:
        row.pop()
    return row


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.hour == value.minute == value.second == 0:
            return value.strftime("%d-%m-%Y")
        return value.strftime("%d-%m-%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}"
    return str(value)


def _safe_error(exc: BaseException, file_id: int) -> str:
    message = str(exc).strip()
    try:
        message = redact_known_passwords(message)
    except Exception:  # noqa: BLE001
        pass
    if not message or "traceback (most recent call last)" in message.lower():
        return "Could not open this file."
    return message.splitlines()[0][:300]


def _size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.0f} MB"
    return f"{max(1, size // 1024)} KB"


def _fail(message: str, reason: str) -> dict:
    return {"ok": False, "error": message, "reason": reason}
