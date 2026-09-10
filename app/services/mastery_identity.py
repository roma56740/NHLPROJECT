from __future__ import annotations

import re
import unicodedata


def canonical_player_key(value: str | None) -> str:
    """Normalize player-key/name-like values without depending on a specific separator."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


# Historical/admin imports do not always use the same player_key spelling.  Mastery
# must still be one lifetime track for the hockey player rather than accidentally
# splitting progress by a harmless key variant.
_MASTERY_ALIASES: dict[str, str] = {
    "martin_brodeur": "martin_brodeur",
    "brodeur": "martin_brodeur",
    "nicklas_lidstrom": "nicklas_lidstrom",
    "nicklas_lidsrom": "nicklas_lidstrom",  # common legacy typo
    "lidstrom": "nicklas_lidstrom",
    "lidsrom": "nicklas_lidstrom",
    "pavel_datsyuk": "pavel_datsyuk",
    "datsyuk": "pavel_datsyuk",
    "jaromir_jagr": "jaromir_jagr",
    "jagr": "jaromir_jagr",
    "carey_price": "carey_price",
    "price": "carey_price",
    "zdeno_chara": "zdeno_chara",
    "chara": "zdeno_chara",
    "sidney_crosby": "sidney_crosby",
    "crosby": "sidney_crosby",
    "alexander_ovechkin": "alexander_ovechkin",
    "alex_ovechkin": "alexander_ovechkin",
    "ovechkin": "alexander_ovechkin",
    "joe_sakic": "joe_sakic",
    "sakic": "joe_sakic",
    "henrik_lundqvist": "henrik_lundqvist",
    "lundqvist": "henrik_lundqvist",
}


def resolve_mastery_player_key(value: str | None) -> str:
    normalized = canonical_player_key(value)
    return _MASTERY_ALIASES.get(normalized, normalized)
