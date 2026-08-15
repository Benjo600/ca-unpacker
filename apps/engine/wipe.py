from __future__ import annotations

from apps.engine.db import reset_engine
from apps.engine.library import delete_library_folder
from apps.engine.pdf_passwords import clear_all_passwords


def wipe_all() -> None:
    clear_all_passwords()
    reset_engine()
    delete_library_folder()
