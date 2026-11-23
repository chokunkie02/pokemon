import sys
import json
from pathlib import Path

# Add backend directory to sys.path so we can import modules
backend_dir = Path("c:/pokemon/backend").resolve()
sys.path.append(str(backend_dir))

from game_manager import CardDatabase, GameState
from ai_agent import parse_state_for_ai, build_system_prompt

def run_test():
    print("Initializing Database...")
    db = CardDatabase(
        cards_file=str(backend_dir / "cards.json"),
        decks_file=str(backend_dir / "decks.json"),
    )

    print("Creating GameState...")
    game = GameState("Shogun", "D01_FIRE", "Goopy AI", "D02_PSYCHIC", db)
    
    full_state = game.get_full_state()
    
    print("\nParsing State for AI...")
    ai_view = parse_state_for_ai(full_state, "Goopy AI")
    
    print("\n--- AI View ---")
    print(json.dumps(ai_view, indent=2, ensure_ascii=False))
    
    print("\n--- Legal Actions Output ---")
    actions = ai_view.get("legal_actions", [])
    for action in actions:
        print(f" - {action}")
        
    print("\n--- System Prompt ---")
    prompt = build_system_prompt()
    print(prompt[:300] + "...\n(Truncated)")

if __name__ == "__main__":
    run_test()
