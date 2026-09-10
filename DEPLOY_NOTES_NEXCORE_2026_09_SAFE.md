# Nexcore September 2026 — safe production deploy

This build is based on the current R15 production baseline and overlays the September Nexcore release without deleting legacy bot systems.

## Database safety

- `SCHEMA_VERSION = 4`, so `railway_boot.py` creates and verifies a predeploy backup before the schema-changing release starts.
- Release migration name: `0012_nexcore_release_2026_09_safe`.
- The migration is additive for the new Nexcore systems. It does **not** reset `users.bp_points`, `premium_pass`, old Hockey Pass progress, DNA balances, Ranked seasons, Stronghold state, legacy Packs, card-frame bindings, or Fortress Tokens.
- Legacy bot systems remain in source and database. Ordinary Telegram users are routed to the Mini App by middleware; administrators bypass the freeze and retain the full bot/admin interface.
- Fireside Pass uses its own `fireside_pass_users.season_points` / `season_level` state instead of overwriting the legacy Hockey Pass progress.

## Mini App

The bot hosts the Mini App at `/miniapp/` on Railway's `$PORT`. If the service has a Railway public domain, the bot can derive its URL from `RAILWAY_PUBLIC_DOMAIN`. You can override it with `MINIAPP_URL`.

For rollout safety, MiniApp-only mode is **off by default**. First deploy, generate/check the Railway public domain and open `/miniapp/`. Then set `MINIAPP_ONLY_MODE=1`; ordinary users receive only the **Open Nexcore** entry screen in Telegram, while administrators bypass the freeze and keep the full admin/legacy interface. `MINIAPP_ONLY_MODE=0` is an immediate kill-switch that restores the old Telegram player UI without changing the database or code. `MINIAPP_URL` can override the generated Railway URL.

Important: the supplied Mini App remains a frontend-first build; many gameplay screens still use local prototype state rather than the production database. The freeze toggle therefore exists so production can stay on the old Telegram gameplay until the Mini App API is fully wired, while the storefront and design are hosted for payment-provider review.

## Store before payment-provider integration

Energy Store is a concrete storefront with fixed Energy packages and RUB prices. Automated payment/crediting is disabled for users. Purchase buttons send the user to `@teyld`. The Mini App never credits Energy itself; after payment an administrator credits the real production balance, and the Mini App refreshes that balance from the authenticated backend.

Administrators can manually credit paid Energy through:

`Admin → ⚡ Донат / Energy → player → Energy → Начислить`

The intentional `0.3%` Premium Pass drop from Dead Man's Chest remains enabled in backend event logic.

## Rollback

1. Code rollback: redeploy/revert to GitHub commit `9ba868c48d646983de79acc71e361f4dfa38f44e` (R15). Do not force-push.
2. Because this release migration is additive, a code rollback normally does not require restoring the DB.
3. If the DB itself becomes damaged, the predeploy copy is under `/app/data/predeploy_backups/`. With the normal bot process stopped, run `python tools/restore_latest_predeploy.py` first for a dry run, then `python tools/restore_latest_predeploy.py --confirm RESTORE` to restore. The tool creates another emergency copy before replacement and verifies `PRAGMA quick_check`.
