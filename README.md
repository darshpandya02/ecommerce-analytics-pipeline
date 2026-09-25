# E-commerce analytics pipeline

Rebuilt from scratch in 2026. The original 2024 project code was not preserved.

A scheduled, batch-incremental analytics pipeline for a simulated online store. Every 30 minutes a
GitHub Actions job produces the store's newest events, lands them as Parquet, loads them idempotently
into Postgres, rebuilds dbt models, runs Great Expectations suites and records the run. A public,
read-only Next.js dashboard reads the marts and the run history.

- Dashboard: https://ecommerce-analytics-pipeline.vercel.app (pipeline health: [/health](https://ecommerce-analytics-pipeline.vercel.app/health))
- Scheduler: [`.github/workflows/pipeline.yml`](.github/workflows/pipeline.yml), run history under [Actions](https://github.com/darshpandya02/ecommerce-analytics-pipeline/actions)

## Architecture

```mermaid
flowchart LR
    subgraph GHA["GitHub Actions (cron 7,37 * * * *)"]
        G["Synthetic store source<br/>pipeline/generator.py<br/>seeded, 5 min buckets,<br/>late + duplicate events,<br/>injected anomalies"]
        P[("Raw zone<br/>Parquet (zstd)<br/>dt=/batch=")]
        QR["Great Expectations<br/>raw_batch suite"]
        L["Loader<br/>COPY + ON CONFLICT (event_id)<br/>watermark + manifest<br/>one transaction"]
        D["dbt build<br/>staging, intermediate, marts<br/>+ 39 dbt tests<br/>+ source freshness"]
        QM["Great Expectations<br/>marts + reconciliation"]
        R["Run record, retention,<br/>alert issue on failure"]
        G --> P --> QR --> L --> D --> QM --> R
    end
    subgraph PG["Neon Postgres (shared database, ecom_* schemas only)"]
        RAW[(ecom_raw)]
        STG[(ecom_staging)]
        MART[(ecom_marts)]
        OPS[(ecom_ops)]
    end
    L --> RAW
    D --> STG
    D --> MART
    QR -.results.-> OPS
    QM -.results.-> OPS
    R --> OPS
    MART --> W["Next.js dashboard on Vercel<br/>role ecom_reader: SELECT on marts + ops,<br/>read-only sessions"]
    OPS --> W
```

### How a run works

1. **Source.** `pipeline/generator.py` simulates the store in 5 minute buckets. A bucket's sessions
   are a pure function of `(seed, bucket start)`: traffic follows an hourly and weekly curve, promo
   days (Labor Day, a fall flash sale) lift traffic and conversion, returning customers are drawn with
   an exponential recency preference (which produces decaying cohorts), and each session walks a funnel
   (page views, product views, add to cart, checkout, order, sometimes a refund days later). About 2 %
   of events are delivered 30 min to 24 h late and 1 % are delivered twice. A batch holds every event
   whose delivery time falls in `(watermark, now]`, so the source is replayable: a failed run is
   repaired by regenerating the same window.
2. **Anomalies.** With probability 0.4 a scheduled batch is corrupted in one of nine ways (new column,
   renamed `amount`, `amount` sent as a string, `customer_id` null burst, duplicate storm, x100 price,
   volume drop, clock skew forward or back). The injection and the number of rows it touched are
   written to `ecom_ops.injected_anomalies` as ground truth. Manual drills force a specific type
   through `workflow_dispatch`.
3. **Raw zone.** The batch is written as Parquet exactly as delivered (drifted columns included) and
   kept as a 7-day workflow artifact.
4. **Raw checks.** A Great Expectations suite validates the Parquet batch: column contract, event id
   nulls and uniqueness, allowed event types, `customer_id` nulls, order amount presence, type and
   range, events stamped in the future, delivery lag beyond the 24 h SLA, and row count against a
   baseline built from the same clock window on each of the previous 7 days.
5. **Freshness.** `dbt source freshness` measures staleness of `ecom_raw.events` before the load.
6. **Load.** Events are copied into a temp table and inserted with `ON CONFLICT (event_id) DO NOTHING`;
   customers and products are upserted; the file, checksum and counts go to `ecom_raw.load_manifest`
   and the watermark advances, all in one transaction. Reloading a file inserts 0 rows.
7. **dbt build.** Staging views parse the JSON payload defensively (drifted values become null instead
   of failing the build). `int_sessions`, `fct_orders` and `fct_refunds` are incremental merge models
   keyed on the load time (`loaded_at`), not event time, so a late event updates the session or order it
   belongs to. Marts: daily revenue, conversion funnel, weekly cohort retention, top products, refund
   rate by category, customer and product dimensions. 39 dbt tests (unique, not_null, relationships,
   accepted_values and a custom funnel monotonicity test); key uniqueness tests are `error`, the rest
   `warn`.
8. **Mart checks and reconciliation.** Great Expectations checks on the marts, plus a per-run revenue
   reconciliation: the producer's order totals in this batch (read leniently, including drifted
   formats) must match what `fct_orders` published within 0.1 %, and every order in the batch must be
   published. Reconciliation failures are `error` severity.
