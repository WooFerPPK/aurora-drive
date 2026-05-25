import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useTabs } from '@/features/dashboard/context/TabsContext'
import type { TabDef } from '@/features/dashboard/context/TabsContext'
import { useDashUI } from '@/features/dashboard/context/DashUIContext'
import { useTabLayout } from '@/features/dashboard/hooks/useTabLayout'
import { cx } from '@/shared/lib/format'
import {
  getWidgetDef, widgetsForCategories,
  TAB_DEFAULT_VISIBLE, GRID_COLS, ROW_HEIGHT_PX, GRID_GAP_PX,
} from '@/features/dashboard/widgetRegistry'
import DashWindow from './DashWindow'

const CELL_SIZE_PX = ROW_HEIGHT_PX
const FIXED_CELL_SIZE = Object.freeze({
  cellW: CELL_SIZE_PX,
  rowH:  CELL_SIZE_PX,
  gap:   GRID_GAP_PX,
})

const MIN_COLS = GRID_COLS

function computeCols(innerW: number): number {
  if (!innerW || innerW <= 0) return MIN_COLS
  const pitch = CELL_SIZE_PX + GRID_GAP_PX
  const fit = Math.floor((innerW + GRID_GAP_PX) / pitch)
  return Math.max(MIN_COLS, fit)
}

function computeRows(innerH: number): number {
  if (!innerH || innerH <= 0) return 6
  const pitch = CELL_SIZE_PX + GRID_GAP_PX
  return Math.max(4, Math.floor((innerH + GRID_GAP_PX) / pitch))
}

function initialCols(): number {
  if (typeof window === 'undefined') return MIN_COLS
  return computeCols(window.innerWidth - 60)
}
function initialRows(): number {
  if (typeof window === 'undefined') return 8
  return computeRows(window.innerHeight - 160)
}

export interface WidgetSurfaceProps {
  tab: TabDef
}

