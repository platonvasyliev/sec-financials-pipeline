-- One value per company, measure and period, from the tags listed in measures.csv.
--
-- Each filing repeats earlier periods for comparison, and companies restate them,
-- e.g. after selling a business. All numbers of a fiscal year come from the
-- latest filing made within 15 months after that fiscal year ended. That takes in
-- the restated figures in next year's reports, so growth compares like with like
-- and the quarters match the year, but not restatements made years later, which
-- cover full years only. For the year in progress the 15 months run from the
-- period end. If nothing was filed in the window, the earliest filing is used.
-- Within the chosen filing:
--   revenue: the largest revenue tag, because some companies use the first tag
--            for only part of their sales (Caleres, Steve Madden)
--   others:  the first tag in the priority list of measures.csv

with facts as (
    select
        f.cik,
        t.measure,
        t.statement,
        f.tag,
        t.priority,
        f.period_start,
        f.period_end,
        datediff('day', f.period_start, f.period_end) + 1 as duration_days,  -- null for balance sheet items
        f.value,
        f.filed,
        f.accession
    from {{ source('raw', 'facts') }} as f
    inner join {{ ref('measures') }} as t
        on f.tag = t.tag
),

full_years as (
    select distinct cik, period_start, period_end
    from facts
    where measure = 'revenue' and duration_days between 350 and 380
),

with_year_end as (
    select
        f.*,
        (
            select min(y.period_end)
            from full_years as y
            where y.cik = f.cik
                and y.period_start <= f.period_end
                and y.period_end >= f.period_end
        ) as fiscal_year_end
    from facts as f
),

ranked as (
    select
        *,
        filed <= coalesce(fiscal_year_end, period_end) + interval 455 day as in_window
    from with_year_end
),

chosen_filing as (
    select *
    from ranked
    qualify filed = first_value(filed) over (
        partition by cik, measure, period_start, period_end
        order by in_window desc, case when in_window then filed end desc, filed
    )
)

select
    cik,
    measure,
    statement,
    period_start,
    period_end,
    duration_days,
    case when measure = 'revenue' then max(value) else arg_min(value, priority) end as value,
    case when measure = 'revenue' then arg_max(tag, value) else arg_min(tag, priority) end as tag,
    max(filed) as filed,
    arg_min(accession, priority) as accession
from chosen_filing
group by cik, measure, statement, period_start, period_end, duration_days
