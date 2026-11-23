"""
fix_turns.py
============
สคริปต์ซ่อม turn number ใน training_data.jsonl

Logic:
- ทุกบรรทัดใน log ปัจจุบันมี "turn": 0 (bug เก่า)
- บรรทัดที่ turn != 0 คือ log ใหม่ที่ถูกต้องแล้ว (ไม่แตะ)
- สำหรับบรรทัดที่ turn == 0:
  * เกมใหม่เริ่มเมื่อ setup_phase=True และ active ของทั้งสองฝ่ายเป็น null
    (หรือมีช่องว่างเวลา > 60 วินาที ก็ถือว่าเกมใหม่)
  * turn เริ่มที่ 1 (เพราะเทิร์นจริงในเกมเริ่มนับตั้งแต่ 1)
  * ทุกครั้งที่เจอ action "end_turn" -> turn += 1 (สำหรับบรรทัดถัดไป)
  * หมายเหตุ: turn จะเพิ่มหลัง end_turn เพราะ state ใน log คือ state ก่อน action
"""

import json
import shutil
from datetime import datetime

INPUT_FILE = "training_data.jsonl"
OUTPUT_FILE = "training_data_fixed.jsonl"
BACKUP_FILE = "training_data_backup.jsonl"

# วิธีตรวจว่าเป็นเกมใหม่
def is_new_game(entry, prev_entry):
    state = entry["state"]
    # ถ้า setup_phase=True และ active ทั้งสองฝ่ายเป็น null → เริ่มต้นเกมจริงๆ
    if state.get("setup_phase") and state["player_1"]["active"] is None and state["player_2"]["active"] is None:
        return True
    # ถ้าช่องว่างเวลา > 60 วินาที → ถือว่าเกมใหม่ (คนกดเริ่มใหม่)
    if prev_entry:
        try:
            t1 = datetime.fromisoformat(prev_entry["timestamp"])
            t2 = datetime.fromisoformat(entry["timestamp"])
            if (t2 - t1).total_seconds() > 60:
                return True
        except:
            pass
    return False

def fix_turns():
    # Backup ก่อน
    shutil.copy(INPUT_FILE, BACKUP_FILE)
    print(f"Backed up to {BACKUP_FILE}")

    entries = []
    with open(INPUT_FILE, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [SKIP] Line {line_num}: JSON error: {e}")

    print(f"Loaded {len(entries)} entries")

    fixed = []
    current_turn = 1
    game_count = 0
    prev_entry = None

    for i, entry in enumerate(entries):
        original_turn = entry["state"].get("turn", 0)

        # ถ้า turn ถูกต้องแล้ว (> 0) → ไม่แตะ
        if original_turn > 0:
            fixed.append(entry)
            # อัพเดต current_turn ให้ sync กับค่าจริง
            current_turn = original_turn
            # ถ้า action นี้คือ end_turn → turn ถัดไปเพิ่ม
            if entry["chosen_action"].get("type") == "end_turn":
                current_turn += 1
            prev_entry = entry
            continue

        # กรณี turn == 0 (bug เก่า) → ซ่อม
        if is_new_game(entry, prev_entry):
            current_turn = 1
            game_count += 1
            print(f"  [GAME {game_count}] Detected at entry {i+1}, ts={entry['timestamp'][:19]}")

        # กำหนด turn ให้ entry นี้
        entry["state"]["turn"] = current_turn

        # ถ้า action คือ end_turn → เพิ่ม turn สำหรับ entry ถัดไป
        if entry["chosen_action"].get("type") == "end_turn":
            current_turn += 1

        fixed.append(entry)
        prev_entry = entry

    # เขียน output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for entry in fixed:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nDone! Written {len(fixed)} entries to {OUTPUT_FILE}")
    print(f"Total games detected: {game_count}")

    # แสดงตัวอย่าง turn distribution
    from collections import Counter
    turn_dist = Counter(e["state"]["turn"] for e in fixed)
    print(f"\nTurn distribution (sample):")
    for t in sorted(turn_dist.keys())[:15]:
        print(f"  turn {t:3d}: {turn_dist[t]} actions")
    if max(turn_dist.keys()) > 15:
        print(f"  ... up to turn {max(turn_dist.keys())}")

    # ถามว่าจะ overwrite ไฟล์เดิมไหม
    ans = input("\nReplace original training_data.jsonl with fixed version? (y/n): ")
    if ans.lower() == "y":
        shutil.copy(OUTPUT_FILE, INPUT_FILE)
        print("Replaced! Original backed up at training_data_backup.jsonl")
    else:
        print(f"Kept original. Fixed version saved at {OUTPUT_FILE}")

if __name__ == "__main__":
    fix_turns()
