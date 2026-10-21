from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sap"


def fixture(name: str) -> Path:
    return FIXTURE_DIR / name


def write_xlsx(path: Path, sheets: dict[str, list[list]]) -> Path:
    """Write synthetic rows into an XLSX workbook for parser tests."""
    from openpyxl import Workbook

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    default = book.active
    for index, (title, rows) in enumerate(sheets.items()):
        sheet = default if index == 0 else book.create_sheet()
        sheet.title = title
        for row in rows:
            sheet.append(row)
    book.save(path)
    return path


def write_positioned_pdf(
    path: Path,
    *,
    title: str,
    columns: list[tuple[float, str]],
    rows: list[list[str]],
) -> Path:
    """Write a synthetic PDF whose columns sit at fixed x coordinates.

    The parser needs word coordinates to separate adjacent Debit and Credit
    columns, so the test fixture places every header and value explicitly
    instead of relying on proportional text spacing.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    y = 790.0
    lines.append(_pdf_text(40.0, y, title))
    y -= 30.0
    for x, text in columns:
        lines.append(_pdf_text(x, y, text))
    y -= 20.0
    for row in rows:
        for (x, _header), value in zip(columns, row):
            if value:
                lines.append(_pdf_text(x, y, value))
        y -= 18.0
    content = "BT /F1 10 Tf\n" + "\n".join(lines) + "\nET"
    path.write_bytes(_pdf_bytes(content))
    return path


def write_text_pdf(path: Path, lines: list[str]) -> Path:
    """Write a synthetic PDF with one text line per row."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ["BT /F1 10 Tf 40 790 Td 14 TL"]
    for index, line in enumerate(lines):
        safe = _escape(line)
        if index == 0:
            body.append(f"({safe}) Tj T*")
        else:
            body.append(f"({safe}) '")
    body.append("ET")
    path.write_bytes(_pdf_bytes("\n".join(body)))
    return path


def _pdf_text(x: float, y: float, text: str) -> str:
    return f"1 0 0 1 {x} {y} Tm ({_escape(text)}) Tj"


def _escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_bytes(content: str) -> bytes:
    stream = content.encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        (
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
            b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        ),
        f"4 0 obj<</Length {len(stream)}>>stream\n".encode("ascii")
        + stream
        + b"endstream\nendobj\n",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]
    body = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(body))
        body += obj
    xref_pos = len(body)
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n"
    trailer = (
        f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    )
    return body + xref.encode("ascii") + trailer.encode("ascii")
