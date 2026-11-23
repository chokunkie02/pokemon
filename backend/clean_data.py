import json
from collections import Counter
import shutil

INPUT_FILE = "data/training_data.jsonl"
OUTPUT_FILE = "data/training_data_clean.jsonl"

entries = []
for line in open(INPUT_FILE, encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    try:
        entries.append(json.loads(line))
    except:
        pass

print(f"Original entries: {len(entries)}")
print()

removed_counts = {"test_entry": 0, "vs_ai": 0, "duplicate_ts": 0}
clean = []
seen_timestamps = set()

for i, e in enumerate(entries):
    action_type = e["chosen_action"].get("type", "")
    state = e["state"]
    p1_name = state["player_1"]["name"]
    p2_name = state["player_2"]["name"]
    ts = e.get("timestamp", "")

    # 1. ลบ test/debug entries
    if action_type in ("test_manual_log",):
        removed_counts["test_entry"] += 1
        continue

    # 2. ลบ game ที่เล่นกับ Goopy AI
    if "Goopy AI" in p2_name or "Goopy AI" in p1_name:
        removed_counts["vs_ai"] += 1
        continue

    # 3. ลบ duplicate โดยใช้ timestamp (เชื่อถือได้ที่สุด)
    if ts in seen_timestamps:
        removed_counts["duplicate_ts"] += 1
        continue
    seen_timestamps.add(ts)

    clean.append(e)

print(f"Removed breakdown:")
print(f"  test/debug entries  : {removed_counts['test_entry']}")
print(f"  vs Goopy AI games   : {removed_counts['vs_ai']}")
print(f"  duplicate timestamp : {removed_counts['duplicate_ts']}")
print(f"\nClean entries: {len(clean)}")

# สถิติหลัง clean
actions = Counter(e["chosen_action"]["type"] for e in clean)
print(f"\nAction types after clean:")
for a, c in actions.most_common():
    print(f"  {a:20s}: {c}")

# Count games
game_count = 0
prev_ts = None
for e in clean:
    s = e["state"]
    if s.get("setup_phase") and s["player_1"]["active"] is None and s["player_2"]["active"] is None:
        game_count += 1

print(f"\nTotal games: {game_count}")

turns = Counter(e["state"]["turn"] for e in clean)
print(f"\nTurn distribution:")
for t in sorted(turns.keys())[:20]:
    bar = "#" * (turns[t] // 5)
    print(f"  turn {t:3d}: {turns[t]:4d}  {bar}")

# เขียน output
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for e in clean:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print(f"\nDone! Saved {len(clean)} clean entries to {OUTPUT_FILE}")
