from game_manager import CardDatabase, GameState

def test():
    db = CardDatabase()
    g = GameState("P1", "D01_FIRE", "P2", "D02_PSYCHIC", db)
    
    # Wait until hands have basic pokemon
    while not g.p1.get_basic_pokemon_in_hand():
        g.p1.check_and_mulligan()
    while not g.p2.get_basic_pokemon_in_hand():
        g.p2.check_and_mulligan()

    p1_basic = g.p1.get_basic_pokemon_in_hand()[0]
    p2_basic = g.p2.get_basic_pokemon_in_hand()[0]

    # Setup phase
    print("P1 active:", g.action_play_active("P1", p1_basic))
    print("P2 active:", g.action_play_active("P2", p2_basic))
    
    print("Setup phase:", g.setup_phase)
    
    # Give P1 another basic pokemon
    p1_basic_2 = None
    for cid in g.p1.hand:
        card = g.db.get_card(cid)
        if card["category"] == "pokemon" and card["stage"] == "basic":
            p1_basic_2 = cid
            break
            
    if not p1_basic_2:
        # Just give them one
        p1_basic_2 = "A1_004"
        g.p1.hand.append(p1_basic_2)

    # Play bench
    print("P1 bench:", g.action_play_bench("P1", p1_basic_2))
    
    print("Game over:", g.game_over)
    print("Winner:", g.winner)

test()
