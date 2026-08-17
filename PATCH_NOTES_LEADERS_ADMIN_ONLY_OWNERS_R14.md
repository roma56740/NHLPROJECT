# R14 — Leaders admin-only + card owners/revoke

## Leaders: only administrators can mint copies

The `Leaders` collection is now treated as an admin-only collection.
Existing owned `user_cards` copies are preserved; normal ownership-transfer mechanics can still move an already-existing copy between players. New copies must not originate from automated acquisition sources.

Protection is applied to:
- normal pack pools, pack slots (including special collection slots) and the regular Shop;
- Ranked pack pools;
- Black Market pool generation, pool editing and purchase grant;
- Stronghold Store direct-card products;
- Starter Kit;
- Free Card;
- Ranked Pass direct-card rewards;
- Hockey Pass direct-card rewards;
- Event direct-card rewards;
- DNA 95–96 Choice Craft;
- Stronghold Upgrade Chain safety guard;
- bulk-import configuration for the same sources.

On every database startup a sanitizer also removes/deactivates legacy Leaders configuration in pack pools/slots, Ranked pack pools, Starter Kit, Black Market, Stronghold Store, direct pass rewards, event card rewards and reward settings. The collection is marked `is_exclusive=1`, so generic bot / Clan War draft pools cannot select it either.

Admin card grants remain allowed (including mass `card_grants`).

## Owners of every card

Admin Panel → Cards → any card now has `👥 Владельцы`.

The screen shows:
- every unique owner;
- the number of copies owned by each user;
- total owners and total copies;
- every exact `user_card_id` copy for a selected owner;
- whether the exact copy is in a lineup, trade-locked, in an open trade, used as Ranked Captain, or has a bound frame.

An admin can open an exact copy and use `🚨 Забрать у владельца` → confirmation.

Revocation semantics:
- removes only the selected `user_cards.id` instance;
- cancels any open trade containing that exact instance;
- cancels an available Creator Bank row pointing to the instance;
- lineup / Ranked Captain / bound-frame relations are removed safely by the existing FK relations;
- the frame cosmetic itself is not destroyed;
- writes `admin_revoke_user_card` to the audit log.

## Validation

- `python -m compileall -q app` — passed.
- Fresh SQLite schema + Leaders distribution sanitizer (including a Leaders-only pack slot) — passed.
- Regular pack random selection never returned Leaders even after manual bad DB insertion — passed.
- Black Market direct Leaders creation — rejected with `ADMIN_ONLY_COLLECTION`.
- Stronghold Store Leaders product validation — rejected.
- Bulk pack/event configuration with Leaders — rejected.
- Owner aggregation (2 owners / 3 copies) — passed.
- Exact-copy revoke from an open trade cancelled the trade, removed only that copy, and `PRAGMA foreign_key_check` returned no errors.

Full runtime pytest was not executed in this container because `aiogram` is not installed here.
