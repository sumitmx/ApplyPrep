import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'

const TONE_STROKE = {
  pine: 'var(--pine)', mint: 'var(--mint)', amber: 'var(--amber)',
  rust: 'var(--rust)', slate: 'var(--ink-3)',
}

export function Panel({ title, note, children }) {
  return (
    <div className="panel">
      {title && (
        <h3>
          <span>{title}</span>
          {note && <small>{note}</small>}
        </h3>
      )}
      {children}
    </div>
  )
}

export function Pill({ tone = 'slate', strong = false, children }) {
  return <span className={'pill p-' + tone + (strong ? ' strong' : '')}>{children}</span>
}

export function Card({ label, value, sub, tone }) {
  return (
    <div className={'card' + (tone ? ' t-' + tone : '')}>
      <div className="k">{label}</div>
      <div className="v">{value}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
  )
}

export function Empty({ title, children, actions }) {
  return (
    <div className="empty">
      <b>{title}</b>
      <div>{children}</div>
      {actions && <div className="btns">{actions}</div>}
    </div>
  )
}

export function Bar({ value, max = 100, tone }) {
  const pct = max ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  return (
    <div className="bar">
      <i className={tone === 'amber' ? 'amb' : ''} style={{ width: pct + '%' }} />
    </div>
  )
}

export function BarList({ rows, emptyText = 'Nothing here yet' }) {
  const navigate = useNavigate()
  const max = Math.max(1, ...rows.map((r) => r.value))
  if (!rows.some((r) => r.value > 0)) {
    return <div className="empty" style={{ padding: '18px 6px' }}>{emptyText}</div>
  }
  return (
    <div className="barlist">
      {rows.map((r) => {
        const pct = (r.value / max) * 100
        return (
          <div
            className={'barrow' + (r.href ? ' clickable' : '')}
            key={r.key}
            onClick={r.href ? () => navigate(r.href) : undefined}
            role={r.href ? 'button' : undefined}
            tabIndex={r.href ? 0 : undefined}
            onKeyDown={r.href ? (e) => { if (e.key === 'Enter') navigate(r.href) } : undefined}
          >
            <span className="barrow-label">{r.label}</span>
            <div className="bar">
              <i className={'t-' + (r.tone || 'slate')} style={{ width: pct + '%' }} />
            </div>
            <span className="barrow-value">{r.value}</span>
          </div>
        )
      })}
    </div>
  )
}

export function Donut({ segments, size = 128, thickness = 18 }) {
  const navigate = useNavigate()
  const total = segments.reduce((sum, s) => sum + s.value, 0)
  if (!total) {
    return <div className="empty" style={{ padding: '18px 6px' }}>Nothing here yet</div>
  }
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const gap = Math.min(3, circumference * 0.012)
  let offset = 0
  const arcs = segments.filter((s) => s.value > 0).map((s) => {
    const raw = (s.value / total) * circumference
    const length = Math.max(raw - gap, 0)
    const dashOffset = -offset
    offset += raw
    return { ...s, length, dashOffset }
  })

  return (
    <div className="donut">
      <svg viewBox={'0 0 ' + size + ' ' + size} width={size} height={size}>
        <g transform={'rotate(-90 ' + size / 2 + ' ' + size / 2 + ')'}>
          {arcs.map((s) => (
            <circle
              key={s.key}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={TONE_STROKE[s.tone] || TONE_STROKE.slate}
              strokeWidth={thickness}
              strokeLinecap="butt"
              strokeDasharray={s.length + ' ' + (circumference - s.length)}
              strokeDashoffset={s.dashOffset}
              className={s.href ? 'donut-seg clickable' : 'donut-seg'}
              onClick={s.href ? () => navigate(s.href) : undefined}
            >
              <title>{s.label + ': ' + s.value}</title>
            </circle>
          ))}
        </g>
      </svg>
      <div className="donut-center">
        <div className="donut-total">{total}</div>
        <div className="donut-total-label">total</div>
      </div>
    </div>
  )
}

