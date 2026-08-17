# V10.2 — Global Tradable Cosmetics and Universal Card Sorting (2026-07-31)

## Global cosmetics

- Cosmetics are no longer treated as Ranked-only or CLAN WAR-only items. The existing
  catalog and inventory tables are reused globally for every game mode.
- Every owned cosmetic is a concrete inventory copy. Two identical frames owned by one
  player are two separate tradable/equippable instances.
- A card frame copy binds to exactly one concrete `user_cards` instance. It cannot be
  silently moved to another card; the player must remove it first or use a second copy.
- Bound frames and equipped backgrounds/prefixes/titles cannot be placed into an open
  trade until explicitly removed.
- Added one global player screen: **Cosmetics**. Frames are assigned to a card there;
  backgrounds, nickname suffixes and titles are equipped globally.
- Added one global admin screen: **Manage cosmetics**. Ranked and CLAN WAR admin menus
  now link to the same catalog instead of implying separate inventories.
- Per-card frame overlays now render in collection views, card profiles, normal-match
  lineups, Ranked lineups and CLAN WAR lineups.
- The equipped paid nickname suffix is appended after the player nickname when lineups
  are announced before matches.

## Black Market and player trades

- Black Market admin creation now supports card frames, profile/lineup backgrounds and
  nickname suffixes using the global cosmetic catalog.
- Player trade offers can contain concrete cosmetic copies and can request either cards,
  cosmetics or currency. Cosmetic transfer is transactional and idempotent together with
  the existing card/currency transfer.
- Trade validation rejects equipped, card-bound, locked or already-listed cosmetic copies.
- Existing card-for-card and card-for-currency exchanges remain compatible.

## Universal card sorting

- Added a persisted per-user card sort preference: highest-to-lowest OVR or
  lowest-to-highest OVR.
- Sorting is available in the user collection, lineup slot picker, trade card pickers and
  the frame-to-card assignment picker.
- The preference is shared across these screens, so the selected order remains consistent.

## Database and safety

- Added additive, idempotent tables for offered/requested cosmetic copies and card-view
  preferences.
- Added `trade_locked` to owned cosmetics and `wanted_asset_type` to trade offers through
  guarded migrations. Existing rows and user data are preserved.
- Added regression tests for one-frame-copy/one-card semantics, cosmetic-only trades,
  bound-cosmetic trade rejection and both OVR sort orders.
- Fresh database initialization, V10.1-to-V10.2 migration, repeat migration, concrete-copy
  cosmetic trades, legacy card trades and cosmetic-for-currency trades were manually
  exercised successfully in the packaging environment.
- Python compile/AST validation passes. The complete pytest suite could not be executed in
  the packaging environment because `aiogram==3.28.2` was unavailable from its offline
  package index.

---

# V10.1 — Navigation and Admin Quick Access (2026-07-31)

## User menu

- Replaced the long 10-row reply keyboard with a compact goal-based first level:
  **Play / Team / Packs / My Progress / Shop / Community / Profile / Help**.
- Added second-level menus for game modes, team management, progress/rewards, and community.
- Added a short **How to play** onboarding screen with a three-step start path.
- Added a direct text entry point for **CLAN WAR 2.0**.
- Updated `/start` and Home copy so the next action is obvious based on lineup readiness.

## Admin menu

- Replaced the scrolling admin keyboard with five logical sections:
  **Content / Modes / Players / Economy / System**.
- Added direct quick-access buttons and handlers for:
  - Ranked admin;
  - Ranked bot diagnostics;
  - Stronghold tower schedule;
  - Clan War 2.0 admin;
  - maintenance mode;
  - active match locks;
  - pack opening videos.
- Added a dedicated pack-video overview listing every pack and its animation status.
- Expanded the inline Admin Panel with direct links to Ranked, Stronghold, Clan War,
  pack videos, tower schedule, maintenance, and active match locks.
- Added permission mappings for every new administrative entry point.

## Safety and compatibility

- Existing feature handlers and callback data were reused; no duplicate game systems
  or database tables were created.
- No database migration is required for this patch.
- Added `tests/test_navigation_menus.py` for menu structure and permission regression.
- Python syntax/AST validation passes for all project modules. The full pytest suite
  could not be executed in the packaging environment because `aiogram==3.28.2` was
  unavailable there; Railway installs it from `requirements.txt`.

---

# PATCH NOTES — Captain System, Ranked Bots, Stronghold Global Schedule, Pack Video Animation, Maintenance Mode, Global Match Lock

This document now covers two work sessions on 2026-07-30. **Part 1** (below) is the
original five-system implementation plus its Black Market/test-suite follow-up pass.
**Part 2** (further down, its own numbering) adds a unified, database-enforced,
cross-mode match lock — see the table of contents there. All work was implemented
directly in the existing NHL Cards bot codebase (no parallel/duplicate systems), with
real migrations, tests, and admin panels. No deployment or git push was performed at
any point in either session.

---

# PART 1 — Captain System, Ranked Bots, Stronghold Global Schedule, Pack Video Animation, Maintenance Mode

Session date: 2026-07-30 (updated same day — follow-up pass). All five requested
systems were implemented directly in the existing NHL Cards bot codebase (no
parallel/duplicate systems), with real migrations, tests, and admin panels. No
deployment or git push was performed.

**Follow-up pass (this update):** fixed all 12 previously-failing Black Market tests
(root cause: hardcoded past calendar dates, not a bug in the shipped feature code),
brought the full suite to 0 failed, and added 10 new targeted tests explicitly
covering: the 10s video-duration rejection, admin video upload/replace/delete/view,
the same-message `edit_message_media` swap after the 10s delay, no-duplicate-reward
on `edit_message_media` failure, captain auto-clear cascading into the UI text,
the exact captain/division/progress/bonus/cap UI strings, maintenance blocking of
stale/old inline buttons and `/`-commands, and admin access via `CallbackQuery`
(not just `Message`). See §18–19 for exact counts and §21 for the new test list.

## 1. What was found in the existing architecture

- **Cards / user cards / lineup**: `cards` catalog table has no `division` column — a
  card's division is resolved via `cards.team -> team_division_teams -> team_divisions`
  (`app/services/admin_divisions.py:get_division_for_team`). There is **no separate
  ranked-lineup table** — Ranked Mode reuses the same `user_cards.is_in_lineup /
  lineup_slot` state as the normal lineup (`app/services/lineup.py`).
- **Salary cap**: `app/services/salary.py` stores everything in *thousands of USD*
  (`54000` = $54,000,000). `RANKED_SALARY_CAP = 54000` was a flat constant used directly
  in `ranked_core.play_ranked_match`.
- **Ranked bots**: bot strength was `compute_bot_opponent_ovr(user_ovr)`
  (`app/services/matches.py`) — a handicap subtracted from the **player's own** lineup
  OVR. Bot opponents had **no real cards at all** — only a scalar OVR — and were
  rendered via a synthetic placeholder object (`render_opponent_lineup_placeholder`).
  Bot nicknames came from a shared 8-item list of hockey-team names (`BOT_NAMES`), not
  a per-player nickname list.
- **The Stronghold "towers"**: called **Fortress** in code (`stronghold_fortresses`,
  15 rows). Unlocking was **100% personal-progress-based** — fortress N+1 unlocked only
  when fortress N's `stronghold_user_fortress_progress.status = 'COMPLETED'`. No
  date/schedule concept existed anywhere. Collection matching for "The Stronghold" was
  **already correct** (matched by normalized `collections.code = 'the_stronghold'` +
  name/OVR, not hardcoded IDs) — no change needed there.
