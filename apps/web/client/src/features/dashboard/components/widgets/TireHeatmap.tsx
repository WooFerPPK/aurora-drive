// client/src/components/widgets/TireHeatmap.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, PINK_RGB,
  valueColour, toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'
import { drawCarBody, EASE_STALE } from '@/shared/components/widgetPrimitives'

// tire_heatmap — top-down car silhouette with 4 colour-coded tires.

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
const CORNER_LABELS: readonly string[] = ['FL', 'FR', 'RL', 'RR']
const CORNER_KEYS: readonly CornerKey[] = ['fl', 'fr', 'rl', 'rr']

export interface TireHeatmapProps {
  w: number
  h: number
}

export default function TireHeatmap({ w, h }: TireHeatmapProps) {
  const tier = w * h <= 9 ? 'compact' : w * h <= 16 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const tempsRef     = useRef(new Float32Array(4))
  const wearsRef     = useRef(new Float32Array(4))

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const wheels = stale ? null : (frame!.wheels ?? null)
    const wearData = (!stale && (frame!.modeled?.tireWearConfidence ?? 0) > 0)
      ? (frame!.modeled?.tireWear ?? null) : null

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, EASE_STALE)

    for (let i = 0; i < 4; i++) {
      const k = CORNER_KEYS[i]!
      const tv = stale ? 0 : Math.min(1, Math.max(0, wheels?.[k]?.tireTemp_normWindow ?? 0))
      const wv = wearData ? Math.min(1, Math.max(0, wearData[k] ?? 0)) : 0
      tempsRef.current[i] = ease(tempsRef.current[i] ?? 0, tv, dt, 4)
      wearsRef.current[i] = ease(wearsRef.current[i] ?? 0, wv, dt, 4)
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const carW = cw * 0.36
    const carH = ch * 0.66
    const { corners } = drawCarBody(ctx, {
      cx: cw / 2, cy: ch / 2,
      carW, carH,
    })

    const tireW = cw * 0.13
    const tireH = ch * 0.22

    for (let i = 0; i < 4; i++) {
      const c = corners[i]!
      const tx = c.x - tireW / 2
      const ty = c.y - tireH / 2

      const t = tempsRef.current[i] ?? 0
      const tc = valueColour(t, 'thermal')

      ctx.shadowColor = toRgb(tc)
      ctx.shadowBlur  = tier === 'compact' ? 10 : 16
      ctx.fillStyle   = toRgba(tc, 0.75)
      roundRectPath(ctx, tx, ty, tireW, tireH, 4); ctx.fill()
      ctx.shadowBlur = 0

      const ig = ctx.createLinearGradient(tx, ty, tx, ty + tireH)
      ig.addColorStop(0, toRgba(tc, 0.4))
      ig.addColorStop(1, 'transparent')
      ctx.fillStyle = ig
      roundRectPath(ctx, tx, ty, tireW, tireH, 4); ctx.fill()

      const isLeft = i === 0 || i === 2

      if (tier !== 'compact') {
        ctx.font = `700 ${tier === 'hero' ? 14 : 12}px "Unbounded", system-ui, sans-serif`
        ctx.fillStyle = C.cream
        ctx.textBaseline = 'middle'
        const label = CORNER_LABELS[i]!
        if (isLeft) {
          ctx.textAlign = 'right'
          ctx.fillText(label, tx - 4, ty + tireH / 2)
        } else {
          ctx.textAlign = 'left'
          ctx.fillText(label, tx + tireW + 4, ty + tireH / 2)
        }
      }

      if (tier === 'hero') {
        ctx.font = '600 11px "JetBrains Mono", monospace'
        ctx.fillStyle = toRgba(tc, 0.95)
        ctx.textBaseline = 'middle'
        const pct = `${Math.round(t * 100)}%`
        if (isLeft) {
          ctx.textAlign = 'left'
          ctx.fillText(pct, tx + tireW + 4, ty + tireH * 0.32)
        } else {
          ctx.textAlign = 'right'
          ctx.fillText(pct, tx - 4, ty + tireH * 0.32)
        }

        if (wearData) {
          const wv  = wearsRef.current[i] ?? 0
          const wbW = tireW * 0.7
          const wbX = isLeft ? tx + tireW + 4 : tx - 4 - wbW
          const wbY = ty + tireH * 0.62
          ctx.fillStyle = 'rgba(0,0,0,0.3)'
          roundRectPath(ctx, wbX, wbY, wbW, 3, 1.5); ctx.fill()
          ctx.fillStyle = wv > 0.7 ? toRgb(PINK_RGB) : toRgb(tc)
          ctx.shadowColor = ctx.fillStyle as string; ctx.shadowBlur = 3
          roundRectPath(ctx, wbX, wbY, wbW * wv, 3, 1.5); ctx.fill()
          ctx.shadowBlur = 0
        }
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}
