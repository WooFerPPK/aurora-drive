// client/src/components/toasts/LiveErrorToast.tsx
//
// Phase 3 §1.3 #5: surface the two `/ws/live` channel error shapes the
// frontend used to silently drop —
//
//   { type: "error", code, message?, topics?, received?, hz? }
//   { type: "udp_bind_failed", message }
//
// `udp_bind_failed` is a one-shot the server pushes right after
// `hello` when the UDP listener never bound (port already in use,
// permission denied, etc.). It explains an empty live stream that
// would otherwise look like the user hasn't started driving yet.
//
// `error` is the discriminator the backend uses for misuses of the
// WS protocol: wrong-channel / unknown-topic / unknown-message /
// unsupported-rate. Treat these as developer-facing warnings — they
// shouldn't fire in normal operation, but when they do, surfacing
// them is much friendlier than the previous "silently dropped"
// behaviour.
//
// Renders nothing — pure side effect. Mount once near the top of
// the app tree (inside NotificationProvider, next to
// EngineCurveChangeToast).

import { useEffect } from 'react'
import type { LiveErrorMessage } from '@fh-racer/contract/ws'
import { liveClient } from '@/shared/lib/wsClient'
import { useNotify } from '@/shared/context/NotificationContext'

const ERROR_TITLES: Record<LiveErrorMessage['code'], string> = {
  'wrong-channel':    'Coach topic subscribed on /ws/live',
  'unknown-topic':    'Unknown live topic',
  'unknown-message':  'Unknown live message',
  'unsupported-rate': 'Unsupported frame rate',
}

export default function LiveErrorToast(): null {
  const notify = useNotify()

  useEffect(() => {
    const offError = liveClient.subscribe('error', (msg) => {
      if (!msg) return
      const title = ERROR_TITLES[msg.code] || `Live channel error: ${msg.code}`
      const message = msg.message
        || (msg.topics ? `Topics: ${msg.topics.join(', ')}`
        : msg.received ? `Received: ${msg.received}`
        : msg.hz != null ? `hz=${msg.hz}`
        : 'No further detail')
      notify({ kind: 'warn', title, message, duration: 8_000 })
    })

    const offBind = liveClient.subscribe('udp_bind_failed', (msg) => {
      if (!msg) return
      notify({
        kind: 'error',
        title: 'UDP listener did not bind',
        message: msg.message
          ? `${msg.message} — telemetry frames will not arrive until the listener can bind.`
          : 'Telemetry frames will not arrive until the listener can bind.',
        // Persistent until dismissed: this is a backend-config issue
        // the user needs to fix (port collision, permission), not a
        // transient warning.
        duration: 0,
      })
    })

    return () => { offError(); offBind() }
  }, [notify])

  return null
}
