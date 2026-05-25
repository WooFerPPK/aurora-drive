import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { TabVisibleEntry } from '@/features/dashboard/widgetRegistry'
import {
  buildDefaultLayout, getWidgetDef, GRID_COLS, nearestSize, defaultSize, maxSize, clampSize,
} from '@/features/dashboard/widgetRegistry'
import { autoArrangeGrid } from '@/features/dashboard/lib/autoLayout'

// Per-tab dashboard layout in **grid units**. Each entry:
//   { kind, x, y, w, h, visible }
// Persisted under fh6.tab.{tabId}.layout.v3. v1 = pixel-based legacy;
// v2 = free grid; v3 = grid with Apple-style discrete sizes. The bump
// drops stale entries without an explicit migration.

export interface LayoutEntry {
  kind: string
  x: number
  y: number
  w: number
  h: number
  visible: boolean
}

export interface LayoutPatch {
  x?: number
  y?: number
  w?: number
  h?: number
  visible?: boolean
}

export type SnapBias = 'grow' | 'shrink' | null

const STORAGE_KEY = (tabId: string): string => `fh6.tab.${tabId}.layout.v3`
const STALE_KEYS  = (tabId: string): string[] => [
  `fh6.tab.${tabId}.layout.v1`,
  `fh6.tab.${tabId}.layout.v2`,
]

function probeStored(tabId: string): boolean {
  try { return localStorage.getItem(STORAGE_KEY(tabId)) != null } catch { return false }
}

function loadLayout(tabId: string, defaultVisible: readonly TabVisibleEntry[]): LayoutEntry[] {
  const def = buildDefaultLayout(defaultVisible as TabVisibleEntry[]) as LayoutEntry[]
  try {
    const raw = localStorage.getItem(STORAGE_KEY(tabId))
    const parsed = raw ? (JSON.parse(raw) as Partial<LayoutEntry>[]) : null
    if (!parsed) return def
    const byKind = Object.fromEntries(parsed.map((m) => [m.kind, m])) as Record<string, Partial<LayoutEntry>>
    return def.map((d) => {
      const persisted = byKind[d.kind]
      if (!persisted) return d
      // Normalise persisted size for the widget. Snap widgets get the
      // value forced onto the nearest preset; freeform widgets just get
      // clamped to the min/max envelope so a previously-saved arbitrary
      // (w, h) survives a reload.
      const wdef = getWidgetDef(d.kind)
      const pw = persisted.w ?? d.w
      const ph = persisted.h ?? d.h
      const sz = !wdef
        ? null
        : wdef.resize === 'freeform'
          ? clampSize(wdef, pw, ph)
          : nearestSize(wdef, pw, ph)
      // Trust the persisted x as-is. With dynamic columns, the saved
      // x may exceed the *current* col count (e.g. layout saved on a
      // wide viewport, loaded on a narrow one); CSS grid auto-extends
      // and the surface scrolls horizontally to reach the widget, so
      // clamping here would just destroy the user's placement on
      // every reload that happens at a different viewport width.
      return {
        ...d,
        x: Math.max(0, persisted.x ?? d.x),
        y: Math.max(0, persisted.y ?? d.y),
        w: sz?.w ?? d.w,
        h: sz?.h ?? d.h,
        visible: persisted.visible ?? d.visible,
      }
    })
  } catch {
    return def
  }
}

function save(tabId: string, layout: LayoutEntry[]): void {
  try { localStorage.setItem(STORAGE_KEY(tabId), JSON.stringify(layout)) } catch { /* ignore */ }
}

// Snap a candidate rect to the grid bounds AND to a valid size for the
// widget. For snap-mode widgets (the default) "valid" means one of the
// declared presets — resize commits pass bias='grow' or 'shrink' so the
// snap target tracks the direction of the gesture. For freeform widgets
// "valid" just means inside the min/max envelope at integer cell coords.
export function snapToGrid(
  kind: string,
  rect: { x: number; y: number; w: number; h: number },
  bias: SnapBias = null,
  cols: number = GRID_COLS,
): { x: number; y: number; w: number; h: number } {
  const def = getWidgetDef(kind)
  let { x, y, w, h } = rect
  if (def?.resize === 'freeform') {
    const sz = clampSize(def, w, h)
    w = sz.w; h = sz.h
  } else {
    const sz = def ? nearestSize(def, w | 0, h | 0, bias as null) : { w: w | 0, h: h | 0 }
    w = sz.w; h = sz.h
  }
  x = Math.max(0, Math.min(cols - w, x | 0))
  y = Math.max(0, y | 0)
  return { x, y, w, h }
}

export interface UseTabLayoutResult {
  layout: LayoutEntry[]
  topKind: string | null
  pristine: boolean
  setEntry: (kind: string, patch: LayoutPatch, bias?: SnapBias) => void
  setSize: (kind: string, sizeIdx: number) => void
  bringToFront: (kind: string) => void
  toggleVisible: (kind: string) => void
  reset: () => void
  arrange: () => void
}

