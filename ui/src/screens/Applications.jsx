import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Donut, Empty, ErrorBox, Legend, Loading, Panel, Pill } from '../components'

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

  const load = () => api.applications().then(setData).catch(setError)
  useEffect(() => { load() }, [])

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

      <Panel title="Every stage, by the numbers">
        <div className="pbody">
          {data.funnel.map((f) => (
            <div key={f.key} style={{ marginBottom: 10 }}>
              <div className="dim">
                <span>{STATUS_LABEL[f.key] || f.key}</span>
                <span>{f.value}</span>
              </div>
              <div className="bar">
                <i
                  className={f.key === 'rejected' ? 'amb' : ''}
                  style={{
                    width: (100 * f.value / maxFunnel) + '%',
                    background: 'var(--' + (STATUS_TONE[f.key] || 'slate') + ')',
                  }}
                />
              </div>
            </div>
          ))}
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
