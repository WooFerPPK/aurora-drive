import type { CSSProperties } from 'react'
import { useReplay } from '@/features/dashboard/context/ReplayContext'
import { useSession } from '@/features/sessions/context/SessionContext'
import { cx } from '@/shared/lib/format'

// Outer shell of the scrubber bar (pinned at the bottom of .app).
const SCRUBBER = 'flex-none flex items-center gap-3 px-4 py-[10px] bg-[linear-gradient(180deg,rgba(26,8,38,0.55)_0%,rgba(42,14,58,0.92)_100%)] border-t border-[rgba(255,193,220,0.22)] shadow-[0_-10px_36px_-20px_rgba(255,94,167,0.55),0_0_0_1px_rgba(255,193,220,0.10)_inset] backdrop-blur-[14px] backdrop-saturate-[1.4] relative z-10'
const LOADING_EXTRA = 'justify-center font-mono text-[12px]'
const TIME = 'font-mono text-[12px] text-ink min-w-[60px] text-center tabular-nums tracking-[0.5px]'

function formatT(seconds: number): string {
  let s = seconds
  if (!isFinite(s) || s < 0) s = 0
  const m = Math.floor(s / 60)
  const rem = s - m * 60
  return `${String(m).padStart(2, '0')}:${rem.toFixed(1).padStart(4, '0')}`
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="w-[14px] h-[14px]">
      <path d="M4 2.5v11l10-5.5z" fill="currentColor" />
    </svg>
  )
}

function PauseIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="w-[14px] h-[14px]">
      <rect x="3.5" y="2.5" width="3" height="11" fill="currentColor" />
      <rect x="9.5" y="2.5" width="3" height="11" fill="currentColor" />
    </svg>
  )
}

export default function ReplayScrubber() {
  const { active, loading, error, duration, t, playing, toggle, seek, loadedSessionId } = useReplay()
  const { clearLoadedSession } = useSession()

  if (!loadedSessionId) return null

  if (loading) {
    return (
      <div className={cx(SCRUBBER, LOADING_EXTRA)}>
        <span className="muted">Loading replay…</span>
      </div>
    )
  }

  if (error || !active) {
    return (
      <div className={cx(SCRUBBER, LOADING_EXTRA)}>
        <span className="muted">{error ? `Replay unavailable — ${error}` : 'No frames in this session.'}</span>
        <button type="button" className="btn ghost small flex-none ml-1" onClick={clearLoadedSession}>
          Exit
        </button>
      </div>
    )
  }

  const pct = duration > 0 ? Math.max(0, Math.min(100, (t / duration) * 100)) : 0
  const max = Math.max(0.001, duration)
  const trackStyle = { '--pct': `${pct}%` } as CSSProperties

  return (
    <div className={SCRUBBER}>
      <button
        type="button"
        className="w-8 h-8 rounded-full border border-[rgba(255,193,220,0.40)] bg-[linear-gradient(155deg,rgba(255,193,220,0.22),rgba(202,166,255,0.18))] text-cream cursor-pointer inline-flex items-center justify-center flex-none transition-[background,transform,box-shadow] duration-150 ease-in-out shadow-[0_0_12px_-4px_rgba(255,94,167,0.4)] hover:bg-[linear-gradient(155deg,rgba(255,193,220,0.36),rgba(202,166,255,0.30))] hover:shadow-[0_0_18px_-2px_rgba(255,94,167,0.65)] active:scale-[0.94]"
        onClick={toggle}
        aria-label={playing ? 'Pause replay' : 'Play replay'}
        title={playing ? 'Pause' : 'Play'}
      >
        {playing ? <PauseIcon /> : <PlayIcon />}
      </button>

      <div className={TIME}>{formatT(t)}</div>

      {/* `replay-track` class kept as marker — the input[type=range]
          vendor-pseudo-element track/thumb rules in index.css scope by
          this class so the slider keeps its custom skin. */}
      <div className="replay-track flex-1 relative flex items-center h-7 min-w-0" style={trackStyle}>
        <input
          type="range"
          min={0}
          max={max}
          step={0.05}
          value={t}
          onChange={(e) => seek(parseFloat(e.target.value))}
          aria-label="Replay scrubber position"
        />
      </div>

      <div className={cx(TIME, 'text-ink-faint')}>{formatT(duration)}</div>

      <button
        type="button"
        className="btn ghost small flex-none ml-1"
        onClick={clearLoadedSession}
        title="Exit replay"
      >
        Exit
      </button>
    </div>
  )
}