- **Pack opening**: the codebase already had ~90% of the requested video-opening
  design built (`app/services/packs.py:open_user_pack`, `app/handlers/packs.py:
  show_pack_opening_result`) — atomic reward determination, one admin-uploaded video,
  `edit_message_media` swap to the revealed card, `TelegramBadRequest` fallback to a
  new message. Missing: crash-safe "pending reveal" persistence, idempotency
  request_id, video enable/disable toggle, duration/size/uploader metadata, and dead
  legacy multi-step "division/team/country" reveal text builders still in the codebase.
- **Maintenance mode**: already existed, but folded into `BannedPlayerMiddleware`
  (`app/middlewares/banned.py`) alongside per-user bans and the subscription gate — no
  configurable text/photo, no per-user cooldown, no audit log, and it ran *after* other
  checks rather than being the earliest gate.

## 2. Old mechanics that were changed

- **Ranked bot strength** no longer depends on the user's lineup OVR/salary at all —
  it is derived solely from the user's Ranked League (NCAA/AHL/NHL/OLYMPICS).
  `matches.compute_bot_opponent_ovr` itself is untouched and still used by normal-mode
  quick match / CLAN WAR 2.0 (out of scope) — Ranked simply stopped calling it.
- **Stronghold fortress unlocking** changed from "must complete the previous fortress"
  to "unlocked by the global date-based schedule", per the explicit requirement that
  unlocking must not depend on personal progress. Two pre-existing tests that encoded
  the old sequential-completion behavior were updated to test the new schedule-based
  behavior instead (see Testing section).
- **Maintenance mode enforcement** moved out of `BannedPlayerMiddleware` into a new,
  earlier-registered `MaintenanceModeMiddleware`. The old inline maintenance branch in
  `banned.py` was removed (dead code — the new middleware already blocks the Update
  before `banned.py` ever runs for a non-admin during maintenance).
- **Pack opening legacy dead code removed**: `build_pack_animation_division_text`,
  `build_pack_animation_team_text`, `build_pack_animation_country_text` in
  `app/texts/packs.py` (unused multi-step division/team/country reveal texts).

## 3. Files changed

**New files:**
- `app/services/ranked_captain.py` — captain assignment/validation/bonus computation
- `app/services/ranked_bot.py` — league-based bot lineup builder (real catalog cards)
- `app/services/ranked_bot_names.py` — fixed 100-nickname loader/cache/fallback
- `data/ranked_bot_nicknames.txt` — the 100 nicknames (verbatim, as provided)
- `app/services/stronghold_schedule.py` — global tower unlock schedule
- `app/services/pack_reveal_recovery.py` — crash-safe pending-reveal boot recovery
- `app/services/maintenance.py` — maintenance-mode state/service (game_settings-backed)
- `app/middlewares/maintenance.py` — `MaintenanceModeMiddleware`
- `app/handlers/admin_maintenance.py` — admin panel for maintenance mode
- `tests/test_ranked_captain.py`, `tests/test_ranked_bots.py`,
  `tests/test_ranked_bot_names.py`, `tests/test_stronghold_schedule.py`,
  `tests/test_packs.py`, `tests/test_maintenance.py`

**Modified files:**
- `app/database/schema.py` — `ranked_captains`, `pack_pending_reveals` tables;
  9 new `maintenance_*` keys in `DEFAULT_GAME_SETTINGS`
- `app/database/db.py` — additive `ensure_column()` calls for `stronghold_events`,
  `packs` (all idempotent, `IF NOT EXISTS`/`PRAGMA table_info` guarded)
- `app/services/salary.py` — `RANKED_CAPTAIN_BONUS`, `RANKED_CAPTAIN_MIN_DIVISION_CARDS`,
  `format_salary_full()`
- `app/services/ranked_core.py` — captain bonus wired into salary-cap check; bot
  opponent generation replaced with league-based real-card bots + fixed nicknames
- `app/handlers/ranked.py` — captain management screens; opponent lineup rendering
- `app/handlers/admin_ranked.py` — bot/nickname diagnostics screen
- `app/services/stronghold_fortress.py` — fortress-level gate switched from
  sequential-progress to global schedule (`app.services.stronghold_schedule`)
- `app/handlers/stronghold.py`, `app/keyboards/stronghold.py` — locked-tower
  messaging (unlock date/time/remaining), "all available towers cleared" screen
- `app/handlers/admin_stronghold.py` — "🕐 Расписание башен" admin section
- `app/services/packs.py` — pending-reveal lifecycle, animation metadata
  (file_id/file_unique_id/duration/size/uploader/enabled toggle)
- `app/handlers/packs.py`, `app/keyboards/packs.py`, `app/texts/packs.py` — pending
  reveal wiring, animation view/toggle/remove admin actions, legacy text removal
- `main.py` — calls `resume_pending_pack_reveals()` at boot (before polling starts)
- `app/middlewares/banned.py` — old inline maintenance branch removed
- `app/handlers/__init__.py` — `MaintenanceModeMiddleware` registered first;
  `admin_maintenance` router included
- `app/handlers/admin_settings.py`, `app/keyboards/admin_settings.py` — quick
  maintenance toggle now routes through `app.services.maintenance`; link to new panel
- `app/services/admin_permissions.py` — `admin_maintenance:` permission prefix
- `tests/test_stronghold_fortress.py` — 2 tests updated for schedule-based unlocking
- `tests/test_stronghold_endless.py` — test helper updated to unlock all 15 towers
  (that test suite validates Endless Siege, not the schedule feature itself); plus
  (follow-up pass) `test_endless_weekly_ft_cap_stops_new_ft` hardened against the match
  engine's own randomness (see §18)

**Follow-up pass — additional files:**
- `tests/conftest.py` — added `business_date_today()`/`business_date_offset(days)`
  relative-date helpers (§18)
- `tests/test_black_market_store.py`, `tests/test_black_market_admin.py`,
  `tests/test_black_market_audit_fixes.py`, `tests/test_black_market_handlers_smoke.py`,
  `tests/test_black_market_generation.py` — all 43 hardcoded `"2026-07-29"`/
  `"2026-07-30"` date literals replaced with the relative helpers above
- `tests/test_packs.py` — 3 new handler-level tests (admin video view, same-message
  edit_media swap, edit_media-failure fallback without duplicate reward)
- `tests/test_ranked_captain.py` — 4 new tests (exact UI text for captain/division/
  progress/bonus/cap in 3 states, end-to-end auto-clear-updates-UI scenario)
- `tests/test_maintenance.py` — 3 new tests (stale/old inline buttons blocked, admin
  access via `CallbackQuery`, explicit `/start` command block)

## 4. New captain system

- **Storage**: `ranked_captains(user_id UNIQUE, user_card_id UNIQUE, created_at,
  updated_at)` — a minimal pointer table. Division, card name, OVR are **not**
  duplicated; they're resolved fresh from the card + `team_divisions` every time.
- **Assignment**: `ranked_captain.assign_captain(user_id, user_card_id)` re-validates
  ownership and lineup membership via `get_lineup_overview(user_id)` — a forged/foreign/
  removed/nonexistent `user_card_id` simply isn't found and is rejected. Only one
  captain per user (`UNIQUE user_id`), upserted on change.
- **Auto-clear**: `get_captain_status()` detects when the captain's card is no longer
  in the active lineup and deletes the row automatically, every time it's called
  (screen view, before-match check, etc. — no caching, always fresh).
- **UI**: "🎖 Капитан состава" screen off the Ranked Mode main menu — assign, change,
  remove, with a status block matching the spec's exact wording, plus the same block
  inline on the Ranked Mode home screen.

## 5. Captain bonus calculation

