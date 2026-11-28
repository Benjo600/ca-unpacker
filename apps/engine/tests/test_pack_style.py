"""Presentation contract for every generated pack.

These tests pin the calm editorial look that all the writers share: the ink
palette, Georgia headings, a single clay accent, hairline table rules, a cover
that lists its own sheets, and a sanitiser that stops a client document from
smuggling a live formula or an illegal character into a workbook.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.pack import style
from apps.engine.pack.style import (
    ACCENT,
    DATE_FORMAT,
    EXCEPTION_TINT,
    HAIRLINE,
    INK,
    MAX_CELL_CHARS,
    SECONDARY,
    WARM_PAPER,
    WHITE,
)

ROWS = [
    {
        "date": "2026-07-01",
        "description": "Opening balance",
        "cheque_ref": "",
        "debit": None,
        "credit": None,
        "balance": 1500.0,
        "source": "HDFC.pdf#p1",
        "flags": [],
        "currency_code": "INR",
    },
    {
        "date": "2026-07-02",
        "description": "Payment to Mehta Printers",
        "cheque_ref": "112233",
        "debit": 250.5,
        "credit": None,
        "balance": 1249.5,
        "source": "HDFC.pdf#p1",
        "flags": ["duplicate_source_row"],
        "currency_code": "INR",
    },
]
CHECK = {
    "status": "match",
    "row_count": 2,
    "opening_balance": 1500.0,
    "stated_closing": 1249.5,
    "computed_closing": 1249.5,
    "broken_at_row": None,
    "flags": [],
}
META = {
    "filename": "HDFC_Statement_Jul2026.pdf",
    "profile_label": "HDFC Bank",
    "account_number": "50100123456789",
    "ifsc": "HDFC0001234",
    "firm": "Ben & Co",
    "client": "Acme Traders",
    "period": "Jul 2026",
}


def _bank_workbook(folder: Path, meta: dict | None = None, rows: list[dict] | None = None):
    from apps.engine.pack.bank_xlsx import write_bank_workbook

    path = folder / "Bank_Statement_Cleaned.xlsx"
    write_bank_workbook(
        path,
        [
            {
                "rows": rows if rows is not None else ROWS,
                "check": CHECK,
                "meta": meta if meta is not None else META,
            }
        ],
    )
    return load_workbook(path)


def _rgb(cell) -> str:
    if cell.fill is None or cell.fill.patternType is None:
        return ""
    colour = getattr(cell.fill, "fgColor", None)
    return str(getattr(colour, "rgb", "") or "")[-6:]


def _texts(sheet) -> list[str]:
    return [
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    ]


class PaletteTests(unittest.TestCase):
    def test_palette_is_the_documented_one_and_nothing_else(self) -> None:
        self.assertEqual(INK, "1F1F1D")
        self.assertEqual(SECONDARY, "6B6B66")
        self.assertEqual(HAIRLINE, "D8D5CC")
        self.assertEqual(WARM_PAPER, "FAF9F5")
        self.assertEqual(ACCENT, "C15F3C")
        self.assertEqual(EXCEPTION_TINT, "FBF1EC")
        self.assertEqual(WHITE, "FFFFFF")
        # The old navy band palette is gone: no writer may resurrect it.
        for name in ("HEADER_BG", "BAND_BG", "LABEL_BG", "RED_BG", "GREEN_BG", "AMBER_BG"):
            self.assertFalse(hasattr(style, name), name)


class DataSheetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.book = _bank_workbook(self.folder)
        self.sheet = self.book["Transactions"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_header_stays_on_row_one_with_ink_rule_and_no_fill(self) -> None:
        header = [cell.value for cell in self.sheet[1]]
        self.assertEqual(header[0], "Date")
        first = self.sheet.cell(1, 1)
        self.assertEqual(first.font.name, "Segoe UI")
        self.assertEqual(first.font.sz, 9)
        self.assertTrue(first.font.bold)
        self.assertEqual(str(first.font.color.rgb)[-6:], INK)
        self.assertEqual(first.border.bottom.style, "thick")
        self.assertEqual(str(first.border.bottom.color.rgb)[-6:], INK)
        self.assertIsNone(first.border.left)
        self.assertIsNone(first.border.right)
        self.assertIsNone(first.fill.patternType)

    def test_body_is_hairline_only_with_no_banding(self) -> None:
        for row in range(2, self.sheet.max_row + 1):
            cell = self.sheet.cell(row, 1)
            self.assertEqual(cell.border.bottom.style, "thin", row)
            self.assertEqual(str(cell.border.bottom.color.rgb)[-6:], HAIRLINE, row)
            self.assertIsNone(cell.border.left, row)
            self.assertIsNone(cell.border.right, row)
            self.assertIsNone(cell.fill.patternType, row)
            self.assertEqual(cell.font.name, "Segoe UI", row)
        # Alternating rows must not be painted.
        self.assertEqual(_rgb(self.sheet.cell(2, 2)), "")
        self.assertEqual(_rgb(self.sheet.cell(3, 2)), "")

    def test_money_right_dates_centred_and_text_left(self) -> None:
        self.assertEqual(self.sheet.cell(2, 1).number_format, DATE_FORMAT)
        self.assertEqual(self.sheet.cell(2, 1).alignment.horizontal, "center")
        self.assertEqual(self.sheet.cell(2, 4).alignment.horizontal, "right")
        self.assertEqual(self.sheet.cell(2, 2).alignment.horizontal, "left")
        self.assertIn("₹", self.sheet.cell(2, 4).number_format)

    def test_exception_marks_one_cell_only(self) -> None:
        flags_col = [cell.value for cell in self.sheet[1]].index("Flags") + 1
        flag_cell = self.sheet.cell(3, flags_col)
        self.assertEqual(_rgb(flag_cell), EXCEPTION_TINT)
        self.assertEqual(flag_cell.border.left.style, "medium")
        self.assertEqual(str(flag_cell.border.left.color.rgb)[-6:], ACCENT)
        self.assertEqual(_rgb(self.sheet.cell(3, 1)), "")
        self.assertEqual(_rgb(self.sheet.cell(2, flags_col)), "")

    def test_freeze_filter_and_no_merged_cells(self) -> None:
        self.assertEqual(self.sheet.freeze_panes, "A2")
        self.assertEqual(self.sheet.auto_filter.ref, f"A1:I{self.sheet.max_row}")
        self.assertEqual(len(self.sheet.merged_cells.ranges), 0)

    def test_print_setup_is_a4_fitted_with_page_footer(self) -> None:
        self.assertEqual(int(self.sheet.page_setup.paperSize), 9)
        self.assertEqual(self.sheet.page_setup.orientation, "landscape")
        self.assertEqual(self.sheet.page_setup.fitToWidth, 1)
        self.assertFalse(self.sheet.print_options.gridLines)
        self.assertEqual(self.sheet.print_title_rows, "$1:$1")
        footer = self.sheet.oddFooter.center.text
        self.assertIn("Acme Traders", footer)
        self.assertIn("Jul 2026", footer)
        self.assertIn("&P", footer)
        self.assertIn("&N", footer)
        self.assertGreaterEqual(self.sheet.page_margins.left, 0.4)
        self.assertLessEqual(self.sheet.page_margins.left, 0.5)


class CoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.book = _bank_workbook(self.folder)
        self.cover = self.book["Balance Check"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_masthead_names_the_firm_pack_client_and_period(self) -> None:
        self.assertEqual(self.cover["A1"].value, "BEN & CO")
        self.assertEqual(self.cover["A1"].font.name, "Georgia")
        self.assertEqual(self.cover["A1"].font.sz, 18)
        self.assertTrue(self.cover["A1"].font.bold)
        texts = _texts(self.cover)
        self.assertIn("Bank statement pack", texts)
        facts = " ".join(texts)
        self.assertIn("Acme Traders", facts)
        self.assertIn("Jul 2026", facts)
        self.assertIn("generated", facts)

    def test_cover_rule_is_clay_and_never_a_colour_block(self) -> None:
        ruled = [
            (row, self.cover.cell(row, 1))
            for row in range(1, 6)
            if self.cover.cell(row, 1).border.bottom.style == "thin"
            and str(self.cover.cell(row, 1).border.bottom.color.rgb)[-6:] == ACCENT
        ]
        self.assertTrue(ruled, "cover should carry one thin clay rule")
        for row, cell in ruled:
            self.assertIsNone(cell.fill.patternType, row)

    def test_index_links_every_sheet_with_a_description(self) -> None:
        links: dict[str, str] = {}
        for row in range(1, self.cover.max_row + 1):
            cell = self.cover.cell(row, 1)
            if cell.hyperlink is not None:
                links[str(cell.value)] = cell.hyperlink.location
        self.assertIn("Transactions", links)
        self.assertEqual(links["Transactions"], "'Transactions'!A1")
        index_texts = " ".join(_texts(self.cover))
        self.assertIn("row", index_texts)
        self.assertNotIn("(s)", index_texts)
        self.assertIn("Contents", index_texts)

    def test_legend_and_sign_off_are_present_in_plain_words(self) -> None:
        texts = _texts(self.cover)
        self.assertIn("How to read this sheet", texts)
        for label in ("Prepared by", "Reviewed by", "Date"):
            self.assertIn(label, texts)
        sign_row = next(
            row for row in range(1, self.cover.max_row + 1)
            if self.cover.cell(row, 1).value == "Prepared by"
        )
        box = self.cover.cell(sign_row, 2)
        self.assertEqual(box.border.bottom.style, "thin")
        self.assertIsNone(box.value)

    def test_cover_never_merges_cells(self) -> None:
        self.assertEqual(len(self.cover.merged_cells.ranges), 0)

    def test_cover_prints_to_a4_without_gridlines(self) -> None:
        self.assertEqual(int(self.cover.page_setup.paperSize), 9)
        # Thirteen summary columns: landscape, fitted to one page wide.
        self.assertEqual(self.cover.page_setup.orientation, "landscape")
        self.assertEqual(self.cover.page_setup.fitToWidth, 1)
        self.assertFalse(self.cover.print_options.gridLines)


class CoverIndexCountsEverySheetTests(unittest.TestCase):
    def test_two_statements_produce_two_index_entries(self) -> None:
        from apps.engine.pack.bank_xlsx import write_bank_workbook

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "two.xlsx"
            item = lambda name: {  # noqa: E731 - readability over style here
                "rows": ROWS,
                "check": CHECK,
                "meta": dict(META, filename=name),
            }
            write_bank_workbook(path, [item("HDFC_Jul.pdf"), item("ICICI_Jul.pdf")])
            cover = load_workbook(path)["Balance Check"]
            links = [
                cover.cell(row, 1).value
                for row in range(1, cover.max_row + 1)
                if cover.cell(row, 1).hyperlink is not None
            ]
            self.assertEqual(len(links), 2, links)
            self.assertIn("HDFC_Jul", " ".join(links))
            self.assertIn("ICICI_Jul", " ".join(links))


class OtherWriterHeaderTests(unittest.TestCase):
    def test_gstr_and_plain_registers_keep_their_header_on_row_one(self) -> None:
        from apps.engine.pack.gstr_xlsx import write_gstr_2b
        from apps.engine.pack.preflight_xlsx import write_preflight_report
        from apps.engine.pack.table_xlsx import write_table
        from apps.engine.preflight import PreflightReport

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            gstr = folder / "GSTR_2B_Formatted.xlsx"
            write_gstr_2b(
                gstr,
                [
                    {
                        "gstin": "27AAPFU0939F1ZV",
                        "trade_name": "Acme Traders",
                        "invoice_number": "INV-1",
                        "invoice_date": "12-07-2026",
                        "invoice_value": 118.0,
                        "taxable": 100.0,
                        "flags": [],
                        "source": "GSTR-2B_July.json",
                    }
                ],
                {"gstin": "27AAPFU0939F1ZV", "period": "Jul 2026"},
            )
            book = load_workbook(gstr)
            self.assertEqual(book["Cover"].cell(1, 1).font.name, "Georgia")
            self.assertEqual(book["Cover"].page_setup.orientation, "portrait")
            self.assertEqual(book["B2B"].cell(1, 1).value, "GSTIN")
            self.assertEqual(book["B2B"].freeze_panes, "A2")
            self.assertEqual(book["B2B"].print_title_rows, "$1:$1")
            self.assertIn("Page &P of &N", book["B2B"].oddFooter.center.text or "")
            self.assertEqual(len(book["Cover"].merged_cells.ranges), 0)

            register = folder / "Books.xlsx"
            write_table(
                register,
                "Books",
                [{"party": "Mehta", "amount": 10.0, "flags": []}],
                [("Party", "party"), ("Amount", "amount"), ("Flags", "flags")],
            )
            sheet = load_workbook(register)["Books"]
            self.assertEqual(sheet.cell(1, 1).value, "Party")
            self.assertEqual(sheet.freeze_panes, "A2")
            self.assertFalse(sheet.print_options.gridLines)

            preflight = folder / "Preflight_Report.xlsx"
            write_preflight_report(preflight, PreflightReport())
            pf = load_workbook(preflight)["Preflight"]
            self.assertEqual(pf.cell(1, 1).value, "Level")
            self.assertIn("Page &P of &N", pf.oddFooter.center.text or "")


IDENTITY = {
    "firm": "Ben & Co, Chartered Accountants",
    "client": "Acme Traders",
    "period": "Jul 2026",
}


class RegisterCoverTests(unittest.TestCase):
    """Every workbook opens on a cover; the data sheet keeps its own contract."""

    def test_plain_register_opens_on_a_cover_and_keeps_its_data_sheet(self) -> None:
        from apps.engine.pack.table_xlsx import write_table

        rows = [
            {
                "party": "Mehta Printers",
                "amount": 1180.0,
                "date": "2026-07-12",
                "flags": [],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Books.xlsx"
            write_table(
                path,
                "Books",
                rows,
                [
                    ("Party", "party"),
                    ("Date", "date"),
                    ("Amount", "amount"),
                    ("Flags", "flags"),
                ],
                identity=IDENTITY,
            )
            book = load_workbook(path)
            self.assertEqual(book.sheetnames, ["Contents", "Books"])
            cover_text = " ".join(
                str(c.value) for row in book["Contents"].iter_rows() for c in row if c.value
            )
            self.assertIn("BEN & CO, CHARTERED ACCOUNTANTS", cover_text)
            self.assertIn("Acme Traders", cover_text)
            self.assertIn("Jul 2026", cover_text)
            self.assertIn("Contents", cover_text)
            links = [
                book["Contents"].cell(r, 1).hyperlink.location
                for r in range(1, book["Contents"].max_row + 1)
                if book["Contents"].cell(r, 1).hyperlink is not None
            ]
            self.assertEqual(links, ["'Books'!A1"])

            sheet = book["Books"]
            self.assertEqual([c.value for c in sheet[1]][:2], ["Party", "Date"])
            self.assertEqual(sheet.freeze_panes, "A2")
            self.assertEqual(sheet.auto_filter.ref, f"A1:D{sheet.max_row}")

    def test_register_dates_are_real_dates_in_dd_mm_yyyy(self) -> None:
        from openpyxl.utils.datetime import to_excel
        from apps.engine.pack.table_xlsx import write_table

        rows = [
            {"party": "Iso", "date": "2026-07-12", "amount": 1.0, "flags": []},
            {"party": "Slash", "date": "05/07/2026", "amount": 2.0, "flags": []},
            {"party": "Swapped", "date": "07-13-2026", "amount": 3.0, "flags": []},
            {"party": "Word", "date": "14-Jul-2026", "amount": 4.0, "flags": []},
            {"party": "Junk", "date": "sometime in July", "amount": 5.0, "flags": []},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Books.xlsx"
            write_table(
                path,
                "Books",
                rows,
                [("Party", "party"), ("Date", "date"), ("Amount", "amount"), ("Flags", "flags")],
            )
            sheet = load_workbook(path)["Books"]
            seen = [sheet.cell(row, 2).value for row in range(2, sheet.max_row + 1)]
            self.assertEqual(seen[0].strftime("%d-%m-%Y"), "12-07-2026")
            self.assertEqual(seen[1].strftime("%d-%m-%Y"), "05-07-2026")
            self.assertEqual(seen[2].strftime("%d-%m-%Y"), "13-07-2026")
            self.assertEqual(seen[3].strftime("%d-%m-%Y"), "14-07-2026")
            # A value that cannot be read is kept exactly as it arrived.
            self.assertEqual(seen[4], "sometime in July")
            for row in range(2, 6):
                self.assertEqual(sheet.cell(row, 2).number_format, DATE_FORMAT)
            self.assertIsNone(to_excel(seen[4]) if not isinstance(seen[4], str) else None)

    def test_purchase_workbook_cover_lists_both_sheets(self) -> None:
        from apps.engine.pack.table_xlsx import write_purchase_workbook

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Purchase_Register_Extracted.xlsx"
            write_purchase_workbook(
                path,
                [{"supplier_name": "Acme", "invoice_number": "A-1", "invoice_date": "2026-07-12"}],
                [{"invoice_number": "A-1", "description": "Fees", "amount": 100.0}],
                [("Supplier", "supplier_name"), ("Invoice no", "invoice_number"), ("Date", "invoice_date")],
                [("Invoice no", "invoice_number"), ("Description", "description"), ("Amount", "amount")],
                identity=IDENTITY,
            )
            book = load_workbook(path)
            self.assertEqual(book.sheetnames, ["Contents", "Invoices", "Line items"])
            cover = book["Contents"]
            links = [
                cover.cell(r, 1).value
                for r in range(1, cover.max_row + 1)
                if cover.cell(r, 1).hyperlink is not None
            ]
            self.assertEqual(links, ["Invoices", "Line items"])
            self.assertEqual(book["Invoices"].cell(1, 1).value, "Supplier")
            self.assertEqual(book["Line items"].cell(1, 1).value, "Invoice no")
            self.assertEqual(book["Invoices"]["C2"].number_format, DATE_FORMAT)

    def test_preflight_report_opens_on_a_cover(self) -> None:
        from apps.engine.pack.preflight_xlsx import write_preflight_report
        from apps.engine.preflight import PreflightReport

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Preflight_Report.xlsx"
            write_preflight_report(path, PreflightReport(), identity=IDENTITY)
            book = load_workbook(path)
            self.assertEqual(book.sheetnames, ["Contents", "Preflight"])
            cover_text = " ".join(
                str(c.value) for row in book["Contents"].iter_rows() for c in row if c.value
            )
            self.assertIn("BEN & CO, CHARTERED ACCOUNTANTS", cover_text)
            self.assertIn("Contents", cover_text)
            self.assertEqual(book["Preflight"].cell(1, 1).value, "Level")

    def test_preview_opens_the_data_sheet_not_the_cover(self) -> None:
        from apps.engine.pack.table_xlsx import write_table
        from apps.engine.preview import _xlsx_preview

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Books.xlsx"
            write_table(
                path,
                "Books",
                [{"party": "Mehta", "amount": 10.0, "flags": []}],
                [("Party", "party"), ("Amount", "amount"), ("Flags", "flags")],
            )
            payload = _xlsx_preview({}, path, "")
            self.assertEqual(payload["table"]["sheet"], "Books")
            self.assertEqual(payload["table"]["rows"][0][0], "Party")


class PluralTests(unittest.TestCase):
    def test_plural_never_writes_brackets(self) -> None:
        from apps.engine.pack.formatting import plural

        self.assertEqual(plural(0, "row"), "0 rows")
        self.assertEqual(plural(1, "row"), "1 row")
        self.assertEqual(plural(2, "row"), "2 rows")
        self.assertEqual(plural(1200, "file"), "1,200 files")
        self.assertEqual(plural(1, "entry", "entries"), "1 entry")
        self.assertEqual(plural(3, "entry", "entries"), "3 entries")

    def test_reconciliation_prose_never_writes_brackets(self) -> None:
        """The grid's Why column and the tolerance notes are pack text too."""
        from apps.engine import recon_engine

        source = Path(recon_engine.__file__).read_text(encoding="utf-8")
        self.assertNotIn("(s)", source)
        self.assertIn("plural(", source)

    def test_no_pack_text_says_row_s_or_file_s(self) -> None:
        from apps.engine.pack.table_xlsx import write_table

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Books.xlsx"
            write_table(
                path,
                "Books",
                [{"party": "Mehta", "amount": 10.0, "flags": []}],
                [("Party", "party"), ("Amount", "amount"), ("Flags", "flags")],
            )
            book = load_workbook(path)
            for sheet in book.worksheets:
                for row in sheet.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str):
                            self.assertNotIn("(s)", cell.value, f"{sheet.title}!{cell.coordinate}")