9. **Record and alert.** The run row in `ecom_ops.pipeline_runs` gets status, rows, step timings,
   failed checks, event-to-mart latency percentiles and warehouse size. `failed` (a step raised or an
   error-severity check failed) exits non-zero; the workflow then opens or comments on a single
   `pipeline-alert` issue, and closes it after the next successful run. `warning` means warn-level
   checks failed but data was published.
10. **Retention.** Raw events older than 30 days are deleted; incremental facts are kept 180 days, so
    marts keep history after the raw rows behind them are purged.

## Real stack vs. the originally listed stack

| Layer | Originally listed (2024) | This rebuild (what actually runs) |
|---|---|---|
| Event source | Kafka | Deterministic synthetic store source in Python, delivered as micro-batches. No broker. |
| Stream / batch compute | Spark | Python (pandas, pyarrow) inside the scheduled job; volumes are small enough that Spark would add nothing |
| Ingestion | Airbyte | Custom loader: Parquet raw zone, `COPY` + `ON CONFLICT`, watermark and load manifest |
| Orchestration | Airflow | GitHub Actions cron (every 30 min) with a concurrency group. No Airflow DAG is included because none was run. |
| Warehouse | Snowflake | Neon Postgres 18 (shared free-tier database, isolated `ecom_*` schemas) |
| Transformation | dbt | dbt-core 1.12 + dbt-postgres 1.11 |
| Data quality | Great Expectations | Great Expectations 1.23 (ephemeral context) + dbt tests, results persisted to `ecom_ops.quality_results` |
| Infrastructure as code | Terraform | Not used. Schemas are created by idempotent SQL (`sql/bootstrap.sql`); the dashboard role by `scripts/create_readonly_role.py`. |
| Monitoring | Prometheus / Grafana | Run history in Postgres, a Next.js "pipeline health" page, and GitHub issues as the alert channel |
| Dashboard | (not listed) | Next.js 16 on Vercel, public and read-only |

## Run it locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20+, and a Postgres database you
can create schemas in.

```bash
uv sync
export ECOM_DATABASE_URL='postgresql://user:pass@host/db?sslmode=require'

uv run pytest -q                        # source determinism + offline anomaly drill (no database)
uv run python -m pipeline.run           # first run backfills from 2026-08-24, later runs are incremental
uv run python -m pipeline.run --force-anomaly schema_renamed_column   # drill one failure mode

# read-only role for the dashboard
ECOM_READER_PASSWORD='...' PYTHONPATH=. uv run python scripts/create_readonly_role.py

cd dashboard && npm install
echo "ECOM_READONLY_DATABASE_URL=postgresql://ecom_reader:...@host/db?sslmode=require" > .env.local
npm run build && npm start
```

dbt can also be run directly: `cd dbt && DBT_PROFILES_DIR=. ECOM_PGHOST=... ECOM_PGUSER=... ECOM_PGPASSWORD=... ECOM_PGDATABASE=... uv run dbt build`.

In GitHub Actions the only secret is `ECOM_DATABASE_URL`.

## Measured results

