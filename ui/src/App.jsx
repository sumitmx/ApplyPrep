import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api'
import Applications from './screens/Applications'
import Dashboard from './screens/Dashboard'
import Discover from './screens/Discover'
import JobDetail from './screens/JobDetail'
import Jobs from './screens/Jobs'
import Letter from './screens/Letter'
import Profile from './screens/Profile'
import Tailor from './screens/Tailor'

const NAV = [
  ['/dashboard', 'Overview'],
  ['/jobs', 'Jobs'],
  ['/discover', 'Where jobs come from'],
  ['/applications', 'Applications'],
  ['/profile', 'My Profile'],
]

function usePersistedTheme() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark') return saved
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  return [theme, setTheme]
}

function AiProviderPicker() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.getSettings().then(setData).catch(() => {})
  }, [])

  const onChange = async (e) => {
    const value = e.target.value
    setBusy(true)
    try {
      setData(await api.setAiProvider(value))
    } catch {
      // leave the previous selection showing
    } finally {
      setBusy(false)
    }
  }

  if (!data) return null

  const current = data.options.find((o) => o.key === data.current)

  return (
    <div className="aipicker">
      <label htmlFor="ai-provider">AI model</label>
      <select id="ai-provider" value={data.current} onChange={onChange} disabled={busy}>
        {data.options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label + (o.available ? '' : ' (not set up)')}
          </option>
        ))}
      </select>
      {current && current.model && <div className="aipicker-model">{current.model}</div>}
    </div>
  )
}

export default function App() {
  const [theme, setTheme] = usePersistedTheme()

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
        <AiProviderPicker />
        <nav className="nav">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'on' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidefoot">
          <button
            className="themetoggle"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          >
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>
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
          <Route path="/profile" element={<Profile />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  )
}