class EveryWorkbookOpensOnACoverTests(unittest.TestCase):
    """Goal: no pack opens straight onto a table any more."""

    def _cover_text(self, book) -> str:
        first = book.worksheets[0]
        return " ".join(
            str(cell.value) for row in first.iter_rows() for cell in row if cell.value
        )

    def test_treatment_workbook_opens_on_a_cover(self) -> None:
        from apps.engine.pack.treatment_xlsx import write_treatment_workbook

        treatment = {
            "flags": [],
            "expense_heads": [],
            "profile": {},
            "as_of": "",
            "disclaimer": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Treatment_Review.xlsx"
            write_treatment_workbook(path, treatment, identity=IDENTITY)
            book = load_workbook(path)
            self.assertEqual(book.sheetnames[0], "Cover")
            self.assertIn("BEN & CO, CHARTERED ACCOUNTANTS", self._cover_text(book))
            self.assertEqual(book["Treatment notes"].cell(1, 1).value, "Severity")

    def test_reconciliation_workbook_opens_on_a_cover(self) -> None:
        from apps.engine.pack.recon_xlsx import write_master_grid

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Master_Reconciliation_Grid.xlsx"
            write_master_grid(path, {"rows": [], "counts": {}, "totals": {}}, identity=IDENTITY)
            book = load_workbook(path)
            self.assertEqual(book.sheetnames[0], "Cover")
            self.assertIn("BEN & CO, CHARTERED ACCOUNTANTS", self._cover_text(book))
            self.assertEqual(book["Grid"].cell(1, 1).value, "Status")

    def test_file_review_workbook_opens_on_a_cover(self) -> None:
        from apps.engine.pack.file_review_xlsx import write_file_review_workbook

        review = {"checklist": [], "checks": [], "counts": {}, "profile": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "File_Review.xlsx"
            write_file_review_workbook(path, review, identity=IDENTITY)
            book = load_workbook(path)
            self.assertEqual(book.sheetnames[0], "Contents")
            self.assertIn("BEN & CO, CHARTERED ACCOUNTANTS", self._cover_text(book))
            self.assertEqual(book["Checklist"].cell(1, 1).value, "Grade")

    def test_cannot_include_workbook_opens_on_a_cover(self) -> None:
        from apps.engine.pack.gstr_xlsx import write_cannot_include

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GSTR_Upload_Cannot_Include.xlsx"
            write_cannot_include(
                path,
                [{"reason": "tax rate missing", "invoice_number": "SAL-1", "date": "2026-07-12"}],
                identity=IDENTITY,
            )
            book = load_workbook(path)
            self.assertEqual(book.sheetnames[0], "Contents")
            self.assertIn("BEN & CO, CHARTERED ACCOUNTANTS", self._cover_text(book))
            self.assertEqual(book["Cannot include"].cell(1, 1).value, "Reason")


class CoverSheetNameTests(unittest.TestCase):
    def test_only_reserved_names_may_be_covers(self) -> None:
        from apps.engine.pack.style import COVER_SHEET_TITLES, data_sheet_name, is_cover_sheet

        self.assertEqual(COVER_SHEET_TITLES, ("Contents", "Cover", "Balance Check"))
        self.assertTrue(is_cover_sheet("contents"))
        self.assertTrue(is_cover_sheet(" Balance Check "))
        self.assertFalse(is_cover_sheet("B2B"))
        # A summary sheet that holds data is not a cover.
        self.assertEqual(data_sheet_name(["Cover", "Summary"]), "Summary")
        self.assertEqual(data_sheet_name(["Balance Check", "Transactions"]), "Transactions")
        self.assertEqual(data_sheet_name(["Contents", "Books"], "Books"), "Books")
        # A single-sheet export keeps working.
        self.assertEqual(data_sheet_name(["Summary"]), "Summary")
        self.assertEqual(data_sheet_name([]), "")


class PreviewFindsTheDataSheetTests(unittest.TestCase):
    def test_gstr_preview_opens_the_b2b_sheet(self) -> None:
        from apps.engine.pack.gstr_xlsx import write_gstr_2b
        from apps.engine.preview import _xlsx_preview

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GSTR_2B_Formatted.xlsx"
            write_gstr_2b(path, [{"gstin": "27AAPFU0939F1ZV", "invoice_number": "INV-1"}], {})
            payload = _xlsx_preview({}, path, "")
            self.assertEqual(payload["table"]["sheet"], "B2B")

    def test_treatment_preview_opens_the_notes_sheet(self) -> None:
        from apps.engine.pack.treatment_xlsx import write_treatment_workbook
        from apps.engine.preview import _xlsx_preview

        treatment = {"flags": [], "expense_heads": [], "profile": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Treatment_Review.xlsx"
            write_treatment_workbook(path, treatment, identity=IDENTITY)
            payload = _xlsx_preview({}, path, "")
            self.assertEqual(payload["table"]["sheet"], "Treatment notes")

    def test_bank_preview_ignores_the_balance_check_cover(self) -> None:
        from apps.engine.preview import _xlsx_preview

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _bank_workbook(folder)
            payload = _xlsx_preview({}, folder / "Bank_Statement_Cleaned.xlsx", "")
            self.assertEqual(payload["table"]["sheet"], "Transactions")


class FirmOnEveryCoverTests(unittest.TestCase):
    def test_exception_and_summary_exports_name_the_firm(self) -> None:
        from apps.engine.recon_exports import write_audit_summary, write_exceptions_workbook

        recon = {
            "rows": [
                {
                    "status": "books_only",
                    "party": "Mehta Printers",
                    "date_2b": "2026-07-12",
                    "date_books": "05-07-2026",
                    "amount_books": 1180.0,
                }
            ],
            "counts": {},
            "totals": {},
            "decisions": {},
            "tolerances": {"days": 7, "amount": 1.0},
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            exceptions = folder / "Exceptions_Only.xlsx"
            write_exceptions_workbook(
                exceptions,
                client_name="Acme Traders",
                period_label="Jul 2026",
                recon=recon,
                firm="Ben & Co",
            )
            sheet = load_workbook(exceptions)["Exceptions"]
            texts = " ".join(_texts(sheet))
            self.assertIn("BEN & CO", texts)
            self.assertEqual(sheet["A1"].font.name, "Georgia")

            summary = folder / "Reconciliation_Summary.xlsx"
            write_audit_summary(
                summary,
                client_name="Acme Traders",
                period_label="Jul 2026",
                recon=recon,
                firm="Ben & Co",
            )
            texts = " ".join(_texts(load_workbook(summary)["Summary"]))
            self.assertIn("BEN & CO", texts)


class RegisterDateKeyTests(unittest.TestCase):
    def test_sap_style_date_keys_become_real_dates(self) -> None:
        from apps.engine.pack.table_xlsx import write_table

        rows = [
            {
                "posting_date": "2026-07-12",
                "baseline_date": "12/07/2026",
                "clearing_date": "05-07-2026",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SAP.xlsx"
            write_table(
                path,
                "SAP reports",
                rows,
                [
                    ("Posting date", "posting_date"),
                    ("Baseline date", "baseline_date"),
                    ("Clearing date", "clearing_date"),
                ],
            )
            sheet = load_workbook(path)["SAP reports"]
            self.assertEqual(sheet.cell(2, 1).value.strftime("%d-%m-%Y"), "12-07-2026")
            self.assertEqual(sheet.cell(2, 2).value.strftime("%d-%m-%Y"), "12-07-2026")
            # Dashes leave the day and month ambiguous, so the text is kept.
            self.assertEqual(sheet.cell(2, 3).value, "05-07-2026")
            self.assertEqual(sheet.cell(2, 3).data_type, "s")
            for col in (1, 2, 3):
                self.assertEqual(sheet.cell(2, col).number_format, DATE_FORMAT)


class SanitiseTests(unittest.TestCase):
    def test_sanitize_text_strips_control_characters_and_caps_length(self) -> None:
        from apps.engine.pack.style import sanitize_text

        self.assertEqual(sanitize_text("Invoice\x00 42\x07"), "Invoice 42")
        self.assertEqual(sanitize_text("line one\nline two"), "line one\nline two")
        long_text = "x" * (MAX_CELL_CHARS + 50)
        self.assertEqual(len(sanitize_text(long_text)), MAX_CELL_CHARS)

    def test_leading_equals_is_stored_as_text_not_a_formula(self) -> None:
        from apps.engine.pack.bank_xlsx import write_bank_workbook

        rows = [
            {
                "date": "2026-07-01",
                "description": '=HYPERLINK("http://example.com","click")',
                "cheque_ref": "=1+1",
                "debit": None,
                "credit": None,
                "balance": 10.0,
                "source": "HDFC.pdf#p1",
                "flags": [],
                "currency_code": "INR",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inject.xlsx"
            write_bank_workbook(
                path,
                [{"rows": rows, "check": CHECK, "meta": META}],
            )
            sheet = load_workbook(path)["Transactions"]
            for col in (2, 3):
                cell = sheet.cell(2, col)
                self.assertEqual(cell.data_type, "s", col)
                self.assertTrue(str(cell.value).startswith("="), col)

    def test_control_characters_never_reach_a_written_cell(self) -> None:
        from apps.engine.pack.table_xlsx import write_table

        rows = [{"party": "Mehta\x00 Printers\x1f", "amount": 5.0, "flags": []}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.xlsx"
            write_table(
                path,
                "Books",
                rows,
                [("Party", "party"), ("Amount", "amount"), ("Flags", "flags")],
            )
            sheet = load_workbook(path)["Books"]
            self.assertEqual(sheet.cell(2, 1).value, "Mehta Printers")

    def test_injection_through_a_flag_text_stays_text(self) -> None:
        from apps.engine.pack.table_xlsx import write_table

        rows = [{"party": "Safe Co", "amount": 5.0, "flags": ["=cmd|calc"]}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.xlsx"
            write_table(
                path,
                "Books",
                rows,
                [("Party", "party"), ("Amount", "amount"), ("Flags", "flags")],
            )
            sheet = load_workbook(path)["Books"]
            self.assertEqual(sheet.cell(2, 3).value, "=cmd|calc")
            self.assertEqual(sheet.cell(2, 3).data_type, "s")


if __name__ == "__main__":
    unittest.main()
