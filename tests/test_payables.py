"""المستخلصات والفواتير (البند 4.7) ومستخلصات المالك (البند 4.8)."""
import unittest
from datetime import date, timedelta

from app import billing as B, contracts as C, payables as X, performance as P, procurement as Q, schedule as T
from app.auth import create_user
from app.db import tx
from app.errors import AuthError

from test_contracts import FORM
from test_procurement import ProcBase

TODAY = date.today().isoformat()


class PayBase(ProcBase):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            self.acc, _, _ = create_user(self.db, username="acc", email="a@co.sa", full_name="المحاسب", role="accountant",
                                         password="AccPass12345")

    def order(self, item, kind, qty, prices, ents):
        rid, _ = self.request(item, kind, qty)
        for e, pr in zip(ents, prices):
            self.quote(rid, e, pr)
        low = Q.comparison(self.db, Q.request(self.db, self.pid, rid))["lowest"]
        with self.ctx():
            Q.select_quote(self.db, self.pid, rid, low, "", self.pm2)
            code = Q.cc_approve(self.db, self.pid, rid, self.cost) or Q.director_approve(self.db, self.pid, rid, self.director)
        return self.db.execute("SELECT id FROM commitments WHERE code = ?", (code,)).fetchone()[0]

    def executed(self, item, qty_milli):
        """كمية منجزة من تقرير يومي معتمد."""
        with tx(self.db):
            rid = self.db.execute("INSERT INTO daily_reports(project_id, code, report_date, status, created_at, created_by) "
                                  "VALUES (?, ?, ?, 'approved', ?, ?) RETURNING id",
                                  (self.pid, f"DSR-{item}", TODAY, TODAY, self.pm)).fetchone()[0]
            self.db.execute("INSERT INTO dsr_quantities(report_id, boq_item_id, qty_milli) VALUES (?, ?, ?)", (rid, item, qty_milli))


class Invoices(PayBase):
    def test_three_way_match_approval_and_payment(self):
        cid = self.order(self.small, "material", "10", ["950", "900"], self.sup[:2])        # 9,000 ريال
        inv = {"commitment_id": str(cid), "qty": "6", "vendor_ref": "INV-77"}
        with self.ctx():
            with self.assertRaises(AuthError):  # لا فاتورة قبل الاستلام
                X.raise_payable(self.db, self.pid, inv, self.pm)
            X.add_receipt(self.db, self.pid, {"commitment_id": str(cid), "received_on": TODAY, "qty": "6"}, self.pm)
            with self.assertRaises(AuthError):  # لا استلام فوق المطلوب
                X.add_receipt(self.db, self.pid, {"commitment_id": str(cid), "received_on": TODAY, "qty": "5"}, self.pm)
            code = X.raise_payable(self.db, self.pid, inv, self.pm)
            with self.assertRaises(AuthError):  # المطابقة الثلاثية
                X.raise_payable(self.db, self.pid, {**inv, "qty": "1"}, self.pm)
            xid = self.db.execute("SELECT id FROM payables WHERE code = ?", (code,)).fetchone()[0]
            with self.assertRaises(AuthError):  # من أعدّ لا يعتمد
                X.approve(self.db, self.pid, xid, self.pm)
            X.approve(self.db, self.pid, xid, self.cost)
            with self.assertRaises(AuthError):  # من اعتمد لا يصرف
                X.pay(self.db, self.pid, xid, {"paid_on": TODAY, "paid_ref": "TRX-1"}, self.cost)
            X.pay(self.db, self.pid, xid, {"paid_on": TODAY, "paid_ref": "TRX-1"}, self.acc)
        self.assertEqual(code, f"{self.pcode}-INV-0001")
        x = self.db.execute("SELECT status, net FROM payables WHERE id = ?", (xid,)).fetchone()
        self.assertEqual((x[0], x[1]), ("paid", 540000))
        self.assertEqual(P.indicators(self.db, self.pid)["by_item"][self.small]["ac"], 540000)