```
effective_ranked_salary_cap = RANKED_SALARY_CAP (54000, i.e. $54M)
                               + captain_bonus

captain_bonus = 20000 ($20M)  if captain assigned AND >=5 lineup cards
                                (including the captain) share the captain's division
              = 0              otherwise
```
Recomputed from scratch (no cache) on: screen view, captain assign/change/remove, and
immediately before every `play_ranked_match()` call. Division membership is resolved
per-card via `team_divisions`/`team_division_teams`, so an admin changing a team's
division is reflected on the very next calculation.

## 6. Ranked-lineup validation

`play_ranked_match()` now computes the captain status fresh, compares
`overview.salary_total` against the **effective** cap (base + bonus), and if exceeded
raises `SALARY_CAP_EXCEEDED` with the effective cap, base cap, bonus amount, current
salary, and overage spelled out — without touching the lineup or captain assignment.
The lineup is never auto-modified; the player must fix the roster or captain
themselves. Bonus logic lives only in `ranked_captain.py`/`ranked_core.py` — Stronghold,
Clan War 2.0, and normal-mode matches never import it (verified by a static test).

## 7. Real-card bot selection (Ranked leagues)

`ranked_bot.build_bot_lineup(league)` picks a `target_ovr` uniformly at random inside
the league's range, then for each of the 6 lineup slots queries the **real** `cards`
catalog (`active=1 AND position=? AND overall BETWEEN target±window`), starting with
`window=0` (exact target) and widening by 1 until a real, unused (`player_key`) card is
found — never inventing cards. `average_overall = round(mean(card.overall))` — Python's
`round()` (round-half-to-even), identical to the rule `get_lineup_overview()` already
uses for user lineups, applied consistently in both code and tests. If the catalog is
too sparse for a slot even after wide expansion, that slot is logged as a warning and
left empty rather than fabricated. Bots render through the same `render_lineup_image()`
used for real players.

## 8. Ranked league OVR ranges (inclusive)

| League | OVR range |
|---|---|
| NCAA | 70–80 |
| AHL | 80–90 |
| NHL | 90–95 |
| OLYMPICS | 95–99 |

## 9. Bot nickname file

`data/ranked_bot_nicknames.txt` — 100 nicknames, one per line, exact spelling/casing as
provided. Loaded once and cached (`app/services/ranked_bot_names.py`); an embedded copy
of the same list is used if the file is missing/corrupted (with an error logged, never
a "Bot123"-style fallback).

## 10. Old nickname generator — confirmed removed for Ranked

`ranked_core.find_ranked_opponent()`'s bot branch no longer calls `random.choice(BOT_NAMES)`
— it calls `ranked_bot_names.pick_nickname()`. `BOT_NAMES` itself (the old 8-item
hockey-team-name list) is untouched and still used by normal-mode quick match and CLAN
WAR 2.0, which were explicitly out of scope for this change.

## 11. Global Stronghold tower schedule

```
tower_unlock_at(N) = schedule_start_at + (N - 1) * unlock_interval
```
`schedule_start_at` = `stronghold_events.fortress_unlock_started_at`, falling back to
the existing `stronghold_events.starts_at` if an admin hasn't set an explicit override
— this fallback is computed **live on every call** (not a one-time backfill), so a
season that's already partway through automatically shows the correct number of
already-open towers with no migration step. `unlock_interval` defaults to 1 day
(`fortress_unlock_interval_seconds = 86400`), configurable per event. A tower's
playability now depends **only** on this formula — not on whether earlier towers were
completed — matching the requirement that unlocking not depend on personal progress.
Manual admin unlocks are stored as a single monotonic
`stronghold_events.manual_unlock_override_count` (never re-locks anything), combined
via `max()` with the time-based count.

## 12. Stronghold admin panel

New "🕐 Расписание башен" section under the existing THE STRONGHOLD admin dashboard:
status (unlocked count, last unlocked tower, next unlock date), edit season-start
date/timezone/interval, unlock the next tower or a specific tower number (confirmation
+ audit log via the existing `stronghold_audit_log` table), and view manual-unlock
history.

## 13. New pack opening animation

Sequence (already mostly correct, hardened this session): callback → `open_user_pack()`
atomically reserves the pack, rolls the reward, grants it, and — in the **same
transaction** — inserts a `pack_pending_reveals` row (`status='pending'`, reward
snapshot, `request_id = 'pack-open-{opening_id}'`) → `bot.send_video()` → row's
`chat_id`/`message_id` attached → 10s wait → `Message.edit_media()` swaps the video for
`render_card_profile_image()`'s output of the *already-decided* card → row marked
`completed`. `TelegramBadRequest` on `edit_media` falls back to delete+send a new
message (unchanged existing behavior), and any other exception marks the reveal
`failed` with the error text. A pack with no video, or with `animation_enabled=0`,
skips straight to the fallback path.

## 14. Pending-reveal recovery

`app/services/pack_reveal_recovery.py:resume_pending_pack_reveals(bot)` runs once at
boot (`main.py`, before `bot.delete_webhook`/polling starts). It scans
`pack_pending_reveals WHERE status='pending'` — which can only be non-empty if the
process died between the reward being committed and the reveal being marked complete —
and for each row sends the already-decided reward as a **new** message (not attempting
to resume the original video message, since its Telegram-side state after a restart is
unknowable) to the user's chat (`chat_id` if captured, else derived from
`users.telegram_id`), then marks it `completed`. No reward is ever re-rolled or
re-granted — it was already fixed atomically in `open_user_pack()`.

## 15. Maintenance-mode middleware

`app/middlewares/maintenance.py:MaintenanceModeMiddleware` is registered **first** in
`app/handlers/__init__.py::setup_routers()` — before `BannedPlayerMiddleware`,
`AdminPermissionMiddleware`, `LastActiveMiddleware`. For each `Message`/`CallbackQuery`/
`InlineQuery`: admins (`app.utils.users.is_admin`, the existing admin system) pass
straight through; everyone else is blocked (`return None`, so the Update never reaches
any handler/FSM) if maintenance mode is on. `CallbackQuery.answer()` is always called
first (before the cooldown check) so buttons never show an infinite spinner. A 3-second
per-user in-memory cooldown throttles only the *notice message* — the Update itself is
unconditionally blocked regardless of cooldown state.

## 16. Admin instructions — configuring text and photo

1. Admin panel → ⚙️ Настройки → "🛠 Технический перерыв (текст/фото/история)" (or the
   quick toggle right there for on/off only).
2. "✏️ Изменить текст" → send the new message text as a plain message. Applied
   immediately (cache is invalidated on every write).
3. "🖼 Загрузить/заменить фото" → send a photo. Its `file_id`/`file_unique_id` are
   stored in `game_settings` (not just a temp path) and reused going forward.
4. "🗑 Удалить фото" removes the photo only; text-only mode falls back automatically.
5. "👁 Предпросмотр" sends you exactly what a blocked user would see right now.
6. "🟢 Начать технический перерыв" / "🔴 Завершить перерыв" both require an explicit
   confirmation tap before taking effect, and are logged to `audit_log`
   (`maintenance_enable`/`maintenance_disable`/`maintenance_text_update`/
   `maintenance_photo_update`/`maintenance_photo_remove`), viewable via
   "📜 История изменений".
7. If neither text nor photo is ever configured, blocked users see the default:
   *"Бот временно недоступен из-за технических работ. Пожалуйста, попробуйте позже."*

## 17. Migrations and indexes

All additive, `IF NOT EXISTS` / `PRAGMA table_info()`-guarded, safe to run repeatedly
and against an existing populated Railway database — no `DROP`, no destructive
`ALTER`, no data deleted:

- `ranked_captains` — new table (`SCHEMA_QUERIES`, `CREATE TABLE IF NOT EXISTS`),
  `UNIQUE(user_id)`, `UNIQUE(user_card_id)` (both auto-indexed by SQLite), FKs to
  `users`/`user_cards` with `ON DELETE CASCADE`.
- `pack_pending_reveals` — new table, `UNIQUE(opening_id)`, `UNIQUE(request_id)`,
  `idx_pack_pending_reveals_status` index, FKs to `pack_openings`/`users`/`packs`.
- `stronghold_events` — 4 new nullable/defaulted columns via `ensure_column()`
  (`fortress_unlock_started_at`, `fortress_unlock_interval_seconds` default 86400,
  `fortress_unlock_timezone` default `'UTC'`, `manual_unlock_override_count` default 0).
- `packs` — 7 new columns via `ensure_column()` (`animation_enabled` default 1,
  `animation_duration_seconds`, `animation_file_size`, `animation_uploaded_at`,
  `animation_uploaded_by`, `animation_file_id`, `animation_file_unique_id`).
- `game_settings` — 9 new `maintenance_*` keys seeded via the existing
  `ON CONFLICT DO UPDATE title/description` upsert (never overwrites an existing
  `value`, so a pre-existing `maintenance_mode` flag on Railway is preserved as-is).

## 18. pytest result — FOLLOW-UP: all 12 Black Market failures fixed, 0 failed

**Root cause (not a feature bug):** 5 Black Market test files hardcoded
`business_date_value="2026-07-29"` while `purchase()`/`list_storefront()` compare
against `app.services.black_market_common.business_date()`, which reads the real wall
clock. Once the real date passed 2026-07-29, every one of those call sites diverged
from "today" and every test that called `purchase()` after generating a rotation hit
`ROTATION_EXPIRED` before reaching its actual assertion.

**Fix — relative date computation, no frozen-time dependency added:** two helpers were
added to `tests/conftest.py`:

```python
def business_date_today() -> str:
    from app.services.black_market_common import business_date
    return business_date()

def business_date_offset(days: int) -> str:
    from datetime import datetime, timedelta, timezone
    from app.services.black_market_common import business_date
    return business_date(datetime.now(timezone.utc) + timedelta(days=days))
```

Every hardcoded date literal across `test_black_market_store.py`,
`test_black_market_admin.py`, `test_black_market_audit_fixes.py`,
`test_black_market_handlers_smoke.py`, and `test_black_market_generation.py` (43 call
sites total) was replaced with `business_date_today()` (single-day cases) or
`business_date_today()` / `business_date_offset(1)` as a `TODAY`/`TOMORROW` pair (the
two tests that specifically need two distinct calendar days —
`test_seed_digest_differs_per_business_date`,
`test_same_user_different_business_date_gets_new_rotation`). This uses the exact same
function production code uses (`business_date()`'s own docstring already documented it
as designed for this), so the tests stay correct on any calendar day the suite is run,
indefinitely — not just patched for today. `freezegun`/`time-machine` were deliberately
**not** added as a new dependency: global datetime freezing in a shared-process test
suite risks side effects on unrelated time-based logic (audit log timestamps, match
locks, Stronghold schedule tests, etc.) for no benefit over the simpler relative-date
fix that was already the designed extension point.

**Second pre-existing failure found and fixed while chasing "0 failed":**
`test_endless_weekly_ft_cap_stops_new_ft` (Stronghold Endless Siege) turned up as a
genuine — if rare — flake in a full-suite run. Root cause: `app.services.matches.
simulate_period()`'s per-shot goal chance is clamped to a `4–13%` band regardless of
how lopsided the OVR gap is (`clamp(7 + (ovr_diff), 4, 13)`), so even a huge mismatch
(a ~70+ OVR lineup vs. a fixed `opponent_ovr=1`) has a small but non-zero chance of a
regulation loss or tie resolved against the player — a property of the shared match
simulation engine, not of anything built this session. Since the test's assertions are
about **weekly FT-cap bookkeeping**, not match outcome, `app.services.matches.
build_simulation` is now monkeypatched to a deterministic user-win for the duration of
that one test only — production randomness, and every other test's use of the real
match engine, is untouched. Verified deterministic across 3 consecutive isolated runs
after the fix.

Full suite (`pytest tests/`, 340 tests collected):

```
340 passed, 0 failed, 0 skipped, 253 warnings
```

All 253 warnings are the same single pre-existing `DeprecationWarning` for
`datetime.datetime.utcnow()` in `app/services/match_guard.py` (unrelated to this
session, present before any of these changes) — no new warning types were introduced.
Confirmed stable across 3 consecutive full-suite runs (340/0/0 each time), plus the
previously-flaky Endless Siege test individually re-run 3x in isolation post-fix.

New tests added across both passes of this session (original 5-system implementation +
this follow-up): **102** total — 18 captain (incl. 4 new UI-text/auto-clear
verification tests), 23 bots, 10 nicknames, 14 schedule, 17 packs (incl. 3 new
handler-level tests: admin "посмотреть видео", same-message `edit_media` swap after
the 10s delay, `edit_media`-failure fallback without a duplicate reward), 22
maintenance (incl. 3 new tests: stale/old inline `callback_data` blocked, admin access
via `CallbackQuery`, explicit `/start` command block). See §21 below for the full list
of what each new verification test proves.

## 19. Smoke-test result

- `init_database()` on an empty DB: OK.
- `init_database()` run 3x in a row against the same (now-populated) DB file: OK,
  idempotent, no errors. Re-verified after the Black Market/Endless-Siege test fixes
  (no production code changed by those fixes, but re-checked for completeness).
- All new tables/columns verified present via `PRAGMA table_info` after migration.
- Full `Bot` + `Dispatcher` + `setup_routers()` construction (no network polling):
  OK — confirms the new middleware and `admin_maintenance` router attach without
  import cycles or registration errors.
- `resume_pending_pack_reveals(bot)` called against a freshly-migrated (empty) DB:
  OK, `resumed=0` as expected.
- `railway_boot.py` itself assumes a real `/app` Railway Volume layout and was not
  executed directly in this Windows dev environment (out of scope to fake); its only
  change-relevant touchpoint is `main.py`, which was smoke-tested directly.

## 20. Known limitations

- `resume_pending_pack_reveals()` delivers a resumed reward as a **new** message
  rather than trying to edit the original (now possibly stale/undeliverable) video
  message — this is a deliberate, documented design choice for correctness, not a bug.
- The Black Market date-drift issue and the Endless Siege probabilistic flake (§18)
  are now both fixed — no outstanding known test-suite issues remain from this session.
- `MaintenanceModeMiddleware`'s per-user notice cooldown is in-process memory (a plain
  dict on the middleware instance, no cross-process/SQLite-backed lock) — correct for
  this project's single-process polling bot, the same concurrency model already used
  everywhere else in the codebase; a restart simply clears the cooldown (harmless —
  worst case one extra notice is sent), and it is not intended to gate anything besides
  notice-spam (the Update itself is always blocked regardless of cooldown state).
- The captain-bonus salary-cap message and Stronghold "tower still locked" alert are
  currently Russian-language, matching every other user-facing string in this codebase.
- Inline-mode (`InlineQuery`) handling in the maintenance middleware is defensive code
  for a feature this bot doesn't currently use (confirmed zero `InlineQuery` handlers
  exist anywhere in the project) — untested against real Telegram inline-mode traffic.

## 21. Explicit verification checklist (this follow-up pass)

Each item below was verified by a real, named pytest test (not just manual inspection)
— file:test_name in parens:

