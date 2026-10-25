"""التقرير اليومي للموقع (البند 4.3) ومراجعته (البند 4.4)، والقيمة المكتسبة وحالة المشروع بالألوان."""
import unittest
from datetime import date, timedelta

from werkzeug.datastructures import MultiDict

from app import daily as Y, performance as P, resources as S, schedule as T, scope as W
from app.errors import AuthError

from test_resources import ResourceBase

BASE = date.today() - timedelta(days=20)


def day(n):
    return (BASE + timedelta(days=n)).isoformat()


class DailyBase(ResourceBase):
    def setUp(self):
        super().setUp()
        with self.ctx():
            self.s = self.staffed(self.pid)
            self.iid = self.s["item"]
            self.st1, _ = W.add_step(self.db, self.pid, self.iid, {"name": "الشدات والحديد", "weight_pct": "40", "party": "crew",
                                                                    "crew_id": str(self._crew())}, self.cost)
            self.st2, _ = W.add_step(self.db, self.pid, self.iid, {"name": "الصب", "weight_pct": "60", "party": "crew",
                                                                    "crew_id": str(self._crew())}, self.cost)
            self.act, _ = T.add_activity(self.db, self.pid, {"name": "صب القواعد", "link": f"item-{self.iid}",
                                                             "planned_start": day(0), "planned_finish": day(9)}, self.pm)
            self.alloc_id, _, _ = self.alloc(self.pid, self.s, from_date=day(0), to_date=day(9), step_id=str(self.st1),
                                             activity_id=str(self.act), allocation_pct="50")
            S.approve_allocation(self.db, self.pid, self.alloc_id, self.director)

    def _crew(self):
        if not hasattr(self, "_crew_id"):
            self._crew_id = S.save_crew(self.db, {"name": "طاقم الخرسانة", "specialty_code": "CNC",
                                                  "leader_id": str(self.s["pm"])}, self.cost)
        return self._crew_id

    def form(self, n, steps=(), qty="30", hours="8", **kw):
        return MultiDict([("report_date", day(n)), ("activities", str(self.act)), (f"qty_{self.iid}", qty),
                          (f"hours_{self.alloc_id}", hours)] + [("steps", str(x)) for x in steps] + list(kw.items()))


class Reports(DailyBase):
    def test_report_review_and_its_effect_on_progress_and_cost(self):
        with self.ctx():
            rid, code, warns = Y.create_report(self.db, self.pid, self.form(2, [self.st1]), self.pm)
            self.assertEqual(code, f"{self.pcode}-DSR-0001")
            self.assertTrue(any("30" in w for w in warns))  # 30 في اليوم أعلى بكثير من إنتاجية 10
            with self.assertRaises(AuthError):  # يوم واحد بتقرير واحد
                Y.create_report(self.db, self.pid, self.form(2), self.pm)
            with self.assertRaises(AuthError):  # لا تقرير ليوم في المستقبل
                Y.create_report(self.db, self.pid, self.form(40), self.pm)
            with self.assertRaises(AuthError):  # من أعدّ لا يراجع
                Y.approve_report(self.db, self.pid, rid, self.pm)
            self.assertEqual(T.item_progress(self.db, self.pid), {})  # لا يُحسب قبل الاعتماد
            Y.approve_report(self.db, self.pid, rid, self.cost)
            with self.assertRaises(AuthError):
                Y.update_report(self.db, self.pid, rid, self.form(2), self.pm)
        self.assertEqual(T.item_progress(self.db, self.pid), {self.iid: 4000})
        a = self.db.execute("SELECT actual_start, actual_finish FROM activities WHERE id = ?", (self.act,)).fetchone()
        self.assertEqual((str(a[0])[:10], a[1]), (day(2), None))
        self.assertEqual(Y.actual_cost(self.db, self.pid), {self.iid: 50000})  # 8 ساعات من 8 × 500 ريال

    def test_return_then_resubmit_and_finishing_the_item(self):
        with self.ctx():
            rid, _c, _w = Y.create_report(self.db, self.pid, self.form(3, [self.st1, self.st2]), self.pm)
            with self.assertRaises(AuthError):
                Y.return_report(self.db, self.pid, rid, "", self.cost)
            Y.return_report(self.db, self.pid, rid, "الكمية غير مطابقة لمحضر الاستلام", self.cost)
            self.assertEqual(Y.report(self.db, self.pid, rid)["status"], "returned")
            Y.update_report(self.db, self.pid, rid, self.form(3, [self.st1, self.st2], qty="10"), self.pm)
            self.assertEqual(Y.report(self.db, self.pid, rid)["status"], "review")
            Y.approve_report(self.db, self.pid, rid, self.cost)
        a = self.db.execute("SELECT actual_finish FROM activities WHERE id = ?", (self.act,)).fetchone()
        self.assertEqual(str(a[0])[:10], day(3))  # اكتملت خطوات البند، فانتهى النشاط فعليًا

    def test_same_resource_in_two_projects_on_the_same_day_is_flagged(self):
        with self.ctx():
            s2 = self.staffed(self.pid2)
            other, _, _ = self.alloc(self.pid2, s2, rid=self.s["eng"], from_date=day(0), to_date=day(9), allocation_pct="50")
            S.approve_allocation(self.db, self.pid2, other, self.director)
            Y.create_report(self.db, self.pid, self.form(4), self.pm)
            _rid, _c, warns = Y.create_report(self.db, self.pid2, MultiDict([
                ("report_date", day(4)), ("activities", str(T.add_activity(self.db, self.pid2, {
                    "name": "أعمال", "link": f"item-{s2['item']}", "planned_start": day(0), "planned_finish": day(9)},
                    self.pm)[0])), (f"hours_{other}", "4")]), self.pm)
        self.assertTrue(any(self.pcode in w for w in warns))


