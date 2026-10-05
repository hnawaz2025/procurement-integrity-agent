export type Severity = 'low' | 'medium' | 'high'

export interface Signal {
  signal_id: string; code: string; category: string; severity: Severity; title: string; detail: string
  evidence_quote?: string | null; graph_path?: string[] | null; entities: string[]
}
export interface RiskFlag {
  id: string; category: string; practice_hint: string; severity: Severity; title: string; rationale: string
  evidence_quote?: string | null; graph_path?: string[] | null; citations: string[]; signal_refs: string[]
  origin: 'rule' | 'pattern' | 'llm' | 'both'
}
export interface TraceStep {
  step: number; agent: 'orchestrator' | 'network_analyst' | 'system'
  kind: 'guardrail' | 'thought' | 'tool_call' | 'verifier' | 'score' | 'error' | 'final'
  name: string; input: Record<string, unknown>; output_summary: string; duration_ms: number
}
export interface Retrieved { id: string; title: string; source: string; url: string; text: string; rrf: number; bm25: number; cosine: number | null; query: string }
export interface ReviewResult {
  review_id: string; created_at: string; mode: 'claude' | 'mock'; planner: string; models: Record<string, string>
  input_sha256: string; redacted_document: string; summary: string; flags: RiskFlag[]
  rejected_flags: { flag: RiskFlag; reasons: string[] }[]; dismissals: { signal_id: string; reason: string }[]
  signals: Signal[]; overall_risk: Severity; confidence: number
  confidence_breakdown: Record<'grounding' | 'citation_validity' | 'retrieval_strength' | 'signal_agreement' | 'coverage' | 'score', number>
  human_review_questions: string[]; escalation: 'standard_review' | 'priority_review'; escalation_reasons: string[]
  guardrail_events: { kind: string; detail: string; severity: Severity }[]; retrieved: Retrieved[]; trace: TraceStep[]
  usage: { input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number; cost_usd: number }
  network_entities: string[]; audit_hash: string; cached: boolean
}
export interface Lead {
  tender_id: string; title: string; entity: string; sector: string; winner: string; winner_id: string
  contract_value: number; published: string; risk: number; lead_score: number; signals: string[]; details: string[]
}
export interface Health {
  status: string; mode: 'claude' | 'mock'; planner: string; retrieval: string; kb_chunks: number
  corpus: { dir: string; tenders: number; companies: number }; telemetry: string; models: Record<string, string>
  audit: { valid: boolean; entries: number }
}
export interface Sample { id: string; title: string; language: string; expected: string[] }
