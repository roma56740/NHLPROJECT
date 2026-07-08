import sqlite3

from config import settings


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False

    if user_id in settings.admin_ids:
        return True

    try:
        connection = sqlite3.connect(settings.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT 1
                FROM bot_admins
                WHERE telegram_id = ? AND active = 1
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            return row is not None
        finally:
            connection.close()
    except sqlite3.Error:
        return False
