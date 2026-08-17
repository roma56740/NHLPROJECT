from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)
# Раздел 12 ТЗ по надёжности: render_cache — временные данные, не должен занимать
# постоянный Railway Volume (/app/data). По умолчанию — /app/cache (пересоздаётся
# каждый деплой, т.к. лежит вне volume); переопределяется RENDER_CACHE_PATH при
# необходимости (например для локальной разработки).
RENDER_CACHE = Path(os.getenv('RENDER_CACHE_PATH', '/app/cache/render_cache'))
MAX_BYTES = 250 * 1024 * 1024
TTL_SECONDS = 2 * 60 * 60
INTERVAL_SECONDS = 30 * 60


def cleanup_render_cache(path: Path = RENDER_CACHE) -> tuple[int, int, int]:
    removed = 0
    freed = 0
    try:
        path.mkdir(parents=True, exist_ok=True)
        now = time.time()
        files = []
        total = 0
        for item in path.rglob('*'):
            if not item.is_file() or item.is_symlink():
                continue
            try:
                stat = item.stat()
            except OSError:
                continue
            files.append((stat.st_mtime, stat.st_size, item))
            total += stat.st_size

        for mtime, size, item in list(files):
            if now - mtime <= TTL_SECONDS:
                continue
            try:
                item.unlink()
                removed += 1
                freed += size
                total -= size
                files.remove((mtime, size, item))
            except OSError:
                logger.exception('[render_cache] failed_to_remove=%s', item)

        if total > MAX_BYTES:
            for _mtime, size, item in sorted(files, key=lambda row: row[0]):
                if total <= MAX_BYTES:
                    break
                try:
                    item.unlink()
                    removed += 1
                    freed += size
                    total -= size
                except OSError:
                    logger.exception('[render_cache] failed_to_remove=%s', item)

        for directory in sorted((p for p in path.rglob('*') if p.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        logger.info('[render_cache] removed=%s', removed)
        logger.info('[render_cache] freed_mb=%.2f', freed / 1024 / 1024)
        logger.info('[render_cache] current_mb=%.2f', max(total, 0) / 1024 / 1024)
        return removed, freed, max(total, 0)
    except Exception:
        logger.exception('[render_cache] cleanup failed')
        return removed, freed, 0


async def render_cache_cleanup_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(cleanup_render_cache)
        except Exception:
            logger.exception('[render_cache] background cleanup failed')
        await asyncio.sleep(INTERVAL_SECONDS)
