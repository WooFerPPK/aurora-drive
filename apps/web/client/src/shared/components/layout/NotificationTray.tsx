import { cx } from '@/shared/lib/format'
import type { NotificationItem, NotificationKind } from '@/shared/context/NotificationContext'

const ICONS: Record<NotificationKind, string> = {
  success: '✓',
  error:   '✕',
  info:    'i',
  warn:    '!',
}

const STRIPE_BY_KIND: Record<NotificationKind, string> = {
  success: 'bg-mint shadow-[0_0_14px_rgba(168,243,208,0.5)]',
  error:   'bg-danger shadow-[0_0_14px_rgba(255,122,141,0.55)]',
  info:    'bg-lilac shadow-[0_0_14px_rgba(202,166,255,0.5)]',
  warn:    'bg-butter shadow-[0_0_14px_rgba(255,224,130,0.5)]',
}

const ICON_BY_KIND: Record<NotificationKind, string> = {
  success: 'text-mint border-[rgba(168,243,208,0.45)] bg-[rgba(168,243,208,0.12)]',
  error:   'text-danger border-[rgba(255,122,141,0.5)] bg-[rgba(255,122,141,0.14)]',
  info:    'text-lilac border-[rgba(202,166,255,0.45)] bg-[rgba(202,166,255,0.12)]',
  warn:    'text-butter border-[rgba(255,224,130,0.45)] bg-[rgba(255,224,130,0.12)]',
}

export interface NotificationTrayProps {
  items: NotificationItem[]
  onDismiss: (id: number) => void
}

export default function NotificationTray({ items, onDismiss }: NotificationTrayProps) {
  if (!items || items.length === 0) return null
  return (
    <div
      className="fixed right-[18px] bottom-[18px] z-[9000] flex flex-col gap-2 pointer-events-none max-w-[min(420px,calc(100vw-36px))]"
      role="region"
      aria-live="polite"
      aria-label="Notifications"
    >
      {items.map((it) => (
        <NotificationItemView key={it.id} item={it} onDismiss={onDismiss} />
      ))}
    </div>
  )
}

interface NotificationItemViewProps {
  item: NotificationItem
  onDismiss: (id: number) => void
}

function NotificationItemView({ item, onDismiss }: NotificationItemViewProps) {
  const kind: NotificationKind = item.kind || 'info'
  return (
    <div
      className={cx(
        'pointer-events-auto relative grid grid-cols-[4px_28px_1fr_22px] gap-3 items-start py-3 pr-[14px] pl-0 bg-[linear-gradient(160deg,rgba(58,24,80,0.96),rgba(26,8,38,0.96))] border border-[rgba(255,193,220,0.28)] rounded-xl shadow-[0_24px_48px_-22px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.04),0_0_30px_-12px_rgba(255,94,167,0.4)] backdrop-blur-[14px] backdrop-saturate-[1.4] origin-bottom-right motion-reduce:animate-none',
        item.closing
          ? 'animate-[notify-out_200ms_ease_forwards] pointer-events-none motion-reduce:opacity-0'
          : 'animate-[notify-in_220ms_cubic-bezier(0.18,1.1,0.4,1)]',
      )}
      role={kind === 'error' ? 'alert' : 'status'}
    >
      <div className={cx('self-stretch rounded-l-xl', STRIPE_BY_KIND[kind])} aria-hidden />
      <div
        className={cx(
          'w-[26px] h-[26px] rounded-full flex items-center justify-center font-display font-bold text-[13px] border mt-[2px] shrink-0',
          ICON_BY_KIND[kind],
        )}
        aria-hidden
      >{ICONS[kind] || 'i'}</div>
      <div className="min-w-0 flex flex-col gap-[2px]">
        {item.title && (
          <div className="font-display text-[13px] text-cream tracking-[0.02em] leading-[1.3]">{item.title}</div>
        )}
        {item.message && (
          <div className="font-ui text-[12px] text-ink-dim leading-[1.45] break-words">{item.message}</div>
        )}
        {item.actions && item.actions.length > 0 && (
          <div className="flex gap-[6px] mt-[6px]">
            {item.actions.map((a, i) => (
              <button
                type="button"
                key={i}
                className="bg-white/[0.05] border border-[rgba(255,193,220,0.28)] text-cream font-display text-[10px] tracking-[0.14em] uppercase px-[10px] py-1 rounded-full cursor-pointer transition-[background,border-color] duration-[120ms] ease-in-out hover:bg-[rgba(255,193,220,0.18)] hover:border-[rgba(255,193,220,0.55)]"
                onClick={() => {
                  try { a.onClick?.() } finally {
                    if (!a.keepOpen) onDismiss(item.id)
                  }
                }}
              >{a.label}</button>
            ))}
          </div>
        )}
      </div>
      <button
        type="button"
        className="w-[22px] h-[22px] flex items-center justify-center bg-transparent border-none text-ink-faint text-[12px] cursor-pointer rounded-full mt-[1px] transition-[background,color] duration-[120ms] ease-in-out hover:bg-white/[0.06] hover:text-cream"
        onClick={() => onDismiss(item.id)}
        title="Dismiss"
        aria-label="Dismiss notification"
      >✕</button>
    </div>
  )
}
