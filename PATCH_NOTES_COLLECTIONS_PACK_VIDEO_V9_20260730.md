# V9 — COLLECTION BINDING + PACK VIDEO OPENING

## Collections

- Ranked collection exact display name: `Ranked Season 1`.
- Stronghold collection exact display name: `The Stronghold`.
- On startup, legacy/admin aliases are merged into the stable collection records.
- Existing uploaded cards are preserved and reassigned to the canonical collection.
- Stronghold gameplay binds card definitions by `player name + OVR + collection`, preferring admin-uploaded images over seed placeholders.

## Regular pack opening animation

- Each regular pack has its own optional `animation_video_path`.
- Admin uploads/replaces/removes the video from the pack profile in the Telegram admin panel.
- Accepted: Telegram video/animation or MP4/MOV/WEBM document. Native Telegram videos longer than 10 seconds are rejected.
- Opening flow: video message -> wait 10 seconds -> same message becomes the awarded card image.
- Multi-card packs reuse the same message and reveal subsequent cards every 2 seconds.
- Rewards are generated/granted once before visuals; animation cannot reroll or duplicate items.
- Uploads are stored under `assets/uploads/packs/animations`, which Railway maps to the persistent uploads volume.

No deployment script is included in this build.
