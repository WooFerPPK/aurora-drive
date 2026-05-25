// client/src/lib/widgetPrimitives/BigNumber.tsx
import { useRef } from 'react'
import type { Frame } from '@fh-racer/contract/ws'
import { useFrameLoop } from '@/shared/hooks/useFrameLoop'
import { valueColour, toRgb, ease } from '@/shared/lib/canvasUtils'
import type { TickTier } from '@/shared/lib/canvasUtils'
import { EASE_VALUE } from './easeConstants'

// <BigNumber>
//   Mono digit panel that mutates DOM text + glow each frame via
//   useFrameLoop (no React state on the hot path). DOM text stays sharp
//   at any size; canvas-drawn text was blurry on small widgets.

export interface BigNumberValueOut {
  display: string
  normalized?: number | null
}

export type BigNumberGetValue = (frame: Frame | null) => BigNumberValueOut | string | null | undefined

export interface BigNumberProps {
  getValue: BigNumberGetValue
  tier?: TickTier
  unit?: string
  className?: string
  ignoreStale?: boolean
}

const FIT_W: Record<TickTier, number> = { compact: 0.82, standard: 0.72, hero: 0.62 }
const FIT_H: Record<TickTier, number> = { compact: 0.45, standard: 0.30, hero: 0.30 }

let measureCtx: CanvasRenderingContext2D | null = null
function getMeasureCtx(): CanvasRenderingContext2D | null {
  if (!measureCtx && typeof document !== 'undefined') {
    measureCtx = document.createElement('canvas').getContext('2d')
  }
  return measureCtx
}

function fitFontSize(content: string, maxWidth: number, maxHeight: number): number {
  const cap = Math.max(14, Math.round(maxHeight))
  const ctx = getMeasureCtx()
  if (!ctx || !content) return cap
  ctx.font = `700 ${cap}px "Unbounded", system-ui, sans-serif`
  const measured = ctx.measureText(content).width
  if (measured <= maxWidth || measured <= 0) return cap
  return Math.max(14, Math.floor(cap * (maxWidth / measured)))
}

export default function BigNumber({ getValue, tier = 'standard', unit, className = '', ignoreStale = false }: BigNumberProps) {
  const wrapRef  = useRef<HTMLDivElement>(null)
  const numRef   = useRef<HTMLSpanElement>(null)
  const unitRef  = useRef<HTMLSpanElement>(null)
  const valueEaseRef = useRef(0)
  const lastDisplayRef = useRef('')
  const lastFitKeyRef  = useRef('')
  // Cache the computed position once — CSS classes don't toggle on this
  // div at runtime, so the answer is stable for the component's lifetime.
  const isAbsoluteRef = useRef<boolean | null>(null)

  useFrameLoop((frame, { dt, frameAgeMs }) => {
    const stale = !ignoreStale && (!frame || (frameAgeMs ?? 0) > 1500)
    let display = '—'
    let normalized: number | null = null
    if (!stale) {
      const out = getValue(frame) ?? null
      if (out && typeof out === 'object') {
        display = out.display ?? '—'
        normalized = typeof out.normalized === 'number' ? out.normalized : null
      } else if (typeof out === 'string') {
        display = out
      }
    }

    if (numRef.current && display !== lastDisplayRef.current) {
      numRef.current.textContent = display
      lastDisplayRef.current = display
    }

    if (normalized != null) {
      valueEaseRef.current = ease(valueEaseRef.current, normalized, dt, EASE_VALUE)
      const col = valueColour(valueEaseRef.current)
      if (wrapRef.current) {
        wrapRef.current.style.setProperty('--big-num-glow', toRgb(col))
      }
    }

    // Re-fit when content text OR container size changes. Which rect we
    // measure depends on positioning:
    //   - Absolute BigNumber (most widgets): the CSS already bounds the
    //     container (full wrap, or shrunk via inset overrides like
    //     GripBudget hero). Use the BigNumber's own rect.
    //   - Relative BigNumber (GearDisplay, where it shares the cell with
    //     dots/dt/clutch in flex flow): the own rect collapses to content
    //     size. Use the parent's rect for the real cell dimensions.
    if (wrapRef.current) {
      if (isAbsoluteRef.current === null) {
        isAbsoluteRef.current = window.getComputedStyle(wrapRef.current).position === 'absolute'
      }
      const sizeEl: HTMLElement = isAbsoluteRef.current
        ? wrapRef.current
        : (wrapRef.current.parentElement ?? wrapRef.current)
      const rect = sizeEl.getBoundingClientRect()
      const fitKey = `${Math.round(rect.width)}x${Math.round(rect.height)}|${display}`
      if (fitKey !== lastFitKeyRef.current) {
        lastFitKeyRef.current = fitKey
        const min  = Math.min(rect.width, rect.height)
        const maxW = (FIT_W[tier] ?? FIT_W.standard) * min
        const maxH = (FIT_H[tier] ?? FIT_H.standard) * min
        const size = fitFontSize(display, maxW, maxH)
        if (numRef.current) {
          numRef.current.style.fontSize = `${size}px`
          if (unitRef.current) {
            unitRef.current.style.fontSize = `${Math.max(12, Math.round(size * 0.32))}px`
          }
        }
      }
    }
  }, [tier, getValue, ignoreStale])

  return (
    <div ref={wrapRef} className={`big-number tier-${tier} ${className}`}>
      <span ref={numRef}  className="big-number-value">—</span>
      {unit ? <span ref={unitRef} className="big-number-unit">{unit}</span> : null}
    </div>
  )
}
