// client/src/components/layout/SidebarTabs.tsx
import { useEffect, useRef, useState } from 'react'
import type { DragEvent, KeyboardEvent } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useTabs } from '@/features/dashboard/context/TabsContext'
import type { TabDef } from '@/features/dashboard/context/TabsContext'
import { useDialog } from '@/shared/context/DialogContext'
import { cx } from '@/shared/lib/format'

export interface SidebarTabsProps {
  onNavigate?: () => void
}

export default function SidebarTabs({ onNavigate }: SidebarTabsProps) {
  const { tabs, addTab, removeTab, renameTab, reorderTab } = useTabs()
  const dialog = useDialog()
  const navigate = useNavigate()
  const location = useLocation()
  const activeId = location.pathname.replace(/^\//, '').split('/')[0] || null

  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft]     = useState('')
  const [dragId, setDragId]   = useState<string | null>(null)
  const [dropAt, setDropAt]   = useState<number | null>(null)
  const scrollerRef = useRef<HTMLDivElement>(null)

  const startRename = (tab: TabDef): void => {
    setEditing(tab.id)
    setDraft(tab.label)
  }
  const commitRename = (id: string): void => { renameTab(id, draft); setEditing(null) }

  const onAdd = async (): Promise<void> => {
    const label = await dialog.prompt({
      title: 'New tab',
      message: 'Give it a short label — it appears uppercased in the sidebar.',
      placeholder: 'NEW TAB',
      confirmLabel: 'Add tab',
    })
    if (label === null) return
    const tab = addTab(label)
    navigate(`/${tab.id}`)
    onNavigate?.()
  }

  const onDragStart = (e: DragEvent<HTMLAnchorElement>, tab: TabDef): void => {
    setDragId(tab.id)
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move'
      try { e.dataTransfer.setData('text/plain', tab.id) } catch { /* ignore */ }
    }
  }

  const onDragOverTab = (e: DragEvent<HTMLAnchorElement>, idx: number): void => {
    if (!dragId) return
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
    const rect = e.currentTarget.getBoundingClientRect()
    const before = e.clientY < rect.top + rect.height / 2
    setDropAt(before ? idx : idx + 1)
  }

  const onDragLeaveContainer = (e: DragEvent<HTMLDivElement>): void => {
    if (e.currentTarget === e.target) setDropAt(null)
  }

  const onDrop = (e: DragEvent<HTMLDivElement>): void => {
    if (!dragId || dropAt == null) { setDragId(null); setDropAt(null); return }
    e.preventDefault()
    const fromIdx = tabs.findIndex((t) => t.id === dragId)
    let toIdx = dropAt
    if (fromIdx >= 0 && toIdx > fromIdx) toIdx -= 1
    if (fromIdx >= 0 && fromIdx !== toIdx) reorderTab(fromIdx, toIdx)
    setDragId(null)
    setDropAt(null)
  }

  const onDragEnd = (): void => {
    setDragId(null)
    setDropAt(null)
  }

  const onDelete = async (tab: TabDef): Promise<void> => {
    if (tab.builtIn) return
    const ok = await dialog.confirm({
      title: `Delete "${tab.label}"?`,
      message: "The tab's layout is wiped. This cannot be undone.",
      confirmLabel: 'Delete tab',
      destructive: true,
    })
    if (!ok) return
    removeTab(tab.id)
    navigate('/live')
    onNavigate?.()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
    const links = scrollerRef.current?.querySelectorAll<HTMLElement>('[role="tab"]')
    if (!links || !links.length) return
    const current = document.activeElement
    const idx = Array.from(links).indexOf(current as HTMLElement)
    if (idx < 0) return
    e.preventDefault()
    const next = e.key === 'ArrowDown'
      ? links[(idx + 1) % links.length]
      : links[(idx - 1 + links.length) % links.length]
    next?.focus()
  }

  useEffect(() => {
    const el = scrollerRef.current
    if (!el || !activeId) return
    const active = el.querySelector<HTMLElement>(`[data-tab-id="${activeId}"]`)
    if (!active) return
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    active.scrollIntoView({
      block: 'nearest',
      inline: 'nearest',
      behavior: prefersReduced ? 'auto' : 'smooth',
    })
  }, [activeId])

  const tabBase = 'group relative flex items-center gap-2 px-[10px] py-[7px] rounded-lg bg-white/[0.02] border border-transparent text-ink-dim font-display text-[10px] font-medium tracking-[0.18em] uppercase no-underline cursor-pointer transition-[background,color,border-color] duration-[120ms] ease-in-out hover:bg-[rgba(255,193,220,0.08)] hover:text-cream'
  const tabActive = 'bg-[linear-gradient(135deg,rgba(255,94,167,0.30)_0%,rgba(202,166,255,0.25)_60%,rgba(255,224,130,0.20)_100%)] text-cream border-[rgba(255,193,220,0.45)] shadow-[0_0_18px_-4px_rgba(255,94,167,0.55)]'
  const dropMark = "after:content-[''] after:absolute after:left-1 after:right-1 after:h-[2px] after:bg-pink after:rounded-[2px] after:shadow-[0_0_8px_rgba(255,94,167,0.85),0_0_14px_rgba(255,94,167,0.45)] after:animate-[pulse_1.6s_ease-in-out_infinite]"
  const dropBefore = `${dropMark} after:-top-[2px]`
  const dropAfter  = `${dropMark} after:-bottom-[2px]`

  return (
    <div className="px-3 py-[10px] border-b border-[rgba(255,193,220,0.10)] last:border-b-0">
      <div className="font-display text-[9px] font-semibold tracking-[0.22em] uppercase text-ink-faint mb-2">Navigation</div>
      <div
        ref={scrollerRef}
        className="flex flex-col gap-[2px] max-h-[50vh] overflow-y-auto [scrollbar-width:thin] [scrollbar-color:rgba(255,193,220,0.25)_transparent]"
        role="tablist"
        aria-orientation="vertical"
        onKeyDown={onKeyDown}
        onDragLeave={onDragLeaveContainer}
        onDrop={onDrop}
        onDragOver={(e) => { if (dragId) e.preventDefault() }}
      >
        {tabs.map((tab, i) => {
          const isEditing = editing === tab.id
          const isActive  = tab.id === activeId
          const isDragging = dragId === tab.id

          if (isEditing) {
            return (
              <input
                key={tab.id}
                autoFocus
                className="bg-[rgba(26,8,38,0.7)] border border-[rgba(255,94,167,0.5)] text-cream font-display font-medium text-[10px] tracking-[0.18em] px-[10px] py-[6px] rounded-lg uppercase outline-none w-full box-border"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => commitRename(tab.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitRename(tab.id)
                  else if (e.key === 'Escape') setEditing(null)
                }}
              />
            )
          }

          return (
            <NavLink
              key={tab.id}
              to={`/${tab.id}`}
              data-tab-id={tab.id}
              draggable
              role="tab"
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              onDragStart={(e) => onDragStart(e, tab)}
              onDragEnd={onDragEnd}
              onDragOver={(e) => onDragOverTab(e, i)}
              onDoubleClick={(e) => { e.preventDefault(); startRename(tab) }}
              onClick={() => onNavigate?.()}
              className={cx(
                tabBase,
                isActive && tabActive,
                isDragging && 'opacity-40',
                dropAt === i && dropBefore,
                dropAt === i + 1 && dropAfter,
              )}
              title="Drag to reorder · Double-click to rename"
            >
              <span className="flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                {tab.label}
              </span>
              {!tab.builtIn && (
                <button
                  type="button"
                  className="inline-flex items-center justify-center w-4 h-4 p-0 bg-transparent border-none text-ink-faint text-[13px] leading-none cursor-pointer rounded-full opacity-0 transition-[opacity,background,color] duration-[120ms] ease-in-out group-hover:opacity-100 focus-visible:opacity-100 hover:bg-[rgba(255,94,167,0.28)] hover:text-white"
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDelete(tab) }}
                  onDoubleClick={(e) => e.stopPropagation()}
                  onPointerDown={(e) => e.stopPropagation()}
                  onDragStart={(e) => e.preventDefault()}
                  title="Delete tab"
                  aria-label={`Delete ${tab.label} tab`}
                >×</button>
              )}
            </NavLink>
          )
        })}

        <button
          type="button"
          className="mt-[6px] w-full text-left px-[10px] py-[7px] rounded-lg bg-[rgba(255,193,220,0.04)] border border-dashed border-[rgba(255,193,220,0.4)] text-bubblegum font-display text-[10px] font-medium tracking-[0.18em] uppercase cursor-pointer transition-[background,border-color,color] duration-[120ms] ease-in-out hover:bg-[rgba(255,193,220,0.12)] hover:border-[rgba(255,94,167,0.55)] hover:text-cream"
          onClick={onAdd}
        >+ NEW TAB</button>
      </div>
    </div>
  )
}
