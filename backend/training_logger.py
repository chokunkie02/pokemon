import json
import os
from datetime import datetime

class BehavioralLogger:
    def __init__(self, log_file="training_data.jsonl"):
        # Put it in the backend folder or project root
        self.log_file = os.path.join(os.path.dirname(__file__), log_file)

    def _prune_state(self, game_state):
        """
        Extract Imperfect Information & Context
        """
        p = game_state.get('player_1', {})
        o = game_state.get('player_2', {})
        
        # We need to know who is who based on current_turn, but action can be from any player.
        # Wait, the game_manager.get_full_state() returns player_1 and player_2, not player/opponent relative to the actor.
        # We should adjust it based on the action's player_name if possible, but let's just log the raw full state and we can process it later,
        # OR we can identify who is acting.
        
        # Let's just store the whole state but pruned. 
        # The script later will figure out who was acting based on current_turn or the action payload.

        return {
            "turn": game_state.get("turn_number", 0),
            "phase": game_state.get("phase", ""),
            "setup_phase": game_state.get("setup_phase", False),
            
            "player_1": {
                "name": p.get("name"),
                "deck": p.get("deck_id", "unknown_deck"),
                "prize_cards_taken": p.get("points", 0),
                "active": self._prune_pokemon(p.get("active_pokemon")),
                "bench": [self._prune_pokemon(b) for b in p.get("bench", [])],
                "hand": [card.get('name') for card in p.get("hand_details", [])] if p.get("hand_details") else [],
                "energy_zone": p.get("energy_zone", 0),
                "retreat_cost_reduction": p.get("retreat_cost_reduction", 0),
                "attack_damage_bonus": p.get("attack_damage_bonus", 0),
            },
            
            "player_2": {
                "name": o.get("name"),
                "deck": o.get("deck_id", "unknown_deck"),
                "prize_cards_taken": o.get("points", 0),
                "active": self._prune_pokemon(o.get("active_pokemon")),
                "bench": [self._prune_pokemon(b) for b in o.get("bench", [])],
                "hand_size": len(o.get("hand", [])), # Store size, but we might want hand_details if we control both for BC
                "hand": [card.get('name') for card in o.get("hand_details", [])] if o.get("hand_details") else [],
                "energy_zone": o.get("energy_zone", 0),
                "retreat_cost_reduction": o.get("retreat_cost_reduction", 0),
                "attack_damage_bonus": o.get("attack_damage_bonus", 0),
            },
            
            "legal_actions": game_state.get("legal_actions", [])
        }

    def _prune_pokemon(self, pkmn):
        if not pkmn: return None
        return {
            "name": pkmn.get("name"),
            "hp": f"{pkmn.get('current_hp')}/{pkmn.get('max_hp')}",
            "energy": pkmn.get("attached_energy", []), 
            "status": pkmn.get("special_conditions", [])
        }

    def log_action(self, raw_state, chosen_action_dict):
        """
        Background Task for logging
        """
        try:
            pruned_state = self._prune_state(raw_state)
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "state": pruned_state,
                "chosen_action": chosen_action_dict
            }
            
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Logger Error] Background logging failed: {e}")

# Global Instance
logger = BehavioralLogger()

