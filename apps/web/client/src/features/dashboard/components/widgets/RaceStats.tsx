// client/src/components/widgets/RaceStats.tsx
import { useRef } from 'react'
import type { RefObject } from 'react'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { cx } from '@/shared/lib/format'

// race_stats — compact live race info strip.

function formatRaceTime(s: number | null | undefined): string {
  if (s == null || s < 0) return '—'
  const total = Math.floor(s)
  const m = Math.floor(total / 60)
  const sec = total - m * 60
  if (m >= 60) {
    const hh = Math.floor(m / 60)
    return `${hh}:${String(m - hh * 60).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }
  return `${m}:${String(sec).padStart(2, '0')}`
}

function formatDistanceKm(m: number | null | undefined): string {
  if (m == null || m < 0) return '—'
  return m < 1000 ? `${m.toFixed(0)} m` : `${(m / 1000).toFixed(2)} km`
}

const WRAP = 'w-full h-full flex flex-col px-3 py-2 gap-1.5'

const GRID_BASE = 'grid flex-1 gap-1.5 grid-cols-2'
const GRID_STANDARD = 'grid-cols-3'
const GRID_HERO     = 'grid-cols-4'

const CELL =
  'flex flex-col justify-center px-2.5 py-1.5 bg-[rgba(255,255,255,0.03)] ' +
  'rounded-lg border-l-2 border-lilac min-w-0'

const LBL_BASE =
  'font-display font-normal text-[12px] [letter-spacing:0.18em] uppercase ' +
  'text-ink-faint whitespace-nowrap overflow-hidden text-ellipsis'
const LBL_STANDARD = 'text-[14px] [letter-spacing:0.12em]'
const LBL_HERO     = 'text-[14px] [letter-spacing:0.10em]'

const VAL_BASE =
  'font-mono font-bold text-[16px] text-cream whitespace-nowrap overflow-hidden text-ellipsis ' +
  '[font-variant-numeric:tabular-nums]'
const VAL_HERO = 'text-[18px]'

const VAL_MAIN =
  '[font-size:clamp(20px,8cqi,30px)] text-cream ' +
  '[text-shadow:0_0_12px_color-mix(in_srgb,var(--mint)_40%,transparent)]'

const VAL_MONO_BASE = 'text-[14px]'
const VAL_MONO_HERO = 'text-[18px]'

export interface RaceStatsProps {
  w: number
  h: number
}

export default function RaceStats({ w, h }: RaceStatsProps) {
  const tier = w * h <= 4 ? 'compact' : w * h <= 6 ? 'standard' : 'hero'

  const posRef   = useRef<HTMLDivElement>(null)
  const lapRef   = useRef<HTMLDivElement>(null)
  const timeRef  = useRef<HTMLDivElement>(null)
  const distRef  = useRef<HTMLDivElement>(null)

  const distanceRef = useRef(0)

  useFrameLoop((frame, { dt, frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const r = stale ? null : (frame!.race ?? null)
    const speed = stale ? 0 : (frame!.motion?.speed_mps ?? 0)

    if (!stale) distanceRef.current += speed * dt

    const set = (ref: RefObject<HTMLDivElement>, val: string): void => {
      if (ref.current && ref.current.textContent !== val)
        ref.current.textContent = val
    }

    if (posRef.current) {
      const p = r?.position
      set(posRef, p != null && p > 0 ? `P${p}` : '—')
    }
    if (lapRef.current) {
      const l = r?.lap
      set(lapRef, l != null && l > 0 ? `L${l}` : '—')
    }
    if (timeRef.current) {
      set(timeRef, formatRaceTime(r?.raceTimeS))
    }
    if (distRef.current) {
      set(distRef, formatDistanceKm(distanceRef.current))
    }
  })

  const gridCls = cx(GRID_BASE, tier === 'standard' && GRID_STANDARD, tier === 'hero' && GRID_HERO)
  const lblCls  = cx(LBL_BASE, tier === 'standard' && LBL_STANDARD, tier === 'hero' && LBL_HERO)
  const valCls  = cx(VAL_BASE, tier === 'hero' && VAL_HERO)
  const monoCls = cx(VAL_BASE, VAL_MONO_BASE, tier === 'hero' && VAL_MONO_HERO)

  return (
    <div className={WRAP}>
      <div className={gridCls}>
        <div className={CELL}>
          <div className={lblCls}>POS</div>
          <div ref={posRef} className={cx(valCls, VAL_MAIN)}>—</div>
        </div>
        <div className={CELL}>
          <div className={lblCls}>LAP</div>
          <div ref={lapRef} className={valCls}>—</div>
        </div>
        {tier !== 'compact' && (
          <div className={CELL}>
            <div className={lblCls}>TIME</div>
            <div ref={timeRef} className={monoCls}>—</div>
          </div>
        )}
        {tier === 'hero' && (
          <div className={CELL}>
            <div className={lblCls}>DIST</div>
            <div ref={distRef} className={monoCls}>—</div>
          </div>
        )}
      </div>
    </div>
  )
}
