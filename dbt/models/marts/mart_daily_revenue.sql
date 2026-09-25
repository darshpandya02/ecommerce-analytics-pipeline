with orders as (
    select
        {{ local_day('o.order_time') }}                                   as day,
        count(*)                                                          as orders,
        coalesce(sum(o.amount), 0)                                        as gross_revenue,
        count(distinct o.customer_id)                                     as customers,
        count(*) filter (where o.order_time = c.first_order_at)           as first_orders
    from {{ ref('fct_orders') }} o
    left join {{ ref('dim_customers') }} c using (customer_id)
    group by 1
), refunds as (
    select {{ local_day('refund_time') }} as day, count(*) as refunds, coalesce(sum(refund_amount), 0) as refunded
    from {{ ref('fct_refunds') }}
    group by 1
), days as (
    select day from orders union select day from refunds
)
select
    d.day,
    coalesce(o.orders, 0)                                              as orders,
    coalesce(o.gross_revenue, 0)                                       as gross_revenue,
    coalesce(r.refunds, 0)                                             as refunds,
    coalesce(r.refunded, 0)                                            as refunded_amount,
    coalesce(o.gross_revenue, 0) - coalesce(r.refunded, 0)             as net_revenue,
    round(o.gross_revenue / nullif(o.orders, 0), 2)                    as avg_order_value,
    coalesce(o.customers, 0)                                           as customers,
    coalesce(o.first_orders, 0)                                        as first_orders
from days d
left join orders o using (day)
left join refunds r using (day)
