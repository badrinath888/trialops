import os
from pathlib import Path
from urllib.parse import quote
import psycopg
from psycopg.rows import dict_row


def secret(name, default=""):
    path = os.getenv(name + "_FILE")
    return Path(path).read_text().strip() if path else os.getenv(name, default)


def connect():
    url = os.getenv("DATABASE_URL")
    if not url:
        url = f"postgresql://trialops:{quote(secret('DB_PASSWORD'),safe='')}@db:5432/trialops"
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=5)


def query(sql, params=()):
    with connect() as c:
        return c.execute(sql, params).fetchall()


def one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None
