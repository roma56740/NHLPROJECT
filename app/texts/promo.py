from html import escape

from app.services.promo import PromoCodeInfo, PromoReward

ADMIN_PROMO_BUTTON_TEXT = "🎫 Промокоды"


PROMO_ENTER_TEXT = """
<b>🎫 Промокод</b>

Отправь промокод сообщением, чтобы получить награду.
""".strip()


def build_promo_success_text(reward: PromoReward) -> str:
    parts = []
    if reward.coins > 0:
        parts.append(f"🪙 Coins: <b>+{reward.coins:,}</b>".replace(",", " "))
    if reward.rubles > 0:
        parts.append(f"💵 Рубли: <b>+{reward.rubles:,}</b>".replace(",", " "))
    if reward.bp_points > 0:
        parts.append(f"🎟 BP Points: <b>+{reward.bp_points}</b>")
    if reward.pack_name:
        parts.append(f"🎁 Пак: <b>{escape(reward.pack_name, quote=False)}</b>")
    body = "\n".join(parts) if parts else "—"
    return f"<b>🎉 Промокод активирован!</b>\n\n{body}"


# ---------------------------------------------------------------------------
# Админ
# ---------------------------------------------------------------------------

ADMIN_PROMO_MAIN_TEXT = """
<b>🎫 Промокоды</b>

Создавай промокоды с наградами и лимитами активаций. Выбери промокод для настройки или создай новый.
""".strip()

ADMIN_PROMO_CREATE_CODE_TEXT = """
<b>🎫 Новый промокод — шаг 1 из 4</b>

Введи код (3–32 символа, буквы и цифры). Например: WELCOME2026.
""".strip()

ADMIN_PROMO_CREATE_COINS_TEXT = "<b>🎫 Шаг 2 из 4</b>\n\nВведи количество Coins (0 — без монет)."
ADMIN_PROMO_CREATE_RUBLES_TEXT = "<b>🎫 Шаг 3 из 4</b>\n\nВведи количество Рублей (0 — без рублей)."
ADMIN_PROMO_CREATE_MAX_TEXT = "<b>🎫 Шаг 4 из 4</b>\n\nОбщий лимит активаций (0 — без лимита)."


def promo_summary_line(promo: PromoCodeInfo) -> str:
    status = "🟢" if promo.active else "🔴"
    used = f"{promo.activations_count}/{promo.max_activations}" if promo.max_activations > 0 else f"{promo.activations_count}/∞"
    return f"{status} {promo.code} · {used}"


def build_admin_promo_list_text(promos: list[PromoCodeInfo]) -> str:
    if not promos:
        return ADMIN_PROMO_MAIN_TEXT + "\n\nПромокодов пока нет."
    lines = ["<b>🎫 Промокоды</b>", ""]
    for promo in promos:
        lines.append(promo_summary_line(promo))
    lines.append("")
    lines.append("Выбери промокод для настройки.")
    return "\n".join(lines)


def build_admin_promo_text(promo: PromoCodeInfo) -> str:
    reward_parts = []
    if promo.coins > 0:
        reward_parts.append(f"🪙 {promo.coins:,}".replace(",", " "))
    if promo.rubles > 0:
        reward_parts.append(f"💵 {promo.rubles}")
    if promo.bp_points > 0:
        reward_parts.append(f"🎟 BP {promo.bp_points}")
    if promo.pack_name:
        reward_parts.append(f"🎁 {escape(promo.pack_name, quote=False)}")
    reward = " + ".join(reward_parts) if reward_parts else "—"

    max_act = str(promo.max_activations) if promo.max_activations > 0 else "∞"
    per_user = str(promo.per_user_limit) if promo.per_user_limit > 0 else "∞"
    expires = promo.expires_at or "нет"
    status = "включён 🟢" if promo.active else "отключён 🔴"

    return (
        f"<b>🎫 {escape(promo.code, quote=False)}</b>\n\n"
        f"Статус: <b>{status}</b>\n"
        f"Награда: {reward}\n"
        f"Активаций: <b>{promo.activations_count}</b> из {max_act}\n"
        f"На игрока: <b>{per_user}</b>\n"
        f"Действует до: <b>{expires}</b>\n\n"
        f"Что изменить?"
    )
