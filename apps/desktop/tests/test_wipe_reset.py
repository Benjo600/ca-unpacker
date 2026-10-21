from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _signed_in_access_token(email: str = "owner@example.com") -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": email, "exp": int(time.time()) + 3600}).encode("utf-8")
    )
    return "header." + payload.decode("ascii").rstrip("=") + ".sig"


class WipeAndResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_wipe_and_reset_clears_data_and_keeps_the_window(self) -> None:
        import apps.desktop.app as desktop_app
        from apps.engine.clients import create_client, list_clients
        from apps.engine.firm import get_firm, save_firm
        from apps.engine.library import get_library_path

        save_firm("Before reset")
        create_client("Old client")

        api = desktop_app.DesktopApi()
        before = desktop_app._wipe_epoch
        result = api.wipe_and_reset()

        self.assertTrue(result["ok"], result.get("error"))
        self.assertIsNone(result["firm"])
        self.assertEqual(result["clients"], [])
        # The epoch moved and no fresh process was spawned for this.
        self.assertEqual(desktop_app._wipe_epoch, before + 1)
        self.assertIsNone(desktop_app._WINDOW)
        # The library was rebuilt empty in place, not left deleted.
        self.assertTrue(get_library_path().exists())
        self.assertIsNone(get_firm())
        self.assertEqual(list_clients(), [])

    def test_wipe_and_reset_leaves_a_usable_engine(self) -> None:
        import apps.desktop.app as desktop_app
        from apps.engine.firm import save_firm

        api = desktop_app.DesktopApi()
        first = api.wipe_and_reset()
        self.assertTrue(first["ok"], first.get("error"))

        # The app is immediately usable again on the rebuilt library.
        saved = save_firm("After reset")
        self.assertIsNotNone(saved)

        second = api.wipe_and_reset()
        self.assertTrue(second["ok"], second.get("error"))
        self.assertIsNone(second["firm"])

    def test_wipe_and_reset_keeps_you_signed_in(self) -> None:
        """Delete everything clears client data, not the login."""
        import apps.desktop.app as desktop_app
        from apps.engine import auth as auth_module
        from apps.engine.clients import create_client, list_clients
        from apps.engine.firm import save_firm

        auth_module.login_via_tokens(_signed_in_access_token(), "refresh-token")
        save_firm("Wipe me")
        create_client("Gone client")

        api = desktop_app.DesktopApi()
        with mock.patch.object(auth_module, "_network_available", return_value=False):
            result = api.wipe_and_reset()

        self.assertTrue(result["ok"], result.get("error"))
        # Client data is gone…
        self.assertIsNone(result["firm"])
        self.assertEqual(result["clients"], [])
        self.assertEqual(list_clients(), [])
        # …but the login survived.
        self.assertTrue(result["auth"]["signed_in"], result.get("auth"))
        self.assertEqual(result["auth"]["email"], "owner@example.com")
        self.assertIsNotNone(auth_module.get_session())


if __name__ == "__main__":
    unittest.main()
