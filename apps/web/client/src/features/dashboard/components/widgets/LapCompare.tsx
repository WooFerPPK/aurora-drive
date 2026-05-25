// client/src/components/widgets/LapCompare.tsx
import { useRef } from 'react'
import type { CSSProperties, RefObject } from 'react'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { cx, formatLapTime } from '@/shared/lib/format'

const WRAP =
  'w-full h-full flex flex-col justify-center gap-[3px] px-2.5 py-1.5 [container-type:inline-size]'

const PAIR = 'grid grid-cols-[1fr_auto_1fr] items-stretch flex-1 min-h-0'

const CELL = 'flex flex-col justify-center gap-0.5 min-w-0 px-1'

const LBL_BASE = 'font-display font-normal text-[12px] [letter-spacing:0.18em] text-ink-faint whitespace-nowrap'
const LBL_STANDARD = 'text-[14px]'
const LBL_HERO = 'text-[16px]'

const VAL_BASE =
  'font-mono font-bold text-[16px] text-cream [font-variant-numeric:tabular-nums] ' +
  'min-w-0 overflow-hidden text-ellipsis'
const VAL_STANDARD = 'text-[20px]'
const VAL_HERO = 'text-[24px]'

const VAL_BEST =
  'text-mint ' +
  '[text-shadow:0_0_10px_color-mix(in_srgb,var(--mint)_40%,transparent)]'

const DIVIDER = 'w-px bg-[rgba(253,233,255,0.10)] mx-2'

const DELTA_ROW = 'flex items-baseline gap-2 pt-[3px] border-t border-[rgba(253,233,255,0.08)]'

const DELTA_LBL_BASE = 'font-display font-medium text-[12px] text-ink-faint'
const DELTA_LBL_HERO_STD = 'text-[14px]'
const DELTA_LBL_HERO = 'text-[16px]'

const DELTA_VAL_BASE =
  'font-mono font-bold text-[12px] text-ink-faint [font-variant-numeric:tabular-nums] ' +
  'data-[sign=up]:text-mint data-[sign=down]:text-pink'
const DELTA_VAL_HERO_STD = 'text-[14px]'
const DELTA_VAL_HERO = 'text-[16px]'

const DELTA_PCT_BASE =
  'font-mono font-normal text-[12px] text-ink-faint [font-variant-numeric:tabular-nums] ml-auto'
const DELTA_PCT_HERO_STD = 'text-[14px]'
const DELTA_PCT_HERO = 'text-[16px]'

const BAR_WRAP = 'relative h-1.5 mt-1'
const BAR_TRACK = 'absolute inset-0 rounded-[3px] bg-[rgba(255,193,220,0.08)]'
const BAR_MID = 'absolute -top-0.5 -bottom-0.5 left-1/2 w-px bg-[rgba(253,233,255,0.18)]'
const BAR_FILL =
  'absolute top-0 bottom-0 rounded-[3px] left-1/2 bg-mint ' +
  '[width:calc(abs(var(--bar-val,0))*50%)] ' +
  '[transition:width_200ms,background_200ms] [transform-origin:50%_50%] ' +
  'data-[sign=down]:left-auto data-[sign=down]:right-1/2 data-[sign=down]:bg-pink ' +
  'data-[sign=down]:[box-shadow:0_0_8px_color-mix(in_srgb,var(--pink)_50%,transparent)] ' +
  'data-[sign=up]:left-1/2 data-[sign=up]:bg-mint ' +
  'data-[sign=up]:[box-shadow:0_0_8px_color-mix(in_srgb,var(--mint)_50%,transparent)]'

export interface LapCompareProps {
  w: number
  h: number
}

