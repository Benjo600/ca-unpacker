# CA Unpacker

Windows desktop app. A CA dumps a client’s month of files and gets GST-ready Excel packs on this PC. Nothing is uploaded.

## Install (for a CA)

1. Open the landing page and click **Download for Windows**, or take **CAUnpacker-Setup.exe** from the GitHub Release (not the green “Code” source zip).
2. Double-click that one file. No unzip, no Python, no Docker.
3. Open **CA Unpacker** from the Start menu or the desktop shortcut.

Landing page (open in a browser): `designs/ca-unpacker-landing/index.html`.

Files stay under `%LOCALAPPDATA%\CAUnpacker\`. Cleaned Excels go in the folder you pick on first launch.

## Run from source (developers)

```bat
start.bat
```

That creates `.venv`, installs `requirements.txt`, and opens the window.

Build the installer:

```bat
build_installer.bat
```

Needs [Inno Setup 6](https://jrsoftware.org/isinfo.php). Output: `dist\CAUnpacker-Windows.zip`.

## Status

Stages 1–7 of `STAGES.md` are done on fixtures (shell, dump, bank pack, crops/OCR, invoices, GSTR JSON, Tally/Zoho). Stage 8 is the master reconciliation grid.
