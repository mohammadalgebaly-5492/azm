"""مراجعات خط الأساس (البند 4.5)، والتقارير الأسبوعية والشهرية (4.3)، ومؤشرات الفريق (4.4)، ومنحنى التكلفة (3.4)،
والنسخ الورقية الموقّعة (قرار م. محمد)."""
import io
import os
import re
import unittest
from datetime import timedelta
from unittest import mock

from app import authority as A, daily as Y, governance as G, performance as P, periodic as PR, schedule as T, signed as S
from app import tasks as TK
from app.errors import AuthError

from test_daily import DailyBase
from test_payables import PayBase
from test_schedule import ScheduleBase, day

PDF = b"%PDF-1.4\n% signed copy\n"


class SignedCopies(PayBase):
    def setUp(self):
        super().setUp()
        self.app.config["UPLOAD_DIR"] = os.path.join(self.tmp.name, "uploads")

    def sid(self, doc):
        return self.db.execute("SELECT id FROM signed_copies WHERE doc_kind = 'commitment' AND doc_id = ? ORDER BY rev DESC",
                               (doc,)).fetchone()[0]

    def test_cost_control_accepts_and_the_director_too_above_the_limit(self):
        small = self.order(self.small, "material", "10", ["950", "900"], self.sup[:2])   # 9,000 ريال
        big = self.order(self.big, "subcontract", "500", ["60", "55"], self.sub)        # 27,500 ريال
        c = self.client("pm.one", "PmPass12345")
        token = re.search(r'name="csrf_token" value="([^"]+)"', c.get(f"/projects/{self.pid}/payables").get_data(as_text=True)).group(1)
        r = c.post(f"/projects/{self.pid}/signed/commitment/{small}", data={"csrf_token": token, "file": (io.BytesIO(PDF), "po.pdf")},
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        with self.ctx():
            with self.assertRaises(AuthError):  # ملف PDF فقط
                S.upload(self.db, self.pid, "commitment", big, io.BytesIO(b"not a pdf"), "x.pdf", self.pm)
            with self.assertRaises(AuthError):  # نسخة واحدة قيد المراجعة
                S.upload(self.db, self.pid, "commitment", small, io.BytesIO(PDF), "po.pdf", self.pm)
            with self.assertRaises(AuthError):  # من رفع لا يعتمد
                S.decide(self.db, self.pid, self.sid(small), True, "", self.pm)
            S.decide(self.db, self.pid, self.sid(small), True, "", self.cost)
            S.upload(self.db, self.pid, "commitment", big, io.BytesIO(PDF), "sc.pdf", self.pm)
            with self.assertRaises(AuthError):  # الإرجاع بسبب
                S.decide(self.db, self.pid, self.sid(big), False, "", self.cost)
            S.decide(self.db, self.pid, self.sid(big), False, "التوقيع غير واضح", self.cost)
            S.upload(self.db, self.pid, "commitment", big, io.BytesIO(PDF), "sc-2.pdf", self.pm)
            S.decide(self.db, self.pid, self.sid(big), True, "", self.cost)
            director = self.db.execute("SELECT * FROM users WHERE id = ?", (self.director,)).fetchone()
            self.assertTrue(any(t["code"].endswith("SC-001") for t in TK.collect(self.db, director)))
            S.decide(self.db, self.pid, self.sid(big), True, "", self.director, director=True)
        rows = self.db.execute("SELECT doc_id, rev, status FROM signed_copies ORDER BY id").fetchall()
        self.assertEqual([tuple(r) for r in rows], [(small, 1, "accepted"), (big, 1, "returned"), (big, 2, "accepted")])
        cost = self.client("cost", "CostPass1234")
        self.assertIn("S02", cost.get(f"/projects/{self.pid}/payables").get_data(as_text=True))
        r = cost.get(f"/projects/{self.pid}/signed/{self.sid(small)}")
        self.assertEqual((r.mimetype, r.data), ("application/pdf", PDF))

    def test_upload_waits_for_storage_on_the_live_site(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("SUPABASE_")}
        with mock.patch.dict(os.environ, {**env, "VERCEL": "1"}, clear=True):
            self.app.config["UPLOAD_DIR"] = None
            small = self.order(self.small, "material", "10", ["950", "900"], self.sup[:2])
            with self.ctx(), self.assertRaises(AuthError):
                S.upload(self.db, self.pid, "commitment", small, io.BytesIO(PDF), "po.pdf", self.pm)
            page = self.client("pm.one", "PmPass12345").get(f"/projects/{self.pid}/payables").get_data(as_text=True)
            self.assertNotIn('type="file"', page)


class Baselines(ScheduleBase):
    def test_each_approval_saves_a_revision_and_the_original_stays(self):
        a1, a2, a3 = self.plan()
        with self.ctx():
            T.review(self.db, self.pid, self.cost)
            T.approve(self.db, self.pid, self.director)
            with self.assertRaises(AuthError):  # طلب التغيير يجب أن يكون معتمدًا ومن نفس المشروع
                T.reopen(self.db, self.pid, "تأخر توريد الخرسانة", self.director, "999")
            T.reopen(self.db, self.pid, "تأخر توريد الخرسانة", self.director)
            T.update_activity(self.db, self.pid, a3, {"name": "التشطيبات", "link": f"wbs-{self.w2}", "planned_start": day(35),
                                                      "planned_finish": day(44), "predecessors": [str(a2)]}, self.pm)
            T.review(self.db, self.pid, self.cost)
            T.approve(self.db, self.pid, self.director)
        revs = T.baselines(self.db, self.pid)
        self.assertEqual([b["code"] for b in revs], [f"{self.pcode}-BL-R01", f"{self.pcode}-BL-R00"])
        self.assertEqual((revs[0]["reason"], revs[1]["reason"]), ("تأخر توريد الخرسانة", None))
        cmp = T.compare(self.db, self.pid, 1)
        self.assertEqual((cmp["finish_shift"], cmp["budget_change"]), (5, 0))
        self.assertEqual([a["shift"] for a in cmp["activities"] if a["code"].endswith("A010") and a["name"] == "التشطيبات"], [5])
        c = self.client("dir", "DirPass12345")
        self.assertEqual(c.get(f"/projects/{self.pid}/schedule/baselines/1").status_code, 200)
        self.assertEqual(c.get(f"/projects/{self.pid}/schedule/baselines/7").status_code, 404)

    def test_weekly_and_monthly_reports_appear_by_themselves(self):
        self.plan()  # يبدأ قبل 60 يومًا
        weeks, months = PR.periods(self.db, self.pid, "weekly"), PR.periods(self.db, self.pid, "monthly")
        self.assertTrue(weeks[0]["current"] and not weeks[1]["current"])
        self.assertTrue(all(w["end"].weekday() == 5 for w in weeks) and 9 <= len(weeks) <= 11)
        self.assertIn(len(months), (2, 3, 4))
        with self.ctx():
            r = PR.build(self.db, self.pid, "weekly", weeks[1]["end"])
            self.assertGreater(r["m"]["pv"], 0)
            self.assertIsNone(PR.build(self.db, self.pid, "weekly", weeks[1]["end"] + timedelta(days=1)))
        c = self.client("pm.one", "PmPass12345")
        self.assertEqual(c.get(f"/projects/{self.pid}/status-reports").status_code, 200)
        self.assertEqual(c.get(f"/projects/{self.pid}/status-reports/monthly/{months[-1]['end']}").status_code, 200)
        self.assertEqual(c.get(f"/projects/{self.pid}/status-reports/yearly/{months[-1]['end']}").status_code, 404)
        self.assertEqual(c.get(f"/projects/{self.pid}/schedule").status_code, 200)


class TeamsAndCost(DailyBase):
    def test_team_indicators_cost_curve_and_daily_overhead(self):
        with self.ctx():
            rid, _c, _w = Y.create_report(self.db, self.pid, self.form(2, [self.st1]), self.pm)
            Y.approve_report(self.db, self.pid, rid, self.cost)
            with self.assertRaises(AuthError):
                G.set_overhead(self.db, self.pid, "-5", self.cost)
            G.set_overhead(self.db, self.pid, "1,500", self.cost)
            self.assertEqual(G.delay_cost_per_day(self.db, self.pid)["overhead"], 150000)
        team = [t for t in A.team_cards(self.db) if t["project"]["id"] == self.pid][0]
        self.assertEqual((team["members"], team["reports"], team["accuracy"]), (1, 1, 10000))
        curve = P.cost_curve(self.db, self.pid, T.compute(self.db, self.pid))
        actual = [c["actual"] for c in curve if c["actual"] is not None]
        self.assertGreater(actual[-1], 0)
        self.assertEqual(actual[-1], P.indicators(self.db, self.pid)["project"]["ac"])
        self.assertEqual(self.client("cost", "CostPass1234").get("/engineers").status_code, 200)


if __name__ == "__main__":
    unittest.main()
