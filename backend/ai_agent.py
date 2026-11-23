import os
import json
import logging
import traceback
import random
import re
import builtins
import math
import urllib.request
import urllib.error
from typing import Dict, Any, List
from groq import Groq
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))
OLLAMA_NUM_GPU = int(os.environ.get("OLLAMA_NUM_GPU", "999"))
LLM_FALLBACK_TO_GROQ = os.environ.get("LLM_FALLBACK_TO_GROQ", "false").lower() == "true"
_groq_client: Groq | None = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _groq_client

logger = logging.getLogger(__name__)


def _safe_print(*args, **kwargs):
    """Print safely on Windows terminals that may use cp1252 encoding."""
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for arg in args:
            text = str(arg)
            safe_args.append(text.encode("cp1252", errors="replace").decode("cp1252", errors="replace"))
        builtins.print(*safe_args, **kwargs)


# Route all prints in this module through a unicode-safe wrapper.
print = _safe_print

# Deck-specific strategy playbooks
DECK_PLAYBOOKS: Dict[str, str] = {
    "D01_FIRE": """
[Deck Strategy: Charizard ex]
- WIN CONDITION: Evolve Charmander -> Charmeleon -> Charizard ex, then use Charizard ex's high-damage attacks.
- ALWAYS bench Charmander early to start the evolution chain ASAP.
- Attach Fire energy to Charizard ex every single turn without exception.
- Do NOT spread energy to random bench Pokemon unless Charizard ex is fully powered.
- If you can evolve, do it BEFORE attaching energy or attacking.
- IMPORTANT: Moltres ex's "Inferno Dance" attack flips 3 coins to attach Fire energy to your Benched Fire Pokemon. It DOES NOT use energy from your Energy Zone. Do NOT worry about having 0 Energy Zone when using Inferno Dance. It is always a good move to accelerate energy!
""",
    "D02_PSYCHIC": """
[Deck Strategy: Mewtwo ex]
- WIN CONDITION: Get Mewtwo ex to Active with 2+ Psychic energy, then spam its powerful attack for 150+ dmg.
- ALWAYS attach Psychic energy to Mewtwo ex FIRST. This is your top priority every single turn.
- Do NOT waste energy on bench Pokemon unless Mewtwo ex already has 2+ energy attached.
- Keep Mewtwo ex healthy — use Potion or retreat if it is below 50% HP and you don't have lethal.
- Bench other Pokemon only as shields or support, not as your main attacker.
- IMPORTANT: Gardevoir's "Psyembrace" ability attaches a Psychic energy from the discard pile to a benched Psychic pokemon. It DOES NOT use energy from your Energy Zone. You can use it even if Energy Zone is 0. Always use it if possible!
""",
    "D03_LIGHTNING": """
[Deck Strategy: Pikachu ex]
- WIN CONDITION: Fill your bench with 3 Pokemon, then use Pikachu ex's Circle Circuit to hit all enemy Pokemon at once.
- FIRST priority each turn: play any Basic Pokemon in hand to your bench (max 3). More bench = more damage.
- SECOND priority: attach Lightning energy to Pikachu ex.
- Only attack with Circle Circuit when your bench is as full as possible for maximum spread damage.
- Never retreat Pikachu ex unnecessarily — it is your primary attacker.
""",
}

# Preferred opening Active candidates by deck (used as a soft bonus, not hard lock)
DECK_OPENING_ACTIVE_PREFS: Dict[str, list[str]] = {
    "D01_FIRE": ["Moltres ex", "Charmander"],
    "D02_PSYCHIC": ["Mewtwo ex", "Ralts"],
    "D03_LIGHTNING": ["Pikachu ex"],
}

def parse_state_for_ai(full_state: Dict[str, Any], ai_name: str = "Goopy AI") -> Dict[str, Any]:
    """
    Filters the game state so the AI only sees what it is supposed to see.
    Removes opponent's hand details and deck order.
    Identifies legal actions available to the AI.
    """
    if full_state.get("player_1", {}).get("name") == ai_name:
        my_state = full_state.get("player_1", {})
        op_state = full_state.get("player_2", {})
    else:
        my_state = full_state.get("player_2", {})
        op_state = full_state.get("player_1", {})

    # Build simplified view
    view = {
        "turn_number": full_state.get("turn_number"),
        "current_turn": full_state.get("current_turn"),
        "phase": full_state.get("phase"),
        "setup_phase": full_state.get("setup_phase"),
        "pending_initial_active": full_state.get("pending_initial_active", []),
        "pending_effect": full_state.get("pending_effect"),
        "game_over": full_state.get("game_over"),
        "my_state": {
            "name": my_state.get("name"),
            "points": my_state.get("points"),
            "energy_type": my_state.get("energy_type"),
            "energy_zone": my_state.get("energy_zone"),
            "hand_count": len(my_state.get("hand", [])),
            "hand_details": my_state.get("hand_details", []), # Can see own hand
            "active_pokemon": my_state.get("active_pokemon"),
            "active_attacks": my_state.get("active_attacks", []),
            "active_ability": my_state.get("active_ability"),
            "bench": my_state.get("bench", []),
            "bench_abilities": my_state.get("bench_abilities", []),
            "pending_promote": my_state.get("pending_promote"),
            "supporter_used_turn": my_state.get("supporter_used_turn"),
            "retreated_this_turn": my_state.get("retreated_this_turn"),
            "retreat_cost_reduction": my_state.get("retreat_cost_reduction", 0)
        },
        "opponent_state": {
            "name": op_state.get("name"),
            "points": op_state.get("points"),
            "energy_type": op_state.get("energy_type"),
            "energy_zone": op_state.get("energy_zone"),
            "hand_count": len(op_state.get("hand", [])),
            # HIDDEN: "hand_details": ...
            "active_pokemon": op_state.get("active_pokemon"),
            "bench": op_state.get("bench", []),
            "pending_promote": op_state.get("pending_promote")
        }
    }

    view["tactical_scenarios"] = _build_tactical_scenarios(full_state, my_state, op_state)
    
    view["legal_actions"] = get_legal_actions_with_hints(full_state, ai_name)
    return view


def _build_tactical_scenarios(full_state: Dict[str, Any], my_state: Dict[str, Any], op_state: Dict[str, Any]) -> list[str]:
    """Compact scenario hints to help LLM choose context-appropriate actions."""
    scenarios: list[str] = []
    deck = _infer_deck_archetype(my_state)
    act = my_state.get("active_pokemon") or {}
    act_name = (act.get("name") or "").lower()
    bench = my_state.get("bench", [])
    has_moltres_bench = any((bp.get("name") or "").lower() == "moltres ex" for bp in bench)

    if deck == "fire" and act_name in {"charmander", "charmeleon"} and has_moltres_bench:
        scenarios.append("FIRE_RETREAT_PLAN: setup unit is active while Moltres ex is on bench; prefer retreat-to-Moltres line.")

    if deck == "psychic":
        has_mewtwo = any("mewtwo" in (p.get("name") or "").lower() for p in [act] + bench)
        has_ralts_line = any((bp.get("name") or "").lower() in {"ralts", "kirlia", "gardevoir"} for bp in bench)
        if has_mewtwo and has_ralts_line:
            scenarios.append("PSYCHIC_CORE_PLAN: keep Mewtwo as primary attacker and use Ralts line as support.")

    if deck == "lightning":
        scenarios.append("LIGHTNING_BENCH_PLAN: prioritize filling bench and powering Pikachu line.")

    if op_state.get("hand_count", 0) >= 5:
        scenarios.append("RED_CARD_VALUE_HIGH: opponent hand is large.")

    return scenarios


def _infer_deck_archetype(my_state: Dict[str, Any]) -> str:
    et = (my_state.get("energy_type") or "").lower()
    if et == "fire":
        return "fire"
    if et == "psychic":
        return "psychic"
    if et == "lightning":
        return "lightning"
    return "generic"


