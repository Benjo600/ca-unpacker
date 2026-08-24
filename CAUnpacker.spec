# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)

datas = [(str(ROOT / "apps" / "ui"), "ui")]
binaries = []
hiddenimports = [
    "apps",
    "apps.desktop",
    "apps.desktop.app",
    "apps.engine",
    "apps.engine.ocr",
    "apps.engine.pdf_extract",
    "apps.engine.pdf_passwords",
    "apps.engine.pdf_render",
    "apps.engine.pipeline",
    "apps.engine.dump",
    "apps.engine.classifier",
    "apps.engine.pack.bank_xlsx",
    "apps.engine.pack.gstr_xlsx",
    "apps.engine.pack.table_xlsx",
    "apps.engine.parsers.bank.parser",
    "apps.engine.parsers.gstr",
    "apps.engine.parsers.invoice",
    "apps.engine.parsers.tally",
    "apps.engine.parsers.zoho",
    "pdf_inspector",
    "webview",
    "clr_loader",
    "pythonnet",
    "openpyxl",
    "pypdf",
    "pypdfium2",
    "pytesseract",
    "PIL",
    "sqlalchemy",
]

hiddenimports += collect_submodules(
    "apps",
    filter=lambda name: "tests" not in name.split("."),
)

for package in (
    "pdf_inspector",
    "webview",
    "openpyxl",
    "pypdf",
    "pypdfium2",
    "pytesseract",
    "PIL",
    "sqlalchemy",
):
    try:
        collected = collect_all(package)
    except Exception:
        continue
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

a = Analysis(
    [str(ROOT / "apps" / "desktop" / "frozen_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

collected_modules = {entry[0] for entry in a.pure}
required_modules = (
    "apps.desktop.app",
    "apps.engine.pipeline",
    "apps.engine.dump",
)
missing = [name for name in required_modules if name not in collected_modules]
if missing:
    raise SystemExit("PyInstaller did not collect required modules: " + ", ".join(missing))
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CAUnpacker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "apps" / "ui" / "app-icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CAUnpacker",
)
