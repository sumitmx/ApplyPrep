import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading, Panel, Toast } from '../components'

const TIER_LABELS = {
  core: 'Your strongest skills',
  working: 'You have worked with these',
  familiar: 'You have some exposure',
}

function formatDate(stamp) {
  return stamp ? stamp.replace('T', ' ').slice(0, 16) : ''
}

function UploadRow({ kind, label, upload, onChanged }) {
  const inputRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const pick = () => inputRef.current && inputRef.current.click()

  const onFile = async (e) => {
    const file = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await api.uploadMasterCv(kind, file)
      onChanged()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const discard = async () => {
    setBusy(true)
    try {
      await api.discardMasterCv(kind)
      onChanged()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="check">
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span>{label}, from your own file</span>
        {upload ? (
          <span className="muted">{upload.filename} - uploaded {formatDate(upload.uploaded_at)}</span>
        ) : (
          <span className="muted">Nothing uploaded yet. PDF, Word, or plain text.</span>
        )}
        {error && <span className="no">{String(error.message || error)}</span>}
      </span>
      <span style={{ display: 'flex', gap: 8 }}>
        {upload && (
          <a className="btn sm" href={api.masterCvDownloadUrl(kind)} download>
            Download
          </a>
        )}
        <button className="btn sm" disabled={busy} onClick={pick}>
          Upload
        </button>
        {upload && (
          <button className="btn sm" disabled={busy} onClick={discard}>
            Remove
          </button>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt,.md,.rtf"
          style={{ display: 'none' }}
          onChange={onFile}
        />
      </span>
    </div>
  )
}

export default function MyCV() {
  const [master, setMaster] = useState(null)
  const [docs, setDocs] = useState(null)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)

  const loadMaster = () => api.masterCv().then(setMaster).catch(setError)

  useEffect(() => {
    loadMaster()
    api.allDocuments().then((d) => setDocs(d.documents)).catch(setError)
  }, [])

  if (error && !master && !docs) return <ErrorBox error={error} />
  if (!master || !docs) return <Loading />

  const latestCv = docs.find((d) => d.kind === 'cv')
  const latestLetter = docs.find((d) => d.kind === 'letter')
  const uploads = master.uploads || {}

  return (
    <div>
      <div className="shead">
        <div>
          <h2>My CV / Cover Letter</h2>
          <p>
            Your CV and cover letters are tailored per job in Claude chat, then
            saved here once you accept them. This page collects the latest one of
            each, your underlying skills, and everything you have saved so far.
          </p>
        </div>
      </div>

      <ErrorBox error={error} />

      <div className="two">
        <Panel title="My latest resume" note={latestCv ? formatDate(latestCv.created_at) : null}>
          <div className="pbody">
            {!latestCv ? (
              <Empty title="Nothing saved yet">
                Open a job, press Tailor my CV, and save the draft you like. It
                shows up here.
              </Empty>
            ) : (
              <div className="check">
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span>{latestCv.title}</span>
                  <span className="muted">{latestCv.company}</span>
                </span>
                <span style={{ display: 'flex', gap: 8 }}>
                  <Link className="btn sm" to={'/jobs/' + latestCv.job_id + '/tailor'}>
                    Open
                  </Link>
                  {latestCv.has_file && (
                    <a className="btn sm" href={api.downloadUrl(latestCv.job_id, 'cv')} download>
                      Download
                    </a>
                  )}
                </span>
              </div>
            )}
            {uploads.cv && uploads.cv.preview && (
              <div className="textpreview">
                {uploads.cv.preview}
                {uploads.cv.preview_truncated ? '…' : ''}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Cover letter" note={latestLetter ? formatDate(latestLetter.created_at) : null}>
          <div className="pbody">
            {!latestLetter ? (
              <Empty title="Nothing saved yet">
                Open a job, press Write cover letter, and save the draft you like.
                It shows up here.
              </Empty>
            ) : (
              <div className="check">
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span>{latestLetter.title}</span>
                  <span className="muted">{latestLetter.company}</span>
                </span>
                <span style={{ display: 'flex', gap: 8 }}>
                  <Link className="btn sm" to={'/jobs/' + latestLetter.job_id + '/letter'}>
                    Open
                  </Link>
                  {latestLetter.has_file && (
                    <a className="btn sm" href={api.downloadUrl(latestLetter.job_id, 'letter')} download>
                      Download
                    </a>
                  )}
                </span>
              </div>
            )}
            {uploads.letter && uploads.letter.preview && (
              <div className="textpreview">
                {uploads.letter.preview}
                {uploads.letter.preview_truncated ? '…' : ''}
              </div>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Your own CV and cover letter" note="uploaded from your disk, not tailored by Claude">
        <div className="pbody">
          <UploadRow
            kind="cv"
            label="Master CV"
            upload={uploads.cv}
            onChanged={() => {
              loadMaster()
              setToast({ tone: 'pine', message: 'Saved.' })
            }}
          />
          <UploadRow
            kind="letter"
            label="Master cover letter"
            upload={uploads.letter}
            onChanged={() => {
              loadMaster()
              setToast({ tone: 'pine', message: 'Saved.' })
            }}
          />
        </div>
      </Panel>

      <Panel title="Edit my resume" note="what Claude tailors from">
        <div className="pbody">
          {!master.available ? (
            <Empty title="No master CV found">
              {master.hint || 'Add master.yaml to the project folder to enable this.'}
            </Empty>
          ) : (
            <>
              {Object.entries(TIER_LABELS).map(([tier, label]) => {
                const items = master.tiers[tier] || []
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
              })}
              <p className="muted" style={{ marginTop: 13 }}>
                This list comes straight from master.yaml on your laptop. There is
                no editor here on purpose: the tiers and honesty notes on each skill
                are what keep you safe in a technical interview, so they are worth
                editing by hand, not through a form. Open master.yaml in any text
                editor, change it, then restart the server for the new version to
                load.
              </p>
            </>
          )}
        </div>
      </Panel>

      <Panel title="Everything you have saved" note={docs.length + ' document(s)'}>
        <div className="pbody">
          {docs.length === 0 ? (
            <Empty title="Nothing saved yet">
              Tailored CVs and cover letters you save from a job page appear here,
              newest first.
            </Empty>
          ) : (
            docs.map((d) => (
              <div className="check" key={d.id}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Link to={'/jobs/' + d.job_id}>{d.title}</Link>
                  <span className="muted">
                    {d.company} - {d.kind === 'cv' ? 'CV' : 'Cover letter'} - {formatDate(d.created_at)}
                  </span>
                </span>
                {d.has_file && (
                  <a className="btn sm" href={api.downloadUrl(d.job_id, d.kind)} download>
                    Download
                  </a>
                )}
              </div>
            ))
          )}
        </div>
      </Panel>

      <Toast
        message={toast && toast.message}
        tone={toast && toast.tone}
        onClose={() => setToast(null)}
      />
    </div>
  )
}
