// Single seam the whole UI reads through. When VITE_MOCK=1 it resolves from
// devMock instead of the network, so the identical components render with the
// database down. In every other case it calls /api/*, which in production is the
// same origin (FastAPI serves this bundle) and in dev is the Vite proxy.
import { mockResponse, classify as mockClassify } from './devMock'

export const IS_MOCK = import.meta.env.VITE_MOCK === '1'

async function request(path, opts) {
  if (IS_MOCK && (!opts || opts.method === undefined || opts.method === 'GET')) {
    return mockResponse(path)
  }
  const res = await fetch(path, opts)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { detail = (await res.json()).detail || detail } catch { /* keep status */ }
    throw new Error(detail)
  }
  return res.json()
}

export function getJSON(path) {
  return request(`/api${path}`)
}

export function postJSON(path, body) {
  return request(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function postForm(path, formData) {
  return request(`/api${path}`, { method: 'POST', body: formData })
}

// /api/classify is a plain JSON POST; in mock mode we run the JS mirror locally
// rather than round-tripping a server that may not exist.
export async function classify(text) {
  if (IS_MOCK) return mockClassify(text)
  return postJSON('/classify', { text })
}
