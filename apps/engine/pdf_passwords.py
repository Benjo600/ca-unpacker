from __future__ import annotations

import threading

_LOCK = threading.Lock()
_PASSWORDS: dict[int, str] = {}


def set_file_password(file_id: int, password: str) -> None:
    with _LOCK:
        _PASSWORDS[int(file_id)] = str(password)


def get_file_password(file_id: int) -> str | None:
    with _LOCK:
        return _PASSWORDS.get(int(file_id))


def clear_file_password(file_id: int) -> None:
    with _LOCK:
        _PASSWORDS.pop(int(file_id), None)


def clear_all_passwords() -> None:
    with _LOCK:
        _PASSWORDS.clear()


def redact_known_passwords(text: str) -> str:
    if not text:
        return text
    with _LOCK:
        secrets = [value for value in _PASSWORDS.values() if value]
    for secret in secrets:
        text = text.replace(secret, "********")
    return text
