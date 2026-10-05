import { useEffect, useRef, useState } from 'react'
import type { TraceStep } from '../types'

const KIND: Record<TraceStep['kind'], { icon: string; tone: string }> = {
  guardrail: { icon: '🛡', tone: 'var(--ink-3)' }, thought: { icon: '💭', tone: 'var(--ink-2)' },
  tool_call: { icon: '⚙', tone: 'var(--accent)' }, verifier: { icon: '✔', tone: 'var(--good)' },
  score: { icon: '◎', tone: 'var(--ink-2)' }, error: { icon: '!', tone: 'var(--crit)' }, final: { icon: '■', tone: 'var(--ink)' },
}
const AGENT: Record<TraceStep['agent'], string> = { orchestrator: 'Orchestrator', network_analyst: 'Network Analyst', system: 'System' }

function Row({ s }: { s: TraceStep }) {
  const [open, setOpen] = useState(false)
  const k = KIND[s.kind]
  const sub = s.agent === 'network_analyst'
  const err = s.output_summary.startsWith('ERROR')
  return (
    <li className={`fadein ${sub ? 'ml-5 border-l-2 pl-3' : ''}`} style={sub ? { borderColor: 'var(--series-1)' } : undefined}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-2">
        <span className="mt-0.5 w-4 text-center text-xs" style={{ color: k.tone }} aria-hidden>{k.icon}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 text-[13px]">
            <span className="font-medium" style={{ color: err ? 'var(--crit)' : undefined }}>{s.kind === 'tool_call' ? <span className="mono">{s.name}</span> : s.name}</span>
            <span className="text-[11px] text-ink-3">{AGENT[s.agent]}</span>
            {s.duration_ms > 0 && <span className="text-[11px] tabular-nums text-ink-3">{s.duration_ms} ms</span>}
          </span>
          {!open && <span className="block truncate text-xs text-ink-3">{s.output_summary}</span>}
        </span>
      </button>
      {open && (
        <div className="mb-2 ml-8 space-y-1 text-xs">
          {Object.keys(s.input).length > 0 && <pre className="mono overflow-x-auto whitespace-pre-wrap rounded bg-surface-2 p-2 text-ink-2">{JSON.stringify(s.input, null, 1)}</pre>}
          <pre className="mono max-h-64 overflow-auto whitespace-pre-wrap rounded bg-surface-2 p-2 text-ink-2">{s.output_summary}</pre>
        </div>
      )}
    </li>
  )
}

export default function Trace({ steps, running }: { steps: TraceStep[]; running: boolean }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { if (running) end.current?.scrollIntoView({ block: 'nearest' }) }, [steps.length, running])
  const tools = steps.filter(s => s.kind === 'tool_call').length
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <div className="text-sm font-semibold">Agent trace</div>
          <div className="text-xs text-ink-3">{steps.length} steps · {tools} tool calls{running && ' · running…'}</div>
        </div>
        {running && <span className="h-2 w-2 animate-pulse rounded-full" style={{ background: 'var(--series-1)' }} />}
      </div>
      <ol className="flex-1 space-y-0.5 overflow-y-auto p-2" aria-live="polite">
        {steps.map(s => <Row key={`${s.step}-${s.name}`} s={s} />)}
        <div ref={end} />
      </ol>
    </div>
  )
}
