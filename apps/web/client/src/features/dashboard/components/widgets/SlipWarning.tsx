// client/src/components/widgets/SlipWarning.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import type { Rgb } from '@/shared/lib/canvasUtils'
import {
  C, MINT_RGB, BUTTER_RGB, PINK_RGB, toRgb, toRgba, ease,
  drawWidgetBg, roundRectPath,
} from '@/shared/lib/canvasUtils'

// slip_warning — big readable status: GRIP / SLIP / SPIN.

type CornerKey = 'fl' | 'fr' | 'rl' | 'rr'
const CORNERS: readonly CornerKey[] = ['fl', 'fr', 'rl', 'rr']
const CORNER_LABELS: readonly string[] = ['FL', 'FR', 'RL', 'RR']

interface SlipState { word: string; col: Rgb; pulseHz: number }

function slipState(maxSlip: number): SlipState {
  if (maxSlip < 0.15) return { word: 'GRIP', col: MINT_RGB,   pulseHz: 0 }
  if (maxSlip < 0.40) return { word: 'SLIP', col: BUTTER_RGB, pulseHz: 1.5 }
  return                       { word: 'SPIN', col: PINK_RGB,   pulseHz: 4 }
}

export interface SlipWarningProps {
  w: number
  h: number
}

export default function SlipWarning({ w, h }: SlipWarningProps) {
  const tier = w * h <= 6 ? 'compact' : w * h <= 12 ? 'standard' : 'hero'

  const staleFadeRef = useRef(0)
  const maxSlipRef   = useRef(0)
  const slipsRef     = useRef(new Float32Array(4))
  const worstIdxRef  = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, frame, dt, elapsed, frameAgeMs }) => {
    const stale  = !frame || (frameAgeMs ?? 0) > 1500
    const wheels = stale ? null : (frame!.wheels ?? null)

    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)

    let maxS = 0
    let worstI = 0
    for (let i = 0; i < 4; i++) {
      const k = CORNERS[i]!
      const s = stale ? 0 : Math.min(1, Math.abs(wheels?.[k]?.combinedSlip ?? 0))
      slipsRef.current[i] = ease(slipsRef.current[i] ?? 0, s, dt, 8)
      const cur = slipsRef.current[i] ?? 0
      if (cur > maxS) { maxS = cur; worstI = i }
    }
    maxSlipRef.current = maxS
    worstIdxRef.current = worstI

    const state = slipState(maxS)
    const flash = state.pulseHz > 0 ? (Math.sin(elapsed * Math.PI * 2 * state.pulseHz) + 1) / 2 : 1
    const flashAlpha = 0.6 + 0.4 * flash

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const bx = cw / 2, by = ch / 2
    const bloomR = Math.max(cw, ch) * 0.6
    const bg = ctx.createRadialGradient(bx, by, 0, bx, by, bloomR)
    bg.addColorStop(0, toRgba(state.col, 0.18 * flashAlpha))
    bg.addColorStop(1, 'transparent')
    ctx.fillStyle = bg; ctx.fillRect(0, 0, cw, ch)

    if (state.pulseHz > 2) {
      ctx.strokeStyle = toRgba(state.col, flashAlpha * 0.7)
      ctx.lineWidth   = 3
      ctx.shadowColor = toRgb(state.col); ctx.shadowBlur = 16
      roundRectPath(ctx, 2, 2, cw - 4, ch - 4, 10); ctx.stroke()
      ctx.shadowBlur = 0
    }

    const wordSize = tier === 'compact' ? Math.min(cw, ch) * 0.32
                   : tier === 'standard' ? Math.min(cw, ch) * 0.28
                   : Math.min(cw, ch) * 0.24
    ctx.font         = `700 ${wordSize}px "Unbounded", system-ui, sans-serif`
    ctx.fillStyle    = toRgb(state.col)
    ctx.textAlign    = 'center'
    ctx.textBaseline = 'middle'
    ctx.shadowColor  = toRgb(state.col); ctx.shadowBlur = wordSize * (0.5 + flash * 0.4)
    const wordCy = tier === 'compact' ? by : tier === 'hero' ? ch * 0.46 : ch * 0.40
    ctx.fillText(state.word, bx, wordCy)
    ctx.shadowBlur = 0

    if (tier !== 'compact' && state.word !== 'GRIP') {
      const subLabel = `${CORNER_LABELS[worstI]} · ${Math.round(maxS * 100)}%`
      ctx.font = '500 13px "JetBrains Mono", monospace'
      ctx.fillStyle = toRgba(state.col, 0.85)
      ctx.fillText(subLabel, bx, wordCy + wordSize * 0.55)
    } else if (tier !== 'compact') {
      ctx.font = '500 13px "JetBrains Mono", monospace'
      ctx.fillStyle = C.inkFaint
      ctx.fillText(`${Math.round(maxS * 100)}% max slip`, bx, wordCy + wordSize * 0.55)
    }

    if (tier === 'hero') {
      const baseY = ch - 28
      const barW = (cw - 32) / 4
      const barGap = 4
      for (let i = 0; i < 4; i++) {
        const x = 12 + i * (barW + barGap)
        const slip = slipsRef.current[i] ?? 0
        const cornerState = slipState(slip)
        ctx.fillStyle = 'rgba(255,193,220,0.08)'
        roundRectPath(ctx, x, baseY, barW, 8, 3); ctx.fill()
        ctx.fillStyle = toRgb(cornerState.col)
        ctx.shadowColor = toRgb(cornerState.col); ctx.shadowBlur = 4
        roundRectPath(ctx, x, baseY, barW * slip, 8, 3); ctx.fill()
        ctx.shadowBlur = 0
        ctx.font = '400 7px "JetBrains Mono", monospace'
        ctx.fillStyle = C.inkFaint
        ctx.textAlign = 'center'; ctx.textBaseline = 'top'
        ctx.fillText(CORNER_LABELS[i]!, x + barW / 2, baseY + 12)
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}
