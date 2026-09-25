{% macro local_day(ts) -%}
    (({{ ts }}) at time zone 'America/New_York')::date
{%- endmacro %}
