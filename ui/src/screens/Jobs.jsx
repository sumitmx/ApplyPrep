import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading, Panel, PasteJobModal, Pill, Score, Toast }
  from '../components'

const GATES = [
  ['passed', 'worth a look'],
  ['saved', 'saved jobs'],
  ['applied', 'applied'],
  ['rejected', 'hidden as not relevant'],
  ['unrated', 'not rated yet'],
  ['', 'everything'],
]

const WINDOWS = [
  ['48', 'listed in 48 hours'],
  ['24', 'listed in 24 hours'],
  ['168', 'listed in 7 days'],
  ['', 'any time'],
]

const MODES = [
  ['', 'anywhere'],
  ['remote', 'remote only'],
  ['onsite', 'onsite only'],
]

const EMPLOYERS = [
  ['', 'any employer'],
  ['false', 'direct only'],
  ['true', 'agency only'],
]

function ageLabel(job) {
  if (job.posted_age === job.found_age) return job.posted_age
  if (job.posted_age && job.found_age) {
    return 'posted ' + job.posted_age + ', found ' + job.found_age
  }
  return job.posted_age || job.found_age
}

function pageWindow(current, total) {
  const pages = new Set([1, total, current, current - 1, current + 1])
  return [...pages].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b)
}

function Pager({ page, totalPages, onGo }) {
  if (totalPages <= 1) return null
  const pages = pageWindow(page, totalPages)
  let prev = 0
  return (
    <div className="filters" style={{ justifyContent: 'center' }}>
      <button className="btn sm" disabled={page <= 1} onClick={() => onGo(page - 1)}>
        Previous
      </button>
      {pages.map((n) => {
        const gap = n - prev > 1
        prev = n
        return (
          <span key={n} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {gap && <span className="muted">...</span>}
            <button
              className={'btn sm' + (n === page ? ' pri' : '')}
              onClick={() => onGo(n)}
              disabled={n === page}
            >
              {n}
            </button>
          </span>
        )
      })}
      <button className="btn sm" disabled={page >= totalPages} onClick={() => onGo(page + 1)}>
        Next
      </button>
      <span className="muted">page {page} of {totalPages}</span>
    </div>
  )
}

