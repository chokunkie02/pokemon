from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, Any

from game_manager import CardDatabase, GameState
from ai_agent import execute_ai_turn
from training_logger import logger


app = FastAPI(title="Pokemon TCG Pocket AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).resolve().parent
db = CardDatabase(
    cards_file=str(BASE_DIR / "cards.json"),
    decks_file=str(BASE_DIR / "decks.json"),
)
game: GameState | None = None


def get_game():
    if game is None:
        raise HTTPException(status_code=400, detail="ยังไม่มีเกม ต้องสร้างเกมก่อน")
    return game


def trigger_ai_if_needed(background_tasks: BackgroundTasks):
    """
    Checks if it's Goopy AI's turn or if Goopy AI needs to perform a mandatory action 
    (like initial active selection, bench placement in setup, or promotion). 
    If so, queues the AI execution.
    """
    g = get_game()
    if g is None or g.game_over:
        return
        
    ai_name = "Goopy AI"
    full_state = g.get_full_state()
    
    act_needed = False
    
    # Check pending initial active
    if full_state.get("setup_phase") and ai_name in full_state.get("pending_initial_active", []):
         act_needed = True
    # Check setup bench: AI has placed its active but setup is still ongoing
    # (the human just placed their active — AI should now place bench pokemon)
    elif full_state.get("setup_phase") and ai_name not in full_state.get("pending_initial_active", []):
        # AI already picked active; check if it has basic pokemon left in hand to bench
        p1 = full_state.get("player_1", {})
        p2 = full_state.get("player_2", {})
        ai_player = p1 if p1.get("name") == ai_name else p2
        if (ai_player.get("active_pokemon") is not None and 
            len(ai_player.get("bench", [])) < 3):
            # Check if the AI player has any basic pokemon in hand still
            hand_details = ai_player.get("hand_details", [])
            has_basic = any(c.get("category") == "pokemon" and c.get("stage") == "basic" for c in hand_details)
            if has_basic:
                act_needed = True
    # Check main turn
    elif full_state.get("current_turn") == ai_name and full_state.get("phase") == "main":
         act_needed = True
    # Check pending promote
    elif full_state.get("player_1", {}).get("name") == ai_name and full_state.get("player_1", {}).get("pending_promote"):
         act_needed = True
    elif full_state.get("player_2", {}).get("name") == ai_name and full_state.get("player_2", {}).get("pending_promote"):
         act_needed = True
    # Check pending effect
    elif full_state.get("pending_effect") and full_state.get("pending_effect").get("player_name") == ai_name:
         act_needed = True
         
    if act_needed:
        background_tasks.add_task(execute_ai_turn, g)



# ==========================================
# Request Models
# ==========================================

class NewGameRequest(BaseModel):
    player1_name: str = "Shogun"
    player1_deck: str = "D01_FIRE"
    player2_name: str = "Goopy AI"
    player2_deck: str = "D02_PSYCHIC"


class PlayBasicRequest(BaseModel):
    player_name: str
    card_id: str


class AttachEnergyRequest(BaseModel):
    player_name: str
    target_position: str
    target_index: int = 0


class PlayBenchRequest(BaseModel):
    player_name: str
    card_id: str


class EvolveRequest(BaseModel):
    player_name: str
    evolution_card_id: str
    target_position: str = "active"
    target_index: int = 0


class UseTrainerRequest(BaseModel):
    player_name: str
    card_id: str
    target_position: str = "active"
    target_index: int = 0
    opponent_switch_index: Optional[int] = None


class AttackRequest(BaseModel):
    player_name: str
    attack_name: str
    bench_target_index: Optional[int] = None
    self_bench_target_index: Optional[int] = None
    fire_attach_targets: Optional[list[int]] = None


class ResolvePendingEffectRequest(BaseModel):
    player_name: str
    target_indexes: list[int]


class RetreatRequest(BaseModel):
    player_name: str
    bench_index: int


class UseAbilityRequest(BaseModel):
    player_name: str
    pokemon_position: str = "active"
    pokemon_index: int = 0


class PromoteRequest(BaseModel):
    player_name: str
    bench_index: int


class ConcedeRequest(BaseModel):
    player_name: str


# ==========================================
# Endpoints
# ==========================================

def _log_player_action(background_tasks: BackgroundTasks, action: dict):
    g = get_game()
    if g and not g.game_over:
        background_tasks.add_task(logger.log_action, g.get_full_state(), action)


@app.get("/")
def read_root():
    return {"message": "Pokemon TCG Pocket AI Backend is running!"}


@app.post("/api/new_game")
def new_game(req: NewGameRequest, background_tasks: BackgroundTasks):
    global game
    game = GameState(req.player1_name, req.player1_deck,
                     req.player2_name, req.player2_deck, db)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": "สร้างเกมใหม่สำเร็จ!", "state": game.get_full_state()}


@app.post("/api/reset")
def reset_game():
    global game
    game = None
    return {"success": True, "message": "รีเซ็ตเกมเรียบร้อย"}


@app.get("/api/state")
def get_game_state():
    g = get_game()
    return g.get_full_state()


@app.get("/api/decks")
def get_available_decks():
    decks = []
    for deck_id, deck_data in db.decks.items():
        decks.append({
            "deck_id": deck_id,
            "name": deck_data["name"],
            "energy_type": deck_data["energy_type"],
            "card_count": len(deck_data["cards"]),
        })
    return decks


@app.post("/api/action/play_active")
def play_active(req: PlayBasicRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "play_active", **req.dict()})
    g = get_game()
    success, message, _ = g.action_play_active(req.player_name, req.card_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "state": g.get_full_state()}


