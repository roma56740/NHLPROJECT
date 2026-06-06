BROADCAST_MAIN_TEXT = """
<b>📢 Рассылка</b>

Здесь можно отправить красивое сообщение всем игрокам.

Можно добавить фото, а перед отправкой будет предпросмотр.
""".strip()

BROADCAST_TEXT_INPUT = """
<b>✍️ Текст рассылки</b>

Напиши сообщение для игроков.
Можно использовать эмодзи и переносы строк.
""".strip()

BROADCAST_PHOTO_INPUT = """
<b>🖼 Фото для рассылки</b>

Отправь фото одним сообщением или нажми «Без фото».
""".strip()

BROADCAST_PREVIEW_TITLE = "<b>👀 Предпросмотр рассылки</b>\n\n"
BROADCAST_CANCELLED_TEXT = "<b>📢 Рассылка отменена</b>\n\nСообщение не отправлялось игрокам."


def build_broadcast_sent_text(total: int, success: int, failed: int) -> str:
    return f"""
<b>📢 Рассылка завершена</b>

👥 Игроков в списке: <b>{total}</b>
✅ Доставлено: <b>{success}</b>
⚠️ Не доставлено: <b>{failed}</b>
""".strip()
