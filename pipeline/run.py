"""One pipeline run: generate -> land -> validate raw -> load -> dbt build -> validate marts.

Every run is recorded in ecom_ops.pipeline_runs. Exit code is 1 when the run failed (a step
raised, or an error-severity check failed) so the scheduler can alert on it.

    uv run python -m pipeline.run                # incremental run up to now
    uv run python -m pipeline.run --until 2026-09-25T15:00:00Z
    uv run python -m pipeline.run --force-anomaly null_burst
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import config, db, generator, ingest, quality, retention

DBT_DIR = config.ROOT / "dbt"


def dbt_env() -> dict:
    u = urlparse(config.database_url())
    env = dict(os.environ)
    env.update({
        "ECOM_PGHOST": u.hostname or "",
        "ECOM_PGPORT": str(u.port or 5432),
        "ECOM_PGUSER": unquote(u.username or ""),
        "ECOM_PGPASSWORD": unquote(u.password or ""),
        "ECOM_PGDATABASE": (u.path or "/").lstrip("/"),
        "DBT_PROFILES_DIR": str(DBT_DIR),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    })
    return env


def dbt(*args: str) -> int:
    cmd = [str(Path(sys.executable).parent / "dbt"), *args, "--project-dir", str(DBT_DIR)]
    proc = subprocess.run(cmd, cwd=DBT_DIR, env=dbt_env(), capture_output=True, text=True)
    tail = "\n".join(proc.stdout.strip().splitlines()[-6:])
    print(f"$ dbt {' '.join(args)} -> exit {proc.returncode}\n{tail}", flush=True)
    return proc.returncode


class Timer:
    def __init__(self):
        self.steps: dict[str, float] = {}

    def __call__(self, name):
        timer = self

        class _Step:
            def __enter__(self):
                self.t = time.perf_counter()

            def __exit__(self, *exc):
                timer.steps[name] = round(time.perf_counter() - self.t, 3)

        return _Step()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="window end (ISO, UTC); defaults to now")
    ap.add_argument("--trigger", default=os.environ.get("ECOM_TRIGGER", "manual"))
    ap.add_argument("--force-anomaly", choices=generator.ANOMALY_TYPES)
    ap.add_argument("--no-anomalies", action="store_true")
    args = ap.parse_args(argv)
    if args.no_anomalies:
        config.ANOMALY_RATE = 0.0

    timer = Timer()
    run_started = time.perf_counter()
    with db.connect() as conn:
        with timer("bootstrap"):
            db.bootstrap(conn)
        with conn.cursor() as cur:
            cur.execute("insert into ecom_ops.pipeline_runs (trigger, github_run_id) values (%s, %s) "
                        "returning run_id, started_at",
                        (args.trigger, os.environ.get("GITHUB_RUN_ID")))
            run_id, started_at = cur.fetchone()
        conn.commit()
        print(f"run {run_id} started {started_at.isoformat()}", flush=True)

        fields: dict = {}
        checks: list[quality.Check] = []
        status, error = "success", None
        batch = None
        try:
            window_start = ingest.get_watermark(conn) or config.STORE_EPOCH
            window_end = (datetime.fromisoformat(args.until.replace("Z", "+00:00")) if args.until
                          else datetime.now(timezone.utc)).replace(microsecond=0)
            fields.update(window_start=window_start, window_end=window_end)

            with timer("generate"):
                batch = generator.generate_window(window_start, window_end)
                batch = generator.inject_anomaly(batch, force=args.force_anomaly)
            with timer("land_parquet"):
                batch_dir = ingest.land(batch)
            fields["rows_emitted"] = len(batch.events)
            print(f"window {window_start:%Y-%m-%d %H:%M} -> {window_end:%Y-%m-%d %H:%M}: "
                  f"{len(batch.events)} events, anomaly={batch.anomaly}", flush=True)

            with timer("quality_raw"):
                baseline = quality.volume_baseline(conn, window_start, window_end)
                checks += quality.raw_batch_checks(ingest.read_events(batch_dir), baseline)
            with timer("load"):
                res = ingest.load(conn, batch_dir)
            fields.update(rows_inserted=res.rows_inserted, duplicates_dropped=res.duplicates_dropped)

            with timer("dbt_freshness"):
                dbt("source", "freshness")
                checks += quality.freshness_check(DBT_DIR / "target")
            with timer("dbt_build"):
                rc = dbt("build")
            rr = json.loads((DBT_DIR / "target" / "run_results.json").read_text())
            nodes = [r for r in rr["results"] if not r["unique_id"].startswith("test.")]
            fields["dbt_nodes_ok"] = sum(r["status"] == "success" for r in nodes)
            fields["dbt_nodes_failed"] = sum(r["status"] != "success" for r in nodes)
            checks += quality.dbt_checks(DBT_DIR / "target")
            if rc != 0 and not any(c.severity == "error" and not c.success for c in checks):
                raise RuntimeError(f"dbt build exited {rc}")

            with timer("quality_marts"):
                checks += quality.mart_checks(conn)
                checks += quality.reconciliation_checks(conn, res.batch_id)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    select count(*),
                           percentile_cont(0.5) within group (order by extract(epoch from _published_at - order_time)),
                           percentile_cont(0.95) within group (order by extract(epoch from _published_at - order_time))
                    from ecom_marts.fct_orders where _source_loaded_at >= %s
                    """,
                    (started_at,),
                )
                n, p50, p95 = cur.fetchone()
            fields.update(orders_published=n, latency_p50_s=p50, latency_p95_s=p95)

            with timer("retention"):
                fields["rows_deleted_retention"] = retention.run(conn)
        except Exception as exc:  # recorded, then surfaced through the exit code
            conn.rollback()
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

        failed = [c for c in checks if not c.success]
        if status != "failed":
            if any(c.severity == "error" for c in failed):
                status = "failed"
            elif failed:
                status = "warning"
        try:
            quality.persist(conn, run_id, checks)
            if batch is not None and batch.anomaly:
                detected, hits = quality.score_anomaly(batch.anomaly, checks)
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into ecom_ops.injected_anomalies (run_id, batch_id, anomaly_type, rows_affected, "
                        "detected, detected_by) values (%s, %s, %s, %s, %s, %s)",
                        (run_id, ingest.batch_id_for(batch.window_end), batch.anomaly["anomaly_type"],
                         batch.anomaly["rows_affected"], detected, hits),
                    )
            fields["ecom_bytes"] = db.ecom_bytes(conn)
        except Exception as exc:
            conn.rollback()
            status, error = "failed", error or f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

        timer.steps["total"] = round(time.perf_counter() - run_started, 3)
        cols = dict(fields, status=status, error=error, checks_total=len(checks), checks_failed=len(failed),
                    failed_checks=[c.name for c in failed], step_seconds=json.dumps(timer.steps))
        sets = ", ".join(f"{k} = %({k})s" for k in cols)
        with conn.cursor() as cur:
            cur.execute(f"update ecom_ops.pipeline_runs set {sets}, finished_at = now() where run_id = %(run_id)s",
                        dict(cols, run_id=run_id))
        conn.commit()

    summary = {"run_id": run_id, "status": status, "rows_emitted": fields.get("rows_emitted"),
               "rows_inserted": fields.get("rows_inserted"), "duplicates_dropped": fields.get("duplicates_dropped"),
               "checks": len(checks), "failed_checks": [c.name for c in failed],
               "anomaly": batch.anomaly if batch else None, "latency_p50_s": fields.get("latency_p50_s"),
               "ecom_mb": round(fields.get("ecom_bytes", 0) / 1e6, 1), "seconds": timer.steps, "error": error}
    print(json.dumps(summary, default=str, indent=2))
    out = os.environ.get("ECOM_SUMMARY_PATH")
    if out:
        Path(out).write_text(json.dumps(summary, default=str))
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
