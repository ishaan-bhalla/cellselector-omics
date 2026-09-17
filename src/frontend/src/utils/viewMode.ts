export type ViewMode = 'list' | 'grid' | 'compact'

const VIEW_MODE_KEY = 'cso-view-mode'

export function getViewMode(): ViewMode {
  try {
    const v = localStorage.getItem(VIEW_MODE_KEY)
    return v === 'grid' || v === 'compact' ? v : 'list'
  } catch {
    return 'list'
  }
}

export function setViewMode(mode: ViewMode): void {
  try {
    localStorage.setItem(VIEW_MODE_KEY, mode)
  } catch {
    // Same reasoning as theme.ts: still applies for this load, just won't
    // persist in private-browsing / storage-disabled contexts.
  }
}
