"""Глобальный технический перерыв: middleware блокирует обычных пользователей
максимально рано, администраторы сохраняют доступ, cooldown не пропускает
Update к игровым хендлерам, текст/фото применяются немедленно, действия пишутся
в audit_log. См. app/middlewares/maintenance.py, app/services/maintenance.py,
app/handlers/admin_maintenance.py.
"""

from datetime import datetime

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from app.database.db import get_connection
from app.middlewares.maintenance import MaintenanceModeMiddleware
from app.services import maintenance
from tests.conftest import create_test_user

ADMIN_TELEGRAM_ID = 999999999


async def _fake_answer(self, *args, **kwargs):
    return None


@pytest.fixture(autouse=True)
def _patch_telegram_io(monkeypatch):
    monkeypatch.setattr(Message, "answer", _fake_answer)
    monkeypatch.setattr(Message, "answer_photo", _fake_answer)
    monkeypatch.setattr(CallbackQuery, "answer", _fake_answer)


def _message(telegram_id: int, text: str = "hi") -> Message:
    user = User(id=telegram_id, is_bot=False, first_name="Test")
    chat = Chat(id=telegram_id, type="private")
    return Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text=text)


def _callback(telegram_id: int, data: str = "packs:open:1") -> CallbackQuery:
    message = _message(telegram_id)
    return CallbackQuery(id="1", from_user=message.from_user, chat_instance="x", message=message, data=data)


async def _handler(event, data):
    data["_called"] = True
    return "handled"


@pytest.fixture
def middleware():
    return MaintenanceModeMiddleware()


async def test_normal_user_passes_through_when_disabled(stronghold_db, middleware):
    user_id = await create_test_user("maint-disabled-user")
    with get_connection() as connection:
        telegram_id = int(connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"])

    event = _message(telegram_id)
    data = {"event_from_user": event.from_user}
    result = await middleware(_handler, event, data)
    assert result == "handled"
    assert data.get("_called") is True


async def test_message_blocked_when_enabled(stronghold_db, middleware):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    event = _message(123456)
    data = {"event_from_user": event.from_user}
    result = await middleware(_handler, event, data)
    assert result is None
    assert data.get("_called") is None


async def test_command_message_blocked_when_enabled(stronghold_db, middleware):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    event = _message(123456, text="/start")
    data = {"event_from_user": event.from_user}
    result = await middleware(_handler, event, data)
    assert result is None
    assert data.get("_called") is None


async def test_callback_blocked_and_answered(stronghold_db, middleware, monkeypatch):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    answered = []

    async def _record_answer(self, *a, **k):
        answered.append(1)

    monkeypatch.setattr(CallbackQuery, "answer", _record_answer)
    event = _callback(123456)
    data = {"event_from_user": event.from_user}
    result = await middleware(_handler, event, data)
    assert result is None
    assert data.get("_called") is None
    assert len(answered) == 1  # answer() всегда вызывается, чтобы не крутился спиннер


async def test_game_handler_not_called_pack_open(stronghold_db, middleware):
    """Хендлер `packs_open` (реальная функция app/handlers/packs.py) передаётся как
    `handler` middleware напрямую — если техперерыв включён, middleware обязан
    вернуть None ДО вызова этой функции, поэтому open_user_pack физически не
    может быть достигнут."""
    from app.handlers.packs import packs_open

    called = {"n": 0}
    import app.services.packs as packs_service

    original = packs_service.open_user_pack

    async def _fail_if_called(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("open_user_pack must not run during maintenance")

    packs_service.open_user_pack = _fail_if_called
    try:
        await maintenance.enable(ADMIN_TELEGRAM_ID)
        event = _callback(555555, data="packs:open:1")

        async def _real_handler(ev, data):
            from aiogram.fsm.context import FSMContext
            from aiogram.fsm.storage.base import StorageKey
            from aiogram.fsm.storage.memory import MemoryStorage

            state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=555555, user_id=555555))
            return await packs_open(ev, state)

        result = await middleware(_real_handler, event, {"event_from_user": event.from_user})
        assert result is None
    finally:
        packs_service.open_user_pack = original
        await maintenance.disable(ADMIN_TELEGRAM_ID)

    assert called["n"] == 0


async def test_admin_keeps_access(stronghold_db, middleware):
    import config

    original = config.settings.admin_ids
    object.__setattr__(config.settings, "admin_ids", frozenset({ADMIN_TELEGRAM_ID}))
    try:
        await maintenance.enable(ADMIN_TELEGRAM_ID)
        event = _message(ADMIN_TELEGRAM_ID)
        data = {"event_from_user": event.from_user}
        result = await middleware(_handler, event, data)
        assert result == "handled"
        assert data.get("_called") is True
    finally:
        object.__setattr__(config.settings, "admin_ids", original)


