import { useEffect, useMemo, useRef, useState } from 'react'
import type { components } from '@fh-racer/contract/api'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useDialog } from '@/shared/context/DialogContext'
import { cx, formatLapTime } from '@/shared/lib/format'
import {
  HDR_PANEL, HDR_PILL, HDR_PILL_OPEN,
  HDR_DROPDOWN, HDR_DROPDOWN_HEAD, HDR_DROPDOWN_TITLE, HDR_DROPDOWN_SUB,
  HDR_DROPDOWN_EMPTY, HDR_DROPDOWN_BODY, HDR_DROPDOWN_FOOT,
  MINI_BTN, MINI_BTN_DANGER, MINI_BTN_HIGHLIGHT,
} from '@/shared/components/layout/panelStyles'

const SESSIONS_PILL_REPLAYING = 'bg-[rgba(255,184,77,0.18)] border-[rgba(255,184,77,0.55)] text-amber'
const SESSIONS_PILL_LABEL     = 'font-display font-extrabold text-[9.5px] tracking-[0.16em]'
const SESSIONS_PILL_META      = 'opacity-70 text-[8.5px]'

const SESSION_ROW_BASE   = 'bg-[rgba(225,200,255,0.05)] border border-[rgba(225,200,255,0.15)] rounded-[10px] p-2 mb-1'
const SESSION_ROW_LOADED = 'bg-[rgba(255,184,77,0.12)] border-[rgba(255,184,77,0.5)]'
const SESSION_KIND       = 'font-display text-[9px] tracking-[0.18em] px-2 py-0.5 rounded-full bg-[color-mix(in_srgb,var(--lilac)_13%,transparent)] text-lilac border border-[color-mix(in_srgb,var(--lilac)_33%,transparent)]'
const SESSION_KIND_RACE  = 'bg-[color-mix(in_srgb,var(--pink)_13%,transparent)] text-pink border-[color-mix(in_srgb,var(--pink)_33%,transparent)]'

type SessionListItem = components['schemas']['SessionListItem']

interface SessionGroup { key: string; label: string; items: SessionListItem[] }

