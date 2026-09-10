from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINIAPP_ROOT = ROOT / "nexcore_miniapp" / "dist"


def get_miniapp_url() -> str | None:
    explicit = (os.getenv("MINIAPP_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/") + "/"

    railway_domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip()
    if railway_domain:
        if railway_domain.startswith(("http://", "https://")):
            base = railway_domain.rstrip("/")
        else:
            base = "https://" + railway_domain.rstrip("/")
        return base + "/miniapp/"

    return None


def miniapp_port() -> int:
    raw = (os.getenv("PORT") or "8080").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 8080
    return max(1, min(value, 65535))


def miniapp_only_mode_enabled() -> bool:
    # Safe rollout default: do not freeze the working Telegram game until the
    # operator explicitly enables Mini App-only mode after checking the public URL.
    raw = (os.getenv("MINIAPP_ONLY_MODE") or "0").strip().lower()
    requested = raw not in {"", "0", "false", "no", "off"}
    return requested and get_miniapp_url() is not None
