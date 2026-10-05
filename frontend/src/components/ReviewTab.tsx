import { useEffect, useMemo, useState } from 'react'
import { getJSON, label, streamReview } from '../api'
import type { Retrieved, ReviewResult, Sample, Severity, TraceStep } from '../types'
import FlagCard from './FlagCard'
import NetworkGraph from './NetworkGraph'
import Trace from './Trace'
import { Empty, SevPill, Tabs } from './ui'

type RTab = 'summary' | 'flags' | 'network' | 'questions' | 'audit' | 'json'
const HL: Record<Severity, string> = { high: 'var(--hl-high)', medium: 'var(--hl-medium)', low: 'var(--hl-low)' }
const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase()

function Gauge({ r }: { r: ReviewResult }) {
  const b = r.confidence_breakdown
  const parts: [string, number][] = [['Grounding', b.grounding], ['Citations valid', b.citation_validity],
    ['Retrieval strength', b.retrieval_strength], ['Agent-rule agreement', b.signal_agreement], ['Coverage', b.coverage]]
  return (
    <div className="card p-4">
      <div className="flex items-baseline justify-between"><div className="label">Computed confidence</div>
        <div className="text-2xl font-semibold tabular-nums">{(r.confidence * 100).toFixed(0)}%</div></div>
      <div className="mt-2 space-y-1.5">
        {parts.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[130px_1fr_36px] items-center gap-2 text-xs" title={`${k}: ${(v * 100).toFixed(0)}%`}>
            <span className="text-ink-2">{k}</span>
            <span className="h-1.5 rounded-full bg-surface-2"><span className="block h-1.5 rounded-full" style={{ width: `${v * 100}%`, background: 'var(--series-1)' }} /></span>
            <span className="text-right tabular-nums text-ink-3">{(v * 100).toFixed(0)}</span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-ink-3">Derived from verifiable properties of the review, not the model's self-assessment.</p>
    </div>
  )
}

function KbModal({ chunk, onClose }: { chunk: Retrieved | null; onClose: () => void }) {
  if (!chunk) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="card max-w-lg p-5" onClick={e => e.stopPropagation()} role="dialog" aria-label={chunk.title}>
        <div className="mono text-xs text-ink-3">{chunk.id}</div>
        <h3 className="mt-1 text-base font-semibold">{chunk.title}</h3>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{chunk.text}</p>
        <div className="mt-3 text-xs text-ink-3">Source: {chunk.url ? <a className="underline" href={chunk.url} target="_blank" rel="noreferrer">{chunk.source}</a> : chunk.source}</div>
        <div className="mt-4 text-right"><button className="btn" onClick={onClose}>Close</button></div>
      </div>
    </div>
  )
}

function CitedText({ text, onCite }: { text: string; onCite: (id: string) => void }) {
  const parts = text.split(/(\[KB-\d+\])/g)
  return <p className="text-[14px] leading-relaxed">{parts.map((p, i) => /^\[KB-\d+\]$/.test(p)
    ? <button key={i} onClick={() => onCite(p.slice(1, -1))} className="chip mx-0.5 align-middle hover:border-accent">{p.slice(1, -1)}</button> : <span key={i}>{p}</span>)}</p>
}

function DocView({ r }: { r: ReviewResult }) {
  const quotes = r.flags.filter(f => f.evidence_quote).map(f => ({ q: norm(f.evidence_quote!), f }))
  return (
    <pre className="mono max-h-[560px] overflow-auto whitespace-pre-wrap p-3 text-[11.5px] leading-relaxed">
      {r.redacted_document.split('\n').map((ln, i) => {
        const hit = quotes.filter(x => x.q && (norm(ln).includes(x.q) || x.q.includes(norm(ln)) && norm(ln).length > 12))
        if (!hit.length) return <div key={i}>{ln || ' '}</div>
        const sev = hit.some(h => h.f.severity === 'high') ? 'high' : hit.some(h => h.f.severity === 'medium') ? 'medium' : 'low'
        return <div key={i} style={{ background: HL[sev as Severity] }} className="rounded-sm" title={hit.map(h => `${h.f.id}: ${h.f.title}`).join('\n')}>
          {ln}<span className="ml-2 text-[10px] font-semibold text-ink-2">{hit.map(h => h.f.id).join(' ')}</span></div>
      })}
    </pre>
  )
}

