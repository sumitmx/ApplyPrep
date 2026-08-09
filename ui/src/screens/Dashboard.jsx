import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Bar, Card, Empty, ErrorBox, Loading, Panel } from '../components'

const CARD_LINKS = {
  'New postings': '/jobs?gate=&hours=48',
  'Worth a look': '/jobs?gate=passed&hours=48',
  'Not rated yet': '/jobs?gate=passed&hours=48',
  'You saved': '/jobs?gate=saved',
  'Applied this month': '/applications',
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [pulling, setPulling] = useState(false)
  const [result, setResult] = useState(null)
  const navigate = useNavigate()

  const load = () => api.dashboard().then(setData).catch(setError)
  useEffect(() => { load() }, [])

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

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Overview</h2>
          <p>
            Everything here is stored on your laptop. Nothing on this page uses AI.
            The cards below show the last {data.window_hours} hours, not everything
            you have ever found. <b>New postings</b> is everything checked, before
            filtering for fit; <b>Worth a look</b> is what actually shows up in Jobs.
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
    </div>
  )
}
