/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Phase 1 design system — see the task's DESIGN SYSTEM block for the
        // exact source values. No pure white/black, no purple, no neon.
        'cso-bg':      '#F7F6F2', // page background (warm off-white)
        'cso-card':    '#FAF9F6', // card background
        'cso-border':  '#E5E3DD', // 1px hairline borders
        'cso-teal':    '#0F766E', // primary accent
        'cso-teal-lt': '#14B8A6', // primary light (gradient stop only)
        'cso-amber':   '#B45309', // secondary accent (mid/warning)
        'cso-muted':   '#9A9691', // low state / warm gray
        'cso-heading': '#1A1A1A', // heading text
        'cso-body':    '#6B6B6B', // body/label text
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '4px',
        sm: '4px',
        md: '6px',
        lg: '6px',
        xl: '6px',
        '2xl': '6px',
        full: '9999px', // pills/chips/rings only — not a "soft card radius"
      },
    },
  },
  plugins: [],
}
