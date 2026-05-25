import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent, ReactNode } from 'react'
import { GRID_COLS as DEFAULT_COLS, getWidgetDef, nearestSize, minSize, maxSize } from '@/features/dashboard/widgetRegistry'
import { cx } from '@/shared/lib/format'

// `group` on the outer wrapper drives `group-hover:opacity-100` on the
// close button. The card chrome (bg-card-gradient + border + radius +
// backdrop-blur + overflow-hidden) is inlined here because the old
// `.card` shared CSS class was retired with the Card primitive
// migration — DashWindow never wrapped the Card component, it just
// borrowed the class.
const SHELL_BASE = 'group dash-window flex flex-col select-none touch-none relative min-w-0 min-h-0 z-10 bg-card-gradient border border-card-border rounded-[14px] backdrop-blur-[14px] backdrop-saturate-[1.4] overflow-hidden'
const SHELL_TOP       = 'shadow-[var(--card-glow),0_0_0_1px_rgba(255,94,167,0.35),0_28px_60px_-24px_rgba(255,94,167,0.6)]'
const SHELL_DRAGGING  = 'shadow-[var(--card-glow),0_0_0_1px_rgba(255,193,220,0.55),0_36px_70px_-20px_rgba(255,94,167,0.7)]'
const SHELL_EDITABLE  = 'shadow-[var(--card-glow),0_0_0_1px_rgba(255,193,220,0.28)] hover:shadow-[var(--card-glow),0_0_0_1px_rgba(255,94,167,0.5),0_18px_40px_-18px_rgba(255,94,167,0.45)]'

export interface CellSize {
  cellW: number
  rowH: number
  gap: number
}

export interface DashWindowProps {
  kind: string
  title: string
  x: number
  y: number
  w: number
  h: number
  z: number
  isTop: boolean
  editMode: boolean
  cellSize: CellSize
  gridCols?: number
  onCommit: (next: { x: number; y: number; w: number; h: number }) => void
  onBringToFront: () => void
  onClose: () => void
  onPickSize?: (sizeIdx: number) => void
  children?: ReactNode
}

type DragKind = 'move' | 'resize'

interface DragState {
  kind: DragKind
  pointerId: number
  sx: number
  sy: number
  startX: number
  startY: number
  startW: number
  startH: number
  targetX: number
  targetY: number
  targetW: number
  targetH: number
  dx: number
  dy: number
}

