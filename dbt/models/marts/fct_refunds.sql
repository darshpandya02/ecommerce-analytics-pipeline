{{ config(
    materialized='incremental',
    unique_key='refund_event_id',
    incremental_strategy='merge',
    on_schema_change='append_new_columns'
) }}
select
    event_id        as refund_event_id,
    order_id,
    event_time      as refund_time,
    refund_amount,
    reason,
    loaded_at       as _source_loaded_at,
    now()           as _published_at
from {{ ref('stg_events') }}
where event_type = 'refund_issued'
{% if is_incremental() %}
  and loaded_at > (select coalesce(max(_source_loaded_at), '1970-01-01') from {{ this }})
{% endif %}
