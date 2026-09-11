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

    def test_legacy_browser_auth_methods_direct_users_to_in_app_form(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        signup = api.open_signup()
        login = api.open_login()
        self.assertFalse(signup["ok"])
        self.assertEqual(signup["error"], "Use the in-app sign up form.")
        self.assertFalse(login["ok"])
        self.assertEqual(login["error"], "Use the in-app login form.")

    def test_logout_clears_session(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        # Keep this test offline: the bundled config points at the real project,
        # and logout would otherwise revoke tokens against it over the network.
        with patch("apps.engine.auth._network_available", return_value=False):
            api.handle_auth_callback(
                "caunpacker://auth/callback#access_token=a.b.c&refresh_token=refresh"
            )
            self.assertTrue(api.get_auth_state()["signed_in"])
            result = api.logout()
            self.assertTrue(result["ok"])
            self.assertFalse(api.get_auth_state()["signed_in"])

    def test_login_with_password_returns_auth_state(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        signed_in = {
            "signed_in": True,
            "email": "ca@firm.in",
            "plan": "starter",
            "files_used": 3,
            "file_limit": 100,
            "offline": False,
        }
        with patch("apps.engine.auth.sign_in_with_password", create=True, return_value=signed_in) as signin, patch(
            "apps.engine.auth.fetch_quota", return_value=None
        ), patch("apps.engine.auth.get_auth_state", return_value=signed_in):
            result = api.login_with_password("ca@firm.in", "hunter2")
        signin.assert_called_once_with("ca@firm.in", "hunter2")
        self.assertTrue(result["ok"])
        self.assertTrue(result["signed_in"])
        self.assertGreaterEqual(
            set(result.keys()),
            {"signed_in", "email", "plan", "files_used", "file_limit", "offline"},
        )

    def test_login_with_password_converts_value_error(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        with patch(
            "apps.engine.auth.sign_in_with_password",
            create=True,
            side_effect=ValueError("That email or password is wrong."),
        ):
            result = api.login_with_password("ca@firm.in", "wrong")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "That email or password is wrong.")

    def test_login_with_password_rejects_blank_fields(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        with patch("apps.engine.auth.sign_in_with_password", create=True) as signin:
            no_email = api.login_with_password("   ", "hunter2")
            no_password = api.login_with_password("ca@firm.in", "")
        signin.assert_not_called()
        self.assertFalse(no_email["ok"])
        self.assertTrue(no_email["error"])
        self.assertFalse(no_password["ok"])
        self.assertTrue(no_password["error"])

    def test_login_survives_quota_fetch_failure(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        signed_in = {
            "signed_in": True,
            "email": "ca@firm.in",
            "plan": "pro",
            "files_used": 0,
            "file_limit": None,
            "offline": True,
        }
        with patch("apps.engine.auth.sign_in_with_password", create=True, return_value=signed_in), patch(
            "apps.engine.auth.fetch_quota", side_effect=RuntimeError("network down")
        ), patch("apps.engine.auth.get_auth_state", return_value=signed_in):
            result = api.login_with_password("ca@firm.in", "hunter2")
        self.assertTrue(result["ok"])
        self.assertTrue(result["signed_in"])

    def test_signup_confirmation_required_is_not_signed_in(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        pending = {
            "signed_in": False,
            "confirmation_required": True,
            "email": "new@firm.in",
        }
        with patch("apps.engine.auth.sign_up_with_password", create=True, return_value=pending):
            result = api.signup_with_password("new@firm.in", "hunter2")
        self.assertTrue(result["ok"])
        self.assertTrue(result["confirmation_required"])
        self.assertFalse(result["signed_in"])
        self.assertEqual(result["email"], "new@firm.in")

    def test_signup_signed_in_returns_auth_state(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        signed_in = {
            "signed_in": True,
            "email": "new@firm.in",
            "plan": "starter",
            "files_used": 0,
            "file_limit": 100,
            "offline": False,
        }
        with patch("apps.engine.auth.sign_up_with_password", create=True, return_value=signed_in), patch(
            "apps.engine.auth.fetch_quota", return_value=None
        ), patch("apps.engine.auth.get_auth_state", return_value=signed_in):
            result = api.signup_with_password("new@firm.in", "hunter2")
        self.assertTrue(result["ok"])
        self.assertTrue(result["signed_in"])
        self.assertFalse(result["confirmation_required"])

    def test_signup_converts_value_error(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        with patch(
            "apps.engine.auth.sign_up_with_password",
            create=True,
            side_effect=ValueError("Password must be at least 8 characters."),
        ):
            result = api.signup_with_password("new@firm.in", "abc")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Password must be at least 8 characters.")

    def test_request_password_reset(self) -> None:
        from unittest.mock import patch

        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        with patch("apps.engine.auth.send_password_reset", create=True) as reset:
            ok = api.request_password_reset("ca@firm.in")
            blank = api.request_password_reset("  ")
        reset.assert_called_once_with("ca@firm.in")
        self.assertTrue(ok["ok"])
        self.assertFalse(blank["ok"])
        self.assertTrue(blank["error"])

    def test_extract_deep_link_url_from_argv(self) -> None:
        from apps.desktop.app import extract_deep_link_url

        url = (
            "caunpacker://auth/callback"
            "#access_token=access.abc&refresh_token=refresh.xyz"
        )
        self.assertEqual(
            extract_deep_link_url(["CAUnpacker.exe", url]),
            url,
        )
        self.assertIsNone(extract_deep_link_url(["CAUnpacker.exe"]))
        self.assertIsNone(
            extract_deep_link_url(["CAUnpacker.exe", "https://example.com"])
        )
