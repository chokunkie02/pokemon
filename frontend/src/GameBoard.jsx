import React, { useEffect, useState, useCallback, useRef } from 'react';

const API = import.meta.env.VITE_API_BASE_URL;

const ENERGY_SYMBOLS = {
  fire: '🔥', water: '💧', psychic: '🔮', lightning: '⚡',
  fighting: '👊', grass: '🌿', darkness: '🌙', colorless: '⚪',
};

const DECK_TYPE_LABELS = {
  fire: 'ไฟ',
  lightning: 'สายฟ้า',
  psychic: 'พลังจิต',
};

function getEnergyClass(type) {
  return `energy-badge energy-${type || 'colorless'}`;
}

function getHpColor(current, max) {
  const pct = current / max;
  if (pct > 0.5) return 'var(--hp-green)';
  if (pct > 0.25) return 'var(--hp-yellow)';
  return 'var(--hp-red)';
}

export default function GameBoard({ isTrueBattle, onBack }) {
  const [gameState, setGameState] = useState(null);
  const [availableDecks, setAvailableDecks] = useState([]);
  const [selectedDeckId1, setSelectedDeckId1] = useState('');
  const [selectedDeckId2, setSelectedDeckId2] = useState('');
  const [showStartSetup, setShowStartSetup] = useState(false);
  const [isStartingGame, setIsStartingGame] = useState(false);
  const [transitionDeck, setTransitionDeck] = useState(null);
  const [error, setError] = useState('');
  const [selectedCard, setSelectedCard] = useState(null);
  const [showRetreatModal, setShowRetreatModal] = useState(false);
  const [showEnergyModal, setShowEnergyModal] = useState(false);
  const [showLogModal, setShowLogModal] = useState(false);
  const [showEvolveTarget, setShowEvolveTarget] = useState(null);
  const [showTrainerTarget, setShowTrainerTarget] = useState(null);
  const [showAttackTarget, setShowAttackTarget] = useState(null);
  const [showInfernoDanceTarget, setShowInfernoDanceTarget] = useState(null);
  const [infernoDanceSelections, setInfernoDanceSelections] = useState([]);
  const [lastAttackResult, setLastAttackResult] = useState(null);
  const [message, setMessage] = useState('');
  const [playedCardOverlay, setPlayedCardOverlay] = useState(null);
  const [aiActionBanner, setAiActionBanner] = useState(null);
  const [cardPopup, setCardPopup] = useState(null); // { cardId, cardName, actionLabel, playerName }
  const logRef = useRef(null);
  const logModalRef = useRef(null);

  const getInfernoDanceModalState = useCallback((state) => {
    const pending = state?.pending_effect;
    if (!pending || pending.type !== 'inferno_dance' || (pending.selection_count || 0) <= 0) {
      return null;
    }

    const pendingPlayer = state?.player_1?.name === pending.player_name
      ? state.player_1
      : state?.player_2?.name === pending.player_name
        ? state.player_2
        : null;

    if (!pendingPlayer) return null;

    const fireBenchTargets = (pendingPlayer.bench || [])
      .map((bp, idx) => ({ ...bp, idx }))
      .filter((bp) => pending.available_bench_indexes?.includes(bp.idx));

    if (fireBenchTargets.length === 0) return null;

    return {
      playerName: pending.player_name,
      targets: fireBenchTargets,
      selectionCount: pending.selection_count,
    };
  }, []);

  const showMsg = useCallback((msg) => {
    setMessage(msg);
    setTimeout(() => setMessage(''), 3000);
  }, []);

  const showCardPopup = useCallback((cardId, cardName, actionLabel, playerName) => {
    setCardPopup({ cardId, cardName, actionLabel, playerName, key: Date.now() });
    setTimeout(() => setCardPopup(null), 1900);
  }, []);

  // AI Action Banner: show a slide-in overlay when AI thought changes
  const prevAiThoughtRef = useRef(null);
  useEffect(() => {
    const thought = gameState?.latest_ai_thought;
    if (thought && thought !== prevAiThoughtRef.current) {
      prevAiThoughtRef.current = thought;
      setAiActionBanner(thought);
      const t = setTimeout(() => setAiActionBanner(null), 2500);
      return () => clearTimeout(t);
    }
  }, [gameState?.latest_ai_thought]);

  const fetchDecks = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/decks`);
      if (!res.ok) throw new Error('Network error');
      const decks = await res.json();
      const selectable = decks.filter((deck) => ['fire', 'lightning', 'psychic'].includes(deck.energy_type));
      setAvailableDecks(selectable);

      setSelectedDeckId1((prev) => {
        if (prev && selectable.some((deck) => deck.deck_id === prev)) return prev;
        return selectable[0]?.deck_id || '';
      });
      setSelectedDeckId2((prev) => {
        if (prev && selectable.some((deck) => deck.deck_id === prev)) return prev;
        return selectable[1]?.deck_id || selectable[0]?.deck_id || '';
      });
    } catch {
      setError('ไม่สามารถโหลดรายชื่อเด็คได้!');
    }
  }, []);

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/state`);
      if (res.status === 400) {
        // ยังไม่มีเกม ให้ผู้เล่นเลือกเด็คก่อนเริ่ม
        setGameState(null);
        setShowStartSetup(true);
        return;
      }
      if (!res.ok) throw new Error('Network error');
      const data = await res.json();
      setGameState(data);
      setShowStartSetup(false);
    } catch {
      setError('ไม่สามารถเชื่อมต่อ Backend ได้!');
    }
  }, []);

  const createNewGame = () => {
    if (!selectedDeckId1 || !selectedDeckId2) {
      showMsg('กรุณาเลือกเด็คทั้งสองฝั่งก่อนเริ่มเกม');
      return;
    }

    const deckObj = availableDecks.find(d => d.deck_id === selectedDeckId1);
    if (deckObj) {
      setTransitionDeck(deckObj.energy_type);
    }
    
    setIsStartingGame(true);

    setTimeout(async () => {
      try {
        const res = await fetch(`${API}/api/new_game`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            player1_name: 'Shogun',
            player1_deck: selectedDeckId1,
            player2_name: 'Goopy AI',
            player2_deck: selectedDeckId2,
          })
        });
        const data = await res.json();
        if (res.ok) {
          setGameState(data.state);
          setShowStartSetup(false);
          setTransitionDeck(null);
          setError('');
        } else {
          showMsg(data.detail || 'เริ่มเกมไม่สำเร็จ');
          setTransitionDeck(null);
        }
      } catch (err) {
        console.error(err);
        setError('ไม่สามารถสร้างเกมใหม่ได้!');
        setTransitionDeck(null);
      } finally {
        setIsStartingGame(false);
      }
    }, 3000);
  };

  useEffect(() => {
    fetchDecks();
    fetchState();
  }, [fetchDecks, fetchState]);

  // Keep frontend state synchronized with backend, even when AI runs asynchronously.
  useEffect(() => {
    if (!gameState || gameState.game_over) return;
    const interval = setInterval(() => {
      fetchState();
    }, 3000);
    return () => clearInterval(interval);
  }, [gameState, fetchState]);

  useEffect(() => {
    if (logModalRef.current) {
      logModalRef.current.scrollTop = logModalRef.current.scrollHeight;
    }
  }, [gameState?.action_log, showLogModal]);

  useEffect(() => {
    if (gameState?.last_played_card && gameState.last_played_card_id > 0) {
      setPlayedCardOverlay(gameState.last_played_card);
      const timer = setTimeout(() => {
        setPlayedCardOverlay(null);
      }, 2500);
      return () => clearTimeout(timer);
    }
  }, [gameState?.last_played_card_id, gameState?.last_played_card]);

  useEffect(() => {
    const modalState = getInfernoDanceModalState(gameState);
    if (!modalState) {
      if (showInfernoDanceTarget) {
        setShowInfernoDanceTarget(null);
        setInfernoDanceSelections([]);
      }
      return;
    }

    setShowInfernoDanceTarget((current) => {
      const sameModal = current
        && current.playerName === modalState.playerName
        && current.selectionCount === modalState.selectionCount
        && current.targets.length === modalState.targets.length
        && current.targets.every((target, index) => target.idx === modalState.targets[index]?.idx);

      if (sameModal) return current;
      setInfernoDanceSelections([]);
      return modalState;
    });
  }, [gameState, getInfernoDanceModalState, showInfernoDanceTarget]);

  // API action helper
  const doAction = async (endpoint, body = {}, method = 'POST') => {
    try {
      const opts = { method, headers: { 'Content-Type': 'application/json' } };
      if (method === 'POST') opts.body = JSON.stringify(body);
      const res = await fetch(`${API}${endpoint}`, opts);
      const data = await res.json();
      if (!res.ok) {
        showMsg(data.detail || 'Error');
        if (data?.detail && /ยังไม่ใช่เทิร์นของคุณ|Main Phase|มีเอฟเฟกต์ค้างอยู่/i.test(String(data.detail))) {
          await fetchState();
        }
        return null;
      }
      if (data.state) setGameState(data.state);
      if (data.attack_result?.coin_results?.length > 0 || data.effect_result?.coin_results?.length > 0) {
        setLastAttackResult(data.attack_result || data.effect_result);
        setTimeout(() => setLastAttackResult(null), 3000);
      }
      return data;
    } catch (err) {
      console.error(err);
      showMsg('เกิดข้อผิดพลาด!');
      return null;
    }
  };

  // Close menus on click outside
  useEffect(() => {
    const handler = (e) => {
      if (!e.target.closest('.hand-card') && !e.target.closest('.card-action-menu')) {
        setSelectedCard(null);
      }
    };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  if (error) return (
    <div className="error-screen">
      <div className="error-text">{error}</div>
      <button className="btn-new-game" onClick={fetchState}>ลองใหม่</button>
    </div>
  );
  if (showStartSetup) return (
    <div className="loading-screen" style={{ position: 'relative' }}>
      {onBack && (
        <button className="btn-back" onClick={onBack} style={{ position: 'absolute', top: 20, left: 20, zIndex: 100 }}>
          ← กลับหน้าหลัก
        </button>
      )}
      <div className="start-setup-card" style={{ maxWidth: '800px', width: '90%' }}>
        <div className="start-setup-title">เลือกเด็คเริ่มเกม</div>
        <div className="start-setup-subtitle">เลือกเด็คสำหรับทั้ง 2 ฝ่าย</div>

        <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 300px' }}>
            <h3 style={{ textAlign: 'center', marginBottom: '1rem' }}>Shogun (ผู้เล่น)</h3>
            <div className="deck-choice-grid">
              {availableDecks.map((deck) => {
                const isSelected = selectedDeckId1 === deck.deck_id;
                const bgClass = `deck-bg-${deck.energy_type}`;
                const orbMap = { fire: 'f.png', psychic: 'p.png', lightning: 'e.png' };
                const orbImg = orbMap[deck.energy_type] || 'e.png';
                const cleanName = deck.name.replace(/^[🔴🔮⚡\s]+/, '');

                return (
                  <button
                    key={deck.deck_id}
                    className={`deck-choice-btn ${bgClass} ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedDeckId1(deck.deck_id)}
                  >
                    <img src={`/picture/${orbImg}`} alt={`${deck.energy_type} orb`} className="deck-orb-icon" />
                    <div className="deck-choice-text">
                      <div className="deck-choice-name">{cleanName}</div>
                      <div className="deck-choice-type">สาย {DECK_TYPE_LABELS[deck.energy_type] || deck.energy_type}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ flex: '1 1 300px' }}>
            <h3 style={{ textAlign: 'center', marginBottom: '1rem' }}>Goopy AI (บอท)</h3>
            <div className="deck-choice-grid">
              {availableDecks.map((deck) => {
                const isSelected = selectedDeckId2 === deck.deck_id;
                const bgClass = `deck-bg-${deck.energy_type}`;
                const orbMap = { fire: 'f.png', psychic: 'p.png', lightning: 'e.png' };
                const orbImg = orbMap[deck.energy_type] || 'e.png';
                const cleanName = deck.name.replace(/^[🔴🔮⚡\s]+/, '');

                return (
                  <button
                    key={deck.deck_id}
                    className={`deck-choice-btn ${bgClass} ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedDeckId2(deck.deck_id)}
                  >
                    <img src={`/picture/${orbImg}`} alt={`${deck.energy_type} orb`} className="deck-orb-icon" />
                    <div className="deck-choice-text">
                      <div className="deck-choice-name">{cleanName}</div>
                      <div className="deck-choice-type">สาย {DECK_TYPE_LABELS[deck.energy_type] || deck.energy_type}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <button
          className="btn-new-game"
          onClick={createNewGame}
          style={{ alignSelf: 'center', marginTop: '2rem' }}
          disabled={isStartingGame}
        >
          {isStartingGame ? 'กำลังเริ่มเกม...' : 'เริ่มเกม!'}
        </button>

        {transitionDeck && (
          <div className="deck-transition-overlay">
            <div className={`deck-transition-bg deck-bg-${transitionDeck}`} />
            <div className="deck-transition-loading">
              <div className="deck-transition-spinner" />
              <span>กำลังโหลด...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
  if (!gameState) return (
    <div className="loading-screen">
      <div className="loading-spinner" />
      <div className="loading-text">กำลังโหลดเกม...</div>
    </div>
  );

  const { current_turn, setup_phase, pending_initial_active = [], game_over, winner,
    player_1: p1, player_2: p2, action_log = [], turn_number } = gameState;

  // Determine which player needs to promote
  const promotingPlayer = p1.pending_promote ? p1 : p2.pending_promote ? p2 : null;

  const getPokemonTargets = (player, options = {}) => {
    const { damagedOnly = false } = options;
    const targets = [];

    if (player.active_pokemon && (!damagedOnly || player.active_pokemon.current_hp < player.active_pokemon.max_hp)) {
      targets.push({ position: 'active', index: 0, pokemon: player.active_pokemon });
    }

    player.bench.forEach((bp, idx) => {
      if (!damagedOnly || bp.current_hp < bp.max_hp) {
        targets.push({ position: 'bench', index: idx, pokemon: bp });
      }
    });

    return targets;
  };

  // ---------- Card Action Menu ----------
  const getCardActions = (player, cardId) => {
    const detail = player.hand_details?.find(c => c.id === cardId);
    if (!detail) return [];
    const isMyTurn = current_turn === player.name;
    const mustSelectActive = setup_phase && pending_initial_active.includes(player.name);
    const actions = [];

    if (detail.category === 'pokemon' && detail.stage === 'basic') {
      if (mustSelectActive || (!setup_phase && isMyTurn && !player.active_pokemon)) {
        actions.push({ label: '⚔️ ลง Active', action: 'play_active' });
      }
      if (!setup_phase && isMyTurn && player.active_pokemon && player.bench.length < 3) {
        actions.push({ label: '🪑 ลงเบนช์', action: 'play_bench' });
      }
    }

    if (detail.category === 'pokemon' && detail.stage !== 'basic' && !setup_phase && isMyTurn) {
      // สามารถ evolve ได้
      actions.push({ label: '✨ วิวัฒนาการ', action: 'evolve' });
    }

    if ((detail.category === 'item' || detail.category === 'supporter') && !setup_phase && isMyTurn) {
      actions.push({ label: '🃏 ใช้การ์ด Trainer', action: 'use_trainer' });
    }

    return actions;
  };

  const handleCardAction = async (player, cardId, action) => {
    if (player?.name === 'Goopy AI') return;
    setSelectedCard(null);
    const detail = player.hand_details?.find(c => c.id === cardId);
    switch (action) {
      case 'play_active':
        showCardPopup(cardId, detail?.name || cardId, 'ลง Active ⚔️', player.name);
        await doAction('/api/action/play_active', { player_name: player.name, card_id: cardId });
        break;
      case 'play_bench':
        showCardPopup(cardId, detail?.name || cardId, 'ลง Bench 🪑', player.name);
        await doAction('/api/action/play_bench', { player_name: player.name, card_id: cardId });
        break;
      case 'evolve': {
        // เช็คว่า evolve ได้ที่ไหนบ้าง
        showCardPopup(cardId, detail?.name || cardId, 'วิวัฒนาการ ✨', player.name);
        const targets = [];
        if (player.active_pokemon && player.active_pokemon.name === detail?.evolves_from) {
          targets.push({ position: 'active', index: 0, pokemon: player.active_pokemon });
        }
        player.bench.forEach((bp, idx) => {
          if (bp.name === detail?.evolves_from) {
            targets.push({ position: 'bench', index: idx, pokemon: bp });
          }
        });

        if (targets.length === 0) {
          alert('ไม่มีโปเกมอนที่สามารถวิวัฒนาการได้บนสนาม');
          break;
        }

        if (targets.length === 1) {
          await doAction('/api/action/evolve', {
            player_name: player.name,
            evolution_card_id: cardId,
            target_position: targets[0].position,
            target_index: targets[0].index,
          });
        } else {
          setShowEvolveTarget({ player, cardId, targets });
        }
        break;
      }
      case 'use_trainer':
        showCardPopup(cardId, detail?.name || cardId, 'ใช้ Trainer 🃏', player.name);
        if (detail?.trainer_effect_calculation === 'heal_20_from_target') {
          const targets = getPokemonTargets(player, { damagedOnly: true });

          if (targets.length === 0) {
            showMsg('ไม่มี Pokemon ที่บาดเจ็บให้ใช้ Potion');
            break;
          }

          if (targets.length === 1) {
            await doAction('/api/action/use_trainer', {
              player_name: player.name,
              card_id: cardId,
              target_position: targets[0].position,
              target_index: targets[0].index,
            });
            break;
          }

          setShowTrainerTarget({
            player,
            cardId,
            title: 'Potion: เลือก Pokemon ที่จะฮีล',
            subtitle: 'เลือก Pokemon ฝั่งตัวเองที่ต้องการฟื้นฟู 20 HP',
            targets,
          });
          break;
        }

        if (detail?.trainer_effect_calculation === 'opponent_switch_active_to_bench') {
          const opponent = player.name === p1.name ? p2 : p1;
          const targets = (opponent?.bench || []).map((pokemon, index) => ({
            position: 'bench',
            index,
            pokemon,
          }));

          if (targets.length === 0) {
            showMsg('คู่ต่อสู้ไม่มี Pokemon บน Bench ให้เลือก');
            break;
          }

          if (targets.length === 1) {
            await doAction('/api/action/use_trainer', {
              player_name: player.name,
              card_id: cardId,
              opponent_switch_index: targets[0].index,
            });
            break;
          }

          setShowTrainerTarget({
            player,
            cardId,
            mode: 'opponent_switch',
            title: 'Sabrina: เลือก Active ตัวใหม่ของฝั่งตรงข้าม',
            subtitle: 'เลือก Pokemon จาก Bench ของฝั่งตรงข้ามที่จะถูกสลับขึ้นมา',
            targets,
          });
          break;
        }

        await doAction('/api/action/use_trainer', { player_name: player.name, card_id: cardId });
        break;
    }
  };

  const handleTrainerTarget = async (target) => {
    if (!showTrainerTarget) return;
    const { player, cardId, mode } = showTrainerTarget;
    if (player?.name === 'Goopy AI') return;
    setShowTrainerTarget(null);
    if (mode === 'opponent_switch') {
      await doAction('/api/action/use_trainer', {
        player_name: player.name,
        card_id: cardId,
        opponent_switch_index: target.index,
      });
      return;
    }

    await doAction('/api/action/use_trainer', {
      player_name: player.name,
      card_id: cardId,
      target_position: target.position,
      target_index: target.index,
    });
  };

  const handleEvolve = async (target) => {
    if (!showEvolveTarget) return;
    const { player, cardId } = showEvolveTarget;
    if (player?.name === 'Goopy AI') return;
    setShowEvolveTarget(null);
    await doAction('/api/action/evolve', {
      player_name: player.name,
      evolution_card_id: cardId,
      target_position: target.position,
      target_index: target.index,
    });
  };

  const handleRetreat = async (benchIndex) => {
    setShowRetreatModal(false);
    const currentPlayer = current_turn === p1.name ? p1 : p2;
    if (currentPlayer?.name === 'Goopy AI') return;
    await doAction('/api/action/retreat', {
      player_name: currentPlayer.name,
      bench_index: benchIndex,
    });
  };

  const handleAttachEnergy = async (position, index) => {
    setShowEnergyModal(false);
    const currentPlayer = current_turn === p1.name ? p1 : p2;
    if (currentPlayer?.name === 'Goopy AI') return;
    await doAction('/api/action/attach_energy', {
      player_name: currentPlayer.name,
      target_position: position,
      target_index: index,
    });
  };

  const handlePromote = async (benchIndex) => {
    if (!promotingPlayer) return;
    if (promotingPlayer?.name === 'Goopy AI') return;
    await doAction('/api/action/promote', {
      player_name: promotingPlayer.name,
      bench_index: benchIndex,
    });
  };

  const handleAttackTarget = async (target) => {
    if (!showAttackTarget) return;
    const { playerName, attackName } = showAttackTarget;
    if (playerName === 'Goopy AI') return;
    setShowAttackTarget(null);
    await doAction('/api/action/attack', {
      player_name: playerName,
      attack_name: attackName,
      bench_target_index: target.position === 'bench' ? target.index : null,
    });
  };

  const handleAttack = async (attack) => {
    const currentPlayer = current_turn === p1.name ? p1 : p2;
    if (currentPlayer?.name === 'Goopy AI') return;
    const opponent = current_turn === p1.name ? p2 : p1;

    if (attack.effect_calculation === 'damage_to_opponent_pokemon_30') {
      const targets = [];
      if (opponent.active_pokemon) {
        targets.push({
          position: 'active',
          index: 0,
          pokemon: opponent.active_pokemon,
        });
      }
      (opponent.bench || []).forEach((bp, idx) => {
        targets.push({ position: 'bench', index: idx, pokemon: bp });
      });

      if (targets.length === 0) {
        showMsg('ไม่มีเป้าหมายให้โจมตี');
        return;
      }

      if (targets.length === 1) {
        await doAction('/api/action/attack', {
          player_name: currentPlayer.name,
          attack_name: attack.name,
          bench_target_index: targets[0].position === 'bench' ? targets[0].index : null,
        });
        return;
      }

      setShowAttackTarget({
        playerName: currentPlayer.name,
        attackName: attack.name,
        title: `${attack.name}: เลือกเป้าหมาย 30 ดาเมจ`,
        subtitle: 'เลือกโปเกมอนฝั่งตรงข้าม 1 ตัว (Active หรือ Bench)',
        targets,
      });
      return;
    }

    await doAction('/api/action/attack', {
      player_name: currentPlayer.name,
      attack_name: attack.name,
    });
  };

  const handleInfernoDanceTarget = (benchIndex) => {
    if (!showInfernoDanceTarget) return;
    if (showInfernoDanceTarget.playerName === 'Goopy AI') return;
    if (infernoDanceSelections.length >= showInfernoDanceTarget.selectionCount) return;
    setInfernoDanceSelections((prev) => [...prev, benchIndex]);
  };

  const handleInfernoDanceUndo = () => {
    if (showInfernoDanceTarget?.playerName === 'Goopy AI') return;
    setInfernoDanceSelections((prev) => prev.slice(0, -1));
  };

  const handleInfernoDanceConfirm = async () => {
    if (!showInfernoDanceTarget) return;
    if (showInfernoDanceTarget.playerName === 'Goopy AI') return;
    if (infernoDanceSelections.length !== showInfernoDanceTarget.selectionCount) {
      showMsg(`ต้องเลือกให้ครบ ${showInfernoDanceTarget.selectionCount} ครั้ง`);
      return;
    }
    const playerName = showInfernoDanceTarget.playerName;
    setShowInfernoDanceTarget(null);
    setInfernoDanceSelections([]);
    await doAction('/api/action/resolve_effect', {
      player_name: playerName,
      target_indexes: infernoDanceSelections,
    });
  };

  const handleAbility = async () => {
    const currentPlayer = current_turn === p1.name ? p1 : p2;
    if (currentPlayer?.name === 'Goopy AI') return;
    await doAction('/api/action/use_ability', {
      player_name: currentPlayer.name,
      pokemon_position: 'active',
      pokemon_index: 0,
    });
  };

  const handleBenchAbility = async (playerName, benchIndex) => {
    if (playerName === 'Goopy AI') return;
    await doAction('/api/action/use_ability', {
      player_name: playerName,
      pokemon_position: 'bench',
      pokemon_index: benchIndex,
    });
  };

  const handleEndTurn = async () => {
    await doAction('/api/action/end_turn');
  };

  const handleConcede = async () => {
    if (!confirm('คุณแน่ใจหรือว่าต้องการยอมแพ้?')) return;
    const currentPlayer = current_turn === p1.name ? p1 : p2;
    await doAction('/api/action/concede', { player_name: currentPlayer.name });
  };

  // ---------- Render Helpers ----------
  const renderEnergyBadges = (energyList) => {
    if (!energyList || energyList.length === 0) return null;
    return (
      <div className="card-energy-badges">
        {energyList.map((e, idx) => (
          <div key={idx} className={`energy-badge energy-${e}`} />
        ))}
      </div>
    );
  };

  const renderConditions = (conditions) => {
    if (!conditions || conditions.length === 0) return null;
    return (
      <div className="conditions-display">
        {conditions.map(c => (
          <span key={c} className={`condition-tag condition-${c}`}>{c}</span>
        ))}
      </div>
    );
  };

  const renderHpBar = (current, max, width = '100%') => {
    const pct = Math.max(0, (current / max) * 100);
    return (
      <div className="hp-bar-container" style={{ width }}>
        <div className="hp-bar-bg">
          <div className="hp-bar-fill" style={{
            width: `${pct}%`,
            background: getHpColor(current, max),
          }} />
        </div>
        <div className="hp-text">
          <span className="current" style={{ color: getHpColor(current, max) }}>{current}</span>
          <span className="max">/{max}</span>
        </div>
      </div>
    );
  };

  const renderPlayerField = (player, isOpponent) => {
    const isGoopyAI = player.name === 'Goopy AI';
    const isMyTurn = current_turn === player.name;
    const mustSelectActive = setup_phase && pending_initial_active.includes(player.name) && !isGoopyAI;
    // Human can ONLY interact with their own field when it's explicitly their turn
    const canInteract = !isGoopyAI && (mustSelectActive || (!setup_phase && isMyTurn));
    const isPlayer1 = player.name === p1.name;

    const deckOrbMap = { fire: 'f.png', psychic: 'p.png', lightning: 'e.png' };

    return (
      <div className={`player-field ${isMyTurn ? 'is-turn' : ''} ${isOpponent ? 'opponent' : 'player'} energy-field-${player.energy_type || 'colorless'}`}>
        {/* Header */}
        <div className="field-header">
          {isGoopyAI ? (
            /* ── Goopy AI: same row layout as human player ── */
            <div className="player-info-row">
              <div className={`ai-avatar-circle ai-avatar-circle-${player.energy_type || 'colorless'} ${isMyTurn ? 'ai-avatar-thinking' : ''}`}>
                <img src="/picture/ai.png" alt="Goopy AI" className="ai-avatar-circle-img" />
              </div>
              <div className="player-stats">
                <div className="player-name">
                  {player.name}
                  {isMyTurn && !setup_phase && (
                    <span className="your-turn-tag" style={{ background: 'var(--accent-psychic)' }}>AI TURN</span>
                  )}
                  {mustSelectActive && <span className="promote-tag">เลือก Active</span>}
                  {player.pending_promote && <span className="promote-tag">เลือก Promote</span>}
                </div>
              </div>
              <div className="prize-section">
                <div className="prize-label-text">ไพ่รางวัล</div>
                <div className="prize-cards-display">
                  {[0, 1, 2].map(i => (
                    <div key={i} className={`prize-card ${i < player.points ? 'taken' : ''}`}>
                      <div className="prize-card-inner" />
                    </div>
                  ))}
                </div>
                <div className="prize-count-text">{player.points}/3 คะแนน</div>
              </div>
            </div>
          ) : (
            /* ── Human player: info row ── */
            <div className={`player-area ${isPlayer1 ? 'player-bottom' : 'player-top'}`}>
              <div className="player-info-row">
                <div className="avatar-placeholder">
                  {isPlayer1 ? 'P1' : 'P2'}
                </div>
                <div className={`player-stats ${isOpponent ? 'glass-panel' : ''}`}>
                  <div className="player-name">
                    {player.name}
                    {isMyTurn && !setup_phase && <span className="your-turn-tag">YOUR TURN</span>}
                    {mustSelectActive && <span className="promote-tag">เลือก Active</span>}
                    {player.pending_promote && <span className="promote-tag">เลือก Promote</span>}
                  </div>
                  {player.energy_type && (
                    <span className={`deck-type-badge deck-badge-${player.energy_type}`}>
                      {deckOrbMap[player.energy_type] && (
                        <img src={`/picture/${deckOrbMap[player.energy_type]}`} alt="" style={{ width: 11, height: 11, verticalAlign: 'middle', marginRight: 3 }} />
                      )}
                      สาย{DECK_TYPE_LABELS[player.energy_type] || player.energy_type}
                    </span>
                  )}
                </div>
                <div className="prize-section">
                  <div className="prize-label-text">ไพ่รางวัล</div>
                  <div className="prize-cards-display">
                    {[0, 1, 2].map(i => (
                      <div key={i} className={`prize-card ${i < player.points ? 'taken' : ''}`}>
                        <div className="prize-card-inner" />
                      </div>
                    ))}
                  </div>
                  <div className="prize-count-text">{player.points}/3 คะแนน</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Energy & Stats */}
        <div className="energy-stats-row">
          <div className={`energy-zone ${isOpponent ? 'glass-panel' : ''}`}>
            <div className="energy-slots">
              {Array.from({ length: 12 }).map((_, i) => {
                const orbMap = { fire: 'f.png', psychic: 'p.png', lightning: 'e.png', water: 'w.png', grass: 'g.png', fighting: 'fi.png', colorless: 'c.png', dark: 'd.png', metal: 'm.png', dragon: 'dr.png', fairy: 'fa.png' };
                const orbImg = orbMap[player.energy_type] || 'c.png';
                const orbClass = `energy-orb-icon energy-orb-${player.energy_type}`;

                return (
                  <div key={i} className={`energy-slot ${i < player.energy_zone ? 'filled' : ''}`}>
                    {i < player.energy_zone && player.energy_type && (
                      <img src={`/picture/${orbImg}`} alt={player.energy_type} className={orbClass} />
                    )}
                  </div>
                );
              })}
            </div>
            <span className="energy-zone-label">Energy Zone</span>
          </div>
          <div className="deck-count">
            🃏 Deck: <strong>{player.deck_count}</strong>
          </div>
          {canInteract && !setup_phase && player.energy_zone > 0 && (
            <button className="utility-btn" onClick={() => setShowEnergyModal(true)}>
              <span className="icon">⚡</span> ติดพลังงาน
            </button>
          )}
        </div>

        {/* Field Content */}
        <div className="field-content" style={{ position: 'relative' }}>

          {/* Active Zone */}
          <div className="active-zone">
            <div className="active-zone-label">Active</div>
            {player.active_pokemon ? (
              <div className="active-card-wrapper">
                <img
                  src={`/picture/${player.active_pokemon.card_id}.webp`}
                  alt={player.active_pokemon.name}
                  className="active-card"
                />
                <div className="pokemon-info-bar">
                  <span className="pokemon-name">{player.active_pokemon.name}</span>
                  {renderEnergyBadges(player.active_pokemon.attached_energy)}
                </div>
                {renderHpBar(player.active_pokemon.current_hp, player.active_pokemon.max_hp, '140px')}
                {renderConditions(player.active_pokemon.special_conditions)}
              </div>
            ) : (
              <div className="empty-slot">ว่าง</div>
            )}
          </div>

          {/* Bench Zone */}
          <div className="bench-zone">
            <div className="bench-zone-label">Bench ({player.bench.length}/3)</div>
            <div className="bench-cards">
              {player.bench.map((bp, idx) => (
                <div
                  key={idx}
                  className={`bench-card-slot ${canInteract && player.pending_promote ? 'clickable' : ''}`}
                  onClick={() => (canInteract && player.pending_promote) ? handlePromote(idx) : null}
                >
                  <img
                    src={`/picture/${bp.card_id}.webp`}
                    alt={bp.name}
                    className={`bench-card-img ${player.pending_promote ? 'promote-highlight' : ''}`}
                  />
                  <div className="bench-hp">
                    <div className="bench-hp-bar">
                      <div className="bench-hp-fill" style={{
                        width: `${Math.max(0, (bp.current_hp / bp.max_hp) * 100)}%`,
                        background: getHpColor(bp.current_hp, bp.max_hp),
                      }} />
                    </div>
                  </div>
                  <div className="bench-name">{bp.name}</div>
                  {(() => {
                    const ability = player.bench_abilities?.find((a) => a.index === idx);
                    if (!ability || !canInteract || setup_phase) return null;
                    return (
                      <button
                        className="utility-btn"
                        style={{ marginTop: 6, padding: '4px 8px', fontSize: 10 }}
                        disabled={!ability.can_use}
                        title={ability.effect}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleBenchAbility(player.name, idx);
                        }}
                      >
                        ⭐ {ability.name}
                      </button>
                    );
                  })()}
                  {renderEnergyBadges(bp.attached_energy)}
                  {renderConditions(bp.special_conditions)}
                </div>
              ))}
              {Array.from({ length: 3 - player.bench.length }).map((_, i) => (
                <div key={`empty-${i}`} className="empty-bench-slot">+</div>
              ))}
            </div>
          </div>
          
          {/* Internal Hand Zone for PC Layout */}
          <div className="internal-hand-zone">
            {renderHand(player)}
          </div>
          
        </div>
      </div>
    );
  };

  const renderHand = (player) => {
    const isGoopyAI = player.name === 'Goopy AI';
    const isMyTurn = current_turn === player.name;
    const mustSelectActive = setup_phase && pending_initial_active.includes(player.name);
    const canInteract = !isGoopyAI && (mustSelectActive || (!setup_phase && isMyTurn));

    return (
      <div className="hand-section">
        <div className="hand-label">
          {player.name}'s Hand
          <span className="hand-count">{player.hand.length} cards</span>
        </div>
        <div className="hand-cards">
          {player.hand.map((cardId, idx) => {
            const detail = player.hand_details?.find(c => c.id === cardId);
            const isBasic = detail?.category === 'pokemon' && detail?.stage === 'basic';
            const highlightBasic = canInteract && isBasic && !player.active_pokemon;
            const actions = canInteract ? getCardActions(player, cardId) : [];
            const isSelected = selectedCard?.cardId === cardId && selectedCard?.playerName === player.name && selectedCard?.idx === idx;

            return (
              <div
                key={`${cardId}-${idx}`}
                className={`hand-card ${highlightBasic ? 'highlight-basic' : ''} ${!canInteract ? 'disabled' : ''} ${isSelected ? 'active-selection' : ''} ${isGoopyAI && isTrueBattle ? 'hidden-card' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!canInteract) return;
                  if (actions.length === 1) {
                    handleCardAction(player, cardId, actions[0].action);
                  } else if (actions.length > 1) {
                    setSelectedCard(isSelected ? null : { cardId, playerName: player.name, idx, actions, player });
                  }
                }}
              >
                {isGoopyAI && isTrueBattle ? (
                  <img src="/picture/A1_001.png" alt="Card back" className="card-back-img" />
                ) : (
                  <img src={`/picture/${cardId}.webp`} alt={`Card ${cardId}`} />
                )}
                {isSelected && actions.length > 1 && (
                  <div className="card-action-menu" onClick={e => e.stopPropagation()}>
                    {actions.map((a, i) => (
                      <button
                        key={i}
                        className="action-btn"
                        onClick={() => handleCardAction(player, cardId, a.action)}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderActionPanel = () => {
    const currentPlayer = current_turn === p1.name ? p1 : p2;
    const attacks = currentPlayer.active_attacks || [];
    const ability = currentPlayer.active_ability;

    // Always render the panel container to keep layout stable (no jump when panel appears)
    const isVisible = !setup_phase && !game_over && current_turn !== 'Goopy AI';

    return (
      <div className="action-panel" style={{ visibility: isVisible ? 'visible' : 'hidden' }}>
        <div className="action-panel-grid">
          {/* Attacks */}
          {attacks.map((atk, idx) => (
              <button
                key={idx}
                className="attack-btn"
                disabled={!atk.can_use}
                onClick={() => handleAttack(atk)}
              >
                <div className="attack-name">{atk.name}</div>
                <div className="attack-info">
                  <div className="attack-cost">
                    {atk.cost.map((e, i) => (
                      <div key={i} className={`energy-badge energy-${e}`} />
                    ))}
                  </div>
                  <div className="attack-damage">{atk.damage > 0 ? atk.damage : '—'}</div>
                </div>
                {atk.effect && <div className="attack-effect">{atk.effect}</div>}
              </button>
          ))}

          {/* Ability */}
          {ability && (
            <button
              className="utility-btn"
              disabled={!ability.can_use}
              onClick={handleAbility}
              title={ability.effect}
            >
              <span className="icon">⭐</span>
              {ability.name}
              {!ability.can_use && ' (ใช้แล้ว)'}
            </button>
          )}

          {/* Retreat */}
          {currentPlayer.bench.length > 0 && currentPlayer.active_pokemon && (
            <button
              className="utility-btn"
              disabled={currentPlayer.retreated_this_turn}
              onClick={() => {
                if (currentPlayer.bench.length === 1) {
                  handleRetreat(0);
                } else {
                  setShowRetreatModal(true);
                }
              }}
            >
              <span className="icon">🔄</span>
              ถอย {currentPlayer.retreated_this_turn ? '(ใช้แล้ว)' : ''}
            </button>
          )}
        </div>
      </div>
    );
  };

  // ---------- Main Render ----------
  return (
    <div className="game-container">
      {/* Top Bar */}
      <div className="top-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          {onBack && (
            <button className="btn-back" onClick={onBack}>← กลับหน้าหลัก</button>
          )}
          <div className="top-bar-logo">
            <h1>Pocket Duelist</h1>
          </div>
        </div>
        <div className="turn-badge">
          <div className="turn-indicator">
            <span className="turn-label">Turn</span>
            <span className="turn-number">{turn_number}</span>
          </div>
          {!setup_phase && (
            <>
              {current_turn === 'Goopy AI' ? (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  color: 'var(--accent-psychic)', fontSize: 13, fontWeight: 600,
                  animation: 'pulse 1.5s ease-in-out infinite'
                }}>
                  <span>🧠</span> Goopy AI กำลังคิด...
                </div>
              ) : (
                <>
                  <button className="btn-concede" onClick={handleConcede}>🏳️ ยอมแพ้</button>
                  <button
                    className="btn-end-turn"
                    disabled={game_over || promotingPlayer !== null}
                    onClick={handleEndTurn}
                  >
                    จบเทิร์น ▶
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Message Toast */}
      {message && (
        <div style={{
          position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '10px 20px', zIndex: 400,
          color: 'var(--text-bright)', fontWeight: 600, fontSize: 13,
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)', animation: 'fadeIn 0.2s',
        }}>
          {message}
        </div>
      )}

      {/* Played Card Overlay (AI last played) */}
      {playedCardOverlay && (
        <div className="card-play-popup" key={playedCardOverlay.card_id + Date.now()}>
          <div className="card-play-popup-inner">
            <span className="card-play-popup-player">{playedCardOverlay.player || 'Goopy AI'}</span>
            <img src={`/picture/${playedCardOverlay.card_id}.webp`} alt="Played Card" className="card-play-popup-img" />
            <span className="card-play-popup-action">ใช้การ์ด!</span>
          </div>
        </div>
      )}

      {/* Player Card Popup */}
      {cardPopup && (
        <div className="card-play-popup" key={cardPopup.key}>
          <div className="card-play-popup-inner">
            <span className="card-play-popup-player">{cardPopup.playerName}</span>
            <img src={`/picture/${cardPopup.cardId}.webp`} alt={cardPopup.cardName} className="card-play-popup-img" />
            <span className="card-play-popup-action">{cardPopup.actionLabel}</span>
          </div>
        </div>
      )}

      {/* AI Action Banner Overlay */}
      {aiActionBanner && (
        <div className="ai-banner-overlay">
          <img src="/picture/ai.png" alt="Goopy AI" className="ai-banner-avatar" />
          <div style={{ flex: 1 }}>
            <div className="ai-banner-label">Goopy AI Action</div>
            <div className="ai-banner-text">{aiActionBanner}</div>
          </div>
        </div>
      )}

      {/* Board */}
      <div className="board">
        {/* Opponent Field */}
        {renderPlayerField(p2, true)}

        {/* VS Divider */}
        <div className="vs-divider">
          <div className="vs-line" />
          <div className="vs-badge">VS</div>
          <div className="vs-line" />
        </div>

        {/* Player Field */}
        {renderPlayerField(p1, false)}
      </div>

      {/* Action Panel */}
      {renderActionPanel()}

      {/* Coin Flip Display */}
      {lastAttackResult?.coin_results?.length > 0 && (
        <div style={{
          position: 'fixed', bottom: 120, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--bg-panel)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '12px 20px', zIndex: 150,
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)', animation: 'slideUp 0.3s',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 6, fontWeight: 600 }}>
            Coin Flip
          </div>
          <div className="coin-flip-display">
            {lastAttackResult.coin_results.map((r, i) => (
              <div key={i} className={`coin ${r}`}>
                {r === 'heads' ? 'H' : 'T'}
              </div>
            ))}
          </div>
          {lastAttackResult.heads_count !== undefined && (
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-gold)', marginTop: 4 }}>
              {lastAttackResult.heads_count} Heads!
            </div>
          )}
          {lastAttackResult.energy_attached !== undefined && (
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
              Attached: {lastAttackResult.energy_attached}
            </div>
          )}
        </div>
      )}

      {/* Log Bar */}
      <div className="log-bar">
        {action_log.length > 0 && (
          <>
            <button className="log-history-btn" onClick={() => setShowLogModal(true)}>
              📋 ประวัติการเล่น
              <span className="log-history-count">{action_log.length}</span>
            </button>
            <span className="log-latest-entry">
              <span className="log-turn">T{action_log[action_log.length - 1].turn}</span>
              {action_log[action_log.length - 1].message}
            </span>
          </>
        )}
      </div>

      {/* Log Modal */}
      {showLogModal && (
        <div className="modal-overlay" onClick={() => setShowLogModal(false)}>
          <div className="log-modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-title">📋 ประวัติการเล่น</div>
            <div className="log-modal-entries" ref={logModalRef}>
              {action_log.map((entry, i) => (
                <div key={i} className={`log-modal-entry ${i === action_log.length - 1 ? 'log-modal-entry-latest' : ''}`}>
                  <span className="log-modal-turn">T{entry.turn}</span>
                  <span className="log-modal-msg">{entry.message}</span>
                </div>
              ))}
            </div>
            <button className="log-modal-close-btn" onClick={() => setShowLogModal(false)}>ปิด</button>
          </div>
        </div>
      )}

      {/* === Modals === */}

      {/* Retreat Modal */}
      {showRetreatModal && (() => {
        const cp = current_turn === p1.name ? p1 : p2;
        return (
          <div className="modal-overlay" onClick={() => setShowRetreatModal(false)}>
            <div className="modal-box" onClick={e => e.stopPropagation()}>
              <div className="modal-title">🔄 เลือก Pokemon สลับขึ้น Active</div>
              <div className="modal-subtitle">เลือก Pokemon จาก Bench ที่จะขึ้นมาแทน</div>
              {cp.bench.map((bp, idx) => (
                <div key={idx} className="retreat-option" onClick={() => handleRetreat(idx)}>
                  <img src={`/picture/${bp.card_id}.webp`} alt={bp.name} />
                  <div className="info">
                    <div className="name">{bp.name}</div>
                    <div className="hp">HP: {bp.current_hp}/{bp.max_hp}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Energy Modal */}
      {showEnergyModal && (() => {
        const cp = current_turn === p1.name ? p1 : p2;
        const targets = [];
        if (cp.active_pokemon) targets.push({ pos: 'active', idx: 0, p: cp.active_pokemon });
        cp.bench.forEach((bp, i) => targets.push({ pos: 'bench', idx: i, p: bp }));
        return (
          <div className="modal-overlay" onClick={() => setShowEnergyModal(false)}>
            <div className="modal-box" onClick={e => e.stopPropagation()}>
              <div className="modal-title">⚡ ติดพลังงานให้ใคร?</div>
              <div className="modal-subtitle">เลือก Pokemon ที่จะรับพลังงาน {cp.energy_type}</div>
              {targets.map((t, i) => (
                <div key={i} className="attach-energy-option" onClick={() => handleAttachEnergy(t.pos, t.idx)}>
                  <img src={`/picture/${t.p.card_id}.webp`} alt={t.p.name} />
                  <div>
                    <div className="name">{t.p.name}</div>
                    <div className="pos">{t.pos === 'active' ? 'Active' : `Bench #${t.idx + 1}`}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Evolve Target Modal */}
      {showEvolveTarget && (
        <div className="modal-overlay" onClick={() => setShowEvolveTarget(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-title">✨ เลือกเป้าหมายวิวัฒนาการ</div>
            <div className="modal-subtitle">จะวิวัฒนาการ Pokemon ตัวไหน?</div>
            <div className="modal-cards">
              {showEvolveTarget.targets.map((t, i) => (
                <div key={i} style={{ textAlign: 'center', cursor: 'pointer' }} onClick={() => handleEvolve(t)}>
                  <img
                    src={`/picture/${t.pokemon.card_id}.webp`}
                    alt={t.pokemon.name}
                    className="modal-card"
                  />
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
                    {t.position === 'active' ? 'Active' : `Bench #${t.index + 1}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showTrainerTarget && (
        <div className="modal-overlay" onClick={() => setShowTrainerTarget(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-title">{showTrainerTarget.title}</div>
            <div className="modal-subtitle">{showTrainerTarget.subtitle}</div>
            <div className="modal-cards">
              {showTrainerTarget.targets.map((target) => (
                <div
                  key={`${target.position}-${target.index}`}
                  style={{ textAlign: 'center', cursor: 'pointer' }}
                  onClick={() => handleTrainerTarget(target)}
                >
                  <img
                    src={`/picture/${target.pokemon.card_id}.webp`}
                    alt={target.pokemon.name}
                    className="modal-card"
                  />
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
                    {target.position === 'active' ? 'Active' : `Bench #${target.index + 1}`}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--accent-gold)', marginTop: 2 }}>
                    HP {target.pokemon.current_hp}/{target.pokemon.max_hp}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showAttackTarget && (
        <div className="modal-overlay" onClick={() => setShowAttackTarget(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-title">{showAttackTarget.title}</div>
            <div className="modal-subtitle">{showAttackTarget.subtitle}</div>
            <div className="modal-cards">
              {showAttackTarget.targets.map((target) => (
                <div
                  key={`${target.position}-${target.index}`}
                  style={{ textAlign: 'center', cursor: 'pointer' }}
                  onClick={() => handleAttackTarget(target)}
                >
                  <img
                    src={`/picture/${target.pokemon.card_id}.webp`}
                    alt={target.pokemon.name}
                    className="modal-card"
                  />
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
                    {target.position === 'active' ? 'Active' : `Bench #${target.index + 1}`}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--accent-gold)', marginTop: 2 }}>
                    HP {target.pokemon.current_hp}/{target.pokemon.max_hp}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Inferno Dance Target Modal */}
      {showInfernoDanceTarget && (
        <div className="modal-overlay" onClick={showInfernoDanceTarget.playerName === 'Goopy AI' ? undefined : () => setShowInfernoDanceTarget(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Inferno Dance: เลือกเป้าหมาย Bench</div>
            <div className="modal-subtitle">เลือก Fire Pokemon ที่จะรับพลังงาน (หัวจะติดให้ตามจำนวนหัว)</div>
            {showInfernoDanceTarget.playerName === 'Goopy AI' && (
              <div style={{ marginTop: -2, marginBottom: 10, color: 'var(--accent-psychic)', fontSize: 12, textAlign: 'center' }}>
                Goopy AI กำลังเลือกเป้าหมายอัตโนมัติ...
              </div>
            )}
            <div className="modal-cards">
              {showInfernoDanceTarget.targets.map((bp) => (
                <div
                  key={bp.idx}
                  style={{ textAlign: 'center', cursor: showInfernoDanceTarget.playerName === 'Goopy AI' ? 'default' : 'pointer' }}
                  onClick={() => handleInfernoDanceTarget(bp.idx)}
                >
                  <img
                    src={`/picture/${bp.card_id}.webp`}
                    alt={bp.name}
                    className="modal-card"
                  />
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>{bp.name}</div>
                  <div style={{ fontSize: 10, color: 'var(--accent-gold)', marginTop: 2 }}>
                    เลือกแล้ว {infernoDanceSelections.filter((i) => i === bp.idx).length} ครั้ง
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 10, textAlign: 'center', display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button className="utility-btn" disabled={showInfernoDanceTarget.playerName === 'Goopy AI'} onClick={handleInfernoDanceUndo}>
                ย้อนกลับ 1 ครั้ง
              </button>
              <button className="utility-btn" disabled={showInfernoDanceTarget.playerName === 'Goopy AI'} onClick={handleInfernoDanceConfirm}>
                ยืนยัน ({infernoDanceSelections.length}/{showInfernoDanceTarget.selectionCount})
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Promote Modal — only show interactively to the human player */}
      {promotingPlayer && promotingPlayer.name !== 'Goopy AI' && (
        <div className="modal-overlay">
          <div className="modal-box">
            <div className="modal-title">⚔️ เลือก Pokemon ขึ้น Active!</div>
            <div className="modal-subtitle">{promotingPlayer.name}: Active ถูก KO แล้ว เลือก Pokemon จาก Bench</div>
            <div className="modal-cards">
              {promotingPlayer.bench.map((bp, idx) => (
                <div key={idx} style={{ textAlign: 'center', cursor: 'pointer' }} onClick={() => handlePromote(idx)}>
                  <img
                    src={`/picture/${bp.card_id}.webp`}
                    alt={bp.name}
                    className="modal-card"
                  />
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>{bp.name}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {/* AI Promote — just show a waiting message, AI will auto-promote */}
      {promotingPlayer && promotingPlayer.name === 'Goopy AI' && (
        <div className="modal-overlay">
          <div className="modal-box" style={{ textAlign: 'center', padding: '30px 40px' }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>🧠</div>
            <div className="modal-title">Goopy AI กำลังเลือก Pokemon...</div>
            <div className="modal-subtitle" style={{ color: 'var(--accent-psychic)' }}>กรุณารอ AI เลือก Pokemon ขึ้น Active</div>
          </div>
        </div>
      )}

      {/* Game Over */}
      {game_over && (
        <div className="game-over-overlay">
          <div className="game-over-box">
            <div className="game-over-title">GAME OVER</div>
            <div className="game-over-winner">🏆 {winner} เป็นผู้ชนะ!</div>
            <button className="btn-new-game" onClick={async () => {
              setGameState(null);
              setShowStartSetup(true);
            }}>
              🔄 เริ่มเกมใหม่
            </button>
          </div>
        </div>
      )}
    </div>
  );
}