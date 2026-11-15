# Apparel & footwear peer benchmarking

Quarterly financials of 32 US apparel and footwear brands (Nike, Lululemon, Gap, Levi's,
Ralph Lauren and others) from FY2018 onward, built from the companies' own SEC filings.
Each brand can be compared with its peers on growth, margins, inventory and cash
conversion, including the inventory build-up of 2022.

All data comes from the SEC's free XBRL API (data.sec.gov). No paid or licensed sources.

## How it works

| Folder | What it does |
|---|---|
| `data_acquisition_code/` | Python. `screen.py` finds the peer group and writes `peer_group.xlsx`. `download.py` downloads the SEC data for those companies and loads it into DuckDB. |
| `transform/` | SQL (dbt). Turns the raw filings into one table with a row per company and quarter, and tests it. `measures.csv` lists which SEC tags make up each column. |
| `dashboard/` | Power BI report (to come). |

Downloaded files and the database are written to `data/`, which is not in the repository.

## Running it

```
python -m venv .venv
.venv\Scripts\activate          # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
copy .env.example .env          # then put your name and email in .env (the SEC asks for it)
```

```
python data_acquisition_code/screen.py      # optional: peer_group.xlsx is already included
python data_acquisition_code/download.py
cd transform
dbt build
```

The result is the table `quarterly` in `data/sec.duckdb`.

## Selection rules

Every company is judged on the same rules, using its situation in 2019, before the
2020-2023 disruption. What happened to it afterwards plays no part, so later winners and
later failures are picked the same way.

1. **Sector.** SEC industry code (SIC) 2300-2399 (apparel), 3020-3021 (rubber and plastic
   footwear), 3100-3199 (leather goods, incl. footwear and handbags) or 5130-5139 (apparel
   wholesale), or on the list of additions.
2. **Size.** Revenue of at least $500 million in 2019.
3. **Data.** Full-year revenue in a 10-K for every fiscal year 2018-2023. Companies that
   stopped filing later (taken over, taken private, bankrupt) stay in up to their last
   report: Skechers, Hanesbrands, Guess and Express.
4. **Not excluded.**

**Additions.** SIC codes cannot tell an own-brand clothing chain from a store selling other
companies' brands: Gap and TJX are both 5651. Ten companies filed under retail codes that
design and sell their own brands are added by name: Gap, American Eagle, Abercrombie &
Fitch, Urban Outfitters, Lands' End, Children's Place, Express, Duluth Trading, Cato and
Hanesbrands. They still have to pass rules 2 and 3. The reason for each, taken from its
10-K, is in `screen.py` and in the workbook.

**Exclusions.** Cintas is in the apparel codes but rents work uniforms to businesses.

**Left out on purpose.** Stores selling mainly other brands (TJX, Ross, Foot Locker,
Nordstrom): they are the group's customers, not its peers. Watch brands (Fossil, Movado).
Textile mills (carpets, yarn, industrial fabrics). S&P/GICS and Yahoo classifications:
licensed, and they only list today's companies, which would leave out the ones that
failed or were taken over.

**Result.** 48 candidates, 33 with revenue of at least $500M, all 33 with full data, 32
after excluding Cintas.

**Limitations.** Only companies filing 10-Ks, so Birkenstock, On, Amer Sports, Canada
Goose and Gildan are missing. Companies that stopped filing before FY2023 (e.g. Tiffany)
fail rule 3. SIC codes are today's codes. "Sells mainly its own brands" relies on each
company's own description.

## From filings to quarters

- **Tags.** Companies use different tags for the same line item. `measures.csv` lists
  them in order of priority. For revenue the largest tag is used instead, because some
  companies tag only part of their sales with the first one (Steve Madden, Caleres).
- **Restatements.** Each filing repeats last year's numbers, often restated, e.g. after
  selling a business. All numbers of a fiscal year are taken from the latest filing made
  within 15 months after that year ended, so growth compares like with like and the
  quarters add up to the year.
- **Single quarters.** Where only year-to-date figures are filed, a quarter is the
  difference between two of them. Q4 is the full year minus the first nine months.
- **Missing lines.** Gross profit = revenue - cost of sales where it is not reported
  (e.g. VF, Kontoor, Cato), and the other way round for Carter's. Nike reports no operating
  income, so it is gross profit - SG&A.
- **Fiscal years** are named after the calendar year holding most of their months:
  Feb 2025 - Jan 2026 is FY2025. Nike's year to May 2026 is its "fiscal 2026" and
  FY2025 here. For comparisons across companies each quarter also gets the calendar
  quarter holding most of its days.

## Measures

| Measure | Formula |
|---|---|
| Revenue growth | revenue / same quarter a year earlier - 1 |
| Gross margin | gross profit / revenue |
| Operating margin | operating income / revenue |
| Inventory days | inventory / cost of sales of the last 4 quarters x 365 |
| Receivable days | receivables / revenue of the last 4 quarters x 365 |
| Payable days | payables / cost of sales of the last 4 quarters x 365 |
| Cash conversion cycle | inventory days + receivable days - payable days |
| Inventory growth gap | inventory growth - revenue growth, both vs a year earlier |
| Operating cash flow margin | operating cash flow / revenue, last 4 quarters |

Operating margin is the main profitability measure. Gap, American Eagle, Lululemon and Cato
include store rent in cost of sales and Nike does not, so gross margin, inventory days and
payable days are not fully comparable between companies.

## Known gaps

- Gap reports receivables only in its 10-K, so its receivable days exist for Q4 only.
- VF restated its figures to take out Supreme (sold in 2024) but never republished Q1
  FY2023 on that basis. That year's quarters add up to $10,034M against $9,916M for the year.
- VF (2018) and Under Armour (2022) moved their year end from December to March. The
  three-month transition period belongs to no fiscal year and is left out.
