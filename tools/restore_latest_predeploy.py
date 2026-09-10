from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def quick_check(path: Path) -> bool:
    try:
        con = sqlite3.connect(path)
        try:
            row = con.execute("PRAGMA quick_check").fetchone()
            return bool(row) and str(row[0]).strip().lower() == "ok"
        finally:
            con.close()
    except sqlite3.Error:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore the newest verified predeploy SQLite backup. Run only with the normal bot process stopped."
    )
    parser.add_argument("--confirm", default="", help="Must be exactly RESTORE")
    args = parser.parse_args()

    db = Path(os.getenv("DATABASE_PATH", "/app/data/nhl_bot.sqlite3"))
    backup_dir = db.parent / "predeploy_backups"
    backups = sorted(backup_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"No predeploy backup found in {backup_dir}")
        return 2

    source = backups[0]
    print(f"Production DB: {db}")
    print(f"Latest predeploy backup: {source}")

    if not quick_check(source):
        print("REFUSED: backup failed PRAGMA quick_check")
        return 3

    if args.confirm != "RESTORE":
        print("DRY RUN ONLY. To restore, stop the normal bot process and run:")
        print("python tools/restore_latest_predeploy.py --confirm RESTORE")
        return 0

    emergency_dir = db.parent / "rollback_safety"
    emergency_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    emergency = emergency_dir / f"before_restore_{stamp}.sqlite3"

    if db.exists():
        if not quick_check(db):
            print("Current DB quick_check failed; preserving raw file before restore.")
            shutil.copy2(db, emergency)
        else:
            src = sqlite3.connect(db)
            dst = sqlite3.connect(emergency)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        print(f"Emergency copy created: {emergency}")

    # Replace through SQLite backup API so the destination is a valid SQLite DB.
    src = sqlite3.connect(source)
    dst = sqlite3.connect(db)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    if not quick_check(db):
        print("RESTORE FAILED: restored DB did not pass PRAGMA quick_check")
        return 4

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db) + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass

    print("RESTORE COMPLETE: production DB passed PRAGMA quick_check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
