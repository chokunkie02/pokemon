import requests
import traceback
import sys

try:
    print("New Game")
    res = requests.post("http://localhost:8000/api/new_game", json={
        "player1_name": "Shogun",
        "player1_deck": "D01_FIRE",
        "player2_name": "Goopy AI",
        "player2_deck": "D02_PSYCHIC"
    })
    
    state = res.json()["state"]
    p1 = state["player_1"]
    active_basic = None
    for card in p1.get("hand_details", []):
      if card.get("category") == "pokemon" and card.get("stage") == "basic":
        active_basic = card["id"]
        break

    print(f"P1 Action: play_active with {active_basic}")
    res = requests.post("http://localhost:8000/api/action/play_active", json={
        "player_name": "Shogun",
        "card_id": active_basic
    })
    print(res.status_code)
    print(res.json())
except Exception as e:
    traceback.print_exc()

