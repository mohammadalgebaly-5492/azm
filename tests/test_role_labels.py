"""مسميات الأدوار الجاهزة كما في الدستور، دون المساس بما غيّره المدير بنفسه."""
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.db import _split_sql, connect, tx

from _db import fresh_database

MIGRATION = Path(__file__).resolve().parent.parent / "app" / "migrations" / "010_role_labels.sql"


class RoleLabelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "a.sqlite3"), "SESSION_COOKIE_SECURE": False,
                               "SECRET_KEY": "t"})
        self.db = connect(self.app.config["DATABASE"])

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def names(self):
        return {r["key"]: (r["name_ar"], r["name_en"]) for r in self.db.execute("SELECT key, name_ar, name_en FROM roles")}

    def test_default_roles_use_constitution_names(self):
        n = self.names()
        self.assertEqual(n["admin"], ("مهندس تحكم تكلفة", "Cost Control Engineer"))
        self.assertEqual(n["director"][0], "المدير التنفيذي")
        self.assertEqual(n["accountant"], ("المحاسبة", "Accounting"))
        self.assertEqual(n["viewer"], ("المشاهد", "Viewer"))

    def test_customised_role_names_are_left_alone(self):
        with tx(self.db):
            self.db.execute("UPDATE roles SET name_ar = 'الكوست كنترول (المسؤول)', name_en = 'Cost Control (Admin)' "
                            "WHERE key = 'admin'")
            self.db.execute("UPDATE roles SET name_ar = 'مدير المالية' WHERE key = 'accountant'")
        with tx(self.db):
            for stmt in _split_sql(MIGRATION.read_text(encoding="utf-8")):
                self.db.execute(stmt)
        n = self.names()
        self.assertEqual(n["admin"], ("مهندس تحكم تكلفة", "Cost Control Engineer"))  # كان على الاسم الافتراضي القديم
        self.assertEqual(n["accountant"][0], "مدير المالية")  # اسم غيّره المدير: لا يُمسّ


if __name__ == "__main__":
    unittest.main()
