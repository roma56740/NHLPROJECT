"""Открытие паков: единая выдача награды, pending-reveal состояние (crash-safe),
идемпотентность, видео открытия (загрузка/лимит длительности/toggle),
восстановление после рестарта. См. app/services/packs.py,
app/services/pack_reveal_recovery.py, app/handlers/packs.py.
"""

from types import SimpleNamespace

import pytest

from app.database.db import get_connection
from app.services.packs import (
    PackDraft,
    add_card_to_pack,
    create_admin_pack,
    encode_rarity_chances,
    get_pack_animation_meta,
    mark_reveal_completed,
    mark_reveal_failed,
    open_user_pack,
    remove_pack_animation_video,
    rewards_from_snapshot,
    set_pack_animation_enabled,
    update_pack_animation_video,
)
from tests.conftest import create_test_user

_SEQ = 0


async def _make_card() -> int:
    global _SEQ
    _SEQ += 1
    with get_connection() as connection:
        collection = connection.execute("SELECT id FROM collections WHERE code = 'free-cards'").fetchone()
        key = f"pack-test-card-{_SEQ}"
        cursor = connection.execute(
            """
            INSERT INTO cards (name, player_key, position, overall, team, country, collection_id, rarity, image_path, salary, active)
            VALUES (?, ?, 'F', 80, 'Test Team', 'Test Country', ?, 'Common', 'assets/uploads/test.png', 0, 1)
            """,
            (key.title(), key, int(collection["id"])),
        )
        connection.commit()
        return int(cursor.lastrowid)


async def _make_pack(*, cards_count: int = 1, free: bool = True) -> int:
    draft = PackDraft(
        image_path="assets/uploads/test.png",
        name=f"Test Pack {_SEQ}",
        description="test pack",
        price_currency_code=None if free else "coins",
        price_amount=0 if free else 1,
        cards_count=cards_count,
        is_shop_available=False,
    )
    pack_id = await create_admin_pack(draft)
    card_id = await _make_card()
    await add_card_to_pack(pack_id, card_id)
    # Все тестовые карты — Common; форсируем 100% Common на слотах, иначе
    # create_pack_slots() ставит стандартные DEFAULT_RARITY_CHANCES и рандомный
    # выбор редкости (Rare/Epic/...) не находит ни одной подходящей карты.
    with get_connection() as connection:
        connection.execute(
            "UPDATE pack_slots SET rarity_chances = ? WHERE pack_id = ?",
            (encode_rarity_chances({"Common": 100}), pack_id),
        )
        connection.commit()
    return pack_id


async def _grant_pack(user_id: int, pack_id: int, quantity: int = 1) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_packs (user_id, pack_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT(user_id, pack_id) DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (user_id, pack_id, quantity),
        )
        connection.commit()


