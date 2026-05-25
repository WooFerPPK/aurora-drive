// client/src/components/widgets/PhysicsInsights.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB, valueColour, toRgb, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'

// physics_insights — aggregate readouts of frame.derived.*.

interface PhysicsStat {
  id: 'gripBudgetUsed' | 'bodyControl' | 'balance' | 'throttleSmoothness' | 'weightFront' | 'weightLeft'
  lbl: string
  bipolar: boolean
}

const STATS: readonly PhysicsStat[] = [
  { id: 'gripBudgetUsed',     lbl: 'GRIP USED',  bipolar: false },
  { id: 'bodyControl',        lbl: 'BODY CTRL',  bipolar: false },
  { id: 'balance',            lbl: 'BALANCE',    bipolar: true  },
  { id: 'throttleSmoothness', lbl: 'THR SMTH',   bipolar: false },
  { id: 'weightFront',        lbl: 'WT FRONT',   bipolar: false },
  { id: 'weightLeft',         lbl: 'WT LEFT',    bipolar: false },
]

export interface PhysicsInsightsProps {
  w: number
  h: number
}

export default function PhysicsInsights({ w, h }: PhysicsInsightsProps) {
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'
  const numTiles = tier === 'compact' ? 2 : tier === 'standard' ? 4 : 6

  const valuesRef    = useRef(new Float32Array(6))
  const staleFadeRef = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const d = stale ? null : (frame!.derived ?? null)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)

    for (let i = 0; i < STATS.length; i++) {
      const stat = STATS[i]!
      const v = d ? Number(d[stat.id] ?? 0) : 0
      const clamped = stat.bipolar
        ? Math.max(-1, Math.min(1, v))
        : Math.max(0, Math.min(1, v))
      valuesRef.current[i] = ease(valuesRef.current[i] ?? 0, clamped, dt, 4)
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const pad = 10
    const headerH = 6
    const gap = 6
    const cols = tier === 'compact' ? 1 : 2
    const rows = Math.ceil(numTiles / cols)
    const tilesAreaW = cw - pad * 2
    const tilesAreaH = ch - headerH - pad
    const tileW = (tilesAreaW - gap * (cols - 1)) / cols
    const tileH = (tilesAreaH - gap * (rows - 1)) / rows

    for (let i = 0; i < numTiles; i++) {
      const col = i % cols
      const row = Math.floor(i / cols)
      const x = pad + col * (tileW + gap)
      const y = headerH + row * (tileH + gap)
      drawTile(ctx, x, y, tileW, tileH, STATS[i]!, valuesRef.current[i] ?? 0)
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}

function drawTile(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  stat: PhysicsStat, v: number,
): void {
  ctx.fillStyle = 'rgba(255,255,255,0.03)'
  roundRectPath(ctx, x, y, w, h, 6); ctx.fill()

  const accent: Rgb = [202, 166, 255]
  ctx.fillStyle = toRgb(accent)
  ctx.fillRect(x, y, 2, h)

  ctx.font = '400 7px "Unbounded", system-ui, sans-serif'
  ctx.fillStyle = C.inkFaint
  ctx.textAlign = 'left'; ctx.textBaseline = 'top'
  ctx.fillText(stat.lbl, x + 8, y + 6)

  const display = stat.bipolar ? v.toFixed(2) : `${Math.round(v * 100)}%`
  const valCol = stat.bipolar
    ? (Math.abs(v) > 0.5 ? PINK_RGB : Math.abs(v) > 0.25 ? BUTTER_RGB : MINT_RGB)
    : valueColour(v)
  ctx.font = '700 16px "JetBrains Mono", monospace'
  ctx.fillStyle = toRgb(valCol)
  ctx.textBaseline = 'top'
  ctx.shadowColor = toRgb(valCol); ctx.shadowBlur = 6
  ctx.fillText(display, x + 8, y + 16)
  ctx.shadowBlur = 0

  const barH = 3
  const barX = x + 8
  const barY = y + h - barH - 6
  const barW = w - 16
  ctx.fillStyle = 'rgba(255,193,220,0.08)'
  roundRectPath(ctx, barX, barY, barW, barH, 1.5); ctx.fill()

  if (stat.bipolar) {
    const midX = barX + barW / 2
    const half = barW / 2
    const fillW = Math.abs(v) * half
    const fx = v >= 0 ? midX : midX - fillW
    ctx.fillStyle = toRgb(valCol)
    ctx.shadowColor = toRgb(valCol); ctx.shadowBlur = 4
    roundRectPath(ctx, fx, barY, fillW, barH, 1.5); ctx.fill()
    ctx.shadowBlur = 0
    ctx.fillStyle = 'rgba(253,233,255,0.40)'
    ctx.fillRect(midX - 0.5, barY - 1, 1, barH + 2)
  } else {
    ctx.fillStyle = toRgb(valCol)
    ctx.shadowColor = toRgb(valCol); ctx.shadowBlur = 4
    roundRectPath(ctx, barX, barY, barW * v, barH, 1.5); ctx.fill()
    ctx.shadowBlur = 0
  }
}
