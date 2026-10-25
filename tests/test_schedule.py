"""الجدول الزمني (البند 3.4): الأنشطة وعلاقاتها، والمتوقع من التأخير، والإنجاز من خطوات النطاق، والاعتماد،
وجدول الدفعات التعاقدية (البند 3.2)، وربط التخصيص بالنشاط (القاعدة 2 في البند 3.6)."""
import unittest
from datetime import date, timedelta

from app import contracts as C, schedule as T, scope as W
from app.boq import add_item, add_wbs
from app.errors import AuthError

from test_contracts import FORM
from test_resources import ResourceBase

BASE = date.today() - timedelta(days=60)


def day(n):
    return (BASE + timedelta(days=n)).isoformat()


class ScheduleBase(ResourceBase):
    def setUp(self):
        super().setUp()
        with self.ctx():
            self.w1, _ = add_wbs(self.db, self.pid, "الأساسات", None, self.cost)
            self.w2, _ = add_wbs(self.db, self.pid, "التشطيبات", None, self.cost)
            self.i1, _ = add_item(self.db, self.pid, self.w1, {"description": "حفر", "item_type": "exec", "unit": "م3",
                                                               "qty": "100", "unit_rate": "100"}, self.cost)   # 10,000
            self.i2, _ = add_item(self.db, self.pid, self.w1, {"description": "خرسانة", "item_type": "both", "unit": "م3",
                                                               "qty": "100", "unit_rate": "300"}, self.cost)   # 30,000
            self.i3, _ = add_item(self.db, self.pid, self.w2, {"description": "دهان", "item_type": "both", "unit": "م2",
                                                               "qty": "100", "unit_rate": "600"}, self.cost)   # 60,000

    def act(self, link, start, finish, preds=(), name="نشاط تجريبي"):
        with self.ctx():
            return T.add_activity(self.db, self.pid, {"name": name, "link": link, "planned_start": day(start),
                                                      "planned_finish": day(finish), "predecessors": [str(p) for p in preds]},
                                  self.pm)

    def plan(self):
        """حفر (10 أيام) ← خرسانة (20 يومًا) ← دهان بنشاط على القسم (10 أيام)."""
        a1, c1 = self.act(f"item-{self.i1}", 0, 9, name="حفر")
        a2, c2 = self.act(f"item-{self.i2}", 10, 29, [a1], name="خرسانة")
        a3, c3 = self.act(f"wbs-{self.w2}", 30, 39, [a2], name="التشطيبات")
        return a1, a2, a3


class Activities(ScheduleBase):
    def test_codes_costs_and_loops(self):
        a1, a2, a3 = self.plan()
        codes = [r["code"] for r in T.activities(self.db, self.pid)]
        wcode = self.db.execute("SELECT code FROM wbs_nodes WHERE id = ?", (self.w1,)).fetchone()[0]
        self.assertEqual(codes[:2], [f"{wcode}-A010", f"{wcode}-A020"])
        rows = {r["a"]["id"]: r for r in T.compute(self.db, self.pid, BASE)}
        self.assertEqual([rows[a]["cost"] for a in (a1, a2, a3)], [1000000, 3000000, 6000000])  # القسم يحمل بنده
        with self.ctx():
            with self.assertRaises(AuthError):  # حلقة: الحفر ينتظر التشطيبات
                T.update_activity(self.db, self.pid, a1, {"name": "حفر", "link": f"item-{self.i1}", "planned_start": day(0),
                                                          "planned_finish": day(9), "predecessors": [str(a3)]}, self.pm)
            with self.assertRaises(AuthError):
                self.act(f"item-{self.i1}", 5, 2)

    def test_delay_moves_the_successors_and_progress_comes_from_steps(self):
        a1, a2, a3 = self.plan()
        with self.ctx():
            T.set_actual(self.db, self.pid, a1, {"actual_start": day(0)}, self.pm)
            sid, _ = W.add_step(self.db, self.pid, self.i1, {"name": "حفر", "weight_pct": "60", "party": "crew",
                                                             "crew_id": str(self._crew())}, self.pm)
            T.finish_step(self.db, self.pid, sid, day(5), self.pm)
            with self.assertRaises(AuthError):
                T.set_actual(self.db, self.pid, a1, {"actual_start": day(0), "actual_finish": day(400)}, self.pm)
        now = BASE + timedelta(days=15)  # الحفر لم ينتهِ في يومه العاشر
        rows = {r["a"]["id"]: r for r in T.compute(self.db, self.pid, now)}
        self.assertEqual(rows[a1]["progress"], 6000)
        self.assertEqual(rows[a1]["ff"], now)
        self.assertEqual(rows[a2]["fs"], now + timedelta(days=1))
        self.assertEqual(rows[a3]["variance"], 6)
        self.assertEqual(rows[a2]["status"], "late")
        curve = T.s_curve(self.db, self.pid, list(rows.values()), now)
        self.assertEqual(curve[-1]["planned"], 10000)
        self.assertEqual(max(c["earned"] or 0 for c in curve), 600)  # 60% من 10,000 من أصل 100,000

    def _crew(self):
        from app import resources as S
        from test_resources import person
        leader = S.save_person(self.db, person("نديم أحمد", prof="TEC", title="SFX", cost="230"), self.cost)
        return S.save_crew(self.db, {"name": "طاقم الحفر", "specialty_code": "CNC", "leader_id": str(leader)}, self.cost)


