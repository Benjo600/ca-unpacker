from __future__ import annotations

import hashlib
import os
from datetime import date

from apps.engine.settings import load_settings, save_settings

STARTER_LIMIT = 100
PLANS = {
    "starter": {
        "id": "starter",
        "label": "Starter",
        "price_inr": 999,
        "file_limit": STARTER_LIMIT,
    },
    "pro": {
        "id": "pro",
        "label": "Pro",
        "price_inr": 2500,
        "file_limit": None,
    },
}
SUITE = {"id": "suite", "label": "Suite", "price_inr": 6000, "status": "coming"}
_TEST_KEYS = {
    "STARTER-TEST": "starter",
    "PRO-TEST": "pro",
}
_SUITE_KEYS = {"SUITE-TEST", "SUITE"}
_QUOTA_MESSAGE = (
    "Starter covers 100 files this calendar month (₹999). "
    "This dump would go over that limit. Upgrade to Pro (₹2,500) for unlimited files, "
    "or wait until next month."
)
_OFFLINE_ACTIVATE = (
    "Could not reach the licence service. Work already on this PC is still here. "
    "Connect to the internet and try again."
)


def activation_payload(key: str) -> dict[str, str]:
    """Metadata sent to a licence host. Never includes documents or extracted rows."""
    cleaned = (key or "").strip()
    return {
        "product": "ca-unpacker",
        "key_sha256": hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
    }


def _month_key(today: date | None = None) -> str:
    when = today or date.today()
    return when.strftime("%Y-%m")


def _dev_mode() -> bool:
    return os.environ.get("CA_UNPACKER_DEV") == "1"


def _use_supabase() -> bool:
    from apps.engine.auth import get_auth_state

    return bool(get_auth_state().get("signed_in"))


def get_license_status(today: date | None = None) -> dict:
    if _use_supabase():
        from apps.engine.auth import get_auth_state

        state = get_auth_state()
        plan_id = str(state.get("plan") or "starter")
        if plan_id not in PLANS:
            plan_id = "starter"
        plan = PLANS[plan_id]
        limit = state.get("file_limit")
        used = int(state.get("files_used") or 0)
        remaining = None if limit is None else max(0, int(limit) - used)
        return {
            "plan": plan_id,
            "plan_label": plan["label"],
            "price_inr": plan["price_inr"],
            "file_limit": limit,
            "files_used": used,
            "files_remaining": remaining,
            "month": _month_key(today),
            "activated": True,
            "auth_mode": "supabase",
            "signed_in": True,
            "email": state.get("email"),
            "offline": bool(state.get("offline")),
            "suite": SUITE,
            "plans": {
                "starter": {**PLANS["starter"], "modules": "all four"},
                "pro": {**PLANS["pro"], "modules": "all four"},
                "suite": SUITE,
            },
        }

    data = load_settings()
    plan_id = str(data.get("license_plan") or "starter")
    if plan_id not in PLANS:
        plan_id = "starter"
    plan = PLANS[plan_id]
    month = str(data.get("license_month") or "")
    used = int(data.get("license_files_used") or 0)
    current = _month_key(today)
    if month != current:
        used = 0
        month = current
    limit = plan["file_limit"]
    remaining = None if limit is None else max(0, limit - used)
    return {
        "plan": plan_id,
        "plan_label": plan["label"],
        "price_inr": plan["price_inr"],
        "file_limit": limit,
        "files_used": used,
        "files_remaining": remaining,
        "month": month,
        "activated": bool(data.get("license_key")),
        "auth_mode": "dev" if _dev_mode() else "supabase",
        "signed_in": False,
        "email": None,
        "offline": False,
        "suite": SUITE,
        "plans": {
            "starter": {**PLANS["starter"], "modules": "all four"},
            "pro": {**PLANS["pro"], "modules": "all four"},
            "suite": SUITE,
        },
    }


def activate_key(key: str, *, network_available: bool | None = None) -> dict:
    cleaned = (key or "").strip().upper()
    if not cleaned:
        raise ValueError("Enter a licence key.")
    if cleaned in _SUITE_KEYS or cleaned.startswith("SUITE-"):
        raise ValueError("Suite (₹6,000) is coming. Starter and Pro are available now.")
    if _dev_mode() and cleaned in _TEST_KEYS:
        return _store_plan(_TEST_KEYS[cleaned], cleaned)
    if network_available is False:
        raise ValueError(_OFFLINE_ACTIVATE)
    raise ValueError("That licence key was not recognised.")


def _store_plan(plan_id: str, key: str) -> dict:
    save_settings(
        {
            "license_plan": plan_id,
            "license_key": key,
        }
    )
    return get_license_status()


def assert_can_ingest(file_count: int, today: date | None = None) -> None:
    if _use_supabase():
        from apps.engine.auth import check_can_ingest

        check_can_ingest(file_count, today=today)
        return
    count = int(file_count or 0)
    if count <= 0:
        return
    status = get_license_status(today)
    limit = status["file_limit"]
    if limit is None:
        return
    if status["files_used"] + count > limit:
        raise ValueError(_QUOTA_MESSAGE)


def record_ingested(file_count: int, today: date | None = None) -> dict:
    if _use_supabase():
        from apps.engine.auth import record_usage

        record_usage(file_count)
        return get_license_status(today)
    count = int(file_count or 0)
    if count <= 0:
        return get_license_status(today)
    status = get_license_status(today)
    used = status["files_used"] + count
    save_settings(
        {
            "license_plan": status["plan"],
            "license_month": status["month"],
            "license_files_used": used,
        }
    )
    return get_license_status(today)
