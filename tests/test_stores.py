"""المخزن الرئيسي والسقالات (طلب م. محمد 2026-10-26): الوارد والصرف والتركيب والفك والإرجاع والتالف، والإيجار اليومي."""
import re
import unittest
from datetime import date, timedelta

from app import performance as P, stores as ST
from app.errors import AuthError
from app.projects import add_member

from test_payables import PayBase


def day(n):
    return (date.today() - timedelta(days=n)).isoformat()


class Scaffolding(PayBase):
    def move(self, actor, kind, qty, on, pid=None, item=None, place=None, reason=None, code="STD"):
        form = {"kind": kind, "material_code": code, "qty": str(qty), "on_date": on, "boq_item_id": str(item or ""),
                "place": place or "", "reason": reason or ""}
        with self.ctx():
            return ST.record(self.db, form, actor, pid)

    def test_store_site_and_installed_quantities_with_daily_rent(self):
        self.assertEqual(len(ST.components(self.db)), 17)
        self.move(self.buyer, "receive", 100, day(20))
        self.move(self.buyer, "issue", 60, day(10), self.pid, self.big)
        with self.assertRaises(AuthError):  # لا صرف فوق رصيد المخزن
            self.move(self.buyer, "issue", 50, day(10), self.pid, self.big)
        self.move(self.pm, "install", 50, day(9), self.pid, self.big)
        with self.assertRaises(AuthError):  # لا تركيب فوق الموجود في الموقع
            self.move(self.pm, "install", 20, day(9), self.pid, self.big)
        self.move(self.pm, "dismantle", 10, day(5), self.pid, self.big)
        with self.assertRaises(AuthError):  # الإرجاع من غير المركّب فقط
            self.move(self.buyer, "return", 30, day(4), self.pid, self.big)
        self.move(self.buyer, "return", 20, day(4), self.pid, self.big)
        with self.assertRaises(AuthError):  # التالف بسبب
            self.move(self.pm, "loss", 5, day(3), self.pid, self.big, place="use")
        self.move(self.pm, "loss", 5, day(3), self.pid, self.big, place="use", reason="سقوط أثناء الفك")
        with self.assertRaises(AuthError):  # لا تاريخ في المستقبل
            self.move(self.buyer, "receive", 5, (date.today() + timedelta(days=1)).isoformat())
        self.assertEqual(ST.store_balance(self.db)["STD"], {"store": 60, "out": 35, "use": 35})
        self.assertEqual(ST.project_balance(self.db, self.pid)[(self.big, "STD")], {"out": 35, "use": 35, "site": 0})
        # 60 قطعة × 6 أيام + 40 × يوم + 35 × 4 أيام حتى اليوم، بريال للقطعة في اليوم
        self.assertEqual(ST.cost_by_item(self.db, self.pid), {self.big: (60 * 6 + 40 * 1 + 35 * 4) * 100})
        self.assertEqual(P.indicators(self.db, self.pid)["by_item"][self.big]["ac"], (60 * 6 + 40 + 35 * 4) * 100)
        self.assertEqual(ST.daily_rent(self.db, self.pid), 35 * 100)

    def test_screens_follow_permissions(self):
        with self.app.app_context():
            add_member(self.db, self.pid, self.buyer, self.cost)
            add_member(self.db, self.pid, self.acc, self.cost)
        self.move(self.buyer, "receive", 40, day(5), code="BJK")
        pm, buyer = self.client("pm.one", "PmPass12345"), self.client("buyer", "BuyPass12345")
        url = f"/projects/{self.pid}/scaffolding"
        self.assertEqual(pm.get(url).status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', pm.get(url).get_data(as_text=True)).group(1)
        form = {"csrf_token": token, "kind": "issue", "material_code": "BJK", "qty": "10", "on_date": day(2),
                "boq_item_id": str(self.big)}
        self.assertEqual(pm.post(url + "/moves", data=form).status_code, 403)       # الصرف لأمين المخزن
        token = re.search(r'name="csrf_token" value="([^"]+)"', buyer.get(url).get_data(as_text=True)).group(1)
        self.assertEqual(buyer.post(url + "/moves", data={**form, "csrf_token": token}).status_code, 302)
        self.assertEqual(buyer.post(url + "/moves", data={**form, "csrf_token": token, "kind": "install"}).status_code, 403)
        self.assertEqual(ST.project_balance(self.db, self.pid)[(self.big, "BJK")]["out"], 10)
        self.assertEqual(self.client("cost", "CostPass1234").get("/stores").status_code, 200)
        self.assertEqual(self.client("acc", "AccPass12345").get("/stores").status_code, 403)
        self.assertEqual(self.client("cost", "CostPass1234").get("/registers/lists?kind=material").status_code, 200)


if __name__ == "__main__":
    unittest.main()
