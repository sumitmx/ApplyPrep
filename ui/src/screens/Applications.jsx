import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Donut, Empty, ErrorBox, GmailSetupModal, Legend, Loading, Panel, Pill }
  from '../components'

const STATUS_TONE = {
  drafting: 'slate',
  applied: 'amber',
  screening: 'amber',
  interview: 'mint',
  offer: 'pine',
  rejected: 'rust',
}

const STATUS_LABEL = {
  drafting: 'Drafting',
  applied: 'Applied',
  screening: 'Screening',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
}

const FUNNEL_ORDER = ['drafting', 'applied', 'screening', 'interview', 'offer', 'rejected']

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function Applications() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)

  const [gmail, setGmail] = useState(null)
  const [suggestions, setSuggestions] = useState(null)
  const [gmailBusy, setGmailBusy] = useState(null)
  const [gmailError, setGmailError] = useState(null)
  const [gmailSetup, setGmailSetup] = useState(false)

  const load = () => api.applications().then(setData).catch(setError)
  const loadGmail = () => {
    api.gmailStatus().then(setGmail).catch(() => {})
    api.gmailSuggestions().then((d) => setSuggestions(d.suggestions)).catch(() => {})
  }
  useEffect(() => { load(); loadGmail() }, [])

  const connectGmail = async () => {
    setGmailBusy('connect')
    setGmailError(null)
    try {
      await api.gmailConnect()
      loadGmail()
    } catch (e) {
      setGmailError(e)
    } finally {
      setGmailBusy(null)
    }
  }

  const onConnectClick = () => {
    if (gmail && gmail.credentials_present) connectGmail()
    else setGmailSetup(true)
  }

  const syncGmail = async () => {
    setGmailBusy('sync')
    setGmailError(null)
    try {
      await api.gmailSync()
      loadGmail()
    } catch (e) {
      setGmailError(e)
    } finally {
      setGmailBusy(null)
    }
  }

  const actOnSuggestion = async (emailId, action) => {
    setGmailBusy(emailId)
    try {
      if (action === 'apply') await api.applyGmailSuggestion(emailId)
      else await api.dismissGmailSuggestion(emailId)
      setSuggestions((prev) => prev.filter((s) => s.email_id !== emailId))
      load()
    } catch (e) {
      setGmailError(e)
    } finally {
      setGmailBusy(null)
    }
  }

  const changeStatus = async (row, status) => {
    setBusy(row.id)
    try {
      await api.setApplicationStatus(row.id, status)
      await load()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  if (error && !data) return <ErrorBox error={error} />
  if (!data) return <Loading />

  const total = data.rows.length
  const maxFunnel = Math.max(1, ...data.funnel.map((f) => f.value))
  const funnelSegments = data.funnel.map((f) => ({
    key: f.key, label: STATUS_LABEL[f.key] || f.key, tone: STATUS_TONE[f.key] || 'slate',
    value: f.value,
  }))
  const responseSegments = data.response_mix || []

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Applications</h2>
          <p>
            An application starts tracking itself here as soon as you save a CV or
            cover letter for a job. Move it along the stages as things happen; you
            still submit everything yourself, this only remembers where things stand.
          </p>
        </div>
        <span className="countpill">{total} tracked</span>
      </div>

      <ErrorBox error={error} />

      {gmailSetup && (
        <GmailSetupModal
          onClose={() => setGmailSetup(false)}
          onConnected={async () => {
            setGmailSetup(false)
            await connectGmail()
          }}
        />
      )}

      <div className="two">
        <Panel title="Where things stand">
          <div className="pbody" style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
            <Donut segments={funnelSegments} />
            <Legend items={funnelSegments} />
          </div>
        </Panel>

        <Panel title="Have they replied" note="drafting isn't sent yet; rejected still counts as a reply">
          <div className="pbody" style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
            <Donut segments={responseSegments} />
            <Legend items={responseSegments} />
          </div>
        </Panel>
      </div>

      <Panel
        title="Responses from your inbox"
        note={gmail && gmail.connected ? gmail.account_email : null}
      >
        <div className="pbody">
          {!gmail ? <Loading /> : !gmail.connected ? (
            <Empty
              title="Gmail is not connected yet"
              actions={
                <button className="btn pri" onClick={onConnectClick} disabled={gmailBusy === 'connect'}>
                  {gmailBusy === 'connect' ? 'Connecting...' : 'Connect Gmail'}
                </button>
              }
            >
              Reads replies from job applications and suggests a status for
              each one - nothing changes until you approve it here.
            </Empty>
          ) : (
            <>
              <div className="btns" style={{ marginBottom: 12, justifyContent: 'space-between' }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  {gmail.last_sync && gmail.last_sync.finished_at
                    ? 'Last checked ' + formatDate(gmail.last_sync.finished_at)
                    : 'Never checked yet'}
                </span>
                <button className="btn sm" onClick={syncGmail} disabled={gmailBusy === 'sync'}>
                  {gmailBusy === 'sync' ? 'Checking...' : 'Check inbox now'}
                </button>
              </div>
              <ErrorBox error={gmailError} />
              {!suggestions ? <Loading /> : suggestions.length === 0 ? (
                <Empty title="Nothing to review">
                  No unread replies look like a status change right now.
                </Empty>
              ) : (
                suggestions.map((s) => (
                  <div key={s.email_id} className="gmailrow">
                    <div className="gmailrow-head">
                      <div>
                        <b>{s.title}</b>
                        <span className="muted"> @ {s.company}</span>
                      </div>
                      <Pill tone={STATUS_TONE[s.suggested_status] || 'slate'}>
                        Looks like: {STATUS_LABEL[s.suggested_status] || s.suggested_status}
                      </Pill>
                    </div>
                    <p className="muted" style={{ fontSize: 12.5 }}>
                      "{s.subject}" - {s.snippet}
                    </p>
                    <div className="btns">
                      <button
                        className="btn pri sm"
                        disabled={gmailBusy === s.email_id}
                        onClick={() => actOnSuggestion(s.email_id, 'apply')}
                      >
                        Mark as {STATUS_LABEL[s.suggested_status] || s.suggested_status}
                      </button>
                      <button
                        className="btn sm"
                        disabled={gmailBusy === s.email_id}
                        onClick={() => actOnSuggestion(s.email_id, 'dismiss')}
                      >
                        Not this one
                      </button>
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>
      </Panel>

      <Panel title="Every application">
        {total === 0 ? (
          <div className="pbody">
            <Empty title="Nothing tracked yet">
              Open a job, tailor a CV or write a cover letter, and save it. That
              starts tracking the application here automatically.
            </Empty>
          </div>
        ) : (
          <div className="atable-wrap">
            <table className="atable">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Company</th>
                  <th>Country</th>
                  <th>Applied</th>
                  <th>Status</th>
                  <th>Match</th>
                  <th>Chances</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Link to={'/jobs/' + row.job_id} style={{ fontWeight: 500 }}>
                        {row.title}
                      </Link>
                      {row.city && <div className="muted">{row.city}</div>}
                    </td>
                    <td>{row.company_name || '-'}</td>
                    <td>{row.country || '-'}</td>
                    <td>{formatDate(row.applied_at)}</td>
                    <td>
                      <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <Pill tone={STATUS_TONE[row.status] || 'slate'}>
                          {STATUS_LABEL[row.status] || row.status}
                        </Pill>
                        <select
                          value={row.status}
                          disabled={busy === row.id}
                          onChange={(e) => changeStatus(row, e.target.value)}
                        >
                          {FUNNEL_ORDER.map((s) => (
                            <option key={s} value={s}>{STATUS_LABEL[s]}</option>
                          ))}
                        </select>
                      </span>
                    </td>
                    <td className="num">{row.fit !== null ? row.fit : '-'}</td>
                    <td className="num">{row.reach !== null ? row.reach : '-'}</td>
                    <td>
                      {row.url && (
                        <a className="btn sm" href={row.url} target="_blank" rel="noreferrer">
                          Open posting
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
