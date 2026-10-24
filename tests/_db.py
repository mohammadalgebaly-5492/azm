"""قاعدة بيانات نظيفة لكل اختبار: SQLite مؤقت افتراضيًا، أو Postgres عند ضبط CC_TEST_DATABASE_URL.

تحذير: مع CC_TEST_DATABASE_URL يُمسح مخطط public بالكامل. لا تستخدمه أبدًا مع قاعدة الإنتاج.
"""
import os


def fresh_database(tmpdir: str, name: str) -> str:
    url = os.environ.get("CC_TEST_DATABASE_URL")
    if not url:
        return os.path.join(tmpdir, name)
    import psycopg
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
    return url
