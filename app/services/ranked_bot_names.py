"""Фиксированные ники Ranked-ботов (ТЗ "ФИКСИРОВАННЫЕ НИКИ БОТОВ").

Ровно 100 ников из data/ranked_bot_nicknames.txt, написание/регистр не меняются.
Список грузится и кэшируется ОДИН раз за процесс (module-level `_cache`). Выбор
ника не зависит от OVR/состава/зарплаты пользователя — единственная случайность
здесь чисто косметическая (`random.choice`), никак не связана с игровыми данными.

Старый генератор случайных "технических" ников для Ranked-ботов не использовался
(его не было — Ranked-боты раньше брали название из общего `matches.BOT_NAMES`,
списка из 8 хоккейных "названий команд"); этот модуль заменяет именно тот источник
для Ranked (см. `app/services/ranked_core.py::find_ranked_opponent`), не трогая
`BOT_NAMES`, которым по-прежнему пользуются обычный режим и CLAN WAR 2.0.

При отсутствии/повреждении файла используется встроенная копия того же списка
(`EMBEDDED_NICKNAMES`) — НЕ технический "Bot123"-генератор.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
NICKNAMES_PATH = ROOT_DIR / "data" / "ranked_bot_nicknames.txt"
EXPECTED_COUNT = 100

EMBEDDED_NICKNAMES: tuple[str, ...] = (
    "icepasser17", "maxon_rink", "dimasik_chel", "kirya_north", "puckhunter91",
    "vladikstorm", "artemka_ufa", "nikosave", "borisov_22", "slyfox_47",
    "egor_onice", "timurpower", "siberian_goalie", "sanya_frost", "makarlegend",
    "denchik_krsk", "romanov_play", "zheka_iceberg", "kostyan_rush", "sergik_mgn",
    "grizzly_86", "danya_clutch", "vovan_rocket", "icekid_2011", "almaz_rink",
    "miron_skates", "yarik_top", "chelmetall", "savelyshot", "glebson_19",
    "northwind_77", "filipp_pro", "maks_behind", "arsyusha_88", "timka_hockey",
    "bogdanrush", "yaroslav_ice", "sanya_bort", "matvey_one", "rezak_74",
    "klimov_play", "semyon_fast", "ruslan_goal", "stepik_chel", "igoryan_55",
    "danik_falcon", "icebear_102", "pasha_skater", "mark_rinkside", "vityaz_16",
    "kolyan_power", "anton_blade", "shurik_ice", "gosha_drive", "rinkmaster_29",
    "levchik_nsk", "ilya_snipe", "fedor_clutch", "westice_10", "slava_bullet",
    "artemon_98", "vitalik_pass", "dimon_frosty", "nikitos_rush", "prosha_goal",
    "timofey_74", "makson_blade", "rodion_playmaker", "valerka_ice", "seroga_north",
    "foxonrink", "rusik_power", "yura_slapshot", "vanyok_iceway", "steelkid_63",
    "alex_rinkman", "danila_rocket", "misha_otbort", "sasha_fivehole", "vovchik_99",
    "artem_sibir", "nikolay_clutch", "max_iceflow", "gleb_bars", "egorka_drive",
    "timon_goalie", "kirill_northside", "savva_rink", "denis_icefox", "pavel_snipe",
    "boroda_17", "grisha_powerplay", "matroskin_ice", "alkashnik_off", "chelboy_96",
    "rusalka_bort", "frostovik", "hockeydemon_13", "zloy_vratary", "mishanya_blade",
)

_cache: list[str] | None = None


def _load_from_disk() -> list[str] | None:
    try:
        text = NICKNAMES_PATH.read_text(encoding="utf-8")
    except OSError as error:
        logger.error("ranked_bot_names: не удалось прочитать %s: %s", NICKNAMES_PATH, error)
        return None
    names = [line.strip() for line in text.splitlines() if line.strip()]
    if not names:
        logger.error("ranked_bot_names: файл %s пуст", NICKNAMES_PATH)
        return None
    return names


def get_all_nicknames() -> list[str]:
    global _cache
    if _cache is not None:
        return _cache
    names = _load_from_disk()
    if names is None:
        logger.error(
            "ranked_bot_names: используется встроенная копия списка ников (%d шт.)", len(EMBEDDED_NICKNAMES)
        )
        names = list(EMBEDDED_NICKNAMES)
    if len(names) != EXPECTED_COUNT:
        logger.warning(
            "ranked_bot_names: ожидалось %d ников, загружено %d (%s)", EXPECTED_COUNT, len(names), NICKNAMES_PATH
        )
    _cache = names
    return _cache


def reset_cache_for_tests() -> None:
    """Только для тестов: сбрасывает кэш, чтобы можно было переключить monkeypatch
    NICKNAMES_PATH между тестами и проверить fallback на встроенный список."""
    global _cache
    _cache = None


def pick_nickname(exclude: set[str] | None = None) -> str:
    """Случайный ник из фиксированного списка, без повтора внутри ОДНОЙ активной
    выборки соперников (`exclude`), пока хватает уникальных вариантов — после
    исчерпания списка допускается повторное использование."""
    names = get_all_nicknames()
    exclude = exclude or set()
    candidates = [name for name in names if name not in exclude]
    pool = candidates if candidates else names
    return random.choice(pool)


def diagnostics() -> dict:
    """Для админ-диагностики: количество загруженных/уникальных ников, путь к
    файлу, наличие дубликатов, случайная выборка, предупреждение если не 100."""
    names = get_all_nicknames()
    unique_count = len(set(names))
    return {
        "path": str(NICKNAMES_PATH),
        "loaded_count": len(names),
        "unique_count": unique_count,
        "has_duplicates": unique_count != len(names),
        "expected_count": EXPECTED_COUNT,
        "count_matches_expected": len(names) == EXPECTED_COUNT,
        "sample": random.sample(names, min(5, len(names))) if names else [],
    }
