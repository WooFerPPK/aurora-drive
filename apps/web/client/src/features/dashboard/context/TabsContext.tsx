import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

// Tab registry, persisted to localStorage so the user's custom tabs and
// reordering survive a reload. Built-in tabs map to backend pageIds for
// /api/layouts compatibility. Each `widgets` tab carries an optional
// `categories` filter — controls which widgets the +menu lists — and an
// `autoArrange` flag for first-paint placement.

// Storage key bumped to v5 — every built-in tab now ships an explicit
// 2560×720 (35×8) layout, MAP was renamed to TRACK, and PREDICTIONS
// was renamed/refocused to STRATEGY. Bumping the version cleanly drops
// stale tab orderings so users land on the new layouts.
const STORAGE_KEY = 'fh6.tabs.v5'

export type TabKind = 'widgets' | 'sessions' | 'coach' | 'settings'

export interface TabDef {
  id: string
  label: string
  kind: TabKind
  pageId: string
  categories?: string[] | null
  autoArrange?: boolean
  builtIn: boolean
}

export const DEFAULT_TABS: TabDef[] = [
  { id: 'live',      label: 'LIVE',      kind: 'widgets',  pageId: 'live',      categories: null,                     autoArrange: false, builtIn: true },
  { id: 'engine',    label: 'ENGINE',    kind: 'widgets',  pageId: 'engine',    categories: ['engine'],               autoArrange: false, builtIn: true },
  { id: 'chassis',   label: 'CHASSIS',   kind: 'widgets',  pageId: 'chassis',   categories: ['chassis'],              autoArrange: false, builtIn: true },
  { id: 'tires',     label: 'TIRES',     kind: 'widgets',  pageId: 'tires',     categories: ['tires'],                autoArrange: false, builtIn: true },
  { id: 'track',     label: 'TRACK',     kind: 'widgets',  pageId: 'track',     categories: ['map', 'analytics'],     autoArrange: false, builtIn: true },
  { id: 'telemetry', label: 'TELEMETRY', kind: 'widgets',  pageId: 'telemetry', categories: ['analytics'],            autoArrange: false, builtIn: true },
  { id: 'strategy',  label: 'STRATEGY',  kind: 'widgets',  pageId: 'strategy',  categories: ['predict', 'analytics'], autoArrange: false, builtIn: true },
  { id: 'driver',    label: 'DRIVER',    kind: 'widgets',  pageId: 'driver',    categories: ['driver', 'analytics'],  autoArrange: false, builtIn: true },
  { id: 'sessions',  label: 'SESSIONS',  kind: 'sessions', pageId: 'sessions',  builtIn: true },
  { id: 'coach',     label: 'COACH',     kind: 'coach',    pageId: 'coach',     builtIn: true },
  { id: 'settings',  label: '⚙',         kind: 'settings', pageId: 'settings',  builtIn: true },
]

function loadTabs(): TabDef[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_TABS
    const parsed = JSON.parse(raw) as TabDef[]
    if (!Array.isArray(parsed) || parsed.length === 0) return DEFAULT_TABS
    const byId = Object.fromEntries(parsed.map((t) => [t.id, t]))
    const merged: TabDef[] = parsed.map((t) => {
      const def = DEFAULT_TABS.find((d) => d.id === t.id)
      return def ? { ...def, ...t, builtIn: true } : { ...t, builtIn: false }
    })
    for (const def of DEFAULT_TABS) {
      if (!byId[def.id]) merged.push(def)
    }
    return merged
  } catch {
    return DEFAULT_TABS
  }
}

function persist(tabs: TabDef[]): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(tabs)) } catch { /* ignore */ }
}

export interface TabsValue {
  tabs: TabDef[]
  addTab: (label: string) => TabDef
  removeTab: (id: string) => void
  renameTab: (id: string, label: string) => void
  setTabCategories: (id: string, categories: string[] | null) => void
  moveTab: (id: string, dir: number) => void
  reorderTab: (fromIdx: number, toIdx: number) => void
  resetTabs: () => void
}

const TabsCtx = createContext<TabsValue | null>(null)

export function TabsProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<TabDef[]>(loadTabs)

  useEffect(() => { persist(tabs) }, [tabs])

  const addTab = useCallback((label: string): TabDef => {
    const clean = (label || '').trim() || 'NEW TAB'
    const id = `t_${Math.random().toString(36).slice(2, 8)}_${Date.now().toString(36).slice(-4)}`
    // User-added tabs start as widget surfaces with no category filter
    // (so every widget kind shows up in the +menu) and auto-arrange on.
    const tab: TabDef = {
      id, label: clean.toUpperCase(),
      kind: 'widgets', pageId: id,
      categories: null,
      autoArrange: true,
      builtIn: false,
    }
    setTabs((prev) => [...prev, tab])
    return tab
  }, [])

  const removeTab = useCallback((id: string) => {
    setTabs((prev) => prev.filter((t) => t.id !== id || t.builtIn))
    try { localStorage.removeItem(`fh6.tab.${id}.layout.v1`) } catch { /* ignore */ }
  }, [])

  const renameTab = useCallback((id: string, label: string) => {
    const next = (label || '').trim().toUpperCase()
    if (!next) return
    setTabs((prev) => prev.map((t) => (t.id === id ? { ...t, label: next } : t)))
  }, [])

  const setTabCategories = useCallback((id: string, categories: string[] | null) => {
    setTabs((prev) => prev.map((t) => (t.id === id ? { ...t, categories } : t)))
  }, [])

  const moveTab = useCallback((id: string, dir: number) => {
    setTabs((prev) => {
      const i = prev.findIndex((t) => t.id === id)
      if (i < 0) return prev
      const j = dir < 0 ? i - 1 : i + 1
      if (j < 0 || j >= prev.length) return prev
      const next = prev.slice()
      const a = next[i]!
      const b = next[j]!
      next[i] = b
      next[j] = a
      return next
    })
  }, [])

  // Move a tab from index `fromIdx` to index `toIdx`. Used by the
  // drag-and-drop handler in SidebarTabs; `toIdx` is the insertion index
  // computed AFTER the source tab has been removed from the list, so
  // callers don't need to compensate.
  const reorderTab = useCallback((fromIdx: number, toIdx: number) => {
    setTabs((prev) => {
      if (fromIdx < 0 || fromIdx >= prev.length) return prev
      if (toIdx === fromIdx) return prev
      const next = prev.slice()
      const [moved] = next.splice(fromIdx, 1)
      if (!moved) return prev
      const clamped = Math.max(0, Math.min(next.length, toIdx))
      next.splice(clamped, 0, moved)
      return next
    })
  }, [])

  const resetTabs = useCallback(() => setTabs(DEFAULT_TABS), [])

  const value = useMemo<TabsValue>(
    () => ({ tabs, addTab, removeTab, renameTab, setTabCategories, moveTab, reorderTab, resetTabs }),
    [tabs, addTab, removeTab, renameTab, setTabCategories, moveTab, reorderTab, resetTabs]
  )

  return <TabsCtx.Provider value={value}>{children}</TabsCtx.Provider>
}

export function useTabs(): TabsValue {
  const ctx = useContext(TabsCtx)
  if (!ctx) throw new Error('useTabs must be used inside <TabsProvider>')
  return ctx
}
