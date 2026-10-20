from __future__ import annotations

from pathlib import Path

from apps.engine.parsers.bank.profiles import BankProfile
from apps.engine.parsers.bank.tables import _map_header, rows_from_cell_tables

_TABLE_SETTINGS = (
    {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 4,
        "join_tolerance": 4,
        "text_x_tolerance": 3,
        "text_y_tolerance": 3,
    },
    {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
    },
)


def rows_from_pdfplumber(path: Path, profile: BankProfile, filename: str) -> list[dict]:
    try:
        import pdfplumber
    except ImportError:
        return []
    from apps.engine.pdf_extract import current_pdf_password

    password = current_pdf_password()
    kwargs = {}
    if password:
        kwargs["password"] = password
    try:
        with pdfplumber.open(str(path), **kwargs) as pdf:
            rows: list[dict] = []
            for index, page in enumerate(pdf.pages, start=1):
                bbox = _page_bbox(page)
                for table in _page_tables(page):
                    rows.extend(rows_from_cell_tables([table], profile, filename, index, bbox))
            return rows
    except Exception:
        return []


def _page_tables(page) -> list[list[list[str | None]]]:
    best: list[list[list[str | None]]] = []
    best_score = (0, 0)
    for settings in _TABLE_SETTINGS:
        try:
            tables = page.extract_tables(table_settings=settings) or []
        except Exception:
            tables = []
        usable = [table for table in tables if table and len(table) >= 2]
        if not usable:
            continue
        score = _header_score(usable)
        if not best or score > best_score:
            best_score = score
            best = usable
        if score[1] == 2 and score[0] >= 3:
            # Both amount columns are mapped; no need to try a fallback.
            break
    return best


def _header_score(tables: list[list[list[str | None]]]) -> tuple[int, int]:
    """Prefer the table whose header maps the most amount columns.

    pdfplumber's text strategy can split a wide statement into a malformed
    table whose header merges the narration and debit columns.  The lines
    strategy usually finds the real header; score both instead of accepting
    whichever strategy returned first.
    """
    best = (0, 0)
    for table in tables:
        for raw in table[:8]:
            mapping = _map_header(raw)
            if mapping:
                keys = set(mapping.values())
                score = (len(keys), int("debit" in keys) + int("credit" in keys))
                best = max(best, score)
                break
    return best


def _page_bbox(page) -> str | None:
    try:
        width = float(page.width or 0)
        height = float(page.height or 0)
    except Exception:
        return None
    if not width or not height:
        return None
    return f"0.0,0.0,{width:.1f},{height:.1f}"
