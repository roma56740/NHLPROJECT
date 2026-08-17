# R12 — DNA Extraction: exact card selection

Fixed DNA Collectible crafting/extraction so the game never silently auto-picks cards for the player in the UI.

## New flow
1. Open DNA → Get Collectibles / DNA Extraction.
2. Choose an extraction recipe (90–92, 93–94, 95–96, 97, 98 or 99 OVR).
3. The bot shows the player's eligible **specific owned card instances**.
4. Tap cards to select/deselect the exact instances to burn.
5. When the exact required number is selected, confirm extraction.
6. Only those selected `user_cards.id` rows are consumed and the configured DNA Collectibles are credited.

## Safety
- DNA collection cards are excluded.
- Cards in lineup, trade-locked, open trade offers, with a per-card frame, or assigned as Ranked Captain are not selectable.
- Each owned copy is treated as a separate instance; duplicates can be distinguished by their instance id.
- Confirmation re-validates every selected instance inside `BEGIN IMMEDIATE`; if any selected card became unavailable, nothing is consumed and the selection is reset.
- Existing service callers remain backwards compatible: `extract_dna_collectibles(..., user_card_ids=None)` still supports automatic selection internally, while the player UI always passes explicit ids.

## Verification
- `python -m compileall -q app` passed.
- Fresh SQLite R11 schema initialized: 141 tables.
- Service test confirmed the selector excludes an in-lineup copy and consumes exactly the three explicitly selected `user_cards.id` instances in the submitted order.
