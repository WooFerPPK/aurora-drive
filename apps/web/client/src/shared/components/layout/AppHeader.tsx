import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useTabs } from '@/features/dashboard/context/TabsContext'
import { formatDateShort } from '@/shared/lib/format'
import Brand from './Brand'
import StatusPill from './StatusPill'
import Sidebar from './Sidebar'
import SidebarTabs from './SidebarTabs'
import SessionsPanel from '@/features/sessions/components/SessionsPanel'
import GaragePanel from '@/features/settings/components/GaragePanel'
import EditPalette from '@/features/dashboard/components/EditPalette'
import EditToggle from '@/features/dashboard/components/EditToggle'

export default function AppHeader() {
  const { loadedSessionId, getLoadedSession } = useSession()
  const loaded = loadedSessionId ? getLoadedSession() : null

  const { tabs } = useTabs()
  const location = useLocation()
  const activeId = location.pathname.replace(/^\//, '').split('/')[0] || null
  const activeTab = tabs.find((t) => t.id === activeId)
  const activeLabel = activeTab?.label || ''

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const closeSidebar = useCallback(() => setSidebarOpen(false), [])
  const wasOpenRef = useRef(false)

  useEffect(() => {
    if (wasOpenRef.current && !sidebarOpen) {
      const btn = document.getElementById('app-hamburger')
      btn?.focus({ preventScroll: true })
    }
    wasOpenRef.current = sidebarOpen
  }, [sidebarOpen])

  return (
    <>
      {/*
        `header` class is preserved as a structural marker so the parent
        `.app.app-header-hidden .header` collapse rule in index.css still
        matches. Visual styling lives in the Tailwind utilities alongside.
      */}
      <header className="header flex items-center px-3 h-header gap-2 border-b border-[rgba(255,193,220,0.18)] bg-[linear-gradient(180deg,rgba(26,8,38,0.85),rgba(42,14,58,0.55))] backdrop-blur-[14px] backdrop-saturate-[1.4] shrink-0 z-[1500] relative [transition:height_220ms_cubic-bezier(0.4,0.2,0.2,1),opacity_180ms_ease,padding_220ms_cubic-bezier(0.4,0.2,0.2,1),border-bottom-color_180ms_ease]">
        <button
          id="app-hamburger"
          type="button"
          className="inline-flex items-center justify-center w-7 h-7 bg-[rgba(255,193,220,0.06)] border border-[rgba(255,193,220,0.22)] text-cream rounded-lg text-[14px] leading-none cursor-pointer shrink-0 transition-[background,border-color] duration-[120ms] ease-in-out hover:bg-[rgba(255,193,220,0.16)] hover:border-[rgba(255,94,167,0.55)]"
          onClick={() => setSidebarOpen((v) => !v)}
          aria-expanded={sidebarOpen}
          aria-controls="app-sidebar"
          aria-label="Open navigation"
          title="Navigation"
        >☰</button>

        <Brand title="Aurora Drive" />

        <StatusPill />

        {activeLabel && (
          <span className="font-display text-[9px] font-medium tracking-[0.22em] uppercase text-bubblegum ml-1 whitespace-nowrap max-[980px]:hidden before:content-['·'] before:text-ink-faint before:mr-[6px]">{activeLabel}</span>
        )}

        {loaded && (
          <div
            className="flex items-center gap-[6px] px-[9px] py-[3px] rounded-full bg-[rgba(154,247,195,0.07)] border border-[rgba(154,247,195,0.22)] font-mono text-[9px] tracking-[0.18em] whitespace-nowrap text-ink-dim"
            title={`Replaying session ${loaded.id || ''}`}
          >
            <span className="w-[6px] h-[6px] rounded-full animate-[pulse_1.4s_ease-in-out_infinite] shrink-0 bg-amber" />
            REPLAY · {formatDateShort(loaded.startedAt)}
          </div>
        )}

        <div className="flex items-center gap-[6px] ml-auto">
          <EditToggle />
          <SessionsPanel />
          <GaragePanel />
        </div>
      </header>

      <Sidebar open={sidebarOpen} onClose={closeSidebar}>
        <SidebarTabs onNavigate={closeSidebar} />
      </Sidebar>

      <EditPalette />
    </>
  )
}
