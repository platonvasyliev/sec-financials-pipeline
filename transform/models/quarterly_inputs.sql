-- The nine inputs per company and fiscal quarter, in long format.
--
-- Income and cash flow items: the single-quarter figure if the company reports
-- one, otherwise the difference between two year-to-date figures. Q4 is never
-- filed on its own, so it is the full year minus the first nine months.
-- Balance sheet items: the value on the last day of the quarter.
--
-- Where an input is still missing it is calculated from the others:
--   cost_of_sales    = revenue - gross_profit   (Carter's)
--   gross_profit     = revenue - cost_of_sales  (VF, Kontoor, Cato, Abercrombie)
--   operating_income = gross_profit - sga       (Nike has no operating income line)

with quarters as (
    select * from {{ ref('fiscal_quarters') }}
),

values_ as (
    select * from {{ ref('measure_values') }}
),

measures as (
    select distinct measure, statement from {{ ref('measures') }}
),

flow_quarters as (
    select q.*, m.measure
    from quarters as q
    cross join measures as m
    where m.statement <> 'balance'
),

flows as (
    select
        f.cik,
        f.fiscal_year,
        f.fiscal_quarter,
        f.period_end,
        f.measure,
        coalesce(single.value, ytd.value - coalesce(ytd_prev.value, 0)) as value,
        coalesce(single.tag, ytd.tag) as tag,
        case
            when single.value is not null then 'reported'
            when f.fiscal_quarter = 1 then 'reported'
            else 'year-to-date difference'
        end as method,
        coalesce(single.filed, ytd.filed) as filed,
        coalesce(single.accession, ytd.accession) as accession
    from flow_quarters as f
    left join values_ as single
        on single.cik = f.cik
        and single.measure = f.measure
        and single.period_end = f.period_end
        and single.duration_days between 80 and 100
    left join values_ as ytd
        on ytd.cik = f.cik
        and ytd.measure = f.measure
        and ytd.period_start = f.fy_start
        and ytd.period_end = f.period_end
    left join values_ as ytd_prev
        on ytd_prev.cik = f.cik
        and ytd_prev.measure = f.measure
        and ytd_prev.period_start = f.fy_start
        and ytd_prev.period_end = f.quarter_start - 1
    -- Without the earlier year-to-date figure the difference would be wrong.
    where single.value is not null
        or f.fiscal_quarter = 1
        or ytd_prev.value is not null
),

balances as (
    select
        q.cik,
        q.fiscal_year,
        q.fiscal_quarter,
        q.period_end,
        v.measure,
        v.value,
        v.tag,
        'reported' as method,
        v.filed,
        v.accession
    from quarters as q
    inner join values_ as v
        on v.cik = q.cik
        and v.period_end = q.period_end
        and v.statement = 'balance'
),

reported as (
    select * from flows where value is not null
    union all
    select * from balances
),

wide as (
    select
        cik,
        fiscal_year,
        fiscal_quarter,
        period_end,
        max(value) filter (where measure = 'revenue') as revenue,
        max(value) filter (where measure = 'cost_of_sales') as cost_of_sales,
        max(value) filter (where measure = 'gross_profit') as gross_profit,
        max(value) filter (where measure = 'sga') as sga
    from reported
    group by cik, fiscal_year, fiscal_quarter, period_end
),

missing as (
    select cik, fiscal_year, fiscal_quarter, period_end,
        'cost_of_sales' as measure, revenue - gross_profit as value
    from wide where cost_of_sales is null
    union all
    select cik, fiscal_year, fiscal_quarter, period_end,
        'gross_profit', revenue - cost_of_sales
    from wide where gross_profit is null
),

with_gross_profit as (
    select
        w.*,
        coalesce(w.gross_profit, m.value) as gross_profit_all
    from wide as w
    left join missing as m
        on m.cik = w.cik and m.period_end = w.period_end and m.measure = 'gross_profit'
),

calculated as (
    select * from missing
    union all
    select cik, fiscal_year, fiscal_quarter, period_end,
        'operating_income', gross_profit_all - sga
    from with_gross_profit as g
    where not exists (
        select 1 from reported as r
        where r.cik = g.cik and r.period_end = g.period_end and r.measure = 'operating_income'
    )
)

select * from reported
union all
select
    cik, fiscal_year, fiscal_quarter, period_end, measure, value,
    null as tag,
    'calculated' as method,
    null as filed,
    null as accession
from calculated
where value is not null
