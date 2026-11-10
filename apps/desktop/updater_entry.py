"""Entry point for the standalone CAUnpackerUpdater.exe build."""

from __future__ import annotations

from apps.desktop.updater import main

if __name__ == "__main__":
    raise SystemExit(main())
