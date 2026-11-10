"""Single source of truth for the CA Unpacker desktop application version.

``APP_VERSION`` is the only place this project writes its version. The desktop
app reports it through ``DesktopApi.get_state()`` and ``build_installer.bat``
reads it to pass ``/DAppVersion=<value>`` to Inno Setup, so the running app, the
built installer metadata, and the published release always agree.

Bump this value and nothing else: ``installer/ca-unpacker.iss`` deliberately
refuses to compile without a version supplied by the build script, and
``apps/engine/tests/test_version_contract.py`` guards the contract.
"""

APP_VERSION = "0.11.0"

__all__ = ["APP_VERSION"]
