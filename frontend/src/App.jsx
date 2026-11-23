import { useState, useCallback } from 'react'
import './App.css'
import GameBoard from './GameBoard'
import SelfPlayBoard from './SelfPlayBoard'
import './theme/playmat.css'

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function App() {
  const [mode, setMode] = useState(null)
  const [showExitConfirm, setShowExitConfirm] = useState(false)

  const handleBackRequest = () => {
    setShowExitConfirm(true)
  }

  const handleConfirmExit = useCallback(async () => {
    setShowExitConfirm(false)
    try {
      await fetch(`${API}/api/reset`, { method: 'POST' })
    } catch {
      // ignore
    }
    setMode(null)
  }, [])

  const handleCancelExit = () => {
    setShowExitConfirm(false)
  }

  // ── Mode Selection Screen ──
  if (!mode) {
    return (
      <div className="mode-selection-screen">
        <div className="branding-container">
          <h1 className="main-title">Pocket <span>Duelist</span></h1>
          <p className="subtitle">Pokemon TCG Pocket Simulation</p>
        </div>

        <div className="menu-cards">
          <button className="menu-card true-ai" onClick={() => setMode('true_ai')}>
            <span className="menu-card-badge">BATTLE</span>
            <img src="/picture/cross.png" className="menu-icon" alt="Fight AI" />
            <h2>สู้กับ AI</h2>
            <p>Battle แบบปกติ ซ่อนหน้าตักของ AI</p>
          </button>

          <button className="menu-card debug-ai" onClick={() => setMode('ai_debug')}>
            <span className="menu-card-badge">DEBUG</span>
            <img src="/picture/gear.png" className="menu-icon" alt="Debug AI" />
            <h2>ทดสอบระบบ AI</h2>
            <p>เปิดหน้าตักและดูความคิดของบอท</p>
          </button>

          <button className="menu-card self-play" onClick={() => setMode('selfplay')}>
            <span className="menu-card-badge">2P LOG</span>
            <img src="/picture/2p.png" className="menu-icon" alt="Play 2 Sides" />
            <h2>เล่น 2 ฝั่ง (เก็บ Log)</h2>
            <p>ควบคุมทั้ง 2 ผู้เล่นเพื่อเก็บข้อมูล</p>
          </button>
        </div>
      </div>
    )
  }

  // ── In-Game Screen ──
  const isTrueBattle = mode === 'true_ai'

  return (
    <div style={{ minHeight: '100vh', position: 'relative' }}>
      {(mode === 'true_ai' || mode === 'ai_debug')
        ? <GameBoard isTrueBattle={isTrueBattle} mode={mode} onBack={handleBackRequest} />
        : <SelfPlayBoard mode={mode} onBack={handleBackRequest} />
      }

      {/* ── Exit Confirmation Dialog ── */}
      {showExitConfirm && (
        <div className="exit-confirm-overlay" onClick={handleCancelExit}>
          <div className="exit-confirm-box" onClick={e => e.stopPropagation()}>
            <h2 className="exit-confirm-title">ออกจากเกม?</h2>
            <p className="exit-confirm-msg">
              เกมที่กำลังเล่นอยู่จะถูกลบทิ้ง<br />
              คุณแน่ใจที่จะกลับหน้าหลักไหม?
            </p>
            <div className="exit-confirm-buttons">
              <button className="exit-btn-cancel" onClick={handleCancelExit}>
                ยกเลิก — เล่นต่อ
              </button>
              <button className="exit-btn-confirm" onClick={handleConfirmExit}>
                ยืนยัน — ออกเกม
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
