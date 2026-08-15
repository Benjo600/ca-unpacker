from __future__ import annotations

import os
import shutil
from pathlib import Path


def main() -> int:
    dest = Path("dist/CAUnpacker/tesseract")
    srcs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "CAUnpacker" / "tesseract",
        Path.home() / "AppData" / "Local" / "CAUnpacker" / "tesseract",
        Path(r"C:\Program Files\Tesseract-OCR"),
    ]
    src = next((path for path in srcs if (path / "tesseract.exe").is_file()), None)
    if src is None:
        print("No Tesseract to bundle; scans will need a local install.")
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "tesseract.exe", dest / "tesseract.exe")
    tessdata = src / "tessdata"
    if tessdata.is_dir():
        shutil.copytree(tessdata, dest / "tessdata", dirs_exist_ok=True)
    print(f"Bundled Tesseract from {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
