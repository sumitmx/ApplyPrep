import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading, Panel, Pill } from '../components'

export default function Search() {
  const [params] = useSearchParams()
  const q = (params.get('q') || '').trim()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (q.length < 2) { setData({ results: [] }); return }
    setData(null)
    setError(null)
    let cancelled = false
    api.search(q, 200)
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(e) })
    return () => { cancelled = true }
  }, [q])

  const results = data ? data.results : []

  return (
    <div>
      <div className="shead">
        <div>
          <h2>Search results</h2>
          <p>
            {q
              ? <>Jobs, companies and locations matching <b>&ldquo;{q}&rdquo;</b>.
                This includes jobs you have already applied to.</>
              : 'Type at least two characters in the search box above.'}
          </p>
        </div>
        {q.length >= 2 && data && (
          <div className="sheadside">
            <span className="countpill">
              {results.length === 0
                ? 'no matches'
                : results.length + ' match' + (results.length === 1 ? '' : 'es')}
            </span>
          </div>
        )}
      </div>

      <ErrorBox error={error} />

      {q.length < 2 ? (
        <Panel>
          <Empty title="Nothing to search for yet">
            Use the search box at the top to look up a job by title, company or
            location.
          </Empty>
        </Panel>
      ) : !data ? (
        <Loading />
      ) : results.length === 0 ? (
        <Panel>
          <Empty title={'Nothing matches “' + q + '”'}>
            Try a shorter or different term. Search covers job titles, companies,
            cities and countries.
          </Empty>
        </Panel>
      ) : (
        <div className="panel">
          {results.map((r) => (
            <Link className="resultrow" key={r.id} to={'/jobs/' + r.id}>
              <div className="body">
                <div className="t">{r.title}</div>
                <div className="m">
                  {[r.company, r.location, r.posted_age].filter(Boolean).join(' · ')}
                </div>
              </div>
              {r.applied && <Pill tone="rust">applied</Pill>}
              {!r.applied && r.status && <Pill tone="slate">{r.status}</Pill>}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
