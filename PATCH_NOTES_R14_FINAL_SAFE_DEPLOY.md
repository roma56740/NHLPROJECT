# R14 final safe deploy

This deploy package preserves the R14 Leaders/admin-only/card-owner changes and restores the production deployment safety layer already used by `roma56740/NHLPROJECT`.

## Persistence safety
- Production SQLite must remain at `/app/data/nhl_bot.sqlite3`.
- Existing production uploads are snapshotted (size + SHA-256) before seed copy and verified unchanged afterwards.
- Bundled assets are seed-only under `restore_seed/uploads`; they only fill missing files and never overwrite existing Volume files.
- `assets/uploads` is not shipped as a normal directory; boot links it to the persistent uploads directory.
- Production DB must pass `PRAGMA quick_check` before startup.
- Missing production DB/uploads abort startup on Railway when strict safety variables are enabled.
- A verified predeploy backup is required before migrations; R14 uses `SCHEMA_VERSION = 3` so the current production marker `2` creates one fresh backup for this release.
- Legacy `/app/data/render_cache` may be deleted; DB/uploads/media are never deleted by that cleanup.

## R14 functionality retained
- `Leaders` remains admin-issued-only for automated distribution paths.
- Existing owned Leaders copies remain owned.
- Admin Cards can list all owners/copies and revoke one exact `user_card_id` after confirmation.
