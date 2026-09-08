from __future__ import annotations

from pathlib import Path

from apps.engine.parsers.bank.profiles import BankProfile
from apps.engine.parsers.bank.tables import rows_from_cell_tables, rows_from_markdown

_converter = None


def rows_from_docling(path: Path, profile: BankProfile, filename: str) -> list[dict]:
    """Layout + table-structure parser (IBM Docling). Local only; used for image PDFs."""
    converter = _docling_converter()
    if converter is None:
        return []
    try:
        result = converter.convert(str(path))
        document = result.document
    except Exception:
        return []

    rows: list[dict] = []
    tables = getattr(document, "tables", None) or []
    for index, table in enumerate(tables, start=1):
        grid = _table_grid(table)
        if grid:
            rows.extend(rows_from_cell_tables([grid], profile, filename, index))
    if rows:
        return rows
    try:
        markdown = document.export_to_markdown() or ""
    except Exception:
        markdown = ""
    return rows_from_markdown(markdown, profile, filename)


def _docling_converter():
    global _converter
    if _converter is False:
        return None
    if _converter is not None:
        return _converter
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            RapidOcrOptions,
            TableFormerMode,
            TableStructureOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except Exception:
        _converter = False
        return None

    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = True
    options.table_structure_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode.ACCURATE,
    )
    try:
        options.ocr_options = RapidOcrOptions(force_full_page_ocr=True, lang=["english", "en"])
    except TypeError:
        options.ocr_options = RapidOcrOptions(force_full_page_ocr=True)
    try:
        _converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            }
        )
    except Exception:
        _converter = False
        return None
    return _converter


def _table_grid(table) -> list[list[str | None]]:
    try:
        frame = table.export_to_dataframe()
        header = [str(col) if col is not None else None for col in frame.columns.tolist()]
        body = [
            [None if cell is None else str(cell) for cell in row]
            for row in frame.astype(object).where(frame.notna(), None).values.tolist()
        ]
        grid = [header] + body if header else body
        return [row for row in grid if any(cell for cell in row)]
    except Exception:
        return []