- **Video longer than 10 seconds is rejected**
  (`tests/test_packs.py:test_video_duration_over_10_seconds_rejected`) — `save_pack_animation_video()`
  returns `None` for an 11-second video and never calls `bot.download()`.
- **Video can be uploaded, replaced, deleted, and viewed via the admin panel**
  — upload/replace/delete at the service layer
  (`tests/test_packs.py:test_animation_video_metadata_saved_and_toggle`), and "view"
  specifically through the real `admin_pack_view_animation` handler
  (`tests/test_packs.py:test_admin_can_view_uploaded_pack_video`, asserts the video is
  sent with a caption containing its duration/enabled status).
- **After 10 seconds the same message is edited and the video is replaced by the card**
  (`tests/test_packs.py:test_video_reveal_edits_same_message_after_delay`) — runs the
  real `packs_open` handler end-to-end with `asyncio.sleep` patched out (so the 10s wait
  is asserted, not actually waited on) and a duck-typed bot that proves `edit_media()`
  is called exactly once on the *same* returned video-message object.
- **A duplicate reward is not granted if `edit_message_media` fails**
  (`tests/test_packs.py:test_edit_media_failure_falls_back_without_duplicating_reward`)
  — forces `edit_media` to raise `TelegramBadRequest`, then asserts exactly one
  `user_cards` row and exactly one `pack_openings` row exist, and the fallback
  (delete + new message) was used instead of a second reveal.
- **Captain is automatically removed after his card is deleted from the Ranked lineup**
  (`tests/test_ranked_captain.py:test_removing_captain_card_from_lineup_clears_captaincy`
  and, end-to-end including the UI text,
  `test_deleting_captain_card_from_lineup_auto_clears_and_updates_ui`).
- **The UI shows captain, division, progress X/5, bonus, and the resulting cap**
  (`tests/test_ranked_captain.py:test_ui_block_shows_captain_division_progress_bonus_cap_below_threshold`,
  `test_ui_block_shows_active_bonus_and_boosted_cap_at_threshold`,
  `test_ui_block_shows_not_assigned_when_no_captain`) — assert the exact rendered
  strings ("Капитан: …", "Дивизион: …", "Прогресс дивизиона: X/5", "Бонус потолка: …",
  "Текущий потолок: …") both below and at the 5-card threshold, and in the
  no-captain-assigned state.
- **Maintenance middleware blocks Message, Command, CallbackQuery, and old inline
  buttons** — Message (`test_message_blocked_when_enabled`), `/start` Command
  (`test_command_message_blocked_when_enabled`,
  `test_command_slash_start_blocked_for_normal_user`), CallbackQuery
  (`test_callback_blocked_and_answered`), and specifically stale/old inline
  `callback_data` values from menus that predate the maintenance toggle
  (`test_old_stale_inline_button_blocked`, parametrized over
  `packs:open:42`/`ranked:play`/`admin_panel:admins`/`stg:fortress:view:3`/an
  arbitrary legacy string) — all in `tests/test_maintenance.py`.
- **A normal user sees the configured photo and text during maintenance**
  (`tests/test_maintenance.py:test_text_without_photo_shown`,
  `test_photo_with_text_shown`, `test_photo_without_text_uses_fallback_caption`,
  `test_no_text_no_photo_uses_default_text`).
- **The administrator retains full access** — via `Message`
  (`test_admin_keeps_access`) and, newly, via `CallbackQuery`
  (`test_admin_keeps_access_via_callback_query`) — both confirm the wrapped handler
  actually runs (not just that no exception was raised).

---

# PART 2 — Global Match Lock (единый глобальный Match Lock)

Session date: 2026-07-30 (same-day continuation). Goal: guarantee, at the database
level, that one user can never participate in more than one unfinished match at a
time, across every game mode, and that this cannot be bypassed by double-clicks,
duplicate/old callbacks, direct commands, concurrent requests, a bot restart, or
multiple running bot processes.

## P1. What protection already existed

`app/services/match_guard.py` already had `try_acquire_match_lock()` /
`release_match_lock()` / `has_active_match()` backed by an `active_matches` table
(`user_id INTEGER PRIMARY KEY`, `started_at`). The acquire function used
`BEGIN IMMEDIATE` + a manual `SELECT` then `INSERT`/`UPDATE` — inside a single SQLite
file this is *not* the naive "SELECT-then-INSERT" race the task warned about (SQLite
serializes concurrent `BEGIN IMMEDIATE` writers), but it had no physical schema-level
constraint backing it, no per-match-type TTL, no `match_id` binding, no `request_id`
idempotency, no admin diagnostics, and — critically — **it was not called from every
place a match gets created.**

## P2. Why it was insufficient

Auditing every match-creation path (see P3) found the coverage was **partial**:

- **Ranked, The Stronghold (Fortress + Endless), Clan War 2.0** — already called
  `try_acquire_match_lock`/`release_match_lock` around their match logic. Sound in
  principle, but Clan War 2.0's lock used the same flat TTL as every other mode
  despite being the *only* mode with a real multi-step drafting phase spanning real
  user think-time — a short TTL there could expire while a draft was still genuinely
  in progress, letting the player start a second match mid-draft.
- **Normal-mode quick match, matchmaking-based PvP, and tournaments — had ZERO
  protection.** `app/services/matches.py::play_quick_match()` and
  `play_player_match()` (the two functions that actually simulate and persist a
  match result) never called the guard at all. The *only* lock call anywhere near
  normal mode was in `app/handlers/matches.py::show_match_playing_and_result()`,
  acquired **after** the match had already been simulated, scored, and written to
  the `matches` table — i.e. it protected the results *animation* from being shown
  twice, not match *creation* from happening twice. A user could double-click
  "Найти соперника", or click it while a Ranked match was also resolving, with no
  server-side guard stopping either.
- `app/services/creator_tournaments.py` calls `play_player_match()` directly for
  tournament matches — since that function had no lock, tournaments inherited the
  same gap automatically.
- `app/services/war2_core.py::cleanup_abandoned_war2_matches()` marked a timed-out
  draft `'abandoned'` via raw SQL but never released the player's lock — the user
  would stay blocked for up to the lock's full TTL (worse than the draft's own
  10-minute abandon timeout) even though their draft was already void.

## P3. All match-creation points found, and guard status after this session

