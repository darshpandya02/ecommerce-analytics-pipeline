"""Data-quality layer built on Great Expectations (1.x, ephemeral context).

Three suites run every pipeline run:
  raw_batch       expectations on the landed Parquet micro-batch (contract, nulls, types,
                  ranges, duplicates, timestamps, volume against a seasonal baseline)
  marts           expectations on published mart tables
  reconciliation  revenue in the orders loaded this run vs. revenue published in fct_orders

dbt test and source-freshness results are folded into the same result table, so the dashboard
has one place to read quality from.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")

import great_expectations as gx  # noqa: E402
import pandas as pd  # noqa: E402
from great_expectations.data_context.types.base import ProgressBarsConfig  # noqa: E402

from . import config  # noqa: E402

logging.getLogger("great_expectations").setLevel(logging.ERROR)

MAX_ORDER_AMOUNT = 2500      # largest legitimate basket is ~1,150; see README
MAX_DELIVERY_LAG_H = 25      # late events arrive within 24 h by design of the source
RECON_TOLERANCE = 0.001      # 0.1 % revenue gap allowed between raw and mart
VOLUME_FLOOR = 0.35          # batch must carry >= 35 % of the seasonal baseline

# Which checks are designed to flag which injected anomaly (used to score detection).
DETECTORS = {
    "schema_new_column": {"raw.contract_columns"},
    "schema_renamed_column": {"raw.contract_columns", "raw.amount_present", "recon.run_revenue_gap"},
    "schema_type_change": {"raw.amount_numeric_type", "recon.run_revenue_gap"},
    "null_burst": {"raw.customer_id_not_null", "dbt.not_null_fct_orders_customer_id"},
    "duplicate_burst": {"raw.event_id_uniqueness"},
    "price_spike": {"raw.order_amount_range"},
    "volume_drop": {"raw.volume_vs_baseline"},
    "clock_skew_future": {"raw.no_future_events"},
    "clock_skew_past": {"raw.delivery_lag_within_sla"},
}


@dataclass
class Check:
    suite: str
    name: str
    severity: str
    success: bool
    observed: dict = field(default_factory=dict)


class _GX:
    def __init__(self):
        self.ctx = gx.get_context(mode="ephemeral")
        self.ctx.variables.progress_bars = ProgressBarsConfig(globally=False)
        self.ds = self.ctx.data_sources.add_pandas("pipeline")
        self._n = 0

    def validate(self, df: pd.DataFrame, expectation) -> tuple[bool, dict]:
        self._n += 1
        asset = self.ds.add_dataframe_asset(f"df_{self._n}")
        batch = asset.add_batch_definition_whole_dataframe("all").get_batch(batch_parameters={"dataframe": df})
        r = batch.validate(expectation)
        keep = ("observed_value", "unexpected_count", "unexpected_percent", "element_count", "details",
                "partial_unexpected_list")
        obs = {k: v for k, v in (r.result or {}).items() if k in keep}
        if r.exception_info and r.exception_info.get("raised_exception"):
            obs["exception"] = str(r.exception_info.get("exception_message"))[:300]
        return bool(r.success), json.loads(json.dumps(obs, default=str))


def raw_batch_checks(df: pd.DataFrame, expected_rows: float | None) -> list[Check]:
    g = _GX()
    E = gx.expectations
    out: list[Check] = []

    def run(name, severity, frame, expectation):
        ok, obs = g.validate(frame, expectation)
        out.append(Check("raw_batch", name, severity, ok, obs))

    run("raw.contract_columns", "warn", df,
        E.ExpectTableColumnsToMatchSet(column_set=config.EVENT_COLUMNS, exact_match=True))
    if df.empty:
        return out
    run("raw.event_id_not_null", "error", df, E.ExpectColumnValuesToNotBeNull(column="event_id"))
    run("raw.event_id_uniqueness", "warn", df,
        E.ExpectColumnProportionOfUniqueValuesToBeBetween(column="event_id", min_value=0.95))
    run("raw.event_type_allowed", "warn", df,
        E.ExpectColumnValuesToBeInSet(column="event_type", value_set=config.EVENT_TYPES))
    run("raw.customer_id_not_null", "warn", df, E.ExpectColumnValuesToNotBeNull(column="customer_id", mostly=0.98))
    run("raw.amount_present", "warn", df, E.ExpectColumnToExist(column="amount"))

    orders = df[df["event_type"] == "order_placed"].copy()
    if not orders.empty and "amount" in orders.columns:
        run("raw.amount_numeric_type", "warn", orders,
            E.ExpectColumnValuesToBeInTypeList(column="amount", type_list=["float64", "Float64", "int64", "float"]))
        run("raw.order_amount_not_null", "warn", orders, E.ExpectColumnValuesToNotBeNull(column="amount"))
        numeric = orders.assign(amount_num=pd.to_numeric(orders["amount"], errors="coerce"))
        run("raw.order_amount_range", "warn", numeric,
            E.ExpectColumnValuesToBeBetween(column="amount_num", min_value=0, max_value=MAX_ORDER_AMOUNT))

    t = df.assign(
        clock_ahead_s=(pd.to_datetime(df["event_time"], utc=True) - pd.to_datetime(df["sent_at"], utc=True)).dt.total_seconds(),
    )
    t["delivery_lag_h"] = -t["clock_ahead_s"] / 3600
    run("raw.no_future_events", "warn", t,
        E.ExpectColumnValuesToBeBetween(column="clock_ahead_s", max_value=300))
    run("raw.delivery_lag_within_sla", "warn", t,
        E.ExpectColumnValuesToBeBetween(column="delivery_lag_h", max_value=MAX_DELIVERY_LAG_H, mostly=0.995))
    if expected_rows is not None and expected_rows >= 40:
        run("raw.volume_vs_baseline", "warn", df,
            E.ExpectTableRowCountToBeBetween(min_value=int(expected_rows * VOLUME_FLOOR)))
        out[-1].observed["baseline_rows"] = round(expected_rows, 1)
    return out


def volume_baseline(conn, window_start: datetime, window_end: datetime) -> float | None:
    """Mean number of events delivered in the same clock window on each of the previous 7 days."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(*) / 7.0 from ecom_raw.events e
            join generate_series(1, 7) d(n)
              on e.sent_at > %(s)s - make_interval(days => d.n) and e.sent_at <= %(e)s - make_interval(days => d.n)
            """,
            {"s": window_start, "e": window_end},
        )
        v = cur.fetchone()[0]
    return float(v) if v is not None else None


def mart_checks(conn) -> list[Check]:
    g = _GX()
    E = gx.expectations
    out: list[Check] = []

    def q(sql):
        return pd.read_sql_query(sql, conn)  # small tables only

    daily = q("select day, orders, gross_revenue::float as gross_revenue, net_revenue::float as net_revenue "
              "from ecom_marts.mart_daily_revenue")
    funnel = q("select * from ecom_marts.mart_conversion_funnel")
    cohorts = q("select retention_rate::float as retention_rate from ecom_marts.mart_cohort_retention")

    def run(name, severity, frame, expectation):
        ok, obs = g.validate(frame, expectation)
        out.append(Check("marts", name, severity, ok, obs))

    run("marts.daily_revenue_non_negative", "warn", daily,
        E.ExpectColumnValuesToBeBetween(column="gross_revenue", min_value=0))
    run("marts.daily_revenue_day_unique", "error", daily, E.ExpectColumnValuesToBeUnique(column="day"))
    run("marts.funnel_orders_le_sessions", "warn", funnel,
        E.ExpectColumnPairValuesAToBeGreaterThanB(column_A="sessions", column_B="order_sessions", or_equal=True))
    run("marts.cohort_retention_bounds", "warn", cohorts,
        E.ExpectColumnValuesToBeBetween(column="retention_rate", min_value=0, max_value=1))
    return out


RAW_AMOUNT_SQL = """
    -- The producer's reported total, read leniently: numeric amount, a formatted string, or the
    -- renamed order_total field. This is the "what the source says" side of the reconciliation.
    coalesce(
        case when payload->>'amount' ~ '^-?[0-9]+(\\.[0-9]+)?$' then (payload->>'amount')::numeric end,
        nullif(regexp_replace(payload->>'amount', '[^0-9.\\-]', '', 'g'), '')::numeric,
        case when payload->>'order_total' ~ '^-?[0-9]+(\\.[0-9]+)?$' then (payload->>'order_total')::numeric end
    )
