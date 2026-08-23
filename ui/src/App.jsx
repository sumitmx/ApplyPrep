import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api } from './api'
import Applications from './screens/Applications'
import Dashboard from './screens/Dashboard'
import Discover from './screens/Discover'
import JobDetail from './screens/JobDetail'
import Jobs from './screens/Jobs'
import Letter from './screens/Letter'
import Profile from './screens/Profile'
import Tailor from './screens/Tailor'

const I = {
  overview: ['M3.5 3.5h7v6h-7z', 'M13.5 3.5h7v4h-7z', 'M13.5 11.5h7v9h-7z', 'M3.5 13.5h7v7h-7z'],
  jobs: ['M3 7.5h18a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5H3A1.5 1.5 0 0 1 1.5 18V9A1.5 1.5 0 0 1 3 7.5Z',
         'M8.5 7.5V5.8A1.8 1.8 0 0 1 10.3 4h3.4a1.8 1.8 0 0 1 1.8 1.8v1.7'],
  applications: ['M5 2.5h8l5 5V21a.5.5 0 0 1-.5.5h-12A.5.5 0 0 1 5 21V3a.5.5 0 0 1 .5-.5Z',
                 'M13 2.5v5h5', 'M8.5 13h7', 'M8.5 17h4.5'],
  sources: ['M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19Z', 'M2.5 12h19',
            'M12 2.5a14 14 0 0 1 0 19 14 14 0 0 1 0-19Z'],
  profile: ['M12 3.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z', 'M4 20.5a8 8 0 0 1 16 0'],
}

function Icon({ paths }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths.map((p, i) => <path key={i} d={p} />)}
    </svg>
  )
}

// One flat, compact list of the main sections. Each row expands its sub-sections
// on hover; nothing is expanded otherwise, so the list stays gap-free. The anchor
// ids match the slugs Panel derives from its own title.
const NAV_GROUPS = [
 ['Dashboard', [
  ['/dashboard', 'Overview', I.overview, [
    ['your-search-funnel', 'Search funnel'],
    ['jobs-by-fit', 'Jobs by fit'],
    ['application-pipeline', 'Application pipeline'],
    ['where-jobs-come-from', 'Job sources'],
    ['my-cv-coverage', 'CV coverage'],
  ]],
 ]],
 ['Workspace', [
  ['/jobs', 'Jobs', I.jobs, []],
  ['/applications', 'Applications', I.applications, [
    ['where-things-stand', 'Where things stand'],
    ['have-they-replied', 'Have they replied'],
    ['responses-from-your-inbox', 'Inbox replies'],
    ['every-application', 'Every application'],
  ]],
  ['/discover', 'Job sources', I.sources, [
    ['jobs-by-board', 'Jobs by board'],
    ['remote-or-in-an-office', 'Remote or office'],
    ['where-the-jobs-are', 'Where the jobs are'],
    ['visa-sponsorship', 'Visa sponsorship'],
    ['job-boards', 'Board status'],
    ['duplicate-removal', 'Duplicate removal'],
    ['last-search', 'Last search'],
  ]],
  ['/profile', 'My Profile', I.profile, [
    ['your-master-cv', 'Master CV'],
    ['add-skills', 'Add skills'],
    ['skill-gap-finder', 'Skill gaps'],
    ['keyword-coverage', 'Keyword coverage'],
    ['skill-tier-balance', 'Skill balance'],
  ]],
 ]],
]

// A hash link can land before the screen's data has rendered, so retry briefly
// rather than scrolling to an element that does not exist yet.
function ScrollToHash() {
  const { hash, pathname } = useLocation()
  useEffect(() => {
    if (!hash) return
    let tries = 0
    let timer = 0
    const tick = () => {
      const el = document.getElementById(hash.slice(1))
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        return
      }
      if (tries++ < 40) timer = setTimeout(tick, 80)
    }
    tick()
    return () => clearTimeout(timer)
  }, [hash, pathname])
  return null
}

