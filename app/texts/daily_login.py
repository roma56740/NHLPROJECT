from app.services.daily_login import DailyClaimResult, DailyRewardDef, DailyStatus

DAILY_BUTTON_TEXT = "📅 Ежедневный вход"
ADMIN_DAILY_BUTTON_TEXT = "📅 Ежедневный вход"


def format_timer(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def reward_line(reward: DailyRewardDef) -> str:
    parts = []
    if reward.coins > 0:
        parts.append(f"🪙 {reward.coins:,}".replace(",", " "))
    if reward.rubles > 0:
        parts.append(f"💵 {reward.rubles:,}".replace(",", " "))
    if reward.pack_name:
        parts.append(f"🎁 {reward.pack_name}")
    return " + ".join(parts) if parts else "—"


def build_daily_text(status: DailyStatus) -> str:
    lines = ["<b>📅 Ежедневный вход</b>", ""]
    lines.append(f"🔥 Серия входов: <b>{status.streak}</b> дн.")
    lines.append("")

    for reward in status.ladder:
        mark = "➡️" if reward.day == status.next_day and status.can_claim else "  "
        lines.append(f"{mark} День {reward.day}: {reward_line(reward)}")

    lines.append("")
    if status.can_claim:
        lines.append("🎉 Награда за сегодня готова — забирай!")
    else:
        lines.append(f"⏳ Следующая награда через <b>{format_timer(status.seconds_until_next)}</b>")

    return "\n".join(lines)


def build_daily_claim_text(result: DailyClaimResult) -> str:
    parts = []
    if result.coins > 0:
        parts.append(f"🪙 Coins: <b>+{result.coins:,}</b>".replace(",", " "))
    if result.rubles > 0:
        parts.append(f"💵 Рубли: <b>+{result.rubles:,}</b>".replace(",", " "))
    if result.pack_name:
        parts.append(f"🎁 Пак: <b>{result.pack_name}</b>")
    body = "\n".join(parts) if parts else "—"

    return (
        f"<b>🎉 Награда получена!</b>\n\n"
        f"День {result.day} · серия {result.streak} дн.\n\n"
        f"{body}"
    )


ADMIN_DAILY_MAIN_TEXT = """
<b>📅 Ежедневный вход — награды</b>

Настрой награды по дням серии (цикл из 7 дней). Игрок получает награду раз в сутки; при пропуске дня серия сбрасывается.

Выбери день для редактирования.
""".strip()


def build_admin_daily_text(ladder: list[DailyRewardDef]) -> str:
    lines = ["<b>📅 Ежедневный вход — награды</b>", ""]
    for reward in ladder:
        lines.append(f"День {reward.day}: {reward_line(reward)}")
    lines.append("")
    lines.append("Выбери день ниже, чтобы изменить награду.")
    return "\n".join(lines)


def build_admin_day_text(reward: DailyRewardDef) -> str:
    pack = reward.pack_name or "нет"
    return (
        f"<b>📅 День {reward.day}</b>\n\n"
        f"🪙 Coins: <b>{reward.coins:,}</b>\n"
        f"💵 Рубли: <b>{reward.rubles}</b>\n"
        f"🎁 Пак: <b>{pack}</b>\n\n"
        f"Что изменить?"
    ).replace(",", " ")
