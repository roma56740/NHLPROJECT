from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qsl, quote

from aiohttp import web

from app.database.db import get_connection
from app.services.miniapp_runtime import MINIAPP_ROOT, ROOT, miniapp_port
from app.services import community
from app.services import creators
from app.services import daily_login
from app.services import mastery as mastery_service
from app.services import quests
from app.services import release_2026_09 as release
from app.services import xfactors
from app.services.lineup import (
    LINEUP_SLOT_ORDER,
    auto_fill_best_lineup,
    clear_lineup,
    get_lineup_overview,
    remove_lineup_slot,
    set_lineup_card,
)
from app.services.match_guard import CAPTCHA_TTL_SECONDS, generate_captcha
from app.services.matches import (
    get_match_details,
    get_match_history_page,
    get_match_main_info,
    play_quick_match,
)
from app.services.user_cards import get_player_cards_page, get_player_card_profile
from app.services.users import get_player_profile_by_telegram_id
from config import settings

logger = logging.getLogger(__name__)

_ACTION_COOLDOWNS: dict[str, float] = {
    "match_challenge": 0.8,
    "quick_match": 31.0,
    "box_buy": 1.5,
    "box_open": 2.0,
    "hero_unlock": 1.5,
    "hero_claim": 1.0,
    "cursed_play": 31.0,
    "cursed_mirror": 1.5,
    "cursed_exchange": 1.5,
    "trade_accept": 1.0,
    "trade_decline": 1.0,
    "trade_cancel": 1.0,
    "trade_create": 2.0,
    "daily_claim": 1.0,
    "quest_claim": 1.0,
    "pass_purchase": 1.5,
    "pass_claim": 1.0,
    "achievement_claim": 1.0,
    "craft": 2.0,
    "lineup": 0.6,
    "xfactor": 0.8,
    "mastery": 1.0,
}
_action_guard_state: dict[tuple[int, str], float] = {}
_mutation_inflight: set[int] = set()
_match_challenges: dict[int, dict[str, object]] = {}



@web.middleware
async def _mutation_serialization_middleware(request: web.Request, handler):
    """Serialize authenticated Mini App writes per player.

    Client debouncing improves UX, but economy safety must be server-side. If an
    autoclicker fires several POST requests while the first transaction is still
    running, only the first is allowed to enter gameplay/economy code.
    """
    if request.method != "POST":
        return await handler(request)
    telegram_id = _request_telegram_id(request)
    if telegram_id is None:
        return await handler(request)
    telegram_id = int(telegram_id)
    if telegram_id in _mutation_inflight:
        return web.json_response(
            {"ok": False, "error": "action_in_progress", "message": "Предыдущее действие ещё выполняется."},
            status=429,
        )
    _mutation_inflight.add(telegram_id)
    try:
        return await handler(request)
    finally:
        _mutation_inflight.discard(telegram_id)

def _new_match_challenge(user_id: int, mode: str) -> dict[str, object]:
    captcha = generate_captcha()
    token = secrets.token_urlsafe(18)
    expires_at = time.monotonic() + float(CAPTCHA_TTL_SECONDS)
    record = {
        "challenge_id": token,
        "correct": str(captcha.correct),
        "prompt": str(captcha.prompt),
        "options": [str(item) for item in captcha.options],
        "mode": str(mode),
        "expires_at": expires_at,
    }
    _match_challenges[int(user_id)] = record
    # Bound stale process-local challenges. They are only anti-autoclick material,
    # never game/economy state, so pruning them has no persistence effect.
    if len(_match_challenges) > 20_000:
        now = time.monotonic()
        expired = [uid for uid, item in _match_challenges.items() if float(item.get("expires_at", 0.0)) <= now]
        for uid in expired[:15_000]:
            _match_challenges.pop(uid, None)
    return record


def _public_match_challenge(record: dict[str, object]) -> dict[str, object]:
    # The prompt itself tells a human which option to press; returning that instruction
    # does not reveal anything beyond the visible challenge. Keep the source text in
    # English so the Mini App localization layer can render either RU or EN.
    target = str(record.get("correct") or "")
    return {
        "challenge_id": str(record.get("challenge_id") or ""),
        "prompt": f"Press number {target} to start the match",
        "options": list(record.get("options") or []),
        "ttl_seconds": int(CAPTCHA_TTL_SECONDS),
        "mode": str(record.get("mode") or "normal"),
    }


def _consume_match_challenge(
    user_id: int, challenge_id: object, answer: object, expected_mode: str
) -> str | None:
    record = _match_challenges.pop(int(user_id), None)
    if record is None:
        return "captcha_missing"
    if float(record.get("expires_at", 0.0)) <= time.monotonic():
        return "captcha_expired"
    if not secrets.compare_digest(str(record.get("challenge_id") or ""), str(challenge_id or "")):
        return "captcha_invalid"
    if not secrets.compare_digest(str(record.get("mode") or "normal"), str(expected_mode)):
        return "captcha_wrong_mode"
    if not secrets.compare_digest(str(record.get("correct") or ""), str(answer or "")):
        return "captcha_wrong"
    return None


async def api_match_challenge(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "match_challenge")
    if guard is not None:
        return guard
    mode = str(request.query.get("mode") or "normal").strip().lower()
    if mode not in {"normal", "cursed"}:
        return web.json_response({"ok": False, "error": "invalid_match_mode"}, status=400)
    # Requiring this one-time challenge BEFORE any Mini App match-start endpoint is
    # the actual anti-autoclick gate. No match/simulation is created here.
    record = _new_match_challenge(int(profile.id), mode)
    return web.json_response({"ok": True, "challenge": _public_match_challenge(record)})


def _action_guard(user_id: int, action: str) -> str | None:
    cooldown = float(_ACTION_COOLDOWNS.get(action, 0.0))
    if cooldown <= 0:
        return None
    now = time.monotonic()
    key = (int(user_id), action)
    unlock_at = _action_guard_state.get(key, 0.0)
    if unlock_at > now:
        wait_for = max(0.1, unlock_at - now)
        return f"too_fast:{action}:{wait_for:.1f}"
    _action_guard_state[key] = now + cooldown
    if len(_action_guard_state) > 30_000:
        expired = [item for item, until in _action_guard_state.items() if until <= now]
        for item in expired[:20_000]:
            _action_guard_state.pop(item, None)
    return None


def _guard_response(profile, action: str):
    message = _action_guard(int(profile.id), action)
    if message is None:
        return None
    return web.json_response(
        {"ok": False, "error": message, "message": "Слишком часто. Подожди немного."},
        status=429,
    )


def _run_async_service(func, *args, **kwargs):
    """Run one DB-heavy async service on its own worker-thread event loop."""
    return asyncio.run(func(*args, **kwargs))


