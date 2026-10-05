import { useState } from 'react'
import { label, postJSON } from '../api'
import type { RiskFlag } from '../types'
import { SevPill } from './ui'

const ORIGIN: Record<RiskFlag['origin'], string> = { rule: 'deterministic rule', pattern: 'corpus pattern', llm: 'agent judgement', both: 'agent + rule' }

export default function FlagCard({ f, reviewId, onCite }: { f: RiskFlag; reviewId: string; onCite: (id: string) => void }) {
  const [decision, setDecision] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const decide = async (d: 'accept' | 'reject' | 'needs_info') => {
    await postJSON(`/api/reviews/${reviewId}/decision`, { flag_id: f.id, decision: d, note })
    setDecision(d)
  }
  const baseline = f.rationale.includes('baseline guarantee')
  return (
    <article className="card p-4 fadein">
      <div className="flex flex-wrap items-center gap-1.5">
        <SevPill s={f.severity} />
        <span className="chip">{label(f.category)}</span>
        {f.practice_hint !== 'unclear' && <span className="chip" title="Which sanctionable-practice definition this indicator relates to">relates to: {f.practice_hint}</span>}
        <span className="chip">{ORIGIN[f.origin]}</span>
        {baseline && <span className="chip" title="Added by the verifier because the agent did not address a deterministic signal">baseline guarantee</span>}
        <span className="ml-auto mono text-[11px] text-ink-3">{f.id}</span>
      </div>
      <h3 className="mt-2 text-[15px] font-semibold">{f.title}</h3>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{f.rationale}</p>
      {f.evidence_quote && (
        <blockquote className="mono mt-2 overflow-x-auto rounded-md border-l-4 bg-surface-2 px-3 py-2 text-xs" style={{ borderColor: 'var(--series-1)' }}>
          {f.evidence_quote}
        </blockquote>
      )}
      {f.graph_path && (
        <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
          {f.graph_path.map((n, i) => (
            <span key={i} className="flex items-center gap-1">
              <span className="chip" style={n.startsWith('shell') ? { borderColor: 'var(--crit)' } : undefined}>{n}</span>
              {i < f.graph_path!.length - 1 && <span className="text-ink-3">→</span>}
            </span>
          ))}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-ink-3">
        Guidance: {f.citations.map(c => <button key={c} onClick={() => onCite(c)} className="chip hover:border-accent">{c}</button>)}
        {f.signal_refs.length > 0 && <span className="ml-2">signals: {f.signal_refs.join(', ')}</span>}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        {decision ? (
          <span className="text-[13px]">Reviewer decision recorded: <strong>{label(decision)}</strong> <span className="text-ink-3">(appended to audit log)</span></span>
        ) : (
          <>
            <input value={note} onChange={e => setNote(e.target.value)} placeholder="Reviewer note (optional)"
              className="min-w-40 flex-1 rounded-md border border-line bg-surface px-2 py-1.5 text-[13px]" />
            <button className="btn" onClick={() => decide('accept')}>Accept</button>
            <button className="btn" onClick={() => decide('needs_info')}>Needs info</button>
            <button className="btn" onClick={() => decide('reject')}>Reject</button>
          </>
        )}
      </div>
    </article>
  )
}
