from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path
from typing import Any

from apps.engine.kinds import IMAGE_SUFFIXES, KIND_LABELS, KINDS
from apps.engine.pdf_render import _get_page, _is_password_failure, _open_pdf


def _detect_kind(path: Path) -> str:
    try:
        from apps.engine.classifier import classify_path

        return classify_path(path).kind
    except Exception:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return "bank"
        if suffix in {".xlsx", ".xls", ".csv"}:
            return "spreadsheet"
        if suffix == ".json":
            return "gstr_2b"
        if suffix == ".xml":
            return "tally"
        return "unknown"

MAX_TEXT_BYTES = 512 * 1024  # 512 KB
MAX_TABLE_ROWS = 250
MAX_TABLE_COLS = 50


def _data_url(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_preview_for_path(
    file_path: str | Path,
    page: int = 1,
    sheet_name: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    path = Path(file_path).resolve()
    if not path.exists():
        return {"ok": False, "error": f"File not found: {path.name}"}
    if not path.is_file():
        return {"ok": False, "error": f"Path is not a regular file: {path.name}"}

    size = path.stat().st_size
    suffix = path.suffix.lower()
    base_info = {
        "filename": path.name,
        "path": str(path),
        "size": size,
        "size_formatted": _format_size(size),
        "extension": suffix,
    }

    # 1. PDF Documents
    if suffix == ".pdf":
        return _preview_pdf(path, page, password, base_info)

    # 2. Spreadsheets (Excel)
    if suffix in {".xlsx", ".xlsm", ".xltx"}:
        return _preview_excel(path, sheet_name, base_info)

    # 3. CSV Tabular Data
    if suffix == ".csv":
        return _preview_csv(path, base_info)

    # 4. JSON Files
    if suffix == ".json":
        return _preview_json(path, base_info)

    # 5. XML Files
    if suffix == ".xml":
        return _preview_xml(path, base_info)

    # 6. Raster Images
    if suffix in IMAGE_SUFFIXES or suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}:
        return _preview_image(path, base_info)

    # 7. Text & Code Files
    if suffix in {".txt", ".md", ".log", ".py", ".sql", ".yaml", ".yml", ".ini", ".env", ".cfg", ".bat", ".sh"}:
        return _preview_text(path, base_info)

    # 8. Fallback / Binary
    return {
        "ok": True,
        "type": "binary",
        "detected_kind": _detect_kind(path),
        **base_info,
    }


def _preview_pdf(
    path: Path, page: int, password: str | None, base_info: dict[str, Any]
) -> dict[str, Any]:
    try:
        pdf = _open_pdf(path, password)
    except ValueError as exc:
        msg = str(exc)
        if "password" in msg.lower():
            return {
                "ok": False,
                "error": msg,
                "needs_password": True,
                "type": "pdf",
                **base_info,
            }
        return {"ok": False, "error": msg, "type": "pdf", **base_info}
    except Exception as exc:
        if _is_password_failure(path, exc):
            return {
                "ok": False,
                "error": "Password required to view this PDF",
                "needs_password": True,
                "type": "pdf",
                **base_info,
            }
        return {"ok": False, "error": f"Could not open PDF: {exc}", "type": "pdf", **base_info}

    try:
        total_pages = len(pdf)
        if total_pages == 0:
            return {
                "ok": False,
                "error": "PDF has 0 pages",
                "type": "pdf",
                **base_info,
            }

        target_page = max(1, min(page, total_pages))
        pdf_page = _get_page(pdf, target_page)
        extracted_text = ""
        try:
            pt_size = tuple(float(v) for v in pdf_page.get_size())
            # Extract plain text if available
            try:
                text_page = pdf_page.get_textpage()
                extracted_text = (text_page.get_text_range() or "").strip()[:10000]
            except Exception:
                extracted_text = ""

            # Render page to PNG bitmap
            bitmap = pdf_page.render(scale=1.5)
            try:
                pil_image = bitmap.to_pil().convert("RGB")
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                png_bytes = buf.getvalue()
                image_data = _data_url(png_bytes, "image/png")
            finally:
                close_fn = getattr(bitmap, "close", None)
                if callable(close_fn):
                    close_fn()
        finally:
            pdf_page.close()
    finally:
        pdf.close()

    return {
        "ok": True,
        "type": "pdf",
        "page": target_page,
        "total_pages": total_pages,
        "width_pts": pt_size[0],
        "height_pts": pt_size[1],
        "image_data": image_data,
        "text": extracted_text,
        **base_info,
    }


def _preview_excel(
    path: Path, requested_sheet: str | None, base_info: dict[str, Any]
) -> dict[str, Any]:
    try:
        import openpyxl
    except ImportError:
        return {"ok": False, "error": "openpyxl is not installed", **base_info}

    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        return {"ok": False, "error": f"Could not read Excel file: {exc}", **base_info}

    try:
        sheets = wb.sheetnames
        if not sheets:
            return {"ok": False, "error": "Workbook contains no sheets", **base_info}

        active_sheet_name = requested_sheet if requested_sheet in sheets else sheets[0]
        ws = wb[active_sheet_name]

        rows_data: list[list[str]] = []
        row_count = 0
        max_cols_found = 0

        for row in ws.iter_rows(values_only=True):
            row_count += 1
            if len(rows_data) < MAX_TABLE_ROWS:
                cleaned_row = []
                for idx, cell in enumerate(row):
                    if idx >= MAX_TABLE_COLS:
                        break
                    if cell is None:
                        cleaned_row.append("")
                    else:
                        cleaned_row.append(str(cell).strip())
                # Check if entire row is empty
                if any(cleaned_row):
                    rows_data.append(cleaned_row)
                    max_cols_found = max(max_cols_found, len(cleaned_row))

        columns: list[str] = []
        rows: list[list[str]] = []
        if rows_data:
            # Use first row as headers if reasonable, or generic Col 1..N
            first_row = rows_data[0]
            # If first row has strings and not too many numbers, use as header
            has_headers = any(first_row) and not all(r.replace(".", "", 1).isdigit() for r in first_row if r)
            if has_headers:
                columns = [col if col else f"Col {i+1}" for i, col in enumerate(first_row)]
                rows = rows_data[1:]
            else:
                columns = [f"Col {i+1}" for i in range(max_cols_found)]
                rows = rows_data

            # Normalize column length across rows
            col_count = len(columns)
            normalized_rows = []
            for r in rows:
                if len(r) < col_count:
                    r = r + [""] * (col_count - len(r))
                else:
                    r = r[:col_count]
                normalized_rows.append(r)
            rows = normalized_rows

        return {
            "ok": True,
            "type": "spreadsheet",
            "sheets": sheets,
            "active_sheet": active_sheet_name,
            "columns": columns,
            "rows": rows,
            "total_rows": row_count,
            "truncated": row_count > MAX_TABLE_ROWS,
            **base_info,
        }
    finally:
        wb.close()


def _preview_csv(path: Path, base_info: dict[str, Any]) -> dict[str, Any]:
    try:
        # Try UTF-8 first, fallback to cp1252 / latin1
        content = ""
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                content = path.read_text(encoding=encoding, errors="strict")
                break
            except UnicodeDecodeError:
                continue
        if not content:
            content = path.read_text(encoding="utf-8", errors="replace")

        reader = csv.reader(io.StringIO(content))
        rows_data: list[list[str]] = []
        row_count = 0
        max_cols = 0
        for row in reader:
            row_count += 1
            if len(rows_data) < MAX_TABLE_ROWS:
                cleaned = [str(cell).strip() for cell in row[:MAX_TABLE_COLS]]
                if any(cleaned):
                    rows_data.append(cleaned)
                    max_cols = max(max_cols, len(cleaned))

        columns: list[str] = []
        rows: list[list[str]] = []
        if rows_data:
            first_row = rows_data[0]
            columns = [col if col else f"Col {i+1}" for i, col in enumerate(first_row)]
            rows = rows_data[1:]
            col_count = len(columns)
            normalized_rows = []
            for r in rows:
                if len(r) < col_count:
                    r = r + [""] * (col_count - len(r))
                else:
                    r = r[:col_count]
                normalized_rows.append(r)
            rows = normalized_rows

        return {
            "ok": True,
            "type": "spreadsheet",
            "sheets": ["CSV"],
            "active_sheet": "CSV",
            "columns": columns,
            "rows": rows,
            "total_rows": row_count,
            "truncated": row_count > MAX_TABLE_ROWS,
            **base_info,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Could not parse CSV: {exc}", **base_info}


def _preview_json(path: Path, base_info: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_BYTES]
        try:
            parsed = json.loads(raw)
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
            meta: dict[str, Any] = {}
            if isinstance(parsed, dict):
                meta["top_keys"] = list(parsed.keys())[:15]
                meta["key_count"] = len(parsed)
            elif isinstance(parsed, list):
                meta["item_count"] = len(parsed)
            return {
                "ok": True,
                "type": "json",
                "content": formatted[:MAX_TEXT_BYTES],
                "truncated": len(raw) >= MAX_TEXT_BYTES,
                "meta": meta,
                **base_info,
            }
        except Exception:
            return {
                "ok": True,
                "type": "text",
                "content": raw,
                "truncated": len(raw) >= MAX_TEXT_BYTES,
                **base_info,
            }
    except Exception as exc:
        return {"ok": False, "error": f"Could not read JSON file: {exc}", **base_info}


def _preview_xml(path: Path, base_info: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_BYTES]
        return {
            "ok": True,
            "type": "xml",
            "content": raw,
            "truncated": len(raw) >= MAX_TEXT_BYTES,
            **base_info,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Could not read XML file: {exc}", **base_info}


def _preview_image(path: Path, base_info: dict[str, Any]) -> dict[str, Any]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            width, height = img.size
            format_name = img.format or "PNG"

        data = path.read_bytes()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
        }
        mime = mime_map.get(base_info["extension"], "image/png")
        data_url = _data_url(data, mime)

        return {
            "ok": True,
            "type": "image",
            "image_data": data_url,
            "width": width,
            "height": height,
            "format": format_name,
            **base_info,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Could not load image: {exc}", **base_info}


def _preview_text(path: Path, base_info: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_BYTES]
        lines = raw.splitlines()
        return {
            "ok": True,
            "type": "text",
            "content": raw,
            "line_count": len(lines),
            "truncated": len(raw) >= MAX_TEXT_BYTES,
            **base_info,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Could not read text file: {exc}", **base_info}


def list_folder_preview_files(folder_path: str | Path, max_files: int = 400) -> dict[str, Any]:
    """List all supported files within a folder for desktop app preview."""
    root = Path(folder_path).resolve()
    if not root.exists():
        return {"ok": False, "error": f"Folder does not exist: {root}"}
    if not root.is_dir():
        return {"ok": False, "error": f"Path is not a directory: {root}"}

    collected: list[dict[str, Any]] = []
    _skip = {".git", ".svn", "__pycache__", ".venv", "node_modules"}

    for item in sorted(root.rglob("*"), key=lambda p: p.name.lower()):
        try:
            rel_parts = item.relative_to(root).parts
        except ValueError:
            continue
        # Only skip hidden/system folders *inside* the chosen folder. The folder's own
        # path may sit under a dot-directory (C:\Users\x\.local\...), which is not ours to skip.
        if any(part in _skip or part.startswith(".") for part in rel_parts):
            continue
        if not item.is_file():
            continue

        size = item.stat().st_size
        suffix = item.suffix.lower()
        rel = str(item.relative_to(root))
        kind = _detect_kind(item)

        collected.append({
            "name": item.name,
            "path": str(item.resolve()),
            "relative_path": rel,
            "size": size,
            "size_formatted": _format_size(size),
            "extension": suffix,
            "kind": kind,
        })

        if len(collected) >= max_files:
            break

    return {
        "ok": True,
        "folder_path": str(root),
        "folder_name": root.name,
        "files": collected,
        "total_files": len(collected),
    }
