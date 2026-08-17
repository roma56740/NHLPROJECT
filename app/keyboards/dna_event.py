from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.dna_crafting import DNA_TARGETS, DnaChoicePage, DnaCraftPreview, DnaExtractionPreview


def build_dna_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 STONE 100", callback_data="dna:view:100:STONE"), InlineKeyboardButton(text="🔥 HUTSON 100", callback_data="dna:view:100:HUTSON")],
        [InlineKeyboardButton(text="🔥 COOLEY 100", callback_data="dna:view:100:COOLEY"), InlineKeyboardButton(text="🔥 SCHAEFER 100", callback_data="dna:view:100:SCHAEFER")],
        [InlineKeyboardButton(text="🧬 Крафт 93", callback_data="dna:tier:93"), InlineKeyboardButton(text="🧬 Крафт 95", callback_data="dna:tier:95")],
        [InlineKeyboardButton(text="🧬 Крафт 98", callback_data="dna:tier:98"), InlineKeyboardButton(text="📖 Путь до 100", callback_data="dna:progression")],
        [InlineKeyboardButton(text="⚗️ Получить Collectibles", callback_data="dna:extract"), InlineKeyboardButton(text="🎁 95–96 Choice · 3 🧬", callback_data="dna:choice:1")],
        [InlineKeyboardButton(text="🎒 Мои DNA предметы", callback_data="dna:inventory")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")],
    ])


def build_dna_tier_keyboard(overall: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{surname} {overall}", callback_data=f"dna:view:{overall}:{surname}")] for surname in DNA_TARGETS.get(overall, ())]
    rows.append([InlineKeyboardButton(text="⬅️ DNA", callback_data="dna:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dna_recipe_keyboard(preview: DnaCraftPreview) -> InlineKeyboardMarkup:
    rows = []
    if preview.target.available and preview.enough:
        rows.append([InlineKeyboardButton(text=f"🔥 Скрафтить {preview.target.surname} {preview.target.overall}", callback_data=f"dna:craft:{preview.target.overall}:{preview.target.surname}")])
    elif not preview.target.available:
        rows.append([InlineKeyboardButton(text="⚠️ Карта ещё не загружена", callback_data="dna:no_target")])
    else:
        rows.append([InlineKeyboardButton(text="❌ Не хватает ресурсов", callback_data="dna:not_enough")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"dna:view:{preview.target.overall}:{preview.target.surname}")])
    rows.append([InlineKeyboardButton(text="⬅️ DNA", callback_data="dna:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dna_result_keyboard(overall: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🧬 Продолжить крафт", callback_data="dna:main")]]
    if overall < 100:
        next_tier = 95 if overall == 93 else 98 if overall == 95 else 100
        rows.insert(0, [InlineKeyboardButton(text=f"➡️ Следующий этап: {next_tier} OVR", callback_data=f"dna:tier:{next_tier}")])
    rows.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dna_extraction_keyboard(items: tuple[DnaExtractionPreview, ...]) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        marker = "✅" if item.can_extract else "❌"
        rows.append([InlineKeyboardButton(text=f"{marker} {item.cards_required}× {item.ovr_label} OVR → +{item.collectibles_reward} 🧬", callback_data=f"dna:extract:{item.code}")])
    rows.append([InlineKeyboardButton(text="⬅️ DNA", callback_data="dna:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dna_choice_keyboard(page: DnaChoicePage) -> InlineKeyboardMarkup:
    rows = []
    if not page.claimed:
        for card in page.items:
            rows.append([InlineKeyboardButton(text=f"{card.name} · {card.overall} OVR · {card.collection_name}", callback_data=f"dna:choice_craft:{card.card_id}")])
        nav = []
        if page.page > 1:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"dna:choice:{page.page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page.page}/{page.pages_count}", callback_data="dna:noop"))
        if page.page < page.pages_count:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"dna:choice:{page.page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ DNA", callback_data="dna:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
