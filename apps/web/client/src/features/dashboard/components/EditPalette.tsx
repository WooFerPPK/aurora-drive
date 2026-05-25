// client/src/components/layout/EditPalette.tsx
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, PointerEvent } from 'react'
import { createPortal } from 'react-dom'
import { useDashUI } from '@/features/dashboard/context/DashUIContext'
import { useDialog } from '@/shared/context/DialogContext'
import { CATEGORIES, type WidgetDef } from '@/features/dashboard/widgetRegistry'
import type { TabDef } from '@/features/dashboard/context/TabsContext'
import type { LayoutEntry } from '@/features/dashboard/hooks/useTabLayout'
import { cx } from '@/shared/lib/format'
import {
  TOOLBAR_BTN, TOOLBAR_BTN_BODY, TOOLBAR_COUNT,
  TOOLBAR_MENU, TOOLBAR_MENU_HEAD, TOOLBAR_MENU_GRID,
  TOOLBAR_MENU_EMPTY, TOOLBAR_MENU_FOOT,
  TOOLBAR_ITEM, TOOLBAR_ITEM_OFF, TOOLBAR_ITEM_ON,
  TOOLBAR_ITEM_MARK, TOOLBAR_ITEM_MARK_ON,
} from '@/shared/components/layout/toolbarStyles'

interface ToolbarShape {
  tab: TabDef
  allowed: WidgetDef[]
  layout: LayoutEntry[]
  onToggle: (kind: string) => void
  onReset: () => void
  onAuto: () => void
  onCategoriesChange: (cats: string[] | null) => void
}

function portalMenuStyle(rect: DOMRect, width = 320): CSSProperties {
  const gutter = 8
  let left = rect.left
  if (left + width > window.innerWidth - gutter) {
    left = Math.max(gutter, window.innerWidth - gutter - width)
  }
  return {
    position: 'fixed',
    top: rect.bottom + 8,
    left,
    width,
    maxHeight: `min(70vh, ${window.innerHeight - rect.bottom - 24}px)`,
    overflowY: 'auto',
  }
}

interface DragRef {
  startX: number
  startY: number
  basePos: { x: number; y: number }
  rect: DOMRect
}

