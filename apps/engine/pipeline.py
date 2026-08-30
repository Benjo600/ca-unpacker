from __future__ import annotations

import base64
import hashlib
import inspect
import json
from pathlib import Path

from apps.engine.db import Client, DataPack, ExtractedRow, Period, StoredFile, get_session
from apps.engine.kinds import IMAGE_SUFFIXES, KIND_LABELS
from apps.engine.library import init_library, resolve_storage_key
from apps.engine.outcomes import (
    evaluate_file_outcome,
    failed_file_outcome,
    persist_file_outcome,
)
from apps.engine.pdf_passwords import get_file_password, redact_known_passwords
from apps.engine.settings import period_output_dir
from apps.engine.pack.bank_xlsx import write_bank_workbook
from apps.engine.pack.gstr_xlsx import write_gstr_1, write_gstr_2b, write_gstr_3b
from apps.engine.pack.recon_xlsx import write_master_grid
from apps.engine.pack.table_xlsx import write_purchase_workbook, write_table
from apps.engine.recon import reconcile
from apps.engine.parsers.bank.parser import parse_bank_pdf
from apps.engine.parsers.gstr import parse_gstr_file
from apps.engine.parsers.invoice import parse_invoice_file
from apps.engine.parsers.tally import parse_tally_file
from apps.engine.parsers.zoho import parse_zoho_file
from apps.engine.validators.balance import check_balance

PURCHASE_COLS = [
    ("Supplier", "supplier_name"),
    ("Supplier GSTIN", "supplier_gstin"),
    ("Invoice no", "invoice_number"),
    ("Date", "invoice_date"),
    ("Taxable", "taxable_value"),
    ("Tax", "tax"),
    ("Invoice value", "invoice_value"),
    ("HSN", "hsn"),
    ("Flags", "flags"),
    ("Source", "source"),
]
SALES_COLS = [
    ("Party", "supplier_name"),
    ("Party GSTIN", "supplier_gstin"),
    ("Invoice no", "invoice_number"),
    ("Date", "invoice_date"),
    ("Taxable", "taxable_value"),
    ("Tax", "tax"),
    ("Invoice value", "invoice_value"),
    ("HSN", "hsn"),
    ("Flags", "flags"),
    ("Source", "source"),
]
GSTR_INV_COLS = [
    ("GSTIN", "gstin"),
    ("Trade name", "trade_name"),
    ("Invoice no", "invoice_number"),
    ("Date", "invoice_date"),
    ("Value", "invoice_value"),
    ("Taxable", "taxable"),
    ("IGST", "igst"),
    ("CGST", "cgst"),
    ("SGST", "sgst"),
    ("Cess", "cess"),
    ("ITC", "itc_availability"),
    ("Type", "document_type"),
    ("Flags", "flags"),
    ("Source", "source"),
    ("Match", "match_status"),
    ("Books ref", "books_ref"),
]
GSTR_3B_COLS = [
    ("Section", "section"),
    ("Taxable", "taxable"),
    ("IGST", "igst"),
    ("CGST", "cgst"),
    ("SGST", "sgst"),
    ("Cess", "cess"),
    ("Source", "source"),
]
LINE_COLS = [
    ("Invoice no", "invoice_number"),
    ("Description", "description"),
    ("HSN", "hsn"),
    ("Qty", "qty"),
    ("Rate", "rate"),
    ("Taxable", "taxable"),
    ("Tax", "tax"),
    ("Amount", "amount"),
    ("Source", "source"),
]
REVIEW_COLS = [
    ("File", "file"),
    ("Detected type", "kind_label"),
    ("Status", "status"),
    ("Reason", "reason"),
]
BOOKS_COLS = [
    ("Type", "voucher_type"),
    ("Number", "voucher_number"),
    ("Date", "date"),
    ("Party", "party_name"),
    ("GSTIN", "gstin"),
    ("Amount", "amount"),
    ("Invoice no", "invoice_number"),
    ("Invoice value", "invoice_value"),
    ("Flags", "flags"),
    ("Source", "source"),
]


def file_kind(row: StoredFile) -> str:
    return row.override_kind or row.detected_kind


def parse_period_banks(period_id: int, job_id: int | None = None) -> dict | None:
    return parse_period(period_id, job_id)


