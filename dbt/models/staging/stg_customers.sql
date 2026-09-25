select customer_id, signup_at, country, acquisition_channel, loaded_at
from {{ source('raw', 'customers') }}
