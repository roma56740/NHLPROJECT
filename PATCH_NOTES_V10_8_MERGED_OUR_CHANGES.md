# V10.8 + merged project changes (R1)

Base: `2026.07.31-ranked-shootout-v10.8`.

## Render system
- New configurable server-side render theme settings and admin section `🖼 Рендеры`.
- Main menu render has no game logo.
- Menu background/video, title, subtitle and accent can be changed from admin without deploy.
- Equipped personal profile/menu background overrides seasonal/default menu media.
- Custom lineup background is supported.
- Normal lineup shows salary total only; no normal-mode salary cap is displayed/applied.
- Ranked lineup shows salary and Ranked salary cap.
- Lineup chemistry is visualized with links.
- Card cosmetics remain instance-bound through V10.8 `user_card_frames`; a frame applies to one concrete `user_card_id`.
- Collection and card-view renders use that per-instance frame.
- Clan War uses the same 3 FWD / 2 DEF / 1 GK visual layout as the ordinary lineup.

## Clan War 2.0
- Clan War gameplay lineup is now 6 cards: 3 FWD, 2 DEF, 1 GK.
- Draft is 6 rounds per side and enforces those position quotas.
- Opponent auto-pick also respects 3F/2D/1G.
- Clone War generates a real 6-card 3F/2D/1G roster.
- Wild Card replacement must preserve the replaced card position.
- If every War mode is disabled in an old database, modes self-heal instead of blocking matchmaking.
- Admin cannot disable the final active War mode.

## Bot opponents
- Bot render lineups use real cards from the global active card catalog.
- An assigned bot OVR X uses random real cards with exactly OVR X, not a nearby rating.
- Preferred bot composition: 3 FWD / 2 DEF / 1 GK.

## Packs
- Existing V10.8 pack-video admin system is preserved.
- Pack opening video is sent cleanly, without extra render/showcase caption chrome.
- Reward reveal/recovery logic from V10.8 is preserved.

## Creator tournaments
- Every creator tournament receives a stable invite token.
- Creator can get/share a deep link: `https://t.me/<bot>?start=ct_<token>`.
- Opening the link registers the player automatically when registration is open and space exists.
- Repeat opens are idempotent.
- Legacy tournaments get invite tokens through migration/backfill.
- Invite payload survives the mandatory-subscription gate and continues after successful subscription check.

## V10.8 preservation
- Ranked Shootout V10.8 kept.
- Black Market kept.
- Existing pack-video system kept.
- Existing match-lock/reliability changes kept.
- Existing instance-specific card-frame implementation kept and used, not replaced with a global frame.
