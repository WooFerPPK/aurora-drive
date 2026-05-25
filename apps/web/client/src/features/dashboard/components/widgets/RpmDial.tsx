// client/src/components/widgets/RpmDial.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { ease, valueColour, drawSparks } from '@/shared/lib/canvasUtils'
import {
  drawRadialGauge,
  BigNumber,
  useThresholdFlash, stepThresholdFlash,
  EASE_VALUE, EASE_STALE,
} from '@/shared/components/widgetPrimitives'
import type { BigNumberValueOut } from '@/shared/components/widgetPrimitives/BigNumber'

const START_RAD   = (135 * Math.PI) / 180
const SWEEP_RAD   = (270 * Math.PI) / 180
const REDLINE_PCT = 0.875

const SHIFT_LABEL =
  'absolute bottom-3.5 left-1/2 -translate-x-1/2 ' +
  'font-display font-bold text-[16px] [letter-spacing:0.22em] text-pink ' +
  'opacity-0 [text-shadow:0_0_10px_var(--pink)] ' +
  '[transition:opacity_100ms_ease] pointer-events-none ' +
  'data-[active=true]:opacity-100'

export interface RpmDialProps {
  w: number
  h: number
}

export default function RpmDial({ w, h }: RpmDialProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const valueEaseRef = useRef(0)
  const staleFadeRef = useRef(0)
  const flashRef     = useThresholdFlash({ decayMs: 400 })
  const shiftRef     = useRef<HTMLSpanElement>(null)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale   = !frame || (frameAgeMs ?? 0) > 1500
    const maxRpm  = stale ? 8000 : (frame!.engine?.maxRpm  ?? 8000)
    const idleRpm = stale ? 900  : (frame!.engine?.idleRpm ?? 900)
    const rpm     = stale ? 0    : (frame!.engine?.rpm     ?? 0)
    const v01     = Math.max(0, Math.min(1, (rpm - idleRpm) / Math.max(1, maxRpm - idleRpm)))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    valueEaseRef.current = ease(valueEaseRef.current, v01,           dt, EASE_VALUE)
    const cur = valueEaseRef.current

    stepThresholdFlash(flashRef, tier === 'hero' && cur > REDLINE_PCT, dt)

    if (shiftRef.current) {
      shiftRef.current.dataset['active'] = flashRef.current.intensity > 0 ? 'true' : 'false'
    }

    const cx = cw / 2, cy = ch / 2 + 2
    const r  = Math.min(cw, ch) * (tier === 'hero' ? 0.46 : 0.40) - 10

    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45
    drawRadialGauge(ctx, {
      cx, cy, r,
      startRad: START_RAD, sweepRad: SWEEP_RAD,
      value: cur,
      tier,
      tickMax: Math.round(maxRpm / 1000),
      redlinePct: REDLINE_PCT,
      ramp: 'intensity',
    })

    if (flashRef.current.intensity > 0) {
      drawSparks(ctx, cx, cy, flashRef.current.intensity, valueColour(cur), {
        innerR: r + 8, outerR: r + 28, count: 14,
      })
    }

    ctx.globalAlpha = 1
  })

  const numberGetter = (frame: Frame | null): BigNumberValueOut | null => {
    if (!frame) return null
    const maxRpm  = frame.engine?.maxRpm  ?? 8000
    const idleRpm = frame.engine?.idleRpm ?? 900
    const rpm     = frame.engine?.rpm     ?? 0
    return {
      display:    (rpm / 1000).toFixed(1),
      normalized: Math.max(0, Math.min(1, (rpm - idleRpm) / Math.max(1, maxRpm - idleRpm))),
    }
  }

  return (
    <div className="radial-gauge-wrap rpm-dial-wrap">
      <canvas ref={canvasRef} className="widget-canvas rpm-dial" />
      <BigNumber tier={tier} getValue={numberGetter} unit="RPM ×1000" />
      {tier === 'hero' && <span ref={shiftRef} className={SHIFT_LABEL} data-active="false">SHIFT</span>}
    </div>
  )
}
