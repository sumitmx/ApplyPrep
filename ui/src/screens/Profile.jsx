import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { BarList, Card, Donut, Empty, ErrorBox, Legend, Loading, Panel, Toast } from '../components'

const TIER_LABELS = {
  core: 'Your strongest skills',
  working: 'You have worked with these',
  familiar: 'You have some exposure',
}

const TIER_TONE = { core: 'pine', working: 'mint', familiar: 'slate' }

function formatDate(stamp) {
  return stamp ? stamp.replace('T', ' ').slice(0, 16) : ''
}

// What the import did to master.yaml. Shown after every upload, because the
// CV rewrites the profile silently otherwise and a misread PDF would only
// surface later, in a bad CV.
function ImportReport({ report }) {
  if (!report) return null
  if (!report.applied) {
    return (
      <div className="err" style={{ marginTop: 10 }}>
        Your CV was saved, but the profile could not be rebuilt from it:{' '}
        {typeof report.reason === 'string' ? report.reason : report.reason?.message}
      </div>
    )
  }
  const lines = [
    report.roles + ' roles, ' + report.bullets + ' bullets',
    report.bullet_ids_kept ? report.bullet_ids_kept + ' kept their id' : null,
    report.bullets_not_in_cv
      ? report.bullets_not_in_cv + ' dropped as not found in the CV'
      : null,
  ].filter(Boolean)

  return (
    <div className="ok" style={{ marginTop: 10 }}>
      <b>Profile rebuilt from your CV.</b> {lines.join(' · ')}.
      {report.skills_added?.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <b>Skills added:</b> {report.skills_added.join(', ')}
        </div>
      )}
      {report.skills_removed?.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <b>No longer in your CV, so removed:</b> {report.skills_removed.join(', ')}
        </div>
      )}
      {report.backup && (
        <div className="muted" style={{ marginTop: 6, fontSize: 11.5 }}>
          Previous profile saved as {report.backup}
        </div>
      )}
    </div>
  )
}

function UploadRow({ upload, onChanged }) {
  const inputRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)

  const pick = () => inputRef.current && inputRef.current.click()

  const onFile = async (e) => {
    const file = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      const meta = await api.uploadMasterCv('cv', file)
      setReport(meta.import || null)
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
      await api.discardMasterCv('cv')
      onChanged()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <div className="check">
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span>Master CV, from your own file</span>
        {upload ? (
          <span className="muted">{upload.filename} - uploaded {formatDate(upload.uploaded_at)}</span>
        ) : (
          <span className="muted">Nothing uploaded yet. PDF, Word, or plain text.</span>
        )}
        {error && <span className="no">{String(error.message || error)}</span>}
      </span>
      <span style={{ display: 'flex', gap: 8 }}>
        {upload && (
          <a className="btn sm" href={api.masterCvDownloadUrl('cv')} download>
            Download
          </a>
        )}
        <button className="btn sm" disabled={busy} onClick={pick}>
          {busy ? 'Reading your CV...' : 'Upload'}
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
    <ImportReport report={report} />
    </>
  )
}

