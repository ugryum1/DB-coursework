"""Слой доступа к данным (PostgreSQL)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg2
import psycopg2.extras

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "host":     os.environ.get("PGHOST", "localhost"),
        "port":     int(os.environ.get("PGPORT", "5432")),
        "dbname":   os.environ.get("PGDATABASE", "dietplan"),
        "user":     os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "postgres"),
    }


class DB:
    """Тонкая обёртка вокруг psycopg2 с единым `query`/`execute` API."""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        self.backend = "postgres"
        self.conn = psycopg2.connect(
            host=self.cfg["host"],
            port=self.cfg["port"],
            dbname=self.cfg["dbname"],
            user=self.cfg["user"],
            password=self.cfg["password"],
        )
        self.conn.autocommit = False

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            return rows
        except Exception:
            # psycopg2 при ошибке оставляет транзакцию в aborted-состоянии,
            # из-за чего ВСЕ следующие запросы падают с
            # "current transaction is aborted". Откатываем явно.
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            rowcount = cur.rowcount
            self.conn.commit()
            return rowcount
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        cur = self.conn.cursor()
        try:
            cur.executemany(sql, list(seq))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
