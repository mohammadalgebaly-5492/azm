"""اتصال قاعدة البيانات وتشغيل المهاجرات.

يدعم محركين بنفس الواجهة:
  - SQLite: ملف محلي (التجربة على الجهاز والاختبارات).
  - PostgreSQL (Supabase): عند ضبط DATABASE_URL على رابط يبدأ بـ postgres:// أو postgresql://
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

MIGRATIONS = Path(__file__).parent / "migrations"
PG_MIGRATIONS = MIGRATIONS / "postgres"
# قفل عام لمعاملات الكتابة على Postgres، بنفس سلوك BEGIN IMMEDIATE في SQLite (كاتب واحد في نفس الوقت)
_PG_WRITE_LOCK = 727274

IntegrityError: tuple = (sqlite3.IntegrityError,)
try:
    import psycopg
    IntegrityError += (psycopg.IntegrityError,)
except ImportError:  # psycopg مطلوب فقط مع Postgres
    psycopg = None


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_postgres_url(target: str) -> bool:
    return str(target).startswith(("postgres://", "postgresql://"))


def connect(target: str):
    if is_postgres_url(target):
        return PgConnection(target)
    conn = sqlite3.connect(target, detect_types=0, isolation_level=None, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


# ---------- Postgres ----------

class Row:
    """صف يُقرأ بالاسم أو بالرقم، مثل sqlite3.Row."""
    __slots__ = ("_idx", "_values")

    def __init__(self, idx, values):
        self._idx = idx
        self._values = values

    def __getitem__(self, k):
        return self._values[self._idx[k] if isinstance(k, str) else k]

    def keys(self):
        return list(self._idx)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"Row({dict(zip(self._idx, self._values))!r})"


def _row_factory(cursor):
    idx = {c.name: i for i, c in enumerate(cursor.description or ())}
    return lambda values: Row(idx, values)


def _pg_loaders(adapters):
    """التواريخ ترجع نصوص ISO 8601 كما في SQLite، و jsonb يرجع نصًا كما خُزن."""
    from psycopg.types.datetime import DateLoader, TimestamptzLoader
    from psycopg.types.string import TextLoader

    class IsoTimestamptz(TimestamptzLoader):
        def load(self, data):
            return super().load(data).astimezone(timezone.utc).isoformat(timespec="seconds")

    class IsoDate(DateLoader):
        def load(self, data):
            return super().load(data).isoformat()

    adapters.register_loader("timestamptz", IsoTimestamptz)
    adapters.register_loader("date", IsoDate)
    adapters.register_loader("jsonb", TextLoader)


class PgConnection:
    """غلاف رفيع حول psycopg يقبل علامات ? مثل sqlite3."""

    def __init__(self, url: str):
        if psycopg is None:
            raise RuntimeError("DATABASE_URL يشير إلى Postgres لكن psycopg غير مثبت: pip install -r requirements.txt")
        # prepare_threshold=None: ضروري مع Supabase pooler في وضع transaction (المنفذ 6543)
        self._c = psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=10,
                                  row_factory=_row_factory)
        _pg_loaders(self._c.adapters)

    def execute(self, sql: str, params=()):
        if params:
            return self._c.execute(sql.replace("%", "%%").replace("?", "%s"), params)
        return self._c.execute(sql)

    def close(self):
        self._c.close()


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def tx(db):
    """معاملة ذرية: كل الكتابات أو لا شيء. BEGIN IMMEDIATE يمنع التعارض بين كاتبين."""
    if isinstance(db, PgConnection):
        db.execute("BEGIN")
        db.execute(f"SELECT pg_advisory_xact_lock({_PG_WRITE_LOCK})")
    else:
        db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def migrate(conn) -> list[str]:
    pg = isinstance(conn, PgConnection)
    with tx(conn):
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at "
                     + ("TIMESTAMPTZ NOT NULL DEFAULT now())" if pg else "TEXT NOT NULL)"))
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted((PG_MIGRATIONS if pg else MIGRATIONS).glob("*.sql")):
        if f.name in done:
            continue
        with tx(conn):
            # إعادة الفحص بعد أخذ القفل: نسخة أخرى من التطبيق ربما طبقته للتو
            if conn.execute("SELECT 1 FROM schema_migrations WHERE name = ?", (f.name,)).fetchone():
                continue
            sql = f.read_text(encoding="utf-8")
            if pg:
                conn.execute(sql)
            else:
                # executescript ينفذ COMMIT ضمنيًا؛ لذلك ننفذ الجمل واحدة واحدة داخل المعاملة
                for stmt in _split_sql(sql):
                    conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?)", (f.name, utcnow()))
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


def next_counter(db, key: str) -> int:
    """عداد ذري. يُستدعى داخل tx()."""
    row = db.execute(
        "INSERT INTO counters(key, value) VALUES (?, 1) "
        "ON CONFLICT(key) DO UPDATE SET value = counters.value + 1 RETURNING value",
        (key,),
    ).fetchone()
    return row[0]