export default function EditPalette() {
  const { toolbarApi, editMode, toggleEditMode } = useDashUI()
  const dialog = useDialog()
  const [open, setOpen]         = useState(false)
  const [catsOpen, setCatsOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const widgetsBtnRef = useRef<HTMLButtonElement>(null)
  const catsBtnRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open && !catsOpen) return
    const onDown = (e: globalThis.PointerEvent): void => {
      if (wrapRef.current && wrapRef.current.contains(e.target as Node)) return
      const menus = document.querySelectorAll('.dash-toolbar-menu')
      for (const m of menus) {
        if (m.contains(e.target as Node)) return
      }
      setOpen(false)
      setCatsOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open, catsOpen])

  const [entering, setEntering] = useState(true)
  useEffect(() => {
    if (!editMode || !toolbarApi) return
    setEntering(true)
    const id = requestAnimationFrame(() => setEntering(false))
    return () => cancelAnimationFrame(id)
  }, [editMode, toolbarApi])

  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef<DragRef | null>(null)
  const paletteRef = useRef<HTMLDivElement | null>(null)

  const onHeaderPointerDown = (e: PointerEvent<HTMLDivElement>): void => {
    if ((e.target as HTMLElement).closest('.edit-palette-close')) return
    if (e.button !== undefined && e.button !== 0) return
    e.preventDefault()
    const rect = paletteRef.current?.getBoundingClientRect()
    if (!rect) return
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      basePos: { ...pos },
      rect,
    }
    setDragging(true)
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }

  const onHeaderPointerMove = (e: PointerEvent<HTMLDivElement>): void => {
    if (!dragRef.current) return
    const { startX, startY, basePos, rect } = dragRef.current
    let nextX = basePos.x + (e.clientX - startX)
    let nextY = basePos.y + (e.clientY - startY)
    const gutter = 8
    const minX = -(rect.left - gutter) + basePos.x
    const maxX = window.innerWidth - rect.right - gutter + basePos.x
    const minY = -(rect.top - gutter) + basePos.y
    const maxY = window.innerHeight - rect.bottom - gutter + basePos.y
    if (nextX < minX) nextX = minX
    if (nextX > maxX) nextX = maxX
    if (nextY < minY) nextY = minY
    if (nextY > maxY) nextY = maxY
    setPos({ x: nextX, y: nextY })
  }

  const onHeaderPointerUp = (e: PointerEvent<HTMLDivElement>): void => {
    if (!dragRef.current) return
    dragRef.current = null
    setDragging(false)
    e.currentTarget.releasePointerCapture?.(e.pointerId)
  }

  if (!editMode || !toolbarApi) return null

  const { tab, allowed, layout, onToggle, onReset, onAuto, onCategoriesChange } = toolbarApi as unknown as ToolbarShape
  const visMap: Record<string, boolean> = Object.fromEntries(layout.map((m) => [m.kind, m.visible]))
  const visibleCount = allowed.filter((w) => visMap[w.kind]).length

  const activeCats = new Set(tab.categories || [])
  const allCatsOn  = !tab.categories

  const toggleCat = (catId: string): void => {
    if (allCatsOn) { onCategoriesChange([catId]); return }
    const next = new Set(activeCats)
    if (next.has(catId)) next.delete(catId); else next.add(catId)
    onCategoriesChange(next.size === 0 ? null : Array.from(next))
  }

  const paletteBase = 'fixed top-[calc(var(--header-h)+12px)] right-4 w-[220px] bg-[linear-gradient(160deg,rgba(42,14,58,0.95),rgba(26,8,38,0.95))] border border-[rgba(255,193,220,0.3)] rounded-xl backdrop-blur-[16px] backdrop-saturate-[1.4] z-[2300] flex flex-col p-2 motion-reduce:transition-none motion-reduce:opacity-100'

  // Renders the toggleable widget toolbar item button (used in both menus).
  const renderItem = (key: string, label: string, on: boolean, onClick: () => void) => (
    <button
      type="button"
      key={key}
      className={cx(TOOLBAR_ITEM, on ? TOOLBAR_ITEM_ON : TOOLBAR_ITEM_OFF)}
      onClick={onClick}
    >
      <span className={cx(TOOLBAR_ITEM_MARK, on && TOOLBAR_ITEM_MARK_ON)}>{on ? '✓' : '+'}</span>
      <span>{label}</span>
    </button>
  )

  return (
    <div
      className={cx(
        paletteBase,
        dragging
          ? '[transition:opacity_180ms_ease-out] cursor-grabbing shadow-[0_30px_80px_-16px_rgba(255,94,167,0.7),0_0_0_1px_rgba(255,255,255,0.06)]'
          : 'transition-[opacity,transform] duration-[180ms] ease-out shadow-[0_24px_60px_-16px_rgba(255,94,167,0.55),0_0_0_1px_rgba(255,255,255,0.04)]',
        entering && 'opacity-0',
      )}
      ref={(el) => { paletteRef.current = el; wrapRef.current = el }}
      style={{ transform: `translate(${pos.x}px, ${pos.y + (entering ? -4 : 0)}px)` }}
      role="toolbar"
      aria-label={`Edit toolbar for ${tab.label}`}
    >
      <div
        className={cx(
          'flex items-center gap-2 pt-1 pr-1 pl-1 pb-2 border-b border-[rgba(255,193,220,0.14)] mb-2 select-none touch-none',
          dragging ? 'cursor-grabbing' : 'cursor-grab',
        )}
        onPointerDown={onHeaderPointerDown}
        onPointerMove={onHeaderPointerMove}
        onPointerUp={onHeaderPointerUp}
        onPointerCancel={onHeaderPointerUp}
      >
        <span className="flex-1 font-display text-[9.5px] tracking-[0.18em] uppercase text-ink-dim whitespace-nowrap">
          <span className="text-pink text-[11px] mr-1">↳</span>
          Editing <strong className="text-bubblegum font-semibold ml-1">{tab.label}</strong>
        </span>
        <button
          type="button"
          className="edit-palette-close inline-flex items-center justify-center w-5 h-5 rounded-full bg-[rgba(255,193,220,0.08)] border border-[rgba(255,193,220,0.22)] text-cream text-[12px] leading-none cursor-pointer transition-[background,border-color] duration-[120ms] ease-in-out hover:bg-[rgba(255,94,167,0.22)] hover:border-[rgba(255,94,167,0.55)]"
          onClick={toggleEditMode}
          aria-label="Exit edit mode"
          title="Exit edit mode"
        >✕</button>
      </div>

      <div className="flex flex-col gap-1">
        <button
          type="button"
          ref={widgetsBtnRef}
          className={cx(TOOLBAR_BTN, TOOLBAR_BTN_BODY)}
          onClick={() => { setOpen((o) => !o); setCatsOpen(false) }}
          aria-haspopup="menu"
          aria-expanded={open}
          title="Add or remove widgets"
        >
          + WIDGETS <span className={TOOLBAR_COUNT}>{visibleCount}/{allowed.length}</span>
        </button>
        <button
          type="button"
          ref={catsBtnRef}
          className={cx(TOOLBAR_BTN, TOOLBAR_BTN_BODY)}
          onClick={() => { setCatsOpen((o) => !o); setOpen(false) }}
          aria-haspopup="menu"
          aria-expanded={catsOpen}
          title="Choose which categories this tab shows"
        >
          ⚙ CATEGORIES
        </button>
        <button
          type="button"
          className={cx(TOOLBAR_BTN, TOOLBAR_BTN_BODY)}
          onClick={onAuto}
          title="Auto-arrange visible widgets"
        >
          ⊞ AUTO
        </button>
        <button
          type="button"
          className={cx(TOOLBAR_BTN, TOOLBAR_BTN_BODY)}
          onClick={async () => {
            const ok = await dialog.confirm({
              title: `Reset ${tab.label} layout?`,
              message: 'Returns every widget on this tab to its default size and position.',
              confirmLabel: 'Reset layout',
              destructive: true,
            })
            if (ok) onReset()
          }}
          title="Reset positions for this tab"
        >
          ↺ RESET
        </button>
      </div>

      {open && widgetsBtnRef.current && createPortal(
        <div
          className={TOOLBAR_MENU}
          style={portalMenuStyle(widgetsBtnRef.current.getBoundingClientRect(), 360)}
        >
          <div className={TOOLBAR_MENU_HEAD}>{tab.label} widgets</div>
          <div className={TOOLBAR_MENU_GRID}>
            {allowed.map((w) => renderItem(w.kind, w.title, visMap[w.kind] === true, () => onToggle(w.kind)))}
            {allowed.length === 0 && (
              <div className={TOOLBAR_MENU_EMPTY}>
                No widgets match this tab&apos;s categories.
              </div>
            )}
          </div>
          <div className={TOOLBAR_MENU_FOOT}>
            Drag any window by its grip. Resize from the corner. Edges snap.
          </div>
        </div>,
        document.body,
      )}

      {catsOpen && catsBtnRef.current && createPortal(
        <div
          className={TOOLBAR_MENU}
          style={portalMenuStyle(catsBtnRef.current.getBoundingClientRect(), 280)}
        >
          <div className={TOOLBAR_MENU_HEAD}>Categories</div>
          <div className={TOOLBAR_MENU_GRID}>
            {renderItem('__all', 'All', allCatsOn, () => onCategoriesChange(null))}
            {CATEGORIES.map((c) => renderItem(c.id, c.label, !allCatsOn && activeCats.has(c.id), () => toggleCat(c.id)))}
          </div>
          <div className={TOOLBAR_MENU_FOOT}>
            Filters which widgets are listed in the + menu for this tab.
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
