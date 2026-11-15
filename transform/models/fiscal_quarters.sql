-- Fiscal years and quarters per company.
--
-- Fiscal years come from the full-year revenue in each 10-K. The year in progress
-- has no 10-K yet: it starts the day after the last one and is assumed to run one
-- year. A fiscal year is named after the calendar year holding most of its months:
-- Feb 2025 - Jan 2026 is FY2025, June 2025 - May 2026 is FY2025 (Nike calls it 2026).
--
-- Quarters are the revenue periods that end inside a fiscal year, either a single
-- quarter or a year-to-date figure. Transition periods after a change of year end
-- belong to no fiscal year and are dropped.

with reported as (
    select cik, period_start as fy_start, period_end as fy_end, true as is_complete
    from {{ ref('measure_values') }}
    where measure = 'revenue' and duration_days between 350 and 380
),

in_progress as (
    select
        cik,
        max(fy_end) + 1 as fy_start,
        cast(max(fy_end) + interval 1 year as date) as fy_end,
        false as is_complete
    from reported
    group by cik
),

all_years as (
    select * from reported
    union all
    select * from in_progress
),

fiscal_years as (
    select
        cik,
        case when month(fy_end) >= 6 then year(fy_end) else year(fy_end) - 1 end as fiscal_year,
        fy_start,
        fy_end,
        is_complete
    from all_years
    -- A few companies tagged the same year with two end dates a day apart
    -- (1 and 2 February); keep the later one, as for quarters.
    qualify row_number() over (partition by cik, fiscal_year order by fy_end desc) = 1
),

quarter_ends as (
    select distinct
        y.cik,
        y.fiscal_year,
        y.fy_start,
        y.fy_end,
        y.is_complete,
        v.period_end
    from {{ ref('measure_values') }} as v
    inner join fiscal_years as y
        on v.cik = y.cik
        and v.period_end > y.fy_start
        and v.period_end <= y.fy_end
    where v.measure = 'revenue'
        and (v.duration_days between 80 and 100 or v.period_start = y.fy_start)
),

numbered as (
    select
        *,
        least(4, greatest(1, round(datediff('day', fy_start, period_end) / 91.3)))::int
            as fiscal_quarter
    from quarter_ends
),

-- One end date per quarter. Where a company tagged two dates for the same
-- quarter (Lands' End FY2019 Q4: 30 and 31 January), the later one is kept.
deduplicated as (
    select *
    from numbered
    qualify row_number() over (
        partition by cik, fiscal_year, fiscal_quarter order by period_end desc
    ) = 1
)

select
    cik,
    fiscal_year,
    fiscal_quarter,
    fy_start,
    fy_end,
    coalesce(
        lag(period_end) over (partition by cik, fiscal_year order by period_end) + 1,
        fy_start
    ) as quarter_start,
    period_end,
    is_complete
from deduplicated
