"""الموردون نوع جهة جديد (ENT-SUP-0001)، ودور «المشتريات» (الدستور، المادة 1 والبند 4.2).

في SQLite نعدّل قيد CHECK على entities.kind بنفس طريقة المهاجرة 006.
"""
OLD = "CHECK (kind IN ('owner','consultant','subcontractor'))"
NEW = "CHECK (kind IN ('owner','consultant','subcontractor','supplier'))"


def run(db):
    version = db.execute("PRAGMA schema_version").fetchone()[0]
    db.execute("PRAGMA writable_schema = ON")
    n = db.execute("UPDATE sqlite_master SET sql = replace(sql, ?, ?) WHERE type = 'table' AND name = 'entities'",
                   (OLD, NEW)).rowcount
    db.execute(f"PRAGMA schema_version = {version + 1}")
    db.execute("PRAGMA writable_schema = OFF")
    if n != 1 or NEW not in db.execute("SELECT sql FROM sqlite_master WHERE name = 'entities'").fetchone()[0]:
        raise RuntimeError("entities.kind constraint not updated")
    db.execute("INSERT INTO roles(key, code, name_ar, name_en, external, system, sort) "
               "VALUES ('procurement', 'PRC', 'المشتريات', 'Procurement', 0, 0, 35) ON CONFLICT DO NOTHING")
