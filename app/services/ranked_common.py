"""Общие мелочи RANKED MODE: единая ошибка, разделяемая всеми ranked_* модулями без
риска циклических импортов (та же роль, что app/services/war2_common.py у CLAN WAR
2.0 — не переиспользуем War2Error здесь напрямую, чтобы не путать читателя логов
именем чужой фичи в трейсбеке Ranked-кода)."""

from __future__ import annotations


class RankedError(Exception):
    """Единая бизнес-ошибка RANKED MODE. `code` — машиночитаемый, `message` — для игрока."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
