-- Each part returns the rows that break a rule; the test passes when there are none.

-- 1. One row per company and quarter.
select 'duplicate quarter' as problem, cik, fiscal_year, fiscal_quarter, null as detail
from {{ ref('quarterly') }}
group by cik, fiscal_year, fiscal_quarter
having count(*) > 1

union all

-- 2. Every complete fiscal year has four quarters.
select 'incomplete year', cik, fiscal_year, null, count(*) || ' quarters'
from {{ ref('quarterly') }}
where (cik, fiscal_year) in (select cik, fiscal_year from {{ ref('fiscal_quarters') }} where is_complete)
group by cik, fiscal_year
having count(*) <> 4

union all

-- 3. The four quarters add up to the 10-K year (revenue and operating cash flow,
--    within 0.5% or $0.2M). Known exception: VF FY2023, see the README.
select 'quarters do not add up to the year', q.cik, q.fiscal_year, null,
    m.measure || ': ' || round(q.total, 1) || ' vs ' || round(m.value / 1e6, 1)
from (
    select cik, fiscal_year, 'revenue' as measure, sum(revenue) as total
    from {{ ref('quarterly') }} group by cik, fiscal_year having count(*) = 4
    union all
    select cik, fiscal_year, 'operating_cash_flow', sum(operating_cash_flow)
    from {{ ref('quarterly') }} group by cik, fiscal_year having count(*) = 4
) as q
inner join (select distinct cik, fiscal_year, fy_start, fy_end from {{ ref('fiscal_quarters') }}) as y
    on y.cik = q.cik and y.fiscal_year = q.fiscal_year
inner join {{ ref('measure_values') }} as m
    on m.cik = q.cik and m.measure = q.measure
    and m.period_start = y.fy_start and m.period_end = y.fy_end
where abs(q.total - m.value / 1e6) > greatest(0.005 * abs(m.value / 1e6), 0.2)
    and not (q.cik = 103379 and q.fiscal_year = 2023)

union all

-- 4. No missing inputs, apart from gaps in the filings: Gap reports receivables
--    only in its 10-K, and SG&A is only needed for Nike's operating income.
select 'missing input', q.cik, q.fiscal_year, q.fiscal_quarter, m.measure
from {{ ref('quarterly') }} as q
cross join (select distinct measure from {{ ref('measures') }} where measure <> 'sga') as m
left join {{ ref('quarterly_inputs') }} as i
    on i.cik = q.cik and i.period_end = q.period_end and i.measure = m.measure
where i.measure is null
    and not (q.ticker = 'GAP' and m.measure = 'receivables' and q.fiscal_quarter < 4)
