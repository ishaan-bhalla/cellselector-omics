import { useState } from 'react'
import { getTheme, toggleTheme, type Theme } from '../utils/theme'

// Minimal sun/moon glyph, custom inline SVG (no icon library). Renders the
// icon for the theme you'd SWITCH TO, not the current one — a sun while
// dark (click for light), a moon while light (click for dark) — the
// common convention for this kind of control.
function SunIcon({ className }: { className?: string }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M12.5 3.5l-1.4 1.4M4.9 11.1l-1.4 1.4" />
    </svg>
  )
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M13 9.3A5.5 5.5 0 016.7 3a5.5 5.5 0 106.3 6.3z" />
    </svg>
  )
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getTheme)

  return (
    <button
      onClick={() => setTheme(toggleTheme(theme))}
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      className="flex items-center justify-center w-7 h-7 rounded text-cso-body hover:text-cso-heading border border-cso-border hover:border-cso-teal transition-colors flex-shrink-0"
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}
