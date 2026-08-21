import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading, Panel, Pill, Score, Toast } from '../components'
import CvPreview from './CvPreview'

const TONE = { kept: 'pine', rewrote: 'amber', dropped: 'rust', pulled: 'slate' }
const WORDING = {
  kept: 'kept', rewrote: 'reworded', dropped: 'left out', pulled: 'brought in',
}

function usePersisted(key, fallback) {
  const [value, setValue] = useState(() => localStorage.getItem(key) || fallback)
  useEffect(() => {
    localStorage.setItem(key, value)
  }, [key, value])
  return [value, setValue]
}

export default function Tailor() {
  const { id } = useParams()
  const [state, setState] = useState(null)
  const [result, setResult] = useState(null)
  const [review, setReview] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [reviewBusy, setReviewBusy] = useState(false)
  const [addingSuggestion, setAddingSuggestion] = useState(null)
  const [action, setAction] = useState(null)
  const [toast, setToast] = useState(null)
  const [accents, setAccents] = useState([])
  const [format, setFormat] = usePersisted('cvFormat', 'docx')
  const [accent, setAccent] = usePersisted('cvAccent', 'navy')
  const chosenAccent = accents.find((a) => a.key === accent) || {}

  useEffect(() => {
    api.cvAccents().then((d) => setAccents(d.accents)).catch(() => {})
  }, [])

  const load = () => {
    setError(null)
    return api.documents(id).then((d) => {
      setState(d)
      setResult(d.cv && d.cv.payload ? d.cv.payload : null)
      setReview(d.review || null)
      return d
    }).catch(setError)
  }

  useEffect(() => {
    setResult(null)
    setReview(null)
    load()
  }, [id])

  const generate = async () => {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.generateCv(id))
      await load()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    setAction('save')
    setError(null)
    try {
      const saved = await api.saveDocument(id, 'cv', accent)
      setToast(saved.cancelled
        ? { tone: 'slate', message: 'Save cancelled.' }
        : { tone: 'pine', message: 'Saved as a Word file: ' + saved.path })
      await load()
    } catch (e) {
      setError(e)
    } finally {
      setAction(null)
    }
  }

  const discard = async () => {
    if (!window.confirm('Throw this draft away? The Word file is deleted too.')) return
    setAction('discard')
    setError(null)
    try {
      await api.discardDocument(id, 'cv')
      setResult(null)
      setToast({ tone: 'rust', message: 'Draft thrown away, and the Word file deleted.' })
      await load()
    } catch (e) {
      setError(e)
    } finally {
      setAction(null)
    }
  }

  const runReview = async () => {
    setReviewBusy(true)
    setError(null)
    try {
      setReview(await api.reviewCv(id))
    } catch (e) {
      setError(e)
    } finally {
      setReviewBusy(false)
    }
  }

  const editSuggestion = (i, text) => {
    setReview((prev) => ({
      ...prev,
      suggestions: prev.suggestions.map((s, idx) => (idx === i ? { ...s, text } : s)),
    }))
  }

  const addSuggestion = async (i) => {
    const text = (review.suggestions[i].text || '').trim()
    if (!text) return
    setAddingSuggestion(i)
    try {
      setResult(await api.addCvHighlight(id, text))
      setReview((prev) => ({
        ...prev,
        suggestions: prev.suggestions.filter((_, idx) => idx !== i),
      }))
      setToast({ tone: 'pine', message: 'Added to your CV under Additional Highlights.' })
    } catch (e) {
      setToast({ tone: 'rust', message: String(e.message || e) })
    } finally {
      setAddingSuggestion(null)
    }
  }

  if (error && !state) return <ErrorBox error={error} />
  if (!state) return <Loading />

  const safety = result && result.parse_safety
  const kw = result && result.keywords
  const saved = state.cv && state.cv.accepted
  const hasFile = state.cv && state.cv.has_file

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Tailor my CV</h2>
          <p>
            Job {id}. Your CV is rewritten for this advert, then shown to you before
            anything is saved. Nothing can be invented.
          </p>
        </div>
        <div className="btns" style={{ marginTop: 0 }}>
          <Link className="btn" to={'/jobs/' + id}>Back to job</Link>
          <button className="btn pri" onClick={generate} disabled={busy}>
            {busy ? 'Writing, up to a minute...' : result ? 'Write it again' : 'Write my CV'}
          </button>
        </div>
      </div>

      <ErrorBox error={error} />

      {!state.agent_available && (
        <div className="note">
          <b>Claude Code is not installed.</b> This page needs it to write, and it
          runs on your existing subscription with no API key.
        </div>
      )}

      {!result ? (
        <Panel>
          <Empty title="Nothing written yet">
            Press Write my CV. Your bullets get reworded to match this advert's
            language, and anything irrelevant is left out. It takes about a minute.
          </Empty>
        </Panel>
      ) : (
        <>
          <Panel
            title="Preview"
            note={saved ? 'saved as a Word file' : 'not saved yet'}
          >
            <div className="pbody">
              <div className="scores" style={{ justifyContent: 'flex-start', marginBottom: 8 }}>
                <Score value={result.ats_score} label="ATS keyword match" />
              </div>
              {kw && (
                <p style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 14 }}>
                  <span style={{ color: 'var(--pine)' }}>
                    Good at: {kw.covered.map((c) => c.term).join(', ') || 'nothing matched yet'}
                  </span>
                  {kw.real_gap.length > 0 && (
                    <>
                      <br />
                      <span style={{ color: 'var(--rust)' }}>
                        Lacking: {kw.real_gap.map((c) => c.term).join(', ')}
                      </span>
                    </>
                  )}
                </p>
              )}
              {result.structured ? (
                <>
                  <div className="btns" style={{ marginBottom: 12, justifyContent: 'space-between' }}>
                    <div className="accentpicker">
                      {accents.map((a) => (
                        <button
                          key={a.key}
                          type="button"
                          className="swatch"
                          style={{ background: a.hex }}
                          aria-pressed={accent === a.key}
                          title={a.label}
                          onClick={() => setAccent(a.key)}
                        />
                      ))}
                    </div>
                    <div className="formattoggle">
                      <button
                        type="button"
                        className={format === 'docx' ? 'on' : ''}
                        onClick={() => setFormat('docx')}
                      >
                        Word
                      </button>
                      <button
                        type="button"
                        className={format === 'pdf' ? 'on' : ''}
                        onClick={() => setFormat('pdf')}
                      >
                        PDF
                      </button>
                    </div>
                  </div>
                  <CvPreview
                    content={result.structured}
                    accentHex={chosenAccent.hex || '#1F3864'}
                    accentInk={chosenAccent.ink}
                    accentText={chosenAccent.text}
                  />
                </>
              ) : (
                <pre style={{
                  whiteSpace: 'pre-wrap', fontFamily: 'inherit',
                  fontSize: 13, lineHeight: 1.7, maxHeight: 460,
                  overflowY: 'auto', overflowX: 'auto',
                }}>{result.rendered || 'This draft was written before previews existed. Press Write it again.'}</pre>
              )}
              <div className="btns" style={{ marginTop: 12 }}>
                <button className="btn pri" onClick={save} disabled={action === 'save'}>
                  {action === 'save' ? 'Saving...' : saved ? 'Save again' : 'Save as Word file'}
                </button>
                <a
                  className="btn"
                  href={api.downloadUrl(id, 'cv')}
                  onClick={(e) => { if (!hasFile) { e.preventDefault() } }}
                  style={{ opacity: hasFile ? 1 : 0.5 }}
                  download
                >
                  Download saved file
                </a>
                {result.structured && (
                  <a className="btn" href={api.exportCvUrl(id, format, accent)} download>
                    Download as {format === 'pdf' ? 'PDF' : 'Word'}
                  </a>
                )}
                <button className="btn" onClick={discard} disabled={action === 'discard'}>
                  {action === 'discard' ? 'Discarding...' : 'Throw it away'}
                </button>
              </div>
              <p className="muted" style={{ marginTop: 10 }}>
                {saved
                  ? 'Saved to ' + (state.cv.path || 'the documents folder') +
                    '. "Download saved file" gives you that exact file to attach.'
                  : 'Nothing is written to disk until you press Save. Writing it again replaces this draft.'}
              </p>
            </div>
          </Panel>

          <Panel title="AI review" note={review ? null : 'not run yet'}>
            <div className="pbody">
              <p className="muted" style={{ marginBottom: 12 }}>
                An honest read of this tailored CV against the job: what stands out,
                what's missing, and specific lines you could add. Suggestions are
                AI-drafted text you edit and approve before anything is added - a
                deliberate exception to the "nothing can be invented" guarantee that
                applies to the automatic tailoring above.
              </p>
              <div className="btns">
                <button className="btn" onClick={runReview} disabled={reviewBusy}>
                  {reviewBusy ? 'Reviewing, up to a minute...'
                    : review ? 'Review again' : 'Review this CV'}
                </button>
              </div>
            </div>
          </Panel>

          {review && (
            <>
              <Panel title="Strengths">
                <div className="pbody">
                  {review.strengths.length === 0 ? (
                    <Empty title="Nothing flagged">No particular strengths called out.</Empty>
                  ) : (
                    review.strengths.map((s, i) => (
                      <div className="check" key={i}><span>{s}</span></div>
                    ))
                  )}
                </div>
              </Panel>

              <Panel title="Areas for improvement">
                <div className="pbody">
                  {review.improvements.length === 0 ? (
                    <Empty title="Nothing flagged">No particular gaps called out.</Empty>
                  ) : (
                    review.improvements.map((s, i) => (
                      <div className="check" key={i}><span>{s}</span></div>
                    ))
                  )}
                </div>
              </Panel>

              <Panel title="Suggestions" note="edit the wording, then add what you approve">
                <div className="pbody">
                  {review.suggestions.length === 0 ? (
                    <Empty title="Nothing left">
                      All suggestions have been added, or none were made.
                    </Empty>
                  ) : (
                    review.suggestions.map((s, i) => (
                      <div key={i} style={{ marginBottom: 14 }}>
                        <textarea
                          className="skillbox"
                          rows={2}
                          value={s.text}
                          onChange={(e) => editSuggestion(i, e.target.value)}
                        />
                        {s.why && <p className="muted" style={{ marginTop: 4 }}>{s.why}</p>}
                        <div className="btns" style={{ marginTop: 6 }}>
                          <button
                            className="btn sm"
                            disabled={addingSuggestion === i || !s.text.trim()}
                            onClick={() => addSuggestion(i)}
                          >
                            {addingSuggestion === i ? 'Adding...' : 'Add'}
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </Panel>
            </>
          )}

          {result.note && <div className="note">{result.note}</div>}

          <Panel
            title="What changed"
            note={Object.entries(result.counts || {})
              .filter(([, n]) => n)
              .map(([k, n]) => n + ' ' + WORDING[k]).join(', ')}
          >
            <div className="pbody">
              {result.changes.map((c) => (
                <div className="check" key={c.id} style={{ alignItems: 'flex-start' }}>
                  <span style={{ flex: 1 }}>
                    {c.was && (
                      <span style={{
                        display: 'block', color: 'var(--ink-3)',
                        textDecoration: 'line-through', marginBottom: 3,
                      }}>{c.was}</span>
                    )}
                    <span style={{ opacity: c.action === 'dropped' ? 0.55 : 1 }}>
                      {c.text}
                    </span>
                    {c.reason && (
                      <span style={{ display: 'block', color: 'var(--ink-3)', fontSize: 12 }}>
                        {c.reason}
                      </span>
                    )}
                  </span>
                  <Pill tone={TONE[c.action]}>{WORDING[c.action]}</Pill>
                </div>
              ))}
            </div>
          </Panel>

          <div className="two">
            <Panel
              title="Will recruiting software read it properly"
              note={safety.passed + ' of ' + (safety.passed + safety.failed) + ' checks pass'}
            >
              <div className="pbody">
                {safety.checks.map((c) => (
                  <div className="check" key={c.check}>
                    <span>{c.check}</span>
                    <span className={c.pass ? 'ok' : 'no'}>
                      {c.pass ? 'fine' : c.detail}
                    </span>
                  </div>
                ))}
                <p className="muted" style={{ marginTop: 11 }}>
                  These are checks code can verify, not a score. No recruiting system
                  gives your CV a number.
                </p>
              </div>
            </Panel>

            <Panel title="Words this advert asks for" note="the three buckets behind the ATS score above">
              <div className="pbody">
                <div className="kw">
                  <div className="kwcol">
                    <div className="h"><b>{kw.counts.covered}</b>already in it</div>
                    <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                      {kw.covered.map((c) => c.term).slice(0, 8).join(', ') || 'none'}
                    </div>
                  </div>
                  <div className="kwcol">
                    <div className="h" style={{ color: 'var(--amber)' }}>
                      <b>{kw.counts.fixable}</b>worth adding
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                      {kw.fixable.map((c) => c.term).slice(0, 8).join(', ') || 'none'}
                    </div>
                  </div>
                  <div className="kwcol">
                    <div className="h" style={{ color: 'var(--rust)' }}>
                      <b>{kw.counts.real_gap}</b>you have not done
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                      {kw.real_gap.map((c) => c.term).slice(0, 8).join(', ') || 'none'}
                    </div>
                  </div>
                </div>
                <p className="muted">
                  Worth adding means you have done it and your CV never said so. The
                  last column belongs in the cover letter, not on the CV.
                </p>
              </div>
            </Panel>
          </div>

        </>
      )}

      <Toast
        message={toast && toast.message}
        tone={toast && toast.tone}
        onClose={() => setToast(null)}
      />
    </div>
  )
}
