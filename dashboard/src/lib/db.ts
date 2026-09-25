import "server-only";
import { neon } from "@neondatabase/serverless";

// The dashboard connects as ecom_reader: SELECT on ecom_marts and ecom_ops only, and every
// session is forced read-only at the role level. All queries below are fixed strings.
const url = process.env.ECOM_READONLY_DATABASE_URL;
const sql = url ? neon(url) : null;

async function q<T>(strings: TemplateStringsArray, ...values: unknown[]): Promise<T[]> {
  if (!sql) throw new Error("ECOM_READONLY_DATABASE_URL is not set");
  return (await sql(strings, ...values)) as T[];
}

export type DailyRevenue = {
  day: string;
  orders: number;
  gross_revenue: number;
  net_revenue: number;
  refunded_amount: number;
  avg_order_value: number | null;
  first_orders: number;
};

export function dailyRevenue() {
  return q<DailyRevenue>`
    select to_char(day, 'YYYY-MM-DD') as day, orders::int as orders, gross_revenue::float8 as gross_revenue,
           net_revenue::float8 as net_revenue, refunded_amount::float8 as refunded_amount,
           avg_order_value::float8 as avg_order_value, first_orders::int as first_orders
    from ecom_marts.mart_daily_revenue
    where day <= (now() at time zone 'America/New_York')::date
    order by day`;
}

export type FunnelRow = {
  device: string;
  sessions: number;
  product_view_sessions: number;
  cart_sessions: number;
  checkout_sessions: number;
  order_sessions: number;
};

export function funnel(days: number) {
  return q<FunnelRow>`
    select device, sum(sessions)::int as sessions, sum(product_view_sessions)::int as product_view_sessions,
           sum(cart_sessions)::int as cart_sessions, sum(checkout_sessions)::int as checkout_sessions,
           sum(order_sessions)::int as order_sessions
    from ecom_marts.mart_conversion_funnel
    where day > (now() at time zone 'America/New_York')::date - ${days}::int
      and day <= (now() at time zone 'America/New_York')::date
    group by device order by sessions desc`;
}

export type DailyConversion = { day: string; sessions: number; order_sessions: number };

export function dailyConversion() {
  return q<DailyConversion>`
    select to_char(day, 'YYYY-MM-DD') as day, sum(sessions)::int as sessions, sum(order_sessions)::int as order_sessions
    from ecom_marts.mart_conversion_funnel
    where day <= (now() at time zone 'America/New_York')::date
    group by day order by day`;
}

export type CohortCell = {
  cohort_week: string;
  week_number: number;
  cohort_size: number;
  active_customers: number;
  purchasing_customers: number;
  retention_rate: number;
};

export function cohorts() {
  return q<CohortCell>`
    select to_char(cohort_week, 'YYYY-MM-DD') as cohort_week, week_number::int as week_number, cohort_size::int as cohort_size,
           active_customers::int as active_customers, purchasing_customers::int as purchasing_customers, retention_rate::float8 as retention_rate
    from ecom_marts.mart_cohort_retention
    where week_number >= 0
    order by cohort_week, week_number`;
}

export type ProductRow = {
  product_id: string;
  product_name: string;
  category: string;
  price: number;
  units: number;
  revenue: number;
  orders: number;
  units_7d: number;
  revenue_7d: number;
  revenue_rank: number;
};

export function topProducts(limit = 15) {
  return q<ProductRow>`
    select product_id, product_name, category, price::float8 as price, units::int as units,
           revenue::float8 as revenue, orders::int as orders, units_7d::int as units_7d,
           revenue_7d::float8 as revenue_7d, revenue_rank::int as revenue_rank
    from ecom_marts.mart_top_products order by revenue_rank, product_id limit ${limit}`;
}

export type RefundRow = { category: string; orders: number; refunded_orders: number; refund_rate: number; refunded_amount: number };

export function refundByCategory() {
  return q<RefundRow>`
    select category, sum(orders)::int as orders, sum(refunded_orders)::int as refunded_orders,
           (sum(refunded_orders)::float8 / nullif(sum(orders), 0)) as refund_rate,
           sum(refunded_amount)::float8 as refunded_amount
    from ecom_marts.mart_refund_rate group by category order by category = 'All' desc, refund_rate desc`;
}

