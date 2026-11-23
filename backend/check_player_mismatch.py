import json
from collections import Counter

# เช็คจาก training_data_clean.jsonl ก่อน strip
mismatch = 0
match_p1 = 0
match_p2 = 0
no_player = 0

with open("training_data_clean.jsonl", encoding="utf-8") as f:
    for i, line in enumerate(f):
        e = json.loads(line)
        p1_name = e["state"]["player_1"]["name"]
        p2_name = e["state"]["player_2"]["name"]
        action_by = e["chosen_action"].get("player_name", "")
        
        if not action_by:
            no_player += 1
        elif action_by == p1_name:
            match_p1 += 1
        elif action_by == p2_name:
            match_p2 += 1
        else:
            mismatch += 1

total = match_p1 + match_p2 + no_player + mismatch
print(f"Total records: {total}")
print(f"P1 actions (correct perspective): {match_p1} ({match_p1/total*100:.1f}%)")
print(f"P2 actions (MISMATCHED perspective): {match_p2} ({match_p2/total*100:.1f}%)")
print(f"No player_name (end_turn etc.): {no_player} ({no_player/total*100:.1f}%)")
print(f"Unknown: {mismatch}")