function AuditView({ r }: { r: ReviewResult }) {
  const [entries, setEntries] = useState<{ kind: string; ts: string; hash: string; payload: Record<string, unknown> }[]>([])
  useEffect(() => { getJSON<typeof entries>(`/api/audit/${r.review_id}`).then(setEntries).catch(() => setEntries([])) }, [r.review_id])
  return (
    <div className="space-y-4 text-[13px]">
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="card p-3"><div className="label">Input SHA-256</div><div className="mono mt-1 break-all text-xs">{r.input_sha256}</div></div>
        <div className="card p-3"><div className="label">Audit entry hash</div><div className="mono mt-1 break-all text-xs">{r.audit_hash}</div></div>
      </div>
      <div className="card p-3 text-xs">
        <div className="label mb-1">Models &amp; usage</div>
        <div className="flex flex-wrap gap-1">{Object.entries(r.models).map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}</div>
        <div className="mt-2 text-ink-2">{r.usage.input_tokens.toLocaleString()} input · {r.usage.output_tokens.toLocaleString()} output · {r.usage.cache_read_tokens.toLocaleString()} cache-read tokens · ${r.usage.cost_usd.toFixed(4)}</div>
      </div>
      <div>
        <div className="label mb-1">Retrieved guidance</div>
        <table className="w-full text-left text-xs"><thead className="text-ink-3"><tr><th className="py-1">Chunk</th><th>Title</th><th className="text-right">RRF</th><th className="text-right">BM25</th><th className="text-right">Cosine</th></tr></thead>
          <tbody>{r.retrieved.map(c => <tr key={c.id} className="border-t border-line"><td className="mono py-1">{c.id}</td><td>{c.title}</td>
            <td className="text-right tabular-nums">{c.rrf}</td><td className="text-right tabular-nums">{c.bm25}</td><td className="text-right tabular-nums">{c.cosine ?? '—'}</td></tr>)}</tbody></table>
      </div>
      <div>
        <div className="label mb-1">Guardrail events</div>
        {r.guardrail_events.length ? r.guardrail_events.map((g, i) => <div key={i} className="text-xs"><SevPill s={g.severity} /> <strong>{label(g.kind)}</strong>: {g.detail}</div>) : <div className="text-xs text-ink-3">none</div>}
      </div>
      {(r.rejected_flags.length > 0 || r.dismissals.length > 0) && <div>
        <div className="label mb-1">Verifier rejections &amp; dismissals</div>
        {r.rejected_flags.map((x, i) => <div key={i} className="text-xs">✗ {x.flag.title}: {x.reasons.join('; ')}</div>)}
        {r.dismissals.map((d, i) => <div key={i} className="text-xs">⊘ {d.signal_id}: {d.reason}</div>)}
      </div>}
      <div>
        <div className="label mb-1">Hash-chained audit entries</div>
        {entries.map((e, i) => <div key={i} className="flex gap-2 border-t border-line py-1 text-xs"><span className="chip">{e.kind}</span><span className="text-ink-3">{e.ts.slice(0, 19)}</span>
          <span className="mono truncate text-ink-3">{e.hash.slice(0, 16)}…</span>{e.kind === 'decision' && <span>{String(e.payload.flag_id)} → {String(e.payload.decision)}</span>}</div>)}
      </div>
    </div>
  )
}