@app.post("/api/action/play_bench")
def play_bench(req: PlayBenchRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "play_bench", **req.dict()})
    g = get_game()
    success, message, _ = g.action_play_bench(req.player_name, req.card_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "state": g.get_full_state()}


@app.post("/api/action/evolve")
def evolve(req: EvolveRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "evolve", **req.dict()})
    g = get_game()
    success, message, _ = g.action_evolve(
        req.player_name,
        req.evolution_card_id,
        target_position=req.target_position,
        target_index=req.target_index,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "state": g.get_full_state()}


@app.post("/api/action/use_trainer")
def use_trainer(req: UseTrainerRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "use_trainer", **req.dict()})
    g = get_game()
    success, message, extra = g.action_use_trainer(
        req.player_name,
        req.card_id,
        target_position=req.target_position,
        target_index=req.target_index,
        opponent_switch_index=req.opponent_switch_index,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "extra": extra, "state": g.get_full_state()}


@app.post("/api/action/attack")
def attack(req: AttackRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "attack", **req.dict()})
    g = get_game()
    success, message, attack_result = g.action_attack(
        req.player_name, req.attack_name,
        bench_target_index=req.bench_target_index,
        self_bench_target_index=req.self_bench_target_index,
        fire_attach_targets=req.fire_attach_targets,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {
        "success": True,
        "message": message,
        "attack_result": attack_result,
        "state": g.get_full_state(),
    }


@app.post("/api/action/resolve_effect")
def resolve_effect(req: ResolvePendingEffectRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "resolve_effect", **req.dict()})
    g = get_game()
    success, message, result = g.action_resolve_pending_effect(req.player_name, req.target_indexes)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {
        "success": True,
        "message": message,
        "effect_result": result,
        "state": g.get_full_state(),
    }


@app.post("/api/action/attach_energy")
def attach_energy(req: AttachEnergyRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "attach_energy", **req.dict()})
    g = get_game()
    success, message, _ = g.action_attach_energy(
        req.player_name,
        req.target_position,
        req.target_index,
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "state": g.get_full_state()}


@app.post("/api/action/retreat")
def retreat(req: RetreatRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "retreat", **req.dict()})
    g = get_game()
    success, message, extra = g.action_retreat(req.player_name, req.bench_index)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "extra": extra, "state": g.get_full_state()}


@app.post("/api/action/use_ability")
def use_ability(req: UseAbilityRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "use_ability", **req.dict()})
    g = get_game()
    success, message, extra = g.action_use_ability(
        req.player_name, req.pokemon_position, req.pokemon_index
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "extra": extra, "state": g.get_full_state()}


@app.post("/api/action/promote")
def promote(req: PromoteRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "promote", **req.dict()})
    g = get_game()
    success, message, _ = g.action_promote(req.player_name, req.bench_index)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "state": g.get_full_state()}


@app.post("/api/action/concede")
def concede(req: ConcedeRequest, background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "concede", **req.dict()})
    g = get_game()
    success, message, _ = g.action_concede(req.player_name)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "state": g.get_full_state()}


@app.post("/api/action/end_turn")
def end_turn(background_tasks: BackgroundTasks):
    _log_player_action(background_tasks, {"type": "end_turn"})
    g = get_game()
    success, message, _ = g.action_end_turn()
    if not success:
        raise HTTPException(status_code=400, detail=message)
    trigger_ai_if_needed(background_tasks)
    return {"success": True, "message": message, "state": g.get_full_state()}


@app.get("/api/debug/action_log")
def debug_action_log(limit: int = 30):
    g = get_game()
    if limit <= 0:
        limit = 1
    return {"entries": g.action_log[-limit:]}


@app.get("/api/debug/action_log_by_turn")
def debug_action_log_by_turn(limit: int = 30):
    g = get_game()
    if limit <= 0:
        limit = 1
    entries = g.action_log[-limit:]
    grouped = {}
    for entry in entries:
        turn = entry.get("turn")
        key = f"turn_{turn}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(entry)
    return {"turns": grouped}


@app.get("/api/debug/event_log")
def debug_event_log(limit: int = 30):
    g = get_game()
    if limit <= 0:
        limit = 1
    return {"entries": g.event_log[-limit:]}


@app.get("/api/debug/event_log_by_turn")
def debug_event_log_by_turn(limit: int = 30):
    g = get_game()
    if limit <= 0:
        limit = 1
    entries = g.event_log[-limit:]
    grouped = {}
    for entry in entries:
        turn = entry.get("turn")
        key = f"turn_{turn}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(entry)
    return {"turns": grouped}
