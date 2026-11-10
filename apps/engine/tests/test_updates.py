from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import httpx

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INSTALLER_URL = (
    "https://github.com/benny-n/ca-unpacker/releases/download/v0.11.0/"
    "CAUnpacker-Setup-0.11.0.exe"
)
CHECKSUM = "a" * 64


def _release(**overrides):
    data = {
        "version": "0.11.0",
        "title": "CA Unpacker 0.11.0",
        "release_notes": "Faster imports and a quieter updater.",
        "installer_url": INSTALLER_URL,
        "installer_sha256": CHECKSUM,
        "installer_size": 4096,
        "mandatory": False,
        "published_at": "2026-09-11T10:00:00Z",
    }
    data.update(overrides)
    return data


def _payload(**overrides):
    return {"update_available": True, "release": _release(**overrides)}


class _TempLocalAppData(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = mock.patch.dict(os.environ, {"LOCALAPPDATA": self._tmp.name})
        env.start()
        self.addCleanup(env.stop)
        from apps.engine import updates

        self.updates = updates

    def patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_version(self, version: str) -> None:
        self.patch(self.updates, "APP_VERSION", version)

    def fake_release_call(self, payload=None, error=None):
        calls: list[tuple[str, dict]] = []

        def fake(name, body):
            calls.append((name, body))
            if error is not None:
                raise error
            return payload

        self.patch(self.updates, "_latest_release_call", fake)
        return calls

    def seed_cache(self, release: dict | None, *, age_hours: float = 0.0) -> dict:
        checked = (datetime.now() - timedelta(hours=age_hours)).isoformat(
            timespec="seconds"
        )
        return self.updates.save_update_cache(
            {
                "checked_at": checked,
                "current_version": self.updates.APP_VERSION,
                "manifest": release,
            }
        )


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST", "https://example.supabase.co/functions/v1/latest-release"
    )
    return httpx.HTTPStatusError(
        "boom", request=request, response=httpx.Response(status, request=request)
    )


