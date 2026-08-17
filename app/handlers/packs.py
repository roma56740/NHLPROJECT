from asyncio import sleep
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message

from app.keyboards.packs import (
    ADMIN_PACKS_PER_PAGE,
    PACK_HISTORY_PER_PAGE,
    USER_PACKS_PER_PAGE,
    build_admin_pack_cancel_keyboard,
    build_admin_pack_confirm_keyboard,
    build_admin_pack_available_cards_keyboard,
    build_admin_pack_cards_keyboard,
    build_admin_pack_currency_keyboard,
    build_admin_pack_profile_keyboard,
    build_admin_pack_shop_keyboard,
    build_admin_packs_list_keyboard,
    build_admin_packs_main_keyboard,
    build_pack_history_keyboard,
    build_pack_opening_result_keyboard,
    build_user_pack_inventory_keyboard,
    build_user_pack_profile_keyboard,
    build_user_packs_main_keyboard,
)

from app.services.renders import render_card_profile_image
from app.services.cache_cleanup import remove_render_cache_file
from app.services.packs import (
    PackDraft,
    add_card_to_pack,
    create_admin_pack,
    get_admin_pack_details,
    get_admin_packs_page,
    get_pack_animation_meta,
    get_pack_history_page,
    get_pack_available_cards_page,
    get_pack_cards_page,
    get_pack_info,
    get_user_pack_inventory_page,
    get_user_pack_quantity,
    open_user_pack,
    parse_rarity_chances,
    remove_card_from_pack,
    toggle_pack_active,
    toggle_pack_shop,
    update_pack_cards_count,
    update_pack_image_path,
    update_pack_price,
    update_pack_rarity_chances,
    update_pack_text_field,
)
from app.services.users import get_player_profile_by_telegram_id
from app.states.packs import AdminPackStates
from app.texts.packs import (
    ADMIN_PACK_BAD_COUNT_TEXT,
    ADMIN_PACK_BAD_DESCRIPTION_TEXT,
    ADMIN_PACK_BAD_IMAGE_TEXT,
    ADMIN_PACK_ANIMATION_TEXT,
    ADMIN_PACK_BAD_ANIMATION_TEXT,
    ADMIN_PACK_BAD_NAME_TEXT,
    ADMIN_PACK_BAD_PRICE_TEXT,
    ADMIN_PACK_CANCEL_TEXT,
    ADMIN_PACK_CARD_SEARCH_TEXT,
    ADMIN_PACK_COUNT_TEXT,
    ADMIN_PACK_CURRENCY_TEXT,
    ADMIN_PACK_DESCRIPTION_TEXT,
    ADMIN_PACK_IMAGE_TEXT,
    ADMIN_PACK_NAME_TEXT,
    ADMIN_PACK_ODDS_TEXT,
    ADMIN_PACK_PRICE_TEXT,
    ADMIN_PACK_SEARCH_TEXT,
    ADMIN_PACK_SHOP_TEXT,
    ADMIN_PACKS_MAIN_TEXT,
    USER_PACKS_MAIN_TEXT,
    build_admin_pack_available_cards_text,
    build_admin_pack_cards_text,
    build_admin_pack_profile_text,
    build_admin_packs_page_text,
    build_pack_draft_text,
    build_pack_history_text,
    build_pack_animation_reveal_text,
    build_pack_opening_error_text,
    build_pack_opening_finish_text,
    build_pack_opening_result_text,
    build_pack_opening_start_text,
    build_pack_reward_caption,
    build_user_pack_inventory_text,
    build_user_pack_profile_text,
)
from app.utils.messages import safe_delete_callback_message, safe_delete_message
from app.utils.users import is_admin


router = Router()

PACKS_BUTTON_TEXT = "🎁 Паки"
PACK_IMAGES_DIR = Path("assets/uploads/packs")
PACK_ANIMATIONS_DIR = PACK_IMAGES_DIR / "animations"
PACK_ANIMATION_SECONDS = 10
PACK_MULTI_REWARD_REVEAL_SECONDS = 2
ADMIN_PACK_SEARCH_CACHE: dict[int, str] = {}
ADMIN_PACK_CARD_SEARCH_CACHE: dict[tuple[int, int], str] = {}


async def _build_pack_videos_screen(page: int = 1) -> tuple[str, InlineKeyboardMarkup]:
    packs_page = await get_admin_packs_page(page=page, per_page=ADMIN_PACKS_PER_PAGE)
    lines = [
        f"<b>🎬 Видео открытия паков</b> · {packs_page.page}/{packs_page.pages_count}",
        "",
        "Выбери пак. На его экране можно загрузить, посмотреть, выключить или удалить видео.",
        "",
    ]
    keyboard: list[list[InlineKeyboardButton]] = []
    for pack in packs_page.packs:
        meta = await get_pack_animation_meta(pack.id)
        if meta and meta.video_path:
            status = "✅ включено" if meta.enabled else "⏸ выключено"
        else:
            status = "➕ не загружено"
        lines.append(f"• {pack.name}: {status}")
        keyboard.append([
            InlineKeyboardButton(
                text=f"🎬 {pack.name} · {status}",
                callback_data=f"admin_packs:view:{pack.id}:{packs_page.page}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if packs_page.page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_packs:videos:{packs_page.page - 1}"))
    if packs_page.page < packs_page.pages_count:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_packs:videos:{packs_page.page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="➕ Создать пак", callback_data="admin_packs:add")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Ко всем пакам", callback_data="admin_packs:main")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


async def edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    try:
        if message.photo:
            await message.delete()
            await callback.bot.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=reply_markup,
            )
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await safe_delete_callback_message(callback)
        await callback.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
        )


