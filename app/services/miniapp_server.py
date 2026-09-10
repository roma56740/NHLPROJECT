from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

from app.services.miniapp_runtime import MINIAPP_ROOT, ROOT, miniapp_port
from app.services import release_2026_09 as release
from config import settings

logger = logging.getLogger(__name__)

_ALIAS_ROOTS = {
    "heroes": ROOT / "assets" / "release" / "heroes",
    "pirates": ROOT / "assets" / "release" / "pirates",
    "fireside": ROOT / "assets" / "release" / "fireside",
}


def _safe_file(root: Path, relative: str) -> Path | None:
    try:
        root_resolved = root.resolve(strict=True)
        candidate = (root_resolved / relative).resolve(strict=True)
        candidate.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _telegram_user_id_from_init_data(raw: str) -> int | None:
    """Validate Telegram Mini App initData and return the Telegram user id."""
    if not raw:
        return None
    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True))
        received_hash = pairs.pop("hash", "")
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
        secret_key = hmac.new(b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            return None
        auth_date = int(pairs.get("auth_date", "0"))
        if auth_date <= 0 or abs(int(time.time()) - auth_date) > 24 * 60 * 60:
            return None
        user = json.loads(pairs.get("user", "{}"))
        return int(user["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _request_telegram_id(request: web.Request) -> int | None:
    return _telegram_user_id_from_init_data(request.headers.get("X-Telegram-Init-Data", ""))


async def api_account(request: web.Request) -> web.Response:
    telegram_id = _request_telegram_id(request)
    if telegram_id is None:
        return web.json_response({"ok": False, "error": "telegram_auth_required"}, status=401)
    status = release.pass_status(telegram_id)
    if status is None:
        return web.json_response({"ok": False, "error": "profile_not_found"}, status=404)
    return web.json_response({
        "ok": True,
        "energy": int(status["energy"]),
        "fireside_premium": bool(status["premium"]),
        "fireside_points": int(status["bp_points"]),
        "fireside_level": int(status["level"]),
    })


async def api_purchase_fireside_pass(request: web.Request) -> web.Response:
    telegram_id = _request_telegram_id(request)
    if telegram_id is None:
        return web.json_response({"ok": False, "error": "telegram_auth_required"}, status=401)
    ok, message = release.purchase_fireside_pass(telegram_id)
    status = release.pass_status(telegram_id)
    payload = {"ok": ok, "message": message}
    if status is not None:
        payload.update({"energy": int(status["energy"]), "fireside_premium": bool(status["premium"])})
    return web.json_response(payload, status=200 if ok else 400)


async def healthz(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "nexcore"})


async def root_redirect(_request: web.Request) -> web.Response:
    raise web.HTTPFound("/miniapp/")


async def miniapp_file(request: web.Request) -> web.StreamResponse:
    tail = (request.match_info.get("tail") or "").lstrip("/")
    if not tail:
        tail = "index.html"

    # Large event artwork is stored only once in the repository, under
    # assets/release. The Mini App keeps its original relative URLs and this
    # router aliases those folders without duplicating ~150 MB of images.
    parts = tail.split("/", 2)
    if len(parts) >= 3 and parts[0] == "assets" and parts[1] in _ALIAS_ROOTS:
        candidate = _safe_file(_ALIAS_ROOTS[parts[1]], parts[2])
    else:
        candidate = _safe_file(MINIAPP_ROOT, tail)

    if candidate is None:
        raise web.HTTPNotFound()

    response = web.FileResponse(candidate)
    if candidate.name in {"index.html", "app.js", "style.css"}:
        response.headers["Cache-Control"] = "no-cache"
    else:
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response


async def start_miniapp_server() -> web.AppRunner:
    index = MINIAPP_ROOT / "index.html"
    if not index.is_file():
        raise RuntimeError(f"Mini App index is missing: {index}")

    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/account", api_account)
    app.router.add_post("/api/fireside/pass/purchase", api_purchase_fireside_pass)
    app.router.add_get("/", root_redirect)
    app.router.add_get("/miniapp/{tail:.*}", miniapp_file)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=miniapp_port())
    await site.start()
    logger.info("Nexcore Mini App HTTP server started on port %s", miniapp_port())
    return runner