async def _threaded_async(func, *args, **kwargs):
    return await asyncio.to_thread(_run_async_service, func, *args, **kwargs)

_ALIAS_ROOTS = {
    "heroes": ROOT / "assets" / "release" / "heroes",
    "pirates": ROOT / "assets" / "release" / "pirates",
    "fireside": ROOT / "assets" / "release" / "fireside",
    "uploads": ROOT / "assets" / "uploads",
}
_IMAGE_KEYS = {"image_path", "icon_path", "logo_path", "team_logo_path"}


def _safe_file(root: Path, relative: str) -> Path | None:
    try:
        root_resolved = root.resolve(strict=True)
        candidate = (root_resolved / relative).resolve(strict=True)
        candidate.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _telegram_user_id_from_init_data(raw: str) -> int | None:
    """Validate Telegram Mini App initData and return the authenticated Telegram id."""
    if not raw:
        return None
    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True))
        received_hash = pairs.pop("hash", "")
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
        secret_key = hmac.new(
            b"WebAppData", settings.bot_token.encode("utf-8"), hashlib.sha256
        ).digest()
        calculated = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            return None
        auth_date = int(pairs.get("auth_date", "0"))
        now = int(time.time())
        age = now - auth_date
        # Telegram initData is short-lived authentication material. Accept up to
        # 24 hours of age and only a small amount of forward clock skew; a client
        # cannot mint a timestamp hours in the future to extend that lifetime.
        if auth_date <= 0 or age > 24 * 60 * 60 or age < -5 * 60:
            return None
        user = json.loads(pairs.get("user", "{}"))
        return int(user["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _request_telegram_id(request: web.Request) -> int | None:
    return _telegram_user_id_from_init_data(
        request.headers.get("X-Telegram-Init-Data", "")
    )


def _public_miniapp_asset(path_value: str | None) -> str | None:
    if not path_value:
        return None
    try:
        raw_text = str(path_value).strip().replace("\\", "/")
        raw_path = Path(raw_text)
        if raw_path.is_absolute():
            try:
                relative = raw_path.resolve(strict=False).relative_to(
                    ROOT.resolve(strict=False)
                )
            except ValueError:
                return None
        else:
            relative = raw_path

        parts = tuple(part for part in relative.parts if part not in {"", "."})
        if ".." in parts:
            return None
        # Production uploads live on the Railway volume at /app/data/uploads,
        # while the HTTP alias is /miniapp/assets/uploads via the existing
        # assets/uploads symlink. Support either form stored in image_path.
        if len(parts) >= 2 and parts[:2] == ("data", "uploads"):
            parts = ("assets", "uploads", *parts[2:])
        if not parts:
            return None
        return "/miniapp/" + "/".join(quote(part, safe="") for part in parts)
    except Exception:
        return None


def _jsonify(value, *, key: str | None = None):
    """Convert project dataclasses/sqlite rows into stable JSON primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        if key in _IMAGE_KEYS and isinstance(value, str):
            return _public_miniapp_asset(value)
        return value
    if isinstance(value, Path):
        return _public_miniapp_asset(str(value)) if key in _IMAGE_KEYS else str(value)
    if isinstance(value, sqlite3.Row):
        return {str(k): _jsonify(value[k], key=str(k)) for k in value.keys()}
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonify(getattr(value, field.name), key=field.name)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(k): _jsonify(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonify(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            str(k): _jsonify(v, key=str(k))
            for k, v in vars(value).items()
            if not str(k).startswith("_")
        }
    return str(value)


def _serialize_balance(balance) -> dict[str, object]:
    return {
        "code": getattr(balance, "code", ""),
        "name": getattr(balance, "name", ""),
        "icon": getattr(balance, "icon", ""),
        "amount": int(getattr(balance, "amount", 0) or 0),
    }


def _serialize_profile(profile) -> dict[str, object]:
    return {
        "id": int(profile.id),
        "telegram_id": int(profile.telegram_id),
        "nickname": profile.nickname,
        "username": profile.username,
        "league": profile.league,
        "rating_points": int(profile.rating_points),
        "wins": int(profile.wins),
        "losses": int(profile.losses),
        "matches_played": int(profile.matches_played),
        "goals_scored": int(profile.goals_scored),
        "goals_allowed": int(profile.goals_allowed),
        "bp_points": int(profile.bp_points),
        "hockey_pass_level": int(profile.hockey_pass_level),
        "premium_pass": bool(profile.premium_pass),
        "hockey_pass_title": profile.hockey_pass_title,
        "hockey_pass_premium_active": bool(profile.hockey_pass_premium_active),
        "team_name": profile.team_name,
        "team_country": profile.team_country,
        "team_logo_path": _public_miniapp_asset(profile.team_logo_path),
        "privacy_public_cards": bool(profile.privacy_public_cards),
        "is_banned": bool(profile.is_banned),
        "is_creator": bool(getattr(profile, "is_creator", False)),
        "balances": [
            _serialize_balance(balance)
            for balance in list(getattr(profile, "balances", []) or [])
        ],
    }


def _serialize_match_info(match_info) -> dict[str, object] | None:
    if match_info is None:
        return None
    return {
        "is_ready": bool(match_info.is_ready),
        "filled_count": int(match_info.filled_count),
        "total_slots": int(match_info.total_slots),
        "lineup_ovr": int(match_info.lineup_ovr)
        if match_info.lineup_ovr is not None
        else None,
        "league": match_info.league,
        "rating_points": int(match_info.rating_points),
        "matches_played": int(match_info.matches_played),
        "wins": int(match_info.wins),
        "losses": int(match_info.losses),
    }


def _card_field(card, name: str, default=None):
    if isinstance(card, sqlite3.Row):
        return card[name] if name in card.keys() else default
    if isinstance(card, dict):
        return card.get(name, default)
    return getattr(card, name, default)


def _serialize_card(card) -> dict[str, object]:
    card_id_value = _card_field(card, "id", None)
    if card_id_value is None:
        card_id_value = _card_field(card, "user_card_id", 0)
    return {
        "id": int(card_id_value or 0),
        "card_id": int(_card_field(card, "card_id", 0) or 0),
        "name": str(_card_field(card, "name", "")),
        "player_key": _card_field(card, "player_key", None),
        "position": str(_card_field(card, "position", "")),
        "overall": int(_card_field(card, "overall", 0) or 0),
        "team": str(_card_field(card, "team", "")),
        "country": str(_card_field(card, "country", "")),
        "collection_name": str(_card_field(card, "collection_name", "")),
        "collection_code": _card_field(card, "collection_code", None),
        "rarity": str(_card_field(card, "rarity", "")),
        "image_path": _public_miniapp_asset(_card_field(card, "image_path", None)),
        "is_in_lineup": bool(_card_field(card, "is_in_lineup", False)),
        "lineup_slot": _card_field(card, "lineup_slot", None),
        "trade_locked": bool(_card_field(card, "trade_locked", False)),
        "salary": int(_card_field(card, "salary", 0) or 0),
        "lock_reason": _card_field(card, "lock_reason", None),
        "lock_until": _card_field(card, "lock_until", None),
        "obtained_from": _card_field(card, "obtained_from", None),
        "created_at": _card_field(card, "created_at", None),
    }


def _serialize_lineup(overview) -> dict[str, object]:
    return {
        "filled_count": int(overview.filled_count),
        "total_slots": int(overview.total_slots),
        "average_overall": int(overview.average_overall)
        if overview.average_overall is not None
        else None,
        "chemistry_bonus": int(overview.chemistry_bonus),
        "final_overall": int(overview.final_overall)
        if overview.final_overall is not None
        else None,
        "is_complete": bool(overview.is_complete),
        "salary_total": int(getattr(overview, "salary_total", 0) or 0),
        "salary_cap": int(getattr(overview, "salary_cap", 0) or 0),
        "slots": {
            slot_code: (_serialize_card(card) if card is not None else None)
            for slot_code, card in overview.slots.items()
        },
    }


def _action_ok(result) -> bool:
    if isinstance(result, tuple) and result:
        return bool(result[0])
    if hasattr(result, "success"):
        return bool(result.success)
    if hasattr(result, "ok"):
        return bool(result.ok)
    return False


def _action_message(result) -> str:
    if isinstance(result, tuple) and len(result) > 1:
        return str(result[1] or "")
    for name in ("message", "description", "title"):
        value = getattr(result, name, None)
        if value:
            return str(value)
    return ""


def _action_response(result, **extra) -> web.Response:
    ok = _action_ok(result)
    payload = {"ok": ok, "message": _action_message(result), "result": _jsonify(result)}
    payload.update(extra)
    return web.json_response(payload, status=200 if ok else 400)


async def _json_body(request: web.Request) -> dict:
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError, TypeError):
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "error": "invalid_json"}),
            content_type="application/json",
        )
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "error": "invalid_json_object"}),
            content_type="application/json",
        )
    return body


def _positive_int(value, *, maximum: int = 2_147_483_647) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 < parsed <= maximum else None


def _nonnegative_int(value, *, maximum: int = 2_147_483_647) -> int | None:
    if value in (None, ""):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= maximum else None


def _id_list(value, *, limit: int = 3) -> list[int] | None:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        return None
    result: list[int] = []
    for item in value:
        parsed = _positive_int(item)
        if parsed is None:
            return None
        if parsed not in result:
            result.append(parsed)
    return result


async def _auth_player(request: web.Request):
    telegram_id = _request_telegram_id(request)
    if telegram_id is None:
        return None, None, web.json_response(
            {"ok": False, "error": "telegram_auth_required"}, status=401
        )
    profile = await _threaded_async(get_player_profile_by_telegram_id, telegram_id)
    if profile is None:
        return telegram_id, None, web.json_response(
            {"ok": False, "error": "profile_not_found"}, status=404
        )
    if bool(getattr(profile, "is_banned", False)):
        return telegram_id, profile, web.json_response(
            {"ok": False, "error": "account_unavailable"}, status=403
        )
    return telegram_id, profile, None


def _load_all_cards(user_id: int) -> list[sqlite3.Row]:
    # The paginated PlayerCardListItem intentionally exposes only list fields.
    # Mini App needs the full owned-copy state (player_key, lineup slot, salary,
    # lock/source metadata) for Mastery, lineup badges and card details, so load
    # that state in one owner-scoped query instead of N per-card profile calls.
    with get_connection() as connection:
        return list(
            connection.execute(
                """
                SELECT
                    user_cards.id AS id,
                    user_cards.card_id,
                    cards.name,
                    cards.player_key,
                    cards.position,
                    cards.overall,
                    cards.team,
                    cards.country,
                    collections.name AS collection_name,
                    collections.code AS collection_code,
                    cards.rarity,
                    cards.image_path,
                    user_cards.is_in_lineup,
                    user_cards.lineup_slot,
                    user_cards.trade_locked,
                    cards.salary,
                    user_cards.lock_reason,
                    user_cards.lock_until,
                    user_cards.obtained_from,
                    user_cards.created_at
                FROM user_cards
                JOIN cards ON cards.id = user_cards.card_id
                JOIN collections ON collections.id = cards.collection_id
                WHERE user_cards.user_id = ?
                ORDER BY cards.overall DESC, user_cards.id DESC
                """,
                (user_id,),
            ).fetchall()
        )


def _load_xfactor_catalog() -> list[dict[str, object]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, code, name, role, description, icon_path, is_mastery, mastery_player_key
            FROM xfactors
            WHERE active = 1
            ORDER BY is_mastery DESC, name COLLATE NOCASE
            """
        ).fetchall()
        has_allowed = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='xfactor_allowed_positions'"
        ).fetchone() is not None
        allowed_by_id: dict[int, list[str]] = {}
        if has_allowed:
            for row in connection.execute(
                "SELECT xfactor_id, position FROM xfactor_allowed_positions ORDER BY xfactor_id, position"
            ).fetchall():
                allowed_by_id.setdefault(int(row["xfactor_id"]), []).append(str(row["position"]))

    result: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["id"] = int(item["id"])
        item["is_mastery"] = bool(item["is_mastery"])
        item["icon_path"] = _public_miniapp_asset(str(item["icon_path"] or ""))
        item["allowed_positions"] = allowed_by_id.get(int(item["id"]), [str(item["role"])])
        result.append(item)
    return result


