{{ config(
    materialized='incremental',
    unique_key='order_id',
    incremental_strategy='merge',
    on_schema_change='append_new_columns'
) }}
-- Orders fact. Incremental on the load watermark (loaded_at), not on event time, so an order
-- that arrives hours late is still picked up by the next build.
select distinct on (order_id)
    order_id,
    event_id                    as order_event_id,
    customer_id,
    session_id,
    event_time                  as order_time,
    amount,
    currency,
    jsonb_array_length(items)   as line_count,
    reason                      as promo,
    device,
    channel,
    loaded_at                   as _source_loaded_at,
    now()                       as _published_at
from {{ ref('stg_events') }}
where event_type = 'order_placed'
{% if is_incremental() %}
  and loaded_at > (select coalesce(max(_source_loaded_at), '1970-01-01') from {{ this }})
{% endif %}
order by order_id, loaded_at desc
