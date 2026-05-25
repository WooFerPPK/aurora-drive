// client/src/components/widgets/InputTrace.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, MINT_RGB, PINK_RGB, BUTTER_RGB, toRgb, toRgba, ease,
  drawWidgetBg,
} from '@/shared/lib/canvasUtils'

// input_trace — rolling 5-second oscilloscope of driver inputs.
// Throttle (mint), brake (pink), clutch (butter), steer (lilac) overlaid
// on a shared 0-1 axis (steer normalised |steer|, with sign indicator
// as a hairline thickness/colour cue).
//
// Tiers (area-based):
//   compact  w×h ≤  6 : throttle + brake only
//   standard w×h ≤ 12 : + clutch
//   hero     w×h > 12 : + steer | sign | + live values right of trace

const BUF_LEN = 180   // ~3s at 60Hz
const LILAC_RGB: Rgb = [202, 166, 255]

export interface InputTraceProps {
  w: number
  h: number
}

export default function InputTrace({ w, h }: InputTraceProps) {
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const throttleBufRef = useRef(new Float32Array(BUF_LEN))
  const brakeBufRef    = useRef(new Float32Array(BUF_LEN))
  const clutchBufRef   = useRef(new Float32Array(BUF_LEN))
  const steerBufRef    = useRef(new Float32Array(BUF_LEN))
  const headRef        = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const t = stale ? 0 : Math.max(0, Math.min(1, frame!.inputs?.throttle ?? 0))
    const b = stale ? 0 : Math.max(0, Math.min(1, frame!.inputs?.brake    ?? 0))
    const c = stale ? 0 : Math.max(0, Math.min(1, frame!.inputs?.clutch   ?? 0))
    const s = stale ? 0 : Math.max(-1, Math.min(1, frame!.inputs?.steer  ?? 0))

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)

    throttleBufRef.current[headRef.current] = t
    brakeBufRef.current[headRef.current]    = b
    clutchBufRef.current[headRef.current]   = c
    steerBufRef.current[headRef.current]    = s
    headRef.current = (headRef.current + 1) % BUF_LEN

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const pad = 8
    const valueW = tier === 'hero' ? 46 : 0
    const chartTop    = pad
    const chartBottom = ch - pad
    const chartLeft   = pad
    const chartRight  = cw - pad - valueW
    const chartW = chartRight - chartLeft
    const chartH = chartBottom - chartTop

    // Mid-line (0 reference for steer; bottom is 0 for others)
    if (tier === 'hero') {
      ctx.strokeStyle = 'rgba(253,233,255,0.06)'
      ctx.lineWidth = 0.6
      ctx.setLineDash([2, 3])
      ctx.beginPath()
      ctx.moveTo(chartLeft, chartTop + chartH / 2)
      ctx.lineTo(chartRight, chartTop + chartH / 2)
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Draw traces
    drawTrace(ctx, throttleBufRef.current, headRef.current, chartLeft, chartTop, chartW, chartH, MINT_RGB, false)
    drawTrace(ctx, brakeBufRef.current,    headRef.current, chartLeft, chartTop, chartW, chartH, PINK_RGB, false)
    if (tier !== 'compact') {
      drawTrace(ctx, clutchBufRef.current, headRef.current, chartLeft, chartTop, chartW, chartH, BUTTER_RGB, false)
    }
    if (tier === 'hero') {
      drawTrace(ctx, steerBufRef.current, headRef.current, chartLeft, chartTop, chartW, chartH, LILAC_RGB, true)
    }

    // Hero: live numeric values on the right
    if (tier === 'hero') {
      const colX = cw - valueW + 2
      ctx.font = '700 14px "JetBrains Mono", monospace'
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle'
      const labels: Array<{ val: number; c: Rgb; y: number }> = [
        { val: Math.round(t * 100), c: MINT_RGB,   y: chartTop + 12 },
        { val: Math.round(b * 100), c: PINK_RGB,   y: chartTop + 30 },
        { val: Math.round(c * 100), c: BUTTER_RGB, y: chartTop + 48 },
        { val: Math.round(s * 100), c: LILAC_RGB,  y: chartTop + 66 },
      ]
      const ts = ['T', 'B', 'C', 'S']
      for (let i = 0; i < 4; i++) {
        const lb = labels[i]!
        ctx.fillStyle = toRgb(lb.c)
        ctx.fillText(String(lb.val), cw - 8, lb.y)
        ctx.font = '500 11px "JetBrains Mono", monospace'
        ctx.fillStyle = C.inkFaint
        ctx.fillText(ts[i]!, colX, lb.y)
        ctx.font = '700 14px "JetBrains Mono", monospace'
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawTrace(
  ctx: CanvasRenderingContext2D,
  buf: Float32Array,
  head: number,
  x: number, y: number, w: number, h: number,
  colRgb: Rgb,
  bipolar: boolean,
): void {
  ctx.strokeStyle = toRgb(colRgb)
  ctx.lineWidth = 1.5
  ctx.shadowColor = toRgb(colRgb); ctx.shadowBlur = 4
  ctx.beginPath()
  const len = BUF_LEN
  for (let i = 0; i < len; i++) {
    const idx = (head - 1 - i + len) % len
    const sample = buf[idx] ?? 0
    const px = x + w - (i / (len - 1)) * w
    let py: number
    if (bipolar) {
      py = y + h / 2 - sample * h / 2 * 0.9
    } else {
      py = y + h - Math.max(0, Math.min(1, sample)) * h
    }
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
  }
  ctx.stroke()
  ctx.shadowBlur = 0

  // Fill under (only unipolar traces)
  if (!bipolar) {
    ctx.beginPath()
    for (let i = 0; i < len; i++) {
      const idx = (head - 1 - i + len) % len
      const sample = buf[idx] ?? 0
      const px = x + w - (i / (len - 1)) * w
      const py = y + h - Math.max(0, Math.min(1, sample)) * h
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
    }
    ctx.lineTo(x, y + h); ctx.lineTo(x + w, y + h); ctx.closePath()
    const fg = ctx.createLinearGradient(0, y, 0, y + h)
    fg.addColorStop(0, toRgba(colRgb, 0.18)); fg.addColorStop(1, toRgba(colRgb, 0.01))
    ctx.fillStyle = fg
    ctx.fill()
  }
}
