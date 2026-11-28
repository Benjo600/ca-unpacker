"""Deterministic fictional stress corpus for CA Unpacker.

Everything here is synthetic: names, account numbers, GSTINs, invoices and
amounts are generated from ``--seed``.  No client document ever enters this
folder, and the whole output tree (``stress-dump/`` by default) is gitignored.

The point of the corpus is *known truth by construction*: the generator knows
how many transactions, invoices, vouchers and line items it wrote and what they
add up to, so ``corpus_run.py`` can compare the engine's answer against the
generator's answer instead of against itself.

Usage
-----
    .venv\\Scripts\\python.exe build_corpus.py                    # standard
    .venv\\Scripts\\python.exe build_corpus.py --profile smoke
    .venv\\Scripts\\python.exe build_corpus.py --seed 7 --out temp/corpus7

Outputs (inside ``--out``):

* the document tree (``banks/``, ``invoices/``, ``gst/``, ``books/``,
  ``junk/``, ``mixed/``)
* ``manifest.json`` / ``manifest.csv`` — one row per file with the expected
  outcome
* ``index.html`` — a browsable gallery of the same information
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import random
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "stress-dump" / "corpus"
DEFAULT_SEED = 2026
KNOWN_PDF_PASSWORD = "corpus-open-2026"

PAGE_W, PAGE_H = 595, 842
FAMILIES = ("banks", "invoices", "gst", "books", "junk", "mixed")

# Banks the engine has a profile for, and banks it does not.
SUPPORTED_BANKS = (
    ("HDFC Bank", "HDFC", "HDFC0001234"),
    ("ICICI Bank", "ICIC", "ICIC0000456"),
    ("State Bank of India", "SBI", "SBIN0000789"),
    ("Axis Bank", "AXIS", "UTIB0000123"),
    ("Kotak Mahindra Bank", "KOTAK", "KKBK0000958"),
)
UNSUPPORTED_BANKS = (
    ("IDFC FIRST Bank", "IDFC", "IDFB0041234"),
    ("Yes Bank", "YESB", "YESB0000123"),
    ("Federal Bank", "FDRL", "FDRL0001456"),
    ("Bank of Baroda", "BARB", "BARB0MUMBAI"),
    ("Punjab National Bank", "PUNB", "PUNB0112345"),
    ("Canara Bank", "CNRB", "CNRB0001234"),
)

VENDORS = (
    "ACME TRADERS",
    "LAKSHMI PRINTERS",
    "NORTH RETAIL",
    "SHREE STEELS",
    "KIRAN AGENCIES",
    "MEHTA EXPORTS",
    "BHARAT PACKAGING",
    "HARBOUR LOGISTICS",
    "SUNRISE ELECTRICALS",
    "PENINSULA CHEMICALS",
    "GREENFIELD PAPERS",
    "RIVERDALE TOOLS",
)

BUYERS = (
    "DEMO ENTERPRISES",
    "PLACEHOLDER INDUSTRIES",
    "SAMPLE TRADING LLP",
    "SYNTHETIC RETAIL PVT LTD",
    "FICTIONAL WORKS",
    "TESTBED AGENCIES",
)

DESCRIPTIONS = (
    "Professional fees",
    "Design sprint block",
    "Consulting retainer",
    "Annual maintenance",
    "Software licence",
    "Printing and stationery",
    "Freight charges",
    "Spare parts kit",
    "Cable tray 2m",
    "LED panel 18W",
    "Office chair",
    "Courier charges",
)


# ---------------------------------------------------------------------------
# Deterministic primitives
# ---------------------------------------------------------------------------

_DIGITS = Decimal("0.01")


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(_DIGITS)


def plain(value: Decimal) -> str:
    """Plain 1234567.89 form (no grouping) as printed by most banks."""
    return f"{money(value):.2f}"


def indian(value: Decimal) -> str:
    """1234567.89 -> 12,34,567.89 (Indian lakh/crore grouping)."""
    value = money(value)
    negative = value < 0
    value = -value if negative else value
    whole, _, frac = f"{value:.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups + [tail])
    return ("-" if negative else "") + whole + "." + frac


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size


GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum(first14: str) -> str:
    factor = 1
    total = 0
    for char in first14:
        code = GSTIN_CHARS.index(char)
        product = factor * code
        factor = 2 if factor == 1 else 1
        total += product // 36 + product % 36
    return GSTIN_CHARS[(36 - (total % 36)) % 36]


def make_gstin(rng: random.Random, state: str = "27") -> str:
    letters = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5))
    digits = "".join(rng.choice("0123456789") for _ in range(4))
    entity = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    branch = rng.choice("123456789")
    first14 = f"{state}{letters}{digits}{entity}{branch}Z"
    return first14 + gstin_checksum(first14)


def break_gstin(gstin: str) -> str:
    """Same shape, checksum deliberately wrong (one character flipped)."""
    tail = gstin[-1]
    replacement = "0" if tail != "0" else "1"
    return gstin[:-1] + replacement


def account_number(rng: random.Random) -> str:
    length = rng.choice((11, 12, 13, 14))
    return "".join(rng.choice("0123456789") for _ in range(length))


# ---------------------------------------------------------------------------
# File rendering primitives
# ---------------------------------------------------------------------------


def _text_document(pages: list[list[str]], fontsize: float = 9.0, leading: float = 15.0) -> pymupdf.Document:
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        y = 56.0
        for line in lines:
            page.insert_text((40, y), line, fontsize=fontsize, fontname="cour")
            y += leading
    doc.set_metadata({})
    return doc


def write_pdf(dest: Path, pages: list[list[str]], *, fontsize: float = 9.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = _text_document(pages, fontsize=fontsize)
    doc.save(dest, garbage=3, deflate=True, no_new_id=1)
    doc.close()


def write_encrypted_pdf(dest: Path, pages: list[list[str]], password: str) -> None:
    """A real password-protected PDF with reproducible bytes.

    MuPDF's AES/RC4 writers salt every file with fresh randomness, so two runs
    of the same seed produced different bytes.  pypdf's RC4-128 writer with a
    fixed document id is deterministic and is still a genuine encrypted PDF
    that both pypdf and MuPDF refuse to open without the password.
    """
    import io

    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, ByteStringObject

    dest.parent.mkdir(parents=True, exist_ok=True)
    plain = _text_document(pages, fontsize=11.0)
    payload = plain.tobytes(garbage=3, deflate=True, no_new_id=1)
    plain.close()
    writer = PdfWriter(clone_from=io.BytesIO(payload))
    fixed = ByteStringObject(b"CORPUS0000000001")
    writer._ID = ArrayObject([fixed, fixed])
    writer.encrypt(password, password + "-owner", algorithm="RC4-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    dest.write_bytes(buffer.getvalue())


def rasterize(dest: Path, pages: list[list[str]], *, dpi: int = 150, rotate: float = 0.0,
              blur: float = 0.0, fontsize: float = 11.0) -> None:
    """Render a text document to a grayscale PNG (the 'scanned' variant)."""
    doc = _text_document(pages, fontsize=fontsize, leading=18.0)
    pixmaps = [
        doc[index].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY) for index in range(doc.page_count)
    ]
    doc.close()
    images = [Image.open(path_bytes(pix)) for pix in pixmaps]
    # Bank/invoice statements are one page by construction; the first is enough.
    image = images[0]
    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor=255, resample=Image.Resampling.BICUBIC)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=blur))
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, "PNG")


def rasterize_statement(dest: Path, spec: BankSpec, *, dpi: int = 200, rotate: float = 0.0,
                        blur: float = 0.0, fontsize: float = 11.0, grouped: bool = False) -> None:
    """Render a statement as a scanned image with real column positions.

    A flat run of text with single spaces lets OCR glue the amount and balance
    columns together ("1234.50154444.50"); right-aligned money columns on a
    monospace grid keep them apart, which is how real printed statements look.
    """
    fmt = indian if grouped else plain
    char = fontsize * 0.6
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = 56.0
    leading = fontsize * 2.0

    def put(x: float, value: str) -> None:
        page.insert_text((x, y), value, fontsize=fontsize, fontname="cour")

    def right(right_edge: float, value: str) -> None:
        put(right_edge - len(value) * char, value)

    for line in (
        f"{spec.bank} Account Statement",
        f"Account Number {spec.account}",
        f"IFSC {spec.ifsc}",
        "Statement Period 01/07/2026 to 31/07/2026",
        f"Opening Balance {fmt(spec.opening)}",
    ):
        put(40, line)
        y += leading
    put(40, "Date")
    put(120, "Narration")
    put(300, "Type")
    right(470, "Amount")
    right(575, "Balance")
    y += leading
    for txn in spec.txns:
        put(40, txn.date)
        put(120, txn.narration[:24])
        put(300, "Withdrawal" if txn.direction == "debit" else "Deposit")
        right(470, fmt(txn.amount))
        right(575, fmt(txn.balance))
        y += leading
    if spec.stated_closing is not None:
        put(40, f"Closing Balance {fmt(spec.stated_closing)}")
    doc.set_metadata({})
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    doc.close()
    image = Image.open(path_bytes(pix))
    if rotate:
        image = image.rotate(rotate, expand=True, fillcolor=255, resample=Image.Resampling.BICUBIC)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=blur))
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, "PNG")


def path_bytes(pix) -> "object":
    """Pixmap -> in-memory PNG stream (kept separate for readability)."""
    import io

    return io.BytesIO(pix.tobytes("png"))


def _normalize_zip(dest: Path) -> None:
    """Rewrite a zip/xlsx with fixed timestamps so identical input = identical bytes."""
    import io
    import re

    with zipfile.ZipFile(dest) as archive:
        items = [(info.filename, archive.read(info.filename)) for info in archive.infolist()]
    normalized: list[tuple[str, bytes]] = []
    for name, data in items:
        if name == "docProps/core.xml":
            # openpyxl stamps the current date and time into the workbook.
            text = data.decode("utf-8")
            text = re.sub(
                r"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:(?:created|modified)>)",
                r"\g<1>2026-01-01T00:00:00Z\g<2>",
                text,
            )
            data = text.encode("utf-8")
        normalized.append((name, data))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in normalized:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    dest.write_bytes(buffer.getvalue())


def write_xlsx(dest: Path, sheet: str, rows: list[list]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    for row in rows:
        worksheet.append(row)
    workbook.save(dest)
    workbook.close()
    _normalize_zip(dest)


def write_zip(dest: Path, entries: dict[str, bytes | str]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data if isinstance(data, bytes) else data.encode("utf-8"))


# ---------------------------------------------------------------------------
# Corpus ledger
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    path: str
    family: str
    kind: str
    outcome: str = "processed"
    rows: int | None = None
    line_items: int | None = None
    totals: dict[str, float] = field(default_factory=dict)
    balance_status: str | None = None
    flags: list[str] = field(default_factory=list)
    notes: str = ""
    requires: list[str] = field(default_factory=list)
    advisory: bool = False
    password: str | None = None

    def manifest(self, sha: str, size: int) -> dict:
        payload = {
            "path": self.path,
            "family": self.family,
            "kind": self.kind,
            "outcome": self.outcome,
            "rows": self.rows,
            "line_items": self.line_items,
            "totals": {key: float(value) for key, value in self.totals.items()},
            "balance_status": self.balance_status,
            "flags": list(self.flags),
            "notes": self.notes,
            "sha256": sha,
            "size": size,
        }
        if self.requires:
            payload["requires"] = list(self.requires)
        if self.advisory:
            payload["advisory"] = True
        if self.password:
            payload["password"] = self.password
        return payload


class Corpus:
    def __init__(self, root: Path, seed: int, profile: str) -> None:
        self.root = root
        self.seed = seed
        self.profile = profile
        self.rng = random.Random(seed)
        self.entries: list[Entry] = []
        self._duplicate_bytes: dict[str, str] = {}

    # -- paths ---------------------------------------------------------
    def path(self, relative: str) -> Path:
        dest = self.root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    def add(self, relative: str, entry: Entry) -> None:
        entry.path = relative.replace("\\", "/")
        self.entries.append(entry)
        sha, size = sha256_file(self.root / relative)
        self._duplicate_bytes.setdefault(sha, entry.path)

    def copy(self, source_relative: str, target_relative: str, family: str = "mixed") -> str:
        source = self.root / source_relative
        target = self.root / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target_relative

    # -- manifest ------------------------------------------------------
    def write_manifest(self) -> None:
        files = []
        for entry in sorted(self.entries, key=lambda item: item.path):
            sha, size = sha256_file(self.root / entry.path)
            files.append(entry.manifest(sha, size))
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.family] = counts.get(entry.family, 0) + 1
        total_bytes = sum(item["size"] for item in files)
        manifest = {
            "corpus": "ca-unpacker-stress-corpus",
            "fictional": True,
            "profile": self.profile,
            "seed": self.seed,
            "generated_by": "build_corpus.py",
            "file_count": len(files),
            "total_bytes": total_bytes,
            "families": counts,
            "files": files,
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with (self.root / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "path",
                    "family",
                    "kind",
                    "outcome",
                    "rows",
                    "line_items",
                    "debit",
                    "credit",
                    "value",
                    "taxable",
                    "balance_status",
                    "flags",
                    "requires",
                    "notes",
                    "size",
                    "sha256",
                ]
            )
            for item in files:
                writer.writerow(
                    [
                        item["path"],
                        item["family"],
                        item["kind"],
                        item["outcome"],
                        "" if item["rows"] is None else item["rows"],
                        "" if item["line_items"] is None else item["line_items"],
                        item["totals"].get("debit", ""),
                        item["totals"].get("credit", ""),
                        item["totals"].get("value", ""),
                        item["totals"].get("taxable", ""),
                        item["balance_status"] or "",
                        " ".join(item["flags"]),
                        " ".join(item.get("requires") or []),
                        item["notes"],
                        item["size"],
                        item["sha256"],
                    ]
                )
        (self.root / "index.html").write_text(self._gallery(manifest), encoding="utf-8")

    def _gallery(self, manifest: dict) -> str:
        rows = []
        for item in manifest["files"]:
            totals = item["totals"]
            total_text = " ".join(f"{key}={value:,.2f}" for key, value in totals.items()) or ""
            requires = item.get("requires") or []
            rows.append(
                "<tr>"
                f"<td class='path'>{html.escape(item['path'])}</td>"
                f"<td>{html.escape(item['family'])}</td>"
                f"<td>{html.escape(item['kind'])}</td>"
                f"<td>{html.escape(item['outcome'])}</td>"
                f"<td class='num'>{'' if item['rows'] is None else item['rows']}</td>"
                f"<td class='num'>{'' if item['line_items'] is None else item['line_items']}</td>"
                f"<td class='num' nowrap>{html.escape(total_text)}</td>"
                f"<td>{html.escape(item['balance_status'] or '')}</td>"
                f"<td>{html.escape(' '.join(item['flags']))}</td>"
                f"<td>{html.escape(' '.join(requires))}</td>"
                f"<td>{html.escape(item['notes'])}</td>"
                f"<td class='num'>{item['size']:,}</td>"
                "</tr>"
            )
        cards = "".join(
            f"<div class='card'><div class='n'>{count}</div><div class='l'>{html.escape(family)}</div></div>"
            for family, count in sorted(manifest["families"].items())
        )
        kinds: dict[str, int] = {}
        for item in manifest["files"]:
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        kind_cards = "".join(
            f"<div class='card small'><div class='n'>{count}</div><div class='l'>{html.escape(kind)}</div></div>"
            for kind, count in sorted(kinds.items())
        )
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>CA Unpacker stress corpus — {html.escape(str(manifest["profile"]))} / seed {manifest["seed"]}</title>
<style>
 body {{ font: 13px/1.45 system-ui, Segoe UI, sans-serif; margin: 24px; color: #16202a; }}
 h1 {{ font-size: 20px; margin: 0 0 4px; }}
 .sub {{ color: #55636f; margin-bottom: 18px; }}
 .cards {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }}
 .card {{ background: #f2f5f8; border: 1px solid #dfe6ec; border-radius: 8px; padding: 10px 16px; min-width: 92px; }}
 .card.small {{ padding: 6px 12px; }}
 .card .n {{ font-size: 20px; font-weight: 650; }}
 .card .l {{ color: #55636f; text-transform: uppercase; letter-spacing: .04em; font-size: 11px; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border-bottom: 1px solid #e6ebf0; padding: 5px 8px; text-align: left; vertical-align: top; }}
 th {{ position: sticky; top: 0; background: #fff; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #55636f; }}
 td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
 td.path {{ font-family: ui-monospace, Consolas, monospace; font-size: 12px; }}
 tr:hover td {{ background: #f8fafc; }}
 .note {{ color: #55636f; font-size: 12px; margin-top: 14px; }}
</style></head><body>
<h1>CA Unpacker stress corpus</h1>
<div class="sub">Fictional, machine generated. Profile <b>{html.escape(str(manifest["profile"]))}</b>,
seed <b>{manifest["seed"]}</b>, {manifest["file_count"]} files,
{manifest["total_bytes"] / (1024 * 1024):.1f} MB. Expected values are known by construction,
never read back from the parser.</div>
<div class="cards">{cards}</div>
<div class="cards">{kind_cards}</div>
<table>
<thead><tr><th>File</th><th>Family</th><th>Expected kind</th><th>Outcome</th><th>Rows</th><th>Lines</th>
<th>Expected totals</th><th>Balance</th><th>Expected flags</th><th>Needs</th><th>Notes</th><th>Bytes</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody></table>
<div class="note">Totals: <code>debit</code>/<code>credit</code> are summed from bank or SAP rows;
<code>value</code>/<code>taxable</code> from invoice, GST, Tally and Zoho rows.</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# Bank statements
# ---------------------------------------------------------------------------


@dataclass
class Txn:
    date: str
    narration: str
    direction: str  # "debit" | "credit"
    amount: Decimal
    balance: Decimal


@dataclass
class BankSpec:
    bank: str
    account: str
    ifsc: str
    opening: Decimal
    txns: list[Txn]
    stated_closing: Decimal | None
    closing_note: str = ""


def _txn_stream(
    rng: random.Random,
    count: int,
    opening: Decimal,
    *,
    scale: int = 1,
    month: int = 7,
) -> tuple[list[Txn], Decimal]:
    """Deterministic transaction stream with an exact running balance."""
    balance = opening
    txns: list[Txn] = []
    for index in range(count):
        day = 1 + (index * 3) % 28
        vendor = VENDORS[index % len(VENDORS)]
        if index % 3 == 0:
            amount = money(Decimal(str(rng.randrange(800, 4000 * scale))) + Decimal("0.50"))
            balance = money(balance + amount)
            txns.append(
                Txn(
                    date=f"{day:02d}/{month:02d}/2026",
                    narration=f"NEFT CR {vendor} INV/{9000 + index}",
                    direction="credit",
                    amount=amount,
                    balance=balance,
                )
            )
        else:
            amount = money(Decimal(str(rng.randrange(90, 1800))) + Decimal("0.25"))
            balance = money(balance - amount)
            txns.append(
                Txn(
                    date=f"{day:02d}/{month:02d}/2026",
                    narration=f"UPI merchant {vendor} ref {610000000000 + index * 37}",
                    direction="debit",
                    amount=amount,
                    balance=balance,
                )
            )
    return txns, money(balance)


def _bank_header(spec: BankSpec, grouped: bool) -> list[str]:
    fmt = indian if grouped else plain
    return [
        f"{spec.bank} Account Statement",
        f"Account Number {spec.account}",
        f"IFSC {spec.ifsc}",
        "Statement Period 01/07/2026 to 31/07/2026",
        f"Opening Balance {fmt(spec.opening)}",
        "Date Narration Withdrawal Deposit Balance",
    ]


def _bank_txn_lines(spec: BankSpec, grouped: bool, suffix_style: bool) -> list[str]:
    fmt = indian if grouped else plain
    lines: list[str] = []
    for txn in spec.txns:
        if suffix_style:
            marker = "Dr" if txn.direction == "debit" else "Cr"
            lines.append(f"{txn.date} {txn.narration} {fmt(txn.amount)} {marker} {fmt(txn.balance)}")
        else:
            word = "Withdrawal" if txn.direction == "debit" else "Deposit"
            lines.append(f"{txn.date} {txn.narration} {word} {fmt(txn.amount)} {fmt(txn.balance)}")
    return lines


def _bank_body(spec: BankSpec, grouped: bool, suffix_style: bool) -> list[str]:
    fmt = indian if grouped else plain
    lines = _bank_txn_lines(spec, grouped, suffix_style)
    if spec.stated_closing is not None:
        lines.append(f"Closing Balance {fmt(spec.stated_closing)}")
    return lines


def _bank_totals(spec: BankSpec) -> dict[str, float]:
    debit = sum((t.amount for t in spec.txns if t.direction == "debit"), Decimal("0"))
    credit = sum((t.amount for t in spec.txns if t.direction == "credit"), Decimal("0"))
    return {"debit": float(debit), "credit": float(credit)}


def _write_bank_text(corpus: Corpus, relative: str, spec: BankSpec, *, grouped: bool = False,
                     suffix_style: bool = False, page_rows: int = 0, wrapped: list[int] | None = None) -> None:
    header = _bank_header(spec, grouped)
    body = _bank_txn_lines(spec, grouped, suffix_style)
    fmt = indian if grouped else plain
    if wrapped:
        for position in wrapped:
            if 0 <= position < len(body):
                body.insert(position + 1, "MUMBAI FORT BRANCH REF 998811")
    closing = f"Closing Balance {fmt(spec.stated_closing)}" if spec.stated_closing is not None else None
    dest = corpus.path(relative)
    if page_rows and len(body) > page_rows:
        chunk_count = (len(body) + page_rows - 1) // page_rows
        pages = []
        for page_index in range(chunk_count):
            chunk = body[page_index * page_rows : (page_index + 1) * page_rows]
            if page_index == 0:
                page_lines = list(header) + chunk
            else:
                page_lines = [
                    f"{spec.bank} Account Statement (continued)",
                    "Date Narration Withdrawal Deposit Balance",
                ] + chunk
            page_lines.append(f"Page {page_index + 1} of {chunk_count}")
            if page_index == chunk_count - 1 and closing:
                page_lines.append(closing)
            pages.append(page_lines)
        write_pdf(dest, pages)
    else:
        lines = header + body
        if closing:
            lines.append(closing)
        write_pdf(dest, [lines])


def build_banks(corpus: Corpus, plan: list[tuple[str, int]] | None = None, scale: int = 1,
                extras: bool = True) -> None:
    rng = corpus.rng
    variants: list[tuple[str, int]] = plan or [
        ("clean_text", 23),
        ("multipage", 15),
        ("indian_grouping", 15),
        ("dr_cr_suffix", 15),
        ("month_name_dates", 10),
        ("zero_opening", 8),
        ("wrapped_narration", 12),
        ("duplicate_rows", 8),
        ("broken_closing", 10),
        ("broken_running", 8),
        ("scanned_image", 4),
        ("rotated_image", 2),
        ("lowres_image", 2),
        ("encrypted", 3),
        ("unsupported_layout", 8),
    ]
    if scale != 1:
        variants = [(variant, count * scale) for variant, count in variants]
    index = 0
    for variant, count in variants:
        for _ in range(count):
            index += 1
            if variant == "unsupported_layout":
                if index % 4 == 0:
                    bank, code, ifsc = "Janakalyan Sahakari Bank", "GENERIC", "JSBL0000123"
                    unsupported = True
                else:
                    bank, code, ifsc = UNSUPPORTED_BANKS[index % len(UNSUPPORTED_BANKS)]
                    unsupported = True
            else:
                bank, code, ifsc = SUPPORTED_BANKS[index % len(SUPPORTED_BANKS)]
                unsupported = False
            rows = rng.choice((4, 5, 6, 8, 10, 12, 18, 24, 40))
            opening = money(Decimal(str(rng.randrange(60_000, 2_500_000))) + Decimal("0.00"))
            if variant == "zero_opening":
                opening = Decimal("0.00")
                rows = rng.choice((3, 4, 5, 6))
            if variant in {"scanned_image", "rotated_image", "lowres_image"}:
                # One page, readable at OCR resolution.
                rows = min(rows, 18)
            scale = 3 if opening > 1_000_000 else 1
            txns, final = _txn_stream(rng, rows, opening, scale=scale)
            if variant == "month_name_dates":
                months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
                for txn in txns:
                    day = int(txn.date[:2])
                    txn.date = f"{day:02d} Jul 2026"
            spec = BankSpec(bank=bank, account=account_number(rng), ifsc=ifsc, opening=opening,
                            txns=txns, stated_closing=final)
            grouped = variant == "indian_grouping"
            suffix = variant == "dr_cr_suffix"
            label = f"{code.capitalize()}_{variant}_{index:03d}_Jul2026"
            notes = variant
            flags: list[str] = []
            totals = _bank_totals(spec)
            balance = "match"
            expected_rows: int | None = len(txns)
            requires: list[str] = []
            advisory = False
            password = None

            if variant == "multipage":
                _write_bank_text(corpus, f"banks/{label}.pdf", spec, grouped=grouped,
                                 suffix_style=suffix, page_rows=25)
            elif variant == "broken_closing":
                spec.stated_closing = money(final + Decimal("999.00"))
                _write_bank_text(corpus, f"banks/{label}.pdf", spec, grouped=grouped)
                balance = "mismatch"
                flags = ["closing_mismatch"]
                notes = "closing balance deliberately wrong"
            elif variant == "broken_running":
                # A balance printed at the wrong scale: the engine should notice the
                # gap and insert one flagged "inferred" row to repair it.
                txns[1].balance = money(txns[1].balance / Decimal("1000"))
                for position in range(2, len(txns)):
                    delta = txns[position].amount * (1 if txns[position].direction == "credit" else -1)
                    txns[position].balance = money(txns[position - 1].balance + delta)
                spec.stated_closing = txns[-1].balance
                _write_bank_text(corpus, f"banks/{label}.pdf", spec, grouped=grouped)
                balance = "match"
                expected_rows = len(txns) + 1
                totals = {}
                flags = ["inferred_from_balance"]
                notes = "running balance jumps; one inferred row expected"
            elif variant == "wrapped_narration":
                _write_bank_text(corpus, f"banks/{label}.pdf", spec, grouped=grouped, wrapped=[0, 2])
                notes = "narration wraps onto a second line"
            elif variant == "duplicate_rows":
                # The same transaction posted twice: identical narration and
                # amount, but the running balance moves twice (a double posting),
                # so the ledger still adds up.
                source = txns[0]
                step = 1 if source.direction == "credit" else -1
                duplicate = type(source)(
                    date=source.date,
                    narration=source.narration,
                    direction=source.direction,
                    amount=source.amount,
                    balance=money(source.balance + source.amount * step),
                )
                txns.insert(1, duplicate)
                for position in range(2, len(txns)):
                    delta = txns[position].amount * (1 if txns[position].direction == "credit" else -1)
                    txns[position].balance = money(txns[position - 1].balance + delta)
                spec.stated_closing = txns[-1].balance
                _write_bank_text(corpus, f"banks/{label}.pdf", spec, grouped=grouped)
                expected_rows = len(txns)
                totals = _bank_totals(spec)
                notes = "one transaction posted twice"
            elif variant in {"scanned_image", "rotated_image", "lowres_image"}:
                if variant == "scanned_image":
                    rasterize_statement(corpus.path(f"banks/{label}.png"), spec, dpi=200)
                elif variant == "rotated_image":
                    rasterize_statement(corpus.path(f"banks/{label}.png"), spec, dpi=200, rotate=1.2)
                else:
                    rasterize_statement(corpus.path(f"banks/{label}.png"), spec, dpi=110, blur=0.4)
                requires = ["ocr"]
                notes = f"{variant} (OCR); needs a working OCR engine"
                corpus.add(
                    f"banks/{label}.png",
                    Entry(path=f"banks/{label}.png", family="banks", kind="bank", rows=expected_rows,
                          totals=totals, balance_status=balance, flags=flags, notes=notes,
                          requires=requires),
                )
                continue
            elif variant == "encrypted":
                pages = [_bank_header(spec, False) + _bank_body(spec, False, False)]
                write_encrypted_pdf(corpus.path(f"banks/{label}.pdf"), pages, KNOWN_PDF_PASSWORD)
                corpus.add(
                    f"banks/{label}.pdf",
                    Entry(path=f"banks/{label}.pdf", family="banks", kind="unknown",
                          outcome="needs_review", rows=None, totals={}, balance_status=None,
                          flags=[], notes="password-protected bank PDF (known password)",
                          password=KNOWN_PDF_PASSWORD),
                )
                continue
            elif variant == "zero_opening":
                _write_bank_text(corpus, f"banks/{label}.pdf", spec, grouped=grouped)
                notes = "opening balance is zero"
            else:
                _write_bank_text(corpus, f"banks/{label}.pdf", spec, grouped=grouped,
                                 suffix_style=suffix)

            if unsupported:
                notes = notes + "; bank has no engine profile (generic path)"
            corpus.add(
                f"banks/{label}.pdf",
                Entry(path=f"banks/{label}.pdf", family="banks", kind="bank", rows=expected_rows,
                      totals=totals, balance_status=balance, flags=flags, notes=notes),
            )

    # One statement with transactions but no printed opening/closing: the engine
    # cannot verify it, so the status must be "unverified".
    if not extras:
        return
    opening = Decimal("45000.00")
    txns, final = _txn_stream(rng, 6, opening)
    spec = BankSpec("HDFC Bank", account_number(rng), "HDFC0001234", opening, txns, None)
    no_context = [
        "HDFC Bank Account Statement",
        f"Account Number {spec.account}",
        f"IFSC {spec.ifsc}",
        "Statement Period 01/07/2026 to 31/07/2026",
        "Date Narration Withdrawal Deposit Balance",
    ] + _bank_txn_lines(spec, False, False)
    write_pdf(corpus.path("banks/HDFC_NoClosing_999_Jul2026.pdf"), [no_context])
    corpus.add(
        "banks/HDFC_NoClosing_999_Jul2026.pdf",
        Entry(path="banks/HDFC_NoClosing_999_Jul2026.pdf", family="banks", kind="bank",
              rows=len(txns), totals=_bank_totals(spec), balance_status="unverified",
              notes="no opening or closing balance printed"),
    )

    # A valid statement with no transactions: the engine must report zero rows
    # and a plain "no transactions" outcome, not a crash.  (It used to raise
    # UnboundLocalError on the empty-statement path.)
    lines = [
        "HDFC Bank Account Statement",
        "Account Number 50100123999999",
        "IFSC HDFC0001234",
        "Narration Withdrawal Deposit Balance",
        "No transactions were posted in this period",
    ]
    write_pdf(corpus.path("banks/HDFC_EmptyStatement_998_Jul2026.pdf"), [lines])
    corpus.add(
        "banks/HDFC_EmptyStatement_998_Jul2026.pdf",
        Entry(path="banks/HDFC_EmptyStatement_998_Jul2026.pdf", family="banks", kind="bank",
              outcome="processed", rows=0, totals={}, balance_status=None,
              notes="valid empty statement: no transactions were posted in this period"),
    )


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@dataclass
class LineItem:
    description: str
    hsn: str
    qty: int
    rate: Decimal
    taxable: Decimal
    rate_pct: Decimal


def _invoice_lines(
    *,
    number: str,
    date: str,
    gstin: str,
    hsn: str,
    items: list[LineItem],
    place_of_supply: str,
    supplier: str,
    customer: str,
    customer_gstin: str | None,
    inter_state: bool,
    discount_note: Decimal | None = None,
    round_off: Decimal | None = None,
    break_total: Decimal | None = None,
    break_taxable: Decimal | None = None,
) -> tuple[list[str], dict]:
    taxable_sum = sum((item.taxable for item in items), Decimal("0"))
    cgst = sum(
        ((item.taxable * item.rate_pct / 100).quantize(_DIGITS) / 2).quantize(_DIGITS)
        for item in items
    )
    sgst = cgst
    igst = sum(((item.taxable * item.rate_pct / 100).quantize(_DIGITS) for item in items))
    tax = igst if inter_state else (cgst + sgst)
    total = money(taxable_sum + tax + (round_off or Decimal("0")))

    header = [
        "TAX INVOICE",
        f"Invoice No {number}",
        f"Invoice Date {date}",
        f"Supplier GSTIN {gstin}",
        f"Supplier name {supplier}",
    ]
    if customer_gstin:
        header.append(f"Customer GSTIN {customer_gstin}")
    header += [
        f"Customer Name {customer}",
        f"Place of Supply {place_of_supply}",
        "All amounts are in INR (Rs.)",
    ]
    if discount_note is not None:
        header.append(f"Discount allowed {money(discount_note)} (already deducted)")
    header += [f"HSN {hsn}", "HSN Qty Rate Taxable Amount"]

    body: list[str] = []
    for item in items:
        line_tax = (item.taxable * item.rate_pct / 100).quantize(_DIGITS)
        amount = money(item.taxable + line_tax)
        body.append(
            f"{item.description} {item.hsn} {item.qty} {plain(item.rate)} {plain(item.taxable)} {plain(amount)}"
        )

    printed_taxable = money(break_taxable) if break_taxable is not None else money(taxable_sum)
    printed_total = money(break_total) if break_total is not None else total
    foot = [f"Taxable value {plain(printed_taxable)}"]
    if inter_state:
        foot.append(f"IGST {plain(igst)}")
    else:
        foot.append(f"CGST {plain(cgst)}  SGST {plain(sgst)}")
    if round_off is not None:
        foot.append(f"Round Off {plain(round_off)}")
    foot.append(f"Invoice value {plain(printed_total)}")
    truth = {
        "value": float(printed_total),
        "taxable": float(printed_taxable),
        "line_items": len(items),
    }
    return header + body + foot, truth


def _paginate_invoice(header: list[str], body: list[str], foot: list[str], per_page: int = 40) -> list[list[str]]:
    if len(body) <= per_page:
        return [header + body + foot]
    pages: list[list[str]] = []
    for start in range(0, len(body), per_page):
        chunk = body[start : start + per_page]
        if start == 0:
            pages.append(header + chunk)
        else:
            pages.append(
                ["TAX INVOICE (continued)", f"Invoice No {header[1].split(' ', 2)[2]}",
                 "HSN Qty Rate Taxable Amount"] + chunk
            )
    pages[-1].extend(foot)
    return pages


def _item_set(rng: random.Random, count: int, *, rate_pct: Decimal, hsn: str) -> list[LineItem]:
    items = []
    for index in range(count):
        qty = 1 + index % 4
        rate = money(Decimal(str(rng.randrange(400, 9000))) + Decimal("0.00"))
        taxable = money(rate * qty)
        items.append(
            LineItem(
                description=(
                    f"{DESCRIPTIONS[index % len(DESCRIPTIONS)]} {chr(65 + index % 26)}"
                ),
                hsn=hsn,
                qty=qty,
                rate=rate,
                taxable=taxable,
                rate_pct=rate_pct,
            )
        )
    return items


def build_invoices(corpus: Corpus, plan: list[tuple[str, int]] | None = None, scale: int = 1,
                   extras: bool = True) -> None:
    rng = corpus.rng
    variants = plan or [
        ("cgst_sgst", 29),
        ("igst", 15),
        ("many_items", 12),
        ("exempt", 6),
        ("discount", 6),
        ("round_off", 6),
        ("multipage", 8),
        ("invalid_gstin", 5),
        ("invalid_hsn", 5),
        ("broken_math", 6),
        ("image_only", 6),
    ]
    if scale != 1:
        variants = [(variant, count * scale) for variant, count in variants]
    index = 0
    for variant, count in variants:
        for _ in range(count):
            index += 1
            items_count = rng.choice((1, 2, 3, 5, 8))
            if variant == "many_items":
                items_count = rng.choice((20, 25, 40, 60))
            if variant == "multipage":
                items_count = rng.choice((45, 55, 60))
            if variant == "exempt":
                items_count = rng.choice((1, 2))
            rate_pct = Decimal("18")
            hsn = rng.choice(("998314", "9405", "8471", "6109", "9983"))
            if variant == "invalid_hsn":
                hsn = rng.choice(("12345", "99831"))
            gstin = make_gstin(rng)
            if variant == "invalid_gstin":
                gstin = break_gstin(gstin)
            number = f"SYN/26-27/{index:04d}"
            date = f"{(index % 27) + 1:02d}/07/2026"
            inter = variant == "igst"
            if variant == "image_only":
                # A single, short invoice rasterised at a readable size.
                items = _item_set(rng, 2, rate_pct=rate_pct, hsn=hsn)
                lines, truth = _invoice_lines(
                    number=number, date=date, gstin=gstin, hsn=hsn, items=items,
                    place_of_supply="27-Maharashtra" if not inter else "29-Karnataka",
                    supplier="Synthetic Traders Pvt Ltd", customer="Demo Enterprises",
                    customer_gstin=None, inter_state=inter,
                )
                rasterize(corpus.path(f"invoices/Scan_{variant}_{index:03d}.png"), [lines], dpi=150)
                corpus.add(
                    f"invoices/Scan_{variant}_{index:03d}.png",
                    Entry(path=f"invoices/Scan_{variant}_{index:03d}.png", family="invoices",
                          kind="invoice", rows=1, line_items=truth["line_items"],
                          totals={"value": truth["value"], "taxable": truth["taxable"]},
                          flags=[], notes="image-only invoice (OCR)", requires=["ocr"]),
                )
                continue

            if variant == "exempt":
                items = [
                    LineItem(
                        description="Charitable services exempt",
                        hsn="999293",
                        qty=1,
                        rate=money(rng.randrange(2000, 9000)),
                        taxable=money(rng.randrange(2000, 9000)),
                        rate_pct=Decimal("0"),
                    )
                    for _ in range(items_count)
                ]
                hsn = "999293"
            else:
                items = _item_set(rng, items_count, rate_pct=rate_pct, hsn=hsn)

            discount = money(rng.randrange(100, 900)) if variant == "discount" else None
            round_off = Decimal("0.40") if variant == "round_off" else None
            break_total = None
            break_taxable = None
            flags: list[str] = []
            notes = variant
            if variant == "broken_math":
                break_total = Decimal("500.00")
                flags = ["invoice_math", "taxable_mismatch", "line_total_mismatch"]
                notes = "invoice total deliberately out by 500.00"
            if variant == "invalid_gstin":
                flags = ["gstin_checksum"]
                notes = "GSTIN checksum deliberately wrong"
            if variant == "invalid_hsn":
                flags = ["hsn_length"]
                notes = "HSN is 5 digits"
            if discount is not None:
                # A real trade discount: the printed taxable values are already net
                # of it, so the arithmetic on the page stays consistent.
                share = money(discount / len(items))
                for item in items:
                    item.taxable = money(max(Decimal("1.00"), item.taxable - share))

            lines, truth = _invoice_lines(
                number=number,
                date=date,
                gstin=gstin,
                hsn=hsn,
                items=items,
                place_of_supply="27-Maharashtra" if not inter else "29-Karnataka",
                supplier="Synthetic Traders Pvt Ltd",
                customer=BUYERS[index % len(BUYERS)],
                customer_gstin=make_gstin(rng, "29") if index % 4 == 0 else None,
                inter_state=inter,
                discount_note=discount,
                round_off=round_off,
                break_total=break_total,
                break_taxable=break_taxable,
            )
            body_start = lines.index("HSN Qty Rate Taxable Amount") + 1
            footer_start = next(
                position for position, line in enumerate(lines) if line.startswith("Taxable value")
            )
            if variant == "multipage" or len(items) > 38:
                pages = _paginate_invoice(
                    lines[:body_start], lines[body_start:footer_start], lines[footer_start:]
                )
                write_pdf(corpus.path(f"invoices/Invoice_{variant}_{index:03d}.pdf"), pages)
            else:
                write_pdf(corpus.path(f"invoices/Invoice_{variant}_{index:03d}.pdf"), [lines])
            if variant == "broken_math":
                truth = {"value": float(break_total), "taxable": truth["taxable"],
                         "line_items": len(items)}
            corpus.add(
                f"invoices/Invoice_{variant}_{index:03d}.pdf",
                Entry(path=f"invoices/Invoice_{variant}_{index:03d}.pdf", family="invoices",
                      kind="invoice", rows=1, line_items=truth["line_items"],
                      totals={"value": truth["value"], "taxable": truth["taxable"]},
                      flags=flags, notes=notes),
            )

    # Deliberately invalid date: the engine should not invent one.
    if not extras:
        return
    lines, truth = _invoice_lines(
        number="SYN/26-27/9001", date="32/13/2026", gstin=make_gstin(rng), hsn="998314",
        items=_item_set(rng, 1, rate_pct=Decimal("18"), hsn="998314"),
        place_of_supply="27-Maharashtra", supplier="Synthetic Traders Pvt Ltd",
        customer="Demo Enterprises", customer_gstin=None, inter_state=False,
    )
    write_pdf(corpus.path("invoices/Invoice_bad_date_901.pdf"), [lines])
    corpus.add(
        "invoices/Invoice_bad_date_901.pdf",
        Entry(path="invoices/Invoice_bad_date_901.pdf", family="invoices", kind="invoice",
              rows=1, line_items=truth["line_items"],
              totals={"value": truth["value"], "taxable": truth["taxable"]},
              flags=["date_missing"], notes="invoice date 32/13/2026 is impossible"),
    )


# ---------------------------------------------------------------------------
# GST returns
# ---------------------------------------------------------------------------


def _gstr2b_payload(rng: random.Random, parties: int, invoices_each: int, notes: int) -> dict:
    b2b = []
    for party_index in range(parties):
        ctin = make_gstin(rng)
        group = []
        for inv_index in range(invoices_each):
            taxable = 1000 * (inv_index + 1)
            group.append(
                {
                    "inum": f"INV/{party_index + 1:02d}/{inv_index + 1:04d}",
                    "dt": f"{(inv_index % 27) + 1:02d}-07-2026",
                    "val": round(taxable * 1.18, 2),
                    "txval": taxable,
                    "camt": round(taxable * 0.09, 2),
                    "samt": round(taxable * 0.09, 2),
                }
            )
        b2b.append({"ctin": ctin, "trdnm": f"Supplier {party_index + 1}", "inv": group})
    cdnr = []
    for index in range(notes):
        cdnr.append(
            {
                "ctin": make_gstin(rng),
                "trdnm": f"Supplier note {index + 1}",
                "nt": [
                    {
                        "ntnum": f"CN/{index + 1:03d}",
                        "dt": f"{(index % 27) + 1:02d}-07-2026",
                        "ntty": "C",
                        "val": 1180,
                        "txval": 1000,
                        "camt": 90,
                        "samt": 90,
                    }
                ],
            }
        )
    return {
        "gstin": make_gstin(rng, "29"),
        "rtnprd": "072026",
        "version": "3.0",
        "data": {"docdata": {"b2b": b2b, "cdnr": cdnr}},
    }


def _gstr1_payload(rng: random.Random, b2b_parties: int, invoices_each: int, notes: int,
                   hsn_rows: int, b2cl: int, b2cs: int) -> dict:
    b2b = []
    for party_index in range(b2b_parties):
        ctin = make_gstin(rng)
        group = []
        for inv_index in range(invoices_each):
            taxable = 5000 * (inv_index + 1)
            group.append(
                {
                    "inum": f"OUT/{party_index + 1:02d}/{inv_index + 1:03d}",
                    "idt": f"{(inv_index % 27) + 1:02d}-07-2026",
                    "val": round(taxable * 1.18, 2),
                    "itms": [{"itm_det": {"txval": taxable, "camt": taxable * 0.09,
                                          "samt": taxable * 0.09}}],
                }
            )
        b2b.append({"ctin": ctin, "trdnm": f"Buyer {party_index + 1}", "inv": group})
    cdnr = [
        {
            "ctin": make_gstin(rng),
            "nt": [
                {
                    "ntnum": f"CN/{index + 1:03d}",
                    "nt_dt": f"{(index % 27) + 1:02d}-07-2026",
                    "val": 1180,
                    "itms": [{"itm_det": {"txval": 1000, "camt": 90, "samt": 90}}],
                }
            ],
        }
        for index in range(notes)
    ]
    hsn = {"data": [{"hsn_sc": f"99{index:02d}", "txval": 1500 * (index + 1)} for index in range(hsn_rows)]}
    payload = {"gstin": make_gstin(rng, "29"), "fp": "072026", "b2b": b2b, "cdnr": cdnr, "hsn": hsn}
    if b2cl:
        payload["b2cl"] = [
            {
                "pos": "29",
                "inv": [
                    {
                        "inum": f"B2CL/{index + 1:02d}",
                        "idt": "10-07-2026",
                        "val": 30000,
                        "itms": [{"itm_det": {"txval": 25000, "iamt": 5000}}],
                    }
                    for index in range(b2cl)
                ],
            }
        ]
    if b2cs:
        payload["b2cs"] = [{"pos": "29", "txval": 10000, "camt": 900, "samt": 900} for _ in range(b2cs)]
    return payload


def _gstr3b_payload(rng: random.Random, *, empty: bool = False) -> dict:
    if empty:
        return {"gstin": make_gstin(rng, "29"), "ret_period": "072026"}
    return {
        "gstin": make_gstin(rng, "29"),
        "ret_period": "072026",
        "sup_details": {
            "osup_det": {"txval": 65000, "iamt": 0, "camt": 5850, "samt": 5850},
            "osup_zero": {"txval": 12000, "iamt": 0, "camt": 0, "samt": 0},
            "osup_nil_exmp": {"txval": 4000, "iamt": 0, "camt": 0, "samt": 0},
        },
        "itc_elg": {"itc_avl": [{"ty": "IMPG", "txval": 1000, "iamt": 180}]},
        "inward_sup": {"isup_details": [{"ty": "GSTR", "inter": 100, "intra": 200}]},
    }


def _write_json(corpus: Corpus, relative: str, payload: dict | str) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    dest = corpus.path(relative)
    dest.write_text(text + "\n", encoding="utf-8")


def build_gst(corpus: Corpus, plan: list[tuple[str, int]] | None = None, scale: int = 1,
              large: bool = True) -> None:
    rng = corpus.rng
    variants = plan or [
        ("2b_valid", 12),
        ("2b_empty", 3),
        ("2b_malformed", 3),
        ("2b_schema", 3),
        ("1_valid", 8),
        ("1_empty", 2),
        ("1_malformed", 2),
        ("3b_valid", 8),
        ("3b_empty", 2),
        ("3b_malformed", 2),
    ]
    if scale != 1:
        variants = [(variant, count * scale) for variant, count in variants]
    index = 0
    for variant, count in variants:
        for _ in range(count):
            index += 1
            if variant.startswith("2b"):
                name = f"GSTR-2B_{variant}_{index:03d}.json"
                if variant == "2b_valid":
                    if index == 1 and large:
                        parties, each, notes = 4, 1250, 5  # ~5,000 invoices
                        name = "GSTR-2B_large_5000.json"
                    else:
                        parties = rng.choice((1, 2, 3, 5))
                        each = rng.choice((1, 2, 4, 8, 20))
                        notes = rng.choice((0, 1, 2))
                    payload = _gstr2b_payload(rng, parties, each, notes)
                    rows = parties * each + notes
                    value = sum(
                        float(inv["val"])
                        for party in payload["data"]["docdata"]["b2b"]
                        for inv in party["inv"]
                    ) + notes * 1180.0
                    taxable = sum(
                        float(inv["txval"])
                        for party in payload["data"]["docdata"]["b2b"]
                        for inv in party["inv"]
                    ) + notes * 1000.0
                    _write_json(corpus, f"gst/{name}", payload)
                    corpus.add(
                        f"gst/{name}",
                        Entry(path=f"gst/{name}", family="gst", kind="gstr_2b", rows=rows,
                              totals={"value": value, "taxable": taxable},
                              notes="valid GSTR-2B"),
                    )
                    continue
                if variant == "2b_empty":
                    _write_json(corpus, f"gst/{name}",
                                {"gstin": make_gstin(rng, "29"), "rtnprd": "072026",
                                 "data": {"docdata": {}}})
                    corpus.add(
                        f"gst/{name}",
                        Entry(path=f"gst/{name}", family="gst", kind="gstr_2b",
                              outcome="needs_review", rows=0, totals={},
                              notes="valid empty GSTR-2B"),
                    )
                    continue
                if variant == "2b_malformed":
                    _write_json(corpus, f"gst/{name}",
                                '{"gstin": "29ABCDE1234F1Z5", "file": "%s", '
                                '"data": {"docdata": {"b2b": [' % name)
                    corpus.add(
                        f"gst/{name}",
                        Entry(path=f"gst/{name}", family="gst", kind="gstr_2b",
                              outcome="failed", rows=0, totals={},
                              notes="truncated JSON"),
                    )
                    continue
                _write_json(corpus, f"gst/{name}",
                            {"gstin": make_gstin(rng, "29"), "rtnprd": "072026",
                             "schema_version": "9.9", "documents": []})
                corpus.add(
                    f"gst/{name}",
                    Entry(path=f"gst/{name}", family="gst", kind="gstr_2b",
                          outcome="needs_review", rows=0, totals={},
                          notes="valid JSON, unknown schema version"),
                )
                continue

            if variant.startswith("1_"):
                name = f"GSTR-1_{variant}_{index:03d}.json"
                if variant == "1_valid":
                    parties = rng.choice((1, 2, 4))
                    each = rng.choice((1, 3, 8))
                    notes = rng.choice((0, 1, 3))
                    hsn_rows = rng.choice((1, 3, 5))
                    b2cl = rng.choice((0, 1, 2))
                    b2cs = rng.choice((0, 1, 3))
                    payload = _gstr1_payload(rng, parties, each, notes, hsn_rows, b2cl, b2cs)
                    # Only B2B, credit notes and the HSN summary are surfaced by the
                    # parser today; B2CL/B2CS are written but not counted.
                    rows = parties * each + notes + hsn_rows
                    value = sum(
                        float(inv["val"])
                        for party in payload["b2b"]
                        for inv in party["inv"]
                    ) + notes * 1180.0
                    taxable = sum(
                        float(inv["itms"][0]["itm_det"]["txval"])
                        for party in payload["b2b"]
                        for inv in party["inv"]
                    ) + notes * 1000.0
                    taxable += sum(float(item["txval"]) for item in payload["hsn"]["data"])
                    _write_json(corpus, f"gst/{name}", payload)
                    corpus.add(
                        f"gst/{name}",
                        Entry(path=f"gst/{name}", family="gst", kind="gstr_1", rows=rows,
                              totals={"value": value, "taxable": taxable},
                              notes="GSTR-1 with B2B/CN/HSN (+B2CL/B2CS not surfaced by parser)"),
                    )
                    continue
                if variant == "1_empty":
                    _write_json(corpus, f"gst/{name}",
                                {"gstin": make_gstin(rng, "29"), "fp": "072026", "b2b": [], "hsn": {"data": []}})
                    corpus.add(
                        f"gst/{name}",
                        Entry(path=f"gst/{name}", family="gst", kind="gstr_1",
                              outcome="needs_review", rows=0, totals={},
                              notes="valid empty GSTR-1"),
                    )
                    continue
                _write_json(corpus, f"gst/{name}", '{"gstin": "29ABCDE1234F1Z5", "file": "%s", "fp": "072026", "b2b": [' % name)
                corpus.add(
                    f"gst/{name}",
                    Entry(path=f"gst/{name}", family="gst", kind="gstr_1",
                          outcome="failed", rows=0, totals={},
                          notes="truncated JSON"),
                )
                continue

            name = f"GSTR-3B_{variant}_{index:03d}.json"
            if variant == "3b_valid":
                payload = _gstr3b_payload(rng)
                taxable = 65000.0 + 12000.0 + 4000.0 + 1000.0 + 300.0
                _write_json(corpus, f"gst/{name}", payload)
                corpus.add(
                    f"gst/{name}",
                    Entry(path=f"gst/{name}", family="gst", kind="gstr_3b", rows=5,
                          totals={"taxable": taxable},
                          notes="valid GSTR-3B with ITC and inward supplies"),
                )
                continue
            if variant == "3b_empty":
                _write_json(corpus, f"gst/{name}", _gstr3b_payload(rng, empty=True))
                corpus.add(
                    f"gst/{name}",
                    Entry(path=f"gst/{name}", family="gst", kind="gstr_3b", rows=1, totals={},
                          notes="GSTR-3B with no blocks: one placeholder row"),
                )
                continue
            _write_json(corpus, f"gst/{name}", '{"gstin": "29ABCDE1234F1Z5", "file": "%s", "ret_period": ' % name)
            corpus.add(
                f"gst/{name}",
                Entry(path=f"gst/{name}", family="gst", kind="gstr_3b",
                      outcome="failed", rows=0, totals={},
                      notes="truncated JSON"),
            )


# ---------------------------------------------------------------------------
# Books (Tally / Zoho / SAP)
# ---------------------------------------------------------------------------


def _tally_xml(rng: random.Random, vouchers: int, *, purchases: int | None = None) -> tuple[str, dict]:
    purchase_count = purchases if purchases is not None else vouchers
    chunks = []
    total = 0.0
    taxable_total = 0.0
    for index in range(1, vouchers + 1):
        is_purchase = index <= purchase_count
        amount = 1180 * index
        taxable = 1000 * index
        total += amount
        taxable_total += taxable
        voucher_type = "Purchase" if is_purchase else "Sales"
        prefix = "PUR" if is_purchase else "SAL"
        gstin = make_gstin(rng)
        chunks.append(
            "   <VOUCHER VCHTYPE=\"{type}\">\n"
            "    <DATE>202607{day:02d}</DATE>\n"
            "    <VOUCHERNUMBER>{prefix}-{number}</VOUCHERNUMBER>\n"
            "    <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>\n"
            "    <PARTYGSTIN>{gstin}</PARTYGSTIN>\n"
            "    <AMOUNT>{amount}</AMOUNT>\n"
            "    <TAXABLEVALUE>{taxable}</TAXABLEVALUE>\n"
            "    <HSNCODE>998314</HSNCODE>\n"
            "   </VOUCHER>".format(
                type=voucher_type,
                day=(index % 27) + 1,
                prefix=prefix,
                number=index,
                party=VENDORS[index % len(VENDORS)].title(),
                gstin=gstin,
                amount=-amount if is_purchase else amount,
                taxable=taxable,
            )
        )
    xml = (
        '<?xml version="1.0"?>\n<ENVELOPE>\n'
        " <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>\n"
        " <BODY>\n  <TALLYMESSAGE>\n" + "\n".join(chunks) + "\n  </TALLYMESSAGE>\n </BODY>\n</ENVELOPE>\n"
    )
    return xml, {"value": float(total), "taxable": float(taxable_total)}


def _zoho_rows(rng: random.Random, rows: int, *, purchases: bool) -> tuple[list[list], dict]:
    if purchases:
        header = ["Bill Number", "Bill Date", "GST Identification Number (GSTIN)",
                  "Item Tax %", "Total", "Vendor Name"]
    else:
        header = ["Invoice Number", "Invoice Date", "GST Treatment",
                  "GST Identification Number (GSTIN)", "Item Tax %", "Total", "Customer Name"]
    records = [header]
    total = 0.0
    for index in range(1, rows + 1):
        amount = 590 + index * 17
        total += amount
        gstin = make_gstin(rng)
        name = VENDORS[index % len(VENDORS)] if purchases else BUYERS[index % len(BUYERS)]
        if purchases:
            records.append([f"BILL-{200 + index}", f"2026-07-{(index % 27) + 1:02d}", gstin, 18, amount, name])
        else:
            records.append([f"INV-{200 + index}", f"2026-07-{(index % 27) + 1:02d}", "taxable",
                            gstin, 18, amount, f"{name.title()}, Andheri"])
    return records, {"value": float(total)}


def build_books(corpus: Corpus, plan: list[tuple[str, int]] | None = None, scale: int = 1,
                large: bool = True) -> None:
    rng = corpus.rng
    variants = plan or [
        ("tally_xml", 10),
        ("tally_zip", 5),
        ("zoho_csv", 8),
        ("zoho_xlsx", 6),
        ("sap_csv", 4),
        ("sap_pdf", 2),
    ]
    if scale != 1:
        variants = [(variant, count * scale) for variant, count in variants]
    index = 0
    for variant, count in variants:
        for _ in range(count):
            index += 1
            if variant in {"tally_xml", "tally_zip"}:
                vouchers = rng.choice((5, 12, 40, 120, 400))
                if index == 1 and large:
                    vouchers = 5000
                xml, totals = _tally_xml(rng, vouchers, purchases=vouchers * 3 // 4)
                if variant == "tally_xml":
                    name = f"Tally_Daybook_{variant}_{index:03d}.xml"
                    corpus.path(f"books/{name}").write_text(xml, encoding="utf-8")
                else:
                    name = f"Tally_Backup_{index:03d}.zip"
                    write_zip(corpus.path(f"books/{name}"), {"DAYBOOK.xml": xml, "README.txt": "Tally export\n"})
                corpus.add(
                    f"books/{name}",
                    Entry(path=f"books/{name}", family="books", kind="tally", rows=vouchers,
                          totals=totals, notes=f"Tally export with {vouchers} vouchers"),
                )
                continue
            if variant in {"zoho_csv", "zoho_xlsx"}:
                rows = rng.choice((5, 20, 60, 300))
                purchases = index % 3 == 0
                records, totals = _zoho_rows(rng, rows, purchases=purchases)
                extension = "csv" if variant == "zoho_csv" else "xlsx"
                if extension == "csv":
                    name = f"Zoho_Books_{'Bills' if purchases else 'Invoices'}_{index:03d}.csv"
                    import io

                    buffer = io.StringIO()
                    writer = csv.writer(buffer, lineterminator="\n")
                    writer.writerows(records)
                    corpus.path(f"books/{name}").write_text(buffer.getvalue(), encoding="utf-8")
                else:
                    name = f"Zoho_Books_{'Bills' if purchases else 'Invoices'}_{index:03d}.xlsx"
                    write_xlsx(corpus.path(f"books/{name}"), "Invoices", records)
                corpus.add(
                    f"books/{name}",
                    Entry(path=f"books/{name}", family="books", kind="zoho", rows=rows,
                          totals=totals,
                          notes=f"Zoho {'bills (purchase)' if purchases else 'invoices (sales)'} export"),
                )
                continue
            rows = rng.choice((3, 8, 30, 120))
            debit_total = 0.0
            credit_total = 0.0
            body = []
            for row_index in range(1, rows + 1):
                debit = 1250.0 * row_index if row_index % 2 else 0.0
                credit = 0.0 if row_index % 2 else 750.5 * row_index
                debit_total += debit
                credit_total += credit
                body.append(
                    [
                        "1000",
                        "400000",
                        "Office Supplies",
                        f"2026-07-{(row_index % 27) + 1:02d}",
                        f"{1000000000 + row_index}",
                        "KR" if debit else "KZ",
                        f"REF-{1000 + row_index}-{index:03d}",
                        f"Synthetic line {row_index} of file {index}",
                        f"{debit:,.2f}",
                        f"{credit:,.2f}",
                        "INR",
                    ]
                )
            title = "SAP General Ledger Line Item Report - SYNTHETIC TEST DATA"
            header = ["Company Code", "GL Account", "Account Name", "Posting Date", "Document Number",
                      "Document Type", "Reference", "Description", "Debit", "Credit", "Currency"]
            if variant == "sap_csv":
                name = f"SAP_GL_{index:03d}.csv"
                import io

                buffer = io.StringIO()
                buffer.write(title + "\n")
                writer = csv.writer(buffer, lineterminator="\n")
                writer.writerow(header)
                writer.writerows(body)
                corpus.path(f"books/{name}").write_text(buffer.getvalue(), encoding="utf-8")
            else:
                name = f"SAP_GL_{index:03d}.pdf"
                # Positioned columns, the way SAP's own PDF export lays them out.
                doc = pymupdf.open()
                page = doc.new_page(width=PAGE_W, height=PAGE_H)
                page.insert_text((40, 56), title, fontsize=10, fontname="cour")
                columns = (40, 140, 230, 320, 420, 510)
                labels = ("Company Code", "GL Account", "Posting Date", "Document Number", "Debit", "Credit")
                y = 84.0
                for x, label in zip(columns, labels):
                    page.insert_text((x, y), label, fontsize=9, fontname="cour")
                y += 16
                for csv_row in body:
                    values = (csv_row[0], csv_row[1], csv_row[3], csv_row[4], csv_row[8], csv_row[9])
                    for x, value in zip(columns, values):
                        page.insert_text((x, y), value, fontsize=9, fontname="cour")
                    y += 15
                doc.set_metadata({})
                doc.save(corpus.path(f"books/{name}"), garbage=3, deflate=True, no_new_id=1)
                doc.close()
            corpus.add(
                f"books/{name}",
                Entry(path=f"books/{name}", family="books", kind="sap", rows=rows,
                      totals={"debit": debit_total, "credit": credit_total},
                      notes="SAP general ledger export"),
            )


# ---------------------------------------------------------------------------
# Junk and hostile files
# ---------------------------------------------------------------------------


def _tiny_png() -> bytes:
    import io

    buffer = io.BytesIO()
    Image.new("L", (1, 1), 255).save(buffer, "PNG")
    return buffer.getvalue()


def _tiny_jpeg() -> bytes:
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 255, 255)).save(buffer, "JPEG")
    return buffer.getvalue()


def build_junk(corpus: Corpus) -> None:
    rng = corpus.rng
    invoice_probe = corpus.path("invoices/Invoice_cgst_sgst_001.pdf").read_bytes()

    # 01 - binary garbage -------------------------------------------------
    corpus.path("junk/01-binary/empty.pdf").write_bytes(b"")
    corpus.add("junk/01-binary/empty.pdf",
               Entry(path="junk/01-binary/empty.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zero bytes"))
    corpus.path("junk/01-binary/one_byte.pdf").write_bytes(b"x")
    corpus.add("junk/01-binary/one_byte.pdf",
               Entry(path="junk/01-binary/one_byte.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="1 byte"))
    corpus.path("junk/01-binary/truncated_invoice.pdf").write_bytes(invoice_probe[: len(invoice_probe) // 3])
    corpus.add("junk/01-binary/truncated_invoice.pdf",
               Entry(path="junk/01-binary/truncated_invoice.pdf", family="junk", kind="invoice",
                     outcome="needs_review", rows=None, totals={},
                     notes="PDF cut in half; repaired by the reader, rows not asserted"))
    corpus.path("junk/01-binary/header_only.pdf").write_bytes(b"%PDF-1.4\n")
    corpus.add("junk/01-binary/header_only.pdf",
               Entry(path="junk/01-binary/header_only.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="PDF header with no body"))
    corpus.path("junk/01-binary/truncated_backup.zip").write_bytes(b"PK\x03\x04garbage")
    corpus.add("junk/01-binary/truncated_backup.zip",
               Entry(path="junk/01-binary/truncated_backup.zip", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="broken zip container"))
    corpus.path("junk/01-binary/corrupt_workbook.xlsx").write_bytes(b"PK\x03\x04not-a-workbook")
    corpus.add("junk/01-binary/corrupt_workbook.xlsx",
               Entry(path="junk/01-binary/corrupt_workbook.xlsx", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zip header, unreadable spreadsheet"))
    corpus.path("junk/01-binary/corrupt_report.docx").write_bytes(b"PK\x03\x04not-a-document")
    corpus.add("junk/01-binary/corrupt_report.docx",
               Entry(path="junk/01-binary/corrupt_report.docx", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zip content with a .docx extension"))
    corpus.path("junk/01-binary/invoice_bytes_named_txt.txt").write_bytes(
        corpus.path("invoices/Invoice_cgst_sgst_010.pdf").read_bytes())
    corpus.add("junk/01-binary/invoice_bytes_named_txt.txt",
               Entry(path="junk/01-binary/invoice_bytes_named_txt.txt", family="junk", kind="invoice",
                     rows=1, line_items=None, totals={},
                     notes="PDF bytes with a .txt extension; content wins over the name"))
    gz = b"\x1f\x8b\x08\x00" + bytes(rng.randrange(0, 255) for _ in range(120))
    corpus.path("junk/01-binary/mystery.gz").write_bytes(gz)
    corpus.add("junk/01-binary/mystery.gz",
               Entry(path="junk/01-binary/mystery.gz", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="gzip container, not a supported export"))
    big = corpus.path("junk/01-binary/large_blob_50mb.bin")
    with big.open("wb") as handle:
        remaining = 50 * 1024 * 1024
        while remaining:
            chunk = min(1024 * 1024, remaining)
            handle.write(rng.randbytes(chunk))
            remaining -= chunk
    corpus.add("junk/01-binary/large_blob_50mb.bin",
               Entry(path="junk/01-binary/large_blob_50mb.bin", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="50 MB binary blob"))

    # 02 - text-shaped junk ----------------------------------------------
    corpus.path("junk/02-text/truncated.json").write_text('{"gstin": "29ABCDE1234F1Z5", "data": ', encoding="utf-8")
    corpus.add("junk/02-text/truncated.json",
               Entry(path="junk/02-text/truncated.json", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="truncated JSON"))
    corpus.path("junk/02-text/truncated.xml").write_text(
        '<?xml version="1.0"?>\n<ENVELOPE><BODY><TALLYMESSAGE><VOUCHER', encoding="utf-8")
    corpus.add("junk/02-text/truncated.xml",
               Entry(path="junk/02-text/truncated.xml", family="junk", kind="tally",
                     outcome="needs_review", rows=0, notes="Tally markers, broken XML"))
    corpus.path("junk/02-text/plain_text.pdf").write_text("This is plain text with a .pdf name.\n", encoding="utf-8")
    corpus.add("junk/02-text/plain_text.pdf",
               Entry(path="junk/02-text/plain_text.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="text content named .pdf"))
    write_pdf(
        corpus.path("junk/02-text/meeting_notes.pdf"),
        [["Team meeting notes", "Follow up on the pending reconciliation", "No GSTIN or invoice table here"]],
    )
    corpus.add("junk/02-text/meeting_notes.pdf",
               Entry(path="junk/02-text/meeting_notes.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="PDF with neither bank nor invoice wording"))

    corpus.path("junk/02-text/notes.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    corpus.add("junk/02-text/notes.json",
               Entry(path="junk/02-text/notes.json", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="JSON array, not a GSTR object"))
    corpus.path("junk/02-text/settings.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    corpus.add("junk/02-text/settings.json",
               Entry(path="junk/02-text/settings.json", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="JSON object, no GSTR schema"))
    corpus.path("junk/02-text/empty.json").write_text("{}", encoding="utf-8")
    corpus.add("junk/02-text/empty.json",
               Entry(path="junk/02-text/empty.json", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="empty JSON object"))
    corpus.path("junk/02-text/empty.xml").write_text("<ENVELOPE></ENVELOPE>", encoding="utf-8")
    corpus.add("junk/02-text/empty.xml",
               Entry(path="junk/02-text/empty.xml", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="XML without Tally markers"))
    corpus.path("junk/02-text/no_header.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    corpus.add("junk/02-text/no_header.csv",
               Entry(path="junk/02-text/no_header.csv", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="CSV without an export header"))
    corpus.path("junk/02-text/blank.txt").write_text("   \n\n", encoding="utf-8")
    corpus.add("junk/02-text/blank.txt",
               Entry(path="junk/02-text/blank.txt", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="whitespace only"))

    # 03 - awkward names -------------------------------------------------
    names = [
        "ग्राहक बिल जुलाई 2026.pdf",
        "client invoice (final) 'copy'.pdf",
        "statement with spaces and CAPS.PDF",
        "report#4 & notes [draft].pdf",
        "রিপোর্ট ২০২৬.pdf",
        "invoice-no-000.png",
        "copy of copy of ledger.pdf",
        "..double.dot..name.pdf",
    ]
    for position, name in enumerate(names):
        relative = f"junk/03-names/{name}"
        dest = corpus.path(relative)
        # A different invoice under every name, so intake never sees a duplicate.
        payload = corpus.path(f"invoices/Invoice_cgst_sgst_{position + 2:03d}.pdf").read_bytes()
        if name.lower().endswith((".png", ".jpg")):
            rasterize(dest, [["TAX INVOICE", "Invoice No NAME/1", "Invoice Date 05/07/2026",
                              "Supplier GSTIN 27AAPFU0939F1ZV", "HSN 998314",
                              "HSN Qty Rate Taxable Amount",
                              "Fees 998314 1 5000.00 5000.00 5900.00",
                              "Taxable value 5000.00", "CGST 450.00  SGST 450.00",
                              "Invoice value 5900.00"]], dpi=150)
            corpus.add(relative, Entry(path=relative, family="junk", kind="invoice", rows=1,
                                       line_items=1, totals={"value": 5900.0, "taxable": 5000.0},
                                       flags=[], notes="unicode/space file name, image invoice",
                                       requires=["ocr"], advisory=True))
            continue
        if name.lower().endswith(".png"):
            dest.write_bytes(_tiny_png())
            corpus.add(relative, Entry(path=relative, family="junk", kind="unknown",
                                       outcome="unclassified", rows=None, notes="tiny image"))
            continue
        dest.write_bytes(payload)
        if name.startswith("."):
            corpus.add(relative, Entry(path=relative, family="junk", kind="invoice",
                                       outcome="skipped_by_name", rows=None,
                                       notes="hidden dot-file: intake skips it by name"))
            continue
        corpus.add(relative, Entry(path=relative, family="junk", kind="invoice", rows=1,
                                   line_items=None, totals={}, notes="awkward file name, valid PDF"))

    # 04 - duplicate bytes ------------------------------------------------
    for pair in range(1, 5):
        first = f"junk/04-duplicates/bill_{pair:02d}_a.pdf"
        second = f"junk/04-duplicates/bill_{pair:02d}_b.pdf"
        payload = corpus.path(f"invoices/Invoice_cgst_sgst_{pair + 1:03d}.pdf").read_bytes()
        corpus.path(first).write_bytes(payload)
        corpus.path(second).write_bytes(payload)
        corpus.add(first, Entry(path=first, family="junk", kind="invoice", rows=1, line_items=None,
                                totals={}, notes="byte-identical duplicate pair (kept)"))
        corpus.add(second, Entry(path=second, family="junk", kind="invoice",
                                 outcome="skipped_duplicate", rows=None,
                                 notes="byte-identical duplicate pair (skipped at intake)"))

    # 05 - archives -------------------------------------------------------
    # The inner archive is built in memory: leaving it on disk would put a file
    # in the tree that the manifest does not describe.
    inner = _zip_bytes({"DAYBOOK.xml": b"<ENVELOPE><TALLYMESSAGE></TALLYMESSAGE></ENVELOPE>"})
    write_zip(corpus.path("junk/05-archives/nested.zip"),
              {"inner.zip": inner, "readme.txt": "nested containers\n"})
    corpus.add("junk/05-archives/nested.zip",
               Entry(path="junk/05-archives/nested.zip", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zip inside a zip"))
    write_zip(corpus.path("junk/05-archives/photos.zip"),
              {"scan1.png": _tiny_png(), "scan2.png": _tiny_png()})
    corpus.add("junk/05-archives/photos.zip",
               Entry(path="junk/05-archives/photos.zip", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zip of images, no export"))
    xml, _totals = _tally_xml(rng, 6)
    write_zip(corpus.path("junk/05-archives/Tally_nested_folder.zip"), {"backup/DAYBOOK.xml": xml})
    corpus.add("junk/05-archives/Tally_nested_folder.zip",
               Entry(path="junk/05-archives/Tally_nested_folder.zip", family="junk", kind="tally",
                     rows=6, totals={}, notes="Tally export inside a subfolder"))
    write_zip(corpus.path("junk/05-archives/empty.zip"), {})
    corpus.add("junk/05-archives/empty.zip",
               Entry(path="junk/05-archives/empty.zip", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="empty zip"))
    corpus.path("junk/05-archives/tar_like.tar").write_bytes(b"ustar\x00" + rng.randbytes(400))
    corpus.add("junk/05-archives/tar_like.tar",
               Entry(path="junk/05-archives/tar_like.tar", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="tar container, unsupported"))
    # A legacy .xls is refused by name *for the whole selection*: it lives in
    # its own folder so the refusal is visible instead of hiding five other files.
    corpus.path("junk/09-legacy-xls/attendance.xls").write_bytes(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + rng.randbytes(64))
    corpus.add("junk/09-legacy-xls/attendance.xls",
               Entry(path="junk/09-legacy-xls/attendance.xls", family="junk", kind="unknown",
                     outcome="rejected_selection", rows=None,
                     notes="legacy .xls: the engine refuses the whole selection"))

    # 06 - images ---------------------------------------------------------
    images = {
        "tiny.png": _tiny_png(),
        "tiny.jpg": _tiny_jpeg(),
        "blank_large.png": None,
        "corrupt.png": b"\x89PNG\r\n\x1a\nbroken",
        "photo.jpg": ["Photograph of a whiteboard", "Nothing relevant on this page"],
        "scan_no_text.png": ["Blank page", "No printed content at all"],
        "receipt.jpg": ["Corner shop receipt", "Two items, total 250"],
        "blank.tiff": None,
    }
    for name, payload in images.items():
        relative = f"junk/06-images/{name}"
        dest = corpus.path(relative)
        if isinstance(payload, list):
            rasterize(dest, [payload], dpi=110)
        elif payload is not None:
            dest.write_bytes(payload)
        elif name.endswith(".tiff"):
            Image.new("L", (200, 200), 255).save(dest, "TIFF")
        else:
            Image.new("L", (900, 1200), 255).save(dest, "PNG")
        corpus.add(relative, Entry(path=relative, family="junk", kind="unknown",
                                   outcome="unclassified", rows=None, notes="image without invoice text"))

    # 07 - office files ---------------------------------------------------
    workbook = corpus.path("junk/07-office/attendance.xlsx")
    write_xlsx(workbook, "Sheet1", [["Name", "Day"], ["Synthetic", 1]])
    corpus.add("junk/07-office/attendance.xlsx",
               Entry(path="junk/07-office/attendance.xlsx", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="spreadsheet with unrelated headers"))
    write_zip(corpus.path("junk/07-office/notes.docx"), {"word/document.xml": "<w:document/>"})
    corpus.add("junk/07-office/notes.docx",
               Entry(path="junk/07-office/notes.docx", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="word document, not a source file"))
    corpus.path("junk/07-office/broken.xlsx").write_bytes(b"PK\x03\x04" + rng.randbytes(200))
    corpus.add("junk/07-office/broken.xlsx",
               Entry(path="junk/07-office/broken.xlsx", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zip with a broken workbook"))
    corpus.path("junk/07-office/broken.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\n")
    corpus.add("junk/07-office/broken.pdf",
               Entry(path="junk/07-office/broken.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="PDF stub with no pages"))
    corpus.path("junk/07-office/empty.docx").write_bytes(b"")
    corpus.add("junk/07-office/empty.docx",
               Entry(path="junk/07-office/empty.docx", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zero-byte document"))
    corpus.path("junk/07-office/legacy_word.doc").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + rng.randbytes(40))
    corpus.add("junk/07-office/legacy_word.doc",
               Entry(path="junk/07-office/legacy_word.doc", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="legacy .doc binary"))
    corpus.path("junk/07-office/screenshot.png").write_bytes(_tiny_png())
    corpus.add("junk/07-office/screenshot.png",
               Entry(path="junk/07-office/screenshot.png", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="1x1 pixel"))
    corpus.path("junk/07-office/logo.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 " + rng.randbytes(32))
    corpus.add("junk/07-office/logo.webp",
               Entry(path="junk/07-office/logo.webp", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="webp image"))

    # 08 - edge cases the engine must survive -----------------------------
    corpus.path("junk/08-edge/unknown_bank_document.pdf").write_bytes(
        corpus.path("invoices/Invoice_cgst_sgst_011.pdf").read_bytes())
    corpus.add("junk/08-edge/unknown_bank_document.pdf",
               Entry(path="junk/08-edge/unknown_bank_document.pdf", family="junk", kind="invoice",
                     rows=1, line_items=1, totals={}, notes="invoice named like a bank document"))
    corpus.path("junk/08-edge/gstr_with_no_rows.json").write_text(
        json.dumps({"gstin": "29ABCDE1234F1Z5", "data": {"docdata": {"b2b": []}}}), encoding="utf-8")
    corpus.add("junk/08-edge/gstr_with_no_rows.json",
               Entry(path="junk/08-edge/gstr_with_no_rows.json", family="junk", kind="gstr_2b",
                     outcome="needs_review", rows=0, notes="valid 2B with no invoices"))
    corpus.path("junk/08-edge/gstr_binary.json").write_bytes(b"\x00\x01\x02\x03")
    corpus.add("junk/08-edge/gstr_binary.json",
               Entry(path="junk/08-edge/gstr_binary.json", family="junk", kind="unknown",
                     outcome="unclassified", rows=0, notes="binary content named .json"))
    corpus.path("junk/08-edge/tally_empty.xml").write_text("<ENVELOPE><TALLYMESSAGE/></ENVELOPE>", encoding="utf-8")
    corpus.add("junk/08-edge/tally_empty.xml",
               Entry(path="junk/08-edge/tally_empty.xml", family="junk", kind="tally",
                     outcome="needs_review", rows=0, notes="Tally markers, no vouchers"))
    corpus.path("junk/08-edge/tally_plain_numbers.xml").write_text(
        '<ENVELOPE><TALLYMESSAGE><VOUCHER VCHTYPE="Purchase"><DATE>not-a-date</DATE>'
        "<AMOUNT>abc</AMOUNT></VOUCHER></TALLYMESSAGE></ENVELOPE>", encoding="utf-8")
    corpus.add("junk/08-edge/tally_plain_numbers.xml",
               Entry(path="junk/08-edge/tally_plain_numbers.xml", family="junk", kind="tally",
                     rows=1, totals={}, notes="voucher with unreadable date and amount"))
    corpus.path("junk/08-edge/zoho_empty.csv").write_text("Invoice Number,Total\n", encoding="utf-8")
    corpus.add("junk/08-edge/zoho_empty.csv",
               Entry(path="junk/08-edge/zoho_empty.csv", family="junk", kind="zoho",
                     outcome="needs_review", rows=0, notes="Zoho headers, no records"))
    corpus.path("junk/08-edge/zoho_missing_columns.csv").write_text(
        "Invoice Number,Total\nINV-1,not a number\n", encoding="utf-8")
    corpus.add("junk/08-edge/zoho_missing_columns.csv",
               Entry(path="junk/08-edge/zoho_missing_columns.csv", family="junk", kind="zoho",
                     rows=1, totals={}, notes="Zoho row with a non-numeric total"))
    corpus.path("junk/08-edge/sap_empty.csv").write_text(
        "SAP General Ledger Line Item Report - SYNTHETIC TEST DATA\n"
        "Company Code,GL Account,Posting Date,Document Number,Debit,Credit\n", encoding="utf-8")
    corpus.add("junk/08-edge/sap_empty.csv",
               Entry(path="junk/08-edge/sap_empty.csv", family="junk", kind="sap",
                     outcome="needs_review", rows=0,
                     notes="SAP export with a header but no data rows"))
    corpus.path("junk/08-edge/document.rtf").write_text(r"{\rtf1\ansi not a source file}", encoding="utf-8")
    corpus.add("junk/08-edge/document.rtf",
               Entry(path="junk/08-edge/document.rtf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="rtf file"))
    corpus.path("junk/08-edge/no_extension").write_bytes(b"plain bytes, no suffix")
    corpus.add("junk/08-edge/no_extension",
               Entry(path="junk/08-edge/no_extension", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="no file extension"))
    corpus.path("junk/08-edge/duplicate_of_invoice.pdf").write_bytes(
        corpus.path("invoices/Invoice_cgst_sgst_012.pdf").read_bytes())
    corpus.add("junk/08-edge/duplicate_of_invoice.pdf",
               Entry(path="junk/08-edge/duplicate_of_invoice.pdf", family="junk", kind="invoice",
                     rows=1, line_items=None, totals={}, notes="duplicate bytes of an invoice"))
    corpus.path("junk/08-edge/zip_with_bank_pdf.zip").write_bytes(
        _zip_bytes({"statement.pdf": corpus.path("invoices/Invoice_cgst_sgst_013.pdf").read_bytes()}))
    corpus.add("junk/08-edge/zip_with_bank_pdf.zip",
               Entry(path="junk/08-edge/zip_with_bank_pdf.zip", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zip holding a PDF"))


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Mixed client-month folders
# ---------------------------------------------------------------------------


def build_mixed(corpus: Corpus, folders: int = 20, per_folder: int = 10) -> None:
    rng = corpus.rng
    # Draw only from small, fast files: the mixed folders exist to exercise the
    # cross-family pipeline, not to re-run the 5,000-row monsters 20 times.
    candidates = [
        entry for entry in corpus.entries
        if entry.family in {"banks", "invoices", "gst", "books"}
        and entry.outcome == "processed"
        and (entry.rows or 0) <= 60
        and not entry.requires
    ]
    if not candidates:
        return
    scenario_entries: list[tuple[dict, list[Entry]]] = []
    for folder_index in range(1, folders + 1):
        month = 1 + (folder_index % 12)
        folder = f"mixed/client-{folder_index:02d}-2026-{month:02d}"
        picks = rng.sample(candidates, min(per_folder, len(candidates)))
        used_names: set[str] = set()
        for pick in picks:
            name = Path(pick.path).name
            if name in used_names:
                stem, suffix = Path(name).stem, Path(name).suffix
                name = f"{stem}_{folder_index}{suffix}"
            used_names.add(name)
            target = f"{folder}/{name}"
            corpus.copy(pick.path, target)
            copied = Entry(
                path=target,
                family="mixed",
                kind=pick.kind,
                outcome=pick.outcome,
                rows=pick.rows,
                line_items=pick.line_items,
                totals=dict(pick.totals),
                balance_status=pick.balance_status,
                flags=list(pick.flags),
                notes=f"copy of {pick.path}",
                requires=list(pick.requires),
                advisory=pick.advisory,
            )
            corpus.add(target, copied)


# ---------------------------------------------------------------------------
# Profiles and entry point
# ---------------------------------------------------------------------------


def build_smoke(corpus: Corpus) -> None:
    corpus.rng = random.Random(corpus.seed)
    build_banks(corpus, plan=[("clean_text", 1), ("multipage", 1), ("broken_closing", 1)], extras=False)
    build_invoices(corpus, plan=[("cgst_sgst", 1), ("igst", 1)], extras=False)
    build_gst(corpus, plan=[("2b_valid", 1), ("3b_valid", 1)], large=False)
    build_books(corpus, plan=[("tally_xml", 1), ("zoho_csv", 1)], large=False)
    # A tiny, hand-picked junk slice: the smoke run must stay in seconds.
    corpus.path("junk/01-binary/empty.pdf").write_bytes(b"")
    corpus.add("junk/01-binary/empty.pdf",
               Entry(path="junk/01-binary/empty.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="zero bytes"))
    corpus.path("junk/02-text/plain_text.pdf").write_text(
        "This is plain text with a .pdf name.\n", encoding="utf-8")
    corpus.add("junk/02-text/plain_text.pdf",
               Entry(path="junk/02-text/plain_text.pdf", family="junk", kind="unknown",
                     outcome="unclassified", rows=None, notes="text content named .pdf"))
    build_mixed(corpus, folders=1, per_folder=1)


def build_standard(corpus: Corpus, scale: int = 1) -> None:
    build_banks(corpus, scale=scale)
    build_invoices(corpus, scale=scale)
    build_gst(corpus, scale=scale)
    build_books(corpus, scale=scale)
    build_junk(corpus)
    build_mixed(corpus, folders=20 * scale, per_folder=10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--profile", choices=("smoke", "standard", "brutal"), default="standard")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    out = args.out if args.out.is_absolute() else (ROOT / args.out)
    out = out.resolve()
    if out.parent == out or out == ROOT or out == ROOT.parent:
        print(f"Refusing to wipe {out}: choose a dedicated corpus folder.")
        return 2
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    started = time.perf_counter()
    corpus = Corpus(out, args.seed, args.profile)
    if args.profile == "smoke":
        build_smoke(corpus)
    elif args.profile == "brutal":
        build_standard(corpus, scale=2)
    else:
        build_standard(corpus)
    corpus.write_manifest()
    elapsed = time.perf_counter() - started

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    print(
        f"Wrote {manifest['file_count']} files, "
        f"{manifest['total_bytes'] / (1024 * 1024):.1f} MB in {elapsed:.1f}s -> {out}"
    )
    for family, count in sorted(manifest["families"].items()):
        print(f"  {family:<9} {count:>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
