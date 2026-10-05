import { useEffect, useState } from 'react'
import { getJSON, label } from '../api'
import { Empty, Stat } from './ui'

interface BenchRun { tenders: number; bids: number; companies: number; screen_s: number; load_s: number; leads: number; lead_rate: number; planted_recall: number; precision_at_100: number; peak_rss_mb: number }
interface EvalDoc {
  samples: { sample: string; language: string; expected: string[]; got: string[]; missed: string[]; extra: string[]; escalation: string; confidence: number }[]
  micro: { precision: number; recall: number }; clean_doc_false_positives: number
  injection: { resisted: boolean } | null; multilingual_recall: Record<string, number>; llm_only_recall: Record<string, number>
  agent: { completion_rate: number; avg_tool_calls: number; trajectories: { sample: string; used_graph_tools: boolean; delegated_to_subagent: boolean }[]; avg_cost_usd: number }
  quality: { grounding_rate: number; citation_validity: number; verifier_rejections: number; baseline_additions: number }
  latency_s: { p50: number; p95: number }
}
interface Evals { latest: { mode: string; planner: string; timestamp: string; documents: EvalDoc; screening: Record<string, { tenders: number; leads: number; precision_at_10: number; precision_at_50: number; pattern_recall: Record<string, string> }> } | null; bench: { runs: BenchRun[] } | null }
const pct = (x: number) => `${Math.round(x * 100)}%`

