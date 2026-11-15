"""Download the SEC filings data of the peer group and load it into DuckDB.

    python data_acquisition_code/download.py            # only files not downloaded yet
    python data_acquisition_code/download.py --refresh  # download everything again

The companies come from peer_group.xlsx. Each company's companyfacts file is
saved unchanged to data/raw/, then every US GAAP dollar amount from its 10-K
and 10-Q filings goes into data/sec.duckdb:

    raw.companies  one row per company
    raw.facts      one row per reported number (all tags, nothing cleaned yet)
"""

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd
from sec import SecClient

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "sec.duckdb"
PEER_GROUP = Path(__file__).with_name("peer_group.xlsx")

FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}


def download(peers, refresh):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    client = SecClient()
    for cik, name in zip(peers["CIK"], peers["Company"]):
        path = RAW_DIR / f"{cik}.json"
        if path.exists() and not refresh:
            continue
        facts = client.company_facts(cik)
        if facts is None:
            raise SystemExit(f"No companyfacts file for {name} ({cik})")
        path.write_text(json.dumps(facts), encoding="utf-8")
        print(f"  downloaded {name}")


def flatten(facts):
    rows = []
    for tag, item in facts["facts"].get("us-gaap", {}).items():
        for f in item["units"].get("USD", []):
            if f.get("form") in FORMS:
                rows.append({
                    "cik": facts["cik"],
                    "tag": tag,
                    "period_start": f.get("start"),  # empty for balance sheet items
                    "period_end": f["end"],
                    "value": f["val"],
                    "form": f["form"],
                    "fiscal_year": f.get("fy"),
                    "fiscal_period": f.get("fp"),
                    "filed": f["filed"],
                    "accession": f["accn"],
                    "frame": f.get("frame"),
                })
    return rows


def load(peers):
    rows = []
    for cik in peers["CIK"]:
        rows += flatten(json.loads((RAW_DIR / f"{cik}.json").read_text(encoding="utf-8")))
    facts = pd.DataFrame(rows)
    for col in ("period_start", "period_end", "filed"):
        facts[col] = pd.to_datetime(facts[col]).dt.date
    facts["fiscal_year"] = facts["fiscal_year"].astype("Int64")

    companies = peers.rename(columns={
        "Company": "company", "Ticker": "ticker", "CIK": "cik", "SIC code": "sic",
        "SIC description": "sic_description", "Revenue FY2019 ($M)": "revenue_2019_musd",
    })[["cik", "company", "ticker", "sic", "sic_description", "revenue_2019_musd"]]

    with duckdb.connect(str(DB_PATH)) as con:
        con.execute("create schema if not exists raw")
        con.execute("create or replace table raw.companies as select * from companies")
        con.execute("create or replace table raw.facts as select * from facts")
    print(f"Loaded {len(companies)} companies and {len(facts):,} facts into {DB_PATH.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="download all files again")
    args = parser.parse_args()

    peers = pd.read_excel(PEER_GROUP, sheet_name="Peer group")
    download(peers, args.refresh)
    load(peers)


if __name__ == "__main__":
    main()
