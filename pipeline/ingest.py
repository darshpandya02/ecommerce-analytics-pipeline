"""Raw zone (Parquet) landing and idempotent load into ecom_raw.

Landing writes the batch exactly as the source delivered it, including any drifted columns.
Loading reads the Parquet file back, inserts events keyed by event_id with ON CONFLICT DO
NOTHING, upserts dimensions, records the file in load_manifest and advances the watermark,
all in one transaction. Re-running a load for the same file is a no-op.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import config
from .generator import Batch

WATERMARK = "events_delivered_through"


def batch_id_for(window_end: datetime) -> str:
    return window_end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def land(batch: Batch, zone: Path = config.RAW_ZONE) -> Path:
    """Write events/customers/products Parquet files for one micro-batch. Returns the batch dir."""
    bid = batch_id_for(batch.window_end)
    d = zone / f"dt={batch.window_end:%Y-%m-%d}" / f"batch={bid}"
    d.mkdir(parents=True, exist_ok=True)
    events = pd.DataFrame.from_records(batch.events)
    if events.empty:
        events = pd.DataFrame(columns=config.EVENT_COLUMNS)
    pq.write_table(pa.Table.from_pandas(events, preserve_index=False), d / "events.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist(batch.customers), d / "customers.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist(batch.products), d / "products.parquet", compression="zstd")
    meta = {"batch_id": bid, "window_start": batch.window_start.isoformat(),
            "window_end": batch.window_end.isoformat(), "rows": len(events)}
    (d / "_batch.json").write_text(json.dumps(meta))
    return d


def read_events(batch_dir: Path) -> pd.DataFrame:
    return pq.read_table(batch_dir / "events.parquet").to_pandas()


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return pd.Timestamp(v).isoformat()
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    return v


@dataclass
class LoadResult:
    batch_id: str
    rows_in_file: int
    rows_inserted: int
    duplicates_dropped: int


def get_watermark(conn) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("select value from ecom_ops.watermarks where name = %s", (WATERMARK,))
        row = cur.fetchone()
    return row[0] if row else None


def load(conn, batch_dir: Path) -> LoadResult:
    meta = json.loads((batch_dir / "_batch.json").read_text())
    events_path = batch_dir / "events.parquet"
    raw = events_path.read_bytes()
    df = read_events(batch_dir)
    core = {"event_id", "event_type", "event_time", "sent_at"}
    rows = []
    for rec in df.to_dict(orient="records"):
        payload = {k: _clean(v) for k, v in rec.items() if k not in core and _clean(v) is not None}
        rows.append((rec["event_id"], rec["event_type"], _clean(rec["event_time"]),
                     _clean(rec.get("sent_at")), json.dumps(payload)))

    with conn.cursor() as cur:
        cur.execute("create temp table _events_in (event_id text, event_type text, event_time timestamptz, "
                    "sent_at timestamptz, payload jsonb) on commit drop")
        with cur.copy("copy _events_in (event_id, event_type, event_time, sent_at, payload) from stdin") as cp:
            for r in rows:
                cp.write_row(r)
        cur.execute(
            """
            insert into ecom_raw.events (event_id, event_type, event_time, sent_at, batch_id, payload)
            select distinct on (event_id) event_id, event_type, event_time, sent_at, %s, payload
            from _events_in order by event_id
            on conflict (event_id) do nothing
            """,
            (meta["batch_id"],),
        )
        inserted = cur.rowcount

        cust = pq.read_table(batch_dir / "customers.parquet").to_pylist()
        if cust:
            cur.executemany(
                """
                insert into ecom_raw.customers (customer_id, signup_at, country, acquisition_channel)
                values (%(customer_id)s, %(signup_at)s, %(country)s, %(acquisition_channel)s)
                on conflict (customer_id) do update set country = excluded.country,
                    acquisition_channel = excluded.acquisition_channel
                where (ecom_raw.customers.country, ecom_raw.customers.acquisition_channel)
                      is distinct from (excluded.country, excluded.acquisition_channel)
                """,
                cust,
            )
        prods = pq.read_table(batch_dir / "products.parquet").to_pylist()
        cur.executemany(
            """
            insert into ecom_raw.products (product_id, name, category, price)
            values (%(product_id)s, %(name)s, %(category)s, %(price)s)
            on conflict (product_id) do update set name = excluded.name, category = excluded.category,
                price = excluded.price, loaded_at = now()
            where (ecom_raw.products.name, ecom_raw.products.category, ecom_raw.products.price)
                  is distinct from (excluded.name, excluded.category, excluded.price)
            """,
            prods,
        )
        cur.execute(
            """
            insert into ecom_raw.load_manifest (batch_id, file_path, file_bytes, sha256, window_start,
                window_end, rows_in_file, rows_inserted, duplicates_dropped)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (batch_id) do update set rows_inserted = ecom_raw.load_manifest.rows_inserted
                + excluded.rows_inserted, loaded_at = now()
            """,
            (meta["batch_id"], str(events_path.relative_to(batch_dir.parent.parent.parent)), len(raw),
             hashlib.sha256(raw).hexdigest(), meta["window_start"], meta["window_end"], len(rows),
             inserted, len(rows) - inserted),
        )
        cur.execute(
            """
            insert into ecom_ops.watermarks (name, value) values (%s, %s)
            on conflict (name) do update set value = greatest(ecom_ops.watermarks.value, excluded.value),
                updated_at = now()
            """,
            (WATERMARK, meta["window_end"]),
        )
    conn.commit()
    return LoadResult(meta["batch_id"], len(rows), inserted, len(rows) - inserted)
