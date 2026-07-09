import os
import shutil
import sys
from pathlib import Path

ROOT = Path("/app")
DATA_UPLOADS = ROOT / "data" / "uploads"
ASSETS_UPLOADS = ROOT / "assets" / "uploads"
SEED_UPLOADS = ROOT / "restore_seed" / "uploads"


def copy_tree_missing(src: Path, dst: Path):
    if not src.exists():
        return 0

    copied = 0
    for item in src.rglob("*"):
        if not item.is_file():
            continue

        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if not target.exists():
            shutil.copy2(item, target)
            copied += 1

    return copied


def ensure_uploads_link():
    DATA_UPLOADS.mkdir(parents=True, exist_ok=True)

    # 1) сначала переносим/копируем seed-карты в volume
    copied = copy_tree_missing(SEED_UPLOADS, DATA_UPLOADS)
    print(f"[seed] copied to volume: {copied}", flush=True)

    # 2) если assets/uploads обычная папка, копируем её содержимое в volume
    if ASSETS_UPLOADS.exists() and not ASSETS_UPLOADS.is_symlink():
        moved = copy_tree_missing(ASSETS_UPLOADS, DATA_UPLOADS)
        print(f"[uploads] copied existing assets to volume: {moved}", flush=True)
        shutil.rmtree(ASSETS_UPLOADS)

    # 3) делаем ссылку assets/uploads -> /app/data/uploads
    ASSETS_UPLOADS.parent.mkdir(parents=True, exist_ok=True)

    if ASSETS_UPLOADS.is_symlink() or ASSETS_UPLOADS.exists():
        try:
            ASSETS_UPLOADS.unlink()
        except IsADirectoryError:
            shutil.rmtree(ASSETS_UPLOADS)

    ASSETS_UPLOADS.symlink_to(DATA_UPLOADS, target_is_directory=True)
    print(f"[uploads] linked {ASSETS_UPLOADS} -> {DATA_UPLOADS}", flush=True)


ensure_uploads_link()

os.execv(sys.executable, [sys.executable, "main.py"])
