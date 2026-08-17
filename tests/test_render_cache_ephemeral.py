from __future__ import annotations

import os
import time
from pathlib import Path

from app.services import cache_cleanup
from app.services import renders


def test_renderer_and_cleaner_use_same_ephemeral_cache_root():
    assert renders.RENDER_DIR == cache_cleanup.RENDER_CACHE
    normalized = str(renders.RENDER_DIR).replace('\\', '/')
    assert '/data/render_cache' not in normalized


def test_remove_render_cache_file_never_deletes_outside_root(tmp_path: Path):
    root = tmp_path / 'cache'
    root.mkdir()
    inside = root / 'lineup_1.png'
    outside = tmp_path / 'permanent.png'
    inside.write_bytes(b'x')
    outside.write_bytes(b'x')

    assert cache_cleanup.remove_render_cache_file(inside, root=root) is True
    assert not inside.exists()
    assert cache_cleanup.remove_render_cache_file(outside, root=root) is False
    assert outside.exists()


def test_cleanup_uses_short_ttl_for_transient_and_long_ttl_for_black_market(tmp_path: Path, monkeypatch):
    root = tmp_path / 'render_cache'
    preview_dir = root / 'black_market_previews'
    preview_dir.mkdir(parents=True)
    transient = root / 'lineup_old.png'
    preview = preview_dir / 'pool_item_1.png'
    transient.write_bytes(b'x' * 10)
    preview.write_bytes(b'x' * 10)

    # 1 hour old: transient (>30m) must go, BM preview (<12h) must stay.
    old = time.time() - 60 * 60
    os.utime(transient, (old, old))
    os.utime(preview, (old, old))

    monkeypatch.setattr(cache_cleanup, 'MAX_BYTES', 10**9)
    removed, freed, current = cache_cleanup.cleanup_render_cache(root)
    assert removed == 1
    assert freed == 10
    assert not transient.exists()
    assert preview.exists()
    assert current == 10
