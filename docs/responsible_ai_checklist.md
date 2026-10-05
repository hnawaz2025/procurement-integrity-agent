# Responsible AI checklist

Status key: ✅ implemented in the prototype · 🟡 partial · ⬜ needed before production.

## Human oversight
- ✅ Every result says "Human review required". Outputs are framed as risk signals, never findings.
- ✅ Reviewers can accept, reject or mark "needs info" on each flag. Each decision is appended to the hash-chained audit log.
- ✅ Automatic escalation to priority review when there is a high-severity flag, a network-level signal, an injection attempt, or confidence below 0.5.
- ✅ No automated action: the system cannot contact, sanction or block anyone.
- ⬜ Reviewer decisions feed threshold recalibration. The data is captured but not yet used.

## Transparency and explainability
- ✅ Every flag carries one of: a verbatim evidence quote, a graph path from the registry, or a corpus-pattern signal.
- ✅ Every flag cites knowledge-base chunks retrieved in that review. Each chunk links to its public source.
- ✅ A live trace shows each plan step, tool call, subagent delegation, verifier outcome and score.
- ✅ Confidence is computed from verifiable properties, and the breakdown is shown.
- ✅ The planner mode (Claude or scripted) and the models used are shown in the UI and recorded in the audit log.

## Reliability and safety
- ✅ A deterministic verifier checks quotes, paths, citations and language. Rejected flags are visible, with reasons.
- ✅ Baseline guarantee: the agent cannot silently drop deterministic evidence.
- ✅ Step, subagent and dollar budgets. LLM failure falls back to the deterministic baseline.
- ✅ Eval harness with a CI quality gate: false positives on the clean document, injection resistance, citation validity, screening precision@10.
- 🟡 Refusal handling: server-side fallback plus a recorded refusal step. Not exercised without an API key.
- ⬜ Evaluation on real, labelled historical cases, with error analysis by country, sector and firm size.

## Privacy and security
- ✅ PII pseudonymised before any LLM call. Tokens stay consistent, so equality-based analysis still works.
- ✅ Bank and phone numbers masked in graph outputs and the UI.
- ✅ Documents and tool outputs are treated as untrusted data. Injection screening runs in English, Spanish and French.
- ✅ Secrets come only from the environment. The container runs as a non-root user.
- ⬜ Entra ID SSO, RBAC by data classification, Key Vault with managed identity, and a private endpoint to the LLM (e.g. Claude via Microsoft Foundry within the tenancy).
- ⬜ A data-retention policy and confirmed LLM data handling (zero-data-retention, or the agreed terms) per WBG information classification.
- ⬜ A named-entity PII detector, e.g. Azure AI Language.

## Fairness
- 🟡 Low-weight signals (new firm, just under threshold) cannot create a lead alone. Thin-market co-bidding is down-weighted.
- ⬜ Disparity analysis of lead rates by firm size, nationality and region.
- ⬜ Review of whether thresholds burden small or local firms.

## Accountability and documentation
- ✅ Model card, architecture document, runbook, reviewer guide.
- ✅ Prompt version ID recorded with every review.
- ⬜ Formal risk assessment and sign-off under WBG IT security and AI governance processes.
- ⬜ Data lineage in Unity Catalog in production.
