import {
  createContext, useCallback, useContext, useMemo, useRef, useState,
} from 'react'
import type { ReactNode } from 'react'
import NotificationTray from '@/shared/components/layout/NotificationTray'

// App-wide notification system. Any component anywhere in the tree
// (widgets, pages, hooks) can pull `useNotify()` and emit transient
// toasts. The tray renders fixed at the bottom-right, capped at 5
// stacked items.
//
// Usage:
//
//   const notify = useNotify()
//   notify.success('Settings saved')
//   notify.error('Save failed', { message: err.message })
//   notify.info('New session', { actions: [{ label: 'Open', onClick: ... }] })
//   notify({ kind: 'warn', title: 'Stream lost', duration: 0 })  // sticky
//
// API surface:
//
//   notify(opts)                  // base call, returns the new toast id
//   notify.success(title, opts?)  // sugar
//   notify.error  (title, opts?)
//   notify.info   (title, opts?)
//   notify.warn   (title, opts?)
//   notify.dismiss(id)            // remove a specific toast
//   notify.clear()                // remove everything
//
// Each opts: { title, message?, kind?, duration?, actions? }
//   kind:     'success' | 'error' | 'info' | 'warn'   (default 'info')
//   duration: ms before auto-dismiss; 0 keeps it open (default 4000)
//   actions:  [{ label, onClick, keepOpen? }]   — optional buttons in the toast

export type NotificationKind = 'success' | 'error' | 'info' | 'warn'

export interface NotificationAction {
  label: string
  onClick: () => void
  keepOpen?: boolean
}

export interface NotificationOptions {
  title?: string
  message?: string
  kind?: NotificationKind
  duration?: number
  actions?: NotificationAction[]
}

export interface NotificationItem extends Required<Pick<NotificationOptions, 'kind' | 'title' | 'message' | 'duration' | 'actions'>> {
  id: number
  closing: boolean
}

export type Notify = ((opts?: NotificationOptions) => number) & {
  success: (title: string, opts?: NotificationOptions) => number
  error:   (title: string, opts?: NotificationOptions) => number
  info:    (title: string, opts?: NotificationOptions) => number
  warn:    (title: string, opts?: NotificationOptions) => number
  dismiss: (id: number) => void
  clear:   () => void
}

const NotificationCtx = createContext<Notify | null>(null)

const MAX_STACK     = 5
const DEFAULT_DURATION_MS = 4000
const EXIT_ANIM_MS  = 220

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<NotificationItem[]>([])
  const counter = useRef(0)
  const timers  = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map()) // id -> timeout handle

  const dismiss = useCallback((id: number) => {
    // Two-phase removal so the leave animation runs before the DOM
    // node unmounts. Mark `closing` first; remove from state after the
    // CSS transition window.
    setItems((cur) => cur.map((it) => (it.id === id ? { ...it, closing: true } : it)))
    const t = timers.current.get(id)
    if (t) { clearTimeout(t); timers.current.delete(id) }
    setTimeout(() => {
      setItems((cur) => cur.filter((it) => it.id !== id))
    }, EXIT_ANIM_MS)
  }, [])

  const clear = useCallback(() => {
    for (const t of timers.current.values()) clearTimeout(t)
    timers.current.clear()
    setItems((cur) => cur.map((it) => ({ ...it, closing: true })))
    setTimeout(() => setItems([]), EXIT_ANIM_MS)
  }, [])

  const notify = useCallback((opts: NotificationOptions = {}): number => {
    counter.current += 1
    const id = counter.current
    const item: NotificationItem = {
      id,
      kind: 'info',
      title: '',
      message: '',
      duration: DEFAULT_DURATION_MS,
      actions: [],
      ...opts,
      closing: false,
    }
    setItems((cur) => {
      const next = [...cur, item]
      // Cap the stack — drop oldest first.
      if (next.length > MAX_STACK) next.shift()
      return next
    })
    if (item.duration > 0) {
      const handle = setTimeout(() => dismiss(id), item.duration)
      timers.current.set(id, handle)
    }
    return id
  }, [dismiss])

  // Build a function-with-properties surface. The bare `notify(opts)`
  // call returns the id; `notify.success(...)` etc. are sugar.
  const value = useMemo<Notify>(() => {
    const fn = ((opts?: NotificationOptions) => notify(opts)) as Notify
    fn.success = (title, opts = {}) => notify({ ...opts, kind: 'success', title })
    fn.error   = (title, opts = {}) => notify({ ...opts, kind: 'error',   title })
    fn.info    = (title, opts = {}) => notify({ ...opts, kind: 'info',    title })
    fn.warn    = (title, opts = {}) => notify({ ...opts, kind: 'warn',    title })
    fn.dismiss = dismiss
    fn.clear   = clear
    return fn
  }, [notify, dismiss, clear])

  return (
    <NotificationCtx.Provider value={value}>
      {children}
      <NotificationTray items={items} onDismiss={dismiss} />
    </NotificationCtx.Provider>
  )
}

export function useNotify(): Notify {
  const ctx = useContext(NotificationCtx)
  if (!ctx) throw new Error('useNotify must be used inside <NotificationProvider>')
  return ctx
}
