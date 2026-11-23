import json
from game_manager import CardDatabase, GameState

def run_test():
    db = CardDatabase()
    g = GameState('P1', 'D01_FIRE', 'P2', 'D01_FIRE', db)

    g.p1.hand.append('A1_004') # Charmander
    g.action_play_active('P1', 'A1_004')

    g.p2.hand.append('A1_004') # Charmander
    g.action_play_active('P2', 'A1_004')

    g.p1.hand.append('A1_005') # Charmeleon
    e1 = g.action_evolve('P1', 'A1_005', 'active', 0)
    
    g.action_end_turn()

    g.p2.hand.append('A1_005') # Charmeleon
    e2 = g.action_evolve('P2', 'A1_005', 'active', 0)
    
    g.action_end_turn()

    e3 = g.action_evolve('P1', 'A1_005', 'active', 0)

    res = {
      'e1 (turn1 p1)': e1,
      'e2 (turn2 p2)': e2,
      'e3 (turn3 p1)': e3,
    }
    with open('debug_evolve.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    run_test()