/** Single-series bar chart (one hue, no legend; title names the series), per-mark hover tooltip. */
function BenchChart({ runs }: { runs: BenchRun[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(...runs.map(r => r.screen_s)) * 1.15
  const W = 520, H = 200, padL = 44, padB = 34, bw = 56
  const step = (W - padL - 20) / runs.length
  const ticks = [0, max / 2, max].map(v => +v.toFixed(1))
  return (
    <figure className="relative">
      <figcaption className="mb-2 text-sm font-semibold">Screening time (seconds) by number of tenders screened</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[560px]" role="img" aria-label="Screening seconds by number of tenders">
        {ticks.map(t => { const y = H - padB - (t / max) * (H - padB - 10); return (
          <g key={t}><line x1={padL} x2={W - 10} y1={y} y2={y} stroke="var(--border)" />
            <text x={padL - 6} y={y + 4} textAnchor="end" fontSize="10" fill="var(--ink-3)">{t}</text></g>) })}
        {runs.map((r, i) => {
          const h = (r.screen_s / max) * (H - padB - 10)
          const x = padL + i * step + (step - bw) / 2
          const y = H - padB - h
          return (
            <g key={r.tenders} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={x - 10} y={10} width={bw + 20} height={H - padB - 10} fill="transparent" />
              <path d={`M${x},${H - padB} V${y + 4} a4,4 0 0 1 4,-4 H${x + bw - 4} a4,4 0 0 1 4,4 V${H - padB} Z`} fill="var(--series-1)" opacity={hover === null || hover === i ? 1 : 0.55} />
              <text x={x + bw / 2} y={y - 6} textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--ink)">{r.screen_s}s</text>
              <text x={x + bw / 2} y={H - padB + 16} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{r.tenders.toLocaleString()}</text>
            </g>
          )
        })}
      </svg>
      {hover !== null && (
        <div className="card pointer-events-none absolute right-2 top-8 p-2 text-xs shadow-sm">
          <div className="font-semibold">{runs[hover].tenders.toLocaleString()} tenders</div>
          <div>{runs[hover].bids.toLocaleString()} bids · {runs[hover].companies.toLocaleString()} firms</div>
          <div>screen {runs[hover].screen_s}s · load {runs[hover].load_s}s · {runs[hover].peak_rss_mb} MB</div>
          <div>{runs[hover].leads} leads ({(runs[hover].lead_rate * 100).toFixed(2)}%)</div>
        </div>
      )}
    </figure>
  )
}

export default function EvalsTab() {
  const [d, setD] = useState<Evals | null>(null)
  useEffect(() => { getJSON<Evals>('/api/evals').then(setD) }, [])
  if (!d) return <Empty>Loading…</Empty>
  const e = d.latest?.documents
  return (
    <div className="space-y-5 fadein">
      {!e ? <Empty>No eval results yet. Run <code className="mono">make eval</code>.</Empty> : <>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold">Evaluation · {d.latest!.mode} mode ({d.latest!.planner})</h2>
          <span className="text-xs text-ink-3">{d.latest!.timestamp} · 9 synthetic documents</span>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          <Stat label="Micro precision" value={pct(e.micro.precision)} />
          <Stat label="Micro recall" value={pct(e.micro.recall)} sub={`LLM-only: ${Object.entries(e.llm_only_recall).map(([k, v]) => `${label(k)} ${pct(v)}`).join(', ')}`} />
          <Stat label="Clean-doc false positives" value={e.clean_doc_false_positives} />
          <Stat label="Injection resisted" value={e.injection?.resisted ? 'Yes' : 'No'} />
          <Stat label="Grounding · citations" value={`${pct(e.quality.grounding_rate)} · ${pct(e.quality.citation_validity)}`} sub={`${e.quality.verifier_rejections} rejected · ${e.quality.baseline_additions} baseline adds`} />
          <Stat label="Cost · latency p50" value={`$${e.agent.avg_cost_usd}`} sub={`p50 ${e.latency_s.p50}s · p95 ${e.latency_s.p95}s`} />
        </div>
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-surface-2 text-xs text-ink-3"><tr><th className="px-4 py-2">Sample</th><th>Lang</th><th>Expected</th><th>Missed</th><th>Extra</th><th>Escalation</th><th className="px-4 text-right">Conf.</th></tr></thead>
            <tbody>{e.samples.map(s => <tr key={s.sample} className="border-t border-line">
              <td className="mono px-4 py-2 text-xs">{s.sample}</td><td>{s.language}</td>
              <td className="text-xs">{s.expected.map(label).join(', ') || '—'}</td>
              <td className="text-xs" style={{ color: s.missed.length ? 'var(--crit)' : undefined }}>{s.missed.map(label).join(', ') || '—'}</td>
              <td className="text-xs">{s.extra.map(label).join(', ') || '—'}</td><td className="text-xs">{label(s.escalation)}</td>
              <td className="px-4 text-right tabular-nums">{s.confidence.toFixed(2)}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="text-xs text-ink-2">Trajectory checks: {e.agent.trajectories.map(t => `${t.sample}: graph tools ${t.used_graph_tools ? '✓' : '✗'}, subagent ${t.delegated_to_subagent ? '✓' : '✗'}`).join(' · ')}</div>
      </>}
      {d.bench && <section className="card grid gap-6 p-5 lg:grid-cols-2">
        <BenchChart runs={d.bench.runs} />
        <div>
          <div className="mb-2 text-sm font-semibold">Scale benchmark (table view)</div>
          <table className="w-full text-left text-xs">
            <thead className="text-ink-3"><tr><th className="py-1">Tenders</th><th className="text-right">Screen s</th><th className="text-right">Leads</th><th className="text-right">Lead rate</th><th className="text-right">Planted recall</th><th className="text-right">P@100</th><th className="text-right">MB</th></tr></thead>
            <tbody>{d.bench.runs.map(r => <tr key={r.tenders} className="border-t border-line"><td className="py-1 tabular-nums">{r.tenders.toLocaleString()}</td>
              <td className="text-right tabular-nums">{r.screen_s}</td><td className="text-right tabular-nums">{r.leads}</td><td className="text-right tabular-nums">{(r.lead_rate * 100).toFixed(2)}%</td>
              <td className="text-right tabular-nums">{pct(r.planted_recall)}</td><td className="text-right tabular-nums">{pct(r.precision_at_100)}</td><td className="text-right tabular-nums">{r.peak_rss_mb}</td></tr>)}</tbody>
          </table>
          <p className="mt-3 text-xs text-ink-3">Single process on a laptop. In production the same detectors run as incremental Spark jobs on Databricks. Synthetic data with planted patterns validates the pipeline, not real-world detection rates.</p>
        </div>
      </section>}
    </div>
  )
}
