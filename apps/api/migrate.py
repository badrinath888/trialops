"""Transactional, checksum-verified additive migrations; backup before live deployment."""

import hashlib
from pathlib import Path
from db import connect


def migrate():
    root = Path(__file__).with_name("migrations")
    if not root.exists():
        root = Path(__file__).resolve().parents[2] / "database/migrations"
    with connect() as c:
        c.execute("SELECT pg_advisory_xact_lock(82419731)")
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY,sha256 TEXT NOT NULL,applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        for file in sorted(root.glob("*.sql")):
            sql = file.read_text()
            sha = hashlib.sha256(sql.encode()).hexdigest()
            old = c.execute(
                "SELECT sha256 FROM schema_migrations WHERE name=%s", (file.name,)
            ).fetchone()
            if old:
                if old["sha256"] != sha:
                    raise RuntimeError(
                        "Applied migration checksum changed: " + file.name
                    )
                continue
            c.execute(sql)
            c.execute(
                "INSERT INTO schema_migrations(name,sha256) VALUES(%s,%s)",
                (file.name, sha),
            )
            from workflows import remember_existing

            remember_existing(c)
            print("Applied " + file.name, flush=True)


if __name__ == "__main__":
    migrate()