async def get_current_player(callback: CallbackQuery):
    profile = await get_player_profile_by_telegram_id(callback.from_user.id)

    if profile is None:
        await callback.answer("Открой профиль через /start", show_alert=True)
        return None

    return profile


async def answer_callback_admin_only(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True

    await callback.answer("Раздел доступен только администрации", show_alert=True)
    return False


async def show_inventory_page(callback: CallbackQuery, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    inventory_page = await get_user_pack_inventory_page(
        user_id=profile.id,
        page=page,
        per_page=USER_PACKS_PER_PAGE,
    )

    await edit_or_send(
        callback,
        build_user_pack_inventory_text(inventory_page),
        reply_markup=build_user_pack_inventory_keyboard(
            packs=inventory_page.packs,
            page=inventory_page.page,
            pages_count=inventory_page.pages_count,
        ),
    )


async def show_pack_profile(callback: CallbackQuery, pack_id: int, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    pack = await get_pack_info(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    quantity = await get_user_pack_quantity(user_id=profile.id, pack_id=pack.id)
    text = build_user_pack_profile_text(pack, quantity)
    keyboard = build_user_pack_profile_keyboard(pack_id=pack.id, page=page, quantity=quantity)
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    image_path = Path(pack.image_path) if pack.image_path else None

    if image_path and image_path.exists():
        await safe_delete_callback_message(callback)
        await callback.bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(image_path),
            caption=text,
            reply_markup=keyboard,
        )
        return

    await edit_or_send(callback, text, reply_markup=keyboard)


async def show_history_page(callback: CallbackQuery, page: int) -> None:
    profile = await get_current_player(callback)

    if profile is None:
        return

    history_page = await get_pack_history_page(
        user_id=profile.id,
        page=page,
        per_page=PACK_HISTORY_PER_PAGE,
    )

    await edit_or_send(
        callback,
        build_pack_history_text(history_page),
        reply_markup=build_pack_history_keyboard(
            page=history_page.page,
            pages_count=history_page.pages_count,
        ),
    )


async def show_admin_packs_page(callback: CallbackQuery, page: int, search: str | None = None) -> None:
    packs_page = await get_admin_packs_page(
        page=page,
        per_page=ADMIN_PACKS_PER_PAGE,
        search=search,
    )

    await edit_or_send(
        callback,
        build_admin_packs_page_text(packs_page),
        reply_markup=build_admin_packs_list_keyboard(
            packs=packs_page.packs,
            page=packs_page.page,
            pages_count=packs_page.pages_count,
            search=packs_page.search,
        ),
    )


async def show_admin_pack_profile(callback: CallbackQuery, pack_id: int, page: int) -> None:
    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    from app.services.packs import get_pack_animation_meta

    animation_meta = await get_pack_animation_meta(pack_id)
    text = build_admin_pack_profile_text(pack, animation_meta=animation_meta)
    keyboard = build_admin_pack_profile_keyboard(
        pack_id=pack.id,
        page=page,
        active=pack.active,
        shop=pack.is_shop_available,
        animation_enabled=animation_meta.enabled if animation_meta else True,
        has_animation=bool(animation_meta and animation_meta.video_path),
    )
    message = callback.message

    if not isinstance(message, Message):
        await callback.answer()
        return

    image_path = Path(pack.image_path) if pack.image_path else None

    if image_path and image_path.exists():
        await safe_delete_callback_message(callback)
        await callback.bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(image_path),
            caption=text,
            reply_markup=keyboard,
        )
        return

    await edit_or_send(callback, text, reply_markup=keyboard)


async def send_admin_pack_profile_after_input(message: Message, pack_id: int, page: int, state: FSMContext) -> None:
    data = await state.get_data()
    panel_chat_id = data.get("pack_panel_chat_id")
    panel_message_id = data.get("pack_panel_message_id")

    if panel_chat_id and panel_message_id:
        try:
            await message.bot.delete_message(chat_id=panel_chat_id, message_id=panel_message_id)
        except Exception:
            pass

    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await message.answer(ADMIN_PACKS_MAIN_TEXT, reply_markup=build_admin_packs_main_keyboard())
        return

    from app.services.packs import get_pack_animation_meta

    animation_meta = await get_pack_animation_meta(pack_id)
    text = build_admin_pack_profile_text(pack, animation_meta=animation_meta)
    keyboard = build_admin_pack_profile_keyboard(
        pack_id=pack.id,
        page=page,
        active=pack.active,
        shop=pack.is_shop_available,
        animation_enabled=animation_meta.enabled if animation_meta else True,
        has_animation=bool(animation_meta and animation_meta.video_path),
    )
    image_path = Path(pack.image_path) if pack.image_path else None

    if image_path and image_path.exists():
        sent = await message.answer_photo(
            photo=FSInputFile(image_path),
            caption=text,
            reply_markup=keyboard,
        )
    else:
        sent = await message.answer(text, reply_markup=keyboard)

    await state.update_data(pack_panel_chat_id=sent.chat.id, pack_panel_message_id=sent.message_id)


async def save_pack_image(message: Message) -> str | None:
    PACK_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    now_value = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id if message.from_user else 0

    if message.photo:
        photo = message.photo[-1]
        file_name = f"pack_{now_value}_{user_id}_{photo.file_unique_id}.jpg"
        file_path = PACK_IMAGES_DIR / file_name
        await message.bot.download(photo, destination=file_path)
        return file_path.as_posix()

    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        suffix = Path(message.document.file_name or "pack.png").suffix.lower()

        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".png"

        file_name = f"pack_{now_value}_{user_id}_{message.document.file_unique_id}{suffix}"
        file_path = PACK_IMAGES_DIR / file_name
        await message.bot.download(message.document, destination=file_path)
        return file_path.as_posix()

    return None


@dataclass(frozen=True)
class SavedPackAnimation:
    path: str
    duration_seconds: int | None
    file_size: int | None
    file_id: str
    file_unique_id: str


async def save_pack_animation_video(message: Message) -> SavedPackAnimation | None:
    """Persist an admin-uploaded pack-opening video in the Railway uploads volume,
    AND keep Telegram's own file_id/file_unique_id (ТЗ: "Не сохраняй единственную
    копию видео только во временную папку контейнера") — the local file is what
    bot.send_video() reads today, file_id is a durable secondary reference."""
    PACK_ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)
    now_value = datetime.now().strftime("%Y%m%d_%H%M%S")
    user_id = message.from_user.id if message.from_user else 0

    downloadable = None
    unique_id = "video"
    suffix = ".mp4"
    duration: int | None = None
    file_size: int | None = None

    if message.video:
        downloadable = message.video
        unique_id = message.video.file_unique_id
        duration = message.video.duration
        file_size = message.video.file_size
        original_suffix = Path(message.video.file_name or "opening.mp4").suffix.lower()
        if original_suffix in {".mp4", ".mov", ".webm", ".m4v"}:
            suffix = original_suffix
    elif message.animation:
        downloadable = message.animation
        unique_id = message.animation.file_unique_id
        duration = message.animation.duration
        file_size = message.animation.file_size
        original_suffix = Path(message.animation.file_name or "opening.mp4").suffix.lower()
        if original_suffix in {".mp4", ".mov", ".webm", ".m4v"}:
            suffix = original_suffix
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("video/"):
        downloadable = message.document
        unique_id = message.document.file_unique_id
        file_size = message.document.file_size
        original_suffix = Path(message.document.file_name or "opening.mp4").suffix.lower()
        if original_suffix not in {".mp4", ".mov", ".webm", ".m4v"}:
            return None
        suffix = original_suffix

    if downloadable is None:
        return None

    # Native Telegram video/animation includes duration metadata. Documents do not,
    # so the admin prompt remains the source of truth for uploaded video files.
    if duration is not None and duration > PACK_ANIMATION_SECONDS:
        return None

    file_name = f"opening_{now_value}_{user_id}_{unique_id}{suffix}"
    file_path = PACK_ANIMATIONS_DIR / file_name
    await message.bot.download(downloadable, destination=file_path)
    return SavedPackAnimation(
        path=file_path.as_posix(),
        duration_seconds=duration,
        file_size=file_size,
        file_id=downloadable.file_id,
        file_unique_id=unique_id,
    )


def validate_pack_name(value: str) -> bool:
    return 2 <= len(value.strip()) <= 50


def validate_pack_description(value: str) -> bool:
    return 2 <= len(value.strip()) <= 300


def parse_positive_int(value: str, min_value: int, max_value: int) -> int | None:
    try:
        number = int(value.strip().replace(" ", ""))
    except ValueError:
        return None

    if number < min_value or number > max_value:
        return None

    return number


async def delete_saved_pack_panel(state: FSMContext, bot) -> None:
    data = await state.get_data()
    panel_chat_id = data.get("pack_panel_chat_id")
    panel_message_id = data.get("pack_panel_message_id")

    if not panel_chat_id or not panel_message_id:
        return

    try:
        await bot.delete_message(chat_id=panel_chat_id, message_id=panel_message_id)
    except Exception:
        pass


async def send_pack_prompt(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    await delete_saved_pack_panel(state, message.bot)
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(pack_panel_chat_id=sent.chat.id, pack_panel_message_id=sent.message_id)


async def prompt_from_callback(callback: CallbackQuery, state: FSMContext, text: str, reply_markup=None) -> None:
    message = callback.message

    if isinstance(message, Message):
        await state.update_data(pack_panel_chat_id=message.chat.id, pack_panel_message_id=message.message_id)

    await edit_or_send(callback, text, reply_markup=reply_markup)


async def _render_pack_reward_image(reward, *, telegram_user_id: int) -> Path | None:
    try:
        rendered = render_card_profile_image(reward, user_id=telegram_user_id)
        if rendered is not None and rendered.exists():
            return rendered
    except Exception:
        pass

    fallback = Path(reward.image_path) if reward.image_path else None
    if fallback is not None and fallback.exists():
        return fallback
    return None


async def _replace_opening_message_with_reward(
    message: Message,
    *,
    result,
    reward,
    index: int,
    total: int,
    final: bool,
    telegram_user_id: int,
) -> Message:
    image_path = await _render_pack_reward_image(reward, telegram_user_id=telegram_user_id)
    caption = build_pack_animation_reveal_text(result, reward, index, total)
    keyboard = build_pack_opening_result_keyboard() if final else None

    if image_path is not None:
        try:
            edited = await message.edit_media(
                media=InputMediaPhoto(media=FSInputFile(image_path), caption=caption, parse_mode="HTML"),
                reply_markup=keyboard,
            )
            if isinstance(edited, Message):
                return edited
            return message
        except TelegramBadRequest:
            pass
        finally:
            remove_render_cache_file(image_path)

    # Safe fallback for a missing/broken card image: keep the award visible and do
    # not lose the already-committed pack result.
    try:
        await message.delete()
    except Exception:
        pass
    return await message.bot.send_message(
        chat_id=message.chat.id,
        text=caption,
        reply_markup=keyboard,
    )


async def show_pack_opening_result(callback: CallbackQuery, result) -> None:
    """Show one admin-uploaded video, then replace that same message with rewards.

    The pack transaction (and the pack_pending_reveals row, see open_user_pack())
    is already completed by open_user_pack() BEFORE this function ever runs — the
    reward is fixed and cannot be duplicated by this visual layer. This function's
    only job is to deliver that already-decided reward and mark the pending reveal
    completed/failed; if the process restarts mid-flow, resume_pending_pack_reveals()
    (called at boot) finishes any reveal still 'pending'.
    """
    from app.services.packs import attach_reveal_message, get_pack_animation_meta, mark_reveal_completed, mark_reveal_failed

    source_message = callback.message
    if not isinstance(source_message, Message):
        await callback.answer()
        return

    await safe_delete_callback_message(callback)
    animation_meta = await get_pack_animation_meta(result.pack_id)
    video_path = (
        Path(animation_meta.video_path)
        if animation_meta and animation_meta.enabled and animation_meta.video_path
        else None
    )

    try:
        opening_message: Message
        if video_path is not None and video_path.exists():
            opening_message = await callback.bot.send_video(
                chat_id=source_message.chat.id,
                video=FSInputFile(video_path),
                supports_streaming=True,
            )
            await attach_reveal_message(result.opening_id, chat_id=opening_message.chat.id, message_id=opening_message.message_id)
            # Fixed UX contract: the opening phase lasts ten seconds before the same
            # message becomes the revealed card (edit_message_media, not a new message).
            await sleep(PACK_ANIMATION_SECONDS)
        else:
            opening_message = await callback.bot.send_message(
                chat_id=source_message.chat.id,
                text=build_pack_opening_start_text(result),
            )
            await attach_reveal_message(result.opening_id, chat_id=opening_message.chat.id, message_id=opening_message.message_id)

        total_rewards = len(result.rewards)
        if total_rewards == 0:
            try:
                await opening_message.edit_text(
                    build_pack_opening_finish_text(result),
                    reply_markup=build_pack_opening_result_keyboard(),
                )
            except TelegramBadRequest:
                await opening_message.delete()
                await callback.bot.send_message(
                    chat_id=source_message.chat.id,
                    text=build_pack_opening_finish_text(result),
                    reply_markup=build_pack_opening_result_keyboard(),
                )
            await mark_reveal_completed(result.opening_id)
            return

        for index, reward in enumerate(result.rewards, start=1):
            opening_message = await _replace_opening_message_with_reward(
                opening_message,
                result=result,
                reward=reward,
                index=index,
                total=total_rewards,
                final=index == total_rewards,
                telegram_user_id=callback.from_user.id,
            )
            if index < total_rewards:
                await sleep(PACK_MULTI_REWARD_REVEAL_SECONDS)

        await mark_reveal_completed(result.opening_id)
    except Exception as error:
        await mark_reveal_failed(result.opening_id, repr(error))
        raise


async def show_admin_pack_cards_page(callback: CallbackQuery, pack_id: int, list_page: int, back_page: int) -> None:
    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    cards_page = await get_pack_cards_page(pack_id=pack_id, page=list_page, per_page=ADMIN_PACKS_PER_PAGE)
    await edit_or_send(
        callback,
        build_admin_pack_cards_text(cards_page, pack.name),
        reply_markup=build_admin_pack_cards_keyboard(
            pack_id=pack_id,
            list_page=cards_page.page,
            back_page=back_page,
            cards=cards_page.cards,
            pages_count=cards_page.pages_count,
        ),
    )


async def show_admin_available_cards_page(
    callback: CallbackQuery,
    pack_id: int,
    back_page: int,
    card_page: int,
    search: str | None = None,
) -> None:
    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await callback.answer("Пак не найден", show_alert=True)
        return

    cards_page = await get_pack_available_cards_page(
        pack_id=pack_id,
        page=card_page,
        per_page=ADMIN_PACKS_PER_PAGE,
        search=search,
    )
    await edit_or_send(
        callback,
        build_admin_pack_available_cards_text(cards_page, pack.name),
        reply_markup=build_admin_pack_available_cards_keyboard(
            pack_id=pack_id,
            back_page=back_page,
            card_page=cards_page.page,
            pages_count=cards_page.pages_count,
            cards=cards_page.cards,
            search=cards_page.search,
        ),
    )


@router.message(F.text == "🎬 Видео паков")
async def admin_pack_videos_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        await message.answer("Раздел доступен только администрации.")
        return
    await state.clear()
    await safe_delete_message(message)
    text, keyboard = await _build_pack_videos_screen(1)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_packs:videos:"))
async def admin_pack_videos_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return
    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    text, keyboard = await _build_pack_videos_screen(page)
    await edit_or_send(callback, text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.text == PACKS_BUTTON_TEXT)
async def packs_button(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()
    await safe_delete_message(message)

    if is_admin(message.from_user.id):
        await message.answer(
            ADMIN_PACKS_MAIN_TEXT,
            reply_markup=build_admin_packs_main_keyboard(),
        )
        return

    await message.answer(
        USER_PACKS_MAIN_TEXT,
        reply_markup=build_user_packs_main_keyboard(),
    )


@router.callback_query(F.data == "packs:main")
async def packs_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_send(
        callback,
        USER_PACKS_MAIN_TEXT,
        reply_markup=build_user_packs_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("packs:inventory:"))
async def packs_inventory(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_inventory_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("packs:view:"))
async def packs_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await show_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("packs:open:"))
async def packs_open(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    profile = await get_current_player(callback)

    if profile is None:
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])

    result, error = await open_user_pack(user_id=profile.id, pack_id=pack_id)

    if error or result is None:
        await edit_or_send(
            callback,
            build_pack_opening_error_text(error or "Пак не открыт."),
            reply_markup=build_user_packs_main_keyboard(),
        )
        await callback.answer()
        return

    await callback.answer("Открываем пак")
    await show_pack_opening_result(callback, result)


@router.callback_query(F.data.startswith("packs:history:"))
async def packs_history(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_history_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data == "packs:page_info")
async def packs_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")


@router.callback_query(F.data == "admin_packs:main")
async def admin_packs_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await edit_or_send(
        callback,
        ADMIN_PACKS_MAIN_TEXT,
        reply_markup=build_admin_packs_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:list:"))
async def admin_packs_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    await show_admin_packs_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:search_page:"))
async def admin_packs_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    page = int(callback.data.split(":")[-1]) if callback.data else 1
    search = ADMIN_PACK_SEARCH_CACHE.get(callback.from_user.id)
    await show_admin_packs_page(callback, page=page, search=search)
    await callback.answer()


@router.callback_query(F.data == "admin_packs:search")
async def admin_packs_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await state.set_state(AdminPackStates.search)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_SEARCH_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPackStates.search)
async def admin_packs_search_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    search = (message.text or "").strip()
    ADMIN_PACK_SEARCH_CACHE[message.from_user.id] = search
    await safe_delete_message(message)
    await delete_saved_pack_panel(state, message.bot)
    await state.clear()

    packs_page = await get_admin_packs_page(page=1, per_page=ADMIN_PACKS_PER_PAGE, search=search)
    await message.answer(
        build_admin_packs_page_text(packs_page),
        reply_markup=build_admin_packs_list_keyboard(
            packs=packs_page.packs,
            page=packs_page.page,
            pages_count=packs_page.pages_count,
            search=packs_page.search,
        ),
    )


@router.callback_query(F.data.startswith("admin_packs:view:"))
async def admin_packs_view(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer()


@router.callback_query(F.data == "admin_packs:add")
async def admin_packs_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    await state.set_state(AdminPackStates.waiting_for_image)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_IMAGE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_image)
async def admin_pack_add_image(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    image_path = await save_pack_image(message)
    await safe_delete_message(message)

    if image_path is None:
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_IMAGE_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(image_path=image_path)
    await state.set_state(AdminPackStates.waiting_for_name)
    await send_pack_prompt(message, state, ADMIN_PACK_NAME_TEXT, reply_markup=build_admin_pack_cancel_keyboard())


@router.message(AdminPackStates.waiting_for_name)
async def admin_pack_add_name(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    name = (message.text or "").strip()
    await safe_delete_message(message)

    if not validate_pack_name(name):
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_NAME_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(name=name)
    await state.set_state(AdminPackStates.waiting_for_description)
    await send_pack_prompt(message, state, ADMIN_PACK_DESCRIPTION_TEXT, reply_markup=build_admin_pack_cancel_keyboard())


@router.message(AdminPackStates.waiting_for_description)
async def admin_pack_add_description(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    description = (message.text or "").strip()
    await safe_delete_message(message)

    if not validate_pack_description(description):
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_DESCRIPTION_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(description=description)
    await state.set_state(None)
    await send_pack_prompt(
        message,
        state,
        ADMIN_PACK_CURRENCY_TEXT,
        reply_markup=build_admin_pack_currency_keyboard("add_currency"),
    )


@router.callback_query(F.data.startswith("admin_packs:add_currency:"))
async def admin_pack_add_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    currency = callback.data.split(":")[-1] if callback.data else "free"

    if currency == "free":
        await state.update_data(price_currency_code=None, price_amount=0)
        await state.set_state(AdminPackStates.waiting_for_cards_count)
        await edit_or_send(
            callback,
            ADMIN_PACK_COUNT_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(),
        )
        await callback.answer()
        return

    await state.update_data(price_currency_code=currency)
    await state.set_state(AdminPackStates.waiting_for_price)
    await edit_or_send(
        callback,
        ADMIN_PACK_PRICE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_price)
async def admin_pack_add_price(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    price = parse_positive_int(message.text or "", 0, 999999999)
    await safe_delete_message(message)

    if price is None:
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_PRICE_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(price_amount=price)
    await state.set_state(AdminPackStates.waiting_for_cards_count)
    await send_pack_prompt(message, state, ADMIN_PACK_COUNT_TEXT, reply_markup=build_admin_pack_cancel_keyboard())


@router.message(AdminPackStates.waiting_for_cards_count)
async def admin_pack_add_count(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    cards_count = parse_positive_int(message.text or "", 1, 20)
    await safe_delete_message(message)

    if cards_count is None:
        await send_pack_prompt(message, state, ADMIN_PACK_BAD_COUNT_TEXT, reply_markup=build_admin_pack_cancel_keyboard())
        return

    await state.update_data(cards_count=cards_count)
    await state.set_state(None)
    await send_pack_prompt(message, state, ADMIN_PACK_SHOP_TEXT, reply_markup=build_admin_pack_shop_keyboard())


@router.callback_query(F.data.startswith("admin_packs:add_shop:"))
async def admin_pack_add_shop(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    is_shop_available = callback.data.endswith(":1") if callback.data else False
    await state.update_data(is_shop_available=is_shop_available)
    data = await state.get_data()

    draft = PackDraft(
        image_path=str(data["image_path"]),
        name=str(data["name"]),
        description=str(data["description"]),
        price_currency_code=data.get("price_currency_code"),
        price_amount=int(data.get("price_amount", 0)),
        cards_count=int(data["cards_count"]),
        is_shop_available=bool(data["is_shop_available"]),
    )
    await state.update_data(draft=draft.__dict__)
    await edit_or_send(
        callback,
        build_pack_draft_text(draft),
        reply_markup=build_admin_pack_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_packs:add_confirm")
async def admin_pack_add_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    data = await state.get_data()
    draft_data = data.get("draft")

    if not isinstance(draft_data, dict):
        await edit_or_send(callback, ADMIN_PACKS_MAIN_TEXT, reply_markup=build_admin_packs_main_keyboard())
        await callback.answer()
        return

    draft = PackDraft(
        image_path=str(draft_data["image_path"]),
        name=str(draft_data["name"]),
        description=str(draft_data["description"]),
        price_currency_code=draft_data.get("price_currency_code"),
        price_amount=int(draft_data.get("price_amount", 0)),
        cards_count=int(draft_data["cards_count"]),
        is_shop_available=bool(draft_data["is_shop_available"]),
    )
    pack_id = await create_admin_pack(draft)
    await state.clear()
    await show_admin_pack_profile(callback, pack_id=pack_id, page=1)
    await callback.answer("Пак создан")


@router.callback_query(F.data.startswith("admin_packs:edit_image:"))
async def admin_pack_edit_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page)
    await state.set_state(AdminPackStates.waiting_for_edit_image)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_IMAGE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_image)
async def admin_pack_edit_image_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    image_path = await save_pack_image(message)
    await safe_delete_message(message)

    if image_path is None:
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_IMAGE_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_image_path(pack_id, image_path)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()



@router.callback_query(F.data.startswith("admin_packs:edit_animation:"))
async def admin_pack_edit_animation(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page)
    await state.set_state(AdminPackStates.waiting_for_edit_animation)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_ANIMATION_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_animation)
async def admin_pack_edit_animation_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    saved = await save_pack_animation_video(message)
    await safe_delete_message(message)

    if saved is None:
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_ANIMATION_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    from app.services.audit_log import record_committed
    from app.services.packs import update_pack_animation_video

    await update_pack_animation_video(
        pack_id,
        video_path=saved.path,
        duration_seconds=saved.duration_seconds,
        file_size=saved.file_size,
        file_id=saved.file_id,
        file_unique_id=saved.file_unique_id,
        uploaded_by=message.from_user.id,
    )
    record_committed(
        message.from_user.id, "pack_animation_upload", entity_type="pack", entity_id=pack_id,
        details={"duration_seconds": saved.duration_seconds, "file_size": saved.file_size},
    )
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:remove_animation:"))
async def admin_pack_remove_animation(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    from app.services.audit_log import record_committed
    from app.services.packs import remove_pack_animation_video

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await remove_pack_animation_video(pack_id)
    record_committed(callback.from_user.id, "pack_animation_remove", entity_type="pack", entity_id=pack_id)
    await state.clear()
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer("Видео открытия удалено")


@router.callback_query(F.data.startswith("admin_packs:toggle_animation:"))
async def admin_pack_toggle_animation(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    from app.services.audit_log import record_committed
    from app.services.packs import get_pack_animation_meta, set_pack_animation_enabled

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    meta = await get_pack_animation_meta(pack_id)
    new_enabled = not (meta.enabled if meta else False)
    await set_pack_animation_enabled(pack_id, new_enabled)
    record_committed(
        callback.from_user.id, "pack_animation_toggle", entity_type="pack", entity_id=pack_id,
        details={"enabled": new_enabled},
    )
    await state.clear()
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer("Анимация включена" if new_enabled else "Анимация выключена")


@router.callback_query(F.data.startswith("admin_packs:view_animation:"))
async def admin_pack_view_animation(callback: CallbackQuery) -> None:
    if not await answer_callback_admin_only(callback):
        return

    from app.services.packs import get_pack_animation_meta

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    meta = await get_pack_animation_meta(pack_id)
    if meta is None or not meta.video_path:
        await callback.answer("Видео не загружено.", show_alert=True)
        return

    video_path = Path(meta.video_path)
    if not video_path.exists():
        await callback.answer("Файл видео не найден на диске.", show_alert=True)
        return

    await callback.bot.send_video(
        chat_id=callback.message.chat.id,
        video=FSInputFile(video_path),
        caption=(
            f"Длительность: {meta.duration_seconds or '—'} c\n"
            f"Размер: {meta.file_size or '—'} байт\n"
            f"Загружено: {meta.uploaded_at or '—'} (админ {meta.uploaded_by or '—'})\n"
            f"Анимация включена: {'да' if meta.enabled else 'нет'}"
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:edit_name:") | F.data.startswith("admin_packs:edit_description:"))
async def admin_pack_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    action = parts[1]
    field = "name" if action == "edit_name" else "description"
    pack_id = int(parts[2])
    page = int(parts[3])
    text = ADMIN_PACK_NAME_TEXT if field == "name" else ADMIN_PACK_DESCRIPTION_TEXT
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page, field=field)
    await state.set_state(AdminPackStates.waiting_for_edit_text)
    await prompt_from_callback(
        callback,
        state,
        text,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_text)
async def admin_pack_edit_text_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    field = str(data["field"])
    value = (message.text or "").strip()
    await safe_delete_message(message)

    if field == "name" and not validate_pack_name(value):
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_NAME_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    if field == "description" and not validate_pack_description(value):
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_DESCRIPTION_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_text_field(pack_id, field, value)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:edit_price:"))
async def admin_pack_edit_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await edit_or_send(
        callback,
        ADMIN_PACK_CURRENCY_TEXT,
        reply_markup=build_admin_pack_currency_keyboard("edit_price_currency", pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:edit_price_currency:"))
async def admin_pack_edit_price_currency(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    currency = parts[4]

    if currency == "free":
        await update_pack_price(pack_id, None, 0)
        await state.clear()
        await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
        await callback.answer("Цена обновлена")
        return

    await state.clear()
    await state.update_data(pack_id=pack_id, page=page, currency=currency)
    await state.set_state(AdminPackStates.waiting_for_edit_price)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_PRICE_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_price)
async def admin_pack_edit_price_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    currency = str(data["currency"])
    price = parse_positive_int(message.text or "", 0, 999999999)
    await safe_delete_message(message)

    if price is None:
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_PRICE_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_price(pack_id, currency, price)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:edit_count:"))
async def admin_pack_edit_count(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page)
    await state.set_state(AdminPackStates.waiting_for_edit_count)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_COUNT_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_count)
async def admin_pack_edit_count_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    cards_count = parse_positive_int(message.text or "", 1, 20)
    await safe_delete_message(message)

    if cards_count is None:
        await send_pack_prompt(
            message,
            state,
            ADMIN_PACK_BAD_COUNT_TEXT,
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_cards_count(pack_id, cards_count)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:edit_odds:"))
async def admin_pack_edit_odds(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=page)
    await state.set_state(AdminPackStates.waiting_for_edit_odds)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_ODDS_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_edit_odds)
async def admin_pack_edit_odds_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    page = int(data.get("page", 1))
    chances, error = parse_rarity_chances(message.text or "")
    await safe_delete_message(message)

    if error or chances is None:
        await send_pack_prompt(
            message,
            state,
            build_pack_opening_error_text(error or "Шансы не сохранены."),
            reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=page),
        )
        return

    await update_pack_rarity_chances(pack_id, chances)
    await send_admin_pack_profile_after_input(message, pack_id=pack_id, page=page, state=state)
    await state.clear()


@router.callback_query(F.data.startswith("admin_packs:cards:"))
async def admin_pack_cards(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    list_page = int(parts[3])
    back_page = int(parts[4])
    await show_admin_pack_cards_page(callback, pack_id=pack_id, list_page=list_page, back_page=back_page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:cards_add:"))
async def admin_pack_cards_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    back_page = int(parts[3])
    card_page = int(parts[4])
    await show_admin_available_cards_page(callback, pack_id=pack_id, back_page=back_page, card_page=card_page)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:cards_search_page:"))
async def admin_pack_cards_search_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    back_page = int(parts[3])
    card_page = int(parts[4])
    search = ADMIN_PACK_CARD_SEARCH_CACHE.get((callback.from_user.id, pack_id))
    await show_admin_available_cards_page(
        callback,
        pack_id=pack_id,
        back_page=back_page,
        card_page=card_page,
        search=search,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_packs:cards_search:"))
async def admin_pack_cards_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    back_page = int(parts[3])
    await state.clear()
    await state.update_data(pack_id=pack_id, page=back_page)
    await state.set_state(AdminPackStates.waiting_for_card_search)
    await prompt_from_callback(
        callback,
        state,
        ADMIN_PACK_CARD_SEARCH_TEXT,
        reply_markup=build_admin_pack_cancel_keyboard(pack_id=pack_id, page=back_page),
    )
    await callback.answer()


@router.message(AdminPackStates.waiting_for_card_search)
async def admin_pack_cards_search_value(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    pack_id = int(data["pack_id"])
    back_page = int(data.get("page", 1))
    search = (message.text or "").strip()
    ADMIN_PACK_CARD_SEARCH_CACHE[(message.from_user.id, pack_id)] = search
    await safe_delete_message(message)
    await delete_saved_pack_panel(state, message.bot)
    await state.clear()

    pack = await get_admin_pack_details(pack_id)

    if pack is None:
        await message.answer(ADMIN_PACKS_MAIN_TEXT, reply_markup=build_admin_packs_main_keyboard())
        return

    cards_page = await get_pack_available_cards_page(
        pack_id=pack_id,
        page=1,
        per_page=ADMIN_PACKS_PER_PAGE,
        search=search,
    )
    await message.answer(
        build_admin_pack_available_cards_text(cards_page, pack.name),
        reply_markup=build_admin_pack_available_cards_keyboard(
            pack_id=pack_id,
            back_page=back_page,
            card_page=cards_page.page,
            pages_count=cards_page.pages_count,
            cards=cards_page.cards,
            search=cards_page.search,
        ),
    )


@router.callback_query(F.data.startswith("admin_packs:cards_add_do:"))
async def admin_pack_cards_add_do(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    card_id = int(parts[3])
    back_page = int(parts[4])
    card_page = int(parts[5])
    await add_card_to_pack(pack_id=pack_id, card_id=card_id)
    await show_admin_available_cards_page(callback, pack_id=pack_id, back_page=back_page, card_page=card_page)
    await callback.answer("Карта добавлена")


@router.callback_query(F.data.startswith("admin_packs:cards_remove:"))
async def admin_pack_cards_remove(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    card_id = int(parts[3])
    list_page = int(parts[4])
    back_page = int(parts[5])
    await remove_card_from_pack(pack_id=pack_id, card_id=card_id)
    await show_admin_pack_cards_page(callback, pack_id=pack_id, list_page=list_page, back_page=back_page)
    await callback.answer("Карта убрана")


@router.callback_query(F.data.startswith("admin_packs:toggle_active:"))
async def admin_pack_toggle_active(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await toggle_pack_active(pack_id)
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin_packs:toggle_shop:"))
async def admin_pack_toggle_shop(callback: CallbackQuery, state: FSMContext) -> None:
    if not await answer_callback_admin_only(callback):
        return

    await state.clear()
    parts = callback.data.split(":") if callback.data else []
    pack_id = int(parts[2])
    page = int(parts[3])
    await toggle_pack_shop(pack_id)
    await show_admin_pack_profile(callback, pack_id=pack_id, page=page)
    await callback.answer("Готово")


@router.callback_query(F.data == "admin_packs:page_info")
async def admin_packs_page_info(callback: CallbackQuery) -> None:
    await callback.answer("Текущая страница")
