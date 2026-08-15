# Local Tesseract (no cloud OCR)

CA Unpacker OCRs scanned bank PDFs on this PC only. Page images are never uploaded.

`find_tesseract()` uses the first existing `tesseract.exe` in this order:

1. Environment variable `CAUNPACKER_TESSERACT` (file, or a folder that contains `tesseract.exe`)
2. `%LOCALAPPDATA%\CAUnpacker\tesseract\tesseract.exe` (and the same path under the user profile if tests override LOCALAPPDATA)
3. `<repo>\third_party\tesseract\tesseract.exe` (installer bundle; not committed)
4. `C:\Program Files\Tesseract-OCR\tesseract.exe`
5. `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`
6. `tesseract` on `PATH` (`shutil.which`)

If none of those exist, extract still runs. Scans come back with `engine="none"` and no lines. Nothing is downloaded.
