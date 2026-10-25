"""تحليل سعر البند (البند 3.3)، ومقارنة التخصيص بسطر التحليل المقابل (القاعدة 5 في البند 3.6)."""
import unittest

from app import pricing as PR
from app.boq import approve_baseline
from app.errors import AuthError

from test_resources import ResourceBase


class Pricing(ResourceBase):
    def test_result_margin_and_lock(self):
        with self.ctx():
            s = self.staffed(self.pid)
            iid = s["item"]                                   # 100 م3 بسعر 100 ريال
            PR.add_line(self.db, self.pid, iid, {"cost_type": "material", "description": "خرسانة جاهزة", "unit": "م3",
                                                 "qty": "1.02", "unit_price": "50"}, self.cost)
            PR.add_line(self.db, self.pid, iid, {"cost_type": "labour", "description": "طاقم الصب", "unit": "يوم",
                                                 "qty": "0.05", "unit_price": "400"}, self.cost)
            PR.set_rates(self.db, self.pid, iid, {"overhead_pct": "10", "profit_pct": "10"}, self.cost)
            item = self.db.execute("SELECT * FROM boq_items WHERE id = ?", (iid,)).fetchone()
            r = PR.result(self.db, item)
            # مباشرة: 51 + 20 = 71 ريال؛ مع 10% غير مباشرة 78.10؛ مقترح 85.91؛ هامش 100 − 78.10
            self.assertEqual((r["direct"], r["cost"], r["proposed"], r["margin"], r["margin_bp"]), (7100, 7810, 8591, 2190, 2190))
            # التخصيص يُقارن بسطر العمالة (20 ريال للوحدة): 12 يومًا × 500 ريال ÷ 100 م3 = 60 ريال
            _aid, _code, warns = self.alloc(self.pid, s)
            self.assertTrue(any("price analysis" in w or "تحليل" in w for w in warns))
            approve_baseline(self.db, self.pid, self.cost)
            with self.assertRaises(AuthError):  # يُقفل مع خط أساس الميزانية
                PR.add_line(self.db, self.pid, iid, {"cost_type": "equipment", "description": "هزاز", "unit": "يوم",
                                                     "qty": "0.05", "unit_price": "80"}, self.cost)
        c = self.client("pm.one", "PmPass12345")
        self.assertEqual(c.get(f"/projects/{self.pid}/pricing").status_code, 200)
        self.assertEqual(c.get(f"/projects/{self.pid}/pricing/{iid}").status_code, 200)
        self.assertEqual(c.post(f"/projects/{self.pid}/pricing/{iid}/rates", data={"csrf_token": self.csrf(c)}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
