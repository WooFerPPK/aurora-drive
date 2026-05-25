import { useEffect, useRef, useState } from 'react'
import type { components } from '@fh-racer/contract/api'
import { useSession } from '@/features/sessions/context/SessionContext'
import { useDialog } from '@/shared/context/DialogContext'
import { cx, formatDuration } from '@/shared/lib/format'
import {
  HDR_PANEL, HDR_PILL, HDR_PILL_OPEN, HDR_PILL_EMPTY,
  HDR_DROPDOWN, HDR_DROPDOWN_HEAD, HDR_DROPDOWN_TITLE, HDR_DROPDOWN_SUB,
  HDR_DROPDOWN_EMPTY, HDR_DROPDOWN_BODY,
  MINI_BTN, MINI_BTN_DANGER,
} from '@/shared/components/layout/panelStyles'

const GARAGE_PILL_PADDING = 'pl-1' // overrides HDR_PILL's px-[9px] to match the old `.garage-pill { padding: 3px 9px 3px 4px }`
const PILL_MONO_BASE      = 'w-[22px] h-[18px] rounded-md bg-[linear-gradient(135deg,var(--lilac),var(--pink))] flex items-center justify-center font-display font-extrabold text-[10px] text-white shadow-[0_0_10px_rgba(255,94,167,0.4)]'
const PILL_META           = 'flex flex-col leading-[1.1] text-left'
const PILL_NAME           = 'text-cream tracking-[0.08em] text-[9.5px] font-display max-w-[140px] overflow-hidden text-ellipsis whitespace-nowrap'
const PILL_SUB            = 'text-[7.5px] text-ink-faint'

const CAR_CARD_BASE       = 'bg-[rgba(225,200,255,0.05)] border border-[rgba(225,200,255,0.15)] rounded-[10px] p-2'
const CAR_CARD_ACTIVE     = 'bg-[rgba(255,193,220,0.12)] border-[rgba(255,94,167,0.5)]'
const CAR_CARD_LIVE       = 'shadow-[0_0_18px_-8px_rgba(168,243,208,0.6)]'
const CAR_MONO_BASE       = 'w-[30px] h-[26px] rounded-md bg-[linear-gradient(135deg,var(--lilac),var(--pink))] flex items-center justify-center font-display font-extrabold text-[12px] text-white shrink-0'
const CAR_MONO_ACTIVE     = 'bg-[linear-gradient(135deg,var(--pink),var(--butter))]'

type CarSummary = components['schemas']['CarSummary']

