import json
import requests

# Check current lines in log
lines = open('training_data.jsonl', encoding='utf-8').readlines()
print(f"Total lines in log: {len(lines)}")

last = json.loads(lines[-1])
print(f"Last timestamp: {last['timestamp']}")
print(f"Last action: {last['chosen_action']}")

# Check current game state
r = requests.get('http://localhost:8000/api/state')
s = r.json()
print(f"\nGame state:")
print(f"  game_over: {s.get('game_over')}")
print(f"  turn_number: {s.get('turn_number')}")
print(f"  phase: {s.get('phase')}")
print(f"  current_turn: {s.get('current_turn')}")

# Try calling end_turn to trigger a log write
r2 = requests.get('http://localhost:8000/api/state')
print(f"\nBackend responded {r2.status_code}")

# Try a dummy log directly
from training_logger import logger
state = r2.json()
logger.log_action(state, {"type": "test_manual_log"})
print("Manual log written! Check last line of training_data.jsonl now.")

lines2 = open('training_data.jsonl', encoding='utf-8').readlines()
print(f"Total lines AFTER manual write: {len(lines2)}")
last2 = json.loads(lines2[-1])
print(f"Last action: {last2['chosen_action']}")
