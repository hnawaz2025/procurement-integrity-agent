import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { getJSON } from '../api'
import { Empty } from './ui'

interface GNode { id: string; kind: string; label: string; requested: boolean; x?: number; y?: number }
interface GLink { source: string | GNode; target: string | GNode; rel: string }

const COLOR: Record<string, string> = { company: '#2a78d6', shell: '#d03b3b', person: '#4a3aa7', address: '#1baf7a', phone: '#eda100', bank: '#e87ba4' }

export default function NetworkGraph({ entities, highlight }: { entities: string[]; highlight: string[][] }) {
  const [data, setData] = useState<{ nodes: GNode[]; links: GLink[] } | null>(null)
  const [err, setErr] = useState('')
  const wrap = useRef<HTMLDivElement>(null)
  const fg = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined)
  const [w, setW] = useState(500)
  useEffect(() => {
    if (!entities.length) return
    getJSON<{ nodes: GNode[]; links: GLink[] }>(`/api/graph/subgraph?entities=${entities.join(',')}`).then(setData).catch(e => setErr(String(e)))
  }, [entities])
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    if (wrap.current) ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])
  useEffect(() => {
    const f = fg.current
    if (!f || !data) return
    f.d3Force('charge')?.strength(-260)
    f.d3Force('link')?.distance(55)
  }, [data])
  // labels on suspicious path, e.g. "company: Rodovia Construct Ltd"
  const hot = useMemo(() => new Set(highlight.flat().map(s => s.split(': ').slice(1).join(': '))), [highlight])
  const dark = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches

  if (!entities.length) return <Empty>No registry parties were resolved for this document.</Empty>
  if (err) return <Empty>{err}</Empty>
  if (!data) return <Empty>Loading graph…</Empty>
  const isHot = (n: GNode) => hot.has(n.label)
  return (
    <div>
      <div ref={wrap} className="overflow-hidden rounded-lg border border-line bg-surface-2">
        <ForceGraph2D ref={fg} graphData={data} width={w} height={400} cooldownTicks={120}
          onEngineStop={() => fg.current?.zoomToFit(400, 60)}
          nodeRelSize={5} linkColor={(l: GLink) => l.rel.startsWith('co-bid') ? 'rgba(42,120,214,.35)' : dark ? '#55554f' : '#c9ccd2'}
          linkWidth={(l: GLink) => l.rel.startsWith('co-bid') ? 1 : 1.5}
          linkLineDash={(l: GLink) => l.rel.startsWith('co-bid') ? [3, 3] : null}
          nodeLabel={(n: GNode) => `${n.kind}: ${n.label}`}
          nodeCanvasObject={(n: GNode, ctx, scale) => {
            const r = n.kind === 'company' || n.kind === 'shell' ? 6 : 4
            ctx.beginPath(); ctx.arc(n.x!, n.y!, r + (isHot(n) ? 3 : 0), 0, 2 * Math.PI)
            ctx.fillStyle = isHot(n) ? 'rgba(208,59,59,.22)' : 'transparent'; ctx.fill()
            ctx.beginPath(); ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI)
            ctx.fillStyle = COLOR[n.kind] ?? '#888'; ctx.fill()
            ctx.lineWidth = 2 / scale; ctx.strokeStyle = dark ? '#1a1a19' : '#fff'; ctx.stroke()
            if (n.kind === 'company' || n.kind === 'shell' || n.kind === 'person' || isHot(n)) {
              ctx.font = `${11 / scale}px Inter, sans-serif`; ctx.textAlign = 'center'
              ctx.fillStyle = dark ? '#f5f5f4' : '#111827'; ctx.fillText(n.label, n.x!, n.y! + r + 11 / scale)
            }
          }} />
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink-2" aria-label="Legend">
        {Object.entries(COLOR).map(([k, c]) => <span key={k} className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} />{k}</span>)}
        <span className="flex items-center gap-1"><span className="inline-block w-4 border-t border-dashed" style={{ borderColor: '#2a78d6' }} />co-bid history</span>
        <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full" style={{ background: 'rgba(208,59,59,.22)' }} />on flagged path</span>
      </div>
      <p className="mt-1 text-xs text-ink-3">Registry graph: companies, directors and shared attributes (bank and phone numbers masked). Shared attributes can have innocent explanations.</p>
    </div>
  )
}
