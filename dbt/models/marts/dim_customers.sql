with orders as (
    select customer_id, min(order_time) as first_order_at, count(*) as orders, sum(amount) as revenue
    from {{ ref('fct_orders') }}
    group by 1
), sessions as (
    select customer_id, min(session_start) as first_seen_at, count(*) as sessions
    from {{ ref('int_sessions') }}
    group by 1
)
select
    c.customer_id,
    c.signup_at,
    c.country,
    c.acquisition_channel,
    s.first_seen_at,
    o.first_order_at,
    coalesce(s.sessions, 0)  as sessions,
    coalesce(o.orders, 0)    as orders,
    coalesce(o.revenue, 0)   as lifetime_revenue
from {{ ref('stg_customers') }} c
left join sessions s using (customer_id)
left join orders o using (customer_id)
