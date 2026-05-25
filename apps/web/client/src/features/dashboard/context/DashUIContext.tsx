import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

// Shared state for widget surfaces. WidgetSurface registers its toolbar
// API on mount; EditPalette / EditToggle read it. When no
// surface is mounted (e.g. on Settings or Sessions pages), the toolbar
// row stays unmounted.

export interface ToolbarApi {
  [key: string]: unknown
}

export interface DashUIValue {
  toolbarApi: ToolbarApi | null
  registerToolbar: (api: ToolbarApi) => void
  unregisterToolbar: () => void
  editMode: boolean
  setEditMode: (v: boolean) => void
  toggleEditMode: () => void
}

const DashUICtx = createContext<DashUIValue | null>(null)

export function DashUIProvider({ children }: { children: ReactNode }) {
  const [toolbarApi, setToolbarApi] = useState<ToolbarApi | null>(null)
  const [editMode, setEditMode]     = useState(false)

  const registerToolbar   = useCallback((api: ToolbarApi) => setToolbarApi(api), [])
  const unregisterToolbar = useCallback(() => setToolbarApi(null), [])
  const toggleEditMode    = useCallback(() => setEditMode((v) => !v), [])

  const value = useMemo<DashUIValue>(
    () => ({
      toolbarApi, registerToolbar, unregisterToolbar,
      editMode, setEditMode, toggleEditMode,
    }),
    [toolbarApi, registerToolbar, unregisterToolbar, editMode, toggleEditMode]
  )

  return <DashUICtx.Provider value={value}>{children}</DashUICtx.Provider>
}

export function useDashUI(): DashUIValue {
  const ctx = useContext(DashUICtx)
  if (!ctx) throw new Error('useDashUI must be inside <DashUIProvider>')
  return ctx
}
