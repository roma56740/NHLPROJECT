"""Ротация backup, диагностика, health-check (Этап 2 надёжности, см.
docs/TOURNAMENT_RELIABILITY_SPEC.md). Использует фикстуру stronghold_db (несмотря на
имя — общая: monkeypatch'ит DATABASE_PATH на временный файл и вызывает init_database())."""

import time

from app.services import backups, diagnostics, health_monitor
from tests.conftest import create_test_user


def test_backup_paths_follow_monkeypatched_database_path(stronghold_db):
    """Регрессионный тест на баг, который сам чуть не попал в прод в этой сессии:
    backups.py раньше делал `from app.database.db import DATABASE_PATH`, замораживая
    путь на момент первого импорта модуля — из-за этого пути к backups/predeploy_backups
    не следовали за monkeypatch в тестах (и потенциально — за любым легитимным поздним
    изменением DATABASE_PATH). backups_dir()/predeploy_backups_dir() обязаны быть внутри
    директории именно текущей (подменённой) БД."""
    assert backups.backups_dir().parent == stronghold_db.parent
    assert backups.predeploy_backups_dir().parent == stronghold_db.parent


def test_create_manual_backup_succeeds_and_passes_quick_check(stronghold_db):
    result = backups.create_backup("manual")
    assert result.success, result.message
    assert result.path is not None
    assert result.path.exists()
    assert backups.quick_check(result.path)


def test_manual_backup_retention_keeps_only_last_two(stronghold_db):
    paths = []
    for _ in range(4):
        result = backups.create_backup("manual")
        assert result.success, result.message
        paths.append(result.path)
        time.sleep(0.05)  # различимый mtime для сортировки по времени

    remaining = backups.list_backups("manual")
    assert len(remaining) == backups.RETENTION["manual"] == 2
    # должны остаться два САМЫХ СВЕЖИХ
    assert {p.name for p in remaining} == {paths[-1].name, paths[-2].name}


def test_daily_backup_retention_keeps_only_last_one(stronghold_db):
    for _ in range(3):
        result = backups.create_backup("daily")
        assert result.success, result.message
        time.sleep(0.05)
    assert len(backups.list_backups("daily")) == 1


def test_predeploy_backup_skipped_when_schema_version_unchanged(stronghold_db):
    first = backups.create_backup("predeploy")
    assert first.success and first.path is not None

    second = backups.create_backup("predeploy")
    assert second.success is True
    assert second.path is None  # пропущен, а не создан заново
    assert "не требуется" in second.message

    assert len(backups.list_backups("predeploy")) == 1


def test_predeploy_backup_created_again_after_schema_version_bump(stronghold_db, monkeypatch):
    first = backups.create_backup("predeploy")
    assert first.success and first.path is not None

    monkeypatch.setattr(backups, "SCHEMA_VERSION", backups.SCHEMA_VERSION + 1)
    second = backups.create_backup("predeploy")
    assert second.success is True
    assert second.path is not None  # версия изменилась -> backup реально создан
    assert len(backups.list_backups("predeploy")) == 1  # retention=1, старый удалён


def test_backup_refuses_when_source_db_fails_quick_check(stronghold_db, monkeypatch):
    monkeypatch.setattr(backups, "quick_check", lambda path: False)
    result = backups.create_backup("manual")
    assert result.success is False
    assert "quick_check" in result.message


def test_backup_stops_below_free_space_threshold(stronghold_db, monkeypatch):
    monkeypatch.setattr(backups, "free_space_percent", lambda path=None: 5.0)
    result = backups.create_backup("manual")
    assert result.success is False
    assert "места" in result.message


def test_delete_backups_over_limit(stronghold_db):
    for _ in range(3):
        backups.create_backup("manual")
        time.sleep(0.05)
    # create_backup уже enforced retention=2 после каждого вызова, добавим лишний файл
    # напрямую, чтобы явно проверить delete_backups_over_limit как отдельную операцию
    extra = backups.backups_dir() / "nhl_bot_manual_extra.sqlite3"
    extra.write_bytes(b"not a real db, just for count")
    assert len(backups.list_backups("manual")) == 3
    removed = backups.delete_backups_over_limit("manual")
    assert removed == 1
    assert len(backups.list_backups("manual")) == 2


# ---------------------------------------------------------------------------
# Диагностика
# ---------------------------------------------------------------------------

async def test_diagnostics_report_reflects_real_state(stronghold_db):
    await create_test_user("diag-user")
    backups.create_backup("manual")

    report = await diagnostics.build_diagnostics_report()
    assert report.db.ok is True
    assert report.db.quick_check_result == "ok"
    assert report.storage.backups_regular[0] == 1
    assert report.volume.free_percent > 0

    text = diagnostics.format_diagnostics_text(report)
    assert "Диагностика" in text
    assert "PRAGMA quick_check: ok" in text


async def test_diagnostics_detects_broken_database(stronghold_db, monkeypatch):
    monkeypatch.setattr(backups, "quick_check", lambda path: False)
    health = diagnostics.get_db_health()
    assert health.ok is False
    assert health.quick_check_result == "FAILED"


