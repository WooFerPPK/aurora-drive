import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { TelemetryProvider }    from '@/features/dashboard/context/TelemetryContext'
import { SessionProvider }      from '@/features/sessions/context/SessionContext'
import { ReplayProvider }       from '@/features/dashboard/context/ReplayContext'
import { SettingsProvider }     from '@/features/settings/context/SettingsContext'
import { TabsProvider }         from '@/features/dashboard/context/TabsContext'
import { DashUIProvider }       from '@/features/dashboard/context/DashUIContext'
import { NotificationProvider } from '@/shared/context/NotificationContext'
import { DialogProvider }       from '@/shared/context/DialogContext'
import { queryClient }          from '@/shared/lib/queryClient'
import './styles/tokens.css'
import './styles/tailwind.css'
import './styles/index.css'

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Missing #root element')

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <NotificationProvider>
          <DialogProvider>
            <SettingsProvider>
              <TelemetryProvider>
                <SessionProvider>
                  <ReplayProvider>
                    <TabsProvider>
                      <DashUIProvider>
                        <App />
                      </DashUIProvider>
                    </TabsProvider>
                  </ReplayProvider>
                </SessionProvider>
              </TelemetryProvider>
            </SettingsProvider>
          </DialogProvider>
        </NotificationProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