export default function DashWindow({
  kind, title,
  x, y, w, h, z, isTop,
  editMode,
  cellSize,
  gridCols = DEFAULT_COLS,
  onCommit,
  onBringToFront,
  onClose,
  onPickSize,
  children,
}: DashWindowProps) {
  const elRef = useRef<HTMLDivElement>(null)
  const [drag, setDrag] = useState<DragState | null>(null)
  const [sizeMenuOpen, setSizeMenuOpen] = useState(false)

  const def      = getWidgetDef(kind)
  const minSz    = minSize(def)
  const maxSz    = maxSize(def)
  const sizes    = def?.sizes || []
  const freeform = def?.resize === 'freeform'
  const activeIdx = sizes.findIndex((s) => s.w === w && s.h === h)

  useEffect(() => {
    if (!editMode && drag) setDrag(null)
    if (!editMode && sizeMenuOpen) setSizeMenuOpen(false)
  }, [editMode, drag, sizeMenuOpen])

  useEffect(() => {
    if (!sizeMenuOpen) return
    const onDown = (e: globalThis.PointerEvent): void => {
      if (elRef.current && !elRef.current.contains(e.target as Node)) setSizeMenuOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [sizeMenuOpen])

  const stepX = useCallback((deltaPx: number): number => {
    if (!cellSize?.cellW) return 0
    return Math.round(deltaPx / (cellSize.cellW + cellSize.gap))
  }, [cellSize])
  const stepY = useCallback((deltaPx: number): number => {
    if (!cellSize?.rowH) return 0
    return Math.round(deltaPx / (cellSize.rowH + cellSize.gap))
  }, [cellSize])

  const onPointerDown = useCallback((e: PointerEvent<HTMLElement>, dKind: DragKind): void => {
    if (!editMode) return
    e.preventDefault()
    e.stopPropagation()
    onBringToFront()
    elRef.current?.setPointerCapture?.(e.pointerId)
    setDrag({
      kind: dKind,
      pointerId: e.pointerId,
      sx: e.clientX, sy: e.clientY,
      startX: x, startY: y, startW: w, startH: h,
      targetX: x, targetY: y, targetW: w, targetH: h,
      dx: 0, dy: 0,
    })
  }, [editMode, x, y, w, h, onBringToFront])

  const onPointerMove = useCallback((e: PointerEvent<HTMLElement>): void => {
    if (!drag) return
    const rawDx = e.clientX - drag.sx
    const rawDy = e.clientY - drag.sy
    let tX = drag.startX, tY = drag.startY, tW = drag.startW, tH = drag.startH

    if (drag.kind === 'move') {
      tX = drag.startX + stepX(rawDx)
      tY = drag.startY + stepY(rawDy)
      tX = Math.max(0, Math.min(gridCols - tW, tX))
      tY = Math.max(0, tY)
    } else {
      const candW = Math.max(minSz.w, Math.min(maxSz.w, gridCols - drag.startX, drag.startW + stepX(rawDx)))
      const candH = Math.max(minSz.h, Math.min(maxSz.h, drag.startH + stepY(rawDy)))
      if (freeform) {
        tW = candW
        tH = candH
      } else {
        const growing = candW > drag.startW || candH > drag.startH
        const shrinking = candW < drag.startW || candH < drag.startH
        const bias: 'shrink' | null = growing && !shrinking ? 'shrink'
                    : shrinking && !growing ? 'shrink'
                    : null
        const sz = def ? nearestSize(def, candW, candH, bias) : { w: candW, h: candH }
        tW = sz.w
        tH = sz.h
      }
      if (drag.startX + tW > gridCols) tW = gridCols - drag.startX
    }

    if (
      tX === drag.targetX && tY === drag.targetY &&
      tW === drag.targetW && tH === drag.targetH &&
      rawDx === drag.dx && rawDy === drag.dy
    ) return
    setDrag({ ...drag, dx: rawDx, dy: rawDy, targetX: tX, targetY: tY, targetW: tW, targetH: tH })
  }, [drag, def, minSz, maxSz, freeform, gridCols, stepX, stepY])

  const onPointerUp = useCallback((e: PointerEvent<HTMLElement>): void => {
    if (!drag) return
    elRef.current?.releasePointerCapture?.(e.pointerId)
    onCommit({ x: drag.targetX, y: drag.targetY, w: drag.targetW, h: drag.targetH })
    setDrag(null)
  }, [drag, onCommit])

  const onPointerCancel = useCallback(() => setDrag(null), [])

  const transform = drag?.kind === 'move' ? `translate(${drag.dx}px, ${drag.dy}px)` : 'none'
  const liveW = drag?.kind === 'resize' ? drag.targetW : w
  const liveH = drag?.kind === 'resize' ? drag.targetH : h

  return (
    <>
      <div
        ref={elRef}
        className={cx(
          SHELL_BASE,
          drag && SHELL_DRAGGING,
          isTop && SHELL_TOP,
          editMode && SHELL_EDITABLE,
        )}
        style={{
          gridColumn: `${x + 1} / span ${liveW}`,
          gridRow:    `${y + 1} / span ${liveH}`,
          zIndex: z,
          transform,
          transition: drag ? 'none' : 'box-shadow 120ms ease, transform 120ms ease',
          cursor: drag?.kind === 'move' ? 'grabbing' : 'default',
        }}
        onPointerDown={editMode ? () => onBringToFront() : undefined}
        onPointerMove={drag ? onPointerMove : undefined}
        onPointerUp={drag ? onPointerUp : undefined}
        onPointerCancel={drag ? onPointerCancel : undefined}
      >
        <div className="flex-none z-[2] flex items-center justify-between gap-2 px-[14px] pt-2 pb-1">
          <div className="flex items-center gap-2 whitespace-nowrap font-display text-[10px] font-medium uppercase tracking-[0.2em] text-bubblegum [text-shadow:0_0_8px_rgba(255,193,220,0.4)]">
            <span className="w-[7px] h-[7px] rounded-full bg-pink shadow-[0_0_8px_var(--pink)] animate-[pulse_1.6s_ease-in-out_infinite]" />
            {title}
          </div>
          <div className="font-mono text-[9px] tracking-[0.14em] text-ink-faint whitespace-nowrap">{liveW}×{liveH}{sizes[activeIdx]?.label ? ` · ${sizes[activeIdx]!.label}` : ''}</div>
        </div>

        {editMode && (
          <>
            <div
              className="absolute top-0 right-0 h-[22px] flex items-center gap-[6px] px-2 cursor-grab z-[3] active:cursor-grabbing"
              onPointerDown={(e) => onPointerDown(e, 'move')}
              title={`Drag · ${title}`}
            >
              <span className="text-[11px] text-[rgba(253,233,255,0.45)] tracking-[-1px]">⋮⋮</span>
              {sizes.length > 1 && (
                <button
                  type="button"
                  className="w-4 h-4 inline-flex items-center justify-center bg-white/[0.04] border border-[rgba(255,193,220,0.25)] text-[rgba(253,233,255,0.7)] rounded-sm text-[10px] cursor-pointer transition-[opacity,background] duration-[120ms] ease-in-out hover:bg-[rgba(202,166,255,0.25)] hover:text-cream"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => { e.stopPropagation(); setSizeMenuOpen((o) => !o) }}
                  title="Pick size"
                >▣</button>
              )}
              <button
                type="button"
                className="w-4 h-4 inline-flex items-center justify-center bg-white/[0.04] border border-[rgba(255,193,220,0.25)] text-[rgba(253,233,255,0.65)] rounded-full text-[9px] cursor-pointer opacity-0 transition-[opacity,background] duration-[120ms] ease-in-out group-hover:opacity-100 hover:bg-[rgba(255,94,167,0.3)] hover:text-[#fff7f0]"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={onClose}
                title="Hide widget"
              >✕</button>
            </div>

            {sizeMenuOpen && sizes.length > 1 && (
              <div
                className="absolute top-[22px] right-1 bg-[linear-gradient(160deg,rgba(42,14,58,0.96),rgba(26,8,38,0.96))] border border-[rgba(255,193,220,0.32)] rounded-[10px] p-[6px] z-[1100] flex flex-col gap-[2px] min-w-[160px] shadow-[0_18px_40px_-16px_rgba(255,94,167,0.55)] backdrop-blur-[14px] backdrop-saturate-[1.4]"
                onPointerDown={(e) => e.stopPropagation()}
              >
                <div className="font-display text-[9px] tracking-[0.18em] text-bubblegum uppercase pt-[2px] px-1 pb-[6px]">Widget size</div>
                {sizes.map((sz, i) => {
                  const isOn = i === activeIdx
                  return (
                    <button
                      type="button"
                      key={`${sz.w}x${sz.h}`}
                      className={cx(
                        'grid grid-cols-[32px_1fr_auto] items-center gap-2 border rounded-lg px-2 py-[6px] cursor-pointer font-display text-[10px] tracking-[0.14em] text-left transition-[background,color,border-color] duration-[120ms] ease-in-out',
                        isOn
                          ? 'bg-[rgba(255,94,167,0.18)] border-[rgba(255,94,167,0.5)] text-cream'
                          : 'bg-[rgba(225,200,255,0.06)] border-[rgba(225,200,255,0.14)] text-ink-dim hover:bg-[rgba(255,193,220,0.15)] hover:text-cream',
                      )}
                      onClick={() => { onPickSize?.(i); setSizeMenuOpen(false) }}
                    >
                      <span
                        className="inline-block bg-[linear-gradient(135deg,var(--lilac),var(--pink))] rounded-[3px] justify-self-center"
                        style={{ width: 12 + sz.w * 4, height: 8 + sz.h * 4 }}
                      />
                      <span className="tracking-[0.18em]">{sz.label || `${sz.w}×${sz.h}`}</span>
                      <span className="font-mono text-[9px] text-ink-faint tracking-[0]">{sz.w}×{sz.h}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </>
        )}

        <div className="flex-1 min-h-0 relative overflow-hidden pt-2 px-3 pb-[10px]">
          {children}
        </div>

        {editMode && (
          <div
            className="absolute right-px bottom-px w-4 h-4 cursor-nwse-resize flex items-end justify-end z-[3] p-px opacity-60 hover:opacity-100"
            onPointerDown={(e) => onPointerDown(e, 'resize')}
            title={freeform ? 'Resize (snaps to grid)' : 'Resize (snaps to widget sizes)'}
          >
            <svg viewBox="0 0 12 12" width="12" height="12">
              <path
                d="M 0 12 L 12 0 M 4 12 L 12 4 M 8 12 L 12 8"
                stroke="rgba(253,233,255,0.45)" strokeWidth="1.2" fill="none"
              />
            </svg>
          </div>
        )}
      </div>

      {drag && drag.kind === 'move' && (
        <div
          className="border-[1.5px] border-dashed border-[rgba(255,94,167,0.7)] rounded-xl bg-[rgba(255,94,167,0.08)] pointer-events-none z-[5]"
          style={{
            gridColumn: `${drag.targetX + 1} / span ${drag.targetW}`,
            gridRow:    `${drag.targetY + 1} / span ${drag.targetH}`,
          }}
        />
      )}
    </>
  )
}
