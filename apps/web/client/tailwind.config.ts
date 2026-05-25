import type { Config } from 'tailwindcss'

// Theme is bound to the CSS custom properties declared in
// src/styles/tokens.css. Every colour/font/spacing token below
// resolves to `var(--foo)` so there is one palette source of truth.
// Preflight is OFF: the legacy reset in tokens.css stays in charge
// while we incrementally peel styles out of index.css. Re-enable
// once index.css is gone (see Phase 7 final step).
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        bg: {
          0: 'var(--bg-0)',
          1: 'var(--bg-1)',
          2: 'var(--bg-2)',
        },
        lilac:       'var(--lilac)',
        pink:        'var(--pink)',
        bubblegum:   'var(--bubblegum)',
        butter:      'var(--butter)',
        mint:        'var(--mint)',
        'baby-blue': 'var(--baby-blue)',
        amber:       'var(--amber)',
        danger:      'var(--danger)',
        cream:       'var(--cream)',
        ink: {
          DEFAULT: 'var(--ink)',
          dim:     'var(--ink-dim)',
          faint:   'var(--ink-faint)',
        },
        card: {
          border: 'var(--card-border)',
        },
      },
      fontFamily: {
        display: ['var(--f-display)'],
        ui:      ['var(--f-ui)'],
        mono:    ['var(--f-mono)'],
      },
      spacing: {
        'header-h':  'var(--header-h)',
        'sidebar-w': 'var(--sidebar-w)',
      },
      height: {
        header: 'var(--header-h)',
      },
      width: {
        sidebar: 'var(--sidebar-w)',
      },
      backgroundImage: {
        'card-gradient': 'var(--card-bg)',
        'app':           'var(--bg-grad)',
      },
      boxShadow: {
        'card-glow': 'var(--card-glow)',
      },
      keyframes: {
        'brand-spin': {
          to: { transform: 'rotate(360deg)' },
        },
        shimmer: {
          '0%':   { 'background-position': '-200% 0' },
          '100%': { 'background-position':  '200% 0' },
        },
        pulse: {
          '0%, 100%': { transform: 'scale(1)',   opacity: '1' },
          '50%':      { transform: 'scale(1.4)', opacity: '0.7' },
        },
        'select-in': {
          from: { opacity: '0', transform: 'translateY(-4px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'dialog-backdrop-in': {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        'dialog-in': {
          from: { opacity: '0', transform: 'translateY(8px) scale(0.97)' },
          to:   { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'notify-in': {
          from: { opacity: '0', transform: 'translateX(28px) scale(0.96)' },
          to:   { opacity: '1', transform: 'translateX(0) scale(1)' },
        },
        'notify-out': {
          from: { opacity: '1', transform: 'translateX(0) scale(1)' },
          to:   { opacity: '0', transform: 'translateX(36px) scale(0.97)' },
        },
        'coach-pulse': {
          '0%, 100%': { transform: 'scale(1)',    'box-shadow': '0 0 4px rgba(168,243,208,0.4)' },
          '50%':      { transform: 'scale(1.15)', 'box-shadow': '0 0 18px rgba(168,243,208,0.7)' },
        },
        'coach-ring-out': {
          '0%':   { transform: 'scale(1)',   opacity: '0.7' },
          '100%': { transform: 'scale(3.5)', opacity: '0' },
        },
        shiftFlashUp: {
          '0%':   { transform: 'translateY(-4px)', opacity: '0.6' },
          '100%': { transform: 'none',             opacity: '1' },
        },
        shiftFlashDown: {
          '0%':   { transform: 'translateY( 4px)', opacity: '0.6' },
          '100%': { transform: 'none',             opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}

export default config
