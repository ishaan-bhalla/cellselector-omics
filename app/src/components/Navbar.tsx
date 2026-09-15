import { NavLink, useNavigate } from 'react-router-dom'

const LINK_BASE = 'text-sm font-medium transition-colors px-1'

export default function Navbar() {
  const navigate = useNavigate()

  return (
    <nav
      className="sticky top-0 z-50 bg-cso-bg"
      style={{ borderBottom: '1px solid #E5E3DD' }}
    >
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        {/* Left — wordmark */}
        <button
          onClick={() => navigate('/')}
          className="font-sans font-semibold text-cso-heading text-[15px] tracking-tight"
          style={{ background: 'none', border: 'none', cursor: 'pointer' }}
        >
          CellSelector Omics
        </button>

        {/* Centre — plain nav links, no glass pill */}
        <div className="flex items-center gap-6">
          {[
            { to: '/',       label: 'Home',   end: true  },
            { to: '/search', label: 'Search', end: false },
            { to: '/data',   label: 'Data',   end: false },
            { to: '/about',  label: 'About',  end: false },
          ].map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `${LINK_BASE} ${isActive ? 'text-cso-heading' : 'text-cso-body hover:text-cso-heading'}`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>

        {/* Right — version tag + partnership line */}
        <div className="flex items-center gap-4">
          <span className="hidden sm:inline text-[11px] text-cso-body">
            Bristol &times; AstraZeneca
          </span>
          <span className="font-mono text-[11px] text-cso-body">v1.0</span>
          <button
            onClick={() => navigate('/search')}
            className="flex items-center gap-1.5 text-xs font-medium text-cso-card bg-cso-teal px-3 py-1.5 rounded hover:bg-[#0D655E] transition-colors"
          >
            Search
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 8h10M9 4l4 4-4 4" />
            </svg>
          </button>
        </div>
      </div>
    </nav>
  )
}