class CallAuthenticatedFunctionTests(_TempLocalAppData):
    def auth(self):
        return self.updates.auth

    def test_requires_a_session(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.auth().call_authenticated_function("latest-release", {})
        self.assertIn("Sign in to check for updates.", str(caught.exception))

    def test_refreshes_once_then_retries(self) -> None:
        auth = self.auth()
        session = {"access_token": "old", "refresh_token": "r", "email": "a@b.c"}
        refreshed = {"access_token": "new", "refresh_token": "r2", "email": "a@b.c"}
        self.patch(auth, "get_session", lambda: session)
        self.patch(auth, "refresh_session", lambda: refreshed)
        seen: list[str] = []

        def fake_call(name, body, sess):
            seen.append(sess["access_token"])
            if len(seen) == 1:
                raise _status_error(401)
            return {"ok": True}

        self.patch(auth, "_call_function", fake_call)

        result = auth.call_authenticated_function(
            "latest-release", {"current_version": "0.10.0"}
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(seen, ["old", "new"])

    def test_failed_refresh_asks_the_user_to_sign_in_again(self) -> None:
        auth = self.auth()
        self.patch(
            auth,
            "get_session",
            lambda: {"access_token": "old", "refresh_token": "r", "email": ""},
        )
        self.patch(auth, "refresh_session", lambda: None)

        def always_401(name, body, sess):
            raise _status_error(401)

        self.patch(auth, "_call_function", always_401)

        with self.assertRaises(ValueError) as caught:
            auth.call_authenticated_function("latest-release", {})
        self.assertIn("Sign in again to check for updates.", str(caught.exception))

    def test_second_401_asks_the_user_to_sign_in_again(self) -> None:
        auth = self.auth()
        self.patch(
            auth,
            "get_session",
            lambda: {"access_token": "old", "refresh_token": "r", "email": ""},
        )
        self.patch(
            auth,
            "refresh_session",
            lambda: {"access_token": "new", "refresh_token": "r2", "email": ""},
        )

        def always_401(name, body, sess):
            raise _status_error(401)

        self.patch(auth, "_call_function", always_401)

        with self.assertRaises(ValueError) as caught:
            auth.call_authenticated_function("latest-release", {})
        self.assertIn("Sign in again to check for updates.", str(caught.exception))

    def test_non_auth_http_error_propagates(self) -> None:
        auth = self.auth()
        self.patch(
            auth,
            "get_session",
            lambda: {"access_token": "old", "refresh_token": "r", "email": ""},
        )

        def boom(name, body, sess):
            raise _status_error(500)

        self.patch(auth, "_call_function", boom)

        with self.assertRaises(httpx.HTTPStatusError):
            auth.call_authenticated_function("latest-release", {})

    def test_document_keys_are_still_rejected(self) -> None:
        auth = self.auth()
        self.patch(
            auth,
            "get_session",
            lambda: {"access_token": "old", "refresh_token": "r", "email": ""},
        )
        with self.assertRaises(ValueError) as caught:
            auth.call_authenticated_function("latest-release", {"invoice_rows": []})
        self.assertIn("document", str(caught.exception))


class CompareVersionsTests(_TempLocalAppData):
    def test_equal_versions(self) -> None:
        self.assertEqual(self.updates.compare_versions("0.11.0", "0.11.0"), 0)

    def test_newer_and_older(self) -> None:
        self.assertEqual(self.updates.compare_versions("0.11.1", "0.11.0"), 1)
        self.assertEqual(self.updates.compare_versions("0.11.0", "0.11.1"), -1)
        self.assertEqual(self.updates.compare_versions("1.0.0", "0.99.99"), 1)
        self.assertEqual(self.updates.compare_versions("0.9.9", "0.10.0"), -1)

    def test_rejects_short_prerelease_and_prefixed_versions(self) -> None:
        for bad in ("1.2", "1.2.3-beta", "v1.2.3", "1.2.3+build", "1.2.3.4", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.updates.compare_versions(bad, "1.2.3")

    def test_rejects_non_text(self) -> None:
        with self.assertRaises(ValueError):
            self.updates.compare_versions(None, "1.2.3")  # type: ignore[arg-type]


class ParseLatestReleaseTests(_TempLocalAppData):
    def test_valid_payload(self) -> None:
        manifest = self.updates.parse_latest_release(_payload())
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest.version, "0.11.0")
        self.assertEqual(manifest.title, "CA Unpacker 0.11.0")
        self.assertEqual(manifest.installer_url, INSTALLER_URL)
        self.assertEqual(manifest.installer_sha256, CHECKSUM)
        self.assertEqual(manifest.installer_size, 4096)
        self.assertFalse(manifest.mandatory)
        self.assertEqual(manifest.published_at, "2026-09-11T10:00:00Z")

    def test_no_update_returns_none(self) -> None:
        self.assertIsNone(self.updates.parse_latest_release({"update_available": False}))

    def test_unknown_keys_are_ignored(self) -> None:
        payload = _payload(extra_field="ignored")
        payload["surprise"] = True
        self.assertIsNotNone(self.updates.parse_latest_release(payload))

    def test_minimum_supported_version_is_kept(self) -> None:
        manifest = self.updates.parse_latest_release(
            _payload(minimum_supported_version="0.11.0")
        )
        self.assertEqual(manifest.minimum_supported_version, "0.11.0")

    def test_minimum_supported_version_beside_release_is_kept(self) -> None:
        payload = _payload()
        payload["minimum_supported_version"] = "0.11.0"
        manifest = self.updates.parse_latest_release(payload)
        self.assertEqual(manifest.minimum_supported_version, "0.11.0")

    def test_http_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.updates.parse_latest_release(
                _payload(installer_url="http://github.com/x/setup.exe")
            )

    def test_unapproved_host_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.updates.parse_latest_release(
                _payload(installer_url="https://evil.example.com/setup.exe")
            )

    def test_lookalike_host_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.updates.parse_latest_release(
                _payload(installer_url="https://github.com.evil.example/setup.exe")
            )

    def test_userinfo_and_odd_port_are_rejected(self) -> None:
        for url in (
            "https://user:pass@github.com/setup.exe",
            "https://github.com:8443/setup.exe",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.updates.parse_latest_release(_payload(installer_url=url))

    def test_subdomain_of_approved_host_is_allowed(self) -> None:
        manifest = self.updates.parse_latest_release(
            _payload(installer_url="https://objects.githubusercontent.com/x/setup.exe")
        )
        self.assertIsNotNone(manifest)

    def test_bad_checksum_length_and_charset(self) -> None:
        for bad in ("a" * 63, "a" * 65, "A" * 64, "z" * 64, ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.updates.parse_latest_release(
                        _payload(installer_sha256=bad)
                    )

    def test_zero_and_negative_size(self) -> None:
        for bad in (0, -1):
            with self.subTest(size=bad):
                with self.assertRaises(ValueError):
                    self.updates.parse_latest_release(_payload(installer_size=bad))

    def test_non_integer_size(self) -> None:
        with self.assertRaises(ValueError):
            self.updates.parse_latest_release(_payload(installer_size="4096"))

    def test_malformed_version(self) -> None:
        with self.assertRaises(ValueError):
            self.updates.parse_latest_release(_payload(version="0.11"))

    def test_missing_or_empty_title(self) -> None:
        for bad in ("", "   ", None):
            with self.subTest(title=bad):
                with self.assertRaises(ValueError):
                    self.updates.parse_latest_release(_payload(title=bad))

    def test_missing_release_object(self) -> None:
        with self.assertRaises(ValueError):
            self.updates.parse_latest_release({"update_available": True})


class CacheTests(_TempLocalAppData):
    def test_round_trip(self) -> None:
        entry = _release()
        saved = self.updates.save_update_cache(
            {
                "checked_at": "2026-09-11T10:00:00",
                "current_version": "0.10.0",
                "manifest": entry,
            }
        )
        self.assertEqual(saved["manifest"]["version"], "0.11.0")
        loaded = self.updates.load_update_cache()
        self.assertEqual(loaded["manifest"]["installer_sha256"], CHECKSUM)
        self.assertEqual(loaded["current_version"], "0.10.0")

    def test_corrupt_json_is_empty(self) -> None:
        path = self.updates._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.updates.load_update_cache(), {})

    def test_corrupt_manifest_is_empty(self) -> None:
        path = self.updates._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "checked_at": "2026-09-11T10:00:00",
                    "current_version": "0.10.0",
                    "manifest": {"version": "nope"},
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.updates.load_update_cache(), {})

    def test_missing_cache_is_empty(self) -> None:
        self.assertEqual(self.updates.load_update_cache(), {})


class CheckForUpdateTests(_TempLocalAppData):
    def test_requires_a_signed_in_session(self) -> None:
        # The real seam runs here: no session, no network.
        with self.assertRaises(ValueError) as caught:
            self.updates.check_for_update()
        self.assertIn("Sign in to check for updates.", str(caught.exception))

    def test_request_body_and_function_name(self) -> None:
        self.set_version("0.10.0")
        calls = self.fake_release_call(_payload())
        self.updates.check_for_update()
        self.assertEqual(len(calls), 1)
        name, body = calls[0]
        self.assertEqual(name, "latest-release")
        self.assertEqual(
            body,
            {
                "current_version": "0.10.0",
                "platform": "windows",
                "arch": self.updates._current_arch(),
            },
        )

    def test_same_version_is_not_an_update(self) -> None:
        self.set_version("0.11.0")
        self.fake_release_call(_payload())
        state = self.updates.check_for_update()
        self.assertFalse(state.available)
        self.assertEqual(state.status, "idle")

    def test_newer_version_is_an_update(self) -> None:
        self.set_version("0.10.0")
        self.fake_release_call(_payload())
        state = self.updates.check_for_update()
        self.assertTrue(state.available)
        self.assertEqual(state.status, "available")
        self.assertEqual(state.version, "0.11.0")
        self.assertEqual(state.title, "CA Unpacker 0.11.0")
        self.assertEqual(state.installer_sha256, CHECKSUM)
        self.assertEqual(state.installer_size, 4096)
        self.assertFalse(state.mandatory)

    def test_older_release_is_never_a_downgrade(self) -> None:
        self.set_version("0.12.0")
        self.fake_release_call(_payload())
        state = self.updates.check_for_update()
        self.assertFalse(state.available)

    def test_mandatory_flag(self) -> None:
        self.set_version("0.10.0")
        self.fake_release_call(_payload(mandatory=True))
        state = self.updates.check_for_update()
        self.assertTrue(state.available)
        self.assertTrue(state.mandatory)

    def test_minimum_supported_version_forces_mandatory(self) -> None:
        self.set_version("0.10.0")
        self.fake_release_call(
            _payload(mandatory=False, minimum_supported_version="0.11.0")
        )
        state = self.updates.check_for_update()
        self.assertTrue(state.mandatory)

    def test_minimum_supported_version_below_current_is_not_mandatory(self) -> None:
        self.set_version("0.10.5")
        self.fake_release_call(
            _payload(mandatory=False, minimum_supported_version="0.10.0")
        )
        state = self.updates.check_for_update()
        self.assertFalse(state.mandatory)

    def test_cached_result_avoids_a_second_call(self) -> None:
        self.set_version("0.10.0")
        calls = self.fake_release_call(_payload())
        first = self.updates.check_for_update()
        second = self.updates.check_for_update()
        self.assertEqual(len(calls), 1)
        self.assertTrue(first.available)
        self.assertTrue(second.available)
        self.assertEqual(second.version, "0.11.0")

    def test_force_bypasses_the_cache(self) -> None:
        self.set_version("0.10.0")
        calls = self.fake_release_call(_payload())
        self.updates.check_for_update()
        self.updates.check_for_update(force=True)
        self.assertEqual(len(calls), 2)

    def test_stale_cache_triggers_a_fresh_check(self) -> None:
        self.set_version("0.10.0")
        self.seed_cache(_release(), age_hours=7)
        calls = self.fake_release_call(_payload())
        self.updates.check_for_update()
        self.assertEqual(len(calls), 1)

    def test_corrupted_cache_is_ignored(self) -> None:
        self.set_version("0.10.0")
        path = self.updates._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<<<broken>>>", encoding="utf-8")
        calls = self.fake_release_call(_payload())
        state = self.updates.check_for_update()
        self.assertEqual(len(calls), 1)
        self.assertTrue(state.available)

    def test_network_error_falls_back_to_newer_cache(self) -> None:
        self.set_version("0.10.0")
        self.seed_cache(_release(), age_hours=24)
        self.fake_release_call(error=httpx.ConnectError("offline"))
        state = self.updates.check_for_update()
        self.assertTrue(state.available)
        self.assertEqual(state.version, "0.11.0")
        self.assertFalse(state.error)

    def test_network_error_without_cache_reports_no_update(self) -> None:
        self.set_version("0.10.0")
        self.fake_release_call(error=httpx.ConnectError("offline"))
        state = self.updates.check_for_update()
        self.assertFalse(state.available)
        self.assertEqual(state.status, "idle")
        self.assertTrue(state.error)

    def test_network_error_with_older_cache_reports_no_update(self) -> None:
        self.set_version("0.12.0")
        self.seed_cache(_release(), age_hours=24)
        self.fake_release_call(error=httpx.ConnectError("offline"))
        state = self.updates.check_for_update()
        self.assertFalse(state.available)
        self.assertTrue(state.error)

    def test_server_http_error_falls_back_instead_of_raising(self) -> None:
        self.set_version("0.10.0")
        request = httpx.Request("POST", "https://example.supabase.co/functions/v1/x")
        error = httpx.HTTPStatusError(
            "boom",
            request=request,
            response=httpx.Response(500, request=request),
        )
        self.fake_release_call(error=error)
        state = self.updates.check_for_update()
        self.assertFalse(state.available)
        self.assertTrue(state.error)


class MandatoryGateTests(_TempLocalAppData):
    def test_no_cache_allows_ingest(self) -> None:
        self.set_version("0.10.0")
        self.updates.assert_update_allows_ingest()

    def test_newer_non_mandatory_release_allows_ingest(self) -> None:
        self.set_version("0.10.0")
        self.seed_cache(_release(mandatory=False))
        self.assertFalse(self.updates.mandatory_update_required())
        self.updates.assert_update_allows_ingest()

    def test_newer_mandatory_release_blocks_ingest(self) -> None:
        self.set_version("0.10.0")
        self.seed_cache(_release(mandatory=True))
        self.assertTrue(self.updates.mandatory_update_required())
        with self.assertRaises(ValueError) as caught:
            self.updates.assert_update_allows_ingest()
        self.assertIn("required CA Unpacker update", str(caught.exception))

    def test_minimum_supported_version_blocks_ingest(self) -> None:
        self.set_version("0.10.0")
        self.seed_cache(_release(minimum_supported_version="0.11.0"))
        self.assertTrue(self.updates.mandatory_update_required())

    def test_mandatory_but_not_newer_allows_ingest(self) -> None:
        self.set_version("0.11.0")
        self.seed_cache(_release(mandatory=True))
        self.assertFalse(self.updates.mandatory_update_required())
        self.updates.assert_update_allows_ingest()


class DownloadUpdateTests(_TempLocalAppData):
    def manifest(self, content: bytes, **overrides):
        data = {
            "version": "0.11.0",
            "title": "CA Unpacker 0.11.0",
            "release_notes": "",
            "installer_url": INSTALLER_URL,
            "installer_sha256": hashlib.sha256(content).hexdigest(),
            "installer_size": len(content),
            "mandatory": False,
            "published_at": "",
        }
        data.update(overrides)
        return self.updates.ReleaseManifest(**data)

    def client(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return client

    def expected_paths(self) -> tuple[Path, Path]:
        folder = self.updates.update_root() / "0.11.0"
        final = folder / "CAUnpacker-Setup-0.11.0.exe"
        partial = final.with_name(final.name + ".partial")
        return final, partial

    def test_download_succeeds_with_progress(self) -> None:
        content = b"installer-bytes" * 300
        progress: list[float] = []

        def handler(request):
            return httpx.Response(200, content=content)

        path = self.updates.download_update(
            self.manifest(content),
            progress_callback=progress.append,
            client=self.client(handler),
        )

        final, partial = self.expected_paths()
        self.assertEqual(path, final)
        self.assertTrue(final.exists())
        self.assertFalse(partial.exists())
        self.assertEqual(final.read_bytes(), content)
        self.assertEqual(
            hashlib.sha256(final.read_bytes()).hexdigest(),
            hashlib.sha256(content).hexdigest(),
        )
        self.assertTrue(progress)
        self.assertEqual(progress[-1], 1.0)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in progress))

    def test_download_lives_under_local_app_data(self) -> None:
        content = b"x" * 64

        def handler(request):
            return httpx.Response(200, content=content)

        path = self.updates.download_update(
            self.manifest(content), client=self.client(handler)
        )
        root = self.updates.update_root()
        self.assertTrue(path.is_relative_to(root))
        self.assertTrue(path.is_relative_to(Path(self._tmp.name).resolve()))

    def test_wrong_size_fails_and_leaves_no_file(self) -> None:
        content = b"y" * 100

        def handler(request):
            return httpx.Response(200, content=content)

        manifest = self.manifest(content, installer_size=len(content) + 5)
        with self.assertRaises(ValueError):
            self.updates.download_update(manifest, client=self.client(handler))
        final, partial = self.expected_paths()
        self.assertFalse(final.exists())
        self.assertFalse(partial.exists())

    def test_wrong_checksum_fails_and_leaves_no_file(self) -> None:
        content = b"z" * 100

        def handler(request):
            return httpx.Response(200, content=content)

        manifest = self.manifest(content, installer_sha256="0" * 64)
        with self.assertRaises(ValueError):
            self.updates.download_update(manifest, client=self.client(handler))
        final, partial = self.expected_paths()
        self.assertFalse(final.exists())
        self.assertFalse(partial.exists())

    def test_oversized_stream_aborts(self) -> None:
        content = b"q" * 200

        def handler(request):
            return httpx.Response(200, content=content)

        manifest = self.manifest(content, installer_size=len(content) - 10)
        with self.assertRaises(ValueError):
            self.updates.download_update(manifest, client=self.client(handler))
        final, partial = self.expected_paths()
        self.assertFalse(final.exists())
        self.assertFalse(partial.exists())

    def test_redirect_to_approved_host_is_followed(self) -> None:
        content = b"r" * 128
        requested: list[str] = []

        def handler(request):
            requested.append(str(request.url))
            if request.url.host == "github.com":
                return httpx.Response(
                    302,
                    headers={
                        "location": "https://objects.githubusercontent.com/blob/setup.exe"
                    },
                )
            return httpx.Response(200, content=content)

        path = self.updates.download_update(
            self.manifest(content), client=self.client(handler)
        )
        self.assertTrue(path.exists())
        self.assertEqual(len(requested), 2)
        self.assertIn("objects.githubusercontent.com", requested[1])

    def test_redirect_to_unapproved_host_is_rejected(self) -> None:
        content = b"s" * 64
        requested: list[str] = []

        def handler(request):
            requested.append(str(request.url))
            return httpx.Response(
                302, headers={"location": "https://evil.example.com/setup.exe"}
            )

        with self.assertRaises(ValueError):
            self.updates.download_update(
                self.manifest(content), client=self.client(handler)
            )
        self.assertEqual(len(requested), 1)
        final, partial = self.expected_paths()
        self.assertFalse(final.exists())
        self.assertFalse(partial.exists())

    def test_redirect_without_location_is_rejected(self) -> None:
        content = b"t" * 64

        def handler(request):
            return httpx.Response(302)

        with self.assertRaises(ValueError):
            self.updates.download_update(
                self.manifest(content), client=self.client(handler)
            )

    def test_http_initial_url_is_rejected_before_any_request(self) -> None:
        content = b"u" * 64
        requested: list[str] = []

        def handler(request):
            requested.append(str(request.url))
            return httpx.Response(200, content=content)

        manifest = self.manifest(
            content, installer_url="http://github.com/x/CAUnpacker-Setup-0.11.0.exe"
        )
        with self.assertRaises(ValueError):
            self.updates.download_update(manifest, client=self.client(handler))
        self.assertEqual(requested, [])

    def test_http_status_error_is_raised(self) -> None:
        content = b"v" * 64

        def handler(request):
            return httpx.Response(404, content=b"missing")

        with self.assertRaises(httpx.HTTPStatusError):
            self.updates.download_update(
                self.manifest(content), client=self.client(handler)
            )
        final, partial = self.expected_paths()
        self.assertFalse(final.exists())
        self.assertFalse(partial.exists())

    def test_cancel_before_start_removes_stale_partial(self) -> None:
        content = b"w" * 64
        final, partial = self.expected_paths()
        final.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(b"stale-download")

        event = threading.Event()
        event.set()

        def handler(request):  # pragma: no cover - must never be called
            raise AssertionError("no request expected")

        with self.assertRaises(self.updates.UpdateCancelled):
            self.updates.download_update(
                self.manifest(content),
                cancel_event=event,
                client=self.client(handler),
            )
        self.assertFalse(final.exists())
        self.assertFalse(partial.exists())

    def test_cancel_mid_stream_removes_partial_and_keeps_no_final(self) -> None:
        content = b"a" * 400
        event = threading.Event()

        def progress(fraction: float) -> None:
            if fraction >= 0.5:
                event.set()

        def handler(request):
            return httpx.Response(
                200,
                content=iter([b"a" * 100, b"a" * 100, b"a" * 100, b"a" * 100]),
            )

        with self.assertRaises(self.updates.UpdateCancelled):
            self.updates.download_update(
                self.manifest(content),
                progress_callback=progress,
                cancel_event=event,
                client=self.client(handler),
            )
        final, partial = self.expected_paths()
        self.assertFalse(final.exists())
        self.assertFalse(partial.exists())

    def test_existing_verified_file_is_reused_without_a_request(self) -> None:
        content = b"reused-installer" * 10
        final, _partial = self.expected_paths()
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(content)
        requested: list[str] = []

        def handler(request):  # pragma: no cover - must never be called
            requested.append(str(request.url))
            raise AssertionError("no request expected")

        path = self.updates.download_update(
            self.manifest(content), client=self.client(handler)
        )
        self.assertEqual(path, final)
        self.assertEqual(requested, [])

    def test_existing_corrupt_file_is_replaced(self) -> None:
        content = b"good" * 50
        final, _partial = self.expected_paths()
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"truncated")

        def handler(request):
            return httpx.Response(200, content=content)

        path = self.updates.download_update(
            self.manifest(content), client=self.client(handler)
        )
        self.assertEqual(path.read_bytes(), content)

    def test_invalid_version_is_rejected(self) -> None:
        content = b"x" * 10

        def handler(request):  # pragma: no cover
            raise AssertionError("no request expected")

        manifest = self.manifest(content, version="../escape")
        with self.assertRaises(ValueError):
            self.updates.download_update(manifest, client=self.client(handler))


if __name__ == "__main__":
    unittest.main()
