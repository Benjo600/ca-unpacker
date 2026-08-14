from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

APP_DIR_NAME = "CAUnpacker"
DB_FILENAME = "app.db"


def get_library_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def get_db_path() -> Path:
    return get_library_path() / DB_FILENAME


def init_library() -> Path:
    root = get_library_path()
    root.mkdir(parents=True, exist_ok=True)
    (root / "files").mkdir(exist_ok=True)
    (root / "packs").mkdir(exist_ok=True)
    return root


def files_root() -> Path:
    return init_library() / "files"


def packs_root() -> Path:
    return init_library() / "packs"


def resolve_storage_key(storage_key: str) -> Path:
    return files_root() / storage_key


def delete_library_folder() -> None:
    root = get_library_path()
    if not root.exists():
        return
    last_error: OSError | None = None
    for _ in range(10):
        try:
            shutil.rmtree(root)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.12)
    if last_error:
        raise last_error
