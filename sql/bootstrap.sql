-- Idempotent DDL for the pipeline-owned schemas. Safe to run on every pipeline start.
-- Only ecom_* schemas are created or modified here.

create schema if not exists ecom_raw;
create schema if not exists ecom_staging;
create schema if not exists ecom_marts;
create schema if not exists ecom_ops;

-- Raw zone mirror: one row per distinct event_id. The full source record is kept in payload
-- so that staging can be rebuilt after a contract change without re-ingesting.
create table if not exists ecom_raw.events (
    event_id    text primary key,
    event_type  text not null,
    event_time  timestamptz not null,
    sent_at     timestamptz,
    batch_id    text not null,
    loaded_at   timestamptz not null default now(),
    payload     jsonb not null
);
create index if not exists events_loaded_at_idx on ecom_raw.events (loaded_at);
create index if not exists events_event_time_idx on ecom_raw.events (event_time);

create table if not exists ecom_raw.customers (
    customer_id          text primary key,
    signup_at            timestamptz not null,
    country              text,
    acquisition_channel  text,
    loaded_at            timestamptz not null default now()
);

create table if not exists ecom_raw.products (
    product_id  text primary key,
    name        text not null,
    category    text not null,
    price       numeric(10, 2) not null,
    loaded_at   timestamptz not null default now()
);

-- Every Parquet file that was loaded, with its checksum, so reloads are auditable.
create table if not exists ecom_raw.load_manifest (
    batch_id            text primary key,
    file_path           text not null,
    file_bytes          bigint not null,
    sha256              text not null,
    window_start        timestamptz not null,
    window_end          timestamptz not null,
    rows_in_file        integer not null,
    rows_inserted       integer not null,
    duplicates_dropped  integer not null,
    loaded_at           timestamptz not null default now()
);

create table if not exists ecom_ops.watermarks (
    name        text primary key,
    value       timestamptz not null,
    updated_at  timestamptz not null default now()
);

create table if not exists ecom_ops.pipeline_runs (
    run_id              bigserial primary key,
    github_run_id       text,
    trigger             text not null,
    started_at          timestamptz not null default now(),
    finished_at         timestamptz,
    status              text not null default 'running',   -- running | success | warning | failed
    window_start        timestamptz,
    window_end          timestamptz,
    rows_emitted      integer,
    rows_inserted       integer,
    duplicates_dropped  integer,
    rows_deleted_retention integer,
    dbt_nodes_ok        integer,
    dbt_nodes_failed    integer,
    checks_total        integer,
    checks_failed       integer,
    failed_checks       text[],
    step_seconds        jsonb,
    latency_p50_s       double precision,
    latency_p95_s       double precision,
    orders_published    integer,
    ecom_bytes          bigint,
    error               text
);

create table if not exists ecom_ops.quality_results (
    id          bigserial primary key,
    run_id      bigint not null references ecom_ops.pipeline_runs (run_id) on delete cascade,
    suite       text not null,        -- raw_batch | marts | reconciliation | dbt_test | dbt_freshness
    check_name  text not null,
    severity    text not null,        -- error | warn
    success     boolean not null,
    observed    jsonb,
    created_at  timestamptz not null default now()
);
create index if not exists quality_results_run_idx on ecom_ops.quality_results (run_id);

-- Ground truth of what the source injected, used to score the quality layer.
create table if not exists ecom_ops.injected_anomalies (
    id             bigserial primary key,
    run_id         bigint not null references ecom_ops.pipeline_runs (run_id) on delete cascade,
    batch_id       text not null,
    anomaly_type   text not null,
    rows_affected  integer not null,
    detected       boolean,
    detected_by    text[],
    created_at     timestamptz not null default now()
);
