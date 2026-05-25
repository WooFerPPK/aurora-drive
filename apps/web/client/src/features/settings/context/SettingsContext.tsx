import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { components } from '@fh-racer/contract/api'
import { api } from '@/shared/lib/api'

type SettingsResponse = components['schemas']['SettingsResponse']

export interface SettingsValue {
  settings: SettingsResponse | null
  loading: boolean
  error: unknown
  refresh: () => Promise<void>
  patch: (partial: Partial<SettingsResponse>) => Promise<SettingsResponse>
}

const SettingsCtx = createContext<SettingsValue | null>(null)

// Single source of truth for /api/settings. Pages may render `settings`
// directly; the Settings page also uses `patch` to mutate.
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<unknown>(null)

  const refresh = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const next = await api.getSettings()
      setSettings(next)
    } catch (err) {
      console.warn('[settings] load failed', err)
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const patch = useCallback(async (partial: Partial<SettingsResponse>) => {
    try {
      const next = await api.patchSettings(partial)
      setSettings(next)
      return next
    } catch (err) {
      console.warn('[settings] patch failed', err)
      throw err
    }
  }, [])

  const value = useMemo<SettingsValue>(
    () => ({ settings, loading, error, refresh, patch }),
    [settings, loading, error, refresh, patch]
  )
  return <SettingsCtx.Provider value={value}>{children}</SettingsCtx.Provider>
}

export function useSettings(): SettingsValue {
  const ctx = useContext(SettingsCtx)
  if (!ctx) throw new Error('useSettings must be used inside <SettingsProvider>')
  return ctx
}