def _trainer_effect_by_id(hand_details: list[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for c in hand_details:
        cid = c.get("id")
        if cid:
            out[cid] = c.get("trainer_effect_calculation") or ""
    return out


def _sorted_opponent_bench_targets(op_state: Dict[str, Any]) -> list[int]:
    """Best Sabrina targets first: low HP / high energy threats first."""
    bench = op_state.get("bench", [])
    scored: list[tuple[float, int]] = []
    for i, bp in enumerate(bench):
        hp = bp.get("current_hp", 999)
        max_hp = max(bp.get("max_hp", 1), 1)
        hp_pct = (hp / max_hp) * 100
        energy = len(bp.get("attached_energy", []))
        score = (100 - hp_pct) + (energy * 8)
        scored.append((score, i))
    scored.sort(reverse=True)
    return [i for _, i in scored]


def _best_fire_inferno_dance_targets(my_state: Dict[str, Any], available_indexes: list[int], count: int) -> list[int]:
    """ลำดับความสำคัญ: Charizard ex (Stage2 ex) > Charmeleon (Stage1) > Charmander (Basic)
    ถ้า stage เท่ากัน เอาตัวที่มีพลังงานมากกว่า (เพื่อ unlock attack ไวขึ้น)
    ถ้าไม่มีสายลิซาด้อนเลย ให้ random ไปเลย"""
    bench = my_state.get("bench", [])

    # Stage rank: higher = better to attach energy to (unlocks evolution sooner)
    STAGE_RANK = {
        "charizard ex": 40,
        "charizard": 35,
        "charmeleon": 20,
        "charmander": 10,
    }

    def bench_score(idx: int) -> tuple[int, int]:
        if idx < 0 or idx >= len(bench):
            return (-999, 0)
        bp = bench[idx]
        name = (bp.get("name") or "").lower().strip()
        energy = len(bp.get("attached_energy", []))
        stage_rank = STAGE_RANK.get(name, 0)
        # Higher stage first, then higher energy first (to push toward attack threshold)
        return (stage_rank, energy)

    # Sort: best targets first
    ordered = sorted(available_indexes, key=bench_score, reverse=True)
    # If no Charizard line in bench, take whatever is available (random fallback)
    if not ordered:
        ordered = available_indexes[:]
    if not ordered:
        return []
    # Stack ALL coins onto the single best target (not spread across multiple pokemon)
    best = ordered[0]
    return [best] * count



def _lightning_circle_damage(my_state: Dict[str, Any], attack_name: str) -> int:
    """Compute effective Circle Circuit damage based on current bench count."""
    if (attack_name or "").lower() != "circle circuit":
        return 0
    # Pikachu ex in this ruleset scales with number of benched pokemon (up to 3).
    bench_count = min(len(my_state.get("bench", [])), 3)
    return bench_count * 30


def _lightning_support_name(name: str) -> bool:
    n = (name or "").lower()
    return n in {"voltorb", "electabuzz", "magnemite", "blitzle", "pincurchin"}


def _is_fire_line_name(name: str) -> bool:
    n = (name or "").lower()
    return n in {"charmander", "charmeleon", "charizard ex", "moltres ex"}


def _opponent_can_hit_for(op_state: Dict[str, Any], threshold: int) -> bool:
    for atk in op_state.get("active_attacks", []):
        if int(atk.get("damage", 0) or 0) >= threshold:
            return True
    return False


def _fire_action_score(
    full_state: dict,
    my_state: dict,
    op_state: dict,
    action: dict,
) -> float:
    endpoint = action.get("endpoint", "")
    payload = action.get("payload", {}) or {}
    hand = my_state.get("hand_details", [])
    bench = my_state.get("bench", [])
    bench_count = len(bench)
    act = my_state.get("active_pokemon") or {}
    act_name = (act.get("name") or "").lower()
    act_energy = len(act.get("attached_energy", []))
    opp_act = op_state.get("active_pokemon") or {}
    opp_hp = int(opp_act.get("current_hp", 0) or 0)
    turn_num = int(full_state.get("turn_number", 0) or 0)

    has_moltres_bench = any((bp.get("name") or "").lower() == "moltres ex" for bp in bench)
    has_moltres_active = act_name == "moltres ex"
    has_moltres_hand = any((c.get("name") or "").lower() == "moltres ex" for c in hand)
    has_fire_basic_hand = any(
        c.get("category") == "pokemon" and c.get("stage") == "basic" and c.get("type") == "fire"
        for c in hand
    )
    has_sabrina_hand = any((c.get("name") or "").lower() == "sabrina" for c in hand)
    has_char_line_bench = any((bp.get("name") or "").lower() in {"charmander", "charmeleon", "charizard ex"} for bp in bench)
    inferno_ready = any(
        (atk.get("name") or "").lower() == "inferno dance" and atk.get("can_use")
        for atk in my_state.get("active_attacks", [])
    )
    fire_bench_targets = [bp for bp in bench if bp.get("type") == "fire"]

    score = 0.0

    if endpoint == "/api/action/evolve":
        evo_id = payload.get("evolution_card_id")
        evo_card = next((x for x in hand if x.get("id") == evo_id), None)
        evo_name = (evo_card.get("name") or "").lower() if evo_card else ""
        tgt_pos = payload.get("target_position")
        tgt_idx = int(payload.get("target_index", 0) or 0)
        target_name = ""
        if tgt_pos == "active":
            target_name = (act.get("name") or "").lower()
        elif tgt_pos == "bench" and 0 <= tgt_idx < bench_count:
            target_name = (bench[tgt_idx].get("name") or "").lower()

        has_charizard = any((x.get("name") or "").lower() == "charizard" for x in hand)
        has_charizard_ex = any((x.get("name") or "").lower() == "charizard ex" for x in hand)

        if target_name == "charmeleon":
            if evo_name == "charizard ex":
                return 950
            if evo_name == "charizard":
                if has_charizard_ex: return 850
                return 900
        if evo_name in {"charmeleon", "charizard", "charizard ex"}:
            return 880
        return 820

    if endpoint == "/api/action/play_bench":
        if bench_count >= 3:
            return -1000
        card_id = payload.get("card_id")
        c = next((x for x in hand if x.get("id") == card_id), None)
        c_name = (c.get("name") or "").lower() if c else ""

        score = 650
        if c_name == "moltres ex":
            if not has_moltres_bench and not has_moltres_active:
                score += 100
        elif c_name == "charmander":
            score += 50
        return score

    if endpoint == "/api/action/play_active":
        card_id = payload.get("card_id")
        c = next((x for x in hand if x.get("id") == card_id), None)
        c_name = (c.get("name") or "").lower() if c else ""
        score = 650
        if c_name == "moltres ex":
            score += 100
        if c_name in {"charmander", "charmeleon"} and any((x.get("name") or "").lower() == "moltres ex" for x in hand):
            score -= 100
        return score

    if endpoint == "/api/action/promote":
        bidx = int(payload.get("bench_index", 0) or 0)
        score = 650
        if 0 <= bidx < bench_count:
            p = bench[bidx]
            p_name = (p.get("name") or "").lower()
            if p_name == "moltres ex":
                score += 100
            if p_name in {"charmander", "charmeleon"} and has_moltres_bench:
                score -= 100
        return score

    if endpoint == "/api/action/retreat":
        bidx = int(payload.get("bench_index", 0) or 0)
        score = 650
        if act_name in {"charmander", "charmeleon"} and has_moltres_bench:
            if 0 <= bidx < bench_count and (bench[bidx].get("name") or "").lower() == "moltres ex":
                score += 100
        return score

    if endpoint == "/api/action/use_trainer":
        card_id = payload.get("card_id")
        c = next((x for x in hand if x.get("id") == card_id), None)
        c_name = (c.get("name") or "").lower() if c else ""
        c_eff = (c.get("trainer_effect_calculation") or "") if c else ""
        
        if c_name == "x speed" or c_eff == "retreat_cost_reduce_1_this_turn":
            score = 650
            if act_name in {"charmander", "charmeleon"} and has_moltres_bench:
                score += 100
            return score

        if c_name == "sabrina" or c_eff == "opponent_switch_active_to_bench":
            switch_idx = payload.get("opponent_switch_index")
            if isinstance(switch_idx, int) and 0 <= switch_idx < len(op_state.get("bench", [])):
                target = op_state.get("bench", [])[switch_idx]
                target_name = (target.get("name") or "").lower()
                target_hp = int(target.get("current_hp", 0) or 0)
                target_is_ex = " ex" in f" {target_name}"

                if target_is_ex and target_hp <= 200:
                    return 950
                elif target_hp <= 90:
                    return 850
                else:
                    return 800
            return 800

        if c_name in {"poké ball", "poke ball"} or c_eff == "search_random_basic_pokemon_to_hand":
            if bench_count < 3 and not has_fire_basic_hand:
                return 950
            elif bench_count < 3:
                return 850
            else:
                return 800

        if c_name == "professor's research" or c_eff in {"draw_2_cards", "draw_cards"}:
            hand_count = my_state.get("hand_count", len(my_state.get("hand", [])))
            if hand_count <= 2:
                return 950
            return 850

        if c_name == "potion" or c_eff == "heal_20_from_target":
            return 850

        return 800

    if endpoint == "/api/action/attach_energy":
        tgt_pos = payload.get("target_position")
        tgt_idx = int(payload.get("target_index", 0) or 0)
        target = act if tgt_pos == "active" else bench[tgt_idx] if 0 <= tgt_idx < bench_count else act
        t_name = (target.get("name") or "").lower()
        t_energy = len(target.get("attached_energy", []))

        # Combo Enabler Heuristic: Retreat Lookahead
        if tgt_pos == "active" and act_name in {"charmander", "charmeleon"} and has_moltres_bench:
            retreat_cost = len(act.get("retreat_cost", [])) if isinstance(act.get("retreat_cost", []), list) else 0
            retreat_reduction = int(my_state.get("retreat_cost_reduction", 0) or 0)
            eff_retreat = max(0, retreat_cost - retreat_reduction)
            if eff_retreat > 0 and t_energy + 1 >= eff_retreat:
                return 950  # 🌟 Massive Bonus: Tier A

        if tgt_pos == "active" and t_name == "moltres ex" and t_energy < 1:
            return 750
        if t_name in {"charmander", "charmeleon", "charizard ex"}:
            if (act_name == "moltres ex" and (act_energy >= 1 or inferno_ready)) or inferno_ready:
                return 700
            if turn_num >= 2:
                return 600
        if t_name == "moltres ex" and (act_name == "moltres ex" and (act_energy >= 1 or inferno_ready)):
            return 500
        if "charmander" in t_name or "charmeleon" in t_name or "charizard" in t_name or "moltres" in t_name:
            return 650
        return 500

    if endpoint == "/api/action/attack":
        atk_name = (payload.get("attack_name") or "").lower()
        dmg = 0
        for atk in my_state.get("active_attacks", []):
            if (atk.get("name") or "").lower() == atk_name and atk.get("can_use"):
                dmg = int(atk.get("damage", 0) or 0)
                break

        if dmg >= opp_hp and dmg > 0:
            return 2000

        if atk_name == "inferno dance":
            if len(fire_bench_targets) > 0:
                return 450
            return 300

        if dmg > 0:
            return 400
        return 300

    if endpoint == "/api/action/end_turn":
        return -1000

    return score


def _lightning_action_score(
    full_state: dict,
    my_state: dict,
    op_state: dict,
    action: dict,
) -> float:
    endpoint = action.get("endpoint", "")
    payload = action.get("payload", {}) or {}
    bench = my_state.get("bench", [])
    bench_count = len(bench)
    hand = my_state.get("hand_details", [])
    act = my_state.get("active_pokemon") or {}
    act_name = (act.get("name") or "").lower()
    act_energy = len(act.get("attached_energy", []))
    opp_act = op_state.get("active_pokemon") or {}
    opp_hp = int(opp_act.get("current_hp", 0) or 0)
    opp_bench = op_state.get("bench", [])
    turn_num = full_state.get("turn_number", 0)
    has_basic_in_hand = any(c.get("category") == "pokemon" and c.get("stage") == "basic" for c in hand)

    score = 0.0

    if endpoint == "/api/action/play_bench":
        if bench_count >= 3:
            return -1000
        card_id = payload.get("card_id")
        c = next((x for x in hand if x.get("id") == card_id), None)
        c_name = (c.get("name") or "").lower() if c else ""
        if c_name == "pikachu ex":
            return 750
        return 650

    if endpoint == "/api/action/attach_energy":
        tgt_pos = payload.get("target_position")
        tgt_idx = int(payload.get("target_index", 0) or 0)
        target = act if tgt_pos == "active" else bench[tgt_idx] if 0 <= tgt_idx < bench_count else act
        t_name = (target.get("name") or "").lower()
        t_energy = len(target.get("attached_energy", []))
        
        # Combo Enabler Heuristic: Retreat Lookahead
        if tgt_pos == "active" and act_name not in {"pikachu ex", "zapdos ex"} and any(bp.get("name", "").lower() in {"pikachu ex", "zapdos ex"} for bp in bench):
            retreat_cost = len(act.get("retreat_cost", [])) if isinstance(act.get("retreat_cost", []), list) else 0
            retreat_reduction = int(my_state.get("retreat_cost_reduction", 0) or 0)
            eff_retreat = max(0, retreat_cost - retreat_reduction)
            if eff_retreat > 0 and t_energy + 1 >= eff_retreat:
                return 950  # 🌟 Massive Bonus: Tier A

        if tgt_pos == "active":
            if act_name == "pikachu ex" and act_energy < 2:
                return 750
            if act_name in {"zapdos ex", "raichu"}:
                return 700
        if tgt_pos == "bench":
            return 650
        return 600

    if endpoint == "/api/action/use_trainer":
        card_id = payload.get("card_id")
        c = next((x for x in hand if x.get("id") == card_id), None)
        c_name = (c.get("name") or "").lower() if c else ""
        c_eff = (c.get("trainer_effect_calculation") or "") if c else ""

        if c_name in {"poké ball", "poke ball"} or c_eff == "search_random_basic_pokemon_to_hand":
            if bench_count < 3 and not has_basic_in_hand:
                return 950
            if bench_count < 3:
                return 850
            return 800

        if c_name == "professor's research" or c_eff in {"draw_2_cards", "draw_cards"}:
            hand_count = my_state.get("hand_count", len(my_state.get("hand", [])))
            if hand_count < 3:
                return 950
            return 850

        if c_name == "sabrina" or c_eff == "opponent_switch_active_to_bench":
            return 850

        if c_name == "giovanni" or c_eff == "attack_damage_boost_10_this_turn":
            return 850
            
        return 800

    if endpoint == "/api/action/retreat":
        return 650
        
    if endpoint == "/api/action/evolve":
        return 900
        
    if endpoint == "/api/action/play_active" or endpoint == "/api/action/promote":
        return 650

    if endpoint == "/api/action/attack":
        atk_name = payload.get("attack_name", "")
        dmg = 0
        
        for atk in my_state.get("active_attacks", []):
            if atk.get("name") == atk_name and atk.get("can_use"):
                dmg = int(atk.get("damage", 0) or 0)
                # Avoid calling _lightning_circle_damage for simplicity, just use base dmg
                if atk_name.lower() == "circle circuit":
                    dmg = 30 * bench_count
                break

        if dmg >= opp_hp and dmg > 0:
            return 2000

        if dmg > 0:
            if atk_name.lower() == "circle circuit":
                return 450
            return 400
        return 300

    if endpoint == "/api/action/end_turn":
        return -1000

    return score


def _psychic_action_score(
    full_state: dict,
    my_state: dict,
    op_state: dict,
    action: dict,
) -> float:
    endpoint = action.get("endpoint", "")
    payload = action.get("payload", {}) or {}
    hand = my_state.get("hand_details", [])
    bench = my_state.get("bench", [])
    bench_count = len(bench)
    act = my_state.get("active_pokemon") or {}
    act_name = (act.get("name") or "").lower()
    act_energy = len(act.get("attached_energy", []))
    opp_act = op_state.get("active_pokemon") or {}
    opp_hp = int(opp_act.get("current_hp", 0) or 0)
    opp_bench = op_state.get("bench", [])
    turn_num = int(full_state.get("turn_number", 0) or 0)

    has_mewtwo_ex_bench = any((bp.get("name") or "").lower() == "mewtwo ex" for bp in bench)
    has_mewtwo_bench = has_mewtwo_ex_bench or any((bp.get("name") or "").lower() == "mewtwo" for bp in bench)

    score = 0.0

    if endpoint in {"/api/action/play_bench", "/api/action/play_active", "/api/action/promote"}:
        if endpoint == "/api/action/play_bench" and bench_count >= 3:
            return -1000
        card_id = payload.get("card_id")
        c = next((x for x in hand if x.get("id") == card_id), None)
        c_name = (c.get("name") or "").lower() if c else ""
        if "mewtwo ex" in c_name:
            return 750
        if "mewtwo" in c_name:
            return 650
        return 650

    if endpoint == "/api/action/evolve":
        evo_id = payload.get("evolution_card_id")
        evo_card = next((c for c in hand if c.get("id") == evo_id), None)
        evo_name = (evo_card.get("name") or "").lower() if evo_card else ""
        if evo_name == "gardevoir":
            return 950
        if evo_name == "kirlia":
            return 900
        return 850

    if endpoint == "/api/action/retreat":
        return 650

    if endpoint == "/api/action/use_ability":
        return 950

    if endpoint == "/api/action/attach_energy":
        tgt_pos = payload.get("target_position")
        tgt_idx = int(payload.get("target_index", 0) or 0)
        target = act if tgt_pos == "active" else bench[tgt_idx] if 0 <= tgt_idx < bench_count else act
        t_name = (target.get("name") or "").lower()
        t_energy = len(target.get("attached_energy", []))

        # Combo Enabler Heuristic: Retreat Lookahead
        if tgt_pos == "active" and act_name in {"ralts", "kirlia"} and has_mewtwo_bench:
            retreat_cost = len(act.get("retreat_cost", [])) if isinstance(act.get("retreat_cost", []), list) else 0
            retreat_reduction = int(my_state.get("retreat_cost_reduction", 0) or 0)
            eff_retreat = max(0, retreat_cost - retreat_reduction)
            if eff_retreat > 0 and t_energy + 1 >= eff_retreat:
                return 950  # 🌟 Massive Bonus: Tier A

        if "mewtwo ex" in t_name: return 750
        if "mewtwo" in t_name: return 700
        return 600

    if endpoint == "/api/action/use_trainer":
        card_id = payload.get("card_id")
        card = next((c for c in hand if c.get("id") == card_id), None)
        c_name = (card.get("name") or "").lower() if card else ""
        c_eff = (card.get("trainer_effect_calculation") or "") if card else ""

        if c_name == "x speed" or c_eff == "retreat_cost_reduce_1_this_turn":
            return 650
        if c_name in {"poké ball", "poke ball"} or c_eff == "search_random_basic_pokemon_to_hand":
            return 900
        if c_name == "professor's research" or c_eff in {"draw_2_cards", "draw_cards"}:
            return 900
        if c_name == "sabrina" or c_eff == "opponent_switch_active_to_bench":
            return 850
        if c_name == "potion" or c_eff == "heal_20_from_target":
            return 850
        return 800

    if endpoint == "/api/action/attack":
        atk_name = (payload.get("attack_name") or "").lower()
        dmg = 0
        for atk in my_state.get("active_attacks", []):
            if (atk.get("name") or "").lower() == atk_name and atk.get("can_use"):
                dmg = int(atk.get("damage", 0) or 0)
                break

        if dmg >= opp_hp and dmg > 0:
            return 2000

        if atk_name == "psychic sphere":
            if dmg > 0: return 400
            return 300
        if atk_name == "psydrive":
            if dmg > 0: return 450
            return 300

        if dmg > 0: return 400
        return 300

    if endpoint == "/api/action/end_turn":
        return -1000

    return score


def _global_trainer_scenario_adjustment(
    my_state: dict,
    op_state: dict,
    action: dict,
) -> float:
    # Deprecated for raw score modification, rely on deck-specific base scores
    return 0.0

def _apply_deck_scoring(
    full_state: Dict[str, Any],
    my_state: Dict[str, Any],
    op_state: Dict[str, Any],
    actions: List[Dict[str, Any]],
    deck_archetype: str,
) -> List[Dict[str, Any]]:
    """Annotate and order legal actions by deck-specific tactical scoring."""
    if not actions:
        return actions

    if deck_archetype not in {"lightning", "fire", "psychic"}:
        for action in actions:
            action.setdefault("score", 0.0)
            action.setdefault("probability", 0.0)
        return actions

    temperature = 0.35
    scored: list[Dict[str, Any]] = []
    for action in actions:
        if deck_archetype == "lightning":
            base = _lightning_action_score(full_state, my_state, op_state, action)
        elif deck_archetype == "psychic":
            base = _psychic_action_score(full_state, my_state, op_state, action)
        else:
            base = _fire_action_score(full_state, my_state, op_state, action)

        # Cross-deck scenario adjustment so trainer usage depends on current alternatives.
        base += _global_trainer_scenario_adjustment(my_state, op_state, action)

        hint = (action.get("hint") or "")
        if "LETHAL" in hint:
            base += 300
        if "CRITICAL" in hint:
            base += 60
        action["score"] = float(base)
        scored.append(action)

    raw_values = [float(a.get("score", 0.0)) for a in scored]
    min_raw = min(raw_values)
    max_raw = max(raw_values)
    raw_span = max_raw - min_raw

    for action in scored:
        raw = float(action.get("score", 0.0))
        action["raw_score"] = raw
        if raw_span <= 1e-9:
            action["score"] = 1.0
        else:
            action["score"] = max(0.0, min(1.0, (raw - min_raw) / raw_span))

    max_score = max(float(a.get("score", 0.0)) for a in scored)
    exps = [math.exp((float(a.get("score", 0.0)) - max_score) / temperature) for a in scored]
    denom = sum(exps) or 1.0
    for i, action in enumerate(scored):
        action["probability"] = exps[i] / denom

    scored.sort(key=lambda a: (a.get("score", 0.0), a.get("probability", 0.0)), reverse=True)
    return scored

def get_legal_actions_with_hints(full_state: Dict[str, Any], ai_name: str = "Goopy AI") -> List[Dict[str, Any]]:
    """
    Returns a list of dictionaries with 'endpoint', 'payload', and 'hint'.
    Analyzes the current state and injects heuristics to prevent LLM hallucinations.
    """
    actions = []
    
    if full_state.get("player_1", {}).get("name") == ai_name:
        my_state = full_state.get("player_1", {})
        op_state = full_state.get("player_2", {})
    else:
        my_state = full_state.get("player_2", {})
        op_state = full_state.get("player_1", {})

    def add_action(endpoint, payload, hint=""):
        actions.append({"endpoint": endpoint, "payload": payload, "hint": hint})

    deck_archetype = _infer_deck_archetype(my_state)

    def finalize_actions() -> List[Dict[str, Any]]:
        return _apply_deck_scoring(full_state, my_state, op_state, actions, deck_archetype)

    # --- Forced Actions ---
    # 1. Setup Phase
    if full_state.get("setup_phase"):
        # 1a. Must place initial Active if not chosen yet
        if ai_name in full_state.get("pending_initial_active", []):
            for card in my_state.get("hand_details", []):
                if card.get("category") == "pokemon" and card.get("stage") == "basic":
                    add_action("/api/action/play_active", {"player_name": ai_name, "card_id": card["id"]}, 
                               "Must play a Basic Pokemon to the Active spot to start the game.")
            return finalize_actions()
        # 1b. Active is already placed — can still place bench during setup
        else:
            bench_count = len(my_state.get("bench", []))
            for card in my_state.get("hand_details", []):
                if card.get("category") == "pokemon" and card.get("stage") == "basic" and bench_count < 3:
                    add_action("/api/action/play_bench", {"player_name": ai_name, "card_id": card["id"]},
                               "Place additional Basic Pokemon on Bench during setup to expand your board.")
            # No bench pokemon left to place or bench full — signal that setup is done from AI's side
            # (The game engine will transition out of setup once the opponent also picks)
            return finalize_actions()

    # 2. Pending Promote
    if my_state.get("pending_promote"):
        for i, bench_poke in enumerate(my_state.get("bench", [])):
            add_action("/api/action/promote", {"player_name": ai_name, "bench_index": i}, 
                       f"Must promote {bench_poke.get('name')} from bench to active after your previous active was knocked out.")
        return finalize_actions()

    # 3. Resolve Pending Effect
    pe = full_state.get("pending_effect")
    if pe and pe.get("player_name") == ai_name:
        if pe.get("type") == "inferno_dance":
            avail = pe.get("available_bench_indexes", [])
            count = pe.get("selection_count", 0)
            if deck_archetype == "fire":
                targets = _best_fire_inferno_dance_targets(my_state, avail, count)
            else:
                targets = avail[:count]
            add_action("/api/action/resolve_effect", {"player_name": ai_name, "target_indexes": targets}, 
                       f"Must resolve effect by selecting up to {count} targets. Prioritize core attacker setup.")
        return finalize_actions()

    # Not our turn or game over -> no actions
    if full_state.get("current_turn") != ai_name or full_state.get("game_over") or full_state.get("phase") != "main":
        return []

    # --- Main Phase Regular Actions ---
    turn_num = full_state.get("turn_number", 0)
    bench_count = len(my_state.get("bench", []))
    act_poke = my_state.get("active_pokemon")
    opp_act_poke = op_state.get("active_pokemon")
    hand_details = my_state.get("hand_details", [])

    has_moltres_on_bench = any((bp.get("name") or "").lower() == "moltres ex" for bp in my_state.get("bench", []))
    active_name = (act_poke.get("name") or "").lower() if act_poke else ""
    active_is_char_line = active_name in {"charmander", "charmeleon"}
    fire_retreat_plan = deck_archetype == "fire" and active_is_char_line and has_moltres_on_bench and bench_count > 0

    # ============================================================
    # ACTION PRUNING: Collect high-priority actions first.
    # 'end_turn' is only shown if no high-priority actions remain.
    # ============================================================
    has_high_priority_action = False

    # Play Basic Pokemon (Active or Bench)
    for card in my_state.get("hand_details", []):
        if card.get("category") == "pokemon" and card.get("stage") == "basic":
            if not act_poke:
                add_action("/api/action/play_active", {"player_name": ai_name, "card_id": card["id"]},
                           "🚨 CRITICAL: You have no Active Pokemon! Play this Basic Pokemon to Active position immediately or you forfeit!")
                has_high_priority_action = True
            elif bench_count < 3:
                add_action("/api/action/play_bench", {"player_name": ai_name, "card_id": card["id"]},
                           f"🚨 IMPORTANT: Play {card.get('name')} to your bench. A larger board gives you more options and protects your active.")
                has_high_priority_action = True

    # Evolve
    for card in my_state.get("hand_details", []):
        if card.get("category") == "pokemon" and card.get("stage") != "basic":
            if act_poke and act_poke.get("name") == card.get("evolves_from"):
                if turn_num > 2 and act_poke.get("turn_played", 0) < turn_num:
                    add_action("/api/action/evolve", {"player_name": ai_name, "evolution_card_id": card["id"], "target_position": "active", "target_index": 0},
                               f"🚨 CRITICAL: Evolve your Active {act_poke.get('name')} into {card.get('name')} NOW. This gives more HP and unlocks stronger attacks. Do this before attacking!")
                    has_high_priority_action = True
            for i, bp in enumerate(my_state.get("bench", [])):
                if bp.get("name") == card.get("evolves_from") and turn_num > 2 and bp.get("turn_played", 0) < turn_num:
                    add_action("/api/action/evolve", {"player_name": ai_name, "evolution_card_id": card["id"], "target_position": "bench", "target_index": i},
                               f"🚨 CRITICAL: Evolve your Bench {bp.get('name')} into {card.get('name')}. More HP and stronger attacks!")
                    has_high_priority_action = True

    # Attach Energy
    if my_state.get("energy_zone", 0) > 0 and turn_num > 1:
        if act_poke:
            needs_energy = any(not atk.get("can_use") for atk in my_state.get("active_attacks", []))
            if fire_retreat_plan:
                retreat_cost = len(act_poke.get("retreat_cost", [])) if isinstance(act_poke.get("retreat_cost", []), list) else 0
                retreat_reduction = int(my_state.get("retreat_cost_reduction", 0) or 0)
                effective_retreat_cost = max(0, retreat_cost - retreat_reduction)
                attached_now = len(act_poke.get("attached_energy", []))

                # If retreat can't be paid yet, attach to active first to unlock retreat this turn.
                if attached_now < effective_retreat_cost:
                    hint = "🔥 CRITICAL FIRE PLAN: ติดพลังงานให้ Active ก่อนเพื่อให้ถอยไป Moltres ex ได้ทันที"
                else:
                    # When retreat is already payable, avoid wasting attachment on dragged setup unit.
                    hint = ""
            elif needs_energy:
                hint = f"🚨 CRITICAL PRIORITY: {act_poke.get('name')} cannot attack yet! You MUST attach energy to it NOW. Skipping this will result in wasted turns and losing the game."
            else:
                hint = f"⚡ IMPORTANT: Attach energy to {act_poke.get('name')} to prepare for future attacks. More energy = more power."
            if hint:
                add_action("/api/action/attach_energy", {"player_name": ai_name, "target_position": "active", "target_index": 0}, hint)
                has_high_priority_action = True
        for i in range(bench_count):
            bp_name = my_state.get("bench", [])[i].get("name", f"Bench#{i}")
            bench_hint = f"⚡ Attach energy to {bp_name} on bench to prepare it for battle."
            if deck_archetype == "fire" and (bp_name or "").lower() == "moltres ex":
                bench_hint = "🔥 CRITICAL FIRE PLAN: ติดพลังงานให้ Moltres ex เพื่อเปิด Inferno Dance เร่งพลังงาน"
            if deck_archetype == "psychic" and "mewtwo" in (bp_name or "").lower():
                bench_hint = "🧠 CRITICAL PSYCHIC PLAN: ติดพลังงานให้สาย Mewtwo เป็นแกนดาเมจ"
            if deck_archetype == "lightning" and "pikachu" in (bp_name or "").lower():
                bench_hint = "⚡ CRITICAL LIGHTNING PLAN: ติดพลังงานให้ Pikachu ex เพื่อปิดเกมด้วย spread damage"
            add_action("/api/action/attach_energy", {"player_name": ai_name, "target_position": "bench", "target_index": i}, bench_hint)
            has_high_priority_action = True

    # Use Trainer
    supporter_used = my_state.get("supporter_used_turn") == turn_num
    for card in my_state.get("hand_details", []):
        cat = card.get("category")
        if cat in ["item", "supporter"]:
            if cat == "supporter" and supporter_used:
                continue

            effect = card.get("trainer_effect_calculation")
            eff_type = card.get("effect_type", "")

            hint = f"🃏 IMPORTANT: Use trainer card {card.get('name')} to gain an advantage."
            if "draw" in str(effect).lower() or eff_type == "draw" or card.get("name") in ["Professor's Research", "Poké Ball"]:
                hint = f"🃏 CRITICAL: Use {card.get('name')} early in your turn to draw more options. More cards = more choices."

            # X Speed should only appear when retreat is actually a tactical plan.
            if effect == "retreat_cost_reduce_1_this_turn":
                can_retreat_now = (
                    act_poke is not None
                    and bench_count > 0
                    and not my_state.get("retreated_this_turn")
                )
                if not can_retreat_now:
                    continue

                act_hp = act_poke.get("current_hp", 0) if act_poke else 0
                act_max_hp = max(act_poke.get("max_hp", 1), 1) if act_poke else 1
                act_hp_pct = (act_hp / act_max_hp) * 100
                can_attack_now = any(atk.get("can_use") for atk in my_state.get("active_attacks", []))

                # Skip wasteful X Speed when active is healthy and can keep attacking.
                if act_hp_pct >= 60 and can_attack_now:
                    continue

                add_action(
                    "/api/action/use_trainer",
                    {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0},
                    f"⚡ Tactical X Speed: ใช้เพื่อลดค่าถอย 1 แล้วสลับตัวหนี ({act_poke.get('name') if act_poke else 'active'})"
                )
                has_high_priority_action = True
                continue

            if effect == "opponent_shuffle_hand_draw_3":
                if op_state.get("hand_count", 0) < 5:
                    continue
                add_action(
                    "/api/action/use_trainer",
                    {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0},
                    f"🃏 Tactical Red Card: คู่ต่อสู้ถือมือ {op_state.get('hand_count', 0)} ใบ คุ้มที่จะกดลดคุณภาพมือ"
                )
                has_high_priority_action = True
                continue

            if effect == "draw_2_cards":
                if my_state.get("hand_count", 0) > 4:
                    continue
                add_action(
                    "/api/action/use_trainer",
                    {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0},
                    f"🃏 CRITICAL: มือบาง ({my_state.get('hand_count', 0)} ใบ) ใช้ draw เพื่อหา combo"
                )
                has_high_priority_action = True
                continue

            if effect == "search_random_basic_pokemon_to_hand":
                if bench_count >= 3:
                    continue
                add_action(
                    "/api/action/use_trainer",
                    {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0},
                    "🃏 Tactical Pokeball: หา Basic มาเติม bench/แผน setup"
                )
                has_high_priority_action = True
                continue

            if effect == "attack_damage_boost_10_this_turn":
                if not act_poke or not opp_act_poke:
                    continue
                opp_hp = opp_act_poke.get("current_hp", 0)
                convertible_ko = any(
                    atk.get("can_use") and atk.get("damage", 0) < opp_hp <= (atk.get("damage", 0) + 10)
                    for atk in my_state.get("active_attacks", [])
                )
                if not convertible_ko:
                    continue
                add_action(
                    "/api/action/use_trainer",
                    {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0},
                    "🃏 LETHAL SETUP: +10 ทำให้โจมตีครั้งนี้ปิด KO ได้"
                )
                has_high_priority_action = True
                continue

            if effect == "heal_20_from_target" or card.get("name") == "Potion":
                if act_poke:
                    missing_hp = act_poke.get("max_hp", 0) - act_poke.get("current_hp", 0)
                    act_hp_pct = (act_poke.get("current_hp", 0) / max(act_poke.get("max_hp", 1), 1)) * 100
                    is_ex = " ex" in f" {(act_poke.get('name') or '').lower()}"
                    if missing_hp >= 20 and (act_hp_pct <= 70 or is_ex):
                        add_action("/api/action/use_trainer", {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0},
                                   f"💊 Heal {act_poke.get('name')} to keep it alive longer.")
                        has_high_priority_action = True
                for i, bp in enumerate(my_state.get("bench", [])):
                    missing_hp = bp.get("max_hp", 0) - bp.get("current_hp", 0)
                    bp_hp_pct = (bp.get("current_hp", 0) / max(bp.get("max_hp", 1), 1)) * 100
                    bp_is_ex = " ex" in f" {(bp.get('name') or '').lower()}"
                    if missing_hp >= 20 and (bp_hp_pct <= 70 or bp_is_ex):
                        add_action("/api/action/use_trainer", {"player_name": ai_name, "card_id": card["id"], "target_position": "bench", "target_index": i},
                                   f"💊 Heal {bp.get('name')} on bench.")
                        has_high_priority_action = True
            elif effect == "opponent_switch_active_to_bench":
                opp_bench = len(op_state.get("bench", []))
                if opp_bench <= 0:
                    continue
                target_indexes = _sorted_opponent_bench_targets(op_state)
                for i in target_indexes:
                    add_action("/api/action/use_trainer", {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0, "opponent_switch_index": i},
                               "🔄 Tactical Sabrina: บังคับสลับเพื่อดึงเป้าหมายที่จัดการง่ายหรือจังหวะเสียเปรียบ")
                    has_high_priority_action = True
            else:
                add_action("/api/action/use_trainer", {"player_name": ai_name, "card_id": card["id"], "target_position": "active", "target_index": 0}, hint)
                has_high_priority_action = True

    # Retreat
    if not my_state.get("retreated_this_turn") and act_poke and bench_count > 0:
        retreat_cost = len(act_poke.get("retreat_cost", [])) if isinstance(act_poke.get("retreat_cost", []), list) else 0
        retreat_reduction = int(my_state.get("retreat_cost_reduction", 0) or 0)
        retreat_cost = max(0, retreat_cost - retreat_reduction)
        attached = len(act_poke.get("attached_energy", []))
        # Do not offer illegal retreats that cannot be paid.
        if attached < retreat_cost:
            retreat_cost = -1
        act_hp_pct = (act_poke.get("current_hp", 0) / max(act_poke.get("max_hp", 1), 1)) * 100
        # Deck-fire tactical plan: if setup unit got dragged active while Moltres is on bench, retreat immediately.
        if deck_archetype == "fire" and active_is_char_line:
            moltres_indexes = [i for i, bp in enumerate(my_state.get("bench", [])) if (bp.get("name") or "").lower() == "moltres ex"]
            if retreat_cost >= 0:
                for i in moltres_indexes:
                    add_action(
                        "/api/action/retreat",
                        {"player_name": ai_name, "bench_index": i},
                        "🔥 CRITICAL RETREAT PLAN: ถอยตัวปั้นกลับ bench แล้วเอา Moltres ex มาเร่งพลังงาน"
                    )
                    has_high_priority_action = True
        if retreat_cost >= 0:
            if act_hp_pct < 40:
                for i in range(bench_count):
                    add_action("/api/action/retreat", {"player_name": ai_name, "bench_index": i},
                               f"⚠️ {act_poke.get('name')} is low on HP ({int(act_hp_pct)}%). Consider retreating to save it!")
            else:
                for i in range(bench_count):
                    add_action("/api/action/retreat", {"player_name": ai_name, "bench_index": i},
                               f"Retreat only if tactically necessary.")

    # Abilities
    act_ability = my_state.get("active_ability")
    if act_ability and act_ability.get("can_use"):
        ab_name = act_ability.get('name')
        hint = f"⭐ Use {ab_name} ability for extra effect!"
        if ab_name == "Psyembrace": 
            hint += " It attaches energy from discard, NOT from your Energy Zone! Very powerful!"
        add_action("/api/action/use_ability", {"player_name": ai_name, "pokemon_position": "active", "pokemon_index": 0}, hint)
        has_high_priority_action = True

    for ab in my_state.get("bench_abilities", []):
        if ab.get("can_use"):
            ab_name = ab.get('name')
            hint = f"⭐ Use {ab_name} bench ability!"
            if ab_name == "Psyembrace": 
                hint += " It attaches energy from discard, NOT from your Energy Zone! Very powerful!"
            add_action("/api/action/use_ability", {"player_name": ai_name, "pokemon_position": "bench", "pokemon_index": ab.get("index", 0)}, hint)
            has_high_priority_action = True

    # Attack (Lethal Calculations)
    is_first_player_turn_1 = (turn_num == 1 and full_state.get("current_turn") == full_state.get("first_player"))
    if not is_first_player_turn_1 and act_poke and opp_act_poke:
        opp_hp = opp_act_poke.get("current_hp", 0)
        fire_bench_count = len([bp for bp in my_state.get("bench", []) if bp.get("type") == "fire"])

        for atk in my_state.get("active_attacks", []):
            if atk.get("can_use"):
                dmg = atk.get("damage", 0)
                eff = atk.get("effect_calculation")

                # Prevent useless Inferno Dance spam when there is no Fire bench target.
                if atk.get("name") == "Inferno Dance" and fire_bench_count <= 0:
                    continue

                if dmg >= opp_hp and dmg > 0:
                    hint = "🏆 LETHAL! Use this attack to KO the opponent and gain a prize point! This is your best move!"
                else:
                    hint = f"⚔️ Attack for {dmg} damage. Opponent will have {max(0, opp_hp - dmg)} HP left."
                    if atk["name"] == "Inferno Dance":
                        hint += " This ALSO flips 3 coins to attach Fire Energy to your bench FOR FREE! It does NOT consume your Energy Zone limit! Fantastic move!"

                if eff == "damage_self_bench_30" and bench_count > 0:
                    if fire_retreat_plan and not (dmg >= opp_hp and dmg > 0):
                        continue
                    # Prefer hitting the healthiest own bench target for recoil-style effects.
                    bench_order = sorted(
                        range(bench_count),
                        key=lambda i: my_state.get("bench", [])[i].get("current_hp", 0),
                        reverse=True,
                    )
                    for i in bench_order:
                        add_action("/api/action/attack", {"player_name": ai_name, "attack_name": atk["name"], "self_bench_target_index": i}, hint)
                elif eff == "damage_to_opponent_pokemon_30":
                    if fire_retreat_plan and not (dmg >= opp_hp and dmg > 0):
                        continue
                    opp_bench_count = len(op_state.get("bench", []))
                    opp_order = _sorted_opponent_bench_targets(op_state)
                    for i in opp_order[:opp_bench_count]:
                        add_action("/api/action/attack", {"player_name": ai_name, "attack_name": atk["name"], "bench_target_index": i}, hint)
                    add_action("/api/action/attack", {"player_name": ai_name, "attack_name": atk["name"]}, hint)
                else:
                    if fire_retreat_plan and not (dmg >= opp_hp and dmg > 0):
                        continue
                    add_action("/api/action/attack", {"player_name": ai_name, "attack_name": atk["name"]}, hint)
                has_high_priority_action = True

    # ============================================================
    # ACTION PRUNING: Only add end_turn if truly nothing else to do
    # ============================================================
    if not has_high_priority_action:
        add_action("/api/action/end_turn", {"player_name": ai_name},
                   "You have exhausted all productive actions. End your turn.")

    return finalize_actions()

def _get_legal_actions(view: Dict[str, Any], full_state: Dict[str, Any], my_state: Dict[str, Any], op_state: Dict[str, Any]) -> List[str]:
    """Deduces legal actions from the current state."""
    actions = []
    
    # 1. Setup Phase Initial Active
    if view["setup_phase"] and my_state["name"] in view["pending_initial_active"]:
        for card in my_state.get("hand_details", []):
            if card.get("category") == "pokemon" and card.get("stage") == "basic":
                actions.append(f"PLAY INITIAL ACTIVE: card_id={card['id']}")
        return actions # Can ONLY do this

    # 2. Pending Promote
    if view["my_state"]["pending_promote"]:
        for i, bench_poke in enumerate(my_state.get("bench", [])):
            actions.append(f"PROMOTE FROM BENCH: bench_index={i} ({bench_poke['name']})")
        return actions # Can ONLY do this

    # 3. Resolve Pending Effect
    if view["pending_effect"] and view["pending_effect"].get("player_name") == my_state["name"]:
        pe = view["pending_effect"]
        if pe.get("type") == "inferno_dance":
            avail = pe.get("available_bench_indexes", [])
            count = pe.get("selection_count", 0)
            actions.append(f"RESOLVE INFERNO DANCE: target_indexes=list (Available indexes: {avail}, need {count})")
        return actions

    # Not our turn or game over -> no actions
    if view["current_turn"] != my_state["name"] or view["game_over"] or view["phase"] != "main":
        return []

    # --- Main Phase Regular Actions ---
    
    # End Turn is always an option in main phase
    actions.append("END TURN")
    
    # Play Basic Pokemon (Active or Bench)
    bench_count = len(my_state.get("bench", []))
    for card in my_state.get("hand_details", []):
        if card.get("category") == "pokemon" and card.get("stage") == "basic":
            if not my_state.get("active_pokemon"):
                actions.append(f"PLAY ACTIVE: card_id={card['id']}")
            elif bench_count < 3:
                actions.append(f"PLAY BENCH: card_id={card['id']}")

    # Evolve
    turn_num = view["turn_number"]
    for card in my_state.get("hand_details", []):
        if card.get("category") == "pokemon" and card.get("stage") != "basic":
            # Check Active
            act = my_state.get("active_pokemon")
            if act and act.get("name") == card.get("evolves_from"):
                if turn_num > 2 and act.get("turn_played", 0) < turn_num:
                    actions.append(f"EVOLVE: evolution_card_id={card['id']}, target_position=active, target_index=0")
            # Check Bench
            for i, bp in enumerate(my_state.get("bench", [])):
                if bp.get("name") == card.get("evolves_from"):
                    if turn_num > 2 and bp.get("turn_played", 0) < turn_num:
                        actions.append(f"EVOLVE: evolution_card_id={card['id']}, target_position=bench, target_index={i}")

    # Attach Energy
    if my_state.get("energy_zone", 0) > 0 and turn_num > 1:
        if my_state.get("active_pokemon"):
            actions.append("ATTACH ENERGY: target_position=active, target_index=0")
        for i in range(bench_count):
            actions.append(f"ATTACH ENERGY: target_position=bench, target_index={i}")

    # Use Trainer
    supporter_used = my_state.get("supporter_used_turn") == turn_num
    for card in my_state.get("hand_details", []):
        cat = card.get("category")
        if cat in ["item", "supporter"]:
            if cat == "supporter" and supporter_used:
                continue
            # Simple assumption: AI can try to use any trainer.
            # Some like Sabrina might need opponent_switch_index, but we'll list the basic one
            effect = card.get("trainer_effect_calculation")
            if effect == "heal_20_from_target":
                actions.append(f"USE TRAINER: card_id={card['id']}, target_position=active, target_index=0")
                for i in range(bench_count):
                    actions.append(f"USE TRAINER: card_id={card['id']}, target_position=bench, target_index={i}")
            elif effect == "opponent_switch_active_to_bench":
                # Require opponent_switch_index
                opp_bench = len(op_state.get("bench", []))
                for i in range(opp_bench):
                    actions.append(f"USE TRAINER (Sabrina): card_id={card['id']}, target_position=active, target_index=0, opponent_switch_index={i}")
            else:
                actions.append(f"USE TRAINER: card_id={card['id']}, target_position=active, target_index=0")

    # Retreat
    if not my_state.get("retreated_this_turn") and my_state.get("active_pokemon") and bench_count > 0:
        # Simplification: we don't strictly check energy cost here because AI will fail gracefuly if it tries.
        for i in range(bench_count):
            actions.append(f"RETREAT: bench_index={i}")

    # Abilities
    act_ability = my_state.get("active_ability")
    if act_ability and act_ability.get("can_use"):
        actions.append("USE ABILITY: pokemon_position=active, pokemon_index=0")
    
    for ab in my_state.get("bench_abilities", []):
        if ab.get("can_use"):
            actions.append(f"USE ABILITY: pokemon_position=bench, pokemon_index={ab['index']}")

    # Attack (only if first player's turn > 1)
    is_first_player_turn_1 = (turn_num == 1 and view["current_turn"] == full_state.get("first_player"))
    if not is_first_player_turn_1 and my_state.get("active_pokemon") and op_state.get("active_pokemon"):
        for atk in my_state.get("active_attacks", []):
            if atk.get("can_use"):
                # Handle specific attack targeting if needed
                eff = atk.get("effect_calculation")
                if eff == "damage_self_bench_30" and bench_count > 0:
                    for i in range(bench_count):
                        actions.append(f"ATTACK: attack_name='{atk['name']}', self_bench_target_index={i}")
                elif eff == "damage_to_opponent_pokemon_30":
                    opp_bench_count = len(op_state.get("bench", []))
                    for i in range(opp_bench_count):
                        actions.append(f"ATTACK: attack_name='{atk['name']}', bench_target_index={i}")
                    actions.append(f"ATTACK: attack_name='{atk['name']}' (Target Active)")
                else:
                    actions.append(f"ATTACK: attack_name='{atk['name']}'")

    return actions

def build_system_prompt(deck_hint: str = "") -> str:
    base = """You are "Goopy AI", a confident and strategic Pokemon TCG Pocket rival.
Your objective is to win the game by scoring 3 points or wiping the opponent's board.

You will be provided with:
1. GAME STATE: The current board, your hand, your energy, and the opponent's visible board.
2. LEGAL ACTIONS: A strict list of actions you are allowed to take this turn (with hints on their priority).

CRITICAL RULES (Follow strictly):
- ACTION PRUNING: If 'end_turn' is NOT in the LEGAL ACTIONS list, you MUST NOT choose it. The system has hidden it because better options exist.
- LETHAL STRIKE: Always prioritize an attack that guarantees a Knock Out (KO).
- RESOURCE MANAGEMENT: Do not waste energy recklessly.
- ACTION-CARD MATCHING: CRITICAL - The 'card_name' MUST match the 'type' of action. You CANNOT use Trainer/Item cards (like X Speed, Potion, Poke Ball, Professor's Research, Sabrina) for actions like 'evolve', 'attack', 'play_bench', or 'attach_energy'.
- LANGUAGE: "final_decision_reasoning" ต้องเป็นภาษาไทยแบบสั้นมาก (ไม่เกิน 8 คำ) และเข้าใจง่าย.
- STYLE: ตรงประเด็น ไม่ต้องบรรยายยาว.
"""
    if deck_hint:
        base += f"\n{deck_hint}\n"

    base += """
OUTPUT FORMAT:
You MUST choose exactly ONE action from the LEGAL ACTIONS list.
You MUST output ONLY a valid, parseable JSON object. DO NOT wrap in markdown blocks.

{
    "final_decision_reasoning": "เหตุผลสั้นๆ ภาษาไทย ไม่เกิน 8 คำ",
  "endpoint": "exact API endpoint from the chosen legal action",
  "payload": {
    "player_name": "Goopy AI"
  }
}

Endpoint API Parameters Context:
- PLAY INITIAL ACTIVE -> "/api/action/play_active" | body: {"player_name", "card_id"}
- PLAY ACTIVE -> "/api/action/play_active" | body: {"player_name", "card_id"}
- PLAY BENCH -> "/api/action/play_bench" | body: {"player_name", "card_id"}
- EVOLVE -> "/api/action/evolve" | body: {"player_name", "evolution_card_id", "target_position", "target_index"}
- ATTACH ENERGY -> "/api/action/attach_energy" | body: {"player_name", "target_position", "target_index"}
- USE TRAINER -> "/api/action/use_trainer" | body: {"player_name", "card_id", "target_position", "target_index", "opponent_switch_index"}
- RETREAT -> "/api/action/retreat" | body: {"player_name", "bench_index"}
- USE ABILITY -> "/api/action/use_ability" | body: {"player_name", "pokemon_position", "pokemon_index"}
- ATTACK -> "/api/action/attack" | body: {"player_name", "attack_name", "bench_target_index", "self_bench_target_index"}
- PROMOTE FROM BENCH -> "/api/action/promote" | body: {"player_name", "bench_index"}
- RESOLVE INFERNO DANCE -> "/api/action/resolve_effect" | body: {"player_name", "target_indexes": [int, ...]}
- END TURN -> "/api/action/end_turn" | body: {}
"""
    return base

def get_deck_hint(game_instance) -> str:
    """Look up the AI's deck ID and return the matching strategy playbook."""
    try:
        ai_player = game_instance.get_player_by_name("Goopy AI")
        if ai_player and hasattr(ai_player, 'deck_id'):
            return DECK_PLAYBOOKS.get(ai_player.deck_id, "")
    except Exception:
        pass
    return ""


def _score_initial_active_candidate(
    card: Dict[str, Any],
    hand_details: list[Dict[str, Any]],
    deck_id: str,
    energy_type: str,
) -> tuple[float, list[str]]:
    """Score a Basic Pokemon for opening Active selection based on deck + hand synergy."""
    score = 0.0
    reasons: list[str] = []

    name = (card.get("name") or "").strip()
    name_l = name.lower()

    # 1) Deck-specific opening preference
    preferred = [n.lower() for n in DECK_OPENING_ACTIVE_PREFS.get(deck_id, [])]
    if name_l in preferred:
        score += 3.0
        reasons.append("ตรงแผนเปิดของเด็ค")

    # 2) Same type as deck energy
    if energy_type and card.get("type") == energy_type:
        score += 1.5
        reasons.append("ธาตุตรงกับพลังงานเด็ค")

    # 3) Evolution potential from current hand
    evolutions_in_hand = [
        c for c in hand_details
        if c.get("category") == "pokemon" and c.get("stage") != "basic" and c.get("evolves_from") == name
    ]
    if evolutions_in_hand:
        score += 2.5
        reasons.append("มีร่างวิวัฒนาการในมือ")

    # 4) Can attack early with low-cost move
    attacks = card.get("attacks") or []
    low_cost = any(len((atk or {}).get("cost", [])) <= 1 for atk in attacks if isinstance(atk, dict))
    if low_cost:
        score += 1.0
        reasons.append("มีท่า cost ต่ำ เปิดเกมง่าย")

    # 5) Higher HP is safer in opening
    hp = card.get("hp") or 0
    if isinstance(hp, (int, float)):
        score += min(float(hp), 180.0) / 90.0
        reasons.append(f"HP {int(hp)}")

    # 6) Lower retreat cost is better for opening flexibility
    retreat_cost = card.get("retreat_cost") or []
    rc = len(retreat_cost) if isinstance(retreat_cost, list) else 0
    if rc <= 1:
        score += 0.8
        reasons.append("retreat cost ต่ำ")
    elif rc >= 3:
        score -= 0.5

    # 7) Slight bias for ex as opener in this format
    if " ex" in f" {name_l}":
        score += 0.6
        reasons.append("สถานะ ex")

    # 8) Deck-specific opening nuance from current hand curve
    pokemon_names = [
        (c.get("name") or "").strip().lower()
        for c in hand_details
        if c.get("category") == "pokemon"
    ]
    basic_fire_count = sum(
        1
        for c in hand_details
        if c.get("category") == "pokemon" and c.get("stage") == "basic" and c.get("type") == "fire"
    )

    if deck_id == "D01_FIRE":
        has_charmeleon = "charmeleon" in pokemon_names
        has_charizard = any("charizard" in n for n in pokemon_names)
        has_moltres = "moltres ex" in pokemon_names
        has_other_fire_basic = basic_fire_count >= 2

        if name_l == "moltres ex":
            # Hard preference: open Moltres ex first to start energy acceleration plan.
            score += 4.5
            reasons.append("ตัวเปิดหลักของเด็คไฟเพื่อเร่งพลังงาน")
            if has_other_fire_basic:
                score += 2.6
                reasons.append("Inferno Dance คุ้มเพราะมีเป้าไฟบน bench")
            if has_charmeleon or has_charizard:
                score += 1.8
                reasons.append("ช่วยเร่งพลังงานให้สาย Charizard")

        if name_l == "charmander":
            # When Moltres exists, keep Charmander safer on bench in most openings.
            if has_moltres:
                score -= 3.2
                reasons.append("มี Moltres ex แล้ว ควรเก็บ Charmander ไว้บน bench")
            if has_charmeleon:
                score += 1.8
                reasons.append("มี Charmeleon ในมือ ปั้นสายวิวัฒนาการได้เร็ว")
            if has_charizard:
                score += 0.9
                reasons.append("มีปลายสาย Charizard ในมือ")

        # If Moltres is not in hand, allow Charmander line to become the opener.
        if not has_moltres and name_l == "charmander":
            score += 2.2
            reasons.append("ไม่มี Moltres ex จึงเปิดด้วยสาย Charizard")

    elif deck_id == "D02_PSYCHIC":
        has_kirlia = "kirlia" in pokemon_names
        has_gardevoir = "gardevoir" in pokemon_names
        has_mewtwo_ex = "mewtwo ex" in pokemon_names
        has_mewtwo = "mewtwo" in pokemon_names

        if name_l == "mewtwo ex":
            score += 4.8
            reasons.append("ตัวเปิดหลักของเด็ค Psychic")
            if has_kirlia or has_gardevoir:
                score += 1.4
                reasons.append("ยืนหน้าให้สาย Gardevoir set up")

        if name_l == "mewtwo":
            score += 3.2
            reasons.append("ตัวทำดาเมจหลัก ควรยืน Active")
            if has_kirlia or has_gardevoir:
                score += 1.0
                reasons.append("ยืนหน้าให้สาย Gardevoir set up")

        if name_l == "ralts":
            if has_mewtwo_ex or has_mewtwo:
                score -= 3.5
                reasons.append("มี Mewtwo แล้ว ควรวาง Ralts ไว้ bench")
            if has_kirlia:
                score += 1.0
                reasons.append("มี Kirlia ในมือ")
            if has_gardevoir:
                score += 0.7
                reasons.append("มี Gardevoir ในมือ")
            if not has_kirlia and not has_gardevoir:
                score -= 1.0

        # If no mewtwo line in hand, Ralts becomes acceptable opener.
        if not has_mewtwo_ex and not has_mewtwo and name_l == "ralts":
            score += 2.5
            reasons.append("ไม่มี Mewtwo ในมือ จึงเปิดด้วย Ralts")

    return score, reasons


def _rank_initial_active_candidates(
    hand_details: list[Dict[str, Any]],
    deck_id: str,
    energy_type: str,
) -> list[Dict[str, Any]]:
    """Return ranked Basic candidates with score and reason text."""
    basics = [
        c for c in hand_details
        if c.get("category") == "pokemon" and c.get("stage") == "basic"
    ]

    ranked: list[Dict[str, Any]] = []
    basic_names = [
        ((c.get("name") or "").strip().lower())
        for c in basics
    ]
    has_moltres_ex_basic = "moltres ex" in basic_names
    has_mewtwo_ex_basic = "mewtwo ex" in basic_names
    has_plain_mewtwo_basic = "mewtwo" in basic_names

    for card in basics:
        score, reasons = _score_initial_active_candidate(card, hand_details, deck_id, energy_type)
        card_name_l = ((card.get("name") or "").strip().lower())

        # Hard opening policy overrides from playstyle feedback.
        if deck_id == "D01_FIRE" and has_moltres_ex_basic:
            if card_name_l == "moltres ex":
                score += 100.0
                reasons.append("override: เปิด Moltres ex ก่อนเพื่อเร่งพลังงาน")
            elif card_name_l == "charmander":
                score -= 40.0
                reasons.append("override: เก็บ Charmander ไว้ bench")

        if deck_id == "D02_PSYCHIC":
            if has_mewtwo_ex_basic:
                if card_name_l == "mewtwo ex":
                    score += 160.0
                    reasons.append("override: เปิด Mewtwo ex ก่อนเสมอ")
                elif card_name_l == "mewtwo":
                    score -= 40.0
                    reasons.append("override: มี Mewtwo ex แล้ว ไม่ควรเปิด Mewtwo ปกติ")
                elif card_name_l == "ralts":
                    score -= 60.0
                    reasons.append("override: Ralts ควรอยู่ bench")
            elif has_plain_mewtwo_basic:
                if card_name_l == "mewtwo":
                    score += 100.0
                    reasons.append("override: เปิด Mewtwo เมื่อไม่มี Mewtwo ex")
                elif card_name_l == "ralts":
                    score -= 50.0
                    reasons.append("override: Ralts ควรอยู่ bench")

        ranked.append({
            "card": card,
            "score": score,
            "reason": ", ".join(reasons) if reasons else "คะแนนรวมดีที่สุดจากสถานะปัจจุบัน",
            "hp": int(card.get("hp") or 0),
        })

    ranked.sort(key=lambda x: (x["score"], x["hp"]), reverse=True)
    return ranked


def _parse_error_meta(err_text: str) -> dict:
    """Extract rate-limit metadata from an exception message."""
    retry_after_seconds = None
    retry_match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", err_text, flags=re.IGNORECASE)
    if retry_match:
        try:
            retry_after_seconds = float(retry_match.group(1))
        except ValueError:
            pass
    is_rate_limited = "429" in err_text or "quota" in err_text.lower() or "rate_limit" in err_text.lower()
    return {"rate_limited": is_rate_limited, "retry_after_seconds": retry_after_seconds}


def query_llm(ai_view: Dict[str, Any], deck_hint: str = "") -> Dict[str, Any]:
    """Query local Qwen2.5 model and return a structured decision JSON."""
    from local_llm import query_local_llm

    prompt = f"Current Game State:\n{json.dumps(ai_view, indent=2)}\n\nWhat is your next action?"
    system_prompt = build_system_prompt(deck_hint) + "\n\nPlease output strictly in JSON format."

    try:
        response_text = query_local_llm(system_prompt=system_prompt, user_prompt=prompt)
        
        # Strip potential markdown code blocks commonly generated by instruction-tuned models
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
            
        parsed = json.loads(response_text)
        
        # [GUARDRAIL] LLM Configuration / Action-Card Hallucination Sanity Check
        endpoint = parsed.get("endpoint", "")
        payload = parsed.get("payload", {})
        if endpoint in {"/api/action/evolve", "/api/action/attach_energy", "/api/action/attack", "/api/action/play_active", "/api/action/play_bench"}:
            card_id = payload.get("card_id") or payload.get("evolution_card_id")
            if card_id:
                hand = ai_view.get("hand_details", [])
                card_name = next(((c.get("name") or "").lower() for c in hand if c.get("id") == card_id), "")
                if card_name in {"x speed", "potion", "poké ball", "poke ball", "professor's research", "sabrina", "giovanni", "hand scope", "red card"}:
                    print(f" [GUARDRAIL] LLM Bug (Endpoint={endpoint}, Card={card_name})")
                    return {"error": "Guardrail Check Failed", "endpoint": "", "payload": {}}

        return parsed
        
    except json.JSONDecodeError as e:
        logger.error(f"Local LLM returned invalid JSON: {e}\nRaw output: {response_text}")
        return {"error": "Invalid JSON", "endpoint": "", "payload": {}}
    except Exception as e:
        err_text = str(e)
        logger.error(f"Local LLM error: {err_text}")
        meta = _parse_error_meta(err_text)
        return {"error": err_text, "endpoint": "", "payload": {}, **meta}


def _pick_best_fallback_action(legal_actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose a safe legal fallback action, preferring productive moves over end_turn."""
    if not legal_actions:
        return None

    # If scored actions are available, trust tactical scoring first.
    scored_sorted = sorted(
        legal_actions,
        key=lambda a: (a.get("score", float("-inf")), a.get("raw_score", float("-inf")), a.get("probability", 0.0)),
        reverse=True,
    )
    top = scored_sorted[0] if scored_sorted else None
    if top and top.get("endpoint") != "/api/action/end_turn":
        return top

    # Emergency tactical overrides from generated hints.
    for action in legal_actions:
        hint = (action.get("hint") or "")
        if "CRITICAL RETREAT PLAN" in hint or "LETHAL" in hint:
            return action

    # Prefer tactical trainer plays over generic trainer usage.
    trainer_effect_by_card = {}
    for action in legal_actions:
        if action.get("endpoint") == "/api/action/use_trainer":
            payload = action.get("payload", {}) or {}
            cid = payload.get("card_id")
            if cid:
                trainer_effect_by_card[cid] = action

    for action in trainer_effect_by_card.values():
        hint = (action.get("hint") or "")
        if "LETHAL SETUP" in hint or "Tactical Sabrina" in hint or "Tactical X Speed" in hint:
            return action

    priority = [
        "/api/action/attack",
        "/api/action/attach_energy",
        "/api/action/evolve",
        "/api/action/use_ability",
        "/api/action/use_trainer",
        "/api/action/play_active",
        "/api/action/play_bench",
        "/api/action/retreat",
        "/api/action/resolve_effect",
        "/api/action/promote",
        "/api/action/end_turn",
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for action in legal_actions:
        endpoint = action.get("endpoint")
        if not endpoint:
            continue
        grouped.setdefault(endpoint, []).append(action)

    for endpoint in priority:
        options = grouped.get(endpoint, [])
        if options:
            return options[0]
    return legal_actions[0]


def _is_supporter_card_in_hand(my_state: dict[str, Any], card_id: str | None) -> bool:
    if not card_id:
        return False
    for c in my_state.get("hand_details", []):
        if c.get("id") == card_id:
            return c.get("category") == "supporter"
    return False


def _best_vs_second_score(legal_actions: list[dict[str, Any]]) -> tuple[float, float]:
    if not legal_actions:
        return (0.0, 0.0)
    sorted_scores = sorted((float(a.get("score", 0.0)) for a in legal_actions), reverse=True)
    best = sorted_scores[0]
    second = sorted_scores[1] if len(sorted_scores) > 1 else float("-inf")
    return (best, second)


def _best_vs_second_raw_score(legal_actions: list[dict[str, Any]]) -> tuple[float, float]:
    if not legal_actions:
        return (0.0, 0.0)
    sorted_scores = sorted((float(a.get("raw_score", a.get("score", 0.0))) for a in legal_actions), reverse=True)
    best = sorted_scores[0]
    second = sorted_scores[1] if len(sorted_scores) > 1 else float("-inf")
    return (best, second)


def _describe_action(endpoint: str, payload: dict) -> str:
    """Human-readable short action description for AI thought syncing."""
    if endpoint == "/api/action/play_active":
        return f"ลง {payload.get('card_id', '')} เป็น Active"
    if endpoint == "/api/action/play_bench":
        return f"ลง {payload.get('card_id', '')} บน Bench"
    if endpoint == "/api/action/evolve":
        return f"วิวัฒนาการด้วย {payload.get('evolution_card_id', '')}"
    if endpoint == "/api/action/attach_energy":
        return f"ติดพลังงานที่ {payload.get('target_position', 'active')}"
    if endpoint == "/api/action/use_trainer":
        return f"ใช้ Trainer {payload.get('card_id', '')}"
    if endpoint == "/api/action/retreat":
        return "สลับ Active ไป Bench"
    if endpoint == "/api/action/use_ability":
        return "ใช้ความสามารถ"
    if endpoint == "/api/action/attack":
        return f"ใช้ท่า {payload.get('attack_name', '')}"
    if endpoint == "/api/action/promote":
        return "โปรโมตโปเกมอนจาก Bench"
    if endpoint == "/api/action/resolve_effect":
        return "แก้เอฟเฟกต์ค้าง"
    if endpoint == "/api/action/end_turn":
        return "จบเทิร์น"
    return endpoint


def execute_ai_turn(game_instance):
    """
    Called by the backend when it's Goopy AI's turn or when it has a mandatory action.
    Loops continuously until the turn is truly over (end_turn called, game over, or
    consecutive failures exceed threshold — meaning the AI is stuck and we force a resolution).
    """
    ai_name = "Goopy AI"
    MAX_CONSECUTIVE_FAILURES = 3  # Fail limit per individual action attempt (resets on success)
    consecutive_failures = 0
    legal_actions = []  # keep in scope for fallback

    while True:
        if game_instance.game_over:
            print("[Goopy AI] Game over — stopping loop.")
            break

        full_state = game_instance.get_full_state()

        # --- Determine if AI needs to act ---
        is_pending_active = full_state.get("setup_phase") and ai_name in full_state.get("pending_initial_active", [])
        is_setup_bench = full_state.get("setup_phase") and not is_pending_active and full_state.get("player_1", {}).get("name") == ai_name and full_state.get("player_1", {}).get("active_pokemon") is not None or \
                         full_state.get("setup_phase") and not is_pending_active and full_state.get("player_2", {}).get("name") == ai_name and full_state.get("player_2", {}).get("active_pokemon") is not None
        is_my_turn_main = full_state.get("current_turn") == ai_name and full_state.get("phase") == "main"
        is_pending_promote = (
            full_state.get("player_1", {}).get("name") == ai_name and full_state.get("player_1", {}).get("pending_promote")
        ) or (
            full_state.get("player_2", {}).get("name") == ai_name and full_state.get("player_2", {}).get("pending_promote")
        )
        is_pending_effect = full_state.get("pending_effect") and full_state.get("pending_effect", {}).get("player_name") == ai_name

        act_needed = is_pending_active or is_setup_bench or is_my_turn_main or is_pending_promote or is_pending_effect

        if not act_needed:
            print("[Goopy AI] No action needed at this time — exiting loop.")
            break

        # --- Get legal actions with heuristic hints ---
        ai_view = parse_state_for_ai(full_state, ai_name)
        legal_actions = ai_view.get("legal_actions", [])

        if not legal_actions:
            # Nothing to do — end turn if we're in main phase, else just stop
            print("[Goopy AI] No legal actions available.")
            if is_my_turn_main and not game_instance.game_over:
                print("[Goopy AI] Ending turn (no valid moves).")
                game_instance.action_end_turn()
            break

        # Forced phases still go to LLM (promote, initial active, pending effects)
        if is_pending_active or is_pending_promote or is_pending_effect:
            print("[Goopy AI] Forced action phase. Will still ask LLM to make strategic decision.")
        
        # FAST PATH: Setup bench only — skip LLM for pure bench placement during setup.
        if is_setup_bench and not is_pending_active:
            print("[Goopy AI] Setup bench phase. Using rule-based fast-path (no LLM needed).")
            best_action = _pick_best_fallback_action(legal_actions)
            if best_action:
                endpoint = best_action.get("endpoint", "")
                payload = best_action.get("payload", {})
                if isinstance(payload, dict):
                    payload["player_name"] = ai_name
                try:
                    if endpoint == "/api/action/play_bench":
                        success, msg, _ = game_instance.action_play_bench(ai_name, payload.get("card_id"))
                    elif endpoint == "/api/action/play_active":
                        success, msg, _ = game_instance.action_play_active(ai_name, payload.get("card_id"))
                    else:
                        success, msg = False, "Unsupported endpoint in setup bench"
                    print(f"[Goopy AI] Setup bench result: success={success} | {msg}")
                    game_instance.latest_ai_thought = f"วางการ์ดตั้งต้น: {_describe_action(endpoint, payload)}"
                except Exception as e:
                    print(f"[Goopy AI] Setup bench error: {e}")
                    success = False
                if not success:
                    break
            else:
                print("[Goopy AI] No bench actions available in setup — done.")
                break
            continue  # Loop back to check if more bench placements are needed

        # --- Ask LLM for a decision only on close-score states ---
        import math
        
        # 1. Softmax Normalization (Temperature = 100 for proper scaling)
        T = 200.0
        scores = [a.get("score", 0) for a in legal_actions]
        max_score = max(scores) if scores else 0
        exp_scores = [math.exp((score - max_score) / T) for score in scores]
        sum_exp = sum(exp_scores)
        
        for i, a in enumerate(legal_actions):
            a["probability"] = exp_scores[i] / sum_exp if sum_exp > 0 else 0.0

        # Sort actions by probability descending
        legal_actions.sort(key=lambda x: x["probability"], reverse=True)
        top_action = legal_actions[0] if legal_actions else None

        # 2. Early Exit Logic (Fast Path)
        if top_action and top_action.get("probability", 0) >= 0.85:
            endpoint = top_action.get("endpoint", "")
            payload = top_action.get("payload", {})
            prob_pct = top_action["probability"] * 100
            print(f" -----  FAST PATH: High confidence ({prob_pct:.1f}%) -> Executing: {endpoint} ------")
            thought = f"Fast Path (Confidence {prob_pct:.1f}%)"
            err = None
            used_fallback = False
        else:
            # 3. LLM Path (Top score < 85%) -> Send top 3 to LLM
            top_3_actions = legal_actions[:3]
            prob_pct = top_action["probability"] * 100 if top_action else 0
            print(f" [ LLM PATH] Close scores (Top score: {prob_pct:.1f}%) -> Sending {len(top_3_actions)} options to LLM")
            
            deck_hint = get_deck_hint(game_instance)
            llm_view = dict(ai_view)
            llm_view["legal_actions"] = top_3_actions # Send only top 3
            decision = query_llm(llm_view, deck_hint)
            err = decision.get("error")
            used_fallback = False

            if not err:
                print(f" [ LLM PATH] LLM Selected: {decision.get('endpoint', 'Unknown')}")
                thought = decision.get("final_decision_reasoning") or decision.get("turn_analysis") or "Thinking..."
                endpoint = decision.get("endpoint", "")
                payload = decision.get("payload", {})
                if isinstance(payload, dict) and "player_name" in payload:
                    payload["player_name"] = ai_name

        if err:
            print(f"[Goopy AI] LLM error: {err}. Trying scored fallback action.")
            fallback_action = _pick_best_fallback_action(legal_actions)
            if not fallback_action:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print("[Goopy AI] Consecutive failure cap reached (LLM errors). Forcing end turn.")
                    if is_my_turn_main and not game_instance.game_over:
                        game_instance.action_end_turn()
                    break
                continue
            endpoint = fallback_action.get("endpoint", "")
            payload = fallback_action.get("payload", {})
            if isinstance(payload, dict) and "player_name" in payload:
                payload["player_name"] = ai_name
            thought = f"โมเดลตอบไม่ทัน เลยใช้แผนสำรอง: {_describe_action(endpoint, payload)}"
            used_fallback = True
        else:
            pass  # endpoint/payload already set in FAST PATH or LLM PATH blocks above

        legal_endpoints = {a.get("endpoint") for a in legal_actions}
        if endpoint not in legal_endpoints:
            print(f"[Goopy AI] Illegal/unknown endpoint from model: {endpoint}. Using fallback action.")
            fallback_action = _pick_best_fallback_action(legal_actions)
            if fallback_action:
                endpoint = fallback_action.get("endpoint", "")
                payload = fallback_action.get("payload", {})
                if isinstance(payload, dict) and "player_name" in payload:
                    payload["player_name"] = ai_name
                used_fallback = True
            else:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print("[Goopy AI] Consecutive failure cap reached (hallucinated endpoints). Forcing end turn.")
                    if is_my_turn_main and not game_instance.game_over:
                        game_instance.action_end_turn()
                    break

        # Hard guard: supporter card can only be used once per turn.
        if endpoint == "/api/action/use_trainer":
            card_id = (payload or {}).get("card_id") if isinstance(payload, dict) else None
            my_state_now = ai_view.get("my_state", {}) if isinstance(ai_view, dict) else {}
            if _is_supporter_card_in_hand(my_state_now, card_id) and my_state_now.get("supporter_used_turn") == full_state.get("turn_number"):
                print("[Goopy AI] Hard rule: supporter already used this turn, switching to fallback action.")
                alt = _pick_best_fallback_action([a for a in legal_actions if a.get("endpoint") != "/api/action/use_trainer"])
                if alt:
                    endpoint = alt.get("endpoint", "")
                    payload = alt.get("payload", {})
                    if isinstance(payload, dict) and "player_name" in payload:
                        payload["player_name"] = ai_name
                    used_fallback = True

        planned_action_text = _describe_action(endpoint, payload)
        planned_thought = thought
        if used_fallback:
            planned_thought = f"แผนเดิมใช้ไม่ได้ เลยเปลี่ยนเป็น: {planned_action_text}"

        print(f"[Goopy AI] Action: {endpoint} | Planned Thought: {planned_thought}")

        # --- Execute the chosen action ---
        success = False
        msg = "Unknown endpoint"

        try:
            if endpoint == "/api/action/play_active":
                success, msg, _ = game_instance.action_play_active(ai_name, payload.get("card_id"))
            elif endpoint == "/api/action/play_bench":
                success, msg, _ = game_instance.action_play_bench(ai_name, payload.get("card_id"))
            elif endpoint == "/api/action/evolve":
                success, msg, _ = game_instance.action_evolve(ai_name, payload.get("evolution_card_id"), payload.get("target_position", "active"), payload.get("target_index", 0))
            elif endpoint == "/api/action/attach_energy":
                success, msg, _ = game_instance.action_attach_energy(ai_name, payload.get("target_position"), payload.get("target_index", 0))
            elif endpoint == "/api/action/use_trainer":
                success, msg, _ = game_instance.action_use_trainer(ai_name, payload.get("card_id"), payload.get("target_position", "active"), payload.get("target_index", 0), payload.get("opponent_switch_index"))
            elif endpoint == "/api/action/retreat":
                success, msg, _ = game_instance.action_retreat(ai_name, payload.get("bench_index", 0))
            elif endpoint == "/api/action/use_ability":
                success, msg, _ = game_instance.action_use_ability(ai_name, payload.get("pokemon_position", "active"), payload.get("pokemon_index", 0))
            elif endpoint == "/api/action/attack":
                success, msg, _ = game_instance.action_attack(ai_name, payload.get("attack_name"), payload.get("bench_target_index"), payload.get("self_bench_target_index"))
            elif endpoint == "/api/action/promote":
                success, msg, _ = game_instance.action_promote(ai_name, payload.get("bench_index", 0))
            elif endpoint == "/api/action/resolve_effect":
                success, msg, _ = game_instance.action_resolve_pending_effect(ai_name, payload.get("target_indexes", []))
            elif endpoint == "/api/action/end_turn":
                success, msg, _ = game_instance.action_end_turn()
                print(f"[Goopy AI] Turn ended: {msg}")
                break  # Turn explicitly ended — exit loop
            else:
                msg = f"Unknown endpoint: {endpoint}"
        except Exception as e:
            traceback.print_exc()
            msg = f"Exception: {e}"
            success = False

        print(f"[Goopy AI] Result: success={success} | {msg}")

        if success:
            game_instance.latest_ai_thought = planned_thought
            consecutive_failures = 0  # Reset on every successful action
            # TCG Rule: After a successful attack the turn ends immediately.
            # EXCEPTION: Some attacks (e.g. Inferno Dance) create a pending_effect that must
            # be resolved before the turn can end. In that case, continue the loop.
            if endpoint == "/api/action/attack":
                post_attack_state = game_instance.get_full_state()
                if (post_attack_state.get("pending_effect") and
                        post_attack_state.get("pending_effect", {}).get("player_name") == ai_name):
                    print("[Goopy AI] Attack created pending effect — continuing loop to resolve it.")
                    continue
                print("[Goopy AI] Attack executed — ending turn per TCG rules.")
                break
        else:
            game_instance.latest_ai_thought = f"ลองแล้วไม่สำเร็จ: {planned_action_text} ({msg})"
            consecutive_failures += 1
            print(f"[Goopy AI] Action failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}).")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("[Goopy AI] Consecutive failure cap reached. Forcing end turn.")
                if is_my_turn_main and not game_instance.game_over:
                    game_instance.action_end_turn()
                break



def _force_resolve(game_instance, ai_name: str, full_state: dict, legal_actions: list):
    """Emergency fallback: execute a productive legal action if possible."""
    if game_instance.game_over:
        return False, "game_over"
    if legal_actions:
        action_dict = _pick_best_fallback_action(legal_actions)
        if not action_dict:
            return False, "no_fallback_action"
        endpoint = action_dict["endpoint"]
        payload = action_dict["payload"]
        print(f"[Goopy AI] Force fallback → Action: {endpoint}")
        try:
            if endpoint == "/api/action/play_active":
                success, msg, _ = game_instance.action_play_active(ai_name, payload.get("card_id"))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/promote":
                success, msg, _ = game_instance.action_promote(ai_name, payload.get("bench_index", 0))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/resolve_effect":
                success, msg, _ = game_instance.action_resolve_pending_effect(ai_name, payload.get("target_indexes", []))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/play_bench":
                success, msg, _ = game_instance.action_play_bench(ai_name, payload.get("card_id"))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/attach_energy":
                success, msg, _ = game_instance.action_attach_energy(ai_name, payload.get("target_position"), payload.get("target_index", 0))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/evolve":
                success, msg, _ = game_instance.action_evolve(ai_name, payload.get("evolution_card_id"), payload.get("target_position", "active"), payload.get("target_index", 0))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/use_trainer":
                success, msg, _ = game_instance.action_use_trainer(ai_name, payload.get("card_id"), payload.get("target_position", "active"), payload.get("target_index", 0), payload.get("opponent_switch_index"))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/use_ability":
                success, msg, _ = game_instance.action_use_ability(ai_name, payload.get("pokemon_position", "active"), payload.get("pokemon_index", 0))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/retreat":
                success, msg, _ = game_instance.action_retreat(ai_name, payload.get("bench_index", 0))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/attack":
                success, msg, _ = game_instance.action_attack(ai_name, payload.get("attack_name"), payload.get("bench_target_index"), payload.get("self_bench_target_index"))
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
            elif endpoint == "/api/action/end_turn":
                success, msg, _ = game_instance.action_end_turn()
                print(f"[Goopy AI] Force fallback result: success={success} | {msg}")
                return success, msg
        except Exception as e:
            logger.error(f"Force fallback failed: {e}")
            return False, f"exception: {e}"

    return False, "no_legal_actions"