export type Run = {
  run_id: number;
  trigger: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  window_start: string | null;
  window_end: string | null;
  rows_emitted: number | null;
  rows_inserted: number | null;
  duplicates_dropped: number | null;
  checks_total: number | null;
  checks_failed: number | null;
  failed_checks: string[] | null;
  duration_s: number | null;
  latency_p50_s: number | null;
  latency_p95_s: number | null;
  orders_published: number | null;
  ecom_bytes: number | null;
  github_run_id: string | null;
  error: string | null;
};

export function runs(limit = 60) {
  return q<Run>`
    select run_id::int, trigger, started_at::text, finished_at::text, status, window_start::text, window_end::text,
           rows_emitted, rows_inserted, duplicates_dropped, checks_total, checks_failed, failed_checks,
           extract(epoch from finished_at - started_at)::float8 as duration_s,
           latency_p50_s, latency_p95_s, orders_published, ecom_bytes::float8 as ecom_bytes, github_run_id, error
    from ecom_ops.pipeline_runs order by run_id desc limit ${limit}`;
}

export type HealthSummary = {
  last_success_at: string | null;
  last_loaded_at: string | null;
  runs_24h: number;
  ok_24h: number;
  scheduled_runs: number;
  p50_duration_s: number | null;
  p95_duration_s: number | null;
  p50_latency_s: number | null;
  p95_latency_s: number | null;
  ecom_bytes: number | null;
};

export async function healthSummary() {
  const rows = await q<HealthSummary>`
    with r as (select * from ecom_ops.pipeline_runs where github_run_id is not null)
    select
      (select max(finished_at)::text from ecom_ops.pipeline_runs where status in ('success', 'warning')) as last_success_at,
      (select max(updated_at)::text from ecom_ops.watermarks) as last_loaded_at,
      (select count(*)::int from r where started_at > now() - interval '24 hours') as runs_24h,
      (select count(*)::int from r where started_at > now() - interval '24 hours' and status in ('success', 'warning')) as ok_24h,
      (select count(*)::int from r where status <> 'running') as scheduled_runs,
      (select percentile_cont(0.5) within group (order by extract(epoch from finished_at - started_at)) from r where finished_at is not null) as p50_duration_s,
      (select percentile_cont(0.95) within group (order by extract(epoch from finished_at - started_at)) from r where finished_at is not null) as p95_duration_s,
      (select percentile_cont(0.5) within group (order by latency_p50_s) from r where latency_p50_s is not null) as p50_latency_s,
      (select percentile_cont(0.5) within group (order by latency_p95_s) from r where latency_p95_s is not null) as p95_latency_s,
      (select ecom_bytes::float8 from ecom_ops.pipeline_runs where ecom_bytes is not null order by run_id desc limit 1) as ecom_bytes`;
  return rows[0];
}

export type CheckRow = { check_name: string; suite: string; severity: string; runs: number; failures: number; last_failed_run: number | null; last_observed: unknown };

export function checkStats(lastRuns = 200) {
  return q<CheckRow>`
    with recent as (select run_id from ecom_ops.pipeline_runs order by run_id desc limit ${lastRuns})
    select check_name, min(suite) as suite, min(severity) as severity, count(*)::int as runs,
           count(*) filter (where not success)::int as failures,
           max(run_id) filter (where not success)::int as last_failed_run,
           (array_agg(observed order by run_id desc) filter (where not success))[1] as last_observed
    from ecom_ops.quality_results where run_id in (select run_id from recent)
    group by check_name order by failures desc, check_name`;
}

export type AnomalyRow = { run_id: number; anomaly_type: string; rows_affected: number; detected: boolean | null; detected_by: string[] | null; created_at: string; trigger: string };

export function anomalies() {
  return q<AnomalyRow>`
    select a.run_id::int, a.anomaly_type, a.rows_affected, a.detected, a.detected_by, a.created_at::text, r.trigger
    from ecom_ops.injected_anomalies a join ecom_ops.pipeline_runs r using (run_id)
    order by a.run_id desc`;
}

export type FalsePositive = { clean_runs: number; clean_runs_with_failures: number };

export async function falsePositives() {
  const rows = await q<FalsePositive>`
    select count(*)::int as clean_runs, count(*) filter (where checks_failed > 0)::int as clean_runs_with_failures
    from ecom_ops.pipeline_runs r
    where status <> 'running' and not exists (select 1 from ecom_ops.injected_anomalies a where a.run_id = r.run_id)`;
  return rows[0];
}
