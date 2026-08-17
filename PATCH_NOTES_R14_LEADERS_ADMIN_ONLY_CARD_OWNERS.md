# R14 — Leaders admin-only + card owners/revoke

## Leaders distribution policy
- `Leaders` is an admin-issued-only collection.
- Existing owned copies are preserved.
- User-to-user ownership transfer is not globally blocked.
- Automated acquisition paths cannot mint Leaders cards: normal packs/shop packs, Ranked packs, Black Market, Stronghold store/upgrades, Hockey Pass, Ranked Pass, starter kit, free card, event rewards, system reward settings, and DNA 95–96 Choice Craft.
- On startup stale Leaders entries are removed/deactivated from configured distribution sources and the collection is marked exclusive so generic bot/draft pools do not use it.
- Direct admin card issuance remains available.

## Admin card ownership tools
- Every card in Admin Cards has a `👥 Владельцы` action.
- Shows all unique owners and copy counts with pagination.
- Opening an owner shows every exact `user_card_id` copy and its state.
- Admin can revoke one exact copy with a confirmation step.
- Revocation safely removes lineup/captain/frame bindings by FK behavior, cancels open trades containing the exact copy, cancels available creator-bank references to it, and writes an audit log entry.
