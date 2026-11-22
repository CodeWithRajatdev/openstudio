export class ApiError extends Error {
  constructor(message, extra = {}) {
    super(message)
    this.name = 'ApiError'
    Object.assign(this, extra)
  }
}

function shape(ok, status, body) {
  if (!ok) {
    let detail = body?.detail ?? `Request failed (${status})`
    if (Array.isArray(detail)) detail = detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
    throw new ApiError(detail, {
      status, suggestions: body?.suggestions || [], failedWords: body?.failed_words || [],
    })
  }
  return body
}

async function parse(res) {
  let body = null
  try { body = await res.json() } catch { /* not JSON */ }
  return shape(res.ok, res.status, body)
}

const wsPath = (path) =>
  path.startsWith('/api/wordsearch/') ? path : path.replace(/^\/api\//, '/api/wordsearch/')

export const api = {
  get: (path, signal) => fetch(wsPath(path), { signal }).then(parse),
  post: (path, data, signal) =>
    fetch(wsPath(path), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data ?? {}), signal
    }).then(parse),
  // XMLHttpRequest (not fetch) so the browser can report upload progress.
  upload: (path, form, onProgress) => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', wsPath(path))
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100)) }
    xhr.onload = () => {
      let body = null
      try { body = JSON.parse(xhr.responseText) } catch { /* not JSON */ }
      try { resolve(shape(xhr.status >= 200 && xhr.status < 300, xhr.status, body)) } catch (e) { reject(e) }
    }
    xhr.onerror = () => reject(new ApiError('Could not reach the server. Is it running?'))
    xhr.send(form)
  }),
}

export const jobPayloadChapters = (chapters) =>
  chapters.map((chapter, index) => ({
    index,
    title: chapter.title,
    words: chapter.words.map((w) => w.text),
  }))
