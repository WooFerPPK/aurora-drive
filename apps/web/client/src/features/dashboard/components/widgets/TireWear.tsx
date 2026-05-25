// client/src/components/widgets/TireWear.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB,
  toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'
import { EASE_STALE } from '@/shared/components/widgetPrimitives'

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
const CORNERS: readonly CornerKey[] = ['fl', 'fr', 'rl', 'rr']
const CORNER_LABELS: readonly string[] = ['FL', 'FR', 'RL', 'RR']
const MAX_SLITS = 8

function wearColour(w: number): Rgb {
  if (w < 0.5) {
    const t = w / 0.5
    return [
      MINT_RGB[0] + (BUTTER_RGB[0] - MINT_RGB[0]) * t | 0,
      MINT_RGB[1] + (BUTTER_RGB[1] - MINT_RGB[1]) * t | 0,
      MINT_RGB[2] + (BUTTER_RGB[2] - MINT_RGB[2]) * t | 0,
    ]
  }
  const t = (w - 0.5) / 0.5
  return [
    BUTTER_RGB[0] + (PINK_RGB[0] - BUTTER_RGB[0]) * t | 0,
    BUTTER_RGB[1] + (PINK_RGB[1] - BUTTER_RGB[1]) * t | 0,
    BUTTER_RGB[2] + (PINK_RGB[2] - BUTTER_RGB[2]) * t | 0,
  ]
}

export interface TireWearProps {
  w: number
  h: number
}

export default function TireWear({ w, h }: TireWearProps) {
  const tier = w * h <= 9 ? 'compact' : w * h <= 16 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const wearsRef     = useRef(new Float32Array(4))
  const confRef      = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const confValue = stale ? 0 : (frame!.modeled?.tireWearConfidence ?? 0)
    const wearData  = (!stale && confValue > 0) ? (frame!.modeled?.tireWear ?? null) : null

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)
    confRef.current = ease(confRef.current, confValue, dt, 2)

    for (let i = 0; i < 4; i++) {
      const wear = wearData ? Math.min(1, Math.max(0, wearData[CORNERS[i]!] ?? 0)) : 0
      wearsRef.current[i] = ease(wearsRef.current[i] ?? 0, wear, dt, 3)
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const pad = 12
    const labelH = tier !== 'compact' ? 22 : 0
    const pctH = tier !== 'compact' ? 26 : 0
    const confH = tier === 'hero' ? 22 : 0
    const stripGap = 8
    const topPad = tier !== 'compact' ? 10 : 8
    const stripW = (cw - pad * 2 - 3 * stripGap) / 4
    const stripH = ch - topPad - pad - labelH - pctH - confH
    const stripY = topPad + labelH

    for (let i = 0; i < 4; i++) {
      const x = pad + i * (stripW + stripGap)
      const wear = wearsRef.current[i] ?? 0
      drawTireStrip(ctx, x, stripY, stripW, stripH, wear, CORNER_LABELS[i]!,
        tier !== 'compact', tier !== 'compact')
    }

    if (tier === 'hero') {
      const cbW = cw * 0.4
      const cbX = (cw - cbW) / 2
      const cbY = ch - 14
      ctx.fillStyle = 'rgba(255,255,255,0.06)'
      roundRectPath(ctx, cbX, cbY, cbW, 2, 1); ctx.fill()
      ctx.fillStyle = toRgb(MINT_RGB)
      ctx.shadowColor = toRgb(MINT_RGB); ctx.shadowBlur = 3
      roundRectPath(ctx, cbX, cbY, cbW * confRef.current, 2, 1); ctx.fill()
      ctx.shadowBlur = 0
      ctx.font = '500 12px "JetBrains Mono", monospace'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'
      ctx.fillText(`CONF ${Math.round(confRef.current * 100)}%`, cw / 2, cbY - 2)
    }

    if (!wearData && confValue < 0.05) {
      ctx.font = '600 14px "JetBrains Mono", monospace'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'
      ctx.fillText('CALIBRATING…', cw / 2, ch - 26)
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawTireStrip(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  wear: number, label: string,
  withLabel: boolean, withPct: boolean,
): void {
  const wc = wearColour(wear)

  ctx.fillStyle = '#0a0314'
  roundRectPath(ctx, x, y, w, h, 5); ctx.fill()
  ctx.strokeStyle = toRgba(wc, 0.8)
  ctx.shadowColor = toRgb(wc); ctx.shadowBlur = 10
  ctx.lineWidth = 1.5
  roundRectPath(ctx, x, y, w, h, 5); ctx.stroke()
  ctx.shadowBlur = 0

  const tg = ctx.createLinearGradient(x, y, x, y + h)
  tg.addColorStop(0, toRgba(wc, 0.5))
  tg.addColorStop(1, toRgba(wc, 0.20))
  ctx.fillStyle = tg
  roundRectPath(ctx, x + 3, y + 3, w - 6, h - 6, 3); ctx.fill()

  const visibleSlits = Math.max(0, Math.floor(MAX_SLITS * (1 - wear)))
  const slitsArea = h - 8
  const slitGap = slitsArea / (MAX_SLITS + 1)
  for (let i = 1; i <= visibleSlits; i++) {
    const sy = y + 4 + i * slitGap
    ctx.fillStyle = 'rgba(0,0,0,0.7)'
    ctx.fillRect(x + 6, sy - 0.75, w - 12, 1.5)
  }

  if (withPct) {
    const barH = 3
    const barY = y + h + 6
    ctx.fillStyle = 'rgba(255,193,220,0.10)'
    roundRectPath(ctx, x, barY, w, barH, 1.5); ctx.fill()
    ctx.fillStyle = toRgb(wc)
    ctx.shadowColor = toRgb(wc); ctx.shadowBlur = 4
    roundRectPath(ctx, x, barY, w * wear, barH, 1.5); ctx.fill()
    ctx.shadowBlur = 0

    ctx.font = '700 14px "JetBrains Mono", monospace'
    ctx.fillStyle = toRgb(wc)
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'
    ctx.fillText(`${Math.round(wear * 100)}%`, x + w / 2, barY + 8)
  }

  if (withLabel) {
    ctx.font = '700 14px "Unbounded", system-ui, sans-serif'
    ctx.fillStyle = C.cream
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'
    ctx.fillText(label, x + w / 2, y - 6)
  }
}
