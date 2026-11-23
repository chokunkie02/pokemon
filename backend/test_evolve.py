from game_manager import CardDatabase, GameState

def test():
    db = CardDatabase()
    g = GameState("P1", "D01_FIRE", "P2", "D01_FIRE", db)

    # Force Charmander to P1's hand
    g.p1.hand.append("A1_004") # Charmander
    
    # Setup phase
    print("Setup P1:", g.action_play_active("P1", "A1_004"))

    # Force P2 to play something
    g.p2.hand.append("A1_004")
    g.action_play_active("P2", "A1_004")

    print(f"Game setup done? {not g.setup_phase}")
    print(f"Turn {g.turn_number}, Current player: {g.current_turn}")
    
    # Give P1 Charmeleon
    g.p1.hand.append("A1_005")

    # Try to evolve Charmander immediately on Turn 1
    success, msg, _ = g.action_evolve("P1", "A1_005", "active", 0)
    print(f"Evolve Turn 1 (P1): success={success}, msg={msg}")

    # End turn 1
    g.action_end_turn()

    # Turn 2 (P2's turn)
    print(f"\nTurn {g.turn_number}, Current player: {g.current_turn}")
    g.p2.hand.append("A1_005") # Charmeleon for P2
    # Try to evolve Charmander on Turn 2 (P2's first turn)
    success, msg, _ = g.action_evolve("P2", "A1_005", "active", 0)
    print(f"Evolve Turn 2 (P2): success={success}, msg={msg}")
    
    # End turn 2
    g.action_end_turn()

    # Turn 3 (P1's turn)
    print(f"\nTurn {g.turn_number}, Current player: {g.current_turn}")
    success, msg, _ = g.action_evolve("P1", "A1_005", "active", 0)
    print(f"Evolve Turn 3 (P1): success={success}, msg={msg}")

test()