class Certificates(PayBase):
    def test_certificate_capped_by_executed_quantity_and_director_above_limit(self):
        cid = self.order(self.big, "subcontract", "500", ["60", "55"], self.sub)            # 27,500 ريال
        form = {"commitment_id": str(cid), "qty": "300", "period_from": TODAY, "period_to": TODAY, "retention_pct": "10"}
        with self.ctx():
            with self.assertRaises(AuthError):  # لا مستخلص بأكثر من المنجز
                X.raise_payable(self.db, self.pid, form, self.pm)
            self.executed(self.big, 400000)
            code = X.raise_payable(self.db, self.pid, form, self.pm)                       # 16,500 − 10%
            xid = self.db.execute("SELECT id FROM payables WHERE code = ?", (code,)).fetchone()[0]
            X.approve(self.db, self.pid, xid, self.cost)
            self.assertEqual(self.db.execute("SELECT status FROM payables WHERE id = ?", (xid,)).fetchone()[0], "cc_approved")
            X.approve(self.db, self.pid, xid, self.director, director=True)
        self.assertEqual(code, f"{self.pcode}-SPC-001")
        x = self.db.execute("SELECT gross, retention, net, status FROM payables WHERE id = ?", (xid,)).fetchone()
        self.assertEqual(tuple(x), (1650000, 165000, 1485000, "approved"))


class OwnerBilling(PayBase):
    def test_draft_from_a_due_payment_then_agree_submit_certify_collect(self):
        with self.ctx():
            C.save_contract(self.db, self.pid, {**FORM, "value_ex_vat": "110,000", "start_on": TODAY}, self.cost)
            start = (date.today() - timedelta(days=10)).isoformat()
            aid, _ = T.add_activity(self.db, self.pid, {"name": "صب الخرسانة", "link": f"item-{self.big}",
                                                        "planned_start": start, "planned_finish": TODAY}, self.pm)
            T.add_milestone(self.db, self.pid, {"description": "الدفعة الأولى", "activity_id": str(aid), "share_pct": "50",
                                                "required_pct": "100"}, self.cost)
            self.assertEqual(B.due_without_certificate(self.db, self.pid), [])
            from app import scope as W
            sid, _ = W.add_step(self.db, self.pid, self.big, {"name": "الصب", "weight_pct": "100", "party": "subcontractor",
                                                              "entity_id": str(self.sub[0])}, self.pm)
            T.finish_step(self.db, self.pid, sid, TODAY, self.pm)
            due = B.due_without_certificate(self.db, self.pid)
            self.assertEqual(len(due), 1)
            code = B.create(self.db, self.pid, {"milestone_id": str(due[0]["m"]["id"])}, self.pm)
            oid = self.db.execute("SELECT id FROM owner_certificates WHERE code = ?", (code,)).fetchone()[0]
            with self.assertRaises(AuthError):  # من أعدّ لا يوافق
                B.advance(self.db, self.pid, oid, "agree", {}, self.pm)
            B.advance(self.db, self.pid, oid, "agree", {}, self.cost)
            B.advance(self.db, self.pid, oid, "submit", {"on": TODAY}, self.pm)
            B.advance(self.db, self.pid, oid, "certify", {"on": TODAY, "amount": "60,000"}, self.pm)
            self.assertEqual(len(B.receivables(self.db, self.pid)), 1)
            B.advance(self.db, self.pid, oid, "collect", {"on": TODAY}, self.acc)
        o = self.db.execute("SELECT gross, retention, advance, vat, net, status FROM owner_certificates WHERE id = ?", (oid,)).fetchone()
        # 55,000 ريال: محتجزات 10%، واسترداد 10%، وضريبة 15%
        self.assertEqual(tuple(o), (5500000, 550000, 550000, 825000, 5225000, "collected"))
        self.assertEqual(code, f"{self.pcode}-IPC-001")

    def test_screens_follow_permissions(self):
        acc, pm = self.client("acc", "AccPass12345"), self.client("pm.one", "PmPass12345")
        from app.projects import add_member
        with self.app.app_context():
            add_member(self.db, self.pid, self.acc, self.cost)
        for c in (acc, pm):
            self.assertEqual(c.get(f"/projects/{self.pid}/payables").status_code, 200)
            self.assertEqual(c.get(f"/projects/{self.pid}/billing").status_code, 200)
        self.assertEqual(acc.post(f"/projects/{self.pid}/billing", data={"csrf_token": self.csrf(acc)}).status_code, 403)
        self.assertEqual(acc.post(f"/projects/{self.pid}/payables/receipts", data={"csrf_token": self.csrf(acc)}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
