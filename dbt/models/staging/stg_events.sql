-- Typed view over the raw events. Parsing is defensive: values that do not match the declared
-- type become null so drift surfaces in tests and reconciliation instead of failing the build.
select
    event_id,
    event_type,
    event_time,
    sent_at,
    loaded_at,
    batch_id,
    payload->>'session_id'                              as session_id,
    payload->>'customer_id'                             as customer_id,
    payload->>'device'                                  as device,
    payload->>'channel'                                 as channel,
    payload->>'page'                                    as page,
    payload->>'product_id'                              as product_id,
    {{ safe_numeric("payload->>'quantity'") }}::int     as quantity,
    {{ safe_numeric("payload->>'unit_price'") }}        as unit_price,
    payload->>'order_id'                                as order_id,
    {{ safe_numeric("payload->>'amount'") }}            as amount,
    payload->>'currency'                                as currency,
    case when payload ? 'items' then (payload->>'items')::jsonb end as items,
    {{ safe_numeric("payload->>'refund_amount'") }}     as refund_amount,
    payload->>'reason'                                  as reason,
    (payload->>'schema_version')::numeric::int          as schema_version
from {{ source('raw', 'events') }}
