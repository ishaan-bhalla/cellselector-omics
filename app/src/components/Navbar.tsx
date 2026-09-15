import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import ThemeToggle from './ThemeToggle'
import ViewModeToggle from './ViewModeToggle'
import type { ViewMode } from '../utils/viewMode'

const NAV_LINKS = [
  { to: '/',       label: 'Home',   end: true  },
  { to: '/about',  label: 'About',  end: false },
  { to: '/search', label: 'Search', end: false },
  { to: '/data',   label: 'Data',   end: false },
]

interface Props {
  viewMode: ViewMode
  onViewModeChange: (m: ViewMode) => void
}

// Corrected direction (see the task that replaced the original hero/nav
// pass): a thin, dense, three-zone chrome bar — LEFT wordmark + adjacent
// tag, CENTRE the view-mode control (only meaningful, so only rendered,
// on /search), RIGHT nav links with a small solid triangle marking the
// active one, plus the theme toggle. No filled accent button anywhere
// here (Part 3) — "Search" is just one of the four equal nav links now,
// not a separate CTA.
export default function Navbar({ viewMode, onViewModeChange }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const onSearchPage = location.pathname === '/search'

  return (
    <nav
      className="sticky top-0 z-50 bg-cso-bg"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <div className="max-w-7xl mx-auto px-6 py-2.5 flex items-center justify-between gap-6">
        {/* Left — wordmark + adjacent tag */}
        <button
          onClick={() => navigate('/')}
          className="flex items-baseline gap-1.5 flex-shrink-0"
          style={{ background: 'none', border: 'none', cursor: 'pointer' }}
        >
          <span className="font-sans font-semibold text-cso-heading text-[14px] tracking-tight">
            CellSelector
          </span>
          <span
            className="font-mono text-cso-body"
            style={{ fontSize: 9, letterSpacing: '0.1em', verticalAlign: 'super' }}
          >
            OMICS / v1.0
          </span>
        </button>

        {/* Centre — LIST/GRID/COMPACT, only meaningful on /search */}
        <div className="flex-1 flex justify-center">
          {onSearchPage && <ViewModeToggle mode={viewMode} onChange={onViewModeChange} />}
        </div>

        {/* Right — nav links (active marked with a triangle to its left,
            dim/bright contrast only, no weight change), theme toggle */}
        <div className="flex items-center gap-5 flex-shrink-0">
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.1em] transition-colors"
            >
              {({ isActive }) => (
                <>
                  <svg width="5" height="7" viewBox="0 0 5 7" aria-hidden="true" style={{ visibility: isActive ? 'visible' : 'hidden' }}>
                    <path d="M5 3.5L0 7V0z" fill="var(--accent)" />
                  </svg>
                  <span style={{ color: isActive ? 'var(--text-heading)' : 'var(--text-body)' }}>{label}</span>
                </>
              )}
            </NavLink>
          ))}
          <ThemeToggle />
        </div>
      </div>
    </nav>
  )
}
