import json

# ตรวจสอบ sft_data.jsonl ว่า perspective ของ YOUR SIDE ตรงกับ acting player จริงไหม
# (เนื่องจากใน sft_data เราเอา player_name ออกไปแล้ว เราต้องตรวจจากเนื้อหา prompt เทียบกับ action)

mismatch = 0
total = 0

with open("sft_data.jsonl", encoding="utf-8") as f:
    for line in f:
        total += 1
        r = json.loads(line)
        user_msg = r["messages"][1]["content"]
        asst_msg = r["messages"][2]["content"]
        
        # ดึงชื่อ YOUR SIDE
        your_side = "?"
        for l in user_msg.split("\n"):
            if "[YOUR SIDE" in l:
                your_side = l.split("-")[1].strip().replace("]", "")
                break
        
        # ดึงชื่อการ์ดใน action (ถ้ามี)
        action = json.loads(asst_msg)
        card_name = action.get("card_name", "") or action.get("evolution_card_name", "")
        
        # ใน Log ดั้งเดิม:
        # Shogun (P1) ถือ Mewtwo/Gardevoir
        # Shogun (P2) ถือ Moltres/Charizard
        
        is_p1_state = "P2" not in your_side
        is_p2_state = "P2" in your_side
        
        # กฎคร่าวๆ: ถ้าเป็น P1 ต้องไม่เล่น Charizard/Moltres/Charmander
        p2_cards = ["Moltres", "Charizard", "Charmander", "Charmeleon"]
        is_p2_card = any(c in card_name for c in p2_cards)
        
        if is_p1_state and is_p2_card:
            mismatch += 1
            if mismatch < 5:
                print(f"Mismatch found: {your_side} playing {card_name}")
        elif is_p2_state and not is_p2_card and card_name and "Psychic" not in card_name:
             # กรณี P2 เล่นการ์ด P1 (Mewtwo etc)
             if any(c in card_name for c in ["Mewtwo", "Gardevoir", "Ralts", "Kirlia"]):
                 mismatch += 1
                 if mismatch < 5:
                     print(f"Mismatch found: {your_side} playing {card_name}")

print(f"\nChecked {total} records")
print(f"Suspected mismatches: {mismatch}")
if mismatch == 0:
    print("✅ PERSPECTIVE LOOKS CORRECT!")
else:
    print("❌ STILL HAVE PERSPECTIVE ISSUES!")
