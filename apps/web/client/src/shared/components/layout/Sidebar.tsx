// client/src/components/layout/Sidebar.tsx
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { cx } from '@/shared/lib/format'
import Brand from './Brand'

export interface SidebarProps {
  open: boolean
  onClose: () => void
  children?: ReactNode
}

export default function Sidebar({ open, onClose, children }: SidebarProps) {
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const asideRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    closeBtnRef.current?.focus()
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab') return
      const root = asideRef.current
      if (!root) return
      const focusables = root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (!focusables.length) return
      const first = focusables[0]!
      const last = focusables[focusables.length - 1]!
      const active = document.activeElement
      if (e.shiftKey && active === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      } else if (!root.contains(active)) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      <div
        className={cx(
          'fixed inset-0 bg-[rgba(10,4,20,0.55)] backdrop-blur-[2px] z-[2400] transition-opacity duration-[180ms] ease-in-out motion-reduce:transition-none',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none',
        )}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        ref={asideRef}
        id="app-sidebar"
        className={cx(
          'fixed top-0 left-0 bottom-0 w-sidebar bg-[linear-gradient(180deg,rgba(42,14,58,0.96),rgba(26,8,38,0.96))] border-r border-[rgba(255,193,220,0.22)] backdrop-blur-[18px] backdrop-saturate-[1.4] shadow-[18px_0_60px_-24px_rgba(255,94,167,0.45)] transition-transform duration-[220ms] ease-[cubic-bezier(0.4,0.2,0.2,1)] motion-reduce:transition-none z-[2500] flex flex-col overflow-hidden',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sidebar-brand"
        aria-hidden={!open}
      >
        <div className="flex items-center gap-[10px] px-3 py-[10px] border-b border-[rgba(255,193,220,0.12)] shrink-0">
          <button
            type="button"
            ref={closeBtnRef}
            className="inline-flex items-center justify-center w-[26px] h-[26px] rounded-full bg-[rgba(255,193,220,0.08)] border border-[rgba(255,193,220,0.22)] text-cream text-[14px] leading-none cursor-pointer transition-[background,border-color] duration-[120ms] ease-in-out hover:bg-[rgba(255,94,167,0.22)] hover:border-[rgba(255,94,167,0.55)]"
            onClick={onClose}
            aria-label="Close navigation"
            title="Close"
          >✕</button>
          <Brand id="sidebar-brand" text="AURORA DRIVE" />
        </div>

        {children}
      </aside>
    </>
  )
}
