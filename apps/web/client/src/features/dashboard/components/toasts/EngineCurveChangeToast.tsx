// client/src/components/toasts/EngineCurveChangeToast.tsx
//
// Subscribes to the WS `engine_curve_change` event (FR-013/FR-034) and
// shows a non-blocking toast with a "Reset training" CTA. The reset CTA
// POSTs to /api/predict/shift/reset with sessionId="live" so the
// backend resolves the current fingerprint and drops its learned state.
//
// Renders nothing — pure side effect. Mount once near the top of the
// app tree (inside NotificationProvider).

import { useEffect } from 'react'
import { liveClient } from '@/shared/lib/wsClient'
import { api } from '@/shared/lib/api'
import { useNotify } from '@/shared/context/NotificationContext'

export default function EngineCurveChangeToast(): null {
  const notify = useNotify()

  useEffect(() => {
    const off = liveClient.subscribe('event', (evt) => {
      if (!evt || evt.kind !== 'engine_curve_change') return
      const direction = evt['direction'] as string | undefined
      const dir = direction === 'positive' ? 'higher' : 'lower'
      const binsRaw = evt['binsAffected'] ?? evt['bins_affected']
      const bins = typeof binsRaw === 'number' ? binsRaw : null
      const message = bins != null
        ? `Detected torque ${dir} across ${bins} RPM bins. Training paused.`
        : `Detected torque ${dir}. Training paused.`
      notify({
        kind: 'warn',
        title: 'Engine curve changed',
        message,
        duration: 10_000,
        actions: [
          {
            label: 'Reset training',
            onClick: async () => {
              try {
                await api.resetShift({ sessionId: 'live' })
                notify.success('Shift training reset')
              } catch (err) {
                notify.error('Reset failed', { message: String(err) })
              }
            },
          },
        ],
      })
    })
    return off
  }, [notify])

  return null
}
