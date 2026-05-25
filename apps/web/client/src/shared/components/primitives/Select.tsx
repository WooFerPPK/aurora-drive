import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { cx } from '@/shared/lib/format'

// Custom Select. Drop-in replacement for native <select> styled to
// match the Aurora Drive UI and keyboard-accessible.
//
//   <Select
//     value={frameRate}
//     onChange={setFrameRate}
//     options={[
//       { value: 10, label: '10 Hz' },
//       { value: 30, label: '30 Hz' },
//       { value: 60, label: '60 Hz' },
//     ]}
//     placeholder="Pick one"   // shown when value is not in options
//     disabled={false}
//   />
//
// Keyboard:
//   Enter/Space  toggle open
//   ArrowUp/Dn   move highlight while open; open if closed
//   Home/End     jump to first/last option
//   Esc          close
//   Enter        select highlighted option

export interface SelectOption<T> {
  value: T
  label: ReactNode
  hint?: ReactNode
}

export interface SelectProps<T> {
  value: T
  onChange: (value: T) => void
  options: SelectOption<T>[]
  placeholder?: string
  disabled?: boolean
  className?: string
  ariaLabel?: string
}

export default function Select<T>({
  value,
  onChange,
  options,
  placeholder = 'Select…',
  disabled = false,
  className = '',
  ariaLabel,
}: SelectProps<T>) {
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef    = useRef<HTMLUListElement>(null)
  const wrapRef    = useRef<HTMLDivElement>(null)
  const listboxId  = useId()

  const selectedIdx = options.findIndex((o) => o.value === value)
  const selected = selectedIdx >= 0 ? options[selectedIdx]! : null

  useEffect(() => {
    if (open) setHighlight(selectedIdx >= 0 ? selectedIdx : 0)
  }, [open, selectedIdx])

  // Close on outside click.
  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent): void => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open])

  // Keep the highlighted option scrolled into view.
  useEffect(() => {
    if (!open) return
    const menu = menuRef.current
    if (!menu) return
    const el = menu.children[highlight]
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [open, highlight])

  const choose = useCallback((idx: number): void => {
    const opt = options[idx]
    if (!opt) return
    onChange(opt.value)
    setOpen(false)
    triggerRef.current?.focus()
  }, [options, onChange])

  const onKeyDown = useCallback((e: KeyboardEvent<HTMLButtonElement>): void => {
    if (disabled) return
    const last = options.length - 1
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (!open) { setOpen(true); return }
      choose(highlight)
    } else if (e.key === 'Escape') {
      if (open) { e.preventDefault(); setOpen(false); triggerRef.current?.focus() }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) { setOpen(true); return }
      setHighlight((h) => Math.min(last, h + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) { setOpen(true); return }
      setHighlight((h) => Math.max(0, h - 1))
    } else if (e.key === 'Home') {
      e.preventDefault()
      if (open) setHighlight(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      if (open) setHighlight(last)
    }
  }, [open, options, highlight, choose, disabled])

  const triggerClass = cx(
    'w-full flex items-center justify-between gap-2 bg-black/[0.32] border text-cream rounded-lg px-3 py-[9px] font-mono text-[13px] cursor-pointer text-left outline-none transition-[border-color,box-shadow,background] duration-[120ms] ease-in-out hover:border-[rgba(255,193,220,0.38)] focus-visible:border-pink focus-visible:shadow-[0_0_0_3px_rgba(255,94,167,0.16)]',
    open ? 'border-pink shadow-[0_0_0_3px_rgba(255,94,167,0.16)]' : 'border-[rgba(255,193,220,0.22)]',
  )

  return (
    <div
      ref={wrapRef}
      className={cx(
        'relative min-w-0',
        disabled && 'opacity-[0.55] pointer-events-none',
        className,
      )}
    >
      <button
        ref={triggerRef}
        type="button"
        className={triggerClass}
        onClick={() => { if (!disabled) setOpen((o) => !o) }}
        onKeyDown={onKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        {...(open ? { 'aria-controls': listboxId } : {})}
        {...(ariaLabel !== undefined ? { 'aria-label': ariaLabel } : {})}
      >
        <span className={cx(
          'overflow-hidden text-ellipsis whitespace-nowrap',
          !selected && 'text-ink-faint',
        )}>
          {selected ? selected.label : placeholder}
        </span>
        <svg
          className={cx(
            'shrink-0 text-ink-dim transition-transform duration-[160ms] ease-[cubic-bezier(0.4,0.2,0.2,1)]',
            open && 'rotate-180',
          )}
          viewBox="0 0 10 6"
          width="10"
          height="6"
          aria-hidden
        >
          <path d="M1 1 L5 5 L9 1" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <ul
          ref={menuRef}
          id={listboxId}
          className="absolute top-[calc(100%+6px)] left-0 right-0 min-w-full max-h-[260px] overflow-y-auto list-none p-1 m-0 bg-[linear-gradient(160deg,rgba(42,14,58,0.96),rgba(26,8,38,0.96))] border border-[rgba(255,193,220,0.32)] rounded-[10px] shadow-[0_20px_50px_-22px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.04),0_0_30px_-12px_rgba(255,94,167,0.35)] backdrop-blur-[14px] backdrop-saturate-[1.4] z-[2050] animate-[select-in_140ms_cubic-bezier(0.18,1.1,0.4,1)]"
          role="listbox"
          tabIndex={-1}
        >
          {options.map((opt, i) => {
            const isSel = opt.value === value
            const isHi = i === highlight
            return (
              <li
                key={String(opt.value)}
                role="option"
                aria-selected={isSel}
                className={cx(
                  'grid grid-cols-[1fr_auto] items-center gap-2 px-[10px] py-2 rounded-md cursor-pointer font-ui text-[13px] text-ink transition-[background,color] duration-100 ease-in-out',
                  isHi && isSel && 'bg-[linear-gradient(135deg,rgba(255,94,167,0.28),rgba(202,166,255,0.22))] text-cream',
                  isHi && !isSel && 'bg-[rgba(255,193,220,0.14)] text-cream',
                  !isHi && isSel && 'bg-[rgba(255,94,167,0.18)] text-cream',
                )}
                onPointerEnter={() => setHighlight(i)}
                onClick={() => choose(i)}
              >
                <span className="tracking-[0.02em]">{opt.label}</span>
                {opt.hint && <span className="col-span-full font-mono text-[10.5px] text-ink-faint mt-px">{opt.hint}</span>}
                {isSel && (
                  <span className="text-pink text-[12px] justify-self-end" aria-hidden>✓</span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
