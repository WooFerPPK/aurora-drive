// client/src/components/widgets/Fingerprint.tsx
import { useRef } from 'react'
import { useCanvas } from '@/shared/hooks/useCanvas'
import {
  C, MINT_RGB, toRgba, ease,
  drawWidgetBg,
} from '@/shared/lib/canvasUtils'
import { useDriverProfileQuery } from '@/shared/hooks/queries/driver'

const TRAITS = ['smooth', 'brave', 'early', 'patient', 'precise', 'consist'] as const
const TRAIT_LABELS = ['SMOOTH', 'BRAVE', 'EARLY', 'PATIENT', 'PRECISE', 'CONSIST'] as const
const N = 6
const TRAIT_ANGLES = (() => {
  const a = new Float32Array(N)
  for (let i = 0; i < N; i++) a[i] = -Math.PI / 2 + (i * Math.PI * 2 / N)
  return a
})()

export interface FingerprintProps {
  w: number
  h: number
}

export default function Fingerprint({ w, h }: FingerprintProps) {
  const tier = w * h <= 9 ? 'compact' : w * h <= 16 ? 'standard' : 'hero'

  const { data: profile } = useDriverProfileQuery()
  const valuesRef    = useRef(new Float32Array(N))
  const baselineRef  = useRef(new Float32Array(N))
  const staleFadeRef = useRef(0)

  const canvasRef = useCanvas(({ ctx, w: cw, h: ch, dt }) => {
    const stale = !profile
    staleFadeRef.current = ease(staleFadeRef.current, stale ? 1 : 0, dt, 3)

    if (profile?.fingerprint) {
      const fp = profile.fingerprint as Record<string, number>
      for (let i = 0; i < N; i++) {
        const v = fp[TRAITS[i]!] ?? 0
        valuesRef.current[i] = ease(valuesRef.current[i] ?? 0, Math.max(0, Math.min(1, v)), dt, 4)
      }
    }
    if (profile?.fingerprintBaseline90d) {
      const base = profile.fingerprintBaseline90d as Record<string, number>
      for (let i = 0; i < N; i++) {
        const v = base[TRAITS[i]!] ?? 0
        baselineRef.current[i] = ease(baselineRef.current[i] ?? 0, Math.max(0, Math.min(1, v)), dt, 4)
      }
    }

    drawWidgetBg(ctx, cw, ch)
    ctx.globalAlpha = 1 - staleFadeRef.current * 0.45

    const cx = cw / 2
    const cy = ch / 2 + (tier === 'compact' ? 0 : 4)
    const maxR = Math.min(cw, ch) * (tier === 'compact' ? 0.42 : 0.38)
    const labelMargin = tier === 'standard' ? 22 : tier === 'hero' ? 32 : 0
    const r = maxR - labelMargin / 2

    if (tier !== 'compact') {
      const ringSteps = tier === 'hero' ? 4 : 3
      for (let k = 1; k <= ringSteps; k++) {
        const rr = r * (k / ringSteps)
        ctx.strokeStyle = k === ringSteps ? 'rgba(253,233,255,0.20)' : 'rgba(253,233,255,0.07)'
        ctx.lineWidth = k === ringSteps ? 1 : 0.6
        ctx.beginPath()
        for (let i = 0; i < N; i++) {
          const a = TRAIT_ANGLES[i]!
          const x = cx + rr * Math.cos(a)
          const y = cy + rr * Math.sin(a)
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        }
        ctx.closePath(); ctx.stroke()
      }

      ctx.strokeStyle = 'rgba(253,233,255,0.08)'
      ctx.lineWidth = 0.6
      for (let i = 0; i < N; i++) {
        const a = TRAIT_ANGLES[i]!
        ctx.beginPath()
        ctx.moveTo(cx, cy)
        ctx.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a))
        ctx.stroke()
      }
    }

    if (tier === 'hero') {
      ctx.strokeStyle = 'rgba(202,166,255,0.45)'
      ctx.lineWidth = 1
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      for (let i = 0; i < N; i++) {
        const a = TRAIT_ANGLES[i]!
        const v = baselineRef.current[i] ?? 0
        const x = cx + r * v * Math.cos(a)
        const y = cy + r * v * Math.sin(a)
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
      }
      ctx.closePath(); ctx.stroke()
      ctx.setLineDash([])
    }

    ctx.beginPath()
    for (let i = 0; i < N; i++) {
      const a = TRAIT_ANGLES[i]!
      const v = valuesRef.current[i] ?? 0
      const x = cx + r * v * Math.cos(a)
      const y = cy + r * v * Math.sin(a)
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.closePath()

    const fillG = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
    fillG.addColorStop(0, toRgba(MINT_RGB, 0.35))
    fillG.addColorStop(1, toRgba(MINT_RGB, 0.10))
    ctx.fillStyle = fillG
    ctx.fill()

    ctx.strokeStyle = C.mint
    ctx.lineWidth = 1.5
    ctx.shadowColor = C.mint; ctx.shadowBlur = 16
    ctx.stroke()
    ctx.shadowBlur = 0

    for (let i = 0; i < N; i++) {
      const a = TRAIT_ANGLES[i]!
      const v = valuesRef.current[i] ?? 0
      const x = cx + r * v * Math.cos(a)
      const y = cy + r * v * Math.sin(a)
      ctx.fillStyle = C.cream
      ctx.shadowColor = C.mint; ctx.shadowBlur = 8
      ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill()
      ctx.shadowBlur = 0
    }

    if (tier !== 'compact') {
      ctx.font = `500 ${tier === 'hero' ? 9 : 7.5}px "Unbounded", system-ui, sans-serif`
      ctx.fillStyle = C.inkFaint
      ctx.textBaseline = 'middle'
      const labelR = r + (tier === 'hero' ? 14 : 10)
      for (let i = 0; i < N; i++) {
        const a = TRAIT_ANGLES[i]!
        const lx = cx + labelR * Math.cos(a)
        const ly = cy + labelR * Math.sin(a)
        const cosA = Math.cos(a)
        if (Math.abs(cosA) < 0.25) ctx.textAlign = 'center'
        else if (cosA > 0)         ctx.textAlign = 'left'
        else                       ctx.textAlign = 'right'
        ctx.fillText(TRAIT_LABELS[i]!, lx, ly)
      }
    }

    if (tier === 'hero') {
      ctx.font = `600 9px "JetBrains Mono", monospace`
      ctx.fillStyle = C.cream
      ctx.textBaseline = 'middle'
      const valueR = r + 26
      for (let i = 0; i < N; i++) {
        const a = TRAIT_ANGLES[i]!
        const vx = cx + valueR * Math.cos(a)
        const vy = cy + valueR * Math.sin(a) + 10
        const cosA = Math.cos(a)
        if (Math.abs(cosA) < 0.25) ctx.textAlign = 'center'
        else if (cosA > 0)         ctx.textAlign = 'left'
        else                       ctx.textAlign = 'right'
        ctx.fillText(String(Math.round((valuesRef.current[i] ?? 0) * 100)), vx, vy)
      }
    }

    ctx.globalAlpha = 1
  })

  return <canvas ref={canvasRef} className="widget-canvas" />
}
