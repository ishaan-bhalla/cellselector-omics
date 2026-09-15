import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Search from './pages/Search'
import About from './pages/About'
import Data from './pages/Data'
import { getViewMode, setViewMode, type ViewMode } from './utils/viewMode'

export default function App() {
  // Lifted out of Search.tsx so the corrected-direction Navbar (Part 2)
  // can host the LIST/GRID/COMPACT control in its centre zone and stay in
  // sync with the Search page in real time, not just on next page load —
  // both read/write the same localStorage-backed value via utils/viewMode.
  const [viewMode, setViewModeState] = useState<ViewMode>(getViewMode)
  const changeViewMode = (m: ViewMode) => { setViewModeState(m); setViewMode(m) }

  return (
    <div className="bg-cso-bg text-[var(--text-heading)] min-h-screen font-sans">
      <Navbar viewMode={viewMode} onViewModeChange={changeViewMode} />
      <Routes>
        <Route path="/"       element={<Home />}   />
        <Route path="/search" element={<Search viewMode={viewMode} />} />
        <Route path="/about"  element={<About />}  />
        <Route path="/data"   element={<Data />}   />
      </Routes>
    </div>
  )
}
