"""بوابة بدء التنفيذ (4.1)، والتأخير (4.5)، والإنذار المبكر وخطط التعافي (4.6)، والإغلاق والأرشفة (4.10)."""
import unittest

from app import contracts as C, governance as G, schedule as T, tasks as TK
from app.boq import approve_baseline
from app.errors import AuthError

from test_contracts import FORM
from test_schedule import ScheduleBase


class Governance(ScheduleBase):
    def test_kickoff_needs_baselines_and_every_element(self):
        self.plan()
        with self.ctx():
            for el in list(G.ELEMENTS)[:-1]:
                G.review_element(self.db, self.pid, {"element": el, "decision": "approved"}, self.pm)
            with self.assertRaises(AuthError):  # طلب التغيير إلزامي مع «معتمد مع طلب تغيير»
                G.review_element(self.db, self.pid, {"element": "documents", "decision": "with_cr"}, self.pm)
            G.review_element(self.db, self.pid, {"element": "documents", "decision": "approved"}, self.pm)
            with self.assertRaises(AuthError):  # خطوط الأساس أولًا
                G.start_execution(self.db, self.pid, self.pm)
            approve_baseline(self.db, self.pid, self.cost)
            T.review(self.db, self.pid, self.cost)
            T.approve(self.db, self.pid, self.director)
            code = G.start_execution(self.db, self.pid, self.pm)
        self.assertEqual(code, f"{self.pcode}-KOF")
        self.assertEqual(self.db.execute("SELECT status FROM projects WHERE id = ?", (self.pid,)).fetchone()[0], "active")

    def test_delays_recovery_plans_and_suggestions(self):
        self.plan()
        with self.ctx():
            C.save_contract(self.db, self.pid, FORM, self.cost)
            act = self.db.execute("SELECT id FROM activities WHERE project_id = ? ORDER BY id", (self.pid,)).fetchone()[0]
            owner = G.record_delay(self.db, self.pid, {"activity_id": str(act), "days": "5", "cause": "تأخر اعتماد المخططات",
                                                       "responsible": "consultant"}, self.cost)
            ours = G.record_delay(self.db, self.pid, {"days": "2", "cause": "تعطل الحفار", "responsible": "company"}, self.cost)
            self.assertTrue(G.suggestions(self.db, self.pid, T.compute(self.db, self.pid)))  # أنشطة متأخرة لم تبدأ
            code = G.add_plan(self.db, self.pid, {"option": "overtime", "description": "وردية إضافية لمدة أسبوعين للحفر",
                                                  "days_saved": "4", "extra_cost": "6,000"}, self.pm)
            plan = self.db.execute("SELECT id FROM recovery_plans WHERE code = ?", (code,)).fetchone()[0]
            with self.assertRaises(AuthError):  # المدير التنفيذي بعد مراجعة مهندس تحكم تكلفة
                G.decide_plan(self.db, self.pid, plan, "approve", "", self.director, director=True)
            G.decide_plan(self.db, self.pid, plan, "approve", "", self.cost)
            ids = [t["code"] for t in TK.collect(self.db, self.db.execute("SELECT * FROM users WHERE id = ?",
                                                                            (self.director,)).fetchone())]
            self.assertIn(code, ids)
            G.decide_plan(self.db, self.pid, plan, "approve", "", self.director, director=True)
        self.assertEqual((owner[-7:-4], ours[-7:-4]), ("CLM", "DLY"))
        cost = self.db.execute("SELECT cost_per_day FROM delays WHERE code = ?", (owner,)).fetchone()[0]
        self.assertEqual(cost, 100000)  # غرامة 0.1% يوميًا من مليون ريال
        self.assertFalse(G.plan_due(self.db, self.pid, "red"))

    def test_closeout_makes_the_project_read_only(self):
        self.plan()
        with self.ctx():
            with self.assertRaises(AuthError):  # الدروس المستفادة أولًا
                G.close_project(self.db, self.pid, self.director)
            G.save_lessons(self.db, self.pid, {"lessons": "ابدأ اعتماد المخططات مبكرًا"}, self.pm, "pm")
            G.save_lessons(self.db, self.pid, {"lessons": "سجّل التكلفة الفعلية يوميًا"}, self.cost, "cc")
            report = G.final_report(self.db, self.pid)
            self.assertEqual(report["m"]["bac"], 10000000)
            code = G.close_project(self.db, self.pid, self.director)
        self.assertEqual(code, f"{self.pcode}-CLS")
        pm = self.client("pm.one", "PmPass12345")
        r = pm.post(f"/projects/{self.pid}/schedule/activities", data={"csrf_token": self.csrf(pm), "name": "نشاط جديد"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(pm.get(f"/projects/{self.pid}/closeout").status_code, 200)

    def test_screens(self):
        self.plan()
        for user, pw in (("pm.one", "PmPass12345"), ("dir", "DirPass12345"), ("cost", "CostPass1234")):
            c = self.client(user, pw)
            for url in ("kickoff", "control", "closeout"):
                self.assertEqual(c.get(f"/projects/{self.pid}/{url}").status_code, 200, (user, url))
            self.assertEqual(c.get(f"/projects/{self.pid}").status_code, 200)
        director = self.client("dir", "DirPass12345")
        self.assertEqual(director.post(f"/projects/{self.pid}/control/plans", data={"csrf_token": self.csrf(director)}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
