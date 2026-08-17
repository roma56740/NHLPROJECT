from app.services.stronghold_health import get_health_status


async def test_health_ok_after_seed(stronghold_db):
    result = await get_health_status()
    assert result.ok is True
    assert result.checks["database_connection"] is True
    assert result.checks["event_seeded"] is True
    assert result.checks["collection_complete"] is True
    assert result.checks["upgrade_chain_complete"] is True
    assert result.checks["fortress_count_complete"] is True
    assert "server_time_utc" in result.details
