import { Card } from '@/shared/components/primitives/Card'
import Select from '@/shared/components/primitives/Select'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useDialog } from '@/shared/context/DialogContext'
import { formatDateShort, formatDuration, formatLapTime } from '@/shared/lib/format'

export default function SessionsPage() {
  const {
    cars, activeCar, activeCarId, selectedCarId, setSelectedCarId,
    sessionsList, sessionsLoading,
    loadSession, loadedSessionId, clearLoadedSession,
    deleteSession,
  } = useSession()
  const dialog = useDialog()

  const rows = sessionsList ?? []
  const carOptions: Array<{ value: string; label: string }> = [
    { value: '', label: 'Follow live' },
    ...cars.map((c) => ({ value: c.id, label: c.display || c.short || c.id })),
  ]

  return (
    <div className="surface surface-sessions">
      <Card
        title="Sessions"
        sub={activeCar ? `${activeCar.display || activeCar.id} · ${rows.length}` : `${rows.length}`}
      >
        <div className="sessions-toolbar">
          <label className="field">
            <span>Car</span>
            <Select<string>
              value={selectedCarId || ''}
              onChange={(v) => setSelectedCarId(v || null)}
              options={carOptions}
              ariaLabel="Filter sessions by car"
            />
          </label>
          {loadedSessionId && (
            <button type="button" className="btn ghost" onClick={clearLoadedSession}>
              Exit replay
            </button>
          )}
        </div>

        {sessionsLoading && <div className="muted">Loading…</div>}
        {!sessionsLoading && rows.length === 0 && (
          <div className="muted">
            {activeCarId ? "No sessions yet for this car — drive once and they'll show up here." : 'No active car.'}
          </div>
        )}

        {rows.length > 0 && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Type</th>
                  <th>Laps</th>
                  <th>Best</th>
                  <th>Duration</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id} className={loadedSessionId === s.id ? 'row-selected' : undefined}>
                    <td>{formatDateShort(s.startedAt)}</td>
                    <td>{(s.type || '—').replace('_', ' ')}</td>
                    <td>{s.lapCount ?? 0}</td>
                    <td>{formatLapTime(s.bestLapS)}</td>
                    <td>{formatDuration(s.durationS)}</td>
                    <td className="row-actions">
                      <button type="button" className="btn small" onClick={() => loadSession(s.id)}>Load</button>
                      <button
                        type="button"
                        className="btn small danger"
                        disabled={!s.endedAt}
                        title={!s.endedAt ? 'In-flight session cannot be deleted' : ''}
                        onClick={async () => {
                          const ok = await dialog.confirm({
                            title: 'Delete this session?',
                            message: `Removes the ${(s.type || 'session').replace('_', ' ')} session and its frames permanently.`,
                            confirmLabel: 'Delete',
                            destructive: true,
                          })
                          if (ok) deleteSession(s.id)
                        }}
                      >Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
