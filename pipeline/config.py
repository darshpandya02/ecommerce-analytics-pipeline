"""Central configuration. Everything that shapes the synthetic store lives here."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_ZONE = Path(os.environ.get("ECOM_RAW_ZONE", ROOT / "data" / "raw_zone"))

# Schemas owned by this project. The pipeline never reads or writes anything else.
SCHEMA_RAW = "ecom_raw"
SCHEMA_STAGING = "ecom_staging"
SCHEMA_MARTS = "ecom_marts"
SCHEMA_OPS = "ecom_ops"
OWNED_SCHEMAS = (SCHEMA_RAW, SCHEMA_STAGING, SCHEMA_MARTS, SCHEMA_OPS)

SEED = int(os.environ.get("ECOM_SEED", "2024"))

# The simulated store opens here. The first run backfills from this instant.
STORE_EPOCH = datetime(2026, 8, 24, tzinfo=timezone.utc)

# Generator shape
BUCKET_SECONDS = 300                 # sessions are simulated per 5 minute bucket
SESSIONS_PER_DAY = 700               # average before seasonality multipliers
LOOKBACK_DAYS = 7                    # refunds and late events can surface up to this long after the session
N_PRODUCTS = 150
NEW_CUSTOMER_EVERY_S = 900           # one new customer identity every 15 minutes
LATE_EVENT_RATE = 0.02               # share of events that arrive 30 min to 24 h late
DUPLICATE_RATE = 0.01                # share of events the source sends twice
ANOMALY_RATE = float(os.environ.get("ECOM_ANOMALY_RATE", "0.4"))  # chance a run's batch gets one injected anomaly

# Warehouse housekeeping
RETENTION_DAYS = int(os.environ.get("ECOM_RETENTION_DAYS", "30"))
SIZE_BUDGET_BYTES = 150 * 1024 * 1024

# Expected raw event contract (column set of every landed Parquet batch)
EVENT_COLUMNS = [
    "event_id", "event_type", "event_time", "sent_at", "session_id", "customer_id",
    "device", "channel", "page", "product_id", "quantity", "unit_price",
    "order_id", "amount", "currency", "items", "refund_amount", "reason", "schema_version",
]
EVENT_TYPES = [
    "session_start", "page_view", "product_view", "add_to_cart",
    "checkout_started", "order_placed", "refund_issued",
]


def database_url() -> str:
    for key in ("ECOM_DATABASE_URL", "DATABASE_URL_UNPOOLED", "DATABASE_URL"):
        if os.environ.get(key):
            return os.environ[key]
    raise RuntimeError("Set ECOM_DATABASE_URL (or DATABASE_URL_UNPOOLED) to a Postgres connection string")