export default function LapCompare({ h }: LapCompareProps) {
  const tier = h <= 1 ? 'compact' : h <= 2 ? 'standard' : 'hero'

  const lastRef     = useRef<HTMLDivElement>(null)
  const bestRef     = useRef<HTMLDivElement>(null)
  const deltaRef    = useRef<HTMLSpanElement>(null)
  const deltaPctRef = useRef<HTMLSpanElement>(null)
  const barRef      = useRef<HTMLDivElement>(null)

  useFrameLoop((frame, { frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const r     = stale ? null : (frame!.race ?? null)

    const setText = (ref: RefObject<Element>, val: string): void => {
      if (ref.current && ref.current.textContent !== val)
        ref.current.textContent = val
    }

    const lastS = r?.lastLapS
    const bestS = r?.bestLapS

    setText(lastRef, formatLapTime(lastS))
    setText(bestRef, formatLapTime(bestS))

    if (deltaRef.current) {
      if (lastS != null && bestS != null && lastS > 0 && bestS > 0 && isFinite(lastS) && isFinite(bestS)) {
        const d = lastS - bestS
        const sign = d > 0.001 ? 'down' : d < -0.001 ? 'up' : 'neutral'
        const text = `${d >= 0 ? '+' : ''}${d.toFixed(3)}s`
        setText(deltaRef, text)
        if (deltaRef.current.dataset['sign'] !== sign) deltaRef.current.dataset['sign'] = sign

        if (deltaPctRef.current) {
          const pct = (d / bestS) * 100
          const pctText = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
          setText(deltaPctRef, pctText)
        }

        if (barRef.current) {
          const clamped = Math.max(-1, Math.min(1, d / Math.max(0.5, bestS * 0.05)))
          barRef.current.style.setProperty('--bar-val', `${clamped.toFixed(3)}`)
          barRef.current.dataset['sign'] = sign
        }
      } else {
        setText(deltaRef, '—')
        if (deltaRef.current.dataset['sign']) delete deltaRef.current.dataset['sign']
        if (deltaPctRef.current) setText(deltaPctRef, '')
        if (barRef.current) {
          barRef.current.style.setProperty('--bar-val', '0')
          if (barRef.current.dataset['sign']) delete barRef.current.dataset['sign']
        }
      }
    }
  })

  const barStyle = { '--bar-val': 0 } as CSSProperties

  const lblCls = cx(LBL_BASE, tier === 'standard' && LBL_STANDARD, tier === 'hero' && LBL_HERO)
  const valCls = cx(VAL_BASE, tier === 'standard' && VAL_STANDARD, tier === 'hero' && VAL_HERO)
  const deltaLblCls = cx(DELTA_LBL_BASE, tier === 'standard' && DELTA_LBL_HERO_STD, tier === 'hero' && DELTA_LBL_HERO)
  const deltaValCls = cx(DELTA_VAL_BASE, tier === 'standard' && DELTA_VAL_HERO_STD, tier === 'hero' && DELTA_VAL_HERO)
  const deltaPctCls = cx(DELTA_PCT_BASE, tier === 'standard' && DELTA_PCT_HERO_STD, tier === 'hero' && DELTA_PCT_HERO)

  return (
    <div className={WRAP}>
      <div className={PAIR}>
        <div className={CELL}>
          <div className={lblCls}>LAST</div>
          <div className={valCls} ref={lastRef}>—</div>
        </div>
        <div className={DIVIDER} />
        <div className={CELL}>
          <div className={lblCls}>BEST</div>
          <div className={cx(valCls, VAL_BEST)} ref={bestRef}>—</div>
        </div>
      </div>
      {tier !== 'compact' && (
        <div className={DELTA_ROW}>
          <span className={deltaLblCls}>Δ</span>
          <span className={deltaValCls} ref={deltaRef}>—</span>
          <span className={deltaPctCls} ref={deltaPctRef} />
        </div>
      )}
      {tier === 'hero' && (
        <div className={BAR_WRAP}>
          <div className={BAR_TRACK} />
          <div className={BAR_MID} />
          <div className={BAR_FILL} ref={barRef} style={barStyle} />
        </div>
      )}
    </div>
  )
}
