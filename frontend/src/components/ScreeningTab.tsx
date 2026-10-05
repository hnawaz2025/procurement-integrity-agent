import { useEffect, useState } from 'react'
import { fmtUSD, getJSON, label, postJSON } from '../api'
import type { Lead } from '../types'
import { Empty, Stat } from './ui'

interface Screening {
  funnel: { tenders_screened: number; with_any_signal: number; leads: number; agent_queue: number; timings: { total_s: number } }
  leads: Lead[]
  groups: { rotation: { members: string[]; n_ring_tenders: number; stable_cover: boolean; cover_ratio_std: number }[];
    concentration: { supplier: string; entity: string; share: number; lift: number }[];
    splitting: { supplier: string; entity: string; n_contracts: number }[]; hidden_links: number }
  cost_projection: {
    contracts_per_year: number; per_review_cost_usd: number; cost_basis: string; assumptions: string
    agent_on_everything: { llm_reviews: number; llm_cost_usd: number; human_hours_if_all_reviewed: number }
    funnel: { screening_compute_seconds: number; leads: number; lead_rate: number; llm_cost_usd: number; human_hours: number }
  }
}
type BatchItem = { status: string; review_id?: string; overall_risk?: string; flags?: number; categories?: string[]; error?: string }

export default function ScreeningTab({ onInvestigate }: { onInvestigate: (tenderId: string) => void }) {
  const [d, setD] = useState<Screening | null>(null)
  const [err, setErr] = useState('')
  const [batch, setBatch] = useState<{ id: string; items: Record<string, BatchItem> } | null>(null)

  useEffect(() => { postJSON<Screening>('/api/screening/run?top=25').then(setD).catch(e => setErr(String(e))) }, [])
  useEffect(() => {
    if (!batch || Object.values(batch.items).every(i => i.status === 'done' || i.status === 'error')) return
    const t = setTimeout(() => getJSON<{ batch_id: string; items: Record<string, BatchItem> }>(`/api/batch/${batch.id}`)
      .then(b => setBatch({ id: b.batch_id, items: b.items })), 1200)
    return () => clearTimeout(t)
  }, [batch])

  if (err) return <Empty>Could not load screening: {err}</Empty>
  if (!d) return <Empty>Screening all tenders…</Empty>
  const f = d.funnel
  const stages = [
    { k: 'All tenders screened', v: f.tenders_screened, note: `deterministic rules + patterns · ${f.timings.total_s}s` },
    { k: 'With any risk signal', v: f.with_any_signal, note: 'single weak signals stay here' },
    { k: 'Leads (risk weight ≥ 2)', v: f.leads, note: 'ranked by risk × log(value)' },
    { k: 'Agent investigation queue', v: f.agent_queue, note: 'top-k leads only' },
  ]
  const cp = d.cost_projection
  const startBatch = async () => {
    const b = await postJSON<{ batch_id: string; items: Record<string, BatchItem> }>('/api/batch', { top_k: 3 })
    setBatch({ id: b.batch_id, items: b.items })
  }

  return (
    <div className="space-y-5 fadein">
      <section className="card p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">Review funnel</h2>
            <p className="text-sm text-ink-2">Screen every contract cheaply; spend agent and reviewer time only where risk × exposure is highest.</p>
          </div>
          <span className="chip">synthetic corpus · {f.tenders_screened.toLocaleString()} tenders</span>
        </div>
        <ol className="mt-5 space-y-2.5" aria-label="Funnel stages">
          {stages.map((s, i) => {
            const w = Math.max(4, Math.sqrt(s.v / stages[0].v) * 100)
            return (
              <li key={s.k} className="grid grid-cols-[minmax(130px,220px)_1fr] items-center gap-3 sm:grid-cols-[220px_1fr_200px]">
                <div className="text-[13px] font-medium">{i + 1}. {s.k}</div>
                <div className="h-7 rounded-md bg-surface-2">
                  <div className="flex h-7 items-center rounded-md px-2 text-[13px] font-semibold text-white"
                    style={{ width: `${w}%`, background: 'var(--series-1)', minWidth: 48 }}>{s.v.toLocaleString()}</div>
                </div>
                <div className="hidden text-xs text-ink-3 sm:block">{s.note}</div>
              </li>
            )
          })}
          <li className="grid grid-cols-[minmax(130px,220px)_1fr] items-center gap-3 sm:grid-cols-[220px_1fr_200px]">
            <div className="text-[13px] font-medium">5. Human reviewer decision</div>
            <div className="text-[13px] text-ink-2">accept / reject / needs info → recorded in hash-chained audit log, feeds threshold tuning</div>
          </li>
        </ol>
        <p className="mt-3 text-xs text-ink-3">Bar length uses a square-root scale so small stages stay visible; exact counts are printed on each bar.</p>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="card p-5">
          <div className="label">Projection · {cp.contracts_per_year.toLocaleString()} contracts / year (illustrative)</div>
          <div className="mt-3 grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm font-semibold">Agent on every contract</div>
              <div className="mt-1 text-2xl font-semibold">{fmtUSD(cp.agent_on_everything.llm_cost_usd)}</div>
              <div className="text-xs text-ink-3">LLM cost · {cp.agent_on_everything.human_hours_if_all_reviewed.toLocaleString()} reviewer-hours</div>
            </div>
            <div>
              <div className="text-sm font-semibold">Screening funnel</div>
              <div className="mt-1 text-2xl font-semibold" style={{ color: 'var(--good)' }}>{fmtUSD(cp.funnel.llm_cost_usd)}</div>
              <div className="text-xs text-ink-3">{cp.funnel.leads.toLocaleString()} leads ({(cp.funnel.lead_rate * 100).toFixed(2)}%) · {cp.funnel.human_hours.toLocaleString()} reviewer-hours · screening {cp.funnel.screening_compute_seconds}s</div>
            </div>
          </div>
          <p className="mt-3 text-xs text-ink-3">Per-review cost ${cp.per_review_cost_usd} · {cp.cost_basis}. {cp.assumptions}.</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Rotation rings" value={d.groups.rotation.filter(g => g.stable_cover).length}
            sub={`${d.groups.rotation.filter(g => !g.stable_cover).length} thin-market group(s) down-weighted`} />
          <Stat label="Hidden links" value={d.groups.hidden_links} sub="co-bidders sharing identity attributes" />
          <Stat label="Concentration" value={d.groups.concentration.length} sub={d.groups.concentration[0] ? `${d.groups.concentration[0].supplier} at ${d.groups.concentration[0].entity}` : '—'} />
          <Stat label="Split series" value={d.groups.splitting.length} sub={d.groups.splitting[0] ? `${d.groups.splitting[0].n_contracts} awards · ${d.groups.splitting[0].supplier}` : '—'} />
        </div>
      </section>

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line p-4">
          <div>
            <h2 className="text-base font-semibold">Ranked lead queue</h2>
            <p className="text-xs text-ink-3">Each lead explains why it ranks. Investigate one interactively, or batch the top three.</p>
          </div>
          <button className="btn" onClick={startBatch} disabled={!!batch && Object.values(batch.items).some(i => i.status !== 'done' && i.status !== 'error')}>
            Batch-investigate top 3
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-surface-2 text-xs text-ink-3">
              <tr><th className="px-4 py-2">#</th><th className="px-2 py-2">Tender</th><th className="px-2 py-2">Entity / winner</th>
                <th className="px-2 py-2 text-right">Value</th><th className="px-2 py-2 text-right">Score</th><th className="px-2 py-2">Why</th><th className="px-4 py-2"></th></tr>
            </thead>
            <tbody>
              {d.leads.map((l, i) => {
                const b = batch?.items[l.tender_id]
                return (
                  <tr key={l.tender_id} className="border-t border-line align-top hover:bg-surface-2">
                    <td className="px-4 py-2.5 text-ink-3">{i + 1}</td>
                    <td className="px-2 py-2.5"><div className="mono text-xs">{l.tender_id}</div><div className="text-xs text-ink-3">{l.published} · {l.sector}</div></td>
                    <td className="px-2 py-2.5"><div>{l.entity}</div><div className="text-xs text-ink-3">{l.winner}</div></td>
                    <td className="px-2 py-2.5 text-right tabular-nums">{fmtUSD(l.contract_value)}</td>
                    <td className="px-2 py-2.5 text-right font-semibold tabular-nums">{l.lead_score.toFixed(1)}</td>
                    <td className="px-2 py-2.5"><div className="flex max-w-[360px] flex-wrap gap-1">{l.signals.map(s => <span key={s} className="chip">{label(s)}</span>)}</div>
                      {b && <div className="mt-1 text-xs text-ink-2">{b.status === 'done' ? `✓ reviewed ${b.review_id} · ${b.overall_risk} · ${b.flags} flag(s)` : b.status === 'error' ? `error: ${b.error}` : `${b.status}…`}</div>}
                    </td>
                    <td className="px-4 py-2.5 text-right"><button className="btn" onClick={() => onInvestigate(l.tender_id)}>Investigate →</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
