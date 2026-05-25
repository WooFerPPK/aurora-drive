// Shared Tailwind class strings for the header dropdown panels — used
// by GaragePanel and SessionsPanel. The pill trigger sits in the header
// strip and opens a dropdown anchored beneath it. The pink-fade mini
// buttons inside the dropdown are also shared.

export const HDR_PANEL = 'relative'

export const HDR_PILL =
  'inline-flex items-center gap-[6px] px-[9px] py-[3px] rounded-[10px] bg-[rgba(225,200,255,0.06)] border border-[rgba(255,193,220,0.28)] font-mono text-[9.5px] tracking-[0.1em] text-ink-dim cursor-pointer transition-[background,border-color] duration-[120ms] ease-in-out hover:bg-[rgba(255,193,220,0.14)]'

export const HDR_PILL_OPEN =
  'bg-[rgba(255,193,220,0.18)] border-[rgba(255,193,220,0.55)]'

export const HDR_PILL_EMPTY = 'opacity-70'

export const HDR_DROPDOWN =
  'absolute top-[calc(100%+8px)] right-0 max-h-[70vh] overflow-auto bg-[linear-gradient(160deg,rgba(42,14,58,0.95),rgba(26,8,38,0.95))] border border-[rgba(255,193,220,0.28)] rounded-[14px] shadow-[0_24px_60px_-20px_rgba(255,94,167,0.5),0_0_0_1px_rgba(255,255,255,0.04)] backdrop-blur-[16px] backdrop-saturate-[1.4] z-[2000] p-[10px]'

export const HDR_DROPDOWN_HEAD =
  'flex items-center justify-between mb-2'

export const HDR_DROPDOWN_TITLE =
  'font-display text-[11px] tracking-[0.22em] text-bubblegum'

export const HDR_DROPDOWN_SUB =
  'font-mono text-[9px] text-ink-faint'

export const HDR_DROPDOWN_EMPTY =
  'font-mono text-[11px] text-ink-faint p-[14px] text-center'

export const HDR_DROPDOWN_BODY =
  'flex flex-col gap-[6px]'

export const HDR_DROPDOWN_FOOT =
  'flex justify-end mt-2'

// Pink-fade pill button. Shared by both dropdowns.
export const MINI_BTN =
  'bg-[rgba(225,200,255,0.10)] border border-[rgba(225,200,255,0.25)] text-ink-dim font-display text-[9px] tracking-[0.18em] px-[9px] py-1 rounded-full cursor-pointer transition-[background,border-color,color] duration-[120ms] ease-in-out disabled:opacity-[0.35] disabled:cursor-not-allowed enabled:hover:bg-[rgba(255,193,220,0.18)] enabled:hover:border-[rgba(255,193,220,0.5)] enabled:hover:text-cream'

export const MINI_BTN_DANGER =
  'bg-[rgba(255,94,167,0.18)] border-[rgba(255,94,167,0.5)] text-[#ffafd1] enabled:hover:bg-[rgba(255,94,167,0.32)] enabled:hover:border-[rgba(255,94,167,0.8)] enabled:hover:text-white'

export const MINI_BTN_HIGHLIGHT =
  'bg-[rgba(255,184,77,0.22)] border-[rgba(255,184,77,0.55)] text-amber enabled:hover:bg-[rgba(255,184,77,0.35)] enabled:hover:text-white'