class Performance(DailyBase):
    def test_earned_value_and_status(self):
        with self.ctx():
            rid, _c, _w = Y.create_report(self.db, self.pid, self.form(2, [self.st1]), self.pm)
            Y.approve_report(self.db, self.pid, rid, self.cost)
        ind = P.indicators(self.db, self.pid)
        m = ind["by_item"][self.iid]
        self.assertEqual((m["bac"], m["pv"], m["ev"], m["ac"]), (1000000, 1000000, 400000, 50000))
        self.assertEqual((m["spi"], m["cpi"]), (4000, 80000))
        self.assertEqual(m["status"], "critical")  # الأسوأ بين الزمن (0.40) والتكلفة (8.0)
        self.assertEqual(P.rag(9600), "green")
        self.assertEqual((P.rag(9400), P.rag(8000), P.rag(6900)), ("yellow", "red", "critical"))
        self.assertEqual(ind["project"]["status"], "critical")
        self.assertEqual(P.most_deviating(ind), [self.iid])

    def test_screens_follow_permissions(self):
        pm, cost, director = (self.client("pm.one", "PmPass12345"), self.client("cost", "CostPass1234"),
                              self.client("dir", "DirPass12345"))
        for url in (f"/projects/{self.pid}/reports", f"/projects/{self.pid}/performance"):
            for c in (pm, cost, director):
                self.assertEqual(c.get(url).status_code, 200, url)
        self.assertEqual(pm.get(f"/projects/{self.pid}/reports/new?report_date={day(2)}").status_code, 200)
        self.assertEqual(director.get(f"/projects/{self.pid}/reports/new").status_code, 403)
        r = pm.post(f"/projects/{self.pid}/reports/new", data={**self.form(2).to_dict(), "csrf_token": self.csrf(pm)})
        self.assertEqual(r.status_code, 302)
        rid = self.db.execute("SELECT id FROM daily_reports").fetchone()[0]
        self.assertEqual(pm.post(f"/projects/{self.pid}/reports/{rid}/approve", data={"csrf_token": self.csrf(pm)}).status_code, 403)
        self.assertEqual(cost.post(f"/projects/{self.pid}/reports/{rid}/approve", data={"csrf_token": self.csrf(cost)}).status_code, 302)
        self.assertIn(f"{self.pcode}-DSR-0001", pm.get(f"/projects/{self.pid}/reports/{rid}").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
