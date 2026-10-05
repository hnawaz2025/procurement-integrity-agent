import type { ReviewResult, TraceStep } from './types'

export async function getJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json() as Promise<T>
}

export const postJSON = <T,>(url: string, body?: unknown) =>
  getJSON<T>(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })

/** POST /api/review and parse the Server-Sent Events stream (fetch-based; EventSource is GET-only). */
export async function streamReview(document: string, useCache: boolean, onStep: (s: TraceStep) => void,
  onResult: (r: ReviewResult) => void, onError: (e: string) => void) {
  const resp = await fetch('/api/review', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ document, use_cache: useCache }),
  })
  if (!resp.ok || !resp.body) { onError(`${resp.status} ${await resp.text()}`); return }
  const reader = resp.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const parts = buf.split(/\r?\n\r?\n/)
    buf = parts.pop() ?? ''
    for (const p of parts) {
      const data = p.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).join('\n')
      if (!data) continue
      const e = JSON.parse(data)
      if (e.type === 'step') onStep(e.step)
      else if (e.type === 'result') onResult(e.result)
      else if (e.type === 'error') onError(e.error)
    }
  }
}

export const fmtUSD = (v: number) => v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}k` : `$${v.toFixed(0)}`
export const label = (s: string) => s.replace(/_/g, ' ')
