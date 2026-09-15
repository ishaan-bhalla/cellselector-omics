/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Dual-theme design system — these resolve through CSS custom
        // properties (see src/index.css), NOT literal hex, so every
        // existing cso-* utility class becomes theme-reactive for free the
        // moment the root `.light` class toggles. Dark is the default
        // token set (:root); `.light` on <html> overrides it. No dark:
        // Tailwind variant is used here on purpose — this codebase's
        // default is INVERTED from Tailwind's own convention (dark-first,
        // light opt-in), so driving everything off CSS variables avoids
        // fighting that assumption and keeps every already-written cso-*
        // class correct with zero further changes.
        'cso-bg':      'var(--bg)',
        'cso-card':    'var(--bg-card)',
        'cso-border':  'var(--border)',
        'cso-teal':    'var(--accent)',
        'cso-amber':   'var(--accent-amber)',
        'cso-muted':   'var(--muted-state)',
        'cso-heading': 'var(--text-heading)',
        'cso-body':    'var(--text-body)',
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
