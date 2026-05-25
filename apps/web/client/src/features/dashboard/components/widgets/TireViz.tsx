// client/src/components/widgets/TireViz.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB,
  valueColour, toRgb, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'
import type { Rgb } from '@/shared/lib/canvasUtils'
import { drawTire, EASE_STALE } from '@/shared/components/widgetPrimitives'

// tire_viz — hero tire close-up; auto-selects the most-stressed corner
// at compact/standard; quad view at hero.

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
const CORNERS: readonly CornerKey[] = ['fl', 'fr', 'rl', 'rr']
const CORNER_LABELS: readonly string[] = ['FL', 'FR', 'RL', 'RR']

function stressIndex(temp: number, slip: number): number { return slip * (0.5 + temp * 0.5) }

export interface TireVizProps {
  w: number
  h: number
}

export default function TireViz({ w, h }: TireVizProps) {
  const tier = w * h <= 9 ? 'compact' : w * h <= 16 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const tempsRef = useRef(new Float32Array(4))
  const slipsRef = useRef(new Float32Array(4))
  const wearsRef = useRef(new Float32Array(4))

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, elapsed, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const wheels = stale ? null : (frame!.wheels ?? null)
    const wearData = (!stale && (frame!.modeled?.tireWearConfidence ?? 0) > 0)
      ? (frame!.modeled?.tireWear ?? null) : null

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)

    for (let i = 0; i < 4; i++) {
      const k = CORNERS[i]!
      const t = stale ? 0 : Math.min(1, Math.max(0, wheels?.[k]?.tireTemp_normWindow ?? 0))
      const s = stale ? 0 : Math.min(1, Math.abs(wheels?.[k]?.combinedSlip ?? 0))
      const wear = wearData ? Math.min(1, Math.max(0, wearData[k] ?? 0)) : 0
      tempsRef.current[i] = ease(tempsRef.current[i] ?? 0, t, dt, 4)
      slipsRef.current[i] = ease(slipsRef.current[i] ?? 0, s, dt, 6)
      wearsRef.current[i] = ease(wearsRef.current[i] ?? 0, wear, dt, 4)
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    if (tier === 'hero') {
      const pad = 10, gap = 8
      const cellW = (cw - pad * 2 - gap) / 2
      const cellH = (ch - pad * 2 - gap) / 2
      const placements = [
        { idx: 0, col: 0, row: 0 },
        { idx: 1, col: 1, row: 0 },
        { idx: 2, col: 0, row: 1 },
        { idx: 3, col: 1, row: 1 },
      ]
      for (const p of placements) {
        const cx = pad + p.col * (cellW + gap) + cellW / 2
        const cy = pad + p.row * (cellH + gap) + cellH * 0.40
        const r  = Math.min(cellW, cellH) * 0.30
        const temp = tempsRef.current[p.idx] ?? 0
        const slip = slipsRef.current[p.idx] ?? 0
        const wear = wearsRef.current[p.idx] ?? 0

        drawTire(ctx, {
          cx, cy, r,
          temp, slip, wear,
          label: CORNER_LABELS[p.idx]!,
          elapsed,
        })

        const metricY = pad + p.row * (cellH + gap) + cellH - 22
        const tc = valueColour(temp, 'thermal')
        const metricW = cellW / 3
        const metricX = pad + p.col * (cellW + gap)
        ctx.font = '500 13px "Unbounded", system-ui, sans-serif'
        ctx.fillStyle = C.inkFaint
        ctx.textAlign = 'center'; ctx.textBaseline = 'top'
        ctx.fillText('T', metricX + metricW * 0.5, metricY)
        ctx.fillText('S', metricX + metricW * 1.5, metricY)
        ctx.fillText('W', metricX + metricW * 2.5, metricY)
        ctx.font = '700 14px "JetBrains Mono", monospace'
        ctx.fillStyle = toRgb(tc)
        ctx.fillText(String(Math.round(temp * 100)), metricX + metricW * 0.5, metricY + 14)
        ctx.fillStyle = slip > 0.4 ? toRgb(PINK_RGB) : toRgb(BUTTER_RGB)
        ctx.fillText(String(Math.round(slip * 100)), metricX + metricW * 1.5, metricY + 14)
        ctx.fillStyle = wearData ? (wear > 0.7 ? toRgb(PINK_RGB) : toRgb(MINT_RGB)) : C.inkFaint
        ctx.fillText(wearData ? String(Math.round(wear * 100)) : '—', metricX + metricW * 2.5, metricY + 14)
      }

      ctx.font = '500 14px "Unbounded", system-ui, sans-serif'
      ctx.fillStyle = C.inkFaint
      ctx.textAlign = 'left'; ctx.textBaseline = 'top'
      ctx.fillText('TIRE VIZ · ALL CORNERS', pad, 4)
    } else {
      let activeIdx = 0, activeStress = -1
      for (let i = 0; i < 4; i++) {
        const s = stressIndex(tempsRef.current[i] ?? 0, slipsRef.current[i] ?? 0)
        if (s > activeStress) { activeStress = s; activeIdx = i }
      }

      const cx = cw / 2
      const cy = tier === 'compact' ? ch / 2 : ch * 0.50
      const r  = tier === 'compact' ? Math.min(cw, ch) * 0.36 : Math.min(cw, ch) * 0.32

      drawTire(ctx, {
        cx, cy, r,
        temp: tempsRef.current[activeIdx] ?? 0,
        slip: slipsRef.current[activeIdx] ?? 0,
        wear: wearsRef.current[activeIdx] ?? 0,
        label: CORNER_LABELS[activeIdx]!,
        elapsed,
      })

      if (tier === 'standard') {
        const mmSize = Math.min(cw, ch) * 0.22
        drawMiniMap(ctx, cw - mmSize - 8, 8, mmSize, mmSize, activeIdx)
        ctx.font = '500 14px "Unbounded", system-ui, sans-serif'
        ctx.fillStyle = C.inkFaint
        ctx.textAlign = 'left'; ctx.textBaseline = 'top'
        ctx.fillText('MOST STRESSED', 8, 8)
        ctx.font = '700 18px "Unbounded", system-ui, sans-serif'
        ctx.fillStyle = C.cream
        ctx.fillText(CORNER_LABELS[activeIdx]!, 8, 26)
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawMiniMap(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  activeIdx: number,
): void {
  const cellW = (w - 2) / 2
  const cellH = (h - 2) / 2
  for (let i = 0; i < 4; i++) {
    const col = i % 2
    const row = i < 2 ? 0 : 1
    const tx = x + col * (cellW + 2)
    const ty = y + row * (cellH + 2)
    const active = i === activeIdx
    const mint: Rgb = [168, 243, 208]
    ctx.fillStyle = active ? toRgb(mint) : 'rgba(202,166,255,0.10)'
    if (active) { ctx.shadowColor = toRgb(mint); ctx.shadowBlur = 6 }
    roundRectPath(ctx, tx, ty, cellW, cellH, 2); ctx.fill()
    ctx.shadowBlur = 0
    ctx.font = '700 9px "Unbounded", system-ui, sans-serif'
    ctx.fillStyle = active ? '#0d0520' : 'rgba(253,233,255,0.4)'
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(CORNER_LABELS[i]!, tx + cellW / 2, ty + cellH / 2)
  }
}
