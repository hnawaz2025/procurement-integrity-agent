"""Entity graph over companies and their identifying attributes.

Nodes: company, person (director/owner), address, phone, bank account.
Two firms are 'linked' when they share any attribute node, directly or via intermediaries
(e.g. A -director- P -director- Shell -address- B). Connected components give an O(V+E) way to
find every linked pair at corpus scale; bounded shortest paths explain a specific link.

Production equivalent: GraphFrames on Databricks, Neo4j, or Cosmos DB (Gremlin).
"""
from __future__ import annotations

from functools import lru_cache

import networkx as nx
import pandas as pd

from .corpus import Corpus

HUB_COMPONENT_LIMIT = 25  # components this large are likely business centres / registered agents


class EntityGraph:
    def __init__(self, corpus: Corpus):
        self.c = corpus
        g = nx.Graph()
        co = corpus.companies
        for row in co.itertuples(index=False):
            cn = f"company:{row.company_id}"
            g.add_node(cn, kind="company", label=row.name, shell=bool(row.is_shell))
            for kind, val in (("address", row.address_n), ("phone", row.phone_n), ("bank", row.bank_account)):
                an = f"{kind}:{val}"
                g.add_node(an, kind=kind, label=val)
                g.add_edge(cn, an, rel=f"has_{kind}")
        for row in corpus.directors.itertuples(index=False):
            pn = f"person:{row.person_id}"
            g.add_node(pn, kind="person", label=corpus.person_name.get(row.person_id, row.person_id))
            g.add_edge(f"company:{row.company_id}", pn, rel="director")
        self.g = g
        comp_of: dict[str, int] = {}
        size: dict[int, int] = {}
        for i, nodes in enumerate(nx.connected_components(g)):
            ncomp = sum(1 for n in nodes if n.startswith("company:"))
            size[i] = ncomp
            for n in nodes:
                if n.startswith("company:"):
                    comp_of[n[8:]] = i
        self.component_of = comp_of
        self.component_size = size

    def linked(self, a: str, b: str) -> bool:
        ca, cb = self.component_of.get(a), self.component_of.get(b)
        return ca is not None and ca == cb and self.component_size[ca] <= HUB_COMPONENT_LIMIT

    def path(self, a: str, b: str, max_hops: int = 6) -> list[str] | None:
        try:
            p = nx.shortest_path(self.g, f"company:{a}", f"company:{b}")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        return p if len(p) - 1 <= max_hops else None

    def describe_path(self, p: list[str]) -> list[str]:
        out = []
        for n in p:
            kind, _, ident = n.partition(":")
            label = self.g.nodes[n].get("label", ident)
            if kind == "company" and self.g.nodes[n].get("shell"):
                kind = "shell company"
            if kind in ("bank", "phone"):  # never expose full account / phone numbers downstream
                label = f"••••{str(label)[-4:]}"
                kind = "bank account" if kind == "bank" else "phone"
            out.append(f"{kind}: {label}")
        return out

    def subgraph(self, company_ids: list[str], radius: int = 2) -> dict:
        nodes: set[str] = set()
        for cid in company_ids:
            n = f"company:{cid}"
            if n in self.g:
                nodes |= set(nx.ego_graph(self.g, n, radius=radius).nodes)
        # keep attribute nodes only when they connect 2+ companies (or belong to requested ones)
        keep = set()
        req = {f"company:{c}" for c in company_ids}
        for n in nodes:
            if n.startswith("company:"):
                keep.add(n)
            else:
                deg = sum(1 for m in self.g.neighbors(n) if m.startswith("company:"))
                if deg >= 2:
                    keep.add(n)
        sg = self.g.subgraph(keep)
        # co-bidding edges between requested companies (from history)
        bx = self.c.bids_x
        sub = bx[bx.company_id.isin(company_ids)]
        pairs = sub.merge(sub, on="tender_id")
        pairs = pairs[pairs.company_id_x < pairs.company_id_y]
        cobid = pairs.groupby(["company_id_x", "company_id_y"]).size().reset_index(name="n")
        return {
            "nodes": [{"id": n, "kind": ("shell" if d.get("shell") else d["kind"]),
                       "label": (f"••••{str(d.get('label', ''))[-4:]}" if d["kind"] in ("bank", "phone")
                                 else d.get("label", n)),
                       "requested": n in req} for n, d in sg.nodes(data=True)],
            "links": [{"source": u, "target": v, "rel": d.get("rel", "")} for u, v, d in sg.edges(data=True)]
            + [{"source": f"company:{r.company_id_x}", "target": f"company:{r.company_id_y}",
                "rel": f"co-bid x{r.n}"} for r in cobid.itertuples(index=False) if r.n >= 2],
        }

    def linked_cobidder_pairs(self) -> pd.DataFrame:
        """Vectorised: co-bidders in the same tender that sit in the same small component."""
        bx = self.c.bids_x[["tender_id", "company_id"]].copy()
        bx["comp"] = bx.company_id.map(self.component_of)
        bx = bx[bx.comp.map(lambda c: self.component_size.get(c, 0)).between(2, HUB_COMPONENT_LIMIT)]
        pairs = bx.merge(bx, on=["tender_id", "comp"])
        return pairs[pairs.company_id_x < pairs.company_id_y][["tender_id", "company_id_x", "company_id_y"]]


@lru_cache(maxsize=4)
def build_graph(corpus: Corpus) -> EntityGraph:
    return EntityGraph(corpus)
