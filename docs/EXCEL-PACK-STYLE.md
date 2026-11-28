# Excel pack house style

Every workbook the app writes follows this page. The code that enforces it is
`apps/engine/pack/style.py`; writers call it and never define their own colour,
font or border. `apps/engine/tests/test_pack_style.py` holds the contract.

Written 28 Nov 2026, after the restyle of the nine pack writers.

## The idea

A pack should read like one document written by one firm: ink on paper, one
clay accent, no colour blocks, no zebra banding. A CA should be able to print
any sheet in black and white and still tell at a glance which cell needs them.

## Palette

| Token | Value | Used for |
| --- | --- | --- |
| `INK` | `1F1F1D` | All body and heading text, the rule under a table header |
| `SECONDARY` | `6B6B66` | Facts under a masthead, muted notes, footer |
| `HAIRLINE` | `D8D5CC` | The thin rule between table rows, sign-off boxes |
| `WARM_PAPER` | `FAF9F5` | Reserved for cover paper; not painted (a full tint prints grey) |
| `ACCENT` | `C15F3C` | One clay rule under a cover masthead, the left edge of an exception cell |
| `EXCEPTION_TINT` | `FBF1EC` | The single status cell of a row that needs a look |
| `WHITE` | `FFFFFF` | Header background (i.e. no fill) |

No navy, no blue banding, no green "good" rows. A matched row is simply not
marked.

## Type

| Where | Font | Size | Weight |
| --- | --- | --- | --- |
| Firm name on a cover | Georgia | 18 | bold, uppercase |
| Pack title (no firm known) | Georgia | 18 | bold |
| Pack title under a firm name | Georgia | 12 | bold |
| Section headings ("Contents", "Money at stake") | Georgia | 12 | bold |
| Table headers | Segoe UI | 9 | bold |
| Body, labels, links | Segoe UI | 9 | regular (labels bold) |
| Facts under a masthead | Segoe UI | 10 | regular, secondary ink |

Georgia and Segoe UI ship with Windows; nothing is installed with the app.

## Cover (sheet 1 of every workbook)

A cover is not decoration: it tells the CA whose pack this is, what is inside,
and who signed it off. In order, top to bottom:

1. **Masthead** — the firm name (uppercase, 18pt), the pack title, then one
   line of facts: client · period · row or file counts · generated date/time.
   Firm, client and period come from the pipeline (`pack_cover_identity`);
   anything unknown is left out, never guessed.
2. **One thin clay rule** closing the masthead. No colour blocks.
3. **Contents** — a linked index of every sheet: name as an internal hyperlink,
   then "`N rows` · what the sheet holds".
4. **The pack's own block** — bank result table, GSTR counts, reconciliation
   counts and money, file-review fields, treatment notes.
5. **Notes** in plain words (tolerance used, what a decision does, and so on).
6. **Legend** — the mark itself (tinted cell with clay left edge) and what it
   means, in one sentence.
7. **Sign-off** — Prepared by / Reviewed by / Date, each with an empty ruled
   box. The pack is paper until someone signs it.

Covers never merge cells. They print A4 portrait, fitted to one page wide,
gridlines off.

A cover is always sheet 1, and only a cover may carry one of these names:
`Contents`, `Cover`, `Balance Check`. The in-app preview and any other reader
therefore picks the sheet to show by name (`style.data_sheet_name`), never by
position — the data sheet is the first sheet that is not a cover.

Two covers keep a pinned layout instead of the order above:

- **Bank** (`Balance Check`): readers find the summary table header on row 4
  and the first file on row 5, so the masthead is fixed to the three rows above
  it and the legend, contents and sign-off sit below the table.
- **Reconciliation summary** and **Exceptions only** exports keep their
  single-sheet shape (the masthead and the table share one sheet); the block
  order is unchanged. They still carry the firm, client and period.

## Tables

- Header row is row 1 of its own sheet, in ink on white, bold Segoe UI 9, one
  heavy INK rule underneath. No vertical borders anywhere.