def parse_period(period_id: int, job_id: int | None = None) -> dict | None:
    session = get_session()
    try:
        files = (
            session.query(StoredFile)
            .filter(StoredFile.period_id == period_id)
            .order_by(StoredFile.id.asc())
            .all()
        )
        pending_extracted: list[dict] = []

        bank_files: list[dict] = []
        purchase_rows: list[dict] = []
        line_item_rows: list[dict] = []
        sales_rows: list[dict] = []
        books_rows: list[dict] = []
        gstr_1: list[dict] = []
        gstr_2b: list[dict] = []
        gstr_3b: list[dict] = []

        for stored in files:
            kind = file_kind(stored)
            if not stored.storage_key:
                persist_file_outcome(
                    stored,
                    failed_file_outcome(
                        "copy_failed",
                        stored.classify_reason or "The file could not be copied into the library.",
                    ),
                )
                session.commit()
                continue
            path = resolve_storage_key(stored.storage_key)
            if not path.exists():
                persist_file_outcome(
                    stored,
                    failed_file_outcome(
                        "source_missing", "The stored source file is missing."
                    ),
                )
                session.commit()
                continue
            if kind == "unknown":
                persist_file_outcome(
                    stored,
                    evaluate_file_outcome(
                        kind=kind,
                        rows=[],
                        parser_metadata={},
                        classification_reason=stored.classify_reason,
                    ),
                )
                session.commit()
                continue
            try:
                rows, extra = _dispatch_stored(stored, path, kind)
            except Exception as exc:
                message = _redact_secret(str(exc), stored.id)
                stored.classify_reason = f"could not parse: {message[:200]}"
                persist_file_outcome(
                    stored,
                    failed_file_outcome("parser_error", message, kind=kind),
                )
                session.commit()
                continue
            if kind == "invoice":
                items = extra.get("line_items") or []
                if extra.get("unreadable") or not rows or not items:
                    reason = stored.classify_reason or ""
                    if "password" not in reason.lower():
                        if extra.get("unreadable") or not items:
                            stored.classify_reason = "recognised as invoice but no line items"
                        else:
                            stored.classify_reason = "recognised as invoice but no rows extracted"
                    rows = []
                    items = []
                else:
                    line_item_rows.extend(items)
                    for item in items:
                        pending_extracted.append(
                            {
                                "file_id": stored.id,
                                "period_id": period_id,
                                "kind": "invoice",
                                "payload_json": json.dumps(item),
                                "source_page": int(item.get("source_page") or 1),
                                "source_bbox": item.get("source_bbox"),
                                "validation_flags": json.dumps(item.get("flags") or []),
                            }
                        )
            if (
                not rows
                and kind in {"bank", "gstr_1", "gstr_2b", "gstr_3b", "tally", "zoho"}
                and "password" not in (stored.classify_reason or "").lower()
            ):
                stored.classify_reason = f"recognised as {kind} but no rows extracted"
            persist_file_outcome(
                stored,
                evaluate_file_outcome(
                    kind=kind,
                    rows=rows,
                    parser_metadata=extra,
                    classification_reason=stored.classify_reason,
                ),
            )
            for row in rows:
                pending_extracted.append(
                    {
                        "file_id": stored.id,
                        "period_id": period_id,
                        "kind": kind,
                        "payload_json": json.dumps(row),
                        "source_page": int(row.get("source_page") or 1),
                        "source_bbox": row.get("source_bbox"),
                        "validation_flags": json.dumps(row.get("flags") or row.get("validation_flags") or []),
                    }
                )
            if kind == "bank" and extra.get("check") is not None:
                bank_files.append(
                    {
                        "file_id": stored.id,
                        "rows": rows,
                        "check": extra["check"],
                        "meta": extra.get("meta") or {"filename": stored.original_name},
                    }
                )
            elif kind == "invoice":
                if rows:
                    purchase_rows.extend(rows)
            elif kind == "gstr_1":
                gstr_1.extend(rows)
            elif kind == "gstr_2b":
                gstr_2b.extend(rows)
            elif kind == "gstr_3b":
                gstr_3b.extend(rows)
            elif kind in {"tally", "zoho"}:
                books_rows.extend(rows)
                for row in rows:
                    register = _books_register(row, kind)
                    if register == "purchase":
                        purchase_rows.append(_as_register_row(row))
                    elif register == "sales":
                        sales_rows.append(_as_register_row(row))
            session.commit()

        period = session.get(Period, period_id)
        client = session.get(Client, period.client_id) if period else None
        dest_dir = period_output_dir(
            client.name if client else "Client",
            period.label if period else f"period-{period_id}",
        )
        outputs: list[dict] = []
        recon_result = None
        if gstr_2b and purchase_rows:
            bank_txns: list[dict] = []
            for item in bank_files:
                bank_txns.extend(item.get("rows") or [])
            recon_result = reconcile(purchase_rows, gstr_2b, bank_txns)
            _apply_gstr_2b_matches(gstr_2b, recon_result)

        if bank_files:
            dest = dest_dir / "Bank_Statement_Cleaned.xlsx"
            write_bank_workbook(dest, bank_files)
            all_match = all(item["check"].get("status") == "match" for item in bank_files)
            if any(item["check"].get("status") == "mismatch" for item in bank_files):
                bank_pack_status = "mismatch"
            elif any(item["check"].get("status") == "unverified" for item in bank_files):
                bank_pack_status = "unverified"
            else:
                bank_pack_status = "match" if all_match else "mismatch"
            outputs.append(
                {
                    "key": "bank",
                    "label": "Bank_Statement_Cleaned.xlsx",
                    "path": str(dest),
                    "rows": sum(item["check"]["row_count"] for item in bank_files),
                    "status": bank_pack_status,
                    "files": [
                        {
                            "filename": item["meta"]["filename"],
                            "row_count": item["check"]["row_count"],
                            "status": item["check"]["status"],
                            "opening_balance": item["check"].get("opening_balance"),
                            "stated_closing": item["check"].get("stated_closing"),
                            "computed_closing": item["check"].get("computed_closing"),
                        }
                        for item in bank_files
                    ],
                }
            )

        if purchase_rows and line_item_rows:
            dest = dest_dir / "Purchase_Register_Extracted.xlsx"
            write_purchase_workbook(dest, purchase_rows, line_item_rows, PURCHASE_COLS, LINE_COLS)
            outputs.append(_simple_out("purchase", dest.name, dest, len(purchase_rows)))
        elif purchase_rows:
            dest = dest_dir / "Purchase_Register_Extracted.xlsx"
            write_table(dest, "Purchase register", purchase_rows, PURCHASE_COLS)
            outputs.append(_simple_out("purchase", dest.name, dest, len(purchase_rows)))

        review_rows = _review_rows(files)
        if review_rows:
            dest = dest_dir / "Needs_Review.xlsx"
            write_table(dest, "Needs review", review_rows, REVIEW_COLS)
            outputs.append(_simple_out("needs_review", dest.name, dest, len(review_rows)))

        if sales_rows:
            dest = dest_dir / "Sales_Register_Extracted.xlsx"
            write_table(dest, "Sales register", sales_rows, SALES_COLS)
            outputs.append(_simple_out("sales", dest.name, dest, len(sales_rows)))

        gstr_meta = {
            "gstin": client.gstin if client else None,
            "period": period.label if period else None,
        }
        if gstr_2b:
            dest = dest_dir / "GSTR_2B_Formatted.xlsx"
            write_gstr_2b(dest, gstr_2b, gstr_meta)
            outputs.append(_simple_out("gstr_2b", dest.name, dest, len(gstr_2b)))

        if gstr_1:
            dest = dest_dir / "GSTR_1_Formatted.xlsx"
            write_gstr_1(dest, gstr_1, gstr_meta)
            outputs.append(_simple_out("gstr_1", dest.name, dest, len(gstr_1)))

        if gstr_3b:
            dest = dest_dir / "GSTR_3B_Formatted.xlsx"
            write_gstr_3b(dest, gstr_3b, gstr_meta)
            outputs.append(_simple_out("gstr_3b", dest.name, dest, len(gstr_3b)))

        if books_rows:
            dest = dest_dir / "Books_Register_Extracted.xlsx"
            write_table(dest, "Books", books_rows, BOOKS_COLS)
            outputs.append(_simple_out("books", dest.name, dest, len(books_rows)))

        if recon_result is not None:
            dest = dest_dir / "Master_Reconciliation_Grid.xlsx"
            write_master_grid(dest, recon_result)
            outputs.append(
                _simple_out("master", dest.name, dest, len(recon_result.get("rows") or []))
            )

        total_rows = sum(item["rows"] for item in outputs)
        bank_status = next((item["status"] for item in outputs if item["key"] == "bank"), None)
        summary = {"outputs": outputs, "total_rows": total_rows, "folder": str(dest_dir)}
        if recon_result is not None:
            summary["recon"] = {
                "counts": recon_result.get("counts") or {},
                "rows": recon_result.get("rows") or [],
            }
        (dest_dir / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        session.query(ExtractedRow).filter(ExtractedRow.period_id == period_id).delete()
        for spec in pending_extracted:
            session.add(ExtractedRow(**spec))

        session.query(DataPack).filter(DataPack.period_id == period_id).delete()
        if not outputs:
            session.commit()
            return None

        pack = DataPack(
            period_id=period_id,
            job_id=job_id,
            bank_xlsx_key=str(dest_dir / "pack_summary.json"),
            balance_status=bank_status,
            row_count=total_rows,
        )
        session.add(pack)
        session.commit()
        session.refresh(pack)
        return pack_dict(pack, dest_dir / "pack_summary.json", summary)
    finally:
        session.close()


def _books_register(row: dict, kind: str) -> str | None:
    register = str(row.get("register") or "").strip().lower()
    if register in {"purchase", "purchases", "bill", "bills"}:
        return "purchase"
    if register in {"sales", "sale", "invoice", "invoices"}:
        return "sales"
    voucher = str(row.get("voucher_type") or "").strip().lower()
    if "purchase" in voucher or voucher in {"bill", "bills"}:
        return "purchase"
    if "sale" in voucher:
        return "sales"
    # Zoho Books invoice exports have no Tally voucher_type; treat as sales.
    if kind == "zoho":
        return "sales"
    return None


def _as_register_row(row: dict) -> dict:
    mapped = dict(row)
    if not mapped.get("supplier_name"):
        mapped["supplier_name"] = mapped.get("party_name")
    if not mapped.get("supplier_gstin"):
        mapped["supplier_gstin"] = mapped.get("gstin") or mapped.get("party_gstin")
    if not mapped.get("invoice_number"):
        mapped["invoice_number"] = mapped.get("voucher_number")
    if not mapped.get("invoice_date"):
        mapped["invoice_date"] = mapped.get("date")
    if mapped.get("invoice_value") is None:
        mapped["invoice_value"] = mapped.get("amount")
    if mapped.get("taxable_value") is None and mapped.get("taxable") is not None:
        mapped["taxable_value"] = mapped.get("taxable")
    return mapped


def _review_status(stored: StoredFile) -> str | None:
    kind = file_kind(stored)
    reason = (stored.classify_reason or "").lower()
    if "password" in reason:
        return "password"
    if kind == "unknown" and not stored.override_kind:
        return "unknown"
    if "unreadable" in reason or "no line items" in reason:
        return "unreadable"
    if reason.startswith("could not parse") or "no rows extracted" in reason:
        return "no rows"
    return None


def _review_rows(files: list[StoredFile]) -> list[dict]:
    rows: list[dict] = []
    for stored in files:
        status = _review_status(stored)
        if not status:
            continue
        kind = file_kind(stored)
        rows.append(
            {
                "file": stored.original_name,
                "kind_label": KIND_LABELS.get(kind, kind),
                "status": status,
                "reason": stored.classify_reason or "",
            }
        )
    return rows


def _simple_out(key: str, label: str, dest: Path, rows: int) -> dict:
    return {
        "key": key,
        "label": label,
        "path": str(dest),
        "rows": rows,
        "status": "ready",
        "files": [],
    }


def _redact_secret(text: str, file_id: int) -> str:
    password = get_file_password(file_id)
    cleaned = redact_known_passwords((text or "").strip())
    if password and password in cleaned:
        cleaned = cleaned.replace(password, "********")
    if "traceback (most recent call last)" in cleaned.lower():
        return "Could not parse this file."
    return cleaned.splitlines()[0] if cleaned else "Could not parse this file."


def _dispatch_stored(stored: StoredFile, path: Path, kind: str) -> tuple[list[dict], dict]:
    password = get_file_password(stored.id)
    if password:
        try:
            from apps.engine.pdf_extract import using_password
        except Exception:
            using_password = None
        if using_password is not None:
            with using_password(password):
                return _dispatch(path, kind, stored.original_name)
    return _dispatch(path, kind, stored.original_name)


def get_source_crop(file_id: int, page: int, bbox: str | None) -> dict:
    """Resolve StoredFile storage_key and crop a PNG via pdf_render."""
    try:
        from apps.engine import pdf_render
    except Exception:
        return {"ok": False, "error": "Crop is not ready."}

    session = get_session()
    try:
        stored = session.get(StoredFile, int(file_id))
        if stored is None:
            return {"ok": False, "error": "File was not found."}
        if not stored.storage_key:
            return {"ok": False, "error": "The source file is missing."}
        path = resolve_storage_key(stored.storage_key)
        if not path.exists():
            return {"ok": False, "error": "The source file is missing."}
    finally:
        session.close()

    password = get_file_password(int(file_id))
    region = bbox.strip() if isinstance(bbox, str) else (bbox or "")
    dest = _crop_cache_path(int(file_id), int(page), region or None)
    try:
        if path.suffix.lower() in IMAGE_SUFFIXES:
            raw = _call_image_render(pdf_render, path, dest, region)
        else:
            raw = _call_pdf_render(pdf_render, path, dest, int(page), region, password)
    except Exception as exc:
        message = str(exc).strip()
        if message == "Crop is not ready.":
            return {"ok": False, "error": "Crop is not ready."}
        return {"ok": False, "error": _redact_secret(message, int(file_id))[:300] or "Could not crop this page."}
    return _normalize_crop_result(raw, dest, int(file_id))


def _crop_cache_path(file_id: int, page: int, bbox: str | None) -> Path:
    digest = hashlib.sha1(f"{file_id}:{page}:{bbox or ''}".encode("utf-8")).hexdigest()[:16]
    folder = init_library() / "cache" / "crops"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{file_id}_p{page}_{digest}.png"


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _normalize_crop_result(raw, dest: Path, file_id: int) -> dict:
    if isinstance(raw, dict) and ("ok" in raw or "path" in raw or "data_url" in raw):
        if raw.get("ok") is False:
            error = _redact_secret(str(raw.get("error") or "Could not crop this page."), file_id)
            return {"ok": False, "error": error[:300]}
        result = {"ok": True}
        if raw.get("path"):
            result["path"] = str(raw["path"])
        if raw.get("data_url"):
            result["data_url"] = raw["data_url"]
        if "path" not in result and dest.is_file():
            result["path"] = str(dest)
        if "data_url" not in result:
            source = Path(result["path"]) if result.get("path") else dest
            if source.is_file():
                result["data_url"] = _data_url(source.read_bytes())
        return result if result.get("path") or result.get("data_url") else {
            "ok": False,
            "error": "Could not crop this page.",
        }
    if isinstance(raw, (bytes, bytearray)):
        dest.write_bytes(raw)
        return {"ok": True, "path": str(dest), "data_url": _data_url(bytes(raw))}
    if isinstance(raw, Path) or (isinstance(raw, str) and raw):
        source = Path(raw)
        if source.is_file():
            return {"ok": True, "path": str(source), "data_url": _data_url(source.read_bytes())}
    if dest.is_file():
        return {"ok": True, "path": str(dest), "data_url": _data_url(dest.read_bytes())}
    return {"ok": False, "error": "Could not crop this page."}


def _call_image_render(pdf_render, path: Path, dest: Path, bbox: str | None):
    bytes_fn = getattr(pdf_render, "crop_image_png_bytes", None)
    path_fn = getattr(pdf_render, "crop_image_png", None)
    if bytes_fn is None and path_fn is None:
        raise RuntimeError("Crop is not ready.")
    region = bbox or ""
    last_type_error: TypeError | None = None
    if bytes_fn is not None:
        try:
            return bytes_fn(path, region)
        except TypeError as exc:
            last_type_error = exc
            try:
                return _invoke_render(bytes_fn, path=path, bbox=region)
            except TypeError as inner:
                last_type_error = inner
    if path_fn is not None:
        try:
            return path_fn(path, region, dest)
        except TypeError as exc:
            last_type_error = exc
            try:
                return _invoke_render(path_fn, path=path, dest=dest, bbox=region)
            except TypeError as inner:
                last_type_error = inner
    if last_type_error is not None:
        raise last_type_error
    raise RuntimeError("Crop is not ready.")


def _call_pdf_render(pdf_render, path: Path, dest: Path, page: int, bbox: str | None, password: str | None):
    bytes_fn = getattr(pdf_render, "crop_png_bytes", None)
    path_fn = getattr(pdf_render, "crop_png", None)
    if bytes_fn is None and path_fn is None:
        raise RuntimeError("Crop is not ready.")
    region = bbox or ""
    last_type_error: TypeError | None = None
    if bytes_fn is not None:
        try:
            return bytes_fn(path, page, region, password=password)
        except TypeError as exc:
            last_type_error = exc
            try:
                return _invoke_render(bytes_fn, path=path, page=page, bbox=region, password=password)
            except TypeError as inner:
                last_type_error = inner
    if path_fn is not None:
        try:
            return path_fn(path, page, region, dest, password=password)
        except TypeError as exc:
            last_type_error = exc
            try:
                return _invoke_render(
                    path_fn, path=path, dest=dest, page=page, bbox=region, password=password
                )
            except TypeError as inner:
                last_type_error = inner
    if last_type_error is not None:
        raise last_type_error
    raise RuntimeError("Crop is not ready.")


def _invoke_render(fn, **values):
    aliases = {
        "path": ("path", "pdf", "pdf_path", "source", "file_path"),
        "dest": ("dest", "out", "output", "dest_path", "output_path"),
        "page": ("page", "page_number", "pageno"),
        "bbox": ("bbox", "box", "rect", "region"),
        "password": ("password", "pwd", "user_password"),
    }
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        sig = None
    if sig is not None:
        names = [name for name in sig.parameters if name not in {"self", "cls"}]
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
        )
        kwargs = {}
        for key, value in values.items():
            for alias in aliases.get(key, (key,)):
                if alias in sig.parameters:
                    kwargs[alias] = value
                    break
            else:
                if accepts_kwargs and key in values:
                    kwargs[key] = value
        if kwargs:
            return fn(**kwargs)
        args = []
        leftover = dict(values)
        for name in names:
            matched = None
            for key, options in aliases.items():
                if name in options and key in leftover:
                    matched = leftover.pop(key)
                    break
            if matched is None and leftover:
                matched = leftover.pop(next(iter(leftover)))
            if matched is not None:
                args.append(matched)
        return fn(*args)
    if "dest" in values:
        return fn(values["path"], values["dest"], values["page"], values.get("bbox"), values.get("password"))
    return fn(values["path"], values["page"], values.get("bbox"), values.get("password"))


