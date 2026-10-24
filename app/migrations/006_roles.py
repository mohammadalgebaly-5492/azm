"""الأدوار تصبح بيانات يديرها مدير النظام: إنشاء، إعادة تسمية، صلاحيات، حذف.

في SQLite نستبدل قيد CHECK على users.role بمرجع إلى جدول roles بنفس طريقة المهاجرة 004.
"""
SEED = [('superadmin', 'SYS', 'مدير النظام', 'System Owner', False, True, 0), ('admin', 'ADM', 'الكوست كنترول (المسؤول)', 'Cost Control (Admin)', False, False, 10), ('pm', 'PM', 'مدير المشروع', 'Project Manager', False, False, 20), ('director', 'DIR', 'الدايركتور', 'Director', False, False, 30), ('accountant', 'ACC', 'المحاسب', 'Accountant', False, False, 40), ('viewer', 'VWR', 'مشاهد (الإدارة العليا)', 'Viewer (Senior Management)', False, False, 50), ('owner_rep', 'OWN', 'ممثل المالك', "Owner's Representative", True, False, 60), ('consultant', 'CON', 'الاستشاري', 'Consultant', True, False, 70)]

CHECK = "CHECK (role IN ('superadmin','admin','pm','director','accountant','viewer','owner_rep','consultant'))"


def run(db):
    db.execute("""CREATE TABLE roles (
        key         TEXT PRIMARY KEY,
        code        TEXT NOT NULL UNIQUE,
        name_ar     TEXT NOT NULL,
        name_en     TEXT NOT NULL,
        external    INTEGER NOT NULL DEFAULT 0,
        system      INTEGER NOT NULL DEFAULT 0,
        sort        INTEGER NOT NULL DEFAULT 100,
        created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    for key, code, ar, en, external, system, sort in SEED:
        db.execute("INSERT INTO roles(key, code, name_ar, name_en, external, system, sort) VALUES (?,?,?,?,?,?,?)",
                   (key, code, ar, en, external, system, sort))

    version = db.execute("PRAGMA schema_version").fetchone()[0]
    db.execute("PRAGMA writable_schema = ON")
    n = db.execute("UPDATE sqlite_master SET sql = replace(sql, ?, ?) WHERE type = 'table' AND name = 'users'",
                   (CHECK, "REFERENCES roles(key)")).rowcount
    db.execute(f"PRAGMA schema_version = {version + 1}")
    db.execute("PRAGMA writable_schema = OFF")
    if n != 1 or "REFERENCES roles(key)" not in db.execute("SELECT sql FROM sqlite_master WHERE name = 'users'").fetchone()[0]:
        raise RuntimeError("users.role constraint not updated")
    db.execute("DELETE FROM role_permissions WHERE role NOT IN (SELECT key FROM roles)")
