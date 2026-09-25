-- Share of orders refunded, by order week and product category (plus an 'All' rollup).
with refunded as (
    select order_id, sum(refund_amount) as refunded_amount from {{ ref('fct_refunds') }} group by 1
), order_categories as (
    select distinct i.order_id, p.category
    from {{ ref('int_order_items') }} i join {{ ref('dim_products') }} p using (product_id)
), base as (
    select
        date_trunc('week', {{ local_day('o.order_time') }})::date as order_week,
        oc.category,
        o.order_id,
        o.amount,
        r.refunded_amount
    from {{ ref('fct_orders') }} o
    join order_categories oc using (order_id)
    left join refunded r using (order_id)
), unioned as (
    select order_week, category, order_id, amount, refunded_amount from base
    union all
    select distinct on (order_week, order_id) order_week, 'All', order_id, amount, refunded_amount from base
)
select
    order_week,
    category,
    count(distinct order_id)                                               as orders,
    count(distinct order_id) filter (where refunded_amount is not null)    as refunded_orders,
    round(count(distinct order_id) filter (where refunded_amount is not null)::numeric
          / nullif(count(distinct order_id), 0), 4)                        as refund_rate,
    coalesce(sum(refunded_amount), 0)                                      as refunded_amount
from unioned
group by 1, 2
