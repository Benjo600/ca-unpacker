from __future__ import annotations

import json
from pathlib import Path

from apps.engine.db import Client, DataPack, ExtractedRow, Period, StoredFile, get_session
from apps.engine.library import packs_root, resolve_storage_key
from apps.engine.settings import period_output_dir
from apps.engine.pack.bank_xlsx import write_bank_workbook
from apps.engine.pack.table_xlsx import write_table
from apps.engine.parsers.bank.parser import parse_bank_pdf
from apps.engine.parsers.gstr import parse_gstr_file
from apps.engine.parsers.invoice import parse_invoice_file
from apps.engine.parsers.tally import parse_tally_file
from apps.engine.parsers.zoho import parse_zoho_file
from apps.engine.validators.balance import check_balance

PURCHASE_COLS = [
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
    ("HSN", "hsn"),
    ("Flags", "flags"),
    ("Source", "source"),
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
        session.query(ExtractedRow).filter(ExtractedRow.period_id == period_id).delete()
        session.commit()

        bank_files: list[dict] = []
        purchase_rows: list[dict] = []
        books_rows: list[dict] = []
        gstr_1: list[dict] = []
        gstr_2b: list[dict] = []
        gstr_3b: list[dict] = []

        for stored in files:
            kind = file_kind(stored)
            if not stored.storage_key:
                continue
            path = resolve_storage_key(stored.storage_key)
            if not path.exists():
                continue
            rows, extra = _dispatch(path, kind, stored.original_name)
            for row in rows:
                session.add(
                    ExtractedRow(
                        file_id=stored.id,
                        period_id=period_id,
                        kind=kind,
                        payload_json=json.dumps(row),
                        source_page=int(row.get("source_page") or 1),
                        source_bbox=row.get("source_bbox"),
                        validation_flags=json.dumps(row.get("flags") or []),
                    )
                )
            if kind == "bank":
                bank_files.append(
                    {
                        "file_id": stored.id,
                        "rows": rows,
                        "check": extra["check"],
                        "meta": extra["meta"],
                    }
                )
            elif kind == "invoice":
                purchase_rows.extend(rows)
            elif kind == "gstr_1":
                gstr_1.extend(rows)
            elif kind == "gstr_2b":
                gstr_2b.extend(rows)
            elif kind == "gstr_3b":
                gstr_3b.extend(rows)
            elif kind in {"tally", "zoho"}:
                books_rows.extend(rows)

        period = session.get(Period, period_id)
        client = session.get(Client, period.client_id) if period else None
        dest_dir = period_output_dir(
            client.name if client else "Client",
            period.label if period else f"period-{period_id}",
        )
        outputs: list[dict] = []

        if bank_files:
            dest = dest_dir / "Bank_Statement_Cleaned.xlsx"
            write_bank_workbook(dest, bank_files)
            all_match = all(item["check"].get("match") for item in bank_files)
            outputs.append(
                {
                    "key": "bank",
                    "label": "Bank_Statement_Cleaned.xlsx",
                    "path": str(dest),
                    "rows": sum(item["check"]["row_count"] for item in bank_files),
                    "status": "match" if all_match else "mismatch",
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

        if purchase_rows:
            dest = dest_dir / "Purchase_Register_Extracted.xlsx"
            write_table(dest, "Purchase register", purchase_rows, PURCHASE_COLS)
            outputs.append(_simple_out("purchase", dest.name, dest, len(purchase_rows)))

        if gstr_2b:
            dest = dest_dir / "GSTR_2B_Formatted.xlsx"
            write_table(dest, "GSTR-2B", gstr_2b, GSTR_INV_COLS)
            outputs.append(_simple_out("gstr_2b", dest.name, dest, len(gstr_2b)))

        if gstr_1:
            dest = dest_dir / "GSTR_1_Formatted.xlsx"
            write_table(dest, "GSTR-1", gstr_1, GSTR_INV_COLS)
            outputs.append(_simple_out("gstr_1", dest.name, dest, len(gstr_1)))

        if gstr_3b:
            dest = dest_dir / "GSTR_3B_Formatted.xlsx"
            write_table(dest, "GSTR-3B", gstr_3b, GSTR_3B_COLS)
            outputs.append(_simple_out("gstr_3b", dest.name, dest, len(gstr_3b)))

        if books_rows:
            dest = dest_dir / "Books_Register_Extracted.xlsx"
            write_table(dest, "Books", books_rows, BOOKS_COLS)
            outputs.append(_simple_out("books", dest.name, dest, len(books_rows)))

        total_rows = sum(item["rows"] for item in outputs)
        bank_status = next((item["status"] for item in outputs if item["key"] == "bank"), None)
        summary = {"outputs": outputs, "total_rows": total_rows, "folder": str(dest_dir)}
        (dest_dir / "pack_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

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


def _simple_out(key: str, label: str, dest: Path, rows: int) -> dict:
    return {
        "key": key,
        "label": label,
        "path": str(dest),
        "rows": rows,
        "status": "ready",
        "files": [],
    }


def _dispatch(path: Path, kind: str, filename: str) -> tuple[list[dict], dict]:
    if kind == "bank":
        parsed = parse_bank_pdf(path, filename)
        check = check_balance(
            parsed["rows"], parsed.get("opening_balance"), parsed.get("stated_closing")
        )
        meta = {
            "filename": filename,
            "profile_label": parsed.get("profile_label"),
            "engine": parsed.get("engine"),
            "page_count": parsed.get("page_count"),
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
        if summary is None and pack is None:
            return None
        if pack is None:
            return {
                "id": None,
                "period_id": period_id,
                "path": str(summary_path.parent),
                "exists": True,
                "outputs": (summary or {}).get("outputs") or [],
                "row_count": (summary or {}).get("total_rows") or 0,
                "files": [],
                "balance_status": None,
            }
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
    return {
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
