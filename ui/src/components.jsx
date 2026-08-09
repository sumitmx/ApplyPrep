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

export function Pill({ tone = 'slate', children }) {
  return <span className={'pill p-' + tone}>{children}</span>
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
