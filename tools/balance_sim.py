"""Headless deck-vs-deck balance simulator.

Plays full games with game_manager.GameState only — it does NOT use ai_agent or the LLM.
Both sides use the same simple greedy policy, so results measure the decks under equal play,
not optimal play.

    python tools/balance_sim.py            # 300 games per matchup
    python tools/balance_sim.py 1000
"""
import contextlib
import io
import itertools
import json
import os
import random
import sys
from collections import Counter, defaultdict

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
from game_manager import CardDatabase, GameState  # noqa: E402

DB = CardDatabase()
CARDS = {c["id"]: c for c in json.load(open("cards.json", encoding="utf-8"))}
MAX_ACTIONS = 4000


def me_of(s, name):
    return s["player_1"] if s["player_1"]["name"] == name else s["player_2"]


def attack_score(atk, me):
    calc = atk.get("effect_calculation") or ""
    dmg = atk.get("damage", 0)
    if calc == "damage_multiplied_by_benched_count":
        dmg = dmg * len(me["bench"])
    elif calc == "damage_multiplied_by_heads_50":
        dmg = 50 * 1.5
    elif calc == "coin_flip_3_attach_fire_energy_from_zone":
        dmg = 25
    elif calc == "damage_to_opponent_pokemon_30":
        dmg = 30
    return dmg


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def play_turn(g, name):
    s = g.get_full_state()
    me = me_of(s, name)
    opp = me_of(s, [p for p in (s["player_1"]["name"], s["player_2"]["name"]) if p != name][0])

    # 1) trainers that help immediately
    for c in list(me["hand_details"]):
        calc = c.get("trainer_effect_calculation")
        if calc in ("draw_2_cards", "search_random_basic_pokemon_to_hand"):
            quiet(g.action_use_trainer, name, c["id"])
        elif calc == "heal_20_from_target" and me["active_pokemon"] and \
                me["active_pokemon"]["max_hp"] - me["active_pokemon"]["current_hp"] >= 20:
            quiet(g.action_use_trainer, name, c["id"], "active", 0)
        elif calc == "opponent_shuffle_hand_draw_3" and len(opp["hand"]) >= 5:
            quiet(g.action_use_trainer, name, c["id"])
    me = me_of(g.get_full_state(), name)

    # 2) basics to bench
    for c in list(me["hand_details"]):
        if c["category"] == "pokemon" and c["stage"] == "basic" and len(me_of(g.get_full_state(), name)["bench"]) < 3:
            quiet(g.action_play_bench, name, c["id"])

    # 3) evolve wherever possible
    me = me_of(g.get_full_state(), name)
    for c in list(me["hand_details"]):
        if c["category"] != "pokemon" or c["stage"] == "basic":
            continue
        s = g.get_full_state(); me = me_of(s, name)
        if me["active_pokemon"] and me["active_pokemon"]["name"] == c["evolves_from"]:
            if quiet(g.action_evolve, name, c["id"], "active", 0)[0]:
                continue
        for i, b in enumerate(me["bench"]):
            if b["name"] == c["evolves_from"] and quiet(g.action_evolve, name, c["id"], "bench", i)[0]:
                break

    # 4) abilities (e.g. Psy Shadow)
    s = g.get_full_state(); me = me_of(s, name)
    if me.get("active_ability") and me["active_ability"].get("can_use"):
        quiet(g.action_use_ability, name, "active", 0)
    for ab in me.get("bench_abilities") or []:
        if ab.get("can_use"):
            quiet(g.action_use_ability, name, "bench", ab["index"])

    # 5) energy: active until its best attack is usable, else the strongest bench mon
    s = g.get_full_state(); me = me_of(s, name)
    if me["energy_zone"] > 0 and me["active_pokemon"]:
        atks = me.get("active_attacks") or []
        best = max(atks, key=lambda a: attack_score(a, me)) if atks else None
        if best is None or not best["can_use"] or not me["bench"]:
            quiet(g.action_attach_energy, name, "active", 0)
        else:
            idx = max(range(len(me["bench"])), key=lambda i: me["bench"][i]["max_hp"])
            quiet(g.action_attach_energy, name, "bench", idx)

    # 6) attack with the best usable attack (Giovanni first if we have it)
    s = g.get_full_state(); me = me_of(s, name)
    usable = [a for a in (me.get("active_attacks") or []) if a["can_use"]]
    if usable:
        for c in me["hand_details"]:
            if c.get("trainer_effect_calculation") == "attack_damage_boost_10_this_turn":
                quiet(g.action_use_trainer, name, c["id"])
                break
        usable.sort(key=lambda a: attack_score(a, me), reverse=True)
        for a in usable:
            ok = quiet(g.action_attack, name, a["name"], bench_target_index=0,
                       self_bench_target_index=0 if me["bench"] else None)[0]
            if ok:
                return
    quiet(g.action_end_turn)


