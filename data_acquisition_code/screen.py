"""Find the peer group: US apparel & footwear brands, judged on their situation in 2019.

    python data_acquisition_code/screen.py

Writes peer_group.xlsx next to this script: the final peer group, and every
candidate with the reason it was included or not. The rules are explained in
the README.
"""

import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sec import SecClient

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache"
WORKBOOK = Path(__file__).with_name("peer_group.xlsx")

# Apparel (2300-2399), rubber and plastic footwear (3020-3021), leather goods
# incl. footwear and handbags (3100-3199), apparel wholesale (5130-5139).
SIC_RANGES = [(2300, 2399), (3020, 3021), (3100, 3199), (5130, 5139)]

MIN_REVENUE_2019 = 500e6
REQUIRED_YEARS = range(2018, 2024)  # FY2018-FY2023

# SIC codes cannot tell an own-brand clothing chain from a store selling other
# companies' brands (Gap and TJX are both 5651), so own-brand companies filed
# under retail codes are added by name. Reasons are from each company's 10-K.
ADDITIONS = {
    39911: "Sells apparel under its own brands (Gap, Old Navy, Banana Republic, Athleta)",
    919012: "Designs its own merchandise (American Eagle, Aerie), made by third-party factories",
    1018840: "Sells its own brands (Abercrombie & Fitch, Hollister)",
    912615: "Sells its own brands (Urban Outfitters, Anthropologie, Free People)",
    799288: "Sells apparel under its own Lands' End brand",
    1041859: "Designs and sells primarily under its proprietary brands",
    1483510: "Designs and sells its own Express brand",
    1649744: "Sells its own Duluth Trading brand",
    18255: "Mainly private-label and exclusive merchandise, sourced directly from manufacturers",
    1359841: "Makes and sells its own basic-apparel brands (Hanes, Champion); SIC lists it as a retailer",
}

# In the sector codes, but most sales go to businesses rather than households.
EXCLUSIONS = {
    723254: "Rents and services work uniforms for businesses (Cintas)",
}

# Some companies tag only part of their sales with the first tag, so the
# largest value across these is used.
REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
]


def cached(name, fetch):
    """Read data/cache/<name>, or fetch it and save it there."""
    path = CACHE_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    if data is not None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return data


def revenue_2019(client):
    """cik -> (revenue, company name) for every company reporting 2019 revenue."""
    found = {}
    for tag in REVENUE_TAGS:
        frame = cached(f"frame_{tag}_CY2019.json", lambda t=tag: client.frame(t, "CY2019"))
        for row in frame["data"] if frame else []:
            if row["val"] > found.get(row["cik"], (0, None))[0]:
                found[row["cik"]] = (row["val"], row["entityName"])
    return found


def company_profiles(client, ciks):
    """SIC code, ticker, year end and last 10-K date for every company."""
    path = CACHE_DIR / "profiles.json"
    profiles = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for i, cik in enumerate([c for c in ciks if str(c) not in profiles], 1):
        sub = client.submissions(cik)
        if sub:
            recent = sub["filings"]["recent"]
            ten_ks = [d for f, d in zip(recent["form"], recent["filingDate"]) if f in ("10-K", "10-K/A")]
            profiles[str(cik)] = {
                "sic": int(sub["sic"]) if sub.get("sic") else None,
                "sic_description": sub.get("sicDescription"),
                "ticker": ",".join(sub.get("tickers") or []),
                "fiscal_year_end": sub.get("fiscalYearEnd"),
                "last_10k": max(ten_ks) if ten_ks else None,
            }
        else:
            profiles[str(cik)] = None
        if i % 250 == 0:
            print(f"  {i} companies looked up")
            path.write_text(json.dumps(profiles), encoding="utf-8")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profiles), encoding="utf-8")
    return profiles


def fiscal_year(end):
    # Named after the calendar year holding most of its months, so Feb 2025 -
    # Jan 2026 is FY2025. Nike calls June 2025 - May 2026 "fiscal 2026"; here it is FY2025.
    return end.year if end.month >= 6 else end.year - 1


def annual_revenue(client, ciks):
    """cik -> {fiscal year: [revenue, year end]} from full-year figures in 10-K filings."""
    path = CACHE_DIR / "annual_revenue.json"
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for cik in [c for c in ciks if str(c) not in cache]:
        facts = client.company_facts(cik) or {}
        years = {}
        gaap = facts.get("facts", {}).get("us-gaap", {})
        for tag in REVENUE_TAGS:
            for f in gaap.get(tag, {}).get("units", {}).get("USD", []):
                if f.get("form") not in ("10-K", "10-K/A") or "start" not in f:
                    continue
                start, end = date.fromisoformat(f["start"]), date.fromisoformat(f["end"])
                if 350 <= (end - start).days <= 380:
                    year = fiscal_year(end)
                    if f["val"] > years.get(year, [0])[0]:
                        years[year] = [f["val"], f["end"]]
        cache[str(cik)] = years
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache), encoding="utf-8")
    return {int(c): {int(y): v for y, v in years.items()} for c, years in cache.items()}


