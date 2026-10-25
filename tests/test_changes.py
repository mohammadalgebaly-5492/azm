"""طلبات التغيير (البند 4.9) وصفحة «مهامي»."""
import unittest

from werkzeug.datastructures import MultiDict

from app import changes as CH, contracts as C, procurement as Q, tasks as TK
from app.errors import AuthError

from test_contracts import FORM
from test_procurement import ProcBase


class Changes(ProcBase):
    def cr(self, kind="internal", amount="2,000", days="0", item=None):
        with self.ctx():
            return CH.create(self.db, self.pid, MultiDict([
                ("kind", kind), ("source", "company"), ("description", "تعديل قطر حديد التسليح حسب ملاحظة الاستشاري"),
                ("items", str(item or self.small)), (f"amount_{item or self.small}", amount), ("days_impact", days)]), self.pm)

    def cid(self, code):
        return self.db.execute("SELECT id FROM change_requests WHERE code = ?", (code,)).fetchone()[0]

    def test_internal_change_adjusts_the_budget(self):
        code = self.cr()
        cid = self.cid(code)
        self.assertEqual(code, f"{self.pcode}-CR-001")
        with self.ctx():
            with self.assertRaises(AuthError):  # من رفع لا يراجع
                CH.advance(self.db, self.pid, cid, self.pm, "pm")
            CH.advance(self.db, self.pid, cid, self.pm2, "pm")
            with self.assertRaises(AuthError):  # من راجع لا يعتمد الخطوة التالية
                CH.advance(self.db, self.pid, cid, self.pm2, "cc")
            CH.advance(self.db, self.pid, cid, self.cost, "cc")
        self.assertEqual(self.db.execute("SELECT status FROM change_requests WHERE id = ?", (cid,)).fetchone()[0], "approved")
        self.assertEqual(Q.available(self.db, self.small), 1200000)

    def test_large_internal_and_contractual_go_to_the_director(self):
        with self.ctx():
            C.save_contract(self.db, self.pid, FORM, self.cost)
        big = self.cid(self.cr(amount="-15,000", item=self.big))
        con = self.cid(self.cr(kind="contractual", amount="25,000", days="15", item=self.big))
        with self.ctx():
            for cid in (big, con):
                CH.advance(self.db, self.pid, cid, self.pm2, "pm")
                CH.advance(self.db, self.pid, cid, self.cost, "cc")
                self.assertEqual(self.db.execute("SELECT status FROM change_requests WHERE id = ?", (cid,)).fetchone()[0],
                                 "dir_review")
            codes = [t["code"] for t in TK.collect(self.db, self._user(self.director))]
            self.assertEqual(sorted(c for c in codes if "-CR-" in c), [f"{self.pcode}-CR-001", f"{self.pcode}-CR-002"])
            CH.advance(self.db, self.pid, big, self.director, "director")
            CH.advance(self.db, self.pid, con, self.director, "director")
        self.assertEqual(Q.available(self.db, self.big), 10000000 - 1500000)
        vo = self.db.execute("SELECT v.status, v.value_delta, v.days_delta FROM change_requests r JOIN variation_orders v "
                             "ON v.id = r.vo_id WHERE r.id = ?", (con,)).fetchone()
        self.assertEqual(tuple(vo), ("study", 2500000, 15))  # أمر تغيير ينتظر موافقة المالك والمدير التنفيذي

    def test_return_and_tasks_page(self):
        cid = self.cid(self.cr())
        from app.projects import add_member
        with self.app.app_context():
            add_member(self.db, self.pid, self.pm2, self.cost)
        with self.ctx():
            self.assertTrue(any(t["code"].endswith("CR-001") for t in TK.collect(self.db, self._user(self.pm2))))
            with self.assertRaises(AuthError):
                CH.send_back(self.db, self.pid, cid, "", self.pm2)
            CH.send_back(self.db, self.pid, cid, "الأثر على التكلفة غير محسوب", self.pm2)
        pm, director = self.client("pm.one", "PmPass12345"), self.client("dir", "DirPass12345")
        for c in (pm, director):
            self.assertEqual(c.get("/tasks").status_code, 200)
            self.assertEqual(c.get(f"/projects/{self.pid}/changes").status_code, 200)
        cid2 = self.cid(self.cr())
        self.assertEqual(director.post(f"/projects/{self.pid}/changes/{cid2}/approve",
                                       data={"csrf_token": self.csrf(director)}).status_code, 403)

    def _user(self, uid):
        return self.db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


if __name__ == "__main__":
    unittest.main()
