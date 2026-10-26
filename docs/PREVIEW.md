# In-app file preview

The preview pane shows the **source document** in the window, so a CA can read a
bill or a portal JSON without leaving the app. It never shows the extracted rows
and it never writes to the library copy.

Open it by clicking a file name in the period's file list. The crop preview also
has **Open full page**, which opens the same pane at the page the crop came from.

## What each file type shows

| File | Pane shows |
| --- | --- |
| PDF | One rendered page at a time, page counter, Previous/Next, fit width or actual size. `←`/`→` also page. |
| JPG / PNG / WEBP / TIFF / BMP | The image, scaled to fit. |
| JSON | The file text, indented for reading. **Show raw file** returns the exact bytes from disk. Invalid JSON is labelled invalid, never repaired. |
| CSV | A table of the first rows, delimiter sniffed (`,` `;` tab `|`). |
| XLSX | A table per sheet, with sheet tabs. |
| TXT / XML | Plain text, wrap on or off. |
| ZIP | Entry names and sizes. Nothing is extracted. |
| Anything else (e.g. DOCX) | "No preview for this file type" plus **Open in app**. |

"Open in app" hands the file to the program Windows associates with it. It is
the escape hatch, not the normal path.

## Password PDFs

The pane asks for the password and passes it to the render **for that preview
only**. It is held in the window's memory so paging keeps working, and it is not
stored with the file. The existing unlock flow (which saves the password for
parsing) is unchanged; when a password is already known, previewing uses it.

## Limits

One 50 MB portal export must not freeze the window, so:

- Text and JSON are capped at 4 MB read / 200,000 characters shown.
- CSV and XLSX show 200 rows and 30 columns.
- A ZIP lists 200 entries.
- Images are scaled to 2,200 px on the long edge.
- PDF pages render at 2× and keep PNG under 900 KB, otherwise JPEG (quality 88).
- Rendered pages are cached under `%LOCALAPPDATA%\CAUnpacker\cache\previews\` and
  the oldest files are pruned past 400 entries.

Every capped view says so in the footer. The full file is still on disk.

## Code

| Piece | File |
| --- | --- |
| Payload builder | `apps/engine/preview.py` (`preview_file`, `source_file_path`) |
| Page count / render | `apps/engine/pdf_render.py` (`page_count`, `render_page_png`) |
| Desktop bridge | `apps/desktop/app.py` (`get_file_preview`, `open_source_file`) |
| Pane markup and styles | `apps/ui/index.html`, `apps/ui/styles.css` |
| Pane behaviour | `apps/ui/app.js` (`openFilePreview`, `loadFilePreview`, `renderPreview*`) |

## Tests

- `apps/engine/tests/test_preview.py` — PDF page + count, out-of-range page,
  password prompt without storing the password, image, JSON (valid, invalid,
  raw), CSV delimiter, XLSX sheets, ZIP entries, unsupported type, missing file,
  text truncation, cache reuse and pruning.
- `apps/desktop/tests/test_preview_api_contract.py` — the bridge shape the UI
  depends on.

## Adding a type

Add a branch to `preview_file` and a `preview_type` the UI knows how to render
(`image`, `text`, `table`, `archive`, `unsupported`). Keep the payload free of
filesystem paths: the pane only needs the name, kind, size and view content.
