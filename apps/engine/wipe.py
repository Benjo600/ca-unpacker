from __future__ import annotations

from apps.engine.db import reset_engine
from apps.engine.library import delete_library_folder


def wipe_all() -> None:
    reset_engine()
    delete_library_folder()
