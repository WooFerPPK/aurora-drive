// client/src/components/widgets/Pedals.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, MINT_RGB, PINK_RGB, BUTTER_RGB, toRgb, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'

// pedals — vertical throttle/brake/clutch bars + handbrake LED.
//
// Tiers (area-based):
//   compact  w×h ≤ 4 : throttle + brake only, no labels
//   standard w×h ≤ 6 : throttle + brake + clutch + short labels
//   hero     w×h > 6 : 3 bars + full labels + percent above + handbrake LED

type PedalKey = 'throttle' | 'brake' | 'clutch'

const BARS_2: PedalKey[] = ['throttle', 'brake']
const BARS_3: PedalKey[] = ['throttle', 'brake', 'clutch']
const COLOUR_MAP: Record<PedalKey, Rgb>      = { throttle: MINT_RGB, brake: PINK_RGB, clutch: BUTTER_RGB }
const LABEL_SHORT: Record<PedalKey, string>  = { throttle: 'T', brake: 'B', clutch: 'C' }
const LABEL_FULL:  Record<PedalKey, string>  = { throttle: 'THROTTLE', brake: 'BRAKE', clutch: 'CLUTCH' }

const LABEL_FONT  = '500 12px "JetBrains Mono", monospace'
const PCT_FONT    = '700 16px "JetBrains Mono", monospace'
const HB_LBL_FONT = '500 12px "JetBrains Mono", monospace'

export interface PedalsProps {
  w: number
  h: number
}

export default function Pedals({ w, h }: PedalsProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 6 ? 'standard' : 'hero'
  const bars: PedalKey[] = tier === 'compact' ? BARS_2 : BARS_3

  const staleFadeRef = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const inputs = stale ? null : (frame!.inputs ?? null)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)

    drawWidgetBg(ctx, cw, ch)

    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const pad     = 8
    const gap     = tier === 'compact' ? 6 : 8
    const lblH    = tier === 'compact' ? 0  : 18
    const pctH    = tier === 'hero'    ? 20 : 0
    const hbH     = tier === 'hero'    ? 24 : 0
    const barW    = (cw - pad * 2 - gap * (bars.length - 1)) / bars.length
    const barTop  = pad + pctH + (pctH > 0 ? 4 : 0)
    const barBtm  = ch - pad - lblH - hbH
    const barH    = barBtm - barTop

    // ── Pass 1: Tracks ───────────────────────────────────────────────────
    ctx.fillStyle = C.track
    for (let i = 0; i < bars.length; i++) {
      const x = pad + i * (barW + gap)
      roundRectPath(ctx, x, barTop, barW, barH, 5); ctx.fill()
    }

    // ── Pass 2: Fills + glows ────────────────────────────────────────────
    for (let i = 0; i < bars.length; i++) {
      const k   = bars[i]!
      const x   = pad + i * (barW + gap)
      const raw = inputs?.[k] ?? 0
      const v   = Math.max(0, Math.min(1, raw))
      if (v <= 0.001) continue
      const fillH = barH * v
      const fc    = COLOUR_MAP[k]
      ctx.fillStyle = toRgb(fc)
      ctx.shadowColor = toRgb(fc); ctx.shadowBlur = 10
      roundRectPath(ctx, x, barBtm - fillH, barW, fillH, 5); ctx.fill()
      ctx.shadowBlur = 0
    }

    // ── Pass 3: Segment marks (standard + hero) ──────────────────────────
    if (tier !== 'compact') {
      for (let i = 0; i < bars.length; i++) {
        const x = pad + i * (barW + gap)
        for (const ref of [0.25, 0.5, 0.75]) {
          const my = barBtm - barH * ref
          ctx.strokeStyle = 'rgba(0,0,0,0.25)'
          ctx.lineWidth   = 0.8
          ctx.beginPath(); ctx.moveTo(x + 2, my); ctx.lineTo(x + barW - 2, my); ctx.stroke()
        }
      }
    }

    // ── Pass 4: Labels ───────────────────────────────────────────────────
    if (tier !== 'compact') {
      ctx.font         = LABEL_FONT
      ctx.fillStyle    = C.inkFaint
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'top'
      for (let i = 0; i < bars.length; i++) {
        const k   = bars[i]!
        const x   = pad + i * (barW + gap)
        const lbl = tier === 'hero' ? LABEL_FULL[k] : LABEL_SHORT[k]
        ctx.fillText(lbl, x + barW / 2, barBtm + 6)
      }
    }

    // ── Pass 5: Percent above each bar (hero only) ───────────────────────
    if (tier === 'hero') {
      ctx.font         = PCT_FONT
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'top'
      for (let i = 0; i < bars.length; i++) {
        const k  = bars[i]!
        const x  = pad + i * (barW + gap)
        const v  = Math.max(0, Math.min(1, inputs?.[k] ?? 0))
        const fc = COLOUR_MAP[k]
        ctx.fillStyle   = C.cream
        ctx.shadowColor = toRgb(fc); ctx.shadowBlur = 6
        ctx.fillText(String(Math.round(v * 100)), x + barW / 2, pad + 4)
        ctx.shadowBlur = 0
      }
    }

    // ── Handbrake LED (hero) ─────────────────────────────────────────────
    if (tier === 'hero') {
      const hb  = !stale && (inputs?.handbrake ?? 0) > 0.5
      const lcy = ch - pad - 8
      ctx.fillStyle   = hb ? C.pink : 'rgba(255,255,255,0.10)'
      ctx.shadowColor = hb ? C.pink : 'transparent'
      ctx.shadowBlur  = hb ? 14 : 0
      ctx.beginPath(); ctx.arc(cw / 2, lcy, 4, 0, Math.PI * 2); ctx.fill()
      ctx.shadowBlur = 0
      ctx.font         = HB_LBL_FONT
      ctx.fillStyle    = hb ? C.pink : C.inkFaint
      ctx.textAlign    = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText('HB', cw / 2, lcy + 12)
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}