export function Legend({ items }) {
  const navigate = useNavigate()
  return (
    <div className="legend">
      {items.map((it) => (
        <div
          className={'legend-row' + (it.href ? ' clickable' : '')}
          key={it.key}
          onClick={it.href ? () => navigate(it.href) : undefined}
          role={it.href ? 'button' : undefined}
          tabIndex={it.href ? 0 : undefined}
          onKeyDown={it.href ? (e) => { if (e.key === 'Enter') navigate(it.href) } : undefined}
        >
          <i style={{ background: TONE_STROKE[it.tone] || TONE_STROKE.slate }} />
          <span className="legend-label">{it.label}</span>
          <span className="legend-value">{it.value}</span>
        </div>
      ))}
    </div>
  )
}

export function Score({ value, label, estimated }) {
  const missing = value === null || value === undefined
  const cls = missing ? 'n none' : value < 45 ? 'n low' : 'n'
  return (
    <div className="sc">
      <div className={cls}>
        {missing ? '-' : value}
        {!missing && <span className="pct">%</span>}
      </div>
      <div className={'l' + (estimated ? ' est' : '')}>{label}</div>
    </div>
  )
}

export function Toast({ message, tone = 'pine', onClose }) {
  if (!message) return null
  return (
    <div className={'toast toast-' + tone} role="status">
      <span>{message}</span>
      <button className="toast-x" onClick={onClose} aria-label="Dismiss">x</button>
    </div>
  )
}

export function Loading() {
  return <div className="empty">Loading...</div>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="err">{String(error.message || error)}</div>
}

const ASK_PRESETS = [
  'Summarize the job advert in headers and bullets',
  'Is it a freelance work?',
  'Is Visa sponsorship available?',
  'Is remote mode available?',
]

export function AskAIChat({ jobId, jobTitle, onClose }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [settings, setSettings] = useState(null)
  const bodyRef = useRef(null)

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [messages, busy])

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => {})
  }, [])

  const current = settings && settings.options.find((o) => o.key === settings.current)

  const ask = async (question) => {
    if (!question || busy) return
    const history = messages.map(({ role, content }) => ({ role, content }))
    setMessages((m) => [...m, { role: 'user', content: question }])
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const res = await api.askJob(jobId, question, history)
      setMessages((m) => [...m, { role: 'assistant', content: res.answer }])
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const send = () => ask(input.trim())

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="chatbackdrop" onClick={onClose}>
      <div className="chatpanel" onClick={(e) => e.stopPropagation()}>
        <div className="chathead">
          <div>
            <b>Ask AI</b>
            <div className="muted" style={{ fontSize: 12 }}>{jobTitle}</div>
            {current && (
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                via {current.label}{current.model ? ' (' + current.model + ')' : ''}
              </div>
            )}
          </div>
          <button className="chatx" onClick={onClose} aria-label="Close">x</button>
        </div>
        <div className="chatbody" ref={bodyRef}>
          {messages.length === 0 && (
            <>
              <p className="muted" style={{ fontSize: 13 }}>
                Ask anything about this job, the posting text, whether a badge looks
                wrong, how you match up. It only knows this one job.
              </p>
              <div className="chatpresets">
                {ASK_PRESETS.map((q) => (
                  <button
                    key={q}
                    className="chatpreset"
                    onClick={() => ask(q)}
                    disabled={busy}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </>
          )}
          {messages.map((m, i) => (
            <div className={'chatmsg ' + (m.role === 'user' ? 'user' : 'ai')} key={i}>
              {m.content}
            </div>
          ))}
          {busy && <div className="chatmsg ai muted">Thinking...</div>}
        </div>
        <ErrorBox error={error} />
        <div className="chatinput">
          <textarea
            rows={2}
            placeholder="Ask about this job..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={busy}
          />
          <button className="btn pri" onClick={send} disabled={busy || !input.trim()}>
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
