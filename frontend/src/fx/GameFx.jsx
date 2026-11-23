import { useEffect, useRef, useState } from 'react'
import { createParticles } from './particles'
import { sfx } from './sfx'
import './fx.css'

/*
 * Visual + audio feedback layer. It never changes game state: it compares each
 * new backend state with the previous one and plays effects for what changed.
 * Board elements are located via data-player="<name>" on each .player-field.
 */

const fieldOf = (name) => document.querySelector(`[data-player="${CSS.escape(name)}"]`)
const centerOf = (el) => {
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
}
const activeEl = (name) => {
  const f = fieldOf(name)
  return f?.querySelector('.active-card-wrapper') || f?.querySelector('.active-zone') || null
}
const benchEl = (name, i) => fieldOf(name)?.querySelectorAll('.bench-card-slot')[i] || null
const restartClass = (el, cls, ms = 600) => {
  if (!el) return
  el.classList.remove(cls)
  void el.offsetWidth
  el.classList.add(cls)
  setTimeout(() => el.classList.remove(cls), ms)
}
const energyCount = (p) => (p?.attached_energy?.length || 0)

function diff(prev, next) {
  const events = []
  if (!prev || !next) return events
  const keys = ['player_1', 'player_2']
  for (const k of keys) {
    const a = prev[k], b = next[k]
    if (!a || !b) continue
    const other = next[k === 'player_1' ? 'player_2' : 'player_1']
    const pa = a.active_pokemon, pb = b.active_pokemon

    // Active: damage / heal / new card / evolution
    if (pa && pb && pa.card_id === pb.card_id) {
      const d = pb.current_hp - pa.current_hp
      if (d < 0) events.push({ t: 'damage', who: b.name, slot: 'active', amount: -d, by: other?.name, byType: other?.energy_type })
      if (d > 0) events.push({ t: 'heal', who: b.name, slot: 'active', amount: d })
    } else if (pb && (!pa || pa.card_id !== pb.card_id)) {
      events.push({ t: 'play', who: b.name, slot: 'active', type: b.energy_type })
    }
    if (pa && pb && pa.card_id === pb.card_id && energyCount(pb) > energyCount(pa)) {
      events.push({ t: 'energy', who: b.name, slot: 'active', type: b.energy_type })
    }

    // Bench
    const ba = a.bench || [], bb = b.bench || []
    bb.forEach((m, i) => {
      const o = ba[i]
      if (o && o.card_id === m.card_id) {
        const d = m.current_hp - o.current_hp
        if (d < 0) events.push({ t: 'damage', who: b.name, slot: i, amount: -d, by: other?.name, byType: other?.energy_type })
        if (d > 0) events.push({ t: 'heal', who: b.name, slot: i, amount: d })
        if (energyCount(m) > energyCount(o)) events.push({ t: 'energy', who: b.name, slot: i, type: b.energy_type })
      } else if (o && bb.length === ba.length) {
        events.push({ t: 'play', who: b.name, slot: i, type: b.energy_type }) // evolved in place
      }
    })
    if (bb.length > ba.length) events.push({ t: 'play', who: b.name, slot: bb.length - 1, type: b.energy_type })

    // Prize points gained => the other side's Pokemon was knocked out
    if ((b.points || 0) > (a.points || 0) && other) {
      events.push({ t: 'ko', who: other.name, scorer: b.name, type: b.energy_type })
    }
  }

  // turn_number check catches a whole AI turn that finished between two polls
  const turnChanged = next.current_turn !== prev.current_turn || next.turn_number !== prev.turn_number
  if (!next.setup_phase && next.current_turn && turnChanged && !next.game_over) {
    events.push({ t: 'turn', who: next.current_turn })
  }
  if (next.game_over && !prev.game_over) events.push({ t: 'over', winner: next.winner })
  return events
}

