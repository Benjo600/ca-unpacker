# -*- mode: python ; coding: utf-8 -*-
"""One-file build of the external update helper (CAUnpackerUpdater.exe).

The desktop app copies this exe into the version-specific update folder before
launching it, so the installed copy is never locked while the app is replaced.
"""

from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "apps" / "desktop" / "updater_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["apps", "apps.desktop", "apps.desktop.updater"],
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
    a.binaries,
    a.datas,
    [],
    name="CAUnpackerUpdater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
