// client/src/components/widgets/StintTimer.tsx
import { useRef } from 'react'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { cx } from '@/shared/lib/format'

function formatStint(s: number | null): string {
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

function stintTone(s: number | null): string {
  if (s == null) return 'idle'
  if (s < 20 * 60) return 'fresh'
  if (s < 40 * 60) return 'mid'
  return 'long'
}

export interface StintTimerProps {
  w: number
  h: number
}

const WRAP_BASE =
  'relative w-full h-full flex flex-col items-end justify-center px-[14px] py-[6px] ' +
  '[--tone-col:var(--mint)] ' +
  'data-[tone=mid]:[--tone-col:var(--butter)] ' +
  'data-[tone=long]:[--tone-col:var(--pink)] ' +
  'data-[tone=idle]:[--tone-col:var(--ink-faint)]'

const WRAP_COMPACT =
  'flex-row items-center gap-[10px] px-[12px] py-[4px]'

const TIME_CLASS =
  'font-mono font-bold [font-variant-numeric:tabular-nums] ' +
  '[font-size:clamp(24px,12cqi,48px)] text-[color:var(--tone-col)] ' +
  '[text-shadow:0_0_14px_color-mix(in_srgb,var(--tone-col)_45%,transparent)] ' +
  '[transition:color_600ms,text-shadow_600ms]'

export default function StintTimer({ w, h }: StintTimerProps) {
  const tier = h <= 1 ? 'compact' : (w >= 4 ? 'hero' : 'standard')

  const timerRef     = useRef<HTMLDivElement>(null)
  const startedAtRef = useRef<number | null>(null)
  const sessionIdRef = useRef<string | null>(null)
  const wrapperRef   = useRef<HTMLDivElement>(null)

  useFrameLoop((frame, { frameAgeMs }) => {
    const stale = !frame || (frameAgeMs ?? 0) > 1500
    const sid = stale ? null : (frame!.sessionId ?? null)
    const raceTime = stale ? null : (frame!.race?.raceTimeS ?? null)

    if (sid !== sessionIdRef.current) {
      sessionIdRef.current = sid
      startedAtRef.current = sid ? Date.now() : null
    }

    let stintS: number | null = null
    if (raceTime != null && raceTime > 0) {
      stintS = raceTime
    } else if (startedAtRef.current != null) {
      stintS = (Date.now() - startedAtRef.current) / 1000
    }

    if (timerRef.current) {
      const text = formatStint(stintS)
      if (timerRef.current.textContent !== text) timerRef.current.textContent = text
    }
    if (wrapperRef.current) {
      const tone = stintTone(stintS)
      if (wrapperRef.current.dataset['tone'] !== tone) wrapperRef.current.dataset['tone'] = tone
    }
  })

  return (
    <div
      ref={wrapperRef}
      data-tone="idle"
      className={cx(WRAP_BASE, tier === 'compact' && WRAP_COMPACT)}
    >
      <div ref={timerRef} className={TIME_CLASS}>—</div>
    </div>
  )
}