def _serialize_mastery(progress_items) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for progress in progress_items:
        claimed = {int(value) for value in progress.claimed_points}
        tiers = []
        for tier in mastery_service.MASTERY_TIERS:
            tiers.append(
                {
                    "points": int(tier.points),
                    "reward_type": tier.reward_type,
                    "label": mastery_service.reward_label(progress.player, tier),
                    "claimed": int(tier.points) in claimed,
                    "claimable": int(progress.points) >= int(tier.points)
                    and int(tier.points) not in claimed
                    and tier.reward_type != "future",
                }
            )
        result.append(
            {
                "player": _jsonify(progress.player),
                "points": int(progress.points),
                "claimed_points": sorted(claimed),
                "max_points": int(mastery_service.MASTERY_MAX_POINTS),
                "win_points": int(mastery_service.MASTERY_WIN_POINTS),
                "loss_points": int(mastery_service.MASTERY_LOSS_POINTS),
                "tiers": tiers,
            }
        )
    return result


def _load_state_bundle(user_id: int, telegram_id: int, is_creator: bool) -> dict[str, object]:
    """Load the large Mini App snapshot off the aiohttp event loop.

    Most legacy service functions are async in signature but use synchronous
    sqlite3 internally. Running the complete snapshot on one worker thread keeps
    other buttons/HTTP requests responsive instead of letting one /api/state call
    monopolize the event loop.
    """
    all_cards = _load_all_cards(user_id)
    card_ids = [int(card["id"]) for card in all_cards]
    xfactor_items, _xf_page, _xf_pages, xf_total = xfactors.get_user_xfactor_inventory(
        user_id, page=1, per_page=500
    )
    installed = xfactors.get_installed_xfactor_codes(card_ids)
    mastery = mastery_service.get_user_mastery_overview(user_id)
    pass_status = _serialize_pass_status(release.pass_status(telegram_id))
    boxes = release.get_box_inventory(telegram_id)
    heroes_state = release.hero_paths(telegram_id)
    cursed = release.cursed_state(telegram_id)
    achievements = release.achievement_status(telegram_id)
    fireside_recipes = release.fireside_recipes(telegram_id)
    xfactor_catalog = _load_xfactor_catalog()

    async def load_async_services() -> dict[str, object]:
        daily = await daily_login.get_daily_status(user_id)
        quest_main = await quests.get_quest_main_info(telegram_id)
        quest_daily = await quests.get_user_quests(telegram_id, "daily")
        quest_seasonal = await quests.get_user_quests(telegram_id, "seasonal")
        history = await get_match_history_page(user_id, page=1, per_page=30)
        incoming = await community.get_trade_offers_page(mode="incoming", user_id=user_id, page=1, per_page=25)
        my_trades = await community.get_trade_offers_page(mode="my", user_id=user_id, page=1, per_page=25)
        market = await community.get_trade_offers_page(mode="market", user_id=user_id, page=1, per_page=25)
        players_page = await community.get_players_page(page=1, per_page=25)
        clans_page = await community.get_clans_page(page=1, per_page=25)
        user_clan = await community.get_user_clan(user_id)
        creator_panel = await creators.get_panel(user_id) if is_creator else None
        match_info = await get_match_main_info(telegram_id)
        lineup = await get_lineup_overview(user_id)
        return {
            "daily": daily, "quest_main": quest_main, "quest_daily": quest_daily,
            "quest_seasonal": quest_seasonal, "history": history, "incoming": incoming,
            "my_trades": my_trades, "market": market, "players_page": players_page,
            "clans_page": clans_page, "user_clan": user_clan, "creator_panel": creator_panel,
            "match_info": match_info, "lineup": lineup,
        }

    async_data = asyncio.run(load_async_services())
    return {
        "all_cards": all_cards, "xfactor_items": xfactor_items, "xf_total": xf_total,
        "installed": installed, "mastery": mastery, "pass_status": pass_status,
        "boxes": boxes, "heroes_state": heroes_state, "cursed": cursed,
        "achievements": achievements, "fireside_recipes": fireside_recipes,
        "xfactor_catalog": xfactor_catalog, **async_data,
    }


