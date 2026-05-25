// client/src/components/widgets/PositionTracker.tsx
import { useRef } from 'react'
import type { RefObject } from 'react'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { cx } from '@/shared/lib/format'

function ordinal(n: number | null): string {
  if (n == null || n <= 0) return '—'
  const v = Math.abs(n) % 100
  const last = v % 10
  if (v >= 11 && v <= 13) return n + 'th'
  if (last === 1) return n + 'st'
  if (last === 2) return n + 'nd'
  if (last === 3) return n + 'rd'
  return n + 'th'
}

const WRAP =
  'relative w-full h-full flex flex-col items-center justify-center px-3 py-2 gap-1 ' +
  'overflow-hidden [container-type:inline-size] ' +
  'before:content-[""] before:absolute before:inset-0 before:rounded-[inherit] before:pointer-events-none ' +
  'before:[background:radial-gradient(ellipse_at_50%_50%,color-mix(in_srgb,var(--mint)_8%,transparent),transparent_70%)]'

const CUR =
  'relative z-[1] font-display font-bold text-cream [font-variant-numeric:tabular-nums] ' +
  '[letter-spacing:0.02em] max-w-full [font-size:clamp(28px,22cqi,60px)] ' +
  '[text-shadow:0_0_18px_color-mix(in_srgb,var(--mint)_50%,transparent)]'

const ROW = 'relative z-[1] flex items-baseline gap-2'

const LBL_BASE = 'font-display font-normal text-[12px] [letter-spacing:0.16em] text-ink-faint'
const LBL_STANDARD = 'text-[14px]'
const LBL_HERO = 'text-[16px]'

const VAL_BASE = 'font-mono font-semibold text-[13px] text-cream [font-variant-numeric:tabular-nums]'
const VAL_STANDARD = 'text-[14px]'
const VAL_HERO = 'text-[16px]'

const VAL_WORST = 'text-ink-faint'

const DELTA =
  'data-[sign=up]:font-bold data-[sign=up]:text-mint ' +
  'data-[sign=down]:font-bold data-[sign=down]:text-pink ' +
  'data-[sign=neutral]:text-ink-faint'

export interface PositionTrackerProps {
  w: number
  h: number
}

export default function PositionTracker({ w, h }: PositionTrackerProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 6 ? 'standard' : 'hero'

  const curRef   = useRef<HTMLDivElement>(null)
  const bestRef  = useRef<HTMLSpanElement>(null)
  const worstRef = useRef<HTMLSpanElement>(null)
  const deltaRef = useRef<HTMLSpanElement>(null)

  const bestPosRef  = useRef<number | null>(null)
  const worstPosRef = useRef<number | null>(null)
  const lastFrameSessionRef = useRef<string | null>(null)

  useFrameLoop((frame, { frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const pos = stale ? null : (frame!.race?.position ?? null)
    const sid = stale ? null : (frame!.sessionId ?? null)

    if (sid !== lastFrameSessionRef.current) {
      lastFrameSessionRef.current = sid
      bestPosRef.current  = null
      worstPosRef.current = null
    }

    if (pos != null && pos > 0) {
      if (bestPosRef.current  == null || pos < bestPosRef.current)  bestPosRef.current = pos
      if (worstPosRef.current == null || pos > worstPosRef.current) worstPosRef.current = pos
    }

    const set = (ref: RefObject<Element>, val: string): void => {
      if (ref.current && ref.current.textContent !== val) ref.current.textContent = val
    }

    if (curRef.current)   set(curRef,  ordinal(pos))
    if (bestRef.current)  set(bestRef, ordinal(bestPosRef.current))
    if (worstRef.current) set(worstRef, ordinal(worstPosRef.current))

    if (deltaRef.current) {
      if (pos != null && bestPosRef.current != null) {
        const d = pos - bestPosRef.current
        const sign = d > 0 ? 'down' : d < 0 ? 'up' : 'neutral'
        set(deltaRef, d === 0 ? '·' : (d > 0 ? `▼${d}` : `▲${Math.abs(d)}`))
        if (deltaRef.current.dataset['sign'] !== sign) deltaRef.current.dataset['sign'] = sign
      } else {
        set(deltaRef, '—')
        if (deltaRef.current.dataset['sign']) delete deltaRef.current.dataset['sign']
      }
    }
  })

  const lblCls = cx(LBL_BASE, tier === 'standard' && LBL_STANDARD, tier === 'hero' && LBL_HERO)
  const valCls = cx(VAL_BASE, tier === 'standard' && VAL_STANDARD, tier === 'hero' && VAL_HERO)

  return (
    <div className={WRAP}>
      <div className={CUR} ref={curRef}>—</div>
      {tier !== 'compact' && (
        <div className={ROW}>
          <span className={lblCls}>BEST</span>
          <span className={valCls} ref={bestRef}>—</span>
        </div>
      )}
      {tier === 'hero' && (
        <>
          <div className={ROW}>
            <span className={lblCls}>WORST</span>
            <span className={cx(valCls, VAL_WORST)} ref={worstRef}>—</span>
          </div>
          <div className={ROW}>
            <span className={lblCls}>Δ FROM BEST</span>
            <span className={cx(valCls, DELTA)} ref={deltaRef}>—</span>
          </div>
        </>
      )}
    </div>
  )
}
