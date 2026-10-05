# Model card: Procurement Integrity Review Agent (prototype v0.3)

## Intended use
- **Purpose:** decision support for trained integrity analysts. It triages procurement records, surfaces risk indicators with evidence and citations, and drafts questions for follow-up.
- **Users:** integrity and procurement reviewers. It is not for public-facing use.
- **Out of scope:**
  - determining wrongdoing
  - sanctioning decisions
  - assessing individuals
  - any automated action against a firm or person

Outputs are indicators that warrant human review. The World Bank sanctions process (INT investigation, then OSD and the Sanctions Board) is the only path to a determination [KB-20].

## System composition
| Component | Model / method | Notes |
|---|---|---|
| Orchestrator | `claude-opus-5-5` (configurable) | Plans the investigation, chooses tools, writes flags and the summary |
| Network Analyst subagent | `claude-sonnet-5-5` | Graph and history tools only, fresh context |
| Extraction | `claude-haiku-4-5` + Pydantic schema | Falls back to the rule-based parser on failure |
| Offline planner | Scripted | Same tools, fixed order. Cannot read qualitative signals |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (fastembed) | 50+ languages. The plan named `multilingual-e5-small`, which fastembed does not ship |
| Screening | Deterministic detectors | Weights and thresholds below |

## Data
- **Corpus:** fully synthetic (fictional Republic of Veloria), produced by `data/generate.py` with a fixed seed. It contains five planted patterns plus deliberate noise: innocent shared directors, and thin markets where the same firms always bid.
- **Knowledge base:** 26 chunks.
  - 20 paraphrase public World Bank material: the Anti-Corruption Guidelines definitions, INT's "Warning Signs of Fraud and Corruption in Procurement" brochure, and the Sanctions Regime information note.
  - 6 are synthetic reviewer guidance, labelled as such.
- **Confidential data:** none.

## Screening weights (illustrative)
| Signal | Weight |
|---|---|
| Rotation ring with stable cover bids | 3.0 |
| Rotation or stable cover alone (thin-market pattern) | 1.5 |
| Hidden link between co-bidders | 3.0 |
| Split-purchase series | 2.5 |
| Supplier concentration with short windows | 2.0 |
| New firm, bid clustering, unjustified direct contracting | 1.5 each |
| Short window, amendment over 15% | 1.0 each |
| Just under the threshold | 0.5 |

A tender becomes a lead when its risk weight is 2 or more. Leads are ranked by risk × log10(contract value).

Rule thresholds are in `config.Thresholds` and KB-24. They are prototype settings, not World Bank policy.

## Confidence (computed, not self-reported)
`confidence = 0.30·grounding + 0.20·citation_validity + 0.15·retrieval_strength + 0.20·signal_agreement + 0.15·coverage`

| Term | How it is computed |
|---|---|
| grounding | Share of agent-proposed flags that passed the verifier |
| citation_validity | Share of citations that were actually retrieved in this review |
| retrieval_strength | Mean cosine of retrieved chunks, rescaled to [0, 1] (0.5 if BM25-only) |
| signal_agreement | Share of deterministic signals the agent addressed itself, rather than the baseline guarantee adding them |
| coverage | Share of extraction, rules, retrieval and (when parties are named) network checks that actually ran |

## Evaluation
See `evals/results/latest.md` and `bench.md`.

**Mock mode** (scripted planner): 100% micro precision and 95% recall on 9 documents. There are 0 false positives on the clean document, the prompt injection is resisted, and the only miss is the LLM-only category (tailored specifications).

**Screening:** all planted patterns A–E are recovered at 200, 10k and 100k tenders, and precision@100 is 100% at 100k.

**Read these numbers carefully:**
- The rules and the samples were written together, and the data is synthetic with cleanly planted patterns.
- These results show the pipeline works as designed. They do not estimate real-world detection performance.
- Claude-mode numbers come from `make eval` with an API key. That run had not been done when this card was written.

## Known limitations and risks
| Risk | Mitigation in prototype | Remaining gap |
|---|---|---|
| False positives harm firms' reputations | Non-accusatory language policy; human sign-off on every output; innocent-explanation guidance [KB-23] | Needs calibration on real, labelled cases |
| Missed signals (false negatives) | Deterministic baseline always runs; an LLM failure falls back to it | Coverage limited to encoded red flags; new schemes are missed |
| Hallucinated evidence or citations | Verifier rejects unmatched quotes, unreturned graph paths and unretrieved citations | Fuzzy quote matching (≥0.85) can accept a near-verbatim paraphrase |
| Prompt injection | Pattern screen, untrusted-data tags, baseline guarantee, `document_manipulation` flag | Heuristic screen. Production should add Azure AI Content Safety Prompt Shields |
| PII exposure | Consistent pseudonymisation before LLM calls; masked bank and phone numbers in graph output | Untitled personal names not detected (needs NER, e.g. Azure AI Language PII) |
| Bias against small, new or local firms | "New firm" is a low-weight signal and never escalates alone | Needs fairness review by firm size and country on real data |
| Multilingual parity | Multilingual embeddings; ES/FR samples in evals | Only 2 non-English samples; low-resource languages untested |
| Over-reliance on automation | Mandatory review banner; reviewer questions; confidence breakdown shown | Needs user research and training (see `reviewer_guide.md`) |
