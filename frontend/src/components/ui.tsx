import type { ReactNode } from 'react'
import type { Severity } from '../types'

const SEV: Record<Severity, { color: string; icon: string; text: string }> = {
  high: { color: 'var(--crit)', icon: '▲', text: 'High' },
  medium: { color: 'var(--serious)', icon: '◆', text: 'Medium' },
  low: { color: 'var(--warn)', icon: '●', text: 'Low' },
}

/** Severity always carries icon + label: never colour alone. */
export function SevPill({ s }: { s: Severity }) {
  const v = SEV[s]
  return (
    <span className="chip" style={{ borderColor: v.color, color: 'var(--ink)' }}>
      <span style={{ color: v.color }} aria-hidden>{v.icon}</span>{v.text}
    </span>
  )
}

export function HumanReviewBanner() {
  return (
    <div role="note" className="sticky top-0 z-30 border-b px-4 py-2 text-[13px]"
      style={{ background: 'var(--banner-bg)', borderColor: 'var(--banner-border)', color: 'var(--banner-ink)' }}>
      <div className="mx-auto flex max-w-[1500px] items-center gap-2">
        <span aria-hidden className="text-base">⚠</span>
        <strong>Human review required.</strong>
        <span>Outputs are risk signals for trained reviewers, not findings of misconduct. All data in this prototype is synthetic.</span>
      </div>
    </div>
  )
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-3">{sub}</div>}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-full min-h-40 items-center justify-center p-6 text-center text-sm text-ink-3">{children}</div>
}

export function Tabs<T extends string>({ tabs, value, onChange, counts }: {
  tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void; counts?: Partial<Record<T, number>>
}) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map(t => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] font-medium ${value === t.id ? 'border-accent text-ink' : 'border-transparent text-ink-3 hover:text-ink'}`}>
          {t.label}{counts?.[t.id] !== undefined && <span className="ml-1.5 text-ink-3">{counts[t.id]}</span>}
        </button>
      ))}
    </div>
  )
}
