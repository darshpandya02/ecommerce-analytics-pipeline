-- Weekly cohorts by first-seen week; a customer is active in a week if they had a session.
with first_week as (
    select customer_id, min(activity_week) as cohort_week
    from {{ ref('int_customer_activity') }}
    group by 1
), sizes as (
    select cohort_week, count(*) as cohort_size from first_week group by 1
)
select
    f.cohort_week,
    ((a.activity_week - f.cohort_week) / 7)::int                          as week_number,
    s.cohort_size,
    count(distinct a.customer_id)                                         as active_customers,
    count(distinct a.customer_id) filter (where a.converting_sessions > 0) as purchasing_customers,
    round(count(distinct a.customer_id)::numeric / s.cohort_size, 4)      as retention_rate
from first_week f
join {{ ref('int_customer_activity') }} a using (customer_id)
join sizes s using (cohort_week)
group by 1, 2, 3
