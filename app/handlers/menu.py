from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.inline import build_back_to_menu_keyboard
from app.keyboards.reply import (
    ADMIN_MAIN_TEXTS,
    USER_MAIN_TEXTS,
    build_admin_main_keyboard,
    build_user_main_keyboard,
)
from app.utils.messages import safe_delete_callback_message
from app.utils.users import is_admin


router = Router()


USER_SECTION_TEXTS: dict[str, str] = {
    "🏠 Главная": "<b>Главная</b>\n\nЗдесь будет краткая сводка профиля: баланс, лига, OVR состава, активные события и быстрые действия.",
    "🏒 Играть": "<b>Играть</b>\n\nЗдесь будет поиск соперника, матч против игрока, матч против бота и история матчей.",
    "🃏 Карты": "<b>Карты</b>\n\nЗдесь будет коллекция карточек, поиск, фильтры, сортировка, просмотр и быстрая продажа.",
    "🧩 Состав": "<b>Состав</b>\n\nЗдесь будет выбор 1 вратаря, 2 защитников, 3 нападающих, расчет OVR и химии.",
    "🎁 Паки": "<b>Паки</b>\n\nЗдесь будут мои паки, открытие паков, паки с несколькими картами и история открытий.",
    "🛒 Магазин": "<b>Магазин</b>\n\nЗдесь будут покупки за Coins, Energy и Rank-point, постоянные и временные товары.",
    "🎯 Задания": "<b>Задания</b>\n\nЗдесь будут ежедневные и сезонные задания, прогресс и получение наград.",
    "🎟 Hockey Pass": "<b>Hockey Pass</b>\n\nЗдесь будет прогресс по 40 уровням, бесплатная ветка и Premium-награды.",
    "🏆 Рейтинг": "<b>Рейтинг</b>\n\nЗдесь будут лиги NCAA, AHL, NHL, OLYMPICS, очки и таблица лидеров.",
    "🤝 Сообщество": "<b>Сообщество</b>\n\nЗдесь будут обмены, кланы и просмотр профилей других игроков.",
    "👤 Профиль": "<b>Профиль</b>\n\nЗдесь будут никнейм, статистика, валюты, победы, поражения и настройки приватности.",
}


ADMIN_SECTION_TEXTS: dict[str, str] = {
    "📊 Админ-панель": "<b>Админ-панель</b>\n\nЗдесь будет сводка по игрокам, матчам, пакам, экономике и активности.",
    "🃏 Карточки": "<b>Карточки</b>\n\nЗдесь будет добавление, редактирование, отключение, поиск, фильтры и импорт карточек.",
    "🎁 Паки": "<b>Паки</b>\n\nЗдесь будет создание паков, настройка количества карт, шансов, гарантий, цены и валюты.",
    "🛒 Магазин": "<b>Магазин</b>\n\nЗдесь будут товары, постоянные паки, недельная ротация и специальные предложения.",
    "👥 Пользователи": "<b>Пользователи</b>\n\nЗдесь будет поиск игроков, выдача валют, карт, паков, бан и просмотр истории.",
    "🎟 Hockey Pass": "<b>Hockey Pass</b>\n\nЗдесь будет настройка уровней, BP Points, бесплатных и Premium-наград.",
    "🎯 Задания": "<b>Задания</b>\n\nЗдесь будет управление ежедневными и сезонными заданиями.",
    "🏆 Лиги и рейтинг": "<b>Лиги и рейтинг</b>\n\nЗдесь будет настройка NCAA, AHL, NHL, OLYMPICS, очков и rank-point.",
    "🧪 Химия": "<b>Химия</b>\n\nЗдесь будет настройка сезонных комбинаций по коллекции, стране и команде.",
    "🎪 События": "<b>События</b>\n\nЗдесь будут DEAD LEGENDS, сезонные события, прогресс и награды.",
    "💱 Валюты": "<b>Валюты</b>\n\nЗдесь будет управление Coins, Energy, Rank-point и дополнительными валютами.",
    "🤝 Кланы": "<b>Кланы</b>\n\nЗдесь будет модерация кланов, участников, приглашений и рейтинга.",
    "🔁 Обмены": "<b>Обмены</b>\n\nЗдесь будет история обменов, спорные обмены и trade lock.",
    "🛡 Безопасность": "<b>Безопасность</b>\n\nЗдесь будет антиавтокликер, капча и подозрительная активность.",
    "📢 Рассылка": "<b>Рассылка</b>\n\nЗдесь будет отправка сообщений игрокам с предпросмотром и подтверждением.",
    "⚙️ Настройки": "<b>Настройки</b>\n\nЗдесь будут сезон, стартовые ресурсы, тексты бота, админы и общие настройки.",
}


@router.message(F.text.in_(USER_MAIN_TEXTS | ADMIN_MAIN_TEXTS))
async def main_menu_button(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    text = message.text or ""

    if text in ADMIN_MAIN_TEXTS and not is_admin(user_id):
        await message.answer("Раздел доступен только администратору.")
        return

    section_text = ADMIN_SECTION_TEXTS.get(text) or USER_SECTION_TEXTS.get(text)

    if section_text is None:
        return

    await message.answer(
        section_text,
        reply_markup=build_back_to_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:main")
async def back_to_main_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else None
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    chat_id = message.chat.id

    await safe_delete_callback_message(callback)

    if is_admin(user_id):
        await callback.bot.send_message(
            chat_id=chat_id,
            text="Главное меню админ-панели.",
            reply_markup=build_admin_main_keyboard(),
        )
    else:
        await callback.bot.send_message(
            chat_id=chat_id,
            text="Главное меню.",
            reply_markup=build_user_main_keyboard(),
        )

    await callback.answer()
