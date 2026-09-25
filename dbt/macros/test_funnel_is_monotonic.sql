{# Generic test: every funnel stage must be <= the stage before it. #}
{% test funnel_is_monotonic(model) %}
select *
from {{ model }}
where not (sessions >= product_view_sessions
       and product_view_sessions >= cart_sessions
       and cart_sessions >= checkout_sessions
       and checkout_sessions >= order_sessions)
{% endtest %}
