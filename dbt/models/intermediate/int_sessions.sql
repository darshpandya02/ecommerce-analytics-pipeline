{{ config(
    materialized='incremental',
    unique_key='session_id',
    incremental_strategy='merge',
    on_schema_change='append_new_columns'
) }}
-- Session rollup with funnel flags. Incremental: only sessions that received events since the
-- last build are recomputed (from all of their events), so late-arriving events update the
-- session they belong to instead of creating a partial duplicate.
with touched as (
    select distinct session_id
    from {{ ref('stg_events') }}
    {% if is_incremental() %}
    where loaded_at > (select coalesce(max(_source_loaded_at), '1970-01-01') from {{ this }})
    {% endif %}
)
select
    e.session_id,
    max(e.customer_id)                                       as customer_id,
    max(e.device)                                            as device,
    max(e.channel)                                           as channel,
    min(e.event_time)                                        as session_start,
    max(e.event_time)                                        as session_end,
    count(*)                                                 as events,
    bool_or(e.event_type = 'product_view')                   as viewed_product,
    bool_or(e.event_type = 'add_to_cart')                    as added_to_cart,
    bool_or(e.event_type = 'checkout_started')               as started_checkout,
    bool_or(e.event_type = 'order_placed')                   as converted,
    max(e.loaded_at)                                         as _source_loaded_at
from {{ ref('stg_events') }} e
join touched t using (session_id)
where e.session_id is not null
group by e.session_id
