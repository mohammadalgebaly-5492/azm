"""العقد الرئيسي (الدستور، البند 3.2): البيانات، والتزامن مع المشروع، والضمانات، وأوامر التغيير وحوكمتها."""
import re
import tempfile
import unittest
from datetime import date, timedelta

from app import contracts as C, create_app
from app.auth import create_user
from app.boq import add_item, add_wbs, approve_baseline
from app.db import connect
from app.errors import AuthError
from app.projects import add_member, create_project

from _db import fresh_database

FORM = {"contract_no": "CT-2026-14", "signed_on": "2026-10-20", "kind": "lump_sum", "value_ex_vat": "1,000,000",
        "vat_pct": "15", "scope": "إنشاء مبنى إداري من ثلاثة طوابق", "site_handover_on": "2026-10-28",
        "start_on": "2026-11-01", "duration_days": "365", "warranty_months": "12", "advance_pct": "10",
        "advance_recovery_pct": "10", "retention_pct": "10", "retention_cap_pct": "5", "payment_days": "30",
        "penalty_method": "daily_pct", "penalty_value": "0.1", "penalty_cap_pct": "10"}


class ContractBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "c.sqlite3"), "SESSION_COOKIE_SECURE": False,
                               "SECRET_KEY": "t"})
        self.db = connect(self.app.config["DATABASE"])
        with self.app.app_context():
            self.cost, _, _ = create_user(self.db, username="cost", email="c@co.sa", full_name="مهندس تحكم تكلفة",
                                          role="admin", password="CostPass1234")
            self.director, _, _ = create_user(self.db, username="dir", email="d@co.sa", full_name="المدير التنفيذي",
                                              role="director", password="DirPass12345")
            self.pm, _, _ = create_user(self.db, username="pm.one", email="p@co.sa", full_name="مدير مشروع",
                                        role="pm", password="PmPass12345")
            self.pid, self.pcode = create_project(self.db, {"name": "مبنى إداري", "start_date": "2026-11-01"}, self.cost)
            add_member(self.db, self.pid, self.pm, self.cost)
            add_member(self.db, self.pid, self.director, self.cost)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def contract(self):
        with self.app.test_request_context():
            C.save_contract(self.db, self.pid, FORM, self.cost)
        return C.contract_of(self.db, self.pid)

    def client(self, username, password):
        c = self.app.test_client()
        self.assertEqual(c.post("/login", data={"username": username, "password": password}).status_code, 302)
        return c

    def csrf(self, c):
        return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/").get_data(as_text=True)).group(1)


class ContractData(ContractBase):
    def test_contract_is_coded_computed_and_synced_with_the_project(self):
        c = self.contract()
        self.assertEqual(c["code"], f"{self.pcode}-CON-01")
        self.assertEqual((c["value_ex_vat"], c["vat_bp"], c["retention_bp"], c["penalty_value"]), (100000000, 1500, 1000, 10))
        s = C.summary(self.db, c)
        self.assertEqual((s["current"], s["current_with_vat"], s["advance"]), (100000000, 115000000, 10000000))
        self.assertEqual(s["contractual_end"], "2027-11-01")
        p = self.db.execute("SELECT contract_no, contract_value, end_date FROM projects WHERE id = ?", (self.pid,)).fetchone()
        self.assertEqual((p[0], p[1], str(p[2])[:10]), ("CT-2026-14", 100000000, "2027-11-01"))

    def test_value_and_duration_are_locked_after_budget_approval(self):
        self.contract()
        with self.app.test_request_context():
            wid, _ = add_wbs(self.db, self.pid, "الأعمال", None, self.cost)
            add_item(self.db, self.pid, wid, {"description": "أعمال المبنى", "item_type": "both", "unit": "مقطوعية",
                                              "qty": "1", "unit_rate": "1000000"}, self.cost)
            approve_baseline(self.db, self.pid, self.cost)
            with self.assertRaises(AuthError):
                C.save_contract(self.db, self.pid, {**FORM, "value_ex_vat": "1,200,000"}, self.cost)
            C.save_contract(self.db, self.pid, {**FORM, "payment_days": "45"}, self.cost)  # غير المقفول يتعدل
        self.assertEqual(C.contract_of(self.db, self.pid)["payment_days"], 45)

    def test_validation(self):
        with self.app.test_request_context():
            for bad in ({"vat_pct": "150"}, {"kind": "x"}, {"duration_days": "0"}, {"scope": "قصير"},
                        {"penalty_method": "daily_pct", "penalty_value": ""}, {"advance_pct": "", "advance_recovery_pct": "5"}):
                with self.assertRaises(AuthError, msg=bad):
                    C.save_contract(self.db, self.pid, {**FORM, **bad}, self.cost)