async def test_pack_opens_and_grants_reward_once(stronghold_db):
    user_id = await create_test_user("pack-open-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)

    result, error = await open_user_pack(user_id=user_id, pack_id=pack_id)
    assert error is None
    assert result is not None
    assert len(result.rewards) == 1

    with get_connection() as connection:
        user_cards_count = connection.execute(
            "SELECT COUNT(*) AS n FROM user_cards WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    assert user_cards_count == 1


async def test_pack_quantity_decrements_exactly_once(stronghold_db):
    user_id = await create_test_user("pack-qty-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 2)

    await open_user_pack(user_id=user_id, pack_id=pack_id)
    with get_connection() as connection:
        qty = connection.execute(
            "SELECT quantity FROM user_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)
        ).fetchone()["quantity"]
    assert qty == 1


async def test_double_open_without_second_copy_fails_cleanly(stronghold_db):
    """Пак списывается ровно один раз — повторное открытие без второй копии не
    выдаёт вторую награду."""
    user_id = await create_test_user("pack-double-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)

    result1, error1 = await open_user_pack(user_id=user_id, pack_id=pack_id)
    assert result1 is not None and error1 is None

    result2, error2 = await open_user_pack(user_id=user_id, pack_id=pack_id)
    assert result2 is None
    assert error2 is not None

    with get_connection() as connection:
        openings_count = connection.execute(
            "SELECT COUNT(*) AS n FROM pack_openings WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)
        ).fetchone()["n"]
    assert openings_count == 1


async def test_pending_reveal_created_atomically_with_reward(stronghold_db):
    """Награда фиксируется ДО начала видео — pending_reveal создаётся в той же
    транзакции, что и выдача карты."""
    user_id = await create_test_user("pack-pending-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)

    result, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM pack_pending_reveals WHERE opening_id = ?", (result.opening_id,)
        ).fetchone()
    assert row is not None
    assert row["status"] == "pending"
    assert row["request_id"] == f"pack-open-{result.opening_id}"

    snapshot_rewards = rewards_from_snapshot(row["reward_snapshot"])
    assert len(snapshot_rewards) == 1
    assert snapshot_rewards[0].card_id == result.rewards[0].card_id


async def test_pending_reveal_request_id_is_unique(stronghold_db):
    """Пак не бесплатный (free-паки — раздел ТЗ "открывается один раз"), чтобы
    проверить именно уникальность request_id/opening_id на ДВУХ легитимных
    открытиях одного и того же платного пака одним пользователем."""
    user_id = await create_test_user("pack-reqid-user")
    pack_id = await _make_pack(free=False)
    await _grant_pack(user_id, pack_id, 2)

    result1, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)
    result2, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)
    assert result1.opening_id != result2.opening_id

    with get_connection() as connection:
        distinct_request_ids = connection.execute(
            "SELECT COUNT(DISTINCT request_id) AS n FROM pack_pending_reveals WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    assert distinct_request_ids == 2


async def test_mark_reveal_completed_transitions_status(stronghold_db):
    user_id = await create_test_user("pack-complete-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)
    result, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)

    await mark_reveal_completed(result.opening_id)
    with get_connection() as connection:
        row = connection.execute(
            "SELECT status, completed_at FROM pack_pending_reveals WHERE opening_id = ?", (result.opening_id,)
        ).fetchone()
    assert row["status"] == "completed"
    assert row["completed_at"] is not None


async def test_mark_reveal_completed_is_idempotent(stronghold_db):
    """Повторный вызов mark_reveal_completed не должен ничего ломать (WHERE status='pending' guard)."""
    user_id = await create_test_user("pack-complete-twice-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)
    result, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)

    await mark_reveal_completed(result.opening_id)
    await mark_reveal_completed(result.opening_id)  # не должно бросать исключение
    with get_connection() as connection:
        row = connection.execute(
            "SELECT status FROM pack_pending_reveals WHERE opening_id = ?", (result.opening_id,)
        ).fetchone()
    assert row["status"] == "completed"


async def test_resume_pending_reveals_finishes_interrupted_openings(stronghold_db):
    """Симулирует рестарт бота во время 10-секундной анимации: pending reveal
    остаётся 'pending' -> resume_pending_pack_reveals должен доставить награду и
    пометить завершённым, БЕЗ повторной выдачи карты."""
    from app.services.pack_reveal_recovery import resume_pending_pack_reveals

    user_id = await create_test_user("pack-resume-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)
    result, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)
    # Намеренно НЕ вызываем attach_reveal_message/mark_reveal_completed — как если
    # бы процесс упал сразу после open_user_pack(), до отправки видео.

    with get_connection() as connection:
        before_cards = connection.execute(
            "SELECT COUNT(*) AS n FROM user_cards WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]

    sent_messages = []

    class FakeBot:
        async def send_message(self, chat_id, text, **kwargs):
            sent_messages.append((chat_id, text))
            return SimpleNamespace(message_id=1)

        async def send_photo(self, chat_id, photo, caption=None, **kwargs):
            sent_messages.append((chat_id, caption))
            return SimpleNamespace(message_id=1)

    resumed = await resume_pending_pack_reveals(FakeBot())
    assert resumed == 1
    assert len(sent_messages) == 1

    with get_connection() as connection:
        after_cards = connection.execute(
            "SELECT COUNT(*) AS n FROM user_cards WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        status = connection.execute(
            "SELECT status FROM pack_pending_reveals WHERE opening_id = ?", (result.opening_id,)
        ).fetchone()["status"]

    assert after_cards == before_cards  # награда не выдана повторно, только доставлена
    assert status == "completed"


async def test_resume_pending_reveals_does_not_duplicate_already_completed(stronghold_db):
    from app.services.pack_reveal_recovery import resume_pending_pack_reveals

    user_id = await create_test_user("pack-resume-clean-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)
    result, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)
    await mark_reveal_completed(result.opening_id)

    class FakeBot:
        async def send_message(self, *a, **k):
            raise AssertionError("should not be called for an already-completed reveal")

        async def send_photo(self, *a, **k):
            raise AssertionError("should not be called for an already-completed reveal")

    resumed = await resume_pending_pack_reveals(FakeBot())
    assert resumed == 0


async def test_pack_without_video_opens_via_fallback(stronghold_db):
    user_id = await create_test_user("pack-no-video-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)
    meta = await get_pack_animation_meta(pack_id)
    assert meta.video_path is None

    result, error = await open_user_pack(user_id=user_id, pack_id=pack_id)
    assert error is None and result is not None


async def test_animation_video_metadata_saved_and_toggle(stronghold_db):
    pack_id = await _make_pack()
    ok = await update_pack_animation_video(
        pack_id,
        video_path="assets/uploads/packs/animations/test.mp4",
        duration_seconds=9,
        file_size=12345,
        file_id="FILEID123",
        file_unique_id="UNIQUEID123",
        uploaded_by=999999999,
    )
    assert ok

    meta = await get_pack_animation_meta(pack_id)
    assert meta.video_path == "assets/uploads/packs/animations/test.mp4"
    assert meta.duration_seconds == 9
    assert meta.file_size == 12345
    assert meta.file_id == "FILEID123"
    assert meta.enabled is True  # включается автоматически при загрузке

    await set_pack_animation_enabled(pack_id, False)
    meta_disabled = await get_pack_animation_meta(pack_id)
    assert meta_disabled.enabled is False

    await remove_pack_animation_video(pack_id)
    meta_removed = await get_pack_animation_meta(pack_id)
    assert meta_removed.video_path is None


async def test_video_duration_over_10_seconds_rejected(stronghold_db):
    from app.handlers.packs import save_pack_animation_video

    class FakeBot:
        async def download(self, *a, **k):
            raise AssertionError("must not download a rejected video")

    fake_message = SimpleNamespace(
        video=SimpleNamespace(file_unique_id="uid-long", duration=11, file_name="opening.mp4", file_size=1000, file_id="fid-long"),
        animation=None,
        document=None,
        from_user=SimpleNamespace(id=999999999),
        bot=FakeBot(),
    )
    saved = await save_pack_animation_video(fake_message)
    assert saved is None


async def test_video_duration_within_10_seconds_accepted(stronghold_db, tmp_path, monkeypatch):
    from app.handlers import packs as packs_handler
    from app.handlers.packs import save_pack_animation_video

    monkeypatch.setattr(packs_handler, "PACK_ANIMATIONS_DIR", tmp_path)

    downloaded = []

    class FakeBot:
        async def download(self, downloadable, destination):
            downloaded.append(destination)
            destination.write_bytes(b"fake video bytes")

    fake_message = SimpleNamespace(
        video=SimpleNamespace(file_unique_id="uid-ok", duration=9, file_name="opening.mp4", file_size=2000, file_id="fid-ok"),
        animation=None,
        document=None,
        from_user=SimpleNamespace(id=999999999),
        bot=FakeBot(),
    )
    saved = await save_pack_animation_video(fake_message)
    assert saved is not None
    assert saved.duration_seconds == 9
    assert saved.file_id == "fid-ok"
    assert len(downloaded) == 1


async def test_mark_reveal_failed_records_error(stronghold_db):
    user_id = await create_test_user("pack-fail-user")
    pack_id = await _make_pack()
    await _grant_pack(user_id, pack_id, 1)
    result, _ = await open_user_pack(user_id=user_id, pack_id=pack_id)

    await mark_reveal_failed(result.opening_id, "TelegramBadRequest: something went wrong")
    with get_connection() as connection:
        row = connection.execute(
            "SELECT status, error FROM pack_pending_reveals WHERE opening_id = ?", (result.opening_id,)
        ).fetchone()
    assert row["status"] == "failed"
    assert "TelegramBadRequest" in row["error"]


# ---------------------------------------------------------------------------
# Handler-level end-to-end: real video message -> 10s -> edit_media -> card,
# admin "посмотреть видео", and edit_media-failure fallback without duplicate
# reward. Uses a duck-typed fake bot/message (same idiom as
# tests/test_black_market_audit_fixes.py::_FakeCallback) since aiogram's real
# CallbackQuery.bot is a read-only contextvar-backed property in this version.
# ---------------------------------------------------------------------------

from datetime import datetime as _datetime

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Chat as _Chat
from aiogram.types import Message as _Message
from aiogram.types import User as _User


class _FakeSentMessage:
    """Stands in for the aiogram Message returned by bot.send_video()/send_message() —
    real aiogram Message objects can't have `.bot` reassigned after construction in
    this pydantic version, so handler code that calls `opening_message.bot.send_message`
    (the edit_media fallback path) needs this duck-typed object instead."""

    def __init__(self, message_id: int, chat_id: int, bot: "_FakeBot", edit_media_mode: str = "success"):
        self.message_id = message_id
        self.chat = SimpleNamespace(id=chat_id)
        self.bot = bot
        self.edit_media_mode = edit_media_mode
        self.edit_media_calls: list = []
        self.deleted = False

    async def edit_media(self, media, reply_markup=None):
        self.edit_media_calls.append((media, reply_markup))
        if self.edit_media_mode == "fail":
            raise TelegramBadRequest(method=None, message="message can't be edited")
        return self  # aiogram returns the (same) edited Message on success

    async def edit_text(self, text, reply_markup=None):
        self.edited_text = text

    async def delete(self):
        self.deleted = True


class _FakeBot:
    def __init__(self, edit_media_mode: str = "success"):
        self.edit_media_mode = edit_media_mode
        self.sent_videos: list[tuple[int, str]] = []
        self.sent_messages: list[tuple[int, str]] = []
        self.sent_photos: list[tuple[int, str]] = []
        self._next_id = 1000

    async def send_video(self, chat_id, video, caption, supports_streaming=False):
        self._next_id += 1
        self.sent_videos.append((chat_id, caption))
        return _FakeSentMessage(self._next_id, chat_id, self, edit_media_mode=self.edit_media_mode)

    async def send_message(self, chat_id, text, reply_markup=None):
        self._next_id += 1
        self.sent_messages.append((chat_id, text))
        return _FakeSentMessage(self._next_id, chat_id, self, edit_media_mode=self.edit_media_mode)

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        self._next_id += 1
        self.sent_photos.append((chat_id, caption))
        return _FakeSentMessage(self._next_id, chat_id, self, edit_media_mode=self.edit_media_mode)


class _FakeCallback:
    def __init__(self, telegram_id: int, data: str, bot: "_FakeBot"):
        self.from_user = _User(id=telegram_id, is_bot=False, first_name="Test")
        self.data = data
        self.bot = bot
        # callback.message must be a REAL aiogram Message: show_pack_opening_result()
        # does `isinstance(source_message, Message)` before doing anything else.
        chat = _Chat(id=telegram_id, type="private")
        self.message = _Message(message_id=1, date=_datetime.now(), chat=chat, from_user=self.from_user, text="x")
        self.answered: list = []

    async def answer(self, text: str | None = None, show_alert: bool = False):
        self.answered.append(text)


async def _make_pack_with_video(tmp_path, *, duration_seconds: int = 9) -> tuple[int, "SimpleNamespace"]:
    pack_id = await _make_pack()
    video_path = tmp_path / f"opening_{pack_id}.mp4"
    video_path.write_bytes(b"fake mp4 bytes")
    await update_pack_animation_video(
        pack_id,
        video_path=str(video_path),
        duration_seconds=duration_seconds,
        file_size=len(b"fake mp4 bytes"),
        file_id=f"FILEID-{pack_id}",
        file_unique_id=f"UNIQUE-{pack_id}",
        uploaded_by=999999999,
    )
    return pack_id, video_path


async def test_admin_can_view_uploaded_pack_video(stronghold_db, tmp_path):
    """Загрузить/заменить/удалить уже покрыты test_animation_video_metadata_saved_and_toggle
    (сервисный уровень) — здесь конкретно "посмотреть видео" через реальный admin-хендлер."""
    from app.handlers.packs import admin_pack_view_animation

    pack_id, _ = await _make_pack_with_video(tmp_path)
    bot = _FakeBot()
    callback = _FakeCallback(999999999, f"admin_packs:view_animation:{pack_id}:1", bot)

    await admin_pack_view_animation(callback)

    assert len(bot.sent_videos) == 1
    chat_id, caption = bot.sent_videos[0]
    assert chat_id == 999999999
    assert "Длительность: 9" in caption
    assert "Анимация включена: да" in caption
    assert callback.answered == [None]  # answer() called without an error alert


async def _fake_delete(self):
    """callback.message here is a real aiogram Message with no bot bound to it
    (Message.delete() would otherwise raise RuntimeError: 'not mounted to any bot
    instance') — same no-op-patch idiom as Message.answer in other smoke tests."""
    return None


async def test_video_reveal_edits_same_message_after_delay(stronghold_db, tmp_path, monkeypatch):
    """После 10 секунд редактируется ТО ЖЕ сообщение (edit_media на том же объекте,
    не новое send_photo) — видео заменяется картой выпавшей награды."""
    import app.handlers.packs as packs_handler

    monkeypatch.setattr(_Message, "delete", _fake_delete)

    slept: list[float] = []

    async def _fast_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(packs_handler, "sleep", _fast_sleep)

    user_id = await create_test_user("pack-video-reveal-user")
    pack_id, _ = await _make_pack_with_video(tmp_path)
    await _grant_pack(user_id, pack_id, 1)

    with get_connection() as connection:
        telegram_id = int(connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"])

    bot = _FakeBot(edit_media_mode="success")
    callback = _FakeCallback(telegram_id, f"packs:open:{pack_id}", bot)

    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id))

    from app.handlers.packs import packs_open

    await packs_open(callback, state)

    assert slept == [10]  # PACK_ANIMATION_SECONDS, real wait skipped via monkeypatch
    assert len(bot.sent_videos) == 1  # видео отправлено ровно один раз

    with get_connection() as connection:
        row = connection.execute(
            "SELECT status FROM pack_pending_reveals WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)
        ).fetchone()
    assert row["status"] == "completed"


async def test_edit_media_failure_falls_back_without_duplicating_reward(stronghold_db, tmp_path, monkeypatch):
    """edit_message_media бросает TelegramBadRequest -> fallback (delete + новое
    сообщение), но награда уже была выдана ДО видео и не выдаётся повторно."""
    import app.handlers.packs as packs_handler

    monkeypatch.setattr(_Message, "delete", _fake_delete)

    async def _fast_sleep(seconds):
        return None

    monkeypatch.setattr(packs_handler, "sleep", _fast_sleep)

    user_id = await create_test_user("pack-edit-fail-user")
    pack_id, _ = await _make_pack_with_video(tmp_path)
    await _grant_pack(user_id, pack_id, 1)

    with get_connection() as connection:
        telegram_id = int(connection.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,)).fetchone()["telegram_id"])

    bot = _FakeBot(edit_media_mode="fail")  # edit_media always raises TelegramBadRequest
    callback = _FakeCallback(telegram_id, f"packs:open:{pack_id}", bot)

    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id))

    from app.handlers.packs import packs_open

    await packs_open(callback, state)

    # Fallback path taken: original video message deleted, new message sent with the reward.
    assert len(bot.sent_videos) == 1
    assert len(bot.sent_messages) == 1  # fallback delete+send, not a second reveal

    with get_connection() as connection:
        user_cards_count = connection.execute(
            "SELECT COUNT(*) AS n FROM user_cards WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        openings_count = connection.execute(
            "SELECT COUNT(*) AS n FROM pack_openings WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)
        ).fetchone()["n"]
        reveal_status = connection.execute(
            "SELECT status FROM pack_pending_reveals WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)
        ).fetchone()["status"]

    assert user_cards_count == 1  # ровно одна карта выдана — не задвоена
    assert openings_count == 1  # ровно одно открытие пака
    assert reveal_status == "completed"  # fallback доставил награду успешно
