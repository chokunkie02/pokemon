import requests

try:
    res = requests.post("http://localhost:8000/api/new_game", json={
        "player1_name": "Shogun (P1)",
        "player1_deck": "D01_FIRE",
        "player2_name": "Shogun (P2)",
        "player2_deck": "D02_PSYCHIC"
    })
    print(res.status_code)
    
    res = requests.post("http://localhost:8000/api/action/play_active", json={
        "player_name": "Shogun (P1)",
        "card_id": "pkmn-001" # dummy
    })
    print(res.status_code)
except Exception as e:
    print(e)
