# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)

datas = [(str(ROOT / "apps" / "ui"), "ui")]
binaries = []
hiddenimports = [
    "apps.desktop",
    "apps.engine",
    "pdf_inspector",
    "webview",
    "clr_loader",
    "pythonnet",
    "openpyxl",
    "pypdf",
    "sqlalchemy",
]

for package in ("pdf_inspector", "webview", "openpyxl", "pypdf"):
    collected = collect_all(package)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

a = Analysis(
    [str(ROOT / "apps" / "desktop" / "__main__.py")],
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CAUnpacker",
)
