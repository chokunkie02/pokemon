import json

with open("sft_data.jsonl", encoding="utf-8") as f:
    for i, line in enumerate(f):
        r = json.loads(line)
        user_msg = r["messages"][1]["content"]
        asst_msg = r["messages"][2]["content"]
        
        your_side = ""
        for l in user_msg.split("\n"):
            if "[YOUR SIDE" in l:
                your_side = l
                break
        
        action = json.loads(asst_msg)
        card_name = action.get("card_name", "") or action.get("evolution_card_name", "")
        
        # Look for the mismatch: Shogun (P2) playing Mewtwo ex
        if "Shogun (P2)" in your_side and "Mewtwo ex" in card_name:
            print(f"--- RECORD {i+1} ---")
            print(user_msg)
            print(f"ACTION: {asst_msg}")
            break