async def test_diagnostics_counts_stuck_matches(stronghold_db):
    from app.database.db import get_connection
    from app.services.creator_tournaments import STATUS_PLAYING

    creator_id = await create_test_user("diag-tourn-creator")
    with get_connection() as connection:
        connection.execute("UPDATE users SET is_creator=1 WHERE id=?", (creator_id,))
        connection.execute(
            "INSERT INTO creator_tournaments (creator_user_id, title, capacity, round_duration_minutes, status) VALUES (?, 't', 2, 60, 'active')",
            (creator_id,),
        )
        tid = connection.execute("SELECT id FROM creator_tournaments WHERE creator_user_id=?", (creator_id,)).fetchone()["id"]
        connection.execute(
            "INSERT INTO creator_tournament_matches (tournament_id, round_no, round_name, bracket_index, status, last_activity_at) VALUES (?, 1, 'r', 0, ?, datetime('now','-20 minutes'))",
            (tid, STATUS_PLAYING),
        )
        connection.commit()

    health = await diagnostics.get_tournament_health()
    assert health.stuck_matches == 1
    assert health.matches_playing == 1


# ---------------------------------------------------------------------------
# Health-check: cooldown и пороги Volume
# ---------------------------------------------------------------------------

class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


async def test_health_check_alerts_on_broken_db(stronghold_db, monkeypatch):
    health_monitor._last_alert_at.clear()
    monkeypatch.setattr(diagnostics, "get_db_health", lambda: diagnostics.DbHealth(ok=False, quick_check_result="FAILED", size_bytes=0, wal_size_bytes=0))
    monkeypatch.setattr(diagnostics, "get_volume_health", lambda: diagnostics.VolumeHealth(free_bytes=10**9, total_bytes=10**10, used_percent=10.0, free_percent=90.0))

    async def _no_stuck():
        return diagnostics.TournamentHealth(active_tournaments=0, matches_playing=0, stuck_matches=0)

    monkeypatch.setattr(diagnostics, "get_tournament_health", _no_stuck)

    bot = _FakeBot()
    await health_monitor.run_health_check(bot)
    assert any("quick_check" in text for _chat_id, text in bot.sent)


async def test_health_check_cooldown_prevents_spam(stronghold_db, monkeypatch):
    health_monitor._last_alert_at.clear()
    monkeypatch.setattr(diagnostics, "get_db_health", lambda: diagnostics.DbHealth(ok=False, quick_check_result="FAILED", size_bytes=0, wal_size_bytes=0))
    monkeypatch.setattr(diagnostics, "get_volume_health", lambda: diagnostics.VolumeHealth(free_bytes=10**9, total_bytes=10**10, used_percent=10.0, free_percent=90.0))

    async def _no_stuck():
        return diagnostics.TournamentHealth(active_tournaments=0, matches_playing=0, stuck_matches=0)

    monkeypatch.setattr(diagnostics, "get_tournament_health", _no_stuck)

    bot = _FakeBot()
    await health_monitor.run_health_check(bot)
    await health_monitor.run_health_check(bot)  # тот же тип проблемы сразу же

    db_alerts = [text for _chat_id, text in bot.sent if "quick_check" in text]
    assert len(db_alerts) == 1  # второй прогон подавлен cooldown'ом


async def test_health_check_critical_volume_alert(stronghold_db, monkeypatch):
    health_monitor._last_alert_at.clear()
    monkeypatch.setattr(diagnostics, "get_db_health", lambda: diagnostics.DbHealth(ok=True, quick_check_result="ok", size_bytes=100, wal_size_bytes=0))
    monkeypatch.setattr(diagnostics, "get_volume_health", lambda: diagnostics.VolumeHealth(free_bytes=1, total_bytes=1000, used_percent=99.9, free_percent=0.1))

    async def _no_stuck():
        return diagnostics.TournamentHealth(active_tournaments=0, matches_playing=0, stuck_matches=0)

    monkeypatch.setattr(diagnostics, "get_tournament_health", _no_stuck)

    bot = _FakeBot()
    await health_monitor.run_health_check(bot)
    assert any("Volume" in text and "🚨" in text for _chat_id, text in bot.sent)


async def test_health_check_alerts_on_stuck_matches(stronghold_db, monkeypatch):
    health_monitor._last_alert_at.clear()
    monkeypatch.setattr(diagnostics, "get_db_health", lambda: diagnostics.DbHealth(ok=True, quick_check_result="ok", size_bytes=100, wal_size_bytes=0))
    monkeypatch.setattr(diagnostics, "get_volume_health", lambda: diagnostics.VolumeHealth(free_bytes=10**9, total_bytes=10**10, used_percent=10.0, free_percent=90.0))

    async def _one_stuck():
        return diagnostics.TournamentHealth(active_tournaments=1, matches_playing=1, stuck_matches=1)

    monkeypatch.setattr(diagnostics, "get_tournament_health", _one_stuck)

    bot = _FakeBot()
    await health_monitor.run_health_check(bot)
    assert any("Зависших" in text for _chat_id, text in bot.sent)
