async function request(path, options) {
  const res = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // response was not json
    }
    // Agent sign-in failures come back as an object carrying the fix-it steps.
    // Copy those onto the Error so a catch block can offer help instead of just
    // printing a sentence; plain string details keep behaving exactly as before.
    if (detail && typeof detail === 'object') {
      const err = new Error(detail.message || res.statusText)
      Object.assign(err, detail)
      err.status = res.status
      throw err
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}

export const api = {
  getSettings: () => request('/settings'),
  agentCheck: () => request('/agent/check'),
  setAiProvider: (aiProvider) =>
    request('/settings', {
      method: 'POST',
      body: JSON.stringify({ ai_provider: aiProvider }),
    }),
  dashboard: () => request('/dashboard'),
  sources: () => request('/sources'),
  jobs: (params) => {
    const q = new URLSearchParams()
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) q.set(k, v)
    })
    const s = q.toString()
    return request('/jobs' + (s ? '?' + s : ''))
  },
  job: (id) => request('/jobs/' + id),
  search: (q, limit = 8) =>
    request('/search?q=' + encodeURIComponent(q) + '&limit=' + limit),
  pasteJob: (fields) =>
    request('/jobs/paste', { method: 'POST', body: JSON.stringify(fields) }),
  rate: (id) => request('/jobs/' + id + '/rate', { method: 'POST' }),
  estimate: (id, kind) => request('/jobs/' + id + '/estimate/' + kind, { method: 'POST' }),
  mark: (id, action, reason) =>
    request('/jobs/' + id + '/mark', {
      method: 'POST',
      body: JSON.stringify({ action, reason: reason || null }),
    }),
  applications: () => request('/applications'),
  gmailStatus: () => request('/gmail/status'),
  gmailSaveCredentials: (clientId, clientSecret) =>
    request('/gmail/credentials', {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
    }),
  gmailConnect: () => request('/gmail/connect', { method: 'POST' }),
  gmailSync: () => request('/gmail/sync', { method: 'POST' }),
  gmailSuggestions: () => request('/gmail/suggestions'),
  applyGmailSuggestion: (emailId) =>
    request('/gmail/suggestions/' + emailId + '/apply', { method: 'POST' }),
  dismissGmailSuggestion: (emailId) =>
    request('/gmail/suggestions/' + emailId + '/dismiss', { method: 'POST' }),
  setApplicationStatus: (id, status, note) =>
    request('/applications/' + id, {
      method: 'POST',
      body: JSON.stringify({ status, note: note || null }),
    }),
  startApplication: (jobId) => request('/jobs/' + jobId + '/apply', { method: 'POST' }),
  jobChat: (jobId) => request('/jobs/' + jobId + '/chat'),
  askJob: (jobId, question) =>
    request('/jobs/' + jobId + '/ask', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  masterCv: () => request('/master-cv'),
  uploadMasterCv: async (kind, file) => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/master-cv/' + kind + '/upload', { method: 'POST', body })
    if (!res.ok) {
      let detail = res.statusText
      try {
        detail = (await res.json()).detail || detail
      } catch {
        // response was not json
      }
      throw new Error(detail)
    }
    return res.json()
  },
  masterCvDownloadUrl: (kind) => '/api/master-cv/' + kind + '/download',
  discardMasterCv: (kind) => request('/master-cv/' + kind, { method: 'DELETE' }),
  extractSkills: (text) =>
    request('/skills/extract', { method: 'POST', body: JSON.stringify({ text }) }),
  saveSkills: (skills) =>
    request('/skills', { method: 'POST', body: JSON.stringify({ skills }) }),
  profileKpis: () => request('/profile/kpis'),
  skillGaps: () => request('/profile/skill-gaps'),
  refreshSkillGaps: () => request('/profile/skill-gaps/refresh', { method: 'POST' }),
  allDocuments: () => request('/documents'),
  documents: (id) => request('/documents/' + id),
  generateCv: (id) => request('/documents/' + id + '/cv', { method: 'POST' }),
  generateLetter: (id) => request('/documents/' + id + '/letter', { method: 'POST' }),
  saveDocument: (id, kind, accent) =>
    request(
      '/documents/' + id + '/' + kind + '/accept'
        + (accent ? '?accent=' + accent : ''),
      { method: 'POST' },
    ),
  discardDocument: (id, kind) =>
    request('/documents/' + id + '/' + kind, { method: 'DELETE' }),
  downloadUrl: (id, kind) => '/api/documents/' + id + '/' + kind + '/download',
  cvAccents: () => request('/documents/cv-accents'),
  exportCvUrl: (id, fmt, accent) =>
    '/api/documents/' + id + '/cv/export?fmt=' + fmt + '&accent=' + accent,
  reviewCv: (id) => request('/documents/' + id + '/cv/review', { method: 'POST' }),
  addCvHighlight: (id, text, topic) =>
    request('/documents/' + id + '/cv/highlights', {
      method: 'POST',
      body: JSON.stringify({ text, topic: topic || null }),
    }),
  pull: (body) =>
    request('/pull', { method: 'POST', body: JSON.stringify(body || {}) }),
}