| # | Entry point | File | Before | After |
|---|---|---|---|---|
| 1 | Ranked Mode match | `app/services/ranked_core.py::play_ranked_match` | old guard (partial) | ✅ unified `MatchGuard`, `match_type="ranked"`, `match_id` bound |
| 2 | The Stronghold — Fortress | `app/services/stronghold_fortress.py::_play_fortress_match_impl` | old guard (partial) | ✅ `match_type="stronghold_fortress"` |
| 3 | The Stronghold — Endless Siege | `app/services/stronghold_endless.py::_play_wave_impl` | old guard (partial) | ✅ `match_type="stronghold_endless"` |
| 4 | Clan War 2.0 draft start | `app/services/war2_core.py::start_war2_match` | old guard (short TTL) | ✅ `match_type="war2"`, 30-min TTL, `bind_lock_to_match` |
| 5 | Clan War 2.0 result submit | `app/services/war2_core.py::record_war2_match_result` | released old lock | ✅ `finalize_match` |
| 6 | Clan War 2.0 draft cancel | `app/services/war2_core.py::cancel_war2_match` | released old lock | ✅ `cancel_match` |
| 7 | Clan War 2.0 auto-abandon sweep | `app/services/war2_core.py::cleanup_abandoned_war2_matches` | **lock never released** | ✅ releases lock for every user it abandons |
| 8 | Normal-mode bot match | `app/services/matches.py::play_quick_match` | **no guard at all** | ✅ `match_type="normal"` |
| 9 | Normal-mode PvP (matchmaking match, and the bot-fallback path via `finish_waiting_search_with_bot*`) | `app/services/matches.py::play_player_match` | **no guard at all** | ✅ two-party lock, `match_type="normal_pvp"` (or caller-supplied) |
| 10 | Tournament match (calls #9 directly) | `app/services/creator_tournaments.py::mark_ready_and_play` (×2 call sites) | **no guard at all** (inherited from #9) | ✅ automatically protected via #9; passes `match_type="tournament"` |
| 11 | Result animation display | `app/handlers/matches.py::show_match_playing_and_result` | old guard, post-hoc | left as-is (harmless secondary lock against double-animation; real protection now lives in #8/#9) |
| 12 | Admin/upgrade "is a match in progress" read check | `app/services/stronghold_upgrade.py` (`has_active_match`) | read-only check | ✅ unchanged call, now reads the new table transparently |

**Every current match-creation point uses the single shared `app.services.match_guard`
service — no second, incompatible locking system was built.** Because the fix for
#8/#9 was made inside the *shared* `app/services/matches.py` functions rather than at
each caller, any future mode that calls `play_quick_match()`/`play_player_match()`
inherits the protection automatically, per the task's "future modes" requirement.

## P4. How the unified `MatchGuard` works

`app/services/match_guard.py` was extended in place (not replaced by a second file)
with the exact function set requested:

```
acquire_player_match_lock(user_id, match_type, *, request_id=None, ttl_seconds=None)
get_active_match(user_id)
bind_lock_to_match(lock_id, match_id)
release_player_match_lock(user_id, *, status, reason)
finalize_match(user_id, *, match_id=None, reason="COMPLETED")
cancel_match(user_id, *, reason="CANCELLED")
expire_stale_lock(lock_id, *, reason="TTL_EXPIRED")
recover_stale_matches() -> RecoveryReport
acquire_two_player_match_lock(user_a, user_b, match_type, ...)
release_two_player_match_lock(result, ...)
finalize_two_player_match(result, ...)
list_active_locks() / admin_force_release_lock(...)          # admin diagnostics
describe_active_match(lock) / describe_active_match_short(lock)  # user-facing text
```

The legacy `try_acquire_match_lock()` / `release_match_lock()` / `has_active_match()`
signatures are kept as thin compatibility wrappers over the *same* new table — any
call site that wasn't explicitly touched (there weren't any left, but this is the
safety net) would still get full cross-mode protection automatically.

## P5. How the database physically forbids two active matches

New table `player_match_locks` (`id, user_id, match_id, match_type, status,
request_id, acquired_at, heartbeat_at, expires_at, released_at, release_reason,
created_at, updated_at`) plus:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_player_match_locks_active_user
ON player_match_locks(user_id)
WHERE status IN ('ACQUIRING', 'ACTIVE', 'RESOLVING');
```

This is a **partial unique index** — SQLite enforces it at the file level for every
connection/process touching that database file, independent of any Python-level
locking. `acquire_player_match_lock()` does a bare `INSERT` inside `BEGIN IMMEDIATE`;
if another active row for that `user_id` already exists, SQLite raises
`sqlite3.IntegrityError` on the `INSERT` itself — there is no "SELECT then decide"
window for two concurrent callers to both pass. This was verified with real OS
threads (not just `asyncio` tasks sharing one event loop, which wouldn't prove
anything about true concurrency) racing to acquire locks for the same `user_id`
across four different `match_type`s simultaneously — exactly one succeeded, every
time, across many repeated runs (see §P13).

No in-memory Python `set`/`dict`/`asyncio.Lock` is used as the actual guarantee
anywhere in this design — those would not survive a second bot process or a restart.

## P6. Two-party PvP locking

`acquire_two_player_match_lock(user_a, user_b, match_type)`:
1. Sorts the pair by **ascending `user_id`**, regardless of call argument order —
   the *only* possible lock-acquisition order for any given user across all
   simultaneous pairing attempts, which structurally rules out a
   circular-wait/deadlock between two concurrent matchmaking attempts touching the
   same two users in opposite order (tested directly: two threads race to pair
   `(A, B)` and `(B, A)` simultaneously — exactly one succeeds, no hang).
2. Acquires the lower-`user_id`'s lock first; if that fails, returns immediately
   (nothing to clean up).
3. Acquires the higher-`user_id`'s lock; **if that fails, the first lock is released
   immediately** — no participant is left holding a lock for a match that will never
   exist.
4. Only if both locks succeed does `app.services.matches.play_player_match()`
   proceed to simulate and persist results for both players; a lineup-incomplete or
   any other failure after that point releases both locks before returning.

This exact same primitive protects normal-mode PvP matchmaking *and* tournaments,
since both call the same `play_player_match()`.

## P7. Idempotency (`request_id`)

`acquire_player_match_lock(..., request_id=...)`: if the `INSERT` conflicts with an
existing active lock **and** that lock's stored `request_id` matches the one just
passed in, the call returns `acquired=True, idempotent_replay=True` pointing at the
*same* lock — a genuine retry of the same logical request is a no-op, not a second
attempt. A *different* `request_id` for the same user still gets a clean rejection —
idempotency never becomes a bypass. This is layered on top of (not instead of) the
unique-index guarantee, which is what actually prevents a second match regardless of
whether a `request_id` was supplied at all.

## P8. Releasing the lock

Every terminal transition (`finalize_match` → `COMPLETED`, `cancel_match` →
`CANCELLED`, `expire_stale_lock` → `EXPIRED`) is a single `UPDATE ... WHERE user_id = ?
AND status IN ('ACQUIRING','ACTIVE','RESOLVING')` — idempotent by construction: calling
it again on an already-terminal row matches zero rows and raises nothing. Every mode's
match-creation function now follows the same shape:

```python
lock = await match_guard.acquire_player_match_lock(user_id, "<mode>")
if not lock.acquired:
    raise/return "already active" (with a human-readable description of the existing match)
try:
    ... simulate + persist the match result ...
except Exception:
    await match_guard.cancel_match(user_id, reason="...")
    raise
await match_guard.finalize_match(user_id, match_id=result.match_id, reason="COMPLETED")
```

If the lineup/eligibility check fails *after* acquiring the lock (e.g. lineup became
incomplete between the initial check and the DB write), the lock is `cancel_match`-ed
before the failure is returned — no user is left blocked by a match that never
actually happened, and nothing was charged/awarded/mutated first (verified by
`test_blocked_second_start_does_not_change_progress_or_currency` and the integration
test in §P12).

## P9. Recovering stale/hung locks

Every lock carries `heartbeat_at` and a **per-`match_type` TTL**
(`MATCH_TYPE_TTL_SECONDS`): 300 seconds for every mode that resolves a match
synchronously in one request (Ranked/Stronghold/normal/tournaments — there is no
real "still in progress" window for these beyond a crashed/hung request), and 1800
seconds for Clan War 2.0, the only mode with a genuine multi-step drafting phase
that spans real user think-time.

`recover_stale_matches()` (boot-time call in `main.py`, before polling starts, plus a
120-second periodic loop while running) scans locks past `expires_at` and, for each,
**checks the real underlying match record first** — it never blindly nukes a lock:

- match `is still 'drafting'` (Clan War 2.0 only) → **`heartbeat_lock` extends the
  TTL**, lock stays `ACTIVE` — a real in-progress draft is never severed just
  because its TTL window closed while the user was still picking cards.
- match row exists and is resolved (or `match_id` was never set — i.e. the crash
  happened before any match was created) → lock closed as `COMPLETED`/`EXPIRED`
  respectively.
- match row referenced by `match_id` doesn't exist (corrupted/orphaned data) →
  `EXPIRED`, logged as a warning for diagnosis.

All automatic actions are logged (`logger.warning`) and returned in a
`RecoveryReport` for the caller (boot log, or the admin panel).

## P10. Admin diagnostics

New "🔒 Активные матч-локи" screen in **⚙️ Безопасность** (`app/handlers/
admin_security.py`, gated by the same `PERMISSION_SECURITY` role the rest of that
panel already uses — no new permission system introduced): paginated list of every
active lock (`user_id`, mode, status, created/heartbeat/expiry timestamps), a detail
view per lock, and a confirm-then-force-release flow. Forced release is recorded to
the existing `audit_log` table (`action='match_lock_force_release'`, actor = the
admin's `user_id`, details include the target `user_id`/mode/match_id/reason) and is
itself idempotent (double-tap on an already-released lock returns a clean "already
released" answer, not an error).

## P11. User-facing "you already have a match" message

`describe_active_match(lock)` builds the mode label, opponent name (best-effort
lookup against the relevant match table), start time, and status. Used two ways:
- **Full screen** (`app/handlers/matches.py`'s `matches:play` pre-check): edits the
  message to the full block with a "↩️ Вернуться к активному матчу", "🔄 Обновить
  статус", and (only if the mode's rules allow cancellation — currently just Clan
  War 2.0's drafting phase, via `match_guard.is_match_type_cancellable`) a cancel
  button.
- **Alert popup** (Ranked/Stronghold/Clan War 2.0/normal-mode service errors, shown
  via `callback.answer(text, show_alert=True)`): `describe_active_match_short(lock)`
  — a single plain-text line, since Telegram alerts don't render HTML and have a
  ~200-character limit that the full HTML block would blow past.

## P12. Migrations

All additive and idempotent, safe against an existing populated Railway database:

- `player_match_locks` table + 5 indexes (the partial unique active-lock index, plus
  `match_id`/`status`/`request_id`/`expires_at`) — added to `SCHEMA_QUERIES`
  (`CREATE TABLE`/`INDEX IF NOT EXISTS`), so they're created idempotently on every
  `init_database()` call, same as every other table in this project.
- `run_once(connection, "0006_migrate_active_matches_to_player_match_locks",
  migrate_active_matches_to_player_match_locks)` — runs exactly once (tracked in the
  existing `database_migrations` registry). For each row still in the old
  `active_matches` table (`PRIMARY KEY user_id`, so at most one row per user — no
  possible internal conflict), it inserts a corresponding `player_match_locks` row
  (`match_type='legacy_migrated'`, `status='ACTIVE'`, `expires_at` = that row's
  `started_at` + the default 300s TTL). **Nothing is charged, awarded, or mutated**
  — only the *fact* that a lock existed is carried over; whether it's still
  meaningful is left entirely to the existing `recover_stale_matches()` logic (same
  code path as any other stale lock), which correctly expires it since a
  `legacy_migrated` lock has no `match_id` to verify against. If, hypothetically, a
  user already had a conflicting active `player_match_locks` row (not possible on a
  fresh table, but checked defensively), that legacy row is **skipped and logged**
  for manual diagnosis rather than silently dropped or force-inserted. `active_matches`
  itself is **not** dropped or modified — verified end-to-end against a database
  seeded with legacy rows (§P13) including confirming the migration report, that
  `active_matches` row count is unchanged, that the migration doesn't re-run on a
  3rd `init_database()` call, and that a stale migrated lock is correctly recovered
  by `recover_stale_matches()`.

## P13. Test results

New test file `tests/test_match_guard.py` — **38 tests**, all passing, covering
(per the mandatory list): first match allowed, second match for the same user
rejected, second Ranked match rejected, Ranked+Stronghold mutual exclusion (both
directions), Ranked+Clan War 2.0 mutual exclusion (both directions), Stronghold+normal
mutual exclusion (both directions), two real concurrent OS-thread requests create
only one match, double-callback creates only one match, different `request_id`s under
concurrency still yield one active match, same `request_id` is idempotent, a blocked
second attempt doesn't touch tickets/currency/progress, a completed match allows a new
one, a cancelled match allows a new one, an error after acquiring the lock releases it,
user A never blocks user B, PvP atomically locks both participants, a busy second PvP
participant leaves the first unlocked, lock ordering prevents deadlock (two threads
racing to pair the same two users in opposite order), a restart-simulated lock survives
in the DB and boot recovery correctly resolves it, a lock bound to an already-completed
match is cleaned up, a lock referencing a missing/corrupted match record is diagnosed
and expired, a not-yet-expired lock is left untouched, a still-'drafting' Clan War 2.0
lock is *extended* not expired, a stale callback after completion never produces two
simultaneous active locks, a spoofed/foreign `user_id` cannot touch another user's
lock, several simulated service instances (real separate threads/connections) never
create two matches for one user, forced release is admin-only (direct handler-level
check, not just middleware) and is recorded to `audit_log`, and a static-source check
confirms every mode's service module actually imports/uses the shared `match_guard`
(and that `match_guard.py` itself no longer reads/writes the old `active_matches`
table). Plus the mandatory separate integration test
(`test_concurrent_ranked_vs_stronghold_exactly_one_match`): two real threads start a
Ranked match and a Stronghold Fortress match for the *same* user at the same time via
their real, separate service entry points — asserts exactly one of the two succeeds,
zero active locks remain afterward, and exactly one new row was written across
*either* `ranked_matches` or `stronghold_user_fortress_match_progress` (never both,
never zero).

Full suite (`pytest tests/`, 378 tests collected):

```
378 passed, 0 failed, 0 skipped
```

Confirmed stable: the full suite was run twice end-to-end (both 378/0/0), plus
`test_match_guard.py` alone re-run standalone, plus its concurrency-specific tests
(`concurrent`/`deadlock`/`double_callback`/`multiple_service`) individually repeated
3 additional times — zero flakes observed. All pre-existing mode test suites
(Ranked/Captain/Stronghold Fortress/Stronghold Endless/Clan War 2.0/tournaments/
infra reliability — 188 tests across both this session's new file and every touched
mode's existing suite) pass unchanged, confirming the refactor didn't alter any
existing gameplay behavior beyond adding the guard itself.

## P14. Smoke-test result

- `init_database()` 3× in a row against the same DB file: idempotent, no errors.
- Migration re-verified against a **populated** database seeded with legacy
  `active_matches` rows (two different users, two different ages) — correct
  migration, correct non-destructive handling of `active_matches`, correct
  idempotent no-op on a 3rd `init_database()` call, and correct downstream recovery
  of the resulting stale lock.
- Full `Bot` + `Dispatcher` + `setup_routers()` construction, `recover_stale_matches()`,
  and `resume_pending_pack_reveals()` (from the Part 1 pack-video work) all run
  cleanly together at simulated boot, confirming the new `match_lock_recovery_loop`
  task and its imports don't introduce any circular-import or registration issue.

## P15. Files changed (Part 2)

**New file:**
- `tests/test_match_guard.py`

**Rewritten in place (not replaced by a second file):**
- `app/services/match_guard.py` — full `MatchGuard` API added; legacy 3-function
  surface kept as compatibility wrappers over the new table.

**Modified:**
- `app/database/schema.py` — `player_match_locks` table + 5 indexes.
- `app/database/db.py` — `migrate_active_matches_to_player_match_locks()` +
  `run_once("0006_...")` registration; module logger added.
- `app/services/ranked_core.py` — upgraded to explicit `match_type="ranked"` API,
  `finalize_match`/`cancel_match`, richer "already active" message.
- `app/services/stronghold_fortress.py` — `match_type="stronghold_fortress"`.
- `app/services/stronghold_endless.py` — `match_type="stronghold_endless"`.
- `app/services/war2_core.py` — `match_type="war2"`; `bind_lock_to_match` after the
  `war2_matches` row is created; `cleanup_abandoned_war2_matches` now releases the
  lock for every match it abandons.
- `app/services/matches.py` — `play_quick_match` (`match_type="normal"`) and
  `play_player_match` (two-party lock, `match_type` parameter, defaults to
  `"normal_pvp"`) now guarded; previously had zero protection.
- `app/services/creator_tournaments.py` — passes `match_type="tournament"` at its
  two `play_player_match()` call sites.
- `app/handlers/matches.py` — richer active-match screen with buttons on the
  `matches:play` pre-check.
- `app/keyboards/matches.py` — `build_active_match_blocked_keyboard`.
- `app/handlers/admin_security.py`, `app/keyboards/admin_security.py` — new match-lock
  diagnostics section.
- `main.py` — boot-time `recover_stale_matches()` call + periodic
  `match_lock_recovery_loop` task (120s interval).

## P16. Known limitations (Part 2)

- `app/handlers/matches.py::show_match_playing_and_result()` still acquires its own
  short-lived lock purely to avoid rendering the same result animation twice for a
  rapid double-click on the result screen — this is now redundant for match-creation
  safety (that's fully covered inside `play_quick_match`/`play_player_match` before
  this function ever runs) but harmless to leave in place; removing it was out of
  scope since it protects a real (if minor) UX duplication, not a data-integrity gap.
- The result-animation lock in the same function, and `stronghold_upgrade.py`'s
  read-only `has_active_match()` check, were left as call sites of the legacy
  wrapper functions rather than migrated to the explicit new API — they only ever
  need the boolean "is anything active", which the compatibility wrapper already
  answers correctly against the new table.
- `MATCH_TYPE_TTL_SECONDS` is a static per-mode table, not per-request-configurable
  from the admin panel — changing a mode's TTL currently requires a code change, not
  an admin-panel setting. Not requested by this task's spec, but noted as a natural
  next step if a mode's real completion time changes significantly.

## V10.3 — единое фото-меню и 12 быстрых кнопок

- Полностью убрана нижняя ReplyKeyboard из `/start` и главной навигации.
- При открытии бота отправляется одна фотография с inline-кнопками, привязанными к сообщению.
- Для игрока вынесены ровно 12 самых частых действий: матчи, состав, карты, паки, Ranked, Stronghold, Clan War, Чёрный рынок, магазин, косметика, прогресс и дополнительные разделы.
- Для администратора вынесены ровно 12 быстрых действий; остальные инструменты доступны через понятные категории «Все разделы».
- Старые нижние клавиатуры автоматически скрываются при `/start` и возврате на главный экран.
- Возврат по `menu:main` восстанавливает общий баннер независимо от того, из текстового или графического экрана пришёл пользователь.
- Добавлен безопасный handoff из фото-меню в существующие игровые и административные обработчики без дублирования бизнес-логики.
- Добавлены проверки структуры меню и отсутствия ReplyKeyboard на стартовом экране.

## V10.4 — глобальная кнопка «Назад»

- На всех inline-экранах без собственного выхода автоматически появляется кнопка `⬅️ Назад`.
- Кнопка возвращает обычного пользователя в пользовательское фото-меню, а администратора — в административный центр.
- При возврате очищается активное FSM-состояние, поэтому пользователь не остаётся внутри незавершённого ввода.
- Уже существующие кнопки `Назад`, `Отмена`, `Главное меню`, переходы к родительскому разделу и закрытие не дублируются.
- Корневые меню с 12 кнопками остаются без бессмысленной дополнительной кнопки назад.
- Изменение реализовано централизованно: не требуется вручную поддерживать сотни отдельных клавиатур.
- Миграции базы данных не требуются.


## V10.5 — универсальная массовая загрузка во всей админ-панели

- На административных inline-экранах автоматически доступна кнопка `📥 Массовая загрузка`; на быстром экране она заменяет менее частую кнопку диагностики матчей, которая остаётся в разделе «Система».
- Добавлен единый центр массового импорта с пятью категориями: Контент, Режимы, Игроки, Экономика и Система.
- Реализовано 38 целей импорта: коллекции, карты, паки, слоты и пулы паков, глобальная косметика, дивизионы, химия, стартовый набор, Ranked, Stronghold, Clan War, события, Чёрный рынок, массовые выдачи игрокам, валюты, зарплаты, задания, пропуски, ежедневные награды, промокоды, сезонные награды и настройки.
- Поддерживаются CSV, JSON и ZIP. ZIP может содержать `manifest.csv`/`manifest.json` и папку `assets/` с изображениями.
- Для каждой цели из бота можно скачать готовый CSV- или JSON-шаблон.
- Перед записью показывается предпросмотр до 20 строк с точными ошибками. При наличии хотя бы одной ошибки кнопка подтверждения не появляется.
- Все строки применяются одной SQLite-транзакцией `BEGIN IMMEDIATE`: частичный импорт запрещён. Созданные во время неудачного импорта ассеты также удаляются.
- Повторная загрузка по ключевым полям обновляет существующие записи вместо создания дублей.
- Массовые выдачи карт и косметики создают отдельные экземпляры; косметика остаётся трейдабл и учитывает количество копий.
- Доступ к каждой цели фильтруется по существующим ролям и permissions; один тип администратора не получает доступ к чужим экономическим или системным операциям.
- Успешный импорт записывается в общий `audit_log` с именем файла и количеством созданных/обновлённых строк.
- Добавлены защита от path traversal в ZIP, лимит 2 000 строк, лимиты размера архива и белый список расширений ассетов.
- Миграция базы не требуется.

## V10.6 — исправление кнопки «Назад» в карточках

- В общем списке пользовательских карточек кнопка «⬅️ Назад» теперь возвращает в единое фото-меню (`menu:main`).
- Раньше она вызывала `user_cards:main`, который повторно открывал тот же список, поэтому визуально кнопка зацикливалась.
- Возврат из профиля конкретной карточки по-прежнему ведёт на исходную страницу списка.
- Возврат из фильтров, поиска и подтверждений остаётся внутри раздела карточек.
- Миграция базы данных не требуется.



## V10.8 — интерактивные буллиты в Ranked

- После трёх периодов Ranked может завершиться вничью; базовый шанс — 20%, меняется в админ-настройках от 0 до 100%.
- Ничья не записывается как готовый матч: рейтинг, XP и история фиксируются только после завершения мини-игры.
- Серия начинается с трёх раундов, затем переходит во внезапную смерть.
- На каждом действии игрок получает четыре угла: верхний левый, верхний правый, нижний левый и нижний правый.
- На выбор броска или угла защиты даётся 10 секунд.
- Совпавшие углы означают сейв; разные углы — гол.
- Если бросающий не ответил, броска и гола нет. Если вратарь не ответил, засчитывается гол.
- Итоговый хоккейный счёт получает только один дополнительный гол победителю серии, а отдельный счёт буллитов показывается в результате.
- Все попытки сохраняются в ranked_matches.shootout_log_json; также хранятся счёт после трёх периодов и итог серии.
- MatchGuard удерживает пользователя на всём протяжении 60-секундной анимации и мини-игры.
- Универсальная кнопка «Назад» не добавляется к четырём игровым кнопкам во время активного выбора.
