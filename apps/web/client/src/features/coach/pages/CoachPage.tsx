import { useEffect, useState } from 'react'
import type { CalloutMessage } from '@fh-racer/contract/ws'
import type { components } from '@fh-racer/contract/api'
import { Card } from '@/shared/components/primitives/Card'
import { api } from '@/shared/lib/api'
import { getCoachClient } from '@/shared/lib/wsClient'
import { formatDateShort } from '@/shared/lib/format'

type CoachStatus = components['schemas']['CoachStatus']

export default function CoachPage() {
  const [status, setStatus]     = useState<CoachStatus | null>(null)
  const [callouts, setCallouts] = useState<CalloutMessage[]>([])
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let alive = true
    api.coachStatus().then((s) => { if (alive) setStatus(s) }).catch(() => {})

    const client = getCoachClient()
    const offConn = client.onConnectionChange(setConnected)
    const offCall = client.subscribe('callout', (msg) => {
      setCallouts((prev) => [msg, ...prev].slice(0, 50))
    })

    return () => { alive = false; offConn(); offCall() }
  }, [])

  return (
    <div className="surface surface-coach">
      <Card title="Coach" sub={connected ? 'connected' : 'disconnected'}>
        <p className="empty-blurb">
          The coach pushes call-outs over <code>/ws/coach</code> while you drive.
          Q&A and rich rendering land with the widget pass.
        </p>
        {status && (
          <div className="kv-block">
            <div><span className="kv-k">availability</span><span>{String(status.available ?? '—')}</span></div>
            <div><span className="kv-k">model</span><span>{status.model || '—'}</span></div>
            <div><span className="kv-k">reason</span><span>{status.reason || '—'}</span></div>
          </div>
        )}
      </Card>

      <Card title="Recent call-outs" sub={`${callouts.length} this session`}>
        {callouts.length === 0
          ? <div className="muted">No call-outs yet.</div>
          : (
            <ul className="callout-list">
              {callouts.map((c) => (
                <li key={c.id} className={`callout callout-${c.priority || 'info'}`}>
                  <div className="callout-head">
                    <span className="callout-priority">{(c.priority || 'info').toUpperCase()}</span>
                    <span className="callout-when">{formatDateShort(new Date(c.atS * 1000).toISOString())}</span>
                  </div>
                  <div className="callout-text">{c.text}</div>
                </li>
              ))}
            </ul>
          )}
      </Card>
    </div>
  )
}
