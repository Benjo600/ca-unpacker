"""Pre-flight gate that runs *before* a pack is written.

The gate answers one question in two tiers:

``blocking``
    The period cannot be packed at all: there is nothing usable to pack, or
    the output folder cannot be written. The pipeline stops, no workbook and
    no summary is produced, and any pack already on disk is left untouched.

``warning``
    The pack can be produced, but the CA must be told exactly what is wrong
    and how many rows are affected. Every warning carries a count and a short
    list of sample references (file + row) so the problem can be found.

The report only *describes* what it found. It never edits, drops or repairs
rows - a CA decides what to do with the finding.

Both tiers are plain data (no openpyxl, no ORM), so they can be unit tested
and serialised to ``pack_summary.json`` without touching the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from apps.engine.library import init_library
from apps.engine.validators.gstin import gstin_flags

BLOCKING = "blocking"
WARNING = "warning"
LEVELS = (BLOCKING, WARNING)

#: How many sample references an issue keeps. The count is always the full
#: number of affected rows; samples are only there to make it findable.
SAMPLE_LIMIT = 5

#: Same rupee tolerance the balance and invoice checks already use.
MONEY_TOLERANCE = Decimal("1.00")

GSTIN_KEYS = (
    "supplier_gstin",
    "gstin",
    "party_gstin",
    "customer_gstin",
    "recipient_gstin",
)
DATE_KEYS = ("invoice_date", "date", "voucher_date")
HSN_KEYS = ("hsn", "hsn_code", "hsn_sac")
TAX_KEYS = ("tax", "total_tax")
TAX_PARTS = ("igst", "cgst", "sgst", "cess")
SUMMARY_TYPES = {"HSN", "SUMMARY", "DOC_ISSUE"}

#: Registers whose rows are invoices (so GSTIN, date and total are checked).
#: ``books`` and ``GSTR-3B`` are deliberately excluded: books repeat the same
#: vouchers the registers already hold, and 3B rows are section totals.
INVOICE_REGISTERS = frozenset({"purchase register", "sales register", "GSTR-1", "GSTR-2B"})
#: HSN lives on the invoice line, so line items are checked as well.
HSN_REGISTERS = INVOICE_REGISTERS | {"line items"}
DUPLICATE_REGISTERS = frozenset({"purchase register", "sales register", "GSTR-2B"})

REPORTS_FOLDER = "reports"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any, limit: int = 200) -> str:
    if value is None:
        return ""
    cleaned = " ".join(str(value).split())
    return cleaned[:limit]


def _number(value: Any) -> Decimal | None:
    """Return a Decimal for a money-ish cell, or None when it is not a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    raw = str(value).strip().replace(",", "").replace("\u20b9", "").replace(" ", "")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _fact(item: Any, key: str) -> Any:
    """Read a fact from a mapping *or* an object (the pipeline passes ORM rows)."""
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _first_value(row: Mapping, keys: Iterable[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _row_file(row: Mapping) -> str:
    for key in ("source", "file", "filename", "original_name"):
        text = _text(row.get(key), 120)
        if text:
            return text.split("#", 1)[0].strip()
    return ""


def _is_summary_row(row: Mapping) -> bool:
    """GSTR-1 HSN summaries and 3B sections are totals, not invoices."""
    if _text(row.get("section")):
        return True
    return _text(row.get("document_type")).upper().split(" ")[0] in SUMMARY_TYPES


def _register_is_date_checked(label: str) -> bool:
    return label in INVOICE_REGISTERS


@dataclass(frozen=True)
class PreflightSample:
    """One place a CA can look to see the problem for themselves."""

    file: str = ""
    row: int | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {"file": self.file, "row": self.row, "detail": self.detail}

    def text(self) -> str:
        label = self.file or "unknown source"
        if self.row:
            label = f"{label} \u00b7 row {self.row}"
        if self.detail:
            label = f"{label} \u00b7 {self.detail}"
        return label


@dataclass(frozen=True)
class PreflightIssue:
    """A single finding. ``count`` is how many rows/files it covers."""

    level: str
    code: str
    message: str
    count: int = 0
    samples: tuple[PreflightSample, ...] = ()

    @property
    def blocking(self) -> bool:
        return self.level == BLOCKING

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "count": self.count,
            "samples": [sample.to_dict() for sample in self.samples],
        }


@dataclass(frozen=True)
class PreflightReport:
    """Everything the gate found, split into blocking findings and warnings."""

    issues: tuple[PreflightIssue, ...] = ()
    generated_at: str = ""

    @property
    def blocking(self) -> list[PreflightIssue]:
        return [issue for issue in self.issues if issue.level == BLOCKING]

    @property
    def warnings(self) -> list[PreflightIssue]:
        return [issue for issue in self.issues if issue.level == WARNING]

    @property
    def ok(self) -> bool:
        return not self.blocking

    @property
    def blocked(self) -> bool:
        return bool(self.blocking)

    @property
    def counts(self) -> dict:
        return {"blocking": len(self.blocking), "warnings": len(self.warnings)}

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "counts": self.counts,
            "blocking": [issue.to_dict() for issue in self.blocking],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping | None) -> "PreflightReport | None":
        if not isinstance(data, Mapping):
            return None
        raw_issues = data.get("issues")
        if raw_issues is None:
            raw_issues = list(data.get("blocking") or []) + list(data.get("warnings") or [])
        issues: list[PreflightIssue] = []
        for item in raw_issues:
            if not isinstance(item, Mapping):
                continue
            level = _text(item.get("level")).lower()
            if level not in LEVELS:
                continue
            samples = tuple(
                PreflightSample(
                    file=_text(sample.get("file"), 160),
                    row=_optional_int(sample.get("row")),
                    detail=_text(sample.get("detail")),
                )
                for sample in (item.get("samples") or [])
                if isinstance(sample, Mapping)
            )
            issues.append(
                PreflightIssue(
                    level=level,
                    code=_text(item.get("code"), 80),
                    message=_text(item.get("message"), 400),
                    count=_optional_int(item.get("count")) or 0,
                    samples=samples,
                )
            )
        return cls(issues=tuple(issues), generated_at=_text(data.get("generated_at"), 40))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_preflight(
    *,
    files: Sequence[Any] = (),
    bank_files: Sequence[Mapping] = (),
    purchase_rows: Sequence[Mapping] = (),
    sales_rows: Sequence[Mapping] = (),
    gstr_1: Sequence[Mapping] = (),
    gstr_2b: Sequence[Mapping] = (),
    gstr_3b: Sequence[Mapping] = (),
    books_rows: Sequence[Mapping] = (),
    line_item_rows: Sequence[Mapping] = (),
    dest_dir: str | Path | None = None,
    destination_error: str | None = None,
) -> PreflightReport:
    """Inspect the material the pipeline already parsed and report on it.

    ``files`` may hold ``StoredFile`` rows or plain mappings; everything else
    is a sequence of parsed row mappings. ``dest_dir`` is probed for writability
    (a probe file is written and removed) unless ``destination_error`` already
    records that the folder could not even be created.
    """
    registers: list[tuple[str, Sequence[Mapping]]] = [
        ("purchase register", purchase_rows),
        ("sales register", sales_rows),
        ("GSTR-1", gstr_1),
        ("GSTR-2B", gstr_2b),
        ("GSTR-3B", gstr_3b),
        ("books", books_rows),
        ("line items", line_item_rows),
    ]
    usable = _usable_row_count(
        bank_files=bank_files,
        registers=registers,
    )

    issues: list[PreflightIssue] = []

    destination_issue = _destination_issue(dest_dir, destination_error)
    if destination_issue is not None:
        issues.append(destination_issue)

    # Blocking: nothing at all to pack.
    if usable == 0:
        issues.append(
            PreflightIssue(
                level=BLOCKING,
                code="no_usable_rows",
                message=(
                    "This period has no usable rows, so nothing was packed. "
                    "Add or fix the client's files and run the pack again."
                ),
                count=0,
                samples=_file_samples(files),
            )
        )

    issues.extend(_gstin_issues(registers))
    issues.extend(_hsn_issues(registers))
    issues.extend(_date_issues(registers))
    issues.extend(_invoice_math_issues(registers))
    issues.extend(_duplicate_invoice_issues(registers))
    issues.extend(_unparsed_file_issues(files))
    issues.extend(_bank_issues(bank_files))

    return PreflightReport(issues=tuple(issues), generated_at=_now())


