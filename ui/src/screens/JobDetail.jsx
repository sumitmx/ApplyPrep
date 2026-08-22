import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { AskAIChat, Bar, Empty, ErrorBox, Loading, Panel, Pill, Score } from '../components'

const TIER_LABELS = {
  core: 'Your strongest skills',
  working: 'You have worked with these',
  familiar: 'You have some exposure',
}

export default function JobDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [docs, setDocs] = useState(null)
  const [error, setError] = useState(null)
  const [rating, setRating] = useState(false)
  const [rateError, setRateError] = useState(null)
  const [allSkills, setAllSkills] = useState(null)
  const [showSkills, setShowSkills] = useState(false)
  const [estimating, setEstimating] = useState(null)
  const [estimateError, setEstimateError] = useState(null)
  const [tracking, setTracking] = useState(false)
  const [showChat, setShowChat] = useState(false)
  const [openedPosting, setOpenedPosting] = useState(
    () => localStorage.getItem('opened_posting_' + id) === '1'
  )

  const load = () => {
    setJob(null)
    setDocs(null)
    setRateError(null)
    setEstimateError(null)
    api.job(id).then(setJob).catch(setError)
    api.documents(id).then(setDocs).catch(() => setDocs(null))
  }
  useEffect(() => { load() }, [id])
  useEffect(() => {
    setOpenedPosting(localStorage.getItem('opened_posting_' + id) === '1')
  }, [id])

  const toggleSkills = async () => {
    if (!showSkills && !allSkills) {
      try {
        setAllSkills(await api.masterCv())
      } catch {
        setAllSkills({ available: false, tiers: {} })
      }
    }
    setShowSkills(!showSkills)
  }

  const rate = async () => {
    setRating(true)
    setRateError(null)
    try {
      await api.rate(id)
      setJob(await api.job(id))
    } catch (e) {
      setRateError(e)
    } finally {
      setRating(false)
    }
  }

  const getEstimate = async (kind) => {
    setEstimating(kind)
    setEstimateError(null)
    try {
      await api.estimate(id, kind)
      setJob(await api.job(id))
    } catch (e) {
      setEstimateError(e)
    } finally {
      setEstimating(null)
    }
  }

  const mark = async (action) => {
    try {
      await api.mark(id, action)
      if (action === 'hide') {
        const neighbours = job.neighbours || {}
        const target = neighbours.next || neighbours.previous
        navigate(target ? '/jobs/' + target : '/jobs')
        return
      }
      load()
    } catch (e) {
      setError(e)
    }
  }

  const startTracking = async () => {
    setTracking(true)
    try {
      await api.startApplication(id)
      setJob(await api.job(id))
    } catch (e) {
      setError(e)
    } finally {
      setTracking(false)
    }
  }

  if (error) return <ErrorBox error={error} />
  if (!job) return <Loading />

  const dims = job.dimensions
  const nb = job.neighbours || {}
  const matchedTiers = job.skill_match
    ? Object.entries(TIER_LABELS)
        .map(([tier, label]) => [tier, label, job.skill_match[tier] || []])
        .filter(([, , items]) => items.length > 0)
    : []
  const metaParts = [
    [job.city, job.country].filter(Boolean).join(', '),
    'job ' + job.id,
    job.posted_age,
  ].filter(Boolean)

  return (
    <div>
      <div className="shead">
        <div>
          <h2>
            {job.title}
            {job.applied && (
              <span className="pill p-rust" style={{ marginLeft: 10 }}>Applied</span>
            )}
          </h2>
          <p>
            {job.company && (
              <b style={{ fontSize: '1.15em' }}>{job.company}</b>
            )}
            {job.company && metaParts.length > 0 ? ' · ' : ''}
            {metaParts.join(' · ')}
          </p>
          <div className="tags" style={{ marginTop: 8 }}>
            {job.badges.map((b, i) => (
              <Pill key={i} tone={b.tone} strong={b.strong}>{b.text}</Pill>
            ))}
          </div>
        </div>
        <div className="btns" style={{ marginTop: 0 }}>
          <button className="btn" disabled={!nb.previous}
            onClick={() => navigate('/jobs/' + nb.previous)}>Previous</button>
          <button className="btn" disabled={!nb.next}
            onClick={() => navigate('/jobs/' + nb.next)}>Next</button>
          <button className="btn pri" onClick={() => setShowChat(true)}>Ask AI</button>
          {job.url && (
            <a
              className="btn"
              href={job.url}
              target="_blank"
              rel="noreferrer"
              onClick={() => {
                localStorage.setItem('opened_posting_' + id, '1')
                setOpenedPosting(true)
              }}
            >
              Open posting
            </a>
          )}
        </div>
      </div>

      <div className="btns" style={{ marginBottom: 14 }}>
        <button className="btn" onClick={rate} disabled={rating}>
          {rating ? 'Rating...' : (job.scored ? 'Rate again' : 'Rate now')}
        </button>
        {job.url && !openedPosting ? (
          <button
            className="btn pri"
            disabled
            title="Open the posting at least once before tailoring your CV"
          >
            Tailor my CV
          </button>
        ) : (
          <Link className="btn pri" to={'/jobs/' + job.id + '/tailor'}>Tailor my CV</Link>
        )}
        <Link className="btn" to={'/jobs/' + job.id + '/letter'}>Write cover letter</Link>
        <button
          className={'btn' + (job.status === 'shortlisted' ? ' pri' : '')}
          onClick={() => mark(job.status === 'shortlisted' ? 'reset' : 'shortlist')}
        >
          {job.status === 'shortlisted' ? 'Saved' : 'Save this one'}
        </button>
        <button className="btn" onClick={() => mark('hide')}>Not interested</button>
        <Link className="btn" to="/jobs">Back to all jobs</Link>
      </div>

      <div className="two">
        <Panel
          title="How well it matches you"
          note={job.scores.fit === null ? 'not rated yet' : String(job.scores.fit) + ' out of 100'}
        >
          <div className="pbody">
            {rateError && (
              <p className="no" style={{ marginBottom: 11 }}>
                Could not rate it: {rateError.message}
              </p>
            )}
            {!job.scored ? (
              <Empty
                title="Not rated yet"
                actions={
                  <button className="btn pri" onClick={rate} disabled={rating}>
                    {rating ? 'Rating, this takes a moment...' : 'Rate now'}
                  </button>
                }
              >
                Rate it here and now, or ask Claude in chat to work through your
                unrated jobs in batches. Only the match score is written here.
                Your chances are always worked out in code.
              </Empty>
            ) : dims ? (
              Object.entries(dims).map(([name, value]) => (
                <div key={name}>
                  <div className="dim">
                    <span>{name}</span>
                    <span>{value}</span>
                  </div>
                  <Bar value={typeof value === 'number' ? value : 0} max={30} />
                </div>
              ))
            ) : (
              <p className="muted">Rated, but no breakdown was saved.</p>
            )}
          </div>
        </Panel>

        <Panel
          title="Your chances of getting it"
          note={job.scores.reach === null ? 'not worked out yet' : String(job.scores.reach) + ' out of 100'}
        >
          <div className="pbody">
            {(job.reach_facts || []).map((f) => (
              <div className="check" key={f.key}>
                <span>{f.label}</span>
                <span className={f.good ? 'ok' : 'no'}>
                  {f.value}
                  {f.points !== null && f.max
                    ? ' (' + f.points + ' of ' + f.max + ')'
                    : ''}
                </span>
              </div>
            ))}
            {!job.reach_facts && (
              <Empty title="Not worked out yet">
                Run <code>cli.py reach</code> to work this out from the advert.
              </Empty>
            )}
            <p className="muted" style={{ marginTop: 11 }}>
              These are facts taken straight from the advert, not opinions, and the
              number is worked out in code rather than guessed.
              {job.scores.reach_base !== null && job.scores.reach_base !== undefined
                ? ' The five lines under the visa line come to ' +
                  job.scores.reach_base +
                  ' out of 100. Because you need sponsorship, that is then multiplied by ' +
                  job.scores.reach_factor +
                  ', giving ' + job.scores.reach + '.'
                : ''}
            </p>
          </div>
        </Panel>
      </div>

      <Panel title="The job posting" note="as written by the company">
        <div className="pbody">
          {job.description ? (
            <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{job.description}</p>
          ) : (
            <Empty title="No description was stored for this posting">
              Open the posting on the company site to read the full requirements.
            </Empty>
          )}
        </div>
      </Panel>

      <Panel title="Claude's guesses" note="not real numbers">
        <div className="pbody">
          {estimateError && (
            <p className="no" style={{ marginBottom: 11 }}>
              Could not get that guess: {estimateError.message}
            </p>
          )}
          <div className="scores" style={{ justifyContent: 'flex-start', textAlign: 'left', gap: 26 }}>
            <div>
              <Score value={job.scores.ats_score} label="cv score*" estimated />
              <button
                className="btn sm"
                style={{ marginTop: 8 }}
                disabled={estimating === 'ats' || !job.scored}
                title={!job.scored ? 'Rate the job first' : undefined}
                onClick={() => getEstimate('ats')}
              >
                {estimating === 'ats' ? 'Working...' : (job.scores.ats_score === null ? 'Get cv score' : 'Get again')}
              </button>
            </div>
            <div>
              <Score value={job.scores.offer_probability} label="offer guess*" estimated />
              <button
                className="btn sm"
                style={{ marginTop: 8 }}
                disabled={estimating === 'offer' || !job.scored}
                title={!job.scored ? 'Rate the job first' : undefined}
                onClick={() => getEstimate('offer')}
              >
                {estimating === 'offer' ? 'Working...' : (job.scores.offer_probability === null ? 'Get offer guess' : 'Get again')}
              </button>
            </div>
          </div>
          <p className="muted" style={{ marginTop: 13 }}>
            * Both of these are Claude's opinion, written on request. Recruiting
            software does not give your CV a score you can look up, and nothing in a
            job advert can tell you whether you will get an offer. Useful as a nudge,
            not as evidence. They only fill in on their own for jobs that are both a
            strong match and realistically reachable; the buttons above get them for
            any job you have already rated, any time you want.
            {job.scores.note ? ' Note: ' + job.scores.note : ''}
          </p>
        </div>
      </Panel>

      <Panel title="Your skills against this job" note="checked against your CV">
        <div className="pbody">
          {!job.skill_match ? (
            <Empty
              title="Your CV is not set up yet"
              actions={
                <button className="btn" onClick={toggleSkills}>
                  {showSkills ? 'Hide my skills' : 'Show my skills'}
                </button>
              }
            >
              Once you add your CV, this panel shows which of your skills this job
              asks for, and tells apart things you have never done from things you
              have done but never wrote down.
            </Empty>
          ) : matchedTiers.length === 0 ? (
            <Empty
              title="None of your skills are named in this advert"
              actions={
                <button className="btn" onClick={toggleSkills}>
                  {showSkills ? 'Hide my skills' : 'Show my skills'}
                </button>
              }
            >
              The advert does not spell out any tool or language that is on your CV.
              That usually means it is written in business terms rather than
              technical ones, not that you are a poor match.
            </Empty>
          ) : (
            <>
              {matchedTiers.map(([tier, label, items]) => (
                <div key={tier}>
                  <div className="tierlab">{label}</div>
                  {items.map((s) => (
                    <span className="skill" key={s.name}>
                      <b>{s.name}</b> {s.context && <em>{s.context}</em>}
                    </span>
                  ))}
                </div>
              ))}
              <div className="btns">
                <button className="btn sm" onClick={toggleSkills}>
                  {showSkills ? 'Hide my skills' : 'Show my skills'}
                </button>
              </div>
            </>
          )}

          {showSkills && allSkills && (
            <div style={{ marginTop: 13, borderTop: '1px solid var(--line)', paddingTop: 13 }}>
              {!allSkills.available ? (
                <p className="muted">
                  {allSkills.hint || 'No master CV was found, so there is nothing to list.'}
                </p>
              ) : (
                Object.entries(TIER_LABELS).map(([tier, label]) => {
                  const items = (allSkills.tiers || {})[tier] || []
                  if (!items.length) return null
                  return (
                    <div key={tier}>
                      <div className="tierlab">{label}</div>
                      {items.map((s) => (
                        <span className="skill" key={s.name}>
                          <b>{s.name}</b> {s.context && <em>{s.context}</em>}
                        </span>
                      ))}
                    </div>
                  )
                })
              )}
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Your documents for this job">
        <div className="pbody">
          {[['cv', 'Tailored CV', 'tailor'], ['letter', 'Cover letter', 'letter']].map(
            ([kind, label, route]) => {
              const doc = docs && docs[kind]
              return (
                <div className="check" key={kind}>
                  <span>{label}</span>
                  <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {doc ? (
                      <>
                        <span className={doc.accepted ? 'ok' : 'no'}>
                          {doc.accepted ? 'saved' : 'draft, not saved'}
                        </span>
                        {doc.has_file && (
                          <a className="btn sm" href={api.downloadUrl(job.id, kind)} download>
                            Download
                          </a>
                        )}
                      </>
                    ) : (
                      <span className="no">not written yet</span>
                    )}
                    <Link className="btn sm" to={'/jobs/' + job.id + '/' + route}>
                      {doc ? 'Open' : 'Write it'}
                    </Link>
                  </span>
                </div>
              )
            }
          )}
          <div className="check">
            <span>Application</span>
            <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {job.application ? (
                <>
                  <span className="ok">
                    {job.application.status}
                    {job.application.applied_at ? ', applied ' + job.application.applied_at.slice(0, 10) : ''}
                  </span>
                  <Link className="btn sm" to="/applications">Manage</Link>
                </>
              ) : (
                <>
                  <span className="no">not tracked yet</span>
                  <button className="btn sm" onClick={startTracking} disabled={tracking}>
                    {tracking ? 'Starting...' : 'Start tracking'}
                  </button>
                </>
              )}
            </span>
          </div>
        </div>
      </Panel>

      {job.rationale && (
        <Panel title="Why Claude rated it this way">
          <div className="pbody"><p className="muted">{job.rationale}</p></div>
        </Panel>
      )}

      {showChat && (
        <AskAIChat jobId={job.id} jobTitle={job.title} onClose={() => setShowChat(false)} />
      )}
    </div>
  )
}