def play_game(d1, d2, stats):
    g = quiet(GameState, "A", d1, "B", d2, DB)
    deck_of = {"A": d1, "B": d2}
    prev_points = {"A": 0, "B": 0}
    for _ in range(MAX_ACTIONS):
        s = g.get_full_state()
        if s["game_over"]:
            break
        acted = False
        for p in (s["player_1"], s["player_2"]):
            if p["pending_promote"] and p["bench"]:
                idx = max(range(len(p["bench"])), key=lambda i: p["bench"][i]["current_hp"])
                quiet(g.action_promote, p["name"], idx); acted = True; break
        if acted:
            continue
        if s.get("pending_effect"):
            pe = s["pending_effect"]
            idxs = (pe.get("available_bench_indexes") or [])[: pe.get("selection_count", 0)]
            quiet(g.action_resolve_pending_effect, pe["player_name"], idxs)
            continue
        if s["setup_phase"]:
            for n in s.get("pending_initial_active") or []:
                me = me_of(s, n)
                basics = [c for c in me["hand_details"] if c["category"] == "pokemon" and c["stage"] == "basic"]
                basics.sort(key=lambda c: c["hp"] or 0, reverse=True)
                if basics:
                    quiet(g.action_play_active, n, basics[0]["id"])
            continue
        cur = s["current_turn"]
        before = {p["name"]: p["points"] for p in (s["player_1"], s["player_2"])}
        attacker = me_of(s, cur)["active_pokemon"]
        play_turn(g, cur)
        after_s = g.get_full_state()
        for p in (after_s["player_1"], after_s["player_2"]):
            gained = p["points"] - before[p["name"]]
            if gained > 0 and p["name"] == cur and attacker:
                stats["prizes_by_card"][attacker["name"]] += gained
        if after_s["turn_number"] > 80:
            break
    s = g.get_full_state()
    w = s.get("winner")
    return (w if w in deck_of else None), s["turn_number"], s.get("first_player")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    random.seed(7)
    decks = [d["deck_id"] for d in json.load(open("decks.json", encoding="utf-8"))]
    stats = {"prizes_by_card": Counter()}
    table = defaultdict(dict)
    turns = defaultdict(list)
    first_wins = Counter(); first_total = 0
    for d1, d2 in itertools.product(decks, repeat=2):
        wins = 0; draws = 0
        for _ in range(n):
            w, t, first = play_game(d1, d2, stats)
            turns[(d1, d2)].append(t)
            if w is None:
                draws += 1
            elif w == "A":
                wins += 1
            if w is not None:
                first_total += 1
                if w == first:
                    first_wins["first"] += 1
        table[d1][d2] = (wins, draws)
    print(f"\nWin rate of ROW deck vs COLUMN deck ({n} games each, draws/timeouts in brackets)\n")
    print(" " * 14 + "".join(f"{d:>16}" for d in decks))
    for d1 in decks:
        row = "".join(f"{table[d1][d2][0] / n:>12.0%} ({table[d1][d2][1]:>2})" for d2 in decks)
        print(f"{d1:>14}{row}")
    print("\nAverage game length (turns):")
    for k, v in turns.items():
        print(f"  {k[0]} vs {k[1]}: {sum(v) / len(v):.1f}")
    if first_total:
        print(f"\nGoing-first win rate: {first_wins['first'] / first_total:.0%}")
    print("\nPrize points taken, by attacking card:")
    for name, c in stats["prizes_by_card"].most_common():
        print(f"  {name:<16} {c}")


if __name__ == "__main__":
    main()
