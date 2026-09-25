"""Create (or rotate) the read-only role the dashboard connects with.

The role can read ecom_marts and ecom_ops and nothing else. Password comes from the
ECOM_READER_PASSWORD environment variable; it is never written to disk by this script.

    ECOM_READER_PASSWORD=... uv run python scripts/create_readonly_role.py
"""

import os

import psycopg
from psycopg import sql

from pipeline import config, db

ROLE = "ecom_reader"
READABLE = ("ecom_marts", "ecom_ops")


def main() -> None:
    password = os.environ["ECOM_READER_PASSWORD"]
    with psycopg.connect(config.database_url(), autocommit=True) as conn:
        db.bootstrap(conn)
        cur = conn.cursor()
        cur.execute("select 1 from pg_roles where rolname = %s", (ROLE,))
        verb = "alter" if cur.fetchone() else "create"
        cur.execute(sql.SQL(verb + " role {} with login password {} nocreatedb nocreaterole")
                    .format(sql.Identifier(ROLE), sql.Literal(password)))
        cur.execute(sql.SQL("alter role {} set default_transaction_read_only = on").format(sql.Identifier(ROLE)))
        cur.execute(sql.SQL("alter role {} set statement_timeout = '5s'").format(sql.Identifier(ROLE)))
        for schema in READABLE:
            ident = dict(s=sql.Identifier(schema), r=sql.Identifier(ROLE))
            cur.execute(sql.SQL("grant usage on schema {s} to {r}").format(**ident))
            cur.execute(sql.SQL("grant select on all tables in schema {s} to {r}").format(**ident))
            # dbt recreates mart tables on every build; default privileges keep the grant alive
            cur.execute(sql.SQL("alter default privileges in schema {s} grant select on tables to {r}").format(**ident))
        print(f"{verb}d role {ROLE} with select on {', '.join(READABLE)}")


if __name__ == "__main__":
    main()
