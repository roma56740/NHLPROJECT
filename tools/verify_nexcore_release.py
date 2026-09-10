from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, token: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    if token not in text:
        raise SystemExit(f"VERIFY FAIL: missing token {token!r} in {path}")


def forbid(path: str, token: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    if token in text:
        raise SystemExit(f"VERIFY FAIL: forbidden token {token!r} in {path}")


def main() -> int:
    required_files = [
        "main.py",
        "railway_boot.py",
        "app/services/backups.py",
        "app/services/release_2026_09.py",
        "app/services/miniapp_server.py",
        "app/services/miniapp_runtime.py",
        "app/middlewares/miniapp_freeze.py",
        "app/middlewares/anti_autoclick.py",
        "app/keyboards/miniapp.py",
        "app/keyboards/main_menu.py",
        "app/handlers/start.py",
        "app/services/admin_wallets.py",
        "nexcore_miniapp/dist/index.html",
        "nexcore_miniapp/dist/app.js",
        "nexcore_miniapp/dist/locale.js",
        "nexcore_miniapp/dist/media.css",
        "nexcore_miniapp/dist/style.css",
        "RESTORE_SEED_SHA256.txt",
        "tools/restore_latest_predeploy.py",
    ]
    for rel in required_files:
        if not (ROOT / rel).is_file():
            raise SystemExit(f"VERIFY FAIL: missing required file {rel}")

    require("app/services/backups.py", "SCHEMA_VERSION = 4")
    require("app/database/db.py", '0012_nexcore_release_2026_09_safe')
    require("app/database/db.py", '0013_nhl_cards_r21_balance_speed')
    require("app/database/db.py", '0012_nexcore_release_2026_09')
    require("app/services/release_2026_09.py", "SAVEPOINT nexcore_release_2026_09_safe")
    require("app/services/release_2026_09.py", '("premium_pass",0.3)')
    require("app/services/release_2026_09.py", "Для покупки напишите @teyld")
    require("app/services/release_2026_09.py", "season_points INTEGER NOT NULL DEFAULT 0")
    require("app/services/release_2026_09.py", "def grant_fireside_pass_points")

    # The destructive preview migration must not exist in the release migration.
    for bad in (
        "UPDATE users SET bp_points=0",
        "DELETE FROM user_card_frames",
        "UPDATE ranked_seasons SET status='ended'",
        "UPDATE packs SET active=0",
        "UPDATE user_items SET quantity=0",
        "code='fortress_token'",
    ):
        forbid("app/services/release_2026_09.py", bad)

    require("app/handlers/__init__.py", "router.include_router(ranked.router)")
    require("app/handlers/__init__.py", "router.include_router(stronghold.router)")
    require("app/handlers/__init__.py", "router.include_router(dna_event.router)")
    require("app/handlers/__init__.py", "router.include_router(packs.router)")
    require("app/handlers/__init__.py", "MiniAppOnlyMiddleware")
    require("main.py", "stronghold_lifecycle_loop")
    require("main.py", "resume_pending_pack_reveals")

    require("app/keyboards/main_menu.py", "⚡ Донат / Energy")
    require("app/keyboards/main_menu.py", "Открыть NHL Cards")
    require("app/texts/admin_wallets.py", "@teyld")
    require("app/services/admin_wallets.py", 'WALLET_CURRENCY_CODES = ("coins", "energy", "rank_point")')

    require("nexcore_miniapp/dist/app.js", "https://t.me/teyld")
    require("nexcore_miniapp/dist/app.js", "syncPaidAccount")
    require("nexcore_miniapp/dist/app.js", "/api/account")
    require("nexcore_miniapp/dist/app.js", "/api/fireside/pass/purchase")
    forbid("nexcore_miniapp/dist/app.js", "state.energy+=n")
    forbid("nexcore_miniapp/dist/app.js", "energy:savedSession.energy??1000")
    require("nexcore_miniapp/dist/index.html", "telegram-web-app.js")
    require("nexcore_miniapp/dist/index.html", "locale.js?v=r21")
    require("nexcore_miniapp/dist/app.js", "MATCH_REPLAY_DURATION_MS=30000")
    require("nexcore_miniapp/dist/app.js", "fireside-pass-caufield.png")
    require("app/services/miniapp_server.py", "_mutation_serialization_middleware")
    require("app/services/miniapp_server.py", "/api/matches/challenge")
    require("app/services/miniapp_server.py", "_consume_match_challenge")
    require("nexcore_miniapp/dist/app.js", "live-match-captcha/")
    require("nexcore_miniapp/dist/app.js", "MATCH_REPLAY_DURATION_MS=30000")
    forbid("nexcore_miniapp/dist/app.js", "Page not found")

    require("app/services/miniapp_server.py", "X-Telegram-Init-Data")
    require("app/services/miniapp_server.py", "hmac.compare_digest")
    require("app/services/miniapp_server.py", "/api/account")
    require("app/services/miniapp_server.py", "/api/fireside/pass/purchase")

    require("app/services/cache_cleanup.py", "/app/cache/render_cache")
    forbid("app/services/renders.py", "/app/data/render_cache")
    require("railway_boot.py", "FATAL PREDEPLOY GUARD")
    require("railway_boot.py", "REQUIRE_PREDEPLOY_BACKUP")

    if (ROOT / "assets" / "uploads").exists():
        raise SystemExit("VERIFY FAIL: assets/uploads must not be shipped")

    forbidden = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if path.name == ".env" or path.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".pyc"}:
            forbidden.append(rel)
        if path.name.endswith(("-wal", "-shm")) or "__pycache__" in path.parts:
            forbidden.append(rel)
    if forbidden:
        raise SystemExit("VERIFY FAIL: forbidden runtime files: " + ", ".join(forbidden[:20]))

    py_files = list(ROOT.rglob("*.py"))
    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    print(f"VERIFY OK: {len(py_files)} Python files parsed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
