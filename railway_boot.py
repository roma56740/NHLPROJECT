import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path.cwd()
PROJECT_UPLOADS = ROOT / "assets" / "uploads"
PERSISTENT_UPLOADS = Path(os.getenv("UPLOADS_PERSIST_DIR", "/app/data/uploads"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/app/data/nhl_bot.sqlite3"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")


def merge_dir(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_dir():
        return

    dst.mkdir(parents=True, exist_ok=True)

    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(item, target)


def setup_uploads_link() -> None:
    PERSISTENT_UPLOADS.mkdir(parents=True, exist_ok=True)
    PROJECT_UPLOADS.parent.mkdir(parents=True, exist_ok=True)

    if PROJECT_UPLOADS.exists() and not PROJECT_UPLOADS.is_symlink():
        merge_dir(PROJECT_UPLOADS, PERSISTENT_UPLOADS)
        shutil.rmtree(PROJECT_UPLOADS)

    if not PROJECT_UPLOADS.exists():
        try:
            PROJECT_UPLOADS.symlink_to(PERSISTENT_UPLOADS, target_is_directory=True)
            print(f"[uploads] linked {PROJECT_UPLOADS} -> {PERSISTENT_UPLOADS}", flush=True)
        except Exception as exc:
            print(f"[uploads] symlink failed, using normal folder: {exc}", flush=True)
            PROJECT_UPLOADS.mkdir(parents=True, exist_ok=True)


def parse_file_id(image_path: str) -> str | None:
    name = Path(image_path).name
    stem = Path(name).stem

    parts = stem.split("_", 4)
    if len(parts) < 5:
        return None

    file_id = parts[4].strip()
    if not file_id:
        return None

    return file_id


def telegram_json(method: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}?{query}"

    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download_telegram_file(file_id: str, target: Path) -> bool:
    try:
        info = telegram_json("getFile", {"file_id": file_id})
        if not info.get("ok"):
            print(f"[restore] getFile failed: {file_id} {info}", flush=True)
            return False

        file_path = info["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

        target.parent.mkdir(parents=True, exist_ok=True)

        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()

        if not data:
            return False

        target.write_bytes(data)
        return True

    except Exception as exc:
        print(f"[restore] failed {target}: {exc}", flush=True)
        return False


def collect_image_paths() -> list[str]:
    if not DATABASE_PATH.exists():
        print(f"[restore] db not found: {DATABASE_PATH}", flush=True)
        return []

    result: set[str] = set()

    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    tables = [
        ("cards", "image_path"),
        ("packs", "image_path"),
        ("events", "image_path"),
        ("team_divisions", "image_path"),
        ("animation_assets", "image_path"),
    ]

    for table, column in tables:
        try:
            rows = cur.execute(
                f"""
                SELECT {column} AS image_path
                FROM {table}
                WHERE {column} IS NOT NULL
                  AND TRIM({column}) != ''
                """
            ).fetchall()

            for row in rows:
                path = str(row["image_path"]).strip().replace("\\", "/")
                if path.startswith("assets/uploads/"):
                    result.add(path)

        except Exception as exc:
            print(f"[restore] skip {table}.{column}: {exc}", flush=True)

    con.close()
    return sorted(result)


def restore_missing_uploads() -> None:
    if not BOT_TOKEN:
        print("[restore] BOT_TOKEN is missing, skip restore", flush=True)
        return

    paths = collect_image_paths()
    if not paths:
        print("[restore] no image paths found", flush=True)
        return

    missing = []
    for rel_path in paths:
        target = ROOT / rel_path
        if not target.exists():
            missing.append(rel_path)

    print(f"[restore] total paths: {len(paths)}, missing: {len(missing)}", flush=True)

    restored = 0
    failed = 0

    for rel_path in missing:
        file_id = parse_file_id(rel_path)
        if not file_id:
            failed += 1
            continue

        target = ROOT / rel_path

        if download_telegram_file(file_id, target):
            restored += 1
            print(f"[restore] restored {rel_path}", flush=True)
        else:
            failed += 1

        time.sleep(0.05)

    print(f"[restore] done. restored={restored}, failed={failed}", flush=True)


def main() -> None:
    setup_uploads_link()
    restore_missing_uploads()

    os.execv(sys.executable, [sys.executable, "main.py"])


if __name__ == "__main__":
    main()
