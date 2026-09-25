-- One row per order line, exploded from the order event's items array.
select
    o.event_id                                   as order_event_id,
    o.order_id,
    o.event_time                                 as order_time,
    o.customer_id,
    item->>'product_id'                          as product_id,
    (item->>'quantity')::numeric::int            as quantity,
    (item->>'unit_price')::numeric               as unit_price,
    (item->>'quantity')::numeric * (item->>'unit_price')::numeric as line_total
from {{ ref('stg_events') }} o
cross join lateral jsonb_array_elements(o.items) as item
where o.event_type = 'order_placed' and o.items is not null