class GuaranteesAndChanges(ContractBase):
    def test_expiring_guarantees_are_flagged_30_days_ahead(self):
        c = self.contract()
        today = date.today()
        with self.app.test_request_context():
            C.add_guarantee(self.db, c["id"], {"kind": "performance", "bank": "البنك الأهلي", "number": "LG-1",
                                               "amount": "50000", "issued_on": (today - timedelta(days=300)).isoformat(),
                                               "expires_on": (today + timedelta(days=20)).isoformat()}, self.cost)
            C.add_guarantee(self.db, c["id"], {"kind": "advance", "bank": "بنك الرياض", "number": "LG-2",
                                               "amount": "100000", "issued_on": today.isoformat(),
                                               "expires_on": (today + timedelta(days=200)).isoformat()}, self.cost)
            C.add_insurance(self.db, c["id"], {"kind": "car", "insurer": "شركة تأمين", "policy_no": "P-9",
                                               "cover_amount": "1000000",
                                               "expires_on": (today - timedelta(days=1)).isoformat()}, self.cost)
        alerts = C.expiring(self.db, c["id"])
        self.assertEqual([(a["ref"], a["days"]) for a in alerts], [("P-9", -1), ("LG-1", 20)])

    def test_change_orders_need_the_director_and_never_touch_the_original_value(self):
        c = self.contract()
        with self.app.test_request_context():
            vid, code = C.add_variation_order(self.db, c["id"], {"description": "أعمال إضافية في السور الخارجي",
                                                                  "issued_on": "2027-01-10", "value_delta": "25,000",
                                                                  "days_delta": "15"}, self.cost)
            with self.assertRaises(AuthError):  # من يُعِد لا يعتمد
                C.decide_variation_order(self.db, c["id"], vid, "approved", "", self.cost)
            C.decide_variation_order(self.db, c["id"], vid, "approved", "", self.director)
            v2, _ = C.add_variation_order(self.db, c["id"], {"description": "حذف أعمال التشجير من النطاق",
                                                              "issued_on": "2027-02-01", "value_delta": "-5000",
                                                              "days_delta": "0"}, self.cost)
            with self.assertRaises(AuthError):  # الرفض يحتاج سببًا
                C.decide_variation_order(self.db, c["id"], v2, "rejected", "", self.director)
        self.assertEqual(code, f"{self.pcode}-VO-001")
        s = C.summary(self.db, C.contract_of(self.db, self.pid))
        self.assertEqual((s["original"], s["vo_total"], s["current"]), (100000000, 2500000, 102500000))
        self.assertEqual(s["current_end"], "2027-11-16")

    def test_screens_follow_permissions(self):
        c = self.contract()
        with self.app.test_request_context():
            vid, _ = C.add_variation_order(self.db, c["id"], {"description": "تعديل في مواصفات الأرضيات",
                                                               "issued_on": "2027-01-10", "value_delta": "10000",
                                                               "days_delta": "0"}, self.cost)
        pm, director = self.client("pm.one", "PmPass12345"), self.client("dir", "DirPass12345")
        page = pm.get(f"/projects/{self.pid}/contract").get_data(as_text=True)
        self.assertIn("CT-2026-14", page)
        self.assertEqual(pm.get(f"/projects/{self.pid}/contract/edit").status_code, 403)
        url = f"/projects/{self.pid}/contract/variations/{vid}/decide"
        self.assertEqual(pm.post(url, data={"csrf_token": self.csrf(pm), "decision": "approved"}).status_code, 403)
        self.assertEqual(director.post(url, data={"csrf_token": self.csrf(director), "decision": "approved"}).status_code, 302)
        self.assertEqual(self.db.execute("SELECT status FROM variation_orders WHERE id = ?", (vid,)).fetchone()[0], "approved")
        cost = self.client("cost", "CostPass1234")
        self.assertEqual(cost.get(f"/projects/{self.pid}/contract/edit").status_code, 200)


if __name__ == "__main__":
    unittest.main()
