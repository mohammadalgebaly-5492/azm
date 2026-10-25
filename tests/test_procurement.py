"""المشتريات والتعاقد (البند 4.2): الطلب، والعروض، والاختيار، والاعتماد حسب الحدود، والالتزام على ميزانية البند."""
import unittest
from datetime import date, timedelta

from werkzeug.datastructures import MultiDict

from app import documents as D, procurement as Q, registers as R
from app.auth import create_user
from app.boq import add_item, add_wbs
from app.errors import AuthError

from test_resources import ResourceBase

VALID = (date.today() + timedelta(days=30)).isoformat()


class ProcBase(ResourceBase):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            self.pm2, _, _ = create_user(self.db, username="pm.two", email="p2@co.sa", full_name="مدير مشروع ثان",
                                         role="pm", password="PmPass12345")
            self.buyer, _, _ = create_user(self.db, username="buyer", email="b@co.sa", full_name="المشتريات",
                                           role="procurement", password="BuyPass12345")
        with self.ctx():
            wid, _ = add_wbs(self.db, self.pid, "الهيكل", None, self.cost)
            self.small, _ = add_item(self.db, self.pid, wid, {"description": "حديد تسليح", "item_type": "supply", "unit": "طن",
                                                              "qty": "10", "unit_rate": "1000"}, self.cost)       # 10,000 ريال
            self.big, _ = add_item(self.db, self.pid, wid, {"description": "صب خرسانة", "item_type": "exec", "unit": "م3",
                                                            "qty": "1000", "unit_rate": "100"}, self.cost)       # 100,000 ريال
            self.doc, _ = D.create_document(self.db, self.pid, {"title": "مخطط الهيكل", "doc_type": "DRW", "issuer": "consultant",
                                                                "issued_on": "2026-10-01"}, self.cost)
            self.sup = [self._vendor("supplier", f"مورد {n}", f"s{n}@v.sa") for n in (1, 2, 3)]
            self.sub = [self._vendor("subcontractor", f"مقاول {n}", f"c{n}@v.sa") for n in (1, 2)]

    def _vendor(self, kind, name, email):
        form = MultiDict([("name", name), ("email", email), ("cr_no", "1010"), ("vat_no", "3000"),
                          ("approval_status", "approved"), ("specialties", "CNC")])
        return R.create_entity(self.db, kind, form, self.cost)[0]

    def request(self, item=None, kind="material", qty="10"):
        with self.ctx():
            return Q.create_request(self.db, self.pid, MultiDict([
                ("kind", kind), ("boq_item_id", str(item or self.small)), ("scope", "توريد حديد تسليح قطر 16 مم"),
                ("qty", qty), ("needed_on", "2026-11-15"), ("documents", str(self.doc))]), self.pm)

    def quote(self, rid, ent, price, ev="compliant"):
        with self.ctx():
            return Q.add_quote(self.db, self.pid, rid, {"entity_id": str(ent), "unit_price": price, "duration_days": "7",
                                                        "payment_terms": "30 يومًا من الاستلام", "valid_until": VALID,
                                                        "evaluation": ev}, self.buyer)


class Requests(ProcBase):
    def test_request_and_quotes_validation(self):
        with self.ctx():
            with self.assertRaises(AuthError):  # المرفقات إلزامية
                Q.create_request(self.db, self.pid, {"kind": "material", "boq_item_id": str(self.small),
                                                     "scope": "توريد حديد تسليح", "qty": "5", "needed_on": "2026-11-15"}, self.pm)
        rid, code = self.request()
        self.assertEqual(code, f"{self.pcode}-PR-0001")
        qcode = self.quote(rid, self.sup[0], "950")
        self.assertEqual(qcode, f"{self.pcode}-QT-0001")
        with self.ctx():
            with self.assertRaises(AuthError):  # طلب مواد: موردون فقط
                self.quote(rid, self.sub[0], "900")
            with self.assertRaises(AuthError):  # عرض واحد لكل جهة
                self.quote(rid, self.sup[0], "900")
            with self.assertRaises(AuthError):  # لا يُختار بأقل من عرضين
                Q.select_quote(self.db, self.pid, rid, 1, "", self.pm2)
        self.assertEqual(Q.quotes(self.db, rid)[0]["total"], 950000)  # 10 طن × 950 ريال

    def test_choosing_rules_and_small_order_by_cost_control_alone(self):
        rid, _ = self.request()
        self.quote(rid, self.sup[0], "980")
        self.quote(rid, self.sup[1], "950")
        self.quote(rid, self.sup[2], "900", ev="non_compliant")
        qs = {q["entity_id"]: q["id"] for q in Q.quotes(self.db, rid)}
        with self.ctx():
            with self.assertRaises(AuthError):  # من رفع لا يختار
                Q.select_quote(self.db, self.pid, rid, qs[self.sup[1]], "", self.pm)
            with self.assertRaises(AuthError):  # غير المطابق لا يُختار
                Q.select_quote(self.db, self.pid, rid, qs[self.sup[2]], "أرخص", self.pm2)
            with self.assertRaises(AuthError):  # غير الأقل يحتاج سببًا
                Q.select_quote(self.db, self.pid, rid, qs[self.sup[0]], "", self.pm2)
            Q.select_quote(self.db, self.pid, rid, qs[self.sup[1]], "", self.pm2)
            with self.assertRaises(AuthError):  # من اختار لا يعتمد
                Q.cc_approve(self.db, self.pid, rid, self.pm2)
            code = Q.cc_approve(self.db, self.pid, rid, self.cost)
        self.assertEqual(code, f"{self.pcode}-PO-0001")
        self.assertEqual(Q.request(self.db, self.pid, rid)["status"], "approved")
        self.assertEqual(Q.available(self.db, self.small), 1000000 - 950000)