export default function GameFx({ state, humanName = null }) {
  const canvasRef = useRef(null)
  const partsRef = useRef(null)
  const prevRef = useRef(null)
  const [floats, setFloats] = useState([])
  const [banner, setBanner] = useState(null)
  const [muted, setMuted] = useState(sfx.isMuted())
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    partsRef.current = createParticles(canvasRef.current)
    return () => partsRef.current?.destroy()
  }, [])

  const float = (pt, text, kind) => {
    if (!pt) return
    const id = Math.random().toString(36).slice(2)
    setFloats((f) => [...f, { id, x: pt.x, y: pt.y, text, kind }])
    setTimeout(() => setFloats((f) => f.filter((x) => x.id !== id)), 1300)
  }

  // React to state changes
  useEffect(() => {
    const prev = prevRef.current
    prevRef.current = state
    if (!state || !prev) return
    if ((state.turn_number || 0) < (prev.turn_number || 0)) return // new game
    const events = diff(prev, state)
    const P = partsRef.current
    let delay = 0

    for (const e of events) {
      const run = () => {
        const target = e.slot === 'active' ? activeEl(e.who) : typeof e.slot === 'number' ? benchEl(e.who, e.slot) : null
        const pt = centerOf(target)
        switch (e.t) {
          case 'damage': {
            const big = e.amount >= 60
            const attacker = e.by ? activeEl(e.by) : null
            const apt = centerOf(attacker)
            if (attacker && apt && pt) {
              attacker.style.setProperty('--lunge-y', `${Math.sign(pt.y - apt.y) * 26}px`)
              restartClass(attacker, 'fx-lunge', 420)
            }
            setTimeout(() => {
              restartClass(target, 'fx-hit', 500)
              if (pt) {
                if (e.byType === 'lightning' && apt) P.zap(apt.x, apt.y, pt.x, pt.y)
                P.impact(pt.x, pt.y, e.byType, big)
                float(pt, `-${e.amount}`, big ? 'dmg big' : 'dmg')
              }
              if (big) restartClass(document.querySelector('.game-container'), 'fx-shake', 450)
              sfx.hit(big)
            }, 170)
            break
          }
          case 'heal':
            if (pt) { P.sparkle(pt.x, pt.y, 'grass'); float(pt, `+${e.amount}`, 'heal') }
            sfx.heal()
            break
          case 'play':
            restartClass(target, 'fx-pop', 500)
            if (pt) P.sparkle(pt.x, pt.y, e.type, 12)
            sfx.play()
            break
          case 'energy':
            restartClass(target, 'fx-charge', 700)
            if (pt) P.ring(pt.x, pt.y, e.type, 40)
            sfx.energy()
            break
          case 'ko': {
            const kpt = centerOf(activeEl(e.who))
            if (kpt) {
              P.burst(kpt.x, kpt.y, 'colorless', { count: 60, speed: 9, life: 50 })
              P.impact(kpt.x, kpt.y, e.type, true)
              float(kpt, 'KO!', 'ko')
            }
            restartClass(document.querySelector('.game-container'), 'fx-shake', 450)
            const prize = fieldOf(e.scorer)?.querySelector('.prize-cards-display')
            restartClass(prize, 'fx-prize', 900)
            sfx.ko()
            break
          }
          case 'turn': {
            const mine = humanName && e.who === humanName
            setBanner({ id: Date.now(), text: mine ? 'ตาของคุณ!' : `ตาของ ${e.who}`, kind: mine ? 'mine' : 'theirs' })
            setTimeout(() => setBanner(null), 1500)
            sfx.turn()
            break
          }
          case 'over': {
            const won = !humanName || e.winner === humanName
            if (won) { P.confetti(); sfx.win() } else { P.ash(); sfx.lose() }
            break
          }
          default:
        }
      }
      setTimeout(run, delay)
      delay += e.t === 'damage' || e.t === 'ko' ? 380 : 120
    }
  }, [state, humanName])

  // Hover any face-up card for 0.45s to see it large
  useEffect(() => {
    let timer = 0
    const SEL = 'img.active-card, img.bench-card-img, .hand-card img:not(.card-back-img)'
    const over = (ev) => {
      const img = ev.target.closest?.(SEL)
      if (!img) return
      clearTimeout(timer)
      timer = setTimeout(() => {
        const r = img.getBoundingClientRect()
        const left = r.left + r.width / 2 < window.innerWidth / 2
        setPreview({ src: img.getAttribute('src'), left })
      }, 450)
    }
    const out = (ev) => {
      if (ev.target.closest?.(SEL)) { clearTimeout(timer); setPreview(null) }
    }
    const down = () => { clearTimeout(timer); setPreview(null) }
    document.addEventListener('mouseover', over)
    document.addEventListener('mouseout', out)
    document.addEventListener('mousedown', down)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('mouseover', over)
      document.removeEventListener('mouseout', out)
      document.removeEventListener('mousedown', down)
    }
  }, [])

  return (
    <>
      <canvas ref={canvasRef} className="fx-canvas" />
      {floats.map((f) => (
        <div key={f.id} className={`fx-float ${f.kind}`} style={{ left: f.x, top: f.y }}>{f.text}</div>
      ))}
      {banner && (
        <div key={banner.id} className={`fx-banner ${banner.kind}`}><span>{banner.text}</span></div>
      )}
      {preview && (
        <div className={`fx-preview ${preview.left ? 'right' : 'left'}`}>
          <img src={preview.src} alt="" />
        </div>
      )}
      <button
        className="fx-mute"
        title={muted ? 'เปิดเสียง' : 'ปิดเสียง'}
        onClick={() => { sfx.setMuted(!muted); setMuted(!muted) }}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M11 5 6 9H2v6h4l5 4V5z" fill="currentColor" />
          {muted
            ? <path d="m23 9-6 6M17 9l6 6" />
            : <path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14" />}
        </svg>
      </button>
    </>
  )
}
