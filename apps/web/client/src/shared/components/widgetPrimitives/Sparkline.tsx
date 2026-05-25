// client/src/lib/widgetPrimitives/Sparkline.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { ColourRamp } from '@/shared/lib/canvasUtils'
import { drawSparkline } from './drawSparkline'

export interface SparklineProps {
  getValue: (frame: Frame) => number
  length?: number
  ramp?: ColourRamp
  baseline?: boolean
  className?: string
}

export default function Sparkline({ getValue, length = 120, ramp = 'intensity', baseline = false, className = '' }: SparklineProps) {
  const bufRef  = useRef<Float32Array>(new Float32Array(length))
  const headRef = useRef(0)

  const canvasRef = useCanvas(({ ctx, w, h, frame, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const v     = stale ? 0 : Math.max(0, Math.min(1, getValue(frame!) ?? 0))
    bufRef.current[headRef.current] = v
    headRef.current = (headRef.current + 1) % length

    ctx.clearRect(0, 0, w, h)
    drawSparkline(ctx, {
      x: 4, y: 4, w: w - 8, h: h - 8,
      buf: bufRef.current, head: headRef.current, ramp, fill: true,
      baselineRgba: baseline ? 'rgba(253,233,255,0.08)' : null,
    })
  })

  return (
    <div className={`sparkline-wrap ${className}`}>
      <canvas ref={canvasRef} className="widget-canvas" />
    </div>
  )
}
