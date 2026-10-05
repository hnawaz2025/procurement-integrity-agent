"""Evaluation harness: document flags, screening, agent behaviour, quality and cost.

    python evals/run_eval.py            # mock mode unless ANTHROPIC_API_KEY is set
    FORCE_MOCK=1 python evals/run_eval.py

Writes evals/results/latest.json and latest.md. Uses a separate audit file so evals never touch
the demo audit log.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AUDIT_PATH", str(Path(tempfile.mkdtemp()) / "eval_audit.jsonl"))

from backend.app.agent.orchestrator import run_review
from backend.app.analytics.corpus import Corpus
from backend.app.analytics.screening import screen
from backend.app.config import settings

OUT = ROOT / "evals" / "results"


def pct(x: float) -> str:
    return f"{x:.0%}"


def eval_documents() -> dict:
    labels = json.loads((ROOT / "samples" / "labels.json").read_text())
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    rows, lat, costs, steps, tools, conf = [], [], [], [], [], []
    grounding, cites, rejected, baseline, budget_hits, completed = [], [], 0, 0, 0, 0
    lang_recall = defaultdict(lambda: [0, 0])
    llm_only_hit = defaultdict(lambda: [0, 0])
    injection = None
    trajectories = []
    for p in sorted((ROOT / "samples").glob("*.md")):
        lab = labels[p.stem]
        t0 = time.perf_counter()
        r = run_review(p.read_text(), use_cache=False)
        lat.append(time.perf_counter() - t0)
        got = {f.category.value for f in r.flags}
        exp = set(lab["expected"])
        for c in got & exp:
            tp[c] += 1
        for c in got - exp:
            fp[c] += 1
        for c in exp - got:
            fn[c] += 1
        lang_recall[lab["language"]][0] += len(got & exp)
        lang_recall[lab["language"]][1] += len(exp)
        for c in lab.get("llm_only", []):
            llm_only_hit[c][0] += c in got
            llm_only_hit[c][1] += 1
        tool_calls = [s for s in r.trace if s.kind == "tool_call"]
        names = [s.name for s in tool_calls]
        steps.append(len(r.trace))
        tools.append(len(tool_calls))
        costs.append(r.usage.cost_usd)
        conf.append(r.confidence)
        grounding.append(r.confidence_breakdown.grounding)
        cites.append(r.confidence_breakdown.citation_validity)
        rejected += len(r.rejected_flags)
        baseline += sum("baseline guarantee" in f.rationale for f in r.flags)
        budget_hits += any(s.kind == "error" and s.name == "budget" for s in r.trace)
        completed += "finish" in names
        if lab.get("requires_graph"):
            trajectories.append({"sample": p.stem, "used_graph_tools": bool({"find_connections", "check_patterns"} & set(names)),
                                 "delegated_to_subagent": "delegate_network_investigation" in names})
        if lab.get("injection"):
            injection = {"guardrail_fired": any(e.kind == "prompt_injection" for e in r.guardrail_events),
                         "flagged_manipulation": "document_manipulation" in got,
                         "not_rated_low": r.overall_risk != "low",
                         "other_signals_kept": len(got - {"document_manipulation"}) > 0}
            injection["resisted"] = all(injection.values())
        rows.append({"sample": p.stem, "language": lab["language"], "expected": sorted(exp), "got": sorted(got),
                     "missed": sorted(exp - got), "extra": sorted(got - exp), "risk": r.overall_risk,
                     "escalation": r.escalation, "confidence": r.confidence, "latency_s": round(lat[-1], 2),
                     "cost_usd": r.usage.cost_usd, "tool_calls": len(tool_calls)})
    cats = sorted(set(tp) | set(fp) | set(fn))
    per_cat = {c: {"precision": tp[c] / (tp[c] + fp[c]) if tp[c] + fp[c] else None,
                   "recall": tp[c] / (tp[c] + fn[c]) if tp[c] + fn[c] else None,
                   "tp": tp[c], "fp": fp[c], "fn": fn[c]} for c in cats}
    TP, FP, FN = sum(tp.values()), sum(fp.values()), sum(fn.values())
    clean = next(r for r in rows if r["sample"].startswith("01_"))
    lat_sorted = sorted(lat)
    return {
        "samples": rows, "per_category": per_cat,
        "micro": {"precision": TP / (TP + FP) if TP + FP else 1.0, "recall": TP / (TP + FN) if TP + FN else 1.0},
        "clean_doc_false_positives": len(clean["got"]),
        "injection": injection,
        "multilingual_recall": {k: v[0] / v[1] if v[1] else None for k, v in lang_recall.items()},
        "llm_only_recall": {k: v[0] / v[1] for k, v in llm_only_hit.items()},
        "agent": {"completion_rate": completed / len(rows), "avg_steps": statistics.mean(steps),
                  "avg_tool_calls": statistics.mean(tools), "budget_hits": budget_hits, "trajectories": trajectories,
                  "avg_cost_usd": round(statistics.mean(costs), 4), "max_cost_usd": round(max(costs), 4)},
        "quality": {"avg_confidence": round(statistics.mean(conf), 3), "grounding_rate": round(statistics.mean(grounding), 3),
                    "citation_validity": round(statistics.mean(cites), 3), "verifier_rejections": rejected,
                    "baseline_additions": baseline},
        "latency_s": {"p50": round(statistics.median(lat), 2),
                      "p95": round(lat_sorted[min(len(lat) - 1, int(0.95 * len(lat)))], 2)},
    }


def pattern_recall(c: Corpus, pr) -> dict:
    found = defaultdict(lambda: [0, 0])
    links = {tuple(sorted(x)) for x in pr.hidden_links[["company_id_x", "company_id_y"]].values.tolist()}
    newf = set(zip(pr.new_firms.tender_id, pr.new_firms.company_id))
    for p in c.planted:
        k = p["pattern"]
        comps = p["companies"]
        if k == "A":
            hit = any(len(set(g["members"]) & set(comps)) >= 3 and g["stable_cover"] for g in pr.rotation_groups)
        elif k == "B":
            hit = tuple(sorted(comps[:2])) in links
        elif k == "C":
            hit = any(x["supplier"] == comps[0] for x in pr.concentration)
        elif k == "D":
            hit = any(x["supplier"] == comps[0] for x in pr.splitting)
        else:
            hit = tuple(sorted(comps)) in links or (p["tenders"][0], comps[1]) in newf
        found[k][0] += hit
        found[k][1] += 1
    return {k: f"{v[0]}/{v[1]}" for k, v in sorted(found.items())}


def eval_screening() -> dict:
    out = {}
    for d in ("demo", "scale_10000"):
        path = ROOT / "data" / d
        if not path.exists():
            continue
        c = Corpus(path)
        leads, pr, funnel = screen(c)
        planted = {t for p in c.planted for t in p["tenders"]}
        out[d] = {"tenders": c.n_tenders, "leads": funnel["leads"], "planted_tenders": len(planted),
                  "precision_at_10": round(leads.head(10).tender_id.isin(planted).mean(), 3),
                  "precision_at_50": round(leads.head(50).tender_id.isin(planted).mean(), 3),
                  "planted_recall_in_leads": round(len(planted & set(leads.tender_id)) / len(planted), 3),
                  "pattern_recall": pattern_recall(c, pr),
                  "thin_market_groups_downweighted": sum(1 for g in pr.rotation_groups if not g["stable_cover"]),
                  "screen_seconds": funnel["timings"]["total_s"]}
    return out


def to_md(r: dict) -> str:
    d = r["documents"]
    L = [f"# Evaluation results ({r['mode']} mode, {r['planner']})", "",
         f"Run: {r['timestamp']} - {len(d['samples'])} synthetic documents, prompt version {r['prompt_version']}", "",
         "## Document-level flags", "",
         f"- Micro precision **{pct(d['micro']['precision'])}**, micro recall **{pct(d['micro']['recall'])}**",
         f"- False positives on the clean document: **{d['clean_doc_false_positives']}**",
         f"- Prompt injection resisted: **{d['injection']['resisted'] if d['injection'] else 'n/a'}** "
         f"({d['injection']})",
         f"- Recall by language: {', '.join(f'{k}: {pct(v)}' for k, v in d['multilingual_recall'].items())}",
         f"- LLM-only categories recall: {', '.join(f'{k}: {pct(v)}' for k, v in d['llm_only_recall'].items())}", "",
         "| Sample | Lang | Expected | Got | Missed | Extra | Escalation | Conf. |", "|---|---|---|---|---|---|---|---|"]
    for s in d["samples"]:
        L.append(f"| {s['sample']} | {s['language']} | {', '.join(s['expected']) or '-'} | {', '.join(s['got']) or '-'} | "
                 f"{', '.join(s['missed']) or '-'} | {', '.join(s['extra']) or '-'} | {s['escalation']} | {s['confidence']:.2f} |")
    L += ["", "| Category | Precision | Recall | TP | FP | FN |", "|---|---|---|---|---|---|"]
    for c, v in d["per_category"].items():
        f = lambda x: "-" if x is None else pct(x)
        L.append(f"| {c} | {f(v['precision'])} | {f(v['recall'])} | {v['tp']} | {v['fp']} | {v['fn']} |")
    a, q = d["agent"], d["quality"]
    L += ["", "## Agent behaviour", "",
          f"- Completion rate {pct(a['completion_rate'])}; avg steps {a['avg_steps']:.1f}; avg tool calls {a['avg_tool_calls']:.1f}; "
          f"budget hits {a['budget_hits']}",
          f"- Trajectory checks (graph-dependent samples): {a['trajectories']}",
          f"- Cost per review: avg ${a['avg_cost_usd']}, max ${a['max_cost_usd']}",
          f"- Latency p50 {d['latency_s']['p50']}s, p95 {d['latency_s']['p95']}s", "",
          "## Quality", "",
          f"- Grounding rate {pct(q['grounding_rate'])}; citation validity {pct(q['citation_validity'])}; "
          f"verifier rejections {q['verifier_rejections']}; baseline additions {q['baseline_additions']}; "
          f"avg confidence {q['avg_confidence']}", "", "## Portfolio screening", "",
          "| Corpus | Tenders | Leads | P@10 | P@50 | Planted recall | Patterns A-E | Thin-market groups down-weighted | Seconds |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, v in r["screening"].items():
        L.append(f"| {k} | {v['tenders']:,} | {v['leads']} | {pct(v['precision_at_10'])} | {pct(v['precision_at_50'])} | "
                 f"{pct(v['planted_recall_in_leads'])} | {v['pattern_recall']} | {v['thin_market_groups_downweighted']} | {v['screen_seconds']} |")
    L += ["", "> Synthetic data with planted patterns: these numbers validate that the pipeline works as designed, "
          "not real-world detection performance. See README > Limitations."]
    return "\n".join(L) + "\n"


def main():
    from backend.app.agent.prompts import PROMPT_VERSION
    OUT.mkdir(parents=True, exist_ok=True)
    mode = "claude" if settings.llm_enabled else "mock"
    r = {"mode": mode, "planner": "claude-agent" if mode == "claude" else "scripted-offline",
         "timestamp": time.strftime("%Y-%m-%d %H:%M"), "prompt_version": PROMPT_VERSION,
         "documents": eval_documents(), "screening": eval_screening()}
    r["agent"] = r["documents"]["agent"]
    (OUT / "latest.json").write_text(json.dumps(r, indent=2, default=str))
    (OUT / f"latest_{mode}.json").write_text(json.dumps(r, indent=2, default=str))
    md = to_md(r)
    (OUT / "latest.md").write_text(md)
    (OUT / f"latest_{mode}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
