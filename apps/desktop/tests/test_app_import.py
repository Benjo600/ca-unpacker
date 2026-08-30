from importlib import import_module


def test_desktop_app_imports() -> None:
    import_module("apps.desktop.app")
