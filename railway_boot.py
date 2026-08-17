from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/nhl_bot.sqlite3").strip() or "data/nhl_bot.sqlite3")
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT / DATABASE_PATH
DATA_DIR = DATABASE_PATH.parent
DATA_UPLOADS = DATA_DIR / "uploads"
ASSETS_UPLOADS = ROOT / "assets" / "uploads"
SEED_UPLOADS = ROOT / "restore_seed" / "uploads"
SEED_MANIFEST = ROOT / "RESTORE_SEED_SHA256.txt"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _is_railway() -> bool:
    return bool(os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("RAILWAY_PROJECT_ID"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quick_check(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        connection = sqlite3.connect(path, timeout=30)
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
            return bool(row) and str(row[0]).strip().lower() == "ok"
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def verify_seed_manifest() -> None:
    if not SEED_MANIFEST.exists():
        raise RuntimeError(f"Seed manifest is missing: {SEED_MANIFEST}")

    checked = 0
    for line in SEED_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split("  ", 1)
        path = ROOT / rel
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"Seed file is missing: {rel}")
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"Seed file checksum mismatch: {rel}")
        checked += 1
    print(f"[seed] manifest verified: {checked} file(s)", flush=True)


def preflight_persistent_storage() -> None:
    strict = _env_bool("STRICT_PERSISTENT_STORAGE", _is_railway())
    allow_empty_database = _env_bool("ALLOW_EMPTY_DATABASE", not _is_railway())
    require_existing_uploads = _env_bool("REQUIRE_EXISTING_UPLOADS", _is_railway())

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if strict:
        resolved_db = DATABASE_PATH.resolve(strict=False)
        resolved_data = DATA_DIR.resolve(strict=False)
        if resolved_db.parent != resolved_data:
            raise RuntimeError(
                f"DATABASE_PATH must live inside the persistent data directory: {resolved_db}"
            )

    if DATABASE_PATH.exists():
        if not _quick_check(DATABASE_PATH):
            raise RuntimeError(
                f"Production database failed PRAGMA quick_check: {DATABASE_PATH}. Startup aborted."
            )
        print(
            f"[database] existing DB verified: {DATABASE_PATH} ({DATABASE_PATH.stat().st_size} bytes)",
            flush=True,
        )
    elif not allow_empty_database:
        raise RuntimeError(
            f"Expected production database is missing: {DATABASE_PATH}. "
            "Startup aborted to avoid silently creating a new empty database."
        )
    else:
        print(f"[database] no existing DB; empty database is explicitly allowed: {DATABASE_PATH}", flush=True)

    if require_existing_uploads:
        existing = [p for p in DATA_UPLOADS.rglob("*") if p.is_file()] if DATA_UPLOADS.exists() else []
        if not existing:
            raise RuntimeError(
                f"Expected production uploads are missing/empty: {DATA_UPLOADS}. "
                "Startup aborted to avoid masking a missing Railway Volume."
            )
        print(f"[uploads] existing persistent files: {len(existing)}", flush=True)


def snapshot_existing_uploads() -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    if not DATA_UPLOADS.exists():
        return snapshot
    for item in DATA_UPLOADS.rglob("*"):
        if not item.is_file() or item.is_symlink():
            continue
        rel = item.relative_to(DATA_UPLOADS).as_posix()
        snapshot[rel] = (item.stat().st_size, _sha256(item))
    print(f"[uploads] protected snapshot: {len(snapshot)} file(s)", flush=True)
    return snapshot


def verify_existing_uploads_unchanged(snapshot: dict[str, tuple[int, str]]) -> None:
    for rel, (expected_size, expected_hash) in snapshot.items():
        item = DATA_UPLOADS / rel
        if not item.exists() or not item.is_file():
            raise RuntimeError(f"Existing production upload disappeared during boot: {rel}")
        if item.stat().st_size != expected_size:
            raise RuntimeError(f"Existing production upload size changed during boot: {rel}")
        if _sha256(item) != expected_hash:
            raise RuntimeError(f"Existing production upload checksum changed during boot: {rel}")
    print(f"[uploads] protected files unchanged: {len(snapshot)}", flush=True)


def copy_tree_missing(src: Path, dst: Path) -> int:
    if not src.exists():
        return 0

    copied = 0
    for item in src.rglob("*"):
        if not item.is_file():
            continue

        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        # Critical persistence rule: bundled assets are seed-only. They can add a
        # missing file, but must NEVER overwrite an administrator/user upload that
        # already exists on the Railway Volume.
        if not target.exists():
            shutil.copy2(item, target)
            copied += 1

    return copied


def ensure_uploads_link() -> None:
    DATA_UPLOADS.mkdir(parents=True, exist_ok=True)
    protected = snapshot_existing_uploads()

    # 1) Add only missing seed assets to the persistent volume.
    copied = copy_tree_missing(SEED_UPLOADS, DATA_UPLOADS)
    print(f"[seed] copied missing files to volume: {copied}", flush=True)

    # 2) Backward compatibility: if an old build still contains a normal
    # assets/uploads directory, copy ONLY its missing files, then remove the
    # ephemeral directory before creating the symlink.
    if ASSETS_UPLOADS.exists() and not ASSETS_UPLOADS.is_symlink():
        moved = copy_tree_missing(ASSETS_UPLOADS, DATA_UPLOADS)
        print(f"[uploads] copied missing bundled assets to volume: {moved}", flush=True)
        shutil.rmtree(ASSETS_UPLOADS)

    # 3) Make all legacy relative paths assets/uploads/... resolve to the Volume.
    ASSETS_UPLOADS.parent.mkdir(parents=True, exist_ok=True)
    if ASSETS_UPLOADS.is_symlink() or ASSETS_UPLOADS.exists():
        try:
            ASSETS_UPLOADS.unlink()
        except IsADirectoryError:
            shutil.rmtree(ASSETS_UPLOADS)
    ASSETS_UPLOADS.symlink_to(DATA_UPLOADS, target_is_directory=True)
    print(f"[uploads] linked {ASSETS_UPLOADS} -> {DATA_UPLOADS}", flush=True)

    # Hash every file that existed before this deploy and prove it was untouched.
    if _env_bool("VERIFY_UPLOADS_ON_BOOT", _is_railway()):
        verify_existing_uploads_unchanged(protected)


def cleanup_startup_cache() -> None:
    try:
        from app.services.cache_cleanup import cleanup_render_cache

        cleanup_render_cache()
    except Exception as error:
        print(f"[render_cache] startup cleanup failed: {error}", flush=True)


def remove_legacy_volume_render_cache() -> None:
    """Delete only obsolete temporary render cache, never DB/uploads/media."""
    legacy_path = DATA_DIR / "render_cache"
    if legacy_path.exists() and legacy_path.is_dir():
        try:
            shutil.rmtree(legacy_path)
            print(f"[render_cache] removed legacy volume cache: {legacy_path}", flush=True)
        except OSError as error:
            print(f"[render_cache] failed to remove legacy volume cache: {error}", flush=True)


def create_required_predeploy_backup() -> None:
    """Create a verified SQLite backup before schema initialization/migrations.

    On Railway an existing production DB is never allowed to continue into a schema
    change when the required backup failed. For an explicitly empty/fresh install,
    there is naturally nothing to back up.
    """
    if not DATABASE_PATH.exists():
        return

    from app.services import backups

    result = backups.create_backup("predeploy")
    print(f"[backup] predeploy: {result.message}", flush=True)
    if not result.success and _env_bool("REQUIRE_PREDEPLOY_BACKUP", _is_railway()):
        raise RuntimeError("Required predeploy backup failed. Startup aborted before migrations.")


try:
    verify_seed_manifest()
    preflight_persistent_storage()
    create_required_predeploy_backup()
    ensure_uploads_link()
    remove_legacy_volume_render_cache()
    cleanup_startup_cache()
except Exception as error:
    print(f"[FATAL PREDEPLOY GUARD] {error}", file=sys.stderr, flush=True)
    raise SystemExit(70) from error

os.execv(sys.executable, [sys.executable, str(ROOT / "main.py")])
