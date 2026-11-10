"""Postgres access. One connection per thread (the alarm scheduler runs in its own thread)."""
from __future__ import annotations

import threading
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .config import CFG

_local = threading.local()


def conn() -> psycopg.Connection:
    h = getattr(_local, "held", None)
    if h is not None:                     # a speculative turn: its writes stay invisible until it is committed
        return h.c
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


class Held:
    """One transaction whose writes stay invisible (and undoable) until commit() — for a speculative voice turn
    (D29): inside `with held:` every q()/one()/conn() of THIS thread goes to it. Leaving the block neither commits
    nor rolls back; the caller decides later (from any thread) with commit() or rollback()."""

    def __init__(self):
        self.c = psycopg.connect(CFG.db_url, autocommit=False, row_factory=dict_row)
        register_vector(self.c)
        self._prev = None

    def __enter__(self) -> "Held":
        self._prev = getattr(_local, "held", None)
        _local.held = self
        return self

    def __exit__(self, *exc) -> None:
        _local.held = self._prev

    def commit(self) -> None:
        try:
            self.c.commit()
        finally:
            self.c.close()

    def rollback(self) -> None:
        try:
            self.c.rollback()
        finally:
            self.c.close()


@contextmanager
def unheld():
    """Writes that must land even if the speculative turn around them is thrown away (LLM quota accounting)."""
    h = getattr(_local, "held", None)
    _local.held = None
    try:
        yield
    finally:
        _local.held = h
