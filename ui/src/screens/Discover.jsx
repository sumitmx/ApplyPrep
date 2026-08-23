import { useEffect, useState } from 'react'
import { api } from '../api'
import {
  BarChart, BarList, Card, Donut, Empty, ErrorBox, Legend, Loading, Panel, Pill,
} from '../components'

const MODE_LABELS = { remote: 'Remote', onsite: 'Onsite', unknown: 'Not stated' }
const MODE_TONE = { remote: 'pine', onsite: 'mint', unknown: 'slate' }
const SPONSOR_LABELS = { confirmed: 'Sponsors visas', denied: 'No sponsorship', unknown: 'Not mentioned' }
const SPONSOR_TONE = { confirmed: 'pine', denied: 'rust', unknown: 'amber' }
const LANG_TONE = { English: 'pine', German: 'amber' }

function jobsLink(extra) {
  const q = new URLSearchParams({ gate: '', hours: '', ...extra })
  return '/jobs?' + q.toString()
}

const stamp = (s) => (s || '').replace('T', ' ').slice(0, 16)

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
  const bd = data.breakdown || {}
  const dedup = data.dedup

  const seg = (rows, { labels = {}, tones = {}, href } = {}) =>
    (rows || []).map((r) => ({
      key: r.key,
      label: labels[r.key] || r.key,
      tone: tones[r.key] || 'slate',
      value: r.count,
      href: href ? href(r) : undefined,
    }))

  const workMode = seg(bd.work_mode, {
    labels: MODE_LABELS, tones: MODE_TONE,
    href: (r) => jobsLink(r.key === 'unknown' ? {} : { remote: r.key }),
  })
  const sponsorship = seg(bd.sponsorship, { labels: SPONSOR_LABELS, tones: SPONSOR_TONE })
  const language = seg(bd.language, { tones: LANG_TONE })

  const boardBars = (bd.by_source || []).slice(0, 7).map((r) => ({
    key: r.key, label: r.key, value: r.count, tone: 'pine',
    href: jobsLink({ source: r.key }),
  }))

  const countryRows = (bd.country || []).slice(0, 7).map((r) => ({
    key: r.key, label: r.key === 'unknown' ? 'Not stated' : r.key,
    value: r.count, tone: r.key === 'unknown' ? 'slate' : 'pine',
    href: r.key === 'unknown' ? undefined : jobsLink({ country: r.key }),
  }))

  const activeBoards = data.sources.filter((s) => s.state === 'done').length
  const dupPct = dedup && dedup.total_jobs
    ? Math.round((dedup.duplicate_jobs / dedup.total_jobs) * 100) : 0

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

      <div className="cards">
        <Card
          label="Jobs stored"
          value={dedup ? dedup.total_jobs : '-'}
          sub="across every board"
          tone="pine"
        />
        <Card
          label="Boards checked"
          value={activeBoards + ' of ' + data.sources.length}
          sub={run ? 'last run ' + stamp(run.started_at) : 'never run'}
          tone="mint"
        />
        <Card
          label="Added last run"
          value={run ? run.new_count : '-'}
          sub={run ? 'from ' + run.raw_count + ' listings checked' : 'no run yet'}
          tone="amber"
        />
        <Card
          label="Look like repeats"
          value={dedup ? dedup.duplicate_jobs : '-'}
          sub={dedup ? dupPct + '% of everything stored' : 'not checked yet'}
          tone="rust"
        />
      </div>

      <Panel title="Jobs by board" note="click a bar to see those jobs">
        <div className="pbody">
          <BarChart rows={boardBars} emptyText="Nothing pulled yet" />
        </div>
      </Panel>

      <div className="two">
        <Panel title="Remote or in an office" note="click a slice to see those jobs">
          <div className="pbody chartrow">
            <Donut segments={workMode} />
            <Legend items={workMode} />
          </div>
        </Panel>

        <Panel title="Where the jobs are" note="top countries, click to see those jobs">
          <div className="pbody">
            <BarList rows={countryRows} emptyText="Nothing pulled yet" />
          </div>
        </Panel>
      </div>

      <div className="two">
        <Panel title="Visa sponsorship" note="what the adverts actually say">
          <div className="pbody chartrow">
            <Donut segments={sponsorship} />
            <Legend items={sponsorship} />
          </div>
        </Panel>

        <Panel title="Language needed">
          <div className="pbody chartrow">
            <Donut segments={language} />
            <Legend items={language} />
          </div>
        </Panel>
      </div>

      <Panel
        title="Job boards"
        note={run ? 'last checked ' + stamp(run.started_at) : 'never checked'}
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

      <div className="two">
        <Panel
          title="Duplicate removal"
          note={dedup ? dedup.duplicate_jobs + ' look like repeats' : null}
        >
          <div className="pbody">
            {dedup ? (
              <>
                <div className="dim"><span>Same web address</span><span>{dedup.exact_url}</span></div>
                <div className="dim"><span>Same role, different address</span><span>{dedup.same_role}</span></div>
                <div className="dim"><span>Reworded repost</span><span>{dedup.reworded}</span></div>
                <div className="dim"><span>Groups once combined</span><span>{dedup.groups}</span></div>
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

        <Panel title="Last search">
          <div className="pbody">
            {run ? (
              <>
                <div className="dim"><span>Started</span><span>{stamp(run.started_at)}</span></div>
                <div className="dim"><span>Finished</span><span>{run.finished_at ? stamp(run.finished_at) : 'did not finish'}</span></div>
                <div className="dim"><span>Listings checked</span><span>{run.raw_count}</span></div>
                <div className="dim"><span>New jobs added</span><span>{run.new_count}</span></div>
              </>
            ) : (
              <Empty title="No search has run yet">
                Press Find jobs to check the boards you have switched on.
              </Empty>
            )}
          </div>
        </Panel>
      </div>
    </div>
  )
}
