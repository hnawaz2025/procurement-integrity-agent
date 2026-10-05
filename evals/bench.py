"""Scale benchmark: screening runtime + peak memory at 1k / 10k / 100k synthetic tenders.
Each size runs in a fresh subprocess so memory numbers are not contaminated.

    python evals/bench.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZES = [1_000, 10_000, 100_000]

CHILD = r"""
import json, resource, sys, time
sys.path.insert(0, {root!r})
from backend.app.analytics.corpus import Corpus
from backend.app.analytics.screening import screen
t0 = time.perf_counter(); c = Corpus({path!r}); t_load = time.perf_counter() - t0
leads, pr, funnel = screen(c)
planted = {{t for p in c.planted for t in p["tenders"]}}
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({{"tenders": c.n_tenders, "bids": int(len(c.bids)), "companies": int(len(c.companies)),
  "load_s": round(t_load, 2), "screen_s": funnel["timings"]["total_s"], "graph_s": funnel["timings"]["graph_s"],
  "patterns_s": funnel["timings"]["patterns_s"], "leads": funnel["leads"],
  "lead_rate": round(funnel["leads"] / c.n_tenders, 4),
  "planted_tenders": len(planted), "planted_recall": round(len(planted & set(leads.tender_id)) / len(planted), 3),
  "precision_at_100": round(float(leads.head(100).tender_id.isin(planted).mean()), 3),
  "peak_rss_mb": round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024))}}))
"""


def main():
    runs = []
    for n in SIZES:
        path = ROOT / "data" / ("demo" if n == 200 else f"scale_{n}")
        if not path.exists():
            subprocess.run([sys.executable, str(ROOT / "data" / "generate.py"), "--tenders", str(n)], check=True)
        out = subprocess.run([sys.executable, "-c", CHILD.format(root=str(ROOT), path=str(path))],
                             capture_output=True, text=True, check=True)
        r = json.loads(out.stdout.strip().splitlines()[-1])
        runs.append(r)
        print(r)
    res = ROOT / "evals" / "results"
    res.mkdir(parents=True, exist_ok=True)
    (res / "bench.json").write_text(json.dumps({"runs": runs, "machine": sys.platform}, indent=2))
    md = ["# Screening scale benchmark", "",
          "| Tenders | Bids | Companies | Load (s) | Screen (s) | Leads | Lead rate | Planted recall | P@100 | Peak RSS (MB) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['tenders']:,} | {r['bids']:,} | {r['companies']:,} | {r['load_s']} | {r['screen_s']} | {r['leads']} | "
           f"{r['lead_rate']:.2%} | {r['planted_recall']:.0%} | {r['precision_at_100']:.0%} | {r['peak_rss_mb']} |" for r in runs]
    md += ["", "Single process, laptop CPU, pandas + networkx. Production would run the same logic as Spark jobs "
           "on Databricks (incremental, partitioned by entity/period)."]
    (res / "bench.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
