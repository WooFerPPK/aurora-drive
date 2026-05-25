import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { useCanvas } from '@/shared/hooks/useCanvas'
import { cx } from '@/shared/lib/format'

// Placeholder for every widget kind until the real component lands.

const WRAP_BASE =
  'w-full h-full flex flex-col items-center justify-center gap-1 text-ink-dim text-center'

const HEADLINE_BASE =
  'font-display font-normal text-[11px] [letter-spacing:0.18em] text-bubblegum uppercase'
const HEADLINE_COMPACT = 'text-[9px]'

const VALUE_BASE =
  'font-display font-bold text-[28px] text-cream leading-none ' +
  '[text-shadow:0_0_14px_rgba(255,193,220,0.45)]'
const VALUE_LG = 'text-[44px]'
const VALUE_COMPACT = 'text-[22px]'

const META = 'font-mono font-normal text-[10px] text-ink-faint'

const TIER = 'font-mono font-normal text-[9px] [letter-spacing:0.14em] text-ink-faint opacity-70 mt-1.5'

const SPARK =
  'block w-full flex-1 min-h-8 mt-1 rounded-md ' +
  '[background:linear-gradient(180deg,rgba(0,0,0,0.18),rgba(0,0,0,0.05))]'

export interface WidgetStubProps {
  kind: string
  title: string
  w?: number
  h?: number
}

export default function WidgetStub({ kind, title, w = 3, h = 2 }: WidgetStubProps) {
  const cells = w * h
  const tier =
    cells <= 4  ? 'compact'  :
    cells <= 9  ? 'standard' :
                  'detailed'

  const headlineCls = cx(HEADLINE_BASE, tier === 'compact' && HEADLINE_COMPACT)

  return (
    <div className={WRAP_BASE}>
      <div className={headlineCls}>{title}</div>

      {tier === 'compact'  && <CompactBody  kind={kind} />}
      {tier === 'standard' && <StandardBody kind={kind} />}
      {tier === 'detailed' && <DetailedBody kind={kind} />}

      <div className={TIER}>{tier} · {w}×{h}</div>
    </div>
  )
}

function CompactBody({ kind }: { kind: string }) {
  const valueRef = useRef<HTMLDivElement>(null)
  useFrameLoop((frame, { frameAgeMs }) => {
    const el = valueRef.current
    if (!el) return
    if (!frame || (frameAgeMs ?? 0) > 1500) { el.textContent = '—'; return }
    el.textContent = pickField(frame, kind).toFixed(0)
  })
  return <div ref={valueRef} className={cx(VALUE_BASE, VALUE_COMPACT)}>—</div>
}

function StandardBody({ kind }: { kind: string }) {
  const valueRef = useRef<HTMLDivElement>(null)
  const metaRef  = useRef<HTMLDivElement>(null)
  useFrameLoop((frame, { frameAgeMs }) => {
    if (!valueRef.current || !metaRef.current) return
    if (!frame || (frameAgeMs ?? 0) > 1500) {
      valueRef.current.textContent = '—'
      metaRef.current.textContent = 'awaiting frames'
      return
    }
    valueRef.current.textContent = pickField(frame, kind).toFixed(1)
    metaRef.current.textContent  = `${kind} · ${Math.round(1000 / Math.max(1, frameAgeMs ?? 1))} Hz observed`
  })
  return (
    <>
      <div ref={valueRef} className={VALUE_BASE}>—</div>
      <div ref={metaRef}  className={META}>awaiting frames</div>
    </>
  )
}

function DetailedBody({ kind }: { kind: string }) {
  const valueRef = useRef<HTMLDivElement>(null)
  const bufRef = useRef(new Float32Array(256))
  const headRef = useRef(0)

  useFrameLoop((frame, { frameAgeMs }) => {
    if (!frame || (frameAgeMs ?? 0) > 1500) return
    const v = pickField(frame, kind)
    const buf = bufRef.current
    buf[headRef.current] = v
    headRef.current = (headRef.current + 1) % buf.length
    if (valueRef.current) valueRef.current.textContent = v.toFixed(1)
  })

  const canvasRef = useCanvas(({ ctx, w, h }) => {
    ctx.clearRect(0, 0, w, h)
    const buf = bufRef.current
    const n = buf.length
    let min = Infinity, max = -Infinity
    for (let i = 0; i < n; i++) {
      const v = buf[i] ?? 0
      if (v < min) min = v
      if (v > max) max = v
    }
    if (!isFinite(min) || min === max) { min = 0; max = 1 }

    ctx.lineWidth = 1.5
    ctx.strokeStyle = 'rgba(255, 193, 220, 0.85)'
    ctx.beginPath()
    const head = headRef.current
    for (let i = 0; i < n; i++) {
      const idx = (head + i) % n
      const x = (i / (n - 1)) * w
      const y = h - (((buf[idx] ?? 0) - min) / (max - min)) * (h - 2) - 1
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.stroke()

    const grad = ctx.createLinearGradient(0, 0, 0, h)
    grad.addColorStop(0, 'rgba(255, 94, 167, 0.22)')
    grad.addColorStop(1, 'rgba(255, 94, 167, 0)')
    ctx.fillStyle = grad
    ctx.lineTo(w, h)
    ctx.lineTo(0, h)
    ctx.closePath()
    ctx.fill()
  })

  return (
    <>
      <div ref={valueRef} className={cx(VALUE_BASE, VALUE_LG)}>—</div>
      <canvas ref={canvasRef} className={SPARK} />
      <div className={META}>{kind} · live sparkline</div>
    </>
  )
}

function pickField(frame: Frame, kind: string): number {
  switch (kind) {
    case 'speed_dial':     return (frame.motion?.speed_mps ?? 0) * 3.6
    case 'rpm_tape':       return frame.engine?.rpm ?? 0
    case 'tire_heatmap':   return (frame.wheels?.fl?.tireTemp_c ?? 0)
    case 'grip_budget':    return (frame.derived?.gripBudgetUsed ?? 0) * 100
    case 'lap_predict':    return frame.race?.currentLapS ?? 0
    case 'finish_predict': return frame.race?.position ?? 0
    case 'shift_coach':    return frame.drivetrain?.gear ?? 0
    case 'session_summary':return frame.race?.lap ?? 0
    case 'fingerprint':    return (frame.derived?.throttleSmoothness ?? 0) * 100
    case 'coach_feed':     return frame.race?.lap ?? 0
    default:               return frame.t ?? 0
  }
}
