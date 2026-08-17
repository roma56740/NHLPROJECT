"""Реестр миграций, общий audit_log, application_errors (Этап 3 надёжности, см.
docs/TOURNAMENT_RELIABILITY_SPEC.md). Использует фикстуру stronghold_db (несмотря на
имя — общая: monkeypatch'ит DATABASE_PATH на временный файл и вызывает init_database())."""

from app.database import migrations
from app.database.db import get_connection
from app.services import admin_panel, audit_log, diagnostics, error_log
from app.services.creator_tournaments import create_tournament, mark_ready_and_play
from tests.conftest import create_test_user
from tests.test_creator_tournaments import _make_creator_with_bank_item, _pending_matches, _register_all, _setup_tournament


# ---------------------------------------------------------------------------
# Реестр миграций (database_migrations)
# ---------------------------------------------------------------------------

async def test_database_migrations_records_stage3_tables(stronghold_db):
    with get_connection() as connection:
        applied = {row["name"] for row in migrations.list_applied(connection)}
    assert "0001_create_audit_log" in applied
    assert "0002_create_application_errors" in applied


async def test_run_once_executes_migration_exactly_once(stronghold_db):
    calls = []

    def _bump(connection):
        calls.append(1)

    with get_connection() as connection:
        first = migrations.run_once(connection, "test_only_migration", _bump)
        second = migrations.run_once(connection, "test_only_migration", _bump)
        connection.commit()

    assert first is True
    assert second is False
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# audit_log
# ---------------------------------------------------------------------------

async def test_audit_log_record_committed_and_recent(stronghold_db):
    actor_id = await create_test_user("audit-actor")
    audit_log.record_committed(actor_id, "test:action", "test_entity", 42, {"foo": "bar"})

    rows = audit_log.recent(limit=5)
    assert rows
    latest = rows[0]
    assert latest["actor_user_id"] == actor_id
    assert latest["action"] == "test:action"
    assert latest["entity_type"] == "test_entity"
    assert latest["entity_id"] == 42
    assert "bar" in latest["details"]


async def test_creator_tournament_actions_are_mirrored_to_audit_log(stronghold_db):
    creator_id = await create_test_user("audit-creator")
    bank_item_id = await _make_creator_with_bank_item(creator_id)
    ok, msg, tid = await create_tournament(
        creator_id, "Audit Cup", "desc", 2, 60,
        [{"place_from": 1, "place_to": 1, "bank_item_id": bank_item_id, "quantity": 5}],
    )
    assert ok, msg

    rows = audit_log.recent(limit=20)
    matching = [r for r in rows if r["entity_type"] == "creator_tournament" and r["entity_id"] == tid]
    assert any(r["action"] == "tournament:created" for r in matching)


async def test_admin_role_changes_write_audit_log(stronghold_db):
    actor_id = await create_test_user("admin-actor")
    target_telegram_id = 555_555_555

    await admin_panel.add_admin(target_telegram_id, actor_id, role="content_admin")
    updated = await admin_panel.update_admin_role(target_telegram_id, "senior_admin", actor_user_id=actor_id)
    assert updated is True
    removed = await admin_panel.remove_admin(target_telegram_id, actor_user_id=actor_id)
    assert removed is True

    rows = audit_log.recent(limit=20)
    actions = [r["action"] for r in rows if r["entity_type"] == "bot_admin" and r["entity_id"] == target_telegram_id]
    assert "admin_added" in actions
    assert "admin_role_changed" in actions
    assert "admin_removed" in actions


# ---------------------------------------------------------------------------
# application_errors
# ---------------------------------------------------------------------------

async def test_error_log_record_and_query(stronghold_db):
    try:
        raise ValueError("boom for test")
    except ValueError as error:
        error_log.record_error("test_source", error, context="unit-test")

    recent = error_log.get_recent_errors(limit=1)
    assert recent
    assert recent[0]["source"] == "test_source"
    assert recent[0]["error_type"] == "ValueError"
    assert "boom for test" in recent[0]["message"]

    assert error_log.count_errors_since_hours(24) >= 1


async def test_crash_during_match_is_recorded_in_application_errors(stronghold_db, monkeypatch):
    creator_id, tid, players = await _setup_tournament(2, "err-log")
    await _register_all(tid, players)
    matches = await _pending_matches(tid)
    match_id = matches[0]["id"]

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated engine crash for error log")

    monkeypatch.setattr("app.services.matches.play_player_match", _boom)

    await mark_ready_and_play(match_id, int(matches[0]["player1_user_id"]))
    await mark_ready_and_play(match_id, int(matches[0]["player2_user_id"]))

    recent = error_log.get_recent_errors(limit=5)
    assert any("simulated engine crash for error log" in row["message"] for row in recent)
    assert any(row["source"] == "creator_tournaments.mark_ready_and_play" for row in recent)


async def test_diagnostics_report_reflects_recorded_errors(stronghold_db):
    try:
        raise RuntimeError("diagnostics visible error")
    except RuntimeError as error:
        error_log.record_error("test_source", error)

    report = await diagnostics.build_diagnostics_report()
    assert report.errors.count_last_24h >= 1
    assert report.errors.last_error_message and "diagnostics visible error" in report.errors.last_error_message

    text = diagnostics.format_diagnostics_text(report)
    assert "Ошибок за 24ч" in text
    assert "diagnostics visible error" in text
