import json
from game_manager import CardDatabase, GameState

def test_abilities_and_attacks():
    db = CardDatabase()
    g = GameState('P1', 'D01_FIRE', 'P2', 'D01_FIRE', db)

    results = []

    # 1. Setup Phase
    g.p1.hand.append('A1_004') # Charmander P1
    g.action_play_active('P1', 'A1_004')

    g.p2.hand.append('A1_004') # Charmander P2
    g.action_play_active('P2', 'A1_004')
    
    # Add some bench support for testing effects
    g.p1.hand.append('A1_004')
    g.action_play_bench('P1', 'A1_004')
    g.p2.hand.append('A1_004')
    g.action_play_bench('P2', 'A1_004')

    if g.setup_phase:
        results.append("Error: Setup phase did not end properly.")
        return results

    # Wait for Turn 3 so we can evolve
    g.action_end_turn() # End P1
    g.action_end_turn() # End P2

    # --- P1 Turn 3 ---
    # Give energy zone
    g.p1.energy_zone = 5
    
    # Evolve Active to Charizard (for Fire Spin test later)
    g.p1.hand.extend(['A1_005', 'A1_002']) # Charmeleon, Charizard
    g.action_evolve('P1', 'A1_005', 'active', 0)
    g.action_end_turn() # P1 turn ends
    g.action_end_turn() # P2 turn ends

    # --- P1 Turn 5 ---
    # Give Charmeleon time to be ready for next evolution
    g.action_evolve('P1', 'A1_002', 'active', 0)
    g.action_end_turn() # P1 turn ends
    g.action_end_turn() # P2 turn ends

    # --- P1 Turn 7 ---
    # 2. Test Ability: Gardevoir's Psy Shadow
    g.p1.hand.extend(['A1_011', 'A1_008', 'A1_007']) # Ralts, Kirlia, Gardevoir
    g.action_play_bench('P1', 'A1_011') # bench_index 1
    g.action_end_turn()
    g.action_end_turn()
    g.action_evolve('P1', 'A1_008', 'bench', 1)
    g.action_end_turn()
    g.action_end_turn()
    g.action_evolve('P1', 'A1_007', 'bench', 1)
    
    # Use Psy Shadow!
    g.p1.energy_zone = 1
    a1_success, a1_msg, a1_res = g.action_use_ability('P1', 'bench', 1)
    results.append(f"Psy Shadow Test: success={a1_success}, msg={a1_msg}")
    
    # Test Trainer Card: X Speed
    g.p1.hand.append('T01_007') # X Speed
    t1_success, t1_msg, _ = g.action_use_trainer('P1', 'T01_007')
    results.append(f"X Speed Test: success={t1_success}, cost reduction count={g.p1.retreat_cost_reduction}")

    # Test Attack Effect: Fire Spin (Discard 2 Energy)
    g.p1.active_pokemon['attached_energy'] = ['fire', 'fire', 'psychic', 'lightning']
    atk_card = g.db.get_card(g.p1.active_pokemon['card_id'])
    results.append(f"Card: {atk_card['name']}, Attacks: {[a['name'] for a in atk_card['attacks']]}")
    
    atk_success, atk_msg, atk_res = g.action_attack('P1', 'Fire Spin')
    results.append(f"Fire Spin Test: msg={atk_msg}, leftover energy={len(g.p1.active_pokemon['attached_energy'])}")
    
    if g.current_turn == 'P2':
        results.append("Auto Switch Turn logic works after Fire Spin attack!")

    with open('test_skills.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    test_abilities_and_attacks()