# --- rules -----------------------------------------------------------------


def _usable_row_count(*, bank_files: Sequence[Mapping], registers) -> int:
    total = 0
    for item in bank_files:
        check = item.get("check") or {}
        rows = item.get("rows") or []
        counted = _optional_int(check.get("row_count"))
        total += counted if counted is not None else len(rows)
    for _label, rows in registers:
        total += _row_count(rows)
    return total


def _row_count(rows: Sequence[Mapping] | None) -> int:
    if not rows:
        return 0
    return sum(1 for row in rows if isinstance(row, Mapping))


def _file_samples(files: Sequence[Any]) -> tuple[PreflightSample, ...]:
    samples: list[PreflightSample] = []
    for item in files:
        name = _text(_fact(item, "original_name") or _fact(item, "name") or _fact(item, "file"), 160)
        if not name:
            continue
        samples.append(
            PreflightSample(
                file=name,
                detail=_text(
                    _fact(item, "parse_reason_message") or _fact(item, "classify_reason"), 120
                ),
            )
        )
        if len(samples) >= SAMPLE_LIMIT:
            break
    return tuple(samples)


def _gstin_issues(registers) -> list[PreflightIssue]:
    found: dict[str, int] = {"gstin_format": 0, "gstin_checksum": 0}
    samples: dict[str, list[PreflightSample]] = {"gstin_format": [], "gstin_checksum": []}
    for label, rows in registers:
        if label not in INVOICE_REGISTERS:
            continue
        for index, row in _iter_rows(rows):
            value = _first_value(row, GSTIN_KEYS)
            if not value:
                continue
            for flag in gstin_flags(value):
                if flag not in found:
                    continue
                found[flag] += 1
                if len(samples[flag]) < SAMPLE_LIMIT:
                    samples[flag].append(
                        PreflightSample(
                            file=_row_file(row),
                            row=index,
                            detail=f"{value} in {label}",
                        )
                    )
    issues: list[PreflightIssue] = []
    if found["gstin_format"]:
        issues.append(
            PreflightIssue(
                level=WARNING,
                code="gstin_format",
                message=(
                    "GSTIN format is wrong (not 15 characters in the standard pattern) on "
                    f"{found['gstin_format']} {_rows_word(found['gstin_format'])}."
                ),
                count=found["gstin_format"],
                samples=tuple(samples["gstin_format"]),
            )
        )
    if found["gstin_checksum"]:
        issues.append(
            PreflightIssue(
                level=WARNING,
                code="gstin_checksum",
                message=(
                    "GSTIN check digit does not match the rest of the number on "
                    f"{found['gstin_checksum']} {_rows_word(found['gstin_checksum'])}."
                ),
                count=found["gstin_checksum"],
                samples=tuple(samples["gstin_checksum"]),
            )
        )
    return issues


