# R16 — X-Factors + Player Mastery

## X-Factors

- Added a 37-item X-Factor catalog: 27 normal factors and 10 unique Mastery factors.
- X-Factors are inventory items and are installed on a concrete `user_cards.id` copy, never on the global card definition.
- Maximum 3 installed factors per card copy.
- Installing consumes one inventory item. Removing destroys the factor after confirmation. Replacing at 3/3 destroys the selected old factor and consumes the new item.
- Normal X-Factors support one-at-a-time Quick Sell for 20,000 Coins.
- Unique Mastery X-Factors cannot be Quick Sold and may only be installed on the matching hockey player.
- Quick Draw can be installed on an F card but its battle bonus activates only in lineup slot F2 (center).
- Card profile render displays all installed X-Factor icons vertically on the right edge, slightly overlapping/protruding from the card.
- Existing card trades keep installed X-Factors on the concrete card copy and now show their names in trade card lines.
- Added `🎒 Инвентарь` with Collectibles and X-Factors sections.
- X-Factor battle modifiers are enabled only for ordinary bot/PvP matches. Stronghold, Ranked, Clan War and creator tournaments are not migrated to this combat layer.

## Player Mastery

Initial mastery roster:

- Martin Brodeur
- Nicklas Lidström
- Pavel Datsyuk
- Jaromír Jágr
- Carey Price
- Zdeno Chára
- Sidney Crosby
- Alexander Ovechkin
- Joe Sakic
- Henrik Lundqvist

Rules:

- Mastery belongs to `(user, hockey player)`, so every copy/version of the same hockey player contributes to one shared progress bar.
- Ordinary-match win: +50 Mastery. Loss: +10 Mastery.
- Every mastery-enabled hockey player in the lineup receives the result independently.
- Maximum progress: 1,000,000.
- Rewards are claimed manually from the Mastery menu.
- A Mastery button is available from eligible card profiles and opens a dedicated progress render plus reward track.

Reward thresholds:

`100, 250, 500, 1k, 2k, 3.5k, 5.5k, 8k, 12k, 18k, 27k, 40k, 60k, 90k, 130k, 180k, 250k, 340k, 450k, 560k, 700k, 850k, 1m`.

The 180k and 700k tiers are intentionally reserved/empty future reward slots. Normal X-Factors are granted at 60k and 340k. The player-specific unique Mastery X-Factor is granted at 1,000,000.

Unique factors:

- Brodeur — Third Defenseman
- Lidström — Perfect Position
- Datsyuk — The Magic Man
- Jágr — Unbreakable
- Price — Calm Under Fire
- Chára — The Giant
- Crosby — Complete Player
- Ovechkin — The Office
- Sakic — Wrist Shot Legend
- Lundqvist — The King

## Database / deploy safety

- Additive migrations only; no production DB recreation.
- New tables: `xfactors`, `user_xfactor_items`, `user_card_xfactors`, `user_player_mastery`, `user_mastery_claims`, `mastery_match_awards`.
- `SCHEMA_VERSION` bumped to 4 so the normal pre-deploy backup guard recognizes this release as a schema-changing build.