def _serialize_pass_status(status) -> dict | None:
    if status is None:
        return None
    claims = set(status["claims"] or [])
    rewards = []
    for level in range(1, int(release.PASS_LEVELS) + 1):
        rewards.append(
            {
                "level": level,
                "free_label": release.reward_label(level, "free"),
                "premium_label": release.reward_label(level, "premium"),
                "free_claimed": (level, "free") in claims,
                "premium_claimed": (level, "premium") in claims,
            }
        )
    return {
        "premium": bool(status["premium"]),
        "bp_points": int(status["bp_points"]),
        "level": int(status["level"]),
        "energy": int(status["energy"]),
        "premium_price_energy": int(release.PASS_PREMIUM_PRICE_ENERGY),
        "rewards": rewards,
    }


async def api_account(request: web.Request) -> web.Response:
    telegram_id, _profile, error = await _auth_player(request)
    if error is not None:
        return error
    status = await asyncio.to_thread(release.pass_status, int(telegram_id))
    if status is None:
        return web.json_response({"ok": False, "error": "profile_not_found"}, status=404)
    return web.json_response(
        {
            "ok": True,
            "energy": int(status["energy"]),
            "fireside_premium": bool(status["premium"]),
            "fireside_points": int(status["bp_points"]),
            "fireside_level": int(status["level"]),
        }
    )


