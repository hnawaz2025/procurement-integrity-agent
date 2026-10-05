"""Procurement corpus: the tables a production system would read from Databricks Delta tables."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .entity_resolution import NameIndex, normalize_address, normalize_phone


class Corpus:
    def __init__(self, path: Path):
        self.path = Path(path)
        rd = lambda n, **kw: pd.read_csv(self.path / f"{n}.csv", **kw)
        self.companies = rd("companies", dtype={"phone": str, "bank_account": str})
        self.persons = rd("persons")
        self.directors = rd("directors")
        self.entities = rd("entities")
        self.tenders = rd("tenders", keep_default_na=False, na_values={"estimated_value": [""]})
        self.bids = rd("bids")
        for c in ("published", "deadline", "award_date"):
            self.tenders[c] = pd.to_datetime(self.tenders[c])
        self.companies["registered"] = pd.to_datetime(self.companies["registered"])
        self.companies["phone_n"] = self.companies["phone"].map(normalize_phone)
        self.companies["address_n"] = self.companies["address"].map(normalize_address)
        pp = self.path / "planted_patterns.json"
        self.planted = json.loads(pp.read_text()) if pp.exists() else []
        self.company_name = dict(zip(self.companies.company_id, self.companies.name))
        self.person_name = dict(zip(self.persons.person_id, self.persons.name))
        self.entity_name = dict(zip(self.entities.entity_id, self.entities.name))
        self.name_index = NameIndex(self.company_name)
        self.entity_index = NameIndex(self.entity_name)
        # enriched bids: tender facts + bidder registration, with rank inside each tender
        b = self.bids.merge(self.tenders[["tender_id", "entity_id", "sector", "published", "contract_value"]],
                            on="tender_id")
        b = b.merge(self.companies[["company_id", "registered"]], on="company_id")
        b["rank"] = b.groupby("tender_id")["price"].rank(method="first")
        self.bids_x = b

    @property
    def n_tenders(self) -> int:
        return len(self.tenders)

    def label(self, cid: str) -> str:
        return self.company_name.get(cid) or self.person_name.get(cid) or self.entity_name.get(cid) or cid


@lru_cache(maxsize=4)
def load_corpus(path: str) -> Corpus:
    return Corpus(Path(path))