- Body rows: hairline bottom rule only, white background, no banding. Row
  height auto-fits whenever a long-text column wraps, otherwise ~16.
- Money right-aligned, dates centred, text left. Numeric columns share one font
  so digits line up in a printout. (Excel has no per-cell OpenType switch for
  tabular figures; the single body font is the closest control we have.)
- Freeze `A2`, autofilter over the table, no merged cells.
- Wide sheets print A4 landscape, fit to one page wide, header row repeated,
  footer "client · period · sheet · Page X of Y", margins 0.4–0.5".

## Numbers, dates, plurals

- Money keeps the pack's own format: Indian lakh/crore with `₹` for INR
  (`formatting.money_format`), the currency module's per-currency format for
  bank statements (it carries the "(inferred)" suffix and red negatives).
- Dates are real date values with `DD-MM-YYYY`. A register column is treated as
  a date by its key (`formatting.DATE_KEYS`), and only unambiguous text is
  converted: ISO, `DD/MM/YYYY` (Indian day-first), `12-Jul-2026`, or
  `DD-MM-YYYY` where the numbers force one reading. `05-07-2026` with dashes
  stays text — a wrong month on a GST invoice is worse than a string that still
  reads correctly. Bank statements use the same rule.
- Counts use `formatting.plural`: "1 row", "7 rows", "1 day apart". Never
  "row(s)" or "day(s)". The tests scan every generated cell for "(s)".

## Print setup

| Sheet | Paper | Orientation | Fitted | Header row repeated | Footer |
| --- | --- | --- | --- | --- | --- |
| Data sheet | A4 | landscape | 1 page wide, as many pages tall | yes (its header row) | client · period · sheet · Page X of Y |
| Cover | A4 | portrait | 1 page wide | no | client · period · pack title · Page X of Y |

Gridlines are off everywhere, content is centred horizontally, margins are
0.4–0.5", and no sheet carries a print area wider than its own columns
(`style.print_setup`, `style.cover_print_setup`).

## Exceptions

One status cell per exception: `EXCEPTION_TINT` fill plus a clay left border.
Never the whole row — a painted row is unreadable in black and white and hides
the plain-language Status/Why text that explains the problem.

## Text safety

Every string value goes through `style.append_row` / `style.put`:

- control characters that would corrupt the `.xlsx` XML are removed;
- length is capped at Excel's 32,767-character limit;
- a value starting with `=` is stored as text (`data_type = "s"`), so a client
  description can never become a live formula.

## How to add a new writer

1. Put the palette, fonts, borders and cover helpers to work — import from
   `apps.engine.pack.style`. Do not define a colour, font or `PatternFill` in a
   writer; `test_pack_style.PaletteTests` fails if the old tokens come back.
2. Build rows with `style.append_row` and headers with `style.put` +
   `style_header`, then `style_body(..., money_cols=..., date_cols=...)`.
3. Mark exceptions with `style.mark_exception(sheet, row, status_col)` **after**
   `style_body`, so the border survives.
4. Add `print_setup(sheet, ncols, header_row=1, footer_parts=[client, period, title])`.
5. Write the cover with `cover_sheet(...)` (masthead, linked index, blocks,
   notes, legend, sign-off) and name it `Contents` or `Cover` — those names, and
   `Balance Check`, are reserved by `style.COVER_SHEET_TITLES`. A new cover name
   must be added there, or readers will open the cover instead of the data. The
   data sheet stays sheet 2 and keeps its header on row 1.
6. Read the firm, client and period from the `identity` mapping the pipeline
   passes (`pipeline.pack_cover_identity`). A writer never opens the database.
7. Cover the look in `test_pack_style.py`: header row 1, hairline body, freeze
   and filter, print setup, cover contents links, real dates, plurals, and the
   formula-injection case.
8. Regenerate one sample pack from `test-dump/07-mixed-client-month` and open
   two or three workbooks before merging.
