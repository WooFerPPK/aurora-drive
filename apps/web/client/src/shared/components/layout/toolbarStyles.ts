// Shared Tailwind class strings for the edit-toolbar surface — the
// pink-pill buttons used by EditToggle (header) and EditPalette
// (floating per-tab toolbar + its dropdown menus).

export const TOOLBAR_BTN =
  'flex items-center gap-[5px] bg-[rgba(26,8,38,0.72)] border border-[rgba(255,193,220,0.3)] text-cream font-display text-[9px] font-semibold tracking-[0.2em] px-[9px] py-[3px] rounded-full cursor-pointer backdrop-blur-[10px] transition-[background,border-color] duration-[120ms] ease-in-out hover:bg-[rgba(255,193,220,0.16)] hover:border-[rgba(255,94,167,0.55)]'

export const TOOLBAR_BTN_EDIT_ON =
  'bg-[rgba(255,94,167,0.22)] border-[rgba(255,94,167,0.65)] text-cream shadow-[0_0_12px_rgba(255,94,167,0.35)]'

// Tweaks applied to TOOLBAR_BTN when stacked vertically inside the
// EditPalette body (full-width, left-aligned, more vertical padding).
export const TOOLBAR_BTN_BODY = 'justify-start w-full px-[10px] py-[7px]'

export const TOOLBAR_COUNT =
  'font-mono text-[9px] bg-[rgba(202,166,255,0.25)] text-cream px-[6px] py-px rounded-full tracking-[0]'

// Floating menu (widgets / categories) portal-mounted under a button.
export const TOOLBAR_MENU =
  'dash-toolbar-menu absolute top-[calc(100%+8px)] right-0 w-[360px] bg-[linear-gradient(160deg,rgba(42,14,58,0.95),rgba(26,8,38,0.95))] border border-[rgba(255,193,220,0.3)] rounded-[14px] p-[10px] shadow-[0_24px_60px_-16px_rgba(255,94,167,0.55),0_0_0_1px_rgba(255,255,255,0.04)] backdrop-blur-[16px] backdrop-saturate-[1.4] z-[2050]'

export const TOOLBAR_MENU_HEAD =
  'font-display text-[10px] tracking-[0.22em] text-bubblegum uppercase mb-2'

export const TOOLBAR_MENU_GRID =
  'grid grid-cols-2 gap-1'

export const TOOLBAR_MENU_EMPTY =
  'col-span-full font-mono text-[11px] text-ink-faint p-3 text-center'

export const TOOLBAR_MENU_FOOT =
  'mt-2 font-mono text-[9px] text-ink-faint text-center tracking-[0.06em]'

export const TOOLBAR_ITEM =
  'flex items-center gap-[6px] border rounded-lg px-2 py-[6px] cursor-pointer font-display text-[10px] font-medium tracking-[0.16em] text-left transition-all duration-[120ms] ease-in-out'

export const TOOLBAR_ITEM_OFF =
  'bg-[rgba(225,200,255,0.06)] border-[rgba(225,200,255,0.16)] text-ink-dim hover:bg-[rgba(255,193,220,0.12)] hover:text-cream'

export const TOOLBAR_ITEM_ON =
  'bg-[rgba(255,94,167,0.18)] border-[rgba(255,94,167,0.45)] text-cream'

export const TOOLBAR_ITEM_MARK =
  'inline-flex items-center justify-center w-[14px] h-[14px] rounded-[4px] bg-white/[0.08] text-[10px] shrink-0'

export const TOOLBAR_ITEM_MARK_ON =
  'bg-[rgba(255,94,167,0.55)] text-white'
