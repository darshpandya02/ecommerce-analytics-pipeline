select product_id, name as product_name, category, price, loaded_at
from {{ source('raw', 'products') }}
