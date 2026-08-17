# R9 — DNA complete card collection

The ten user-provided DNA card visuals are bundled unchanged and seeded into the live catalog automatically.

## DNA catalog

- Danila Yurov — 93 OVR — F — Minnesota Wild — Russia — salary 6300
- Matvei Michkov — 93 OVR — F — Philadelphia Flyers — Russia — salary 6300
- Cole Caufield — 95 OVR — F — Montreal Canadiens — USA — salary 7000
- Jack Eichel — 95 OVR — F — Vegas Golden Knights — USA — salary 7000
- Mark Scheifele — 98 OVR — F — Winnipeg Jets — Canada — salary 8200
- Martin Necas — 98 OVR — F — Colorado Avalanche — Czechia — salary 8200
- Mark Stone — 100 OVR — F — Vegas Golden Knights — Canada — salary 9000
- Lane Hutson — 100 OVR — D — Montreal Canadiens — USA — salary 9000
- Logan Cooley — 100 OVR — F — Utah Mammoth — USA — salary 9000
- Matthew Schaefer — 100 OVR — D — New York Islanders — Canada — salary 9000

All cards use rarity `Event` and collection `DNA`. The DNA collection is marked exclusive so it does not leak into generic Clan War draft pools or generic 95–96 choice pools.

## Deployment behavior

`seed_dna_content()` now upserts the complete card catalog on startup. Existing surname-only placeholder rows (for example `Yurov 93`) are reused and updated rather than duplicated, preserving their card IDs and any owned user-card instances that reference them.

The original uploaded image bytes are copied without resizing, recompression, retouching, or AI generation. Runtime rendering may resize them in memory exactly like every other card render, while the source PNGs remain unchanged.
