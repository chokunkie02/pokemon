"""
convert_to_sft.py
=================
แปลง training_data_clean.jsonl เป็น SFT format สำหรับ Qwen 3B fine-tuning

- จัดการ Perspective Swapping: ให้ผู้เล่นที่กำลังจะ Take Action เป็น "YOUR SIDE" เสมอ
- แก้ไขข้อมูลที่ Player 2 เป็นคนเล่น แต่ State เป็น Player 1
"""

import json
import os

# ===== Load card lookup =====
CARDS_FILE = "cards.json"
cards_data = json.load(open(CARDS_FILE, encoding="utf-8"))
card_lookup = {c["id"]: c["name"] for c in cards_data}

def card_name(card_id):
    return card_lookup.get(card_id, card_id)

# ===== System Prompt =====
SYSTEM_PROMPT = """You are an expert Pokemon Trading Card Game (TCG) AI. 
You analyze the current game state and decide the best action to take.
Always respond with ONLY a valid JSON action object. Do not add any explanation.

Action types and their required fields:
- play_active: {"type": "play_active", "card_id": "...", "card_name": "..."}
- play_bench: {"type": "play_bench", "card_id": "...", "card_name": "..."}
- attach_energy: {"type": "attach_energy", "target_position": "active"|"bench", "target_index": 0}
- use_trainer: {"type": "use_trainer", "card_id": "...", "card_name": "...", "target_position": "active"|"bench", "target_index": 0}
- attack: {"type": "attack", "attack_name": "...", "bench_target_index": null}
- evolve: {"type": "evolve", "evolution_card_id": "...", "evolution_card_name": "...", "target_position": "active"|"bench", "target_index": 0}
- retreat: {"type": "retreat", "bench_index": 0}
- use_ability: {"type": "use_ability", "pokemon_position": "active"|"bench", "pokemon_index": 0}
- promote: {"type": "promote", "bench_index": 0}
- resolve_effect: {"type": "resolve_effect", "target_indexes": [...]}
- end_turn: {"type": "end_turn"}"""

# ===== State → Prompt =====
def format_pokemon(p):
    if p is None:
        return "None"
    energy_str = ", ".join(p.get("energy", [])) if p.get("energy") else "no energy"
    status_str = ", ".join(p.get("status", [])) if p.get("status") else "healthy"
    return f"{p['name']} (HP: {p['hp']}, Energy: [{energy_str}], Status: {status_str})"

def format_bench(bench_list):
    if not bench_list:
        return "  (empty)"
    lines = []
    for i, p in enumerate(bench_list):
        lines.append(f"  [{i}] {format_pokemon(p)}")
    return "\n".join(lines)

def state_to_prompt(state, actor_key="player_1"):
    """
    actor_key: "player_1" หรือ "player_2"
    แสดงฝั่ง actor เป็น YOUR SIDE เสมอ
    """
    p_acting = state[actor_key]
    p_opponent = state["player_2" if actor_key == "player_1" else "player_1"]
    
    turn = state.get("turn", "?")
    phase = state.get("phase", "?")
    setup = state.get("setup_phase", False)
    
    lines = []
    lines.append(f"=== Pokemon TCG Game State ===")
    lines.append(f"Turn: {turn} | Phase: {'Setup' if setup else phase.capitalize()}")
    lines.append("")

    # Actor info (จะกลายเป็น P1 เสมอในสายตา Model)
    lines.append(f"[YOUR SIDE - {p_acting['name']}]")
    lines.append(f"  Active: {format_pokemon(p_acting.get('active'))}")
    lines.append(f"  Bench:")
    lines.append(format_bench(p_acting.get("bench", [])))
    lines.append(f"  Hand: {', '.join(p_acting.get('hand', [])) if p_acting.get('hand') else '(empty)'}")
    lines.append(f"  Energy Zone: {p_acting.get('energy_zone', 0)} energy ready")
    lines.append(f"  Prize cards taken: {p_acting.get('prize_cards_taken', 0)}/3")
    lines.append("")

    # Opponent info
    lines.append(f"[OPPONENT - {p_opponent['name']}]")
    lines.append(f"  Active: {format_pokemon(p_opponent.get('active'))}")
    lines.append(f"  Bench:")
    lines.append(format_bench(p_opponent.get("bench", [])))
    
    hand_info = p_opponent.get("hand", [])
    if isinstance(hand_info, list) and hand_info:
        lines.append(f"  Known Hand: {', '.join(hand_info)} ({p_opponent.get('hand_size', '?')} cards)")
    else:
        lines.append(f"  Hand Size: {p_opponent.get('hand_size', '?')} cards (hidden)")
        
    lines.append(f"  Energy Zone: {p_opponent.get('energy_zone', 0)} energy ready")
    lines.append(f"  Prize cards taken: {p_opponent.get('prize_cards_taken', 0)}/3")
    lines.append("")
    lines.append(f"What is the best action to take?")

    return "\n".join(lines)

# ===== Action → Output =====
def action_to_output(action):
    """Clean action JSON (remove player metadata)"""
    clean_action = {k: v for k, v in action.items() if k not in ("player_name", "timestamp")}
    
    # เติมชื่อการ์ดให้ model จำง่าย
    if "card_id" in clean_action and "card_name" not in clean_action:
        clean_action["card_name"] = card_name(clean_action["card_id"])
    if "evolution_card_id" in clean_action and "evolution_card_name" not in clean_action:
        clean_action["evolution_card_name"] = card_name(clean_action["evolution_card_id"])
        
    return json.dumps(clean_action, ensure_ascii=False)

# ===== Main Loop =====
INPUT_FILE = "data/training_data_clean.jsonl"
OUTPUT_FILE = "data/sft_data.jsonl"

entries = []
with open(INPUT_FILE, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            try: entries.append(json.loads(line))
            except: pass

print(f"Loaded {len(entries)} entries")

sft_records = []
stats = {"p1": 0, "p2": 0}

for e in entries:
    state = e["state"]
    action = e["chosen_action"]
    
    p1_name = state["player_1"]["name"]
    p2_name = state["player_2"]["name"]
    action_player = action.get("player_name", "")
    
    # 1. ระบุว่าใครเป็นคนเล่น
    if action_player:
        actor_key = "player_1" if action_player == p1_name else "player_2"
    else:
        # ถ้าไม่มี player_name (เช่น end_turn) ให้ดูที่ Turn
        # Turn 1=P1, 2=P2, 3=P1...
        turn = state.get("turn", 1)
        actor_key = "player_1" if turn % 2 == 1 else "player_2"
    
    stats[actor_key.replace("layer_", "")] += 1

    # 2. สร้าง Prompt จากมุมมองของ Actor คนนั้น
    prompt = state_to_prompt(state, actor_key=actor_key)
    response = action_to_output(action)

    sft_records.append({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
            {"role": "assistant", "content": response}
        ]
    })

print(f"Perspective summary: P1={stats['p1']}, P2={stats['p2']}")
print(f"Saved {len(sft_records)} records to {OUTPUT_FILE}")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for r in sft_records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