def _hsn_issues(registers) -> list[PreflightIssue]:
    checked = HSN_REGISTERS
    count = 0
    samples: list[PreflightSample] = []
    for label, rows in registers:
        if label not in checked:
            continue
        for index, row in _iter_rows(rows):
            if _first_value(row, HSN_KEYS):
                continue
            count += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append(
                    PreflightSample(
                        file=_row_file(row),
                        row=index,
                        detail=(
                            f"invoice {_text(row.get('invoice_number'), 40)} in {label}"
                            if _text(row.get("invoice_number"))
                            else label
                        ),
                    )
                )
    if not count:
        return []
    return [
        PreflightIssue(
            level=WARNING,
            code="hsn_missing",
            message=f"Missing HSN code on {count} {_rows_word(count)}.",
            count=count,
            samples=tuple(samples),
        )
    ]


def _date_issues(registers) -> list[PreflightIssue]:
    count = 0
    samples: list[PreflightSample] = []
    for label, rows in registers:
        if not _register_is_date_checked(label):
            continue
        for index, row in _iter_rows(rows):
            if _is_summary_row(row):
                continue
            if _first_value(row, DATE_KEYS):
                continue
            count += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append(
                    PreflightSample(
                        file=_row_file(row),
                        row=index,
                        detail=(
                            f"invoice {_text(row.get('invoice_number'), 40)} in {label}"
                            if _text(row.get("invoice_number"))
                            else label
                        ),
                    )
                )
    if not count:
        return []
    return [
        PreflightIssue(
            level=WARNING,
            code="missing_date",
            message=f"No date on {count} {_rows_word(count)}.",
            count=count,
            samples=tuple(samples),
        )
    ]


