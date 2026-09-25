"""Deterministic synthetic event source for a small online store.

The store is simulated in 5 minute buckets. Each bucket's sessions are a pure function of
(seed, bucket start), so any time window can be reproduced exactly. That makes the source
replayable: the loader only advances its watermark after a commit, and a failed run is
repaired simply by regenerating the same window on the next run.

A batch for window (start, end] contains every event whose *delivery* time falls inside the
window. Delivery is usually seconds after the event, but some events arrive late (mobile
clients reconnecting) and some are delivered twice (at-least-once delivery), exactly the
situations downstream dedup and incremental logic have to handle.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import config

ET = ZoneInfo("America/New_York")

# Relative traffic by local hour (America/New_York). Normalised to mean 1 below.
_HOURLY = [0.35, 0.25, 0.18, 0.15, 0.15, 0.2, 0.35, 0.55, 0.8, 0.95, 1.05, 1.1,
           1.2, 1.15, 1.1, 1.1, 1.15, 1.25, 1.4, 1.6, 1.75, 1.7, 1.3, 0.75]
_HOURLY_MEAN = sum(_HOURLY) / len(_HOURLY)
HOURLY = [h / _HOURLY_MEAN for h in _HOURLY]
WEEKLY = [1.05, 0.97, 0.95, 0.97, 1.0, 0.98, 1.1]  # Monday .. Sunday

# Promotions: (first day, last day, traffic multiplier, conversion multiplier, discount)
PROMOS = [
    (date(2026, 9, 4), date(2026, 9, 7), 1.6, 1.35, 0.15, "labor_day_sale"),
    (date(2026, 9, 18), date(2026, 9, 19), 1.4, 1.25, 0.10, "fall_flash_sale"),
    (date(2026, 10, 9), date(2026, 10, 12), 1.5, 1.3, 0.15, "columbus_day_sale"),
    (date(2026, 11, 27), date(2026, 11, 30), 2.4, 1.6, 0.25, "black_friday"),
]

CATEGORIES = {
    # category: (price low, price high, refund probability, popularity weight)
    "Electronics": (25, 450, 0.07, 1.0),
    "Home": (12, 180, 0.05, 1.1),
    "Apparel": (15, 120, 0.14, 1.3),
    "Beauty": (8, 65, 0.04, 0.9),
    "Sports": (15, 220, 0.06, 0.8),
    "Books": (9, 40, 0.03, 0.6),
}
_ADJ = ["Classic", "Nordic", "Everyday", "Pro", "Compact", "Urban", "Trail", "Studio", "Cloud",
        "Vintage", "Aero", "Lumen", "Core", "Summit", "Harbor", "Cedar"]
_NOUN = {
    "Electronics": ["Earbuds", "Speaker", "Charger", "Keyboard", "Monitor Arm", "Webcam", "Smartwatch"],
    "Home": ["Mug Set", "Throw Blanket", "Lamp", "Cutting Board", "Planter", "Candle", "Towel Set"],
    "Apparel": ["Hoodie", "Tee", "Rain Jacket", "Sneakers", "Beanie", "Chinos", "Socks 3-Pack"],
    "Beauty": ["Face Serum", "Lip Balm", "Shampoo Bar", "Sunscreen", "Hand Cream"],
    "Sports": ["Yoga Mat", "Water Bottle", "Resistance Bands", "Running Belt", "Dumbbell Pair"],
    "Books": ["Cookbook", "Field Guide", "Notebook", "Novel", "Sketchbook"],
}
DEVICES = [("mobile", 0.58, 0.8), ("desktop", 0.35, 1.25), ("tablet", 0.07, 1.0)]
CHANNELS = [("organic", 0.34, 1.0), ("paid_search", 0.22, 1.1), ("direct", 0.18, 1.15),
            ("email", 0.12, 1.35), ("social", 0.14, 0.7)]
COUNTRIES = [("US", 0.70), ("CA", 0.08), ("GB", 0.07), ("DE", 0.05), ("IN", 0.05), ("AU", 0.05)]
PAGES = ["/", "/search", "/category", "/deals", "/new-arrivals"]


def _pick(rng: random.Random, options):
    r = rng.random() * sum(o[1] for o in options)
    for o in options:
        r -= o[1]
        if r <= 0:
            return o
    return options[-1]


def _sid(*parts) -> str:
    return hashlib.sha1(":".join(str(p) for p in parts).encode()).hexdigest()[:20]


@lru_cache(maxsize=4)
def catalog(seed: int = config.SEED) -> tuple[dict, ...]:
    rng = random.Random(f"{seed}:catalog")
    cats = list(CATEGORIES)
    products = []
    for i in range(config.N_PRODUCTS):
        cat = cats[i % len(cats)]
        lo, hi, _, pop = CATEGORIES[cat]
        # log-uniform prices look like a real catalog: many cheap items, a few expensive ones
        price = round(math.exp(rng.uniform(math.log(lo), math.log(hi))), 0) - 0.01
        products.append({
            "product_id": f"p{i + 1:04d}",
            "name": f"{rng.choice(_ADJ)} {rng.choice(_NOUN[cat])}",
            "category": cat,
            "price": round(price, 2),
            # Zipf-like popularity inside the catalog, scaled by category appeal
            "weight": pop / (1 + rng.random() * 12) ** 1.1,
        })
    return tuple(products)


def customer(idx: int, seed: int = config.SEED) -> dict:
    rng = random.Random(f"{seed}:customer:{idx}")
    signup = config.STORE_EPOCH + timedelta(seconds=idx * config.NEW_CUSTOMER_EVERY_S + rng.uniform(0, 600))
    return {
        "customer_id": f"c{idx + 100000:06d}",
        "signup_at": signup,
        "country": _pick(rng, COUNTRIES)[0],
        "acquisition_channel": _pick(rng, CHANNELS)[0],
    }


def promo_for(d: date):
    for first, last, traffic, conv, discount, name in PROMOS:
        if first <= d <= last:
            return traffic, conv, discount, name
    return 1.0, 1.0, 0.0, None


def traffic_rate(t: datetime) -> float:
    """Expected sessions in the bucket starting at t."""
    local = t.astimezone(ET)
    traffic, _, _, _ = promo_for(local.date())
    growth = 1 + 0.004 * max(0.0, (t - config.STORE_EPOCH).total_seconds() / 86400)
    per_bucket = config.SESSIONS_PER_DAY * config.BUCKET_SECONDS / 86400
    return per_bucket * HOURLY[local.hour] * WEEKLY[local.weekday()] * traffic * growth


def _poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


@dataclass
class Emission:
    record: dict
    delivered_at: datetime
    duplicate: bool = False


@dataclass
class Bucket:
    start: datetime
    emissions: list[Emission] = field(default_factory=list)
    customer_idx: set[int] = field(default_factory=set)


def _bucket_start(t: datetime) -> datetime:
    epoch = int(t.timestamp())
    return datetime.fromtimestamp(epoch - epoch % config.BUCKET_SECONDS, tz=timezone.utc)


@lru_cache(maxsize=4096)
def bucket(start: datetime, seed: int = config.SEED) -> Bucket:
    """All events of the sessions that start inside [start, start + 5 min)."""
    b = Bucket(start=start)
    if start < config.STORE_EPOCH:
        return b
    rng = random.Random(f"{seed}:bucket:{int(start.timestamp())}")
    products = catalog(seed)
    weights = [p["weight"] for p in products]
    _, conv_mult, discount, promo = promo_for(start.astimezone(ET).date())

    for s in range(_poisson(rng, traffic_rate(start))):
        t = start + timedelta(seconds=rng.uniform(0, config.BUCKET_SECONDS))
        session_id = f"s{int(start.timestamp())}_{s}"
        device, _, dev_conv = _pick(rng, DEVICES)
        channel, _, ch_conv = _pick(rng, CHANNELS)
        # Returning customers are drawn with an exponential recency preference, which produces
        # realistic decaying cohort retention without keeping any state.
        if rng.random() < 0.62:
            age_s = rng.expovariate(1 / (12 * 86400))
        else:
            age_s = rng.uniform(0, config.NEW_CUSTOMER_EVERY_S)
        idx = max(-5000, math.floor(((t - config.STORE_EPOCH).total_seconds() - age_s) / config.NEW_CUSTOMER_EVERY_S))
        cust = customer(idx, seed)
        b.customer_idx.add(idx)
        conv = conv_mult * dev_conv * ch_conv
        seq = 0
        base = {"session_id": session_id, "customer_id": cust["customer_id"], "device": device,
                "channel": channel, "schema_version": 1}

        def emit(event_type: str, when: datetime, **fields):
            nonlocal seq
            rec = dict.fromkeys(config.EVENT_COLUMNS)
            rec.update(base)
            rec.update(fields)
            rec["event_id"] = _sid(seed, session_id, seq, event_type)
            rec["event_type"] = event_type
            rec["event_time"] = when
            seq += 1
            late_p = config.LATE_EVENT_RATE * (1.6 if device == "mobile" else 0.5)
            if rng.random() < late_p:
                sent = when + timedelta(seconds=rng.uniform(1800, 86400))
            else:
                sent = when + timedelta(seconds=rng.uniform(0.3, 12))
            rec["sent_at"] = sent
            b.emissions.append(Emission(rec, sent))
            if rng.random() < config.DUPLICATE_RATE:
                b.emissions.append(Emission(dict(rec), sent + timedelta(seconds=rng.uniform(1, 900)), True))

        emit("session_start", t, page="/")
        cart: dict[str, dict] = {}
        n_pages = 1 + min(12, int(rng.expovariate(1 / 2.2)))
        for _ in range(n_pages):
            t += timedelta(seconds=rng.expovariate(1 / 35))
            emit("page_view", t, page=rng.choice(PAGES))
            if rng.random() < 0.72:
                p = rng.choices(products, weights=weights)[0]
                t += timedelta(seconds=rng.expovariate(1 / 25))
                emit("product_view", t, page=f"/p/{p['product_id']}", product_id=p["product_id"],
                     unit_price=p["price"])
                if rng.random() < 0.075 * conv:
                    qty = 1 if rng.random() < 0.8 else rng.randint(2, 3)
                    t += timedelta(seconds=rng.expovariate(1 / 20))
                    emit("add_to_cart", t, product_id=p["product_id"], quantity=qty, unit_price=p["price"])
                    line = cart.setdefault(p["product_id"], {"product_id": p["product_id"], "quantity": 0,
                                                             "unit_price": p["price"], "category": p["category"]})
                    line["quantity"] += qty
        if not cart or rng.random() > 0.5:
            continue
        t += timedelta(seconds=rng.expovariate(1 / 40))
        emit("checkout_started", t, page="/checkout")
        if rng.random() > min(0.95, 0.62 * conv):
            continue
        t += timedelta(seconds=rng.expovariate(1 / 60))
        order_id = f"o{_sid(seed, session_id, 'order')[:14]}"
        subtotal = sum(l["quantity"] * l["unit_price"] for l in cart.values())
        total = round(subtotal * (1 - discount) + (0 if subtotal >= 50 else 5.99), 2)
        items = [{k: l[k] for k in ("product_id", "quantity", "unit_price")} for l in cart.values()]
        emit("order_placed", t, page="/checkout/complete", order_id=order_id, amount=total, currency="USD",
             items=json.dumps(items), reason=promo)
        refund_p = max(CATEGORIES[l["category"]][2] for l in cart.values())
        if rng.random() < refund_p:
            rt = t + timedelta(seconds=rng.uniform(6 * 3600, 5 * 86400))
            full = rng.random() < 0.6 or len(items) == 1
            refund = total if full else round(max(l["quantity"] * l["unit_price"] for l in cart.values()), 2)
            emit("refund_issued", rt, order_id=order_id, refund_amount=min(refund, total), currency="USD",
                 reason=rng.choice(["damaged", "wrong_size", "not_as_described", "changed_mind", "late_delivery"]))
    return b


@dataclass
class Batch:
    window_start: datetime
    window_end: datetime
    events: list[dict]
    customers: list[dict]
    products: list[dict]
    duplicates_sent: int
    anomaly: dict | None = None


def generate_window(window_start: datetime, window_end: datetime, seed: int = config.SEED) -> Batch:
    """Every event delivered in (window_start, window_end], in delivery order."""
    window_start = max(window_start, config.STORE_EPOCH)
    first = _bucket_start(window_start - timedelta(days=config.LOOKBACK_DAYS))
    first = max(first, config.STORE_EPOCH)
    out: list[Emission] = []
    cust_idx: set[int] = set()
    t = first
    step = timedelta(seconds=config.BUCKET_SECONDS)
    while t <= window_end:
        b = bucket(t, seed)
        for e in b.emissions:
            if window_start < e.delivered_at <= window_end:
                out.append(e)
                cust_idx.add(int(e.record["customer_id"][1:]) - 100000)
        t += step
    out.sort(key=lambda e: (e.delivered_at, e.record["event_id"]))
    events = [dict(e.record) for e in out]
    customers = [customer(i, seed) for i in sorted(cust_idx)]
    products = [{k: p[k] for k in ("product_id", "name", "category", "price")} for p in catalog(seed)]
    return Batch(window_start, window_end, events, customers, products, sum(e.duplicate for e in out))


# ---------------------------------------------------------------------------------------------
# Anomaly injection. These are the failure modes the quality layer is supposed to catch. The
# ground truth (what was injected, how many rows) is recorded so detection can be scored.
# ---------------------------------------------------------------------------------------------

ANOMALY_TYPES = [
    "schema_new_column",      # producer starts sending an undeclared field
    "schema_renamed_column",  # `amount` silently renamed to `order_total`
    "schema_type_change",     # `amount` sent as a formatted string ("USD 42.00")
    "null_burst",             # identity service outage: customer_id missing
    "duplicate_burst",        # producer retry storm
    "price_spike",            # fat-fingered order amount (x100)
    "volume_drop",            # partial upstream outage, most events never arrive
    "clock_skew_future",      # device clocks two days ahead
    "clock_skew_past",        # events stamped three days in the past
]


def _applicable(kind: str, events: list[dict]) -> bool:
    has_orders = any(e["event_type"] == "order_placed" for e in events)
    if kind in ("schema_renamed_column", "schema_type_change", "price_spike"):
        return has_orders
    return len(events) >= 20


def inject_anomaly(batch: Batch, seed: int = config.SEED, force: str | None = None) -> Batch:
    events = batch.events
    rng = random.Random(f"{seed}:anomaly:{int(batch.window_end.timestamp()) // 60}")
    if (batch.window_end - batch.window_start) > timedelta(hours=6) and not force:
        return batch  # never corrupt a backfill
    if not force and rng.random() >= config.ANOMALY_RATE:
        return batch
    options = [k for k in ANOMALY_TYPES if _applicable(k, events)]
    kind = force if force in options else (None if force else (rng.choice(options) if options else None))
    if not kind:
        return batch  # nothing in this batch the anomaly could affect
    affected = 0
    orders = [e for e in events if e["event_type"] == "order_placed"]
    if kind == "schema_new_column":
        for e in events:
            e["coupon_code"] = rng.choice([None, "FALL10", "WELCOME5"])
        affected = len(events)
    elif kind == "schema_renamed_column":
        for e in events:
            e["order_total"] = e.pop("amount")
        affected = len(orders)
    elif kind == "schema_type_change":
        for e in events:
            if e["amount"] is not None:
                e["amount"] = f"USD {e['amount']:.2f}"
        affected = len(orders)
    elif kind == "null_burst":
        for e in events:
            if rng.random() < 0.35:
                e["customer_id"] = None
                affected += 1
    elif kind == "duplicate_burst":
        dups = [dict(e) for e in events if rng.random() < 0.25]
        events.extend(dups)
        affected = len(dups)
    elif kind == "price_spike":
        o = rng.choice(orders)
        o["amount"] = round(o["amount"] * 100, 2)
        affected = 1
    elif kind == "volume_drop":
        keep = [e for e in events if rng.random() < 0.12]
        affected = len(events) - len(keep)
        events[:] = keep
    elif kind in ("clock_skew_future", "clock_skew_past"):
        shift = timedelta(days=2) if kind == "clock_skew_future" else timedelta(days=-3)
        for e in events:
            if rng.random() < 0.3:
                e["event_time"] = e["event_time"] + shift
                affected += 1
    batch.anomaly = {"anomaly_type": kind, "rows_affected": affected}
    return batch
