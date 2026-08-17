"""Универсальная массовая загрузка данных из админ-панели.

Поддерживаются CSV, JSON и ZIP-пакеты (manifest.csv/manifest.json + assets/).
Импорт выполняется строго атомарно: если хотя бы одна строка не проходит
валидацию или запись в БД, изменения откатываются целиком.

Сервис намеренно использует белый список целей. Администратор не может выбрать
произвольную таблицу/колонку и обойти бизнес-ограничения проекта.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

from app.database.db import get_connection
from app.services.admin_permissions import (
    PERMISSION_ADMIN_PANEL,
    PERMISSION_BLACK_MARKET,
    PERMISSION_CARDS,
    PERMISSION_CHEMISTRY,
    PERMISSION_COSMETICS,
    PERMISSION_DAILY_LOGIN,
    PERMISSION_DIVISIONS,
    PERMISSION_EVENTS,
    PERMISSION_FREE_CARDS,
    PERMISSION_HOCKEY_PASS,
    PERMISSION_PACKS,
    PERMISSION_PROMO,
    PERMISSION_QUESTS,
    PERMISSION_RANKED,
    PERMISSION_REWARDS,
    PERMISSION_SALARIES,
    PERMISSION_SETTINGS,
    PERMISSION_STARTER_KIT,
    PERMISSION_STRONGHOLD,
    PERMISSION_USERS,
    PERMISSION_WALLETS,
    PERMISSION_WAR2,
)

MAX_ROWS = 2_000
MAX_ARCHIVE_FILES = 2_500
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
ALLOWED_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov"}
UPLOADS_ROOT = Path("assets/uploads")


@dataclass(frozen=True)
class BulkTarget:
    code: str
    title: str
    section: str
    permission: str
    table: str | None
    description: str
    headers: tuple[str, ...]
    example: dict[str, Any]
    required: tuple[str, ...] = ()
    key_fields: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    asset_column: str | None = None
    asset_dir: str | None = None
    special_handler: str | None = None


@dataclass(frozen=True)
class PreparedSource:
    manifest_path: Path
    original_name: str
    assets_root: Path | None = None


@dataclass(frozen=True)
class RowPreview:
    index: int
    display: str
    error: str | None


@dataclass(frozen=True)
class BulkPreview:
    target: BulkTarget
    rows: tuple[dict[str, Any], ...]
    previews: tuple[RowPreview, ...]

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def errors(self) -> tuple[RowPreview, ...]:
        return tuple(row for row in self.previews if row.error)

    @property
    def valid(self) -> int:
        return self.total - len(self.errors)


@dataclass(frozen=True)
class BulkApplyResult:
    target_code: str
    total: int
    inserted: int
    updated: int
    skipped: int


# Разделы используются и в интерфейсе, и для удобной навигации.
SECTION_TITLES: dict[str, str] = {
    "content": "🃏 Контент",
    "modes": "🎮 Режимы",
    "players": "👥 Игроки",
    "economy": "💰 Экономика",
    "system": "🛡 Система",
}


def _target(**kwargs: Any) -> BulkTarget:
    return BulkTarget(**kwargs)


TARGETS: dict[str, BulkTarget] = {
    # ---------- CONTENT ----------
    "collections": _target(
        code="collections", title="Коллекции", section="content", permission=PERMISSION_CARDS,
        table="collections", description="Создание и обновление коллекций карт.",
        headers=("code", "name", "description", "active", "is_exclusive"),
        example={"code": "ranked_s1", "name": "Ranked Season 1", "description": "Сезонная коллекция", "active": 1, "is_exclusive": 1},
        required=("code", "name"), key_fields=("code",), defaults={"description": "", "active": 1, "is_exclusive": 0},
    ),
    "cards": _target(
        code="cards", title="Карточки", section="content", permission=PERMISSION_CARDS,
        table="cards", description="Карты. В ZIP поле asset_file подхватывает изображение из assets/.",
        headers=("name", "player_key", "position", "overall", "team", "country", "collection_code", "rarity", "salary", "active", "image_path", "asset_file"),
        example={"name": "Sidney Crosby", "player_key": "sidney_crosby", "position": "F", "overall": 97, "team": "Pittsburgh Penguins", "country": "Canada", "collection_code": "ranked_s1", "rarity": "Legendary", "salary": 9500000, "active": 1, "image_path": "", "asset_file": "assets/crosby_97.png"},
        required=("name", "position", "overall", "team", "country", "collection_code", "rarity"),
        key_fields=("player_key", "overall", "collection_id"), defaults={"salary": 0, "active": 1, "image_path": "logo.png"},
        aliases={"collection": "collection_code"}, asset_column="image_path", asset_dir="cards",
    ),
    "packs": _target(
        code="packs", title="Паки", section="content", permission=PERMISSION_PACKS,
        table="packs", description="Обычные паки и их изображения.",
        headers=("code", "name", "description", "price_currency_code", "price_amount", "active", "is_shop_available", "is_starter", "sort_order", "image_path", "asset_file"),
        example={"code": "ranked_pack_1", "name": "Ranked Pack", "description": "Сезонный пак", "price_currency_code": "coins", "price_amount": 100000, "active": 1, "is_shop_available": 1, "is_starter": 0, "sort_order": 100, "image_path": "", "asset_file": "assets/ranked_pack.png"},
        required=("code", "name"), key_fields=("code",), defaults={"description": "", "price_amount": 0, "active": 1, "is_shop_available": 0, "is_starter": 0, "sort_order": 100},
        asset_column="image_path", asset_dir="packs",
    ),
    "pack_slots": _target(
        code="pack_slots", title="Слоты паков", section="content", permission=PERMISSION_PACKS,
        table="pack_slots", description="Правила слотов паков. pack_code и collection_code преобразуются в ID.",
        headers=("pack_code", "slot_number", "title", "collection_code", "position", "rarity", "rarity_chances", "min_overall", "max_overall", "special_collection_code", "special_chance_percent", "active"),
        example={"pack_code": "ranked_pack_1", "slot_number": 1, "title": "Основная карта", "collection_code": "ranked_s1", "position": "", "rarity": "", "rarity_chances": "{\"Legendary\":70,\"Icon\":30}", "min_overall": 92, "max_overall": 99, "special_collection_code": "", "special_chance_percent": 0, "active": 1},
        required=("pack_code", "slot_number"), key_fields=("pack_id", "slot_number"), defaults={"title": "", "special_chance_percent": 0, "active": 1},
    ),
    "pack_cards": _target(
        code="pack_cards", title="Пул карт паков", section="content", permission=PERMISSION_PACKS,
        table="pack_cards", description="Связи паков с конкретными картами.",
        headers=("pack_code", "card_id", "player_key", "overall", "collection_code"),
        example={"pack_code": "ranked_pack_1", "card_id": "", "player_key": "sidney_crosby", "overall": 97, "collection_code": "ranked_s1"},
        required=("pack_code",), key_fields=("pack_id", "card_id"),
    ),
    "cosmetics": _target(
        code="cosmetics", title="Косметика", section="content", permission=PERMISSION_COSMETICS,
        table="war2_cosmetic_items", description="Глобальная трейдабл-косметика: рамки, фоны, приписки и титулы.",
        headers=("type", "code", "title", "description", "rarity", "badge_text", "active", "image_path", "asset_file"),
        example={"type": "CARD_FRAME", "code": "ice_frame", "title": "Ice Frame", "description": "Ледяная рамка", "rarity": "Epic", "badge_text": "", "active": 1, "image_path": "", "asset_file": "assets/ice_frame.png"},
        required=("type", "code", "title", "rarity"), key_fields=("code",), defaults={"description": "", "active": 1},
        asset_column="image_path", asset_dir="cosmetics",
    ),
    "divisions": _target(
        code="divisions", title="Дивизионы", section="content", permission=PERMISSION_DIVISIONS,
        table="team_divisions", description="Дивизионы и их изображения.",
        headers=("code", "name", "active", "image_path", "asset_file"),
        example={"code": "atlantic", "name": "Atlantic", "active": 1, "image_path": "", "asset_file": "assets/atlantic.png"},
        required=("code", "name"), key_fields=("code",), defaults={"active": 1}, asset_column="image_path", asset_dir="divisions",
    ),
    "division_teams": _target(
        code="division_teams", title="Команды дивизионов", section="content", permission=PERMISSION_DIVISIONS,
        table="team_division_teams", description="Массовое распределение команд по дивизионам.",
        headers=("division_code", "team_name"), example={"division_code": "atlantic", "team_name": "Boston Bruins"},
        required=("division_code", "team_name"), key_fields=("team_name",),
    ),
    "animation_assets": _target(
        code="animation_assets", title="Картинки анимаций", section="content", permission=PERMISSION_DIVISIONS,
        table="animation_assets", description="Изображения команд, стран, дивизионов и стадий.",
        headers=("asset_type", "asset_key", "title", "image_path", "asset_file"),
        example={"asset_type": "team", "asset_key": "Boston Bruins", "title": "Boston Bruins", "image_path": "", "asset_file": "assets/boston.png"},
        required=("asset_type", "asset_key"), key_fields=("asset_type", "asset_key"), defaults={"title": ""}, asset_column="image_path", asset_dir="animation",
    ),
    "chemistry_rules": _target(
        code="chemistry_rules", title="Правила химии", section="content", permission=PERMISSION_CHEMISTRY,
        table="chemistry_rules", description="Правила химии по стране, команде или коллекции.",
        headers=("rule_type", "value", "required_cards", "bonus_ovr", "active"),
        example={"rule_type": "team", "value": "Boston Bruins", "required_cards": 3, "bonus_ovr": 1, "active": 1},
        required=("rule_type", "value"), key_fields=("rule_type", "value"), defaults={"required_cards": 3, "bonus_ovr": 1, "active": 1},
    ),
    "starter_kit": _target(
        code="starter_kit", title="Стартовый набор", section="content", permission=PERMISSION_STARTER_KIT,
        table="starter_kit_cards", description="Карты по слотам стартового набора.",
        headers=("slot_code", "card_id", "player_key", "overall", "collection_code"),
        example={"slot_code": "F1", "card_id": "", "player_key": "sidney_crosby", "overall": 97, "collection_code": "ranked_s1"},
        required=("slot_code",), key_fields=("slot_code",),
    ),

    # ---------- MODES ----------
    "ranked_leagues": _target(
        code="ranked_leagues", title="Ступени Ranked", section="modes", permission=PERMISSION_RANKED,
        table="ranked_leagues", description="Пороги и параметры рангов Ranked.",
        headers=("division_code", "tier_number", "title", "min_points", "sort_order", "icon", "active"),
        example={"division_code": "gold", "tier_number": 2, "title": "Gold II", "min_points": 1700, "sort_order": 8, "icon": "🥇", "active": 1},
        required=("division_code", "tier_number", "title", "min_points"), key_fields=("division_code", "tier_number"), defaults={"sort_order": 0, "icon": "", "active": 1},
    ),
    "ranked_packs": _target(
        code="ranked_packs", title="Ranked-паки", section="modes", permission=PERMISSION_RANKED,
        table="ranked_packs", description="Каталог Ranked-паков.",
        headers=("code", "division_code", "name", "description", "active"),
        example={"code": "gold_pack", "division_code": "gold", "name": "Gold Pack", "description": "Награда Gold", "active": 1},
        required=("code", "division_code", "name"), key_fields=("code",), defaults={"description": "", "active": 1},
    ),
    "ranked_pack_slots": _target(
        code="ranked_pack_slots", title="Слоты Ranked-паков", section="modes", permission=PERMISSION_RANKED,
        table="ranked_pack_slots", description="Слоты Ranked-паков.",
        headers=("ranked_pack_code", "slot_number", "reward_type", "currency_code", "amount", "cosmetic_code", "active"),
        example={"ranked_pack_code": "gold_pack", "slot_number": 1, "reward_type": "card", "currency_code": "", "amount": 1, "cosmetic_code": "", "active": 1},
        required=("ranked_pack_code", "slot_number", "reward_type"), key_fields=("pack_id", "slot_number"), defaults={"amount": 0, "active": 1},
    ),
    "ranked_pack_cards": _target(
        code="ranked_pack_cards", title="Карты Ranked-паков", section="modes", permission=PERMISSION_RANKED,
        table="ranked_pack_cards", description="Пул конкретных карт Ranked-паков.",
        headers=("ranked_pack_code", "card_id", "player_key", "overall", "collection_code"),
        example={"ranked_pack_code": "gold_pack", "card_id": "", "player_key": "sidney_crosby", "overall": 97, "collection_code": "ranked_s1"},
        required=("ranked_pack_code",), key_fields=("pack_id", "card_id"),
    ),
    "ranked_pass_rewards": _target(
        code="ranked_pass_rewards", title="Награды Ranked Pass", section="modes", permission=PERMISSION_RANKED,
        table="ranked_pass_rewards", description="Free/Gold/Platinum награды Ranked Pass.",
        headers=("pass_id", "level", "track", "reward_type", "currency_code", "amount", "pack_code", "card_id", "cosmetic_code", "title", "active"),
        example={"pass_id": 1, "level": 1, "track": "free", "reward_type": "currency", "currency_code": "coins", "amount": 10000, "pack_code": "", "card_id": "", "cosmetic_code": "", "title": "10 000 Coins", "active": 1},
        required=("pass_id", "level", "track", "reward_type"), key_fields=("pass_id", "level", "track"), defaults={"amount": 0, "title": "", "active": 1},
    ),
    "stronghold_upgrade_steps": _target(
        code="stronghold_upgrade_steps", title="Upgrade Chain", section="modes", permission=PERMISSION_STRONGHOLD,
        table="stronghold_upgrade_steps", description="Этапы улучшения карты Stronghold.",
        headers=("event_id", "step_order", "from_card_id", "to_card_id", "ft_cost", "coins_cost"),
        example={"event_id": 1, "step_order": 1, "from_card_id": 100, "to_card_id": 101, "ft_cost": 25, "coins_cost": 150000},
        required=("event_id", "step_order", "from_card_id", "to_card_id"), key_fields=("event_id", "step_order"), defaults={"ft_cost": 0, "coins_cost": 0},
    ),
    "stronghold_fortresses": _target(
        code="stronghold_fortresses", title="Крепости Stronghold", section="modes", permission=PERMISSION_STRONGHOLD,
        table="stronghold_fortresses", description="Крепости события.",
        headers=("event_id", "order_index", "code", "title", "description", "is_boss", "first_completion_ft", "repeat_coins_reward", "active", "image_path", "asset_file"),
        example={"event_id": 1, "order_index": 1, "code": "tower_1", "title": "Первая башня", "description": "Начало штурма", "is_boss": 0, "first_completion_ft": 20, "repeat_coins_reward": 10000, "active": 1, "image_path": "", "asset_file": "assets/tower_1.png"},
        required=("event_id", "order_index", "code", "title"), key_fields=("event_id", "order_index"), defaults={"description": "", "is_boss": 0, "first_completion_ft": 0, "repeat_coins_reward": 0, "active": 1}, asset_column="image_path", asset_dir="stronghold_fortresses",
    ),
    "stronghold_matches": _target(
        code="stronghold_matches", title="Матчи крепостей", section="modes", permission=PERMISSION_STRONGHOLD,
        table="stronghold_fortress_matches", description="Шесть матчей каждой крепости.",
        headers=("fortress_id", "order_index", "opponent_name", "opponent_ovr", "star_rules", "active"),
        example={"fortress_id": 1, "order_index": 1, "opponent_name": "Steel Guard", "opponent_ovr": 92, "star_rules": "[]", "active": 1},
        required=("fortress_id", "order_index", "opponent_name", "opponent_ovr"), key_fields=("fortress_id", "order_index"), defaults={"star_rules": "[]", "active": 1},
    ),
    "stronghold_missions": _target(
        code="stronghold_missions", title="Задания Stronghold", section="modes", permission=PERMISSION_STRONGHOLD,
        table="stronghold_missions", description="Ежедневные, недельные и сезонные задания Stronghold.",
        headers=("event_id", "code", "type", "title", "description", "condition_type", "target_value", "reward_ft", "reward_coins", "reward_xp", "sort_order", "active"),
        example={"event_id": 1, "code": "daily_win_3", "type": "DAILY", "title": "Три победы", "description": "Победи 3 раза", "condition_type": "win_matches", "target_value": 3, "reward_ft": 5, "reward_coins": 5000, "reward_xp": 100, "sort_order": 1, "active": 1},
        required=("event_id", "code", "type", "title", "condition_type"), key_fields=("event_id", "code"), defaults={"description": "", "target_value": 1, "reward_ft": 0, "reward_coins": 0, "reward_xp": 0, "sort_order": 100, "active": 1},
    ),
    "stronghold_track": _target(
        code="stronghold_track", title="Season Track Stronghold", section="modes", permission=PERMISSION_STRONGHOLD,
        table="stronghold_season_track_levels", description="Уровни сезонной шкалы Stronghold.",
        headers=("event_id", "level", "xp_threshold", "reward_ft", "reward_coins", "pack_code", "title"),
        example={"event_id": 1, "level": 1, "xp_threshold": 100, "reward_ft": 0, "reward_coins": 10000, "pack_code": "", "title": "10 000 Coins"},
        required=("event_id", "level", "xp_threshold"), key_fields=("event_id", "level"), defaults={"reward_ft": 0, "reward_coins": 0, "title": ""},
    ),
    "stronghold_store": _target(
        code="stronghold_store", title="Магазин Stronghold", section="modes", permission=PERMISSION_STRONGHOLD,
        table="stronghold_store_products", description="Товары магазина Stronghold.",
        headers=("event_id", "code", "category", "title", "description", "price_currency_code", "price_amount", "purchase_limit", "starts_at", "ends_at", "contents", "sort_order", "active", "image_path", "asset_file"),
        example={"event_id": 1, "code": "ft_pack", "category": "Packs", "title": "Stronghold Pack", "description": "Пак события", "price_currency_code": "FT", "price_amount": 50, "purchase_limit": 1, "starts_at": "", "ends_at": "", "contents": '[{"type":"pack","pack_id":1,"quantity":1}]', "sort_order": 1, "active": 1, "image_path": "", "asset_file": "assets/ft_pack.png"},
        required=("event_id", "code", "category", "title", "price_currency_code", "price_amount"), key_fields=("event_id", "code"), defaults={"description": "", "purchase_limit": 0, "contents": "[]", "sort_order": 100, "active": 1}, asset_column="image_path", asset_dir="stronghold_store",
    ),
    "war2_modes": _target(
        code="war2_modes", title="Режимы Clan War", section="modes", permission=PERMISSION_WAR2,
        table="war2_modes", description="Настройки Clone War, Salary War и Wild Card.",
        headers=("code", "title", "description", "uses_draft", "active", "sort_order"),
        example={"code": "SALARY_WAR", "title": "Salary War", "description": "Драфт с лимитом", "uses_draft": 1, "active": 1, "sort_order": 2},
        required=("code", "title"), key_fields=("code",), defaults={"description": "", "uses_draft": 1, "active": 1, "sort_order": 100},
    ),
    "events": _target(
        code="events", title="События", section="modes", permission=PERMISSION_EVENTS,
        table="events", description="Игровые события с наградами и обложками.",
        headers=("title", "description", "target_type", "target_value", "reward_type", "reward_currency_code", "reward_amount", "reward_pack_id", "reward_card_id", "start_at", "end_at", "active", "image_path", "asset_file"),
        example={"title": "Weekend Wins", "description": "Выиграй 10 матчей", "target_type": "matches_won", "target_value": 10, "reward_type": "currency", "reward_currency_code": "coins", "reward_amount": 50000, "reward_pack_id": "", "reward_card_id": "", "start_at": "2026-08-01 00:00:00", "end_at": "2026-08-03 23:59:59", "active": 1, "image_path": "", "asset_file": "assets/weekend.png"},
        required=("title", "target_type", "reward_type"), key_fields=("title", "start_at"), defaults={"description": "", "target_value": 1, "reward_amount": 1, "active": 1}, asset_column="image_path", asset_dir="events",
    ),
    "black_market_items": _target(
        code="black_market_items", title="Пул Чёрного рынка", section="modes", permission=PERMISSION_BLACK_MARKET,
        table="black_market_pool_items", description="Карты, паки, валюта и косметика Чёрного рынка.",
        headers=("item_type", "currency_code", "amount", "pack_code", "card_id", "cosmetic_code", "rarity", "title", "description", "price_currency_code", "price_mode", "price_amount", "price_min_amount", "price_max_amount", "max_stock_per_rotation", "personal_purchase_limit", "selection_weight", "active"),
        example={"item_type": "cosmetic", "currency_code": "", "amount": 1, "pack_code": "", "card_id": "", "cosmetic_code": "ice_frame", "rarity": "Epic", "title": "Ice Frame", "description": "Ледяная рамка", "price_currency_code": "rubles", "price_mode": "FIXED", "price_amount": 150, "price_min_amount": "", "price_max_amount": "", "max_stock_per_rotation": 1, "personal_purchase_limit": 1, "selection_weight": 10, "active": 1},
        required=("item_type", "rarity", "price_currency_code", "price_mode"), key_fields=("item_type", "title", "rarity"), defaults={"amount": 1, "price_amount": 0, "max_stock_per_rotation": 1, "personal_purchase_limit": 0, "selection_weight": 1, "active": 1},
    ),
    "black_market_weights": _target(
        code="black_market_weights", title="Веса Чёрного рынка", section="modes", permission=PERMISSION_BLACK_MARKET,
        table="black_market_rarity_weights", description="Вероятности редкостей Чёрного рынка.",
        headers=("rarity", "weight"), example={"rarity": "Epic", "weight": 20}, required=("rarity", "weight"), key_fields=("rarity",),
    ),

    # ---------- PLAYERS ----------
    "wallet_adjustments": _target(
        code="wallet_adjustments", title="Массовые изменения валют", section="players", permission=PERMISSION_WALLETS,
        table=None, special_handler="wallet_adjustments", description="Начисление, списание или установка балансов по Telegram ID.",
        headers=("telegram_id", "currency_code", "operation", "amount"),
        example={"telegram_id": 123456789, "currency_code": "coins", "operation": "add", "amount": 100000},
        required=("telegram_id", "currency_code", "operation", "amount"), key_fields=("telegram_id", "currency_code"),
    ),
    "card_grants": _target(
        code="card_grants", title="Массовая выдача карт", section="players", permission=PERMISSION_USERS,
        table=None, special_handler="card_grants", description="Выдача нескольких экземпляров карт игрокам.",
        headers=("telegram_id", "card_id", "player_key", "overall", "collection_code", "quantity", "source"),
        example={"telegram_id": 123456789, "card_id": "", "player_key": "sidney_crosby", "overall": 97, "collection_code": "ranked_s1", "quantity": 1, "source": "bulk_admin"},
        required=("telegram_id",), defaults={"quantity": 1, "source": "bulk_admin"},
    ),
    "pack_grants": _target(
        code="pack_grants", title="Массовая выдача паков", section="players", permission=PERMISSION_USERS,
        table=None, special_handler="pack_grants", description="Выдача паков по Telegram ID.",
        headers=("telegram_id", "pack_code", "quantity"), example={"telegram_id": 123456789, "pack_code": "ranked_pack_1", "quantity": 1},
        required=("telegram_id", "pack_code"), defaults={"quantity": 1},
    ),
    "cosmetic_grants": _target(
        code="cosmetic_grants", title="Массовая выдача косметики", section="players", permission=PERMISSION_COSMETICS,
        table=None, special_handler="cosmetic_grants", description="Каждая quantity создаёт отдельный трейдабл-экземпляр косметики.",
        headers=("telegram_id", "cosmetic_code", "quantity", "source"), example={"telegram_id": 123456789, "cosmetic_code": "ice_frame", "quantity": 2, "source": "bulk_admin"},
        required=("telegram_id", "cosmetic_code"), defaults={"quantity": 1, "source": "bulk_admin"},
    ),

    # ---------- ECONOMY ----------
    "salaries": _target(
        code="salaries", title="Зарплаты карт", section="economy", permission=PERMISSION_SALARIES,
        table=None, special_handler="salaries", description="Массовое обновление зарплат карт.",
        headers=("card_id", "player_key", "overall", "collection_code", "salary"),
        example={"card_id": "", "player_key": "sidney_crosby", "overall": 97, "collection_code": "ranked_s1", "salary": 9500000},
        required=("salary",),
    ),
    "reward_settings": _target(
        code="reward_settings", title="Системные награды", section="economy", permission=PERMISSION_REWARDS,
        table="reward_settings", description="Настройки наград за матчи и другие действия.",
        headers=("key", "title", "reward_type", "currency_code", "amount", "pack_code", "card_id", "active"),
        example={"key": "match_win", "title": "Победа", "reward_type": "currency", "currency_code": "coins", "amount": 5000, "pack_code": "", "card_id": "", "active": 1},
        required=("key", "title", "reward_type"), key_fields=("key",), defaults={"amount": 0, "active": 1},
    ),
    "quests": _target(
        code="quests", title="Задания", section="economy", permission=PERMISSION_QUESTS,
        table="quests", description="Ежедневные и сезонные задания.",
        headers=("code", "title", "description", "period_type", "target_type", "target_value", "bp_reward", "coins_reward", "active", "sort_order"),
        example={"code": "daily_win_3", "title": "Три победы", "description": "Победи 3 раза", "period_type": "daily", "target_type": "matches_won", "target_value": 3, "bp_reward": 20, "coins_reward": 5000, "active": 1, "sort_order": 1},
        required=("code", "title", "period_type", "target_type"), key_fields=("code",), defaults={"description": "", "target_value": 1, "bp_reward": 0, "coins_reward": 0, "active": 1, "sort_order": 100},
    ),
    "hockey_pass_rewards": _target(
        code="hockey_pass_rewards", title="Награды Hockey Pass", section="economy", permission=PERMISSION_HOCKEY_PASS,
        table="hockey_pass_rewards", description="Free/Premium награды Hockey Pass.",
        headers=("pass_id", "level", "track", "reward_type", "currency_code", "amount", "pack_code", "card_id", "title", "active"),
        example={"pass_id": 1, "level": 1, "track": "free", "reward_type": "currency", "currency_code": "coins", "amount": 5000, "pack_code": "", "card_id": "", "title": "5 000 Coins", "active": 1},
        required=("pass_id", "level", "track", "reward_type"), key_fields=("pass_id", "level", "track"), defaults={"amount": 0, "title": "", "active": 1},
    ),
    "daily_login_rewards": _target(
        code="daily_login_rewards", title="Ежедневный вход", section="economy", permission=PERMISSION_DAILY_LOGIN,
        table="daily_login_rewards", description="Награды дней 1–7.",
        headers=("day", "coins", "rubles", "pack_code"), example={"day": 7, "coins": 15000, "rubles": 3, "pack_code": "legendary_pack"},
        required=("day",), key_fields=("day",), defaults={"coins": 0, "rubles": 0},
    ),
    "promo_codes": _target(
        code="promo_codes", title="Промокоды", section="economy", permission=PERMISSION_PROMO,
        table="promo_codes", description="Массовое создание и обновление промокодов.",
        headers=("code", "coins", "rubles", "pack_code", "bp_points", "max_activations", "per_user_limit", "expires_at", "active"),
        example={"code": "WELCOME26", "coins": 25000, "rubles": 0, "pack_code": "starter_pack", "bp_points": 0, "max_activations": 500, "per_user_limit": 1, "expires_at": "2026-08-31 23:59:59", "active": 1},
        required=("code",), key_fields=("code",), defaults={"coins": 0, "rubles": 0, "bp_points": 0, "max_activations": 0, "per_user_limit": 1, "active": 1},
    ),
    "season_rewards": _target(
        code="season_rewards", title="Награды сезона", section="economy", permission=PERMISSION_REWARDS,
        table="season_reward_tiers", description="Награды по диапазонам мест сезона.",
        headers=("tier_key", "coins", "rubles", "pack_code"), example={"tier_key": "T1", "coins": 500000, "rubles": 100, "pack_code": "winners_pack"},
        required=("tier_key",), key_fields=("tier_key",), defaults={"coins": 0, "rubles": 0},
    ),

    # ---------- SYSTEM ----------
    "game_settings": _target(
        code="game_settings", title="Настройки проекта", section="system", permission=PERMISSION_SETTINGS,
        table="game_settings", description="Массовое обновление key/value. Только существующие или явно указанные ключи.",
        headers=("key", "value"), example={"key": "match_win_coins", "value": "5000"}, required=("key", "value"), key_fields=("key",),
    ),
}


# Некоторые схемы менялись между релизами. Фильтрация по реальным колонкам делает
# импорт обратимо совместимым и не даёт падать из-за необязательного нового поля.
def _table_columns(connection: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {str(row["name"]): row for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def list_targets(section: str | None = None) -> list[BulkTarget]:
    values = list(TARGETS.values())
    if section is not None:
        values = [item for item in values if item.section == section]
    return sorted(values, key=lambda item: item.title.lower())


def get_target(code: str) -> BulkTarget | None:
    return TARGETS.get(str(code or "").strip())


def template_csv_bytes(target: BulkTarget) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(target.headers), extrasaction="ignore")
    writer.writeheader()
    writer.writerow({key: target.example.get(key, "") for key in target.headers})
    return stream.getvalue().encode("utf-8-sig")


def template_json_bytes(target: BulkTarget) -> bytes:
    return json.dumps({"target": target.code, "rows": [target.example]}, ensure_ascii=False, indent=2).encode("utf-8")


def _safe_zip_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"небезопасный путь в ZIP: {name}")
    return path


def prepare_source(upload_path: Path, work_dir: Path, original_name: str | None = None) -> PreparedSource:
    suffix = upload_path.suffix.lower()
    original_name = original_name or upload_path.name
    work_dir.mkdir(parents=True, exist_ok=True)

    if suffix in {".csv", ".json"}:
        destination = work_dir / f"manifest{suffix}"
        if upload_path.resolve() != destination.resolve():
            shutil.copy2(upload_path, destination)
        return PreparedSource(destination, original_name, None)

    if suffix != ".zip":
        raise ValueError("поддерживаются только CSV, JSON и ZIP")

    extract_dir = work_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    total_size = 0
    with zipfile.ZipFile(upload_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise ValueError(f"слишком много файлов в ZIP: {len(members)}")
        for info in members:
            safe_path = _safe_zip_member(info.filename)
            total_size += int(info.file_size)
            if total_size > MAX_UNPACKED_BYTES:
                raise ValueError("распакованный ZIP превышает 200 МБ")
            target_path = extract_dir.joinpath(*safe_path.parts)
            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)

    candidates = [
        extract_dir / "manifest.csv",
        extract_dir / "manifest.json",
        extract_dir / "data.csv",
        extract_dir / "data.json",
    ]
    manifest = next((path for path in candidates if path.exists()), None)
    if manifest is None:
        found = list(extract_dir.rglob("*.csv")) + list(extract_dir.rglob("*.json"))
        if len(found) == 1:
            manifest = found[0]
    if manifest is None:
        raise ValueError("в ZIP не найден manifest.csv или manifest.json")
    return PreparedSource(manifest, original_name, extract_dir)


def _decode_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("не удалось определить кодировку файла")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    text = _decode_text(path)
    if suffix == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("rows", payload.get("items"))
        if not isinstance(payload, list):
            raise ValueError("JSON должен быть массивом строк или объектом с полем rows")
        rows = [dict(item) for item in payload if isinstance(item, dict)]
    elif suffix == ".csv":
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        rows = [dict(row) for row in reader]
    else:
        raise ValueError("manifest должен быть CSV или JSON")

    if not rows:
        raise ValueError("файл не содержит строк")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"максимум {MAX_ROWS} строк за одну загрузку")
    return rows


def _clean_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _normalize_row(target: BulkTarget, raw: dict[str, Any]) -> dict[str, Any]:
    aliases = {_clean_key(key): value for key, value in target.aliases.items()}
    allowed = set(target.headers)
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        name = _clean_key(key)
        name = aliases.get(name, name)
        if name not in allowed:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
        normalized[name] = value
    for key, value in target.defaults.items():
        if normalized.get(key) is None:
            normalized[key] = value
    return normalized


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9а-яё]+", "_", value, flags=re.IGNORECASE)
    return value.strip("_") or "card"


def _int(value: Any, field_name: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(float(str(value).replace(" ", "").replace(",", ".")))
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}: требуется целое число") from None
    if minimum is not None and result < minimum:
        raise ValueError(f"{field_name}: минимум {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{field_name}: максимум {maximum}")
    return result


def _optional_int(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    return _int(value, field_name)


def _collection_id(connection: sqlite3.Connection, row: dict[str, Any], prefix: str = "collection") -> int | None:
    direct = row.get(f"{prefix}_id")
    if direct not in (None, ""):
        return _int(direct, f"{prefix}_id", minimum=1)
    code = row.get(f"{prefix}_code")
    if code in (None, ""):
        return None
    found = connection.execute("SELECT id FROM collections WHERE code = ? OR name = ? LIMIT 1", (str(code), str(code))).fetchone()
    if found is None:
        raise ValueError(f"коллекция не найдена: {code}")
    return int(found["id"])


def _pack_id(connection: sqlite3.Connection, value: Any, *, ranked: bool = False) -> int | None:
    if value in (None, ""):
        return None
    table = "ranked_packs" if ranked else "packs"
    found = connection.execute(f"SELECT id FROM {table} WHERE code = ? LIMIT 1", (str(value),)).fetchone()
    if found is None:
        raise ValueError(f"пак не найден: {value}")
    return int(found["id"])


def _cosmetic_id(connection: sqlite3.Connection, value: Any) -> int | None:
    if value in (None, ""):
        return None
    found = connection.execute("SELECT id FROM war2_cosmetic_items WHERE code = ? LIMIT 1", (str(value),)).fetchone()
    if found is None:
        raise ValueError(f"косметика не найдена: {value}")
    return int(found["id"])


def _user_id(connection: sqlite3.Connection, telegram_id: Any) -> int:
    tid = _int(telegram_id, "telegram_id", minimum=1)
    found = connection.execute("SELECT id FROM users WHERE telegram_id = ? LIMIT 1", (tid,)).fetchone()
    if found is None:
        raise ValueError(f"игрок с Telegram ID {tid} не найден")
    return int(found["id"])


def _card_id(connection: sqlite3.Connection, row: dict[str, Any]) -> int:
    direct = row.get("card_id")
    if direct not in (None, ""):
        card_id = _int(direct, "card_id", minimum=1)
        found = connection.execute("SELECT id FROM cards WHERE id = ?", (card_id,)).fetchone()
        if found is None:
            raise ValueError(f"карта ID {card_id} не найдена")
        return card_id
    player_key = row.get("player_key")
    overall = row.get("overall")
    if not player_key or overall in (None, ""):
        raise ValueError("укажи card_id или player_key + overall")
    params: list[Any] = [str(player_key), _int(overall, "overall", minimum=1, maximum=110)]
    sql = "SELECT id FROM cards WHERE player_key = ? AND overall = ?"
    collection_id = _collection_id(connection, row)
    if collection_id is not None:
        sql += " AND collection_id = ?"
        params.append(collection_id)
    sql += " ORDER BY id DESC LIMIT 1"
    found = connection.execute(sql, params).fetchone()
    if found is None:
        raise ValueError(f"карта не найдена: {player_key} {overall} OVR")
    return int(found["id"])


def _coerce_direct_types(connection: sqlite3.Connection, table: str, row: dict[str, Any]) -> dict[str, Any]:
    columns = _table_columns(connection, table)
    result: dict[str, Any] = {}
    for key, value in row.items():
        if key not in columns or key in {"id", "created_at", "updated_at"}:
            continue
        if value is None:
            result[key] = None
            continue
        declared = str(columns[key]["type"] or "").upper()
        if "INT" in declared:
            result[key] = _int(value, key)
        else:
            result[key] = str(value)
    return result


def _prepare_row(connection: sqlite3.Connection, target: BulkTarget, row: dict[str, Any], *, assets_root: Path | None, commit_assets: bool, created_assets: list[Path] | None = None) -> dict[str, Any]:
    for required in target.required:
        if row.get(required) in (None, ""):
            raise ValueError(f"нет обязательного поля {required}")

    # Общие проверки и преобразования.
    if "active" in row and row["active"] is not None:
        row["active"] = 1 if _int(row["active"], "active") else 0
    if target.code == "cards":
        row["player_key"] = str(row.get("player_key") or _slug(str(row["name"])))
        row["position"] = str(row["position"]).upper()
        if row["position"] not in {"G", "D", "F"}:
            raise ValueError("position должна быть G, D или F")
        row["overall"] = _int(row["overall"], "overall", minimum=1, maximum=110)
        row["collection_id"] = _collection_id(connection, row)
        if row["collection_id"] is None:
            raise ValueError("collection_code обязателен")
        rarity = str(row["rarity"]).title()
        if rarity not in {"Common", "Rare", "Epic", "Legendary", "Event", "Icon"}:
            raise ValueError("неверная rarity")
        row["rarity"] = rarity
    elif target.code == "pack_slots":
        row["pack_id"] = _pack_id(connection, row.get("pack_code"))
        row["collection_id"] = _collection_id(connection, row)
        row["special_collection_id"] = _collection_id(connection, row, "special_collection")
    elif target.code == "pack_cards":
        row["pack_id"] = _pack_id(connection, row.get("pack_code"))
        row["card_id"] = _card_id(connection, row)
    elif target.code == "division_teams":
        found = connection.execute("SELECT id FROM team_divisions WHERE code = ? OR name = ? LIMIT 1", (str(row.get("division_code")), str(row.get("division_code")))).fetchone()
        if found is None:
            raise ValueError(f"дивизион не найден: {row.get('division_code')}")
        row["division_id"] = int(found["id"])
    elif target.code == "starter_kit":
        row["card_id"] = _card_id(connection, row)
    elif target.code == "ranked_pack_slots":
        row["pack_id"] = _pack_id(connection, row.get("ranked_pack_code"), ranked=True)
        row["cosmetic_item_id"] = _cosmetic_id(connection, row.get("cosmetic_code"))
    elif target.code == "ranked_pack_cards":
        row["pack_id"] = _pack_id(connection, row.get("ranked_pack_code"), ranked=True)
        row["card_id"] = _card_id(connection, row)
    elif target.code in {"ranked_pass_rewards", "hockey_pass_rewards"}:
        row["pack_id"] = _pack_id(connection, row.get("pack_code"))
        row["cosmetic_item_id"] = _cosmetic_id(connection, row.get("cosmetic_code")) if target.code == "ranked_pass_rewards" else None
        if row.get("card_id") not in (None, ""):
            row["card_id"] = _card_id(connection, row)
    elif target.code == "black_market_items":
        row["pack_id"] = _pack_id(connection, row.get("pack_code"))
        row["cosmetic_item_id"] = _cosmetic_id(connection, row.get("cosmetic_code"))
        if row.get("card_id") not in (None, ""):
            row["card_id"] = _card_id(connection, row)
    elif target.code == "stronghold_track":
        row["reward_pack_id"] = _pack_id(connection, row.get("pack_code"))
    elif target.code in {"reward_settings", "daily_login_rewards", "promo_codes", "season_rewards"}:
        row["pack_id"] = _pack_id(connection, row.get("pack_code"))
        if target.code == "reward_settings" and row.get("card_id") not in (None, ""):
            row["card_id"] = _card_id(connection, row)

    # ZIP-ассет копируется только на commit, при preview проверяется существование.
    asset_file = row.get("asset_file")
    if target.asset_column and asset_file:
        if assets_root is None:
            raise ValueError("asset_file разрешён только в ZIP-пакете")
        safe = _safe_zip_member(str(asset_file))
        source = assets_root.joinpath(*safe.parts)
        if not source.exists() or not source.is_file():
            raise ValueError(f"asset_file не найден в ZIP: {asset_file}")
        if source.suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
            raise ValueError(f"неподдерживаемый тип ассета: {source.suffix}")
        if commit_assets:
            destination_dir = UPLOADS_ROOT / str(target.asset_dir or target.code)
            destination_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", source.name)
            destination = destination_dir / safe_name
            counter = 1
            while destination.exists() and source.read_bytes() != destination.read_bytes():
                destination = destination_dir / f"{source.stem}_{counter}{source.suffix.lower()}"
                counter += 1
            if not destination.exists():
                shutil.copy2(source, destination)
                if created_assets is not None:
                    created_assets.append(destination)
            row[target.asset_column] = destination.as_posix()
        elif not row.get(target.asset_column):
            row[target.asset_column] = f"{UPLOADS_ROOT.as_posix()}/{target.asset_dir or target.code}/{source.name}"

    if target.special_handler:
        return row
    assert target.table is not None
    return _coerce_direct_types(connection, target.table, row)


def _display_row(target: BulkTarget, row: dict[str, Any]) -> str:
    preferred = (
        "name", "title", "code", "player_key", "team_name", "telegram_id",
        "key", "rarity", "level", "fortress_number", "slot_number",
    )
    pieces: list[str] = []
    for key in preferred:
        value = row.get(key)
        if value not in (None, ""):
            pieces.append(f"{key}={value}")
        if len(pieces) >= 3:
            break
    return " · ".join(pieces) or target.title


def build_preview(target: BulkTarget, source: PreparedSource) -> BulkPreview:
    raw_rows = _load_rows(source.manifest_path)
    normalized_rows = tuple(_normalize_row(target, row) for row in raw_rows)
    previews: list[RowPreview] = []
    with get_connection() as connection:
        for index, row in enumerate(normalized_rows, start=1):
            savepoint = f"bulk_preview_{index}"
            try:
                prepared = _prepare_row(connection, target, dict(row), assets_root=source.assets_root, commit_assets=False)
                # Проверяем реальные FK/CHECK/UNIQUE и специальные операции внутри
                # SAVEPOINT, затем откатываем. Так предпросмотр не обещает успех,
                # который затем упадёт только на кнопке подтверждения.
                connection.execute(f"SAVEPOINT {savepoint}")
                if target.special_handler:
                    _apply_special(connection, target, prepared)
                else:
                    _manual_upsert(connection, target, prepared)
                connection.execute(f"ROLLBACK TO {savepoint}")
                connection.execute(f"RELEASE {savepoint}")
                previews.append(RowPreview(index, _display_row(target, prepared), None))
            except Exception as error:  # noqa: BLE001
                try:
                    connection.execute(f"ROLLBACK TO {savepoint}")
                    connection.execute(f"RELEASE {savepoint}")
                except sqlite3.Error:
                    pass
                previews.append(RowPreview(index, _display_row(target, row), str(error)))
    return BulkPreview(target, normalized_rows, tuple(previews))


def _manual_upsert(connection: sqlite3.Connection, target: BulkTarget, row: dict[str, Any]) -> str:
    assert target.table is not None
    columns = _table_columns(connection, target.table)
    clean = {key: value for key, value in row.items() if key in columns and key not in {"id", "created_at", "updated_at"}}
    if not clean:
        raise ValueError("после нормализации не осталось колонок для записи")

    keys = [key for key in target.key_fields if key in clean]
    existing = None
    where = ""
    key_values: tuple[Any, ...] = ()
    if keys:
        where = " AND ".join(f"{key} IS ?" for key in keys)
        key_values = tuple(clean[key] for key in keys)
        existing = connection.execute(
            f"SELECT 1 FROM {target.table} WHERE {where} LIMIT 1",
            key_values,
        ).fetchone()

    if existing is not None:
        update_keys = [key for key in clean if key not in keys]
        if update_keys:
            assignments = ", ".join(f"{key} = ?" for key in update_keys)
            if "updated_at" in columns:
                assignments += ", updated_at = CURRENT_TIMESTAMP"
            connection.execute(
                f"UPDATE {target.table} SET {assignments} WHERE {where}",
                tuple(clean[key] for key in update_keys) + key_values,
            )
        return "updated"

    names = list(clean)
    placeholders = ", ".join("?" for _ in names)
    connection.execute(
        f"INSERT INTO {target.table} ({', '.join(names)}) VALUES ({placeholders})",
        tuple(clean[name] for name in names),
    )
    return "inserted"


def _apply_special(connection: sqlite3.Connection, target: BulkTarget, row: dict[str, Any]) -> tuple[int, int, int]:
    kind = target.special_handler
    if kind == "wallet_adjustments":
        user_id = _user_id(connection, row.get("telegram_id"))
        currency = str(row.get("currency_code"))
        exists = connection.execute("SELECT code FROM currencies WHERE code = ?", (currency,)).fetchone()
        if exists is None:
            raise ValueError(f"валюта не найдена: {currency}")
        amount = _int(row.get("amount"), "amount", minimum=0)
        operation = str(row.get("operation") or "add").lower()
        current = connection.execute("SELECT amount FROM currency_balances WHERE user_id = ? AND currency_code = ?", (user_id, currency)).fetchone()
        current_amount = int(current["amount"] if current else 0)
        if operation == "add":
            new_amount = current_amount + amount
        elif operation in {"subtract", "sub"}:
            new_amount = max(0, current_amount - amount)
        elif operation == "set":
            new_amount = amount
        else:
            raise ValueError("operation: add, subtract или set")
        connection.execute(
            """INSERT INTO currency_balances(user_id, currency_code, amount)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, currency_code) DO UPDATE SET amount = excluded.amount, updated_at = CURRENT_TIMESTAMP""",
            (user_id, currency, new_amount),
        )
        return (0, 1 if current else 0, 0) if current else (1, 0, 0)

    if kind == "card_grants":
        user_id = _user_id(connection, row.get("telegram_id"))
        card_id = _card_id(connection, row)
        quantity = _int(row.get("quantity", 1), "quantity", minimum=1, maximum=500)
        source = str(row.get("source") or "bulk_admin")
        connection.executemany(
            "INSERT INTO user_cards(user_id, card_id, obtained_from) VALUES (?, ?, ?)",
            [(user_id, card_id, source)] * quantity,
        )
        return quantity, 0, 0

    if kind == "pack_grants":
        user_id = _user_id(connection, row.get("telegram_id"))
        pack_id = _pack_id(connection, row.get("pack_code"))
        quantity = _int(row.get("quantity", 1), "quantity", minimum=1, maximum=10000)
        current = connection.execute("SELECT quantity FROM user_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)).fetchone()
        connection.execute(
            """INSERT INTO user_packs(user_id, pack_id, quantity) VALUES (?, ?, ?)
               ON CONFLICT(user_id, pack_id) DO UPDATE SET quantity = quantity + excluded.quantity, updated_at = CURRENT_TIMESTAMP""",
            (user_id, pack_id, quantity),
        )
        return (0, 1, 0) if current else (1, 0, 0)

    if kind == "cosmetic_grants":
        user_id = _user_id(connection, row.get("telegram_id"))
        cosmetic_id = _cosmetic_id(connection, row.get("cosmetic_code"))
        item = connection.execute("SELECT type, rarity FROM war2_cosmetic_items WHERE id = ?", (cosmetic_id,)).fetchone()
        quantity = _int(row.get("quantity", 1), "quantity", minimum=1, maximum=500)
        source = str(row.get("source") or "bulk_admin")
        connection.executemany(
            "INSERT INTO user_cosmetic_items(owner_id, cosmetic_item_id, type, rarity, source) VALUES (?, ?, ?, ?, ?)",
            [(user_id, cosmetic_id, str(item["type"]), str(item["rarity"]), source)] * quantity,
        )
        return quantity, 0, 0

    if kind == "salaries":
        card_id = _card_id(connection, row)
        salary = _int(row.get("salary"), "salary", minimum=0)
        connection.execute("UPDATE cards SET salary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (salary, card_id))
        return 0, 1, 0

    raise ValueError(f"неизвестный special_handler: {kind}")


def apply_import(target: BulkTarget, source: PreparedSource) -> BulkApplyResult:
    preview = build_preview(target, source)
    if preview.errors:
        raise ValueError(f"импорт отменён: строк с ошибками {len(preview.errors)}")

    inserted = updated = skipped = 0
    created_assets: list[Path] = []
    with get_connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            for raw in preview.rows:
                prepared = _prepare_row(connection, target, dict(raw), assets_root=source.assets_root, commit_assets=True, created_assets=created_assets)
                if target.special_handler:
                    add_i, add_u, add_s = _apply_special(connection, target, prepared)
                    inserted += add_i
                    updated += add_u
                    skipped += add_s
                else:
                    action = _manual_upsert(connection, target, prepared)
                    inserted += int(action == "inserted")
                    updated += int(action == "updated")
            connection.commit()
        except Exception:
            connection.rollback()
            for asset_path in reversed(created_assets):
                try:
                    asset_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
    return BulkApplyResult(target.code, preview.total, inserted, updated, skipped)


def cleanup_job_dir(path: Path | None) -> None:
    if path is None:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def make_job_dir(user_id: int, token: str) -> Path:
    root = Path(tempfile.gettempdir()) / "nhl_admin_bulk"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{user_id}_{token}"
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "BulkApplyResult", "BulkPreview", "BulkTarget", "PreparedSource", "SECTION_TITLES",
    "TARGETS", "apply_import", "build_preview", "cleanup_job_dir", "get_target",
    "list_targets", "make_job_dir", "prepare_source", "template_csv_bytes", "template_json_bytes",
]