def _invoice_math_issues(registers) -> list[PreflightIssue]:
    checked = INVOICE_REGISTERS
    count = 0
    samples: list[PreflightSample] = []
    for label, rows in registers:
        if label not in checked:
            continue
        for index, row in _iter_rows(rows):
            if _is_summary_row(row):
                continue
            total = _number(row.get("invoice_value"))
            taxable = _number(row.get("taxable_value"))
            if taxable is None:
                taxable = _number(row.get("taxable"))
            tax = _row_tax(row)
            if total is None or taxable is None or tax is None:
                continue
            if (total - (taxable + tax)).copy_abs() <= MONEY_TOLERANCE:
                continue
            count += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append(
                    PreflightSample(
                        file=_row_file(row),
                        row=index,
                        detail=(
                            f"invoice value {total} vs taxable + tax {taxable + tax}"
                            f" in {label}"
                        ),
                    )
                )
    if not count:
        return []
    return [
        PreflightIssue(
            level=WARNING,
            code="invoice_math",
            message=(
                "Invoice value is not taxable value plus tax on "
                f"{count} {_rows_word(count)}."
            ),
            count=count,
            samples=tuple(samples),
        )
    ]


def _row_tax(row: Mapping) -> Decimal | None:
    for key in TAX_KEYS:
        value = _number(row.get(key))
        if value is not None:
            return value
    parts = [_number(row.get(key)) for key in TAX_PARTS]
    if all(part is None for part in parts):
        return None
    return sum((part for part in parts if part is not None), Decimal("0"))


def _duplicate_invoice_issues(registers) -> list[PreflightIssue]:
    checked = DUPLICATE_REGISTERS
    count = 0
    samples: list[PreflightSample] = []
    for label, rows in registers:
        if label not in checked:
            continue
        groups: dict[str, list[tuple[int, Mapping]]] = {}
        for index, row in _iter_rows(rows):
            number = _text(row.get("invoice_number"), 60)
            if not number:
                continue
            groups.setdefault(number.upper(), []).append((index, row))
        for number, group in groups.items():
            if len(group) < 2:
                continue
            count += len(group) - 1
            if len(samples) < SAMPLE_LIMIT:
                second_row, row = group[1]
                samples.append(
                    PreflightSample(
                        file=_row_file(row),
                        row=second_row,
                        detail=f"{number} appears {len(group)} times in the {label}",
                    )
                )
    if not count:
        return []
    return [
        PreflightIssue(
            level=WARNING,
            code="duplicate_invoice",
            message=(
                f"{count} {_rows_word(count)} repeat an invoice number already used in the "
                "same register."
            ),
            count=count,
            samples=tuple(samples),
        )
    ]


