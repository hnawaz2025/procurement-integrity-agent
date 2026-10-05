import { useEffect, useState } from 'react'
import { getJSON } from './api'
import EvalsTab from './components/EvalsTab'
import ReviewTab from './components/ReviewTab'
import ScreeningTab from './components/ScreeningTab'
import { HumanReviewBanner, Tabs } from './components/ui'
import type { Health } from './types'

type Tab = 'screening' | 'review' | 'evals'

export default function App() {
  const params = new URLSearchParams(window.location.search)
  const [tab, setTab] = useState<Tab>((params.get('tab') as Tab) || 'screening')
  const [health, setHealth] = useState<Health | null>(null)
  const [lead, setLead] = useState<{ doc: string; label: string; n: number } | null>(null)
  useEffect(() => { getJSON<Health>('/api/health').then(setHealth).catch(() => setHealth(null)) }, [])

  const investigate = async (tenderId: string) => {
    const d = await getJSON<{ document: string }>(`/api/leads/${tenderId}/document`)
    setLead(p => ({ doc: d.document, label: `Lead ${tenderId} (from screening)`, n: (p?.n ?? 0) + 1 }))
    setTab('review')
  }

  return (
    <div className="min-h-screen">
      <HumanReviewBanner />
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-3 px-4 py-3">
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <div className="min-w-0">
            <h1 className="text-[17px] font-semibold tracking-tight">Procurement Integrity Review Agent</h1>
            <p className="text-xs text-ink-3">Screening funnel · agentic investigation · human-in-the-loop · prototype on synthetic data</p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            {health ? <>
              <span className="chip" style={{ borderColor: health.mode === 'claude' ? 'var(--good)' : undefined }}>
                <span aria-hidden style={{ color: health.mode === 'claude' ? 'var(--good)' : 'var(--ink-3)' }}>●</span>
                {health.mode === 'claude' ? `Claude agent · ${health.models.orchestrator}` : 'Offline · planner: scripted'}
              </span>
              <span className="chip">{health.retrieval.split(' (')[0]} retrieval · {health.kb_chunks} KB chunks</span>
              <span className="chip">audit chain {health.audit.valid ? 'verified ✓' : 'BROKEN ✗'}</span>
            </> : <span className="chip">API offline: start the backend on :8000</span>}
          </div>
        </div>
        <div className="mx-auto max-w-[1500px] px-4">
          <Tabs<Tab> value={tab} onChange={setTab} tabs={[
            { id: 'screening', label: '1 · Portfolio screening' }, { id: 'review', label: '2 · Agent review' }, { id: 'evals', label: '3 · Evals & scale' }]} />
        </div>
      </header>
      <main className="mx-auto max-w-[1500px] px-4 py-5">
        <div hidden={tab !== 'screening'}><ScreeningTab onInvestigate={investigate} /></div>
        <div hidden={tab !== 'review'}><ReviewTab initialDoc={lead?.doc} initialLabel={lead?.label} autoRun={lead?.n}
          autoSample={params.get('sample') ?? undefined} autoTab={params.get('rtab') ?? undefined} /></div>
        {tab === 'evals' && <EvalsTab />}
      </main>
    </div>
  )
}
