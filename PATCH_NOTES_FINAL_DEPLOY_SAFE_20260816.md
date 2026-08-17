# FINAL DEPLOY SAFE — 2026-08-16

Deployment-only hardening for CURRENT19 + R9 DNA. Gameplay behavior is not intentionally changed.

- Moved all bundled `assets/uploads/*` files into tracked `restore_seed/uploads/*`, including all 10 DNA card images.
- Added SHA-256 manifest for every seed asset.
- Added Railway startup guard against a missing/empty production DB.
- Added pre-migration and post-migration `PRAGMA quick_check`.
- Bumped backup schema marker from 1 to 2 so this release gets a fresh verified predeploy backup.
- Existing upload files are hashed before seed copy and verified unchanged afterward.
- Seed copy is missing-only; it can never overwrite an existing production image/video.
- Removed Python bytecode/cache artifacts from the deploy payload.
- Added production environment checklist in `FINAL_DEPLOY_SAFETY.md`.