class Limits(ProcBase):
    def _chosen(self, item, kind, qty, prices, ents):
        rid, _ = self.request(item, kind, qty)
        for e, pr in zip(ents, prices):
            self.quote(rid, e, pr)
        low = Q.comparison(self.db, Q.request(self.db, self.pid, rid))["lowest"]
        with self.ctx():
            Q.select_quote(self.db, self.pid, rid, low, "", self.pm2)
        return rid

    def test_above_the_limit_needs_the_director_and_issues_a_subcontract(self):
        rid = self._chosen(self.big, "subcontract", "500", ["60", "55"], self.sub)  # 27,500 ريال
        with self.ctx():
            self.assertIsNone(Q.cc_approve(self.db, self.pid, rid, self.cost))
            self.assertEqual(Q.request(self.db, self.pid, rid)["status"], "cc_approved")
            with self.assertRaises(AuthError):  # من اعتمد أولًا لا يعتمد ثانيًا
                Q.director_approve(self.db, self.pid, rid, self.cost)
            code = Q.director_approve(self.db, self.pid, rid, self.director)
        self.assertEqual(code, f"{self.pcode}-SC-001")

    def test_budget_and_splitting(self):
        rid = self._chosen(self.small, "material", "10", ["1200", "1150"], self.sup[:2])  # 11,500 > ميزانية 10,000
        with self.ctx():
            with self.assertRaises(AuthError):  # لا التزام بدون ميزانية
                Q.cc_approve(self.db, self.pid, rid, self.cost)
            Q.return_request(self.db, self.pid, rid, "العروض أعلى من الميزانية", self.cost)
        self.assertEqual(Q.request(self.db, self.pid, rid)["status"], "returned")
        self.assertIsNone(Q.request(self.db, self.pid, rid)["selected_quote_id"])
        # أمران لنفس البند ونفس المورد خلال 30 يومًا: الثاني يحتاج المدير التنفيذي إذا تجاوز المجموع 10,000 ريال
        first = self._chosen(self.big, "material", "80", ["100", "90"], self.sup[:2])        # 7,200 ريال
        with self.ctx():
            self.assertTrue(Q.cc_approve(self.db, self.pid, first, self.cost))
        second = self._chosen(self.big, "material", "50", ["100", "90"], self.sup[:2])       # 4,500 ريال
        with self.ctx():
            self.assertIsNone(Q.cc_approve(self.db, self.pid, second, self.cost))
        self.assertTrue(Q.request(self.db, self.pid, second)["needs_director"])


class Screens(ProcBase):
    def test_screens_follow_permissions(self):
        rid, _ = self.request()
        buyer, pm, director = (self.client("buyer", "BuyPass12345"), self.client("pm.one", "PmPass12345"),
                               self.client("dir", "DirPass12345"))
        self.add_member_for_buyer()
        self.assertEqual(pm.get(f"/projects/{self.pid}/procurement/new").status_code, 200)
        self.assertEqual(buyer.get(f"/projects/{self.pid}/procurement/new").status_code, 403)
        r = buyer.post(f"/projects/{self.pid}/procurement/{rid}/quotes", data={
            "entity_id": str(self.sup[0]), "unit_price": "950", "duration_days": "7", "payment_terms": "30 يومًا",
            "valid_until": VALID, "evaluation": "compliant", "csrf_token": self.csrf(buyer)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(Q.quotes(self.db, rid)), 1)
        self.assertEqual(pm.post(f"/projects/{self.pid}/procurement/{rid}/approve",
                                 data={"csrf_token": self.csrf(pm)}).status_code, 403)
        for c in (pm, director):
            self.assertEqual(c.get(f"/projects/{self.pid}/procurement").status_code, 200)
            self.assertEqual(c.get(f"/projects/{self.pid}/procurement/{rid}").status_code, 200)

    def add_member_for_buyer(self):
        from app.projects import add_member
        with self.app.app_context():
            add_member(self.db, self.pid, self.buyer, self.cost)


if __name__ == "__main__":
    unittest.main()
