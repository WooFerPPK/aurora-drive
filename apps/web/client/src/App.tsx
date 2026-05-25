import { useCallback, useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import AppHeader from '@/shared/components/layout/AppHeader'
import HeaderToggle from '@/shared/components/layout/HeaderToggle'
import ReplayScrubber from '@/features/dashboard/components/ReplayScrubber'
import ErrorBoundary from '@/shared/components/primitives/ErrorBoundary'
import EngineCurveChangeToast from '@/features/dashboard/components/toasts/EngineCurveChangeToast'
import LiveErrorToast from '@/features/dashboard/components/toasts/LiveErrorToast'
import { useTabs } from '@/features/dashboard/context/TabsContext'
import { useSettings } from '@/features/settings/context/SettingsContext'
import { renderTabRoute, DEFAULT_ROUTE } from '@/routes'
import Sandbox from '@/features/sandbox/pages/Sandbox'

const HEADER_HIDDEN_KEY = 'fh6.shell.headerHidden'

function useHeaderVisible(): [boolean, () => void] {
  const [visible, setVisible] = useState<boolean>(() => {
    try { return localStorage.getItem(HEADER_HIDDEN_KEY) !== '1' }
    catch { return true }
  })
  useEffect(() => {
    try { localStorage.setItem(HEADER_HIDDEN_KEY, visible ? '0' : '1') }
    catch { /* ignore */ }
  }, [visible])
  const toggle = useCallback(() => setVisible((v) => !v), [])
  return [visible, toggle]
}

function useThemeAttribute(): void {
  const { settings } = useSettings()
  const theme = settings?.display.theme ?? 'dark'
  useEffect(() => {
    document.documentElement.dataset['theme'] = theme
  }, [theme])
}

export default function App() {
  const { tabs } = useTabs()
  const [headerVisible, toggleHeader] = useHeaderVisible()
  useThemeAttribute()

  // `app` class is preserved as a structural marker for the state-driven
  // `.app.app-header-hidden .header` + `.header-toggle` collapse rules
  // still living in index.css. Visual styling for the shell itself is
  // Tailwind utilities.
  return (
    <div className={`app relative flex flex-col h-screen z-[2] ${headerVisible ? '' : 'app-header-hidden'}`}>
      <AppHeader />
      <HeaderToggle visible={headerVisible} onToggle={toggleHeader} />
      <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
        <Routes>
          {tabs.map((tab) => (
            <Route
              key={tab.id}
              path={`/${tab.id}`}
              element={<ErrorBoundary>{renderTabRoute(tab)}</ErrorBoundary>}
            />
          ))}
          {import.meta.env.DEV && (
            <Route path="/sandbox" element={<ErrorBoundary><Sandbox /></ErrorBoundary>} />
          )}
          <Route path="*" element={<Navigate to={DEFAULT_ROUTE} replace />} />
        </Routes>
      </main>
      <ReplayScrubber />
      <EngineCurveChangeToast />
      <LiveErrorToast />
    </div>
  )
}
