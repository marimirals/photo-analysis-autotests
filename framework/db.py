"""Прямой доступ к PostgreSQL сервиса — серый ящик: проверяем то, чего не видно через API,
и готовим тестовые данные, которые через API не создать."""
from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from framework import config


class Db:
    def __init__(self, dsn: str = config.DB_DSN):
        # autocommit: каждый запрос сразу видит свежие данные сервиса
        self.conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row, connect_timeout=5)

    def one(self, sql: str, *params) -> dict | None:
        """Одна строка (или None). Параметры — через %s, никогда не вклеиваем значения в SQL строкой."""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def all(self, sql: str, *params) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def execute(self, sql: str, *params) -> int:
        """Изменение данных; возвращает число затронутых строк."""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def close(self) -> None:
        self.conn.close()


def phash_hex_to_db(hex_value: str) -> int:
    """В API хеш — 16 hex-символов (беззнаковое 64-битное число),
    а в Postgres столбец BIGINT — знаковый. Биты те же, число другое."""
    n = int(hex_value, 16)
    return n - (1 << 64) if n >= (1 << 63) else n
