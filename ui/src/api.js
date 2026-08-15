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
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  getSettings: () => request('/settings'),
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
  rate: (id) => request('/jobs/' + id + '/rate', { method: 'POST' }),
  estimate: (id, kind) => request('/jobs/' + id + '/estimate/' + kind, { method: 'POST' }),
  mark: (id, action, reason) =>
    request('/jobs/' + id + '/mark', {
      method: 'POST',
      body: JSON.stringify({ action, reason: reason || null }),
    }),
  applications: () => request('/applications'),
  setApplicationStatus: (id, status, note) =>
    request('/applications/' + id, {
      method: 'POST',
      body: JSON.stringify({ status, note: note || null }),
    }),
  startApplication: (jobId) => request('/jobs/' + jobId + '/apply', { method: 'POST' }),
  askJob: (jobId, question, history) =>
    request('/jobs/' + jobId + '/ask', {
      method: 'POST',
      body: JSON.stringify({ question, history: history || [] }),
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
  allDocuments: () => request('/documents'),
  documents: (id) => request('/documents/' + id),
  generateCv: (id) => request('/documents/' + id + '/cv', { method: 'POST' }),
  generateLetter: (id) => request('/documents/' + id + '/letter', { method: 'POST' }),
  saveDocument: (id, kind) =>
    request('/documents/' + id + '/' + kind + '/accept', { method: 'POST' }),
  discardDocument: (id, kind) =>
    request('/documents/' + id + '/' + kind, { method: 'DELETE' }),
  downloadUrl: (id, kind) => '/api/documents/' + id + '/' + kind + '/download',
  pull: (body) =>
    request('/pull', { method: 'POST', body: JSON.stringify(body || {}) }),
}
