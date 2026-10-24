"""اتصال قاعدة البيانات وتشغيل المهاجرات."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

MIGRATIONS = Path(__file__).parent / "migrations"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, detect_types=0, isolation_level=None, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def tx(db: sqlite3.Connection):
    """معاملة ذرية: كل الكتابات أو لا شيء. BEGIN IMMEDIATE يمنع التعارض بين كاتبين."""
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            # executescript ينفذ COMMIT ضمنيًا؛ لذلك ننفذ الجمل واحدة واحدة داخل المعاملة
            for stmt in _split_sql(f.read_text(encoding="utf-8")):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?)", (f.name, utcnow()))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        applied.append(f.name)
    return applied


def _split_sql(sql: str) -> list[str]:
    """يقسم ملف SQL إلى جمل، مع مراعاة كتل TRIGGER ... END;"""
    out, buf = [], []
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        joined = "\n".join(buf)
        if sqlite3.complete_statement(joined):
            out.append(joined)
            buf = []
    if buf and "\n".join(buf).strip():
        out.append("\n".join(buf))
    return out


def next_counter(db: sqlite3.Connection, key: str) -> int:
    """عداد ذري. يُستدعى داخل tx()."""
    row = db.execute(
        "INSERT INTO counters(key, value) VALUES (?, 1) "
        "ON CONFLICT(key) DO UPDATE SET value = value + 1 RETURNING value",
        (key,),
    ).fetchone()
    return row[0]