export default function Jobs() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [toast, setToast] = useState(null)
  const [websites, setWebsites] = useState([])
  const [selected, setSelected] = useState(() => new Set())
  const [rating, setRating] = useState(null)
  const [previewJob, setPreviewJob] = useState(null)
  const [pasting, setPasting] = useState(false)
  const previewCloseTimer = useRef(null)
  const navigate = useNavigate()

  const PAGE_SIZE = 25

  const openPreview = (id) => {
    if (previewCloseTimer.current) {
      clearTimeout(previewCloseTimer.current)
      previewCloseTimer.current = null
    }
    setPreviewJob(id)
  }

  const scheduleClosePreview = () => {
    previewCloseTimer.current = setTimeout(() => setPreviewJob(null), 250)
  }

  useEffect(() => () => {
    if (previewCloseTimer.current) clearTimeout(previewCloseTimer.current)
  }, [])

  const gate = params.get('gate') ?? 'passed'
  const hours = params.get('hours') ?? '48'
  const country = params.get('country') ?? ''
  const minFit = params.get('min_fit') ?? ''
  const remote = params.get('remote') ?? ''
  const agency = params.get('agency') ?? ''
  const source = params.get('source') ?? ''
  const band = params.get('band') ?? ''
  const page = Math.max(1, parseInt(params.get('page'), 10) || 1)

  const onlySaved = gate === 'saved'
  const onlyApplied = gate === 'applied'
  const onlyUnrated = gate === 'unrated'

  useEffect(() => {
    api.sources().then((d) => setWebsites(d.sources.map((s) => s.name))).catch(() => {})
  }, [])

  const load = () => {
    setData(null)
    api
      .jobs({
        gate: (onlySaved || onlyApplied) ? '' : (onlyUnrated ? 'passed' : gate),
        status: onlySaved ? 'shortlisted' : '',
        applied: onlyApplied ? '1' : '',
        hours: (onlySaved || onlyApplied || onlyUnrated) ? '' : hours,
        country,
        min_fit: minFit,
        remote,
        agency,
        source,
        band: onlyUnrated ? 'unrated' : band,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      })
      .then(setData)
      .catch(setError)
  }

  useEffect(() => { load() }, [gate, hours, country, minFit, remote, agency, source, band, page])
  useEffect(() => { setSelected(new Set()) }, [gate, hours, country, minFit, remote, agency, source, band, page])

  const set = (key, value) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    next.delete('page')
    if (key !== 'band') next.delete('band')
    setParams(next)
  }

  const clearBand = () => {
    const next = new URLSearchParams(params)
    next.delete('band')
    next.delete('page')
    setParams(next)
  }

  const goToPage = (n) => {
    const next = new URLSearchParams(params)
    if (n <= 1) next.delete('page')
    else next.set('page', String(n))
    setParams(next)
  }

  const mark = async (event, job, action) => {
    event.preventDefault()
    event.stopPropagation()
    setBusy(job.id)
    try {
      await api.mark(job.id, action)
      const messages = {
        shortlist: '"' + job.title + '" saved. Find it again under Show, saved jobs.',
        reset: '"' + job.title + '" taken off your saved list.',
        hide: '"' + job.title + '" hidden. It stays in the database and can be brought back.',
      }
      setToast({
        tone: action === 'shortlist' ? 'pine' : 'rust',
        message: messages[action] || 'Done.',
      })
      load()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  const toggleSelected = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAllUnrated = () => {
    if (!data) return
    setSelected(new Set(data.jobs.filter((j) => !j.scored).map((j) => j.id)))
  }

  const clearSelected = () => setSelected(new Set())

  const rateSelected = async () => {
    const ids = [...selected]
    if (!ids.length) return
    let failed = 0
    setRating({ done: 0, total: ids.length, failed: 0 })
    for (let i = 0; i < ids.length; i++) {
      try {
        await api.rate(ids[i])
      } catch {
        failed += 1
      }
      setRating({ done: i + 1, total: ids.length, failed })
    }
    setRating(null)
    setSelected(new Set())
    load()
    setToast({
      tone: failed ? 'rust' : 'pine',
      message: 'Rated ' + (ids.length - failed) + ' of ' + ids.length + ' job(s).' +
        (failed ? ' ' + failed + ' failed.' : ''),
    })
  }

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Jobs</h2>
          <p>
            Two numbers, never averaged. <b>Match</b> is how well the job suits you.
            <b> Chances</b> is how realistic it is to actually get it, given visa
            sponsorship, language and how old the ad is.
          </p>
        </div>
        <div className="sheadside">
          <button className="btn pri" type="button" onClick={() => setPasting(true)}>
            Paste a job description
          </button>
          {data && (
            <span className="countpill">
              {data.total === 0
                ? '0 jobs'
                : 'showing ' + (data.offset + 1) + '-' + (data.offset + data.jobs.length) +
                  ' of ' + data.total}
            </span>
          )}
        </div>
      </div>

      {pasting && (
        <PasteJobModal
          onClose={() => setPasting(false)}
          onCreated={(res) => {
            setPasting(false)
            navigate('/jobs/' + res.job_id)
          }}
        />
      )}

      <div className="filters">
        <label htmlFor="f-gate">Show</label>
        <select id="f-gate" value={gate} onChange={(e) => set('gate', e.target.value)}>
          {GATES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <label htmlFor="f-window">When</label>
        <select id="f-window" value={hours} onChange={(e) => set('hours', e.target.value)}>
          {WINDOWS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <label htmlFor="f-source">Website</label>
        <select id="f-source" value={source} onChange={(e) => set('source', e.target.value)}>
          <option value="">any website</option>
          {websites.map((w) => <option key={w} value={w}>{w}</option>)}
        </select>

        <label htmlFor="f-country">Country</label>
        <select id="f-country" value={country} onChange={(e) => set('country', e.target.value)}>
          <option value="">any</option>
          <option value="DE">DE</option>
          <option value="NL">NL</option>
          <option value="GB">GB</option>
          <option value="AT">AT</option>
          <option value="CH">CH</option>
        </select>

        <label htmlFor="f-mode">Work mode</label>
        <select id="f-mode" value={remote} onChange={(e) => set('remote', e.target.value)}>
          {MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <label htmlFor="f-employer">Employer</label>
        <select id="f-employer" value={agency} onChange={(e) => set('agency', e.target.value)}>
          {EMPLOYERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <label htmlFor="f-fit">Min match</label>
        <input
          id="f-fit"
          type="number"
          min="0"
          max="100"
          style={{ width: 74 }}
          value={minFit}
          onChange={(e) => set('min_fit', e.target.value)}
        />

        {[...params.keys()].length > 0 && (
          <button className="btn sm" onClick={() => setParams(new URLSearchParams())}>
            Reset
          </button>
        )}
      </div>

      {band && (
        <div className="filters">
          <Pill tone="amber">
            Only: {(data && data.bands.find((b) => b.key === band)?.label) || band}
          </Pill>
          <button className="btn sm" onClick={clearBand}>
            Show all bands
          </button>
        </div>
      )}

      <div className="filters">
        <button className="btn sm" onClick={selectAllUnrated} disabled={!data || !!rating}>
          Select all unrated
        </button>
        {selected.size > 0 && (
          <button className="btn sm" onClick={clearSelected} disabled={!!rating}>
            Clear selection
          </button>
        )}
        <button
          className="btn pri sm"
          onClick={rateSelected}
          disabled={selected.size === 0 || !!rating}
        >
          {rating
            ? 'Rating ' + rating.done + ' of ' + rating.total + '...'
            : 'Rate now (' + selected.size + ')'}
        </button>
        {selected.size > 0 && !rating && (
          <span className="muted">
            {selected.size} job{selected.size === 1 ? '' : 's'} selected
          </span>
        )}
      </div>

      <ErrorBox error={error} />

      {data && data.total > 0 && (
        <Pager
          page={page}
          totalPages={Math.max(1, Math.ceil(data.total / PAGE_SIZE))}
          onGo={goToPage}
        />
      )}

      {!data ? (
        <Loading />
      ) : data.jobs.length === 0 ? (
        <Panel title="0 jobs">
          {onlySaved ? (
            <Empty title="You have not saved any job yet">
              Press Save on any job and it will appear here.
            </Empty>
          ) : (
            <Empty title="Nothing here with those filters">
              Try a longer time range, or set Show to everything. If you have not
              searched yet, press Find jobs on the overview page.
            </Empty>
          )}
        </Panel>
      ) : (
        data.bands.map((bandInfo) => {
          const rows = data.jobs.filter((j) => j.band === bandInfo.key)
          if (!rows.length) return null
          return (
            <div key={bandInfo.key}>
              <div className="bandhead">
                <h3 style={{ color: 'var(--' + bandInfo.tone + ')' }}>{bandInfo.label}</h3>
                <span className="n">{rows.length}</span>
                <p>{bandInfo.blurb}</p>
              </div>
              <div className={'panel band-' + bandInfo.key}>
                {rows.map((job) => (
                  <div className={'jobwrap' + (job.saved ? ' saved' : '')} key={job.id}>
                    {job.requirements && (
                      <div
                        className="preview"
                        style={{ display: previewJob === job.id ? 'block' : 'none' }}
                        onMouseEnter={() => openPreview(job.id)}
                        onMouseLeave={scheduleClosePreview}
                      >
                        <b>{job.title}</b>
                        {!job.requirements_found && (
                          <em className="fallback-note">
                            No separate requirements heading was found, showing the
                            full posting instead.
                          </em>
                        )}
                        {job.requirements}
                      </div>
                    )}
                    <input
                      type="checkbox"
                      checked={selected.has(job.id)}
                      onChange={() => toggleSelected(job.id)}
                      disabled={!!rating}
                      style={{ marginLeft: 16, flexShrink: 0 }}
                      aria-label={'Select ' + job.title}
                    />
                    <Link className="job" to={'/jobs/' + job.id}>
                      <div className="body">
                        <div
                          className="t"
                          onMouseEnter={() => openPreview(job.id)}
                          onMouseLeave={scheduleClosePreview}
                        >
                          {job.title}
                          {job.websites && job.websites[0] && (
                            <span className="pill p-slate" style={{ marginLeft: 8 }}>
                              {job.websites[0]}
                            </span>
                          )}
                          {job.applied && (
                            <span className="pill p-rust" style={{ marginLeft: 6 }}>
                              Applied
                            </span>
                          )}
                        </div>
                        <div className="c">
                          {[job.company, [job.city, job.country].filter(Boolean).join(', '),
                            ageLabel(job)].filter(Boolean).join(' · ')}
                        </div>
                        <div className="tags">
                          {job.saved && <Pill tone="pine">saved</Pill>}
                          {job.badges.map((b, i) => (
                            <Pill key={i} tone={b.tone} strong={b.strong}>{b.text}</Pill>
                          ))}
                        </div>
                      </div>
                    </Link>
                    {job.url && (
                      <a
                        className="btn sm"
                        href={job.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                      >
                        Open posting
                      </a>
                    )}
                    <div className="scores">
                      <Score value={job.scores.fit} label="match" />
                      <Score value={job.scores.reach} label="chances" />
                      <Score value={job.scores.ats_score} label="cv score*" estimated />
                      <Score value={job.scores.offer_probability} label="offer guess*" estimated />
                    </div>
                    <div className="rowacts">
                      <button
                        className={'btn sm' + (job.saved ? ' pri' : '')}
                        disabled={busy === job.id}
                        onClick={(e) => mark(e, job, job.saved ? 'reset' : 'shortlist')}
                      >
                        {job.saved ? 'Saved' : 'Save'}
                      </button>
                      <button
                        className="btn sm"
                        disabled={busy === job.id}
                        onClick={(e) => mark(e, job, 'hide')}
                      >
                        Not interested
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })
      )}

      {data && data.total > 0 && (
        <Pager
          page={page}
          totalPages={Math.max(1, Math.ceil(data.total / PAGE_SIZE))}
          onGo={goToPage}
        />
      )}

      <Toast
        message={toast && toast.message}
        tone={toast && toast.tone}
        onClose={() => setToast(null)}
      />

      <p className="muted">
        * <b>CV score</b> and <b>offer guess</b> are Claude's guesses, not real numbers.
        Recruiting software does not actually give your CV a score, and nothing in a
        job advert can predict whether you will get an offer. Treat them as a
        starting point, not a fact. Match and chances are kept separate on purpose,
        because a job can suit you perfectly and still be out of reach.
      </p>
    </div>
  )
}
