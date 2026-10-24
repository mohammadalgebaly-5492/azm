"""دور مدير النظام (System Owner) فوق الكوست كنترول، وجدول إعدادات المنصة، ومصفوفة صلاحيات الأدوار.

SQLite لا يعدّل قيود CHECK بـ ALTER TABLE، فنعدّل تعريف الجدول بالطريقة الموثقة:
https://www.sqlite.org/lang_altertable.html#otheralter (تغيير لا يمس شكل البيانات على القرص).
"""
import json

DEFAULT_PERMISSIONS = [('admin', 'users.manage'), ('admin', 'projects.create'), ('admin', 'projects.manage'), ('admin', 'projects.view_all'), ('admin', 'audit.view'), ('admin', 'boq.manage'), ('director', 'projects.view_all'), ('viewer', 'projects.view_all')]

OLD = "('admin','pm','director','accountant','viewer','owner_rep','consultant')"
NEW = "('superadmin','admin','pm','director','accountant','viewer','owner_rep','consultant')"


def run(db):
    from app.db import utcnow

    version = db.execute("PRAGMA schema_version").fetchone()[0]
    db.execute("PRAGMA writable_schema = ON")
    n = db.execute("UPDATE sqlite_master SET sql = replace(sql, ?, ?) WHERE type = 'table' AND name = 'users'",
                   (OLD, NEW)).rowcount
    db.execute(f"PRAGMA schema_version = {version + 1}")
    db.execute("PRAGMA writable_schema = OFF")
    if n != 1 or NEW not in db.execute("SELECT sql FROM sqlite_master WHERE name = 'users'").fetchone()[0]:
        raise RuntimeError("users role CHECK constraint not updated")

    db.execute("""CREATE TABLE settings (
        key         TEXT PRIMARY KEY,
        value       TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        updated_by  INTEGER REFERENCES users(id)
    )""")

    # صلاحيات كل دور يعدّلها مدير النظام من الواجهة. مدير النظام نفسه له كل الصلاحيات دائمًا ولا يُسجل هنا
    db.execute("""CREATE TABLE role_permissions (
        role        TEXT NOT NULL,
        permission  TEXT NOT NULL,
        PRIMARY KEY (role, permission)
    )""")
    for role, perm in DEFAULT_PERMISSIONS:
        db.execute("INSERT INTO role_permissions(role, permission) VALUES (?, ?)", (role, perm))

    # كل منصة لازم يكون فيها مدير نظام: أقدم أدمن فعّال يُرقّى تلقائيًا، ويُسجل ذلك في السجل
    if db.execute("SELECT 1 FROM users WHERE role = 'superadmin'").fetchone() is None:
        row = db.execute("SELECT id FROM users WHERE role = 'admin' AND status = 'active' ORDER BY id LIMIT 1").fetchone()
        if row:
            db.execute("UPDATE users SET role = 'superadmin' WHERE id = ?", (row[0],))
            db.execute("INSERT INTO audit_log(at, actor_id, action, entity, entity_id, details) VALUES (?,?,?,?,?,?)",
                       (utcnow(), None, "user_updated", "user", row[0],
                        json.dumps({"role": {"from": "admin", "to": "superadmin"},
                                    "reason": "system owner role introduced"})))
