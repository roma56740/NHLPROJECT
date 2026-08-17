from app.database.db import get_connection, init_database


async def test_migrations_on_empty_database(stronghold_db):
    with get_connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
    assert "stronghold_events" in tables
    assert "stronghold_upgrade_steps" in tables
    assert "stronghold_fortresses" in tables
    assert "users" in tables  # существующие таблицы проекта не пострадали


async def test_migrations_are_safe_to_rerun_on_existing_schema(stronghold_db):
    await init_database()
    await init_database()
    with get_connection() as connection:
        events_count = connection.execute("SELECT COUNT(*) AS c FROM stronghold_events").fetchone()["c"]
    assert events_count == 1


async def test_seed_is_idempotent(stronghold_db):
    with get_connection() as connection:
        cards_before = connection.execute(
            "SELECT COUNT(*) AS c FROM cards WHERE collection_id = (SELECT id FROM collections WHERE code = 'the_stronghold')"
        ).fetchone()["c"]

    await init_database()
    await init_database()

    with get_connection() as connection:
        cards_after = connection.execute(
            "SELECT COUNT(*) AS c FROM cards WHERE collection_id = (SELECT id FROM collections WHERE code = 'the_stronghold')"
        ).fetchone()["c"]
        fortress_count = connection.execute("SELECT COUNT(*) AS c FROM stronghold_fortresses").fetchone()["c"]
        match_count = connection.execute("SELECT COUNT(*) AS c FROM stronghold_fortress_matches").fetchone()["c"]

    assert cards_before == 23
    assert cards_after == 23
    assert fortress_count == 15
    assert match_count == 90


async def test_upgrade_chain_totals_match_spec(stronghold_db):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS steps, SUM(ft_cost) AS ft, SUM(coins_cost) AS coins FROM stronghold_upgrade_steps"
        ).fetchone()
    assert row["steps"] == 7
    assert row["ft"] == 375
    assert row["coins"] == 4_050_000


async def test_fortress_ft_total_matches_spec(stronghold_db):
    with get_connection() as connection:
        row = connection.execute("SELECT SUM(first_completion_ft) AS total FROM stronghold_fortresses").fetchone()
    assert row["total"] == 220


async def test_mission_and_season_track_totals_match_spec(stronghold_db):
    with get_connection() as connection:
        daily_total = connection.execute(
            "SELECT SUM(reward_ft) AS t FROM stronghold_missions WHERE type = 'DAILY'"
        ).fetchone()["t"]
        weekly_total = connection.execute(
            "SELECT SUM(reward_ft) AS t FROM stronghold_missions WHERE type = 'WEEKLY'"
        ).fetchone()["t"]
        season_total = connection.execute("SELECT SUM(reward_ft) AS t FROM stronghold_season_track_levels").fetchone()["t"]

    assert daily_total == 4  # * 30 дней = 120
    assert weekly_total == 20  # * 4 недели = 80
    assert season_total == 50