def in_sector(sic):
    return sic is not None and any(lo <= sic <= hi for lo, hi in SIC_RANGES)


def screen():
    client = SecClient()
    revenue = revenue_2019(client)
    print(f"{len(revenue)} companies report 2019 revenue. Looking up SIC codes...")
    profiles = company_profiles(client, list(revenue))

    candidates = []
    for cik, (value, name) in revenue.items():
        profile = profiles.get(str(cik))
        if profile and (in_sector(profile["sic"]) or cik in ADDITIONS):
            candidates.append({
                "cik": cik,
                "name": " ".join(name.replace("\xa0", " ").split()),
                **profile,
                "entered": "Added by name" if cik in ADDITIONS else "SIC code",
                "revenue_2019": value / 1e6,
            })

    by_year = annual_revenue(client, [c["cik"] for c in candidates])
    for c in candidates:
        years = by_year.get(c["cik"], {})
        missing = [y for y in REQUIRED_YEARS if y not in years]
        c["first_year"], c["last_year"] = (min(years), max(years)) if years else (None, None)
        c["latest_revenue"], c["latest_year_end"] = years[max(years)] if years else (None, None)
        c["missing"] = " ".join(str(y) for y in missing)
        if c["revenue_2019"] < MIN_REVENUE_2019 / 1e6:
            c["decision"], c["reason"] = "Failed", "FY2019 revenue below $500M"
        elif missing:
            c["decision"], c["reason"] = "Failed", f"No annual data for FY {c['missing']}"
        elif c["cik"] in EXCLUSIONS:
            c["decision"], c["reason"] = "Excluded", EXCLUSIONS[c["cik"]]
        else:
            c["decision"] = "Included"
            c["reason"] = ADDITIONS.get(c["cik"], "Meets all rules")
    return candidates


HEADER_FONT = Font(name="Arial", bold=True)
HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def add_sheet(wb, title, columns, rows):
    ws = wb.create_sheet(title)
    for col, (name, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        ws.column_dimensions[cell.column_letter].width = width
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial")
            if isinstance(cell.value, float):
                cell.number_format = "#,##0"
            elif isinstance(cell.value, date):
                cell.number_format = "yyyy-mm-dd"
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions


def write_workbook(candidates):
    wb = Workbook()
    wb.remove(wb.active)

    peers = sorted((c for c in candidates if c["decision"] == "Included"),
                   key=lambda c: -c["latest_revenue"])
    add_sheet(wb, "Peer group", [
        ("Company", 36), ("Ticker", 9), ("CIK", 10), ("How it entered", 15), ("SIC code", 9),
        ("SIC description", 40), ("Year ends", 10), ("Revenue FY2019 ($M)", 13),
        ("Latest annual revenue ($M)", 14), ("Latest year ended", 12), ("Last 10-K filed", 12),
    ], [[
        c["name"], c["ticker"].split(",")[0] or "(delisted)", c["cik"], c["entered"], c["sic"],
        c["sic_description"], MONTHS[int(c["fiscal_year_end"][:2]) - 1],
        c["revenue_2019"], c["latest_revenue"] / 1e6, date.fromisoformat(c["latest_year_end"]),
        date.fromisoformat(c["last_10k"]),
    ] for c in peers])

    order = {"Included": 0, "Excluded": 1, "Failed": 2}
    add_sheet(wb, "All candidates", [
        ("Company", 36), ("Ticker", 9), ("CIK", 10), ("How it entered", 15), ("SIC code", 9),
        ("SIC description", 40), ("Revenue FY2019 ($M)", 13), ("Annual data", 14),
        ("Decision", 10), ("Reason", 70),
    ], [[
        c["name"], c["ticker"].split(",")[0], c["cik"], c["entered"], c["sic"],
        c["sic_description"], c["revenue_2019"],
        f"FY{c['first_year']}-FY{c['last_year']}" if c["first_year"] else "none",
        c["decision"], c["reason"],
    ] for c in sorted(candidates, key=lambda c: (order[c["decision"]], -c["revenue_2019"]))])

    wb.save(WORKBOOK)
    return peers


def main():
    candidates = screen()
    peers = write_workbook(candidates)
    big = [c for c in candidates if c["revenue_2019"] >= MIN_REVENUE_2019 / 1e6]
    print(f"Candidates: {len(candidates)}, revenue >= $500M: {len(big)}, "
          f"with FY2018-2023 data: {sum(not c['missing'] for c in big)}, "
          f"peer group: {len(peers)}")
    print(f"Saved {WORKBOOK.name}")


if __name__ == "__main__":
    main()
