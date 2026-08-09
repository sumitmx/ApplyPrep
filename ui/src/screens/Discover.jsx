import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading, Panel, Pill } from '../components'

const MODE_LABELS = { remote: 'Remote', onsite: 'Onsite', unknown: 'Not stated' }

function jobsLink(extra) {
  const q = new URLSearchParams({ gate: '', hours: '', ...extra })
  return '/jobs?' + q.toString()
}

function Breakdown({ title, note, rows, href }) {
  const total = rows.reduce((sum, r) => sum + r.count, 0)
  return (
    <Panel title={title} note={note}>
      <div className="pbody">
        {rows.length === 0 ? (
          <Empty title="Nothing pulled yet">Run a pull to populate this.</Empty>
        ) : (
          rows.map((r) => (
            <div className="dim" key={r.value ?? r.key}>
              <span>
                {href ? (
                  <Link to={href(r)} style={{ textDecoration: 'underline' }}>
                    {MODE_LABELS[r.key] || r.key}
                  </Link>
                ) : (
                  MODE_LABELS[r.key] || r.key
                )}
              </span>
              <span>
                {r.count}
                {total ? '  (' + Math.round((r.count / total) * 100) + '%)' : ''}
              </span>
            </div>
          ))
        )}
      </div>
    </Panel>
  )
}

export default function Discover() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [pulling, setPulling] = useState(false)
  const [result, setResult] = useState(null)

  const load = () => api.sources().then(setData).catch(setError)
  useEffect(() => { load() }, [])

  const pull = async () => {
    setPulling(true)
    setResult(null)
    try {
      setResult(await api.pull({}))
      await load()
    } catch (e) {
      setError(e)
    } finally {
      setPulling(false)
    }
  }

  if (error && !data) return <ErrorBox error={error} />
  if (!data) return <Loading />

  const run = data.last_run

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Where jobs come from</h2>
          <p>
            Public job boards that allow this. Nothing behind a login, so no account
            of yours is ever at risk.
          </p>
        </div>
        <button className="btn pri" onClick={pull} disabled={pulling}>
          {pulling ? 'Looking for jobs, up to a minute...' : 'Find jobs'}
        </button>
      </div>

      <ErrorBox error={error} />

      {result && (
        <div className="note">
          <b>Finished.</b> Checked {result.raw} listings, added {result.new} new ones.
        </div>
      )}

      <Panel
        title="Job boards"
        note={run ? 'last checked ' + (run.started_at || '').replace('T', ' ').slice(0, 16) : 'never checked'}
      >
        <div className="pbody">
          {data.sources.length === 0 ? (
            <Empty title="No job boards have been checked yet">
              Press Find jobs to search the boards switched on in your settings.
            </Empty>
          ) : (
            data.sources.map((s) => (
              <div className="srcrow" key={s.name}>
                <span className="nm">{s.name}</span>
                <span className="ct">{s.detail || 'no data'}</span>
                <Pill tone={s.state === 'done' ? 'pine' : 'slate'}>{s.state}</Pill>
              </div>
            ))
          )}
        </div>
      </Panel>

      {data.breakdown && (
        <div className="two">
          <Breakdown
            title="Remote or in an office"
            note="click a row to see those jobs"
            rows={data.breakdown.work_mode}
            href={(r) => jobsLink(r.key === 'unknown' ? {} : { remote: r.key })}
          />
          <Breakdown
            title="Where the jobs are"
            note="click a row to see those jobs"
            rows={data.breakdown.country}
            href={(r) => jobsLink(r.key === 'unknown' ? {} : { country: r.key })}
          />
        </div>
      )}

      {data.breakdown && (
        <div className="two">
          <Breakdown title="Visa sponsorship" rows={data.breakdown.sponsorship} />
          <Breakdown title="Language needed" rows={data.breakdown.language} />
        </div>
      )}

      <Panel
        title="Duplicate removal"
        note={data.dedup ? data.dedup.duplicate_jobs + ' look like repeats' : null}
      >
        <div className="pbody">
          {data.dedup ? (
            <>
              <div className="dim">
                <span>Same web address</span><span>{data.dedup.exact_url}</span>
              </div>
              <div className="dim">
                <span>Same role, different address</span><span>{data.dedup.same_role}</span>
              </div>
              <div className="dim">
                <span>Reworded repost</span><span>{data.dedup.reworded}</span>
              </div>
              <div className="dim">
                <span>Groups once combined</span><span>{data.dedup.groups}</span>
              </div>
              <p className="muted" style={{ marginTop: 11 }}>
                The same job often appears on several boards. Nothing is merged
                automatically. Run <code>cli.py dedup</code> to see exactly what would
                be combined, then <code>cli.py dedup --apply</code> to do it.
              </p>
            </>
          ) : (
            <Empty title="Nothing checked yet">
              Duplicate checking runs against the jobs already in your database.
            </Empty>
          )}
        </div>
      </Panel>

      {run && (
        <Panel title="Last search">
          <div className="pbody">
            <div className="dim"><span>Started</span><span>{(run.started_at || '').replace('T', ' ').slice(0, 16)}</span></div>
            <div className="dim"><span>Finished</span><span>{run.finished_at ? run.finished_at.replace('T', ' ').slice(0, 16) : 'did not finish'}</span></div>
            <div className="dim"><span>Listings checked</span><span>{run.raw_count}</span></div>
            <div className="dim"><span>New jobs added</span><span>{run.new_count}</span></div>
          </div>
        </Panel>
      )}
    </div>
  )
}