def _dispatch(path: Path, kind: str, filename: str) -> tuple[list[dict], dict]:
    if kind == "bank":
        parsed = parse_bank_pdf(path, filename)
        check = check_balance(
            parsed["rows"], parsed.get("opening_balance"), parsed.get("stated_closing")
        )
        dropped = int(parsed.get("dropped_count") or 0)
        if dropped:
            flags = list(check.get("flags") or [])
            flags.append(f"dropped_lines:{dropped}")
            check["flags"] = flags
        check["candidate_count"] = parsed.get("candidate_count")
        check["dropped_count"] = dropped
        meta = {
            "filename": filename,
            "profile_label": parsed.get("profile_label"),
            "engine": parsed.get("engine"),
            "pdf_type": parsed.get("pdf_type"),
            "page_count": parsed.get("page_count"),
            "account_number": parsed.get("account_number"),
            "ifsc": parsed.get("ifsc"),
        }
        return parsed["rows"], {"check": check, "meta": meta}
    if kind == "invoice":
        parsed = parse_invoice_file(path, filename)
        return parsed["rows"], parsed
    if kind in {"gstr_1", "gstr_2b", "gstr_3b"}:
        parsed = parse_gstr_file(path, kind, filename)
        return parsed["rows"], parsed
    if kind == "tally":
        parsed = parse_tally_file(path, filename)
        return parsed["rows"], parsed
    if kind == "zoho":
        parsed = parse_zoho_file(path, filename)
        return parsed["rows"], parsed
    return [], {}


