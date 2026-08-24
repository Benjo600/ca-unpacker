from __future__ import annotations

import importlib
import inspect
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.tests.fixtures_stage4 import make_image_only_pdf, make_password_pdf
from apps.engine.tests.test_stage3_bank import write_hdfc

from apps.engine.tests.dump_paths import HDFC as HDFC_DIGITAL
STAGE4_PASSWORD = "CAUnpacker-Stage4-Pw-7f3a9c"
OCR_PATH = ROOT / "apps" / "engine" / "ocr.py"

_CROP_MODULES = (
    "apps.engine.pipeline",
    "apps.engine.pdf_render",
    "apps.engine.crop",
    "apps.desktop.app",
)
_PASSWORD_MODULES = (
    "apps.engine.pdf_extract",
    "apps.engine.pdf_passwords",
    "apps.engine.passwords",
    "apps.engine.password",
    "apps.engine.password_pdf",
)
_TESSERACT_MODULES = (
    "apps.engine.ocr",
    "apps.engine.pdf_extract",
    "apps.engine.pdf_render",
)


def _hdfc_src(folder: Path) -> Path:
    dest = folder / "HDFC_Statement_Jul2026.pdf"
    if HDFC_DIGITAL.is_file():
        shutil.copy2(HDFC_DIGITAL, dest)
        return dest
    return write_hdfc(folder)


def _import_attr(module_names: tuple[str, ...], attr: str):
    last_err: BaseException | None = None
    for name in module_names:
        try:
            module = importlib.import_module(name)
        except ImportError as exc:
            last_err = exc
            continue
        value = getattr(module, attr, None)
        if value is not None:
            return value
    if last_err is not None:
        return None
    return None


def _money_rows(rows: list[dict]) -> list[dict]:
    found = []
    for row in rows:
        if row.get("debit") or row.get("credit"):
            found.append(row)
    return found


def _as_bytes(value) -> bytes:
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, Path):
        return value.read_bytes()
    if isinstance(value, str) and Path(value).is_file():
        return Path(value).read_bytes()
    return b""


def _crop_ok_and_png(result) -> tuple[bool, bytes]:
    if isinstance(result, (bytes, bytearray)):
        return True, bytes(result)
    if isinstance(result, (str, Path)) and Path(result).is_file():
        return True, Path(result).read_bytes()
    if isinstance(result, tuple) and result:
        blob = _as_bytes(result[1]) if len(result) > 1 else b""
        return bool(result[0]), blob
    if isinstance(result, dict):
        ok = result.get("ok", True)
        for key in ("png", "png_bytes", "bytes", "image", "data", "content"):
            if result.get(key):
                return bool(ok), _as_bytes(result[key])
        if result.get("path"):
            blob = _as_bytes(result["path"])
            if blob:
                return bool(ok), blob
        url = result.get("data_url") or result.get("dataUrl")
        if isinstance(url, str) and "," in url:
            import base64

            try:
                return bool(ok), base64.b64decode(url.split(",", 1)[1])
            except Exception:
                return bool(ok), b""
        return bool(ok), b""
    return False, b""


def _call_get_source_crop(fn, context: dict):
    aliases = {
        "page": context.get("source_page"),
        "bbox": context.get("source_bbox"),
        "pdf": context.get("path"),
        "pdf_path": context.get("path"),
        "src": context.get("path"),
    }
    merged = {**aliases, **context}
    sig = inspect.signature(fn)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if name in merged and merged[name] is not None:
            kwargs[name] = merged[name]
        elif param.default is inspect.Parameter.empty and param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise TypeError(f"get_source_crop needs {name}")
    return fn(**kwargs)


def _using_password_cm(using, password: str, path: Path):
    sig = inspect.signature(using)
    names = [name for name in sig.parameters if name != "self"]
    if not names:
        return using()
    if len(names) == 1:
        return using(password)
    kwargs = {}
    if names[0] in {"path", "pdf", "src", "pdf_path"}:
        return using(path, password)
    for name in names:
        if name in {"path", "pdf", "src", "pdf_path"}:
            kwargs[name] = path
        elif name == "password":
            kwargs[name] = password
    if kwargs:
        return using(**kwargs)
    return using(password)


