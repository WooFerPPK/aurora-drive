import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react'
import type { ReactNode } from 'react'

// App-wide custom dialog system. Replaces native `alert` / `confirm` /
// `prompt` with promise-returning equivalents that match the Aurora
// Drive aesthetic. ONE dialog at a time — calls are queued.
//
// Usage:
//
//   const dialog = useDialog()
//
//   if (await dialog.confirm({
//     title: 'Delete this session?',
//     message: 'This cannot be undone.',
//     confirmLabel: 'Delete',
//     destructive: true,
//   })) deleteSession()
//
//   const name = await dialog.prompt({
//     title: 'New tab name?',
//     initial: '',
//     placeholder: 'TAB NAME',
//   })
//   if (name !== null) addTab(name)
//
//   await dialog.alert({
//     title: 'Built-in tab',
//     message: 'Built-in tabs cannot be deleted.',
//   })

export type DialogKind = 'confirm' | 'prompt' | 'alert'

export interface DialogOptions {
  title?: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  initial?: string
  placeholder?: string
}

interface DialogEntry extends DialogOptions {
  id: number
  kind: DialogKind
  resolve: (result: boolean | string | null) => void
}

export interface DialogApi {
  confirm: (opts?: DialogOptions) => Promise<boolean>
  prompt:  (opts?: DialogOptions) => Promise<string | null>
  alert:   (opts?: DialogOptions) => Promise<boolean>
}

const DialogCtx = createContext<DialogApi | null>(null)

export function DialogProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<DialogEntry[]>([])
  const counter = useRef(0)

  // Show next dialog (peek at head of queue).
  const current = queue[0] ?? null

  const showDialog = useCallback(<T,>(kind: DialogKind, opts: DialogOptions): Promise<T> => {
    return new Promise<T>((resolve) => {
      counter.current += 1
      const id = counter.current
      setQueue((q) => [...q, { ...opts, kind, id, resolve: resolve as DialogEntry['resolve'] }])
    })
  }, [])

  const close = useCallback((result: boolean | string | null) => {
    setQueue((q) => {
      const [head, ...rest] = q
      if (head?.resolve) head.resolve(result)
      return rest
    })
  }, [])

  const api = useMemo<DialogApi>(() => {
    const confirm = (opts: DialogOptions = {}) => showDialog<boolean>('confirm', opts)
    const prompt  = (opts: DialogOptions = {}) => showDialog<string | null>('prompt', opts)
    const alert   = (opts: DialogOptions = {}) => showDialog<boolean>('alert', opts)
    return { confirm, prompt, alert }
  }, [showDialog])

  return (
    <DialogCtx.Provider value={api}>
      {children}
      {current && <DialogStage dialog={current} onClose={close} />}
    </DialogCtx.Provider>
  )
}

export function useDialog(): DialogApi {
  const ctx = useContext(DialogCtx)
  if (!ctx) throw new Error('useDialog must be used inside <DialogProvider>')
  return ctx
}

// ---- the modal itself ----

function DialogStage({ dialog, onClose }: { dialog: DialogEntry; onClose: (result: boolean | string | null) => void }) {
  const { kind, title, message, confirmLabel, cancelLabel, destructive, initial, placeholder } = dialog
  const [value, setValue] = useState<string>(initial ?? '')
  const dialogRef = useRef<HTMLDivElement>(null)
  const initialFocusRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const labelConfirm = confirmLabel ?? (kind === 'prompt' ? 'OK' : kind === 'alert' ? 'OK' : 'Confirm')
  const labelCancel  = cancelLabel ?? 'Cancel'
  const showCancel   = kind !== 'alert'

  const cancel = useCallback(() => {
    onClose(kind === 'prompt' ? null : false)
  }, [onClose, kind])

  const confirmAction = useCallback(() => {
    if (kind === 'prompt')      onClose(value)
    else if (kind === 'alert')  onClose(true)
    else                        onClose(true)
  }, [kind, onClose, value])

  // Keyboard: ESC cancels, Enter confirms (unless inside a textarea).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); cancel() }
      else if (e.key === 'Enter' && (e.target as HTMLElement)?.tagName !== 'TEXTAREA') {
        e.preventDefault(); confirmAction()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [cancel, confirmAction])

  // Focus management: focus input on prompt, primary button otherwise.
  useEffect(() => {
    const el = kind === 'prompt' ? inputRef.current : initialFocusRef.current
    el?.focus()
    if (kind === 'prompt' && inputRef.current) inputRef.current.select?.()
  }, [kind])

  return (
    <div
      className="fixed inset-0 z-[9500] bg-[rgba(10,4,16,0.62)] backdrop-blur-[6px] backdrop-saturate-[1.2] flex items-center justify-center p-5 animate-[dialog-backdrop-in_180ms_ease]"
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? `dialog-title-${dialog.id}` : undefined}
      onPointerDown={(e) => { if (e.target === e.currentTarget) cancel() }}
    >
      <div
        ref={dialogRef}
        className={
          'w-[min(440px,calc(100vw-40px))] px-[22px] pt-[22px] pb-[18px] bg-[linear-gradient(160deg,rgba(58,24,80,0.97),rgba(26,8,38,0.97))] border rounded-2xl backdrop-blur-[18px] backdrop-saturate-[1.4] animate-[dialog-in_200ms_cubic-bezier(0.18,1.1,0.4,1)] ' + (destructive
            ? 'border-[rgba(255,94,167,0.5)] shadow-[0_36px_80px_-30px_rgba(0,0,0,0.75),0_0_0_1px_rgba(255,255,255,0.04),0_0_60px_-16px_rgba(255,94,167,0.6)]'
            : 'border-[rgba(255,193,220,0.36)] shadow-[0_36px_80px_-30px_rgba(0,0,0,0.75),0_0_0_1px_rgba(255,255,255,0.04),0_0_60px_-18px_rgba(255,94,167,0.45)]')
        }
        onPointerDown={(e) => e.stopPropagation()}
      >
        {title && (
          <h2
            id={`dialog-title-${dialog.id}`}
            className={
              'font-display text-[18px] font-semibold tracking-[0.02em] text-cream mb-2 leading-[1.25] ' + (destructive ? '[text-shadow:0_0_14px_rgba(255,94,167,0.4)]' : '')
            }
          >{title}</h2>
        )}
        {message && (
          <p className="font-ui text-[14px] leading-[1.55] text-ink-dim mb-4 whitespace-pre-wrap">{message}</p>
        )}

        {kind === 'prompt' && (
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder || ''}
            className="w-full bg-black/[0.32] border border-[rgba(255,193,220,0.28)] text-cream rounded-lg px-3 py-[10px] font-mono text-[14px] outline-none mb-4 transition-[border-color,box-shadow] duration-[120ms] ease-in-out focus:border-pink focus:shadow-[0_0_0_3px_rgba(255,94,167,0.16)]"
          />
        )}

        <div className="flex justify-end gap-2">
          {showCancel && (
            <button
              type="button"
              className="btn ghost"
              onClick={cancel}
            >{labelCancel}</button>
          )}
          <button
            ref={initialFocusRef}
            type="button"
            className={`btn ${destructive ? 'danger' : 'primary'}`}
            onClick={confirmAction}
          >{labelConfirm}</button>
        </div>
      </div>
    </div>
  )
}
