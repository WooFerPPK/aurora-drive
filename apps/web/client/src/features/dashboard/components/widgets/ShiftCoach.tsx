// client/src/components/widgets/ShiftCoach.tsx
import { useEffect, useRef, useState } from 'react'
import type { ShiftRecommendation } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { liveClient } from '@/shared/lib/wsClient'
import { api } from '@/shared/lib/api'
import { cx } from '@/shared/lib/format'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB, toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'

const WRAP = 'relative w-full h-full'

const CANVAS_ABS = 'widget-canvas absolute inset-0 rounded-[inherit]'

const MISSED_BLOCK = 'absolute top-1 right-2.5 flex flex-col items-end z-[1] pointer-events-none'

const MISSED_LBL_BASE = 'font-display font-normal text-[12px] [letter-spacing:0.18em] text-ink-faint'
const MISSED_LBL_STANDARD = 'text-[14px]'
const MISSED_LBL_HERO = 'text-[16px]'

const MISSED_VAL_BASE =
  'font-mono font-bold text-[14px] text-cream [font-variant-numeric:tabular-nums] ' +
  '[text-shadow:0_0_8px_color-mix(in_srgb,var(--pink)_40%,transparent)]'
const MISSED_VAL_HERO = 'text-[18px]'

const LEARNING_BASE =
  'absolute bottom-1.5 left-2.5 font-mono font-normal text-[10px] text-ink-faint [letter-spacing:0.06em] ' +
  'z-[1] pointer-events-none'
const LEARNING_HERO = 'text-[11px]'

const RESET_BTN =
  'absolute bottom-1.5 right-2.5 font-mono font-normal text-[10px] [letter-spacing:0.08em] text-ink-faint ' +
  '[background:color-mix(in_srgb,var(--ink-faint)_8%,transparent)] ' +
  'border border-[color:color-mix(in_srgb,var(--ink-faint)_20%,transparent)] ' +
  'rounded px-2 py-px cursor-pointer z-[2] ' +
  '[transition:background_0.15s_ease,color_0.15s_ease] ' +
  'enabled:hover:text-cream enabled:hover:[background:color-mix(in_srgb,var(--pink)_15%,transparent)] ' +
  'disabled:opacity-40 disabled:cursor-default'

const CHROME_BASE = 'absolute top-[22px] right-2.5 flex items-center gap-1 z-[1] pointer-events-none'
const CHROME_HERO = 'top-[26px]'

const TRANS_CHIP =
  'inline-block font-mono font-semibold text-[11px] text-ink-dim ' +
  '[background:color-mix(in_srgb,var(--bg-1)_80%,transparent)] ' +
  'px-1.5 py-px rounded-lg [letter-spacing:0.08em] pointer-events-auto ' +
  'data-[mode=auto]:text-mint data-[mode=manual]:text-butter data-[mode=unknown]:text-ink-faint'

const ASSIST_BADGE =
  'inline-block font-mono font-semibold text-[11px] text-pink ' +
  '[background:color-mix(in_srgb,var(--pink)_12%,transparent)] ' +
  'px-2 py-px rounded-lg [letter-spacing:0.04em] pointer-events-auto'

// shift_coach — F1-style rev-light bar + learned shift recommendation marker.
//
// FR-050 adds downshift target, transmission-mode chip, and
// assist-intervention badge that the contract schema doesn't yet
// describe — model them as optional extensions here.

interface TransmissionMode {
  mode?: 'auto' | 'manual' | 'unknown'
  confidence?: number
}
interface AssistIntervention {
  active?: boolean
}
interface ShiftRecExt extends ShiftRecommendation {
  displayActiveDown?: boolean
  currentGearDownshiftTarget?: number | null
  currentGearDownshiftConfidence?: number
  transmissionMode?: TransmissionMode
  assistIntervention?: AssistIntervention
}

