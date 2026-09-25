with lines as (
    select i.*, (i.order_time >= now() - interval '7 days') as last_7d
    from {{ ref('int_order_items') }} i
    join {{ ref('fct_orders') }} o using (order_id)
)
select
    p.product_id,
    p.product_name,
    p.category,
    p.price,
    coalesce(sum(l.quantity), 0)                              as units,
    coalesce(sum(l.line_total), 0)                            as revenue,
    count(distinct l.order_id)                                as orders,
    coalesce(sum(l.quantity) filter (where l.last_7d), 0)     as units_7d,
    coalesce(sum(l.line_total) filter (where l.last_7d), 0)   as revenue_7d,
    rank() over (order by coalesce(sum(l.line_total), 0) desc) as revenue_rank
from {{ ref('dim_products') }} p
left join lines l using (product_id)
group by 1, 2, 3, 4