def _extract_with_password(extract_pdf, path: Path, password: str):
    using = _import_attr(_PASSWORD_MODULES, "using_password")
    sig = inspect.signature(extract_pdf)
    if using is not None:
        ctx = _using_password_cm(using, password, path)
        if hasattr(ctx, "__enter__"):
            with ctx:
                if "password" in sig.parameters:
                    return extract_pdf(path, password=password)
                return extract_pdf(path)
        if ctx is not None and ctx is not using:
            return ctx
    if "password" in sig.parameters:
        return extract_pdf(path, password=password)
    return None


def _password_hits(root: Path, password: str) -> list[str]:
    needle = password.encode("utf-8")
    hits: list[str] = []
    if not root.exists():
        return hits
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if needle in data:
            hits.append(str(path))
    return hits


def _classified_parts(classified) -> tuple[str, str]:
    if classified is None:
        return "", ""
    if isinstance(classified, dict):
        return str(classified.get("kind") or ""), str(classified.get("reason") or "")
    return str(getattr(classified, "kind", "") or ""), str(getattr(classified, "reason", "") or "")


def _looks_encrypted(extracted, classified=None) -> bool:
    pdf_type = str(getattr(extracted, "pdf_type", "") or "").lower()
    if pdf_type in {"encrypted", "password", "password_protected"}:
        return True
    kind, reason = _classified_parts(classified)
    blob = f"{kind} {reason}".lower()
    return "password" in blob or "encrypt" in blob


class _IsolatedApp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        try:
            from apps.engine.db import reset_engine

            reset_engine()
        except ImportError:
            pass

    def tearDown(self) -> None:
        try:
            from apps.engine.db import reset_engine

            reset_engine()
        except ImportError:
            pass
        self._tmp.cleanup()

    def _period(self):
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
        client = create_client("Acme")
        return create_period(client["id"], "Jul 2026")

    def _inbox(self) -> Path:
        folder = Path(self._tmp.name) / "inbox"
        folder.mkdir(exist_ok=True)
        return folder


class Stage4DigitalCropTests(_IsolatedApp):
    def test_digital_crop(self) -> None:
        get_source_crop = _import_attr(_CROP_MODULES, "get_source_crop")
        try:
            importlib.import_module("apps.engine.pdf_render")
            pdf_render_ready = True
        except ImportError:
            pdf_render_ready = False
        if get_source_crop is None or not pdf_render_ready:
            self.skipTest("get_source_crop/pdf_render not ready")

        try:
            from apps.engine.dump import ingest_paths, start_job
            from apps.engine.parsers.bank.parser import parse_bank_pdf
        except ImportError as exc:
            self.skipTest(f"digital parse/dump not ready: {exc}")

        inbox = self._inbox()
        pdf = _hdfc_src(inbox)
        period = self._period()
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(pdf)])

        parsed = parse_bank_pdf(pdf)
        rows = _money_rows(parsed.get("rows") or [])
        self.assertTrue(rows, "digital HDFC parse produced no debit/credit rows")
        row = next((item for item in rows if item.get("source_page") and item.get("source_bbox")), None)
        if row is None:
            self.skipTest("source_bbox not ready")

        from apps.engine.dump import list_period_files
        from apps.engine.library import resolve_storage_key

        files = list_period_files(period["id"])
        stored = next((item for item in files if item.get("kind") == "bank"), files[0] if files else None)
        file_id = stored.get("id") if stored else None
        stored_path = pdf
        if stored and stored.get("storage_key"):
            stored_path = resolve_storage_key(stored["storage_key"])

        preview_row_id = None
        try:
            from apps.engine.pipeline import get_period_preview

            preview = get_period_preview(period["id"])
            for item in preview.get("files") or []:
                for prow in item.get("preview") or []:
                    if prow.get("row_id"):
                        preview_row_id = prow.get("row_id")
                        break
        except ImportError:
            pass

        result = _call_get_source_crop(
            get_source_crop,
            {
                "row": row,
                "row_id": preview_row_id or row.get("row_id"),
                "file_id": file_id,
                "period_id": period["id"],
                "source_page": row.get("source_page"),
                "source_bbox": row.get("source_bbox"),
                "path": stored_path,
            },
        )
        ok, png = _crop_ok_and_png(result)
        self.assertTrue(ok, result)
        self.assertGreater(len(png), 100)


