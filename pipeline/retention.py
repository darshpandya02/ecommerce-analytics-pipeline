"""Keeps the warehouse inside the free-tier budget.

Raw events are kept for RETENTION_DAYS. Incremental facts (orders, refunds, sessions) are
compact, so they are kept for FACT_RETENTION_DAYS, which means marts keep history after the raw
rows behind them are purged. Operational history is trimmed to 90 days.
"""

from __future__ import annotations

from . import config

FACT_RETENTION_DAYS = 180
OPS_RETENTION_DAYS = 90


def _exists(cur, qualified: str) -> bool:
    cur.execute("select to_regclass(%s) is not null", (qualified,))
    return cur.fetchone()[0]


def run(conn) -> int:
    deleted = 0
    with conn.cursor() as cur:
        cur.execute("delete from ecom_raw.events where event_time < now() - make_interval(days => %s)",
                    (config.RETENTION_DAYS,))
        deleted += cur.rowcount
        cur.execute("delete from ecom_raw.load_manifest where window_end < now() - make_interval(days => %s)",
                    (config.RETENTION_DAYS,))
        for table, col in (("ecom_marts.fct_orders", "order_time"), ("ecom_marts.fct_refunds", "refund_time"),
                           ("ecom_staging.int_sessions", "session_start")):
            if _exists(cur, table):
                cur.execute(f"delete from {table} where {col} < now() - make_interval(days => %s)",
                            (FACT_RETENTION_DAYS,))
                deleted += cur.rowcount
        cur.execute("delete from ecom_ops.pipeline_runs where started_at < now() - make_interval(days => %s)",
                    (OPS_RETENTION_DAYS,))
    conn.commit()
    return deleted