def get_period_pack(period_id: int) -> dict | None:
    session = get_session()
    try:
        period = session.get(Period, period_id)
        client = session.get(Client, period.client_id) if period else None
        dest_dir = period_output_dir(
            client.name if client else "Client",
            period.label if period else f"period-{period_id}",
        )
        summary_path = dest_dir / "pack_summary.json"
        pack = (
            session.query(DataPack)
            .filter(DataPack.period_id == period_id)
            .order_by(DataPack.id.desc())
            .first()
        )
        summary = _read_summary(summary_path)
        outputs = (summary or {}).get("outputs") or []
        xlsx_exists = any(Path(item.get("path") or "").exists() for item in outputs)
        if not outputs and pack is None:
            return None
        if pack is None:
            payload = {
                "id": None,
                "period_id": period_id,
                "path": str(summary_path.parent),
                "exists": xlsx_exists,
                "outputs": outputs,
                "row_count": (summary or {}).get("total_rows") or 0,
                "files": [],
                "balance_status": None,
            }
            if summary and summary.get("recon") is not None:
                payload["recon"] = summary["recon"]
            return payload
        return pack_dict(pack, summary_path, summary)
    finally:
        session.close()


def get_period_preview(period_id: int, limit: int = 8) -> dict:
    session = get_session()
    try:
        rows = (
            session.query(ExtractedRow, StoredFile)
            .join(StoredFile, ExtractedRow.file_id == StoredFile.id)
            .filter(ExtractedRow.period_id == period_id)
            .order_by(ExtractedRow.id.asc())
            .all()
        )
        grouped: dict[tuple[int, str], dict] = {}
        for extracted, stored in rows:
            key = (stored.id, extracted.kind)
            bucket = grouped.setdefault(
                key,
                {
                    "file_id": stored.id,
                    "filename": stored.original_name,
                    "kind": extracted.kind,
                    "rows": [],
                },
            )
            try:
                payload = json.loads(extracted.payload_json)
            except json.JSONDecodeError:
                payload = {"raw_text": extracted.payload_json}
            if not isinstance(payload, dict):
                payload = {"value": payload}
            else:
                payload = dict(payload)
            payload["row_id"] = extracted.id
            payload["source_page"] = extracted.source_page
            payload["source_bbox"] = extracted.source_bbox
            bucket["rows"].append(payload)
        files = []
        for bucket in grouped.values():
            all_rows = bucket["rows"]
            preview = all_rows[:limit]
            if len(all_rows) > limit * 2:
                preview = all_rows[:limit] + all_rows[-limit:]
            files.append(
                {
                    "file_id": bucket["file_id"],
                    "filename": bucket["filename"],
                    "kind": bucket["kind"],
                    "row_count": len(all_rows),
                    "preview": preview,
                }
            )
        return {"files": files}
    finally:
        session.close()