export default function GaragePanel() {
  const {
    cars,
    activeCarId, activeCar,
    liveCarId,
    selectedCarId, setSelectedCarId,
    deleteCar, deleteCarSessions, renameCar,
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

  const label = activeCar?.display || activeCar?.short || 'NO CAR'
  const initial = (label[0] || '?').toUpperCase()

  return (
    <div className={HDR_PANEL} ref={wrapRef}>
      <button
        type="button"
        className={cx(HDR_PILL, GARAGE_PILL_PADDING, open && HDR_PILL_OPEN, !activeCar && HDR_PILL_EMPTY)}
        onClick={() => setOpen((o) => !o)}
        title="Garage — saved per-car sessions"
      >
        <span className={PILL_MONO_BASE}>{initial}</span>
        <span className={PILL_META}>
          <span className={PILL_NAME}>{label}</span>
          <span className={PILL_SUB}>
            {activeCar?.class || '—'} · PI {activeCar?.pi ?? '—'} · {cars.length} saved
          </span>
        </span>
      </button>

      {open && (
        <div className={cx(HDR_DROPDOWN, 'w-[360px]')}>
          <div className={HDR_DROPDOWN_HEAD}>
            <span className={HDR_DROPDOWN_TITLE}>GARAGE</span>
            <span className={HDR_DROPDOWN_SUB}>{cars.length} car{cars.length === 1 ? '' : 's'}</span>
          </div>

          {cars.length === 0 ? (
            <div className={HDR_DROPDOWN_EMPTY}>
              No cars recorded yet. Start driving to begin saving.
            </div>
          ) : (
            <div className={HDR_DROPDOWN_BODY}>
              {cars.map((c: CarSummary) => {
                const isActive = c.id === activeCarId
                const isLive   = c.id === liveCarId
                const isPinned = c.id === selectedCarId
                const isPlaceholderName = typeof c.display === 'string'
                  && /^Car\s+#?\d+\s*$/.test(c.display.trim())
                return (
                  <div
                    key={c.id}
                    className={cx(CAR_CARD_BASE, isActive && CAR_CARD_ACTIVE, isLive && CAR_CARD_LIVE)}
                  >
                    <div className="flex items-center gap-2">
                      <div className={cx(CAR_MONO_BASE, isActive && CAR_MONO_ACTIVE)}>
                        {(c.short?.[0] || c.display?.[0] || '?').toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-display text-[12px] text-cream tracking-[0.08em] flex items-center gap-2 overflow-hidden text-ellipsis whitespace-nowrap">
                          {c.display || c.short || c.id}
                          {isLive && <span className="text-mint text-[9px] tracking-[0.16em] [text-shadow:0_0_6px_rgba(168,243,208,0.5)] shrink-0">● LIVE</span>}
                          {isPinned && !isLive && <span className="text-butter text-[9px] tracking-[0.16em] shrink-0">PINNED</span>}
                          {isPlaceholderName && <span className="text-butter text-[9px] tracking-[0.16em] shrink-0">UNKNOWN</span>}
                        </div>
                        <div className="font-mono text-[9px] text-ink-faint mt-px">
                          #{c.ordinal ?? '—'} · {c.class || '—'} · PI {c.pi ?? '—'} · {c.drivetrain || '—'}
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-[6px] mt-2">
                      <Stat label="SESSIONS" value={c.sessionCount ?? 0} />
                      <Stat label="DRIVEN"   value={formatDuration(c.totalSecondsDriven)} />
                      <Stat label="GROUP"    value={c.groupLabel || c.group || '—'} />
                    </div>

                    <div className="flex gap-1 mt-2 flex-wrap justify-end">
                      {!isPinned && (
                        <button
                          type="button"
                          className={MINI_BTN}
                          onClick={() => setSelectedCarId(c.id)}
                          disabled={!isLive && isActive}
                          title="Pin this car as active"
                        >
                          {isLive ? 'PIN' : isActive ? 'ACTIVE' : 'SELECT'}
                        </button>
                      )}
                      {isPinned && (
                        <button
                          type="button"
                          className={MINI_BTN}
                          onClick={() => setSelectedCarId(null)}
                          title="Follow the live car again"
                        >
                          UNPIN
                        </button>
                      )}
                      <button
                        type="button"
                        className={MINI_BTN}
                        disabled={c.ordinal == null}
                        title={
                          c.ordinal == null
                            ? 'No ordinal — cannot rename'
                            : isPlaceholderName
                              ? 'This car is not in the bundled name table. Submit the real name.'
                              : 'Correct the displayed name for this car.'
                        }
                        onClick={async () => {
                          const next = await dialog.prompt({
                            title: isPlaceholderName
                              ? `Name car #${c.ordinal}`
                              : `Rename "${c.display || c.id}"`,
                            message: isPlaceholderName
                              ? 'The community ordinal table does not know this car yet. Enter the real name (e.g. "2024 Lamborghini Revuelto") and it will be remembered across sessions.'
                              : 'Update the name shown across the dashboard for every tune of this car.',
                            initial: isPlaceholderName ? '' : (c.display || ''),
                            placeholder: 'YEAR MAKE MODEL',
                            confirmLabel: 'Save name',
                          })
                          if (next === null) return
                          try {
                            await renameCar(c.ordinal, next)
                          } catch (err) {
                            await dialog.alert({
                              title: 'Could not rename car',
                              message: (err as Error)?.message || 'Unknown error',
                            })
                          }
                        }}
                      >
                        {isPlaceholderName ? 'NAME' : 'RENAME'}
                      </button>
                      <button
                        type="button"
                        className={MINI_BTN}
                        onClick={async () => {
                          const ok = await dialog.confirm({
                            title: `Wipe sessions for ${c.display || c.id}?`,
                            message: 'Deletes every session for this car. The car row stays in the garage.',
                            confirmLabel: 'Wipe sessions',
                            destructive: true,
                          })
                          if (ok) deleteCarSessions(c.id)
                        }}
                      >
                        WIPE SESSIONS
                      </button>
                      <button
                        type="button"
                        className={cx(MINI_BTN, MINI_BTN_DANGER)}
                        onClick={async () => {
                          const ok = await dialog.confirm({
                            title: `Delete "${c.display || c.id}"?`,
                            message: 'All sessions for this car are removed along with it. Cannot be undone.',
                            confirmLabel: 'Delete car',
                            destructive: true,
                          })
                          if (ok) deleteCar(c.id)
                        }}
                      >
                        DELETE
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface StatProps {
  label: string
  value: string | number | null | undefined
}

function Stat({ label, value }: StatProps) {
  return (
    <div className="flex flex-col gap-px px-[6px] py-1 bg-black/[0.18] rounded-md">
      <span className="font-display text-[7px] tracking-[0.18em] text-ink-faint">{label}</span>
      <span className="font-mono text-[11px] text-cream">{value ?? '—'}</span>
    </div>
  )
}
