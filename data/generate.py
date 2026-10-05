"""Synthetic procurement corpus generator for the fictional Republic of Veloria.

Writes Delta-table-shaped CSVs (companies, persons, directors, entities, tenders, bids)
plus planted_patterns.json (ground truth for evals). Everything is synthetic.

    python data/generate.py                    # demo corpus  -> data/demo/
    python data/generate.py --tenders 100000   # scale corpus -> data/scale_100000/
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

START = date(2023, 1, 1)
END = date(2025, 12, 31)

SECTORS = {
    "roads": {"kind": "works", "threshold": 1_000_000, "est": (250_000, 4_000_000)},
    "water": {"kind": "works", "threshold": 1_000_000, "est": (150_000, 2_500_000)},
    "health": {"kind": "goods", "threshold": 100_000, "est": (20_000, 600_000)},
    "education": {"kind": "goods", "threshold": 100_000, "est": (15_000, 400_000)},
    "office": {"kind": "goods", "threshold": 100_000, "est": (8_000, 250_000)},
}

BASE_ENTITIES = [
    ("PE01", "Ministry of Public Works", ["roads"]),
    ("PE02", "Rural Roads Authority", ["roads", "water"]),
    ("PE03", "Ministry of Education", ["education", "office"]),
    ("PE04", "Ministry of Health - Central Medical Stores", ["health"]),
    ("PE05", "National Statistics Office", ["office"]),
    ("PE06", "Water and Sanitation Agency", ["water"]),
]

PREFIX = ["Alder", "Brightwater", "Cobalt", "Delta", "Everline", "Fairhaven", "Granite", "Harbor",
          "Ironwood", "Juniper", "Keystone", "Larch", "Mosaic", "Northfield", "Oakridge", "Pinnacle",
          "Quarry", "Riverside", "Summit", "Tidewater", "Upland", "Vantage", "Westbrook", "Yarrow",
          "Zenith", "Amber", "Beacon", "Cedar", "Driftwood", "Ember", "Falcon", "Glen", "Highland",
          "Indigo", "Jasper", "Kingfisher", "Lantern", "Maple", "Nimbus", "Orchid", "Prairie"]
SUFFIX = {"roads": ["Construction", "Civil Works", "Engineering", "Builders"],
          "water": ["Hydro Works", "Water Engineering", "Pipeline Services", "Civil Contractors"],
          "health": ["Medical", "Pharma Supplies", "Health Logistics", "Medical Trading"],
          "education": ["Learning Supplies", "Educational Trading", "School Supplies"],
          "office": ["Office Solutions", "IT Services", "Business Supplies", "Systems"]}
FORMS = ["Ltd", "SA", "LLC", "& Co", "Group", "SARL"]
FIRST = ["Amara", "Bilal", "Chen", "Dalia", "Emeka", "Farah", "Goran", "Hana", "Ivan", "Jae", "Kofi",
         "Lucia", "Mateo", "Nadia", "Omar", "Priya", "Quentin", "Rosa", "Samir", "Tanvi", "Umar",
         "Vera", "Wen", "Ximena", "Yusuf", "Zara", "Aditi", "Bruno", "Carmen", "Dmitri", "Elif"]
LAST = ["Okafor", "Haddad", "Lindqvist", "Moreau", "Tanaka", "Silva", "Kowalski", "Nwosu", "Rahman",
        "Petrov", "Mensah", "Costa", "Ibrahim", "Novak", "Duarte", "Kaya", "Fischer", "Osei",
        "Varga", "Quispe", "Bakr", "Sato", "Romero", "Adeyemi", "Horvat", "Ndiaye", "Larsen"]
STREETS = ["Harbour Road", "Unity Avenue", "Market Street", "Station Lane", "Independence Blvd",
           "Riverside Drive", "Hill Street", "Garden Close", "Port Way", "Cathedral Square"]
CITIES = ["Velor City", "Port Ansel", "Mirada", "Kessrin", "Douvan"]


class World:
    def __init__(self, n_tenders: int, seed: int):
        self.rng = random.Random(seed)
        self.n_tenders = n_tenders
        self.companies: list[dict] = []
        self.persons: list[dict] = []
        self.directors: list[dict] = []
        self.entities: list[dict] = []
        self.tenders: list[dict] = []
        self.bids: list[dict] = []
        self.planted: list[dict] = []
        self._names: set[str] = set()
        self._addr_n = 0
        self._phone_n = 0
        self._acct_n = 0

    # ---------- primitives ----------
    def pid(self, name: str | None = None) -> str:
        p = {"person_id": f"P{len(self.persons) + 1:06d}",
             "name": name or f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"}
        self.persons.append(p)
        return p["person_id"]

    def new_address(self) -> str:
        self._addr_n += 1
        return f"{self._addr_n} {self.rng.choice(STREETS)}, {self.rng.choice(CITIES)}"

    def new_phone(self) -> str:
        self._phone_n += 1
        return f"+999 {20 + self._phone_n // 10_000:02d} {self._phone_n % 10_000:04d} {self.rng.randint(100, 999)}"

    def new_account(self) -> str:
        self._acct_n += 1
        return f"VL{self._acct_n:010d}"

    def unique_name(self, sector: str) -> str:
        for _ in range(50):
            n = f"{self.rng.choice(PREFIX)} {self.rng.choice(SUFFIX[sector])} {self.rng.choice(FORMS)}"
            if n not in self._names:
                self._names.add(n)
                return n
        n = f"{self.rng.choice(PREFIX)} {self.rng.choice(SUFFIX[sector])} {len(self._names)}"
        self._names.add(n)
        return n

    def company(self, sector: str, name: str | None = None, registered: date | None = None,
                address: str | None = None, phone: str | None = None, account: str | None = None,
                directors: list[str] | None = None, is_shell: bool = False) -> str:
        cid = f"C{len(self.companies) + 1:06d}"
        if name:
            self._names.add(name)
        self.companies.append({
            "company_id": cid, "name": name or self.unique_name(sector), "sector": sector,
            "registered": (registered or START - timedelta(days=self.rng.randint(400, 6000))).isoformat(),
            "address": address or self.new_address(), "phone": phone or self.new_phone(),
            "bank_account": account or self.new_account(), "is_shell": is_shell,
        })
        for p in directors or [self.pid()]:
            self.directors.append({"company_id": cid, "person_id": p})
        return cid

    def rand_date(self, lo: date = START, hi: date = END) -> date:
        return lo + timedelta(days=self.rng.randint(0, (hi - lo).days))

    def tender(self, entity_id: str, sector: str, published: date, est: float, bids: list[tuple[str, float]],
               winner: str, method: str | None = None, window: int | None = None,
               justification: str = "", award_note: str = "", amendment_pct: float = 0.0,
               title: str | None = None) -> str:
        tid = f"T{len(self.tenders) + 1:07d}"
        thr = SECTORS[sector]["threshold"]
        if method is None:
            method = "open" if est >= thr * 0.6 else "rfq"
        if window is None:
            window = self.rng.randint(21, 45) if method == "open" else self.rng.randint(7, 20)
        deadline = published + timedelta(days=window)
        win_price = dict(bids)[winner]
        self.tenders.append({
            "tender_id": tid, "entity_id": entity_id, "sector": sector,
            "title": title or f"{sector.title()} package {tid[-4:]}", "method": method,
            "estimated_value": round(est, 2), "review_threshold": thr,
            "published": published.isoformat(), "deadline": deadline.isoformat(), "window_days": window,
            "award_date": (deadline + timedelta(days=self.rng.randint(10, 40))).isoformat(),
            "winner_id": winner, "contract_value": round(win_price, 2),
            "amendment_pct": round(amendment_pct, 3), "justification": justification, "award_note": award_note,
        })
        for cid, price in bids:
            self.bids.append({"tender_id": tid, "company_id": cid, "price": round(price, 2),
                              "is_winner": cid == winner})
        return tid

    # ---------- background noise ----------
    def build_background(self):
        n_ent_extra = max(0, self.n_tenders // 400 - len(BASE_ENTITIES))
        for eid, name, sectors in BASE_ENTITIES:
            self.entities.append({"entity_id": eid, "name": name, "sectors": "|".join(sectors)})
        for i in range(n_ent_extra):
            secs = self.rng.sample(list(SECTORS), k=2)
            self.entities.append({"entity_id": f"PE{i + 7:04d}", "name": f"Provincial Agency {i + 7}",
                                  "sectors": "|".join(secs)})
        n_comp = max(60, self.n_tenders // 4)
        self.by_sector: dict[str, list[str]] = {s: [] for s in SECTORS}
        for i in range(n_comp):
            s = list(SECTORS)[i % len(SECTORS)]
            self.by_sector[s].append(self.company(s))
        # innocent links: family businesses sharing a director (honest false-positive bait)
        for _ in range(max(3, n_comp // 200)):
            s = self.rng.choice(list(SECTORS))
            a, b = self.rng.sample(self.by_sector[s], 2)
            shared = self.pid()
            self.directors.append({"company_id": a, "person_id": shared})
            self.directors.append({"company_id": b, "person_id": shared})

    def background_tender(self):
        ent = self.rng.choice(self.entities)
        sector = self.rng.choice(ent["sectors"].split("|"))
        lo, hi = SECTORS[sector]["est"]
        est = self.rng.uniform(lo, hi)
        pub = self.rand_date()
        r = self.rng.random()
        method = "direct" if r < 0.03 else None
        k = 1 if method == "direct" else self.rng.randint(3, 6)
        pool = self.by_sector[sector]
        bidders = self.rng.sample(pool, k=min(k, len(pool)))
        bids = [(c, est * self.rng.uniform(0.85, 1.25)) for c in bidders]
        ranked = sorted(bids, key=lambda x: x[1])
        winner, note = ranked[0][0], "Lowest evaluated responsive bid."
        if len(ranked) > 1 and self.rng.random() < 0.08:
            winner, note = ranked[1][0], "Lowest bid found non-responsive on technical criteria (documented)."
        just = ""
        if method == "direct":
            just = self.rng.choice(["Emergency repair following flood damage.", "Proprietary spare parts from OEM.",
                                    "Continuation of existing contract to ensure compatibility."])
            if self.rng.random() < 0.2:
                just = ""
        amend = 0.0
        if self.rng.random() < 0.10:
            amend = self.rng.uniform(0.02, 0.12) if self.rng.random() < 0.85 else self.rng.uniform(0.15, 0.30)
        self.tender(ent["entity_id"], sector, pub, est, bids, winner, method=method,
                    justification=just, award_note=note, amendment_pct=amend)

    # ---------- planted patterns ----------
    def plant_cartel(self, g: int, entity_ids: list[str], named: bool):
        """A: rotation cartel with stable cover bids. B: two members linked via a shell company."""
        sector = "roads"
        names = ["Rodovia Construct Ltd", "Meridian Roadworks SA", "Altura Infraestructura SA",
                 "Basalt & Grade Co"] if named else [None] * 4
        shared_director = self.pid("Tomas Ilver" if named else None)
        shell_addr = self.new_address()
        members = []
        for i, nm in enumerate(names):
            dirs = [shared_director] if i == 0 else None
            addr = shell_addr if i == 2 else None
            members.append(self.company(sector, name=nm, directors=dirs, address=addr))
        shell = self.company(sector, name="Corvane Holdings Ltd" if named else None, directors=[shared_director],
                             address=shell_addr, is_shell=True,
                             registered=START + timedelta(days=self.rng.randint(0, 200)))
        # ring members bid almost exclusively against each other (not added to the open pool)
        tids = []
        n = 14
        for j in range(n):
            pub = START + timedelta(days=int(j * 1050 / n) + self.rng.randint(0, 20))
            est = self.rng.uniform(800_000, 3_500_000)
            winner = members[j % 4]
            win_price = est * self.rng.uniform(1.05, 1.12)
            bidders = members if j % 3 else [m for m in members if m != members[(j + 1) % 4]]
            bids = [(winner, win_price)] + [(m, win_price * self.rng.uniform(1.03, 1.08))
                                            for m in bidders if m != winner]
            if j % 5 == 0:  # occasional genuine outsider who bids high
                bids.append((self.rng.choice(self.by_sector[sector][:20]), est * self.rng.uniform(1.15, 1.3)))
            tids.append(self.tender(self.rng.choice(entity_ids), sector, pub, est, bids, winner,
                                    method="open", award_note="Lowest evaluated responsive bid."))
        self.planted.append({"pattern": "A", "label": "bid_rotation_cartel", "group": g,
                             "companies": members, "tenders": tids})
        link_tenders = [t for t in tids if {members[0], members[2]} <= {b["company_id"] for b in self.bids
                                                                         if b["tender_id"] == t}]
        self.planted.append({"pattern": "B", "label": "hidden_ownership_link", "group": g,
                             "companies": [members[0], members[2], shell], "tenders": link_tenders})

    def plant_concentration(self, g: int, entity_id: str, named: bool):
        """C: one supplier wins an abnormal share at one entity, often with short windows."""
        sector = "health"
        fav = self.company(sector, name="MedSupply Partners Ltd" if named else None)
        tids = []
        for _ in range(16):
            est = self.rng.uniform(40_000, 300_000)
            others = self.rng.sample(self.by_sector[sector], 2)
            fp = est * self.rng.uniform(1.0, 1.1)
            bids = [(fav, fp)] + [(o, fp * self.rng.uniform(1.02, 1.2)) for o in others]
            tids.append(self.tender(entity_id, sector, self.rand_date(), est, bids, fav,
                                    window=self.rng.randint(5, 9), method="rfq" if est < 100_000 else "open",
                                    award_note="Lowest evaluated responsive bid."))
        self.by_sector[sector].append(fav)
        self.planted.append({"pattern": "C", "label": "supplier_concentration", "group": g,
                             "companies": [fav], "tenders": tids, "entity_id": entity_id})

    def plant_splitting(self, g: int, entity_id: str, named: bool):
        """D: series of awards just under the review threshold to one supplier within weeks."""
        sector = "office"
        sup = self.company(sector, name="Lumen Office Solutions Ltd" if named else None)
        thr = SECTORS[sector]["threshold"]
        start = self.rand_date(START, END - timedelta(days=60))
        tids = []
        for k in range(4):
            v = thr * self.rng.uniform(0.91, 0.99)
            other = self.rng.choice(self.by_sector[sector])
            bids = [(sup, v), (other, v * self.rng.uniform(1.05, 1.15))]
            tids.append(self.tender(entity_id, sector, start + timedelta(days=k * 6), v / 0.98, bids, sup,
                                    method="rfq", window=self.rng.randint(7, 10),
                                    award_note="Lowest evaluated responsive bid."))
        self.by_sector[sector].append(sup)
        self.planted.append({"pattern": "D", "label": "split_purchases", "group": g,
                             "companies": [sup], "tenders": tids, "entity_id": entity_id})

    def plant_phantom(self, g: int, entity_id: str, named: bool):
        """E: newly registered bidder sharing a bank account with the winner."""
        sector = "education"
        winner = self.company(sector, name="Kestrel Supplies Ltd" if named else None)
        acct = self.companies[-1]["bank_account"]
        pub = self.rand_date(START + timedelta(days=200), END - timedelta(days=30))
        phantom = self.company(sector, name="Northgate Trading LLC" if named else None,
                               registered=pub - timedelta(days=21), account=acct)
        other = self.rng.choice(self.by_sector[sector])
        est = self.rng.uniform(60_000, 90_000)
        wp = est * 1.08
        bids = [(winner, wp), (phantom, wp * 1.04), (other, wp * 1.11)]
        t = self.tender(entity_id, sector, pub, est, bids, winner, method="rfq",
                        award_note="Lowest evaluated responsive bid.")
        self.by_sector[sector].extend([winner, phantom])
        self.planted.append({"pattern": "E", "label": "phantom_bidder", "group": g,
                             "companies": [winner, phantom], "tenders": [t]})

    def plant_thin_market(self):
        """Honest noise: a thin local market where the same 3 firms always bid, prices independent.
        Looks like a ring on co-bidding alone; cover-bid margins are NOT stable. Not ground truth."""
        sector = "water"
        firms = [self.company(sector) for _ in range(3)]
        ent = self.rng.choice([e["entity_id"] for e in self.entities if sector in e["sectors"].split("|")])
        for _ in range(10):
            est = self.rng.uniform(150_000, 900_000)
            bids = [(f, est * self.rng.uniform(0.88, 1.25)) for f in firms]
            winner = min(bids, key=lambda x: x[1])[0]
            self.tender(ent, sector, self.rand_date(), est, bids, winner,
                        award_note="Lowest evaluated responsive bid.")

    def build(self):
        self.build_background()
        groups = max(1, self.n_tenders // 10_000)
        def ents_for(sector: str) -> list[str]:
            return [e["entity_id"] for e in self.entities if sector in e["sectors"].split("|")]

        for g in range(groups):
            named = g == 0
            road_ents = ["PE01", "PE02"] if named else self.rng.sample(ents_for("roads"), 2)
            self.plant_cartel(g, road_ents, named)
            self.plant_concentration(g, "PE04" if named else self.rng.choice(ents_for("health")), named)
            self.plant_splitting(g, "PE05" if named else self.rng.choice(ents_for("office")), named)
            self.plant_phantom(g, "PE03" if named else self.rng.choice(ents_for("education")), named)
        for _ in range(max(1, self.n_tenders // 5000)):
            self.plant_thin_market()
        while len(self.tenders) < self.n_tenders:
            self.background_tender()

    def write(self, out: Path):
        out.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(self.companies).to_csv(out / "companies.csv", index=False)
        pd.DataFrame(self.persons).to_csv(out / "persons.csv", index=False)
        pd.DataFrame(self.directors).to_csv(out / "directors.csv", index=False)
        pd.DataFrame(self.entities).to_csv(out / "entities.csv", index=False)
        pd.DataFrame(self.tenders).to_csv(out / "tenders.csv", index=False)
        pd.DataFrame(self.bids).to_csv(out / "bids.csv", index=False)
        (out / "planted_patterns.json").write_text(json.dumps(self.planted, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenders", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=str, default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else Path(__file__).parent / ("demo" if a.tenders == 200 else f"scale_{a.tenders}")
    w = World(a.tenders, a.seed)
    w.build()
    w.write(out)
    print(f"wrote {len(w.tenders)} tenders, {len(w.bids)} bids, {len(w.companies)} companies, "
          f"{len(w.planted)} planted pattern instances -> {out}")


if __name__ == "__main__":
    main()
