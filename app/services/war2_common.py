"""Общие мелочи CLAN WAR 2.0: единая ошибка, разделяемая всеми war2_* модулями без
риска циклических импортов (war2_draft/war2_modes/war2_cosmetics/war2_core все читают
только отсюда, друг друга — по минимуму и однонаправленно: core -> modes -> draft)."""

from __future__ import annotations


class War2Error(Exception):
    """Единая бизнес-ошибка CLAN WAR 2.0. `code` — машиночитаемый, `message` — для игрока."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
