import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading, Panel, Pill, Toast } from '../components'

export default function Letter() {
  const { id } = useParams()
  const [state, setState] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const [action, setAction] = useState(null)
  const [toast, setToast] = useState(null)

  const load = () => {
    setError(null)
    return api.documents(id).then((d) => {
      setState(d)
      setResult(d.letter ? {
        body: d.letter.body,
        word_count: d.letter.word_count,
        note: (d.letter.payload || {}).note,
      } : null)
      return d
    }).catch(setError)
  }

  useEffect(() => {
    setResult(null)
    load()
  }, [id])

  const generate = async () => {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.generateLetter(id))
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
      const saved = await api.saveDocument(id, 'letter')
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
    if (!window.confirm('Throw this letter away? The Word file is deleted too.')) return
    setAction('discard')
    setError(null)
    try {
      await api.discardDocument(id, 'letter')
      setResult(null)
      setToast({ tone: 'rust', message: 'Letter thrown away, and the Word file deleted.' })
      await load()
    } catch (e) {
      setError(e)
    } finally {
      setAction(null)
    }
  }

  if (error && !state) return <ErrorBox error={error} />
  if (!state) return <Loading />

  const saved = state.letter && state.letter.accepted
  const hasFile = state.letter && state.letter.has_file

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Cover letter</h2>
          <p>
            Job {id}. Written from your CV facts only, states plainly that you need
            sponsorship, and names one real gap rather than hiding it.
          </p>
        </div>
        <div className="btns" style={{ marginTop: 0 }}>
          {result && (
            <Pill tone={result.over_limit ? 'amber' : 'slate'}>
              {result.word_count} words
            </Pill>
          )}
          <Link className="btn" to={'/jobs/' + id}>Back to job</Link>
          <button className="btn pri" onClick={generate} disabled={busy}>
            {busy ? 'Writing, up to a minute...' : result ? 'Write it again' : 'Write my letter'}
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
            Press Write my letter. It reads the advert and your CV, then drafts under
            250 words. You review it here before it goes anywhere.
          </Empty>
        </Panel>
      ) : (
        <>
          <Panel title="Preview" note={saved ? 'saved as a Word file' : 'not saved yet'}>
            <div className="pbody" style={{ fontSize: 13.5, lineHeight: 1.75 }}>
              <p style={{ marginBottom: 11 }}>Dear hiring team,</p>
              {result.body.split(/\n\s*\n/).map((para, i) => (
                <p key={i} style={{ marginBottom: 11 }}>{para}</p>
              ))}
              <p style={{ marginBottom: 11 }}>Warm regards,<br />Alex Morgan</p>
              <div className="btns">
                <button className="btn pri" onClick={save} disabled={action === 'save'}>
                  {action === 'save' ? 'Saving...' : saved ? 'Save again' : 'Save as Word file'}
                </button>
                <a
                  className="btn"
                  href={api.downloadUrl(id, 'letter')}
                  onClick={(e) => { if (!hasFile) { e.preventDefault() } }}
                  style={{ opacity: hasFile ? 1 : 0.5 }}
                  download
                >
                  Download
                </a>
                <button className="btn" onClick={discard} disabled={action === 'discard'}>
                  {action === 'discard' ? 'Discarding...' : 'Throw it away'}
                </button>
              </div>
              <p className="muted" style={{ marginTop: 10 }}>
                {saved
                  ? 'Saved to ' + (state.letter.path || 'the documents folder') + '.'
                  : 'Nothing is written to disk until you press Save.'}
              </p>
            </div>
          </Panel>
          {result.note && <div className="note">{result.note}</div>}
          <div className="note">
            <b>Why the gap is stated.</b> Naming it once, plainly, costs nothing and
            makes everything else on the page more believable. Hiding it means
            finding out in a technical interview instead.
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
