from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

APP_DIR_NAME = "CAUnpacker"
DB_FILENAME = "app.db"
LOCK_FILENAME = "library.lock"

_lock_held = False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_library_lock() -> None:
    """One writer at a time for a shared library folder (second PC / second window)."""
    global _lock_held
    if _lock_held:
        return
    root = init_library()
    path = root / LOCK_FILENAME
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            data = {}
        try:
            pid = int(data.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid and pid != os.getpid() and _pid_alive(pid):
            raise ValueError(
                "CA Unpacker is already using this library folder. "
                "Only one window can write at a time."
            )
    path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    _lock_held = True


def release_library_lock() -> None:
    global _lock_held
    if not _lock_held:
        return
    path = get_library_path() / LOCK_FILENAME
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if int(data.get("pid") or 0) == os.getpid():
                path.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    _lock_held = False


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