export default function ReviewTab({ initialDoc, initialLabel, autoRun, autoSample, autoTab }: {
  initialDoc?: string; initialLabel?: string; autoRun?: number; autoSample?: string; autoTab?: string }) {
  const [samples, setSamples] = useState<Sample[]>([])
  const [sel, setSel] = useState('')
  const [doc, setDoc] = useState('')
  const [steps, setSteps] = useState<TraceStep[]>([])
  const [res, setRes] = useState<ReviewResult | null>(null)
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState('')
  const [tab, setTab] = useState<RTab>('summary')
  const [view, setView] = useState<'edit' | 'evidence'>('edit')
  const [kb, setKb] = useState<Retrieved | null>(null)
  const [fresh, setFresh] = useState(false)

  useEffect(() => { getJSON<Sample[]>('/api/samples').then(setSamples) }, [])
  useEffect(() => { // deep link: ?tab=review&sample=08_looks_clean_carretera_es&rtab=network
    if (!autoSample) return
    getJSON<{ document: string }>(`/api/samples/${autoSample}`).then(async s => {
      setSel(autoSample); setDoc(s.document); await run(s.document); if (autoTab) setTab(autoTab as RTab)
    })
  }, [autoSample]) // eslint-disable-line react-hooks/exhaustive-deps
  const pick = async (id: string) => {
    setSel(id)
    if (id) { const s = await getJSON<{ document: string }>(`/api/samples/${id}`); setDoc(s.document); setRes(null); setSteps([]); setView('edit') }
  }
  const run = async (d = doc) => {
    setRunning(true); setErr(''); setRes(null); setSteps([]); setTab('summary')
    await streamReview(d, !fresh, s => setSteps(p => [...p, s]), r => { setRes(r); setView('evidence'); if (r.cached) setSteps(r.trace) }, setErr)
    setRunning(false)
  }
  useEffect(() => { if (initialDoc) { setDoc(initialDoc); setSel(''); run(initialDoc) } }, [autoRun]) // eslint-disable-line react-hooks/exhaustive-deps

  const cite = async (id: string) => setKb(res?.retrieved.find(c => c.id === id) ?? await getJSON<Retrieved>(`/api/kb/${id}`))
  const paths = useMemo(() => res?.flags.filter(f => f.graph_path).map(f => f.graph_path!) ?? [], [res])
  const current = samples.find(s => s.id === sel)

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(320px,1fr)_minmax(300px,0.85fr)_minmax(380px,1.25fr)]">
      {/* input */}
      <section className="card flex min-h-[640px] flex-col overflow-hidden">
        <div className="space-y-2 border-b border-line p-4">
          <div className="text-sm font-semibold">Document under review</div>
          <select value={sel} onChange={e => pick(e.target.value)} className="w-full rounded-md border border-line bg-surface px-2 py-2 text-[13px]">
            <option value="">{initialLabel && !sel ? initialLabel : 'Choose a synthetic sample…'}</option>
            {samples.map(s => <option key={s.id} value={s.id}>{s.id.slice(0, 2)} · {s.title} ({s.language})</option>)}
          </select>
          {current && <div className="text-xs text-ink-3">Ground truth: {current.expected.length ? current.expected.map(label).join(', ') : 'no signals (clean)'}</div>}
          <div className="flex items-center gap-2">
            <button className="btn btn-primary" onClick={() => run()} disabled={running || doc.trim().length < 50}>{running ? 'Investigating…' : 'Run agent review'}</button>
            <label className="flex items-center gap-1.5 text-xs text-ink-2"><input type="checkbox" checked={fresh} onChange={e => setFresh(e.target.checked)} />bypass cache</label>
            {res && <div className="ml-auto flex rounded-md border border-line text-xs">
              {(['edit', 'evidence'] as const).map(v => <button key={v} onClick={() => setView(v)} className={`px-2 py-1 ${view === v ? 'bg-surface-2 font-semibold' : 'text-ink-3'}`}>{v === 'edit' ? 'Source' : 'Evidence'}</button>)}
            </div>}
          </div>
        </div>
        {view === 'evidence' && res ? <DocView r={res} /> :
          <textarea value={doc} onChange={e => setDoc(e.target.value)} spellCheck={false}
            placeholder="Paste a procurement document (bid evaluation report, award memo…), or choose a sample above."
            className="mono flex-1 resize-none bg-surface p-3 text-[11.5px] leading-relaxed outline-none" />}
        {view === 'evidence' && res && <div className="border-t border-line px-3 py-2 text-[11px] text-ink-3">Shown as the model saw it: identifiers pseudonymised ([PHONE_1]…). Highlighted lines are verified evidence.</div>}
      </section>

      {/* trace */}
      <section className="card min-h-[640px] overflow-hidden xl:max-h-[calc(100vh-170px)]">
        {steps.length ? <Trace steps={steps} running={running} /> : <Empty>The agent's plan, tool calls, subagent delegation, verifier and scoring stream here.</Empty>}
      </section>

      {/* result */}
      <section className="card min-h-[640px] overflow-hidden">
        {err && <div className="m-4 rounded-md border p-3 text-[13px]" style={{ borderColor: 'var(--crit)' }}>Error: {err}</div>}
        {!res ? <Empty>{running ? 'Waiting for the verified result…' : 'Results appear here after verification.'}</Empty> : (
          <div className="flex h-full flex-col">
            <div className="space-y-2 border-b border-line p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold">Overall</span><SevPill s={res.overall_risk} />
                <span className="chip" style={{ borderColor: res.escalation === 'priority_review' ? 'var(--crit)' : undefined }}>
                  {res.escalation === 'priority_review' ? '⚑ Priority human review' : 'Standard human review'}</span>
                {res.cached && <span className="chip">cached result</span>}
                <span className="ml-auto mono text-[11px] text-ink-3">{res.review_id}</span>
              </div>
              {res.escalation_reasons.length > 0 && <div className="text-xs text-ink-2">Escalated because: {res.escalation_reasons.join('; ')}</div>}
            </div>
            <div className="px-4"><Tabs<RTab> value={tab} onChange={setTab} counts={{ flags: res.flags.length, questions: res.human_review_questions.length }}
              tabs={[{ id: 'summary', label: 'Summary' }, { id: 'flags', label: 'Flags' }, { id: 'network', label: 'Network' },
                { id: 'questions', label: 'Reviewer questions' }, { id: 'audit', label: 'Audit' }, { id: 'json', label: 'JSON' }]} /></div>
            <div className="flex-1 overflow-y-auto p-4">
              {tab === 'summary' && <div className="space-y-4"><CitedText text={res.summary} onCite={cite} /><Gauge r={res} />
                <div className="text-xs text-ink-3">Planner: {res.planner} · {res.flags.length} verified flag(s) · {res.rejected_flags.length} rejected by verifier · {res.dismissals.length} dismissed</div></div>}
              {tab === 'flags' && (res.flags.length ? <div className="space-y-3">{res.flags.map(f => <FlagCard key={f.id} f={f} reviewId={res.review_id} onCite={cite} />)}</div>
                : <Empty>No risk signals found. A clean result still requires human sign-off.</Empty>)}
              {tab === 'network' && <NetworkGraph entities={res.network_entities} highlight={paths} />}
              {tab === 'questions' && <ol className="list-decimal space-y-2 pl-5 text-[14px]">{res.human_review_questions.map((q, i) => <li key={i}>{q}</li>)}</ol>}
              {tab === 'audit' && <AuditView r={res} />}
              {tab === 'json' && <pre className="mono overflow-x-auto whitespace-pre-wrap text-[11px]">{JSON.stringify({ ...res, trace: `[${res.trace.length} steps]`, redacted_document: '[omitted]' }, null, 2)}</pre>}
            </div>
          </div>
        )}
      </section>
      <KbModal chunk={kb} onClose={() => setKb(null)} />
    </div>
  )
}