async def test_text_without_photo_shown(stronghold_db, middleware, monkeypatch):
    await maintenance.set_message_text("Идут технические работы, ждите.", ADMIN_TELEGRAM_ID)
    await maintenance.enable(ADMIN_TELEGRAM_ID)

    sent = []

    async def _answer(self, text, **k):
        sent.append(("text", text))

    async def _answer_photo(self, **k):
        sent.append(("photo", k))

    monkeypatch.setattr(Message, "answer", _answer)
    monkeypatch.setattr(Message, "answer_photo", _answer_photo)

    event = _message(777777)
    await middleware(_handler, event, {"event_from_user": event.from_user})
    assert sent == [("text", "Идут технические работы, ждите.")]


async def test_photo_with_text_shown(stronghold_db, middleware, monkeypatch):
    await maintenance.set_message_text("Кастомный текст", ADMIN_TELEGRAM_ID)
    await maintenance.set_photo("FILEID1", "UNIQUE1", ADMIN_TELEGRAM_ID)
    await maintenance.enable(ADMIN_TELEGRAM_ID)

    sent = []

    async def _answer(self, text, **k):
        sent.append(("text", text))

    async def _answer_photo(self, photo, caption=None, **k):
        sent.append(("photo", photo, caption))

    monkeypatch.setattr(Message, "answer", _answer)
    monkeypatch.setattr(Message, "answer_photo", _answer_photo)

    event = _message(777778)
    await middleware(_handler, event, {"event_from_user": event.from_user})
    assert sent == [("photo", "FILEID1", "Кастомный текст")]


async def test_photo_without_text_uses_fallback_caption(stronghold_db, middleware, monkeypatch):
    await maintenance.set_photo("FILEID2", "UNIQUE2", ADMIN_TELEGRAM_ID)
    await maintenance.enable(ADMIN_TELEGRAM_ID)

    sent = []

    async def _answer_photo(self, photo, caption=None, **k):
        sent.append(("photo", photo, caption))

    monkeypatch.setattr(Message, "answer_photo", _answer_photo)

    event = _message(777779)
    await middleware(_handler, event, {"event_from_user": event.from_user})
    assert sent[0][2] == maintenance.DEFAULT_MAINTENANCE_TEXT


async def test_no_text_no_photo_uses_default_text(stronghold_db, middleware, monkeypatch):
    await maintenance.enable(ADMIN_TELEGRAM_ID)

    sent = []

    async def _answer(self, text, **k):
        sent.append(text)

    monkeypatch.setattr(Message, "answer", _answer)

    event = _message(777780)
    await middleware(_handler, event, {"event_from_user": event.from_user})
    assert sent == [maintenance.DEFAULT_MAINTENANCE_TEXT]


async def test_text_change_applies_without_restart(stronghold_db):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    status1 = await maintenance.get_status()
    assert status1.effective_text == maintenance.DEFAULT_MAINTENANCE_TEXT

    await maintenance.set_message_text("Новый текст сразу", ADMIN_TELEGRAM_ID)
    status2 = await maintenance.get_status()  # даже с кэшем — invalidate_cache() уже сработал
    assert status2.effective_text == "Новый текст сразу"


async def test_photo_change_applies_without_restart(stronghold_db):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    await maintenance.set_photo("F1", "U1", ADMIN_TELEGRAM_ID)
    status = await maintenance.get_status()
    assert status.photo_file_id == "F1"

    await maintenance.set_photo("F2", "U2", ADMIN_TELEGRAM_ID)
    status2 = await maintenance.get_status()
    assert status2.photo_file_id == "F2"


async def test_disable_restores_access_immediately(stronghold_db, middleware):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    event = _message(888881)
    result = await middleware(_handler, event, {"event_from_user": event.from_user})
    assert result is None

    await maintenance.disable(ADMIN_TELEGRAM_ID)
    event2 = _message(888881)
    data2 = {"event_from_user": event2.from_user}
    result2 = await middleware(_handler, event2, data2)
    assert result2 == "handled"
    assert data2.get("_called") is True


async def test_state_persists_after_simulated_restart(stronghold_db):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    maintenance.invalidate_cache()  # симулирует чистый процесс без in-memory состояния
    status = await maintenance.get_status(use_cache=False)
    assert status.enabled is True


