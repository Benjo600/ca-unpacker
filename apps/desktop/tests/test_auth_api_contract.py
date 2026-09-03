from __future__ import annotations

import os
import tempfile
import unittest


class DesktopAuthApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def test_get_auth_state_shape(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        state = api.get_auth_state()
        self.assertGreaterEqual(
            set(state.keys()),
            {
                "signed_in",
                "email",
                "plan",
                "files_used",
                "file_limit",
                "offline",
            },
        )
        self.assertFalse(state["signed_in"])

    def test_handle_auth_callback_parses_fragment_tokens(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        url = (
            "caunpacker://auth/callback"
            "#access_token=access.abc&refresh_token=refresh.xyz&token_type=bearer"
        )
        result = api.handle_auth_callback(url)
        self.assertTrue(result["ok"])
        self.assertTrue(result["signed_in"])
        self.assertEqual(api.get_auth_state()["signed_in"], True)

    def test_open_signup_and_login_return_ok(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        with patch("webbrowser.open") as opener:
            signup = api.open_signup()
            login = api.open_login()
        self.assertTrue(signup["ok"])
        self.assertTrue(login["ok"])
        self.assertEqual(opener.call_count, 2)

    def test_logout_clears_session(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        api.handle_auth_callback(
            "caunpacker://auth/callback#access_token=a.b.c&refresh_token=refresh"
        )
        self.assertTrue(api.get_auth_state()["signed_in"])
        result = api.logout()
        self.assertTrue(result["ok"])
        self.assertFalse(api.get_auth_state()["signed_in"])