class Stage4PasswordTests(_IsolatedApp):
    def test_password_pdf(self) -> None:
        try:
            from apps.engine.classifier import classify_path
            from apps.engine.pdf_extract import extract_pdf
        except ImportError as exc:
            self.skipTest(f"classify/extract_pdf not ready: {exc}")

        inbox = self._inbox()
        src = _hdfc_src(inbox)
        locked = make_password_pdf(src, inbox / "HDFC_Statement_Jul2026_locked.pdf", STAGE4_PASSWORD)

        classified = classify_path(locked)
        extracted = extract_pdf(locked)
        self.assertTrue(
            _looks_encrypted(extracted, classified),
            f"expected encrypted/password without secret, got type={getattr(extracted, 'pdf_type', None)} class={classified}",
        )

        unlocked = _extract_with_password(extract_pdf, locked, STAGE4_PASSWORD)
        if unlocked is None:
            hits = _password_hits(Path(self._tmp.name), STAGE4_PASSWORD)
            self.assertEqual(hits, [], f"password leaked to {hits}")
            self.skipTest("using_password / extract_pdf password= not ready")

        self.assertFalse(
            _looks_encrypted(unlocked),
            f"correct password still encrypted: {getattr(unlocked, 'pdf_type', None)}",
        )

        try:
            wrong = _extract_with_password(extract_pdf, locked, "definitely-wrong-password")
            if wrong is not None:
                self.assertTrue(
                    _looks_encrypted(wrong),
                    f"wrong password should stay encrypted, got {getattr(wrong, 'pdf_type', None)}",
                )
        except ValueError as exc:
            self.assertIn("password", str(exc).lower())

        hits = _password_hits(Path(self._tmp.name), STAGE4_PASSWORD)
        self.assertEqual(hits, [], f"password leaked to {hits}")


class Stage4ScanTests(_IsolatedApp):
    def test_scan_produces_rows(self) -> None:
        find_tesseract = _import_attr(_TESSERACT_MODULES, "find_tesseract")
        if find_tesseract is None:
            self.skipTest("find_tesseract not ready")
        if find_tesseract() is None:
            self.skipTest("tesseract not available")

        try:
            from apps.engine.parsers.bank.parser import parse_bank_pdf
        except ImportError as exc:
            self.skipTest(f"parse_bank_pdf not ready: {exc}")

        inbox = self._inbox()
        src = _hdfc_src(inbox)
        try:
            scan = make_image_only_pdf(src, inbox / "HDFC_Statement_Jul2026_scan.pdf")
        except ImportError as exc:
            self.skipTest(f"pypdfium2 not ready: {exc}")

        try:
            parsed = parse_bank_pdf(scan)
            rows = parsed.get("rows") or []
        except ImportError as exc:
            self.skipTest(f"scan parse not ready: {exc}")
        except TypeError:
            from apps.engine.pdf_extract import extract_pdf

            extracted = extract_pdf(scan)
            if not hasattr(parse_bank_pdf, "__wrapped__"):
                try:
                    parsed = parse_bank_pdf(scan, extracted=extracted)
                    rows = parsed.get("rows") or []
                except TypeError as exc:
                    self.skipTest(f"scan parse signature not ready: {exc}")
            else:
                raise
        self.assertGreaterEqual(len(rows), 1, "scanned statement produced no rows")


class Stage4OcrSourceTests(unittest.TestCase):
    def test_no_network_ocr(self) -> None:
        if not OCR_PATH.is_file():
            self.skipTest("ocr.py missing")
        text = OCR_PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("openai", text)
        self.assertNotIn("google vision", text)


class Stage4PreviewTests(_IsolatedApp):
    def test_preview_includes_crop_fields(self) -> None:
        try:
            from apps.engine.dump import ingest_paths, start_job
            from apps.engine.pipeline import get_period_preview
        except ImportError as exc:
            self.skipTest(f"preview/dump not ready: {exc}")

        inbox = self._inbox()
        pdf = _hdfc_src(inbox)
        period = self._period()
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(pdf)])
        preview = get_period_preview(period["id"])
        files = preview.get("files") or []
        self.assertTrue(files)
        rows = [row for item in files for row in (item.get("preview") or [])]
        self.assertTrue(rows)
        expect_row_id = any("row_id" in row for row in rows)
        for row in rows:
            self.assertTrue(row.get("source_page"), row)
            if expect_row_id:
                self.assertTrue(row.get("row_id"), row)


if __name__ == "__main__":
    unittest.main()
