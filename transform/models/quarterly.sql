-- One row per company and fiscal quarter from FY2018: the nine inputs in
-- $ millions and the benchmarking measures (formulas in the README).
--
-- Days measures compare the balance at quarter end with the last four quarters
-- of revenue or cost of sales, so seasonal peaks do not distort them.
-- Growth compares with the quarter that ended about a year earlier.

with inputs as (
    select
        cik,
        fiscal_year,
        fiscal_quarter,
        period_end,
        max(value) filter (where measure = 'revenue') / 1e6 as revenue,
        max(value) filter (where measure = 'cost_of_sales') / 1e6 as cost_of_sales,
        max(value) filter (where measure = 'gross_profit') / 1e6 as gross_profit,
        max(value) filter (where measure = 'sga') / 1e6 as sga,
        max(value) filter (where measure = 'operating_income') / 1e6 as operating_income,
        max(value) filter (where measure = 'inventory') / 1e6 as inventory,
        max(value) filter (where measure = 'receivables') / 1e6 as receivables,
        max(value) filter (where measure = 'payables') / 1e6 as payables,
        max(value) filter (where measure = 'operating_cash_flow') / 1e6 as operating_cash_flow,
        max(filed) as filed
    from {{ ref('quarterly_inputs') }}
    group by cik, fiscal_year, fiscal_quarter, period_end
),

rolling as (
    select
        *,
        -- Sums over the last four quarters, only when all four are there.
        case when count(*) over last_4 = 4
            and min(period_end) over last_4 >= period_end - 300
            then sum(revenue) over last_4 end as revenue_4q,
        case when count(cost_of_sales) over last_4 = 4
            and min(period_end) over last_4 >= period_end - 300
            then sum(cost_of_sales) over last_4 end as cost_of_sales_4q,
        case when count(operating_cash_flow) over last_4 = 4
            and min(period_end) over last_4 >= period_end - 300
            then sum(operating_cash_flow) over last_4 end as operating_cash_flow_4q
    from inputs
    window last_4 as (partition by cik order by period_end rows between 3 preceding and current row)
),

with_prior_year as (
    select
        t.*,
        p.revenue as revenue_prior_year,
        p.inventory as inventory_prior_year
    from rolling as t
    left join inputs as p
        on p.cik = t.cik
        and p.period_end between t.period_end - 380 and t.period_end - 350
),

measures as (
    select
        *,
        revenue / nullif(revenue_prior_year, 0) - 1 as revenue_growth,
        gross_profit / nullif(revenue, 0) as gross_margin,
        operating_income / nullif(revenue, 0) as operating_margin,
        inventory / nullif(cost_of_sales_4q, 0) * 365 as inventory_days,
        receivables / nullif(revenue_4q, 0) * 365 as receivable_days,
        payables / nullif(cost_of_sales_4q, 0) * 365 as payable_days,
        operating_cash_flow_4q / nullif(revenue_4q, 0) as operating_cash_flow_margin,
        inventory / nullif(inventory_prior_year, 0) - 1 as inventory_growth
    from with_prior_year
)

select
    m.cik,
    c.company,
    c.ticker,
    m.fiscal_year,
    m.fiscal_quarter,
    m.period_end,
    year(m.period_end - 45) || '-Q' || quarter(m.period_end - 45) as calendar_quarter,
    round(m.revenue, 1) as revenue,
    round(m.cost_of_sales, 1) as cost_of_sales,
    round(m.gross_profit, 1) as gross_profit,
    round(m.sga, 1) as sga,
    round(m.operating_income, 1) as operating_income,
    round(m.inventory, 1) as inventory,
    round(m.receivables, 1) as receivables,
    round(m.payables, 1) as payables,
    round(m.operating_cash_flow, 1) as operating_cash_flow,
    m.revenue_growth,
    m.gross_margin,
    m.operating_margin,
    m.inventory_days,
    m.receivable_days,
    m.payable_days,
    m.inventory_days + m.receivable_days - m.payable_days as cash_conversion_cycle,
    m.inventory_growth - m.revenue_growth as inventory_growth_gap,
    m.operating_cash_flow_margin,
    m.filed
from measures as m
inner join {{ source('raw', 'companies') }} as c
    on m.cik = c.cik
where m.fiscal_year >= 2018
