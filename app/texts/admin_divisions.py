from html import escape

from app.services.admin_divisions import AnimationAssetsPage, DivisionItem, MissingAssetReport, TeamAssignmentsPage


def safe(value: object | None) -> str:
    text = str(value or "").strip()
    return escape(text or "не указано", quote=False)


ADMIN_DIVISIONS_MAIN_TEXT = """
<b>🏒 Дивизионы и анимация</b>

Здесь настраиваются дивизионы команд и картинки для анимации открытия паков.

Логика открытия: <b>дивизион → команда → страна → карточка</b>.
""".strip()

ADMIN_DIVISION_NAME_TEXT = """
<b>➕ Новый дивизион</b>

Отправь название дивизиона одним сообщением.

Пример: <b>Atlantic Division</b>
""".strip()

ADMIN_DIVISION_IMAGE_TEXT = """
<b>🖼 Картинка дивизиона</b>

Отправь изображение дивизиона фото или файлом PNG/JPG.
Оно будет показываться на первом этапе открытия пака.
""".strip()

ADMIN_ASSET_IMAGE_TEXT = """
<b>🖼 Картинка для анимации</b>

Отправь изображение фото или файлом PNG/JPG.
Оно будет показываться вместе с текстом в одном сообщении.
""".strip()

ADMIN_BAD_IMAGE_TEXT = "⚠️ Отправь картинку как фото или файл PNG/JPG/WEBP."
ADMIN_SAVED_TEXT = "✅ Сохранено."
ADMIN_CANCEL_TEXT = "❌ Действие отменено."


def build_divisions_text(divisions: list[DivisionItem]) -> str:
    lines = ["<b>🏒 Дивизионы</b>", ""]
    if not divisions:
        lines.append("Дивизионов пока нет. Создай первый дивизион и добавь команды кнопками.")
    else:
        for d in divisions:
            status = "✅" if d.active else "⏸"
            image = "🖼" if d.image_path else "без картинки"
            lines.append(f"{status} <b>{safe(d.name)}</b> — {d.teams_count} команд · {image}")
    return "\n".join(lines)


def build_division_profile_text(division: DivisionItem) -> str:
    status = "активен" if division.active else "выключен"
    image = division.image_path or "не загружена"
    return f"""
<b>🏒 Дивизион</b>

Название: <b>{safe(division.name)}</b>
Команд: <b>{division.teams_count}</b>
Статус: <b>{status}</b>
Картинка: <b>{safe(image)}</b>

Через кнопку ниже можно открыть список всех команд из базы и добавить их в этот дивизион.
""".strip()


def build_team_assignments_text(division: DivisionItem, page: TeamAssignmentsPage) -> str:
    lines = [
        f"<b>➕ Команды дивизиона: {safe(division.name)}</b>",
        "",
        f"Страница: <b>{page.page}/{page.pages_count}</b>",
        f"Всего команд в базе: <b>{page.total_count}</b>",
        "",
        "Нажимай на команды: ✅ — уже в этом дивизионе, ➕ — можно добавить, ↪️ — команда привязана к другому дивизиону и будет перенесена сюда.",
    ]
    return "\n".join(lines)


def build_assets_text(page: AnimationAssetsPage) -> str:
    title = "Команды" if page.asset_type == "team" else "Страны"
    lines = [f"<b>🖼 Картинки анимации: {title}</b>", "", f"Страница: <b>{page.page}/{page.pages_count}</b>", f"Всего: <b>{page.total_count}</b>", ""]
    if not page.assets:
        lines.append("Значений пока нет. Они появятся после добавления карточек.")
    else:
        for item in page.assets:
            mark = "✅" if item.exists else "⚠️"
            lines.append(f"{mark} {safe(item.asset_key)}")
    return "\n".join(lines)


def build_missing_report_text(report: MissingAssetReport) -> str:
    lines = ["<b>⚠️ Проверка картинок и данных</b>", ""]
    if not report.has_issues:
        lines.append("Все обязательные данные и картинки загружены.")
        return "\n".join(lines)

    groups = [
        ("🃏 Карточки", report.missing_cards),
        ("🎁 Паки", report.missing_packs),
        ("🏒 Дивизионы без картинки", report.missing_divisions),
        ("🛡 Команды без дивизиона", report.teams_without_division),
        ("🖼 Команды без картинки анимации", report.missing_team_images),
        ("🌍 Страны без картинки анимации", report.missing_country_images),
    ]
    for title, values in groups:
        if not values:
            continue
        lines.append(f"<b>{title}</b>")
        for value in values:
            lines.append(f"• {safe(value)}")
        lines.append("")
    lines.append("Бот будет повторять это предупреждение администраторам каждые 2 часа, пока проблема не будет закрыта или настройка не будет выключена.")
    return "\n".join(lines).strip()
