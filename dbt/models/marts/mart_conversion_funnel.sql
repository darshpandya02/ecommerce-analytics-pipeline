select
    {{ local_day('session_start') }}              as day,
    device,
    count(*)                                      as sessions,
    count(*) filter (where viewed_product)        as product_view_sessions,
    count(*) filter (where added_to_cart)         as cart_sessions,
    count(*) filter (where started_checkout)      as checkout_sessions,
    count(*) filter (where converted)             as order_sessions
from {{ ref('int_sessions') }}
group by 1, 2
