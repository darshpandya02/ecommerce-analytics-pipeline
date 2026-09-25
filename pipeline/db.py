from __future__ import annotations

from contextlib import contextmanager

import psycopg

from . import config


@contextmanager
def connect(autocommit: bool = False):
    conn = psycopg.connect(config.database_url(), autocommit=autocommit, connect_timeout=30,
                           application_name="ecom-pipeline")
    try:
        yield conn
    finally:
        conn.close()


def bootstrap(conn) -> None:
    sql = (config.ROOT / "sql" / "bootstrap.sql").read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def ecom_bytes(conn) -> int:
    """Total on-disk size (tables, indexes, toast) of the ecom_* schemas only."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select coalesce(sum(pg_total_relation_size(c.oid)), 0)
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = any(%s) and c.relkind in ('r', 'm', 'p')
            """,
            (list(config.OWNED_SCHEMAS),),
        )
        return int(cur.fetchone()[0])