Measured on 2026-09-25 against the live Neon database. Run records are in `ecom_ops.pipeline_runs` and on
the [health page](https://ecommerce-analytics-pipeline.vercel.app/health).

**Runs (n = 12 GitHub Actions runs that executed the pipeline, 16:13 to 18:18 UTC).** GitHub never fired
the `schedule` trigger for this new repository during the measurement window (0 cron runs across five
slots), so every run was a `workflow_dispatch` on the same workflow: 3 anomaly drills, 3 dispatches at
the 30-minute cadence, and 6 dispatched back-to-back. The cron schedule is still configured.

| Metric | Value |
|---|---|
| Pipeline duration per run (bootstrap to retention) | p50 22.4 s, p95 28.3 s (n = 12) |
| GitHub job wall time (includes `uv sync`) | 34 s to 60 s |
| Slowest steps (median) | `dbt build` 12.4 s, `dbt source freshness` 7.5 s, raw checks 0.6 s, load 0.5 s |
| Events per run at the 30-minute cadence | 46 to 148 (back-to-back runs: 0 to 3) |
| Total events inserted by the 12 runs / duplicates dropped | 502 / 13 |
| Initial backfill (local, 2026-08-24 to 2026-09-25) | 159,676 events delivered, 158,060 inserted, 1,616 duplicates dropped; load 7.8 s; reloading the same file inserted 0 rows |
| Event-to-mart latency, runs at the 30-minute cadence (n = 3) | per-run p50 227 s to 753 s, p95 599 s to 1,186 s |
| Event-to-mart latency, back-to-back runs (n = 6) | per-run p50 42 s to 86 s |
| Data freshness | dbt source freshness passed in all 12 runs; about 1 min right after the last run |
| Checks per run | 48 to 59 (GX raw batch, GX marts, reconciliation, 39 dbt tests, freshness); 774 results stored |
| Warehouse size (`ecom_*` only) | 65.2 MB (ecom_raw 60.3, ecom_staging 3.0, ecom_marts 1.5, ecom_ops 0.4); 147,774 raw events kept under 30-day retention |

**Anomaly detection.**

- Live runs: 3 injected anomalies touched rows, and 3 were caught. The duplicate burst (9 rows) was
  caught by `raw.event_id_uniqueness`. Two null bursts (50 and 40 rows) were caught by
  `raw.customer_id_not_null`, and the second one also by the dbt test
  `not_null_fct_orders_customer_id`. The ground-truth row for the first null burst (run 4) was lost to
  the bug described below, so `ecom_ops.injected_anomalies` holds 2 rows. One drill
  (`schema_renamed_column`) found no order event in its window, so nothing was injected. This live
  sample covers only 2 of the 9 anomaly types.
- Offline drill (`uv run pytest`, each type forced into a 2-hour batch): 8 of 9 types were caught by
  their designed check. `price_spike` was missed: x100 of a small basket stays under the $2,500 range
  limit, and the test marks it as an expected failure.
- False positives: none of the 10 runs without an injection failed a raw-batch, mart or reconciliation
  check. 6 of them did end in `warning`, because the dbt test `not_null_fct_orders_customer_id` kept
  failing on 1 order that run 9's null burst had already published. The test checks the whole table,
  so the problem stays flagged until someone fixes the row.

**Failed runs.**

- GitHub run 36159303281 (16:12 UTC) failed at job setup because `astral-sh/setup-uv@v10` has no
  major-version tag. No pipeline code ran. Fixed by pinning `v10.2.0`.
- Pipeline run 4 (GitHub 36163500774, 16:52 UTC, `null_burst` drill) was a real bug. The anomaly was
  detected, but writing the results crashed: Great Expectations sampled the null values as `NaN`,
  which Postgres `jsonb` rejects. The run marked itself `failed` and opened issue #1. Fixed in
  `ecd692a`: observations are now converted to strict JSON, ground truth is committed first, and there
  is a regression test. The next successful run closed issue #1.


## Limitations

- **Batch, not streaming.** Latency is bounded by the 30 minute schedule plus GitHub's cron delay;
  nothing here is sub-minute. The "real-time" part of the original title is not reproduced.
- **Synthetic data.** The store, its customers and its anomalies are simulated. Detection rates show
  that the checks work against the failure modes they were designed for, not against unknown ones.
- **Raw zone is ephemeral.** Parquet batches live on the runner and as 7-day workflow artifacts, not in
  object storage. Postgres keeps the full source record in `ecom_raw.events.payload`, which is what
  staging rebuilds from.
- **Anomalies are not quarantined.** Corrupted batches are loaded and flagged; staging nulls
  unparseable values. A drifted order stays under-reported in marts until the source is fixed, and
  whole-table dbt tests keep warning on bad rows that were already published.
- **Cron reliability.** GitHub's `schedule` trigger did not fire at all during the measured window;
  the numbers above come from manual dispatches of the same workflow.
- **Shared, small warehouse.** Neon's free tier with other projects in the same database; volume is
  sized (about 700 sessions a day) to stay far below the 150 MB budget, and compute wakes every
  30 minutes.
- **Single writer.** Incremental models assume one run at a time, which the workflow's concurrency
  group enforces.
- **Full refresh loses history.** Marts beyond the 30-day raw window only exist in the incremental
  facts; `dbt build --full-refresh` would rebuild them from the retained raw rows only.
