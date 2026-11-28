from __future__ import annotations

from apps.engine.db import reset_engine
from apps.engine.library import delete_library_folder
from apps.engine.pdf_passwords import clear_all_passwords


def wipe_all() -> None:
    from apps.engine.ocr import clear_extraction_cache

    clear_all_passwords()
    reset_engine()
    clear_extraction_cache()
    delete_library_folder()
