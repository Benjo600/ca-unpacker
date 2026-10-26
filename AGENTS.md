# AGENTS.md

CA Unpacker: a **Windows-only, offline-first** desktop app that turns a CA client's document dump into GST-ready Excel packs. Client files never leave the PC; only license/auth may use the internet.

## Layout

- `apps/engine/` — all parsing, validation, Excel writing, SQLite/SQLAlchemy, reconciliation. Pure Python, importable without the UI.
  - `parsers/` — `bank/` (profiles, tables, OCR), `invoice.py`, `gstr.py`, `tally.py`, `zoho.py`
  - `pack/` — xlsx writers; `validators/` — GSTIN/HSN/balance checks
- `apps/desktop/` — pywebview shell. `app.py` exposes the JS bridge (`DesktopApi`); `protocol.py` = `caunpacker://`; `frozen_entry.py` = PyInstaller entry.
- `apps/ui/` — the *desktop* UI (vanilla HTML/CSS/JS). Loaded via `apps/ui/index.html` (`shell.html`, `auth.html`, `redesign.html` are separate surfaces).
- `apps/web/` — separate React 19 + Vite SPA (signup/login/admin), deployed to Netlify. Not bundled in the app.
- `supabase/` — Deno Edge Functions + SQL migrations. `designs/ca-unpacker-landing/` — static landing page (Netlify root site).
- `test-dump/` — **gitignored, generated fixtures** (see `build_test_dump.py`); `dump_paths.py` auto-builds it on import.

## Commands

Run Python from the repo root (tests add it to `sys.path` and import root-level modules like `make_test_dump`).

```powershell
start.bat                                             # create .venv, install requirements.txt, run the app
.venv\Scripts\python.exe -m apps.desktop              # run app directly
.venv\Scripts\python.exe -m pytest apps -q            # full Python suite (~266 tests: engine + desktop)
.venv\Scripts\python.exe -m pytest apps/engine/tests/test_stage3_bank.py -q   # one file
.venv\Scripts\python.exe -m pytest apps/desktop/tests/test_app_import.py -q   # bridge contract tests
node apps/ui/tests/status-summary.test.js             # UI JS tests (plain node scripts, not jest)
cd apps/web; npm install; npm run build               # web SPA (tsc -b && vite build)
build_installer.bat                                   # PyInstaller + Inno Setup 6 -> dist\CAUnpacker-Setup.exe
```

## Gotchas

- **Never freeze `apps/desktop/__main__.py`.** PyInstaller entry is `apps/desktop/frozen_entry.py`; freezing `__main__` drops `apps.desktop.app` and the app boots with "No module named 'apps.desktop.app'".
- Runtime data lives in `%LOCALAPPDATA%\CAUnpacker\` (`app.db`, `files\`, `packs\`), not the repo. A `library.lock` enforces one writer; `settings.py` warns on OneDrive/Desktop library paths.
- `apps/config.json` holds the **tracked** production Supabase URL/anon key used by the shipped build; `.env` (gitignored) only overrides `SUPABASE_URL`/`SUPABASE_ANON_KEY` for `start.bat`.
- `pyrightconfig.json` covers `apps/` and `scratch/` only; pyright is not in `.venv` by default.
- Add a new bank format by editing `apps/engine/parsers/bank/profiles.py` — see `docs/ADDING-A-BANK.md`.

## Project contracts

- `STAGES.md` is the build-order gate list. Do not start Stage N+1 until Stage N's gate is checked and recorded in its gate log.
- `DESIGN.md` is the canonical design system for the `apps/ui` shell ("Practice Desk"). UI edits trigger the impeccable design hook (`.claude/settings.local.json`, `.codex/hooks.json`).
- `BUILD-PLAN.md` is the whole-product spec; `docs/superpowers/plans/` and `specs/` hold per-task plans.
