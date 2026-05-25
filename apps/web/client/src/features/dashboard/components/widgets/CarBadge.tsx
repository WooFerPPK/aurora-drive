// client/src/components/widgets/CarBadge.tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { components } from '@fh-racer/contract/api'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { useListCarsQuery } from '@/shared/hooks/queries/cars'
import { cx } from '@/shared/lib/format'

// car_badge — active car identity card.

type CarSummary = components['schemas']['CarSummary']
type Drivetrain = CarSummary['drivetrain']

const DT_COL: Record<Drivetrain, string> = { AWD: 'var(--mint)', RWD: 'var(--pink)', FWD: 'var(--butter)' }

const WRAP =
  'w-full h-full flex flex-col justify-center px-[14px] py-[8px] gap-1 ' +
  '[background:linear-gradient(135deg,transparent_0%,rgba(202,166,255,0.04)_100%)]'

const WRAP_EMPTY = 'justify-center items-center'

const NAME =
  'font-display font-bold text-cream [letter-spacing:0.02em] whitespace-nowrap overflow-hidden text-ellipsis ' +
  '[font-size:clamp(15px,6cqi,22px)] ' +
  '[text-shadow:0_0_10px_color-mix(in_srgb,var(--lilac)_40%,transparent)]'

const META = 'flex gap-2 items-baseline flex-wrap'

const CLASS_BASE = 'font-display font-bold text-[12px] text-butter [letter-spacing:0.08em]'
const CLASS_STANDARD = 'text-[14px]'
const CLASS_HERO = 'text-[16px]'

const PI_BASE = 'font-mono font-semibold text-[12px] text-ink-faint [font-variant-numeric:tabular-nums]'
const PI_STANDARD = 'text-[14px]'
const PI_HERO = 'text-[16px]'

const DT_BASE =
  'font-display font-bold text-[12px] [letter-spacing:0.18em] ' +
  'text-[color:var(--dt-col,var(--mint))] ' +
  'px-1.5 py-px rounded-full ml-auto ' +
  'border border-[color:var(--dt-col,var(--mint))]'
const DT_STANDARD = 'text-[14px]'
const DT_HERO = 'text-[16px]'

const EXTRA_BASE = 'flex gap-2.5 mt-px font-mono font-normal text-[12px] text-ink-faint'
const EXTRA_HERO = 'text-[16px]'

const EMPTY_CAPTION = 'font-ui font-normal text-[10px] text-ink-faint'

export interface CarBadgeProps {
  w: number
  h: number
}

export default function CarBadge({ w, h }: CarBadgeProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 6 ? 'standard' : 'hero'

  const { data: carList } = useListCarsQuery()
  const carsById = useMemo<Record<string, CarSummary>>(() => {
    const map: Record<string, CarSummary> = {}
    for (const c of carList?.cars ?? []) map[c.id] = c
    return map
  }, [carList])

  const [active, setActive] = useState<CarSummary | null>(null)
  const lastCarIdRef        = useRef<string | null>(null)

  useFrameLoop((frame) => {
    const cid = frame?.carId ? String(frame.carId) : null
    if (cid !== lastCarIdRef.current) {
      lastCarIdRef.current = cid
      setActive(cid ? (carsById[cid] ?? null) : null)
    }
  })

  useEffect(() => {
    if (lastCarIdRef.current) setActive(carsById[lastCarIdRef.current] ?? null)
  }, [carsById])

  if (!active) {
    return (
      <div className={cx(WRAP, WRAP_EMPTY)}>
        <div className={EMPTY_CAPTION}>No active car</div>
      </div>
    )
  }

  const dt = active.drivetrain
  const dtColor = DT_COL[dt] ?? 'var(--mint)'
  const dtStyle = { '--dt-col': dtColor } as CSSProperties

  const classCls = cx(CLASS_BASE, tier === 'standard' && CLASS_STANDARD, tier === 'hero' && CLASS_HERO)
  const piCls    = cx(PI_BASE,    tier === 'standard' && PI_STANDARD,    tier === 'hero' && PI_HERO)
  const dtCls    = cx(DT_BASE,    tier === 'standard' && DT_STANDARD,    tier === 'hero' && DT_HERO)
  const extraCls = cx(EXTRA_BASE,                                       tier === 'hero' && EXTRA_HERO)

  return (
    <div className={WRAP}>
      <div className={NAME}>{active.display || active.short || 'Unknown'}</div>
      {tier !== 'compact' && (
        <div className={META}>
          <span className={classCls}>{active.class ?? '—'}</span>
          <span className={piCls}>PI {active.pi ?? '—'}</span>
          <span className={dtCls} style={dtStyle}>{dt}</span>
        </div>
      )}
      {tier === 'hero' && (
        <div className={extraCls}>
          <span>#{active.ordinal ?? '—'}</span>
          <span>{active.sessionCount ?? 0} sessions</span>
          {active.totalSecondsDriven != null && (
            <span>{Math.round(active.totalSecondsDriven / 60)} min</span>
          )}
        </div>
      )}
    </div>
  )
}
