import type { ReactElement } from 'react'
import WidgetSurface from '@/features/dashboard/components/WidgetSurface'
import SessionsPage from '@/features/sessions/pages/SessionsPage'
import CoachPage from '@/features/coach/pages/CoachPage'
import SettingsPage from '@/features/settings/pages/SettingsPage'
import type { TabDef } from '@/features/dashboard/context/TabsContext'

export function renderTabRoute(tab: TabDef): ReactElement {
  switch (tab.kind) {
    case 'sessions':  return <SessionsPage />
    case 'coach':     return <CoachPage />
    case 'settings':  return <SettingsPage />
    case 'widgets':
    default:          return <WidgetSurface tab={tab} />
  }
}

export const DEFAULT_ROUTE = '/live'