def pack_dict(pack: DataPack, path: Path, summary: dict | None = None) -> dict:
    outputs = (summary or {}).get("outputs") or []
    bank = next((item for item in outputs if item["key"] == "bank"), None)
    payload = {
        "id": pack.id,
        "period_id": pack.period_id,
        "bank_xlsx_key": pack.bank_xlsx_key,
        "balance_status": pack.balance_status,
        "row_count": pack.row_count,
        "path": str(path.parent if path.suffix == ".json" else path),
        "exists": bool(outputs) or path.exists(),
        "files": (bank or {}).get("files") or [],
        "outputs": outputs,
        "all_match": bank["status"] == "match" if bank else None,
    }
    if summary and summary.get("recon") is not None:
        payload["recon"] = summary["recon"]
    return payload


def _apply_gstr_2b_matches(gstr_2b: list[dict], result: dict) -> None:
    by_source: dict[str, dict] = {}
    for row in result.get("rows") or []:
        source = str(row.get("source_2b") or "")
        if source:
            by_source[source] = row
    for item in gstr_2b:
        rec = by_source.get(str(item.get("source") or ""))
        if rec is None:
            continue
        item["match_status"] = rec.get("status") or ""
        item["books_ref"] = rec.get("invoice_books") or ""


def open_pack_path(period_id: int, key: str | None = None) -> str:
    pack = get_period_pack(period_id)
    if pack is None:
        raise ValueError("No pack for this period yet.")
    outputs = pack.get("outputs") or []
    if key:
        for item in outputs:
            if item["key"] == key:
                return item["path"]
        raise ValueError("That Excel is not in this pack.")
    if outputs:
        return outputs[0]["path"]
    raise ValueError("No pack for this period yet.")


def open_pack_folder(period_id: int) -> str:
    pack = get_period_pack(period_id)
    if pack and pack.get("path"):
        folder = Path(pack["path"])
        if folder.is_file():
            folder = folder.parent
        if folder.exists():
            return str(folder)
    raise ValueError("No pack folder for this period yet.")


def _read_summary(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