// `cols` is the current viewport-derived column count, passed in by
// WidgetSurface. Used to clamp drag commits and to feed the auto-
// arranger so it packs widgets into the visible grid. Defaults to
// GRID_COLS (the static fallback) for non-WidgetSurface callers.
//
// `rows` is the visible row count derived from the surface height.
// The arranger treats it as a soft cap — it will swap widgets onto
// smaller presets to fit when overflowing is the alternative, but
// won't refuse to place anything.
export function useTabLayout(
  tabId: string,
  defaultVisible: readonly TabVisibleEntry[],
  cols: number = GRID_COLS,
  rows: number = Infinity,
): UseTabLayoutResult {
  const [layout, setLayout]     = useState<LayoutEntry[]>(() => loadLayout(tabId, defaultVisible))
  const [topKind, setTopKind]   = useState<string | null>(null)
  const [pristine, setPristine] = useState<boolean>(() => !probeStored(tabId))
  const layoutRef = useRef(layout)
  layoutRef.current = layout
  const defaultVisibleRef = useRef(defaultVisible)
  defaultVisibleRef.current = defaultVisible

  useEffect(() => {
    setLayout(loadLayout(tabId, defaultVisibleRef.current))
    setPristine(!probeStored(tabId))
    setTopKind(null)
    // Best-effort cleanup of older storage formats.
    for (const k of STALE_KEYS(tabId)) {
      try { localStorage.removeItem(k) } catch { /* ignore */ }
    }
  }, [tabId])

  useEffect(() => { save(tabId, layout) }, [tabId, layout])

  // setEntry accepts a patch that may include x/y/w/h; we run the
  // result through snapToGrid so callers can't drop the layout into an
  // unsupported size.
  const setEntry = useCallback((kind: string, patch: LayoutPatch, bias: SnapBias = null) => {
    setLayout((prev) =>
      prev.map((m) => {
        if (m.kind !== kind) return m
        const merged = { ...m, ...patch }
        const snapped = snapToGrid(kind, merged, bias, cols)
        return { ...m, ...snapped }
      })
    )
  }, [cols])

  // Set a widget to a specific declared size by index (used by the
  // size picker in the window head).
  const setSize = useCallback((kind: string, sizeIdx: number) => {
    setLayout((prev) =>
      prev.map((m) => {
        if (m.kind !== kind) return m
        const def = getWidgetDef(kind)
        const sz = def?.sizes?.[sizeIdx]
        if (!sz) return m
        const w = sz.w, h = sz.h
        const x = Math.max(0, Math.min(cols - w, m.x))
        return { ...m, w, h, x }
      })
    )
  }, [cols])

  const bringToFront = useCallback((kind: string) => setTopKind(kind), [])

  const toggleVisible = useCallback((kind: string) => {
    setLayout((prev) => {
      const target = prev.find((m) => m.kind === kind)
      const turningOn = target && !target.visible
      return prev.map((m) => {
        if (m.kind !== kind) return m
        // When turning a widget back on, reset to its default size
        // (and let the user re-pick where it goes) rather than restore
        // a stale geometry that might collide.
        if (turningOn) {
          const def = getWidgetDef(kind)
          const sz = defaultSize(def)
          return { ...m, visible: true, w: sz.w, h: sz.h }
        }
        return { ...m, visible: false }
      })
    })
  }, [])

  const reset = useCallback(() => {
    try { localStorage.removeItem(STORAGE_KEY(tabId)) } catch { /* ignore */ }
    setLayout(buildDefaultLayout(defaultVisibleRef.current as TabVisibleEntry[]) as LayoutEntry[])
    setPristine(true)
    setTopKind(null)
  }, [tabId])

  const arrange = useCallback(() => {
    setLayout((prev) => {
      // Hand the packer everything it needs to consider size variants:
      // the widget's preset list and its resize mode (freeform widgets
      // keep their current rect). The packer may return different w/h
      // than we passed in — we merge those back verbatim.
      const visibleItems = prev
        .filter((m) => m.visible)
        .map((m) => {
          const def = getWidgetDef(m.kind)
          return {
            kind:       m.kind,
            w:          m.w,
            h:          m.h,
            sizes:      def?.sizes,
            resize:     def?.resize,
            categories: def?.categories,
          }
        })
      const placed = autoArrangeGrid(visibleItems, cols, { targetRows: rows }) as Record<string, Partial<LayoutEntry>>
      return prev.map((m) => (placed[m.kind] ? { ...m, ...placed[m.kind] } : m))
    })
    setPristine(false)
  }, [cols, rows])

  return useMemo(
    () => ({ layout, topKind, pristine, setEntry, setSize, bringToFront, toggleVisible, reset, arrange }),
    [layout, topKind, pristine, setEntry, setSize, bringToFront, toggleVisible, reset, arrange]
  )
}

// Re-export so callers don't have to thread through widgetRegistry.
export { GRID_COLS, maxSize }
