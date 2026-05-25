import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { components } from '@fh-racer/contract/api'
import { useSettings } from '@/features/settings/context/SettingsContext'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useNotify } from '@/shared/context/NotificationContext'
import { useDialog } from '@/shared/context/DialogContext'
import Select from '@/shared/components/primitives/Select'

type Settings = components['schemas']['SettingsResponse']
type FrameRate = 10 | 30 | 60
type SpeedUnit = 'kmh' | 'mph'
type TempUnit = 'c' | 'f'
type Theme = 'dark' | 'light'
type CoachPriority = 'info' | 'tip' | 'warn'

interface SectionDef { id: string; label: string; hint: string }

const SECTIONS: SectionDef[] = [
  { id: 'telemetry', label: 'Telemetry',  hint: 'Network + cadence' },
  { id: 'display',   label: 'Display',    hint: 'Units + theme' },
  { id: 'models',    label: 'Models',     hint: 'What to enable' },
  { id: 'data',      label: 'Data',       hint: 'Retention + privacy' },
  { id: 'garage',    label: 'Garage',     hint: 'Saved cars' },
  { id: 'danger',    label: 'Danger zone',hint: 'Permanent actions' },
]

export default function SettingsPage() {
  const { settings, loading, error, patch, refresh } = useSettings()
  const { cars, wipeAll, deleteCar } = useSession()
  const notify = useNotify()
  const dialog = useDialog()
  const [pending, setPending] = useState(false)
  const [draft, setDraft]     = useState<Settings | null>(null)
  const [activeId, setActiveId] = useState<string>(SECTIONS[0]!.id)
  const contentRef = useRef<HTMLDivElement>(null)
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({})

  useEffect(() => { if (settings && !draft) setDraft(settings) }, [settings, draft])

  const dirty = useMemo(
    () => !!draft && JSON.stringify(draft) !== JSON.stringify(settings),
    [draft, settings],
  )

  useEffect(() => {
    const root = contentRef.current
    if (!root) return
    let raf = 0
    const onScroll = (): void => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const rootTop = root.getBoundingClientRect().top
        const triggerY = rootTop + 80
        let next = SECTIONS[0]!.id
        for (const s of SECTIONS) {
          const el = sectionRefs.current[s.id]
          if (!el) continue
          if (el.getBoundingClientRect().top <= triggerY) next = s.id
        }
        setActiveId((cur) => (cur === next ? cur : next))
      })
    }
    onScroll()
    root.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      if (raf) cancelAnimationFrame(raf)
      root.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [draft])

  const save = async (): Promise<void> => {
    if (!dirty || !draft) return
    setPending(true)
    try {
      await patch(draft)
      notify.success('Settings saved', { message: 'Synced to the backend.' })
    } catch (err) {
      notify.error('Could not save settings', {
        message: (err as Error)?.message || 'Unknown error',
        duration: 0,
      })
    } finally {
      setPending(false)
    }
  }

  const jumpTo = (id: string): void => {
    const el = sectionRefs.current[id]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const set = (path: string, value: unknown): void => {
    setDraft((cur) => {
      if (!cur) return cur
      const next = structuredClone(cur) as unknown as Record<string, unknown>
      let node: Record<string, unknown> = next
      const parts = path.split('.')
      for (let i = 0; i < parts.length - 1; i++) {
        node = node[parts[i]!] as Record<string, unknown>
      }
      node[parts[parts.length - 1]!] = value
      return next as unknown as Settings
    })
  }

  if (loading || !draft) {
    return (
      <div className="settings-page">
        <div className="settings-loading">Loading settings…</div>
      </div>
    )
  }
  if (error) {
    return (
      <div className="settings-page">
        <div className="settings-error">
          <div className="settings-error-title">Couldn&apos;t load settings</div>
          <div className="settings-error-msg">{String((error as Error).message || error)}</div>
          <button type="button" className="btn" onClick={refresh}>Retry</button>
        </div>
      </div>
    )
  }

  const setRef = (id: string) => (el: HTMLElement | null): void => { sectionRefs.current[id] = el }

  return (
    <div className="settings-page">
      <aside className="settings-nav">
        <div className="settings-nav-title">Settings</div>
        <ul className="settings-nav-list">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className={`settings-nav-item ${activeId === s.id ? 'active' : ''} ${s.id === 'danger' ? 'danger' : ''}`}
                onClick={() => jumpTo(s.id)}
              >
                <span className="settings-nav-label">{s.label}</span>
                <span className="settings-nav-hint">{s.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="settings-content" ref={contentRef}>
        <section
          ref={setRef('telemetry')}
          data-section="telemetry"
          className="settings-section"
        >
          <SectionHead title="Telemetry" hint="How the backend listens for FH6's UDP stream." />
          <div className="settings-field-grid">
            <Field label="Listen address" hint="Bind address for the UDP socket.">
              <input
                type="text"
                value={draft.telemetry.listenAddr}
                onChange={(e) => set('telemetry.listenAddr', e.target.value)}
              />
            </Field>
            <Field label="Listen port" hint="1024–65535. Avoid 5200–5300 (FH6 reserved).">
              <input
                type="number" min="1024" max="65535"
                value={draft.telemetry.listenPort}
                onChange={(e) => set('telemetry.listenPort', Number(e.target.value))}
              />
            </Field>
            <Field label="Preferred frame rate" hint="WS push rate. Widgets draw at rAF regardless.">
              <Select<FrameRate>
                value={draft.telemetry.preferredFrameRate}
                onChange={(v) => set('telemetry.preferredFrameRate', v)}
                options={[
                  { value: 10, label: '10 Hz' },
                  { value: 30, label: '30 Hz' },
                  { value: 60, label: '60 Hz' },
                ]}
              />
            </Field>
            <Toggle
              label="Auto-detect cadence"
              hint="Track the live frame rate from packet deltas."
              checked={draft.telemetry.autoDetectCadence}
              onChange={(v) => set('telemetry.autoDetectCadence', v)}
            />
          </div>
        </section>

        <section
          ref={setRef('display')}
          data-section="display"
          className="settings-section"
        >
          <SectionHead title="Display" hint="How values render across every widget." />
          <div className="settings-field-grid">
            <Field label="Speed">
              <Select<SpeedUnit>
                value={draft.display.speedUnit}
                onChange={(v) => set('display.speedUnit', v)}
                options={[
                  { value: 'kmh', label: 'km/h' },
                  { value: 'mph', label: 'mph' },
                ]}
              />
            </Field>
            <Field label="Temperature">
              <Select<TempUnit>
                value={draft.display.tempUnit}
                onChange={(v) => set('display.tempUnit', v)}
                options={[
                  { value: 'c', label: '°C' },
                  { value: 'f', label: '°F' },
                ]}
              />
            </Field>
            <Field label="Theme">
              <Select<Theme>
                value={draft.display.theme}
                onChange={(v) => set('display.theme', v)}
                options={[
                  { value: 'dark',  label: 'Dark' },
                  { value: 'light', label: 'Light' },
                ]}
              />
            </Field>
            <Toggle
              label="Reduce motion"
              hint="Mute large animations on lower-power machines."
              checked={draft.display.reduceMotion}
              onChange={(v) => set('display.reduceMotion', v)}
            />
          </div>
        </section>

        <section
          ref={setRef('models')}
          data-section="models"
          className="settings-section"
        >
          <SectionHead title="Models" hint="Toggle individual ML models and coach features." />
          <div className="settings-toggle-list">
            {([
              ['llmCoach',           'LLM coach',            'Real-time call-outs from the language model coach.'],
              ['tireWearModel',      'Tire wear model',      'Models tire wear since FH6 does not ship it.'],
              ['shiftCoach',         'Shift coach',          'Detects missed upshifts and rev-match opportunities.'],
              ['predictions',        'Predictions',          'Lap / finish / tire failure predictions.'],
              ['drivingFingerprint', 'Driving fingerprint',  'Continuous trait scoring (smooth, brave, precise…).'],
              ['voiceCallouts',      'Voice call-outs',      'Speak coach call-outs aloud while driving.'],
            ] as const).map(([k, label, hint]) => (
              <Toggle
                key={k}
                label={label}
                hint={hint}
                checked={!!draft.models[k]}
                onChange={(v) => set(`models.${k}`, v)}
              />
            ))}
          </div>
          <div className="settings-field-grid settings-field-grid-half">
            <Field
              label="Min coach priority"
              hint="Suppress lower-priority call-outs while driving."
            >
              <Select<CoachPriority>
                value={draft.models.minCoachPriority}
                onChange={(v) => set('models.minCoachPriority', v)}
                options={[
                  { value: 'info', label: 'Info',    hint: 'Show all call-outs' },
                  { value: 'tip',  label: 'Tip',     hint: 'Hide info-level' },
                  { value: 'warn', label: 'Warning', hint: 'Only critical alerts' },
                ]}
              />
            </Field>
          </div>
        </section>

        <section
          ref={setRef('data')}
          data-section="data"
          className="settings-section"
        >
          <SectionHead title="Data" hint="Retention and privacy. All telemetry stays on-device by default." />
          <div className="settings-toggle-list">
            <Toggle
              label="Record sessions"
              hint="Persist sessions and per-frame telemetry."
              checked={draft.data.recordSessions}
              onChange={(v) => set('data.recordSessions', v)}
            />
            <Toggle
              label="Store raw packets"
              hint="Keep the original 324-byte FH6 packets. Useful for debugging."
              checked={draft.data.storeRawPackets}
              onChange={(v) => set('data.storeRawPackets', v)}
            />
            <Toggle
              label="Share analytics"
              hint="Off by default. Telemetry never leaves the machine unless this is on."
              checked={draft.data.shareAnalytics}
              onChange={(v) => set('data.shareAnalytics', v)}
            />
          </div>
          <div className="settings-field-grid settings-field-grid-half">
            <Field label="Retention" hint="How long to keep recorded sessions.">
              <div className="settings-suffix">
                <input
                  type="number" min="1"
                  value={draft.data.retentionDays}
                  onChange={(e) => set('data.retentionDays', Number(e.target.value))}
                />
                <span>days</span>
              </div>
            </Field>
          </div>
        </section>

        <section
          ref={setRef('garage')}
          data-section="garage"
          className="settings-section"
        >
          <SectionHead
            title="Garage"
            hint={`${cars.length} car${cars.length === 1 ? '' : 's'} recorded`}
          />
          {cars.length === 0
            ? <div className="settings-empty">No cars yet — drive once to populate this list.</div>
            : (
              <ul className="settings-car-list">
                {cars.map((c) => (
                  <li key={c.id} className="settings-car-row">
                    <div className="settings-car-mono">
                      {(c.short?.[0] || c.display?.[0] || '?').toUpperCase()}
                    </div>
                    <div className="settings-car-main">
                      <div className="settings-car-name">{c.display || c.short || c.id}</div>
                      <div className="settings-car-meta">
                        {c.class || '—'} · PI {c.pi ?? '—'} · {c.sessionCount ?? 0} session{c.sessionCount === 1 ? '' : 's'}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn small danger"
                      onClick={async () => {
                        const ok = await dialog.confirm({
                          title: `Delete "${c.display || c.id}"?`,
                          message: 'All sessions for this car are removed along with it. Cannot be undone.',
                          confirmLabel: 'Delete car',
                          destructive: true,
                        })
                        if (ok) deleteCar(c.id)
                      }}
                    >Delete</button>
                  </li>
                ))}
              </ul>
            )}
        </section>

        <section
          ref={setRef('danger')}
          data-section="danger"
          className="settings-section settings-section-danger"
        >
          <SectionHead
            title="Danger zone"
            hint="Permanent actions. Confirm twice."
            tone="danger"
          />
          <div className="settings-danger-row">
            <div className="settings-danger-text">
              <div className="settings-danger-label">Wipe all data</div>
              <div className="settings-danger-hint">
                Deletes every car, session, frame, and mistake. Cannot be undone.
              </div>
            </div>
            <button
              type="button"
              className="btn danger"
              onClick={async () => {
                const ok = await dialog.confirm({
                  title: 'Wipe ALL data?',
                  message: 'Deletes every car, session, frame, and mistake recorded by this backend. Cannot be undone.',
                  confirmLabel: 'Wipe everything',
                  destructive: true,
                })
                if (ok) wipeAll()
              }}
            >Wipe all data</button>
          </div>
        </section>

        <div className="settings-foot-spacer" />
      </div>

      <div
        className={`settings-savebar ${dirty ? 'dirty' : 'clean'}`}
        aria-hidden={!dirty && !pending}
      >
        <div className="settings-savebar-inner">
          <div className="settings-savebar-status">
            <span className={`dot ${dirty ? 'dirty' : 'clean'}`} aria-hidden />
            <span>{dirty ? 'Unsaved changes' : 'All changes saved'}</span>
          </div>
          <div className="settings-savebar-actions">
            {dirty && (
              <button type="button" className="btn ghost" onClick={() => setDraft(settings)}>
                Revert
              </button>
            )}
            <button
              type="button"
              className="btn primary"
              onClick={save}
              disabled={!dirty || pending}
            >
              {pending ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

interface SectionHeadProps { title: string; hint?: string; tone?: 'danger' }
function SectionHead({ title, hint, tone }: SectionHeadProps) {
  return (
    <header className={`settings-section-head ${tone === 'danger' ? 'danger' : ''}`}>
      <h2 className="settings-section-title">{title}</h2>
      {hint && <div className="settings-section-hint">{hint}</div>}
    </header>
  )
}

interface FieldProps { label: string; hint?: string; children?: ReactNode }
function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="settings-field">
      <span className="settings-field-label">{label}</span>
      {children}
      {hint && <span className="settings-field-hint">{hint}</span>}
    </label>
  )
}

interface ToggleProps {
  label: string
  hint?: string
  checked: boolean
  onChange: (next: boolean) => void
}
function Toggle({ label, hint, checked, onChange }: ToggleProps) {
  return (
    <label className={`settings-toggle ${checked ? 'on' : ''}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="settings-toggle-switch" aria-hidden>
        <span className="settings-toggle-knob" />
      </span>
      <span className="settings-toggle-text">
        <span className="settings-toggle-label">{label}</span>
        {hint && <span className="settings-toggle-hint">{hint}</span>}
      </span>
    </label>
  )
}