def _unparsed_file_issues(files: Sequence[Any]) -> list[PreflightIssue]:
    count = 0
    samples: list[PreflightSample] = []
    for item in files:
        outcome = _text(_fact(item, "parse_outcome")).lower()
        reason_code = _text(_fact(item, "parse_reason_code")).lower()
        kind = _text(
            _fact(item, "kind")
            or _fact(item, "override_kind")
            or _fact(item, "detected_kind")
        ).lower()
        reason = _text(_fact(item, "parse_reason_message") or _fact(item, "classify_reason"), 160)
        needs_review = bool(_fact(item, "needs_review"))
        problem = (
            outcome in {"failed", "needs_review", "unclassified"}
            or kind in {"", "unknown"}
            or needs_review
            or reason_code
            in {"parser_error", "no_rows", "copy_failed", "source_missing", "password_required"}
            or reason.lower().startswith("could not parse")
        )
        if not problem:
            continue
        count += 1
        if len(samples) < SAMPLE_LIMIT:
            samples.append(
                PreflightSample(
                    file=_text(_fact(item, "original_name") or _fact(item, "name"), 160),
                    detail=reason,
                )
            )
    if not count:
        return []
    return [
        PreflightIssue(
            level=WARNING,
            code="file_unparsed",
            message=(
                f"{count} {_files_word(count)} were skipped or produced no rows. "
                "The reason for each one is listed here."
            ),
            count=count,
            samples=tuple(samples),
        )
    ]


def _bank_issues(bank_files: Sequence[Mapping]) -> list[PreflightIssue]:
    count = 0
    samples: list[PreflightSample] = []
    for item in bank_files:
        check = item.get("check") or {}
        status = _text(check.get("status")).lower()
        if status in {"", "match"}:
            continue
        meta = item.get("meta") or {}
        name = _text(meta.get("filename") or _fact(item, "filename"), 160)
        if status == "mismatch":
            detail = "balance did not reconcile"
        elif status == "unverified":
            detail = "balance could not be verified"
        else:
            detail = f"balance status {status}"
        flags = [str(flag) for flag in (check.get("flags") or []) if str(flag).strip()]
        if flags:
            detail = f"{detail} ({', '.join(flags)})"
        count += 1
        if len(samples) < SAMPLE_LIMIT:
            samples.append(
                PreflightSample(
                    file=name,
                    row=_optional_int(check.get("broken_at_row")),
                    detail=detail,
                )
            )
    if not count:
        return []
    return [
        PreflightIssue(
            level=WARNING,
            code="bank_unreconciled",
            message=(
                f"{count} bank {_statements_word(count)} did not reconcile the opening balance, "
                "the running balance and the closing balance."
            ),
            count=count,
            samples=tuple(samples),
        )
    ]


def _destination_issue(
    dest_dir: str | Path | None, destination_error: str | None
) -> PreflightIssue | None:
    message = (
        "The output folder cannot be written to, so nothing was packed. "
        "Choose a folder you can write to and run the pack again."
    )
    if destination_error:
        return PreflightIssue(
            level=BLOCKING,
            code="destination_unwritable",
            message=message,
            count=1,
            samples=(PreflightSample(file=str(dest_dir or ""), detail=_text(destination_error, 200)),),
        )
    if dest_dir is None:
        return None
    folder = Path(dest_dir)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".ca_unpacker_preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        try:
            probe.unlink()
        except OSError:
            pass
    except OSError as exc:
        return PreflightIssue(
            level=BLOCKING,
            code="destination_unwritable",
            message=message,
            count=1,
            samples=(PreflightSample(file=str(folder), detail=_text(str(exc), 200)),),
        )
    return None


def _iter_rows(rows: Sequence[Mapping] | None):
    if not rows:
        return
    for index, row in enumerate(rows, start=1):
        if isinstance(row, Mapping):
            yield index, row


def _rows_word(count: int) -> str:
    return "row" if count == 1 else "rows"


def _files_word(count: int) -> str:
    return "file" if count == 1 else "files"


def _statements_word(count: int) -> str:
    return "statement" if count == 1 else "statements"


# --- persistence -----------------------------------------------------------


def report_path(period_id: int) -> Path:
    """Where the latest pre-flight report for a period is kept."""
    return init_library() / REPORTS_FOLDER / f"preflight_period_{int(period_id)}.json"


def save_report(period_id: int, report: PreflightReport) -> Path:
    path = report_path(period_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def load_report(period_id: int) -> PreflightReport | None:
    path = report_path(period_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return PreflightReport.from_dict(data)