class Approval(ScheduleBase):
    def test_review_then_director_approval_locks_the_plan(self):
        a1, c1 = self.act(f"item-{self.i1}", 0, 9)
        with self.ctx():
            with self.assertRaises(AuthError):  # بنود بلا نشاط
                T.review(self.db, self.pid, self.cost)
            self.act(f"wbs-{self.w1}", 10, 19)
            self.act(f"wbs-{self.w2}", 20, 29)
            T.review(self.db, self.pid, self.cost)
            with self.assertRaises(AuthError):  # من راجع لا يعتمد
                T.approve(self.db, self.pid, self.cost)
            T.approve(self.db, self.pid, self.director)
            with self.assertRaises(AuthError):
                self.act(f"item-{self.i2}", 0, 5)
            T.set_actual(self.db, self.pid, a1, {"actual_start": day(1)}, self.pm)  # الفعلي يُحدَّث بعد الاعتماد
            with self.assertRaises(AuthError):
                T.reopen(self.db, self.pid, "", self.director)
            T.reopen(self.db, self.pid, "تعديل تسلسل الأعمال", self.director)
            self.act(f"item-{self.i2}", 0, 5)

    def test_payment_schedule_follows_the_activities(self):
        with self.ctx():
            C.save_contract(self.db, self.pid, {**FORM, "start_on": day(0)}, self.cost)
        a1, a2, a3 = self.plan()
        with self.ctx():
            code = T.add_milestone(self.db, self.pid, {"description": "الدفعة الأولى: الأساسات", "activity_id": str(a2),
                                                       "share_pct": "40"}, self.cost)
            with self.assertRaises(AuthError):  # المجموع لا يتجاوز 100%
                T.add_milestone(self.db, self.pid, {"description": "الدفعة الثانية", "activity_id": str(a3),
                                                    "share_pct": "70"}, self.cost)
            T.add_milestone(self.db, self.pid, {"description": "الدفعة الثانية", "activity_id": str(a3), "share_pct": "60"},
                            self.cost)
        cc = C.contract_of(self.db, self.pid)["code"]
        self.assertEqual(code, f"{cc}-PAY-01")
        ms = T.milestones(self.db, self.pid, T.compute(self.db, self.pid, BASE + timedelta(days=15)))
        self.assertEqual([m["value"] for m in ms], [40000000, 60000000])
        self.assertEqual(ms[0]["planned"], BASE + timedelta(days=29))
        self.assertEqual(ms[0]["delay"], 15)  # لم يبدأ شيء حتى اليوم الخامس عشر، فتأخرت الدفعة 15 يومًا
        self.assertEqual(ms[0]["expected"], BASE + timedelta(days=44))
        checks = dict((t, ok) for ok, t, _b in T.checks(self.db, self.pid, T.compute(self.db, self.pid)))
        self.assertTrue(any(ok for t, ok in checks.items() if "100%" in t))


class AllocationActivity(ScheduleBase):
    def test_allocation_needs_the_activity_of_its_item(self):
        with self.ctx():
            s = self.staffed(self.pid)
            item = s["item"]
            wid = self.db.execute("SELECT wbs_id FROM boq_items WHERE id = ?", (item,)).fetchone()[0]
            aid, _ = T.add_activity(self.db, self.pid, {"name": "صب القواعد", "link": f"item-{item}",
                                                        "planned_start": "2026-11-01", "planned_finish": "2026-11-07"}, self.pm)
            other, _ = T.add_activity(self.db, self.pid, {"name": "أعمال أخرى", "link": f"item-{self.i3}",
                                                          "planned_start": "2026-11-01", "planned_finish": "2026-11-07"}, self.pm)
            with self.assertRaises(AuthError):
                self.alloc(self.pid, s)
            with self.assertRaises(AuthError):  # نشاط بند آخر
                self.alloc(self.pid, s, activity_id=str(other))
            _id, _c, warnings = self.alloc(self.pid, s, activity_id=str(aid))
        self.assertTrue(any("2026-11-07" in w for w in warnings))  # التخصيص حتى 14 نوفمبر خارج فترة النشاط
        self.assertIsNotNone(wid)


class Screens(ScheduleBase):
    def test_screens_follow_permissions(self):
        a1, a2, a3 = self.plan()
        pm, cost, director = (self.client("pm.one", "PmPass12345"), self.client("cost", "CostPass1234"),
                              self.client("dir", "DirPass12345"))
        for c in (pm, cost, director):
            self.assertEqual(c.get(f"/projects/{self.pid}/schedule").status_code, 200)
            self.assertEqual(c.get(f"/projects/{self.pid}/schedule/{a2}").status_code, 200)
        r = pm.post(f"/projects/{self.pid}/schedule/activities", data={
            "name": "تنظيف نهائي", "link": f"wbs-{self.w2}", "planned_start": day(40), "planned_finish": day(42),
            "csrf_token": self.csrf(pm)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(director.post(f"/projects/{self.pid}/schedule/activities",
                                       data={"csrf_token": self.csrf(director)}).status_code, 403)
        self.assertEqual(pm.post(f"/projects/{self.pid}/schedule/review", data={"csrf_token": self.csrf(pm)}).status_code, 403)
        self.assertEqual(cost.post(f"/projects/{self.pid}/schedule/review", data={"csrf_token": self.csrf(cost)}).status_code, 302)
        self.assertEqual(director.post(f"/projects/{self.pid}/schedule/approve",
                                       data={"csrf_token": self.csrf(director)}).status_code, 302)
        self.assertTrue(T.state(self.db, self.pid)["schedule_approved_at"])


if __name__ == "__main__":
    unittest.main()
