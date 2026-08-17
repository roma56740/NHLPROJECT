# R15 — Render cache / Railway Volume fix

## Исправлено

- Все runtime-рендеры теперь используют единый `RENDER_CACHE_PATH` (по умолчанию `/app/cache/render_cache`) вне persistent `/app/data` Railway Volume.
- `app/services/renders.py` больше не пишет PNG в `/app/data/render_cache`.
- Black Market previews перенесены в `/app/cache/render_cache/black_market_previews`.
- Одноразовые menu/lineup/collection/card/DNA/Ranked/Clan War/match/free-card/admin-preview рендеры удаляются сразу после успешной или неуспешной попытки отправки в Telegram (`finally`).
- Удаление после отправки защищено: helper удаляет только файлы, находящиеся внутри render-cache, и никогда не трогает постоянные uploads/assets.
- Страховочный TTL обычного render-cache: 30 минут. Black Market preview: 12 часов. Общий cap остаётся 250 MB.
- Cleaner рекурсивный, поэтому чистит и вложенные директории.
- При старте `railway_boot.py` по-прежнему удаляет legacy `/app/data/render_cache`, освобождая уже накопившееся место на Volume.

## Проверки

- `python -m compileall` — OK.
- Unit tests на единый cache root, безопасное удаление и разные TTL — OK.
