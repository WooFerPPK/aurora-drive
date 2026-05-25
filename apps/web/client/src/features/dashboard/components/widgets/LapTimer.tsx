// client/src/components/widgets/LapTimer.tsx
import { useRef } from 'react'
import type { RefObject } from 'react'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { cx, formatLapTime } from '@/shared/lib/format'
import { ConfettiBurst } from '@/shared/components/widgetPrimitives'
import type { ConfettiBurstHandle } from '@/shared/components/widgetPrimitives/ConfettiBurst'

export interface LapTimerProps {
  w: number
  h: number
}

const WRAP =
  'relative w-full h-full flex flex-col justify-center gap-[2px] px-[10px] py-[4px] ' +
  '[background:linear-gradient(90deg,transparent_0%,rgba(202,166,255,0.03)_50%,transparent_100%)]'

const WRAP_COMPACT = 'px-[10px] py-[2px]'

const SEP = 'h-px bg-[rgba(253,233,255,0.07)] my-px'

const ROW = 'flex items-baseline justify-between gap-2'

const LBL_BASE =
  'font-display font-medium text-[12px] tracking-[0.14em] uppercase text-ink-faint'
const LBL_STANDARD = 'text-[14px]'
const LBL_HERO     = 'text-[16px]'

const VAL_BASE =
  'font-mono font-semibold text-[13px] text-ink-faint [font-variant-numeric:tabular-nums]'
const VAL_STANDARD = 'text-[14px]'
const VAL_HERO     = 'text-[16px]'

const VAL_MAIN_BASE =
  'text-cream [font-size:clamp(16px,5.5cqi,26px)] ' +
  '[text-shadow:0_0_12px_color-mix(in_srgb,var(--lilac)_40%,transparent)]'
const VAL_MAIN_COMPACT = '[font-size:clamp(20px,7cqi,32px)]'

const VAL_BEST = 'text-mint'

const DELTA_BASE =
  'font-mono font-semibold text-[13px] [font-variant-numeric:tabular-nums] ' +
  'data-[sign=up]:font-bold data-[sign=up]:text-mint ' +
  'data-[sign=down]:font-bold data-[sign=down]:text-pink ' +
  'text-ink-faint'

export default function LapTimer({ h }: LapTimerProps) {
  const tier = h <= 1 ? 'compact' : h <= 2 ? 'standard' : 'hero'

  const curRef   = useRef<HTMLSpanElement>(null)
  const lastRef  = useRef<HTMLSpanElement>(null)
  const bestRef  = useRef<HTMLSpanElement>(null)
  const deltaRef = useRef<HTMLSpanElement>(null)
  const confettiRef = useRef<ConfettiBurstHandle>(null)
  const lastBestRef = useRef<number | null>(null)

  useFrameLoop((frame, { frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const r     = stale ? null : (frame!.race ?? null)

    const set = (ref: RefObject<HTMLSpanElement>, val: string): void => {
      if (ref.current && ref.current.textContent !== val)
        ref.current.textContent = val
    }

    set(curRef, formatLapTime(r?.currentLapS))
    if (lastRef.current) set(lastRef, formatLapTime(r?.lastLapS))
    if (bestRef.current) set(bestRef, formatLapTime(r?.bestLapS))

    const bb = r?.bestLapS
    if (bb != null && isFinite(bb) && bb > 0) {
      const prev = lastBestRef.current
      if (prev != null && bb < prev - 0.001) {
        confettiRef.current?.fire()
      }
      lastBestRef.current = bb
    } else if (bb == null) {
      lastBestRef.current = null
    }

    if (deltaRef.current) {
      const ll = r?.lastLapS
      if (ll != null && bb != null && ll >= 0 && bb >= 0 && isFinite(ll) && isFinite(bb)) {
        const d    = ll - bb
        const sign = d >= 0 ? 'down' : 'up'
        const text = `${d >= 0 ? '+' : ''}${d.toFixed(3)}s`
        set(deltaRef, text)
        if (deltaRef.current.dataset['sign'] !== sign) deltaRef.current.dataset['sign'] = sign
      } else {
        set(deltaRef, '—')
        if (deltaRef.current.dataset['sign']) delete deltaRef.current.dataset['sign']
      }
    }
  })

  const lblCls = cx(LBL_BASE, tier === 'standard' && LBL_STANDARD, tier === 'hero' && LBL_HERO)
  const valCls = cx(VAL_BASE, tier === 'standard' && VAL_STANDARD, tier === 'hero' && VAL_HERO)
  const mainCls = cx(valCls, VAL_MAIN_BASE, tier === 'compact' && VAL_MAIN_COMPACT)
  const bestCls = cx(valCls, VAL_BEST)

  return (
    <div className={cx(WRAP, tier === 'compact' && WRAP_COMPACT)}>
      <ConfettiBurst ref={confettiRef} colour="butter" />
      <div className={ROW}>
        <span className={lblCls}>LAP</span>
        <span ref={curRef} className={mainCls}>—</span>
      </div>
      {tier !== 'compact' && <>
        <div className={SEP} />
        <div className={ROW}>
          <span className={lblCls}>LAST</span>
          <span ref={lastRef} className={valCls}>—</span>
        </div>
        <div className={ROW}>
          <span className={lblCls}>BEST</span>
          <span ref={bestRef} className={bestCls}>—</span>
        </div>
      </>}
      {tier === 'hero' && <>
        <div className={SEP} />
        <div className={cx(ROW, 'pt-[3px]')}>
          <span className={lblCls}>Δ</span>
          <span ref={deltaRef} className={DELTA_BASE}>—</span>
        </div>
      </>}
    </div>
  )
}
