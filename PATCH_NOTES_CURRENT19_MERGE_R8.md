# R8 — merge current project (19) + prior designed changes

Base intent: preserve the current `NHLPROJECT-main (19)` branch, including its arena Clan Wars / clan season additions, while restoring and retaining the feature set from the previous R7 branch.

## Preserved from current project

- Arena Clan Wars (`clan_arenas`, attacks, defense, shields, cooldowns, anti-monopoly rules).
- Clan-war personal contribution and global clan ratings.
- Clan season rewards, top-5 reward tiers, history and protected reset flow.
- Arena admin modules and permissions.
- Current project assets, including uploaded card/pack images.
- Current creator/division/subscription/admin-level foundations where compatible.

## Brought in from previous R7 / our prior changes

- Ranked mode, Ranked Shootout and exact-OVR real-card bots.
- Stronghold and the replay reward/rating fix.
- Black Market and the purchase transaction/callback fix.
- CLAN WAR 2.0 with active-mode self-heal, real-card structures and 3F/2D/1G roster logic.
- Creator Tournament invite/deep-link flow.
- Premium server-side render system.
- Per-card cosmetic frame ownership (`user_card_id`), not global-by-player framing.
- DNA as a main-menu system with DNA Collectibles, extraction, choice craft and 93→95→98→100 progression.
- Card OVR technical support up to 110.
- Automated weekly creator-bank payouts with idempotent `period_key`.
- Reliability additions from R7: stale match-lock recovery, backups, health loop, black-market notifications and pending pack-reveal recovery.

## Important merge decision

The previous R7 branch contained a migration that removed the older arena Clan Wars tables. That destructive migration/helper is removed from R8. The current project's arena Clan Wars are retained alongside CLAN WAR 2.0.

## Additional integration fix

Fixed `get_dna_craft_preview()` so input selection happens while its SQLite connection is still open. Without this, a fully funded DNA recipe preview could attempt to use a closed connection.

## Validation performed

- `python -m compileall -q .` — passed.
- Fresh SQLite initialization — passed; 141 tables, no FK violations.
- Current-project SQLite schema → R8 migration — passed; arena Clan Wars tables survived and R7 tables were added.
- OVR `cards` CHECK verified at `1..110`.
- Creator weekly payout smoke test — same `period_key` is not paid twice; a later period is paid normally.
- DNA smoke test — welcome collectible is one-time; a funded 93 OVR craft consumes five distinct source copies and creates a new 93 DNA card without mutating source OVR.

Full aiogram/pytest runtime suite was not executed in this container because `aiogram` is not installed here; syntax and database/service-level checks above were run directly.
