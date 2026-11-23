// Pixel-style particle system drawn on one full-screen canvas.
const PX = 3 // pixel grid

export const TYPE_COLORS = {
  fire: ['#ff3d00', '#ff8a00', '#ffd23f', '#fff1a8'],
  psychic: ['#a855f7', '#d8b4fe', '#f472b6', '#7c3aed'],
  lightning: ['#ffe600', '#fff7a1', '#7dd3fc', '#ffffff'],
  water: ['#38bdf8', '#93c5fd', '#e0f2fe', '#2563eb'],
  grass: ['#22c55e', '#86efac', '#bef264', '#15803d'],
  colorless: ['#e5e7eb', '#cbd5e1', '#ffffff', '#94a3b8'],
}
const colorsFor = (type) => TYPE_COLORS[type] || TYPE_COLORS.colorless
const pick = (a) => a[(Math.random() * a.length) | 0]
const snap = (v) => Math.round(v / PX) * PX

export function createParticles(canvas) {
  const g = canvas.getContext('2d')
  let parts = []
  let raf = 0

  const resize = () => {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
  }
  resize()
  window.addEventListener('resize', resize)

  const loop = () => {
    g.clearRect(0, 0, canvas.width, canvas.height)
    parts = parts.filter((p) => p.life > 0)
    for (const p of parts) {
      p.vy += p.grav
      p.vx *= p.drag
      p.vy *= p.drag
      p.x += p.vx
      p.y += p.vy
      p.life -= 1
      if (p.rot) p.angle += p.rot
      g.globalAlpha = Math.min(1, p.life / p.fade)
      g.fillStyle = p.color
      const s = p.size
      if (p.rot) {
        g.save()
        g.translate(snap(p.x), snap(p.y))
        g.rotate(p.angle)
        g.fillRect(-s / 2, -s / 4, s, s / 2)
        g.restore()
      } else {
        g.fillRect(snap(p.x) - s / 2, snap(p.y) - s / 2, s, s)
      }
    }
    g.globalAlpha = 1
    raf = parts.length ? requestAnimationFrame(loop) : 0
  }
  const kick = () => { if (!raf) raf = requestAnimationFrame(loop) }

  const add = (p) => {
    parts.push({ grav: 0, drag: 0.96, fade: 18, angle: 0, rot: 0, size: PX * 2, ...p })
  }

  const api = {
    burst(x, y, type, { count = 28, speed = 6, grav = 0.18, life = 40 } = {}) {
      const cols = colorsFor(type)
      for (let i = 0; i < count; i++) {
        const a = Math.random() * Math.PI * 2
        const v = speed * (0.35 + Math.random())
        add({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, grav, life: life * (0.6 + Math.random() * 0.6),
          color: pick(cols), size: PX * (1 + ((Math.random() * 3) | 0)) })
      }
      kick()
    },
    // type-flavoured attack impact
    impact(x, y, type, big) {
      const n = big ? 46 : 26
      if (type === 'fire') {
        api.burst(x, y, type, { count: n, speed: big ? 7 : 5, grav: -0.12, life: 46 })
      } else if (type === 'psychic') {
        api.burst(x, y, type, { count: n, speed: 3.5, grav: -0.05, life: 55 })
        api.ring(x, y, type, big ? 70 : 50)
      } else if (type === 'lightning') {
        api.burst(x, y, type, { count: n, speed: big ? 9 : 7, grav: 0.1, life: 26 })
      } else {
        api.burst(x, y, type, { count: n, speed: 6 })
      }
    },
    ring(x, y, type, radius = 50) {
      const cols = colorsFor(type)
      const n = 32
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2
        add({ x, y, vx: Math.cos(a) * radius / 14, vy: Math.sin(a) * radius / 14, drag: 0.88,
          life: 26, color: pick(cols), size: PX * 2 })
      }
      kick()
    },
    // jagged pixel bolt between two points
    zap(x1, y1, x2, y2, type = 'lightning') {
      const cols = colorsFor(type)
      const steps = 22
      let ox = 0
      for (let i = 0; i <= steps; i++) {
        const t = i / steps
        ox += (Math.random() - 0.5) * 22
        ox *= 0.7
        const nx = -(y2 - y1), ny = x2 - x1
        const len = Math.hypot(nx, ny) || 1
        const x = x1 + (x2 - x1) * t + (nx / len) * ox
        const y = y1 + (y2 - y1) * t + (ny / len) * ox
        add({ x, y, vx: 0, vy: 0, life: 14 + Math.random() * 6, fade: 8, color: pick(cols), size: PX * 2 })
      }
      kick()
    },
    sparkle(x, y, type, count = 14) {
      api.burst(x, y, type, { count, speed: 2.5, grav: -0.06, life: 34 })
    },
    confetti(colors = ['#f87171', '#fbbf24', '#34d399', '#60a5fa', '#a78bfa', '#f472b6']) {
      const w = canvas.width
      for (let i = 0; i < 160; i++) {
        add({ x: Math.random() * w, y: -20 - Math.random() * 300, vx: (Math.random() - 0.5) * 2, vy: 2 + Math.random() * 3,
          grav: 0.04, drag: 0.995, life: 220, fade: 40, color: pick(colors), size: PX * 3,
          rot: (Math.random() - 0.5) * 0.3 })
      }
      kick()
    },
    ash() {
      const w = canvas.width
      for (let i = 0; i < 90; i++) {
        add({ x: Math.random() * w, y: -10 - Math.random() * 300, vx: (Math.random() - 0.5) * 0.6, vy: 0.8 + Math.random(),
          grav: 0.005, drag: 1, life: 260, fade: 60, color: pick(['#4b5563', '#6b7280', '#374151']), size: PX * 2 })
      }
      kick()
    },
    destroy() {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    },
  }
  return api
}