export default function SessionsPanel() {
  const {
    activeCarId,
    sessionsList, sessionsLoading,
    loadSession, clearLoadedSession, deleteSession,
    loadedSessionId,
  } = useSession()
  const dialog = useDialog()
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent): void => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open])

  const sessions = sessionsList ?? []
  const groups   = useMemo(() => groupByDate(sessions), [sessions])

  const triggerLabel = loadedSessionId
    ? 'REPLAY'
    : sessions.length > 0
      ? `${sessions.length} SESSION${sessions.length === 1 ? '' : 'S'}`
      : sessionsLoading ? '…' : 'NO SESSIONS'

  return (
    <div className={HDR_PANEL} ref={wrapRef}>
      <button
        type="button"
        className={cx(HDR_PILL, open && HDR_PILL_OPEN, loadedSessionId && SESSIONS_PILL_REPLAYING)}
        onClick={() => setOpen((o) => !o)}
        title="Sessions — per-car history"
      >
        <span className={SESSIONS_PILL_LABEL}>SESSIONS</span>
        <span className={SESSIONS_PILL_META}>{triggerLabel}</span>
      </button>

      {open && (
        <div className={cx(HDR_DROPDOWN, 'w-[380px]')}>
          <div className={HDR_DROPDOWN_HEAD}>
            <span className={HDR_DROPDOWN_TITLE}>SESSIONS</span>
            <span className={HDR_DROPDOWN_SUB}>{sessions.length} total</span>
          </div>

          {!activeCarId && (
            <div className={HDR_DROPDOWN_EMPTY}>No active car. Start driving to begin.</div>
          )}

          {activeCarId && sessions.length === 0 && (
            <div className={HDR_DROPDOWN_EMPTY}>
              {sessionsLoading ? 'Loading…' : 'No sessions yet. Drive to record one.'}
            </div>
          )}

          {groups.length > 0 && (
            <div className={HDR_DROPDOWN_BODY}>
              {groups.map(({ key, label, items }) => (
                <div key={key} className="mb-1">
                  <div className="font-display text-[9px] tracking-[0.22em] text-ink-faint px-0.5 py-1 mt-1">{label}</div>
                  {items.map((s) => (
                    <SessionRow
                      key={s.id}
                      s={s}
                      isLoaded={s.id === loadedSessionId}
                      onLoad={() => loadSession(s.id)}
                      onDelete={async () => {
                        if (!s.endedAt) return
                        const ok = await dialog.confirm({
                          title: 'Delete this session?',
                          message: `Removes the ${(s.type || 'session').replace('_', ' ')} session and its frames permanently.`,
                          confirmLabel: 'Delete',
                          destructive: true,
                        })
                        if (ok) deleteSession(s.id)
                      }}
                    />
                  ))}
                </div>
              ))}
            </div>
          )}

          {loadedSessionId && (
            <div className={HDR_DROPDOWN_FOOT}>
              <button
                type="button"
                className={cx(MINI_BTN, MINI_BTN_HIGHLIGHT)}
                onClick={() => { clearLoadedSession(); setOpen(false) }}
              >
                RETURN TO LIVE
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface SessionRowProps {
  s: SessionListItem
  isLoaded: boolean
  onLoad: () => void
  onDelete: () => void
}

function SessionRow({ s, isLoaded, onLoad, onDelete }: SessionRowProps) {
  const isRace = s.type === 'race'
  const isOpen = !s.endedAt
  const time   = formatTimeOfDay(s.startedAt)
  const dur    = formatShortDuration(s.durationS)
  const best   = s.bestLapS ? `BEST ${formatLapTime(s.bestLapS)}` : null
  const kindLabel = (s.type || 'session').replace('_', ' ').toUpperCase()

  return (
    <div className={cx(SESSION_ROW_BASE, isLoaded && SESSION_ROW_LOADED)}>
      <div className="flex items-center gap-2">
        <span className={cx(SESSION_KIND, isRace && SESSION_KIND_RACE)}>{kindLabel}</span>
        {isOpen && (
          <span className="font-display text-[8px] tracking-[0.2em] px-[6px] py-0.5 rounded-full bg-[rgba(168,243,208,0.18)] text-mint border border-[rgba(168,243,208,0.45)]">LIVE · OPEN</span>
        )}
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-cream">{time}</span>
      </div>

      <div className="flex gap-[10px] mt-[6px] font-mono text-[10px] text-ink-dim">
        <span>{dur}</span>
        {s.lapCount > 0 && <span>{s.lapCount} lap{s.lapCount === 1 ? '' : 's'}</span>}
        {best && <span>{best}</span>}
      </div>

      <div className="flex gap-1 mt-[6px] justify-end items-center">
        {isLoaded
          ? <span className="font-display text-[9px] tracking-[0.18em] text-amber px-2 py-[3px]">● VIEWING</span>
          : <button type="button" className={MINI_BTN} onClick={onLoad}>LOAD</button>}
        <button
          type="button"
          className={cx(MINI_BTN, MINI_BTN_DANGER)}
          disabled={isOpen}
          title={isOpen ? 'In-flight session cannot be deleted' : 'Delete this session'}
          onClick={onDelete}
        >DELETE</button>
      </div>
    </div>
  )
}

function groupByDate(sessions: SessionListItem[]): SessionGroup[] {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1)
  const buckets = new Map<string, SessionGroup>()
  for (const s of sessions) {
    const raw = new Date(s.startedAt)
    if (isNaN(raw.getTime())) continue
    const d = new Date(raw); d.setHours(0, 0, 0, 0)
    let key: string, label: string
    if (d.getTime() === today.getTime())          { key = 'today';     label = 'TODAY' }
    else if (d.getTime() === yesterday.getTime()) { key = 'yesterday'; label = 'YESTERDAY' }
    else {
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      key = `${y}-${m}-${dd}`
      label = key
    }
    if (!buckets.has(key)) buckets.set(key, { key, label, items: [] })
    buckets.get(key)!.items.push(s)
  }
  for (const b of buckets.values()) {
    b.items.sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())
  }
  return [...buckets.values()]
}

function formatShortDuration(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.round(seconds || 0))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${String(r).padStart(2, '0')}`
}

function formatTimeOfDay(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}
