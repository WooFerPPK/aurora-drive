// client/src/lib/widgetPrimitives/LinearGauge.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { ease } from '@/shared/lib/canvasUtils'
import type { ColourRamp, TickTier } from '@/shared/lib/canvasUtils'
import { drawLinearGauge } from './drawLinearGauge'
import { EASE_VALUE, EASE_STALE } from './easeConstants'

export interface LinearGaugeProps {
  getValue: (frame: Frame) => number
  max: number
  min?: number
  orientation?: 'h' | 'v'
  tier?: TickTier
  ramp?: ColourRamp
  className?: string
}

// <LinearGauge> — convenience wrapper. Takes getValue(frame), max,
// orientation, and renders a single bar filling the canvas.
//
// For multi-bar layouts (e.g. Pedals' three bars), use drawLinearGauge
// directly inside the widget's own useCanvas.
export default function LinearGauge({ getValue, max, min = 0, orientation = 'h', tier = 'standard', ramp = 'intensity', className = '' }: LinearGaugeProps) {
  const valueEaseRef = useRef(0)
  const staleFadeRef = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const raw   = stale ? min : getValue(frame!)
    const v01   = Math.max(0, Math.min(1, (raw - min) / Math.max(1e-6, max - min)))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    valueEaseRef.current = ease(valueEaseRef.current, v01,           dt, EASE_VALUE)

    ctx.clearRect(0, 0, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const padX = 6
    const padY = orientation === 'h' ? Math.max(4, ch * 0.30) : 6
    drawLinearGauge(ctx, {
      x: padX,
      y: padY,
      w: cw - 2 * padX,
      h: ch - 2 * padY,
      value: valueEaseRef.current,
      orientation,
      ramp,
    })

    ctx.globalAlpha = 1
  })

  return (
    <div className={`linear-gauge-wrap tier-${tier} ${className}`}>
      <canvas ref={canvasRef} className="widget-canvas" />
    </div>
  )
}
