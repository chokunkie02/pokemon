from game_manager import CardDatabase, GameState
from training_logger import logger
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db = CardDatabase(
    cards_file=os.path.join(BASE_DIR, "cards.json"),
    decks_file=os.path.join(BASE_DIR, "decks.json"),
)
game = GameState("Shogun (P1)", "D01_FIRE", "Shogun (P2)", "D02_PSYCHIC", db)

# Get full state
state = game.get_full_state_dict("Shogun (P1)") if hasattr(game, 'get_full_state_dict') else game.get_full_state()

# Prune it to see the output
pruned = logger._prune_state(state)
import json
print(json.dumps(pruned, indent=2, ensure_ascii=False))