async def api_bootstrap(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    match_info = await _threaded_async(get_match_main_info, profile.telegram_id)
    lineup = await _threaded_async(get_lineup_overview, profile.id)
    cards_page = await _threaded_async(get_player_cards_page, profile.id, page=1, per_page=12)
    return web.json_response(
        {
            "ok": True,
            "profile": _serialize_profile(profile),
            "match": _serialize_match_info(match_info),
            "lineup": _serialize_lineup(lineup),
            "collection_preview": [_serialize_card(card) for card in cards_page.cards],
            "collection_pagination": {
                "page": int(cards_page.page),
                "pages_count": int(cards_page.pages_count),
                "total_count": int(cards_page.total_count),
            },
            "lineup_slot_order": list(LINEUP_SLOT_ORDER),
        }
    )


async def api_state(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error

    data = await asyncio.to_thread(
        _load_state_bundle,
        int(profile.id),
        int(telegram_id),
        bool(getattr(profile, "is_creator", False)),
    )
    all_cards = data["all_cards"]
    installed = data["installed"]

    return web.json_response(
        {
            "ok": True,
            "profile": _serialize_profile(profile),
            "match": _serialize_match_info(data["match_info"]),
            "lineup": _serialize_lineup(data["lineup"]),
            "cards": [_serialize_card(card) for card in all_cards],
            "lineup_slot_order": list(LINEUP_SLOT_ORDER),
            "xfactors": {
                "inventory": _jsonify(data["xfactor_items"]),
                "catalog": _jsonify(data["xfactor_catalog"]),
                "installed_by_user_card_id": {str(k): v for k, v in installed.items()},
                "total_types": int(data["xf_total"]),
                "max_per_card": int(xfactors.MAX_XFACTORS_PER_CARD),
                "quicksell_coins": int(xfactors.XFACTOR_QUICKSELL_COINS),
            },
            "mastery": _serialize_mastery(data["mastery"]),
            "fireside_pass": data["pass_status"],
            "energy_packages": [
                {
                    "quantity": int(quantity),
                    "discount_percent": int(discount),
                    "price_rub": int(release.energy_price_rub(quantity)),
                }
                for quantity, discount in release.ENERGY_TIERS
            ],
            "boxes": _jsonify(data["boxes"]),
            "heroes": _jsonify(data["heroes_state"]),
            "cursed_mirror": _jsonify(data["cursed"]),
            "achievements": _jsonify(data["achievements"]),
            "fireside_craft": _jsonify(data["fireside_recipes"]),
            "daily": _jsonify(data["daily"]),
            "quests": {
                "summary": _jsonify(data["quest_main"]),
                "daily": _jsonify(data["quest_daily"]),
                "seasonal": _jsonify(data["quest_seasonal"]),
            },
            "history": _jsonify(data["history"]),
            "trades": {
                "incoming": _jsonify(data["incoming"]),
                "my": _jsonify(data["my_trades"]),
                "market": _jsonify(data["market"]),
            },
            "community": {
                "players": _jsonify(data["players_page"]),
                "clans": _jsonify(data["clans_page"]),
                "my_clan": _jsonify(data["user_clan"]),
            },
            "creator": _jsonify(data["creator_panel"]),
        }
    )


async def api_cards(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    try:
        page = max(1, int(request.query.get("page", "1") or 1))
        per_page = max(1, min(250, int(request.query.get("per_page", "120") or 120)))
    except ValueError:
        return web.json_response({"ok": False, "error": "invalid_pagination"}, status=400)
    search = (request.query.get("search") or "").strip() or None
    position = (request.query.get("position") or "").strip() or None
    rarity = (request.query.get("rarity") or "").strip() or None
    cards_page = await _threaded_async(
        get_player_cards_page,
        profile.id,
        page=page,
        per_page=per_page,
        search=search,
        position=position,
        rarity=rarity,
    )
    return web.json_response(
        {
            "ok": True,
            "cards": [_serialize_card(card) for card in cards_page.cards],
            "page": int(cards_page.page),
            "pages_count": int(cards_page.pages_count),
            "total_count": int(cards_page.total_count),
            "sort_order": cards_page.sort_order,
            "search": cards_page.search,
            "position": cards_page.position,
            "rarity": cards_page.rarity,
        }
    )


async def api_card_details(request: web.Request) -> web.Response:
    telegram_id, _profile, error = await _auth_player(request)
    if error is not None:
        return error
    user_card_id = _positive_int(request.match_info.get("user_card_id"))
    if user_card_id is None:
        return web.json_response({"ok": False, "error": "invalid_card_id"}, status=400)
    card = await _threaded_async(get_player_card_profile, user_card_id, telegram_id=int(telegram_id))
    if card is None:
        return web.json_response({"ok": False, "error": "card_not_found"}, status=404)
    installed = await asyncio.to_thread(xfactors.get_installed_xfactors, user_card_id)
    mastery = await asyncio.to_thread(
        mastery_service.get_mastery_progress_for_user_card, card.user_id, user_card_id
    )
    return web.json_response(
        {
            "ok": True,
            "card": _serialize_card(card),
            "xfactors": _jsonify(installed),
            "mastery": _jsonify(mastery),
        }
    )


async def api_lineup_set(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "lineup")
    if guard is not None:
        return guard
    body = await _json_body(request)
    user_card_id = _positive_int(body.get("user_card_id"))
    slot_code = str(body.get("slot_code") or "").strip().upper()
    if user_card_id is None or not slot_code:
        return web.json_response({"ok": False, "error": "invalid_lineup_request"}, status=400)
    result = await _threaded_async(set_lineup_card, profile.id, slot_code, user_card_id)
    return _action_response(result)


async def api_lineup_remove(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "lineup")
    if guard is not None:
        return guard
    body = await _json_body(request)
    slot_code = str(body.get("slot_code") or "").strip().upper()
    if not slot_code:
        return web.json_response({"ok": False, "error": "invalid_lineup_request"}, status=400)
    return _action_response(await _threaded_async(remove_lineup_slot, profile.id, slot_code))


async def api_lineup_clear(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "lineup")
    if guard is not None:
        return guard
    return _action_response(await _threaded_async(clear_lineup, profile.id))


async def api_lineup_auto(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "lineup")
    if guard is not None:
        return guard
    return _action_response(await _threaded_async(auto_fill_best_lineup, profile.id))


async def api_xfactor_install(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "xfactor")
    if guard is not None:
        return guard
    body = await _json_body(request)
    user_card_id = _positive_int(body.get("user_card_id"))
    code = str(body.get("code") or "").strip()
    replace_slot_raw = body.get("replace_slot")
    replace_slot = None
    if replace_slot_raw is not None:
        replace_slot = _positive_int(replace_slot_raw, maximum=3)
        if replace_slot is None:
            return web.json_response({"ok": False, "error": "invalid_replace_slot"}, status=400)
    if user_card_id is None or not code or len(code) > 128:
        return web.json_response({"ok": False, "error": "invalid_xfactor_request"}, status=400)
    result = await asyncio.to_thread(xfactors.install_xfactor, profile.id, user_card_id, code, replace_slot=replace_slot)
    return _action_response(result)


async def api_xfactor_remove(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "xfactor")
    if guard is not None:
        return guard
    body = await _json_body(request)
    user_card_id = _positive_int(body.get("user_card_id"))
    slot_no = _positive_int(body.get("slot_no"), maximum=3)
    if user_card_id is None or slot_no is None:
        return web.json_response({"ok": False, "error": "invalid_xfactor_request"}, status=400)
    return _action_response(
        await asyncio.to_thread(xfactors.remove_installed_xfactor, profile.id, user_card_id, slot_no)
    )


async def api_mastery_claim(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "mastery")
    if guard is not None:
        return guard
    body = await _json_body(request)
    player_key = str(body.get("player_key") or "").strip()
    tier_points = _positive_int(body.get("tier_points"), maximum=1_000_000)
    if not player_key or tier_points is None:
        return web.json_response({"ok": False, "error": "invalid_mastery_request"}, status=400)
    return _action_response(
        await asyncio.to_thread(mastery_service.claim_mastery_reward, profile.id, player_key, tier_points)
    )


async def api_daily_claim(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "daily_claim")
    if guard is not None:
        return guard
    result, reason = await _threaded_async(daily_login.claim_daily, profile.id)
    if result is None:
        message = "Daily reward already claimed." if reason == "already" else "Daily reward is unavailable."
        return web.json_response(
            {"ok": False, "message": message, "error": reason or "daily_unavailable"},
            status=400,
        )
    return web.json_response({"ok": True, "message": "Daily reward claimed.", "result": _jsonify(result)})


async def api_quest_claim(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "quest_claim")
    if guard is not None:
        return guard
    body = await _json_body(request)
    progress_id = _positive_int(body.get("progress_id"))
    if progress_id is None:
        return web.json_response({"ok": False, "error": "invalid_progress_id"}, status=400)
    return _action_response(await _threaded_async(quests.claim_quest_reward, int(telegram_id), progress_id))


async def api_purchase_fireside_pass(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "pass_purchase")
    if guard is not None:
        return guard
    ok, message = await asyncio.to_thread(release.purchase_fireside_pass, int(telegram_id))
    status = await asyncio.to_thread(release.pass_status, int(telegram_id))
    return web.json_response(
        {
            "ok": ok,
            "message": message,
            "fireside_pass": _serialize_pass_status(status),
        },
        status=200 if ok else 400,
    )


async def api_claim_fireside_pass(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "pass_claim")
    if guard is not None:
        return guard
    body = await _json_body(request)
    level = _positive_int(body.get("level"), maximum=int(release.PASS_LEVELS))
    track = str(body.get("track") or "").strip().lower()
    if level is None or track not in {"free", "premium"}:
        return web.json_response({"ok": False, "error": "invalid_pass_claim"}, status=400)
    ok, message = await asyncio.to_thread(release.claim_pass_reward, int(telegram_id), level, track)
    pass_status = await asyncio.to_thread(release.pass_status, int(telegram_id))
    return web.json_response(
        {"ok": ok, "message": message, "fireside_pass": _serialize_pass_status(pass_status)},
        status=200 if ok else 400,
    )


async def api_box_buy(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "box_buy")
    if guard is not None:
        return guard
    body = await _json_body(request)
    box_code = str(body.get("box_code") or "").strip()
    if not box_code or len(box_code) > 128:
        return web.json_response({"ok": False, "error": "invalid_box_code"}, status=400)
    ok, message = await asyncio.to_thread(release.buy_box, int(telegram_id), box_code)
    boxes = await asyncio.to_thread(release.get_box_inventory, int(telegram_id))
    return web.json_response(
        {"ok": ok, "message": message, "boxes": _jsonify(boxes)},
        status=200 if ok else 400,
    )


async def api_box_open(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "box_open")
    if guard is not None:
        return guard
    body = await _json_body(request)
    box_code = str(body.get("box_code") or "").strip()
    if not box_code or len(box_code) > 128:
        return web.json_response({"ok": False, "error": "invalid_box_code"}, status=400)
    ok, message, rewards = await asyncio.to_thread(release.open_box, int(telegram_id), box_code)
    boxes = await asyncio.to_thread(release.get_box_inventory, int(telegram_id))
    return web.json_response(
        {
            "ok": ok,
            "message": message,
            "rewards": _jsonify(rewards),
            "boxes": _jsonify(boxes),
        },
        status=200 if ok else 400,
    )


async def api_hero_unlock(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "hero_unlock")
    if guard is not None:
        return guard
    body = await _json_body(request)
    hero_key = str(body.get("hero_key") or "").strip()
    if not hero_key or len(hero_key) > 64:
        return web.json_response({"ok": False, "error": "invalid_hero_key"}, status=400)
    ok, message = await asyncio.to_thread(release.unlock_hero, int(telegram_id), hero_key)
    heroes = await asyncio.to_thread(release.hero_paths, int(telegram_id))
    return web.json_response(
        {"ok": ok, "message": message, "heroes": _jsonify(heroes)},
        status=200 if ok else 400,
    )


async def api_hero_claim(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "hero_claim")
    if guard is not None:
        return guard
    body = await _json_body(request)
    hero_key = str(body.get("hero_key") or "").strip()
    if not hero_key or len(hero_key) > 64:
        return web.json_response({"ok": False, "error": "invalid_hero_key"}, status=400)
    ok, message = await asyncio.to_thread(release.claim_hero_100, int(telegram_id), hero_key)
    heroes = await asyncio.to_thread(release.hero_paths, int(telegram_id))
    return web.json_response(
        {"ok": ok, "message": message, "heroes": _jsonify(heroes)},
        status=200 if ok else 400,
    )


async def api_achievement_claim(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "achievement_claim")
    if guard is not None:
        return guard
    body = await _json_body(request)
    code = str(body.get("code") or "").strip()
    if not code or len(code) > 128:
        return web.json_response({"ok": False, "error": "invalid_achievement_code"}, status=400)
    ok, message = await asyncio.to_thread(release.claim_achievement, int(telegram_id), code)
    achievements = await asyncio.to_thread(release.achievement_status, int(telegram_id))
    return web.json_response(
        {"ok": ok, "message": message, "achievements": _jsonify(achievements)},
        status=200 if ok else 400,
    )


async def api_fireside_craft_materials(request: web.Request) -> web.Response:
    telegram_id, _profile, error = await _auth_player(request)
    if error is not None:
        return error
    target_card_id = _positive_int(request.query.get("target_card_id"))
    if target_card_id is None:
        return web.json_response({"ok": False, "error": "invalid_target_card_id"}, status=400)
    materials = await asyncio.to_thread(release.fireside_material_cards, int(telegram_id), target_card_id)
    return web.json_response({"ok": True, "materials": _jsonify(materials)})


async def api_fireside_craft(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "craft")
    if guard is not None:
        return guard
    body = await _json_body(request)
    target_card_id = _positive_int(body.get("target_card_id"))
    material_user_card_id = _positive_int(body.get("material_user_card_id"))
    if target_card_id is None or material_user_card_id is None:
        return web.json_response({"ok": False, "error": "invalid_craft_request"}, status=400)
    ok, message = await asyncio.to_thread(release.craft_fireside, int(telegram_id), target_card_id, material_user_card_id)
    recipes = await asyncio.to_thread(release.fireside_recipes, int(telegram_id))
    return web.json_response(
        {"ok": ok, "message": message, "fireside_craft": _jsonify(recipes)},
        status=200 if ok else 400,
    )


async def api_cursed_play(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    body = await _json_body(request)
    challenge_error = _consume_match_challenge(
        int(profile.id), body.get("challenge_id"), body.get("answer"), "cursed"
    )
    if challenge_error is not None:
        messages = {
            "captcha_missing": "Complete the pre-match check first.",
            "captcha_expired": "The pre-match check expired. Try again.",
            "captcha_invalid": "The pre-match check is invalid. Try again.",
            "captcha_wrong": "Wrong answer. Complete the pre-match check again.",
            "captcha_wrong_mode": "This pre-match check belongs to another mode. Try again.",
        }
        return web.json_response(
            {"ok": False, "error": challenge_error, "message": messages[challenge_error]},
            status=403,
        )
    guard = _guard_response(profile, "cursed_play")
    if guard is not None:
        return guard
    ok, message, result = await _threaded_async(release.play_cursed_match, int(telegram_id))
    cursed_state = await asyncio.to_thread(release.cursed_state, int(telegram_id))
    return web.json_response(
        {"ok": ok, "message": message, "result": _jsonify(result), "cursed_mirror": _jsonify(cursed_state)},
        status=200 if ok else 400,
    )


async def api_cursed_mirror(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "cursed_mirror")
    if guard is not None:
        return guard
    body = await _json_body(request)
    match_id = _positive_int(body.get("match_id"))
    source_card_id = _positive_int(body.get("source_card_id"))
    replace_id = body.get("replace_id")
    if replace_id is not None:
        replace_id = _positive_int(replace_id)
    if match_id is None or source_card_id is None:
        return web.json_response({"ok": False, "error": "invalid_mirror_request"}, status=400)
    if body.get("replace_id") is not None and replace_id is None:
        return web.json_response({"ok": False, "error": "invalid_replace_id"}, status=400)
    if replace_id is None:
        ok, message = await asyncio.to_thread(release.add_mirror_card, int(telegram_id), match_id, source_card_id)
    else:
        ok, message = await asyncio.to_thread(release.add_mirror_card, int(telegram_id), match_id, source_card_id, replace_id)
    return web.json_response(
        {"ok": ok, "message": message, "cursed_mirror": _jsonify(await asyncio.to_thread(release.cursed_state, int(telegram_id)))},
        status=200 if ok else 400,
    )


async def api_cursed_exchange(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "cursed_exchange")
    if guard is not None:
        return guard
    body = await _json_body(request)
    choice = str(body.get("choice") or "").strip().lower()
    player_key = {
        "sakic": "joe sakic",
        "joe_sakic": "joe sakic",
        "lundqvist": "henrik lundqvist",
        "henrik_lundqvist": "henrik lundqvist",
    }.get(choice)
    if player_key is None:
        return web.json_response({"ok": False, "error": "invalid_cursed_choice"}, status=400)
    ok, message = await asyncio.to_thread(release.exchange_cursed_collectibles, int(telegram_id), player_key)
    return web.json_response(
        {"ok": ok, "message": message, "cursed_mirror": _jsonify(await asyncio.to_thread(release.cursed_state, int(telegram_id)))},
        status=200 if ok else 400,
    )


async def api_quick_match(request: web.Request) -> web.Response:
    telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    # Anti-autoclick verification is mandatory and consumed BEFORE any gameplay
    # service is entered. Replays, duplicate POSTs and direct calls without the
    # challenge therefore cannot start a match.
    body = await _json_body(request)
    challenge_error = _consume_match_challenge(
        int(profile.id), body.get("challenge_id"), body.get("answer"), "normal"
    )
    if challenge_error is not None:
        messages = {
            "captcha_missing": "Complete the pre-match check first.",
            "captcha_expired": "The pre-match check expired. Try again.",
            "captcha_invalid": "The pre-match check is invalid. Try again.",
            "captcha_wrong": "Wrong answer. Complete the pre-match check again.",
            "captcha_wrong_mode": "This pre-match check belongs to another mode. Try again.",
        }
        return web.json_response(
            {"ok": False, "error": challenge_error, "message": messages[challenge_error]},
            status=403,
        )
    guard = _guard_response(profile, "quick_match")
    if guard is not None:
        return guard
    result = await _threaded_async(play_quick_match, int(telegram_id))
    return _action_response(result)


async def api_history(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    try:
        page = max(1, int(request.query.get("page", "1") or 1))
        per_page = max(1, min(100, int(request.query.get("per_page", "30") or 30)))
    except ValueError:
        return web.json_response({"ok": False, "error": "invalid_pagination"}, status=400)
    return web.json_response(
        {"ok": True, "history": _jsonify(await _threaded_async(get_match_history_page, profile.id, page=page, per_page=per_page))}
    )


async def api_history_detail(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    match_id = _positive_int(request.match_info.get("match_id"))
    if match_id is None:
        return web.json_response({"ok": False, "error": "invalid_match_id"}, status=400)
    detail = await _threaded_async(get_match_details, profile.id, match_id)
    if detail is None:
        return web.json_response({"ok": False, "error": "match_not_found"}, status=404)
    return web.json_response({"ok": True, "match": _jsonify(detail)})


async def api_trades(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    mode = str(request.query.get("mode") or "market").strip().lower()
    if mode not in {"market", "my", "incoming"}:
        return web.json_response({"ok": False, "error": "invalid_trade_mode"}, status=400)
    try:
        page = max(1, int(request.query.get("page", "1") or 1))
    except ValueError:
        return web.json_response({"ok": False, "error": "invalid_pagination"}, status=400)
    result = await _threaded_async(
        community.get_trade_offers_page, mode=mode, user_id=profile.id, page=page, per_page=25
    )
    return web.json_response({"ok": True, "trades": _jsonify(result)})


async def api_trade_detail(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    offer_id = _positive_int(request.match_info.get("offer_id"))
    if offer_id is None:
        return web.json_response({"ok": False, "error": "invalid_offer_id"}, status=400)
    offer = await _threaded_async(community.get_trade_offer_profile, offer_id)
    if offer is None:
        return web.json_response({"ok": False, "error": "trade_not_found"}, status=404)
    target_id = getattr(offer, "target_user_id", None)
    creator_id = int(getattr(offer, "creator_user_id"))
    if target_id is not None and profile.id not in {creator_id, int(target_id)}:
        return web.json_response({"ok": False, "error": "trade_not_found"}, status=404)
    return web.json_response({"ok": True, "trade": _jsonify(offer)})


async def api_trade_options(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    own_cards = await _threaded_async(
        community.get_available_user_cards_page, user_id=profile.id, page=1, per_page=100
    )
    wanted_cards = await _threaded_async(community.get_card_choices_page, page=1, per_page=100, user_id=profile.id)
    targets = await _threaded_async(
        community.get_direct_trade_players_page, user_id=profile.id, page=1, per_page=100
    )
    return web.json_response(
        {
            "ok": True,
            "offered_cards": _jsonify(own_cards),
            "wanted_cards": _jsonify(wanted_cards),
            "targets": _jsonify(targets),
        }
    )


async def api_trade_create(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "trade_create")
    if guard is not None:
        return guard
    body = await _json_body(request)
    offered_cards = _id_list(body.get("offered_user_card_ids"))
    offered_cosmetics = _id_list(body.get("offered_user_cosmetic_ids"))
    wanted_cards = _id_list(body.get("wanted_card_ids"))
    wanted_cosmetics = _id_list(body.get("wanted_cosmetic_item_ids"))
    if None in (offered_cards, offered_cosmetics, wanted_cards, wanted_cosmetics):
        return web.json_response({"ok": False, "error": "invalid_trade_assets"}, status=400)
    wanted_type = str(body.get("wanted_type") or "cards").strip().lower()
    wanted_asset_type = str(body.get("wanted_asset_type") or "cards").strip().lower()
    if wanted_type not in {"cards", "currency"} or wanted_asset_type not in {"cards", "cosmetics"}:
        return web.json_response({"ok": False, "error": "invalid_trade_type"}, status=400)
    target_user_id = body.get("target_user_id")
    if target_user_id is not None:
        target_user_id = _positive_int(target_user_id)
        if target_user_id is None:
            return web.json_response({"ok": False, "error": "invalid_target_user"}, status=400)
    wanted_amount = _nonnegative_int(body.get("wanted_currency_amount"), maximum=2_147_483_647)
    if wanted_amount is None:
        return web.json_response({"ok": False, "error": "invalid_currency_amount"}, status=400)
    currency_code = str(body.get("wanted_currency_code") or "").strip() or None
    result = await _threaded_async(community.create_trade_offer,
        creator_user_id=profile.id,
        offered_user_card_ids=offered_cards,
        wanted_type=wanted_type,
        wanted_card_ids=wanted_cards,
        wanted_currency_code=currency_code,
        wanted_currency_amount=wanted_amount,
        target_user_id=target_user_id,
        offered_user_cosmetic_ids=offered_cosmetics,
        wanted_cosmetic_item_ids=wanted_cosmetics,
        wanted_asset_type=wanted_asset_type,
    )
    return _action_response(result)


async def api_trade_accept(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "trade_accept")
    if guard is not None:
        return guard
    offer_id = _positive_int(request.match_info.get("offer_id"))
    if offer_id is None:
        return web.json_response({"ok": False, "error": "invalid_offer_id"}, status=400)
    return _action_response(await _threaded_async(community.accept_trade_offer, offer_id, profile.id))


async def api_trade_decline(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "trade_decline")
    if guard is not None:
        return guard
    offer_id = _positive_int(request.match_info.get("offer_id"))
    if offer_id is None:
        return web.json_response({"ok": False, "error": "invalid_offer_id"}, status=400)
    return _action_response(await _threaded_async(community.decline_trade_offer, offer_id, profile.id))


async def api_trade_cancel(request: web.Request) -> web.Response:
    _telegram_id, profile, error = await _auth_player(request)
    if error is not None:
        return error
    guard = _guard_response(profile, "trade_cancel")
    if guard is not None:
        return guard
    offer_id = _positive_int(request.match_info.get("offer_id"))
    if offer_id is None:
        return web.json_response({"ok": False, "error": "invalid_offer_id"}, status=400)
    return _action_response(await _threaded_async(community.cancel_trade_offer, offer_id, user_id=profile.id))


async def healthz(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "nexcore"})


async def root_redirect(_request: web.Request) -> web.Response:
    raise web.HTTPFound("/miniapp/")


async def miniapp_file(request: web.Request) -> web.StreamResponse:
    tail = (request.match_info.get("tail") or "").lstrip("/")
    if not tail:
        tail = "index.html"
    parts = tail.split("/", 2)
    if len(parts) >= 3 and parts[0] == "assets" and parts[1] in _ALIAS_ROOTS:
        candidate = _safe_file(_ALIAS_ROOTS[parts[1]], parts[2])
    else:
        candidate = _safe_file(MINIAPP_ROOT, tail)
        # Backend image_path/icon_path values normally point at the repository's
        # assets tree, while UI-only assets live in nexcore_miniapp/dist/assets.
        # Keep the bundled Mini App asset first; if it does not exist, expose only
        # a safely-resolved file below ROOT/assets. This covers cards, X-Factors,
        # team logos and future art folders without permitting path traversal.
        if candidate is None and len(parts) >= 2 and parts[0] == "assets":
            candidate = _safe_file(ROOT / "assets", "/".join(parts[1:]))

    # Telegram/WebView can reopen a previously cached direct Mini App path after
    # a deploy. For route-like paths (no file extension), serve the SPA shell
    # instead of a hard 404; app.js then normalizes stale hashes/routes to home.
    if candidate is None and "." not in Path(tail).name:
        candidate = _safe_file(MINIAPP_ROOT, "index.html")

    if candidate is None:
        raise web.HTTPNotFound()
    response = web.FileResponse(candidate)
    if candidate.name in {"index.html", "app.js", "style.css", "media.css", "locale.js"}:
        response.headers["Cache-Control"] = "no-cache"
    else:
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response


async def start_miniapp_server() -> web.AppRunner:
    index = MINIAPP_ROOT / "index.html"
    if not index.is_file():
        raise RuntimeError(f"Mini App index is missing: {index}")

    app = web.Application(client_max_size=64 * 1024, middlewares=[_mutation_serialization_middleware])
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/account", api_account)
    app.router.add_get("/api/bootstrap", api_bootstrap)
    app.router.add_get("/api/state", api_state)
    app.router.add_get("/api/cards", api_cards)
    app.router.add_get("/api/cards/{user_card_id}", api_card_details)

    app.router.add_post("/api/lineup/set", api_lineup_set)
    app.router.add_post("/api/lineup/remove", api_lineup_remove)
    app.router.add_post("/api/lineup/clear", api_lineup_clear)
    app.router.add_post("/api/lineup/auto", api_lineup_auto)
    app.router.add_post("/api/xfactors/install", api_xfactor_install)
    app.router.add_post("/api/xfactors/remove", api_xfactor_remove)
    app.router.add_post("/api/mastery/claim", api_mastery_claim)
    app.router.add_post("/api/daily/claim", api_daily_claim)
    app.router.add_post("/api/quests/claim", api_quest_claim)
    app.router.add_post("/api/fireside/pass/purchase", api_purchase_fireside_pass)
    app.router.add_post("/api/fireside/pass/claim", api_claim_fireside_pass)
    app.router.add_post("/api/boxes/buy", api_box_buy)
    app.router.add_post("/api/boxes/open", api_box_open)
    app.router.add_post("/api/heroes/unlock", api_hero_unlock)
    app.router.add_post("/api/heroes/claim", api_hero_claim)
    app.router.add_post("/api/achievements/claim", api_achievement_claim)
    app.router.add_get("/api/fireside/craft/materials", api_fireside_craft_materials)
    app.router.add_post("/api/fireside/craft", api_fireside_craft)
    app.router.add_post("/api/cursed/play", api_cursed_play)
    app.router.add_post("/api/cursed/mirror", api_cursed_mirror)
    app.router.add_post("/api/cursed/exchange", api_cursed_exchange)
    app.router.add_post("/api/matches/challenge", api_match_challenge)
    app.router.add_post("/api/matches/quick", api_quick_match)

    app.router.add_get("/api/history", api_history)
    app.router.add_get("/api/history/{match_id}", api_history_detail)
    app.router.add_get("/api/trades", api_trades)
    app.router.add_get("/api/trades/options", api_trade_options)
    app.router.add_get("/api/trades/{offer_id}", api_trade_detail)
    app.router.add_post("/api/trades", api_trade_create)
    app.router.add_post("/api/trades/{offer_id}/accept", api_trade_accept)
    app.router.add_post("/api/trades/{offer_id}/decline", api_trade_decline)
    app.router.add_post("/api/trades/{offer_id}/cancel", api_trade_cancel)

    app.router.add_get("/", root_redirect)
    app.router.add_get("/miniapp/{tail:.*}", miniapp_file)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=miniapp_port())
    await site.start()
    logger.info("Nexcore Mini App HTTP server started on port %s", miniapp_port())
    return runner
