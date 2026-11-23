// Tiny synthesized sound effects (WebAudio) — no audio files needed.
let ctx = null
let muted = false
try { muted = localStorage.getItem('pd-muted') === '1' } catch { /* storage unavailable */ }

function ac() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) return null
    ctx = new AC()
  }
  if (ctx.state === 'suspended') ctx.resume()
  return ctx
}

function tone({ freq = 440, to = freq, dur = 0.12, type = 'square', vol = 0.08, delay = 0 }) {
  const a = ac()
  if (!a || muted) return
  const t = a.currentTime + delay
  const o = a.createOscillator()
  const g = a.createGain()
  o.type = type
  o.frequency.setValueAtTime(freq, t)
  o.frequency.exponentialRampToValueAtTime(Math.max(20, to), t + dur)
  g.gain.setValueAtTime(vol, t)
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur)
  o.connect(g).connect(a.destination)
  o.start(t)
  o.stop(t + dur + 0.02)
}

function noise({ dur = 0.15, vol = 0.12, delay = 0, hp = 800 }) {
  const a = ac()
  if (!a || muted) return
  const t = a.currentTime + delay
  const buf = a.createBuffer(1, Math.floor(a.sampleRate * dur), a.sampleRate)
  const d = buf.getChannelData(0)
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length)
  const src = a.createBufferSource()
  src.buffer = buf
  const f = a.createBiquadFilter()
  f.type = 'highpass'
  f.frequency.value = hp
  const g = a.createGain()
  g.gain.value = vol
  src.connect(f).connect(g).connect(a.destination)
  src.start(t)
}

export const sfx = {
  hit(big) {
    noise({ dur: big ? 0.28 : 0.14, vol: big ? 0.18 : 0.1, hp: big ? 300 : 900 })
    tone({ freq: big ? 220 : 330, to: 60, dur: big ? 0.25 : 0.12, type: 'square', vol: 0.06 })
  },
  heal() {
    tone({ freq: 520, to: 780, dur: 0.15, type: 'triangle', vol: 0.06 })
    tone({ freq: 780, to: 1040, dur: 0.15, type: 'triangle', vol: 0.05, delay: 0.08 })
  },
  ko() {
    noise({ dur: 0.45, vol: 0.16, hp: 200 })
    tone({ freq: 440, to: 55, dur: 0.5, type: 'sawtooth', vol: 0.07 })
  },
  play() { tone({ freq: 300, to: 600, dur: 0.08, type: 'triangle', vol: 0.06 }) },
  energy() {
    tone({ freq: 660, dur: 0.06, type: 'square', vol: 0.04 })
    tone({ freq: 990, dur: 0.08, type: 'square', vol: 0.04, delay: 0.05 })
  },
  turn() {
    tone({ freq: 392, dur: 0.09, type: 'triangle', vol: 0.06 })
    tone({ freq: 523, dur: 0.12, type: 'triangle', vol: 0.06, delay: 0.09 })
  },
  win() {
    ;[523, 659, 784, 1047].forEach((f, i) => tone({ freq: f, dur: 0.18, type: 'square', vol: 0.06, delay: i * 0.12 }))
  },
  lose() {
    ;[392, 330, 262, 196].forEach((f, i) => tone({ freq: f, dur: 0.25, type: 'triangle', vol: 0.06, delay: i * 0.18 }))
  },
  isMuted: () => muted,
  setMuted(v) {
    muted = v
    try { localStorage.setItem('pd-muted', v ? '1' : '0') } catch { /* ignore */ }
  },
}
