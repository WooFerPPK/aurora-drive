// client/src/components/widgets/GearDisplay.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { useCanvas }    from '@/shared/hooks/useCanvas'
import { drawWidgetBg, drawGaugeArc, valueColour, toRgb } from '@/shared/lib/canvasUtils'
import { BigNumber, MetricLabel } from '@/shared/components/widgetPrimitives'
import type { BigNumberValueOut } from '@/shared/components/widgetPrimitives/BigNumber'
import { cx } from '@/shared/lib/format'

const MAX_GEAR  = 7
const START_RAD = (150 * Math.PI) / 180
const SWEEP_RAD = (240 * Math.PI) / 180

function gearLabel(g: number | null): string {
  if (g == null) return '—'
  if (g <= 0)   return 'R'
  if (g > 10)   return '—'
  return String(g)
}

// `widget-gear` is kept as a marker class — index.css carries:
//   - .widget-gear[data-shift=up|down] .big-number-value { animation: shiftFlash... }
//   - .widget-gear .big-number { position: relative; inset: auto; ... } (overrides BigNumber positioning)
const WRAP =
  'widget-gear relative w-full h-full flex flex-col items-center justify-center gap-1 overflow-visible ' +
  'before:content-[""] before:absolute before:inset-0 before:rounded-[inherit] before:pointer-events-none ' +
  'before:[background:radial-gradient(ellipse_at_50%_40%,color-mix(in_srgb,var(--gear-col,var(--mint))_18%,transparent)_0%,transparent_65%)]'

const ARC_CANVAS = 'absolute inset-0 w-full h-full rounded-[inherit]'

const DOTS_ROW = 'relative z-[1] flex gap-[7px] items-center'

const DOT =
  'w-1.5 h-1.5 rounded-full bg-[rgba(253,233,255,0.12)] ' +
  '[transition:background_150ms,box-shadow_150ms] ' +
  '[&.active]:bg-[color:var(--gear-col,var(--mint))] ' +
  '[&.active]:[box-shadow:0_0_8px_var(--gear-col,var(--mint))]'

const DT_BASE =
  'relative z-[1] font-display font-medium text-[12px] text-ink-faint [letter-spacing:0.12em] uppercase'
const DT_HERO = 'text-[16px]'

const CLUTCH =
  'relative z-[1] font-mono font-medium text-[8px] text-[rgba(253,233,255,0.2)] [letter-spacing:0.18em] ' +
  'px-2 py-0.5 border border-[rgba(253,233,255,0.12)] rounded-full [transition:all_120ms] ' +
  '[&.on]:text-butter [&.on]:border-butter'

export interface GearDisplayProps {
  w: number
  h: number
}

export default function GearDisplay({ w, h }: GearDisplayProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 9 ? 'standard' : 'hero'

  const wrapRef     = useRef<HTMLDivElement>(null)
  const dtRef       = useRef<HTMLDivElement>(null)
  const clutchRef   = useRef<HTMLDivElement>(null)
  const dotsRef     = useRef<HTMLDivElement>(null)
  const lastGearRef = useRef<number | null>(null)
  const flashUntil  = useRef(0)

  const numberGetter = (frame: Frame | null): BigNumberValueOut | null => {
    if (!frame) return null
    const g = frame.drivetrain?.gear ?? null
    const label = gearLabel(g)
    if (g != null && wrapRef.current) {
      if (lastGearRef.current != null && g !== lastGearRef.current) {
        wrapRef.current.dataset['shift'] = g > lastGearRef.current ? 'up' : 'down'
        flashUntil.current = performance.now() + 280
      }
      if (flashUntil.current && performance.now() > flashUntil.current) {
        delete wrapRef.current.dataset['shift']
        flashUntil.current = 0
      }
      lastGearRef.current = g
      const gv = Math.max(0, Math.min(1, (g - 1) / (MAX_GEAR - 1)))
      return { display: label, normalized: gv }
    }
    return { display: label }
  }

  useFrameLoop((frame, { frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const g     = stale ? null : (frame!.drivetrain?.gear ?? null)
    if (dtRef.current && tier !== 'compact') {
      const t2 = stale ? '—' : (frame!.drivetrain?.type ?? '—')
      if (dtRef.current.textContent !== t2) dtRef.current.textContent = t2
    }
    if (clutchRef.current && tier === 'hero') {
      const on = !stale && (frame!.drivetrain?.clutch ?? 0) > 0.5
      clutchRef.current.classList.toggle('on', on)
    }
    if (dotsRef.current && g != null) {
      const dots = dotsRef.current.children
      for (let i = 0; i < dots.length; i++) {
        dots[i]!.classList.toggle('active', i + 1 === g)
      }
    }
    if (wrapRef.current && g != null) {
      const gv  = Math.max(0, Math.min(1, (g - 1) / (MAX_GEAR - 1)))
      const col = valueColour(gv)
      wrapRef.current.style.setProperty('--gear-col', toRgb(col))
    }
  })

  const arcRef = useCanvas(({ ctx, w: cw, h: ch, frame, frameAgeMs }) => {
    if (tier !== 'hero') { ctx.clearRect(0, 0, cw, ch); return }
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const g     = stale ? 1 : Math.max(1, frame!.drivetrain?.gear ?? 1)
    const gv    = Math.max(0, Math.min(1, (g - 1) / (MAX_GEAR - 1)))
    drawWidgetBg(ctx, cw, ch)
    const cxv = cw / 2, cy = ch / 2 - 8
    const r  = Math.min(cw, ch) * 0.42 - 8
    drawGaugeArc(ctx, cxv, cy, r, START_RAD, SWEEP_RAD, gv, 8, 16)
  })

  const dots = Array.from({ length: MAX_GEAR }, (_, i) => (
    <span key={i} className={DOT} />
  ))

  return (
    <div ref={wrapRef} className={cx(WRAP, 'radial-gauge-wrap')}>
      {tier === 'hero' && <canvas ref={arcRef} className={ARC_CANVAS} />}
      <BigNumber tier={tier} getValue={numberGetter} />
      {tier !== 'compact' && (
        <div ref={dotsRef} className={DOTS_ROW}>{dots}</div>
      )}
      {tier === 'hero' && <div ref={dtRef}     className={cx(DT_BASE, DT_HERO)}>—</div>}
      {tier === 'hero' && <div ref={clutchRef} className={CLUTCH}><MetricLabel text="CLUTCH" tier="hero" /></div>}
    </div>
  )
}
