from app.services.admin_permissions import is_panel_admin


def is_admin(user_id: int | None) -> bool:
    return is_panel_admin(user_id)
