export type Theme = 'dark' | 'light'

const THEME_KEY = 'cso-theme'

// Dark is the default whenever localStorage has no explicit preference —
// matches index.html's inline pre-mount script (which only ever ADDS the
// `light` class, never removes one), so both agree on the same default
// without needing to duplicate the full apply logic there.
export function getTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('light', theme === 'light')
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // Private-browsing / storage-disabled — theme still applies for this
    // load via the class toggle above, it just won't persist. Not worth
    // surfacing to the user for a cosmetic preference.
  }
}

export function toggleTheme(current: Theme): Theme {
  const next: Theme = current === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  return next
}
