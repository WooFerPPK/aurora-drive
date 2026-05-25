export interface HeaderToggleProps {
  visible: boolean
  onToggle: () => void
}

export default function HeaderToggle({ visible, onToggle }: HeaderToggleProps) {
  // `header-toggle` class is kept as a marker so the state-driven
  // `.app.app-header-hidden .header-toggle { top: 0 }` + the svg rotate
  // rule in index.css still apply. Visual styling is Tailwind.
  return (
    <button
      type="button"
      className="header-toggle absolute top-header left-1/2 -translate-x-1/2 w-[52px] h-[14px] p-0 flex items-center justify-center bg-[linear-gradient(180deg,rgba(58,24,80,0.92),rgba(26,8,38,0.92))] border-x border-b border-[rgba(255,193,220,0.32)] rounded-b-xl text-ink-dim cursor-pointer z-[1600] backdrop-blur-[10px] backdrop-saturate-[1.4] [transition:top_220ms_cubic-bezier(0.4,0.2,0.2,1),background_140ms_ease,color_140ms_ease,width_140ms_ease,box-shadow_140ms_ease] hover:bg-[linear-gradient(180deg,rgba(255,94,167,0.28),rgba(202,166,255,0.22))] hover:text-cream hover:w-[62px] hover:shadow-[0_6px_20px_-8px_rgba(255,94,167,0.55)]"
      onClick={onToggle}
      title={visible ? 'Hide header' : 'Show header'}
      aria-label={visible ? 'Hide header' : 'Show header'}
      aria-expanded={visible}
    >
      <svg
        viewBox="0 0 20 10"
        width="20"
        height="10"
        aria-hidden
        className="transition-transform duration-[220ms] ease-[cubic-bezier(0.4,0.2,0.2,1)]"
      >
        <path
          d="M3 7 L10 3 L17 7"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </button>
  )
}