interface RecState {
  stage: ShiftRecommendation['stage']
  currentSamples: number
  requiredSamples: number
  gear: number | null
  target: number | null
  fingerprint: ShiftRecommendation['fingerprint'] | null
}

interface TransState {
  mode: 'auto' | 'manual' | 'unknown'
  conf: number
}

const LED_COUNT          = 15
const REDLINE_PCT        = 0.875
const TRAINING_THRESHOLD = 200

export interface ShiftCoachProps {
  w: number
  h: number
}

export default function ShiftCoach({ w, h }: ShiftCoachProps) {
  const tier = h <= 1 ? 'compact' : w >= 5 ? 'hero' : 'standard'

  const valueRef        = useRef(0)
  const staleFadeRef    = useRef(0)
  const missedCountRef  = useRef(0)
  const recommendationRef = useRef<ShiftRecExt | null>(null)
  const [missedDisplay, setMissedDisplay] = useState(0)
  const [recState, setRecState] = useState<RecState | null>(null)
  const [resetting, setResetting] = useState(false)
  const [transState, setTransState] = useState<TransState>({ mode: 'unknown', conf: 0 })
  const [assistActive, setAssistActive] = useState(false)

  useEffect(() => {
    const off = liveClient.subscribe('event', (evt) => {
      if (!evt) return
      if (evt.kind === 'missed_upshift') {
        missedCountRef.current++
        setMissedDisplay(missedCountRef.current)
      } else if (evt.kind === 'session_started') {
        missedCountRef.current = 0
        setMissedDisplay(0)
      }
    })
    return off
  }, [])

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, elapsed, frameAgeMs }) => {
    const stale   = !frame || (frameAgeMs ?? 0) > 1500
    const maxRpm  = stale ? 8000 : (frame!.engine?.maxRpm  ?? 8000)
    const idleRpm = stale ? 900  : (frame!.engine?.idleRpm ?? 900)
    const rpm     = stale ? 0    : (frame!.engine?.rpm     ?? 0)
    const v       = Math.max(0, Math.min(1, (rpm - idleRpm) / Math.max(1, maxRpm - idleRpm)))

    const rec = stale ? null : (frame!.modeled?.shiftRecommendation as ShiftRecExt | null ?? null)
    recommendationRef.current = rec

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)
    valueRef.current     = ease(valueRef.current, v, dt, 10)
    const cur = valueRef.current

    const displayActive = rec?.displayActive === true
    const target        = rec?.currentGearTarget ?? null
    const conf          = Math.max(0, Math.min(1, rec?.currentGearConfidence ?? 0))
    const flashAt       = displayActive && target != null
      ? Math.max(0, Math.min(1, (target - idleRpm) / Math.max(1, maxRpm - idleRpm)))
      : REDLINE_PCT
    const flash = cur > flashAt && Math.sin(elapsed * Math.PI * 8) > 0

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const pad     = 10
    const topPad  = tier === 'compact' ? 0 : 28
    const ledRow  = tier === 'compact' ? ch / 2 : topPad + (ch - topPad - 10) / 2
    const ledH    = Math.min(16, ch * (tier === 'compact' ? 0.5 : 0.32))
    const ledGap  = 2
    const ledRowW = cw - pad * 2
    const ledW    = (ledRowW - (LED_COUNT - 1) * ledGap) / LED_COUNT

    for (let i = 0; i < LED_COUNT; i++) {
      const ledV = (i + 0.5) / LED_COUNT
      const on   = flash || ledV < cur

      let col
      if (ledV < 0.33)      col = MINT_RGB
      else if (ledV < 0.66) col = BUTTER_RGB
      else                  col = PINK_RGB

      const x = pad + i * (ledW + ledGap)
      const y = ledRow - ledH / 2

      if (on) {
        ctx.fillStyle   = toRgb(col)
        ctx.shadowColor = toRgb(col)
        ctx.shadowBlur  = 8
        roundRectPath(ctx, x, y, ledW, ledH, 3); ctx.fill()
        ctx.shadowBlur = 0
      } else {
        ctx.fillStyle = toRgba(col, 0.12)
        roundRectPath(ctx, x, y, ledW, ledH, 3); ctx.fill()
      }
    }

    const downActive = rec?.displayActiveDown === true
    const downTarget = rec?.currentGearDownshiftTarget ?? null
    const downConf   = Math.max(0, Math.min(1, rec?.currentGearDownshiftConfidence ?? 0))
    if (downActive && downTarget != null) {
      const downPct = Math.max(0, Math.min(1, (downTarget - idleRpm) / Math.max(1, maxRpm - idleRpm)))
      const markerX = pad + downPct * ledRowW
      const bandHalfPx = Math.min(24, Math.max(2, 18 * (1 - downConf)))
      ctx.fillStyle = toRgba(BUTTER_RGB, 0.2)
      roundRectPath(ctx,
        markerX - bandHalfPx, ledRow - ledH / 2 - 2,
        bandHalfPx * 2, ledH + 4, 4,
      )
      ctx.fill()
      ctx.fillStyle   = C.butter
      ctx.shadowColor = C.butter
      ctx.shadowBlur  = 6
      const tickW = 2
      ctx.fillRect(markerX - tickW / 2, ledRow - ledH / 2 - 4, tickW, ledH + 8)
      ctx.shadowBlur = 0
    }

    if (displayActive && target != null) {
      const markerX = pad + flashAt * ledRowW
      const bandHalfPx = Math.min(24, Math.max(2, 18 * (1 - conf)))
      ctx.fillStyle = toRgba([253, 244, 220], 0.18)
      roundRectPath(ctx,
        markerX - bandHalfPx, ledRow - ledH / 2 - 2,
        bandHalfPx * 2, ledH + 4, 4,
      )
      ctx.fill()
      ctx.fillStyle   = C.cream
      ctx.shadowColor = C.cream
      ctx.shadowBlur  = 6
      const tickW = 3
      ctx.fillRect(markerX - tickW / 2, ledRow - ledH / 2 - 4, tickW, ledH + 8)
      ctx.shadowBlur = 0
    }

    if (tier !== 'compact') {
      const gear = stale ? null : (frame!.drivetrain?.gear ?? null)
      let gearText = '—'
      if (gear != null) {
        if (gear <= 0)       gearText = 'R'
        else if (gear <= 10) gearText = String(gear)
      }

      ctx.font         = `700 ${tier === 'hero' ? 22 : 18}px "Unbounded", system-ui, sans-serif`
      ctx.fillStyle    = C.cream
      ctx.textAlign    = 'left'
      ctx.textBaseline = 'top'
      ctx.shadowColor  = C.mint
      ctx.shadowBlur   = 10
      ctx.fillText(gearText, pad, 4)
      ctx.shadowBlur   = 0

      ctx.font      = `400 10px "JetBrains Mono", monospace`
      ctx.fillStyle = C.inkFaint
      ctx.fillText('GEAR', pad + (tier === 'hero' ? 32 : 28), 11)
    }

    if (tier === 'hero') {
      const shiftRpm = displayActive && target != null
        ? target
        : Math.round(maxRpm * REDLINE_PCT / 100) * 100
      ctx.font         = `400 11px "JetBrains Mono", monospace`
      ctx.fillStyle    = C.inkFaint
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'top'
      ctx.fillText(`SHIFT @ ${shiftRpm} RPM`, cw / 2, 8)
    }

    ctx.globalAlpha = 1
  })

  useEffect(() => {
    const id = setInterval(() => {
      const rec = recommendationRef.current
      if (rec == null) {
        if (recState != null) setRecState(null)
        if (transState.mode !== 'unknown' || transState.conf !== 0) {
          setTransState({ mode: 'unknown', conf: 0 })
        }
        if (assistActive) setAssistActive(false)
        return
      }
      const stage = rec.stage
      const target = rec.currentGearTarget
      const samples = rec.byGearSamples || {}
      const live = liveClient.getLatestFrame?.()
      const gear = live?.drivetrain?.gear ?? null
      const samp = gear != null ? (samples[String(gear)] ?? 0) : 0
      const next: RecState = {
        stage,
        currentSamples: samp,
        requiredSamples: TRAINING_THRESHOLD,
        gear,
        target,
        fingerprint: rec.fingerprint ?? null,
      }
      if (
        recState == null
        || recState.stage !== next.stage
        || recState.currentSamples !== next.currentSamples
        || recState.gear !== next.gear
      ) {
        setRecState(next)
      }

      const tm: TransState['mode'] = rec.transmissionMode?.mode ?? 'unknown'
      const tc = Math.max(0, Math.min(1, rec.transmissionMode?.confidence ?? 0))
      if (transState.mode !== tm || Math.abs(transState.conf - tc) > 0.02) {
        setTransState({ mode: tm, conf: tc })
      }

      const aa = rec.assistIntervention?.active === true
      if (aa !== assistActive) setAssistActive(aa)
    }, 1000)
    return () => clearInterval(id)
  }, [recState, transState, assistActive])

  const handleReset = async (): Promise<void> => {
    if (resetting) return
    const fp = recState?.fingerprint
    const fpDesc = fp != null
      ? `car ${fp['carOrdinal'] ?? '?'} (PI ${fp['performanceIndex'] ?? '?'})`
      : 'this car'
    if (!window.confirm(`Reset learned shift curve for ${fpDesc}?`)) return
    setResetting(true)
    try {
      await api.resetShift({ sessionId: 'live' })
    } finally {
      setResetting(false)
    }
  }

  const showLearning = tier !== 'compact'
    && recState != null
    && recState.stage !== 'learned'

  const showChrome = tier !== 'compact'
  const chipLabel = transState.mode === 'auto'
    ? 'AUTO'
    : transState.mode === 'manual'
      ? 'MANUAL'
      : '?'

  const missedLblCls = cx(MISSED_LBL_BASE, tier === 'standard' && MISSED_LBL_STANDARD, tier === 'hero' && MISSED_LBL_HERO)
  const missedValCls = cx(MISSED_VAL_BASE, tier === 'hero' && MISSED_VAL_HERO)

  return (
    <div className={WRAP}>
      <canvas ref={canvasRef} className={CANVAS_ABS} />
      {tier !== 'compact' && (
        <div className={MISSED_BLOCK}>
          <span className={missedLblCls}>MISSED</span>
          <span className={missedValCls}>{missedDisplay}</span>
        </div>
      )}
      {showChrome && (
        <div className={cx(CHROME_BASE, tier === 'hero' && CHROME_HERO)}>
          <span
            className={TRANS_CHIP}
            data-mode={transState.mode}
            title={`transmission ${transState.mode} · confidence ${(transState.conf * 100) | 0}%`}
          >
            {chipLabel}
          </span>
          {assistActive && (
            <span className={ASSIST_BADGE} title="Traction-control intervention detected in recent frames">
              TCS clipping detected
            </span>
          )}
        </div>
      )}
      {showLearning && recState && (
        <div className={cx(LEARNING_BASE, tier === 'hero' && LEARNING_HERO)}>
          {recState.stage === 'fallback'
            ? 'Using default'
            : `Gear ${recState.gear}→${(recState.gear ?? 0) + 1}: ${recState.currentSamples}/${recState.requiredSamples}`}
        </div>
      )}
      {tier === 'hero' && (
        <button
          type="button"
          className={RESET_BTN}
          onClick={handleReset}
          disabled={resetting}
          title="Reset learned shift curve"
        >
          {resetting ? '…' : 'Reset'}
        </button>
      )}
    </div>
  )
}
