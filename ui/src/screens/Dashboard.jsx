import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Bar, BarList, Card, Donut, Empty, ErrorBox, Legend, Loading, Panel } from '../components'

function periodLabel(hours) {
  if (hours % 24 === 0) {
    const days = hours / 24
    return days + (days === 1 ? ' day' : ' days')
  }
  return hours + (hours === 1 ? ' hour' : ' hours')
}

const CARD_LINKS = {
  'New postings': '/jobs?gate=&hours=168',
  'Worth a look': '/jobs?gate=passed&hours=',
  'Not rated yet': '/jobs?gate=unrated',
  'You saved': '/jobs?gate=saved',
  'Applied this month': '/applications',
}

const FUNNEL_TONE = {
  drafting: 'slate', applied: 'amber', screening: 'amber',
  interview: 'mint', offer: 'pine', rejected: 'rust',
}

const FUNNEL_LABEL = {
  drafting: 'Drafting', applied: 'Applied', screening: 'Screening',
  interview: 'Interview', offer: 'Offer', rejected: 'Rejected',
}

const TIER_ROWS = [
  { key: 'core', label: 'Strongest skills', tone: 'pine' },
  { key: 'working', label: 'Worked with', tone: 'mint' },
  { key: 'familiar', label: 'Some exposure', tone: 'slate' },
]

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [pulling, setPulling] = useState(false)
  const [result, setResult] = useState(null)
  const [applications, setApplications] = useState(null)
  const [sources, setSources] = useState(null)
  const [masterCv, setMasterCv] = useState(null)
  const navigate = useNavigate()

  const load = () => api.dashboard().then(setData).catch(setError)
  useEffect(() => {
    load()
    api.applications().then(setApplications).catch(() => setApplications(null))
    api.sources().then(setSources).catch(() => setSources(null))
    api.masterCv().then(setMasterCv).catch(() => setMasterCv(null))
  }, [])

  const pull = async () => {
    setPulling(true)
    setResult(null)
    setError(null)
    try {
      const summary = await api.pull({})
      setResult(summary)
      await load()
      navigate('/jobs?gate=passed&hours=48')
    } catch (e) {
      setError(e)
    } finally {
      setPulling(false)
    }
  }

  if (error && !data) return <ErrorBox error={error} />
  if (!data) return <Loading />

  const bands = data.response_by_band || []
  const noApplications = bands.every((b) => b.sent === 0)

  const bandSegments = (data.bands || []).map((b) => ({
    key: b.key, label: b.label, tone: b.tone,
    value: (data.band_counts || {})[b.key] || 0,
    href: '/jobs?gate=passed&hours=&band=' + b.key,
  }))

  const funnelRows = (applications ? applications.funnel : []).map((f) => ({
    key: f.key, label: FUNNEL_LABEL[f.key] || f.key, tone: FUNNEL_TONE[f.key],
    value: f.value, href: '/applications',
  }))

  const sourceRows = (sources && sources.breakdown ? sources.breakdown.by_source : [])
    .slice(0, 6)
    .map((s) => ({
      key: s.key, label: s.key, tone: 'pine', value: s.count,
      href: '/jobs?source=' + encodeURIComponent(s.key) + '&gate=&hours=',
    }))

  const tierRows = TIER_ROWS.map((t) => ({
    ...t, value: masterCv && masterCv.tiers ? (masterCv.tiers[t.key] || []).length : 0,
    href: '/my-cv',
  }))

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Overview</h2>
          <p>
            Everything here is stored on your laptop. Nothing on this page uses AI.
            <b>New postings</b> is everything posted in the last{' '}
            {periodLabel(data.window_hours)}, before filtering for fit. The other
            cards show your current totals, not just recent activity.{' '}
            <b>Worth a look</b> is what actually shows up in Jobs.
          </p>
        </div>
        <button className="btn pri" onClick={pull} disabled={pulling}>
          {pulling ? 'Looking for jobs, up to a minute...' : 'Find jobs'}
        </button>
      </div>

      <ErrorBox error={error} />

      {result && (
        <div className="note">
          <b>Finished.</b> Checked {result.raw} listings and added {result.new} new
          ones. The rest were duplicates you already had.
        </div>
      )}

      {data.last_run && (
        <p className="muted" style={{ marginBottom: 11 }}>
          Last pull {(data.last_run.finished_at || data.last_run.started_at || '')
            .replace('T', ' ').slice(0, 16)}
          {data.last_run.finished_at ? '' : ', did not finish'}, added{' '}
          {data.last_run.new_count} new job(s).
        </p>
      )}

      <div className="cards">
        {data.cards.map((c) => {
          const card = <Card label={c.key} value={c.value} sub={c.sub} tone={c.tone} />
          const href = CARD_LINKS[c.key]
          return href ? (
            <Link key={c.key} to={href} className="card-link">
              {card}
            </Link>
          ) : (
            <div key={c.key}>{card}</div>
          )
        })}
      </div>

      <div className="two">
        <Panel title="How often you hear back" note="by how good the match was">
          <div className="pbody">
            {noApplications ? (
              <Empty title="You have not applied to anything yet">
                Once you start applying, this shows whether the strong matches
                really do get more replies than the weaker ones. If both lines end
                up the same, the ratings are not telling you anything useful.
              </Empty>
            ) : (
              bands.map((b) => (
                <div key={b.label}>
                  <div className="dim">
                    <span>{b.label}</span>
                    <span>
                      {b.rate === null
                        ? 'none sent yet'
                        : b.replied + ' replies out of ' + b.sent + ' sent'}
                    </span>
                  </div>
                  <Bar value={b.rate || 0} tone={b.rate !== null && b.rate < 15 ? 'amber' : null} />
                </div>
              ))
            )}
          </div>
        </Panel>

        <Panel title="What to do next">
          <div className="pbody">
            {data.next_actions.map((a, i) => (
              <div className="check" key={i}>
                <span>{a.text}</span>
                <span className={a.tone === 'no' ? 'no' : 'ok'}>{a.state}</span>
              </div>
            ))}
            <p className="muted" style={{ marginTop: 11 }}>
              Rating jobs and writing CVs happens in Claude chat, not on this page.{' '}
              <Link to="/jobs" style={{ textDecoration: 'underline' }}>
                See the jobs worth a look
              </Link>
              .
            </p>
          </div>
        </Panel>
      </div>

      <div className="two">
        <Panel title="Jobs by fit" note="click a band to see those jobs">
          <div className="pbody chartrow">
            <Donut segments={bandSegments} />
            <Legend items={bandSegments} />
          </div>
        </Panel>

        <Panel title="Application pipeline" note="click to open Applications">
          <div className="pbody">
            {applications ? (
              <BarList rows={funnelRows} emptyText="Nothing tracked yet" />
            ) : (
              <Loading />
            )}
          </div>
        </Panel>
      </div>

      <div className="two">
        <Panel title="Where jobs come from" note="top boards, click to see those jobs">
          <div className="pbody">
            {sources ? (
              <BarList rows={sourceRows} emptyText="Nothing pulled yet" />
            ) : (
              <Loading />
            )}
          </div>
        </Panel>

        <Panel title="My CV coverage" note="click to open My CV">
          <div className="pbody">
            {masterCv ? (
              masterCv.available ? (
                <BarList rows={tierRows} />
              ) : (
                <Empty
                  title="No master CV set up yet"
                  actions={<Link className="btn sm" to="/my-cv">Set it up</Link>}
                >
                  Add your CV so tailoring and this breakdown have something to work with.
                </Empty>
              )
            ) : (
              <Loading />
            )}
          </div>
        </Panel>
      </div>
    </div>
  )
}
