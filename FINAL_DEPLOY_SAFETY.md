# FINAL DEPLOY SAFETY — CURRENT19 R9 DNA

This build is prepared for an in-place Railway deploy with the persistent Volume mounted at `/app/data`.

## Protected production data

The deploy package intentionally contains **no** live SQLite database, WAL/SHM files, `.env`, runtime render cache, or administrator upload directory.

At Railway boot:

1. The existing database must be present in production (`ALLOW_EMPTY_DATABASE=0` by default on Railway).
2. `PRAGMA quick_check` must pass before any migration.
3. A predeploy SQLite backup is forced once for this release (`SCHEMA_VERSION=2`).
4. Existing upload files are SHA-256 snapshotted before bundled seed assets are copied.
5. Bundled assets use **copy-if-missing only**. Existing production files are never overwritten.
6. Existing uploads are SHA-256 verified unchanged after the seed step.
7. `assets/uploads` is only a symlink to the persistent uploads directory.
8. After database initialization/migrations, `PRAGMA quick_check` runs again before Telegram polling starts.
9. Any failed guard stops startup instead of silently creating a fresh DB or hiding a missing Volume.

## Railway variables for production

Recommended/required values:

```env
DATABASE_PATH=/app/data/nhl_bot.sqlite3
STRICT_PERSISTENT_STORAGE=1
ALLOW_EMPTY_DATABASE=0
REQUIRE_EXISTING_UPLOADS=1
VERIFY_UPLOADS_ON_BOOT=1
REQUIRE_PREDEPLOY_BACKUP=1
STRICT_DB_INTEGRITY=1
```

Keep the existing secret values unchanged:

```env
BOT_TOKEN=...
ADMIN_IDS=...
BLACK_MARKET_SEED_SECRET=...
```

The Railway Volume must remain mounted at `/app/data`.

## Bundled images

Files that were previously inside ignored `assets/uploads/` were moved into `restore_seed/uploads/`. This includes the DNA card art. `RESTORE_SEED_SHA256.txt` verifies every seed asset in the image before startup. Seed files only fill missing paths and never replace a file already on the Volume.
