{# Cast text to numeric only when it looks like a number. Drifted values become null, which the
   quality layer then reports, instead of crashing the whole build. #}
{% macro safe_numeric(expr) -%}
    case when ({{ expr }}) ~ '^-?[0-9]+(\.[0-9]+)?$' then ({{ expr }})::numeric end
{%- endmacro %}