async def test_normal_user_cannot_enable(stronghold_db):
    from app.handlers.admin_maintenance import admin_maintenance_enable

    event = _callback(444444, data="admin_maintenance:enable")
    await admin_maintenance_enable(event)
    status = await maintenance.get_status(use_cache=False)
    assert status.enabled is False


async def test_normal_user_cannot_disable(stronghold_db):
    from app.handlers.admin_maintenance import admin_maintenance_disable

    await maintenance.enable(ADMIN_TELEGRAM_ID)
    event = _callback(444445, data="admin_maintenance:disable")
    await admin_maintenance_disable(event)
    status = await maintenance.get_status(use_cache=False)
    assert status.enabled is True  # обычный пользователь не смог выключить


async def test_spoofed_admin_callback_rejected(stronghold_db):
    """Подмена callback_data на admin_maintenance:enable от обычного пользователя
    отклоняется на уровне хендлера (_require_permission), а не только UI."""
    from app.handlers.admin_maintenance import admin_maintenance_enable_confirm

    event = _callback(444446, data="admin_maintenance:enable_confirm")
    await admin_maintenance_enable_confirm(event)
    status = await maintenance.get_status(use_cache=False)
    assert status.enabled is False


async def test_actions_recorded_in_audit_log(stronghold_db):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    await maintenance.set_message_text("audit text", ADMIN_TELEGRAM_ID)
    await maintenance.set_photo("FX", "UX", ADMIN_TELEGRAM_ID)
    await maintenance.disable(ADMIN_TELEGRAM_ID)

    with get_connection() as connection:
        actions = {
            row["action"]
            for row in connection.execute(
                "SELECT action FROM audit_log WHERE actor_user_id = ? AND action LIKE 'maintenance_%'", (ADMIN_TELEGRAM_ID,)
            ).fetchall()
        }
    assert {"maintenance_enable", "maintenance_text_update", "maintenance_photo_update", "maintenance_disable"} <= actions


async def test_cooldown_does_not_let_update_reach_handler(stronghold_db, middleware, monkeypatch):
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    sent = []

    async def _answer(self, text, **k):
        sent.append(text)

    monkeypatch.setattr(Message, "answer", _answer)

    event1 = _message(999991)
    event2 = _message(999991)
    result1 = await middleware(_handler, event1, {"event_from_user": event1.from_user})
    result2 = await middleware(_handler, event2, {"event_from_user": event2.from_user})

    assert result1 is None
    assert result2 is None  # cooldown блокирует только повторную ОТПРАВКУ уведомления, не Update
    assert len(sent) == 1  # второе уведомление подавлено cooldown'ом


async def test_old_stale_inline_button_blocked(stronghold_db, middleware):
    """Нажатие на СТАРУЮ inline-кнопку (callback_data от меню, отправленного ДО
    включения техперерыва — например из уже неактуального экрана паков/ranked/
    admin) должно блокироваться точно так же, как и любой другой CallbackQuery —
    middleware не делает исключений по значению callback_data."""
    await maintenance.enable(ADMIN_TELEGRAM_ID)

    stale_callback_datas = [
        "packs:open:42",
        "ranked:play",
        "admin_panel:admins",
        "stg:fortress:view:3",
        "some_removed_legacy_menu:button_from_2019",
    ]
    for data in stale_callback_datas:
        event = _callback(123123, data=data)
        result = await middleware(_handler, event, {"event_from_user": event.from_user})
        assert result is None, f"stale callback_data={data!r} must be blocked during maintenance"


async def test_admin_keeps_access_via_callback_query(stronghold_db, middleware):
    """Административный доступ сохраняется не только для Message, но и для
    CallbackQuery (нажатие любой inline-кнопки админом продолжает работать)."""
    import config

    original = config.settings.admin_ids
    object.__setattr__(config.settings, "admin_ids", frozenset({ADMIN_TELEGRAM_ID}))
    try:
        await maintenance.enable(ADMIN_TELEGRAM_ID)
        event = _callback(ADMIN_TELEGRAM_ID, data="admin_panel:admins")
        data = {"event_from_user": event.from_user}
        result = await middleware(_handler, event, data)
        assert result == "handled"
        assert data.get("_called") is True
    finally:
        object.__setattr__(config.settings, "admin_ids", original)


async def test_command_slash_start_blocked_for_normal_user(stronghold_db, middleware):
    """Отдельная явная проверка именно КОМАНДЫ (/start), не просто произвольного
    текстового сообщения."""
    await maintenance.enable(ADMIN_TELEGRAM_ID)
    event = _message(654321, text="/start")
    data = {"event_from_user": event.from_user}
    result = await middleware(_handler, event, data)
    assert result is None
    assert data.get("_called") is None
