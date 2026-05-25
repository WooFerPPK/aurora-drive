// client/src/components/widgets/GripBudget.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { ease } from '@/shared/lib/canvasUtils'
import {
  drawRadialGauge, drawLinearGauge,
  BigNumber,
  EASE_VALUE, EASE_STALE,
} from '@/shared/components/widgetPrimitives'
import type { BigNumberValueOut } from '@/shared/components/widgetPrimitives/BigNumber'

const START_RAD = (135 * Math.PI) / 180
const SWEEP_RAD = (270 * Math.PI) / 180

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
const CORNER_KEYS: readonly CornerKey[]   = ['fl', 'fr', 'rl', 'rr']
const CORNER_LABELS: readonly string[]    = ['FL', 'FR', 'RL', 'RR']

// `grip-budget-wrap` kept as marker for `.grip-budget-wrap .big-number.tier-hero` override.
const WRAP = 'grip-budget-wrap relative w-full h-full'

const CANVAS =
  'widget-canvas absolute inset-0 ' +
  '[background:radial-gradient(ellipse_at_50%_60%,color-mix(in_srgb,var(--mint)_10%,transparent)_0%,transparent_60%),radial-gradient(ellipse_at_50%_0%,color-mix(in_srgb,var(--butter)_8%,transparent)_0%,transparent_70%)] ' +
  '[box-shadow:inset_0_0_60px_-20px_color-mix(in_srgb,var(--bubblegum)_15%,transparent)]'

export interface GripBudgetProps {
  w: number
  h: number
}

export default function GripBudget({ w, h }: GripBudgetProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const usageEaseRef = useRef(0)
  const staleFadeRef = useRef(0)
  const cornersRef   = useRef(new Float32Array(4))

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const target = stale ? 0 : Math.min(1, Math.max(0, frame!.derived?.gripBudgetUsed ?? 0))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    usageEaseRef.current = ease(usageEaseRef.current, target, dt, EASE_VALUE)
    const u = usageEaseRef.current

    if (tier === 'hero' && frame?.wheels) {
      for (let i = 0; i < 4; i++) {
        const k = CORNER_KEYS[i]!
        const slip = Math.min(1, Math.abs(frame.wheels[k]?.combinedSlip ?? 0))
        cornersRef.current[i] = ease(cornersRef.current[i] ?? 0, stale ? 0 : slip, dt, EASE_VALUE)
      }
    }

    const heroBarReserve = tier === 'hero' ? 50 : 0
    const cy = (ch - heroBarReserve) / 2 + 8
    const cx = cw / 2
    const r  = Math.min(cw, ch - heroBarReserve) * (tier === 'hero' ? 0.46 : 0.40) - 10

    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    drawRadialGauge(ctx, {
      cx, cy, r,
      startRad: START_RAD, sweepRad: SWEEP_RAD,
      value: u,
      tier,
      tickMax: 100,
    })

    if (tier === 'hero') {
      const barY = ch - heroBarReserve + 8
      const barW = (cw - 32) / 4
      const barGap = 2
      const barH = 14
      for (let i = 0; i < 4; i++) {
        const x = 8 + i * (barW + barGap)
        drawLinearGauge(ctx, { x, y: barY, w: barW, h: barH, value: cornersRef.current[i] ?? 0 })
        ctx.font         = `500 9px "JetBrains Mono", monospace`
        ctx.fillStyle    = 'rgba(253,233,255,0.42)'
        ctx.textAlign    = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(CORNER_LABELS[i]!, x + barW / 2, barY + barH + 4)
      }
    }
    ctx.globalAlpha = 1
  })

  const numberGetter = (frame: Frame | null): BigNumberValueOut | null => {
    if (!frame) return null
    const u = Math.min(1, Math.max(0, frame.derived?.gripBudgetUsed ?? 0))
    return { display: `${Math.round(u * 100)}%`, normalized: u }
  }

  return (
    <div className={WRAP}>
      <canvas ref={canvasRef} className={CANVAS} />
      <BigNumber tier={tier} getValue={numberGetter} unit="GRIP USED" />
    </div>
  )
}