export default function Profile() {
  const [master, setMaster] = useState(null)
  const [kpis, setKpis] = useState(null)
  const [gaps, setGaps] = useState(null)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)

  const [skillText, setSkillText] = useState('')
  const [proposed, setProposed] = useState(null)
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState(null)
  const [savingSkills, setSavingSkills] = useState(false)
  const [gapsRefreshing, setGapsRefreshing] = useState(false)
  const [addingGap, setAddingGap] = useState(null)

  const loadMaster = () => api.masterCv().then(setMaster).catch(setError)
  const loadKpis = () => api.profileKpis().then(setKpis).catch(() => {})
  const loadGaps = () => api.skillGaps().then(setGaps).catch(() => {})

  useEffect(() => {
    loadMaster()
    loadKpis()
    loadGaps()
  }, [])

  if (error && !master) return <ErrorBox error={error} />
  if (!master) return <Loading />

  const uploads = master.uploads || {}

  const extract = async () => {
    setExtracting(true)
    setExtractError(null)
    try {
      const res = await api.extractSkills(skillText)
      setProposed(res.skills.map((s) => ({ ...s, include: true })))
    } catch (e) {
      setExtractError(e)
    } finally {
      setExtracting(false)
    }
  }

  const editProposed = (i, key, value) => {
    setProposed((prev) => prev.map((p, idx) => (idx === i ? { ...p, [key]: value } : p)))
  }

  const saveProposed = async () => {
    const chosen = proposed.filter((p) => p.include && p.name.trim())
    if (!chosen.length) return
    setSavingSkills(true)
    try {
      const res = await api.saveSkills(
        chosen.map(({ name, tier, context }) => ({ name, tier, context: context || null }))
      )
      setToast({
        tone: 'pine',
        message: 'Added ' + res.added.length + ', skipped ' + res.skipped.length + ' already there.',
      })
      setProposed(null)
      setSkillText('')
      loadMaster()
      loadKpis()
    } catch (e) {
      setToast({ tone: 'rust', message: String(e.message || e) })
    } finally {
      setSavingSkills(false)
    }
  }

  const refreshGaps = async () => {
    setGapsRefreshing(true)
    try {
      setGaps(await api.refreshSkillGaps())
    } catch (e) {
      setToast({ tone: 'rust', message: String(e.message || e) })
    } finally {
      setGapsRefreshing(false)
    }
  }

  const addGap = async (name) => {
    setAddingGap(name)
    try {
      await api.saveSkills([{ name, tier: 'familiar', context: null }])
      setGaps((prev) => ({ ...prev, gaps: prev.gaps.filter((g) => g.name !== name) }))
      setToast({ tone: 'pine', message: 'Added ' + name + ' under Familiar.' })
      loadMaster()
      loadKpis()
    } catch (e) {
      setToast({ tone: 'rust', message: String(e.message || e) })
    } finally {
      setAddingGap(null)
    }
  }

  const tierSegments = Object.entries(TIER_LABELS).map(([key, label]) => ({
    key, label, tone: TIER_TONE[key], value: (master.tiers[key] || []).length,
  }))

  const demandRows = (kpis && kpis.skill_demand) || []

  const bulletRows = ((kpis && kpis.bullet_usage && kpis.bullet_usage.bullets) || []).map((b) => ({
    key: b.id,
    label: (b.text.length > 110 ? b.text.slice(0, 110) + '…' : b.text)
      + ' · dropped ' + b.dropped + '/' + b.total,
    tone: b.drop_rate >= 50 ? 'rust' : 'slate',
    value: b.drop_rate,
  }))

  const sponsorshipSegments = (kpis && kpis.sponsorship_mix) || []
  const languageSegments = (kpis && kpis.language_mix) || []
  const agencySegments = (kpis && kpis.agency_mix) || []
  const coverageRows = ((kpis && kpis.keyword_coverage && kpis.keyword_coverage.jobs) || []).map((j) => ({
    ...j, label: j.label.length > 55 ? j.label.slice(0, 55) + '…' : j.label,
  }))

  return (
    <div>
      <div className="shead">
        <div>
          <h2>My Profile</h2>
          <p>
            Your master CV file, the skills Claude tailors from, and how your
            profile is actually performing across the jobs you have pulled.
          </p>
        </div>
      </div>

      <ErrorBox error={error} />

      <div className="two">
        <Panel title="Skill tier balance">
          <div className="pbody" style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
            <Donut segments={tierSegments} />
            <Legend items={tierSegments} />
          </div>
        </Panel>

        <Panel title="Profile freshness">
          <div className="pbody">
            {!kpis ? (
              <Loading />
            ) : !kpis.freshness.available ? (
              <Empty title="No master CV file yet">
                Upload your CV below so freshness can be tracked.
              </Empty>
            ) : (
              <div className="cards">
                <Card
                  label="Last updated"
                  value={kpis.freshness.days_since === 0 ? 'today' : kpis.freshness.days_since + 'd ago'}
                  sub={formatDate(kpis.freshness.updated_at)}
                  tone={kpis.freshness.days_since > 30 ? 'amber' : 'pine'}
                />
                <Card
                  label="Jobs rated since"
                  value={kpis.freshness.jobs_rated_since}
                  sub="worth a refresh?"
                />
              </div>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Skill demand" note="how often each skill shows up in jobs you've pulled">
        <div className="pbody">
          {!kpis ? <Loading /> : (
            <BarList rows={demandRows} emptyText="Pull some jobs first, or add skills below" />
          )}
        </div>
      </Panel>

      <Panel
        title="Bullet usage"
        note={kpis ? 'across ' + kpis.bullet_usage.documents_considered + ' saved CV(s)' : null}
      >
        <div className="pbody">
          {!kpis ? <Loading /> : (
            <BarList
              rows={bulletRows}
              wide
              emptyText="Nothing dropped often yet, or not enough tailored CVs saved"
            />
          )}
        </div>
      </Panel>

      <Panel
        title="Skill gap finder"
        note={gaps && gaps.computed_at ? 'last checked ' + formatDate(gaps.computed_at) : 'not run yet'}
      >
        <div className="pbody">
          <p className="muted" style={{ marginBottom: 12 }}>
            Scans your recent job postings for skills that keep coming up but are
            not in your profile yet.
          </p>
          {!gaps ? (
            <Loading />
          ) : gaps.gaps.length === 0 ? (
            <Empty title={gaps.computed_at ? 'No gaps found' : 'Not checked yet'}>
              {gaps.computed_at
                ? 'Nothing recurring enough to flag right now.'
                : 'Run a scan to compare your skills against jobs you have pulled.'}
            </Empty>
          ) : (
            gaps.gaps.map((g) => (
              <div className="check" key={g.name}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span>{g.name}</span>
                  {g.note && <span className="muted">{g.note}</span>}
                </span>
                <button
                  className="btn sm"
                  disabled={addingGap === g.name}
                  onClick={() => addGap(g.name)}
                >
                  {addingGap === g.name ? 'Adding...' : 'Add'}
                </button>
              </div>
            ))
          )}
          <div className="btns">
            <button className="btn sm" disabled={gapsRefreshing} onClick={refreshGaps}>
              {gapsRefreshing ? 'Scanning...' : gaps && gaps.computed_at ? 'Scan again' : 'Find skill gaps'}
            </button>
          </div>
        </div>
      </Panel>

      <Panel title="Add skills" note="describe them in your own words, AI turns them into entries">
        <div className="pbody">
          <textarea
            className="skillbox"
            rows={3}
            placeholder="e.g. Strong in Python, used Docker and Kubernetes for about 2 years, some exposure to Rust"
            value={skillText}
            onChange={(e) => setSkillText(e.target.value)}
          />
          <div className="btns">
            <button
              className="btn sm pri"
              disabled={extracting || !skillText.trim()}
              onClick={extract}
            >
              {extracting ? 'Reading...' : 'Extract skills'}
            </button>
          </div>
          {extractError && <p className="no">{String(extractError.message || extractError)}</p>}

          {proposed && (
            <div className="proposedlist">
              {proposed.length === 0 ? (
                <p className="muted">Nothing new found in that text.</p>
              ) : (
                <>
                  {proposed.map((p, i) => (
                    <div className="proposedrow" key={i}>
                      <input
                        type="checkbox"
                        checked={p.include}
                        onChange={() => editProposed(i, 'include', !p.include)}
                      />
                      <input
                        className="mono"
                        value={p.name}
                        onChange={(e) => editProposed(i, 'name', e.target.value)}
                      />
                      <select value={p.tier} onChange={(e) => editProposed(i, 'tier', e.target.value)}>
                        <option value="core">Core</option>
                        <option value="working">Working</option>
                        <option value="familiar">Familiar</option>
                      </select>
                      <input
                        placeholder="context (optional)"
                        value={p.context || ''}
                        onChange={(e) => editProposed(i, 'context', e.target.value)}
                      />
                    </div>
                  ))}
                  <div className="btns">
                    <button className="btn sm pri" disabled={savingSkills} onClick={saveProposed}>
                      {savingSkills ? 'Saving...' : 'Save to profile'}
                    </button>
                    <button className="btn sm" onClick={() => setProposed(null)}>
                      Discard
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Your master CV" note="the real file and skills Claude tailors from, not an AI-tailored version">
        <div className="pbody">
          <UploadRow
            upload={uploads.cv}
            onChanged={() => {
              loadMaster()
              setToast({ tone: 'pine', message: 'Saved.' })
            }}
          />
          {uploads.cv && uploads.cv.preview && (
            <div className="textpreview textpreview-tall">
              {uploads.cv.preview}
            </div>
          )}

          {master.available && (
            <>
              <div className="tierlab" style={{ marginTop: 16 }}>Skills Claude tailors from</div>
              {Object.entries(TIER_LABELS).map(([tier, label]) => {
                const items = master.tiers[tier] || []
                if (!items.length) return null
                return (
                  <div key={tier}>
                    <div className={'tierlab t-' + TIER_TONE[tier]}>{label}</div>
                    {items.map((s) => (
                      <span className={'skill t-' + TIER_TONE[tier]} key={s.name}>
                        <b>{s.name}</b> {s.context && <em>{s.context}</em>}
                      </span>
                    ))}
                  </div>
                )
              })}
            </>
          )}
        </div>
      </Panel>

      <div className="three">
        <Panel title="Sponsorship mix" note="among jobs worth a look">
          <div className="pbody" style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
            {!kpis ? <Loading /> : (
              <>
                <Donut segments={sponsorshipSegments} />
                <Legend items={sponsorshipSegments} />
              </>
            )}
          </div>
        </Panel>

        <Panel title="Language mix" note="among jobs worth a look">
          <div className="pbody" style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
            {!kpis ? <Loading /> : (
              <>
                <Donut segments={languageSegments} />
                <Legend items={languageSegments} />
              </>
            )}
          </div>
        </Panel>

        <Panel title="Direct vs agency" note="among jobs worth a look">
          <div className="pbody" style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
            {!kpis ? <Loading /> : (
              <>
                <Donut segments={agencySegments} />
                <Legend items={agencySegments} />
              </>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Keyword coverage" note="how much of each posting's language your CV actually uses">
          <div className="pbody">
            {!kpis ? <Loading /> : (
              <>
                <div className="cards" style={{ marginBottom: 12 }}>
                  <Card
                    label="Average coverage"
                    value={kpis.keyword_coverage.average === null ? '—' : kpis.keyword_coverage.average + '%'}
                    sub={'across last ' + coverageRows.length + ' tailored CV(s)'}
                    tone={kpis.keyword_coverage.average >= 66 ? 'pine' : kpis.keyword_coverage.average >= 40 ? 'amber' : undefined}
                  />
                </div>
                <BarList rows={coverageRows} titled emptyText="Tailor a CV for a job first" />
              </>
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
