# DNA R5 validation

Проверено локальным smoke-тестом на чистой SQLite базе:

- init_database создаёт коллекцию `dna`;
- схема `cards` принимает OVR 100;
- полный путь 12× NEXT GEN + 3× 99 прошёл до STONE 100;
- промежуточные карты физически удалялись и создавались новые user_cards;
- в конце остался отдельный экземпляр Mark Stone 100;
- dna_craft_logs сохранил все 8 операций полного smoke-пути;
- PRAGMA foreign_key_check: без нарушений;
- DNA event render успешно генерируется;
- `python -m compileall -q app`: OK.

Aiogram-runtime в этой среде не запускался, потому что пакет aiogram здесь не установлен.
