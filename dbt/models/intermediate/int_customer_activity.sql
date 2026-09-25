-- Customer x week activity, the basis for cohort retention.
select
    customer_id,
    date_trunc('week', {{ local_day('session_start') }})::date as activity_week,
    count(*)                                                   as sessions,
    count(*) filter (where converted)                          as converting_sessions
from {{ ref('int_sessions') }}
where customer_id is not null
group by 1, 2