export default function WidgetSurface({ tab }: WidgetSurfaceProps) {
  const { setTabCategories } = useTabs()
  const { registerToolbar, unregisterToolbar, editMode } = useDashUI()

  const defaultVisible = useMemo(() => TAB_DEFAULT_VISIBLE[tab.id] || [], [tab.id])

  const surfaceRef = useRef<HTMLDivElement>(null)
  const [cols, setCols] = useState<number>(initialCols)
  const [rows, setRows] = useState<number>(initialRows)

  useEffect(() => {
    const el = surfaceRef.current
    if (!el) return
    const measure = (): void => {
      const r = el.getBoundingClientRect()
      const style = getComputedStyle(el)
      const padL = parseFloat(style.paddingLeft) || 0
      const padR = parseFloat(style.paddingRight) || 0
      const padT = parseFloat(style.paddingTop) || 0
      const padB = parseFloat(style.paddingBottom) || 0
      const nextCols = computeCols(r.width - padL - padR)
      const nextRows = computeRows(r.height - padT - padB)
      setCols((cur) => (cur === nextCols ? cur : nextCols))
      setRows((cur) => (cur === nextRows ? cur : nextRows))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const {
    layout, topKind, pristine,
    setEntry, setSize, bringToFront, toggleVisible, reset, arrange,
  } = useTabLayout(tab.id, defaultVisible, cols, rows)

  const allowed = useMemo(() => widgetsForCategories(tab.categories), [tab.categories])
  const allowedKinds = useMemo(() => new Set(allowed.map((w) => w.kind)), [allowed])

  const defaultVisibleKinds = useMemo(
    () => new Set(defaultVisible.map((e) => (typeof e === 'string' ? e : e?.kind))),
    [defaultVisible],
  )
  const visible = useMemo(
    () => layout.filter((m) => m.visible && (allowedKinds.has(m.kind) || defaultVisibleKinds.has(m.kind))),
    [layout, allowedKinds, defaultVisibleKinds],
  )

  const handleCommit = useCallback(
    (kind: string, rect: { x: number; y: number; w: number; h: number }) => setEntry(kind, rect),
    [setEntry],
  )

  useEffect(() => {
    if (!tab.autoArrange) return
    if (!pristine) return
    if (!visible.length) return
    arrange()
  }, [tab.autoArrange, pristine, visible.length, arrange])

  useEffect(() => {
    registerToolbar({
      tab, allowed, layout,
      onToggle: toggleVisible,
      onReset: reset,
      onAuto: arrange,
      onCategoriesChange: (c: string[] | null) => setTabCategories(tab.id, c),
    })
    return () => unregisterToolbar()
  }, [tab, allowed, layout, toggleVisible, reset, arrange, setTabCategories, registerToolbar, unregisterToolbar])

  const surfaceStyle = {
    '--grid-cols':     cols,
    '--grid-cell-size': `${CELL_SIZE_PX}px`,
    '--grid-row-h':    `${CELL_SIZE_PX}px`,
    '--grid-gap':      `${GRID_GAP_PX}px`,
  } as CSSProperties

  return (
    <div
      ref={surfaceRef}
      className={cx(
        'relative flex-1 m-[10px] min-h-0 p-[10px] overflow-auto rounded-xl grid auto-rows-[var(--grid-cell-size,64px)] [grid-auto-columns:var(--grid-cell-size,64px)] [gap:var(--grid-gap,6px)] [grid-template-columns:repeat(var(--grid-cols,12),var(--grid-cell-size,64px))] content-start justify-start',
        editMode
          ? "bg-[radial-gradient(ellipse_at_50%_0%,rgba(255,94,167,0.08),transparent_60%),repeating-linear-gradient(45deg,rgba(255,193,220,0.025)_0_12px,transparent_12px_24px)] before:content-[''] before:absolute before:top-[10px] before:left-[10px] before:[width:calc(var(--grid-cols,24)*var(--grid-cell-size,64px)+(var(--grid-cols,24)-1)*var(--grid-gap,6px))] before:bottom-[10px] before:pointer-events-none before:bg-[linear-gradient(to_right,rgba(255,193,220,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,193,220,0.06)_1px,transparent_1px)] before:[background-size:calc(var(--grid-cell-size,64px)+var(--grid-gap,6px))_100%,100%_calc(var(--grid-cell-size,64px)+var(--grid-gap,6px))] before:[background-position:0_0,0_0] before:opacity-60 before:z-0"
          : 'bg-[radial-gradient(ellipse_at_50%_0%,rgba(255,193,220,0.04),transparent_60%)]',
      )}
      style={surfaceStyle}
    >
      {visible.length === 0 && (
        <div className="col-span-full row-start-1 row-end-7 flex items-center justify-center pointer-events-none">
          <div className="pointer-events-auto text-center px-[26px] py-[22px] bg-[rgba(26,8,38,0.55)] border border-dashed border-[rgba(255,193,220,0.4)] rounded-[14px] max-w-[360px]">
            <div className="font-display text-[12px] tracking-[0.22em] text-bubblegum uppercase mb-2">{tab.label} is empty</div>
            <div className="font-mono text-[12px] text-ink-dim leading-[1.5]">
              Toggle <b>EDIT</b> in the header, then open <b>+ WIDGETS</b> to add some.
            </div>
          </div>
        </div>
      )}

      {visible.map((m, i) => {
        const def = getWidgetDef(m.kind)
        if (!def) return null
        const isTop = topKind === m.kind
        const z = isTop ? 1000 : 10 + i
        return (
          <DashWindow
            key={m.kind}
            kind={m.kind}
            title={def.title}
            x={m.x} y={m.y} w={m.w} h={m.h}
            z={z} isTop={isTop}
            editMode={editMode}
            cellSize={FIXED_CELL_SIZE}
            gridCols={cols}
            onCommit={(rect) => handleCommit(m.kind, rect)}
            onBringToFront={() => bringToFront(m.kind)}
            onClose={() => toggleVisible(m.kind)}
            onPickSize={(idx) => setSize(m.kind, idx)}
          >
            {def.render({ kind: m.kind, w: m.w, h: m.h, size: { w: m.w, h: m.h } })}
          </DashWindow>
        )
      })}
    </div>
  )
}