// Topbar search. Matches job title, company, city and country, and finds jobs you
// have already applied to as well - the Jobs list hides those, but you should
// still be able to look one up by name.
function GlobalSearch() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const box = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setResults([]); return }
    let cancelled = false
    const timer = setTimeout(() => {
      api.search(term)
        .then((d) => { if (!cancelled) { setResults(d.results); setCursor(0) } })
        .catch(() => { if (!cancelled) setResults([]) })
    }, 180)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [q])

  useEffect(() => {
    const onDown = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => {
      if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        box.current?.querySelector('input')?.focus()
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const go = (id) => {
    setOpen(false)
    setQ('')
    navigate('/jobs/' + id)
  }

  const onKeyDown = (e) => {
    if (!results.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => (c + 1) % results.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => (c - 1 + results.length) % results.length) }
    else if (e.key === 'Enter') { e.preventDefault(); go(results[cursor].id) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  const showing = open && q.trim().length >= 2

  return (
    <div className="searchbox" ref={box}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
      </svg>
      <input
        type="search"
        value={q}
        placeholder="Search jobs, companies, locations…"
        aria-label="Search jobs, companies and locations"
        onChange={(e) => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      <span className="kbd">Ctrl K</span>

      {showing && (
        <div className="searchdrop">
          {results.length === 0 ? (
            <div className="searchempty">Nothing matches “{q.trim()}”.</div>
          ) : results.map((r, i) => (
            <button
              key={r.id}
              className={'searchrow' + (i === cursor ? ' on' : '')}
              onMouseEnter={() => setCursor(i)}
              onClick={() => go(r.id)}
            >
              <span className="t">{r.title}</span>
              <span className="m">
                {[r.company, r.location, r.posted_age].filter(Boolean).join(' · ')}
              </span>
              {r.applied && <span className="pill p-rust">applied</span>}
              {!r.applied && r.status && <span className="pill p-slate">{r.status}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

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

  const dark = theme === 'dark'

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="brandmark">
            <span className="logo"><img src="/favicon.svg" alt="" width="19" height="19" /></span>
            <span className="nm">
              ApplyPrep
              <span>local build</span>
            </span>
          </div>
        </div>

        {NAV_GROUPS.map(([group, items]) => (
          <div className="navgroup" key={group}>
            <div className="navlabel">{group}</div>
            <nav className="nav">
              {items.map(([to, label, icon, sections]) => (
                <div className="navitem" key={to}>
                  <NavLink to={to} className={({ isActive }) => (isActive ? 'on' : '')}>
                    <Icon paths={icon} />
                    {label}
                    {sections.length > 0 && (
                      <svg className="ch" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="m6 9 6 6 6-6" />
                      </svg>
                    )}
                  </NavLink>
                  {sections.length > 0 && (
                    <div className="subnav">
                      <div className="subnav-inner">
                        {sections.map(([anchor, text]) => (
                          <Link key={anchor} to={to + '#' + anchor}>
                            <span className="dot" />
                            {text}
                          </Link>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </nav>
          </div>
        ))}

        <div className="sidefoot">
          <AiProviderPicker />
          <p style={{ marginTop: 12 }}>
            <span className="dot" />
            local only, port 8756
            <br />
            No AI API key needed
          </p>
        </div>
      </aside>

      <div className="col">
        <div className="topbar">
          <GlobalSearch />
          <span className="statuspill"><span className="dot" />Running locally · port 8756</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 9 }}>
            <button
              className="iconbtn"
              onClick={() => setTheme(dark ? 'light' : 'dark')}
              aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
              title={dark ? 'Light mode' : 'Dark mode'}
            >
              {dark ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="4.2" />
                  <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
                </svg>
              )}
            </button>
          </div>
        </div>

        <main className="main">
          <ScrollToHash />
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
    </div>
  )
}
