# R15 final safe deploy

R15 render-cache/Volume fix merged on top of the deployed R14 safe release.

Deployment safety retained:
- production SQLite remains on `/app/data` and is never packaged;
- startup verifies the existing production DB with `PRAGMA quick_check`;
- startup aborts instead of silently creating an empty Railway production DB;
- predeploy backup remains required before schema changes;
- existing `/app/data/uploads` files are snapshotted and hash-verified as unchanged;
- bundled uploads are seed-only and only fill missing files;
- legacy `/app/data/render_cache` is deleted because it is temporary data;
- runtime render cache now lives outside the persistent Volume at `/app/cache/render_cache` by default;
- generated one-shot renders are removed after Telegram send through the safe cache-only deletion helper.

`SCHEMA_VERSION` remains 3 because R15 changes render-cache behavior and does not add a database schema migration.
