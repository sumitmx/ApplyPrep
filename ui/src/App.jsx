import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import Applications from './screens/Applications'
import Dashboard from './screens/Dashboard'
import Discover from './screens/Discover'
import JobDetail from './screens/JobDetail'
import Jobs from './screens/Jobs'
import Letter from './screens/Letter'
import MyCV from './screens/MyCV'
import Tailor from './screens/Tailor'

const NAV = [
  ['/dashboard', 'Overview'],
  ['/jobs', 'Jobs'],
  ['/discover', 'Where jobs come from'],
  ['/applications', 'Applications'],
  ['/my-cv', 'My CV'],
]

export default function App() {
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="brandmark">
            <img src="/favicon.svg" alt="" width="20" height="20" />
            ApplyPrep
          </div>
          <span>local build</span>
        </div>
        <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'on' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidefoot">
          <span className="dot" />
          local only, port 8756
          <br />
          No AI API key needed
        </div>
      </aside>

      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/jobs/:id/tailor" element={<Tailor />} />
          <Route path="/jobs/:id/letter" element={<Letter />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/my-cv" element={<MyCV />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  )
}