"""


def reconciliation_checks(conn, batch_id: str) -> list[Check]:
    g = _GX()
    E = gx.expectations
    with conn.cursor() as cur:
        cur.execute(
            f"""
            with raw as (
                select event_id, {RAW_AMOUNT_SQL} as amount
                from ecom_raw.events where batch_id = %s and event_type = 'order_placed'
            )
            select count(*), coalesce(sum(r.amount), 0), count(o.order_event_id), coalesce(sum(o.amount), 0)
            from raw r left join ecom_marts.fct_orders o on o.order_event_id = r.event_id
            """,
            (batch_id,),
        )
        raw_n, raw_total, mart_n, mart_total = cur.fetchone()
        cur.execute("select coalesce(sum(gross_revenue), 0) from ecom_marts.mart_daily_revenue")
        mart_daily_total = cur.fetchone()[0]
        cur.execute("select coalesce(sum(amount), 0) from ecom_marts.fct_orders")
        fct_total = cur.fetchone()[0]
    raw_total, mart_total = float(raw_total), float(mart_total)
    gap = abs(raw_total - mart_total) / raw_total if raw_total else 0.0
    frame = pd.DataFrame([{"gap_pct": gap, "missing_orders": raw_n - mart_n,
                           "daily_vs_fct_gap": abs(float(mart_daily_total) - float(fct_total))}])
    out = []
    ok, obs = g.validate(frame, E.ExpectColumnValuesToBeBetween(column="gap_pct", max_value=RECON_TOLERANCE))
    obs.update({"raw_orders": raw_n, "raw_revenue": round(raw_total, 2), "mart_orders": mart_n,
                "mart_revenue": round(mart_total, 2), "gap_pct": round(gap, 6)})
    out.append(Check("reconciliation", "recon.run_revenue_gap", "error", ok, obs))
    ok, obs = g.validate(frame, E.ExpectColumnValuesToBeBetween(column="missing_orders", max_value=0))
    out.append(Check("reconciliation", "recon.run_orders_published", "error", ok, obs))
    ok, obs = g.validate(frame, E.ExpectColumnValuesToBeBetween(column="daily_vs_fct_gap", max_value=0.01))
    out.append(Check("reconciliation", "recon.daily_mart_matches_fct", "error", ok, obs))
    return out


def dbt_checks(target_dir: Path) -> list[Check]:
    """Fold dbt test results and source freshness into Check records."""
    out: list[Check] = []
    rr = target_dir / "run_results.json"
    if rr.exists():
        data = json.loads(rr.read_text())
        mf = target_dir / "manifest.json"
        nodes = json.loads(mf.read_text()).get("nodes", {}) if mf.exists() else {}
        for r in data.get("results", []):
            uid = r.get("unique_id", "")
            if not uid.startswith("test."):
                continue
            name = uid.split(".")[2]
            status = r.get("status")
            sev = str(nodes.get(uid, {}).get("config", {}).get("severity", "warn")).lower()
            out.append(Check("dbt_test", f"dbt.{name}"[:200], sev, status == "pass",
                             {"status": status, "failures": r.get("failures"), "message": (r.get("message") or "")[:200]}))
    return out


def freshness_check(target_dir: Path) -> list[Check]:
    p = target_dir / "sources.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    out = []
    for r in data.get("results", []):
        status = r.get("status")
        out.append(Check("dbt_freshness", f"freshness.{r.get('unique_id', '').split('.')[-1]}",
                         "error" if status == "error" else "warn", status == "pass",
                         {"status": status, "max_loaded_at_time_ago_in_s": r.get("max_loaded_at_time_ago_in_s")}))
    return out


def persist(conn, run_id: int, checks: list[Check]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "insert into ecom_ops.quality_results (run_id, suite, check_name, severity, success, observed) "
            "values (%s, %s, %s, %s, %s, %s)",
            [(run_id, c.suite, c.name, c.severity, c.success, json.dumps(c.observed, default=str)) for c in checks],
        )
    conn.commit()


def score_anomaly(anomaly: dict | None, checks: list[Check]) -> tuple[bool, list[str]] | None:
    if not anomaly:
        return None
    failed = {c.name for c in checks if not c.success}
    hits = sorted(failed & DETECTORS[anomaly["anomaly_type"]])
    return bool(hits), hits
