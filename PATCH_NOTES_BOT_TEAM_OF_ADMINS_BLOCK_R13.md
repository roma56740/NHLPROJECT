# R13 — bots cannot use Team Of Admins cards

`Team Of Admins` is now a hard-blocked collection for automated card selection.

Covered paths:
- Ranked bot real-card lineup generation, including exact-OVR availability checks.
- Generic bot/opponent lineup renders used by match screens.
- CLAN WAR 2.0 Clone War random roster generation.
- New CLAN WAR 2.0 Draft pools.
- CLAN WAR 2.0 automated opponent auto-picks, including already-cached legacy draft pools created before this patch.
- Ranked bot catalog diagnostics now count only cards the bot is actually allowed to use.

The restriction matches both collection name `Team Of Admins` and canonical code `team-of-admins` case-insensitively. Human-owned cards are not deleted or modified; the rule only affects server-side automated/random bot selection.
