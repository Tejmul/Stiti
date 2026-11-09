"""Postgres access. One connection per thread (the alarm scheduler runs in its own thread)."""
from __future__ import annotations

import threading

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .config import CFG

_local = threading.local()


def conn() -> psycopg.Connection:
    c = getattr(_local, "conn", None)
    if c is None or c.closed:
        c = psycopg.connect(CFG.db_url, autocommit=True, row_factory=dict_row)
        register_vector(c)
        _local.conn = c
    return c


def q(sql: str, params=None) -> list[dict]:
    with conn().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def one(sql: str, params=None) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None
