from __future__ import annotations

from dataclasses import dataclass

from app.services.xfactors import get_installed_xfactor_codes, get_xfactor_by_code


@dataclass(frozen=True)
class BattleModifiers:
    shots_bonus: int = 0
    goal_chance_bonus: int = 0
    possession_bonus: int = 0
    opponent_shots_reduction: int = 0
    opponent_goal_chance_reduction: int = 0
    overtime_bonus: int = 0
    active_codes: tuple[str, ...] = ()


REGULAR_EFFECTS: dict[str, tuple[int,int,int,int,int,int]] = {
    # shots, goal%, possession, opp shots, opp goal%, OT
    "elite_edges": (0,0,2,0,0,0),
    "quick_draw": (1,0,3,0,0,1),
    "send_it": (1,0,2,0,0,0),
    "tape_to_tape": (0,0,3,0,0,0),
    "unstoppable": (0,1,2,0,0,0),
    "wheels": (1,0,2,0,0,1),
    "backhand_beauty": (0,2,0,0,0,0),
    "big_rig": (1,1,1,0,0,0),
    "big_tipper": (0,2,0,0,0,0),
    "one_t": (0,3,0,0,0,0),
    "pressure_plus": (2,0,1,0,0,0),
    "quick_release": (0,2,0,0,0,0),
    "rocket": (1,2,0,0,0,0),
    "born_leader": (0,0,2,0,0,1),
    "hipster": (0,0,0,1,1,0),
    "no_contest": (0,0,2,1,0,0),
    "quick_pick": (0,0,2,2,0,0),
    "second_wind": (0,0,1,0,1,0),
    "spark_plug": (0,0,2,1,0,1),
    "stick_em_up": (0,0,1,2,0,0),
    "truculence": (0,0,0,1,2,0),
    "warrior": (0,0,0,1,2,0),
    "dialed_in": (0,0,0,0,2,0),
    "post_to_post": (0,0,0,0,3,0),
    "recharge": (0,0,0,1,2,0),
    "show_stopper": (0,0,0,0,3,0),
    "sponge": (0,0,0,1,2,0),
}

MASTERY_EFFECTS: dict[str, tuple[int,int,int,int,int,int]] = {
    "third_defenseman": (1,0,4,1,3,1),
    "perfect_position": (0,0,3,3,5,1),
    "the_magic_man": (1,4,4,1,0,2),
    "unbreakable_mastery": (2,4,3,0,0,2),
    "calm_under_fire": (0,0,0,2,6,2),
    "the_giant": (0,0,1,3,6,1),
    "complete_player": (2,4,5,1,1,3),
    "the_office": (2,7,1,0,0,2),
    "wrist_shot_legend": (1,6,1,0,0,2),
    "the_king": (0,0,1,2,7,4),
}


def get_lineup_battle_modifiers(lineup_cards) -> BattleModifiers:
    cards=list(lineup_cards or [])
    by_id=get_installed_xfactor_codes([getattr(card,"user_card_id",0) for card in cards])
    totals=[0,0,0,0,0,0]
    active=[]
    for card in cards:
        for code in by_id.get(int(getattr(card,"user_card_id",0) or 0),[]):
            # Quick Draw is installable on any F, but only activates in center (F2).
            if code == "quick_draw" and str(getattr(card,"lineup_slot", "")) != "F2":
                continue
            effect=MASTERY_EFFECTS.get(code) or REGULAR_EFFECTS.get(code)
            if effect is None:
                continue
            for index,value in enumerate(effect): totals[index]+=value
            active.append(code)
    # Caps prevent a 3-factor card / 6-card lineup from making the simple simulator deterministic.
    return BattleModifiers(
        shots_bonus=min(totals[0],8),
        goal_chance_bonus=min(totals[1],14),
        possession_bonus=min(totals[2],12),
        opponent_shots_reduction=min(totals[3],6),
        opponent_goal_chance_reduction=min(totals[4],14),
        overtime_bonus=min(totals[5],10),
        active_codes=tuple(active),
    )


def active_factor_names(modifiers: BattleModifiers) -> list[str]:
    names=[]
    for code in modifiers.active_codes:
        xf=get_xfactor_by_code(code)
        if xf and xf.name not in names: names.append(xf.name)
    return names
